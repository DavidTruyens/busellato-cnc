"""The DISKETTE folder of a job: exactly what goes on the 1.44 MB diskette for the CNC90.

  DISKETTE\\LOAD.BAT, L1.BAT, COLLECT.BAT, C1.BAT   the loader (tools/make-loader.py)
  DISKETTE\\B01D, B01C, ...                          the programs, flat (what LOAD.BAT copies)
  DISKETTE\\SORG\\INDICE.PRG                         the import index, one 82-byte record per program
  DISKETTE\\SORG\\SRG\\<first char>\\<rest of name>  the programs where the machine keeps them

The SORG tree is the format CNC90 file management (BESTANDEN BEHEER) itself writes on a diskette,
for Programma Kopie from the floppy to the hard disk: the machine registers a program in
C:\\CNC90\\MOD1\\SORG\\INDICE.PRG only when it copies it in that way. Same logic as the
make-import-disk.py tool (record(), describe()), in pure Python, so no mtools are needed.

INDICE.PRG record, 82 bytes: name (13) | comment (25) | date MM/DD/YY (8) | '*' | 6 zero | 'M' |
L, H, S as float32 (G71 X, Y, Z) | 14 bytes the machine fills with leftovers | CR LF.
"""
from __future__ import annotations

import datetime
import re
import shutil
import struct
from pathlib import Path

NAME = 'DISKETTE'
LOADER_FILES = ('LOAD.BAT', 'L1.BAT', 'COLLECT.BAT', 'C1.BAT')
TAIL = bytes.fromhex('009b97ff0100b000530000a0004e')
RECORD = 82

# 1.44 MB FAT12: 2847 data clusters of 512 bytes, 224 entries in the root directory
CLUSTER = 512
CLUSTERS = 2847
ROOT_ENTRIES = 224
SPARE = 0.9          # warn above 90 % of the data area


def record(name: str, comment: str, date: str, l: float, h: float, s: float) -> bytes:
    r = (name.ljust(13) + comment[:25].ljust(25) + date).encode('ascii')
    r += b'*' + bytes(6) + b'M' + struct.pack('<fff', l, h, s) + TAIL + b'\r\n'
    if len(r) != RECORD:
        raise ValueError(f'{name}: INDICE.PRG record is {len(r)} bytes, not {RECORD}')
    return r


def describe(text: str) -> tuple[str, float, float, float]:
    """(G150 comment, G71 X, Y, Z) of a program source."""
    lines = text.upper().splitlines()
    m = re.match(r'G71X([\d.]+)Y([\d.]+)Z([\d.]+)', lines[0] if lines else '')
    if not m:
        raise ValueError('program does not start with a G71X..Y..Z.. header')
    c = re.match(r'G150\((.*?)\)', lines[1]) if len(lines) > 1 else None
    return (c.group(1) if c else ''), *(float(v) for v in m.groups())


def index(programs: dict[str, bytes], date: str) -> bytes:
    """INDICE.PRG for `programs` (name -> source bytes), records sorted by name."""
    out = b''
    for name in sorted(programs, key=str.upper):
        comment, l, h, s = describe(programs[name].decode('ascii'))
        out += record(name.upper(), comment, date, l, h, s)
    return out


def write_diskette(dest: Path, job: Path, programs: list[str],
                   today: datetime.date | None = None) -> Path:
    """Build `dest` (must not exist) from the loader files and flat programs in `job`."""
    date = (today or datetime.date.today()).strftime('%m/%d/%y')
    dest = Path(dest)
    dest.mkdir()
    srcs = {}
    for name in programs:
        srcs[name.upper()] = (Path(job) / name.upper()).read_bytes()
    for f in LOADER_FILES:
        shutil.copyfile(Path(job) / f, dest / f)
    for name, data in srcs.items():
        (dest / name).write_bytes(data)
    sorg = dest / 'SORG'
    (sorg / 'SRG').mkdir(parents=True)
    (sorg / 'INDICE.PRG').write_bytes(index(srcs, date))
    for name, data in sorted(srcs.items()):
        folder = sorg / 'SRG' / name[0]
        folder.mkdir(exist_ok=True)
        (folder / name[1:]).write_bytes(data)
    return dest


def usage(folder: Path) -> tuple[int, int]:
    """(clusters the folder's files and subfolders take on a 1.44 MB FAT12 disk,
    entries in its root directory)."""
    folder = Path(folder)
    clusters = 0
    for p in folder.rglob('*'):
        if p.is_dir():
            # a subfolder is one cluster per 16 entries (32 bytes each), . and .. included
            clusters += max(1, -(-(len(list(p.iterdir())) + 2) // 16))
        else:
            clusters += -(-p.stat().st_size // CLUSTER)
    return clusters, len(list(folder.iterdir()))


def size_warning(folder: Path) -> str | None:
    """A message when the folder would not fit a 1.44 MB diskette with room to spare."""
    clusters, root = usage(folder)
    kb = clusters * CLUSTER // 1024
    if root > ROOT_ENTRIES:
        return (f'{Path(folder).name} has {root} files in its top folder; a 1.44 MB diskette takes '
                f'at most {ROOT_ENTRIES}. Generate fewer blanks per job.')
    if clusters > CLUSTERS * SPARE:
        full = 'does not fit' if clusters > CLUSTERS else 'nearly fills'
        return (f'{Path(folder).name} takes about {kb} KB on disk and {full} a 1.44 MB diskette '
                f'({CLUSTERS * CLUSTER // 1024} KB). Generate fewer blanks per job.')
    return None
