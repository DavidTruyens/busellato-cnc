# Cabinet documentation: wiring source, generated schematics, Fusion plate layout — design

Date: 2026-10-03
Status: approved in chat, awaiting written-spec review

## Goal

Document the new LinuxCNC (Mesa 7I97T) control cabinet so that it serves
both as **build drawings** (plate layout, terminal plan, wire list) and as
the **as-built record** a technician uses later to trace a fault.

Two deliverables, fed by one source:

1. **Electrical documentation** generated from a single hand-edited text
   file: wiring diagrams, terminal plan, wire list, cable list, BOM.
2. **A Fusion model of the mounting plate**, used to size the plate and
   experiment with the layout before anything is drilled.

## Decisions taken in chat

- The new control goes **inside the existing TPA cabinet**. The TPA PC,
  screen and control electronics are **removed**. No backwards
  compatibility, no adapter, no dual-state documentation. (This supersedes
  the adapter-PCB goal in `docs/electrical/connector-inventory.md`; its
  per-connector survey is still the input for the machine I/O.)
- Schematic approach: **one YAML source, everything else generated**
  (option 1). Classic IEC schematic sheets (e.g. QElectroTech) are not in
  scope.
- 3D in **Fusion** (Personal licence). Part placeholders live in a library
  of one document per part type; each is made read-only before the next is
  created, to stay within the editable-document limit.
- DIN-rail parts move along their rail with **slider joints**; layout
  changes made by dragging in Fusion are **exported back** to the repo.

## Precondition outside this spec

Removing the TPA PC destroys the only live copy of its hard disk. The
remaining backup batches of `hdd/COPY-PLAN.md` (2–8 irreplaceable), or a
full IDE disk image, must be complete before the PC is pulled. This spec
does not do that work but the README / order of work must say so.

## Files

```
docs/electrical/
  cabinet.yaml          hand-edited: components, cables, wires   (source)
  layout.yaml           hand-edited or exported: part positions   (source)
  generated/            output of tools/cabinet.py — never edited by hand
    diagrams/*.svg      WireViz diagrams
    terminal-plan.md
    wire-list.md
    cable-list.md
    bom.md
    layout-parts.json   input for the Fusion scripts
tools/cabinet.py        validate + generate
tests/test_cabinet.py   unit tests (unittest, like the existing tests)
tests/fixtures/cabinet-sample.yaml
fusion/cabinet_parts/   Fusion script: placeholder part library
fusion/cabinet_plate/   Fusion script: plate assembly, joints, checks, export
fusion/MEASURE.md       + cabinet inside dimensions, depth to closed door
```

## 1. `cabinet.yaml`

Three top-level lists. IDs follow IEC 81346-style letter codes:
`A` assemblies/electronics (A1 = 7I97T), `G` power supplies, `Q` switches
and breakers, `K` relays/contactors, `S` push buttons (E-stop), `X`
terminal strips, `W` external cables, `T` transformers, `U` drives.

### components

```yaml
components:
  - id: A1
    name: Mesa 7I97T
    part: 7I97T
    supplier: https://store.mesanet.com/...
    mount: din            # din | plate
    size: {w: 165, h: 100, d: 30}   # mm, footprint on the plate and depth
    placeholder: false    # true = estimated footprint, real part not chosen
    pins:
      TB3.1: X ENC A
      TB3.2: X ENC B
      ...
```

- `part` identifies the part type. Components with the same `part` share
  one Fusion library document; `size` and `mount` must then agree.
- Terminal strips list their terminals as pins (`X2` pins `1`..`n`).
- Machine I/O that is not yet surveyed enters as `placeholder: true`
  components with estimated footprints and no pins, so the plate is sized
  for it.

### cables (leave the cabinet)

```yaml
cables:
  - id: W01
    name: X axis encoder
    type: 4x0.25 + shield
    cores: 4
    shield: true
    from: X3             # cabinet side: a terminal strip or component
    to: X motor encoder  # far end, free text
    cores_map:           # core colour -> cabinet pin, far-end pin
      WH: {cabinet: "X3:1", far: "A"}
      ...
```

### wires (inside the cabinet)

```yaml
wires:
  - no: 101
    from: A1:TB3.1
    to: X3:1
    colour: VT
    section: 0.25        # mm²
```

Endpoints are `<component id>:<pin>`.

## 2. `tools/cabinet.py`

Commands:

- `check` — validate only, non-zero exit on errors.
- `generate` — validate, then write `docs/electrical/generated/`.

### Checks

- every wire and cable-core endpoint names an existing component and pin;
- IDs unique (components, cables); wire numbers unique;
- a pin is used by at most one wire, unless the pin is listed in the
  component's `bridges` (e.g. a terminal with a jumper);
- every component has `mount` and a complete `size`;
- components sharing a `part` agree on `size` and `mount`.

Errors name the file location (component/wire) and the rule broken.

### Outputs

- **WireViz diagrams**: one per external cable (cabinet pin → core →
  far end), and one per functional group. Groups are a `group:` field on
  wires (`axis-x`, `axis-y`, `axis-z`, `spindle`, `24v`, `estop`, ...).
  WireViz is used as a Python package (one new dependency); the generator
  writes WireViz YAML and renders SVG.
- **terminal-plan.md**: per terminal strip, each terminal with the wire
  numbers and the far ends on both sides.
- **wire-list.md**: sorted by wire number: from, to, colour, section, group.
- **cable-list.md**: cables with type, cores, ends.
- **bom.md**: parts grouped by `part`, with quantity and supplier link,
  formatted to paste into the buy-list Google Sheet (the sheet stays the
  source for prices and status).
- **layout-parts.json**: per part type: `part`, `name`, `mount`, `size`;
  per component: `id`, `part`.

Generation is deterministic: two runs on the same input give identical
files, so diffs show only real changes.

## 3. Fusion part library — `fusion/cabinet_parts`

- Reads `layout-parts.json`. For each **part type** not yet in the
  "Cabinet parts" folder of the Fusion project, creates a document named
  after the part:
  - one body: a box of the part's `size`;
  - a **joint origin** at the mounting reference: for `din`, on the back
    face at the DIN-rail centreline (horizontal centre of the part
    footprint); for `plate`, the back face bottom-left corner;
  - an attribute marking it as generated by this script.
- After saving each document it stops and asks the user to make it
  read-only (unless the feasibility test shows the API can), then
  continues with the next. Re-running skips existing documents, so the
  run can be interrupted at any point.
- **Swapping in real CAD later**: make the one document editable, import
  the vendor STEP, align it to the same joint origin, delete the box,
  save, make read-only again. The plate picks it up through the
  reference.

## 4. Fusion plate assembly — `fusion/cabinet_plate`

One editable document.

### Parameters (Fusion user parameters)

`plate_w`, `plate_h`, `plate_t`, `edge_margin`; `cab_w`, `cab_h`,
`cab_depth` (inside the cabinet, back wall to closed door); per DIN rail
its height `rail_<n>_y` and length; per duct its position and size.
Initial values from `layout.yaml`; cabinet values provisional until
measured (`fusion/MEASURE.md`).

### Geometry

- Plate, DIN rails and wire ducts are built natively in this document
  (they are cut to length, so they are not library parts).
- Each component in `layout-parts.json` is inserted as a **reference**
  to its library document.

### `layout.yaml`

```yaml
rails:
  - {id: 1, y: 600, x0: 20, length: 560}
ducts:
  - {id: D1, x: 0, y: 650, w: 600, h: 40, orient: h}
parts:
  - {id: A1, rail: 1, x: 140}        # din: position along the rail
  - {id: U1, x: 50, y: 80, rot: 0}   # plate: x/y on the plate
```

### Joints

- DIN parts: **slider joint** between the part's joint origin and its
  rail, along the rail, limited to the rail length minus the part width.
  Dragging moves the part only along its rail. Moving to another rail is
  done in `layout.yaml` and a re-run.
- Plate parts: **planar joint** on the plate face (x/y and rotation about
  the plate normal).
- Collisions between parts are **not** enforced by joints or contact sets
  (too slow with dozens of parts); they are a check.

### Commands

- **Build / rebuild** from `layout.yaml` and `layout-parts.json`.
  Re-running replaces the previous build, recognised by attribute (same
  pattern as `busellato_table`).
- **Check**: part footprints overlapping; closer than a clearance to a
  duct; outside `edge_margin`; part depth + plate standoff deeper than
  `cab_depth`; plate larger than the cabinet inside. Reports plate area
  used (%).
- **Export layout**: reads each joint's current value and writes
  `layout.yaml` (rail + x, or x/y/rot), keeping rails/ducts as they are.

## 5. Feasibility test (first step, throwaway)

A small script, run through the Fusion MCP, answers before steps 3–4 are
built:

1. Can a **read-only** document be inserted into another as a reference?
2. Does a **joint** between that reference's joint origin and geometry in
   the host document work, with limits?
3. Can the **slide value** be read back after dragging?
4. Can the API **make a document read-only**? (If yes, the manual step in
   section 3 goes away.)

If 1 or 2 fails, the library falls back to inserting copies (not
references) or to keeping placeholders as components inside the plate
document; the spec is amended before continuing.

## Order of work

1. Feasibility test (section 5).
2. `cabinet.yaml` schema + checks in `tools/cabinet.py`, test-first, on
   `tests/fixtures/cabinet-sample.yaml`.
3. Generators: tables, BOM, WireViz diagrams, `layout-parts.json`.
4. `fusion/cabinet_parts`.
5. `fusion/cabinet_plate`: parameters, rails/ducts, inserted parts,
   joints, checks, export.
6. Phase 1 content: 7I97T, power supplies, main switch, E-stop chain,
   axis and spindle drives, terminal strips — from the TPA scans and the
   Mesa manual — plus I/O placeholders; first plate layout.

## Testing

- Python: unit tests for every check (one passing and one failing fixture
  per rule) and for generator output (golden files, determinism).
- Fusion scripts cannot be unit-tested here. They are run through the
  Fusion MCP with screenshots; the layout itself is judged by David in
  Fusion.
- Nothing is verified against the real cabinet until its inside
  dimensions are measured.

## Out of scope

- IEC schematic sheets (QElectroTech); may be added later for the power
  and safety-chain sheets.
- Cable routing through ducts, duct fill, cable lengths.
- Machine I/O content beyond placeholders (needs the connector survey).
- Changes to the buy-list Google Sheet (the BOM is pasted by hand).
