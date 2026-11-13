"""Copy a job's DISKETTE folder onto a diskette and check it by reading it back.

  python -m nesting.diskette [OUT_FOLDER] [DRIVE] [--keep] [--force-size]

OUT_FOLDER is a job folder (PROJECT/out/<stamp>), its DISKETTE folder, or a project folder (then
its newest job is used). Default: the newest job of ~/nesting-project (%USERPROFILE% on Windows).
DRIVE is the diskette drive, like A: (Windows); without it the removable drives are listed and
asked for. On macOS / Linux DRIVE is the mounted diskette's folder (or any empty folder, for a
test).

Safety, in this order:
  - Windows: only a removable drive (GetDriveTypeW == DRIVE_REMOVABLE). Elsewhere: an existing
    folder that is not the job, not the repo, and does not contain either.
  - a drive (or mount point) larger than 1.5 MB is refused, so a USB stick or a hard disk is never
    wiped by mistake, unless --force-size is given.
  - the diskette is dedicated to the programs: anything on it is erased, after typing YES.
    --keep erases nothing and only adds or overwrites our files (also after YES when it overwrites
    something: SORG\\INDICE.PRG then replaces the index on the diskette).
  - every file is read back and compared after writing.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import string
import sys
from pathlib import Path

from .importdisk import NAME, size_warning

REPO = Path(__file__).resolve().parent.parent
DRIVE_REMOVABLE = 2
MAX_DISK = 1_600_000          # a 1.44 MB diskette is 1,474,560 bytes
SKIP = {'system volume information', '$recycle.bin'}    # Windows may put these on any drive
STAMP = re.compile(r'(\d{8}-\d{6})(?:-(\d+))?$')


class Refused(Exception):
    """A plain message for the user; nothing (more) is written."""


def default_project() -> Path:
    return Path.home() / 'nesting-project'


# --- the system, injectable for tests -----------------------------------------------------------
def windows_drive_type(root: str) -> int:
    import ctypes
    return ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root))


def windows_removable_drives() -> list[str]:
    import ctypes
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    return [f'{c}:' for i, c in enumerate(string.ascii_uppercase)
            if mask >> i & 1 and windows_drive_type(f'{c}:\\') == DRIVE_REMOVABLE]


def disk_total(path: Path) -> int:
    return shutil.disk_usage(path).total


class System:
    """What the copy needs from the computer. Tests replace the parts they fake."""

    def __init__(self, windows: bool | None = None, drive_type=None, removable_drives=None,
                 total=None, is_mount=None, ask=None, say=None):
        self.windows = os.name == 'nt' if windows is None else windows
        self.drive_type = drive_type or windows_drive_type
        self.removable_drives = removable_drives or windows_removable_drives
        self.total = total or disk_total
        self.is_mount = is_mount or os.path.ismount
        self.ask = ask or input
        self.say = say or print


# --- what to copy -------------------------------------------------------------------------------
def newest_job(project: Path) -> Path:
    out = Path(project) / 'out'
    jobs = []
    if out.is_dir():
        for p in out.iterdir():
            m = STAMP.match(p.name)
            if m and p.is_dir():
                jobs.append((m.group(1), int(m.group(2) or 1), p))
    if not jobs:
        raise Refused(f'No generated job in {out}. Generate the programs first.')
    return max(jobs)[2]


def source_folder(arg: str | None) -> Path:
    """The DISKETTE folder to copy, from a job folder, a DISKETTE folder or a project folder."""
    p = Path(arg) if arg else default_project()
    if not p.is_dir():
        raise Refused(f'{p} is not a folder.')
    if p.name.upper() == NAME and (p / 'SORG').is_dir():
        return p
    if not (p / NAME).is_dir() and (p / 'out').is_dir():
        p = newest_job(p)
    if not (p / NAME).is_dir():
        raise Refused(f'{p} has no {NAME} folder (made before this version?). Generate again.')
    return p / NAME


def files_in(folder: Path) -> list[Path]:
    """Relative paths of the files under `folder`, skipping Windows' own system folders."""
    out = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if d.lower() not in SKIP)
        for f in sorted(filenames):
            out.append((Path(dirpath) / f).relative_to(folder))
    return out


# --- where to copy it ---------------------------------------------------------------------------
def _inside(a: Path, b: Path) -> bool:
    """True when a is b or lies inside b."""
    try:
        a.relative_to(b)
        return True
    except ValueError:
        return False


def target_folder(drive: str, job: Path, system: System, force_size: bool) -> Path:
    if system.windows:
        m = re.fullmatch(r'([A-Za-z]):?\\?', drive.strip())
        if not m:
            raise Refused(f'{drive!r} is not a drive letter; give it like A:')
        root = f'{m.group(1).upper()}:\\'
        kind = system.drive_type(root)
        if kind != DRIVE_REMOVABLE:
            raise Refused(f'{root} is not a removable drive (type {kind}): refused. Give the '
                          'diskette drive, usually A:.')
        target, looks_like_disk = Path(root), True
    else:
        target = Path(drive).expanduser()
        if not target.is_dir():
            raise Refused(f'{target} is not an existing folder. Give the mounted diskette, '
                          'for example /Volumes/UNTITLED.')
        target = target.resolve()
        looks_like_disk = system.is_mount(target)
    for other, what in ((job.resolve(), 'the job folder'), (REPO, 'the repo folder')):
        if _inside(target, other) or _inside(other, target):
            raise Refused(f'{target} is, holds or lies inside {what}: refused.')
    if looks_like_disk:
        try:
            total = system.total(target)
        except OSError as e:
            raise Refused(f'Cannot read {target} ({e}). Is a diskette in the drive?')
        if total > MAX_DISK and not force_size:
            raise Refused(f'{target} holds {total / 1e6:.1f} MB: that is not a 1.44 MB diskette, '
                          'refused (a USB stick or disk is never erased). Use --force-size only '
                          'if you are sure.')
    return target


def pick_drive(system: System) -> str:
    if not system.windows:
        raise Refused('Give the target folder (the mounted diskette), for example '
                      'python3 -m nesting.diskette JOB /Volumes/UNTITLED')
    drives = system.removable_drives()
    system.say('Removable drives: ' + (', '.join(drives) if drives else 'none found'))
    answer = system.ask('Drive letter of the diskette (for example A), Enter to stop: ').strip()
    if not answer:
        raise Refused('No drive given: nothing written.')
    return answer


# --- the copy -----------------------------------------------------------------------------------
def erase(target: Path) -> None:
    for p in target.iterdir():
        if p.name.lower() in SKIP:
            continue
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
        else:
            p.unlink()


def write_and_verify(src: Path, target: Path, files: list[Path]) -> None:
    for rel in files:
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = (src / rel).read_bytes()
        with open(dest, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    bad = [str(rel) for rel in files if (target / rel).read_bytes() != (src / rel).read_bytes()]
    if bad:
        raise Refused('Read back differs for: ' + ', '.join(bad) + '. Do not use this diskette.')


def run(args, system: System) -> int:
    src = source_folder(args.out_folder)
    job = src.parent
    files = files_in(src)
    size = sum((src / f).stat().st_size for f in files)
    system.say(f'Job:        {job}')
    system.say(f'To write:   {len(files)} files, {size} bytes (from {src})')
    warn = size_warning(src)
    if warn:
        system.say('WARNING: ' + warn)
    target = target_folder(args.drive or pick_drive(system), job, system, args.force_size)
    there = files_in(target)
    system.say(f'On {target} now: {len(there)} files')
    if args.keep:
        clash = sorted(set(map(str, there)) & set(map(str, files)))
        system.say('--keep: nothing is erased; our files are added or overwritten. '
                   'SORG\\INDICE.PRG replaces the index that is on the diskette now.')
        if clash and system.ask(f'{len(clash)} files on it will be overwritten. '
                                'Type YES to continue: ').strip() != 'YES':
            raise Refused('Not confirmed: nothing written.')
    elif any(p.name.lower() not in SKIP for p in target.iterdir()):
        if system.ask(f'Everything on {target} will be ERASED. Type YES to continue: '
                      ).strip() != 'YES':
            raise Refused('Not confirmed: nothing erased or written.')
        erase(target)
    write_and_verify(src, target, files)
    system.say(f'OK: {len(files)} files written to {target} and read back identical.')
    system.say('Eject the diskette safely before you take it out (Windows: in Explorer, '
               'right-click the drive, Eject; then wait until the drive light is off).')
    return 0


def main(argv: list[str] | None = None, system: System | None = None) -> int:
    ap = argparse.ArgumentParser(prog='python -m nesting.diskette',
                                 description='Copy a job\'s DISKETTE folder onto a diskette.')
    ap.add_argument('out_folder', nargs='?',
                    help='job folder, its DISKETTE folder, or project folder (newest job); '
                         'default: the newest job of ~/nesting-project')
    ap.add_argument('drive', nargs='?', help='diskette drive like A: (asked if left out)')
    ap.add_argument('--keep', action='store_true',
                    help='do not erase the diskette, only add or overwrite our files')
    ap.add_argument('--force-size', action='store_true',
                    help='allow a target larger than a diskette (not for normal use)')
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    system = system or System()
    try:
        return run(args, system)
    except Refused as e:
        system.say('STOPPED: ' + str(e))
        return 1
    except OSError as e:
        system.say(f'ERROR: {e}. The diskette may be incomplete: do not use it; '
                   'run this again (a new diskette if it keeps failing).')
        return 1
    except (KeyboardInterrupt, EOFError):
        system.say('\nStopped.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
