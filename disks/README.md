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
| D04 | PTPSYS | 2026-09-25 | `df70a1cf7ba18aa24e1777f2d295e58a9e15cb222b3be9429a1f1543b904fd38` | 0 | 4 / 0 (4 deleted, recovered) | OK | All 4 files deleted; recovered in `D04/recovered/`, see `D04/RECOVERED.md`. Older `C:\PTPSYS\` than D14 |
| D05 | PTP0 / CARSCAR 20772 | 2026-09-25 | `18583180121338ac161a4e8a396c61136dbca52d39411caac9a4f19f74d2b304` | 704 (unused space, no file affected) | 39 / 37 ⚠ | OK | `C:\PTP0\`: machine configuration (`CONF*.PAR`), macros `*.0F`. Read as "D04", moved. Label count 39 unexplained (no deleted entries); D14's PTP0 has 39 |
| D06 | PTP1000 | 2026-09-25 | `2d0e695de577a089a6c4cd534f517af466a03e540b1f5c49f3f7d7c38654b82e` | 0 | 40 / 40 | OK | `C:\PTP1000\` |
| D07 | LINGUE — 1/1 | 2026-09-25 | `4dd6ce6d811b70cce301cd2b815a208cd4a117be5e8940fc20c8509ad26a40b4` | 0 | 75 / 75 | substituted | `C:\CNC90\LINGUE\`: language/message files |
| D12 | C:\CNC90\MOD1\USER (red label) | 2026-09-25 | `8274f038d94e659ce7f4b8182ee73e4eff603329ae9f66886d2152b72c244bdd` | 0 | no count / 93 | OK | `C:\CNC90\MOD1\USER\`: user data |
| D14 | PARAMETERS CNC, 10-22-01 (blue Sony) | 2026-09-25 | `0bf22a582b2c1c72584bf7bd247f5f8ccec8bb7bca5167331ca774df366f244b` | 0 | no count / 126 | OK | Parameter backup Oct 2001: `PTP0\` (39), `PTPSYS\` (6), `PIPPO\TOPO\USER\` (87) |

Photo of the set: `2026-09-25_diskettes-set-of-7.jpg`.
