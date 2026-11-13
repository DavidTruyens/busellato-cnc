import unittest

from nesting.dxf import Pocket, Shape
from nesting.geometry import Line
from nesting.pockets import PALETTE, effective, find_groups, group_key
from nesting.settings import Pockets


def rect_pocket(x0, y0, x1, y1):
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return Pocket([Line(pts[i], pts[(i + 1) % 4]) for i in range(4)])


def poly_pocket(pts):
    return Pocket([Line(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))])


def shape(*pockets):
    return Shape("s", [], [], list(pockets))


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
        ell = poly_pocket([(10, 10), (60, 10), (60, 30), (30, 30), (30, 50), (10, 50)])
        mir = poly_pocket([(100 - x, y) for x, y in
                           [(10, 10), (60, 10), (60, 30), (30, 30), (30, 50), (10, 50)]][::-1])
        self.assertEqual(len(find_groups([shape(ell), shape(mir)])), 2)

    def test_ids_colours_first_seen_order_and_cycle(self):
        pockets = [rect_pocket(0, 0, 10 + i, 10) for i in range(len(PALETTE) + 2)]
        gs = find_groups([shape(*pockets)])
        self.assertEqual([g.id for g in gs[:3]], ["G1", "G2", "G3"])
        self.assertEqual(gs[0].color, PALETTE[0])
        self.assertEqual(gs[len(PALETTE)].color, PALETTE[0])
        self.assertGreaterEqual(len(set(PALETTE)), 8)
        self.assertEqual(find_groups([shape(*pockets)]), gs)

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


if __name__ == "__main__":
    unittest.main()
