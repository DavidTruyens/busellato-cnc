import json
import re
import unittest
from pathlib import Path
from unittest import mock

from nesting.dxf import Hole, Pocket, Shape, read_dxf
from nesting.geometry import Arc, Line, OffsetError, bbox, set_direction, split_large_arcs, translate
from nesting.layout import Blank, PanelPlan, PlacedShape, Plan, ShapeEntry, build_plan
import nesting.pockets as pockets
from nesting.pockets import PocketError, find_groups, memo_pocket_rings, pocket_rings
from nesting.program import (ContourOp, DrillOp, Program, ProgramError, base_label, blank_programs,
                             check_depths, group_by_tool, pass_depths, plan_programs, stack_top,
                             check_pocket_heads)
from nesting.settings import Settings
from helpers import put_bit

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


def is_pocket(op):
    return ' pocket ' in getattr(op, 'label', '')         # drill ops have no label


def pocket_ops(prog):
    """The pocket ops of a cut program, checked to come before every outline op."""
    ops = [o for o in prog.ops if is_pocket(o)]
    assert prog.ops[:len(ops)] == ops, f'{prog.name}: a pocket op after an outline op'
    return ops


def outline_ops(prog):
    return [o for o in prog.ops if not is_pocket(o)]


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
        self.assertEqual(len(plan_programs(plan, s)), 12)       # 6 blanks x D, C


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
        d = s.router_bit.diameter
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
        # same head (so the same bit): still one group
        s.drill_screw.tool = s.drill_fix.tool
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
            self.assertRegex(p.name, r'^B\d{2}[DC]$')

    def test_programs_are_per_blank_not_per_panel(self):
        plan, s = real_plan()
        progs = plan_programs(plan, s)
        self.assertEqual([p.name for p in progs],
                         [f'B0{n}{k}' for n in range(1, 7) for k in 'DC'])
        for p in progs:
            b = next(b for b in plan.blanks if b.id == p.blank)
            self.assertEqual(p.stock, (b.width, b.height, 36))

    def test_equal_drills_merge(self):
        s = Settings()
        s.drill_screw.tool = s.drill_fix.tool
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
                if isinstance(op, ContourOp) and p.kind == 'cut' and not is_pocket(op):
                    b = base_label(op.label)
                    self.assertRegex(b, r'^B\d\d \S+ #\d+$')
                    self.assertNotIn('outline', op.label)
                    self.assertNotIn('template', op.label.lower())
                elif isinstance(op, ContourOp):
                    self.assertNotIn('template', op.label.lower())
        cut = by_name(progs)['B01C']
        shapes = plan.blanks[0].shapes
        self.assertTrue(pocket_ops(cut))                # the real plates have pockets
        self.assertEqual(len(outline_ops(cut)), 3 * len(shapes))
        self.assertEqual(cut.description, 'Pockets and shape outlines')
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
        r = s.router_bit.diameter / 2
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
                    if p.kind != 'cut':
                        continue
                    for op in outline_ops(p):       # pockets: pockets.direction
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
        self.assertEqual(len(names), 2 * 54)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(names[:2], ['B01D', 'B01C'])
        self.assertTrue(all(re.fullmatch(r'B\d{2}[DC]', n) for n in names))

    def test_duplicate_blank_ids_refused(self):
        plan = Plan([PanelPlan('P1', [hand_blank('B01'), hand_blank('B01')])])
        with self.assertRaises(ProgramError):
            plan_programs(plan, Settings())

    def test_line_warning(self):
        s = Settings()
        put_bit(s, 66, depth_per_pass=1)  # many passes -> many lines
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
        pocket_ops(cut)                                 # pockets first, then the outlines
        outlines = outline_ops(cut)
        labels = []
        for o in outlines:
            b = base_label(o.label)
            if not labels or labels[-1] != b:
                labels.append(b)
        # contours are cut one after another, each fully before the next
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(len(labels), 2)
        for b in labels:
            d = cut_depths(outlines, b)
            for got, want in zip(d, (18.5 / 3, 18.5 * 2 / 3, 18.5)):
                self.assertAlmostEqual(got, want, places=6)
        self.assertEqual([o.label.rsplit(' ', 1)[1] for o in outlines],
                         ['1/3', '2/3', '3/3'] * 2)

    def test_large_depth_per_pass_gives_one_pass(self):
        s = Settings()
        put_bit(s, 66, depth_per_pass=100)
        plan, _ = real_plan(s)
        cut = by_name(plan_programs(plan, s))['B01C']
        pocket_ops(cut)
        self.assertEqual(len(outline_ops(cut)), 2)
        self.assertEqual({o.depth for o in outline_ops(cut)}, {18.5})


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
    """The pockets of a blank: the first ops of its cut program B<nn>C, before the outlines."""

    def test_pockets_go_first_in_the_cut_program(self):
        plan, s = real_plan()
        progs = plan_programs(plan, s)
        self.assertEqual([p.name for p in progs if p.blank == 'B01'], ['B01D', 'B01C'])
        self.assertEqual([p.name for p in progs],
                         [f'B0{n}{k}' for n in range(1, 7) for k in 'DC'])
        self.assertFalse([p for p in progs if p.kind == 'pocket' or p.name.endswith('P')])
        c = by_name(progs)['B01C']
        self.assertEqual((c.kind, c.description, c.blank),
                         ('cut', 'Pockets and shape outlines', 'B01'))
        self.assertEqual(c.tool, s.router.tool)
        pk = pocket_ops(c)                              # first, before every outline op
        self.assertTrue(pk)
        self.assertTrue(outline_ops(c))
        self.assertEqual({o.tool for o in pk}, {s.pockets.tool})
        self.assertEqual({o.tool for o in outline_ops(c)}, {None})     # the program's, router
        self.assertEqual(c.tools, [s.pockets.tool])     # 66 is both the pocket and router head
        b = plan.blanks[0]
        self.assertEqual(c.stock, (b.width, b.height, 36))

    def test_project_groups_keep_their_ids_on_a_plan_without_some_shapes(self):
        from nesting.preview import pocket_groups_data, preview_data
        a = pocket_shape('a', [rect_loop(100, 50, 40, 30)])
        b = pocket_shape('b', [rect_loop(100, 50, 60, 30)])
        project = find_groups([a, b])                   # G1 is a's pocket, G2 b's
        plan, s = plan_for(b)                           # a switched off: only b placed
        ids = lambda progs: {re.search(r' (G\d+) pocket ', o.label).group(1)
                             for p in progs for o in p.ops if is_pocket(o)}
        # without groups: as before, numbered over the plan's shapes
        self.assertEqual(ids(plan_programs(plan, s)), {'G1'})
        self.assertEqual([g['id'] for g in pocket_groups_data(plan, s)], ['G1'])
        # with the project's groups: b's group keeps G2 and its colour everywhere
        progs = plan_programs(plan, s, None, project)
        self.assertEqual(ids(progs), {'G2'})
        listed = pocket_groups_data(plan, s, None, project)
        self.assertEqual([(g['id'], g['color'], g['count']) for g in listed],
                         [('G2', project[1].color, 1)])
        data = preview_data(plan, progs, s, None, project)
        self.assertEqual(data['pocket_groups'], listed)
        blank = data['blanks'][0]
        self.assertEqual({(p['group'], p['color']) for q in blank['shapes'] for p in q['pockets']},
                         {('G2', project[1].color)})
        self.assertEqual({(r['group'], r['color']) for r in blank['pocket_rings']},
                         {('G2', project[1].color)})

    def test_no_pocket_ops_without_pockets(self):
        plan, s = plan_for(rect('a', 1000, 230))
        progs = plan_programs(plan, s)
        self.assertEqual([p.name for p in progs], ['B01D', 'B01C'])
        c = by_name(progs)['B01C']
        self.assertFalse([o for o in c.ops if is_pocket(o)])
        self.assertEqual(c.description, 'Shape outlines')

    def test_pocket_passes_and_depths(self):
        s = Settings()
        bit = put_bit(s, 65, depth_per_pass=4)
        s.pockets.depth, s.pockets.tool = 8, 65
        plan, _ = plan_for(pocket_shape('p', [rect_loop(100, 50, 40, 30)]), settings=s)
        pk = pocket_ops(by_name(plan_programs(plan, s))['B01C'])
        n = len(pocket_rings(rect_loop(100, 50, 40, 30), bit.diameter, bit.stepover_pct))
        self.assertGreater(n, 1)
        self.assertEqual(len(pk), 2 * n)
        self.assertEqual([o.depth for o in pk], [4.0] * n + [8.0] * n)
        # from the top of the blank: the depth is the pass depth itself
        self.assertEqual([o.segs for o in pk[:n]], [o.segs for o in pk[n:]])
        self.assertEqual([o.label for o in pk[:2]],
                         [f'B01 p #1 G1 pocket 1 pass 1/2 ring 1/{n}',
                          f'B01 p #1 G1 pocket 1 pass 1/2 ring 2/{n}'])
        self.assertEqual(pk[-1].label, f'B01 p #1 G1 pocket 1 pass 2/2 ring {n}/{n}')

    def test_ops_carry_tool_spindle_feed(self):
        s = Settings()
        sh = pocket_shape('p', [rect_loop(100, 50, 40, 30), slot_loop(300, 60, 120, 20)])
        plan, _ = plan_for(sh, settings=s)
        groups = find_groups([sh])
        put_bit(s, 65, spindle_rpm=12000, plunge_feed=2, cut_feed=5, diameter=12)
        ov = {groups[1].key: {'tool': 65}}
        c = by_name(plan_programs(plan, s, ov))['B01C']
        pk = pocket_ops(c)
        g1 = [o for o in pk if ' G1 ' in o.label]
        g2 = [o for o in pk if ' G2 ' in o.label]
        self.assertTrue(g1 and g2)
        self.assertEqual({(o.tool, o.spindle_rpm, o.plunge_feed, o.cut_feed) for o in g1},
                         {(66, 18000, 1, 3)})            # the default table's bit in T66
        self.assertEqual({(o.tool, o.spindle_rpm, o.plunge_feed, o.cut_feed) for o in g2},
                         {(65, 12000, 2, 5)})
        self.assertEqual(c.tools, [66, 65])            # the outlines' router 66 already used
        # the program's numbers are the router's (the default bit in T66)
        self.assertEqual((c.tool, c.spindle_rpm, c.plunge_feed, c.cut_feed),
                         (66, 18000, 1, 3))
        # grouped by tool: every G1 op before every G2 op
        self.assertEqual(pk, g1 + g2)

    def test_groups_ordered_by_tool(self):
        s = Settings()
        sh = pocket_shape('p', [rect_loop(100, 50, 40, 30), slot_loop(300, 60, 120, 20),
                                rect_loop(450, 50, 40, 40)])
        plan, _ = plan_for(sh, settings=s)
        g = find_groups([sh])
        put_bit(s, 65)
        ov = {g[1].key: {'tool': 65}}
        pk = pocket_ops(by_name(plan_programs(plan, s, ov))['B01C'])
        order = []
        for o in pk:
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
                pk = pocket_ops(by_name(plan_programs(plan, s))['B01C'])
                # depth 8 in one pass: the default bit cuts 9 mm per pass (R4)
                self.assertEqual(len(pk), len(rings))
                for op, ring in zip(pk, rings):
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
                y0 = min(min(sg.a[1], sg.b[1]) for sg in pk[0].segs)
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
        pk = pocket_ops(by_name(plan_programs(plan, s, {key: {'direction': 'ccw'}}))['B01C'])
        arcs = [sg for o in pk for sg in o.segs if isinstance(sg, Arc)]
        self.assertTrue(arcs)
        self.assertTrue(all(a.ccw for a in arcs))

    def test_disabled_group_gives_no_ops(self):
        s = Settings()
        sh = pocket_shape('p', [rect_loop(100, 50, 40, 30), slot_loop(300, 60, 120, 20)])
        plan, _ = plan_for(sh, settings=s)
        g = find_groups([sh])
        pk = pocket_ops(by_name(plan_programs(plan, s, {g[0].key: {'enabled': False}}))['B01C'])
        self.assertTrue(pk)
        self.assertFalse([o for o in pk if ' G1 ' in o.label])
        off = {g[0].key: {'enabled': False}, g[1].key: {'enabled': False}}
        progs = plan_programs(plan, s, off)
        self.assertEqual([p.name for p in progs], ['B01D', 'B01C'])
        self.assertFalse([o for o in by_name(progs)['B01C'].ops if is_pocket(o)])
        self.assertEqual(by_name(progs)['B01C'].description, 'Shape outlines')
        # a disabled group's depth is not checked: it is not cut
        off[g[0].key]['depth'] = 17
        plan_programs(plan, s, off)

    def test_screw_hole_close_to_pocket_warns(self):
        s = Settings()
        # screw hole at (150, 40); head 14 -> clearance 7 + 3 = 10 mm
        near = pocket_shape('p', [rect_loop(155, 30, 40, 30)], holes=[(150, 40)])
        plan, _ = plan_for(near, settings=s)
        pk = by_name(plan_programs(plan, s))['B01C']
        ws = [w for w in pk.warnings if 'screw hole' in w]
        self.assertEqual(len(ws), 1, pk.warnings)
        self.assertTrue(ws[0].startswith('B01C: '), ws[0])
        self.assertIn('B01 p #1 G1 pocket 1', ws[0])
        far = pocket_shape('p', [rect_loop(161, 30, 40, 30)], holes=[(150, 40)])
        plan, _ = plan_for(far, settings=s)
        self.assertEqual(by_name(plan_programs(plan, s))['B01C'].warnings, [])
        # a hole inside the pocket warns too, however far from its outline
        inside = pocket_shape('p', [rect_loop(100, 10, 100, 70)], holes=[(150, 40)])
        plan, _ = plan_for(inside, settings=s)
        pk = by_name(plan_programs(plan, s))['B01C']
        self.assertEqual(len([w for w in pk.warnings if 'screw hole' in w]), 1, pk.warnings)

    def test_fixing_hole_close_to_pocket_warns(self):
        s = Settings()
        # the shape sits at (45, 45); the fixing hole at (15, 15): a pocket at the corner
        plan, _ = plan_for(pocket_shape('p', [rect_loop(0.5, 0.5, 40, 30)]), settings=s)
        b = plan.blanks[0]
        self.assertEqual((b.fix_holes[0].x, b.fix_holes[0].y), (15, 15))
        s.blank.head_dia = 82         # clearance 44 mm reaches the pocket corner (~43.1 mm)
        pk = by_name(blank_programs(b, s))['B01C']
        ws = [w for w in pk.warnings if 'fixing hole' in w]
        self.assertEqual(len(ws), 1, pk.warnings)
        self.assertTrue(ws[0].startswith('B01C: '), ws[0])

    def test_pockets_close_together_warn(self):
        s = Settings()
        close = pocket_shape('p', [rect_loop(100, 50, 40, 30), rect_loop(147, 50, 40, 30)])
        plan, _ = plan_for(close, settings=s)
        pk = by_name(plan_programs(plan, s))['B01C']
        ws = [w for w in pk.warnings if 'pocket' in w and 'apart' in w]
        self.assertEqual(len(ws), 1, pk.warnings)
        self.assertTrue(ws[0].startswith('B01C: '), ws[0])
        apart = pocket_shape('p', [rect_loop(100, 50, 40, 30), rect_loop(149, 50, 40, 30)])
        plan, _ = plan_for(apart, settings=s)
        self.assertEqual(by_name(plan_programs(plan, s))['B01C'].warnings, [])

    def test_line_count_warning_counts_the_pockets(self):
        s = Settings()
        put_bit(s, 65, depth_per_pass=0.5)
        s.pockets.tool = 65
        plan, _ = real_plan(s)
        progs = by_name(plan_programs(plan, s))
        self.assertTrue(any('over 250' in w for w in progs['B01C'].warnings),
                        progs['B01C'].warnings)
        plan, s = real_plan()
        self.assertEqual(by_name(plan_programs(plan, s))['B01C'].warnings, [])

    def test_round_pocket_of_the_tool_diameter_is_one_plunge(self):
        s = Settings()
        c = (200, 100)
        circle = [Arc((204, 100), (196, 100), c, 4, True), Arc((196, 100), (204, 100), c, 4, True)]
        plan, _ = plan_for(pocket_shape('p', [circle]), settings=s)
        pk = pocket_ops(by_name(plan_programs(plan, s))['B01C'])
        self.assertEqual(len(pk), 1)                # one per pass: 8 deep, 9 per pass (R4)
        for o in pk:
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
                  for p in plan_programs(plan, s) for o in p.ops if is_pocket(o)}
        self.assertEqual(labels, {'a': 'G1', 'b': 'G1', 'c': 'G2'})



class PocketHeadTests(unittest.TestCase):
    """A pocket group names a head; its bit gives the diameter, speeds and feeds. A program is
    never written with numbers from a bit other than the one in the head it names."""

    def setUp(self):
        self.s = Settings()
        self.sh = pocket_shape('p', [rect_loop(100, 50, 40, 30)])
        self.plan, _ = plan_for(self.sh, settings=self.s)
        self.key = find_groups([self.sh])[0].key

    def test_group_head_errors_only_when_enabled(self):
        # T65 is empty in the default table
        with self.assertRaises(ProgramError) as cm:
            plan_programs(self.plan, self.s, {self.key: {'tool': 65}})
        self.assertEqual(str(cm.exception), 'pocket group G1: head T65 holds no bit')
        progs = by_name(plan_programs(self.plan, self.s, {self.key: {'tool': 65,
                                                                     'enabled': False}}))
        self.assertEqual(sorted(progs), ['B01C', 'B01D'])
        self.assertFalse([o for o in progs['B01C'].ops if is_pocket(o)])

    def test_check_pocket_heads_names_the_field_to_fix(self):
        groups = find_groups([self.sh])
        self.assertIsNone(check_pocket_heads(self.s, {}, groups, [self.sh]))
        self.assertEqual(check_pocket_heads(self.s, {self.key: {'tool': 65}}, groups, [self.sh]),
                         ('pocket group G1: head T65 holds no bit', 'pockets.G1.tool'))
        s = Settings()
        s.pockets.tool = 65                             # the default head, empty
        self.assertEqual(check_pocket_heads(s, {}, groups, [self.sh]),
                         ('pocket group G1: head T65 holds no bit', 'pockets.tool'))
        # a group with no pocket on the shapes is not checked
        self.assertIsNone(check_pocket_heads(s, {}, groups, [rect('a', 1000, 230)]))
        msg, field = check_pocket_heads(self.s, {self.key: {'tool': 1}}, groups, [self.sh])
        self.assertEqual(field, 'pockets.G1.tool')
        self.assertIn('head T1 cannot be used here', msg)

    def test_empty_pocket_head_without_pockets_plans(self):
        s = Settings()
        put_bit(s, 65, diameter=8)
        s.router.tool = 65
        s.tools.heads.pop(66)
        self.assertEqual(s.pockets.tool, 66)
        s.validate()
        plan, _ = plan_for(rect('a', 1000, 230), settings=s)
        self.assertEqual([p.name for p in plan_programs(plan, s)], ['B01D', 'B01C'])

    def test_pocket_ops_carry_the_bit(self):
        s = Settings()
        put_bit(s, 65, diameter=6, spindle_rpm=16000, plunge_feed=0.5, cut_feed=2)
        s.pockets.tool = 65
        plan, _ = plan_for(self.sh, settings=s)
        c = by_name(plan_programs(plan, s))['B01C']
        pk = pocket_ops(c)
        self.assertEqual({(o.tool, o.spindle_rpm, o.plunge_feed, o.cut_feed) for o in pk},
                         {(65, 16000, 0.5, 2)})
        # the outlines keep the router's numbers: the program's (default bit in T66)
        self.assertEqual((c.tool, c.spindle_rpm, c.plunge_feed, c.cut_feed),
                         (66, 18000, 1, 3))
        self.assertEqual({(o.tool, o.spindle_rpm, o.plunge_feed, o.cut_feed)
                          for o in outline_ops(c)}, {(None, None, None, None)})
        self.assertEqual(c.tools, [65, 66])
        # the wall ring is offset by the 6 mm bit's radius: 40 x 30 pocket -> 34 x 24 ring
        wall = pk[len(pocket_rings(rect_loop(100, 50, 40, 30), 6, 40)) - 1]
        xs = [c for sg in wall.segs for c in (sg.a[0], sg.b[0])]
        ys = [c for sg in wall.segs for c in (sg.a[1], sg.b[1])]
        self.assertEqual((round(max(xs) - min(xs), 6), round(max(ys) - min(ys), 6)), (34, 24))

    def test_obsolete_group_numbers_are_ignored(self):
        ov = {self.key: {'diameter': 6, 'spindle_rpm': 12000, 'stepover_pct': 50}}
        self.assertEqual(plan_programs(self.plan, self.s, ov), plan_programs(self.plan, self.s))

    def test_drills_on_one_head_share_its_bit(self):
        s = Settings()
        s.drill_screw.tool = s.drill_fix.tool
        plan = plan_for(self.sh, settings=s)[0]
        d = by_name(plan_programs(plan, s))['B01D']
        self.assertEqual({(o.tool, o.diameter) for o in d.ops}, {(1, 6)})

    def test_router_numbers_come_from_its_head(self):
        s = Settings()
        put_bit(s, 66, spindle_rpm=12000, plunge_feed=2, cut_feed=5)
        plan, _ = plan_for(rect('a', 1000, 230), settings=s)
        blank = plan.blanks[0]
        cut = next(p for p in blank_programs(blank, s) if p.kind == 'cut')
        self.assertEqual((cut.tool, cut.spindle_rpm, cut.plunge_feed, cut.cut_feed),
                         (66, 12000, 2, 5))
        from nesting.backends.cnc90 import emit
        self.assertIn('S12000', emit(cut, s))

    def test_drill_diameter_comes_from_its_head(self):
        s = Settings()
        put_bit(s, 1, diameter=5)
        plan, _ = plan_for(rect('a', 1000, 230), settings=s)
        d = next(p for p in blank_programs(plan.blanks[0], s) if p.kind == 'drill')
        fixing = [o for o in d.ops if o.tool == s.drill_fix.tool]
        self.assertTrue(fixing)
        self.assertEqual({o.diameter for o in fixing}, {5})


class RealPlatePocketTests(unittest.TestCase):
    """Plate klas 3-1 of the real plates, default settings: the slot's lines in B..C pinned, derived
    from the DXF and the placement (15.1 mm rail slot, 8 mm tool, 40 % stepover: wall ring
    3.55 mm from the slot's centre line, inner ring 0.35 mm; depth 8 in one pass: 9 mm per
    pass, R4)."""

    def test_plate_klas_3_1_slot_rings(self):
        from nesting.backends.cnc90 import emit, fmt
        dxf = read_dxf(repo / 'plates' / 'klas_3-1.dxf')
        self.assertEqual(len(dxf.pockets), 1)
        arcs = [s for s in dxf.pockets[0].outline if isinstance(s, Arc)]
        self.assertEqual(len(arcs), 2)
        half = arcs[0].radius                           # slot half-width (7.55)
        (lx, cy), (rx, _) = sorted(a.center for a in arcs)
        for y_toward in ('front', 'back'):
            with self.subTest(y_toward=y_toward):
                s = Settings()
                s.machine.y_toward = y_toward
                plan, _ = real_plan(s)
                blank, ps = next((b, p) for b in plan.blanks for p in b.shapes
                                 if p.name == 'klas_3-1')
                self.assertEqual((blank.id, ps.x, ps.y, blank.height), ('B06', 45, 45, 560))
                X0, X1, Y = lx + ps.x, rx + ps.x, cy + ps.y          # layout frame
                self.assertEqual((X0, X1, Y), (85, 1630, 135))
                bit = s.tools.bit_in(s.pockets.tool)
                r = bit.diameter / 2
                wall = half - r
                inner = wall - bit.diameter * bit.stepover_pct / 100
                self.assertEqual((round(wall, 6), round(inner, 6)), (3.55, 0.35))
                front = y_toward == 'front'

                def y(v):
                    return blank.height - v if front else v
                arc = 'G2'      # cw seen from above, whatever the Y direction (2026-11-20)
                lines = []
                for z in (8,):                  # one pass: the bit cuts 9 mm per pass (R4)
                    for u in (inner, wall):
                        top, bot = fmt(y(Y + u)), fmt(y(Y - u))
                        lines += [f'G88G90G54P5T0166S18000F1X{fmt(X0)}Y{top}Z{z}',
                                  f'G1G90F3X{fmt(X1)}Y{top}Z{z}',
                                  f'{arc}G90G17X{fmt(X1)}Y{bot}U{fmt(u)}',
                                  f'G1G90X{fmt(X0)}Y{bot}Z{z}',
                                  f'{arc}G90G17X{fmt(X0)}Y{top}U{fmt(u)}']
                c = by_name(plan_programs(plan, s))['B06C']
                ops = [o for o in pocket_ops(c) if ' klas_3-1 ' in o.label]
                one = Program('B06C', c.tool, 'cut', '', c.stock, ops, c.spindle_rpm,
                              c.plunge_feed, c.cut_feed)
                got = emit(one, s).split('\r\n')[2:-2]
                self.assertEqual(got, lines)
                # the whole cut program starts with its pockets' lines (these among them, in
                # one run), the outlines follow
                pockets_only = Program('B06C', c.tool, 'cut', '', c.stock, pocket_ops(c),
                                       c.spindle_rpm, c.plunge_feed, c.cut_feed)
                head = emit(pockets_only, s).split('\r\n')[2:-2]
                whole = emit(c, s).split('\r\n')
                self.assertEqual(whole[2:2 + len(head)], head)
                self.assertTrue(any(head[i:i + len(lines)] == lines for i in range(len(head))))
                text = '\n'.join(got)
                if front:
                    for v in ('Y421.45', 'Y428.55', 'Y424.65', 'Y425.35'):
                        self.assertIn(v, text)
                else:
                    for v in ('Y131.45', 'Y138.55', 'Y134.65', 'Y135.35'):
                        self.assertIn(v, text)
                self.assertEqual(set(re.findall(r'U[\d.]+', text)), {'U3.55', 'U0.35'})


class ZCorrectionTests(unittest.TestCase):
    """The tool table's Z correction per head: how much deeper the head really cuts than
    written (T66 on the machine, 2026-11-20). Every op on that head is written that much
    shallower; the passes stay the same; other heads are untouched."""

    def plan(self, corrections):
        s = Settings()
        s.tools.z_corrections = dict(corrections)
        plan, _ = real_plan(s)
        return {p.name: p for p in plan_programs(plan, s)}, s

    def test_router_ops_are_written_shallower_by_the_correction(self):
        base, _ = self.plan({})
        corr, s = self.plan({66: 4})
        self.assertEqual(set(base), set(corr))
        for name, p in base.items():
            q = corr[name]
            self.assertEqual(len(p.ops), len(q.ops), name)          # same passes
            for a, b in zip(p.ops, q.ops):
                if isinstance(a, DrillOp):
                    self.assertEqual(a.depth, b.depth)
                else:
                    self.assertEqual(p.op_tool(a), 66)
                    self.assertAlmostEqual(b.depth, a.depth - 4, places=9)

    def test_a_drill_head_correction_moves_only_its_holes(self):
        base, s = self.plan({})
        corr, _ = self.plan({s.drill_fix.tool: 0.5})
        for name, p in base.items():
            for a, b in zip(p.ops, corr[name].ops):
                want = a.depth - 0.5 if p.op_tool(a) == s.drill_fix.tool else a.depth
                self.assertAlmostEqual(b.depth, want, places=9)

    def test_another_head_is_not_corrected(self):
        def c_program(corr):
            s = Settings()
            put_bit(s, 65)
            s.pockets.tool = 65
            s.tools.z_corrections = dict(corr)
            plan, _ = real_plan(s)
            return by_name(plan_programs(plan, s))['B01C']
        base, c = c_program({}), c_program({66: 4})
        for a, b in zip(base.ops, c.ops):
            if ' pocket ' in a.label:
                self.assertEqual(c.op_tool(b), 65)
                self.assertEqual(a.depth, b.depth)
            else:
                self.assertAlmostEqual(b.depth, a.depth - 4, places=9)

    def test_a_correction_that_leaves_no_depth_is_an_error(self):
        with self.assertRaises(ProgramError) as e:
            self.plan({66: 7})            # the first slot pass is 5.5 mm deep
        self.assertIn('T66', str(e.exception))
        self.assertIn('z_corrections', str(e.exception))


class RingMemoTests(unittest.TestCase):
    """Process-wide memo of pocket rings: keyed on the exact segment numbers, tool diameter
    and stepover, so a repeated plan (every /api/plan) does not recompute them."""

    def setUp(self):
        pockets.clear_ring_memo()
        self.addCleanup(pockets.clear_ring_memo)

    def test_same_numbers_give_the_same_rings(self):
        outline = slot_loop(10, 10, 300, 20)
        a = memo_pocket_rings(outline, 8, 40)
        self.assertEqual(a, pocket_rings(outline, 8, 40))
        a[0].clear()                                 # the caller's copy, not the memo's
        with mock.patch.object(pockets, 'pocket_rings', side_effect=AssertionError('missed')):
            # a new outline with the same numbers is a hit; the test's own name for
            # pocket_rings is the real function, not the patched module attribute
            self.assertEqual(memo_pocket_rings(slot_loop(10, 10, 300, 20), 8, 40),
                             pocket_rings(outline, 8, 40))
            for args in ((outline, 10, 40), (outline, 8, 30),
                         (slot_loop(10, 10, 300 + 1e-9, 20), 8, 40)):   # exact: no tolerance
                with self.assertRaises(AssertionError):
                    memo_pocket_rings(*args)
        self.assertNotEqual(memo_pocket_rings(outline, 10, 40), pocket_rings(outline, 8, 40))

    def test_memo_is_bounded_oldest_first(self):
        with mock.patch.object(pockets, 'RING_MEMO_SIZE', 3):
            loops = [rect_loop(0, 0, 40 + i, 30) for i in range(4)]
            for lp in loops:
                memo_pocket_rings(lp, 8, 40)
            self.assertEqual(len(pockets._RING_MEMO), 3)
            with mock.patch.object(pockets, 'pocket_rings', side_effect=AssertionError('missed')):
                for lp in loops[1:]:
                    memo_pocket_rings(lp, 8, 40)
                with self.assertRaises(AssertionError):      # the oldest was dropped
                    memo_pocket_rings(loops[0], 8, 40)
            self.assertEqual(len(pockets._RING_MEMO), 3)

    def test_errors_are_not_memoised(self):
        outline = rect_loop(0, 0, 5, 5)              # narrower than the tool
        for _ in range(2):
            with self.assertRaises(PocketError):
                memo_pocket_rings(outline, 8, 40)
        self.assertEqual(len(pockets._RING_MEMO), 0)

    def test_second_plan_does_not_recompute_rings_and_diameter_still_counts(self):
        plan, s = real_plan()
        first = by_name(plan_programs(plan, s))
        with mock.patch.object(pockets, 'pocket_rings', side_effect=AssertionError('recomputed')):
            again = by_name(plan_programs(plan, s))
            self.assertEqual(again['B01C'].ops, first['B01C'].ops)
            s6 = Settings()
            put_bit(s6, 65, diameter=6)
            s6.pockets.tool = 65
            with self.assertRaises(AssertionError):
                plan_programs(plan, s6)
        other = by_name(plan_programs(plan, s6))
        self.assertNotEqual(pocket_ops(other['B01C']), pocket_ops(first['B01C']))
        self.assertEqual(outline_ops(other['B01C']), outline_ops(first['B01C']))


if __name__ == '__main__':
    unittest.main()
