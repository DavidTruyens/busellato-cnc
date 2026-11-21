"""Registering a job's programs from DOS (nesting/register.py). The machine's MS-DOS 5 FC sets
no error level (2026-11-20), so the batch files check copies by existence only."""
import unittest
from pathlib import Path

from nesting import register
from nesting.importdisk import RECORD, record

repo = Path(__file__).resolve().parent.parent
MACHINE = repo / 'disks' / 'H05' / 'files' / 'CNC90' / 'MOD1' / 'SORG' / 'INDICE.PRG'
IDX = r'C:\CNC90\MOD1\SORG\INDICE.PRG'
NEW = r'C:\CNC90\MOD1\SORG\INDICE.NEW'
ALL = r'C:\CNC90\MOD1\SORG\INDICE.ALL'
CUR = r'C:\CNC90\MOD1\SORG\INDICE.CUR'
PROGS = ['B00301D', 'B00301C', 'B00302D', 'B00302C']


def rec(name, l=100.0):
    return record(name, '', '11/20/26', l, 50.0, 36.0)


def lines(test, text):
    test.assertTrue(text.endswith('\r\n'))
    out = text.split('\r\n')[:-1]
    for x in out:
        test.assertLessEqual(len(x), 127, x)        # DOS batch line limit
        x.encode('ascii')
    labels = {x[1:] for x in out if x.startswith(':')}
    gotos = {x.split('GOTO ')[1] for x in out if 'GOTO ' in x}
    test.assertLessEqual(gotos, labels)
    test.assertFalse([x for x in out if x.startswith('FC ') or 'ERRORLEVEL' in x])
    # DOS 5 redirects even in a REM line: INDICE.<job> gave "File non trovato" (2026-11-20)
    test.assertFalse([x for x in out if x.startswith('REM') and set(x) & set('<>|')])
    return out


class RecordsTests(unittest.TestCase):
    def test_the_machine_backup_index_is_accepted(self):
        if not MACHINE.exists():
            self.skipTest('no machine backup')
        self.assertEqual(len(register.records(MACHINE.read_bytes())), 2860)

    def test_refuses_what_it_does_not_understand(self):
        good = rec('A1') + rec('B1')
        for bad in (b'', good[:-1], rec('B1') + rec('A1'), rec('A1') + rec('A1'),
                    good[:RECORD - 2] + b'XX'):
            with self.subTest(bad=bad[:20]), self.assertRaises(ValueError):
                register.records(bad)


class LoadTests(unittest.TestCase):
    def setUp(self):
        self.L = lines(self, register.load_bat(PROGS, 3))

    def test_nothing_is_touched_before_the_key(self):
        pause = self.L.index('PAUSE > NUL')
        before = self.L[:pause]
        self.assertFalse([x for x in before if x.startswith(('COPY', 'DEL', 'REN'))])
        self.assertIn(r'IF NOT EXIST C:\CNC90\MOD1\SORG\SRG\B\NUL GOTO NODIR', before)
        self.assertIn(r'IF NOT EXIST A:\SORG\INDICE.PRG GOTO NOJOB', before)

    def test_every_program_is_copied_to_a_deleted_name_and_checked(self):
        for n in PROGS:
            src, dst = rf'A:\SORG\SRG\B\{n[1:]}', rf'C:\CNC90\MOD1\SORG\SRG\B\{n[1:]}'
            i = self.L.index(f'COPY /V {src} {dst} > NUL')
            self.assertEqual(self.L[i - 1], f'IF EXIST {dst} DEL {dst}')
            self.assertEqual(self.L[i + 1], f'IF NOT EXIST {dst} GOTO BADCOPY')

    def test_full_list_once_then_backup_then_the_job_list_via_a_rename(self):
        L = self.L
        bak = r'C:\CNC90\MOD1\SORG\INDICE.003'
        last_prog = max(i for i, x in enumerate(L) if x.startswith(r'COPY /V A:\SORG\SRG'))
        skip = L.index(f'IF EXIST {ALL} GOTO HAVEALL')
        keep_all = L.index(f'COPY /V {IDX} {ALL} > NUL')
        keep_bak = L.index(f'COPY /V {IDX} {bak} > NUL')
        copy_new = L.index(rf'COPY /V A:\SORG\INDICE.PRG {NEW} > NUL')
        delete = L.index(f'DEL {IDX}')
        rename = L.index(f'REN {NEW} INDICE.PRG')
        self.assertLess(last_prog, skip)
        self.assertEqual(L[skip + 1:skip + 4], [f'IF EXIST {ALL} DEL {ALL}',
                                                f'COPY /V {IDX} {ALL} > NUL',
                                                f'IF NOT EXIST {ALL} GOTO NOBAK'])
        self.assertLess(keep_all, L.index(':HAVEALL'))
        self.assertLess(L.index(':HAVEALL'), keep_bak)
        self.assertEqual(L[keep_bak + 1], f'IF NOT EXIST {bak} GOTO NOBAK')
        # the old list is deleted only once the new one is beside it
        self.assertLess(keep_bak, copy_new)
        self.assertEqual(L[copy_new + 1], f'IF NOT EXIST {NEW} GOTO NONEW')
        self.assertLess(copy_new, delete)
        self.assertEqual(rename, delete + 1)
        self.assertEqual(L[rename + 1], f'IF NOT EXIST {IDX} GOTO RESTORE')
        r = L.index(':RESTORE')
        self.assertEqual(L[r + 1], f'COPY /V {bak} {IDX} > NUL')
        # INDICE.ALL is written in one place only, and only when it is not there
        self.assertEqual([x for x in L if x.startswith('COPY') and x.split()[-3] == ALL],
                         [f'COPY /V {IDX} {ALL} > NUL'])


class FullIdxTests(unittest.TestCase):
    def test_keeps_the_list_in_use_then_puts_the_full_list_back(self):
        L = lines(self, register.fullidx_bat())
        self.assertIn(f'IF NOT EXIST {ALL} GOTO NOALL', L)
        pause = L.index('PAUSE > NUL')
        cur = L.index(f'COPY /V {IDX} {CUR} > NUL')
        new = L.index(f'COPY /V {ALL} {NEW} > NUL')
        self.assertLess(pause, cur)
        self.assertLess(cur, new)
        self.assertEqual(L[cur + 1], f'IF NOT EXIST {CUR} GOTO NOCUR')
        self.assertEqual(L[new + 1:new + 5], [f'IF NOT EXIST {NEW} GOTO NONEW', f'DEL {IDX}',
                                              f'REN {NEW} INDICE.PRG',
                                              f'IF NOT EXIST {IDX} GOTO RESTORE'])
        self.assertEqual(L[L.index(':RESTORE') + 1], f'COPY /V {CUR} {IDX} > NUL')
        self.assertFalse([x for x in L if x.startswith(('DEL', 'IF EXIST')) and ALL in x])

class GetIdxTests(unittest.TestCase):
    def test_only_writes_to_the_diskette(self):
        L = lines(self, register.getidx_bat())
        targets = [x.split()[-1] for x in L if x.startswith(('DEL', 'REN', 'MD'))]
        targets += [x.split()[-3] for x in L if x.startswith('COPY')]
        targets += [x.split()[-1] for x in L if x.startswith('IF ') and ' DEL ' in x]
        targets += [x.split()[-1] for x in L if x.startswith('IF ') and ' MD ' in x]
        self.assertTrue(targets)
        self.assertFalse([d for d in targets if not d.startswith('A:')], targets)
        self.assertIn(rf'COPY /V {IDX} A:\REG\NOW.PRG > NUL', L)

if __name__ == '__main__':
    unittest.main()
