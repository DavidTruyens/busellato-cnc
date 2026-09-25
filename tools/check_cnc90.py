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
