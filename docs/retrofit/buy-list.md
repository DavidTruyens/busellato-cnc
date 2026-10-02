# Busellato S.EASY — buy list

Status as of 2026-10-02. Prices are indicative (checked online on 2026-10-02
where a link is given, otherwise estimated) and exclude shipping.

## A. Keep the old control running and back it up

| # | Part | What to look for | ~Price | Where | Status |
|---|---|---|---|---|---|
| 1 | PS/2 → AT keyboard adapter (5-pin DIN male → 6-pin mini-DIN female) | | €5 | [Amazon.com.be](https://www.amazon.com.be/dp/B0BXLYVZ7W) | ordered |
| 2 | PS/2 keyboard | A real PS/2 keyboard; USB keyboards with a small PS/2 adapter often fail on 286-era controllers | €15 | [Olimex PS2-KEYBOARD](https://www.olimex.com/Products/Retro-Computers/PS2-KEYBOARD/) | to order |
| 3 | USB → IDE adapter **with its own 12 V power supply** | For 3.5" drives with one 40-pin ribbon (IDE). Check the drive first: two ribbons (34 + 20 pin) = MFM, and this adapter will not work | €15–25 | [Amazon.com.be search](https://www.amazon.com.be/s?k=usb+ide+sata+adapter+12V+3.5) | to order |
| 4 | *(optional)* CompactFlash card ≥ 256 MB + CF-to-IDE (40-pin) adapter | Solid-state replacement for the hard disk, written from the disk image | €15–30 | [Amazon.com.be search](https://www.amazon.com.be/s?k=cf+to+ide+40+pin+adapter) | optional |

## B. New controller (LinuxCNC), phase 1: axes X/Y/Z + spindle

| # | Part | What to look for | ~Price | Where |
|---|---|---|---|---|
| 5 | Mesa 7I97T | Ethernet analog servo interface: 6× ±10 V + enable, 6 encoder inputs, 16 isolated inputs, 6 isolated outputs, RS-422 expansion | €315 (EU) / US$279 | [EUSurplus (EU stock)](https://eusurplus.com/index.php?route=product%2Fproduct&product_id=115) · [Mesa store (US)](https://store.mesanet.com/index.php?product_id=397&route=product%2Fproduct) |
| 6 | PC for LinuxCNC | x86 (Intel), ≥ 4 GB RAM, SSD, **two wired Ethernet ports** (one dedicated to the Mesa board; Intel NIC, e.g. i210/i226, preferred) | €150–300 | [Amazon.com.be search: mini PC dual Intel LAN](https://www.amazon.com.be/s?k=mini+pc+dual+intel+i226+lan) |
| 7 | 5 V DIN-rail power supply, ≥ 2 A — Mean Well HDR-15-5 | Logic power for the 7I97T | €15 | [TinyTronics (NL)](https://www.tinytronics.nl/en/power/power-supplies/5v/mean-well-hdr-15-5-din-rail-power-supply-5v-2.4a) |
| 8 | Monitor + USB keyboard/mouse | Replaces the CRT | €100–150 | any shop |
| 9 | Short Cat5e/6 Ethernet cable | PC ↔ 7I97T | €5 | any shop |
| 10 | Shielded twisted-pair cable, e.g. LiYCY 4×2×0.25 mm², ~20 m | ±10 V commands and encoders | €40–60 | electrical wholesaler |
| 11 | Small parts | 35 mm DIN rail, ferrules, cable ties, DIN terminals | €20–30 | electrical wholesaler |

Totals: A (without item 4) ≈ €35–45. B ≈ €650–880.

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

## Order of work

1. Back up the hard disk completely (keyboard → Gotek, or the IDE adapter →
   disk image). If the keyboard cannot be revived, the disk image is the only
   way back, so it comes before any rewiring.
2. Bench-test the PC + 7I97T without touching the machine.
3. Read the drive data, then one axis at a time with a working emergency stop.
