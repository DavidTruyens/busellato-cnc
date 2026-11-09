import json
import re
import unittest
from pathlib import Path

from nesting.dxf import Hole, Shape, read_dxf
from nesting.geometry import Arc, Line, OffsetError, bbox
from nesting.layout import Blank, PanelPlan, PlacedShape, Plan, ShapeEntry, build_plan
from nesting.program import (ContourOp, DrillOp, Program, ProgramError, base_label, blank_programs,
                             check_depths, pass_depths, plan_programs, stack_top)
from nesting.settings import Settings

repo = Path(__file__).resolve().parent.parent
FOLDER = set('79ABCDEFGHIJKLMNOP' + 'RSTVWXYZ')      # tools/make-loader.py FOLDERS


def rect(name, length, width, holes=True):
    outline = [Line((0, 0), (length, 0)), Line((length, 0), (length, width)),
               Line((length, width), (0, width)), Line((0, width), (0, 0))]
    hs = [Hole(150, 40, 6.6), Hole(length - 150, 40, 6.6)] if holes else []
    return Shape(name, outline, hs)


def plan_for(*shapes, settings=None):
    s = settings or Settings()
    return build_plan([ShapeEntry(sh) for sh in shapes], s), s


def real_plan(settings=None):
    s = settings or Settings()
    es = [ShapeEntry(read_dxf(p)) for p in sorted((repo / 'plates').glob('*.dxf'))]
    return build_plan(es, s), s


def by_name(progs):
    return {p.name: p for p in progs}


def cut_depths(ops, label):
    """Depths of the passes of one contour, in op order."""
    return [o.depth for o in ops if base_label(o.label) == label]


def hand_blank(bid='B01', x=45, rotated=False):
    s = rect('r', 600, 200)
    ps = PlacedShape('r', 1, x, 45, s)
    return Blank(bid, 690, 290, [ps], [Hole(15, 15, 6)], [Hole(x + 150, 45 + 40, 3)],
                 'P1', 100, 50, rotated)


class CupDepthCheckTests(unittest.TestCase):
    """C1: a program never carries a depth at or below the top of the cups."""

    def prog(self, ops):
        return Program('B01C', 66, 'cut', 'test', (2440, 1220, 54), ops)

    def test_too_deep_drill_raises_with_program_and_depth(self):
        p = self.prog([DrillOp(100, 100, 30, 3), DrillOp(200, 100, 54, 3)])
        with self.assertRaises(ProgramError) as cm:
            check_depths(p)
        msg = str(cm.exception)
        self.assertIn('B01C', msg)
        self.assertIn('54', msg)
        self.assertIn('200', msg)                       # which drill
        self.assertIsInstance(cm.exception, ValueError)

    def test_too_deep_contour_raises_with_label(self):
        seg = [Line((0, 0), (10, 0)), Line((10, 0), (0, 0))]
        p = self.prog([ContourOp(seg, 54.5, 'B01 a #1 pass 2/2')])
        with self.assertRaises(ProgramError) as cm:
            check_depths(p)
        self.assertIn('B01 a #1 pass 2/2', str(cm.exception))
        self.assertIn('54.5', str(cm.exception))

    def test_shallower_ops_pass(self):
        seg = [Line((0, 0), (10, 0)), Line((10, 0), (0, 0))]
        check_depths(self.prog([DrillOp(1, 1, 53.9, 3), ContourOp(seg, 53.99, 'x')]))

    def test_plan_programs_refuses_a_too_deep_setting(self):
        # validate() would stop this first; plan_programs must stop it on its own too
        plan, s = plan_for(rect('a', 1000, 200))
        s.heights.into_scrap = 20
        with self.assertRaises(ProgramError) as cm:
            plan_programs(plan, s)
        self.assertIn('B01C', str(cm.exception))
        self.assertIn('B01 a #1', str(cm.exception))

    def test_too_deep_screw_and_fixing_holes_refused(self):
        for attr in ('fix_into_scrap', 'screw'):
            with self.subTest(attr=attr):
                plan, s = plan_for(rect('a', 1000, 200))
                if attr == 'screw':
                    s.drill_screw.depth = 18
                    name = 'B01S'
                else:
                    s.heights.fix_into_scrap = 18
                    name = 'B01F'
                with self.assertRaises(ProgramError) as cm:
                    plan_programs(plan, s)
                self.assertIn(name, str(cm.exception))

    def test_default_real_plan_passes(self):
        plan, s = real_plan()
        self.assertEqual(len(plan_programs(plan, s)), 18)       # 6 blanks x F, S, C


CUTTER_WARNING = re.compile(r'^(B\d+C): cutter reaches X(-?\d+\.\d)\.\.(-?\d+\.\d), '
                            r'Y(-?\d+\.\d)\.\.(-?\d+\.\d), outside the blank 0\.\.(\S+) x 0\.\.(\S+)$')


class CutterOutsideBlankTests(unittest.TestCase):
    """I3: a cut that reaches past the blank is a warning, never a refusal."""

    def cutter_warnings(self, progs):
        return [w for p in progs for w in p.warnings if 'cutter reaches' in w]

    def test_defaults_give_no_warning(self):
        plan, s = real_plan()
        self.assertEqual(self.cutter_warnings(plan_programs(plan, s)), [])

    def test_shape_near_the_blank_edge_warns_with_the_cutter_bounds(self):
        s = Settings()
        progs = by_name(blank_programs(hand_blank(x=3), s))
        ws = self.cutter_warnings(progs.values())
        self.assertEqual(len(ws), 1, ws)
        m = CUTTER_WARNING.match(ws[0])
        self.assertIsNotNone(m, ws[0])
        self.assertEqual(m.group(1), 'B01C')
        self.assertIn(ws[0], progs['B01C'].warnings)
        # independent: the centre line runs r outside the shape, the cutter edge 2r
        d = s.router.diameter
        self.assertEqual([float(g) for g in m.group(2, 3, 4, 5)],
                         [round(3 - d, 1), round(603 + d, 1), round(45 - d, 1), round(245 + d, 1)])
        self.assertEqual((m.group(6), m.group(7)), ('690', '290'))
        self.assertEqual(self.cutter_warnings([progs['B01F'], progs['B01S']]), [])

    def test_cutter_just_inside_the_blank_is_fine(self):
        s = Settings()
        self.assertEqual(self.cutter_warnings(blank_programs(hand_blank(x=8), s)), [])
        self.assertEqual(len(self.cutter_warnings(blank_programs(hand_blank(x=7.9), s))), 1)


class ProgramTests(unittest.TestCase):
    def test_three_programs_per_blank_with_names(self):
        plan, s = plan_for(rect('a', 1000, 230))
        progs = plan_programs(plan, s)
        self.assertEqual([p.name for p in progs], ['B01F', 'B01S', 'B01C'])
        self.assertEqual([p.tool for p in progs], [1, 2, 66])
        self.assertEqual([p.kind for p in progs], ['drill', 'drill', 'cut'])
        self.assertEqual({p.blank for p in progs}, {'B01'})

    def test_programs_are_per_blank_not_per_panel(self):
        plan, s = real_plan()
        progs = plan_programs(plan, s)
        self.assertEqual([p.name for p in progs],
                         [f'B0{n}{k}' for n in range(1, 7) for k in 'FSC'])
        for p in progs:
            b = next(b for b in plan.blanks if b.id == p.blank)
            self.assertEqual(p.stock, (b.width, b.height, 36))

    def test_equal_drills_merge(self):
        s = Settings()
        s.drill_screw.tool, s.drill_screw.diameter = s.drill_fix.tool, s.drill_fix.diameter
        plan, _ = plan_for(rect('a', 1000, 230), settings=s)
        progs = by_name(plan_programs(plan, s))
        self.assertEqual(sorted(progs), ['B01C', 'B01F'])
        self.assertEqual(len(progs['B01F'].ops), 4 + 2)
        self.assertEqual({round(o.depth, 6) for o in progs['B01F'].ops}, {19, 26})

    def test_stack_is_scrap_plus_blank(self):
        s = Settings()
        self.assertEqual(stack_top(s), 36)
        s.heights.scrap, s.panel.thickness = 16, 22
        self.assertEqual(stack_top(s), 38)

    def test_depths(self):
        plan, s = plan_for(rect('a', 1000, 230))
        progs = by_name(plan_programs(plan, s))
        b = plan.blanks[0]
        self.assertEqual(progs['B01F'].stock, (b.width, b.height, 36))
        # fixing: through the 18 blank + 1 into the scrap; screw: 18 + 8
        self.assertEqual({o.depth for o in progs['B01F'].ops}, {19})
        self.assertEqual({o.depth for o in progs['B01S'].ops}, {26})
        cuts = progs['B01C'].ops
        # through the blank from its top, 0.5 into the scrap, three equal passes
        self.assertEqual(len(cuts), 3)
        for o, want in zip(cuts, (18.5 / 3, 18.5 * 2 / 3, 18.5)):
            self.assertAlmostEqual(o.depth, want)

    def test_depths_with_distinct_heights(self):
        s = Settings()
        s.heights.scrap, s.panel.thickness = 16, 22
        s.heights.into_scrap, s.heights.fix_into_scrap, s.drill_screw.depth = 0.7, 2, 9
        plan, _ = plan_for(rect('a', 1000, 230), settings=s)
        progs = by_name(plan_programs(plan, s))
        self.assertEqual(progs['B01F'].stock[2], 38)
        self.assertAlmostEqual(progs['B01F'].ops[0].depth, 24)
        self.assertAlmostEqual(progs['B01S'].ops[0].depth, 31)
        self.assertAlmostEqual(progs['B01C'].ops[-1].depth, 22.7)
        for p in progs.values():
            for op in p.ops:
                self.assertLess(op.depth, 38)       # never reaches the cups

    def test_no_template_contour_anywhere(self):
        plan, s = real_plan()
        progs = plan_programs(plan, s)
        for p in progs:
            for op in p.ops:
                if isinstance(op, ContourOp):
                    b = base_label(op.label)
                    self.assertRegex(b, r'^B\d\d \S+ #\d+$')
                    self.assertNotIn('outline', op.label)
                    self.assertNotIn('template', op.label.lower())
        cut = by_name(progs)['B01C']
        shapes = plan.blanks[0].shapes
        self.assertEqual(len(cut.ops), 3 * len(shapes))
        self.assertEqual(cut.description, 'Shape outlines')
        from nesting.preview import preview_data
        data = preview_data(plan, progs, s)
        self.assertNotIn('template', json.dumps(data).lower())
        for b in data['blanks'] + [x for p in data['panels'] for x in p['blanks']]:
            self.assertNotIn('cut_path', b)         # only the shapes have a cut path

    def test_programs_in_blank_coordinates_even_when_turned_on_the_panel(self):
        s = Settings()
        flat = blank_programs(hand_blank(rotated=False), s)
        turned = blank_programs(hand_blank(rotated=True), s)
        for a, b in zip(flat, turned):
            self.assertEqual(a.name, b.name)
            self.assertEqual(a.ops, b.ops)
            self.assertEqual(a.stock, (690, 290, 36))
        self.assertEqual((flat[0].ops[0].x, flat[0].ops[0].y), (15, 15))

    def test_cuts_stay_inside_the_blank(self):
        plan, s = real_plan()
        r = s.router.diameter / 2
        for p in plan_programs(plan, s):
            b = next(b for b in plan.blanks if b.id == p.blank)
            for op in p.ops:
                if isinstance(op, ContourOp):
                    x0, y0, x1, y1 = bbox(op.segs)
                    self.assertTrue(x0 - r >= 0 and y0 - r >= 0 and x1 + r <= b.width
                                    and y1 + r <= b.height, (p.name, x0, y0, x1, y1))
                else:
                    self.assertTrue(0 < op.x < b.width and 0 < op.y < b.height)

    def test_passes_equal_steps(self):
        steps = pass_depths(18.3, 9)
        self.assertEqual(len(steps), 3)
        self.assertAlmostEqual(steps[0], 6.1)
        self.assertAlmostEqual(steps[1], 12.2)
        self.assertAlmostEqual(steps[2], 18.3)
        self.assertEqual(len(pass_depths(18, 9)), 2)

    def test_offset_error_names_the_shape(self):
        pts = [(0, 0), (500, 0), (500, 100), (252, 100), (252, 60), (248, 60),
               (248, 100), (0, 100)]
        outline = [Line(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
        plan, s = plan_for(Shape('slot', outline, []))
        with self.assertRaises(OffsetError) as cm:
            plan_programs(plan, s)
        self.assertTrue(str(cm.exception).startswith('B01 slot #1: '), str(cm.exception))

    def test_direction_and_arcs(self):
        for direction in ('ccw', 'cw'):
            s = Settings()
            s.router.direction = direction
            plan, _ = real_plan(s)
            progs = plan_programs(plan, s)
            self.assertTrue(progs)
            for p in progs:
                for op in p.ops:
                    if isinstance(op, ContourOp):
                        for seg in op.segs:
                            if isinstance(seg, Arc):
                                self.assertTrue(seg.ccw == (direction == 'ccw'))

    def test_every_name_valid_and_unique(self):
        s = Settings()
        blanks = [hand_blank(f'B{n:03d}') for n in range(1, 121)]
        plan = Plan([PanelPlan('P1', blanks)])
        progs = plan_programs(plan, s)
        self.assertEqual(len(progs), 360)
        for p in progs:
            self.assertRegex(p.name, r'^[A-Z0-9_-]{2,8}$')
            self.assertIn(p.name[0], FOLDER)
        self.assertEqual(len({p.name for p in progs}), 360)

    def test_names_from_a_large_real_plan_are_unique(self):
        s = Settings()
        es = [ShapeEntry(read_dxf(p), qty=9) for p in sorted((repo / 'plates').glob('*.dxf'))]
        plan = build_plan(es, s)
        progs = plan_programs(plan, s)
        names = [p.name for p in progs]
        self.assertEqual(len(plan.blanks), 54)
        self.assertEqual(len(names), 3 * 54)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(names[0], 'B01F')
        self.assertTrue(all(re.fullmatch(r'B\d{2}[FSC]', n) for n in names))

    def test_duplicate_blank_ids_refused(self):
        plan = Plan([PanelPlan('P1', [hand_blank('B01'), hand_blank('B01')])])
        with self.assertRaises(ProgramError):
            plan_programs(plan, Settings())

    def test_line_warning(self):
        s = Settings()
        s.router.depth_per_pass = 1       # many passes -> many lines
        plan, _ = plan_for(rect('a', 1000, 230), rect('b', 1000, 230), settings=s)
        progs = by_name(plan_programs(plan, s))
        self.assertTrue(progs['B01C'].warnings)
        self.assertFalse(progs['B01F'].warnings)
        self.assertTrue(progs['B01C'].ops)      # never split or refused
        plan2, s2 = plan_for(rect('a', 1000, 230))
        self.assertEqual(by_name(plan_programs(plan2, s2))['B01C'].warnings, [])

    def test_real_plan_passes_per_contour(self):
        plan, _ = real_plan()
        cut = by_name(plan_programs(plan, Settings()))['B01C']
        labels = []
        for o in cut.ops:
            b = base_label(o.label)
            if not labels or labels[-1] != b:
                labels.append(b)
        # contours are cut one after another, each fully before the next
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(len(labels), 2)
        for b in labels:
            d = cut_depths(cut.ops, b)
            for got, want in zip(d, (18.5 / 3, 18.5 * 2 / 3, 18.5)):
                self.assertAlmostEqual(got, want, places=6)
        self.assertEqual([o.label.rsplit(' ', 1)[1] for o in cut.ops],
                         ['1/3', '2/3', '3/3'] * 2)

    def test_large_depth_per_pass_gives_one_pass(self):
        s = Settings()
        s.router.depth_per_pass = 100
        plan, _ = real_plan(s)
        cut = by_name(plan_programs(plan, s))['B01C']
        self.assertEqual(len(cut.ops), 2)
        self.assertEqual({o.depth for o in cut.ops}, {18.5})


if __name__ == '__main__':
    unittest.main()
