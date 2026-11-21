import builtins
import os
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
                 total=FLOPPY, mount=True, drives=('A:',), mac=False, on_remount=None):
        self.answers = list(answers)
        self.asked, self.said = [], []
        self.remounts = []              # per remount: (repair?, the files on the diskette then)
        self.on_remount = on_remount    # what the "remount" does to the diskette (macOS faults)
        super().__init__(windows=windows, drive_type=lambda root: drive_type,
                         removable_drives=lambda: list(drives), total=lambda p: total,
                         is_mount=lambda p: mount, ask=self._ask, say=self.said.append,
                         mac=mac, remount=self._remount)

    def _remount(self, target, repair=False):
        files = sorted(str(p.relative_to(target)) for p in target.rglob('*') if p.is_file())
        self.remounts.append(('repair' if repair else 'verify', files))
        if self.on_remount:
            self.on_remount(target, len(self.remounts), repair)

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
        self.assertIn(str(Path('SORG') / 'SRG' / 'B' / '01D'), fake.text)
        self.assertNotIn('OK:', fake.text)

    # --- the machine's program list: REG\\NOW.PRG (GETIDX.BAT) is kept on the Mac -----------
    def machine_list(self):
        from nesting.importdisk import record
        return b''.join(record(n, '', '11/01/26', 10, 10, 18) for n in ('A1', 'B9', 'Z1'))

    def saved(self):
        d = self.project / 'machine-index'
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def test_list_on_the_diskette_is_kept_before_erasing(self):
        saved = self.saved()
        (self.drive / 'REG').mkdir()
        (self.drive / 'REG' / 'NOW.PRG').write_bytes(self.machine_list())
        fake = Fake(answers=['YES'])
        self.assertEqual(self.run_main(fake, self.job, self.drive), 0, fake.text)
        [copy] = saved.iterdir()
        self.assertEqual(copy.read_bytes(), self.machine_list())
        self.assertIn('3 programs', fake.text)
        self.assertEqual(tree(self.drive), self.src)          # erased; the job as generated

    def test_without_a_list_nothing_is_kept(self):
        saved = self.saved()
        fake = Fake()
        self.assertEqual(self.run_main(fake, self.job, self.drive), 0, fake.text)
        self.assertFalse(saved.exists())
        self.assertEqual(tree(self.drive), self.src)

    def test_a_list_it_does_not_understand_is_not_kept(self):
        saved = self.saved()
        (self.drive / 'REG').mkdir()
        (self.drive / 'REG' / 'NOW.PRG').write_bytes(b'not an index')
        fake = Fake(answers=['YES'])
        self.assertEqual(self.run_main(fake, self.job, self.drive), 0, fake.text)
        self.assertIn('Not kept', fake.text)
        self.assertFalse(saved.exists())

    # --- macOS: event log, AppleDouble files, check after a remount ---------------------------
    NO_LOG = str(Path('.fseventsd') / 'no_log')

    @staticmethod
    def written(target):
        return (target / 'LOAD.BAT').exists()

    def test_mac_erase_then_repair_then_write_then_check(self):
        # deleting on the diskette under macOS leaked clusters (2026-11-20): after the erase a
        # repair frees them, and its remount makes no_log count; after writing (and removing
        # ._ files, deletes too) another repair, then a read-only check from a fresh mount
        (self.drive / 'OLD').write_bytes(b'old')
        fake = Fake(mac=True, answers=['YES'])
        self.assertEqual(self.run_main(fake, self.job, self.drive), 0, fake.text)
        self.assertEqual([r for r, _ in fake.remounts], ['repair', 'repair', 'verify'])
        self.assertEqual(fake.remounts[0][1], [self.NO_LOG])
        self.assertIn('LOAD.BAT', fake.remounts[1][1])
        self.assertEqual((self.drive / '.fseventsd' / 'no_log').read_bytes(), b'')
        self.assertEqual({k: v for k, v in tree(self.drive).items() if k != self.NO_LOG},
                         self.src)
        self.assertIn('after a remount', fake.text)

    def test_mac_failed_repair_writes_nothing(self):
        def broken(target, n, repair):
            raise diskette.Refused('the repair of the diskette failed')
        fake = Fake(mac=True, on_remount=broken)
        self.assertEqual(self.run_main(fake, self.job, self.drive), 1)
        self.assertIn('repair of the diskette failed', fake.text)
        self.assertEqual(list(tree(self.drive)), [self.NO_LOG])

    def test_mac_keep_checks_first_and_makes_no_log_count(self):
        fake = Fake(mac=True)
        self.assertEqual(self.run_main(fake, self.job, self.drive, '--keep'), 0, fake.text)
        self.assertEqual([r for r, _ in fake.remounts], ['verify', 'verify', 'repair', 'verify'])
        self.assertEqual(fake.remounts[:2], [('verify', []), ('verify', [self.NO_LOG])])
        fake = Fake(mac=True, answers=['YES'])          # no_log is there now: one less
        self.assertEqual(self.run_main(fake, self.job, self.drive, '--keep'), 0, fake.text)
        self.assertEqual([r for r, _ in fake.remounts], ['verify', 'repair', 'verify'])

    def test_mac_keep_failed_first_check_writes_nothing(self):
        def broken(target, n, repair):
            raise diskette.Refused('the file system check of the diskette failed')
        (self.drive / 'OLD').write_bytes(b'old')
        fake = Fake(mac=True, on_remount=broken)
        self.assertEqual(self.run_main(fake, self.job, self.drive, '--keep'), 1)
        self.assertIn('check of the diskette failed', fake.text)
        self.assertEqual(tree(self.drive), {'OLD': b'old'})

    def test_mac_appledouble_files_are_removed_after_writing(self):
        real = diskette.write_and_verify

        def with_appledouble(src, target, files):
            real(src, target, files)
            for rel in files:                    # what macOS does for files with xattrs
                (target / rel.parent / ('._' + rel.name)).write_bytes(b'\x00\x05\x16\x07')
            (target / '._SORG').write_bytes(b'x')
        fake = Fake(mac=True)
        with mock.patch('nesting.diskette.write_and_verify', with_appledouble):
            self.assertEqual(self.run_main(fake, self.job, self.drive), 0, fake.text)
        self.assertFalse([k for k in tree(self.drive) if Path(k).name.startswith('._')])

    def test_mac_appledouble_back_after_remount_is_refused(self):
        def appledouble(target, n, repair):
            if self.written(target) and not repair:
                (target / '._B01C').write_bytes(b'x')
        fake = Fake(mac=True, on_remount=appledouble)
        self.assertEqual(self.run_main(fake, self.job, self.drive), 1)
        self.assertIn('._B01C', fake.text)
        self.assertIn('Do not use this diskette', fake.text)
        self.assertNotIn('OK:', fake.text)

    def test_mac_file_overwritten_at_remount_is_refused(self):
        # seen 2026-11-20: at the remount macOS wrote its event-log id over a program's
        # cluster (it was B04P, a pocket program; the pockets are in B04C now)
        def corrupt(target, n, repair):
            if self.written(target) and not repair:
                (target / 'SORG' / 'SRG' / 'B' / '04C').write_bytes(
                    b'ED3BF384-7CE2-42B6-A000-591E6EB4DC86')
        fake = Fake(mac=True, on_remount=corrupt)
        self.assertEqual(self.run_main(fake, self.job, self.drive), 1)
        self.assertIn(str(Path('SORG') / 'SRG' / 'B' / '04C'), fake.text)
        self.assertIn('Do not use this diskette', fake.text)
        self.assertNotIn('OK:', fake.text)

    def test_mac_failed_final_check_is_refused(self):
        def fails_last(target, n, repair):
            if self.written(target) and not repair:
                raise diskette.Refused('the file system check of the diskette failed')
        fake = Fake(mac=True, on_remount=fails_last)
        self.assertEqual(self.run_main(fake, self.job, self.drive), 1)
        self.assertIn('check of the diskette failed', fake.text)
        self.assertNotIn('OK:', fake.text)

    def test_mac_erase_when_deleting_a_file_also_deletes_its_appledouble(self):
        # macOS removes ._X itself when X is deleted (seen 2026-11-20: ENOENT on ._B01C)
        (self.drive / 'SORG').mkdir()
        for name in ('B01C', '._B01C', '._SORG', 'SORG/INDICE.PRG', 'SORG/._INDICE.PRG'):
            (self.drive / name).write_bytes(b'x')
        real_unlink, real_rmdir = os.unlink, os.rmdir

        def and_appledouble(real):
            def gone(path, *, dir_fd=None):
                real(path, dir_fd=dir_fd)
                head, name = os.path.split(os.fspath(path))
                try:
                    real_unlink(os.path.join(head, '._' + name), dir_fd=dir_fd)
                except FileNotFoundError:
                    pass
            return gone
        real_scandir = os.scandir

        class FatOrder:                         # the diskette listed X before ._X
            def __init__(self, *a):
                with real_scandir(*a) as it:
                    self.entries = iter(sorted(it, key=lambda e: e.name.startswith('._')))

            def __iter__(self):
                return self

            def __next__(self):
                return next(self.entries)

            def close(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        fake = Fake(mac=True, answers=['YES'])
        with mock.patch('os.unlink', and_appledouble(real_unlink)), \
                mock.patch('os.rmdir', and_appledouble(real_rmdir)), \
                mock.patch('os.scandir', FatOrder):
            self.assertEqual(self.run_main(fake, self.job, self.drive), 0, fake.text)
        self.assertEqual({k: v for k, v in tree(self.drive).items() if k != self.NO_LOG},
                         self.src)

    def test_mac_folder_that_is_not_a_mount_is_not_remounted(self):
        fake = Fake(mac=True, mount=False)
        self.assertEqual(self.run_main(fake, self.job, self.drive), 0, fake.text)
        self.assertEqual(fake.remounts, [])
        self.assertEqual(tree(self.drive), self.src)

    def test_other_systems_are_not_remounted(self):
        fake = Fake(mac=False)
        self.assertEqual(self.run_main(fake, self.job, self.drive), 0, fake.text)
        self.assertEqual(fake.remounts, [])
        self.assertFalse((self.drive / '.fseventsd').exists())

    def test_mac_keep_leaves_other_files_but_still_refuses_appledouble(self):
        (self.drive / 'OLD').write_bytes(b'old')
        fake = Fake(mac=True)
        self.assertEqual(self.run_main(fake, self.job, self.drive, '--keep'), 0, fake.text)
        self.assertEqual((self.drive / 'OLD').read_bytes(), b'old')

        def appledouble(target, n, repair):
            if n == 3:                          # no_log is there: check, write, repair, check
                (target / '._LOAD.BAT').write_bytes(b'x')
        fake = Fake(mac=True, on_remount=appledouble, answers=['YES'])
        self.assertEqual(self.run_main(fake, self.job, self.drive, '--keep'), 1)
        self.assertIn('._LOAD.BAT', fake.text)


if __name__ == '__main__':
    unittest.main()
