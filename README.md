# busellato-cnc

Documentation and (eventually) retrofit work for a **Busellato S.EASY**
woodworking machining centre.

| | |
|---|---|
| Machine | Busellato S.EASY, matr. 3229 |
| Year | 1992 |
| Supply | 380V, 14 kW |
| Control | TPA Compact 90, matr. 87/0492, dated 9/09/92 |
| Axis drives | AXOR (3x) |
| Spindle drive | Berges CO-SINUS ACI |
| Status | **Working.** Nothing has been modified. |

## What this repo is for

Capturing everything about this machine *while it still runs*, so that a
future control retrofit starts from a known machine instead of an
archaeology project.

A retrofit is not scheduled. The trigger would be a hardware failure
(CRT, floppy controller, CPU board) or a capability the TPA control
genuinely cannot provide. "It's old" is not a trigger.

## Where things live

- **This repo** — text: notes, transcribed parameters, terminal-strip
  tables, part programs, and later any LinuxCNC config and HAL files.
- **Google Drive** — photos, video, scanned schematics, vendor PDFs and the
  shared buy list.
  <https://drive.google.com/drive/folders/13UeDKkH23NIK_m7m3_Y3FiJwd0A7dI5h>

Transcriptions belong here rather than in Drive, so that corrections to
misread values leave a history.

## Layout

```
docs/
  parameters/     transcribed from the TPA parameter screens
  electrical/     terminal strips, safety chain, connector pinouts
  drives/         AXOR and Berges settings, DIP switch positions
  io/             pneumatics, boring head, vacuum zones, I/O count
programs/         part programs recovered from floppy / COM2
disks/            byte-exact diskette images + extracted files (index in disks/README.md)
hdd/              files copied from the control's hard disk C:
tools/            imaging scripts (image-disk.sh, extract-disk.sh)
NOTES.md          running log, dated entries, newest last
```

The nesting tool (`python3 -m nesting`) that lays out parts and writes CNC90 programs is
described in [nesting/README.md](nesting/README.md).

## Open questions

These gate any parts decision. Until 1, 2 and 5 are answered, a parts
list is guesswork.

1. AXOR command input — ±10V analog, or step/dir?
2. AXOR feedback — resolver or encoder? Counts per rev?
3. Berges speed reference — 0-10V, 4-20mA, or digital?
4. Total I/O count (expect 60+)
5. Do the electrical schematics exist anywhere?
6. Is the existing safety chain fully traced?

## Notes for any future retrofit

- The new controller sits **alongside** a hardwired safety chain, never
  inside it.
- The I/O side (boring head, vacuum zones, clamps) will take longer than
  the motion side.
- Keep a measured test part cut on the original control as the accuracy
  benchmark.
