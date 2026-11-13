#!/usr/bin/env python3
"""Compare the compiler's output for the ZZR* test programs with the machine's own earlier output.

  compare-compiled.py OUT_DIR

OUT_DIR is a copy of the diskette's \\OUT folder (made by COLLECT.BAT): TAB\\Z, NOC\\Z, SPC\\Z and INDICE.PRG.
Each ZZRn is an unchanged copy of a real program whose TAB / COMP\\NOC / COMP\\SPC files are in
disks/H02. If the compiler is deterministic, the outputs match except for fields that hold the
program name or the compile date. Prints, per file, whether it is identical or where it differs.
Exit 0 if every pair was found, 1 if something is missing. Differences are information, not failure.
"""
import sys
from pathlib import Path

repo = Path(__file__).resolve().parent.parent
h02 = repo / 'disks' / 'H02' / 'files'
# program name -> (file name on the machine, original it is a copy of); ZZR1 is SRG\Z\ZR1
PAIRS = {'ZZR1': ('ZR1', 'EL1'), 'ZZR2': ('ZR2', 'BJOLAN2'), 'ZZR3': ('ZR3', 'WEVER1'), 'ZZR4': ('ZR4', 'EL')}
FORMS = {'TAB': h02 / 'TAB' / 'Z', 'NOC': h02 / 'COMP' / 'NOC' / 'Z', 'SPC': h02 / 'COMP' / 'SPC' / 'Z'}


def ranges(offsets):
    out = []
    for o in offsets:
        if out and o == out[-1][1] + 1:
            out[-1][1] = o
        else:
            out.append([o, o])
    return out


def find(folder, name):
    for p in folder.iterdir():
        if p.name.upper() == name:
            return p
    return None


def compare(new, old):
    a, b = new.read_bytes(), old.read_bytes()
    if a == b:
        return 'IDENTICAL', []
    if len(a) != len(b):
        return f'DIFFERENT SIZE: new {len(a)} bytes, original {len(b)} bytes', []
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    return f'{len(diff)} of {len(a)} bytes differ', ranges(diff)


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(argv[1])
    missing = 0
    for zzr, (fname, orig) in PAIRS.items():
        print(f'{zzr}  (SRG\\Z\\{fname}, copy of Z\\{orig})')
        for form, folder in FORMS.items():
            sub = out / form / 'Z'
            new = find(sub, fname) if sub.is_dir() else None
            old = find(folder, orig)
            if new is None or old is None:
                print(f'  {form}: MISSING ({"new" if new is None else "original"})')
                missing += 1
                continue
            verdict, spans = compare(new, old)
            print(f'  {form}: {verdict}')
            for s, e in spans[:12]:
                a, b = new.read_bytes()[s:e + 1], old.read_bytes()[s:e + 1]
                print(f'      offset {s}-{e}: new {a[:16].hex()}  original {b[:16].hex()}')
    return 1 if missing else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
