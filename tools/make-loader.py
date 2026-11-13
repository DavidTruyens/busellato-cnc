#!/usr/bin/env python3
"""Build a diskette folder that loads programs into the TPA CNC90 and collects the compiler output.

  make-loader.py OUT_DIR PROGRAM_FILE...

Each PROGRAM_FILE is a program source named like the program (Fusion post output, e.g. ZZT1A). On the
machine the FIRST character of the program name is the folder under C:\\CNC90\\MOD1\\SORG\\SRG and the
REST is the file name (index entry ZEL1 = SRG\\Z\\EL1, 9JACOBS05 = SRG\\9\\JACOBS05). The programs are
copied into OUT_DIR together with:

  LOAD.BAT     copies every program to its folder; never overwrites; says what it did   (+ L1.BAT)
  COLLECT.BAT  after compiling in CNC90: copies the generated TAB / NOC / SPC files and
               INDICE.PRG to A:\\OUT\\                                                    (+ C1.BAT)

Copy OUT_DIR's contents to the root of the diskette. Names must be 2-8 characters of A-Z 0-9 _ - and
start with a letter (not Q or U) or with 7 or 9: those are the folders that exist on the machine.
"""
import re
import shutil
import sys
from pathlib import Path

SRG = r'C:\CNC90\MOD1\SORG\SRG'
FOLDERS = set('79ABCDEFGHIJKLMNOPRSTVWXYZ')
NAME = re.compile(r'[A-Z0-9_-]{2,8}$')


def split(name):
    if not NAME.match(name):
        raise ValueError(f'{name}: name must be 2-8 characters of A-Z 0-9 _ -')
    if name[0] not in FOLDERS:
        raise ValueError(f'{name}: no SRG folder "{name[0]}" on the machine (folders: 7, 9, A-P, R-Z)')
    return name[0], name[1:]


def write(path, lines):
    path.write_bytes(('\r\n'.join(lines) + '\r\n').upper().encode('ascii'))


def main(argv):
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(argv[1])
    programs = [Path(p) for p in argv[2:]]
    pairs = []
    for p in programs:
        try:
            pairs.append((p, *split(p.name.upper())))
        except ValueError as e:
            print('error:', e, file=sys.stderr)
            return 1
    if len({(f, r) for _, f, r in pairs}) != len(pairs):
        print('error: two programs map to the same file', file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)
    for p, folder, rest in pairs:
        shutil.copyfile(p, out / p.name.upper())

    write(out / 'LOAD.BAT', [
        '@ECHO OFF',
        f'REM Copies the programs on this diskette into {SRG}, folder = first letter, file = rest of name.',
        'REM Writes only NEW files: an existing program is never overwritten.',
        f'ECHO {len(pairs)} programs to SRG folders (first letter = folder). Ctrl+C to stop, any other key to copy.',
        'PAUSE > NUL',
        *[f'CALL A:\\L1.BAT {f} {r} {p.name.upper()}' for p, f, r in pairs],
        'ECHO.',
        'ECHO Done. Start CNC90 and compile the programs.',
    ])
    write(out / 'L1.BAT', [
        '@ECHO OFF',
        'REM %1 = SRG folder, %2 = file name on the machine, %3 = file on this diskette',
        f'IF NOT EXIST {SRG}\\%1\\NUL GOTO NODIR',
        f'IF EXIST {SRG}\\%1\\%2 GOTO TAKEN',
        f'COPY A:\\%3 {SRG}\\%1\\%2 > NUL',
        'ECHO %3 copied to SRG\\%1\\%2',
        'GOTO END',
        ':TAKEN',
        'ECHO %3: SRG\\%1\\%2 ALREADY EXISTS - not copied',
        'GOTO END',
        ':NODIR',
        'ECHO %3: no folder SRG\\%1 - not copied',
        ':END',
    ])
    write(out / 'COLLECT.BAT', [
        '@ECHO OFF',
        'REM After compiling: copies the generated TAB, NOC and SPC files and INDICE.PRG to A:\\OUT. Reads C:, writes A: only.',
        'ECHO Collecting compiler output to A:\\OUT. Any key to continue.',
        'PAUSE > NUL',
        *[f'CALL A:\\C1.BAT {f} {r}' for _, f, r in pairs],
        'XCOPY C:\\CNC90\\MOD1\\SORG\\INDICE.PRG A:\\OUT\\',
        'ECHO.',
        'DIR A:\\OUT /S',
    ])
    write(out / 'C1.BAT', [
        '@ECHO OFF',
        'REM %1 = SRG folder, %2 = file name',
        'IF NOT EXIST C:\\CNC90\\MOD1\\SORG\\TAB\\%1\\%2 ECHO %1\\%2: no TAB file (not compiled?)',
        'IF EXIST C:\\CNC90\\MOD1\\SORG\\TAB\\%1\\%2 XCOPY C:\\CNC90\\MOD1\\SORG\\TAB\\%1\\%2 A:\\OUT\\TAB\\%1\\',
        'IF EXIST C:\\CNC90\\MOD1\\COMP\\NOC\\%1\\%2 XCOPY C:\\CNC90\\MOD1\\COMP\\NOC\\%1\\%2 A:\\OUT\\NOC\\%1\\',
        'IF EXIST C:\\CNC90\\MOD1\\COMP\\SPC\\%1\\%2 XCOPY C:\\CNC90\\MOD1\\COMP\\SPC\\%1\\%2 A:\\OUT\\SPC\\%1\\',
    ])
    for p, f, r in pairs:
        print(f'{p.name.upper():8} -> SRG\\{f}\\{r}', file=sys.stderr)
    print(f'wrote {out}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
