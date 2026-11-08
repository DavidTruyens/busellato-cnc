import re
import unittest
from pathlib import Path

from nesting.dxf import Hole, Shape, read_dxf
from nesting.geometry import Arc, Line, bbox
from nesting.layout import PanelPlan, PlacedShape, PlacedTemplate, Plan, ShapeEntry, build_plan, footprint, to_panel
from nesting.program import ContourOp, DrillOp, pass_depths, plan_programs, stack_top
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
        self.assertAlmostEqual(cuts[0].depth, 18.3)
        self.assertAlmostEqual(cuts[-1].depth, 36.5)

    def test_cut_order_shapes_before_templates(self):
        plan, s = plan_for(rect('a', 1000, 230), rect('b', 600, 230), rect('c', 500, 230),
                           rect('d', 400, 230))
        ops = by_name(plan_programs(plan, s))['N1C'].ops
        kinds = ['outline' if o.label.endswith('outline') else 'shape' for o in ops]
        self.assertEqual(kinds, ['shape'] * 4 + ['outline'] * 2)

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
            if op.label.endswith('outline'):
                self.assertAlmostEqual(x0, 100 - 4)
                self.assertAlmostEqual(x1, 100 + fw + 4)
            else:
                self.assertGreaterEqual(x0, 100)
                self.assertLessEqual(x1, 100 + fw)
                self.assertGreaterEqual(y0, 50)
                self.assertLessEqual(y1, 50 + fh)

    def test_real_rotated_template_from_layout(self):
        shapes = [rect('a', 2400, 1100, holes=False)] * 1
        s = Settings()
        s.template.mode = 'none'
        # a narrow panel forces a turn: the shape only fits rotated
        s.panel.length, s.panel.width = 1200, 2440
        plan = build_plan([ShapeEntry(shapes[0])], s)
        t = plan.panels[0].templates[0]
        self.assertTrue(t.rotated)
        op = by_name(plan_programs(plan, s))['N1C'].ops[0]
        x0, y0, x1, y1 = bbox(op.segs)
        fw, fh = footprint(t)
        r = s.router.diameter / 2     # no template margin: the cut runs one radius outside
        self.assertGreaterEqual(x0, t.x - r - 1e-6)
        self.assertLessEqual(x1, t.x + fw + r + 1e-6)
        self.assertLessEqual(y1, t.y + fh + r + 1e-6)
        self.assertAlmostEqual(x1 - x0, fw + 2 * r)

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


if __name__ == '__main__':
    unittest.main()
