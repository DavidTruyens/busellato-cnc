#!/usr/bin/env python3
# Usage (from repo root): python3 tools/copy-plan.py  -> writes hdd/COPY-PLAN.md
"""Pack C: directories from hdd/LISTING.TXT into diskette-sized batches."""
import re, sys
from collections import OrderedDict
CAP = 1_300_000          # usable bytes per 1.44 MB diskette, with margin
CL = 512                 # floppy cluster size
text = open('hdd/LISTING.TXT', encoding='cp850').read().replace('\r', '')
dirs = OrderedDict(); cur = None
for l in text.split('\n'):
    m = re.match(r'\s*Directory di (.*)', l)
    if m: cur = m.group(1).strip(); dirs[cur] = []; continue
    m = re.match(r'^(\S+)\s+(\S*)\s+(\d+)\s+\d\d-\d\d-\d\d', l)
    if m and cur: dirs[cur].append((m.group(1) + ('.' + m.group(2) if m.group(2) else ''), int(m.group(3))))
def cost(files, ndirs=1):
    return sum(max(1, -(-s // CL)) * CL for _, s in files) + ndirs * CL * (1 + len(files) * 32 // CL)
order = ['C:\\CNC90\\MOD1\\USER', 'C:\\PTP0', 'C:\\PTPSYS', 'C:\\PTP1000', 'C:\\CNC90\\LINGUE',
         'C:\\CNC90\\MOD1\\SORG', 'C:\\CNC90\\MOD1\\COMP', 'C:\\CNC90\\MOD1', 'C:\\CNC90', 'C:\\CHECKIT', 'C:\\DOS5', 'C:\\']
def rank(d):
    for i, p in enumerate(order):
        if d == p or d.startswith(p + '\\') or p == 'C:\\': return i
units = []   # (label, xcopy source pattern, dest dir, files)
for d in sorted((d for d in dirs if dirs[d]), key=lambda d: (rank(d), d)):
    files = dirs[d]; dest = 'A:' + d[2:] + '\\' if d != 'C:\\' else 'A:\\ROOT\\'
    if cost(files) <= CAP:
        units.append((d, d.rstrip('\\') + '\\*.*', dest, files)); continue
    by = OrderedDict()
    for f in files: by.setdefault(f[0][0], []).append(f)
    for letter, fs in by.items():
        units.append((d + ' ' + letter + '*', d.rstrip('\\') + '\\' + letter + '*.*', dest, fs))
batches = [[]]
for u in units:
    if batches[-1] and cost([f for x in batches[-1] for f in x[3]], len(batches[-1])) + cost(u[3]) > CAP:
        batches.append([])
    batches[-1].append(u)
out = ['# Hard disk copy plan', '',
       'Generated from `hdd/LISTING.TXT` (DIR C:\\ /S, 2026-09-25). One batch = one trip',
       'with the shuttle diskette. Nothing is deleted or written on C:.', '',
       '**Rules at the machine:** never type `FORMAT`, `DEL`, `CHKDSK /F`, a command with',
       '`C:` as destination, or `SALVAINC`. If XCOPY asks "F = file, D = directory", answer **D**.',
       'Stop and photograph anything unexpected.', '',
       '**Each trip:** Mac: format the shuttle (`diskutil unmountDisk /dev/disk4 && sudo newfs_msdos -F 12 -f 1440 -v H<nn> /dev/rdisk4`),',
       'hole closed → machine: run the batch → Mac: hole open, `tools/image-disk.sh H<nn> "batch <n>" <files>`.',
       '', 'Skipped on purpose: `IBMBIO.COM`, `IBMDOS.COM` (hidden DOS system files, recreated by `SYS`); empty folders (listed in LISTING.TXT).', '']
total_files = 0
for i, b in enumerate(batches, 1):
    n = sum(len(u[3]) for u in b); total_files += n
    kb = cost([f for u in b for f in u[3]], len(b)) // 1024
    out += [f'## Batch {i} → H{i+2:02d}  ({n} files, ~{kb} KB on diskette)', '', '```']
    out += [f'XCOPY {src} {dest} /V' for _, src, dest, _ in b]
    out += ['```', '']
out.insert(4, f'{len(batches)} batches, {total_files} files. Batch IDs start at H03 (H02 = SORG samples).\n')
open('hdd/COPY-PLAN.md', 'w').write('\n'.join(out))
print(len(batches), 'batches', total_files, 'files')
for i, b in enumerate(batches, 1): print(i, len(b), 'cmds', sum(len(u[3]) for u in b), 'files', [u[0] for u in b][:3], '...' if len(b) > 3 else '')
