import os
import subprocess
import sys
import tempfile
import unittest

from helpers import IMG_SIZE, TOOLS, make_floppy, read_bytes, write_bytes

sys.path.insert(0, TOOLS)
import diskimg  # noqa: E402

# Captured from the real Mac with D01 in the USB drive (2026-09-25).
DISKUTIL_ONE = """/dev/disk4 (external, physical):
   #:                       TYPE NAME                    SIZE       IDENTIFIER
   0:     FDisk_partition_scheme                        *1.5 MB     disk4
   1:               DOS_FAT_16_S                         1.5 MB     disk4s1

"""
USB_STICK = """/dev/disk5 (external, physical):
   #:                       TYPE NAME                    SIZE       IDENTIFIER
   0:     FDisk_partition_scheme                        *32.0 GB    disk5
   1:             Windows_FAT_32 STICK                   32.0 GB    disk5s1

"""
FLOPPY_TWO = DISKUTIL_ONE.replace('disk4', 'disk6')

MAP_CLEAN = """# Mapfile. Created by GNU ddrescue version 1.30
# Start time:   2026-09-25 10:06:51
# current_pos  current_status  current_pass
0x00160000     +               1
#      pos        size  status
0x00000000  0x00168000  +
"""
MAP_BAD = """# Mapfile. Created by GNU ddrescue version 1.30
# current_pos  current_status  current_pass
0x00001000     +               1
#      pos        size  status
0x00000000  0x00001000  +
0x00001000  0x00000400  -
0x00001400  0x00000200  /
0x00001600  0x00166A00  +
"""


def floppy_bytes(files=None):
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, 'a.img')
        make_floppy(p, files or {'A.TXT': b'hello'})
        return read_bytes(p)


def clobber_sector0(data):
    """Mimic the damage seen on D01/D02: sector 0 replaced by an MBR."""
    mbr = bytearray(512)
    mbr[0x1BE:0x1CE] = bytes.fromhex('80010100040391651100000007a30000')
    mbr[510:512] = b'\x55\xAA'
    return bytes(mbr) + data[512:]


class ClassifyTest(unittest.TestCase):
    def test_fresh_floppy_is_ok(self):
        self.assertEqual(diskimg.classify(floppy_bytes()), 'ok')

    def test_overwritten_sector0_is_substitute(self):
        self.assertEqual(diskimg.classify(clobber_sector0(floppy_bytes())), 'substitute')

    def test_wrong_size_is_unrecognised(self):
        self.assertEqual(diskimg.classify(floppy_bytes()[:-512]), 'unrecognised')

    def test_random_data_is_unrecognised(self):
        self.assertEqual(diskimg.classify(os.urandom(IMG_SIZE)), 'unrecognised')

    def test_fat_copies_differ_is_unrecognised(self):
        d = bytearray(clobber_sector0(floppy_bytes()))
        d[512 * 10 + 5] ^= 0xFF  # corrupt second FAT copy
        self.assertEqual(diskimg.classify(bytes(d)), 'unrecognised')


class MakeWorkingTest(unittest.TestCase):
    def test_ok_image_returned_unchanged(self):
        d = floppy_bytes()
        out, status = diskimg.make_working(d)
        self.assertEqual((out, status), (d, 'ok'))

    def test_substituted_image_is_readable_by_mtools(self):
        d = clobber_sector0(floppy_bytes({'CNC90.BAT': b'@ECHO OFF\r\n'}))
        out, status = diskimg.make_working(d)
        self.assertEqual(status, 'substituted')
        self.assertEqual(out[512:], d[512:])
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, 'w.img')
            write_bytes(p, out)
            r = subprocess.run(['mtype', '-i', p, '::/CNC90.BAT'],
                               capture_output=True, check=True)
            self.assertEqual(r.stdout, b'@ECHO OFF\r\n')

    def test_short_read_is_padded(self):
        # ddrescue leaves the image short when the tail of the disk is unreadable
        d = floppy_bytes()
        out, status = diskimg.make_working(d[:0x110000])
        self.assertEqual(status, 'ok')
        self.assertEqual(len(out), IMG_SIZE)
        self.assertEqual(out[:0x110000], d[:0x110000])
        self.assertEqual(out[0x110000:], bytes(IMG_SIZE - 0x110000))

    def test_unrecognised_raises(self):
        with self.assertRaises(ValueError):
            diskimg.make_working(os.urandom(IMG_SIZE))

    def test_real_d01_if_present(self):
        p = os.path.join(os.path.dirname(TOOLS), 'disks', 'D01', 'D01.img')
        if not os.path.exists(p):
            self.skipTest('D01.img not present')
        _, status = diskimg.make_working(read_bytes(p))
        self.assertEqual(status, 'substituted')


class BadBytesTest(unittest.TestCase):
    def test_clean_map(self):
        self.assertEqual(diskimg.bad_bytes(MAP_CLEAN), 0)

    def test_bad_and_untrimmed_areas_counted(self):
        self.assertEqual(diskimg.bad_bytes(MAP_BAD), 0x400 + 0x200)


class FindFloppyTest(unittest.TestCase):
    def test_find_floppy_single(self):
        self.assertEqual(diskimg.find_floppy(DISKUTIL_ONE + USB_STICK), '/dev/disk4')

    def test_find_floppy_rejects_two(self):
        with self.assertRaises(LookupError):
            diskimg.find_floppy(DISKUTIL_ONE + FLOPPY_TWO)

    def test_find_floppy_rejects_none(self):
        with self.assertRaises(LookupError):
            diskimg.find_floppy(USB_STICK)


class CliTest(unittest.TestCase):
    def run_cli(self, *args, stdin=''):
        return subprocess.run([sys.executable, os.path.join(TOOLS, 'diskimg.py'), *args],
                              input=stdin, capture_output=True, text=True)

    def test_work_cli_exit_2_on_garbage(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'g.img')
            write_bytes(src, os.urandom(IMG_SIZE))
            r = self.run_cli('work', src, os.path.join(tmp, 'o.img'))
            self.assertEqual(r.returncode, 2)
            self.assertFalse(os.path.exists(os.path.join(tmp, 'o.img')))

    def test_find_floppy_cli(self):
        r = self.run_cli('find-floppy', stdin=DISKUTIL_ONE)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, '/dev/disk4'))


if __name__ == '__main__':
    unittest.main()
