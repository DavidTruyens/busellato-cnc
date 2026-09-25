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
| D01 | CNC 90 — 1 | 2026-09-25 | `cda6c8700a378ad253cabdfbe41b313cf79421ab70392317904f628ca9341812` | 0 | 28 / 28 | substituted | CNC90 root: startup `CNC90.BAT`, `SALVAINA`/`SALVAINC` save/restore scripts, editor, compiler, menu drawings |
| D02 | CNC 90 — 2 | 2026-09-25 | `01ba94adcabedbb9ed200a1d1dfd17e86e9f308ad593c2eb296a8fbd2d87d9a7` | 0 | 11 / 11 | substituted | CNC90 programs: `GO_CNC90`, parameter/list/part editors (`EDIPAR`, `EDILIST`, `EDIPART`), diagnostics (`MANDIAG`) |
| D03 | CNC 90 — 3 | 2026-09-25 | `b1d6a03b3487544fc113955ed897cfc3680c8ef8dfa0d1153755a6e08e02672e` | 0 | 7 / 7 | substituted | CNC90 programs: `PLANCIA`, `VENTOSE` (vacuum cups), `WORK`, `SPY`, `PRINTDIR` |

Photo of the set: `2026-09-25_diskettes-set-of-7.jpg`.
