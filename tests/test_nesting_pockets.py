import unittest

from nesting.dxf import Pocket, Shape
from nesting.geometry import Line
from nesting.pockets import PALETTE, effective, find_groups, group_for, group_key
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


if __name__ == "__main__":
    unittest.main()
