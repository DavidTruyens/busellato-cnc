# Vacuum table model in Fusion — design

Date: 2026-09-26
Status: sections 1–2 approved in chat; section 3 (testing, measurement,
later work) written here for review

## Goal

Before a program goes to the Busellato S.EASY, see in Fusion whether the
cutter (router or drill) runs into a vacuum pod or beam under the panel.
The pod layout changes per job, so the model must be quick to re-position.

Out of scope for this version: collisions of the head bodies (spindle
housings, drill block, saw guard) with pods, beams or clamps.

## Context

- A through-cut goes 1 mm below the panel (`Z19` on 18 mm), so it cuts
  into any pod the path crosses.
- The control's own vacuum program `VENTOSE.EXE` ("SUCKERS PROGRAM")
  models the table as cross bars with suckers and reads plane length,
  bar width, bar count, sucker count, first sucker coordinate, sucker
  width/distance and an anticollision coordinate. Its parameter file
  `VENTOSE.PAR` does not exist on the machine and the vacuum values in
  `MOD1\USER\PARTEC0.PAR` are zero: the program was never configured. The
  beams and pods are positioned by hand.
- `PARTEC0.PAR` contains values 1306.5, 2600.2 and 1290.5 whose meaning
  (travel limits or field stops) is not decoded. They are hints only.
- **Feasibility confirmed 2026-09-26:** in Fusion Personal, a body set as
  a setup **fixture** makes the normal stock simulation show the tool in
  red where it enters the fixture (setup PODTEST, operation RECT-POD, body
  PodTest in the "Busselato Test" document). Toolpath generation of a 2D
  contour ignores the fixture, so the simulation is the check.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Collision check | Fusion stock simulation with beams and pods as setup fixtures | Works in Fusion Personal (confirmed) |
| How the table enters a job | A Fusion script builds it from user parameters | Layout changes per job; linked components are awkward to re-position; a script is repeatable and testable |
| Fixed machine dimensions | JSON machine file in the repo | Measured once; versioned; editable without code changes |
| Geometry logic | Plain Python module, separate from the Fusion API layer | Testable here without Fusion |
| Head collisions | Later, separate design | User's main risk is the cutter into a pod |

## Section 1 — How the table gets into a job

Per job, in the job's design:

1. Run the script "Busellato table" (Utilities → Scripts and Add-Ins).
2. First run: it creates the layout user parameters with starting values.
3. The user sets them in Fusion's Parameters dialog to match the machine.
4. Run the script again: it builds or updates the beams and pods as bodies
   in a component "Vacuum table", positioned relative to the setup's panel
   origin (G54 corner), and sets them as fixtures.
5. Simulate the setup. Red = collision.

Repository:

```
fusion/
  busellato_table/
    busellato_table.py      Fusion script entry (thin: parameters, bodies, fixtures)
    busellato_table.manifest
    table_geometry.py       pure Python: machine file + parameters -> boxes + problems
  busellato-table.json      machine file (fixed dimensions)
  MEASURE.md                measurement sheet for the machine visit
tests/
  test_table_geometry.py    unit tests for table_geometry.py
```

## Section 2 — Rules and checks

### Parameters (mm, Fusion user parameters)

- `BEAM<n>_X` for n = 1…N: beam position on the machine's own X scale (as
  read on the rail).
- `BEAM<n>_POD<k>_Y` for k = 1…P: pod position on the machine's own Y
  scale along the beam.
- `BEAM<n>_POD<k>_ON`: 1 = pod in use, 0 = not.

N (beams) and P (pods per beam) come from the machine file. The script
creates missing parameters with starting values and never overwrites
existing ones.

### Machine file `fusion/busellato-table.json`

| Key | Meaning |
|---|---|
| `beams` | number of beams N |
| `pods_per_beam` | P |
| `beam_width`, `beam_height`, `beam_length` | beam cross-section and length (mm) |
| `beam_x_min`, `beam_x_max` | X travel of a beam's reference edge on the machine scale |
| `pod_x_size`, `pod_y_size`, `pod_height` | pod footprint and height |
| `pod_y_min`, `pod_y_max` | Y travel of a pod's reference edge on the machine scale |
| `scale_to_g54_x`, `scale_to_g54_y` | offset from machine scale to the G54 panel corner |
| `reference` | which edge/corner of beam and pod the scale values refer to |
| `provisional` | list of keys not yet measured |

### What gets built

- Beams always (they are on the machine); pods only where `_ON` = 1.
- Pod tops on the panel underside (setup stock bottom); beams directly
  under the pods.
- All bodies in component "Vacuum table". Re-running replaces what the
  script built earlier and nothing else.
- Beams and active pods become fixtures in every setup of the document;
  fixtures added by the user stay.

### Checks — script stops, shows all problems at once, changes nothing

- beam outside its X travel; two beams closer than one beam width;
- pod outside its Y travel; two active pods on the same beam overlapping;
- a missing or non-numeric parameter; a machine file with missing keys;
- no setup with stock in the document.

Warning (not a stop): any key listed in `provisional`.

## Section 3 — Testing, measurement, later work

### Testing

- `tests/test_table_geometry.py` tests `table_geometry.py` without
  Fusion: box positions from parameters and the scale offset, pods only
  when `_ON` = 1, pod top at the stock bottom, every check above (one
  test per rule) and the provisional warning.
- The Fusion layer is checked through the Fusion MCP on the "Busselato
  Test" document: running the script creates the parameters, builds the
  bodies, sets the fixtures; a pod placed under the RECT contour makes the
  simulation show a collision (as PODTEST did), a pod moved away does not.
  The simulation step is done by David (not scriptable).

### Measurement sheet `fusion/MEASURE.md` (next machine visit)

A table to fill in with a tape measure and photos: number of beams and
pods per beam; beam width, height, length; beam X travel and where the
X scale reads zero; pod footprint and height; pod Y travel and where the
Y scale reads zero; which edge the scales refer to; the position of the
G54 corner (from run sheet step 2) relative to both scales. Until filled
in, the machine file holds provisional values from the photos, all listed
under `provisional`.

### Later (not in this version)

- Head bodies (spindle housings, drill block, saw guard) as a separate
  collision model — needs head measurements and possibly Fusion machine
  simulation.
- A second safety net in the post-processor (refuse cuts deeper than the
  panel over pod rectangles).
- A helper that proposes pod positions from the panel and toolpaths.
