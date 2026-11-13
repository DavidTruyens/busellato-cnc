import unittest
from pathlib import Path

from nesting.dxf import Hole, Shape, read_dxf
from nesting.geometry import Line
from nesting.layout import (MAX_QTY, Blank, LayoutError, Plan, ShapeEntry, build_blanks,
                            build_plan, footprint, saw_plan, to_panel)
from nesting.settings import Settings

repo = Path(__file__).resolve().parent.parent
EPS = 1e-6


def rect(name, length, width, holes=True):
    outline = [Line((0, 0), (length, 0)), Line((length, 0), (length, width)),
               Line((length, width), (0, width)), Line((0, width), (0, 0))]
    hs = [Hole(150, 40, 6.6), Hole(length - 150, 40, 6.6)] if holes else []
    return Shape(name, outline, hs)


def entries(*shapes, qty=1):
    return [ShapeEntry(s, qty=qty) for s in shapes]


def real_entries():
    return [ShapeEntry(read_dxf(p)) for p in sorted((repo / 'plates').glob('*.dxf'))]


def names(b):
    return sorted(p.name for p in b.shapes)


def one_blank(length, width, settings, name='a'):
    """A blank of exactly length x width (whole mm) around one shape, with default margins."""
    m = settings.blank
    return rect(name, length - 2 * m.margin_end, width - 2 * m.margin_side, holes=False)


def check_guillotine(tc, plan, settings, n_blanks=None):
    """Replay every panel's cut list on the panel, independently of the layout code:
    each cut must run edge to edge through exactly one current piece, kerf respected,
    and every blank must end up as exactly one resulting piece, inside the trimmed panel."""
    p = settings.panel
    L, W, e, k = p.length, p.width, p.edge, p.kerf
    seen = []
    for pan in plan.panels:
        pieces = [(0.0, 0.0, L, W)]                 # x0, y0, x1, y1
        stages = [c.stage for c in pan.cuts]
        n1 = stages.count(1)
        tc.assertEqual(stages[:n1], [1] * n1)       # all strip cuts first ...
        tc.assertTrue(all(st in (2, 3) for st in stages[n1:]), stages)
        ats = [c.at for c in pan.cuts[:n1]]
        tc.assertEqual(ats, sorted(ats))            # ... from the origin side outward
        tc.assertEqual([c.n for c in pan.cuts], list(range(1, len(pan.cuts) + 1)))
        for c in pan.cuts:
            hits = []
            for r in pieces:
                if c.axis == 'x':       # line at constant y, from x=start to x=end
                    full = abs(r[0] - c.start) < EPS and abs(r[2] - c.end) < EPS
                    inside = r[1] - EPS <= c.at and c.at < r[3] - EPS
                else:
                    full = abs(r[1] - c.start) < EPS and abs(r[3] - c.end) < EPS
                    inside = r[0] - EPS <= c.at and c.at < r[2] - EPS
                if full and inside:
                    hits.append(r)
            tc.assertEqual(len(hits), 1, (pan.id, c, pieces))
            r = hits[0]
            pieces.remove(r)
            if c.axis == 'x':
                lo, hi = (r[0], r[1], r[2], c.at), (r[0], min(c.at + k, r[3]), r[2], r[3])
            else:
                lo, hi = (r[0], r[1], c.at, r[3]), (min(c.at + k, r[2]), r[1], r[2], r[3])
            if c.size:
                tc.assertAlmostEqual(lo[2] - lo[0], c.size[0], delta=EPS, msg=c)
                tc.assertAlmostEqual(lo[3] - lo[1], c.size[1], delta=EPS, msg=c)
            pieces += [q for q in (lo, hi) if q[2] - q[0] > EPS and q[3] - q[1] > EPS]
        for b in pan.blanks:
            w, h = footprint(b)
            box = (b.x, b.y, b.x + w, b.y + h)
            tc.assertTrue(e - EPS <= box[0] and box[2] <= L - e + EPS
                          and e - EPS <= box[1] and box[3] <= W - e + EPS, (b.id, box))
            same = [q for q in pieces if all(abs(q[i] - box[i]) < EPS for i in range(4))]
            tc.assertEqual(len(same), 1, (pan.id, b.id, box))
            seen.append(b.id)
        boxes = [(b.x, b.y, b.x + footprint(b)[0], b.y + footprint(b)[1]) for b in pan.blanks]
        for i, a in enumerate(boxes):
            for o in boxes[i + 1:]:
                sep = max(o[0] - a[2], a[0] - o[2], o[1] - a[3], a[1] - o[3])
                tc.assertGreaterEqual(sep, k - EPS)          # no overlap, a kerf between
    tc.assertEqual(len(seen), len(set(seen)))
    if n_blanks is not None:
        tc.assertEqual(len(seen), n_blanks)


class Pairing(unittest.TestCase):
    def test_neighbours_by_length(self):
        plan = build_plan(entries(rect('a', 2000, 230), rect('b', 1000, 230),
                                  rect('c', 1990, 230), rect('d', 1010, 230)), Settings())
        self.assertEqual(sorted(names(b) for b in plan.blanks), [['a', 'c'], ['b', 'd']])

    def test_odd_count_leaves_a_single(self):
        plan = build_plan(entries(*[rect(x, 1500, 230) for x in 'abc']), Settings())
        self.assertEqual(sorted(len(b.shapes) for b in plan.blanks), [1, 2])

    def test_quantity(self):
        es = [ShapeEntry(rect('a', 1500, 230), qty=3), ShapeEntry(rect('b', 1500, 230), qty=0)]
        plan = build_plan(es, Settings())
        shapes = [p for b in plan.blanks for p in b.shapes]
        self.assertEqual(sorted((p.name, p.copy) for p in shapes), [('a', 1), ('a', 2), ('a', 3)])

    def test_quantity_zero_skipped(self):
        plan = build_plan([ShapeEntry(rect('a', 1500, 230), qty=0)], Settings())
        self.assertEqual((plan.panels, plan.problems), ([], []))

    def test_empty_when_nothing_enabled(self):
        self.assertEqual(build_plan([], Settings()).panels, [])
        plan = build_plan([ShapeEntry(rect('a', 1500, 230), enabled=False)], Settings())
        self.assertEqual(plan.panels, [])
        self.assertEqual(plan.problems, [])

    def test_group_by_order_keeps_list_order(self):
        s = Settings()
        s.blank.group_by = 'order'
        plan = build_plan(entries(rect('a', 2000, 230), rect('b', 1000, 230),
                                  rect('c', 1990, 230), rect('d', 1010, 230)), s)
        self.assertEqual(sorted(names(b) for b in plan.blanks), [['a', 'b'], ['c', 'd']])


class BlankGeometry(unittest.TestCase):
    def setUp(self):
        self.s = Settings()

    def one(self, *shapes, settings=None):
        plan = build_plan(entries(*shapes), settings or self.s)
        self.assertEqual(plan.problems, [])
        return plan.blanks[0]

    def test_size_and_holes(self):
        b = self.one(rect('a', 2000, 230), rect('b', 1900, 220))
        c = self.s.blank
        self.assertEqual(b.width, 2000 + 2 * c.margin_end)
        self.assertEqual(b.height, 450 + self.s.gap + 2 * c.margin_side)
        self.assertEqual(len(b.fix_holes), 4)
        self.assertEqual(len(b.screw_holes), 4)
        a = [p for p in b.shapes if p.name == 'a'][0]     # widest at the bottom
        self.assertAlmostEqual(a.y, c.margin_side)
        self.assertAlmostEqual(a.x, c.margin_end)
        self.assertAlmostEqual(b.screw_holes[0].x, c.margin_end + 150)
        self.assertAlmostEqual(b.screw_holes[0].y, c.margin_side + 40)
        self.assertEqual(b.screw_holes[0].diameter, self.s.drill_screw.diameter)
        self.assertEqual(b.fix_holes[0].diameter, self.s.drill_fix.diameter)

    def test_size_is_rounded_up_to_whole_mm(self):
        b = self.one(rect('a', 1000.2, 230.7))
        self.assertEqual((b.width, b.height), (1091, 321))
        ins = self.s.blank.fix_inset
        self.assertEqual(sorted({h.x for h in b.fix_holes}), [ins, 1091 - ins])
        self.assertEqual(sorted({h.y for h in b.fix_holes}), [ins, 321 - ins])

    def test_fixing_holes_clear_of_shapes(self):
        b = self.one(rect('a', 2000, 230), rect('b', 1900, 220))
        for h in b.fix_holes:
            for p in b.shapes:
                inside = (p.x <= h.x <= p.x + p.shape.length
                          and p.y <= h.y <= p.y + p.shape.width)
                self.assertFalse(inside)

    def test_too_small_margin_is_a_hard_error(self):
        s = Settings()
        s.blank.margin_end = 20
        s.blank.margin_side = 20
        with self.assertRaises(LayoutError) as cm:
            build_plan(entries(rect('a', 2000, 230)), s)
        self.assertIn('a', str(cm.exception))
        self.assertIsInstance(cm.exception, ValueError)


class ScrewHeadClearance(unittest.TestCase):
    """C2: the cutter edge runs a full diameter outside the shape; the head must stay clear
    of it, and must sit inside the blank with 3 mm to spare."""

    def settings(self, tool=66, dia=8, margin=45, inset=15):
        s = Settings()
        s.router.tool, s.router.diameter = tool, dia
        s.blank.margin_end = s.blank.margin_side = margin
        s.blank.fix_inset = inset
        return s

    def rejected(self, s, *needles):
        with self.assertRaises(LayoutError) as cm:
            build_plan(entries(rect('sharp', 1000, 200)), s)
        for n in ('sharp',) + needles:
            self.assertIn(n, str(cm.exception))
        return str(cm.exception)

    def test_reviewer_case_t66_d8_margin_20_inset_10(self):
        # head 0.86 mm inside the cutter path: hole (10,10), shape corner (20,20), 14.1 < 8+7+3
        self.rejected(self.settings(margin=20, inset=10), 'need 18.0')

    def test_reviewer_case_t65_d18_margin_25_inset_10(self):
        # 21.2 mm from the shape, needs 18+7+3 = 28
        self.rejected(self.settings(tool=65, dia=18, margin=25, inset=10), 'need 28.0')

    def test_inset_too_small_for_the_head(self):
        msg = self.rejected(self.settings(inset=3), 'inset 3', '10')
        self.assertIn('blank', msg)

    def test_inset_exactly_head_radius_plus_3_is_fine(self):
        plan = build_plan(entries(rect('sharp', 1000, 200)), self.settings(inset=10))
        self.assertEqual(len(plan.blanks), 1)

    def test_defaults_and_real_plates_keep_clearance(self):
        s = Settings()
        plan = build_plan(real_entries(), s)
        need = s.router.diameter + s.blank.head_dia / 2 + 3.0     # 18
        for b in plan.blanks:
            for h in b.fix_holes:
                self.assertGreaterEqual(min(h.x, h.y, b.width - h.x, b.height - h.y),
                                        s.blank.head_dia / 2 + 3.0)
                for p in b.shapes:
                    dx = max(p.x - h.x, 0, h.x - (p.x + p.shape.length))
                    dy = max(p.y - h.y, 0, h.y - (p.y + p.shape.width))
                    self.assertGreaterEqual((dx * dx + dy * dy) ** 0.5, need)


class WorkFrame(unittest.TestCase):
    """A blank must fit the machine work frame (frame_x along the long side)."""

    def test_default_blanks_fit_the_frame(self):
        s = Settings()
        for b in build_plan(real_entries(), s).blanks:
            self.assertLessEqual(b.width, s.machine.frame_x)
            self.assertLessEqual(b.height, s.machine.frame_y)
            self.assertGreaterEqual(b.width, b.height)          # long side along machine X

    def test_frame_y_forces_a_split(self):
        # two 400 wide shapes: 400 + 12 + 400 + 90 = 902 > 787, so one shape per blank
        s = Settings()
        blanks = build_blanks(entries(rect('a', 1500, 400), rect('b', 1490, 400)), s)
        self.assertEqual(sorted(names(b) for b in blanks), [['a'], ['b']])
        self.assertTrue(all(b.height <= 787 for b in blanks))
        s.machine.frame_y = 902
        blanks = build_blanks(entries(rect('a', 1500, 400), rect('b', 1490, 400)), s)
        self.assertEqual([names(b) for b in blanks], [['a', 'b']])
        self.assertEqual(blanks[0].height, 902)

    def test_split_keeps_as_many_as_fit(self):
        # shapes_per 3, only two fit within frame_y: 2 + 1, not 1 + 1 + 1
        s = Settings()
        s.blank.shapes_per = 3
        blanks = build_blanks(entries(*[rect(x, 1500, 300) for x in 'abc']), s)
        self.assertEqual(sorted(len(b.shapes) for b in blanks), [1, 2])

    def test_no_auto_grow_beyond_shapes_per(self):
        # three 150 wide shapes would fit in frame_y, but shapes_per is 2
        s = Settings()
        blanks = build_blanks(entries(*[rect(x, 1500, 150) for x in 'abc']), s)
        self.assertEqual(sorted(len(b.shapes) for b in blanks), [1, 2])
        s.blank.shapes_per = 3
        self.assertEqual(len(build_blanks(entries(*[rect(x, 1500, 150) for x in 'abc']), s)), 1)

    def test_one_shape_too_wide_for_the_frame_is_a_hard_error(self):
        with self.assertRaises(LayoutError) as cm:
            build_plan(entries(rect('wide one', 1000, 700), rect('ok', 1000, 230)), Settings())
        msg = str(cm.exception)
        self.assertIn('wide one', msg)
        self.assertIn('work frame 3072 x 787', msg)
        self.assertIn('to verify', msg)
        self.assertNotIn('ok', msg.replace('work', ''))

    def test_one_shape_too_long_for_the_frame_is_a_hard_error(self):
        s = Settings()
        s.machine.frame_x = 1500
        with self.assertRaises(LayoutError) as cm:
            build_plan(entries(rect('long', 1450, 200)), s)
        self.assertIn('long', str(cm.exception))
        self.assertIn('machine.frame_x', str(cm.exception))

    def test_too_long_for_the_panel_is_a_hard_error(self):
        # fits the frame, but 2400 + 90 is longer than the trimmed panel
        with self.assertRaises(LayoutError) as cm:
            build_plan(entries(rect('wide', 2400, 230)), Settings())
        self.assertIn('wide', str(cm.exception))
        self.assertIn('panel', str(cm.exception))

    def test_every_unfit_shape_is_named_once(self):
        with self.assertRaises(LayoutError) as cm:
            build_plan([ShapeEntry(rect('x1', 3000, 200), qty=3),
                        ShapeEntry(rect('x2', 1000, 900))], Settings())
        msg = str(cm.exception)
        self.assertEqual(msg.count('x1:'), 1)
        self.assertEqual(msg.count('x2:'), 1)


class Guillotine(unittest.TestCase):
    def test_validator_catches_a_bad_plan(self):
        s = Settings()
        for change in ('at', 'start', 'size', 'x'):
            with self.subTest(change=change):
                plan = build_plan(real_entries(), s)
                pan = plan.panels[0]
                if change == 'at':
                    pan.cuts[1].at -= 20            # strip cut through the first blank
                elif change == 'start':
                    pan.cuts[-1].start += 5         # stage 2 cut not edge to edge
                elif change == 'size':
                    pan.cuts[1].size = (2440, 1)
                else:
                    pan.blanks[0].x += 1            # blank not where the saw leaves it
                with self.assertRaises(AssertionError):
                    check_guillotine(self, plan, s)

    def test_real_plates_plan_is_valid(self):
        s = Settings()
        plan = build_plan(real_entries(), s)
        self.assertEqual(sum(len(b.shapes) for b in plan.blanks), 12)
        check_guillotine(self, plan, s, n_blanks=6)
        self.assertEqual(len(plan.panels), 3)

    def test_blank_ids_in_cut_order(self):
        plan = build_plan(real_entries(), Settings())
        ids = [b.id for b in plan.blanks]
        self.assertEqual(ids, ['B01', 'B02', 'B03', 'B04', 'B05', 'B06'])
        for pan in plan.panels:
            for b in pan.blanks:
                self.assertEqual(b.panel, pan.id)

    def test_deterministic(self):
        a = build_plan(real_entries(), Settings())
        b = build_plan(real_entries(), Settings())
        self.assertEqual([(p.id, p.strips, p.cuts) for p in a.panels],
                         [(p.id, p.strips, p.cuts) for p in b.panels])
        self.assertEqual([(x.id, x.x, x.y, x.rotated, names(x)) for x in a.blanks],
                         [(x.id, x.x, x.y, x.rotated, names(x)) for x in b.blanks])

    def test_cut_list_of_one_blank(self):
        s = Settings()
        plan = build_plan(entries(one_blank(1100, 700, s)), s)
        (pan,) = plan.panels
        self.assertEqual(pan.strips, 'x')
        got = [(c.n, c.stage, c.axis, c.at, c.start, c.end, c.frees, c.blanks, c.size)
               for c in pan.cuts]
        self.assertEqual(got, [
            (1, 1, 'x', 6, 0, 2440, 'offcut', [], (2440, 6)),          # trim: kerf 6..10
            (2, 1, 'x', 710, 0, 2440, 'strip', ['B01'], (2440, 700)),
            (3, 2, 'y', 6, 10, 710, 'offcut', [], (6, 700)),
            (4, 2, 'y', 1110, 10, 710, 'blank', ['B01'], (1100, 700)),
        ])
        b = pan.blanks[0]
        self.assertEqual((b.x, b.y, b.rotated), (10, 10, False))

    def test_cut_list_order_and_stage_3_trim(self):
        s = Settings()
        blanks = build_blanks([ShapeEntry(one_blank(1100, 700, s, 'tall')),
                               ShapeEntry(one_blank(1100, 600, s, 'low'))], s)
        (pan,) = saw_plan(blanks, s, directions=('x',))
        got = [(c.stage, c.axis, c.at, c.start, c.end, c.frees, c.blanks, c.size)
               for c in pan.cuts]
        self.assertEqual(got, [
            (1, 'x', 6, 0, 2440, 'offcut', [], (2440, 6)),
            (1, 'x', 710, 0, 2440, 'strip', ['B01', 'B02'], (2440, 700)),
            (2, 'y', 6, 10, 710, 'offcut', [], (6, 700)),
            (2, 'y', 1110, 10, 710, 'blank', ['B01'], (1100, 700)),
            (2, 'y', 2214, 10, 710, 'rough', ['B02'], (1100, 700)),
            (3, 'x', 610, 1114, 2214, 'blank', ['B02'], (1100, 600)),
        ])
        self.assertEqual([c.n for c in pan.cuts], list(range(1, 7)))
        check_guillotine(self, Plan([pan]), s, n_blanks=2)

    def test_picks_the_direction_with_fewest_panels(self):
        # 1100 x 700 blanks: strips along X hold 2 per panel, strips along Y hold 3 (turned)
        s = Settings()
        es = [ShapeEntry(one_blank(1100, 700, s), qty=3)]
        blanks = build_blanks(es, s)
        self.assertEqual(len(saw_plan(blanks, s, directions=('x',))), 2)
        plan = build_plan(es, s)
        self.assertEqual(len(plan.panels), 1)
        self.assertEqual(plan.panels[0].strips, 'y')
        self.assertTrue(all(b.rotated for b in plan.blanks))
        check_guillotine(self, plan, s, n_blanks=3)

    def test_same_panels_less_sliver_waste_wins(self):
        # x strips: the 600 blank shares a 700 strip (sliver); y strips: no sliver
        s = Settings()
        es = [ShapeEntry(one_blank(1100, 700, s, 'tall')), ShapeEntry(one_blank(1100, 600, s, 'low'))]
        plan = build_plan(es, s)
        self.assertEqual(plan.panels[0].strips, 'y')
        self.assertFalse(any(c.stage == 3 for c in plan.panels[0].cuts))
        check_guillotine(self, plan, s, n_blanks=2)

    def test_rotated_blanks_on_a_swapped_panel(self):
        # panel 1220 long x 2440 wide: the 2 m blanks must turn 90 degrees
        s = Settings()
        s.panel.length, s.panel.width = 1220, 2440
        plan = build_plan(real_entries(), s)
        self.assertTrue(all(b.rotated for b in plan.blanks))
        check_guillotine(self, plan, s, n_blanks=6)
        for b in plan.blanks:
            fw, fh = footprint(b)
            self.assertEqual((fw, fh), (b.height, b.width))
            for p in b.shapes:
                for seg in p.shape.outline:
                    x, y = to_panel(b, p.x + seg.a[0], p.y + seg.a[1])
                    self.assertTrue(b.x - EPS <= x <= b.x + fw + EPS
                                    and b.y - EPS <= y <= b.y + fh + EPS)

    def test_many_blanks_with_mixed_sizes(self):
        s = Settings()
        es = [ShapeEntry(rect('a', 2000, 230), qty=7), ShapeEntry(rect('b', 600, 120), qty=9),
              ShapeEntry(rect('c', 1200, 300), qty=5), ShapeEntry(rect('d', 300, 500), qty=3)]
        plan = build_plan(es, s)
        check_guillotine(self, plan, s, n_blanks=len(plan.blanks))
        self.assertEqual(sum(len(b.shapes) for b in plan.blanks), 24)
        for d in ('x', 'y'):
            one = Plan(saw_plan(plan.blanks, s, directions=(d,)))
            check_guillotine(self, one, s, n_blanks=len(plan.blanks))

    def test_edge_zero_has_no_trim_cuts(self):
        s = Settings()
        s.panel.edge = 0
        plan = build_plan(entries(one_blank(1100, 700, s)), s)
        self.assertFalse(any(c.frees == 'offcut' for c in plan.panels[0].cuts))
        self.assertEqual((plan.blanks[0].x, plan.blanks[0].y), (0, 0))
        check_guillotine(self, plan, s, n_blanks=1)

    def test_kerf_between_blanks(self):
        s = Settings()
        s.panel.kerf = 10
        s.panel.edge = 10
        blanks = build_blanks([ShapeEntry(one_blank(1100, 500, s), qty=4)], s)
        plan = Plan(saw_plan(blanks, s, directions=('x',)))
        check_guillotine(self, plan, s, n_blanks=4)
        xs = sorted({b.x for b in plan.blanks})
        ys = sorted({b.y for b in plan.blanks})
        self.assertEqual(xs, [10, 1120])
        self.assertEqual(ys, [10, 520])

    def test_waste_per_panel(self):
        s = Settings()
        plan = build_plan(entries(one_blank(1100, 700, s)), s)
        self.assertEqual(plan.panels[0].waste(s), 2440 * 1220 - 1100 * 700)

    def test_rotation_transform_maps_corners_inside_footprint(self):
        b = Blank('B', 300.0, 100.0, [], [], [], 'P1', 50.0, 20.0, True)
        pts = [to_panel(b, x, y) for x, y in ((0, 0), (300, 0), (300, 100), (0, 100))]
        self.assertEqual(sorted(pts), [(50.0, 20.0), (50.0, 320.0), (150.0, 20.0), (150.0, 320.0)])
        self.assertEqual(to_panel(b, 1, 0), (150.0, 21.0))       # blank +x -> panel +y
        self.assertEqual(footprint(b), (100.0, 300.0))


class QuantityLimitTests(unittest.TestCase):
    def test_max_qty_is_500(self):
        self.assertEqual(MAX_QTY, 500)

    def test_quantity_over_limit_raises_before_expanding(self):
        import time
        for qty in (501, 10 ** 30):
            with self.subTest(qty=qty):
                t0 = time.monotonic()
                with self.assertRaises(ValueError) as cm:
                    build_plan([ShapeEntry(rect('big one', 500, 200), qty=qty)], Settings())
                self.assertLess(time.monotonic() - t0, 0.5)
                self.assertIn('big one', str(cm.exception))
                self.assertIn(str(qty), str(cm.exception))
                self.assertIn('500', str(cm.exception))

    def test_negative_quantity_raises(self):
        with self.assertRaises(ValueError) as cm:
            build_plan([ShapeEntry(rect('neg', 500, 200), qty=-1)], Settings())
        self.assertIn('neg', str(cm.exception))

    def test_limit_itself_and_disabled_entries_are_fine(self):
        build_plan([ShapeEntry(rect('off', 500, 200), qty=10 ** 30, enabled=False)], Settings())
        plan = build_plan([ShapeEntry(rect('small', 100, 50, holes=False), qty=MAX_QTY)], Settings())
        self.assertEqual(sum(len(b.shapes) for b in plan.blanks), MAX_QTY)
        self.assertEqual(plan.blanks[-1].id, 'B250')       # 3 digits once past 99


if __name__ == '__main__':
    unittest.main()
