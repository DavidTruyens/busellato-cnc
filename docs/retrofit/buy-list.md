# Busellato S.EASY — buy list

The buy list lives in a Google Sheet, shared with the machine owner:
**[Busellato S.EASY - buy list](https://docs.google.com/spreadsheets/d/1mgyK7yOsuJX0RepOMAWNcIIysELuvGcH3JSw95iiXVA/edit)**
(in the project's Google Drive folder). The sheet is the source: parts,
prices, suppliers, status and totals are kept there, not here.

Groups in the sheet:

- **A** — keep the old control running and back it up (keyboard, IDE adapter)
- **B** — new controller (LinuxCNC), phase 1: axes X/Y/Z and spindle
- **C** — options that depend on the drive data and on phase 2 (machine I/O)
- **D** — optional extras (e.g. a wireless hand controller)

## Why the 7I97T

From the TPA wiring maps (`docs/vendor/tpa-ptp1000-wiring-and-boards.pdf`):
each axis gets an analog voltage reference (`VOUT RIFERIMENTO` + GND) and
returns a single-ended incremental encoder (phase 1, phase 2, zero mark, +V,
GND; supply selectable 5 V or 12 V on the TPA board). The 7I97T provides
exactly that per axis, plus spare channels and an expansion port for the
machine I/O.

## Order of work

1. Back up the hard disk completely (keyboard → Gotek, or the IDE adapter →
   disk image). If the keyboard cannot be revived, the disk image is the only
   way back, so it comes before any rewiring.
2. Bench-test the PC + 7I97T without touching the machine.
3. Read the drive data, then one axis at a time with a working emergency stop.
