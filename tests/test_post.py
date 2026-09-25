"""Post-processor tests. Mode A: CLI post engine on post/tests/cases/*.cnc
(captured by post/tests/fusion_capture.py:capture_cnc(), with <case>.json sidecars).
Mode B: reads post/tests/out/ written by post/tests/fusion_capture.py:post_all()."""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

from helpers import REPO, TOOLS

sys.path.insert(0, TOOLS)
import check_cnc90  # noqa: E402

POST_BIN = glob.glob(os.path.expanduser(
    '~/Library/Application Support/Autodesk/webdeploy/production/*/Autodesk Fusion.app/'
    'Contents/Libraries/Applications/CAM360/post'))
CPS = os.path.join(REPO, 'post', 'busellato-cnc90.cps')
CASES_DIR = os.path.join(REPO, 'post', 'tests', 'cases')
OUT_DIR = os.path.join(REPO, 'post', 'tests', 'out')
with open(os.path.join(REPO, 'post', 'tests', 'cases.json')) as fh:
    CASES = json.load(fh)
MODE = 'A' if glob.glob(os.path.join(CASES_DIR, '*.cnc')) else 'B'


def run_case(key, spec):
    """Return (ok, text, log) for one case key."""
    case = spec.get('case', key)
    if MODE == 'A':
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, case)
            log = os.path.join(tmp, 'post.log')
            cmd = [POST_BIN[0], '--noeditor', '--nobackup', '--log', log]
            # Fusion passes programName and unit to the post; they are not in the .cnc,
            # so capture_cnc() stored them in <case>.json. Property values are JS-evaluated.
            with open(os.path.join(CASES_DIR, case + '.json')) as fh:
                fusion = json.load(fh)
            props = {'programName': fusion['programName'], 'unit': fusion['unit']}
            props.update(spec.get('props', {}))
            for k, v in props.items():
                cmd += ['--property', k, json.dumps(v)]
            cmd += [CPS, os.path.join(CASES_DIR, case + '.cnc'), out]
            r = subprocess.run(cmd, capture_output=True, text=True)
            produced = [f for f in os.listdir(tmp) if f.startswith(case) and not f.endswith('.log')]
            text = open(os.path.join(tmp, produced[0]), 'rb').read() if produced else b''
            logtext = (open(log).read() if os.path.exists(log) else '') + r.stdout + r.stderr
            return r.returncode == 0 and bool(produced), text, logtext
    with open(os.path.join(OUT_DIR, key + '.status')) as fh:
        ok = fh.read().strip() == 'ok'
    with open(os.path.join(OUT_DIR, key + '.nc'), 'rb') as fh:
        return ok, fh.read(), ''


def lines_of(text):
    return text.decode('ascii').split('\r\n')[:-1]


class PostCaseTest(unittest.TestCase):
    def check_assertion(self, key, a, text, name):
        lines = lines_of(text)
        kind, _, arg = a.partition(' ')
        if kind == 'checker':
            self.assertEqual(check_cnc90.check(text, name), [], key)
        elif kind == 'crlf':
            self.assertTrue(text.endswith(b'\r\n') and b'\n' not in text.replace(b'\r\n', b''), key)
        elif kind in ('line1', 'line2', 'last'):
            line = {'line1': lines[0], 'line2': lines[1], 'last': lines[-1]}[kind]
            self.assertRegex(line, arg, key)
        elif kind in ('has', 'none'):
            hits = [l for l in lines if re.search(arg, l)]
            self.assertTrue(bool(hits) if kind == 'has' else not hits, f'{key}: {a}\n' + '\n'.join(lines))
        elif kind in ('count', 'atleast'):
            n, _, rx = arg.partition(' ')
            hits = len([l for l in lines if re.search(rx, l)])
            if kind == 'count':
                self.assertEqual(hits, int(n), f'{key}: {a}\n' + '\n'.join(lines))
            else:
                self.assertGreaterEqual(hits, int(n), f'{key}: {a}\n' + '\n'.join(lines))
        elif kind == 'xy':
            x, y = arg.split(',')
            self.assertTrue(any(re.search(rf'X{x}Y{y}(Z|U|$)', l) for l in lines if re.match('G(88|1|2|3)', l)),
                            f'{key}: no move ends at X{x}Y{y}\n' + '\n'.join(lines))
        else:
            self.fail(f'unknown assertion {a!r}')

    def test_cases(self):
        if MODE == 'A' and not POST_BIN:
            self.skipTest('Fusion post engine not found')
        if MODE == 'B' and not os.path.isdir(OUT_DIR):
            self.skipTest('no captured cases and no Fusion outputs')
        for key, spec in CASES.items():
            with self.subTest(case=key):
                ok, text, log = run_case(key, spec)
                self.assertEqual(ok, spec['ok'], f'{key}: ok={ok}\n{log[-2000:]}')
                if not spec['ok'] and MODE == 'A':
                    self.assertIn(spec['error'].lower(), log.lower(), f'{key}: {log[-2000:]}')
                for a in spec['assert']:
                    self.check_assertion(key, a, text, spec.get('case', key))

    def test_circpock_ramp_depth(self):
        """CIRCPOCK's profile ramp follows a full circle, so (unlike RAMP's rectangle) almost
        the whole descent is arcs. Guards against the depth being silently dropped on a
        Z-changing arc written flat (no Z word) instead of interpolated lines: depth must
        creep down in small steps and actually reach the full 10mm, not jump or stall."""
        if MODE == 'A' and not POST_BIN:
            self.skipTest('Fusion post engine not found')
        if MODE == 'B' and not os.path.isdir(OUT_DIR):
            self.skipTest('no captured cases and no Fusion outputs')
        ok, text, log = run_case('CIRCPOCK', CASES['CIRCPOCK'])
        self.assertTrue(ok, f'CIRCPOCK: ok=False\n{log[-2000:]}')
        lines = lines_of(text)
        depths = [float(re.search(r'Z(-?[\d.]+)$', l).group(1)) for l in lines if l.startswith('G1G90')]
        self.assertTrue(depths, 'CIRCPOCK: no G1 lines found')
        for prev, cur in zip(depths, depths[1:]):
            self.assertLessEqual(abs(cur - prev), 0.05,
                                  f'CIRCPOCK: depth step from {prev} to {cur} exceeds 0.05mm')
        self.assertEqual(max(depths), 10, f'CIRCPOCK: maximum depth reached is {max(depths)}, expected 10')


if __name__ == '__main__':
    unittest.main()
