import re
import unittest
from pathlib import Path

from nesting.dxf import Hole, Shape, read_dxf
from nesting.geometry import Arc, Line, OffsetError, bbox
from nesting.layout import PanelPlan, PlacedShape, PlacedTemplate, Plan, ShapeEntry, build_plan, footprint, to_panel
from nesting.program import ContourOp, DrillOp, base_label, pass_depths, plan_programs, stack_top
from nesting.settings import Settings

repo = Path(__file__).resolve().parent.parent
FOLDER = set('79ABCDEFGHIJKLMNOP' + 'RSTUVWXYZ')


def rect(name, length, width, holes=True):
    outline = [Line((0, 0), (length, 0)), Line((length, 0), (length, width)),
               Line((length, width), (0, width)), Line((0, width), (0, 0))]
    hs = [Hole(150, 40, 6.6), Hole(length - 150, 40, 6.6)] if holes else []
    return Shape(name, outline, hs)


def plan_for(*shapes, thick=None, settings=None):
    s = settings or Settings()
    es = [ShapeEntry(sh, thickness=(thick[i] if thick else None)) for i, sh in enumerate(shapes)]
    return build_plan(es, s), s


def by_name(progs):
    return {p.name: p for p in progs}


def cut_depths(ops, label):
    """Depths of the passes of one contour, in op order."""
    return [o.depth for o in ops if base_label(o.label) == label]


def hand_panel(pid, rotated=False):
    s = rect('r', 600, 200)
    ps = PlacedShape('r', 1, 45, 45, s, 18)
    t = PlacedTemplate('T01', 690, 290, [ps], [Hole(15, 15, 6)], [Hole(45 + 150, 45 + 40, 3)],
                       x=100, y=50, rotated=rotated)
    return PanelPlan(pid, [t])


class ProgramTests(unittest.TestCase):
    def test_three_programs_per_panel_with_names(self):
        plan, s = plan_for(rect('a', 1000, 230))
        progs = plan_programs(plan, s)
        self.assertEqual([p.name for p in progs], ['N1F', 'N1S', 'N1C'])
        self.assertEqual([p.tool for p in progs], [1, 2, 66])
        self.assertEqual([p.kind for p in progs], ['drill', 'drill', 'cut'])

    def test_equal_drills_merge(self):
        s = Settings()
        s.drill_screw.tool, s.drill_screw.diameter = s.drill_fix.tool, s.drill_fix.diameter
        plan, _ = plan_for(rect('a', 1000, 230), settings=s)
        progs = by_name(plan_programs(plan, s))
        self.assertEqual(sorted(progs), ['N1C', 'N1F'])
        self.assertEqual(len(progs['N1F'].ops), 4 + 2)
        self.assertEqual({round(o.depth, 6) for o in progs['N1F'].ops}, {37, 26})

    def test_stack_top_uses_thickest_shape(self):
        plan, s = plan_for(rect('a', 1000, 230), rect('b', 1000, 230), thick=[18, 22])
        self.assertEqual(len(plan.panels[0].templates), 1)
        self.assertEqual(stack_top(s, plan.panels[0]), 18 + 18 + 22)
        for p in plan_programs(plan, s):
            self.assertEqual(p.stock, (2440, 1220, 58))

    def test_depths(self):
        plan, s = plan_for(rect('a', 1000, 230))
        progs = by_name(plan_programs(plan, s))
        self.assertEqual(progs['N1F'].stock, (2440, 1220, 54))
        self.assertAlmostEqual(progs['N1F'].ops[0].depth, 37)
        self.assertAlmostEqual(progs['N1S'].ops[0].depth, 26)
        cuts = progs['N1C'].ops
        self.assertAlmostEqual(cuts[2].depth, 18.3)       # last pass of the shape
        self.assertAlmostEqual(cuts[-1].depth, 36.5)      # last pass of the template

    def test_cut_order_shapes_before_templates(self):
        plan, s = plan_for(rect('a', 1000, 230), rect('b', 600, 230), rect('c', 500, 230),
                           rect('d', 400, 230))
        ops = by_name(plan_programs(plan, s))['N1C'].ops
        kinds = ['outline' if base_label(o.label).endswith('outline') else 'shape' for o in ops]
        self.assertEqual(kinds, ['shape'] * 12 + ['outline'] * 6)

    def test_passes_equal_steps(self):
        steps = pass_depths(18.3, 9)
        self.assertEqual(len(steps), 3)
        self.assertAlmostEqual(steps[0], 6.1)
        self.assertAlmostEqual(steps[1], 12.2)
        self.assertAlmostEqual(steps[2], 18.3)
        self.assertEqual(len(pass_depths(18, 9)), 2)

    def test_hole_coordinates_follow_rotated_template(self):
        plan = Plan([hand_panel('P1', rotated=True)])
        t = plan.panels[0].templates[0]
        self.assertTrue(t.rotated)
        s = Settings()
        progs = by_name(plan_programs(plan, s))
        fx, fy = to_panel(t, 15, 15)
        self.assertEqual((progs['N1F'].ops[0].x, progs['N1F'].ops[0].y), (fx, fy))
        self.assertEqual((fx, fy), (100 + 290 - 15, 50 + 15))
        sx, sy = to_panel(t, 195, 85)
        self.assertEqual((progs['N1S'].ops[0].x, progs['N1S'].ops[0].y), (sx, sy))
        fw, fh = footprint(t)
        for op in progs['N1C'].ops:
            x0, y0, x1, y1 = bbox(op.segs)
            if base_label(op.label).endswith('outline'):
                self.assertAlmostEqual(x0, 100 - 4)
                self.assertAlmostEqual(x1, 100 + fw + 4)
            else:
                self.assertGreaterEqual(x0, 100)
                self.assertLessEqual(x1, 100 + fw)
                self.assertGreaterEqual(y0, 50)
                self.assertLessEqual(y1, 50 + fh)

    def test_real_rotated_template_from_layout(self):
        s = Settings()
        s.panel.length, s.panel.width = 1200, 2440
        # 2400 long cannot lie along the 1200 panel edge: the template must turn
        plan = build_plan([ShapeEntry(rect('a', 2300, 230, holes=False))], s)
        t = plan.panels[0].templates[0]
        self.assertTrue(t.rotated)
        ops = by_name(plan_programs(plan, s))['N1C'].ops
        fw, fh = footprint(t)
        for op in ops:
            x0, y0, x1, y1 = bbox(op.segs)
            self.assertGreaterEqual(x0, t.x - 4 - 1e-6)
            self.assertLessEqual(x1, t.x + fw + 4 + 1e-6)
            self.assertGreaterEqual(y0, t.y - 4 - 1e-6)
            self.assertLessEqual(y1, t.y + fh + 4 + 1e-6)

    def test_none_mode_has_no_template_layer(self):
        s = Settings()
        s.template.mode = 'none'
        plan, _ = plan_for(rect('a', 1000, 230), settings=s)
        self.assertEqual(stack_top(s, plan.panels[0]), 36)
        progs = by_name(plan_programs(plan, s))
        self.assertEqual(sorted(progs), ['N1C', 'N1S'])
        self.assertEqual(progs['N1C'].stock, (2440, 1220, 36))
        for op in progs['N1S'].ops:
            self.assertAlmostEqual(op.depth, 36 - (18 - 8))
        cuts = progs['N1C'].ops
        # material 18 + 0.5 = 18.5 -> 3 passes from the top; no template outline at all
        self.assertEqual(len(cuts), 3)
        self.assertFalse(any('outline' in o.label for o in cuts))
        for o, want in zip(cuts, (18.5 / 3, 18.5 * 2 / 3, 18.5)):
            self.assertAlmostEqual(o.depth, want)

    def test_offset_error_names_the_shape(self):
        pts = [(0, 0), (500, 0), (500, 100), (252, 100), (252, 60), (248, 60),
               (248, 100), (0, 100)]
        outline = [Line(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
        plan, s = plan_for(Shape('slot', outline, []))
        with self.assertRaises(OffsetError) as cm:
            plan_programs(plan, s)
        self.assertTrue(str(cm.exception).startswith('T01 slot #1: '), str(cm.exception))

    def test_all_depths_with_mixed_thickness(self):
        plan, s = plan_for(rect('a', 1000, 230), rect('b', 1000, 230), thick=[18, 22])
        progs = by_name(plan_programs(plan, s))
        self.assertEqual({round(o.depth, 6) for o in progs['N1F'].ops}, {41})
        self.assertEqual({round(o.depth, 6) for o in progs['N1S'].ops}, {30})
        cuts = progs['N1C'].ops
        # each contour's final depth: both shapes 22.3, template 40.5
        self.assertAlmostEqual(cut_depths(cuts, 'T01 a #1')[-1], 22.3)
        self.assertAlmostEqual(cut_depths(cuts, 'T01 b #1')[-1], 22.3)
        self.assertAlmostEqual(cut_depths(cuts, 'T01 outline')[-1], 40.5)

    def test_depths_with_distinct_heights(self):
        s = Settings()
        s.heights.scrap, s.heights.template_stock, s.heights.shape_thickness = 16, 19, 22
        plan, _ = plan_for(rect('a', 1000, 230), settings=s)
        # stack 16+19+22 = 57; fixing bottom 15 -> 42; screw bottom 16+19-8 = 27 -> 30
        # shape bottom 35-0.3 = 34.7 -> 22.3; template bottom 16-0.5 = 15.5 -> 41.5
        self.assertAlmostEqual(stack_top(s, plan.panels[0]), 57)
        progs = by_name(plan_programs(plan, s))
        self.assertAlmostEqual(progs['N1F'].ops[0].depth, 42)
        self.assertAlmostEqual(progs['N1S'].ops[0].depth, 30)
        self.assertAlmostEqual(progs['N1C'].ops[2].depth, 22.3)
        self.assertAlmostEqual(progs['N1C'].ops[-1].depth, 41.5)

    def test_direction_and_arcs(self):
        entries = [ShapeEntry(read_dxf(p)) for p in sorted((repo / 'plates').glob('*.dxf'))]
        for direction in ('ccw', 'cw'):
            s = Settings()
            s.router.direction = direction
            plan = build_plan(entries, s)
            progs = plan_programs(plan, s)
            self.assertTrue(progs)
            for p in progs:
                for op in p.ops:
                    if isinstance(op, ContourOp):
                        for seg in op.segs:
                            if isinstance(seg, Arc):
                                self.assertTrue(seg.ccw == (direction == 'ccw'))

    def test_every_name_valid(self):
        s = Settings()
        plan = Plan([hand_panel(f'P{i}') for i in range(1, 121)])
        progs = plan_programs(plan, s)
        self.assertEqual(len(progs), 360)
        for p in progs:
            self.assertRegex(p.name, r'^[A-Z0-9_-]{2,8}$')
            self.assertIn(p.name[0], FOLDER)
        self.assertEqual(len({p.name for p in progs}), 360)

    def test_line_warning(self):
        s = Settings()
        s.router.depth_per_pass = 1       # many passes -> many lines
        plan, _ = plan_for(rect('a', 1000, 230), settings=s)
        progs = by_name(plan_programs(plan, s))
        self.assertTrue(progs['N1C'].warnings)
        self.assertFalse(progs['N1F'].warnings)
        self.assertTrue(progs['N1C'].ops)      # never split or refused
        plan2, s2 = plan_for(rect('a', 1000, 230))
        self.assertEqual(by_name(plan_programs(plan2, s2))['N1C'].warnings, [])

    # ---- real passes: depth_per_pass is applied to the material only ----
    def real_n1c(self, settings=None):
        s = settings or Settings()
        entries = [ShapeEntry(read_dxf(p)) for p in sorted((repo / 'plates').glob('*.dxf'))]
        plan = build_plan(entries, s)
        return by_name(plan_programs(plan, s))['N1C'], s

    def test_real_plan_passes_per_contour(self):
        cut, _ = self.real_n1c()
        labels = []
        for o in cut.ops:
            b = base_label(o.label)
            if not labels or labels[-1] != b:
                labels.append(b)
        # contours are cut one after another, each fully before the next
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(len(cut.ops), 3 * len(labels))
        outline_at = [i for i, b in enumerate(labels) if b.endswith('outline')]
        self.assertEqual(outline_at, list(range(len(labels) - len(outline_at), len(labels))))
        for b in labels:
            d = cut_depths(cut.ops, b)
            self.assertEqual(len(d), 3)
            self.assertEqual(d, sorted(d))
            if b.endswith('outline'):
                for got, want in zip(d, (18 + 18.5 / 3, 18 + 18.5 * 2 / 3, 36.5)):
                    self.assertAlmostEqual(got, want, places=6)
            else:
                for got, want in zip(d, (6.1, 12.2, 18.3)):
                    self.assertAlmostEqual(got, want, places=6)
        for i in range(0, len(cut.ops), 3):
            self.assertEqual([base_label(o.label) for o in cut.ops[i:i + 3]],
                             [base_label(cut.ops[i].label)] * 3)
            self.assertEqual([o.label.rsplit(' ', 1)[1] for o in cut.ops[i:i + 3]],
                             ['1/3', '2/3', '3/3'])

    def test_mixed_thickness_pass_starts(self):
        plan, s = plan_for(rect('a', 1000, 230), rect('b', 1000, 230), thick=[18, 22])
        ops = by_name(plan_programs(plan, s))['N1C'].ops
        for got, want in zip(cut_depths(ops, 'T01 a #1'), (10.1, 16.2, 22.3)):  # top 4 down
            self.assertAlmostEqual(got, want, places=6)
        for got, want in zip(cut_depths(ops, 'T01 b #1'), (22.3 / 3, 22.3 * 2 / 3, 22.3)):
            self.assertAlmostEqual(got, want, places=6)
        self.assertEqual(len(cut_depths(ops, 'T01 a #1')), 3)
        self.assertEqual(len(cut_depths(ops, 'T01 b #1')), 3)
        for got, want in zip(cut_depths(ops, 'T01 outline'), (22 + 18.5 / 3, 22 + 18.5 * 2 / 3, 40.5)):
            self.assertAlmostEqual(got, want, places=6)

    def test_large_depth_per_pass_gives_one_pass(self):
        s = Settings()
        s.router.depth_per_pass = 100
        cut, _ = self.real_n1c(s)
        self.assertEqual(len(cut.ops), 6)
        self.assertAlmostEqual(cut.ops[0].depth, 18.3)
        self.assertAlmostEqual(cut.ops[-1].depth, 36.5)

    def test_estimate_is_emitted_line_count(self):
        from nesting.backends import BACKENDS
        cut, s = self.real_n1c()       # defaults: 6 contours x 3 passes is still over 250
        n = len(BACKENDS['cnc90'](cut, s).splitlines())
        self.assertEqual(cut.warnings, [f'N1C: about {n} lines, over 250'])


if __name__ == '__main__':
    unittest.main()
