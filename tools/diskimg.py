#!/usr/bin/env python3
"""Helpers for imaging 3.5" 1.44 MB DOS diskettes.

See docs/superpowers/specs/2026-09-25-disk-capture-design.md.

  diskimg.py work IMG OUT        write a mtools-readable working copy of IMG
  diskimg.py bad-bytes MAP       bytes not rescued according to a ddrescue map
  diskimg.py find-floppy         read `diskutil list external physical` on stdin
  diskimg.py damaged-files IMG MAP   files with data in sectors ddrescue could not read
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


def _unrescued_blocks(map_text):
    """(start, end) byte ranges in a ddrescue map whose status is not '+',
    clipped to the diskette. `ddrescue -s` adds a '?' block running from the
    end of the diskette to the largest possible offset; clipping drops it."""
    lines = [l for l in map_text.splitlines() if l.strip() and not l.startswith('#')]
    for line in lines[1:]:  # lines[0] is the current_pos/status/pass line
        pos, size, status = line.split()[:3]
        start = int(pos, 16)
        end = min(start + int(size, 16), IMG_SIZE)
        if status != '+' and start < end:
            yield start, end


def bad_bytes(map_text):
    """Bytes of the diskette that ddrescue did not rescue."""
    return sum(end - start for start, end in _unrescued_blocks(map_text))


def unread_sectors(map_text, img_len):
    """Sector numbers ddrescue did not rescue, plus any beyond a short image."""
    unread = set()
    for start, end in _unrescued_blocks(map_text):
        unread.update(range(start // SECTOR, (end + SECTOR - 1) // SECTOR))
    unread.update(range(img_len // SECTOR, IMG_SIZE // SECTOR))
    return unread


def damaged_files(data, unread):
    """Paths of files (walking the FAT12 tree of working image `data`) whose
    data or directory touches a sector in `unread`."""
    bps, spc, res, nfats, roots, _total, _media, spf = struct.unpack_from(
        '<HBHBHHBH', data, 11)
    fat = data[res * bps:(res + spf) * bps]
    root_start = res + nfats * spf
    data_start = root_start + roots * 32 // bps

    def chain(cluster):
        seen = []
        while 2 <= cluster < 0xFF0 and cluster not in seen and len(seen) < 4096:
            seen.append(cluster)
            off = cluster * 3 // 2
            if off + 1 >= len(fat):
                break
            v = fat[off] | fat[off + 1] << 8
            cluster = v >> 4 if cluster & 1 else v & 0xFFF
        return [data_start + (c - 2) * spc + i for c in seen for i in range(spc)]

    damaged = []

    def walk(sectors, prefix):
        buf = b''.join(data[s * bps:(s + 1) * bps] for s in sectors)
        for i in range(0, len(buf), 32):
            e = buf[i:i + 32]
            if e[0] == 0:
                break
            attr = e[11]
            if e[0] == 0xE5 or attr == 0x0F or attr & 0x08:
                continue
            base = e[0:8].decode('cp850').rstrip()
            ext = e[8:11].decode('cp850').rstrip()
            if base in ('.', '..'):
                continue
            name = prefix + base + ('.' + ext if ext else '')
            secs = chain(struct.unpack_from('<H', e, 26)[0])
            if unread.intersection(secs):
                damaged.append(name)
            if attr & 0x10:
                walk(secs, name + '/')

    walk(list(range(root_start, data_start)), '')
    return damaged


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
    if cmd == 'damaged-files' and len(argv) == 4:
        with open(argv[2], 'rb') as f:
            raw = f.read()
        with open(argv[3]) as f:
            unread = unread_sectors(f.read(), len(raw))
        try:
            work, _ = make_working(raw)
        except ValueError as e:
            print(f'error: {argv[2]}: {e}', file=sys.stderr)
            return 2
        for name in damaged_files(work, unread):
            print(name)
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
