import math
import unittest
from pathlib import Path

from nesting.dxf import read_dxf
from nesting.geometry import (
    Arc, Line, OffsetError, bbox, distance_to_chain, offset_outline, sample,
    set_direction, split_large_arcs)

ROOT = Path(__file__).resolve().parent.parent
PLATES = sorted((ROOT / "plates").glob("*.dxf"))


def poly(*pts):
    """Closed chain of lines through the given points."""
    return [Line(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]


def signed_area(segs):
    pts = sample(segs, 0.5)
    return 0.5 * sum(x0 * y1 - x1 * y0
                     for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))


def sweep(arc):
    a0 = math.atan2(arc.a[1] - arc.center[1], arc.a[0] - arc.center[0])
    a1 = math.atan2(arc.b[1] - arc.center[1], arc.b[0] - arc.center[0])
    tau = 2 * math.pi
    return (a1 - a0) % tau if arc.ccw else (a0 - a1) % tau


RECT = poly((0, 0), (200, 0), (200, 100), (0, 100))  # counter-clockwise


def slot_bar(width, rounded=False):
    """100 x 40 bar (ccw) with a slot of `width` cut 20 deep from the top."""
    x0, x1 = 50 - width / 2, 50 + width / 2
    if rounded:
        r = width / 2
        bottom = [Line((x1, 40), (x1, 20 + r)),
                  Arc((x1, 20 + r), (x0, 20 + r), (50, 20 + r), r, False),
                  Line((x0, 20 + r), (x0, 40))]
    else:
        bottom = poly((x1, 40), (x1, 20), (x0, 20), (x0, 40))[:3]
    return ([Line((0, 0), (100, 0)), Line((100, 0), (100, 40)),
             Line((100, 40), (x1, 40))] + bottom + [Line((x0, 40), (0, 40)),
                                                    Line((0, 40), (0, 0))])


class OffsetTests(unittest.TestCase):
    def assert_closed(self, segs):
        self.assertGreater(len(segs), 1)
        for s, nxt in zip(segs, segs[1:] + segs[:1]):
            self.assertLess(math.dist(s.b, nxt.a), 1e-9, (s, nxt))

    def assert_r_away(self, offset, original, r, label=""):
        for p in sample(offset, 0.5):
            d = distance_to_chain(p, original)
            self.assertAlmostEqual(d, r, delta=0.01, msg=f"{label} at {p}")

    def test_rectangle_offset_by_4(self):
        out = offset_outline(RECT, 4)
        x0, y0, x1, y1 = bbox(out)
        self.assertAlmostEqual(x1 - x0, 208, places=6)
        self.assertAlmostEqual(y1 - y0, 108, places=6)
        self.assertAlmostEqual(x0, -4, places=6)
        self.assertAlmostEqual(y0, -4, places=6)
        arcs = [s for s in out if isinstance(s, Arc)]
        self.assertEqual(len(arcs), 4)
        self.assertEqual(sorted(a.center for a in arcs),
                         [(0, 0), (0, 100), (200, 0), (200, 100)])
        for a in arcs:
            self.assertAlmostEqual(a.radius, 4)
            self.assertAlmostEqual(sweep(a), math.pi / 2)
            self.assertTrue(a.ccw)
        self.assert_r_away(out, RECT, 4)

    def test_real_plate_offset_is_r_away(self):
        self.assertEqual(len(PLATES), 12)
        for path in PLATES:
            outline = read_dxf(path).outline
            for outward in (True, False):
                with self.subTest(plate=path.name, outward=outward):
                    out = offset_outline(outline, 4, outward)
                    self.assert_closed(out)
                    self.assert_r_away(out, outline, 4, path.name)
                    a_in, a_out = signed_area(outline), signed_area(out)
                    if outward:
                        self.assertGreater(abs(a_out), abs(a_in))
                    else:
                        self.assertLess(abs(a_out), abs(a_in))

    def test_inward_offset(self):
        out = offset_outline(RECT, 4, outward=False)
        self.assertTrue(all(isinstance(s, Line) for s in out))
        self.assertEqual(len(out), 4)
        for got, want in zip(bbox(out), (4, 4, 196, 96)):
            self.assertAlmostEqual(got, want, places=6)
        self.assert_r_away(out, RECT, 4)
        # A convex fillet smaller than r disappears into a sharp corner.
        rounded = [Line((0, 0), (98, 0)), Arc((98, 0), (100, 2), (98, 2), 2, True),
                   Line((100, 2), (100, 50)), Line((100, 50), (0, 50)),
                   Line((0, 50), (0, 0))]
        out = offset_outline(rounded, 4, outward=False)
        self.assertEqual(len(out), 4)
        for got, want in zip(bbox(out), (4, 4, 96, 46)):
            self.assertAlmostEqual(got, want, places=6)

    def test_narrow_slot_raises_offset_error(self):
        for rounded in (False, True):
            with self.subTest(rounded=rounded):
                with self.assertRaises(OffsetError):
                    offset_outline(slot_bar(6, rounded), 4)
                with self.assertRaises(OffsetError):
                    offset_outline(list(reversed(
                        [_rev(s) for s in slot_bar(6, rounded)])), 4)

    def test_narrow_channel_into_cavity_raises_offset_error(self):
        # No edge vanishes here: the two 20 mm channel walls each survive,
        # but their offsets cross each other inside the 3 mm channel.
        block = poly((0, 0), (100, 0), (100, 100), (51.5, 100), (51.5, 80),
                     (80, 80), (80, 20), (20, 20), (20, 80), (48.5, 80),
                     (48.5, 100), (0, 100))
        with self.assertRaises(OffsetError):
            offset_outline(block, 4)

    def test_wide_slot_is_offset(self):
        for rounded in (False, True):
            with self.subTest(rounded=rounded):
                bar = slot_bar(10, rounded)
                out = offset_outline(bar, 4)
                self.assert_closed(out)
                self.assert_r_away(out, bar, 4)

    def test_too_thin_for_inward_offset_raises(self):
        with self.assertRaises(OffsetError):
            offset_outline(poly((0, 0), (100, 0), (100, 6), (0, 6)), 4,
                           outward=False)

    def test_direction_ccw_cw(self):
        cw = set_direction(RECT, ccw=False)
        self.assertLess(signed_area(cw), 0)
        self.assert_closed(cw)
        self.assertGreater(signed_area(set_direction(cw, ccw=True)), 0)
        self.assertEqual(set_direction(RECT, ccw=True), RECT)
        # "Outward" follows the enclosed area, not the winding.
        for got, want in zip(bbox(offset_outline(cw, 4)), (-4, -4, 204, 104)):
            self.assertAlmostEqual(got, want, places=6)
        for got, want in zip(bbox(offset_outline(cw, 4, outward=False)),
                             (4, 4, 196, 96)):
            self.assertAlmostEqual(got, want, places=6)
        plate = read_dxf(PLATES[0]).outline
        for ccw in (True, False):
            chain = set_direction(plate, ccw)
            self.assertEqual(signed_area(chain) > 0, ccw)
            out = offset_outline(chain, 4)
            self.assertEqual(signed_area(out) > 0, ccw)
            self.assert_r_away(out, plate, 4)

    def test_split_large_arcs(self):
        r = 10
        a = (r, 0)
        b = (0, -r)  # ccw from 0 deg to 270 deg
        for arc in (Arc(a, b, (0, 0), r, True), Arc(b, a, (0, 0), r, False)):
            with self.subTest(ccw=arc.ccw):
                first, second = split_large_arcs([arc])
                self.assertEqual(first.a, arc.a)
                self.assertEqual(second.b, arc.b)
                self.assertEqual(first.b, second.a)
                for part in (first, second):
                    self.assertEqual(part.ccw, arc.ccw)
                    self.assertEqual(part.center, arc.center)
                    self.assertEqual(part.radius, r)
                    self.assertAlmostEqual(math.dist(part.a, part.center), r)
                    self.assertAlmostEqual(math.dist(part.b, part.center), r)
                    self.assertAlmostEqual(sweep(part), math.radians(135))
                self.assertAlmostEqual(sweep(first) + sweep(second),
                                       math.radians(270))
        small = Arc((r, 0), (0, r), (0, 0), r, True)
        line = Line((0, 0), (1, 1))
        self.assertEqual(split_large_arcs([line, small]), [line, small])

    def test_offset_returns_closed_chain(self):
        for chain in (RECT, set_direction(RECT, False), slot_bar(10, True)):
            for outward in (True, False):
                self.assert_closed(offset_outline(chain, 4, outward))

    def test_distance_to_chain(self):
        arc = [Arc((10, 0), (0, 10), (0, 0), 10, True)]
        self.assertAlmostEqual(distance_to_chain((20, 20), arc),
                               math.hypot(20, 20) - 10)
        self.assertAlmostEqual(distance_to_chain((0, -5), arc),
                               math.dist((0, -5), (10, 0)))
        self.assertAlmostEqual(distance_to_chain((50, 3), RECT), 3)


def _rev(s):
    if isinstance(s, Arc):
        return Arc(s.b, s.a, s.center, s.radius, not s.ccw)
    return Line(s.b, s.a)


if __name__ == "__main__":
    unittest.main()
