import json
import os
import sys
import unittest

from helpers import REPO

sys.path.insert(0, os.path.join(REPO, 'fusion', 'busellato_table'))
import table_geometry as tg  # noqa: E402

MACHINE = {
    'beams': 2, 'pods_per_beam': 2,
    'beam_width': 100, 'beam_height': 90, 'beam_length': 1300, 'beam_y_start': 0,
    'beam_x_min': 0, 'beam_x_max': 2500,
    'pod_x_size': 120, 'pod_y_size': 120, 'pod_height': 100,
    'pod_y_min': 0, 'pod_y_max': 1180,
    'scale_to_g54_x': 50, 'scale_to_g54_y': 20,
    'reference': 'test', 'provisional': [],
}


def params(**over):
    p = {'BEAM1_X': 300, 'BEAM2_X': 900,
         'BEAM1_POD1_Y': 100, 'BEAM1_POD1_ON': 1, 'BEAM1_POD2_Y': 600, 'BEAM1_POD2_ON': 0,
         'BEAM2_POD1_Y': 100, 'BEAM2_POD1_ON': 1, 'BEAM2_POD2_Y': 600, 'BEAM2_POD2_ON': 1}
    p.update(over)
    return p


def by_name(result):
    return {b.name: b for b in result.boxes}


class MachineFileTest(unittest.TestCase):
    def test_repo_machine_file_is_complete(self):
        m = tg.load_machine(os.path.join(REPO, 'fusion', 'busellato-table.json'))
        self.assertEqual(tg.check_machine(m), [])

    def test_measure_sheet_covers_machine_keys(self):
        with open(os.path.join(REPO, 'fusion', 'MEASURE.md')) as fh:
            sheet = fh.read()
        for key in tg.REQUIRED_KEYS:
            self.assertIn(f'`{key}`', sheet, key)

    def test_machine_file_missing_key(self):
        m = dict(MACHINE)
        del m['pod_height']
        self.assertTrue(any('pod_height' in p for p in tg.check_machine(m)))

    def test_machine_file_non_numeric(self):
        m = dict(MACHINE, beam_width='wide')
        self.assertTrue(any('beam_width' in p for p in tg.check_machine(m)))


class ParameterSpecTest(unittest.TestCase):
    def test_names_units_and_count(self):
        specs = tg.parameter_specs(MACHINE)
        names = [s[0] for s in specs]
        self.assertEqual(len(names), 2 + 2 * 2 * 2)
        lookup = {n: (u, v) for n, u, v in specs}
        self.assertEqual(lookup['BEAM2_POD2_ON'], ('', 1.0))     # first and last pod start switched on
        self.assertEqual(lookup['BEAM1_POD1_ON'], ('', 1.0))
        self.assertEqual({u for n, u, v in specs if n.endswith('_X') or n.endswith('_Y')}, {'mm'})

    def test_starting_values_pass_the_checks(self):
        start = {n: v for n, u, v in tg.parameter_specs(MACHINE)}
        self.assertEqual(tg.build(MACHINE, start, -18).problems, [])


class BuildTest(unittest.TestCase):
    def test_beam_and_pod_positions(self):
        r = tg.build(MACHINE, params(), -18)
        self.assertEqual(r.problems, [])
        boxes = by_name(r)
        beam1 = boxes['BEAM1']
        self.assertEqual((beam1.x0, beam1.x1), (250, 350))          # 300 - 50, width 100
        self.assertEqual((beam1.y0, beam1.y1), (-20, 1280))         # beam_y_start 0 - 20, length 1300
        self.assertEqual((beam1.z0, beam1.z1), (-208, -118))        # under the pods
        pod = boxes['BEAM1_POD1']
        self.assertEqual((pod.x0, pod.x1), (240, 360))              # centred on the beam
        self.assertEqual((pod.y0, pod.y1), (80, 200))               # 100 - 20, size 120
        self.assertEqual((pod.z0, pod.z1), (-118, -18))             # top on the panel underside

    def test_inactive_pods_not_built(self):
        names = set(by_name(tg.build(MACHINE, params(), -18)))
        self.assertNotIn('BEAM1_POD2', names)
        self.assertEqual(names, {'BEAM1', 'BEAM2', 'BEAM1_POD1', 'BEAM2_POD1', 'BEAM2_POD2'})

    def test_beam_outside_travel(self):
        r = tg.build(MACHINE, params(BEAM2_X=2600), -18)
        self.assertTrue(any('BEAM2_X' in p for p in r.problems))
        self.assertEqual(r.boxes, [])

    def test_beams_overlap(self):
        r = tg.build(MACHINE, params(BEAM2_X=350), -18)
        self.assertTrue(any('BEAM1' in p and 'BEAM2' in p for p in r.problems))

    def test_pod_outside_travel(self):
        r = tg.build(MACHINE, params(BEAM1_POD1_Y=1200), -18)
        self.assertTrue(any('BEAM1_POD1_Y' in p for p in r.problems))

    def test_inactive_pod_outside_travel_ignored(self):
        self.assertEqual(tg.build(MACHINE, params(BEAM1_POD2_Y=5000), -18).problems, [])

    def test_active_pods_overlap(self):
        r = tg.build(MACHINE, params(BEAM2_POD2_Y=150), -18)
        self.assertTrue(any('BEAM2_POD1' in p and 'BEAM2_POD2' in p for p in r.problems))

    def test_touching_pods_allowed(self):
        self.assertEqual(tg.build(MACHINE, params(BEAM2_POD2_Y=220), -18).problems, [])

    def test_pod_at_travel_limit_allowed(self):
        self.assertEqual(tg.build(MACHINE, params(BEAM1_POD1_Y=1180, BEAM2_POD2_Y=1180, BEAM2_POD1_Y=0), -18).problems, [])

    def test_missing_and_bad_parameters(self):
        p = params()
        del p['BEAM1_X']
        p['BEAM2_POD1_ON'] = 2
        r = tg.build(MACHINE, p, -18)
        self.assertTrue(any('BEAM1_X' in x for x in r.problems))
        self.assertTrue(any('BEAM2_POD1_ON' in x for x in r.problems))

    def test_all_problems_reported_at_once(self):
        r = tg.build(MACHINE, params(BEAM2_X=2600, BEAM1_POD1_Y=1200), -18)
        self.assertGreaterEqual(len(r.problems), 2)

    def test_provisional_warning(self):
        m = dict(MACHINE, provisional=['pod_height'])
        r = tg.build(m, params(), -18)
        self.assertEqual(r.problems, [])
        self.assertTrue(any('pod_height' in w for w in r.warnings))

    def test_reference_warning(self):
        self.assertTrue(any('S2' in w for w in tg.reference_warnings('S1', ['S1', 'S2'], {'S2'})))
        self.assertEqual(tg.reference_warnings('S1', ['S1'], set()), [])


if __name__ == '__main__':
    unittest.main()
