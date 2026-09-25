"""Test helpers: build synthetic 1.44 MB floppy images with mtools."""
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
