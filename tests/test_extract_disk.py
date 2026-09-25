import os
import shutil
import subprocess
import tempfile
import time
import unittest

from helpers import IMG_SIZE, TOOLS, make_floppy, read_bytes, read_text, write_bytes, write_text
from test_diskimg import MAP_BAD, MAP_CLEAN, clobber_sector0

SCRIPT = os.path.join(TOOLS, 'extract-disk.sh')
DATE_1992 = time.mktime((1992, 9, 9, 12, 14, 0, 0, 0, -1))


class ExtractDiskTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dir = os.path.join(self.tmp, 'D09')
        os.mkdir(self.dir)
        self.img = os.path.join(self.dir, 'D09.img')

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_script(self, expected='2', label='TEST DISK'):
        env = dict(os.environ, DISKS_DIR=self.tmp)
        return subprocess.run([SCRIPT, 'D09', label, expected],
                              capture_output=True, text=True, env=env)

    def files(self):
        root = os.path.join(self.dir, 'files')
        return sorted(os.path.relpath(os.path.join(d, f), root)
                      for d, _, fs in os.walk(root) for f in fs)

    def test_clean_disk_row_and_files(self):
        make_floppy(self.img, {'CNC90.BAT': b'@ECHO OFF\r\n', 'SUB/X.TXT': b'x'}, DATE_1992)
        write_text(os.path.join(self.dir, 'D09.map'), MAP_CLEAN)
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.files(), ['CNC90.BAT', 'SUB/X.TXT'])
        self.assertEqual(read_bytes(os.path.join(self.dir, 'files', 'CNC90.BAT')),
                         b'@ECHO OFF\r\n')  # CRLF kept
        row = r.stdout.strip()
        self.assertTrue(row.startswith('| D09 | TEST DISK | 2026-09-25 | `'), row)
        self.assertIn('| 0 | 2 / 2 | OK |', row)

    def test_dir_txt_keeps_dos_dates(self):
        make_floppy(self.img, {'CNC90.BAT': b'x'}, DATE_1992)
        self.run_script(expected='1')
        listing = read_text(os.path.join(self.dir, 'D09.dir.txt'))
        self.assertIn('CNC90', listing)
        self.assertIn('1992-09-09', listing)

    def test_substituted_boot_sector_leaves_img_untouched(self):
        make_floppy(self.img, {'A.TXT': b'a', 'B.TXT': b'b'})
        damaged = clobber_sector0(read_bytes(self.img))
        write_bytes(self.img, damaged)
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('| substituted |', r.stdout)
        self.assertEqual(read_bytes(self.img), damaged)
        self.assertEqual(self.files(), ['A.TXT', 'B.TXT'])

    def test_bad_sectors_flagged(self):
        make_floppy(self.img, {'A.TXT': b'a', 'B.TXT': b'b'})
        write_text(os.path.join(self.dir, 'D09.map'), MAP_BAD)
        r = self.run_script()
        self.assertEqual(r.returncode, 3)
        self.assertIn('| 3 |', r.stdout)          # 0x600 bytes = 3 sectors
        self.assertEqual(self.files(), ['A.TXT', 'B.TXT'])

    def test_count_mismatch_flagged(self):
        make_floppy(self.img, {'A.TXT': b'a'})
        r = self.run_script(expected='28')
        self.assertEqual(r.returncode, 3)
        self.assertIn('28 / 1 ⚠', r.stdout)

    def test_rerun_replaces_files(self):
        make_floppy(self.img, {'OLD.TXT': b'o', 'KEEP.TXT': b'k'})
        self.run_script()
        make_floppy(self.img, {'NEW.TXT': b'n', 'KEEP.TXT': b'k'})
        self.run_script()
        self.assertEqual(self.files(), ['KEEP.TXT', 'NEW.TXT'])

    def test_unrecognised_image_leaves_files_alone(self):
        make_floppy(self.img, {'A.TXT': b'a', 'B.TXT': b'b'})
        self.run_script()
        write_bytes(self.img, os.urandom(IMG_SIZE))
        r = self.run_script()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.files(), ['A.TXT', 'B.TXT'])

    def test_windows_folder_extracted_not_counted(self):
        make_floppy(self.img, {'A.TXT': b'a', 'B.TXT': b'b',
                               'SYSTEM~1/INDEXE~1': b'guid'})
        # mtools stores the long name only via VFAT; rename the dir to match real disks
        subprocess.run(['mren', '-i', self.img, '::/SYSTEM~1',
                        '::/System Volume Information'], check=True, capture_output=True)
        r = self.run_script(expected='2')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('System Volume Information/INDEXE~1', self.files())
        self.assertIn('| 2 / 2 |', r.stdout)

    def test_empty_disk(self):
        make_floppy(self.img, {})
        r = self.run_script(expected='0')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.files(), [])

    def test_missing_image(self):
        r = self.run_script()
        self.assertEqual(r.returncode, 1)

    def test_damaged_fat_still_reports(self):
        make_floppy(self.img, {'A.TXT': b'a', 'BIG.BIN': os.urandom(40000)})
        d = bytearray(read_bytes(self.img))
        d[512:1024] = bytes(512)  # first FAT sector lost, as a bad sector leaves it
        write_bytes(self.img, bytes(d))
        r = self.run_script()
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertTrue(r.stdout.startswith('| D09 |'), r.stdout)
        self.assertIn('extraction failed', r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.dir, 'D09.dir.txt')))

    def test_short_read_still_extracts(self):
        make_floppy(self.img, {'A.TXT': b'a', 'B.TXT': b'b'})
        full = read_bytes(self.img)
        write_bytes(self.img, full[:0x110000])
        write_text(os.path.join(self.dir, 'D09.map'), MAP_CLEAN.replace(
            '0x00000000  0x00168000  +', '0x00000000  0x00110000  +\n0x00110000  0x00058000  -'))
        r = self.run_script()
        self.assertEqual(r.returncode, 3)
        self.assertIn('| 704 | 2 / 2 |', r.stdout)
        self.assertEqual(self.files(), ['A.TXT', 'B.TXT'])
        self.assertEqual(read_bytes(self.img), full[:0x110000])  # raw image untouched

    def test_invalid_id_rejected(self):
        # ID '..' would resolve to <tmp>/...img and rm -rf <tmp>/files
        disks = os.path.join(self.tmp, 'disks')
        os.mkdir(disks)
        make_floppy(os.path.join(self.tmp, '...img'), {'A.TXT': b'a'})
        os.mkdir(os.path.join(self.tmp, 'files'))
        sentinel = os.path.join(self.tmp, 'files', 'KEEP')
        write_bytes(sentinel, b'k')
        os.mkdir(os.path.join(disks, 'D1'))
        make_floppy(os.path.join(disks, 'D1', 'D1.img'), {'A.TXT': b'a'})
        env = dict(os.environ, DISKS_DIR=disks)
        for bad in ('..', 'D1'):
            r = subprocess.run([SCRIPT, bad, 'L', '1'], capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 1, bad)
        self.assertTrue(os.path.exists(sentinel))

if __name__ == '__main__':
    unittest.main()
