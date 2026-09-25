import os
import subprocess
import unittest

from helpers import REPO, read_text

HEADER = '| ID | Label | Imaged | SHA-256 | Bad sectors | Files expected / found | Boot sector | Contents |'


class RepoLayoutTest(unittest.TestCase):
    def test_disk_files_are_binary_to_git(self):
        for d in ('disks', 'hdd'):
            r = subprocess.run(['git', 'check-attr', 'text', '--', f'{d}/X/files/CNC90.BAT'],
                               cwd=REPO, capture_output=True, text=True, check=True)
            self.assertIn('text: unset', r.stdout, d)

    def test_index_header(self):
        self.assertIn(HEADER, read_text(os.path.join(REPO, 'disks', 'README.md')))


if __name__ == '__main__':
    unittest.main()
