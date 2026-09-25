import os
import shutil
import subprocess
import tempfile
import unittest

from helpers import TOOLS, make_floppy, read_bytes, read_text

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

    def test_rerun_resumes_without_error(self):
        self.run_script(self.src)
        r = self.run_script(self.src)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_usage(self):
        r = subprocess.run([SCRIPT, 'D09'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)


if __name__ == '__main__':
    unittest.main()
