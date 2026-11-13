import datetime
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nesting import importdisk
from nesting.dxf import read_dxf
from nesting.layout import ShapeEntry, build_plan
from nesting.output import write_output
from nesting.program import plan_programs
from nesting.settings import Settings

repo = Path(__file__).resolve().parent.parent

# made with record() of tools/make-import-disk.py (the mtools version) on the same input
ZZT2A_RECORD = bytes.fromhex(
    '5a5a54324120202020202020202020202020202020202020202020202020202020202020202031312f31332f3236'
    '2a0000000000004d0000c8430000964300007042009b97ff0100b000530000a0004e0d0a')
B01D_RECORD = bytes.fromhex(
    '4230314420202020202020202048454c4c4f20574f524c44202020202020202020202020202030312f30322f3033'
    '2a0000000000004d00509a4400d00d4400001242009b97ff0100b000530000a0004e0d0a')


class RecordTests(unittest.TestCase):
    def test_record_matches_the_original_tool(self):
        self.assertEqual(importdisk.record('B01D', 'HELLO WORLD', '01/02/03', 1234.5, 567.25, 36.5),
                         B01D_RECORD)

    def test_machine_test_program_record_matches_the_original_tool(self):
        text = (repo / 'post' / 'machine-tests' / 'ZZT2A').read_bytes()
        self.assertEqual(importdisk.index({'ZZT2A': text}, '11/13/26'), ZZT2A_RECORD)

    def test_record_fields(self):
        r = importdisk.record('ZZT1', 'A COMMENT THAT IS LONGER THAN 25', '12/31/26', 400, 300, 60)
        self.assertEqual(len(r), 82)
        self.assertEqual(r[:13], b'ZZT1'.ljust(13))
        self.assertEqual(r[13:38], b'A COMMENT THAT IS LONGER ')
        self.assertEqual(r[38:46], b'12/31/26')
        self.assertEqual(r[46:54], b'*' + bytes(6) + b'M')
        self.assertEqual(struct.unpack('<fff', r[54:66]), (400.0, 300.0, 60.0))
        self.assertEqual(r[-2:], b'\r\n')

    def test_describe(self):
        self.assertEqual(importdisk.describe('g71x400.5y300z60t00n5l2\r\ng150(part a)\r\n'),
                         ('PART A', 400.5, 300.0, 60.0))
        self.assertEqual(importdisk.describe('G71X1Y2Z3T00N5L2\r\nG88G90\r\n'), ('', 1, 2, 3))
        with self.assertRaises(ValueError):
            importdisk.describe('G1X0\r\n')

    def test_index_sorted_by_name(self):
        src = b'G71X1Y2Z3T00N5L2\r\nG150()\r\n'
        idx = importdisk.index({'B02C': src, 'B01D': src, 'B01C': src}, '01/01/27')
        names = [idx[i:i + 13].strip() for i in range(0, len(idx), 82)]
        self.assertEqual(names, [b'B01C', b'B01D', b'B02C'])


class DisketteFolderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Settings()
        entries = [ShapeEntry(read_dxf(p)) for p in sorted((repo / 'plates').glob('*.dxf'))]
        cls.plan = build_plan(entries, cls.s)
        cls.progs = plan_programs(cls.plan, cls.s)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / 'job'
        write_output(self.out, self.plan, self.progs, self.s, {'name': 'x'},
                     today=datetime.date(2026, 11, 13))
        self.disk = self.out / 'DISKETTE'
        self.names = sorted(p.name for p in self.progs)

    def test_layout(self):
        root = sorted(p.name for p in self.disk.iterdir())
        self.assertEqual(root, sorted(self.names + list(importdisk.LOADER_FILES) + ['SORG']))
        self.assertEqual(sorted(p.name for p in (self.disk / 'SORG').iterdir()), ['INDICE.PRG', 'SRG'])
        tree = sorted(str(p.relative_to(self.disk / 'SORG' / 'SRG'))
                      for p in (self.disk / 'SORG' / 'SRG').rglob('*') if p.is_file())
        self.assertEqual(tree, sorted(str(Path(n[0]) / n[1:]) for n in self.names))

    def test_files_match_the_job_byte_for_byte(self):
        for n in self.names:
            data = (self.out / n).read_bytes()
            self.assertEqual((self.disk / n).read_bytes(), data, n)
            self.assertEqual((self.disk / 'SORG' / 'SRG' / n[0] / n[1:]).read_bytes(), data, n)
        for f in importdisk.LOADER_FILES:
            self.assertEqual((self.disk / f).read_bytes(), (self.out / f).read_bytes(), f)

    def test_indice(self):
        idx = (self.disk / 'SORG' / 'INDICE.PRG').read_bytes()
        self.assertEqual(len(idx), 82 * len(self.names))
        recs = [idx[i:i + 82] for i in range(0, len(idx), 82)]
        self.assertEqual([r[:13].decode().strip() for r in recs], self.names)
        for r, n in zip(recs, self.names):
            self.assertEqual(r[38:46], b'11/13/26')
            comment, l, h, s = importdisk.describe((self.out / n).read_text(encoding='ascii'))
            self.assertEqual(r[13:38], comment.encode().ljust(25))
            self.assertEqual(struct.unpack('<fff', r[54:66]),
                             struct.unpack('<fff', struct.pack('<fff', l, h, s)))
            self.assertEqual(r, importdisk.record(n, comment, '11/13/26', l, h, s))

    def test_sample_fits_with_room_to_spare(self):
        clusters, root = importdisk.usage(self.disk)
        self.assertLess(clusters, importdisk.CLUSTERS * importdisk.SPARE)
        self.assertLess(root, importdisk.ROOT_ENTRIES)
        self.assertIsNone(importdisk.size_warning(self.disk))

    def test_size_warning_when_too_big(self):
        big = Path(self.tmp.name) / 'big'
        big.mkdir()
        (big / 'A').write_bytes(bytes(1_400_000))
        self.assertIn('nearly fills', importdisk.size_warning(big))
        (big / 'A').write_bytes(bytes(1_500_000))
        self.assertIn('does not fit', importdisk.size_warning(big))
        many = Path(self.tmp.name) / 'many'
        many.mkdir()
        for i in range(230):
            (many / f'F{i}').write_bytes(b'x')
        self.assertIn('at most 224', importdisk.size_warning(many))

    def test_diskette_failure_leaves_nothing(self):
        out = Path(self.tmp.name) / 'job2'
        with mock.patch('nesting.output.write_diskette', side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                write_output(out, self.plan, self.progs, self.s, {})
        self.assertFalse(out.exists())
        self.assertEqual(sorted(p.name for p in Path(self.tmp.name).iterdir()), ['job'])


if __name__ == '__main__':
    unittest.main()
