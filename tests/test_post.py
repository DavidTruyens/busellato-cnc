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


@unittest.skipIf(MODE == 'A' and not POST_BIN,
                 "needs Autodesk's post engine (Fusion installed on a Mac); not available on CI")
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

    def test_allowed_tools_parsing(self):
        for key in ('RECT.tools', 'DRILL.tools'):
            ok, _, log = run_case(key, CASES[key])
            self.assertEqual(ok, CASES[key]['ok'], f'{key}\n{log[-1500:]}')

    def test_circpock_ramp_depth(self):
        """CIRCPOCK's profile ramp follows a full circle, so (unlike RAMP's rectangle) almost
        the whole descent is arcs. Guards against the depth being silently dropped on a
        Z-changing arc written flat (no Z word) instead of interpolated lines: while ramping
        (from the G88 to the first time full depth is reached), depth must never go back up,
        and must actually pass through intermediate depths on the way -- not jump straight
        from the G88's depth to 10. Later G1 lines (moving to another pocket-clearing loop)
        are free to retreat; only the ramp itself is checked. Max depth is exactly 10."""
        if MODE == 'A' and not POST_BIN:
            self.skipTest('Fusion post engine not found')
        if MODE == 'B' and not os.path.isdir(OUT_DIR):
            self.skipTest('no captured cases and no Fusion outputs')
        ok, text, log = run_case('CIRCPOCK', CASES['CIRCPOCK'])
        self.assertTrue(ok, f'CIRCPOCK: ok=False\n{log[-2000:]}')
        lines = lines_of(text)
        g88_depth = float(re.search(r'Z(-?[\d.]+)$', next(l for l in lines if l.startswith('G88'))).group(1))
        depths = [float(re.search(r'Z(-?[\d.]+)$', l).group(1)) for l in lines if l.startswith('G1G90')]
        self.assertTrue(depths, 'CIRCPOCK: no G1 lines found')
        first_full = next((i for i, d in enumerate(depths) if d >= 10 - 1e-6), None)
        self.assertIsNotNone(first_full, 'CIRCPOCK: no G1 line reaches full depth (10)')
        ramp = depths[:first_full + 1]
        for prev, cur in zip(ramp, ramp[1:]):
            self.assertGreaterEqual(cur - prev, -0.001,
                                     f'CIRCPOCK: depth went back up from {prev} to {cur} while ramping')
        self.assertTrue(any(g88_depth < d < 10 for d in ramp),
                         f'CIRCPOCK: no intermediate depth between the G88 depth ({g88_depth}) and 10 '
                         'while ramping -- the ramp does not appear to descend gradually')
        self.assertEqual(max(depths), 10, f'CIRCPOCK: maximum depth reached is {max(depths)}, expected 10')


    def test_mirror_swaps_arcs(self):
        ok1, plain, _ = run_case('LSHAPE', CASES['LSHAPE'])
        ok2, mirrored, _ = run_case('LSHAPE.mirror', CASES['LSHAPE.mirror'])
        self.assertTrue(ok1 and ok2)
        a, b = lines_of(plain), lines_of(mirrored)
        self.assertEqual(len(a), len(b))
        for la, lb in zip(a[2:-1], b[2:-1]):
            ya, yb = float(re.search(r'Y(-?[\d.]+)', la).group(1)), float(re.search(r'Y(-?[\d.]+)', lb).group(1))
            self.assertAlmostEqual(ya + yb, 300, places=3, msg=f'{la} / {lb}')
            if la[:2] in ('G2', 'G3'):
                self.assertEqual({la[:2], lb[:2]}, {'G2', 'G3'}, f'{la} / {lb}')

    def test_multidepth_three_contours(self):
        ok, text, _ = run_case('MULTIDEP', CASES['MULTIDEP'])
        depths = [float(re.search(r'Z([\d.]+)$', l).group(1)) for l in lines_of(text) if l.startswith('G88')]
        self.assertEqual(len(depths), 3)
        self.assertEqual(depths, sorted(depths))
        self.assertEqual(depths[-1], 19)

    def test_no_move_above_top(self):
        for key in ('RECT', 'LSHAPE', 'MULTIDEP', 'POCKET', 'RAMP', 'CIRCLE'):
            ok, text, _ = run_case(key, CASES[key])
            for l in lines_of(text)[2:-1]:
                if l.startswith('G1'):
                    self.assertGreater(float(re.search(r'Z([\d.]+)$', l).group(1)), 0, f'{key}: {l}')

    def test_line_warning(self):
        if MODE != 'A':
            self.skipTest('warnings are only visible in the CLI log')
        ok, _, log = run_case('RECT.warn', CASES['RECT.warn'])
        self.assertTrue(ok)
        self.assertIn('lines', log.lower())
        self.assertIn('warn', log.lower())

    def test_merge_keeps_reversal(self):
        # A merge across a reversal would drop the turn-around point and shrink the path's extents.
        ok1, merged, _ = run_case('CIRCPOCK', CASES['CIRCPOCK'])
        ok2, raw, _ = run_case('CIRCPOCK.nomerge', CASES['CIRCPOCK.nomerge'])
        self.assertTrue(ok1 and ok2)
        self.assertLess(len(lines_of(merged)), len(lines_of(raw)), 'no merge happened')

        def extents(text):
            pts = [tuple(map(float, re.search(r'X(-?[\d.]+)Y(-?[\d.]+)', l).groups())) for l in lines_of(text)[2:-1]]
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            return min(xs), max(xs), min(ys), max(ys)
        self.assertEqual(extents(merged), extents(raw))

    def test_merge_keeps_feed_change(self):
        # Every feed change present without merging must still be written after merging.
        ok1, merged, _ = run_case('CIRCPOCK', CASES['CIRCPOCK'])
        ok2, raw, _ = run_case('CIRCPOCK.nomerge', CASES['CIRCPOCK.nomerge'])
        self.assertTrue(ok1 and ok2)
        self.assertLess(len(lines_of(merged)), len(lines_of(raw)), 'no merge happened')

        def feeds(text):
            return [re.search(r'F([\d.]+)', l).group(1) for l in lines_of(text) if re.match(r'G(88|1G90F)', l)]
        self.assertEqual(feeds(merged), feeds(raw))

    def test_merge_within_tolerance(self):
        # Every point dropped by merging must lie within mergeTolerance (0.05) of the merged path.
        # CIRCPOCK's linearized lead-out is a gentle curve: checking only the newest middle point
        # lets the deviation accumulate far beyond the tolerance.
        def pts(props):
            spec = dict(CASES['CIRCPOCK'], props=props)
            ok, text, log = run_case('CIRCPOCK', spec)
            self.assertTrue(ok, log[-1500:])
            return [tuple(map(float, re.search(r'X(-?[\d.]+)Y(-?[\d.]+)', l).groups()))
                    + ((float(re.search(r'Z(-?[\d.]+)$', l).group(1)),) if 'Z' in l else (None,))
                    for l in lines_of(text)[2:-1]]
        raw, merged = pts({'mergeTolerance': 0}), pts({})
        self.assertLess(len(merged), len(raw), 'no merge happened')
        # Arc lines carry no Z: take the Z of the preceding point.
        for seq in (raw, merged):
            for i, p in enumerate(seq):
                if p[2] is None:
                    seq[i] = (p[0], p[1], seq[i - 1][2])

        def dseg(p, a, b):
            ab = [b[i] - a[i] for i in range(3)]
            ap = [p[i] - a[i] for i in range(3)]
            n = sum(x * x for x in ab)
            t = max(0, min(1, sum(ab[i] * ap[i] for i in range(3)) / n)) if n else 0
            return sum((ap[i] - t * ab[i]) ** 2 for i in range(3)) ** 0.5
        for p in raw:
            d = min(dseg(p, merged[i], merged[i + 1]) for i in range(len(merged) - 1))
            self.assertLessEqual(d, 0.05 + 0.002, f'{p} is {d:.3f} mm from the merged path')

if __name__ == '__main__':
    unittest.main()
