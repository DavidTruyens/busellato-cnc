# Diskettes

Byte-exact captures of every diskette belonging to the Busellato S.EASY
control. `D` = original diskettes, `H` = diskettes written from the
control's hard disk (C:).

Each `<ID>/` holds:

- `<ID>.img` — raw sector image as read by ddrescue. Never modified.
- `<ID>.map` — ddrescue map: which sectors read and which failed.
- `<ID>.dir.txt` — directory listing with the original DOS dates
  (git does not keep file dates).
- `files/` — the files extracted from the image.

Made with `tools/image-disk.sh` (read a disk) or `tools/extract-disk.sh`
(process an existing image). See
`docs/superpowers/specs/2026-09-25-disk-capture-design.md`.

**Boot sector "substituted"** means sector 0 on the original diskette had
been overwritten (on D01/D02 by a hard-disk MBR, around January 2021),
so the files were extracted from a copy with a standard 1.44 MB boot
sector. The `.img` still holds exactly what is on the diskette.

## Index

| ID | Label | Imaged | SHA-256 | Bad sectors | Files expected / found | Boot sector | Contents |
|---|---|---|---|---|---|---|---|
