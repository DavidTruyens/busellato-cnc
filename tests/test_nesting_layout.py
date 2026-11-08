import unittest
from pathlib import Path

from nesting.dxf import Hole, Shape, read_dxf
from nesting.geometry import Line
from nesting.layout import (MAX_QTY, PlacedTemplate, ShapeEntry, build_plan, footprint,
                            to_panel)
from nesting.settings import Settings

repo = Path(__file__).resolve().parent.parent


def rect(name, length, width, holes=True):
    outline = [Line((0, 0), (length, 0)), Line((length, 0), (length, width)),
               Line((length, width), (0, width)), Line((0, width), (0, 0))]
    hs = [Hole(150, 40, 6.6), Hole(length - 150, 40, 6.6)] if holes else []
    return Shape(name, outline, hs)


def entries(*shapes, qty=1):
    return [ShapeEntry(s, qty=qty) for s in shapes]


def real_entries():
    return [ShapeEntry(read_dxf(p)) for p in sorted((repo / 'plates').glob('*.dxf'))]


def all_templates(plan):
    return [t for p in plan.panels for t in p.templates]


def names(t):
    return sorted(p.name for p in t.shapes)


class Pairing(unittest.TestCase):
    def test_neighbours_by_length(self):
        plan = build_plan(entries(rect('a', 2000, 230), rect('b', 1000, 230),
                                  rect('c', 1990, 230), rect('d', 1010, 230)), Settings())
        self.assertEqual(sorted(names(t) for t in all_templates(plan)), [['a', 'c'], ['b', 'd']])

    def test_odd_count_leaves_a_single(self):
        plan = build_plan(entries(*[rect(x, 1500, 230) for x in 'abc']), Settings())
        self.assertEqual(sorted(len(t.shapes) for t in all_templates(plan)), [1, 2])

    def test_quantity(self):
        es = [ShapeEntry(rect('a', 1500, 230), qty=3), ShapeEntry(rect('b', 1500, 230), qty=0)]
        plan = build_plan(es, Settings())
        shapes = [p for t in all_templates(plan) for p in t.shapes]
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
        s.template.group_by = 'order'
        plan = build_plan(entries(rect('a', 2000, 230), rect('b', 1000, 230),
                                  rect('c', 1990, 230), rect('d', 1010, 230)), s)
        self.assertEqual(sorted(names(t) for t in all_templates(plan)), [['a', 'b'], ['c', 'd']])

    def test_thickness_override_and_default(self):
        s = Settings()
        es = [ShapeEntry(rect('a', 1500, 230), thickness=22), ShapeEntry(rect('b', 1500, 230))]
        plan = build_plan(es, s)
        th = {p.name: p.thickness for t in all_templates(plan) for p in t.shapes}
        self.assertEqual(th, {'a': 22, 'b': s.heights.shape_thickness})


class Template(unittest.TestCase):
    def setUp(self):
        self.s = Settings()

    def one(self, *shapes, settings=None):
        plan = build_plan(entries(*shapes), settings or self.s)
        self.assertEqual(plan.problems, [])
        return all_templates(plan)[0]

    def test_size_and_holes(self):
        t = self.one(rect('a', 2000, 230), rect('b', 1900, 220))
        c = self.s.template
        self.assertAlmostEqual(t.width, 2000 + 2 * c.margin_end)
        self.assertAlmostEqual(t.height, 450 + self.s.gap + 2 * c.margin_side)
        self.assertEqual(len(t.fix_holes), 4)
        self.assertEqual(len(t.screw_holes), 4)
        a = [p for p in t.shapes if p.name == 'a'][0]     # widest at the bottom
        self.assertAlmostEqual(a.y, c.margin_side)
        self.assertAlmostEqual(a.x, c.margin_end)
        self.assertAlmostEqual(t.screw_holes[0].x, c.margin_end + 150)
        self.assertAlmostEqual(t.screw_holes[0].y, c.margin_side + 40)
        self.assertEqual(t.screw_holes[0].diameter, self.s.drill_screw.diameter)
        self.assertEqual(t.fix_holes[0].diameter, self.s.drill_fix.diameter)

    def test_fixing_holes_clear_of_plates(self):
        t = self.one(rect('a', 2000, 230), rect('b', 1900, 220))
        for h in t.fix_holes:
            for p in t.shapes:
                inside = (p.x <= h.x <= p.x + p.shape.length
                          and p.y <= h.y <= p.y + p.shape.width)
                self.assertFalse(inside)

    def test_too_small_margin_is_rejected(self):
        s = Settings()
        s.template.margin_end = 20
        s.template.margin_side = 20
        plan = build_plan(entries(rect('a', 2000, 230)), s)
        self.assertEqual(plan.panels, [])
        self.assertEqual(len(plan.problems), 1)
        self.assertIn('a', plan.problems[0])

    def test_fixed_template_size(self):
        s = Settings()
        s.template.mode = 'fixed'
        s.template.fixed_width = 1000
        s.template.fixed_height = 400
        t = self.one(rect('a', 800, 230), settings=s)
        self.assertEqual((t.width, t.height), (1000, 400))
        self.assertEqual(len(t.fix_holes), 4)

    def test_fixed_template_too_small_is_a_problem(self):
        s = Settings()
        s.template.mode = 'fixed'
        s.template.fixed_width = 500
        s.template.fixed_height = 400
        plan = build_plan(entries(rect('a', 800, 230)), s)
        self.assertEqual(plan.panels, [])
        self.assertIn('a', plan.problems[0])

    def test_none_mode_has_no_fixing_holes(self):
        s = Settings()
        s.template.mode = 'none'
        plan = build_plan(entries(rect('a', 1500, 230), rect('b', 1490, 230)), s)
        ts = all_templates(plan)
        self.assertEqual(len(ts), 2)                      # each shape its own unit
        for t in ts:
            self.assertEqual(t.fix_holes, [])
            self.assertEqual(len(t.screw_holes), 2)
            self.assertEqual((t.width, t.height), (t.shapes[0].shape.length, t.shapes[0].shape.width))
            self.assertEqual((t.shapes[0].x, t.shapes[0].y), (0, 0))


class ScrewHeadClearance(unittest.TestCase):
    """C2: the cutter edge runs a full diameter outside the shape; the head must stay clear
    of it, and must sit inside the template with 3 mm to spare."""

    def settings(self, tool=66, dia=8, margin=45, inset=15):
        s = Settings()
        s.router.tool, s.router.diameter = tool, dia
        s.template.margin_end = s.template.margin_side = margin
        s.template.fix_inset = inset
        return s

    def rejected(self, s, *needles):
        plan = build_plan(entries(rect('sharp', 1000, 200)), s)
        self.assertEqual(plan.panels, [])
        self.assertEqual(len(plan.problems), 1, plan.problems)
        for n in ('sharp',) + needles:
            self.assertIn(n, plan.problems[0])
        return plan.problems[0]

    def test_reviewer_case_t66_d8_margin_20_inset_10(self):
        # head 0.86 mm inside the cutter path: hole (10,10), shape corner (20,20), 14.1 < 8+7+3
        self.rejected(self.settings(margin=20, inset=10), 'need 18.0')

    def test_reviewer_case_t65_d18_margin_25_inset_10(self):
        # 21.2 mm from the shape, needs 18+7+3 = 28
        self.rejected(self.settings(tool=65, dia=18, margin=25, inset=10), 'need 28.0')

    def test_inset_too_small_for_the_head(self):
        msg = self.rejected(self.settings(inset=3), 'inset 3', '10')
        self.assertIn('template', msg)

    def test_inset_exactly_head_radius_plus_3_is_fine(self):
        plan = build_plan(entries(rect('sharp', 1000, 200)), self.settings(inset=10))
        self.assertEqual(plan.problems, [])

    def test_fixed_mode_checks_the_inset_too(self):
        s = self.settings(inset=3)
        s.template.mode = 'fixed'
        s.template.fixed_width, s.template.fixed_height = 1200, 400
        self.rejected(s, 'inset 3')

    def test_defaults_and_real_plates_keep_clearance(self):
        s = Settings()
        plan = build_plan(real_entries(), s)
        self.assertEqual(plan.problems, [])
        need = s.router.diameter + s.template.head_dia / 2 + 3.0     # 18
        for t in all_templates(plan):
            for h in t.fix_holes:
                self.assertGreaterEqual(min(h.x, h.y, t.width - h.x, t.height - h.y),
                                        s.template.head_dia / 2 + 3.0)
                for p in t.shapes:
                    dx = max(p.x - h.x, 0, h.x - (p.x + p.shape.length))
                    dy = max(p.y - h.y, 0, h.y - (p.y + p.shape.width))
                    self.assertGreaterEqual((dx * dx + dy * dy) ** 0.5, need)


class Nesting(unittest.TestCase):
    def test_real_plates_fit_without_overlap(self):
        s = Settings()
        plan = build_plan(real_entries(), s)
        self.assertEqual(plan.problems, [])
        self.assertEqual(sum(len(t.shapes) for t in all_templates(plan)), 12)
        e, pl, pw = s.panel.edge, s.panel.length, s.panel.width
        for pan in plan.panels:
            boxes = []
            for t in pan.templates:
                w, h = footprint(t)
                self.assertGreaterEqual(t.x, e - 1e-6)
                self.assertGreaterEqual(t.y, e - 1e-6)
                self.assertLessEqual(t.x + w, pl - e + 1e-6)
                self.assertLessEqual(t.y + h, pw - e + 1e-6)
                boxes.append((t.x, t.y, w, h))
            for i, a in enumerate(boxes):
                for b in boxes[i + 1:]:
                    sep = max(b[0] - (a[0] + a[2]), a[0] - (b[0] + b[2]),
                              b[1] - (a[1] + a[3]), a[1] - (b[1] + b[3]))
                    self.assertGreaterEqual(sep, s.gap - 1e-6)

    def test_every_template_placed_once(self):
        plan = build_plan(real_entries(), Settings())
        ids = [t.id for t in all_templates(plan)]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 6)

    def test_rotation_transform_maps_corners_inside_footprint(self):
        t = PlacedTemplate('T', 300.0, 100.0, [], [], [], 50.0, 20.0, True)
        pts = [to_panel(t, x, y) for x, y in ((0, 0), (300, 0), (300, 100), (0, 100))]
        self.assertEqual(sorted(pts), [(50.0, 20.0), (50.0, 320.0), (150.0, 20.0), (150.0, 320.0)])
        self.assertEqual(to_panel(t, 1, 0), (150.0, 21.0))       # template +x -> panel +y
        self.assertEqual(footprint(t), (100.0, 300.0))

    def test_oversize_shape_reported_not_raised(self):
        plan = build_plan(entries(rect('huge', 2500, 230), rect('ok', 1000, 230)), Settings())
        self.assertIn('huge', plan.problems[0])
        placed = [p.name for t in all_templates(plan) for p in t.shapes]
        self.assertEqual(placed, ['ok'])

    def test_oversize_does_not_spoil_its_partner(self):
        plan = build_plan(entries(rect('huge', 2500, 230), rect('ok', 2300, 230)), Settings())
        self.assertEqual(len(plan.problems), 1)
        self.assertIn('huge', plan.problems[0])
        self.assertEqual([p.name for t in all_templates(plan) for p in t.shapes], ['ok'])

    def test_template_too_big_for_panel_is_a_problem(self):
        # fits alone in none mode... but with margins the template exceeds the panel
        plan = build_plan(entries(rect('wide', 2400, 230)), Settings())
        self.assertEqual(plan.panels, [])
        self.assertIn('wide', plan.problems[0])


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
        self.assertEqual(sum(len(t.shapes) for p in plan.panels for t in p.templates), MAX_QTY)


class SwappedPanel(unittest.TestCase):
    """Panel 1220 long x 2440 wide: the long templates must turn 90 degrees.
    Checked with geometry written here, not with the layout helpers."""

    def setUp(self):
        self.s = Settings()
        self.s.panel.length, self.s.panel.width = 1220, 2440
        self.plan = build_plan(real_entries(), self.s)

    @staticmethod
    def rect(t):
        w, h = (t.height, t.width) if t.rotated else (t.width, t.height)
        return t.x, t.y, t.x + w, t.y + h

    @staticmethod
    def on_panel(t, x, y):
        # template frame -> panel: a quarter turn counter-clockwise, then the offset
        return (t.x + t.height - y, t.y + x) if t.rotated else (t.x + x, t.y + y)

    def test_all_placed_and_some_turned(self):
        self.assertEqual(self.plan.problems, [])
        ts = all_templates(self.plan)
        self.assertEqual(sum(len(t.shapes) for t in ts), 12)
        self.assertTrue(any(t.rotated for t in ts))

    def test_everything_inside_the_panel_and_its_template(self):
        L, W, e = self.s.panel.length, self.s.panel.width, self.s.panel.edge
        for t in all_templates(self.plan):
            x0, y0, x1, y1 = self.rect(t)
            self.assertTrue(e - 1e-6 <= x0 and x1 <= L - e + 1e-6 and e - 1e-6 <= y0
                            and y1 <= W - e + 1e-6, (t.id, x0, y0, x1, y1))
            pts = [self.on_panel(t, h.x, h.y) for h in t.fix_holes + t.screw_holes]
            for p in t.shapes:
                for seg in p.shape.outline:
                    pts += [self.on_panel(t, p.x + seg.a[0], p.y + seg.a[1]),
                            self.on_panel(t, p.x + seg.b[0], p.y + seg.b[1])]
            for x, y in pts:
                self.assertTrue(x0 - 1e-6 <= x <= x1 + 1e-6 and y0 - 1e-6 <= y <= y1 + 1e-6,
                                (t.id, x, y))

    def test_programs_stay_on_the_panel(self):
        from nesting.program import ContourOp, plan_programs
        L, W = self.s.panel.length, self.s.panel.width
        r = self.s.router.diameter / 2
        for prog in plan_programs(self.plan, self.s):
            self.assertFalse([w for w in prog.warnings if 'cutter' in w], prog.warnings)
            for op in prog.ops:
                pts = ([a for s in op.segs for a in (s.a, s.b)] if isinstance(op, ContourOp)
                       else [(op.x, op.y)])
                for x, y in pts:
                    self.assertTrue(r <= x <= L - r and r <= y <= W - r, (prog.name, x, y))

    def test_no_overlap_and_gap_between_templates(self):
        for pan in self.plan.panels:
            rs = [self.rect(t) for t in pan.templates]
            for i in range(len(rs)):
                for j in range(i + 1, len(rs)):
                    a, b = rs[i], rs[j]
                    sep = max(b[0] - a[2], a[0] - b[2], b[1] - a[3], a[1] - b[3])
                    self.assertGreaterEqual(sep, self.s.gap - 1e-6, (pan.id, i, j))

    def test_fixing_holes_clear_of_shapes_and_template_edge(self):
        need = self.s.router.diameter + self.s.template.head_dia / 2 + 3.0
        edge = self.s.template.head_dia / 2 + 3.0
        for t in all_templates(self.plan):
            x0, y0, x1, y1 = self.rect(t)
            for h in t.fix_holes:
                hx, hy = self.on_panel(t, h.x, h.y)
                self.assertGreaterEqual(min(hx - x0, x1 - hx, hy - y0, y1 - hy), edge - 1e-6)
                for p in t.shapes:
                    cs = [self.on_panel(t, p.x + cx, p.y + cy)
                          for cx in (0, p.shape.length) for cy in (0, p.shape.width)]
                    sx0, sx1 = min(c[0] for c in cs), max(c[0] for c in cs)
                    sy0, sy1 = min(c[1] for c in cs), max(c[1] for c in cs)
                    dx, dy = max(sx0 - hx, 0, hx - sx1), max(sy0 - hy, 0, hy - sy1)
                    self.assertGreaterEqual((dx * dx + dy * dy) ** 0.5, need - 1e-6, (t.id, h))


if __name__ == '__main__':
    unittest.main()
