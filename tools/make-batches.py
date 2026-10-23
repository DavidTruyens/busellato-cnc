#!/usr/bin/env python3
"""Write one COPY.BAT per batch of hdd/COPY-PLAN.md to hdd/batches/H<nn>.BAT.

On the Mac, after formatting diskette H<nn>:  cp hdd/batches/H<nn>.BAT /Volumes/H<nn>/COPY.BAT
On the machine (plain DOS prompt):            A:COPY
The file is written with CRLF line endings, uppercase, plain ASCII.
"""
import re
import sys
from pathlib import Path

repo = Path(__file__).resolve().parent.parent
plan = (repo / 'hdd' / 'COPY-PLAN.md').read_text(encoding='utf-8')
out = repo / 'hdd' / 'batches'
out.mkdir(exist_ok=True)

for block in re.split(r'^## Batch ', plan, flags=re.M)[1:]:
    head = re.match(r'(\d+) → (H\d+)\s+\((\d+) files', block)
    batch, label, files = head.groups()
    cmds = re.search(r'```\n(.*?)```', block, re.S).group(1).strip().splitlines()
    cmds = [c.replace(' /V', '') for c in cmds]
    lines = [
        '@ECHO OFF',
        f'REM Batch {batch} -> {label}: {files} files plus this COPY.BAT',
        'ECHO.',
        f'ECHO Batch {batch}: this diskette must be labelled {label}.',
        'VOL A:',
        'ECHO Ctrl+C to stop, any other key to copy.',
        'PAUSE > NUL',
        *cmds,
        'ECHO.',
        f'ECHO Done. Expected {files} files (+ COPY.BAT). Check the count below.',
        'DIR A: /S',
    ]
    text = '\r\n'.join(lines).upper() + '\r\n'
    text.encode('ascii')
    (out / f'{label}.BAT').write_bytes(text.encode('ascii'))
    print(f'{label}.BAT  batch {batch}  {len(cmds)} XCOPY lines', file=sys.stderr)
