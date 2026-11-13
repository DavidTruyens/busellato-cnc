# Vacuum Table Model in Fusion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Fusion script that builds the Busellato's vacuum beams and pods from user parameters and a machine file, and sets them as setup fixtures so Fusion's simulation shows cutter collisions.

**Architecture:** All geometry and validation live in a pure-Python module (`table_geometry.py`) that turns the machine file and parameter values into boxes in G54 panel coordinates plus a list of problems and warnings; it is unit-tested without Fusion. A thin Fusion script (`busellato_table.py`) reads/creates user parameters, calls the module, transforms the boxes into design coordinates via the reference setup's WCS, rebuilds the "Vacuum table" component and updates setup fixtures. The Fusion layer is verified through the Fusion MCP.

**Tech Stack:** Python 3 stdlib (module + `unittest`), Fusion 360 Python API (script), Fusion MCP (`execute_python`) for verification.

**Spec:** `docs/superpowers/specs/2026-09-26-vacuum-table-design.md`

## Global Constraints

- Units: mm everywhere in the machine file, parameters and module; Fusion's internal cm conversion happens only in `busellato_table.py`.
- Parameters: `BEAM<n>_X`, `BEAM<n>_POD<k>_Y` (length, mm), `BEAM<n>_POD<k>_ON` (unitless, 0 or 1), n = 1…N (`beams`), k = 1…P (`pods_per_beam`). Missing ones are created with starting values; existing ones are never overwritten.
- Beams always built; pods only where `_ON` = 1. Pod tops on the panel underside (stock bottom); beams directly under the pods.
- Everything built goes in one component named `Vacuum table`; re-running replaces only what the script built.
- Beams and active pods become fixtures in every setup; user-added fixtures stay.
- On any problem the script stops, shows all problems at once, and changes nothing. Keys listed in `provisional` produce a warning, not a stop.
- No Fusion-free code imports `adsk`. Commit messages never mention Claude and have no Co-Authored-By line.

## Review Focus

1. **Re-running the script twice** must not duplicate bodies or fixtures, and must not remove user fixtures or other components. → Task 2 Step 5 MCP check "run twice".
2. **Setups with a different WCS** (the test document's S2 has its origin on the bottom face) must still get fixtures, but the geometry is placed relative to the reference setup only; the user is warned. → Task 1 `test_reference_warning` (module side) + Task 2 Step 5.
3. **Parameter values typed with units or as expressions** (e.g. `1000 mm`, `BEAM1_X + 500`) must be read correctly (Fusion evaluates them; the script reads `.value` and converts cm → mm). → Task 2 Step 5 "expression parameter".
4. **A pod exactly touching its travel limit or a neighbouring pod** (edge-to-edge) is allowed; only real overlap is refused. → Task 1 `test_touching_pods_allowed`, `test_pod_at_travel_limit_allowed`.
5. **A machine file with a wrong type** (string instead of number) gives a clear problem, not a Python traceback. → Task 1 `test_machine_file_non_numeric`.

## Rulings made while writing this plan

- Spec gap: the machine file needs the Y position where a beam starts. Added key `beam_y_start` (machine Y scale of the beam's front end).
- `scale_to_g54_x`/`_y` are defined precisely as **the scale reading at the G54 corner**; G54 coordinate = scale value − scale_to_g54.
- Reference edges: a beam's X scale value is its **left edge (min X)**; a pod's Y scale value is its **front edge (min Y)**; pods are centred on their beam in X. Recorded in the machine file's `reference` text.
- Reference setup = the first setup in the document that has stock; other setups with a different WCS get fixtures plus a warning.

---

## File Structure

```
fusion/
  busellato-table.json            machine file (provisional values until measured)
  MEASURE.md                      measurement sheet for the machine visit
  README.md                       install + per-job workflow
  busellato_table/
    busellato_table.py            Fusion script (run(context) + apply(...))
    busellato_table.manifest
    table_geometry.py             pure Python geometry + checks
tests/
  test_table_geometry.py
```

---

### Task 1: Machine file and geometry module

**Files:**
- Create: `fusion/busellato-table.json`, `fusion/busellato_table/table_geometry.py`, `tests/test_table_geometry.py`

**Interfaces:**
- Produces: `REQUIRED_KEYS: tuple[str, ...]`; `load_machine(path: str) -> dict`; `check_machine(machine: dict) -> list[str]` (problems); `parameter_specs(machine: dict) -> list[tuple[str, str, float]]` as (name, unit `"mm"` or `""`, starting value); `build(machine: dict, params: dict[str, float], stock_bottom_z: float) -> Result` where `Result` has `boxes: list[Box]`, `problems: list[str]`, `warnings: list[str]`; `Box(name: str, kind: "beam"|"pod", x0, y0, z0, x1, y1, z1)` in G54 mm with x0<x1 etc.

- [ ] **Step 1: Write the machine file** `fusion/busellato-table.json` (all values provisional, from photos):

```json
{
  "beams": 6,
  "pods_per_beam": 4,
  "beam_width": 100,
  "beam_height": 90,
  "beam_length": 1300,
  "beam_y_start": 0,
  "beam_x_min": 0,
  "beam_x_max": 2500,
  "pod_x_size": 120,
  "pod_y_size": 120,
  "pod_height": 100,
  "pod_y_min": 0,
  "pod_y_max": 1180,
  "scale_to_g54_x": 0,
  "scale_to_g54_y": 0,
  "reference": "Beam X scale value = beam left edge (min X). Pod Y scale value = pod front edge (min Y). Pods centred on their beam in X. scale_to_g54 = scale reading at the G54 panel corner.",
  "provisional": ["beams", "pods_per_beam", "beam_width", "beam_height", "beam_length", "beam_y_start",
                  "beam_x_min", "beam_x_max", "pod_x_size", "pod_y_size", "pod_height", "pod_y_min",
                  "pod_y_max", "scale_to_g54_x", "scale_to_g54_y"]
}
```

- [ ] **Step 2: Write the failing tests** — `tests/test_table_geometry.py`:

```python
import json
import os
import sys
import unittest

from helpers import REPO

sys.path.insert(0, os.path.join(REPO, 'fusion', 'busellato_table'))
import table_geometry as tg  # noqa: E402

MACHINE = {
    'beams': 2, 'pods_per_beam': 2,
    'beam_width': 100, 'beam_height': 90, 'beam_length': 1300, 'beam_y_start': 0,
    'beam_x_min': 0, 'beam_x_max': 2500,
    'pod_x_size': 120, 'pod_y_size': 120, 'pod_height': 100,
    'pod_y_min': 0, 'pod_y_max': 1180,
    'scale_to_g54_x': 50, 'scale_to_g54_y': 20,
    'reference': 'test', 'provisional': [],
}


def params(**over):
    p = {'BEAM1_X': 300, 'BEAM2_X': 900,
         'BEAM1_POD1_Y': 100, 'BEAM1_POD1_ON': 1, 'BEAM1_POD2_Y': 600, 'BEAM1_POD2_ON': 0,
         'BEAM2_POD1_Y': 100, 'BEAM2_POD1_ON': 1, 'BEAM2_POD2_Y': 600, 'BEAM2_POD2_ON': 1}
    p.update(over)
    return p


def by_name(result):
    return {b.name: b for b in result.boxes}


class MachineFileTest(unittest.TestCase):
    def test_repo_machine_file_is_complete(self):
        m = tg.load_machine(os.path.join(REPO, 'fusion', 'busellato-table.json'))
        self.assertEqual(tg.check_machine(m), [])

    def test_machine_file_missing_key(self):
        m = dict(MACHINE)
        del m['pod_height']
        self.assertTrue(any('pod_height' in p for p in tg.check_machine(m)))

    def test_machine_file_non_numeric(self):
        m = dict(MACHINE, beam_width='wide')
        self.assertTrue(any('beam_width' in p for p in tg.check_machine(m)))


class ParameterSpecTest(unittest.TestCase):
    def test_names_units_and_count(self):
        specs = tg.parameter_specs(MACHINE)
        names = [s[0] for s in specs]
        self.assertEqual(len(names), 2 + 2 * 2 * 2)
        lookup = {n: (u, v) for n, u, v in specs}
        self.assertEqual(lookup['BEAM2_POD2_ON'], ('', 1.0))     # first and last pod start switched on
        self.assertEqual(lookup['BEAM1_POD1_ON'], ('', 1.0))
        self.assertEqual({u for n, u, v in specs if n.endswith('_X') or n.endswith('_Y')}, {'mm'})

    def test_starting_values_pass_the_checks(self):
        start = {n: v for n, u, v in tg.parameter_specs(MACHINE)}
        self.assertEqual(tg.build(MACHINE, start, -18).problems, [])


class BuildTest(unittest.TestCase):
    def test_beam_and_pod_positions(self):
        r = tg.build(MACHINE, params(), -18)
        self.assertEqual(r.problems, [])
        boxes = by_name(r)
        beam1 = boxes['BEAM1']
        self.assertEqual((beam1.x0, beam1.x1), (250, 350))          # 300 - 50, width 100
        self.assertEqual((beam1.y0, beam1.y1), (-20, 1280))         # beam_y_start 0 - 20, length 1300
        self.assertEqual((beam1.z0, beam1.z1), (-208, -118))        # under the pods
        pod = boxes['BEAM1_POD1']
        self.assertEqual((pod.x0, pod.x1), (240, 360))              # centred on the beam
        self.assertEqual((pod.y0, pod.y1), (80, 200))               # 100 - 20, size 120
        self.assertEqual((pod.z0, pod.z1), (-118, -18))             # top on the panel underside

    def test_inactive_pods_not_built(self):
        names = set(by_name(tg.build(MACHINE, params(), -18)))
        self.assertNotIn('BEAM1_POD2', names)
        self.assertEqual(names, {'BEAM1', 'BEAM2', 'BEAM1_POD1', 'BEAM2_POD1', 'BEAM2_POD2'})

    def test_beam_outside_travel(self):
        r = tg.build(MACHINE, params(BEAM2_X=2600), -18)
        self.assertTrue(any('BEAM2_X' in p for p in r.problems))
        self.assertEqual(r.boxes, [])

    def test_beams_overlap(self):
        r = tg.build(MACHINE, params(BEAM2_X=350), -18)
        self.assertTrue(any('BEAM1' in p and 'BEAM2' in p for p in r.problems))

    def test_pod_outside_travel(self):
        r = tg.build(MACHINE, params(BEAM1_POD1_Y=1200), -18)
        self.assertTrue(any('BEAM1_POD1_Y' in p for p in r.problems))

    def test_inactive_pod_outside_travel_ignored(self):
        self.assertEqual(tg.build(MACHINE, params(BEAM1_POD2_Y=5000), -18).problems, [])

    def test_active_pods_overlap(self):
        r = tg.build(MACHINE, params(BEAM2_POD2_Y=150), -18)
        self.assertTrue(any('BEAM2_POD1' in p and 'BEAM2_POD2' in p for p in r.problems))

    def test_touching_pods_allowed(self):
        self.assertEqual(tg.build(MACHINE, params(BEAM2_POD2_Y=220), -18).problems, [])

    def test_pod_at_travel_limit_allowed(self):
        self.assertEqual(tg.build(MACHINE, params(BEAM1_POD1_Y=1180, BEAM2_POD2_Y=1180, BEAM2_POD1_Y=0), -18).problems, [])

    def test_missing_and_bad_parameters(self):
        p = params()
        del p['BEAM1_X']
        p['BEAM2_POD1_ON'] = 2
        r = tg.build(MACHINE, p, -18)
        self.assertTrue(any('BEAM1_X' in x for x in r.problems))
        self.assertTrue(any('BEAM2_POD1_ON' in x for x in r.problems))

    def test_all_problems_reported_at_once(self):
        r = tg.build(MACHINE, params(BEAM2_X=2600, BEAM1_POD1_Y=1200), -18)
        self.assertGreaterEqual(len(r.problems), 2)

    def test_provisional_warning(self):
        m = dict(MACHINE, provisional=['pod_height'])
        r = tg.build(m, params(), -18)
        self.assertEqual(r.problems, [])
        self.assertTrue(any('pod_height' in w for w in r.warnings))

    def test_reference_warning(self):
        self.assertTrue(any('S2' in w for w in tg.reference_warnings('S1', ['S1', 'S2'], {'S2'})))
        self.assertEqual(tg.reference_warnings('S1', ['S1'], set()), [])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 3: Run to see it fail**

Run: `python3 -m unittest discover -s tests -p 'test_table_geometry.py'`
Expected: `ModuleNotFoundError: No module named 'table_geometry'`

- [ ] **Step 4: Implement** `fusion/busellato_table/table_geometry.py`:

```python
"""Vacuum table geometry for the Busellato S.EASY (no Fusion imports).

Turns the machine file and the per-job parameter values into boxes in G54
panel coordinates (mm, panel top at Z=0), plus problems and warnings.
Spec: docs/superpowers/specs/2026-09-26-vacuum-table-design.md
"""
import json
from collections import namedtuple

REQUIRED_KEYS = ('beams', 'pods_per_beam', 'beam_width', 'beam_height', 'beam_length', 'beam_y_start',
                 'beam_x_min', 'beam_x_max', 'pod_x_size', 'pod_y_size', 'pod_height',
                 'pod_y_min', 'pod_y_max', 'scale_to_g54_x', 'scale_to_g54_y')
EPS = 1e-6

Box = namedtuple('Box', 'name kind x0 y0 z0 x1 y1 z1')
Result = namedtuple('Result', 'boxes problems warnings')


def load_machine(path):
    with open(path) as fh:
        return json.load(fh)


def check_machine(machine):
    problems = []
    for key in REQUIRED_KEYS:
        if key not in machine:
            problems.append(f'machine file: missing "{key}"')
        elif isinstance(machine[key], bool) or not isinstance(machine[key], (int, float)):
            problems.append(f'machine file: "{key}" must be a number, got {machine[key]!r}')
    for key in ('beams', 'pods_per_beam'):
        if not problems and (int(machine[key]) != machine[key] or machine[key] < 1):
            problems.append(f'machine file: "{key}" must be a whole number >= 1')
    return problems


def parameter_specs(machine):
    n, p = int(machine['beams']), int(machine['pods_per_beam'])
    x_span = machine['beam_x_max'] - machine['beam_x_min']
    y_span = machine['pod_y_max'] - machine['pod_y_min']
    specs = []
    for b in range(1, n + 1):
        x = machine['beam_x_min'] + (x_span * (b - 1) / (n - 1) if n > 1 else 0)
        specs.append((f'BEAM{b}_X', 'mm', float(x)))
        for k in range(1, p + 1):
            y = machine['pod_y_min'] + (y_span * (k - 1) / (p - 1) if p > 1 else 0)
            specs.append((f'BEAM{b}_POD{k}_Y', 'mm', float(y)))
            specs.append((f'BEAM{b}_POD{k}_ON', '', 1.0 if k in (1, p) else 0.0))
    return specs


def reference_warnings(reference, setups, differing):
    return [f'setup {s} has a different work coordinate system than {reference}: '
            f'the table is placed relative to {reference}' for s in setups if s in differing]


def build(machine, params, stock_bottom_z):
    problems = check_machine(machine)
    if problems:
        return Result([], problems, [])
    m = machine
    values = {}
    for name, unit, _ in parameter_specs(m):
        v = params.get(name)
        if v is None:
            problems.append(f'parameter {name} is missing')
        elif isinstance(v, bool) or not isinstance(v, (int, float)):
            problems.append(f'parameter {name} must be a number, got {v!r}')
        elif name.endswith('_ON') and v not in (0, 1):
            problems.append(f'parameter {name} must be 0 or 1, got {v:g}')
        else:
            values[name] = float(v)
    if problems:
        return Result([], problems, [])

    n, p = int(m['beams']), int(m['pods_per_beam'])
    beams = []
    for b in range(1, n + 1):
        x = values[f'BEAM{b}_X']
        if x < m['beam_x_min'] - EPS or x > m['beam_x_max'] + EPS:
            problems.append(f'BEAM{b}_X = {x:g} is outside the beam travel {m["beam_x_min"]:g}..{m["beam_x_max"]:g}')
        beams.append((b, x))
    for i, (b1, x1) in enumerate(beams):
        for b2, x2 in beams[i + 1:]:
            if abs(x1 - x2) < m['beam_width'] - EPS:
                problems.append(f'BEAM{b1} and BEAM{b2} overlap (X {x1:g} and {x2:g}, beam width {m["beam_width"]:g})')
    active = {}
    for b in range(1, n + 1):
        active[b] = []
        for k in range(1, p + 1):
            if values[f'BEAM{b}_POD{k}_ON'] != 1:
                continue
            y = values[f'BEAM{b}_POD{k}_Y']
            if y < m['pod_y_min'] - EPS or y > m['pod_y_max'] + EPS:
                problems.append(f'BEAM{b}_POD{k}_Y = {y:g} is outside the pod travel {m["pod_y_min"]:g}..{m["pod_y_max"]:g}')
            active[b].append((k, y))
        for i, (k1, y1) in enumerate(active[b]):
            for k2, y2 in active[b][i + 1:]:
                if abs(y1 - y2) < m['pod_y_size'] - EPS:
                    problems.append(f'BEAM{b}_POD{k1} and BEAM{b}_POD{k2} overlap (Y {y1:g} and {y2:g}, pod size {m["pod_y_size"]:g})')
    if problems:
        return Result([], problems, [])

    ox, oy = m['scale_to_g54_x'], m['scale_to_g54_y']
    pod_top = stock_bottom_z
    pod_bottom = pod_top - m['pod_height']
    beam_bottom = pod_bottom - m['beam_height']
    boxes = []
    for b, x in beams:
        bx0 = x - ox
        by0 = m['beam_y_start'] - oy
        boxes.append(Box(f'BEAM{b}', 'beam', bx0, by0, beam_bottom, bx0 + m['beam_width'], by0 + m['beam_length'], pod_bottom))
        px0 = bx0 + (m['beam_width'] - m['pod_x_size']) / 2
        for k, y in active[b]:
            py0 = y - oy
            boxes.append(Box(f'BEAM{b}_POD{k}', 'pod', px0, py0, pod_bottom, px0 + m['pod_x_size'], py0 + m['pod_y_size'], pod_top))
    warnings = []
    if m.get('provisional'):
        warnings.append('provisional machine dimensions (not measured yet): ' + ', '.join(m['provisional']))
    return Result(boxes, [], warnings)
```

- [ ] **Step 5: Run and see it pass**

Run: `python3 -m unittest discover -s tests -p 'test_table_geometry.py'`, then the full suite `python3 -m unittest discover -s tests`.
Expected: all pass (existing tests on this branch + the new ones).

- [ ] **Step 6: Commit**

```bash
git add fusion/busellato-table.json fusion/busellato_table/table_geometry.py tests/test_table_geometry.py
git commit -m "Vacuum table geometry module and provisional machine file"
```

---

### Task 2: Fusion script

**Files:**
- Create: `fusion/busellato_table/busellato_table.py`, `fusion/busellato_table/busellato_table.manifest`

**Interfaces:**
- Consumes: `table_geometry.load_machine`, `check_machine`, `parameter_specs`, `build`, `reference_warnings`, `Box` (Task 1).
- Produces: `apply(app, machine_path: str) -> dict` with keys `ok: bool`, `problems: list[str]`, `warnings: list[str]`, `created_parameters: list[str]`, `bodies: list[str]`, `setups: list[str]`; `run(context)` shows the result in a message box.

- [ ] **Step 1: Probe the API through the Fusion MCP** (the controller could not confirm these while writing the plan — Fusion was not responding). In the "Busselato Test" document run, via `execute_python` (short calls):

```python
import adsk.core, adsk.cam, adsk.fusion
app = adsk.core.Application.get(); doc = app.activeDocument
cam = adsk.cam.CAM.cast(doc.products.itemByProductType('CAMProductType'))
des = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
s = cam.setups.itemByName('S1')
o, x, y, z = s.workCoordinateSystem.getAsCoordinateSystem()
print('WCS origin cm', o.x, o.y, o.z, 'x', x.asArray(), 'y', y.asArray(), 'z', z.asArray())
bb = s.models.item(0).boundingBox
print('model z cm', bb.minPoint.z, bb.maxPoint.z, 'designType', des.designType)
```

Expected for S1: origin (0, 0, 1.8) cm, axes along design X/Y/Z, model z 0..1.8. Record the real API names in the report; adapt Step 2's code to them if they differ.

- [ ] **Step 2: Write** `fusion/busellato_table/busellato_table.manifest`:

```json
{
  "autodeskProduct": "Fusion",
  "type": "script",
  "author": "busellato-cnc",
  "description": {"": "Build the Busellato S.EASY vacuum beams and pods from parameters and set them as fixtures."},
  "supportedOS": "windows|mac",
  "editEnabled": true
}
```

and `fusion/busellato_table/busellato_table.py`:

```python
"""Busellato S.EASY vacuum table: build beams and pods from user parameters
and set them as fixtures in every setup.
Spec: docs/superpowers/specs/2026-09-26-vacuum-table-design.md (busellato-cnc repo).
"""
import os
import sys
import traceback

import adsk.cam
import adsk.core
import adsk.fusion

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import table_geometry as tg  # noqa: E402

COMPONENT = 'Vacuum table'
MACHINE_FILE = os.path.join(os.path.dirname(HERE), 'busellato-table.json')
ATTR_GROUP, ATTR_NAME = 'busellato', 'table'


def _param_values(des, specs):
    created, values = [], {}
    up = des.userParameters
    for name, unit, start in specs:
        p = up.itemByName(name)
        if p is None:
            text = f'{start:g} mm' if unit == 'mm' else f'{start:g}'
            up.add(name, adsk.core.ValueInput.createByString(text), unit, 'Busellato vacuum table')
            created.append(name)
            p = up.itemByName(name)
        values[name] = p.value * 10.0 if unit == 'mm' else p.value      # Fusion lengths are in cm
    return created, values


def _reference_setup(cam):
    for s in cam.setups:
        if s.models.count > 0:
            return s
    return None


def _frame(setup):
    o, x, y, z = setup.workCoordinateSystem.getAsCoordinateSystem()
    return o, x, y, z


def _stock_bottom_g54(setup, frame):
    o, x, y, z = frame
    lowest = None
    for i in range(setup.models.count):
        bb = setup.models.item(i).boundingBox
        for px in (bb.minPoint.x, bb.maxPoint.x):
            for py in (bb.minPoint.y, bb.maxPoint.y):
                for pz in (bb.minPoint.z, bb.maxPoint.z):
                    v = adsk.core.Vector3D.create(px - o.x, py - o.y, pz - o.z)
                    zz = v.dotProduct(z) * 10.0
                    lowest = zz if lowest is None else min(lowest, zz)
    return lowest


def _same_frame(a, b):
    return (a[0].distanceTo(b[0]) < 0.001 and all(a[i].isParallelTo(b[i]) and a[i].dotProduct(b[i]) > 0 for i in (1, 2, 3)))


def _remove_previous(root):
    for occ in [root.occurrences.item(i) for i in range(root.occurrences.count)]:
        if occ.component.name == COMPONENT and occ.component.attributes.itemByName(ATTR_GROUP, ATTR_NAME):
            occ.deleteMe()


def _box_body(comp, box, frame):
    o, x, y, z = frame
    cx, cy, cz = (box.x0 + box.x1) / 20.0, (box.y0 + box.y1) / 20.0, (box.z0 + box.z1) / 20.0   # mm -> cm
    centre = adsk.core.Point3D.create(o.x + x.x * cx + y.x * cy + z.x * cz,
                                      o.y + x.y * cx + y.y * cy + z.y * cz,
                                      o.z + x.z * cx + y.z * cy + z.z * cz)
    obb = adsk.core.OrientedBoundingBox3D.create(centre, x, y, (box.x1 - box.x0) / 10.0,
                                                 (box.y1 - box.y0) / 10.0, (box.z1 - box.z0) / 10.0)
    temp = adsk.fusion.TemporaryBRepManager.get().createBox(obb)
    design = adsk.fusion.Design.cast(comp.parentDesign)
    if design.designType == adsk.fusion.DesignTypes.ParametricDesignType:
        feature = comp.features.baseFeatures.add()
        feature.startEdit()
        comp.bRepBodies.add(temp, feature)
        feature.finishEdit()
    else:
        comp.bRepBodies.add(temp)
    body = comp.bRepBodies.item(comp.bRepBodies.count - 1)
    body.name = box.name
    return body


def apply(app, machine_path=MACHINE_FILE):
    doc = app.activeDocument
    des = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
    cam_product = doc.products.itemByProductType('CAMProductType')
    report = {'ok': False, 'problems': [], 'warnings': [], 'created_parameters': [], 'bodies': [], 'setups': []}
    cam = adsk.cam.CAM.cast(cam_product) if cam_product else None
    reference = _reference_setup(cam) if cam else None
    if reference is None:
        report['problems'].append('no setup with stock in this document (Manufacture workspace)')
        return report
    machine = tg.load_machine(machine_path)
    report['problems'] += tg.check_machine(machine)
    if report['problems']:
        return report
    specs = tg.parameter_specs(machine)
    missing = [s for s in specs if des.userParameters.itemByName(s[0]) is None]
    if missing:                                    # first run: only create parameters, build nothing
        report['created_parameters'], _ = _param_values(des, specs)
        report['warnings'].append('parameters created with starting values: set them to match the machine, then run again')
        report['ok'] = True
        return report
    _, values = _param_values(des, specs)
    frame = _frame(reference)
    result = tg.build(machine, values, _stock_bottom_g54(reference, frame))
    report['problems'] += result.problems
    if report['problems']:
        return report
    differing = {s.name for s in cam.setups if not _same_frame(frame, _frame(s))}
    report['warnings'] += result.warnings + tg.reference_warnings(reference.name, [s.name for s in cam.setups], differing)

    root = des.rootComponent
    _remove_previous(root)
    occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    comp = occ.component
    comp.name = COMPONENT
    comp.attributes.add(ATTR_GROUP, ATTR_NAME, '1')
    bodies = [_box_body(comp, box, frame) for box in result.boxes]
    report['bodies'] = [b.name for b in bodies]

    table_names = {b.name for b in bodies}
    for s in cam.setups:
        col = adsk.core.ObjectCollection.create()
        for i in range(s.fixtures.count):
            f = s.fixtures.item(i)
            if f.isValid and not (f.parentComponent.name == COMPONENT and f.name in table_names):
                col.add(f)
        for b in bodies:
            col.add(occ.bRepBodies.itemByName(b.name) if occ.bRepBodies.itemByName(b.name) else b)
        s.fixtures = col
        s.fixtureEnabled = True
        report['setups'].append(s.name)
    report['ok'] = True
    return report


def run(context):
    ui = adsk.core.Application.get().userInterface
    try:
        r = apply(adsk.core.Application.get())
        lines = []
        if r['problems']:
            lines.append('Nothing was changed. Problems:')
            lines += ['- ' + p for p in r['problems']]
        else:
            if r['created_parameters']:
                lines.append(f'Created {len(r["created_parameters"])} parameters (Modify > Change Parameters).')
            if r['bodies']:
                lines.append(f'Built {len(r["bodies"])} bodies; fixtures set in: {", ".join(r["setups"])}.')
        if r['warnings']:
            lines.append('Warnings:')
            lines += ['- ' + w for w in r['warnings']]
        ui.messageBox('\n'.join(lines), 'Busellato table')
    except Exception:
        ui.messageBox('Failed:\n' + traceback.format_exc(), 'Busellato table')
```

- [ ] **Step 3: Install for Fusion** — symlink the script folder so Fusion sees the repo version:

```bash
ln -sfn "$PWD/fusion/busellato_table" "$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/busellato_table"
```

(`MACHINE_FILE` resolves through `realpath`, so the symlinked script finds `fusion/busellato-table.json` in the repo.)

- [ ] **Step 4: Run through the MCP — first run creates parameters only**

```python
import sys; sys.path.insert(0, '/Users/davidtruyens/Source/busellato-cnc/fusion/busellato_table')
import importlib, busellato_table; importlib.reload(busellato_table)
print(busellato_table.apply(adsk.core.Application.get()))
```

Expected: `ok: True`, `created_parameters` has 6 + 6·4·2 = 54 names, `bodies: []`.

- [ ] **Step 5: Verification runs through the MCP** (record every output in the report):
  1. Second run: `ok: True`, 6 beams + 12 active pods (pods 1 and 4 of each beam), warnings include "provisional" and "setup S2 has a different work coordinate system". Every setup lists the table bodies among its fixtures; PODTEST still also has `PodTest`.
  2. **Run twice** (Review Focus 1): third run gives the same body count; component `Vacuum table` exists once; fixture counts per setup unchanged; `Panel` and `PodTest` untouched.
  3. **Expression parameter** (Review Focus 3): set `BEAM1_X` expression to `BEAM2_X - 400 mm` via `des.userParameters.itemByName('BEAM1_X').expression = ...`; run; BEAM1 body min X (in mm, relative to the S1 WCS) = BEAM2_X − 400 − scale_to_g54_x. Restore the original expression afterwards.
  4. **Refusal**: set `BEAM2_X` to beam_x_max + 100; run → `ok: False`, the problem names BEAM2_X, and the bodies/fixtures are unchanged from run 2. Restore.
  5. **Collision position**: place `BEAM1_X` and `BEAM1_POD1_Y` so that BEAM1_POD1 lies under the RECT contour's lower-left corner (RECT path passes X29 Y29 in G54); run; confirm via bounding box that the pod spans X29/Y29 and its top is at the panel underside (design z = 0 cm for S1).
  6. Save the document.
  The simulation check (pod under RECT shows red; moved away shows none) is done by David — put the exact instructions in the report for the controller to relay.

- [ ] **Step 6: Run the suite and commit**

`python3 -m unittest discover -s tests` (unchanged + Task 1 tests pass), then:

```bash
git add fusion/busellato_table/busellato_table.py fusion/busellato_table/busellato_table.manifest
git commit -m "Fusion script: build vacuum table from parameters and set fixtures"
```

---

### Task 3: Measurement sheet and README

**Files:**
- Create: `fusion/MEASURE.md`, `fusion/README.md`
- Test: `tests/test_table_geometry.py` (add `test_measure_sheet_covers_machine_keys`)

**Interfaces:**
- Consumes: `table_geometry.REQUIRED_KEYS` (Task 1).

- [ ] **Step 1: Write the failing test** — append to `tests/test_table_geometry.py` inside `MachineFileTest`:

```python
    def test_measure_sheet_covers_machine_keys(self):
        with open(os.path.join(REPO, 'fusion', 'MEASURE.md')) as fh:
            sheet = fh.read()
        for key in tg.REQUIRED_KEYS:
            self.assertIn(f'`{key}`', sheet, key)
```

- [ ] **Step 2: Confirm red** — `python3 -m unittest discover -s tests -p 'test_table_geometry.py'` → FileNotFoundError.

- [ ] **Step 3: Write `fusion/MEASURE.md`**:

```markdown
# Vacuum table — measurement sheet

Fill in at the machine with a tape measure; photograph every scale and
reference edge. Then copy the values into `fusion/busellato-table.json`
and remove each measured key from `provisional`.

Reference edges (keep consistent): a beam's X value = its **left edge
(min X)** on the X scale; a pod's Y value = its **front edge (min Y)** on
the Y scale. G54 corner = the origin corner found in run-sheet step 2.

| Key | What to measure | Value (mm) | Photo |
|---|---|---|---|
| `beams` | Number of beams (cross bars) | | |
| `pods_per_beam` | Pods available per beam | | |
| `beam_width` | Beam width along X | | |
| `beam_height` | Beam height (table surface to top of beam) | | |
| `beam_length` | Beam length along Y | | |
| `beam_y_start` | Y scale reading at the beam's front end | | |
| `beam_x_min` | X scale reading of a beam's left edge, beam fully left | | |
| `beam_x_max` | X scale reading of a beam's left edge, beam fully right | | |
| `pod_x_size` | Pod footprint along X | | |
| `pod_y_size` | Pod footprint along Y | | |
| `pod_height` | Pod height (top of beam to top of pod) | | |
| `pod_y_min` | Y scale reading of a pod's front edge, pod fully to the front | | |
| `pod_y_max` | Y scale reading of a pod's front edge, pod fully to the back | | |
| `scale_to_g54_x` | X scale reading at the G54 panel corner | | |
| `scale_to_g54_y` | Y scale reading at the G54 panel corner | | |

Also note: pod shape if not rectangular (sketch with dimensions); any
clamps or stops that stick up above the pods; where the scales are
fixed to the machine.
```

- [ ] **Step 4: Write `fusion/README.md`**:

```markdown
# Busellato S.EASY — vacuum table model for collision checks

A Fusion script that builds the vacuum beams and pods under the panel and
sets them as fixtures, so Fusion's simulation shows the cutter in red
where it would hit a pod or beam. Spec:
`docs/superpowers/specs/2026-09-26-vacuum-table-design.md`.

## Install (once)
    ln -sfn "<repo>/fusion/busellato_table" "$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/busellato_table"
Then Utilities → Scripts and Add-Ins → "busellato_table".

## Per job
1. In the job's design (with its setup: stock = the panel, origin on the top face at the G54 corner), run the script. The first time it only creates the parameters.
2. Modify → Change Parameters: set `BEAM<n>_X` and `BEAM<n>_POD<k>_Y` to the scale readings of the machine, `BEAM<n>_POD<k>_ON` to 1 for pods in use.
3. Run the script again. It builds the "Vacuum table" component and sets the bodies as fixtures in every setup.
4. Simulate the setup. Red tool = collision with a pod or beam.

The script stops and changes nothing if a beam or pod is outside its
travel, pods overlap, or a parameter is missing; it lists every problem.
Dimensions in `busellato-table.json` are **provisional** until measured
with `MEASURE.md` — until then the model is an approximation.

## Tests
`python3 -m unittest discover -s tests -p 'test_table_geometry.py'`
```

- [ ] **Step 5: Run and commit**

`python3 -m unittest discover -s tests` → all pass.

```bash
git add fusion/MEASURE.md fusion/README.md tests/test_table_geometry.py
git commit -m "Vacuum table measurement sheet and README"
```
