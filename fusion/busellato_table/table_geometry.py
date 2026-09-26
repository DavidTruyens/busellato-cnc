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
