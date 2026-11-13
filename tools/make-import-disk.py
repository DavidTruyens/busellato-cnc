#!/usr/bin/env python3
"""Build a diskette image in the format of CNC90 file management (BESTANDEN BEHEER), for Programma Kopie
from the floppy to the hard disk. The machine registers a program in C:\\CNC90\\MOD1\\SORG\\INDICE.PRG
only when it copies it in; programs copied with LOAD.BAT never appear in the compiler list.

  make-import-disk.py OUT.img PROGRAM_FILE...

Layout (as written by the machine itself, see disks/ notes in post/machine-tests/regen/README.md):
  SORG\\INDICE.PRG          one 82-byte record per program, sorted by name
  SORG\\SRG\\<first char>\\<rest of name>   the program source
No TAB, NOC or SPC files: those are compiler output. Needs mtools (mformat, mmd, mcopy).

INDICE.PRG record, 82 bytes: name (13) | comment (25) | date MM/DD/YY (8) | '*' | 6 zero | 'M' |
L, H, S as float32 (G71 X, Y, Z) | 14 bytes the machine fills with leftovers | CR LF.
"""
import datetime
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

TAIL = bytes.fromhex('009b97ff0100b0005300 00a0004e'.replace(' ', ''))


def record(name, comment, date, l, h, s):
    r = (name.ljust(13) + comment[:25].ljust(25) + date).encode('ascii')
    r += b'*' + bytes(6) + b'M' + struct.pack('<fff', l, h, s) + TAIL + b'\r\n'
    assert len(r) == 82, len(r)
    return r


def describe(path):
    lines = path.read_text(encoding='ascii').upper().splitlines()
    m = re.match(r'G71X([\d.]+)Y([\d.]+)Z([\d.]+)', lines[0])
    c = re.match(r'G150\((.*?)\)', lines[1])
    return (c.group(1) if c else ''), *(float(v) for v in m.groups())


def main(argv):
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(argv[1])
    programs = sorted((Path(p) for p in argv[2:]), key=lambda p: p.name.upper())
    date = datetime.date.today().strftime('%m/%d/%y')
    index = b''
    for p in programs:
        comment, l, h, s = describe(p)
        index += record(p.name.upper(), comment, date, l, h, s)
    out.unlink(missing_ok=True)
    run = lambda *a: subprocess.run(a, check=True)
    run('mformat', '-C', '-f', '1440', '-v', 'IMPORT', '-i', str(out), '::')
    run('mmd', '-i', str(out), '::SORG', '::SORG/SRG')
    with tempfile.TemporaryDirectory() as t:
        (Path(t) / 'INDICE.PRG').write_bytes(index)
        run('mcopy', '-i', str(out), str(Path(t) / 'INDICE.PRG'), '::SORG/INDICE.PRG')
    made = set()
    for p in programs:
        name = p.name.upper()
        if name[0] not in made:
            run('mmd', '-i', str(out), f'::SORG/SRG/{name[0]}')
            made.add(name[0])
        run('mcopy', '-i', str(out), str(p), f'::SORG/SRG/{name[0]}/{name[1:]}')
        print(f'{name:8} -> SORG\\SRG\\{name[0]}\\{name[1:]}', file=sys.stderr)
    print(f'wrote {out}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
