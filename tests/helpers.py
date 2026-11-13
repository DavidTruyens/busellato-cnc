"""Test helpers: build synthetic 1.44 MB floppy images with mtools; put a bit in a head."""
import dataclasses
import os
import subprocess
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, 'tools')
IMG_SIZE = 1474560


def make_floppy(path, files, mtime=None):
    """Create a formatted 1.44 MB image at `path` containing `files`.

    `files` maps DOS paths like 'CNC90.BAT' or 'SUB DIR/X.TXT' to bytes.
    `mtime` (epoch seconds) is applied to every file if given.
    """
    subprocess.run(['mformat', '-i', path, '-C', '-f', '1440', '::'],
                   check=True, capture_output=True)
    made = set()
    with tempfile.TemporaryDirectory() as tmp:
        for name, data in files.items():
            parts = name.split('/')
            for i in range(1, len(parts)):
                d = '/'.join(parts[:i])
                if d not in made:
                    subprocess.run(['mmd', '-i', path, '::/' + d],
                                   check=True, capture_output=True)
                    made.add(d)
            src = os.path.join(tmp, 'f')
            with open(src, 'wb') as f:
                f.write(data)
            if mtime is not None:
                os.utime(src, (mtime, mtime))
            subprocess.run(['mcopy', '-m', '-i', path, src, '::/' + name],
                           check=True, capture_output=True)
            os.remove(src)


def read_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def write_bytes(path, data):
    with open(path, 'wb') as f:
        f.write(data)


def read_text(path):
    with open(path) as f:
        return f.read()


def write_text(path, text):
    with open(path, 'w') as f:
        f.write(text)


def put_bit(settings, head: int, **numbers):
    """Put a new bit in `head` of settings.tools and return it: a copy of the bit now in that
    head (or of the default table's bit of the head's first allowed type) with `numbers`
    applied, a new id and the name '<Type> <diameter>'. Only `head` changes: another head
    holding the old bit keeps it."""
    from nesting.tools import HEADS, ToolTable
    table = settings.tools
    base = table.bit_in(head)
    if base is None:
        kind = HEADS[head].allows[0]
        base = next(b for b in ToolTable.default().bits if b.type == kind)
    bit = dataclasses.replace(base, **numbers)
    bit.id = table.new_id()
    bit.name = f"{bit.type.capitalize()} {bit.diameter:g}"
    table.bits.append(bit)
    table.heads[head] = bit.id
    table.heads = dict(sorted(table.heads.items()))
    return bit
