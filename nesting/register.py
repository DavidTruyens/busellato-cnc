"""Register a job's programs in the machine's program list from DOS, without Programma Kopie.

CNC90 lists only the programs in C:\\CNC90\\MOD1\\SORG\\INDICE.PRG: 82-byte records (see
importdisk.record), sorted on the 13-byte name field, no header, no trailer (2,860 records on
the H05 backup). Copying a program file into SRG does not register it.

LOAD.BAT makes the machine list only the job: it copies the programs into SRG, keeps the full
list once as INDICE.ALL (never overwritten) and the list in use as INDICE.<job>, then puts the
diskette's own job index (SORG\\INDICE.PRG, the one Programma Kopie reads) in place. FULLIDX.BAT
puts the full list back. GETIDX.BAT copies the machine's list to the diskette (REG\\NOW.PRG); the
diskette tool keeps it in the project as a backup of the full list.

The machine runs MS-DOS 5 (Italian). Its FC sets no error level (seen 2026-11-20), so nothing
here compares files: a copy goes to a name that was deleted first and is checked to exist,
COPY /V verifies the writing, the new list is copied beside the old one and only renamed into
place once it is there, and no message text of a DOS command is relied on.
"""
from __future__ import annotations

from .importdisk import RECORD

C_SORG = r'C:\CNC90\MOD1\SORG'
C_INDEX = C_SORG + r'\INDICE.PRG'
C_NEW = C_SORG + r'\INDICE.NEW'
C_ALL = C_SORG + r'\INDICE.ALL'     # the full list, kept once, never overwritten
C_CUR = C_SORG + r'\INDICE.CUR'
NAME_FIELD = 13


def records(data: bytes, what: str = 'index') -> list[bytes]:
    """The records of an INDICE.PRG, checked: whole records ending in CR LF, sorted on the
    name field, no name twice. ValueError otherwise."""
    if not data:
        raise ValueError(f'{what} is empty')
    if len(data) % RECORD:
        raise ValueError(f'{what}: {len(data)} bytes is not a whole number of '
                         f'{RECORD}-byte records')
    recs = [data[i:i + RECORD] for i in range(0, len(data), RECORD)]
    for n, r in enumerate(recs, 1):
        if r[-2:] != b'\r\n':
            raise ValueError(f'{what}: record {n} does not end in CR LF')
    names = [r[:NAME_FIELD] for r in recs]
    for n, (a, b) in enumerate(zip(names, names[1:]), 2):
        if a >= b:
            raise ValueError(f'{what}: record {n} ({b.decode("ascii", "replace").strip()}) '
                             f'is not after {a.decode("ascii", "replace").strip()}: '
                             'not sorted or a name twice')
    return recs


def _copy(src: str, dst: str, bad: str) -> list[str]:
    """Copy src to dst, deleted first, so that dst existing afterwards means it was written."""
    return [f'IF EXIST {dst} DEL {dst}', f'COPY /V {src} {dst} > NUL',
            f'IF NOT EXIST {dst} GOTO {bad}']


def _swap_in(src: str, restore: str) -> list[str]:
    """Put src in place of the program list: beside it first, then rename; restore from
    `restore` if the list is gone afterwards."""
    return [*_copy(src, C_NEW, 'NONEW'),
            f'DEL {C_INDEX}',
            f'REN {C_NEW} INDICE.PRG',
            f'IF NOT EXIST {C_INDEX} GOTO RESTORE']


def _bat(lines: list[str]) -> str:
    return '\r\n'.join(lines) + '\r\n'


def load_bat(programs: list[str], job: int | None) -> str:
    """LOAD.BAT for the job's programs (names as on the machine, e.g. B00101C)."""
    bak = C_SORG + (rf'\INDICE.{job:03d}' if job else r'\INDICE.BAK')
    L = ['@ECHO OFF',
         'REM Copies this job\'s programs and makes CNC90 list only them. Run at the DOS',
         'REM prompt (exit CNC90 first). The full list is kept once as INDICE.ALL;',
         'REM A:FULLIDX puts it back. The list in use is kept under the job number.',
         r'IF NOT EXIST A:\SORG\INDICE.PRG GOTO NOJOB',
         f'IF NOT EXIST {C_INDEX} GOTO NOIDX']
    for f in sorted({n[0] for n in programs}):
        L.append(rf'IF NOT EXIST {C_SORG}\SRG\{f}\NUL GOTO NODIR')
    L += [f'ECHO {len(programs)} PROGRAMS WILL BE COPIED AND REGISTERED.',
          'ECHO CNC90 WILL THEN LIST ONLY THIS JOB. A:FULLIDX PUTS THE FULL LIST BACK.',
          'ECHO CTRL+C TO STOP, ANY OTHER KEY TO GO ON.',
          'PAUSE > NUL']
    for n in programs:
        L += [*_copy(rf'A:\SORG\SRG\{n[0]}\{n[1:]}', rf'{C_SORG}\SRG\{n[0]}\{n[1:]}', 'BADCOPY'),
              f'ECHO {n} COPIED']
    L += [f'IF EXIST {C_ALL} GOTO HAVEALL',
          *_copy(C_INDEX, C_ALL, 'NOBAK'),
          f'ECHO THE FULL PROGRAM LIST IS KEPT AS {C_ALL}',
          ':HAVEALL',
          *_copy(C_INDEX, bak, 'NOBAK'),
          *_swap_in(r'A:\SORG\INDICE.PRG', bak),
          'ECHO.',
          f'ECHO DONE: {len(programs)} PROGRAMS REGISTERED. START CNC90 (TYPE EXIT).',
          f'ECHO THE LIST THAT WAS IN USE IS KEPT AS {bak}',
          'GOTO END',
          ':RESTORE',
          f'COPY /V {bak} {C_INDEX} > NUL',
          'ECHO THE NEW LIST COULD NOT BE PUT IN PLACE; THE OLD LIST IS BACK.',
          'ECHO LOAD THE JOB WITH PROGRAMMA KOPIE.',
          'GOTO END',
          ':NONEW',
          'ECHO THE NEW LIST COULD NOT BE COPIED. THE PROGRAM LIST WAS NOT CHANGED.',
          'ECHO LOAD THE JOB WITH PROGRAMMA KOPIE.',
          'GOTO END',
          ':NOJOB',
          r'ECHO NO A:\SORG\INDICE.PRG ON THIS DISKETTE. NOTHING CHANGED.',
          'GOTO END',
          ':NOIDX',
          f'ECHO {C_INDEX} NOT FOUND. NOTHING CHANGED.',
          'GOTO END',
          ':NODIR',
          f'ECHO A PROGRAM FOLDER IS MISSING UNDER {C_SORG}\\SRG. NOTHING CHANGED.',
          'GOTO END',
          ':BADCOPY',
          'ECHO A PROGRAM DID NOT COPY. THE PROGRAM LIST WAS NOT CHANGED.',
          'ECHO LOAD THE JOB WITH PROGRAMMA KOPIE.',
          'GOTO END',
          ':NOBAK',
          'ECHO THE BACKUP OF THE PROGRAM LIST FAILED. THE LIST WAS NOT CHANGED.',
          ':END']
    return _bat(L)


def fullidx_bat() -> str:
    """FULLIDX.BAT: put back the full program list LOAD.BAT kept as INDICE.ALL; the list in
    use is kept as INDICE.CUR first."""
    return _bat([
        '@ECHO OFF',
        'REM Puts back the full program list (all old programs) that A:LOAD kept the first',
        'REM time. Run at the DOS prompt (exit CNC90 first). The list in use is kept as',
        f'REM {C_CUR}. Programs registered since then must be loaded again.',
        f'IF NOT EXIST {C_ALL} GOTO NOALL',
        'ECHO THE FULL PROGRAM LIST WILL BE PUT BACK. CTRL+C TO STOP, ANY OTHER KEY TO GO ON.',
        'PAUSE > NUL',
        *_copy(C_INDEX, C_CUR, 'NOCUR'),
        *_swap_in(C_ALL, C_CUR),
        'ECHO DONE: THE FULL PROGRAM LIST IS BACK.',
        f'ECHO THE LIST THAT WAS IN USE IS KEPT AS {C_CUR}',
        'GOTO END',
        ':RESTORE',
        f'COPY /V {C_CUR} {C_INDEX} > NUL',
        'ECHO THE FULL LIST COULD NOT BE PUT IN PLACE; THE LIST IN USE IS BACK.',
        'GOTO END',
        ':NONEW',
        'ECHO THE FULL LIST COULD NOT BE COPIED. NOTHING CHANGED.',
        'GOTO END',
        ':NOCUR',
        'ECHO COULD NOT KEEP THE LIST IN USE. NOTHING CHANGED.',
        'GOTO END',
        ':NOALL',
        f'ECHO {C_ALL} NOT FOUND: A:LOAD HAS NOT REPLACED THE LIST YET. NOTHING CHANGED.',
        ':END'])


def getidx_bat() -> str:
    """GETIDX.BAT: copy the machine's program list to the diskette (REG\\NOW.PRG); the
    diskette tool keeps it on the Mac as a backup."""
    return _bat([
        '@ECHO OFF',
        'REM Copies the machine\'s program list to the diskette (A:\\REG\\NOW.PRG); the Mac',
        'REM keeps it as a backup. Changes nothing on the machine.',
        f'IF NOT EXIST {C_INDEX} GOTO NOIDX',
        r'IF NOT EXIST A:\REG\NUL MD A:\REG',
        *_copy(C_INDEX, r'A:\REG\NOW.PRG', 'BAD'),
        'ECHO PROGRAM LIST COPIED TO THE DISKETTE.',
        'GOTO END',
        ':BAD',
        'ECHO THE PROGRAM LIST COULD NOT BE COPIED. TRY AGAIN OR USE ANOTHER DISKETTE.',
        'GOTO END',
        ':NOIDX',
        f'ECHO {C_INDEX} NOT FOUND.',
        ':END'])
