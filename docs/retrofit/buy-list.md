# Buy list

Status as of 2026-10-02. Prices are rough estimates, not checked against a shop.

## A. Keep the old control running and back it up

| # | Part | What to look for | ~Price | Status |
|---|---|---|---|---|
| 1 | PS/2 → AT keyboard adapter (5-pin DIN male → 6-pin mini-DIN female) | | €5 | ordered |
| 2 | PS/2 keyboard | A real PS/2 keyboard; USB keyboards with a PS/2 adapter often fail on 286-era controllers | €15–25 | to order |
| 3 | USB → IDE adapter with its own 12 V power supply | For 3.5" drives with one 40-pin ribbon (IDE). Check the drive first: two ribbons (34 + 20 pin) = MFM, and this adapter will not work | €15–25 | to order |
| 4 | *(optional)* CompactFlash card ≥ 256 MB + CF-to-IDE (40-pin) adapter | Solid-state replacement for the hard disk, written from the disk image | €15–30 | optional |

## B. New controller (LinuxCNC), phase 1: axes X/Y/Z + spindle

| # | Part | What to look for | ~Price |
|---|---|---|---|
| 5 | Mesa 7I97T | Ethernet analog servo interface: 6× ±10 V + enable, 6 encoder inputs (differential or single-ended), 16 isolated inputs, 6 isolated outputs, RS-422 expansion | €230–280 |
| 6 | PC for LinuxCNC | x86 (Intel), ≥ 4 GB RAM, SSD, **two wired Ethernet ports** (one dedicated to the Mesa board; Intel NIC preferred) | €150–300 |
| 7 | 5 V DIN-rail power supply, ≥ 2 A | Logic power for the 7I97T | €20–30 |
| 8 | Monitor + USB keyboard/mouse | Replaces the CRT | €100–150 |
| 9 | Short Cat5e/6 Ethernet cable | PC ↔ 7I97T | €5 |
| 10 | Shielded twisted-pair cable, e.g. LiYCY 4×2×0.25 mm², ~20 m | ±10 V commands and encoders | €40–60 |
| 11 | Small parts | 35 mm DIN rail, ferrules, cable ties, DIN terminals | €20–30 |

Totals: A (without item 4) ≈ €35–55. B ≈ €570–900.

## C. Wait for the drive data

Needed first: photos of the AXOR and Berges type labels, the label above the
Berges control strip, and the jumpers P10/P16–P19 on the PTP200N board (or a
voltage measurement on CU1 pins 24C/D vs 24A/Z).

- Encoder level converter or a 12 V encoder supply, if the encoders are 12 V
- Interface (relays or optocouplers) for drive enable and spindle start
- Connectors/adapters to the existing wiring
- Phase 2 I/O expansion (tool valves, motors, sensors; see the `DEF.0` list in `docs/vendor/`)

## Why the 7I97T

From the TPA wiring maps (`docs/vendor/tpa-ptp1000-wiring-and-boards.pdf`):
each axis gets an analog voltage reference (`VOUT RIFERIMENTO` + GND) and
returns a single-ended incremental encoder (phase 1, phase 2, zero mark, +V,
GND; supply selectable 5 V or 12 V on the TPA board). The 7I97T provides
exactly that per axis, plus spare channels and an expansion port for the
machine I/O.
