import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from nesting.backends import BACKENDS
from nesting.backends.cnc90 import emit, fmt
from nesting.dxf import read_dxf
from nesting.geometry import Arc, Line
from nesting.layout import ShapeEntry, build_plan
from nesting.program import ContourOp, DrillOp, Program, plan_programs
from nesting.settings import Settings

repo = Path(__file__).resolve().parent.parent
MT = repo / 'post' / 'machine-tests'


def golden(name):
    return (MT / name).read_bytes().decode('ascii')


def zzt1_segs():
    return [
        Arc((388.974, 80.69), (389, 80), (380, 80), 9, False),
        Line((389, 80), (389, 20)),
        Arc((389, 20), (380, 11), (380, 20), 9, False),
        Line((380, 11), (220, 11)),
        Arc((220, 11), (211, 20), (220, 20), 9, False),
        Line((211, 20), (211, 180)),
        Arc((211, 180), (220, 189), (220, 180), 9, False),
        Line((220, 189), (290, 189)),
        Arc((290, 189), (299, 180), (290, 180), 9, False),
        Line((299, 180), (299, 110)),
        Arc((299, 110), (320, 89), (320, 110), 21, True),
        Line((320, 89), (380, 89)),
        Arc((380, 89), (388.974, 80.69), (380, 80), 9, False),
    ]


class Cnc90Tests(unittest.TestCase):
    def setUp(self):
        self.s = Settings()

    def test_matches_ZZT1AD(self):
        ops = [DrillOp(320, 220, 2, 6), DrillOp(352, 220, 2, 6), DrillOp(320, 260, 2, 6)]
        p = Program('ZZT1AD', 1, 'drill', '', (400, 300, 60), ops, None, 1, 1)
        self.assertEqual(emit(p, self.s), golden('ZZT1AD'))

    def test_matches_ZZT2A(self):
        op = ContourOp([Line((0, 159), (500, 159))], 2, 'x')
        p = Program('ZZT2A', 65, 'cut', '', (400, 300, 60), [op], 18000, 0.333, 1)
        self.assertEqual(emit(p, self.s), golden('ZZT2A'))

    def test_matches_ZZT1(self):
        op = ContourOp(zzt1_segs(), 2, 'x')
        p = Program('ZZT1', 65, 'cut', '', (400, 300, 18), [op], 18000, 1, 3)
        self.assertEqual(emit(p, self.s), golden('ZZT1'))

    def test_equal_feeds_arc_first_no_repeat_line(self):
        op = ContourOp(zzt1_segs(), 2, 'x')
        p = Program('T', 66, 'cut', '', (400, 300, 18), [op], 18000, 3, 3)
        lines = emit(p, self.s).split('\r\n')
        self.assertTrue(lines[2].startswith('G88G90G54P5T0166S18000F3X388.974'))
        self.assertTrue(lines[3].startswith('G2G90G17'))

    def test_n_and_l_counts(self):
        op = ContourOp(zzt1_segs(), 2, 'x')
        p = Program('T', 66, 'cut', '', (400, 300, 18), [op, op], 18000, 1, 3)
        lines = emit(p, self.s).split('\r\n')[:-1]
        m = re.match(r'G71X400Y300Z18T00N(\d+)L(\d+)$', lines[0])
        self.assertEqual(int(m.group(1)), len(lines))
        self.assertEqual(int(m.group(2)), len(lines) - 3)

    def test_number_format(self):
        self.assertEqual(fmt(9.15), '9.15')
        self.assertEqual(fmt(13.0), '13')
        self.assertEqual(fmt(0.5), '0.5')
        self.assertEqual(fmt(18.299999999999997), '18.3')
        self.assertEqual(fmt(-0.0001), '0')
        self.assertEqual(fmt(388.9744), '388.974')

    def test_crlf_upper_ascii(self):
        op = ContourOp(zzt1_segs(), 2, 'x')
        text = emit(Program('T', 66, 'cut', 'abc', (400, 300, 18), [op], 18000, 1, 3), self.s)
        text.encode('ascii')
        self.assertEqual(text, text.upper())
        self.assertTrue(text.endswith('M2\r\n'))
        self.assertNotIn('\n', text.replace('\r\n', ''))

    def test_origin_g55(self):
        self.s.origin = 'G55'
        p = Program('T', 1, 'drill', '', (400, 300, 60), [DrillOp(1, 2, 3, 6)], None, 1, 1)
        self.assertIn('G81G90G55P5T0101X1Y2Z3\r\n', emit(p, self.s))

    def test_registry_has_cnc90(self):
        self.assertIs(BACKENDS['cnc90'], emit)

    def test_passes_check_cnc90(self):
        entries = [ShapeEntry(read_dxf(p)) for p in sorted((repo / 'plates').glob('*.dxf'))]
        self.assertEqual(len(entries), 12)
        plan = build_plan(entries, self.s)
        progs = plan_programs(plan, self.s)
        self.assertTrue(progs)
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for p in progs:
                path = Path(tmp) / p.name
                path.write_bytes(emit(p, self.s).encode('ascii'))
                paths.append(str(path))
            r = subprocess.run([sys.executable, str(repo / 'tools' / 'check_cnc90.py'), *paths],
                               capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class MultiPassEmitTests(unittest.TestCase):
    """The default B01C as emitted: each shape contour is cut in three equal passes."""

    def test_default_b01c_pass_depths_in_the_text(self):
        s = Settings()
        es = [ShapeEntry(read_dxf(p)) for p in sorted((repo / 'plates').glob('*.dxf'))]
        prog = next(p for p in plan_programs(build_plan(es, s), s) if p.name == 'B01C')
        text = BACKENDS['cnc90'](prog, s)
        self.assertTrue(text.startswith(f'G71X{prog.stock[0]:g}Y{prog.stock[1]:g}Z36T00'))
        blocks, cur = [], None                  # one block per G88 (one pass)
        for line in text.split('\r\n')[2:]:
            if line.startswith('G88'):
                cur = []
                blocks.append(cur)
            if cur is not None:
                cur += [float(z) for z in re.findall(r'Z(-?[\d.]+)', line)]
        self.assertEqual(len(blocks), len(prog.ops))
        self.assertEqual(len(blocks), 6)        # 2 shapes x 3 passes, no template outline

        def distinct(bs):
            out = []
            for b in bs:
                self.assertEqual(len(set(b)), 1, b)      # a pass stays at one depth
                out.append(b[0])
            return out

        self.assertEqual(distinct(blocks), [6.167, 12.333, 18.5] * 2)


if __name__ == '__main__':
    unittest.main()
