"""Preview data for the UI, built from the programs the machine will get.

Hole positions and cut paths come from the programs' DrillOp / ContourOp objects.
Only the un-offset shape outlines come from the layout.
Y is flipped for SVG (panel width - y); template x, y are the top-left corner.
"""
from __future__ import annotations

import math

from .backends import BACKENDS
from .geometry import Line, _sweep, bbox, translate
from .layout import PanelPlan, PlacedTemplate, Plan, footprint, to_panel
from .program import LINE_WARNING, base_label, ContourOp, DrillOp, Program, _map_seg, _panel_number, stack_top
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


def _inside(t: PlacedTemplate, x: float, y: float) -> bool:
    w, h = footprint(t)
    return t.x <= x <= t.x + w and t.y <= y <= t.y + h


def _classify(panel: PanelPlan, drills: list[DrillOp]):
    """Label each drill op fixing or screw by matching it to the layout's holes."""
    def mapped(attr):
        return [to_panel(t, h.x, h.y) for t in panel.templates for h in getattr(t, attr)]

    fix_at, screw_at = mapped('fix_holes'), mapped('screw_holes')

    def hit(o, at):
        return any(abs(o.x - x) <= TOL and abs(o.y - y) <= TOL for x, y in at)

    fix_ops, screw_ops = [], []
    for o in drills:
        f, sc = hit(o, fix_at), hit(o, screw_at)
        if f == sc:
            raise ValueError(f'drill at ({o.x:.3f}, {o.y:.3f}) on {panel.id} matches '
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


def _panel_data(panel: PanelPlan, programs: list[Program], settings: Settings) -> dict:
    pw = settings.panel.width
    prefix = f'N{_panel_number(panel)}'
    mine = [p for p in programs if p.name.startswith(prefix)
            and p.name[len(prefix):] in ('F', 'S', 'C')]
    drills = [o for p in mine if p.kind == 'drill' for o in p.ops]
    cuts = {base_label(o.label): o for p in mine if p.kind == 'cut' for o in p.ops}
    fix_ops, screw_ops = _classify(panel, drills)

    def holes(t, ops):
        return [{'x': o.x, 'y': pw - o.y} for o in ops if _inside(t, o.x, o.y)]

    templates = []
    for t in panel.templates:
        w, h = footprint(t)
        shapes = []
        for ps in t.shapes:
            moved = [_map_seg(s, t) for s in translate(ps.shape.outline, ps.x, ps.y)]
            x0, y0, x1, y1 = bbox(moved)
            op = cuts.get(f'{t.id} {ps.name} #{ps.copy}')
            shapes.append({'name': ps.name, 'path': _path(moved, pw),
                           'cut_path': _path(op.segs, pw) if op else '',
                           'cx': (x0 + x1) / 2, 'cy': pw - (y0 + y1) / 2})
        outline = cuts.get(f'{t.id} outline')
        templates.append({'id': t.id, 'x': t.x, 'y': pw - (t.y + h), 'w': w, 'h': h,
                          'rotated': t.rotated, 'shapes': shapes,
                          'cut_path': _path(outline.segs, pw) if outline else '',
                          'fix': holes(t, fix_ops), 'screw': holes(t, screw_ops)})

    ops = [o for p in mine for o in p.ops]
    shape_cut = next((o.depth for o in reversed(ops) if isinstance(o, ContourOp)
                      and not base_label(o.label).endswith(' outline')), None)
    z = {'stack_top': stack_top(settings, panel),
         'fixing': fix_ops[0].depth if fix_ops else None,
         'screw': screw_ops[0].depth if screw_ops else None,
         'shape_cut': shape_cut,
         'template_cut': next((o.depth for o in reversed(ops) if isinstance(o, ContourOp)
                               and base_label(o.label).endswith(' outline')), None)}
    return {'id': panel.id, 'templates': templates,
            'programs': [_program_entry(p, settings) for p in mine],
            'z': {k: v for k, v in z.items() if v is not None}}


def preview_data(plan: Plan, programs: list[Program], settings: Settings) -> dict:
    return {'panel': {'length': settings.panel.length, 'width': settings.panel.width},
            'panels': [_panel_data(p, programs, settings) for p in plan.panels],
            'problems': list(plan.problems)}
