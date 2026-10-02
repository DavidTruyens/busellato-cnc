# Vendor documents (scanned 2026-10-02)

Paper documents found with the machine, scanned by David.

## `tpa-ptp1000-wiring-and-boards.pdf` (20 pages)

| Pages | Content |
|---|---|
| 1–7 | GPL1000 compiler listing `DEF.0` (20 Nov 1995): symbolic I/O definitions for station 0 — every input, output, counter and flag with its bit/port code and an Italian description (e.g. `EMERGPA 4002` air pressure emergency, `EVUT1..50` tool valves, `MTFRESA1..7` router motors, `FCSPX/Y/Z` axis setpoint sensors) |
| 8 | Board layout **PWA PTP200N** (drawing 01.05.127R2): the axis/I/O board. Jumpers for encoder supply (+5 V / +12 V), encoder zero mark inputs, NPN/PNP I/O, master/slave, gain and offset trimmers for axes X and Y, non-differential drive outputs |
| 9 | Board layout **PWA IOMOD 05.155**: I/O module carrier with 6 plug positions |
| 10 | Schematic **PWA-LBD MODOUTR 05.149**: 8-channel relay output module |
| 11 | Board layout **PWA ESPAS 05.125 R4** (NPN/PNP): axis extension board (axes Z, W, V, U) — encoder phase multiplication, analog outputs differential/non-differential, encoder supply |
| 12–16 | **PTP1000 wiring maps** ("mappe di cablaggio"), pin by pin: IOMOD CU8 and CU9 (inputs 1000–1047), ESPAS CU3 (encoders Z/W/V, analog references W/Z/V/U, feed-rate potentiometer), PTP200 CU2 (OUT00–OUT23, INP16–19), PTP200 CU1 (INP00–INP23, encoders X/Y, references X/Y) |
| 17–19 | TPA connection drawings (June 1988): PNP output wiring, PNP input wiring, **incremental encoder and drive wiring** |
| 20 | Notes on the wiring maps, encoder zero-mark pin assignment |

## `tpa-boards-busch-pump-main-switch.pdf` (5 pages)

| Pages | Content |
|---|---|
| 1 | Board layout **PWA HSINT 05.147** (17 Sep 1990) — likely the PC-side interface card |
| 2 | Schematic **PWA-LBD MODINP 05.150** (20 Mar 1992): 8-channel opto-isolated input module, NPN and PNP versions |
| 3–4 | Busch Seco SV/SD dry rotary vane vacuum pump: operating instructions, spare parts (filters, carbon vanes) |
| 5 | Square D class 9421 type V emergency/main switch: mounting instructions |

## What this settles for a retrofit

- **Axis drives are analog**: each axis gets a `VOUT RIFERIMENTO` (voltage reference) + GND from the TPA board to the AXOR drive input — i.e. ±10 V speed command, not step/dir (open question 1 in the main README).
- **Feedback is incremental encoders** wired to the TPA board (phase 1, phase 2, zero mark, +V, GND), not resolvers (open question 2). Counts per rev still to be read from the motors/encoders.
- **I/O is 24 V DC**, NPN or PNP selectable per board, with a full symbolic I/O list (`DEF.0`) — the basis for the I/O count (open question 4).
