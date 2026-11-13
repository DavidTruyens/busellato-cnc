import os
import re
import sys
import unittest

from helpers import REPO, TOOLS

sys.path.insert(0, TOOLS)
import check_cnc90  # noqa: E402

DIR = os.path.join(REPO, 'post', 'machine-tests')
NAMES = ['ZZT1', 'ZZT1D', 'ZZT1A', 'ZZT1AD', 'ZZT2A', 'ZZT3A', 'ZZT3B', 'ZZT3C', 'ZZT3D',
         'ZZT4D']
REAL = ['ZZT1', 'ZZT1D']  # cut into an 18 mm panel; every other program runs in the air


def read_lines(name):
    with open(os.path.join(DIR, name), 'rb') as fh:
        return fh.read().decode('ascii').split('\r\n')[:-1]


class MachineTestProgramsTest(unittest.TestCase):
    def test_programs_valid(self):
        for n in NAMES:
            with open(os.path.join(DIR, n), 'rb') as fh:
                self.assertEqual(check_cnc90.check(fh.read(), n), [], n)

    def test_names_not_on_machine(self):
        with open(os.path.join(REPO, 'hdd', 'LISTING.TXT'), encoding='cp850') as fh:
            listing = fh.read()
        in_z = re.search(r'Directory di C:\\CNC90\\MOD1\\SORG\\SRG\\Z\r?\n(.*?)(?:\r?\n\s*Directory di|\Z)',
                         listing, re.S).group(1)
        existing = {l.split()[0] for l in in_z.splitlines() if l.strip() and not l.startswith(' ')}
        for n in NAMES:
            self.assertNotIn(n, existing, n)

    def test_air_programs_stay_high(self):
        # "A" programs: stock thickness 60 in G71, max depth 2 -> tool stays >= 58 mm above the table
        for n in [x for x in NAMES if x not in REAL]:
            lines = read_lines(n)
            self.assertTrue(lines[0].startswith('G71') and 'Z60T00' in lines[0], n)
            for l in lines[2:-1]:
                depth = re.search(r'Z([\d.]+)$', l)
                if depth:
                    self.assertLessEqual(float(depth.group(1)), 2, f'{n}: {l}')

    def test_air_contour_matches_real_contour(self):
        # ZZT1A is the air rehearsal of ZZT1: same moves (G88/G1/G2/G3 order, same XY),
        # so the air run shows origin, Y direction and arc direction of the real cut.
        def moves(name):
            return [(re.match(r'G\d+', l).group(0), re.search(r'X([-\d.]+)Y([-\d.]+)', l).groups())
                    for l in read_lines(name)[2:-1]]
        real, air = moves('ZZT1'), moves('ZZT1A')
        self.assertEqual(real, air)
        self.assertIn('G2', [c for c, _ in real])
        self.assertIn('G3', [c for c, _ in real])

    def test_drill_head_check_calls_each_vertical_drill_once(self):
        # ZZT4D: one air hole per vertical drill T1..T14, in order, each at its own X, so the
        # position and the order show which spindle has which number
        lines = read_lines('ZZT4D')[2:-1]
        tools = [int(re.search(r'T01(\d\d)', l).group(1)) for l in lines]
        xs = [float(re.search(r'X([\d.]+)', l).group(1)) for l in lines]
        self.assertEqual(tools, list(range(1, 15)))
        self.assertEqual(len(set(xs)), 14)
        self.assertTrue(all(l.startswith('G81') for l in lines))


if __name__ == '__main__':
    unittest.main()
