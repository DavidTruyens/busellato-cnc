import builtins
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nesting import diskette
from nesting.dxf import read_dxf
from nesting.layout import ShapeEntry, build_plan
from nesting.output import write_output
from nesting.program import plan_programs
from nesting.settings import Settings

repo = Path(__file__).resolve().parent.parent
FLOPPY = 1_457_664


class Fake(diskette.System):
    def __init__(self, answers=(), windows=False, drive_type=diskette.DRIVE_REMOVABLE,
                 total=FLOPPY, mount=True, drives=('A:',)):
        self.answers = list(answers)
        self.asked, self.said = [], []
        super().__init__(windows=windows, drive_type=lambda root: drive_type,
                         removable_drives=lambda: list(drives), total=lambda p: total,
                         is_mount=lambda p: mount, ask=self._ask, say=self.said.append)

    def _ask(self, prompt):
        self.asked.append(prompt)
        if not self.answers:
            raise AssertionError(f'unexpected question: {prompt}')
        return self.answers.pop(0)

    @property
    def text(self):
        return '\n'.join(self.said)


def tree(folder: Path) -> dict:
    return {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob('*') if p.is_file()}


class DisketteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctmp = tempfile.TemporaryDirectory()
        s = Settings()
        plan = build_plan([ShapeEntry(read_dxf(p)) for p in sorted((repo / 'plates').glob('*.dxf'))], s)
        cls.project = Path(cls.ctmp.name) / 'project'
        cls.job = cls.project / 'out' / '20261113-101500'
        write_output(cls.job, plan, plan_programs(plan, s), s, {})
        cls.src = tree(cls.job / 'DISKETTE')

    @classmethod
    def tearDownClass(cls):
        cls.ctmp.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.drive = Path(self.tmp.name) / 'floppy'
        self.drive.mkdir()

    def run_main(self, fake, *args):
        return diskette.main([*map(str, args)], fake)

    # --- writing ------------------------------------------------------------------------------
    def test_empty_diskette_is_written_and_verified(self):
        fake = Fake()
        self.assertEqual(self.run_main(fake, self.job, self.drive), 0, fake.text)
        self.assertEqual(tree(self.drive), self.src)
        self.assertEqual(fake.asked, [])
        self.assertIn('read back identical', fake.text)
        self.assertIn('Eject', fake.text)
        self.assertIn('LOAD.BAT', self.src)
        self.assertIn(str(Path('SORG') / 'INDICE.PRG'), self.src)

    def test_project_folder_means_its_newest_job(self):
        older = self.project / 'out' / '20261113-101500-2'
        newer = self.project / 'out' / '20261113-101500-10'
        for p in (older, newer):
            shutil.copytree(self.job, p)
        self.addCleanup(shutil.rmtree, older)
        self.addCleanup(shutil.rmtree, newer)
        (newer / 'DISKETTE' / 'MARK').write_bytes(b'newest')
        fake = Fake()
        self.assertEqual(self.run_main(fake, self.project, self.drive), 0, fake.text)
        self.assertEqual((self.drive / 'MARK').read_bytes(), b'newest')

    def test_job_without_diskette_folder_is_refused(self):
        old = Path(self.tmp.name) / 'p' / 'out' / '20250101-000000'
        old.mkdir(parents=True)
        fake = Fake()
        self.assertEqual(self.run_main(fake, old.parent.parent, self.drive), 1)
        self.assertIn('no DISKETTE folder', fake.text)

    # --- safety -------------------------------------------------------------------------------
    def test_windows_refuses_a_drive_that_is_not_removable(self):
        fake = Fake(windows=True, drive_type=3)          # DRIVE_FIXED
        self.assertEqual(self.run_main(fake, self.job, 'C:'), 1)
        self.assertIn('not a removable drive', fake.text)

    def test_windows_refuses_a_removable_drive_larger_than_a_diskette(self):
        fake = Fake(windows=True, total=16_000_000_000)  # a USB stick
        self.assertEqual(self.run_main(fake, self.job, 'E:'), 1)
        self.assertIn('not a 1.44 MB diskette', fake.text)

    def test_windows_rejects_a_path_instead_of_a_drive_letter(self):
        fake = Fake(windows=True)
        self.assertEqual(self.run_main(fake, self.job, r'C:\Users'), 1)
        self.assertIn('not a drive letter', fake.text)

    def test_windows_asks_for_the_drive_and_stops_on_empty_answer(self):
        fake = Fake(windows=True, answers=[''])
        self.assertEqual(self.run_main(fake, self.job), 1)
        self.assertIn('Removable drives: A:', fake.text)
        self.assertIn('nothing written', fake.text)

    def test_oversize_mount_refused_unless_forced(self):
        (self.drive / 'OLD').write_bytes(b'old')
        fake = Fake(total=500_000_000)
        self.assertEqual(self.run_main(fake, self.job, self.drive), 1)
        self.assertEqual(tree(self.drive), {'OLD': b'old'})
        fake = Fake(total=500_000_000, answers=['YES'])
        self.assertEqual(self.run_main(fake, self.job, self.drive, '--force-size'), 0, fake.text)
        self.assertEqual(tree(self.drive), self.src)

    def test_job_folder_and_repo_are_refused_as_target(self):
        for target in (self.job, self.job / 'DISKETTE', self.project, repo, repo / 'plates'):
            fake = Fake()
            self.assertEqual(self.run_main(fake, self.job, target), 1, target)
            self.assertIn('refused', fake.text)
        self.assertEqual(tree(self.job / 'DISKETTE'), self.src)

    def test_missing_target_folder_is_refused(self):
        fake = Fake()
        self.assertEqual(self.run_main(fake, self.job, self.drive / 'nope'), 1)
        self.assertIn('not an existing folder', fake.text)

    # --- erase / keep -------------------------------------------------------------------------
    def test_non_empty_diskette_needs_yes(self):
        (self.drive / 'OLD').write_bytes(b'old')
        (self.drive / 'DIR').mkdir()
        (self.drive / 'DIR' / 'X').write_bytes(b'x')
        fake = Fake(answers=['yes'])                     # only YES counts
        self.assertEqual(self.run_main(fake, self.job, self.drive), 1)
        self.assertIn('2 files', fake.text)
        self.assertEqual(tree(self.drive), {'OLD': b'old', str(Path('DIR') / 'X'): b'x'})
        fake = Fake(answers=['YES'])
        self.assertEqual(self.run_main(fake, self.job, self.drive), 0, fake.text)
        self.assertEqual(tree(self.drive), self.src)
        self.assertFalse((self.drive / 'DIR').exists())

    def test_empty_folder_alone_also_needs_yes(self):
        (self.drive / 'EMPTY').mkdir()
        fake = Fake(answers=['YES'])
        self.assertEqual(self.run_main(fake, self.job, self.drive), 0, fake.text)
        self.assertEqual(len(fake.asked), 1)
        self.assertFalse((self.drive / 'EMPTY').exists())

    def test_keep_adds_without_erasing(self):
        (self.drive / 'OLD').write_bytes(b'old')
        fake = Fake()
        self.assertEqual(self.run_main(fake, self.job, self.drive, '--keep'), 0, fake.text)
        self.assertIn('INDICE.PRG replaces', fake.text)
        self.assertEqual(tree(self.drive), {**self.src, 'OLD': b'old'})

    def test_keep_asks_before_overwriting(self):
        (self.drive / 'LOAD.BAT').write_bytes(b'mine')
        fake = Fake(answers=['no'])
        self.assertEqual(self.run_main(fake, self.job, self.drive, '--keep'), 1)
        self.assertEqual(tree(self.drive), {'LOAD.BAT': b'mine'})
        fake = Fake(answers=['YES'])
        self.assertEqual(self.run_main(fake, self.job, self.drive, '--keep'), 0, fake.text)
        self.assertEqual(tree(self.drive), self.src)

    # --- failures -----------------------------------------------------------------------------
    def test_write_error_is_reported(self):
        fake = Fake()
        with mock.patch('nesting.diskette.os.fsync', side_effect=OSError(28, 'No space left on device')):
            self.assertEqual(self.run_main(fake, self.job, self.drive), 1)
        self.assertIn('ERROR', fake.text)
        self.assertIn('No space left', fake.text)
        self.assertNotIn('OK:', fake.text)

    def test_read_back_difference_is_reported(self):
        real_open = builtins.open

        class Lossy:
            def __init__(self, f):
                self.f = f

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return self.f.__exit__(*a)

            def write(self, data):
                return self.f.write(data[:-1] if data.endswith(b'\r\n') and b'G71' in data else data)

            def __getattr__(self, name):
                return getattr(self.f, name)

        def lossy_open(path, mode='r', *a, **kw):
            return Lossy(real_open(path, mode, *a, **kw))

        fake = Fake()
        with mock.patch('nesting.diskette.open', lossy_open, create=True):
            self.assertEqual(self.run_main(fake, self.job, self.drive), 1)
        self.assertIn('Read back differs', fake.text)
        self.assertIn('B01D', fake.text)
        self.assertNotIn('OK:', fake.text)


if __name__ == '__main__':
    unittest.main()
