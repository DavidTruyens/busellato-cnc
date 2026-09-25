#!/usr/bin/env python3
"""Helpers for imaging 3.5" 1.44 MB DOS diskettes.

See docs/superpowers/specs/2026-09-25-disk-capture-design.md.

  diskimg.py work IMG OUT        write a mtools-readable working copy of IMG
  diskimg.py bad-bytes MAP       bytes not rescued according to a ddrescue map
  diskimg.py find-floppy         read `diskutil list external physical` on stdin
"""
import re
import struct
import sys

SECTOR = 512
IMG_SIZE = 2880 * SECTOR
FAT_SECTORS = 9


def standard_boot_sector():
    """Boot sector of a standard DOS 1.44 MB floppy (no boot code)."""
    bs = bytearray(SECTOR)
    bs[0:3] = b'\xEB\x3C\x90'
    bs[3:11] = b'MSDOS5.0'
    # bytes/sector, sectors/cluster, reserved, FATs, root entries,
    # total sectors, media, sectors/FAT, sectors/track, heads, hidden, large total
    struct.pack_into('<HBHBHHBHHHII', bs, 11,
                     512, 1, 1, 2, 224, 2880, 0xF0, 9, 18, 2, 0, 0)
    bs[510:512] = b'\x55\xAA'
    return bytes(bs)


def _bpb_ok(sector0):
    if sector0[510:512] != b'\x55\xAA':
        return False
    bps, _spc, res, nfats, _roots, total, media, spf = struct.unpack_from(
        '<HBHBHHBH', sector0, 11)
    return (bps, res, nfats, total, media, spf) == (512, 1, 2, 2880, 0xF0, 9)


def classify(data):
    """'ok', 'substitute' (sector 0 overwritten, FATs intact) or 'unrecognised'."""
    if len(data) != IMG_SIZE:
        return 'unrecognised'
    if _bpb_ok(data[:SECTOR]):
        return 'ok'
    fat1 = data[SECTOR:SECTOR * (1 + FAT_SECTORS)]
    fat2 = data[SECTOR * (1 + FAT_SECTORS):SECTOR * (1 + 2 * FAT_SECTORS)]
    if fat1[:3] == b'\xF0\xFF\xFF' and fat1 == fat2:
        return 'substitute'
    return 'unrecognised'


def make_working(data):
    """Return (image, status). Never modifies `data`.

    A short image (ddrescue could not read the end of the disk) is padded
    with zeros; the ddrescue map records which sectors those are.
    """
    if len(data) < IMG_SIZE and len(data) % SECTOR == 0:
        data = data + bytes(IMG_SIZE - len(data))
    status = classify(data)
    if status == 'ok':
        return data, 'ok'
    if status == 'substitute':
        return standard_boot_sector() + data[SECTOR:], 'substituted'
    raise ValueError('not a recognisable 1.44 MB FAT12 image')


def bad_bytes(map_text):
    """Sum of block sizes in a ddrescue map whose status is not '+'."""
    lines = [l for l in map_text.splitlines() if l.strip() and not l.startswith('#')]
    total = 0
    for line in lines[1:]:  # lines[0] is the current_pos/status/pass line
        _pos, size, status = line.split()[:3]
        if status != '+':
            total += int(size, 16)
    return total


def find_floppy(diskutil_text):
    """/dev/diskN of the single external physical disk of 1.4-1.5 MB."""
    found = []
    for block in re.split(r'^(?=/dev/disk\d+ )', diskutil_text, flags=re.M):
        head = re.match(r'(/dev/disk\d+) \(external, physical\)', block)
        if not head:
            continue
        size = re.search(r'\*([\d.]+)\s*(KB|MB|GB|TB)', block)
        if size and size.group(2) == 'MB' and 1.4 <= float(size.group(1)) <= 1.5:
            found.append(head.group(1))
    if len(found) != 1:
        raise LookupError(f'expected exactly one 1.44 MB floppy, found {len(found)}: {found}')
    return found[0]


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ''
    if cmd == 'work' and len(argv) == 4:
        with open(argv[2], 'rb') as f:
            data = f.read()
        try:
            out, status = make_working(data)
        except ValueError as e:
            print(f'error: {argv[2]}: {e}', file=sys.stderr)
            return 2
        with open(argv[3], 'wb') as f:
            f.write(out)
        print(status)
        return 0
    if cmd == 'bad-bytes' and len(argv) == 3:
        with open(argv[2]) as f:
            print(bad_bytes(f.read()))
        return 0
    if cmd == 'find-floppy' and len(argv) == 2:
        try:
            print(find_floppy(sys.stdin.read()))
        except LookupError as e:
            print(f'error: {e}', file=sys.stderr)
            return 2
        return 0
    print(__doc__, file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
