#!/usr/bin/env python3
"""Read the spindle correction table of the CNC90 control: where each tool sits on the head.

  spindle_offsets.py [PARTEC1.PAR]

Default file: the H03 backup, disks/H03/files/CNC90/MOD1/USER/PARTEC1.PAR (last changed 2003).
Its fields are defined in DEFTEC1.PAR, next to it:

  "Correttore mandrino X #80#Qf#10#..."   80 floats   spindle correction X
  "Correttore mandrino Y #80#Qf#10#..."   80 floats   spindle correction Y
  "Correttore mandrino Z #80#Qf#10#..."   80 floats   spindle correction Z
  "Offset (X,Y)          #2#Qf#10#..."     2 floats
  "Offset pressori       #5#Qf#10#..."     5 floats
  "Quote antiscontro     #2#Qf#10#..."     2 floats

The file is one header byte and then those fields as little-endian 32-bit floats, in that order
(1 + 4 x (80 + 80 + 80 + 2 + 5 + 2) = 997 bytes). Entry i of each spindle array is tool T(i+1).
X and Y are mm from T1 (T1 is 0, 0). Z is read as the tool's length correction; that reading of
the field name is not checked on the machine, nor is which way +X and +Y point on the machine.

Prints one line per tool that has a non-zero entry: tool, X, Y, Z.
"""
import struct
import sys
from pathlib import Path

DEFAULT = (Path(__file__).resolve().parent.parent / 'disks' / 'H03' / 'files' / 'CNC90' / 'MOD1'
           / 'USER' / 'PARTEC1.PAR')
SPINDLES = 80
SIZE = 1 + 4 * (3 * SPINDLES + 2 + 5 + 2)


def read(path=DEFAULT) -> dict:
    """{tool number: (x, y, z)} for every tool with a non-zero entry; 'offset': (x, y)."""
    data = Path(path).read_bytes()
    if len(data) != SIZE:
        raise ValueError(f'{path}: {len(data)} bytes, expected {SIZE} for a PARTEC1.PAR')

    def floats(start, n):
        return struct.unpack(f'<{n}f', data[start:start + 4 * n])

    xs = floats(1, SPINDLES)
    ys = floats(1 + 4 * SPINDLES, SPINDLES)
    zs = floats(1 + 8 * SPINDLES, SPINDLES)
    out = {i + 1: (round(xs[i], 3), round(ys[i], 3), round(zs[i], 3))
           for i in range(SPINDLES) if xs[i] or ys[i] or zs[i]}
    out['offset'] = tuple(round(v, 3) for v in floats(1 + 12 * SPINDLES, 2))
    return out


def main(argv):
    table = read(argv[1] if len(argv) > 1 else DEFAULT)
    offset = table.pop('offset')
    print('tool        X         Y        Z')
    for tool, (x, y, z) in table.items():
        print(f'T{tool:<3d} {x:9.2f} {y:9.2f} {z:8.2f}')
    print(f'offset (X,Y): {offset[0]:g}, {offset[1]:g}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
