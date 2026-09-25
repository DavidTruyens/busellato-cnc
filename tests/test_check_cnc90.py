import os
import subprocess
import sys
import tempfile
import unittest

from helpers import REPO, TOOLS, write_bytes

sys.path.insert(0, TOOLS)
import check_cnc90  # noqa: E402

SAMPLES = os.path.join(REPO, 'disks', 'H02', 'files', 'SRG')

GOOD = (b'G71X400Y300Z18T00N7L4\r\n'
        b'G150(TEST PIECE)\r\n'
        b'G88G90G54P5T0165S18000F1X29Y29Z19\r\n'
        b'G1G90F3X171Y29Z19\r\n'
        b'G3G90G17X171Y111U41\r\n'
        b'G1G90X29Y111Z19\r\n'
        b'M2\r\n')


def replace_line(data, index, new):
    lines = data.split(b'\r\n')
    lines[index] = new
    return b'\r\n'.join(lines)


class SampleTest(unittest.TestCase):
    def test_all_real_programs_pass_in_sample_mode(self):
        if not os.path.isdir(SAMPLES):
            self.skipTest('H02 samples not present')
        count = 0
        for d in sorted(os.listdir(SAMPLES)):
            for f in sorted(os.listdir(os.path.join(SAMPLES, d))):
                with open(os.path.join(SAMPLES, d, f), 'rb') as fh:
                    self.assertEqual(check_cnc90.check(fh.read(), f, samples=True), [], f'{d}/{f}')
                count += 1
        self.assertEqual(count, 118)

    def test_sample_codes_rejected_in_post_mode(self):
        with open(os.path.join(SAMPLES, 'Z', '003'), 'rb') as fh:
            problems = check_cnc90.check(fh.read(), 'Z003')
        self.assertTrue(any('G184' in p for p in problems), problems)


class PostModeTest(unittest.TestCase):
    def test_good_program_passes(self):
        self.assertEqual(check_cnc90.check(GOOD, 'ZZT1'), [])

    def test_wrong_n(self):
        bad = replace_line(GOOD, 0, b'G71X400Y300Z18T00N8L4')
        self.assertTrue(any('N8' in p for p in check_cnc90.check(bad, 'ZZT1')))

    def test_wrong_l(self):
        bad = replace_line(GOOD, 0, b'G71X400Y300Z18T00N7L5')
        self.assertTrue(any('L5' in p for p in check_cnc90.check(bad, 'ZZT1')))

    def test_bare_lf_and_missing_final_crlf(self):
        problems = check_cnc90.check(GOOD.replace(b'\r\n', b'\n'), 'ZZT1')
        self.assertTrue(any('LF' in p or 'CRLF' in p for p in problems), problems)

    def test_non_ascii(self):
        self.assertEqual(check_cnc90.check(GOOD.replace(b'TEST', b'T\xc9ST'), 'ZZT1'), ['not plain ASCII'])

    def test_too_deep(self):
        bad = GOOD.replace(b'Z19', b'Z23.5')
        self.assertTrue(any('deeper' in p for p in check_cnc90.check(bad, 'ZZT1')))

    def test_compensation_code_is_malformed(self):
        bad = replace_line(GOOD, 2, b'G88G90G54P5T0165S18000F1G41X29Y29Z19')
        self.assertTrue(any('malformed G88' in p for p in check_cnc90.check(bad, 'ZZT1')))

    def test_bad_names(self):
        for name in ('TOOLONGNAME', 'zzt1', 'ZZ T1', ''):
            self.assertTrue(any('name' in p for p in check_cnc90.check(GOOD, name)), name)

    def test_missing_m2(self):
        bad = replace_line(GOOD, 6, b'M30')
        self.assertTrue(any('M2' in p for p in check_cnc90.check(bad, 'ZZT1')))

    def test_long_comment(self):
        bad = replace_line(GOOD, 1, b'G150(' + b'X' * 31 + b')')
        self.assertTrue(any('G150' in p for p in check_cnc90.check(bad, 'ZZT1')))


class CliTest(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, os.path.join(TOOLS, 'check_cnc90.py'), *args],
                              capture_output=True, text=True)

    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, 'ZZT1.txt')
            write_bytes(good, GOOD)
            bad = os.path.join(tmp, 'ZZT2')
            write_bytes(bad, GOOD.replace(b'N7', b'N9'))
            self.assertEqual(self.run_cli(good).returncode, 0)
            self.assertEqual(self.run_cli(good, bad).returncode, 1)
            self.assertEqual(self.run_cli().returncode, 2)


if __name__ == '__main__':
    unittest.main()
