"""Preview data for the UI, built from the programs the machine will get.

Hole positions and cut paths come from the programs' DrillOp / ContourOp objects (blank
coordinates); the panel view maps those same numbers onto the panel. Only the un-offset shape
outlines and the saw plan come from the layout.
Y is flipped for SVG (height - y); x, y of a rectangle are its top-left corner.
"""
from __future__ import annotations

import math

from .backends import BACKENDS
from .geometry import Arc, Line, _sweep, bbox, translate
from .layout import Blank, PanelPlan, Plan, SawCut, footprint, to_panel
from .program import LINE_WARNING, ContourOp, DrillOp, Program, base_label, stack_top
from .settings import Settings

BACKEND = 'cnc90'
TOL = 0.001


def _path(segs, flip: float) -> str:
    """SVG path with true arcs. Flipping Y reverses the turning direction, so a
    counter-clockwise machine arc becomes sweep 0."""
    if not segs:
        return ''
    out = [f'M{segs[0].a[0]:.3f},{flip - segs[0].a[1]:.3f}']
    for sg in segs:
        x, y = sg.b[0], flip - sg.b[1]
        if isinstance(sg, Line):
            out.append(f'L{x:.3f},{y:.3f}')
        else:
            large = int(_sweep(sg) > math.pi)
            out.append(f'A{sg.radius:.3f},{sg.radius:.3f} 0 {large} {int(not sg.ccw)} {x:.3f},{y:.3f}')
    return ' '.join(out)


def _map_seg(s, b: Blank):
    """Blank-frame segment -> panel frame; a quarter turn keeps the winding."""
    if isinstance(s, Line):
        return Line(to_panel(b, *s.a), to_panel(b, *s.b))
    return Arc(to_panel(b, *s.a), to_panel(b, *s.b), to_panel(b, *s.center), s.radius, s.ccw)


def _classify(blank: Blank, drills: list[DrillOp]):
    """Label each drill op fixing or screw by matching it to the layout's holes."""
    def hit(o, holes):
        return any(abs(o.x - h.x) <= TOL and abs(o.y - h.y) <= TOL for h in holes)

    fix_ops, screw_ops = [], []
    for o in drills:
        f, sc = hit(o, blank.fix_holes), hit(o, blank.screw_holes)
        if f == sc:
            raise ValueError(f'drill at ({o.x:.3f}, {o.y:.3f}) on {blank.id} matches '
                             f'{"both fixing and screw" if f else "no"} hole of the layout')
        (fix_ops if f else screw_ops).append(o)
    return fix_ops, screw_ops


def _program_entry(p: Program, settings: Settings) -> dict:
    lines = len(BACKENDS[BACKEND](p, settings).splitlines())
    warnings = list(p.warnings)
    if lines > LINE_WARNING and not any('lines' in w for w in warnings):
        warnings.append(f'{lines} lines, more than {LINE_WARNING}')
    return {'name': p.name, 'tool': p.tool, 'kind': p.kind, 'description': p.description,
            'ops': len(p.ops), 'lines': lines, 'warnings': warnings}


def _blank_data(b: Blank, programs: list[Program], settings: Settings):
    """(blank view in blank coordinates, holes as drilled in blank coordinates)."""
    H = b.height
    mine = [p for p in programs if p.blank == b.id]
    drills = [o for p in mine if p.kind == 'drill' for o in p.ops]
    cuts = {base_label(o.label): o for p in mine if p.kind == 'cut' for o in p.ops}
    fix_ops, screw_ops = _classify(b, drills)
    shapes = []
    for ps in b.shapes:
        moved = translate(ps.shape.outline, ps.x, ps.y)
        x0, y0, x1, y1 = bbox(moved)
        op = cuts.get(f'{b.id} {ps.name} #{ps.copy}')
        shapes.append({'name': ps.name, 'copy': ps.copy, 'path': _path(moved, H),
                       'cut_path': _path(op.segs, H) if op else '',
                       'cx': (x0 + x1) / 2, 'cy': H - (y0 + y1) / 2})
    ops = [o for p in mine for o in p.ops]
    z = {'stack_top': stack_top(settings),
         'fixing': fix_ops[0].depth if fix_ops else None,
         'screw': screw_ops[0].depth if screw_ops else None,
         'shape_cut': next((o.depth for o in reversed(ops) if isinstance(o, ContourOp)), None)}
    data = {'id': b.id, 'panel': b.panel, 'width': b.width, 'height': b.height,
            'rotated': b.rotated, 'shapes': shapes,
            'fix': [{'x': o.x, 'y': H - o.y} for o in fix_ops],
            'screw': [{'x': o.x, 'y': H - o.y} for o in screw_ops],
            'programs': [_program_entry(p, settings) for p in mine],
            'z': {k: v for k, v in z.items() if v is not None}}
    return data, fix_ops, screw_ops


def _cut_data(c: SawCut, settings: Settings) -> dict:
    pw, k = settings.panel.width, settings.panel.kerf
    if c.axis == 'x':           # runs along X at y = at .. at + kerf
        rect = [c.start, pw - (c.at + k), c.end - c.start, k]
    else:
        rect = [c.at, pw - c.end, k, c.end - c.start]
    return {'n': c.n, 'stage': c.stage, 'axis': c.axis, 'at': c.at, 'start': c.start,
            'end': c.end, 'frees': c.frees, 'blanks': list(c.blanks),
            'size': list(c.size) if c.size else None, 'rect': rect}


def _panel_data(panel: PanelPlan, holes: dict, settings: Settings) -> dict:
    pw = settings.panel.width
    blanks = []
    for b in panel.blanks:
        w, h = footprint(b)
        shapes = []
        for ps in b.shapes:
            moved = [_map_seg(s, b) for s in translate(ps.shape.outline, ps.x, ps.y)]
            x0, y0, x1, y1 = bbox(moved)
            shapes.append({'name': ps.name, 'path': _path(moved, pw),
                           'cx': (x0 + x1) / 2, 'cy': pw - (y0 + y1) / 2})
        fix_ops, screw_ops = holes[b.id]

        def mapped(ops):
            return [{'x': x, 'y': pw - y} for x, y in (to_panel(b, o.x, o.y) for o in ops)]

        blanks.append({'id': b.id, 'x': b.x, 'y': pw - (b.y + h), 'w': w, 'h': h,
                       'width': b.width, 'height': b.height, 'rotated': b.rotated,
                       'shapes': shapes, 'fix': mapped(fix_ops), 'screw': mapped(screw_ops)})
    area = settings.panel.length * settings.panel.width
    waste = panel.waste(settings)
    return {'id': panel.id, 'strips': panel.strips, 'blanks': blanks,
            'cuts': [_cut_data(c, settings) for c in panel.cuts],
            'waste': waste, 'waste_pct': 100 * waste / area}


def preview_data(plan: Plan, programs: list[Program], settings: Settings) -> dict:
    p, m = settings.panel, settings.machine
    blanks, holes = [], {}
    for b in plan.blanks:
        data, fix_ops, screw_ops = _blank_data(b, programs, settings)
        blanks.append(data)
        holes[b.id] = (fix_ops, screw_ops)
    return {'panel': {'length': p.length, 'width': p.width, 'thickness': p.thickness,
                      'edge': p.edge, 'kerf': p.kerf},
            'frame': {'x': m.frame_x, 'y': m.frame_y},
            'panels': [_panel_data(pp, holes, settings) for pp in plan.panels],
            'blanks': blanks,
            'problems': list(plan.problems)}
