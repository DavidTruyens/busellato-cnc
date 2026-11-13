import math
import unittest

from nesting.dxf import Pocket, Shape, _round_pocket
from nesting.geometry import Arc, Line, _signed_area, _sweep, bbox, distance_to_chain, sample
from nesting.pockets import (PALETTE, PocketError, effective, find_groups, group_for, group_key,
                             pocket_rings)
from nesting.settings import Pockets


def rect_pocket(x0, y0, x1, y1):
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return Pocket([Line(pts[i], pts[(i + 1) % 4]) for i in range(4)])


def poly_pocket(pts):
    return Pocket([Line(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))])


def shape(*pockets, name="s"):
    return Shape(name, [], [], list(pockets))


class PocketGroupTests(unittest.TestCase):
    def test_identical_slots_share_a_group(self):
        gs = find_groups([shape(rect_pocket(10, 10, 110, 20)), shape(rect_pocket(10, 10, 110, 20))])
        self.assertEqual(len(gs), 1)
        self.assertEqual(gs[0].count, 2)
        self.assertEqual(gs[0].kind, "slot")
        self.assertAlmostEqual(gs[0].width, 100)
        self.assertAlmostEqual(gs[0].height, 10)

    def test_tolerance(self):
        a = rect_pocket(10, 10, 99.98, 20)
        near = rect_pocket(10, 10, 100.02, 20)
        far = rect_pocket(10, 10, 100.2, 20)
        self.assertEqual(group_key(a), group_key(near))
        self.assertNotEqual(group_key(a), group_key(far))
        self.assertEqual(len(find_groups([shape(a, near)])), 1)
        self.assertEqual(len(find_groups([shape(a, far)])), 2)

    def test_mirrored_is_different_group(self):
        pts = [(10, 10), (60, 10), (60, 30), (30, 30), (30, 50), (10, 50)]
        x0, x1 = 10, 60  # mirror in place about the pocket's own bbox: only orientation differs
        mir = [(x0 + x1 - x, y) for x, y in pts][::-1]
        self.assertEqual(len(find_groups([shape(poly_pocket(pts)), shape(poly_pocket(mir))])), 2)

    def test_straddling_grid_line_still_shares(self):
        a, b = rect_pocket(10, 10, 100.01, 20), rect_pocket(10, 10, 100.05, 20)
        self.assertEqual(len(find_groups([shape(a, b)])), 1)

    def test_just_over_tolerance_splits(self):
        a, b = rect_pocket(10, 10, 100.0, 20), rect_pocket(10, 10, 100.06, 20)
        self.assertEqual(len(find_groups([shape(a, b)])), 2)

    def test_no_chaining(self):
        ps = [rect_pocket(10, 10, 100.0 + 0.04 * i, 20) for i in range(3)]  # 0, .04, .08
        gs = find_groups([shape(*ps)])
        self.assertEqual([g.count for g in gs], [2, 1])

    def test_same_slot_on_plates_of_different_length_shares(self):
        gs = find_groups([Shape("a", [], [], [rect_pocket(10, 10, 110, 20)]),
                          Shape("b", [], [], [rect_pocket(10, 10, 110, 20)])])
        self.assertEqual(len(gs), 1)

    def test_different_y_splits(self):
        self.assertEqual(len(find_groups([shape(rect_pocket(10, 10, 110, 20),
                                                rect_pocket(10, 30, 110, 40))])), 2)

    def test_order_independent_and_group_for(self):
        a = Shape("a", [], [], [rect_pocket(10, 10, 100.0, 20)])
        b = Shape("b", [], [], [rect_pocket(10, 10, 100.04, 20)])
        g1, g2 = find_groups([a, b]), find_groups([b, a])
        self.assertEqual([g.key for g in g1], [g.key for g in g2])
        self.assertEqual(g1[0].key, group_key(a.pockets[0]))
        self.assertIs(group_for(b.pockets[0], g1), g1[0])
        self.assertIsNone(group_for(rect_pocket(0, 0, 50, 50), g1))

    def test_ids_colours_first_seen_order_and_cycle(self):
        pockets = [rect_pocket(0, 0, 10 + i, 10) for i in range(len(PALETTE) + 2)]
        gs = find_groups([shape(*pockets)])
        self.assertEqual([g.id for g in gs[:3]], ["G1", "G2", "G3"])
        self.assertEqual(gs[0].color, PALETTE[0])
        self.assertEqual(gs[len(PALETTE)].color, PALETTE[0])
        self.assertGreaterEqual(len(set(PALETTE)), 8)
        self.assertEqual(find_groups([shape(*pockets)]), gs)
        self.assertEqual(len(set(PALETTE)), len(PALETTE))
        self.assertTrue(all(c.startswith("#") and len(c) == 7 for c in PALETTE))

    def test_kinds(self):
        from nesting.dxf import _round_pocket
        gs = find_groups([shape(_round_pocket(20, 20, 10), rect_pocket(0, 0, 30, 20))])
        self.assertEqual([g.kind for g in gs], ["round", "shape"])


class EffectiveTests(unittest.TestCase):
    def test_merge_and_unknown_ignored(self):
        d = Pockets()
        s = effective("k", {"k": {"depth": 5, "enabled": False, "bogus": 1}, "other": {"depth": 1}}, d)
        self.assertEqual(s.depth, 5)
        self.assertFalse(s.enabled)
        self.assertEqual(s.diameter, d.diameter)
        self.assertEqual(s.direction, d.direction)
        self.assertTrue(effective("none", {}, d).enabled)

    def test_invalid_value(self):
        with self.assertRaisesRegex(ValueError, "depth"):
            effective("k", {"k": {"depth": "abc"}}, Pockets())

    def test_rejections_name_the_field(self):
        inf, nan = float("inf"), float("nan")
        cases = [("depth", nan), ("depth", inf), ("depth", -inf), ("depth", -1), ("depth", 0),
                 ("diameter", 0), ("plunge_feed", -2), ("cut_feed", 0), ("spindle_rpm", -1),
                 ("depth_per_pass", 0), ("stepover_pct", 0), ("stepover_pct", 100.5),
                 ("stepover_pct", nan), ("direction", "up"), ("direction", 1),
                 ("depth", "5"), ("depth", True), ("depth", None), ("tool", 2.5), ("tool", 0),
                 ("tool", inf), ("tool", 10 ** 400), ("tool", "2"), ("tool", True),
                 ("enabled", 1), ("enabled", "yes")]
        for name, v in cases:
            with self.subTest(name=name, v=v):
                with self.assertRaisesRegex(ValueError, name):
                    effective("k", {"k": {name: v}}, Pockets())

    def test_accepted_values(self):
        s = effective("k", {"k": {"tool": 2.0, "stepover_pct": 100, "direction": "ccw",
                                  "depth": 3, "enabled": False}}, Pockets())
        self.assertEqual(s.tool, 2)
        self.assertIsInstance(s.tool, int)
        self.assertEqual(s.stepover_pct, 100)
        self.assertEqual(s.direction, "ccw")
        self.assertEqual(s.depth, 3)

    def test_missing_and_odd_overrides(self):
        d = Pockets()
        self.assertEqual(effective("k", {"k": None}, d).depth, d.depth)
        self.assertEqual(effective("k", {"k": {}}, d).tool, d.tool)
        with self.assertRaises(ValueError):
            effective("k", {"k": [1]}, d)


def slot_outline(x0, y0, length, width=20.0):
    """Closed CCW slot: two parallel lines and two 180-degree end arcs, overall length x width."""
    r = width / 2
    xa, xb, yc = x0 + r, x0 + length - r, y0 + r
    return [Line((xa, y0), (xb, y0)),
            Arc((xb, y0), (xb, y0 + width), (xb, yc), r, True),
            Line((xb, y0 + width), (xa, y0 + width)),
            Arc((xa, y0 + width), (xa, y0), (xa, yc), r, True)]


def rect_outline(x0, y0, x1, y1):
    return rect_pocket(x0, y0, x1, y1).outline


def _inside(p, poly):
    x, y = p
    inside = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def uncovered_points(outline, rings, radius, step=0.5, skip=None):
    """Grid points inside the pocket farther than radius from every ring."""
    poly = sample(outline, 0.2)
    x0, y0, x1, y1 = bbox(outline)
    out = []
    nx, ny = int((x1 - x0) / step), int((y1 - y0) / step)
    for i in range(1, nx):
        for j in range(1, ny):
            p = (x0 + i * step, y0 + j * step)
            if not _inside(p, poly) or (skip and skip(p)):
                continue
            if all(distance_to_chain(p, ring) > radius + 0.01 for ring in rings):
                out.append(p)
    return out


class PocketRingTests(unittest.TestCase):
    def test_slot_20_wide_tool_12_gives_one_ring_at_offset_6(self):
        outline = slot_outline(30, 15, 940)
        rings = pocket_rings(outline, 12, 40)
        self.assertEqual(len(rings), 1)
        for p in sample(rings[0], 0.5):
            self.assertAlmostEqual(distance_to_chain(p, outline), 6, places=2)
        x0, y0, x1, y1 = bbox(rings[0])
        self.assertAlmostEqual(y0, 21, places=2)
        self.assertAlmostEqual(y1, 29, places=2)
        self.assertAlmostEqual(x0, 36, places=2)
        self.assertAlmostEqual(x1, 964, places=2)
        self.assertEqual(sum(isinstance(s, Arc) for s in rings[0]), 2)

    def test_every_point_in_pocket_is_covered_by_cutter(self):
        slot = slot_outline(0, 0, 200)
        self.assertEqual(uncovered_points(slot, pocket_rings(slot, 12, 40), 6), [])
        rect = rect_outline(0, 0, 60, 40)
        r = 4

        def corner(p):  # a round cutter cannot reach into a sharp corner
            return min(p[0], 60 - p[0]) < r and min(p[1], 40 - p[1]) < r
        for pct in (40, 50, 75, 100):
            with self.subTest(pct=pct):
                rings = pocket_rings(rect, 2 * r, pct)
                self.assertEqual(uncovered_points(rect, rings, r, skip=corner), [])
        # wider than the cutter's reach at full stepover: the core must still be cleared
        for w in (44, 50, 37):
            with self.subTest(width=w):
                s = slot_outline(0, 0, 150, w)
                self.assertEqual(uncovered_points(s, pocket_rings(s, 10, 100), 5), [])
        circle = _round_pocket(30, 30, 25).outline
        for pct in (40, 100):
            with self.subTest(circle_pct=pct):
                self.assertEqual(uncovered_points(circle, pocket_rings(circle, 8, pct), 4), [])

    def test_cutter_never_leaves_pocket(self):
        cases = [(slot_outline(0, 0, 200), 12, 40), (rect_outline(0, 0, 60, 40), 8, 40),
                 (slot_outline(0, 0, 150, 44), 10, 100), (_round_pocket(30, 30, 25).outline, 8, 60),
                 (poly_pocket([(0, 0), (60, 0), (60, 30), (30, 30), (30, 50), (0, 50)]).outline, 6, 50)]
        for outline, d, pct in cases:
            with self.subTest(d=d, pct=pct):
                for ring in pocket_rings(outline, d, pct):
                    for p in sample(ring, 0.25):
                        self.assertGreaterEqual(distance_to_chain(p, outline), d / 2 - 0.01)

    def test_ring_order_inner_to_outer_wall_last(self):
        outline = rect_outline(0, 0, 60, 40)
        rings = pocket_rings(outline, 8, 40)
        levels = [min(distance_to_chain(p, outline) for p in sample(r, 0.5)) for r in rings]
        self.assertEqual(levels, sorted(levels, reverse=True))
        self.assertAlmostEqual(levels[-1], 4, places=2)
        for p in sample(rings[-1], 0.5):
            self.assertAlmostEqual(distance_to_chain(p, outline), 4, places=2)
        # every ring winds the same way as the outline, and stays closed
        for ring in rings:
            self.assertGreater(_signed_area(ring), 0)
            self.assertLess(math.dist(ring[0].a, ring[-1].b), 1e-6)
            for s, t in zip(ring, ring[1:]):
                self.assertLess(math.dist(s.b, t.a), 1e-6)
        cw = [Line(s.b, s.a) for s in reversed(outline)]
        for ring in pocket_rings(cw, 8, 40):
            self.assertLess(_signed_area(ring), 0)

    def test_wider_pocket_gets_several_rings_with_stepover(self):
        outline = rect_outline(0, 0, 60, 40)
        rings = pocket_rings(outline, 8, 40)
        levels = sorted(min(distance_to_chain(p, outline) for p in sample(r, 0.5)) for r in rings)
        self.assertEqual(len(rings), 5)
        for got, want in zip(levels, [4, 7.2, 10.4, 13.6, 16.8]):
            self.assertAlmostEqual(got, want, places=2)

    def test_pocket_equal_to_tool_width(self):
        for width in (12, 12.008, 11.992):
            with self.subTest(width=width):
                outline = slot_outline(0, 0, 100, width)
                rings = pocket_rings(outline, 12, 40)
                self.assertEqual(len(rings), 1)
                (a, b) = rings[0]
                self.assertIsInstance(a, Line)
                self.assertIsInstance(b, Line)
                self.assertEqual((a.a, a.b), (b.b, b.a))
                ends = sorted([a.a, a.b])
                self.assertAlmostEqual(ends[0][0], width / 2, places=2)
                self.assertAlmostEqual(ends[1][0], 100 - width / 2, places=2)
                for p in ends:
                    self.assertAlmostEqual(p[1], width / 2, places=2)
        rings = pocket_rings(_round_pocket(20, 20, 6).outline, 12, 40)
        self.assertEqual(len(rings), 1)
        for s in rings[0]:
            self.assertIsInstance(s, Line)
            for p in (s.a, s.b):
                self.assertAlmostEqual(p[0], 20, places=3)
                self.assertAlmostEqual(p[1], 20, places=3)

    def test_pocket_narrower_than_tool_is_an_error(self):
        for outline in (slot_outline(0, 0, 100, 10), rect_outline(0, 0, 50, 11.9),
                        _round_pocket(20, 20, 5).outline):
            with self.assertRaisesRegex(PocketError, "narrower than the tool"):
                pocket_rings(outline, 12, 40)
        self.assertTrue(issubclass(PocketError, ValueError))

    def test_round_pocket_rings_are_concentric_arcs(self):
        outline = _round_pocket(30, 30, 25).outline
        rings = pocket_rings(outline, 8, 40)
        radii = []
        for ring in rings:
            self.assertEqual(len(ring), 2)
            for s in ring:
                self.assertIsInstance(s, Arc)
                self.assertTrue(s.ccw)
                self.assertAlmostEqual(s.center[0], 30, places=6)
                self.assertAlmostEqual(s.center[1], 30, places=6)
                self.assertAlmostEqual(_sweep(s), math.pi, places=4)
            self.assertAlmostEqual(ring[0].radius, ring[1].radius, places=6)
            radii.append(ring[0].radius)
        self.assertEqual(radii, sorted(radii))
        self.assertAlmostEqual(radii[-1], 21, places=3)
        self.assertGreater(radii[0], 0.01)
        self.assertLessEqual(radii[0], 4 + 1e-6)  # the centre is reached by the innermost ring
        for a, b in zip(radii, radii[1:]):
            self.assertLessEqual(b - a, 3.2 + 1e-6)


if __name__ == "__main__":
    unittest.main()
