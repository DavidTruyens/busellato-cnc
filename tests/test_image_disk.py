import os
import shutil
import subprocess
import tempfile
import unittest

from helpers import TOOLS, make_floppy, read_bytes, read_text, write_bytes, write_text

SCRIPT = os.path.join(TOOLS, 'image-disk.sh')


class ImageDiskTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, 'source.img')
        make_floppy(self.src, {'A.TXT': b'a', 'B.TXT': b'b'})
        self.disks = os.path.join(self.tmp, 'disks')

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_script(self, *extra):
        env = dict(os.environ, DISKS_DIR=self.disks)
        return subprocess.run([SCRIPT, 'D09', 'TEST', '2', *extra],
                              capture_output=True, text=True, env=env)

    def test_images_file_source_and_extracts(self):
        r = self.run_script(self.src)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = os.path.join(self.disks, 'D09')
        self.assertEqual(read_bytes(os.path.join(d, 'D09.img')), read_bytes(self.src))
        self.assertIn('# Mapfile', read_text(os.path.join(d, 'D09.map')))
        self.assertTrue(os.path.exists(os.path.join(d, 'files', 'A.TXT')))
        self.assertIn('| 0 | 2 / 2 | OK |', r.stdout)

    def test_refuses_rerun_of_complete_capture(self):
        self.run_script(self.src)
        img = os.path.join(self.disks, 'D09', 'D09.img')
        before = read_bytes(img)
        other = os.path.join(self.tmp, 'other.img')
        make_floppy(other, {'X.TXT': b'x'})
        r = self.run_script(other)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(read_bytes(img), before)

    def test_refuses_img_without_map(self):
        d = os.path.join(self.disks, 'D09')
        os.makedirs(d)
        write_bytes(os.path.join(d, 'D09.img'), read_bytes(self.src))
        r = self.run_script(self.src)
        self.assertEqual(r.returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(d, 'D09.map')))

    def test_resumes_incomplete_capture(self):
        self.run_script(self.src)
        m = os.path.join(self.disks, 'D09', 'D09.map')
        text = read_text(m).replace('0x00000000  0x00168000  +',
                                    '0x00000000  0x00001000  +\n0x00001000  0x00167000  -')
        write_text(m, text)
        r = self.run_script(self.src)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_source_larger_than_floppy_is_capped(self):
        big = os.path.join(self.tmp, 'big.img')
        write_bytes(big, read_bytes(self.src) + os.urandom(600000))
        self.run_script(big)
        self.assertEqual(os.path.getsize(os.path.join(self.disks, 'D09', 'D09.img')), 1474560)

    def test_usage(self):
        r = subprocess.run([SCRIPT, 'D09'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)


if __name__ == '__main__':
    unittest.main()
