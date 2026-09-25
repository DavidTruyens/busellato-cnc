# Fusion Post-Processor for the TPA CNC90 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Fusion post-processor (`post/busellato-cnc90.cps`) that turns 2D contours, 2D pockets and vertical drilling into CNC90 program sources the Busellato S.EASY can compile, plus a format checker and the test programs for the first machine visit.

**Architecture:** A Python checker (`tools/check_cnc90.py`) encodes the CNC90 format rules and is proven on the machine's 118 real programs first. The post is a standard Fusion `.cps` file that buffers every output line and writes the header last (it needs the line counts). Tests post fixed Fusion toolpaths — either with the command-line post engine on captured intermediate files (`.cnc`) or, if those can't be captured, inside Fusion through the Fusion MCP — and assert on the output with `unittest` plus the checker.

**Tech Stack:** Fusion post API (JavaScript, `.cps`), Fusion post engine 5.413.5 (`…/CAM360/post`), Fusion Python API via the `autodesk-fusion-mcp` server, Python 3 stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-25-fusion-post-design.md`

## Global Constraints

- Output = CNC90 text source only; never `TAB` or compiled files.
- Codes written: `G71`, `G150`, `G81`, `G88`, `G1`, `G2`, `G3`, `M2` — nothing else. Never `G41`/`G42`.
- `N` = total lines in the file. `L` = steps between `G150` and `M2` (for the codes the post writes: `L = N − 3`).
- Z is depth below the stock top, positive downwards: CNC90 `Z` = −(Fusion Z), setup origin on the stock top.
- Numbers: mm, max 3 decimals, trailing zeros and trailing `.` removed; header dimensions rounded to 0.01 mm.
- File: ASCII, upper case, CRLF line endings, program name 1–8 chars of `A–Z 0–9 _ -`.
- Tool `nn` → `T01nn` (two digits). Top face `P5`. Origin `G54` default, `G55` selectable.
- Arcs: `G2`/`G3G90G17X…Y…U<radius>`, split above 180°, no `F`, no `Z`.
- Refused (error, no file): no stock / origin not on stock top; compensation not "computer"; helix or non-XY arc; strategy other than 2D contour, 2D pocket, drilling; tool not allowed; depth > thickness + max depth; invalid program name.
- Default settings: feed unit m/min, origin G54, mirror Y off, arcs, segment 2 mm, merge 0.05 mm, line warning 250, max depth below 5 mm, allowed tools `1-30,65,66`.
- Commit messages never mention Claude and have no Co-Authored-By line.
- Nothing in this plan runs on the machine. Machine steps (Task 8 run sheet) are executed by David next visit.

## Review Focus

1. **A contour that enters by ramping from above the stock** (Fusion ramp entry, the pocket fallback when helix is refused) must start with `G88 … Z0` at the ramp start and continue with `G1` down to depth — not be refused and not plunge at full depth. → Task 3 case `POCKET` (plunge) and Task 3 test `test_ramp_entry_starts_at_surface` on case `RAMP`.
2. **Retract and re-plunge inside one operation** (pocket islands, multiple depths) must end the contour and start a new `G88`; no `G1` may connect two contours through the air. → Task 3 `test_multidepth_three_contours`, `test_no_move_above_top`.
3. **Mirror Y** must also swap `G2`/`G3`; mirroring coordinates without swapping arcs cuts the wrong side. → Task 7 `test_mirror_swaps_arcs`.
4. **Collinear merge must not merge across a feed change or a direction reversal** (going back along the same line). → Task 7 `test_merge_keeps_reversal`, `test_merge_keeps_feed_change`.
5. **Tool numbers in Fusion that look right but aren't allowed** (e.g. the MC50A library's `T1` end mills) must be refused only if outside the list; `T1` drill is allowed. Parsing of `1-30,65,66` must handle ranges and spaces. → Task 6 `test_allowed_tools_parsing`.

## Rulings made while writing this plan

- Checker file is `tools/check_cnc90.py` (underscore, importable by tests) instead of the spec's `check-cnc90.py`.
- Spec error "contour whose first cut starts above the stock top" is replaced by handling it: a feed move from at/above the top to below it with an XY change (ramp) becomes `G88 … Z0` at the ramp start + `G1` to depth (this is how sample `WEVER3` starts: `G88 … Z0`, then `G1 … Z22`). A vertical plunge becomes `G88` at the bottom.
- Output file extension: the post first tries `extension = ""` (spec: no extension); if Fusion refuses an empty extension, Task 3 switches to `"txt"` with a ledgered ruling and the README tells David to drop `.TXT` when copying.

---

## File Structure

```
tools/check_cnc90.py              format checker (CLI + check() function)
tests/test_check_cnc90.py         checker tests, incl. all 118 real programs
post/busellato-cnc90.cps          the post-processor
post/tests/cases.json             case list: expected result + assertions
post/tests/cases/<CASE>.cnc       captured intermediate toolpaths (mode A)
post/tests/out/<CASE>[.<variant>].nc / .status   outputs posted inside Fusion (mode B)
post/tests/fusion_capture.py      runs inside Fusion: capture .cnc (A) or post all cases (B)
tests/test_post.py                runs every case (CLI in mode A, reads out/ in mode B) and asserts
post/machine-tests/               ZZT1, ZZT1A, ZZT2A, ZZT3A–D + RUN-SHEET.md for the machine visit
post/README.md                    install in Fusion, settings, workflow onto the machine
```

---

### Task 1: Format checker

**Files:**
- Create: `tools/check_cnc90.py`
- Test: `tests/test_check_cnc90.py`

**Interfaces:**
- Produces: `check(data: bytes, name: str, samples: bool = False, max_depth_below: float = 5.0) -> list[str]` (empty = valid); CLI `python3 tools/check_cnc90.py [--samples] FILE…` exits 0 when all pass, 1 otherwise, 2 on usage. In post mode a trailing `.txt` on the file name is ignored for the name rule.

- [ ] **Step 1: Write the failing tests** — `tests/test_check_cnc90.py`:

```python
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
```

- [ ] **Step 2: Run to see it fail**

Run: `python3 -m unittest discover -s tests -p 'test_check_cnc90.py'`
Expected: `ModuleNotFoundError: No module named 'check_cnc90'`

- [ ] **Step 3: Implement** — `tools/check_cnc90.py`:

```python
#!/usr/bin/env python3
"""Validate a TPA CNC90 program source (SORG\\SRG format).

  check_cnc90.py [--samples] FILE...

Default mode checks post-processor output (only the codes the post writes).
--samples accepts every code seen in the machine's own programs.
Exit 0 if every file passes, 1 otherwise, 2 on usage. A trailing .txt on
the file name is ignored for the name rule.
Spec: docs/superpowers/specs/2026-09-25-fusion-post-design.md
"""
import os
import re
import sys

POST_CODES = {'G81', 'G88', 'G1', 'G2', 'G3'}
SAMPLE_CODES = POST_CODES | {'G37', 'G85', 'G183', 'G184', 'G185', 'G186'}
STEP_WEIGHT = {'G183': 2, 'G184': 2}
D = r'\d+(?:\.\d+)?'
N = r'-?\d+(?:\.\d+)?'
HEADER = re.compile(rf'G71X({D})Y({D})Z({D})T00N(\d+)L(\d+)$')
COMMENT = re.compile(r"G150\([ !-'*-~]{0,30}\)$")
POST_LINE = {
    'G81': re.compile(rf'G81G90G5[45]P5T01\d\dX{N}Y{N}Z({D})$'),
    'G88': re.compile(rf'G88G90G5[45]P5T01\d\d(?:S\d+)?F{D}X{N}Y{N}Z({D})$'),
    'G1': re.compile(rf'G1G90(?:F{D})?X{N}Y{N}Z({D})$'),
    'G2': re.compile(rf'G2G90G17X{N}Y{N}U{D}$'),
    'G3': re.compile(rf'G3G90G17X{N}Y{N}U{D}$'),
}
POST_NAME = re.compile(r'[A-Z0-9_-]{1,8}$')
SAMPLE_NAME = re.compile(r"[A-Z0-9_$~!#%&@^'{}()-]{1,8}(\.[A-Z0-9_$~!#%&@^'{}()-]{1,3})?$")


def check(data, name, samples=False, max_depth_below=5.0):
    """Return a list of problems; empty means the program is valid."""
    try:
        text = data.decode('ascii')
    except UnicodeDecodeError:
        return ['not plain ASCII']
    problems = []
    if not (SAMPLE_NAME if samples else POST_NAME).match(name):
        problems.append(f'invalid program name {name!r}')
    if re.search(r'(?<!\r)\n', text):
        problems.append('bare LF line ending')
    if not text.endswith('\r\n'):
        problems.append('file does not end with CRLF')
    lines = text.replace('\r\n', '\n').rstrip('\n').split('\n')
    if len(lines) < 3:
        return problems + ['fewer than 3 lines']
    header = HEADER.match(lines[0])
    if not header:
        return problems + [f'line 1 is not a G71 header: {lines[0]!r}']
    thickness = float(header.group(3))
    n, l = int(header.group(4)), int(header.group(5))
    if not lines[1].startswith('G150('):
        problems.append('line 2 is not G150(...)')
    elif not samples and not COMMENT.match(lines[1]):
        problems.append(f'line 2: G150 comment not plain ASCII of max 30 characters: {lines[1]!r}')
    if lines[-1] != 'M2':
        problems.append('last line is not M2')
    if n != len(lines):
        problems.append(f'N{n} but the file has {len(lines)} lines')
    allowed = SAMPLE_CODES if samples else POST_CODES
    codes = []
    for i, line in enumerate(lines[2:-1], start=3):
        m = re.match(r'[GM]\d+', line)
        code = m.group(0) if m else ''
        if code not in allowed:
            problems.append(f'line {i}: code {code or line[:8]!r} not allowed')
            continue
        codes.append(code)
        if samples:
            continue
        pm = POST_LINE[code].match(line)
        if not pm:
            problems.append(f'line {i}: malformed {code}: {line!r}')
        elif code in ('G81', 'G88', 'G1') and float(pm.group(1)) > thickness + max_depth_below + 1e-9:
            problems.append(f'line {i}: depth {pm.group(1)} deeper than {thickness:g} + {max_depth_below:g}')
    steps = sum(STEP_WEIGHT.get(c, 1) for c in codes)
    if l != steps:
        problems.append(f'L{l} but the program has {steps} steps')
    return problems


def main(argv):
    samples = '--samples' in argv
    files = [a for a in argv[1:] if a != '--samples']
    if not files:
        print(__doc__, file=sys.stderr)
        return 2
    failed = 0
    for path in files:
        with open(path, 'rb') as fh:
            data = fh.read()
        name = os.path.basename(path)
        if not samples and name.lower().endswith('.txt'):
            name = name[:-4]
        problems = check(data, name, samples)
        for p in problems:
            print(f'{path}: {p}')
        failed += bool(problems)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
```

Then `chmod +x tools/check_cnc90.py`.

- [ ] **Step 4: Run all tests**

Run: `python3 -m unittest discover -s tests`
Expected: all pass (existing 45 + the new checker tests). If a real program fails in sample mode, print its problems: the checker rule is wrong, not the program — fix the rule and add a note to the ledger.

- [ ] **Step 5: Commit**

```bash
git add tools/check_cnc90.py tests/test_check_cnc90.py
git commit -m "Add CNC90 format checker, proven on the 118 machine programs"
```

---

### Task 2: Fusion test document, tool library and case capture

This task needs David at Fusion for Step 1 (about 30 minutes). Everything else runs through the Fusion MCP (`execute_python`).

**Files:**
- Create: `post/tests/cases.json`, `post/tests/fusion_capture.py`, `tests/test_post.py`
- Create (mode A): `post/tests/cases/*.cnc`

**Interfaces:**
- Produces: `post/tests/cases.json` — object keyed by case name: `{"ok": bool, "error": str (substring, CLI only), "props": {name: value}, "assert": [...]}` with assertion strings described in Step 4. `tests/test_post.py` runs each case with `run_case(name, props) -> (ok: bool, text: str, log: str)`. `fusion_capture.py` defines `capture_cnc()` (mode A) and `post_all(variants)` (mode B), both run inside Fusion.

- [ ] **Step 1: David builds the test document** (instructions to hand over verbatim):

  1. **Tool library** "Busellato S.EASY" (Manufacture → Tool Library → new local library), units mm:
     - T65: flat end mill Ø18, flute length 40, 18000 rpm, cutting feed 3000 mm/min, plunge feed 1000 mm/min.
     - T66: flat end mill Ø8, flute length 30, 18000 rpm, same feeds.
     - T1: drill Ø8, 118°, 3000 rpm, plunge feed 1000 mm/min.
     - T99: flat end mill Ø8 (only for the "refused tool" case).
  2. **Design** "Busellato post tests": one box body 400 (X) × 300 (Y) × 18 (Z), corner at the origin, top face at Z = 18. One sketch on the top face with:
     - RECT: rectangle (20,20)–(180,120)
     - L shape: polygon (220,20) (380,20) (380,80) (290,80) (290,180) (220,180), fillet R30 at (290,80)
     - CIRCLE: circle centre (100,220) Ø80
     - POCKET: rectangle (160,200)–(260,270)
     - holes: points (320,220) (352,220) (320,260)
  3. **Setup "S1"**: stock = the body (fixed box, no offsets); WCS origin = **top face, lower-left corner** (X0 Y0 at the (0,0) corner, Z0 on the top face, Z up).
  4. **Operations in S1** (leave defaults unless listed; compensation "In computer"; lead-in/lead-out **off**; ramp **off**; no stock to leave):

     | Operation name | Type | Tool | Geometry | Depth | Special |
     |---|---|---|---|---|---|
     | RECT | 2D contour, inside | T65 | RECT | bottom 1 mm below stock bottom | – |
     | LSHAPE | 2D contour, outside | T65 | L shape | 1 mm below stock bottom | – |
     | MULTIDEP | 2D contour, outside | T65 | L shape | 1 mm below stock bottom | Multiple depths, max stepdown 7 |
     | CIRCLE | 2D contour, outside | T65 | CIRCLE | 1 mm below stock bottom | – |
     | POCKET | 2D pocket | T66 | POCKET | 10 mm below top | Ramp type **plunge** |
     | RAMP | 2D pocket | T66 | POCKET | 10 mm below top | Ramp type **profile/zig-zag ramp**, ramp angle 5° |
     | POCKHLX | 2D pocket | T66 | POCKET | 10 mm below top | Ramp type **helix** (default) |
     | DRILL | Drilling | T1 | the three points | 13 mm below top | Cycle **drilling – rapid out** |
     | CTRLCOMP | 2D contour, inside | T65 | RECT | 1 mm below stock bottom | Compensation **In control** |
     | TOOL99 | 2D contour, inside | T99 | RECT | 1 mm below stock bottom | – |
     | DEEP | 2D contour, inside | T65 | RECT | 12 mm below stock bottom | – |

  5. **Setup "S2"** (copy of S1) with WCS origin on the **bottom** face, one operation BADORIG = copy of RECT.
  6. **NC programs**: one per operation above, **browser name = operation name**, program name = operation name (e.g. `RECT`), post = any (the capture script sets it), output folder = anywhere. Plus NC program BADNAME = RECT operation with program name `TOOLONGNAME1`.
  7. Save the document and keep it open (active) in Fusion.

- [ ] **Step 2: Verify the document through the MCP**

Run via `execute_python` (session `busellato-post`):

```python
import adsk.core, adsk.cam
app = adsk.core.Application.get()
cam = adsk.cam.CAM.cast(app.activeDocument.products.itemByProductType('CAMProductType'))
names = [cam.ncPrograms.item(i).name for i in range(cam.ncPrograms.count)]
want = {'RECT','LSHAPE','MULTIDEP','CIRCLE','POCKET','RAMP','POCKHLX','DRILL','CTRLCOMP','TOOL99','DEEP','BADORIG','BADNAME'}
print('missing:', sorted(want - set(names)), 'extra:', sorted(set(names) - want))
for s in cam.setups:
    for o in s.allOperations:
        print(s.name, o.name, o.strategy, 'T', o.tool.parameters.itemByName('tool_number').value.value, 'valid:', o.isToolpathValid)
```

Expected: `missing: [] extra: []`, every operation `valid: True` (if not, `cam.generateAllToolpaths(False)` and wait, then re-run).

- [ ] **Step 3: Probe whether intermediate `.cnc` files can be captured (decides mode A or B)**

Write `post/tests/fusion_capture.py`:

```python
"""Runs INSIDE Fusion (via the Fusion MCP: exec(open(PATH).read())).

capture_cnc(): mode A - posts every NC program once and copies the intermediate
               .cnc file Fusion writes to post/tests/cases/<NAME>.cnc.
post_all(variants): mode B - posts every NC program with post/busellato-cnc90.cps
               and writes post/tests/out/<NAME>[.<variant>].nc and .status.
"""
import glob
import json
import os
import shutil
import tempfile
import time

import adsk.cam
import adsk.core

REPO = '/Users/davidtruyens/Source/busellato-cnc'
POSTS_DIR = os.path.expanduser('~/Library/Application Support/Autodesk/Fusion 360 CAM/Posts')
CASES = os.path.join(REPO, 'post', 'tests', 'cases')
OUT = os.path.join(REPO, 'post', 'tests', 'out')


def _cam():
    app = adsk.core.Application.get()
    return adsk.cam.CAM.cast(app.activeDocument.products.itemByProductType('CAMProductType'))


def _post_config(file_name):
    lib = adsk.cam.CAMManager.get().libraryManager.postLibrary
    root = lib.urlByLocation(adsk.cam.LibraryLocations.LocalLibraryLocation)
    for url in lib.childAssetURLs(root):
        if url.toString().endswith(file_name):
            return lib.postConfigurationAtURL(url)
    raise RuntimeError(f'{file_name} not found in the local post library ({POSTS_DIR})')


def _post(ncp, post_file, out_dir, props=None):
    ncp.postConfiguration = _post_config(post_file)
    ncp.parameters.itemByName('nc_program_output_folder').value.value = out_dir
    ncp.parameters.itemByName('nc_program_openInEditor').value.value = False
    if props:
        params = ncp.postParameters
        for key, value in props.items():
            p = params.itemByName(key)
            if p is None:
                raise RuntimeError(f'post property {key} not found')
            p.value.value = value
        ncp.updatePostParameters(params)
    return ncp.postProcess(adsk.cam.NCProgramPostProcessOptions.create())


def _search_dirs():
    return {tempfile.gettempdir(), os.environ.get('TMPDIR', '/tmp'),
            os.path.expanduser('~/Library/Application Support/Autodesk/Autodesk Fusion 360/CAM'),
            os.path.expanduser('~/Library/Caches')}


def capture_cnc(stand_in_post='grbl.cps'):
    os.makedirs(CASES, exist_ok=True)
    found = {}
    cam = _cam()
    for i in range(cam.ncPrograms.count):
        ncp = cam.ncPrograms.item(i)
        start = time.time() - 1
        with tempfile.TemporaryDirectory() as tmp:
            _post(ncp, stand_in_post, tmp)
            time.sleep(0.5)
            fresh = [f for d in _search_dirs() for f in glob.glob(os.path.join(d, '**', '*.cnc'), recursive=True)
                     if os.path.getmtime(f) >= start]
        if fresh:
            newest = max(fresh, key=os.path.getmtime)
            shutil.copyfile(newest, os.path.join(CASES, ncp.name + '.cnc'))
            found[ncp.name] = newest
    return found


def post_all(variants):
    """variants: {suffix: {case: props}}; suffix '' = default properties."""
    shutil.copyfile(os.path.join(REPO, 'post', 'busellato-cnc90.cps'),
                    os.path.join(POSTS_DIR, 'busellato-cnc90.cps'))
    os.makedirs(OUT, exist_ok=True)
    cam = _cam()
    programs = {cam.ncPrograms.item(i).name: cam.ncPrograms.item(i) for i in range(cam.ncPrograms.count)}
    report = {}
    for suffix, cases in variants.items():
        for case, props in cases.items():
            key = case + (('.' + suffix) if suffix else '')
            with tempfile.TemporaryDirectory() as tmp:
                ok = _post(programs[case], 'busellato-cnc90.cps', tmp, props)
                produced = [f for f in os.listdir(tmp) if not f.endswith('.log')]
                text = open(os.path.join(tmp, produced[0]), 'rb').read() if (ok and produced) else b''
            with open(os.path.join(OUT, key + '.nc'), 'wb') as fh:
                fh.write(text)
            with open(os.path.join(OUT, key + '.status'), 'w') as fh:
                fh.write('ok' if ok else 'failed')
            report[key] = ok
    return report
```

Run via MCP:

```python
exec(open('/Users/davidtruyens/Source/busellato-cnc/post/tests/fusion_capture.py').read())
print(capture_cnc())
```

Decision (write it to the ledger as `Task 2: Ruling: mode A|B — <evidence>`):
- **Mode A** if all 13 programs produced a `.cnc` in `post/tests/cases/`. Check one with the CLI: `"$POST" --noeditor "$HOME/Library/Application Support/Autodesk/Fusion 360 CAM/Posts/grbl.cps" post/tests/cases/RECT.cnc /tmp/rect.nc` produces G-code. (`$POST` = the `post` binary path from the spec.)
- **Mode B** otherwise. `capture_cnc()` found nothing, so the test runner reads outputs that `post_all()` writes; every post task then re-runs `post_all()` through the MCP before running `unittest`.
- If `postProcess` itself fails for the stand-in post (e.g. `nc_program_output_folder` has a different name), print `[p.name for p in ncp.parameters]` and fix the parameter names in `_post`; ledger the names.

- [ ] **Step 4: Write `post/tests/cases.json`**

Assertion strings (all run on the output text, CRLF split into lines):
- `"line1 ^regex$"` — line 1 matches; `"line2 ^regex$"`; `"last ^regex$"`
- `"has ^regex$"` — at least one line matches; `"count N ^regex$"` — exactly N lines match; `"atleast N ^regex$"`
- `"none ^regex$"` — no line matches
- `"xy X,Y"` — some `G88`/`G1`/`G2`/`G3` line ends at exactly `X<X>Y<Y>`
- `"checker"` — `check_cnc90.check(text, name)` returns `[]`
- `"crlf"` — every line ends with CRLF

```json
{
  "RECT": {"ok": true, "props": {}, "assert": [
    "checker", "crlf",
    "line1 ^G71X400Y300Z18T00N\\d+L\\d+$", "line2 ^G150\\(.*\\)$", "last ^M2$",
    "count 1 ^G88G90G54P5T0165S18000F1X[-\\d.]+Y[-\\d.]+Z19$",
    "xy 29,29", "xy 171,29", "xy 171,111", "xy 29,111",
    "none ^G[23]", "none G4[12]", "none Z-"]},
  "LSHAPE": {"ok": true, "props": {}, "assert": [
    "checker", "count 1 ^G88", "atleast 1 ^G[23]G90G17X[-\\d.]+Y[-\\d.]+U9$",
    "atleast 1 ^G[23]G90G17X[-\\d.]+Y[-\\d.]+U21$"]},
  "MULTIDEP": {"ok": true, "props": {}, "assert": [
    "checker", "count 3 ^G88", "has ^G88.*Z19$", "none ^G1G90.*Z-"]},
  "CIRCLE": {"ok": true, "props": {}, "assert": [
    "checker", "atleast 2 ^G[23]G90G17X[-\\d.]+Y[-\\d.]+U49$"]},
  "POCKET": {"ok": true, "props": {}, "assert": [
    "checker", "atleast 1 ^G88G90G54P5T0166S18000F1X[-\\d.]+Y[-\\d.]+Z10$", "none Z1[1-9]"]},
  "RAMP": {"ok": true, "props": {}, "assert": [
    "checker", "has ^G88G90G54P5T0166S18000F1X[-\\d.]+Y[-\\d.]+Z0$"]},
  "POCKHLX": {"ok": false, "error": "helix", "props": {}, "assert": []},
  "DRILL": {"ok": true, "props": {}, "assert": [
    "checker", "count 3 ^G81G90G54P5T0101X(320|352)Y(220|260)Z13$",
    "has ^G81.*X320Y220Z13$", "has ^G81.*X352Y220Z13$", "has ^G81.*X320Y260Z13$"]},
  "CTRLCOMP": {"ok": false, "error": "compensation", "props": {}, "assert": []},
  "TOOL99": {"ok": false, "error": "T99", "props": {}, "assert": []},
  "DEEP": {"ok": false, "error": "Depth", "props": {}, "assert": []},
  "BADORIG": {"ok": false, "error": "TOP surface", "props": {}, "assert": []},
  "BADNAME": {"ok": false, "error": "program name", "props": {}, "assert": []}
}
```

(Property variants are added by later tasks under keys like `"LSHAPE.mirror"` with `"case": "LSHAPE"`.)

- [ ] **Step 5: Write `tests/test_post.py`** (runs cases; red until the post exists)

```python
"""Post-processor tests. Mode A: CLI post engine on post/tests/cases/*.cnc.
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
            for k, v in spec.get('props', {}).items():
                cmd += ['--property', k, str(v)]
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


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 6: Run and confirm it fails for the right reason**

Mode A: `python3 -m unittest discover -s tests -p 'test_post.py'` → FAIL (post file missing: every `ok` is False).
Mode B: run `post_all({'': {k: v['props'] for k, v in CASES.items() if 'case' not in v}})` via MCP → it raises because `post/busellato-cnc90.cps` does not exist yet. That is the expected red.

- [ ] **Step 7: Commit**

```bash
git add post/tests/cases.json post/tests/fusion_capture.py tests/test_post.py post/tests/cases 2>/dev/null
git commit -m "Post-processor test harness and Fusion test cases"
```

---

### Task 3: Post core — header, comment, contours with lines, CRLF, name

**Files:**
- Create: `post/busellato-cnc90.cps`
- Modify: `post/tests/cases.json` (replace the `RAMP` entry, extend `MULTIDEP`)

**Interfaces:**
- Consumes: `cases.json` cases `RECT`, `MULTIDEP`, `POCKET`, `RAMP`, `BADNAME`; `fusion_capture.post_all()` in mode B.
- Produces: post globals and functions later tasks extend: `moves` (array of `{kind: "G88"|"G1"|"ARC"|"G81", ...}`), `fmt(v) -> string`, `outY(y) -> number`, `feedOut(f) -> number`, `emitG88(x, y, z, feed)`, `addLine(p0, p1, feed)`, `cut(p0, p1, feed)`, `checkDepth(z)`, `stock` (`{lx, ly, lz, ux, uy, uz}`), property ids `feedUnit, origin, mirrorY, arcOutput, segmentLength, mergeTolerance, lineWarning, maxDepthBelow, allowedTools`.

- [ ] **Step 1: The failing tests already exist** (Task 2). Replace the `RAMP` entry in `cases.json` with:

```json
  "RAMP": {"ok": true, "props": {}, "assert": [
    "checker", "has ^G88G90G54P5T0166S18000F1X[-\\d.]+Y[-\\d.]+Z0$",
    "atleast 1 ^G1G90(F[\\d.]+)?X[-\\d.]+Y[-\\d.]+Z10$", "none Z-"]},
```

and extend `MULTIDEP` with `"none ^G1G90.*Z0$"` (no `G1` at the surface: the contours are separate `G88` starts).

- [ ] **Step 2: Confirm red** — mode A `python3 -m unittest discover -s tests -p 'test_post.py'`; mode B `post_all(...)` raises (file missing). Expected: FAIL.

- [ ] **Step 3: Implement `post/busellato-cnc90.cps`**

```javascript
/**
  Busellato S.EASY - TPA CNC90 v3.0 post processor.
  Writes a CNC90 program source for C:\CNC90\MOD1\SORG\SRG\<first letter>\<NAME>.
  Spec: docs/superpowers/specs/2026-09-25-fusion-post-design.md (busellato-cnc repo).
*/

description = "Busellato S.EASY - TPA CNC90";
vendor = "TPA";
longDescription = "CNC90 ISO-DGT program source: 2D contour, 2D pocket, vertical drilling, top face (P5).";
certificationLevel = 2;
minimumRevision = 45917;
extension = "";
setCodePage("ascii");
capabilities = CAPABILITY_MILLING;
tolerance = spatial(0.002, MM);
minimumChordLength = spatial(0.25, MM);
minimumCircularRadius = spatial(0.01, MM);
maximumCircularRadius = spatial(100000, MM);
minimumCircularSweep = toRad(0.01);
maximumCircularSweep = toRad(180);
allowHelicalMoves = true;
allowedCircularPlanes = undefined;

properties = {
  feedUnit: {title: "Feed unit", description: "m/min: Fusion mm/min / 1000 (F1 = 1 m/min). mm/min: unchanged.",
    type: "enum", values: [{id: "mpm", title: "m/min"}, {id: "mmpm", title: "mm/min"}], value: "mpm", scope: "post"},
  origin: {title: "Origin", description: "Reference origin of the machine.",
    type: "enum", values: [{id: "G54", title: "G54"}, {id: "G55", title: "G55"}], value: "G54", scope: "post"},
  mirrorY: {title: "Mirror Y", description: "Mirror Y about the stock centre and swap G2/G3.",
    type: "boolean", value: false, scope: "post"},
  arcOutput: {title: "Arc output", description: "arcs: G2/G3. lines: straight segments only (emergency fallback).",
    type: "enum", values: [{id: "arcs", title: "G2/G3 arcs"}, {id: "lines", title: "Straight lines only"}], value: "arcs", scope: "post"},
  segmentLength: {title: "Segment length (mm)", description: "Segment length when arc output = lines.",
    type: "number", value: 2, scope: "post"},
  mergeTolerance: {title: "Merge tolerance (mm)", description: "Collinear straight moves within this distance are merged.",
    type: "number", value: 0.05, scope: "post"},
  lineWarning: {title: "Warn above N lines", description: "Largest program the machine is known to run is ~250 lines.",
    type: "integer", value: 250, scope: "post"},
  maxDepthBelow: {title: "Max depth below stock (mm)", description: "Deeper cuts than stock thickness + this are refused.",
    type: "number", value: 5, scope: "post"},
  allowedTools: {title: "Allowed tool numbers", description: "Comma separated numbers and ranges, e.g. 1-30,65,66.",
    type: "string", value: "1-30,65,66", scope: "post"}
};

var TOP = 0.0005;          // mm; at or above this Z counts as "not in the material"
var moves = [];            // output lines between G150 and M2, as objects
var stock = null;          // {lx, ly, lz, ux, uy, uz} in WCS mm
var inContour = false;
var progName = "";
var progComment = "";
var sectionTool = 0;
var sectionRpm = 0;

function fmt(v) {
  var r = Math.round(v * 1000) / 1000;
  if (Math.abs(r) < 0.0005) {
    r = 0;
  }
  return String(r);
}

function pad2(n) {
  return (n < 10 ? "0" : "") + n;
}

function outY(y) {
  return getProperty("mirrorY") ? (stock.ly + stock.uy - y) : y;
}

function feedOut(f) {
  return getProperty("feedUnit") == "mpm" ? f / 1000 : f;
}

function onOpen() {
  setEOL(CRLF);
  if (unit != MM) {
    error("Set the NC program output units to millimetres.");
  }
  progName = String(programName || "").toUpperCase();
  if (!/^[A-Z0-9_-]{1,8}$/.test(progName)) {
    error("Invalid program name '" + programName + "': use 1-8 characters A-Z, 0-9, _ or - (DOS file name).");
  }
  progComment = String(programComment || "").toUpperCase().replace(/[^\x20-\x7E]/g, "").replace(/[()]/g, "").substr(0, 30);
}

function onSection() {
  inContour = false;
  if (!stock) {
    var box = getWorkpiece();
    if (!box || !(box.upper.x > box.lower.x)) {
      error("No stock defined in the setup.");
    }
    if (Math.abs(box.upper.z) > 0.01) {
      error("The setup origin must be on the TOP surface of the stock (stock top is at Z=" + fmt(box.upper.z) + ").");
    }
    stock = {lx: box.lower.x, ly: box.lower.y, lz: box.lower.z, ux: box.upper.x, uy: box.upper.y, uz: box.upper.z};
  }
  sectionTool = tool.number;
  sectionRpm = tool.spindleRPM;
}

function checkDepth(z) {
  var limit = (stock.uz - stock.lz) + getProperty("maxDepthBelow");
  if (-z > limit + 1e-6) {
    error("Depth " + fmt(-z) + " mm is deeper than stock thickness + " + getProperty("maxDepthBelow") + " mm (" + fmt(limit) + ").");
  }
}

function emitG88(x, y, z, feed) {
  moves.push({kind: "G88", x: x, y: y, z: z, f: feedOut(feed), tool: sectionTool, rpm: sectionRpm});
}

function addLine(p0, p1, feed) {
  moves.push({kind: "G1", start: {x: p0.x, y: p0.y, z: p0.z}, end: {x: p1.x, y: p1.y, z: p1.z}, f: feedOut(feed)});
}

function cut(p0, p1, feed) {
  if (p1.z >= -TOP) {       // retract or move in the air: ends the contour, nothing written
    inContour = false;
    return;
  }
  checkDepth(p1.z);
  if (inContour) {
    addLine(p0, p1, feed);
    return;
  }
  var sameXY = Math.abs(p0.x - p1.x) < 1e-4 && Math.abs(p0.y - p1.y) < 1e-4;
  if (p0.z >= -TOP && sameXY) {          // vertical plunge: G88 at the bottom
    emitG88(p1.x, p1.y, p1.z, feed);
  } else if (p0.z >= -TOP) {             // ramp from the surface
    emitG88(p0.x, p0.y, 0, feed);
    addLine({x: p0.x, y: p0.y, z: 0}, p1, feed);
  } else {                                // already below the top (e.g. after a rapid at depth)
    emitG88(p0.x, p0.y, p0.z, feed);
    addLine(p0, p1, feed);
  }
  inContour = true;
}

function onRapid(x, y, z) {
  inContour = false;
}

function onLinear(x, y, z, feed) {
  cut(getCurrentPosition(), {x: x, y: y, z: z}, feed);
}

function onSectionEnd() {
  inContour = false;
}

function formatMoves() {
  var origin = getProperty("origin");
  var out = [];
  var lastF = null;
  for (var i = 0; i < moves.length; ++i) {
    var m = moves[i];
    if (m.kind == "G88") {
      lastF = m.f;
      out.push("G88G90" + origin + "P5T01" + pad2(m.tool) + (m.rpm > 0 ? "S" + Math.round(m.rpm) : "") +
        "F" + fmt(m.f) + "X" + fmt(m.x) + "Y" + fmt(outY(m.y)) + "Z" + fmt(-m.z));
    } else if (m.kind == "G1") {
      var f = (m.f != lastF) ? "F" + fmt(m.f) : "";
      lastF = m.f;
      out.push("G1G90" + f + "X" + fmt(m.end.x) + "Y" + fmt(outY(m.end.y)) + "Z" + fmt(-m.end.z));
    }
  }
  return out;
}

function onClose() {
  var lines = ["G150(" + progComment + ")"].concat(formatMoves()).concat(["M2"]);
  var n = lines.length + 1;
  var dims = function (v) {
    return fmt(Math.round(v * 100) / 100);
  };
  writeln("G71X" + dims(stock.ux - stock.lx) + "Y" + dims(stock.uy - stock.ly) + "Z" + dims(stock.uz - stock.lz) +
    "T00N" + n + "L" + (n - 3));
  for (var i = 0; i < lines.length; ++i) {
    writeln(lines[i]);
  }
}
```

- [ ] **Step 4: Run and iterate**

Mode B: via MCP run `exec(open(…/fusion_capture.py).read()); print(post_all({'': {k: v['props'] for k, v in json.load(open('/Users/davidtruyens/Source/busellato-cnc/post/tests/cases.json')).items() if 'case' not in v}}))` first.
Then: `python3 -m unittest discover -s tests -p 'test_post.py'`
Expected now: `RECT`, `MULTIDEP`, `POCKET`, `RAMP`, `BADNAME` pass. `LSHAPE`/`CIRCLE` (arcs), `DRILL`, and the refusal cases other than `BADNAME`/`BADORIG` still fail — they belong to Tasks 4–6. `BADORIG` already passes (origin check).

If Fusion refuses `extension = ""` (post fails for every case with an extension error in the log): set `extension = "txt"`, re-run, and ledger the ruling.

If `setEOL(CRLF)` is unknown to this engine version: use `setEOL("\r\n")`; ledger it.

- [ ] **Step 5: Commit**

```bash
git add post/busellato-cnc90.cps post/tests/cases.json post/tests/out 2>/dev/null
git commit -m "Post core: header, comment, contours (lines), CRLF, program name"
```

---

### Task 4: Arcs — G2/G3, split above 180°, lines fallback, helix refused

**Files:**
- Modify: `post/busellato-cnc90.cps` (add `onCircular`, `linearizeArc`; extend `formatMoves`)
- Modify: `post/tests/cases.json` (variant `CIRCLE.lines`)

**Interfaces:**
- Consumes: `cut`, `emitG88`, `checkDepth`, `feedOut`, `moves`, `inContour` (Task 3).
- Produces: move kind `"ARC"` `{end:{x,y,z}, r, cw}`.

- [ ] **Step 1: Add the failing variant** to `cases.json`:

```json
  "CIRCLE.lines": {"case": "CIRCLE", "ok": true, "props": {"arcOutput": "lines", "segmentLength": 5}, "assert": [
    "checker", "none ^G[23]", "atleast 60 ^G1G90"]},
```

(Circumference of the Ø98 path ≈ 308 mm / 5 mm ≈ 62 segments.) In mode B the `post_all` call gains `'lines': {'CIRCLE': {'arcOutput': 'lines', 'segmentLength': 5}}`.

- [ ] **Step 2: Confirm red** — `LSHAPE`, `CIRCLE`, `CIRCLE.lines`, `POCKHLX` fail.

- [ ] **Step 3: Implement** — add to `post/busellato-cnc90.cps` after `onLinear`:

```javascript
function onCircular(clockwise, cx, cy, cz, x, y, z, feed) {
  var p0 = getCurrentPosition();
  if (getCircularPlane() != PLANE_XY) {
    error("Only arcs in the XY plane are supported (operation " + getParameter("operation-comment", "") + ").");
  }
  if (isHelical()) {
    error("Helical move (helix) in operation " + getParameter("operation-comment", "") +
      ". Set the entry to plunge or ramp (Fusion's pocket default is a helix).");
  }
  var p1 = {x: x, y: y, z: z};
  if (getProperty("arcOutput") == "lines") {
    linearizeArc(p0, clockwise, cx, cy, p1, feed);
    return;
  }
  if (p1.z >= -TOP) {
    inContour = false;
    return;
  }
  checkDepth(p1.z);
  if (!inContour) {
    emitG88(p0.x, p0.y, p0.z, feed);
    inContour = true;
  }
  moves.push({kind: "ARC", end: p1, r: getCircularRadius(), cw: clockwise});
}

function linearizeArc(p0, clockwise, cx, cy, p1, feed) {
  var r = Math.sqrt((p0.x - cx) * (p0.x - cx) + (p0.y - cy) * (p0.y - cy));
  var sweep = getCircularSweep();            // radians, positive
  var n = Math.max(1, Math.ceil(r * sweep / getProperty("segmentLength")));
  var a0 = Math.atan2(p0.y - cy, p0.x - cx);
  var dir = clockwise ? -1 : 1;
  var prev = p0;
  for (var i = 1; i <= n; ++i) {
    var a = a0 + dir * sweep * i / n;
    var p = (i == n) ? p1 : {x: cx + r * Math.cos(a), y: cy + r * Math.sin(a), z: p1.z};
    cut(prev, p, feed);
    prev = p;
  }
}
```

and in `formatMoves`, after the `G1` branch:

```javascript
    } else if (m.kind == "ARC") {
      var cw = getProperty("mirrorY") ? !m.cw : m.cw;
      out.push((cw ? "G2" : "G3") + "G90G17X" + fmt(m.end.x) + "Y" + fmt(outY(m.end.y)) + "U" + fmt(m.r));
    }
```

- [ ] **Step 4: Run** (mode B: `post_all` first). Expected: `LSHAPE`, `CIRCLE`, `CIRCLE.lines`, `POCKHLX` pass; all earlier cases still pass.

- [ ] **Step 5: Commit** — `git commit -am "Post: G2/G3 arcs, split above 180, lines fallback, helix refused"` (plus `git add post/tests/out` in mode B).

---

### Task 5: Vertical drilling

**Files:**
- Modify: `post/busellato-cnc90.cps` (add `onCycle`, `onCyclePoint`, `onCycleEnd`; extend `formatMoves`)

**Interfaces:**
- Consumes: `checkDepth`, `outY`, `moves`, `sectionTool` (Task 3).
- Produces: move kind `"G81"` `{x, y, depth, tool}`.

- [ ] **Step 1: Test exists** (`DRILL` in `cases.json`). Add a refusal for other cycles — no extra Fusion case; the error path is covered by code review of `onCycle`.
- [ ] **Step 2: Confirm red** — `DRILL` fails.
- [ ] **Step 3: Implement** — add:

```javascript
function onCycle() {
  inContour = false;
  if (cycleType != "drilling") {
    error("Drill cycle '" + cycleType + "' is not supported; use plain drilling (drilling - rapid out).");
  }
}

function onCyclePoint(x, y, z) {
  checkDepth(cycle.bottom);
  moves.push({kind: "G81", x: x, y: y, depth: -cycle.bottom, tool: sectionTool});
}

function onCycleEnd() {
}
```

and in `formatMoves`:

```javascript
    } else if (m.kind == "G81") {
      out.push("G81G90" + origin + "P5T01" + pad2(m.tool) + "X" + fmt(m.x) + "Y" + fmt(outY(m.y)) + "Z" + fmt(m.depth));
    }
```

- [ ] **Step 4: Run** — `DRILL` passes, others unchanged.
- [ ] **Step 5: Commit** — `git commit -am "Post: vertical drilling as G81"`.

---

### Task 6: Refusals — strategy, compensation, tool list, depth

**Files:**
- Modify: `post/busellato-cnc90.cps` (add `parseAllowed`, checks in `onSection`, `onRadiusCompensation`)
- Test: `tests/test_post.py` (add `test_allowed_tools_parsing`)

**Interfaces:**
- Consumes: `onSection`, `checkDepth` (Task 3).
- Produces: `parseAllowed(text) -> object` keyed by tool number (value `true`).

- [ ] **Step 1: Write the failing tests** — cases `CTRLCOMP`, `TOOL99`, `DEEP` exist. Add to `tests/test_post.py` a parsing test that runs the post's `parseAllowed` through Node-free means: a case variant with a custom list:

```json
  "RECT.tools": {"case": "RECT", "ok": false, "error": "T65", "props": {"allowedTools": " 1 - 30 , 66 "}, "assert": []},
  "DRILL.tools": {"case": "DRILL", "ok": true, "props": {"allowedTools": "1-30, 65,66"}, "assert": ["checker"]}
```

and in `tests/test_post.py` add the method:

```python
    def test_allowed_tools_parsing(self):
        for key in ('RECT.tools', 'DRILL.tools'):
            ok, _, log = run_case(key, CASES[key])
            self.assertEqual(ok, CASES[key]['ok'], f'{key}\n{log[-1500:]}')
```

(mode B: `post_all` gains `'tools': {'RECT': {'allowedTools': ' 1 - 30 , 66 '}, 'DRILL': {'allowedTools': '1-30, 65,66'}}`).

- [ ] **Step 2: Confirm red** — `CTRLCOMP`, `TOOL99`, `DEEP` and `RECT.tools` do not refuse yet.

- [ ] **Step 3: Implement** — add before `onSection`:

```javascript
function parseAllowed(text) {
  var allowed = {};
  var parts = String(text).split(",");
  for (var i = 0; i < parts.length; ++i) {
    var p = parts[i].replace(/\s+/g, "");
    if (!p) {
      continue;
    }
    var m = p.match(/^(\d+)-(\d+)$/);
    if (m) {
      for (var t = parseInt(m[1], 10); t <= parseInt(m[2], 10); ++t) {
        allowed[t] = true;
      }
    } else if (/^\d+$/.test(p)) {
      allowed[parseInt(p, 10)] = true;
    } else {
      error("Allowed tool numbers: cannot read '" + parts[i] + "'.");
    }
  }
  return allowed;
}

function onRadiusCompensation() {
  if (radiusCompensation != RADIUS_COMPENSATION_OFF) {
    error("Cutter compensation must be 'In computer' (found compensation in control).");
  }
}
```

and in `onSection`, after the stock block:

```javascript
  var strategy = currentSection.strategy || getParameter("operation-strategy", "");
  if (["contour2d", "pocket2d", "drill"].indexOf(strategy) < 0) {
    error("Operation " + getParameter("operation-comment", "") + " (" + strategy +
      ") is not supported. Use 2D contour, 2D pocket or drilling.");
  }
  if (hasParameter("operation:compensationType") && getParameter("operation:compensationType") != "computer") {
    error("Cutter compensation must be 'In computer' in operation " + getParameter("operation-comment", "") + ".");
  }
  if (!parseAllowed(getProperty("allowedTools"))[tool.number]) {
    error("Tool T" + tool.number + " is not in the allowed tool list (" + getProperty("allowedTools") + ").");
  }
```

(`DEEP` is already handled by `checkDepth` from Task 3; if it still passes, check that its operation really cuts 12 mm below the stock bottom.)

- [ ] **Step 4: Run** — all cases so far pass.
- [ ] **Step 5: Commit** — `git commit -am "Post: refuse unsupported strategies, compensation in control, unknown tools"`.

---

### Task 7: Settings — merge, mirror Y, feed unit, G55, line warning

**Files:**
- Modify: `post/busellato-cnc90.cps` (`addLine` merge; warning in `onClose`)
- Modify: `post/tests/cases.json`, `tests/test_post.py`

**Interfaces:**
- Consumes: `addLine`, `formatMoves`, `onClose` (Tasks 3–5).
- Produces: `collinear(a, b, c) -> bool`.

- [ ] **Step 1: Write the failing tests** — add variants:

```json
  "LSHAPE.mirror": {"case": "LSHAPE", "ok": true, "props": {"mirrorY": true}, "assert": ["checker"]},
  "RECT.mmpm": {"case": "RECT", "ok": true, "props": {"feedUnit": "mmpm"}, "assert": [
    "checker", "has ^G88.*F1000X", "has ^G1G90F3000X"]},
  "RECT.g55": {"case": "RECT", "ok": true, "props": {"origin": "G55"}, "assert": ["checker", "has ^G88G90G55P5", "none G54"]},
  "RECT.warn": {"case": "RECT", "ok": true, "props": {"lineWarning": 3}, "assert": ["checker"]},
  "POCKET.nomerge": {"case": "POCKET", "ok": true, "props": {"mergeTolerance": 0}, "assert": ["checker"]}
```

and in `tests/test_post.py`:

```python
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
        ok1, merged, _ = run_case('POCKET', CASES['POCKET'])
        ok2, raw, _ = run_case('POCKET.nomerge', CASES['POCKET.nomerge'])
        self.assertTrue(ok1 and ok2)

        def extents(text):
            pts = [tuple(map(float, re.search(r'X(-?[\d.]+)Y(-?[\d.]+)', l).groups())) for l in lines_of(text)[2:-1]]
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            return min(xs), max(xs), min(ys), max(ys)
        self.assertEqual(extents(merged), extents(raw))
        self.assertLessEqual(len(lines_of(merged)), len(lines_of(raw)))

    def test_merge_keeps_feed_change(self):
        # Every feed change present without merging must still be written after merging.
        ok1, merged, _ = run_case('POCKET', CASES['POCKET'])
        ok2, raw, _ = run_case('POCKET.nomerge', CASES['POCKET.nomerge'])

        def feeds(text):
            return [re.search(r'F([\d.]+)', l).group(1) for l in lines_of(text) if re.match(r'G(88|1G90F)', l)]
        self.assertEqual(feeds(merged), feeds(raw))
```

(mode B: `post_all` gains `'mirror': {'LSHAPE': {'mirrorY': True}}, 'mmpm': {'RECT': {'feedUnit': 'mmpm'}}, 'g55': {'RECT': {'origin': 'G55'}}, 'warn': {'RECT': {'lineWarning': 3}}, 'nomerge': {'POCKET': {'mergeTolerance': 0}}`.)

- [ ] **Step 2: Confirm red** — `test_line_warning` fails (no warning yet) and, with `mergeTolerance` not yet used, `POCKET` and `POCKET.nomerge` are identical so the merge tests pass vacuously: confirm `len(lines_of(merged)) == len(lines_of(raw))` now, and after Step 3 that the merged program is shorter. `test_mirror_swaps_arcs` may already pass because Task 4 swaps arcs; it stays as a guard.

- [ ] **Step 3: Implement** — replace `addLine` in `post/busellato-cnc90.cps`:

```javascript
function collinear(a, b, c) {
  var tol = getProperty("mergeTolerance");
  var acx = c.x - a.x, acy = c.y - a.y, acz = c.z - a.z;
  var abx = b.x - a.x, aby = b.y - a.y, abz = b.z - a.z;
  var len2 = acx * acx + acy * acy + acz * acz;
  if (len2 < 1e-12) {
    return false;
  }
  var t = (abx * acx + aby * acy + abz * acz) / len2;
  if (t <= 0 || t >= 1) {                 // b must lie strictly between a and c: no reversals
    return false;
  }
  var cx = aby * acz - abz * acy, cy = abz * acx - abx * acz, cz = abx * acy - aby * acx;
  return Math.sqrt(cx * cx + cy * cy + cz * cz) / Math.sqrt(len2) <= tol;
}

function addLine(p0, p1, feed) {
  var f = feedOut(feed);
  var last = moves.length ? moves[moves.length - 1] : null;
  if (last && last.kind == "G1" && last.f == f && collinear(last.start, last.end, p1)) {
    last.end = {x: p1.x, y: p1.y, z: p1.z};
    return;
  }
  moves.push({kind: "G1", start: {x: p0.x, y: p0.y, z: p0.z}, end: {x: p1.x, y: p1.y, z: p1.z}, f: f});
}
```

and at the end of `onClose`:

```javascript
  if (n > getProperty("lineWarning")) {
    warning("Program has " + n + " lines; the largest program this machine is known to run has about 250 lines.");
  }
```

- [ ] **Step 4: Run** — every case and test passes. Then `python3 -m unittest discover -s tests` for the whole suite.
- [ ] **Step 5: Commit** — `git commit -am "Post: collinear merge, mirror Y, feed unit, G55, line warning"`.

---

### Task 8: Machine test programs, run sheet, README

**Files:**
- Create: `post/machine-tests/ZZT1`, `ZZT1A`, `ZZT2A`, `ZZT3A`, `ZZT3B`, `ZZT3C`, `ZZT3D`, `post/machine-tests/RUN-SHEET.md`
- Create: `post/README.md`
- Test: `tests/test_machine_tests.py`

**Interfaces:**
- Consumes: the finished post (Tasks 3–7), `check_cnc90.check`, `hdd/LISTING.TXT`.

- [ ] **Step 1: Write the failing test** — `tests/test_machine_tests.py`:

```python
import os
import re
import sys
import unittest

from helpers import REPO, TOOLS

sys.path.insert(0, TOOLS)
import check_cnc90  # noqa: E402

DIR = os.path.join(REPO, 'post', 'machine-tests')
NAMES = ['ZZT1', 'ZZT1A', 'ZZT2A', 'ZZT3A', 'ZZT3B', 'ZZT3C', 'ZZT3D']


class MachineTestProgramsTest(unittest.TestCase):
    def test_programs_valid(self):
        for n in NAMES:
            with open(os.path.join(DIR, n), 'rb') as fh:
                self.assertEqual(check_cnc90.check(fh.read(), n), [], n)

    def test_names_not_on_machine(self):
        with open(os.path.join(REPO, 'hdd', 'LISTING.TXT'), encoding='cp850') as fh:
            listing = fh.read()
        in_z = re.search(r'Directory di C:\\CNC90\\MOD1\\SORG\\SRG\\Z\r?\n(.*?)(?:\r?\n\s*Directory di|\Z)',
                         listing, re.S).group(1)
        existing = {l.split()[0] for l in in_z.splitlines() if l.strip() and not l.startswith(' ')}
        for n in NAMES:
            self.assertNotIn(n, existing, n)

    def test_air_programs_stay_high(self):
        # "A" programs: stock thickness 60 in G71, max depth 2 -> tool stays >= 58 mm above the table
        for n in [x for x in NAMES if x != 'ZZT1']:
            with open(os.path.join(DIR, n), 'rb') as fh:
                lines = fh.read().decode('ascii').split('\r\n')[:-1]
            self.assertTrue(lines[0].startswith('G71') and 'Z60T00' in lines[0], n)
            for l in lines[2:-1]:
                depth = re.search(r'Z([\d.]+)$', l)
                if depth:
                    self.assertLessEqual(float(depth.group(1)), 2, f'{n}: {l}')


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Confirm red** — files missing.

- [ ] **Step 3: Generate the programs** with David's help in Fusion (or through the MCP on a copy of the test document):
  - `ZZT1` (real cut): the test piece — operations `LSHAPE` (depth 2 mm) + `DRILL` (depth 2 mm), stock 400×300×18, program name `ZZT1`.
  - `ZZT1A` (air): same operations, stock thickness set to **60** (virtual; no panel on the table), depth 2 mm.
  - `ZZT2A` (feed timing): one straight 2D contour line 500 mm long along X at Y150, T65, feed 1000 mm/min (`F1`), stock thickness 60, depth 2.
  - `ZZT3A`–`ZZT3D` (point rate): a Ø200 circle contour, T65, feed 3000 mm/min, stock thickness 60, depth 2; `ZZT3A` arcs, `ZZT3B` lines with segment 5, `ZZT3C` segment 2, `ZZT3D` segment 1.
  Copy each output into `post/machine-tests/` under its program name (no extension).

- [ ] **Step 4: Write `post/machine-tests/RUN-SHEET.md`**:

```markdown
# Machine test run sheet (first visit with the post-processor)

Rules at the machine: never type FORMAT, DEL, CHKDSK /F, or SALVAINC; the only
writes to C: are the new ZZT* files below. Photograph anything unexpected.
Hand on the emergency stop for every run. Feed override at minimum for the first run.

Copy (per program, from the shuttle diskette):
    COPY A:\ZZT1 C:\CNC90\MOD1\SORG\SRG\Z\ZZT1

| # | Program | Panel on table | Watch / measure | Result |
|---|---|---|---|---|
| 1 | ZZT1A | none | Does it compile and appear in the program list? | |
| 2 | ZZT1A | none | Origin corner, Y direction, arc direction, order. Tool must stay ~58 mm above the table. If it goes lower, STOP: the Z reference is not "table + G71 thickness" | |
| 3 | ZZT2A | none | Stopwatch over the 500 mm line: 30 s → F is m/min; 0.03 s → mm/min | |
| 4 | ZZT3A–D | none | Time each circle; listen for stutter. Note the finest segment that still runs smoothly | |
| 5 | ZZT1 | 18 mm scrap | Measure: L outline, arc R, hole positions (320,220) (352,220) (320,260), depth 2 | |

After the visit: set the post settings from the results (mirror Y, feed unit,
origin, line warning) and record them in post/README.md.
```

- [ ] **Step 5: Write `post/README.md`**:

```markdown
# Busellato S.EASY post-processor (TPA CNC90)

Fusion post for the CNC90 v3.0 control. Writes a program **source**
(text, TPA dialect of ISO G-code) that is copied onto the control and
compiled there. Spec: `docs/superpowers/specs/2026-09-25-fusion-post-design.md`.

## Install
Copy `busellato-cnc90.cps` to
`~/Library/Application Support/Autodesk/Fusion 360 CAM/Posts/` and pick
"Busellato S.EASY - TPA CNC90" in the NC program dialog.

## Setup rules in Fusion
- Stock = the panel. Setup origin on the **top** face (Z0 = panel top), X0 Y0 at the panel corner.
- Tools from the "Busellato S.EASY" library: T65 router Ø18, T66 router Ø8, T1-T30 vertical drills.
- 2D contour and 2D pocket: compensation "In computer"; pocket entry **plunge** or **ramp** (helix is refused).
- Drilling: plain "drilling - rapid out" only.
- Program name = 1-8 characters A-Z 0-9 _ - ; it becomes the file name on the machine.

## Settings
| Setting | Default | Meaning |
|---|---|---|
| Feed unit | m/min | F1 = 1 m/min (confirm on the machine) |
| Origin | G54 | G55 selectable |
| Mirror Y | off | if the machine's Y runs opposite to Fusion's |
| Arc output | arcs | "lines" = emergency fallback |
| Segment length | 2 mm | only for arc output = lines |
| Merge tolerance | 0.05 mm | collinear moves merged |
| Warn above N lines | 250 | largest known program ~250 lines |
| Max depth below stock | 5 mm | protects the spoilboard |
| Allowed tool numbers | 1-30,65,66 | extend when more tools are mapped |

## Getting a program onto the machine
1. Post in Fusion; copy the file to the shuttle diskette (Mac: format first, see `hdd/COPY-PLAN.md`).
2. At the DOS prompt: `COPY A:\<NAME> C:\CNC90\MOD1\SORG\SRG\<first letter>\<NAME>` —
   **check first** that `<NAME>` does not exist (`DIR C:\CNC90\MOD1\SORG\SRG\<letter>\<NAME>`).
3. Start CNC90 (`CNC90`), compile the program ("Programma Kompileren"), run it.

## Tests
`python3 -m unittest discover -s tests` (format checker on the 118 machine
programs, post cases, machine test programs). See `post/tests/`.
```

- [ ] **Step 6: Run** — `python3 -m unittest discover -s tests` → all pass.
- [ ] **Step 7: Commit** — `git add post/ tests/test_machine_tests.py && git commit -m "Machine test programs, run sheet and post README"`.
