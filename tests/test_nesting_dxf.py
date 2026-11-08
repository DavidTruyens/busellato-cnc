import json
import tempfile
import unittest
from pathlib import Path

from nesting.dxf import DxfError, Shape, read_dxf
from nesting.geometry import Arc, Line, bbox

ROOT = Path(__file__).resolve().parent.parent


def dxf(*entities):
    body = "".join(entities)
    return f"0\nSECTION\n2\nENTITIES\n{body}0\nENDSEC\n0\nEOF\n"


def line(x0, y0, x1, y1, layer="CONTOUR"):
    return f"0\nLINE\n8\n{layer}\n10\n{x0}\n20\n{y0}\n11\n{x1}\n21\n{y1}\n"


def circle(x, y, r, layer="HOLES"):
    return f"0\nCIRCLE\n8\n{layer}\n10\n{x}\n20\n{y}\n40\n{r}\n"


def rect(x0, y0, x1, y1, layer="CONTOUR"):
    return (line(x0, y0, x1, y0, layer) + line(x1, y0, x1, y1, layer)
            + line(x1, y1, x0, y1, layer) + line(x0, y1, x0, y0, layer))


class DxfTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, text):
        p = Path(self.tmp.name) / name
        p.write_text(text)
        return p

    def test_reads_all_exported_plates(self):
        info = json.loads((ROOT / "plates" / "plates.json").read_text())
        self.assertTrue(info)
        for entry in info:
            with self.subTest(plate=entry["name"]):
                shape = read_dxf(ROOT / "plates" / entry["dxf"])
                chain = shape.outline
                for s, t in zip(chain, chain[1:] + chain[:1]):
                    self.assertAlmostEqual(s.b[0], t.a[0], delta=0.01)
                    self.assertAlmostEqual(s.b[1], t.a[1], delta=0.01)
                self.assertEqual(len(shape.holes), 2)
                for h in shape.holes:
                    self.assertAlmostEqual(h.diameter, 6.6, delta=0.001)
                L, W = entry["world_bbox_xy"]
                self.assertAlmostEqual(shape.length, L, delta=0.05)
                self.assertAlmostEqual(shape.width, W, delta=0.05)
                x0, y0, _, _ = bbox(shape.outline)
                self.assertAlmostEqual(x0, 0, delta=1e-9)
                self.assertAlmostEqual(y0, 0, delta=1e-9)

    def _bulge_plate(self, bulge):
        poly = ("0\nLWPOLYLINE\n8\nCONTOUR\n90\n4\n70\n1\n"
                "10\n0\n20\n0\n10\n100\n20\n0\n10\n100\n20\n50\n"
                f"42\n{bulge}\n10\n0\n20\n50\n")
        return read_dxf(self.write("bulge.dxf", dxf(poly)))

    def test_lwpolyline_with_bulge(self):
        # positive bulge = counter-clockwise: top edge (100,50)->(0,50) bulges up by 25
        shape = self._bulge_plate(0.5)
        kinds = [type(s) for s in shape.outline]
        self.assertEqual(kinds.count(Line), 3)
        self.assertEqual(kinds.count(Arc), 1)
        arc = next(s for s in shape.outline if isinstance(s, Arc))
        self.assertTrue(arc.ccw)
        self.assertAlmostEqual(arc.radius, (50 ** 2 + 25 ** 2) / (2 * 25))
        self.assertAlmostEqual(arc.center[0], 50)
        self.assertAlmostEqual(arc.center[1], 50 - (arc.radius - 25))
        self.assertAlmostEqual(shape.length, 100, delta=1e-9)
        self.assertAlmostEqual(shape.width, 75, delta=1e-9)

    def test_lwpolyline_negative_bulge_is_cw(self):
        # negative bulge bulges down into the rectangle: bbox unchanged
        shape = self._bulge_plate(-0.5)
        arc = next(s for s in shape.outline if isinstance(s, Arc))
        self.assertFalse(arc.ccw)
        self.assertAlmostEqual(arc.center[1], 50 + (arc.radius - 25))
        self.assertAlmostEqual(shape.width, 50, delta=1e-9)

    def test_open_outline_names_file(self):
        p = self.write("openplate.dxf", dxf(line(0, 0, 10, 0), line(10, 0, 10, 10),
                                           line(10, 10, 0, 10)))
        with self.assertRaises(DxfError) as cm:
            read_dxf(p)
        self.assertIn("openplate.dxf", str(cm.exception))
        self.assertIn("open", str(cm.exception))

    def test_no_outline(self):
        p = self.write("empty.dxf", dxf(circle(5, 5, 3)))
        with self.assertRaises(DxfError) as cm:
            read_dxf(p)
        self.assertIn("empty.dxf", str(cm.exception))
        self.assertIn("no outline", str(cm.exception))

    def test_two_outlines(self):
        p = self.write("two.dxf", dxf(rect(0, 0, 10, 10), rect(20, 0, 30, 10)))
        with self.assertRaises(DxfError) as cm:
            read_dxf(p)
        self.assertIn("two.dxf", str(cm.exception))
        self.assertIn("more than one", str(cm.exception))

    def test_missing_file(self):
        with self.assertRaises(DxfError) as cm:
            read_dxf(Path(self.tmp.name) / "nope.dxf")
        self.assertIn("nope.dxf", str(cm.exception))
        self.assertIn("open", str(cm.exception))

    def test_circles_without_layers_become_holes(self):
        text = dxf(rect(5, 5, 105, 55, "0"), circle(20, 20, 3, "0"),
                   circle(90, 40, 4, "0"), circle(500, 500, 3, "0"))
        shape = read_dxf(self.write("nolayers.dxf", text))
        self.assertIsInstance(shape, Shape)
        self.assertEqual(len(shape.holes), 2)
        h = sorted(shape.holes, key=lambda h: h.x)
        self.assertAlmostEqual(h[0].x, 15)
        self.assertAlmostEqual(h[0].y, 15)
        self.assertAlmostEqual(h[0].diameter, 6)
        self.assertAlmostEqual(h[1].diameter, 8)

    def test_arc_entity_is_ccw(self):
        # half-disc: arc from 0 to 180 degrees plus closing line
        arc = "0\nARC\n8\nCONTOUR\n10\n50\n20\n0\n40\n50\n50\n0\n51\n180\n"
        shape = read_dxf(self.write("half.dxf", dxf(arc, line(0, 0, 100, 0))))
        self.assertAlmostEqual(shape.length, 100, delta=1e-9)
        self.assertAlmostEqual(shape.width, 50, delta=1e-9)


if __name__ == "__main__":
    unittest.main()
