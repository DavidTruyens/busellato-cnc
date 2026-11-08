import json
import sys
import unittest
from pathlib import Path

repo = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo / 'tools'))
import nest_plates as n  # noqa: E402

PLATES = json.load(open(repo / 'plates' / 'plates.json'))


def plate(name, length, width):
    return {'name': name, 'dxf': name + '.dxf', 'thickness': 18.0, 'world_bbox_xy': [length, width],
            'holes': [{'x': 150, 'y': 40, 'diameter': 6.6}, {'x': length - 150, 'y': 40, 'diameter': 6.6}]}


class Pairing(unittest.TestCase):
    def test_neighbours_by_length(self):
        items = n.expand([plate('a', 2000, 230), plate('b', 1000, 230), plate('c', 1990, 230),
                          plate('d', 1010, 230)], {})
        pairs = n.pair_plates(items)
        self.assertEqual([sorted(p['name'] for p in c) for c in pairs], [['a', 'c'], ['b', 'd']])

    def test_odd_count_leaves_a_single(self):
        pairs = n.pair_plates(n.expand([plate(x, 1500, 230) for x in 'abc'], {}))
        self.assertEqual([len(c) for c in pairs], [2, 1])

    def test_quantity(self):
        items = n.expand([plate('a', 1500, 230), plate('b', 1500, 230)], {'a': 3, 'b': 0})
        self.assertEqual([p['name'] for p in items], ['a', 'a', 'a'])


class Template(unittest.TestCase):
    def setUp(self):
        self.cfg = n.Config()

    def test_size_and_holes(self):
        t = n.build_template('T01', n.expand([plate('a', 2000, 230), plate('b', 1900, 220)], {}), self.cfg)
        c = self.cfg
        self.assertAlmostEqual(t['width'], 2000 + 2 * c.margin_end)
        self.assertAlmostEqual(t['height'], 450 + c.gap + 2 * c.margin_side)
        self.assertEqual(len(t['fix_holes']), 4)
        self.assertEqual(len(t['pilot_holes']), 4)            # 2 per plate
        a = [p for p in t['plates'] if p['name'] == 'a'][0]   # widest at the bottom
        self.assertAlmostEqual(a['y'], c.margin_side)
        first = [h for h in t['pilot_holes'] if h['plate'] == 'a'][0]
        self.assertAlmostEqual(first['x'], c.margin_end + 150)

    def test_fixing_holes_clear_of_plates(self):
        t = n.build_template('T01', n.expand([plate('a', 2000, 230), plate('b', 1900, 220)], {}), self.cfg)
        n.check_template(t, self.cfg)
        for h in t['fix_holes']:
            for p in t['plates']:
                inside = p['x'] <= h['x'] <= p['x'] + p['length'] and p['y'] <= h['y'] <= p['y'] + p['width']
                self.assertFalse(inside)

    def test_too_small_margin_is_rejected(self):
        cfg = n.Config(margin_end=20, margin_side=20)
        with self.assertRaises(ValueError):
            n.build_template('T01', n.expand([plate('a', 2000, 230)], {}), cfg)


class Nesting(unittest.TestCase):
    def test_real_plates_fit_without_overlap(self):
        res = n.run(PLATES, {}, n.Config())
        cfg = res['config']
        tm = {t['id']: t for t in res['templates']}
        self.assertEqual(res['stats']['plates'], 12)
        for pan in res['panels']:
            boxes = []
            for pl in pan['placements']:
                w, h = n.footprint(pl, tm[pl['template']])
                self.assertGreaterEqual(pl['x'], cfg['panel_edge'] - 1e-6)
                self.assertGreaterEqual(pl['y'], cfg['panel_edge'] - 1e-6)
                self.assertLessEqual(pl['x'] + w, cfg['panel_l'] - cfg['panel_edge'] + 1e-6)
                self.assertLessEqual(pl['y'] + h, cfg['panel_w'] - cfg['panel_edge'] + 1e-6)
                boxes.append((pl['x'], pl['y'], w, h))
            for i, a in enumerate(boxes):
                for b in boxes[i + 1:]:
                    sep = max(b[0] - (a[0] + a[2]), a[0] - (b[0] + b[2]),
                              b[1] - (a[1] + a[3]), a[1] - (b[1] + b[3]))
                    self.assertGreaterEqual(sep, cfg['tool_dia'] + cfg['clearance'] - 1e-6)

    def test_every_template_placed_once(self):
        res = n.run(PLATES, {}, n.Config())
        placed = sorted(p['template'] for pan in res['panels'] for p in pan['placements'])
        self.assertEqual(placed, sorted(t['id'] for t in res['templates']))

    def test_rotation_transform_maps_corners_inside_footprint(self):
        t = {'width': 300.0, 'height': 100.0}
        pl = {'x': 50.0, 'y': 20.0, 'rotated': True}
        pts = [n.to_panel(pl, t, x, y) for x, y in ((0, 0), (300, 0), (300, 100), (0, 100))]
        self.assertEqual(sorted(pts), [(50.0, 20.0), (50.0, 320.0), (150.0, 20.0), (150.0, 320.0)])
        # counter-clockwise: template +x points to panel +y
        self.assertEqual(n.to_panel(pl, t, 1, 0), (150.0, 21.0))

    def test_oversize_template_is_an_error(self):
        t = n.build_template('T01', n.expand([plate('a', 2400, 230)], {}), n.Config())
        with self.assertRaises(ValueError):
            n.nest([t], n.Config())


if __name__ == '__main__':
    unittest.main()
