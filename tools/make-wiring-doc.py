#!/usr/bin/env python3
"""Write docs/electrical/ptp1000-wiring-maps.md.

The pin tables are transcribed by hand from pages 12-16 and 20 of
docs/vendor/tpa-ptp1000-wiring-and-boards.pdf (the printed forms are blank apart
from pin and signal name). The I/O names come from DEF.0D, captured in H04.
Run:  python3 -I tools/make-wiring-doc.py
"""
import re
from pathlib import Path

repo = Path(__file__).resolve().parent.parent
out = repo / 'docs' / 'electrical' / 'ptp1000-wiring-maps.md'
defs = repo / 'disks' / 'H04' / 'files' / 'PTP0' / 'DEF.0D'

# ---- DEF.0D: code = bit * 1000 + port ------------------------------------
codes = {}
section = None
for line in defs.read_bytes().decode('cp437').replace('\r', '').split('\n'):
    if 'CODICI DI INPUT' in line:
        section = 'in'
    elif 'CODICI DI OUTPUT' in line:
        section = 'out'
    m = re.match(r'^(\S+)\s+(\d{4})\s*;(.*)$', line)
    if section and m:
        name, code, desc = m.group(1), int(m.group(2)), m.group(3).strip()
        codes[(section, code % 1000, code // 1000)] = (name, desc)

# ---- pin tables (pin, signal) in the order printed on the forms ----------
def pairs(*items):
    return list(items)

CU1 = [('14A/Z', 'INP00'), ('14C/D', 'INP01'), ('16A/Z', 'INP02'), ('16C/D', 'INP03'),
       ('10A/Z', 'INP04'), ('10C/D', 'INP05'), ('12A/Z', 'INP06'), ('12C/D', 'INP07'),
       ('6A/Z', 'INP08'), ('6C/D', 'INP09'), ('8A/Z', 'INP10'), ('8C/D', 'INP11'),
       ('2A/Z', 'INP12'), ('2C/D', 'INP13'), ('4A/Z', 'INP14'), ('4C/D', 'INP15'),
       ('28C/D', 'INP20'), ('28A/Z', 'INP21'), ('26C/D', 'INP22'), ('26A/Z', 'INP23'),
       ('18A/Z', 'field supply if NPN'), ('18C/D', 'field GND if PNP'),
       ('24C/D', 'encoder supply'), ('24A/Z', 'encoder GND'),
       ('20A/Z', 'encoder X phase 1'), ('20C/D', 'encoder X phase 2'),
       ('22A/Z', 'encoder Y phase 1'), ('22C/D', 'encoder Y phase 2'),
       ('30A/Z', 'VOUT reference X'), ('32C/D', 'GND reference X'),
       ('32A/Z', 'VOUT reference Y'), ('30C/D', 'GND reference Y')]

CU2 = [('30C/D', 'OUT00'), ('32A/Z', 'OUT01'), ('32C/D', 'OUT02'), ('28A/Z', 'OUT03'),
       ('28C/D', 'OUT04'), ('30A/Z', 'OUT05'), ('24C/D', 'OUT06'), ('26A/Z', 'OUT07'),
       ('26C/D', 'OUT08'), ('22A/Z', 'OUT09'), ('22C/D', 'OUT10'), ('24A/Z', 'OUT11'),
       ('18C/D', 'OUT12'), ('20A/Z', 'OUT13'), ('20C/D', 'OUT14'), ('14A/Z', 'OUT15'),
       ('14C/D', 'OUT16'), ('18A/Z', 'OUT17'), ('8C/D', 'OUT18'), ('10A/Z', 'OUT19'),
       ('10C/D', 'OUT20'), ('6A/Z', 'OUT21'), ('6C/D', 'OUT22'), ('8A/Z', 'OUT23'),
       ('2A/Z', 'field supply'), ('2C/D', 'field supply'),
       ('4A/Z', 'field GND'), ('4C/D', 'field GND'),
       ('12C/D', 'INP16'), ('12A/Z', 'INP17'), ('16C/D', 'INP18'), ('16A/Z', 'INP19')]

CU3 = [('14C/D', 'INP24'), ('14A/Z', 'INP25'), ('12C/D', 'INP26'), ('12A/Z', 'INP27'),
       ('10A/Z', 'field supply if NPN'), ('10C/D', 'field GND if PNP'),
       ('26A/Z', 'encoder supply'), ('26C/D', 'encoder supply'),
       ('28A/Z', 'encoder GND'), ('28C/D', 'encoder GND'),
       ('20A/Z', 'encoder Z phase 1'), ('20C/D', 'encoder Z phase 2'),
       ('22A/Z', 'encoder W phase 1'), ('22C/D', 'encoder W phase 2'),
       ('24A/Z', 'encoder V phase 1'), ('24C/D', 'encoder V phase 2'),
       ('2A/Z', 'VOUT reference W'), ('2C/D', 'GND reference W'),
       ('4A/Z', 'VOUT reference Z'), ('4C/D', 'GND reference Z'),
       ('8A/Z', 'VOUT reference V'), ('8C/D', 'GND reference V'),
       ('6A/Z', 'VOUT analog output U'), ('6C/D', 'GND analog output U'),
       ('16A/Z', '(blank on form)'), ('16C/D', '(blank on form)'),
       ('18A/Z', '(blank on form)'), ('18C/D', '(blank on form)'),
       ('30A/Z', 'GND 5V feed rate'), ('30C/D', 'feed rate analog input'),
       ('32A/Z', '(blank on form)'), ('32C/D', '+5V feed rate supply')]

CU8 = [('2A/Z', '1000'), ('2C/D', '1001'), ('4A/Z', '1002'), ('4C/D', '1003'),
       ('6A/Z', '1004'), ('6C/D', '1005'), ('8A/Z', '1006'), ('8C/D', '1007'),
       ('32A/Z', 'common 1000-1003'), ('32C/D', 'common 1004-1007'),
       ('10A/Z', '1008'), ('10C/D', '1009'), ('12A/Z', '1010'), ('12C/D', '1011'),
       ('14A/Z', '1012'), ('14C/D', '1013'), ('16A/Z', '1014'), ('16C/D', '1015'),
       ('30A/Z', 'common 1008-1011'), ('30C/D', 'common 1012-1015'),
       ('18A/Z', '1016'), ('18C/D', '1017'), ('20A/Z', '1018'), ('20C/D', '1019'),
       ('22A/Z', '1020'), ('22C/D', '1021'), ('24A/Z', '1022'), ('24C/D', '1023'),
       ('28A/Z', 'common 1016-1019'), ('28C/D', 'common 1020-1023'),
       ('26A/Z', 'GND (24 VDC) from field'), ('26C/D', '+24 VDC / 1 A from field')]

CU9 = [('2C/D', '1024'), ('2A/Z', '1025'), ('4C/D', '1026'), ('4A/Z', '1027'),
       ('6C/D', '1028'), ('6A/Z', '1029'), ('8C/D', '1030'), ('8A/Z', '1031'),
       ('26A/Z', 'common 1024-1027'), ('26C/D', 'common 1028-1031'),
       ('10C/D', '1032'), ('10A/Z', '1033'), ('12C/D', '1034'), ('12A/Z', '1035'),
       ('14C/D', '1036'), ('14A/Z', '1037'), ('16C/D', '1038'), ('16A/Z', '1039'),
       ('30A/Z', 'common 1032-1035'), ('30C/D', 'common 1036-1039'),
       ('18C/D', '1040'), ('18A/Z', '1041'), ('20C/D', '1042'), ('20A/Z', '1043'),
       ('22C/D', '1044'), ('22A/Z', '1045'), ('24C/D', '1046'), ('24A/Z', '1047'),
       ('28A/Z', 'common 1040-1043'), ('28C/D', 'common 1044-1047'),
       ('32A/Z', 'input common'), ('32C/D', 'input common')]


def table(rows, header=('Pin', 'Signal')):
    lines = ['| ' + ' | '.join(header) + ' |', '|' + '---|' * len(header)]
    lines += ['| ' + ' | '.join(r) + ' |' for r in rows]
    return '\n'.join(lines)


def inferred(rows):
    """PTP200 INPnn / OUTnn -> DEF.0D name, if the code layout holds."""
    res = []
    for pin, sig in rows:
        m = re.match(r'^(INP|OUT)(\d\d)$', sig)
        if not m:
            continue
        n = int(m.group(2))
        if m.group(1) == 'INP':
            port, bit, kind = n // 8, n % 8, 'in'
        else:
            port, bit, kind = 16 + n // 8, n % 8, 'out'
        name, desc = codes.get((kind, port, bit), ('', ''))
        code = f'{bit}{port:03d}'
        res.append((sig, pin, code, name or '(not defined)', desc))
    return res


doc = f"""# PTP1000 wiring maps (transcribed)

Source: `docs/vendor/tpa-ptp1000-wiring-and-boards.pdf`, pages 12 to 16 and 20
(TPA "Sistema PTP1000, mappe di cablaggio"). Generated by
`tools/make-wiring-doc.py`; I/O names come from `DEF.0D` (disk H04, `C:\\PTP0\\`).

## What these maps are, and are not

- They are **blank forms**. Each page prints the connector, the pin and the
  board's generic signal name (`INP00`, `OUT00`, encoder phase 1, ...). The columns
  that would say what is wired to it (BIT/PORTO, CODE, WIRE, DESCRIZIONE) are
  **empty on every page**.
- So they give the **board connector pinout**, not the machine's wiring. What is
  actually connected to each pin is still unknown and needs the machine visit
  (`connector-inventory.md`).
- Pin labels such as `14A/Z` and `14C/D` are copied as printed. They look like a
  DIN 41612 style row with two pins per label; the scan does not say whether the two
  pins are tied together, so check the connector before assuming either way.
- Transcribed by reading the scan; check against the paper before relying on any
  single pin.

## Reading the I/O codes (page 20, and `DEF.0D`)

Page 20 says the BIT/PORTO column holds "the bit number (0 to 7) followed by the
port number (000 to 255)", and CODE the symbolic name defined in the I/O definitions
file. In `DEF.0D` a code is therefore `bit x 1000 + port`: `4002` is bit 4 of
port 2 (`EMERGPA`, air pressure emergency). Inputs use ports 0 to 4, outputs
ports 16 to 24 in this file.

Notes from page 20:

- Inputs are NPN or PNP. For NPN, tie the input commons to +24 V; for PNP, to GND.
  On pins with two names in one box, connect field supply (NPN) or field GND (PNP).
- Encoder zero marks (if the PTP200N board is set up for it): X on CU1 26C/D (INP22),
  Y on CU1 26A/Z (INP23), Z on CU3 14A/Z (INP25), W on CU3 12C/D (INP26),
  V on CU3 12A/Z (INP27).

## Axes, from page 19 and the maps

- Each axis: **incremental encoder** (phase 1, phase 2, zero mark, supply, GND) in, and an
  analog **voltage reference** (VOUT and GND) out to the drive, both shielded.
  This answers README questions 1 and 2 as far as the control side goes.
- X and Y are on the PTP200 board (CU1); Z, W, V on the ESPAS board (CU3);
  U has only an analog output (CU3).
- Page 19 is a generic drawing (June 1988) and shows other pin numbers than the
  maps; trust the maps for pins.
- The feed-rate potentiometer comes in on CU3 (30A/Z to 32C/D).

## CU1: PTP200 board 05.127R2, inputs INP00 to INP23 (part), encoders X/Y, references X/Y

{table(CU1)}

## CU2: PTP200 board 05.127R2, outputs OUT00 to OUT23, inputs INP16 to INP19

{table(CU2)}

## CU3: ESPAS board 05.125R4, inputs INP24 to INP27, encoders Z/W/V, references W/Z/V, analog U, feed rate

{table(CU3)}

## CU8: IOMOD board 05.155, inputs 1000 to 1023 (plugs 1 to 3)

{table(CU8)}

## CU9: IOMOD board 05.155, inputs 1024 to 1047 (plugs 4 to 6)

{table(CU9)}

## Which pin is which machine signal: inferred, NOT verified

If the PTP200's inputs and outputs follow the port layout in `DEF.0D`
(INP00 = port 0 bit 0, ..., OUT00 = port 16 bit 0, ...), this is what each pin would carry.
It matches in count (24 outputs = ports 16 to 18) but nothing on the forms confirms it.
**Check each one with a meter at the machine before using it.** The IOMOD inputs
(1000 to 1047) cannot be matched this way: how they map to ports is not stated anywhere I have.

{table([(a, b, c, d, e) for a, b, c, d, e in inferred(CU1 + CU2 + CU3)], ('Board signal', 'Pin', 'Code', 'DEF.0D name', 'Description (Italian)'))}

Things that stand out (all depend on the inference above):

- INP20 to INP23 would be the four emergency-type inputs: air pressure, axis drives, inverter
  and general emergency. That grouping is a point in favour of the layout being right.
- INP22 and INP23 are also the pins page 20 gives for the X and Y encoder zero marks
  (CU1 26C/D and 26A/Z). If they carry the inverter and general emergency signals, the zero
  marks cannot be in use on X and Y, which fits homing with the setpoint photocells
  (`FCSPX`, `FCSPY`). Confirm before wiring anything to these pins.
- The safety inputs are read by the control. Per the README, a new controller sits alongside
  the hardwired safety chain, not inside it, so these signals still need tracing to the
  contactors and emergency stop.
"""
out.write_text(doc, encoding='utf-8')
print(f'wrote {out}')
