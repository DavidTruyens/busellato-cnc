import json
import re
import unittest
from pathlib import Path

from nesting.dxf import Hole, Pocket, Shape, read_dxf
from nesting.geometry import Arc, Line, OffsetError, bbox, set_direction, split_large_arcs, translate
from nesting.layout import Blank, PanelPlan, PlacedShape, Plan, ShapeEntry, build_plan
from nesting.pockets import PocketError, find_groups, pocket_rings
from nesting.program import (ContourOp, DrillOp, Program, ProgramError, base_label, blank_programs,
                             check_depths, group_by_tool, pass_depths, plan_programs, stack_top)
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
                    depth = '36.000'
                else:
                    s.heights.fix_into_scrap = 18
                    depth = '36.000'
                with self.assertRaises(ProgramError) as cm:
                    plan_programs(plan, s)
                self.assertIn('B01D', str(cm.exception))      # the merged drill program
                self.assertIn(depth, str(cm.exception))

    def test_depth_check_is_per_op_in_the_merged_drill_program(self):
        # only the screw holes (second tool) are too deep: still refused, naming that drill
        plan, s = plan_for(rect('a', 1000, 230))
        s.drill_screw.depth = 18
        b = plan.blanks[0]
        with self.assertRaises(ProgramError) as cm:
            blank_programs(b, s)
        msg = str(cm.exception)
        self.assertIn('B01D', msg)
        sx, sy = b.screw_holes[0].x, b.height - b.screw_holes[0].y
        self.assertIn(f'X{sx:.3f} Y{sy:.3f}', msg)

    def test_default_real_plan_passes(self):
        plan, s = real_plan()
        self.assertEqual(len(plan_programs(plan, s)), 18)       # 6 blanks x D, P, C


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
        self.assertEqual(self.cutter_warnings([progs['B01D']]), [])

    def test_cutter_just_inside_the_blank_is_fine(self):
        s = Settings()
        self.assertEqual(self.cutter_warnings(blank_programs(hand_blank(x=8), s)), [])
        self.assertEqual(len(self.cutter_warnings(blank_programs(hand_blank(x=7.9), s))), 1)


class ProgramTests(unittest.TestCase):
    def test_one_drill_and_one_cut_program_per_blank(self):
        plan, s = plan_for(rect('a', 1000, 230))
        progs = plan_programs(plan, s)
        self.assertEqual([p.name for p in progs], ['B01D', 'B01C'])
        self.assertEqual([p.tool for p in progs], [1, 66])
        self.assertEqual([p.tools for p in progs], [[1, 2], [66]])
        self.assertEqual([p.kind for p in progs], ['drill', 'cut'])
        self.assertEqual({p.blank for p in progs}, {'B01'})
        d = progs[0]
        self.assertEqual(d.description, 'Fixing and screw holes')
        self.assertEqual(len(d.ops), 4 + 2)

    def test_two_tools_grouped_fixing_tool_first(self):
        plan, s = plan_for(rect('a', 1000, 230))
        d = by_name(plan_programs(plan, s))['B01D']
        b = plan.blanks[0]
        self.assertEqual([o.tool for o in d.ops], [1] * 4 + [2] * 2)
        self.assertEqual([o.diameter for o in d.ops], [6] * 4 + [3] * 2)
        self.assertEqual([o.depth for o in d.ops], [19] * 4 + [26] * 2)
        # within a tool, the layout's hole order
        self.assertEqual([(o.x, o.y) for o in d.ops],
                         [(h.x, b.height - h.y) for h in b.fix_holes + b.screw_holes])

    def test_grouping_is_by_tool_not_by_kind(self):
        # screw tool listed first would still give one group per tool, in first-seen order
        ops = [DrillOp(1, 1, 5, 6, 7), DrillOp(2, 1, 5, 3, 9), DrillOp(3, 1, 5, 6, 7),
               DrillOp(4, 1, 5, 3, 9), DrillOp(5, 1, 5, 8, 4)]
        got = group_by_tool(ops)
        self.assertEqual([(o.x, o.tool) for o in got], [(1, 7), (3, 7), (2, 9), (4, 9), (5, 4)])
        self.assertEqual(group_by_tool(got), got)               # stable, deterministic

    def test_one_tool_is_one_group_fixing_holes_first(self):
        s = Settings()
        s.drill_screw.tool = s.drill_fix.tool           # same tool, other diameter: still one
        plan, _ = plan_for(rect('a', 1000, 230), settings=s)
        progs = by_name(plan_programs(plan, s))
        self.assertEqual(sorted(progs), ['B01C', 'B01D'])
        d = progs['B01D']
        self.assertEqual(d.tools, [1])
        self.assertEqual([o.depth for o in d.ops], [19] * 4 + [26] * 2)

    def test_no_screw_holes_gives_a_fixing_only_drill(self):
        plan, s = plan_for(rect('a', 1000, 230, holes=False))
        d = by_name(plan_programs(plan, s))['B01D']
        self.assertEqual(d.description, 'Fixing holes')
        self.assertEqual(d.tools, [1])
        self.assertEqual(len(d.ops), 4)

    def test_no_fixing_or_screw_program_names(self):
        plan, s = real_plan()
        for p in plan_programs(plan, s):
            self.assertRegex(p.name, r'^B\d{2}[DPC]$')

    def test_programs_are_per_blank_not_per_panel(self):
        plan, s = real_plan()
        progs = plan_programs(plan, s)
        self.assertEqual([p.name for p in progs],
                         [f'B0{n}{k}' for n in range(1, 7) for k in 'DPC'])
        for p in progs:
            b = next(b for b in plan.blanks if b.id == p.blank)
            self.assertEqual(p.stock, (b.width, b.height, 36))

    def test_equal_drills_merge(self):
        s = Settings()
        s.drill_screw.tool, s.drill_screw.diameter = s.drill_fix.tool, s.drill_fix.diameter
        plan, _ = plan_for(rect('a', 1000, 230), settings=s)
        progs = by_name(plan_programs(plan, s))
        self.assertEqual(sorted(progs), ['B01C', 'B01D'])
        self.assertEqual(len(progs['B01D'].ops), 4 + 2)
        self.assertEqual({round(o.depth, 6) for o in progs['B01D'].ops}, {19, 26})

    def test_stack_is_scrap_plus_blank(self):
        s = Settings()
        self.assertEqual(stack_top(s), 36)
        s.heights.scrap, s.panel.thickness = 16, 22
        self.assertEqual(stack_top(s), 38)

    def test_depths(self):
        plan, s = plan_for(rect('a', 1000, 230))
        progs = by_name(plan_programs(plan, s))
        b = plan.blanks[0]
        self.assertEqual(progs['B01D'].stock, (b.width, b.height, 36))
        # fixing: through the 18 blank + 1 into the scrap; screw: 18 + 8
        self.assertEqual({o.depth for o in progs['B01D'].ops if o.tool == 1}, {19})
        self.assertEqual({o.depth for o in progs['B01D'].ops if o.tool == 2}, {26})
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
        self.assertEqual(progs['B01D'].stock[2], 38)
        self.assertAlmostEqual(progs['B01D'].ops[0].depth, 24)
        self.assertAlmostEqual(progs['B01D'].ops[-1].depth, 31)
        self.assertAlmostEqual(progs['B01C'].ops[-1].depth, 22.7)
        for p in progs.values():
            for op in p.ops:
                self.assertLess(op.depth, 38)       # never reaches the cups

    def test_no_template_contour_anywhere(self):
        plan, s = real_plan()
        progs = plan_programs(plan, s)
        for p in progs:
            for op in p.ops:
                if isinstance(op, ContourOp) and p.kind == 'cut':
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
        # layout hole (15, 15) on a 290 high blank: program Y from the back edge (y_toward front)
        self.assertEqual((flat[0].ops[0].x, flat[0].ops[0].y), (15, 275))

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
        # every arc of an outside contour turns with the walk; in the program numbers the
        # sense is the one seen from above when Y grows toward the back, the opposite when
        # Y grows toward the front (a mirror)
        for y_toward in ('front', 'back'):
            for direction in ('ccw', 'cw'):
                s = Settings()
                s.router.direction = direction
                s.machine.y_toward = y_toward
                plan, _ = real_plan(s)
                progs = plan_programs(plan, s)
                self.assertTrue(progs)
                want = (direction == 'ccw') == (y_toward == 'back')
                for p in progs:
                    if p.kind != 'cut':             # pockets: pockets.direction
                        continue
                    for op in p.ops:
                        if isinstance(op, ContourOp):
                            for seg in op.segs:
                                if isinstance(seg, Arc):
                                    self.assertEqual(seg.ccw, want, (y_toward, direction))

    def test_every_name_valid_and_unique(self):
        s = Settings()
        blanks = [hand_blank(f'B{n:03d}') for n in range(1, 121)]
        plan = Plan([PanelPlan('P1', blanks)])
        progs = plan_programs(plan, s)
        self.assertEqual(len(progs), 240)
        for p in progs:
            self.assertRegex(p.name, r'^B\d{3}[DC]$')          # same width past 99 blanks
            self.assertRegex(p.name, r'^[A-Z0-9_-]{2,8}$')
            self.assertIn(p.name[0], FOLDER)
        self.assertEqual(len({p.name for p in progs}), 240)

    def test_names_from_a_large_real_plan_are_unique(self):
        s = Settings()
        es = [ShapeEntry(read_dxf(p), qty=9) for p in sorted((repo / 'plates').glob('*.dxf'))]
        plan = build_plan(es, s)
        progs = plan_programs(plan, s)
        names = [p.name for p in progs]
        self.assertEqual(len(plan.blanks), 54)
        self.assertEqual(len(names), 3 * 54)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(names[:3], ['B01D', 'B01P', 'B01C'])
        self.assertTrue(all(re.fullmatch(r'B\d{2}[DPC]', n) for n in names))

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
        self.assertFalse(progs['B01D'].warnings)
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


def rect_loop(x0, y0, w, h):
    pts = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
    return [Line(pts[i], pts[(i + 1) % 4]) for i in range(4)]


def slot_loop(x0, y0, length, width):
    """A counter-clockwise slot: two straight sides and two half-circle ends."""
    r = width / 2
    x1 = x0 + length - r
    return [Line((x0 + r, y0), (x1, y0)),
            Arc((x1, y0), (x1, y0 + width), (x1, y0 + r), r, True),
            Line((x1, y0 + width), (x0 + r, y0 + width)),
            Arc((x0 + r, y0 + width), (x0 + r, y0), (x0 + r, y0 + r), r, True)]


def pocket_shape(name, loops, length=600, width=200, holes=()):
    s = rect(name, length, width, holes=False)
    s.holes = [Hole(x, y, 6.6) for x, y in holes]
    s.pockets = [Pocket(lp) for lp in loops]
    return s


class PocketProgramTests(unittest.TestCase):
    """B<nn>P: the pockets of a blank, run between the drill and the cut program."""

    def test_pocket_program_name_and_order(self):
        plan, s = real_plan()
        progs = plan_programs(plan, s)
        self.assertEqual([p.name for p in progs if p.blank == 'B01'], ['B01D', 'B01P', 'B01C'])
        self.assertEqual([p.name for p in progs],
                         [f'B0{n}{k}' for n in range(1, 7) for k in 'DPC'])
        pk = by_name(progs)['B01P']
        self.assertEqual((pk.kind, pk.description, pk.blank), ('pocket', 'Pockets', 'B01'))
        self.assertEqual(pk.tool, s.pockets.tool)
        self.assertEqual(pk.tools, [s.pockets.tool])
        b = plan.blanks[0]
        self.assertEqual(pk.stock, (b.width, b.height, 36))

    def test_no_pocket_program_without_pockets(self):
        plan, s = plan_for(rect('a', 1000, 230))
        self.assertEqual([p.name for p in plan_programs(plan, s)], ['B01D', 'B01C'])

    def test_pocket_passes_and_depths(self):
        s = Settings()
        s.pockets.depth, s.pockets.depth_per_pass = 8, 4
        plan, _ = plan_for(pocket_shape('p', [rect_loop(100, 50, 40, 30)]), settings=s)
        pk = by_name(plan_programs(plan, s))['B01P']
        n = len(pocket_rings(rect_loop(100, 50, 40, 30), s.pockets.diameter,
                             s.pockets.stepover_pct))
        self.assertGreater(n, 1)
        self.assertEqual(len(pk.ops), 2 * n)
        self.assertEqual([o.depth for o in pk.ops], [4.0] * n + [8.0] * n)
        # from the top of the blank: the depth is the pass depth itself
        self.assertEqual([o.segs for o in pk.ops[:n]], [o.segs for o in pk.ops[n:]])
        self.assertEqual([o.label for o in pk.ops[:2]],
                         [f'B01 p #1 G1 pocket 1 pass 1/2 ring 1/{n}',
                          f'B01 p #1 G1 pocket 1 pass 1/2 ring 2/{n}'])
        self.assertEqual(pk.ops[-1].label, f'B01 p #1 G1 pocket 1 pass 2/2 ring {n}/{n}')

    def test_ops_carry_tool_spindle_feed(self):
        s = Settings()
        sh = pocket_shape('p', [rect_loop(100, 50, 40, 30), slot_loop(300, 60, 120, 20)])
        plan, _ = plan_for(sh, settings=s)
        groups = find_groups([sh])
        ov = {groups[1].key: {'tool': 7, 'spindle_rpm': 12000, 'plunge_feed': 2,
                              'cut_feed': 5, 'diameter': 12}}
        pk = by_name(plan_programs(plan, s, ov))['B01P']
        g1 = [o for o in pk.ops if ' G1 ' in o.label]
        g2 = [o for o in pk.ops if ' G2 ' in o.label]
        self.assertTrue(g1 and g2)
        self.assertEqual({(o.tool, o.spindle_rpm, o.plunge_feed, o.cut_feed) for o in g1},
                         {(s.pockets.tool, int(s.pockets.spindle_rpm), s.pockets.plunge_feed,
                           s.pockets.cut_feed)})
        self.assertEqual({(o.tool, o.spindle_rpm, o.plunge_feed, o.cut_feed) for o in g2},
                         {(7, 12000, 2, 5)})
        self.assertEqual(pk.tools, [s.pockets.tool, 7])
        self.assertEqual((pk.tool, pk.spindle_rpm, pk.plunge_feed, pk.cut_feed),
                         (s.pockets.tool, int(s.pockets.spindle_rpm), s.pockets.plunge_feed,
                          s.pockets.cut_feed))
        # grouped by tool: every G1 op before every G2 op
        self.assertEqual(pk.ops, g1 + g2)

    def test_groups_ordered_by_tool(self):
        s = Settings()
        sh = pocket_shape('p', [rect_loop(100, 50, 40, 30), slot_loop(300, 60, 120, 20),
                                rect_loop(450, 50, 40, 40)])
        plan, _ = plan_for(sh, settings=s)
        g = find_groups([sh])
        ov = {g[1].key: {'tool': 7}}
        pk = by_name(plan_programs(plan, s, ov))['B01P']
        order = []
        for o in pk.ops:
            gid = o.label.split()[3]
            if not order or order[-1] != gid:
                order.append(gid)
        self.assertEqual(order, ['G1', 'G3', 'G2'])

    def test_depth_below_floor_is_hard_error(self):
        s = Settings()
        sh = pocket_shape('p', [rect_loop(100, 50, 40, 30)])
        plan, _ = plan_for(sh, settings=s)
        key = find_groups([sh])[0].key
        # 18 thick, 2 floor: 16 is the deepest allowed
        by_name(plan_programs(plan, s, {key: {'depth': 16}}))
        with self.assertRaises(ProgramError) as cm:
            plan_programs(plan, s, {key: {'depth': 16.5}})
        msg = str(cm.exception)
        for want in ('B01', 'p', 'G1', '16.5'):
            self.assertIn(want, msg)

    def test_pocket_error_names_blank_shape_and_group(self):
        s = Settings()
        plan, _ = plan_for(pocket_shape('p', [rect_loop(100, 50, 6, 30)]), settings=s)
        with self.assertRaises(PocketError) as cm:
            plan_programs(plan, s)
        self.assertTrue(str(cm.exception).startswith('B01 p G1 (6 x 30 pocket): '),
                        str(cm.exception))

    def test_pocket_position_in_program_frame_matches_mirror(self):
        # asymmetric: a slot near the shape's top-left corner
        slot = slot_loop(50, 150, 200, 20)
        rings = pocket_rings(slot, 8, 40)
        for y_toward in ('front', 'back'):
            with self.subTest(y_toward=y_toward):
                s = Settings()
                s.machine.y_toward = y_toward
                plan, _ = plan_for(pocket_shape('p', [slot]), settings=s)
                b = plan.blanks[0]
                ps = b.shapes[0]
                self.assertEqual((ps.x, ps.y, b.height), (45, 45, 290))
                pk = by_name(plan_programs(plan, s))['B01P']
                self.assertEqual(len(pk.ops), 2 * len(rings))
                for op, ring in zip(pk.ops, rings):
                    # cw seen from above, in the layout frame
                    lay = split_large_arcs(set_direction(translate(ring, 45, 45), False))
                    self.assertEqual(len(op.segs), len(lay))
                    for got, want in zip(op.segs, lay):
                        self.assertIs(type(got), type(want))
                        pts = [want.a, want.b] + ([want.center] if isinstance(want, Arc) else [])
                        gpts = [got.a, got.b] + ([got.center] if isinstance(got, Arc) else [])
                        for (gx, gy), (wx, wy) in zip(gpts, pts):
                            self.assertAlmostEqual(gx, wx, places=9)
                            self.assertAlmostEqual(gy, 290 - wy if y_toward == 'front' else wy,
                                                   places=9)
                        if isinstance(want, Arc):
                            self.assertFalse(want.ccw)
                            self.assertEqual(got.ccw, y_toward == 'front')
                # the slot is near the back edge of the blank (layout y high): program Y small
                # when Y grows toward the front
                y0 = min(min(sg.a[1], sg.b[1]) for sg in pk.ops[0].segs)
                if y_toward == 'front':
                    self.assertLess(y0, 100)
                else:
                    self.assertGreater(y0, 190)

    def test_direction_ccw(self):
        s = Settings()
        s.machine.y_toward = 'back'
        sh = pocket_shape('p', [slot_loop(50, 150, 200, 20)])
        plan, _ = plan_for(sh, settings=s)
        key = find_groups([sh])[0].key
        pk = by_name(plan_programs(plan, s, {key: {'direction': 'ccw'}}))['B01P']
        arcs = [sg for o in pk.ops for sg in o.segs if isinstance(sg, Arc)]
        self.assertTrue(arcs)
        self.assertTrue(all(a.ccw for a in arcs))

    def test_disabled_group_gives_no_ops(self):
        s = Settings()
        sh = pocket_shape('p', [rect_loop(100, 50, 40, 30), slot_loop(300, 60, 120, 20)])
        plan, _ = plan_for(sh, settings=s)
        g = find_groups([sh])
        pk = by_name(plan_programs(plan, s, {g[0].key: {'enabled': False}}))['B01P']
        self.assertTrue(pk.ops)
        self.assertFalse([o for o in pk.ops if ' G1 ' in o.label])
        off = {g[0].key: {'enabled': False}, g[1].key: {'enabled': False}}
        self.assertEqual([p.name for p in plan_programs(plan, s, off)], ['B01D', 'B01C'])
        # a disabled group's depth is not checked: it is not cut
        off[g[0].key]['depth'] = 17
        plan_programs(plan, s, off)

    def test_screw_hole_close_to_pocket_warns(self):
        s = Settings()
        # screw hole at (150, 40); head 14 -> clearance 7 + 3 = 10 mm
        near = pocket_shape('p', [rect_loop(155, 30, 40, 30)], holes=[(150, 40)])
        plan, _ = plan_for(near, settings=s)
        pk = by_name(plan_programs(plan, s))['B01P']
        ws = [w for w in pk.warnings if 'screw hole' in w]
        self.assertEqual(len(ws), 1, pk.warnings)
        self.assertIn('B01P', ws[0])
        self.assertIn('B01 p #1 G1 pocket 1', ws[0])
        far = pocket_shape('p', [rect_loop(161, 30, 40, 30)], holes=[(150, 40)])
        plan, _ = plan_for(far, settings=s)
        self.assertEqual(by_name(plan_programs(plan, s))['B01P'].warnings, [])
        # a hole inside the pocket warns too, however far from its outline
        inside = pocket_shape('p', [rect_loop(100, 10, 100, 70)], holes=[(150, 40)])
        plan, _ = plan_for(inside, settings=s)
        pk = by_name(plan_programs(plan, s))['B01P']
        self.assertEqual(len([w for w in pk.warnings if 'screw hole' in w]), 1, pk.warnings)

    def test_fixing_hole_close_to_pocket_warns(self):
        s = Settings()
        # the shape sits at (45, 45); the fixing hole at (15, 15): a pocket at the corner
        plan, _ = plan_for(pocket_shape('p', [rect_loop(0.5, 0.5, 40, 30)]), settings=s)
        b = plan.blanks[0]
        self.assertEqual((b.fix_holes[0].x, b.fix_holes[0].y), (15, 15))
        s.blank.head_dia = 82         # clearance 44 mm reaches the pocket corner (~43.1 mm)
        pk = by_name(blank_programs(b, s))['B01P']
        self.assertEqual(len([w for w in pk.warnings if 'fixing hole' in w]), 1, pk.warnings)

    def test_pockets_close_together_warn(self):
        s = Settings()
        close = pocket_shape('p', [rect_loop(100, 50, 40, 30), rect_loop(147, 50, 40, 30)])
        plan, _ = plan_for(close, settings=s)
        pk = by_name(plan_programs(plan, s))['B01P']
        ws = [w for w in pk.warnings if 'pocket' in w and 'apart' in w]
        self.assertEqual(len(ws), 1, pk.warnings)
        apart = pocket_shape('p', [rect_loop(100, 50, 40, 30), rect_loop(149, 50, 40, 30)])
        plan, _ = plan_for(apart, settings=s)
        self.assertEqual(by_name(plan_programs(plan, s))['B01P'].warnings, [])

    def test_line_count_warning_for_pocket_program(self):
        s = Settings()
        s.pockets.depth_per_pass = 0.5
        plan, _ = real_plan(s)
        progs = by_name(plan_programs(plan, s))
        self.assertTrue(any('over 250' in w for w in progs['B01P'].warnings),
                        progs['B01P'].warnings)
        plan, s = real_plan()
        self.assertEqual(by_name(plan_programs(plan, s))['B01P'].warnings, [])

    def test_round_pocket_of_the_tool_diameter_is_one_plunge(self):
        s = Settings()
        c = (200, 100)
        circle = [Arc((204, 100), (196, 100), c, 4, True), Arc((196, 100), (204, 100), c, 4, True)]
        plan, _ = plan_for(pocket_shape('p', [circle]), settings=s)
        pk = by_name(plan_programs(plan, s))['B01P']
        self.assertEqual(len(pk.ops), 2)            # one per pass
        for o in pk.ops:
            self.assertEqual(o.segs, [Line((245, 145), (245, 145))])

    def test_groups_are_found_over_the_whole_plan(self):
        # the same pocket in two shapes on two blanks: one group, one id everywhere
        s = Settings()
        a = pocket_shape('a', [rect_loop(100, 50, 40, 30)], length=1900)
        b = pocket_shape('b', [rect_loop(100, 50, 40, 30)], length=1000)
        c = pocket_shape('c', [slot_loop(300, 60, 120, 20)], length=1900)
        s.blank.shapes_per = 1
        plan, _ = plan_for(a, b, c, settings=s)
        self.assertEqual(len(plan.blanks), 3)
        labels = {o.label.split()[1]: o.label.split()[3]
                  for p in plan_programs(plan, s) if p.kind == 'pocket' for o in p.ops}
        self.assertEqual(labels, {'a': 'G1', 'b': 'G1', 'c': 'G2'})


if __name__ == '__main__':
    unittest.main()
