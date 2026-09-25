# Disk Capture (Part A, diskettes) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Mac-side tooling that turns a 3.5" 1.44 MB diskette into a byte-exact image, extracted files and an index row, then use it to capture the seven original diskettes D01–D07 into the repo.

**Architecture:** One small Python module (`tools/diskimg.py`, standard library only) holds the logic that can be unit-tested: checking and substituting the boot sector, parsing ddrescue maps, and finding the floppy in `diskutil` output. Two thin bash scripts build on it. `tools/extract-disk.sh` processes an image that already exists. `tools/image-disk.sh` reads a physical disk with `ddrescue` and then calls `extract-disk.sh`. Tests use `unittest` and build synthetic floppy images with `mtools`, so no hardware is needed.

**Tech Stack:** Python 3 (stdlib only), bash 3.2 (the macOS default), GNU ddrescue 1.30, mtools, macOS `diskutil`.

**Spec:** `docs/superpowers/specs/2026-09-25-disk-capture-design.md`

**Scope:** Steps 0 and 1 of the spec (tooling and the original diskettes), plus the README change from "Related changes". Spec steps 2–4 (hard-disk listing, copy plan, copy, `tools/verify-hdd.sh`) are left out on purpose and get their own plan once H01's `LISTING.TXT` exists. The verifier has to parse the Italian DOS 5 `DIR /S` output, and we shouldn't guess that format before seeing it.

**Deviations from the spec (small, for testability):**
- The `image-disk.sh` work is split into `image-disk.sh` (reading the disk) and `extract-disk.sh` (processing the image). D01 and D02 were already read by hand and only need processing.
- Each disk also gets `<ID>.dir.txt`, the `mdir` listing with the original DOS dates and times. Git doesn't store file modification times, so without it the dates would only survive inside the `.img`.

## Global Constraints

- The raw image `disks/<ID>/<ID>.img` is never modified after `ddrescue` writes it. Every fix-up happens on a temporary working copy, and that copy is never committed.
- Images are exactly 1,474,560 bytes (2880 × 512). Anything else is "unrecognised".
- Files are stored byte-exact. There is no character set conversion. `disks/.gitattributes` and `hdd/.gitattributes` contain `* -text`.
- Plain git, no Git LFS.
- Tools: Python 3 standard library only. Bash must run on macOS's bash 3.2, so it can't rely on empty arrays under `set -u` or on `mapfile`.
- Commit messages must not mention Claude, and must not include a Co-Authored-By line.
- Machine rules (never `FORMAT`, `DEL`, `CHKDSK /F`, `C:` as a destination, `SALVAINC.BAT`) don't affect this plan, because nothing here runs on the machine.

## Review Focus

1. **A disk with bad sectors.** Extraction should still run on what was read, the index row should show a non-zero bad-sector count, and the script should exit non-zero so nobody misses it. → Task 3, `test_bad_sectors_flagged`.
2. **The wrong device, or more than one candidate device, attached.** Floppy auto-detection must refuse rather than pick a disk. → Task 1, `test_find_floppy_rejects_two` / `test_find_floppy_rejects_none`.
3. **Re-running on a disk that was already extracted** (for example after a better re-read). `files/` must be replaced completely, with no leftover files from the earlier run. → Task 3, `test_rerun_replaces_files`.
4. **An image that isn't a FAT12 floppy at all** (random data, or a truncated read). Expect a clear error, exit code 2, and an existing `files/` left untouched. → Task 3, `test_unrecognised_image_leaves_files_alone`.
5. **Windows-created content**, such as `System Volume Information` with spaces in its name. It must be extracted, since it's part of what's on the disk, but not counted against the file count on the label. → Task 3, `test_windows_folder_extracted_not_counted`.

---

## File Structure

```
tools/
  diskimg.py          classify/substitute boot sector, map parsing, floppy detection (CLI + functions)
  extract-disk.sh     image -> files/, <ID>.dir.txt, index row
  image-disk.sh       physical disk -> <ID>.img/.map, then extract-disk.sh
tests/
  helpers.py          builds synthetic floppy images with mtools
  test_diskimg.py
  test_extract_disk.py
  test_image_disk.py
disks/
  .gitattributes
  README.md           index
  D01/ … D07/         <ID>.img, <ID>.map, <ID>.dir.txt, files/
hdd/
  .gitattributes
README.md             Google Drive -> Proton Drive; disks/ in layout
```

Run all tests with `python3 -m unittest discover -s tests -v` from the repo root.

---

### Task 1: `diskimg.py`: boot sector, map parsing, floppy detection

**Files:**
- Create: `tools/diskimg.py`
- Create: `tests/helpers.py`
- Create: `tests/test_diskimg.py`

**Interfaces:**
- Produces (Python): `classify(data: bytes) -> str` returns `"ok" | "substitute" | "unrecognised"`; `make_working(data: bytes) -> tuple[bytes, str]` returns `(image, "ok" | "substituted")` and raises `ValueError` if unrecognised; `bad_bytes(map_text: str) -> int`; `find_floppy(diskutil_text: str) -> str` returns `"/dev/diskN"` and raises `LookupError` unless exactly one match.
- Produces (CLI): `diskimg.py work IMG OUT` prints `ok` or `substituted`, exits 2 if unrecognised. `diskimg.py bad-bytes MAP` prints an integer. `diskimg.py find-floppy < diskutil-output` prints `/dev/diskN`, exits 2 on zero or several matches.
- Produces (tests): `helpers.make_floppy(path: str, files: dict[str, bytes], mtime: float | None = None) -> None`, `helpers.REPO`, `helpers.IMG_SIZE`.

- [ ] **Step 1: Write the test helper**

`tests/helpers.py`:

```python
"""Test helpers: build synthetic 1.44 MB floppy images with mtools."""
import os
import subprocess
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, 'tools')
IMG_SIZE = 1474560


def make_floppy(path, files, mtime=None):
    """Create a formatted 1.44 MB image at `path` containing `files`.

    `files` maps DOS paths like 'CNC90.BAT' or 'SUB DIR/X.TXT' to bytes.
    `mtime` (epoch seconds) is applied to every file if given.
    """
    subprocess.run(['mformat', '-i', path, '-C', '-f', '1440', '::'],
                   check=True, capture_output=True)
    made = set()
    with tempfile.TemporaryDirectory() as tmp:
        for name, data in files.items():
            parts = name.split('/')
            for i in range(1, len(parts)):
                d = '/'.join(parts[:i])
                if d not in made:
                    subprocess.run(['mmd', '-i', path, '::/' + d],
                                   check=True, capture_output=True)
                    made.add(d)
            src = os.path.join(tmp, 'f')
            with open(src, 'wb') as f:
                f.write(data)
            if mtime is not None:
                os.utime(src, (mtime, mtime))
            subprocess.run(['mcopy', '-m', '-i', path, src, '::/' + name],
                           check=True, capture_output=True)
            os.remove(src)
```

- [ ] **Step 2: Write the failing tests**

`tests/test_diskimg.py`:

```python
import os
import subprocess
import sys
import tempfile
import unittest

from helpers import IMG_SIZE, TOOLS, make_floppy

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
        return open(p, 'rb').read()


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
            open(p, 'wb').write(out)
            r = subprocess.run(['mtype', '-i', p, '::/CNC90.BAT'],
                               capture_output=True, check=True)
            self.assertEqual(r.stdout, b'@ECHO OFF\r\n')

    def test_unrecognised_raises(self):
        with self.assertRaises(ValueError):
            diskimg.make_working(os.urandom(IMG_SIZE))

    def test_real_d01_if_present(self):
        p = os.path.join(os.path.dirname(TOOLS), 'disks', 'D01', 'D01.img')
        if not os.path.exists(p):
            self.skipTest('D01.img not present')
        _, status = diskimg.make_working(open(p, 'rb').read())
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
            open(src, 'wb').write(os.urandom(IMG_SIZE))
            r = self.run_cli('work', src, os.path.join(tmp, 'o.img'))
            self.assertEqual(r.returncode, 2)
            self.assertFalse(os.path.exists(os.path.join(tmp, 'o.img')))

    def test_find_floppy_cli(self):
        r = self.run_cli('find-floppy', stdin=DISKUTIL_ONE)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, '/dev/disk4'))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 3: Run the tests and check that they fail**

Run: `python3 -m unittest discover -s tests -v`
Expected: `ModuleNotFoundError: No module named 'diskimg'`

- [ ] **Step 4: Implement `tools/diskimg.py`**

```python
#!/usr/bin/env python3
"""Helpers for imaging 3.5" 1.44 MB DOS diskettes.

See docs/superpowers/specs/2026-09-25-disk-capture-design.md.

  diskimg.py work IMG OUT        write a mtools-readable working copy of IMG
  diskimg.py bad-bytes MAP       bytes not rescued according to a ddrescue map
  diskimg.py find-floppy         read `diskutil list external physical` on stdin
"""
import re
import struct
import sys

SECTOR = 512
IMG_SIZE = 2880 * SECTOR
FAT_SECTORS = 9


def standard_boot_sector():
    """Boot sector of a standard DOS 1.44 MB floppy (no boot code)."""
    bs = bytearray(SECTOR)
    bs[0:3] = b'\xEB\x3C\x90'
    bs[3:11] = b'MSDOS5.0'
    # bytes/sector, sectors/cluster, reserved, FATs, root entries,
    # total sectors, media, sectors/FAT, sectors/track, heads, hidden, large total
    struct.pack_into('<HBHBHHBHHHII', bs, 11,
                     512, 1, 1, 2, 224, 2880, 0xF0, 9, 18, 2, 0, 0)
    bs[510:512] = b'\x55\xAA'
    return bytes(bs)


def _bpb_ok(sector0):
    if sector0[510:512] != b'\x55\xAA':
        return False
    bps, _spc, res, nfats, _roots, total, media, spf = struct.unpack_from(
        '<HBHBHHBH', sector0, 11)
    return (bps, res, nfats, total, media, spf) == (512, 1, 2, 2880, 0xF0, 9)


def classify(data):
    """'ok', 'substitute' (sector 0 overwritten, FATs intact) or 'unrecognised'."""
    if len(data) != IMG_SIZE:
        return 'unrecognised'
    if _bpb_ok(data[:SECTOR]):
        return 'ok'
    fat1 = data[SECTOR:SECTOR * (1 + FAT_SECTORS)]
    fat2 = data[SECTOR * (1 + FAT_SECTORS):SECTOR * (1 + 2 * FAT_SECTORS)]
    if fat1[:3] == b'\xF0\xFF\xFF' and fat1 == fat2:
        return 'substitute'
    return 'unrecognised'


def make_working(data):
    """Return (image, status). Never modifies `data`."""
    status = classify(data)
    if status == 'ok':
        return data, 'ok'
    if status == 'substitute':
        return standard_boot_sector() + data[SECTOR:], 'substituted'
    raise ValueError('not a recognisable 1.44 MB FAT12 image')


def bad_bytes(map_text):
    """Sum of block sizes in a ddrescue map whose status is not '+'."""
    lines = [l for l in map_text.splitlines() if l.strip() and not l.startswith('#')]
    total = 0
    for line in lines[1:]:  # lines[0] is the current_pos/status/pass line
        _pos, size, status = line.split()[:3]
        if status != '+':
            total += int(size, 16)
    return total


def find_floppy(diskutil_text):
    """/dev/diskN of the single external physical disk of 1.4-1.5 MB."""
    found = []
    for block in re.split(r'^(?=/dev/disk\d+ )', diskutil_text, flags=re.M):
        head = re.match(r'(/dev/disk\d+) \(external, physical\)', block)
        if not head:
            continue
        size = re.search(r'\*([\d.]+)\s*(KB|MB|GB|TB)', block)
        if size and size.group(2) == 'MB' and 1.4 <= float(size.group(1)) <= 1.5:
            found.append(head.group(1))
    if len(found) != 1:
        raise LookupError(f'expected exactly one 1.44 MB floppy, found {len(found)}: {found}')
    return found[0]


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ''
    if cmd == 'work' and len(argv) == 4:
        with open(argv[2], 'rb') as f:
            data = f.read()
        try:
            out, status = make_working(data)
        except ValueError as e:
            print(f'error: {argv[2]}: {e}', file=sys.stderr)
            return 2
        with open(argv[3], 'wb') as f:
            f.write(out)
        print(status)
        return 0
    if cmd == 'bad-bytes' and len(argv) == 3:
        with open(argv[2]) as f:
            print(bad_bytes(f.read()))
        return 0
    if cmd == 'find-floppy' and len(argv) == 2:
        try:
            print(find_floppy(sys.stdin.read()))
        except LookupError as e:
            print(f'error: {e}', file=sys.stderr)
            return 2
        return 0
    print(__doc__, file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
```

Then run `chmod +x tools/diskimg.py`.

- [ ] **Step 5: Run the tests and check that they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all tests in `test_diskimg.py` pass. `test_real_d01_if_present` also passes, because `disks/D01/D01.img` exists locally.

If `test_fresh_floppy_is_ok` fails, print the BPB that `mformat -f 1440` wrote (`xxd -s 11 -l 16 a.img`) and compare it with the tuple in `_bpb_ok`. Fix whichever one is wrong. The standard values are 512 bytes/sector, 1 reserved sector, 2 FATs, 2880 sectors, media `F0`, 9 sectors/FAT.

- [ ] **Step 6: Commit**

```bash
git add tools/diskimg.py tests/helpers.py tests/test_diskimg.py
git commit -m "Add diskimg.py: boot sector check/substitute, map parsing, floppy detection"
```

---

### Task 2: `.gitattributes` and index skeleton

**Files:**
- Create: `disks/.gitattributes`
- Create: `hdd/.gitattributes`
- Create: `disks/README.md`
- Create: `tests/test_repo_layout.py`

**Interfaces:**
- Produces: `disks/README.md` with an index table. Task 3 prints rows in exactly this column order: `| ID | Label | Imaged | SHA-256 | Bad sectors | Files expected / found | Boot sector | Contents |`.

- [ ] **Step 1: Write the failing test**

`tests/test_repo_layout.py`:

```python
import os
import subprocess
import unittest

from helpers import REPO

HEADER = '| ID | Label | Imaged | SHA-256 | Bad sectors | Files expected / found | Boot sector | Contents |'


class RepoLayoutTest(unittest.TestCase):
    def test_disk_files_are_binary_to_git(self):
        for d in ('disks', 'hdd'):
            r = subprocess.run(['git', 'check-attr', 'text', '--', f'{d}/X/files/CNC90.BAT'],
                               cwd=REPO, capture_output=True, text=True, check=True)
            self.assertIn('text: unset', r.stdout, d)

    def test_index_header(self):
        with open(os.path.join(REPO, 'disks', 'README.md')) as f:
            self.assertIn(HEADER, f.read())


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run the test and check that it fails**

Run: `python3 -m unittest tests.test_repo_layout -v` (from the repo root, with `PYTHONPATH=tests`)
Expected: FAIL, with `text: unspecified` and `FileNotFoundError` for `disks/README.md`.

- [ ] **Step 3: Create the files**

`disks/.gitattributes` and `hdd/.gitattributes`, both containing:

```
# Byte-exact DOS files: never convert line endings or treat as text.
* -text
```

`disks/README.md`:

```markdown
# Diskettes

Byte-exact captures of every diskette belonging to the Busellato S.EASY
control. `D` = original diskettes, `H` = diskettes written from the
control's hard disk (C:).

Each `<ID>/` holds:

- `<ID>.img` — raw sector image as read by ddrescue. Never modified.
- `<ID>.map` — ddrescue map: which sectors read and which failed.
- `<ID>.dir.txt` — directory listing with the original DOS dates
  (git does not keep file dates).
- `files/` — the files extracted from the image.

Made with `tools/image-disk.sh` (read a disk) or `tools/extract-disk.sh`
(process an existing image). See
`docs/superpowers/specs/2026-09-25-disk-capture-design.md`.

**Boot sector "substituted"** means sector 0 on the original diskette had
been overwritten (on D01/D02 by a hard-disk MBR, around January 2021),
so the files were extracted from a copy with a standard 1.44 MB boot
sector. The `.img` still holds exactly what is on the diskette.

## Index

| ID | Label | Imaged | SHA-256 | Bad sectors | Files expected / found | Boot sector | Contents |
|---|---|---|---|---|---|---|---|
```

- [ ] **Step 4: Run the test and check that it passes**

Run: `PYTHONPATH=tests python3 -m unittest tests.test_repo_layout -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add disks/.gitattributes hdd/.gitattributes disks/README.md tests/test_repo_layout.py
git commit -m "Add disks index and byte-exact gitattributes"
```

---

### Task 3: `extract-disk.sh`

**Files:**
- Create: `tools/extract-disk.sh`
- Create: `tests/test_extract_disk.py`

**Interfaces:**
- Consumes: `tools/diskimg.py work` and `bad-bytes` (Task 1). The index column order comes from Task 2.
- Produces: `tools/extract-disk.sh ID "label" EXPECTED`. It reads `$DISKS_DIR/<ID>/<ID>.img` (`DISKS_DIR` defaults to `<repo>/disks`) and the optional `<ID>.map`. It writes `<ID>/files/` and `<ID>/<ID>.dir.txt`, and prints one index row on stdout.
- Exit codes: 0 if clean and the count matches; 3 if the count doesn't match or there are bad sectors (the row is still printed and the files still extracted); 2 if the image is unrecognised (nothing written); 1 on usage errors or a missing image.

- [ ] **Step 1: Write the failing tests**

`tests/test_extract_disk.py`:

```python
import os
import shutil
import subprocess
import tempfile
import time
import unittest

from helpers import IMG_SIZE, TOOLS, make_floppy
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
        open(os.path.join(self.dir, 'D09.map'), 'w').write(MAP_CLEAN)
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.files(), ['CNC90.BAT', 'SUB/X.TXT'])
        with open(os.path.join(self.dir, 'files', 'CNC90.BAT'), 'rb') as f:
            self.assertEqual(f.read(), b'@ECHO OFF\r\n')  # CRLF kept
        row = r.stdout.strip()
        self.assertTrue(row.startswith('| D09 | TEST DISK | 2026-09-25 | `'), row)
        self.assertIn('| 0 | 2 / 2 | OK |', row)

    def test_dir_txt_keeps_dos_dates(self):
        make_floppy(self.img, {'CNC90.BAT': b'x'}, DATE_1992)
        self.run_script(expected='1')
        with open(os.path.join(self.dir, 'D09.dir.txt')) as f:
            listing = f.read()
        self.assertIn('CNC90', listing)
        self.assertIn('1992-09-09', listing)

    def test_substituted_boot_sector_leaves_img_untouched(self):
        make_floppy(self.img, {'A.TXT': b'a', 'B.TXT': b'b'})
        damaged = clobber_sector0(open(self.img, 'rb').read())
        open(self.img, 'wb').write(damaged)
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('| substituted |', r.stdout)
        self.assertEqual(open(self.img, 'rb').read(), damaged)
        self.assertEqual(self.files(), ['A.TXT', 'B.TXT'])

    def test_bad_sectors_flagged(self):
        make_floppy(self.img, {'A.TXT': b'a', 'B.TXT': b'b'})
        open(os.path.join(self.dir, 'D09.map'), 'w').write(MAP_BAD)
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
        open(self.img, 'wb').write(os.urandom(IMG_SIZE))
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
        os.remove(self.img) if os.path.exists(self.img) else None
        r = self.run_script()
        self.assertEqual(r.returncode, 1)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run the tests and check that they fail**

Run: `python3 -m unittest discover -s tests -p 'test_extract_disk.py' -v`
Expected: every test fails, because `tools/extract-disk.sh` doesn't exist (`FileNotFoundError` / `PermissionError`).

- [ ] **Step 3: Implement `tools/extract-disk.sh`**

```bash
#!/usr/bin/env bash
# Extract files from disks/<ID>/<ID>.img and print its index row.
#
#   tools/extract-disk.sh ID "label text" EXPECTED_FILE_COUNT
#
# Writes <ID>/files/ and <ID>/<ID>.dir.txt. Never modifies <ID>.img.
# Exit: 0 clean, 3 count mismatch or bad sectors, 2 unrecognised image,
# 1 usage/missing image. DISKS_DIR overrides <repo>/disks (tests).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(dirname "$here")"

if [[ $# -ne 3 ]]; then
  echo "usage: $0 ID \"label text\" EXPECTED_FILE_COUNT" >&2
  exit 1
fi
disk_id="$1"; label="$2"; expected="$3"
dir="${DISKS_DIR:-$repo/disks}/$disk_id"
img="$dir/$disk_id.img"
map="$dir/$disk_id.map"

if [[ ! -f "$img" ]]; then
  echo "error: $img not found" >&2
  exit 1
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
work="$tmp/work.img"

# Fails with exit 2 before anything in $dir is touched.
boot="$(python3 "$here/diskimg.py" work "$img" "$work")" || exit 2

rm -rf "$dir/files"
mkdir "$dir/files"
if [[ -n "$(mdir -i "$work" -b '::' 2>/dev/null || true)" ]]; then
  mcopy -i "$work" -s -m -n '::/*' "$dir/files/"
fi
mdir -i "$work" -/ -a '::' > "$dir/$disk_id.dir.txt" 2>&1 || true

found="$(find "$dir/files" -type f -not -path '*/System Volume Information/*' | wc -l | tr -d ' ')"

if [[ -f "$map" ]]; then
  bad_b="$(python3 "$here/diskimg.py" bad-bytes "$map")"
  bad=$(( (bad_b + 511) / 512 ))
  imaged="$(grep -m1 '^# Start time:' "$map" | awk '{print $4}' || true)"
else
  bad="no map"
  imaged=""
fi
[[ -n "$imaged" ]] || imaged="$(date +%Y-%m-%d)"

sha="$(shasum -a 256 "$img" | cut -d' ' -f1)"
[[ "$boot" == ok ]] && boot_col="OK" || boot_col="substituted"

status=0
count="$expected / $found"
if [[ "$found" != "$expected" ]]; then
  count="$count ⚠"
  status=3
fi
if [[ "$bad" != 0 && "$bad" != "no map" ]]; then
  status=3
fi

echo "| $disk_id | $label | $imaged | \`$sha\` | $bad | $count | $boot_col | |"
echo "$disk_id: $found files (expected $expected), bad sectors: $bad, boot sector: $boot_col" >&2
exit "$status"
```

Then run `chmod +x tools/extract-disk.sh`.

Note on `test_clean_disk_row_and_files`: the date comes from `MAP_CLEAN`'s `# Start time:` line (`2026-09-25`), not from today's date.

- [ ] **Step 4: Run the tests and check that they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: every test in `test_extract_disk.py` passes, and the earlier tests still pass.

If `test_windows_folder_extracted_not_counted` fails in the `mren` setup (mtools may refuse to rename a directory), change the setup to build the folder name directly: `make_floppy(self.img, {..., 'System Volume Information/INDEXE~1': b'guid'})`. `mmd` accepts long names. Keep the assertions as they are.

- [ ] **Step 5: Commit**

```bash
git add tools/extract-disk.sh tests/test_extract_disk.py
git commit -m "Add extract-disk.sh: files, DOS listing and index row from a disk image"
```

---

### Task 4: `image-disk.sh`

**Files:**
- Create: `tools/image-disk.sh`
- Create: `tests/test_image_disk.py`

**Interfaces:**
- Consumes: `diskimg.py find-floppy` (Task 1) and `extract-disk.sh` (Task 3).
- Produces: `tools/image-disk.sh ID "label" EXPECTED [SOURCE]`. Without `SOURCE`, it detects the single 1.44 MB USB floppy, unmounts it without ejecting, and reads `/dev/rdiskN` with sudo. If `SOURCE` is a regular file (as in the tests), it reads that file without sudo or diskutil. Its exit code is `extract-disk.sh`'s.

- [ ] **Step 1: Write the failing tests**

`tests/test_image_disk.py`:

```python
import os
import shutil
import subprocess
import tempfile
import unittest

from helpers import TOOLS, make_floppy

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
        self.assertEqual(open(os.path.join(d, 'D09.img'), 'rb').read(),
                         open(self.src, 'rb').read())
        self.assertIn('# Mapfile', open(os.path.join(d, 'D09.map')).read())
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
```

- [ ] **Step 2: Run the tests and check that they fail**

Run: `python3 -m unittest discover -s tests -p 'test_image_disk.py' -v`
Expected: all 3 tests fail, because the script doesn't exist.

- [ ] **Step 3: Implement `tools/image-disk.sh`**

```bash
#!/usr/bin/env bash
# Read one diskette into disks/<ID>/ with ddrescue, then extract it.
#
#   tools/image-disk.sh ID "label text" EXPECTED_FILE_COUNT [SOURCE]
#
# Lock the diskette's write-protect tab first. If macOS says the disk is
# not readable, click "Ignore" (never "Initialize").
# SOURCE defaults to the single attached 1.44 MB USB floppy (needs sudo).
# A regular file may be given instead; then no sudo or diskutil is used.
# Re-running resumes from the existing map; good sectors are not re-read.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(dirname "$here")"

if [[ $# -lt 3 || $# -gt 4 ]]; then
  echo "usage: $0 ID \"label text\" EXPECTED_FILE_COUNT [SOURCE]" >&2
  exit 1
fi
disk_id="$1"; label="$2"; expected="$3"; src="${4:-}"
dir="${DISKS_DIR:-$repo/disks}/$disk_id"
mkdir -p "$dir"
img="$dir/$disk_id.img"
map="$dir/$disk_id.map"

if [[ -z "$src" ]]; then
  disk="$(diskutil list external physical | python3 "$here/diskimg.py" find-floppy)"
  echo "Using $disk" >&2
  diskutil unmountDisk "$disk" >/dev/null
  src="/dev/r${disk#/dev/}"
fi

run() {
  if [[ -f "$src" ]]; then "$@"; else sudo "$@"; fi
}

# Pass 1: everything, no retries. Pass 2: retry bad sectors up to 3 times.
run ddrescue -n -b 512 "$src" "$img" "$map"
run ddrescue -r3 -b 512 "$src" "$img" "$map"
if [[ ! -f "$src" ]]; then
  sudo chown "$(id -u):$(id -g)" "$img" "$map"
fi

exec "$here/extract-disk.sh" "$disk_id" "$label" "$expected"
```

Then run `chmod +x tools/image-disk.sh`.

- [ ] **Step 4: Run the tests and check that they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all tests pass (Tasks 1–4).

- [ ] **Step 5: Commit**

```bash
git add tools/image-disk.sh tests/test_image_disk.py
git commit -m "Add image-disk.sh: read a diskette with ddrescue, then extract"
```

---

### Task 5: Capture D01–D07

This task needs David for the physical disks. D01 and D02 are already imaged (`disks/D01/`, `disks/D02/`). D03–D07 are either imaged by David in the meantime with the raw `ddrescue` command, or read now with `tools/image-disk.sh`.

**Files:**
- Create: `disks/D01/` … `disks/D07/` (`.img`, `.map`, `.dir.txt`, `files/`)
- Create: `disks/2026-09-25_diskettes-set-of-7.jpg` (copied from `~/Documents/cnc-images/disks/`)
- Modify: `disks/README.md` (index rows)

**Disk table** (labels as read from the photo; David confirms D05's top line with the disk in hand):

| ID | Label | Expected |
|---|---|---|
| D01 | CNC 90 — 1 | 28 |
| D02 | CNC 90 — 2 | 11 |
| D03 | CNC 90 — 3 | 7 |
| D04 | PTPSYS | 4 |
| D05 | PTP0 / CASCHR 20772 (?) | 39 |
| D06 | PTP1000 | 40 |
| D07 | LINGUE — 1/1 | 75 |

- [ ] **Step 1: Check which disks are imaged**

Run: `ls -l disks/D0*/D0*.img`
For each ID in the table without an `.img` file, ask David to lock the write-protect tab, insert the disk, and run:
`tools/image-disk.sh <ID> "<Label>" <Expected>`
(It prompts for his sudo password. It can't run unattended.)

- [ ] **Step 2: Process every disk**

```bash
for args in 'D01|CNC 90 — 1|28' 'D02|CNC 90 — 2|11' 'D03|CNC 90 — 3|7' \
            'D04|PTPSYS|4' 'D05|PTP0|39' 'D06|PTP1000|40' 'D07|LINGUE — 1/1|75'; do
  IFS='|' read -r i l n <<< "$args"
  [[ -f "disks/$i/$i.img" ]] && tools/extract-disk.sh "$i" "$l" "$n"
done
```

Expected: seven rows on stdout. For D01, the row should read `28 / 28 | substituted` with SHA-256 `cda6c8700a378ad253cabdfbe41b313cf79421ab70392317904f628ca9341812`. For D02, `11 / 11 | substituted` with SHA-256 `01ba94adcabedbb9ed200a1d1dfd17e86e9f308ad593c2eb296a8fbd2d87d9a7`.
Any row with `⚠` or a non-zero bad-sector count: **stop and report it to David**. Don't retry in a loop. D01's map says `Start time` 2026-09-25, and so does D02's.

- [ ] **Step 3: Fill in the index**

Paste the seven rows into `disks/README.md` under the table header. For each, fill the Contents cell with one line based on `disks/<ID>/<ID>.dir.txt`. For example, D01: "CNC90 root: startup BAT files, SALVAINA/SALVAINC save/restore scripts, editors, compiler". Replace D05's label with David's confirmed reading.

Add under the table:

```markdown
Photo of the set: `2026-09-25_diskettes-set-of-7.jpg`.
```

Copy the photo: `cp ~/Documents/cnc-images/disks/2026-09-25_diskettes-set-of-7.jpg disks/`

- [ ] **Step 4: Verify**

Run: `python3 -m unittest discover -s tests -v` (all pass), then
`git status --short disks | head`, and check that no `work.img` or temporary files are staged.
Run: `git check-attr text -- disks/D01/files/CNC90.BAT` → `text: unset`.

- [ ] **Step 5: Commit**

```bash
git add disks/
git commit -m "Capture original diskettes D01-D07"
```

---

### Task 6: README update

**Files:**
- Modify: `README.md` ("Where things live" and "Layout" sections)

- [ ] **Step 1: Replace the Google Drive bullet**

In `README.md`, replace:

```markdown
- **Google Drive** — photos, video, scanned schematics, vendor PDFs.
  <https://drive.google.com/drive/folders/13UeDKkH23NIK_m7m3_Y3FiJwd0A7dI5h>
```

with:

```markdown
- **Proton Drive** — photos, video, scanned schematics, vendor PDFs.
```

- [ ] **Step 2: Add disks, hdd and tools to the layout block**

In the ```` ``` ```` layout block, after the `programs/` line, add:

```
disks/            byte-exact diskette images + extracted files (index in disks/README.md)
hdd/              files copied from the control's hard disk C:
tools/            imaging scripts (image-disk.sh, extract-disk.sh)
```

- [ ] **Step 3: Verify**

Run: `grep -n "Google" README.md` → no output. `grep -n "disks/" README.md` → one match.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "README: Proton Drive for media, document disks/ hdd/ tools/"
```
