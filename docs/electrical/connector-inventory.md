# Connector inventory — TPA Compact 90 cabinet

Goal: a complete list of every connector between the TPA control and the
rest of the machine, with the signal on every pin. This is the input for a
future adapter PCB: machine cables unplug from the TPA and plug into the
adapter, so the TPA stays untouched and remains the fallback.

It also answers README open questions 1, 2, 3, 4 and 5.

Status: **empty — to be filled on the next machine visit.**

## Safety while measuring

- 380V is present in the cabinet. Continuity and pin tracing: **main switch
  off and locked out.**
- Live measurements only on low-voltage signal pins (analog command, encoder,
  24V I/O), probing at connector backshells or terminal strips, never inside
  the drives or the power section.
- Do not unplug anything while powered. Photograph before unplugging;
  replug exactly as found.
- Do not force the machine into an error state to observe a signal.

## Bring

- [ ] Multimeter (DC V, continuity, resistance)
- [ ] Oscilloscope, or at least a logic probe (encoder signals)
- [ ] Phone camera + a ruler or coin for scale in connector photos
- [ ] Masking tape + marker for temporary labels (C01, C02, …)
- [ ] Thin probe tips / back-probe pins
- [ ] Printout of this sheet
- [ ] Shuttle diskette for the hard-disk backup batch (combine visits)

## Procedure

1. **Photograph** every side of the TPA cabinet with all cables connected.
2. **Label** each connector C01, C02, … with tape on both the plug and the
   socket. Log them in the summary table below.
3. Per connector: fill in a connector sheet (template below). Close-up
   photo of the socket face showing pin numbers, and of the cable plug.
4. **Follow each cable** to where it lands (drive, terminal strip, sensor,
   valve bank) and write that down.
5. Power off → **trace pins** by continuity from connector pin to terminal
   strip / drive terminal.
6. Power on, machine idle → **live measurements** from the checklist.
7. Upload photos to Proton Drive `busellato-cnc-images/connectors/`, named
   `C01-socket.jpg`, `C01-plug.jpg`, etc.

## Summary table

| ID  | Location on cabinet | Connector type | Pins | Gender (cabinet side) | Cable goes to | Signal group | Photo |
|-----|---------------------|----------------|------|-----------------------|---------------|--------------|-------|
| C01 |                     |                |      |                       |               |              |       |
| C02 |                     |                |      |                       |               |              |       |
| C03 |                     |                |      |                       |               |              |       |
| C04 |                     |                |      |                       |               |              |       |
| C05 |                     |                |      |                       |               |              |       |
| C06 |                     |                |      |                       |               |              |       |
| C07 |                     |                |      |                       |               |              |       |
| C08 |                     |                |      |                       |               |              |       |

Connector type examples: DB-9/15/25/37/50 (D-sub), Harting Han (+ insert
type), Amphenol/MIL circular, Phoenix terminal plug, IDC ribbon, other.

Signal groups: axis command, encoder/resolver, drive enable/ready, spindle,
digital inputs, digital outputs, safety/E-stop, power supply, serial
(COM), operator panel, unknown.

---

## Connector sheet template

Copy this block once per connector (`### C01`, `### C02`, …).

### Cxx — <short name>

- Location on cabinet:
- Connector type / series / part number printed on it:
- Pin count, gender (cabinet side):
- Backshell / locking (screws, latch, bayonet):
- Cable: conductors, shielded (Y/N), shield connected where:
- Cable goes to:
- Markings / wire numbers on the cable:
- Photos:

| Pin | Wire colour / number | Goes to (terminal / device) | Signal name | Type | Measured (idle) | Notes |
|-----|----------------------|-----------------------------|-------------|------|-----------------|-------|
| 1   |                      |                             |             |      |                 |       |
| 2   |                      |                             |             |      |                 |       |
| 3   |                      |                             |             |      |                 |       |

Type: `AO` analog out, `AI` analog in, `DI` digital in, `DO` digital out,
`ENC` encoder, `RES` resolver, `PWR` supply, `GND`, `SHLD` shield,
`SAFE` safety chain, `SER` serial, `NC` not connected.

---

## Measurement checklist

### Axis drives (AXOR ×3) — open questions 1 and 2

Per axis (X, Y, Z — note which drive is which):

- [ ] Drive model / label photo (front and side plates)
- [ ] Command input: which drive terminals come from the TPA?
- [ ] Command type: **±10V analog** (voltage changes with jog speed and
      direction) or **step/dir** (pulses, scope needed)?
- [ ] Command voltage at standstill with the axis enabled (expect ~0V, a few mV offset)
- [ ] Command voltage while jogging slowly +/− (sign and rough magnitude)
- [ ] Enable signal: pin, voltage, active high/low
- [ ] Drive ready / fault signal back to TPA: pin, voltage
- [ ] Feedback to TPA: **encoder or resolver**? Where does it come from:
      the motor, or the drive's simulated encoder output?
- [ ] Encoder: differential (A, /A, B, /B, Z, /Z) or single-ended? Supply
      voltage (5V / 12V / 24V)? Signal levels on scope?
- [ ] Encoder counts per rev (motor plate, drive setting, or TPA parameter —
      cross-check [axis-parameters.md](../../axis-parameters.md))
- [ ] Home / limit switches: which connector, NO/NC, voltage

### Spindle (Berges CO-SINUS ACI) — open question 3

- [ ] Drive label photo
- [ ] Speed reference: 0–10V, ±10V, 4–20mA, or digital (fixed speeds via inputs)?
- [ ] Reference value at two known speeds (e.g. 12000 and 18000 rpm)
- [ ] Run / direction / fault / at-speed signals: pins, voltage, polarity
- [ ] Tool clamp / tool-present sensors, if any

### Digital I/O — open question 4

- [ ] I/O voltage (expect 24V DC) and common: sinking (NPN) or sourcing (PNP)?
- [ ] Count inputs and outputs per connector
- [ ] Per output: what it drives (valve, contactor, lamp), coil voltage
- [ ] Per input: what it senses (switch, pressure, sensor), NO/NC
- [ ] Groups: boring head spindles, vacuum zones, clamps / stops, lubrication,
      operator panel buttons and lamps

### Safety chain — open question 6

- [ ] Where the E-stop chain passes through the TPA (if at all): pins
- [ ] Safety relay / contactor model(s)
- [ ] Which signals tell the TPA "safety OK"
- [ ] Anything the TPA must actively hold for the machine to run (watchdog,
      "CNC ready" output) — the adapter must reproduce this

### Power and other

- [ ] Supplies coming into the TPA: voltages and on which connector
- [ ] Serial ports (COM1 / COM2): which are cabled, and to what
- [ ] Operator panel / handwheel connections
- [ ] Any connector whose purpose can't be found: mark `unknown`, photograph, move on

### Schematics — open question 5

- [ ] Check inside the cabinet doors, pockets and binders for schematics
- [ ] Note any drawing numbers or TPA/Busellato document references seen on labels
