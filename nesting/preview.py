"""Preview data for the UI, built from the programs the machine will get.

Hole positions and cut paths come from the programs' DrillOp / ContourOp objects (program
frame, see program.py); the panel view maps those same numbers back to the layout frame and onto
the panel. Only the un-offset shape outlines and the saw plan come from the layout.

SVG y runs down. Blank (job) view: with machine.y_toward 'front' the program frame already has
Y down from the top-left origin, so the SVG numbers are the program numbers unchanged; with
'back' they are flipped (height - y). Panel view: always flipped (panel width - y), the panel's
origin corner is bottom left. x, y of a rectangle are its top-left corner.
"""
from __future__ import annotations

import math
import re

from .backends import BACKENDS
from .geometry import Arc, Line, _sweep, bbox, translate
from .layout import Blank, PanelPlan, Plan, SawCut, footprint, to_panel
from .pockets import PocketGroup, effective, find_groups, group_for
from .program import (LINE_WARNING, ContourOp, DrillOp, Program, base_label, plan_shapes,
                      segs_to_program, stack_top, to_program, y_flipped)
from .settings import Settings

BACKEND = 'cnc90'
TOL = 0.001


def _path(segs, flip: float | None) -> str:
    """SVG path with true arcs. SVG sweep 1 is the direction of increasing angle in the numbers
    written, so an arc that is counter-clockwise in its own numbers gets sweep 1 unflipped.
    flip=h writes h - y, which reverses the turning direction: then ccw becomes sweep 0."""
    if not segs:
        return ''

    def fy(y):
        return y if flip is None else flip - y
    out = [f'M{segs[0].a[0]:.3f},{fy(segs[0].a[1]):.3f}']
    for sg in segs:
        x, y = sg.b[0], fy(sg.b[1])
        if isinstance(sg, Line):
            out.append(f'L{x:.3f},{y:.3f}')
        else:
            large = int(_sweep(sg) > math.pi)
            sweep = int(sg.ccw) if flip is None else int(not sg.ccw)
            out.append(f'A{sg.radius:.3f},{sg.radius:.3f} 0 {large} {sweep} {x:.3f},{y:.3f}')
    return ' '.join(out)


def _job_flip(b: Blank, settings: Settings) -> float | None:
    """Program frame -> SVG of the blank view: none when Y already runs down (front)."""
    return None if y_flipped(settings) else b.height


def _map_seg(s, b: Blank):
    """Blank-frame segment -> panel frame; a quarter turn keeps the winding."""
    if isinstance(s, Line):
        return Line(to_panel(b, *s.a), to_panel(b, *s.b))
    return Arc(to_panel(b, *s.a), to_panel(b, *s.b), to_panel(b, *s.center), s.radius, s.ccw)


def _classify(blank: Blank, drills: list[DrillOp], settings: Settings):
    """Label each drill op fixing or screw by matching it to the layout's holes."""
    def hit(o, holes):
        return any(abs(o.x - x) <= TOL and abs(o.y - y) <= TOL
                   for x, y in (to_program(blank, settings, h.x, h.y) for h in holes))

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
    return {'name': p.name, 'tool': p.tool, 'tools': p.tools, 'kind': p.kind,
            'description': p.description, 'ops': len(p.ops), 'lines': lines, 'warnings': warnings}


def _drill_tools(fix_ops, screw_ops, tool_of, settings: Settings) -> list[dict]:
    """Per hole kind of the blank's drill program: tool, diameter and feed (the last two from
    the settings: the emitter writes neither), hole count and depth."""
    out = []
    for what, ops, cfg in (('fixing', fix_ops, settings.drill_fix),
                           ('screw', screw_ops, settings.drill_screw)):
        if ops:
            out.append({'holes': what, 'count': len(ops), 'tool': tool_of(ops[0]),
                        'diameter': cfg.diameter, 'feed': cfg.feed, 'depth': ops[0].depth})
    return out


_RING = re.compile(r' (G\d+) pocket \d+ pass (\d+)/\d+ ring \d+/\d+$')


def _pocket_rings(mine: list[Program], colors: dict, flip: float | None) -> list[dict]:
    """One SVG path per ring of the first depth pass of the blank's pocket program: the
    segments the emitter writes (program frame), later passes repeat the same rings."""
    out = []
    for p in mine:
        if p.kind != 'pocket':
            continue
        for o in p.ops:
            m = _RING.search(o.label)
            if m and m.group(2) == '1':
                out.append({'group': m.group(1), 'color': colors.get(m.group(1), ''),
                            'path': _path(o.segs, flip)})
    return out


def pocket_groups_data(plan: Plan, settings: Settings,
                       pocket_overrides: dict | None = None,
                       groups: list[PocketGroup] | None = None) -> list[dict]:
    """The plan's pocket groups with their effective settings (defaults + overrides), for the
    UI and the run sheet. count is the number of pockets on the plan, copies included. A group
    whose override is invalid gets enabled False, the default settings and an `error`.
    groups: the project's groups (ids and colours over every shape of the project); only
    those with a pocket on the plan are listed. None: found over the plan's shapes."""
    given = groups is not None
    if not given:
        groups = find_groups(plan_shapes(plan))
    counts = {g.id: 0 for g in groups}
    for b in plan.blanks:
        for ps in b.shapes:
            for pk in ps.shape.pockets:
                g = group_for(pk, groups)
                if g is not None:
                    counts[g.id] += 1
    out = []
    for g in groups:
        if given and not counts[g.id]:
            continue
        error = None
        try:
            gs = effective(g.key, pocket_overrides or {}, settings.pockets)
        except ValueError as e:
            gs = effective(g.key, {}, settings.pockets)
            gs.enabled = False
            error = f'pocket group {g.id}: {e}'
        d = {'id': g.id, 'key': g.key, 'width': g.width, 'height': g.height, 'kind': g.kind,
             'count': counts[g.id], 'color': g.color, 'enabled': gs.enabled, 'tool': gs.tool,
             'diameter': gs.diameter, 'depth': gs.depth, 'depth_per_pass': gs.depth_per_pass,
             'plunge_feed': gs.plunge_feed, 'cut_feed': gs.cut_feed,
             'stepover_pct': gs.stepover_pct, 'direction': gs.direction}
        if error:
            d['error'] = error
        out.append(d)
    return out


def _blank_data(b: Blank, programs: list[Program], settings: Settings,
                groups: list[PocketGroup] | None = None):
    """(blank view: program frame drawn for SVG, holes as drilled in the program frame)."""
    groups = groups or []
    colors = {g.id: g.color for g in groups}
    flip = _job_flip(b, settings)

    def sy(y):
        return y if flip is None else flip - y
    mine = [p for p in programs if p.blank == b.id]
    drills = [o for p in mine if p.kind == 'drill' for o in p.ops]
    tool_by_op = {id(o): p.op_tool(o) for p in mine if p.kind == 'drill' for o in p.ops}
    cuts = {base_label(o.label): o for p in mine if p.kind == 'cut' for o in p.ops}
    fix_ops, screw_ops = _classify(b, drills, settings)
    shapes = []
    for ps in b.shapes:
        moved = segs_to_program(b, settings, translate(ps.shape.outline, ps.x, ps.y))
        x0, y0, x1, y1 = bbox(moved)
        op = cuts.get(f'{b.id} {ps.name} #{ps.copy}')
        pockets = []
        for pk in ps.shape.pockets:
            g = group_for(pk, groups)
            if g is not None:
                pocket = segs_to_program(b, settings, translate(pk.outline, ps.x, ps.y))
                pockets.append({'group': g.id, 'path': _path(pocket, flip), 'color': g.color})
        shapes.append({'name': ps.name, 'copy': ps.copy, 'path': _path(moved, flip),
                       'cut_path': _path(op.segs, flip) if op else '', 'pockets': pockets,
                       'cx': (x0 + x1) / 2, 'cy': sy((y0 + y1) / 2)})
    ops = [o for p in mine if p.kind == 'cut' for o in p.ops]
    z = {'stack_top': stack_top(settings),
         'fixing': fix_ops[0].depth if fix_ops else None,
         'screw': screw_ops[0].depth if screw_ops else None,
         'shape_cut': next((o.depth for o in reversed(ops) if isinstance(o, ContourOp)), None)}
    data = {'id': b.id, 'panel': b.panel, 'width': b.width, 'height': b.height,
            'rotated': b.rotated, 'shapes': shapes,
            'fix': [{'x': o.x, 'y': sy(o.y)} for o in fix_ops],
            'screw': [{'x': o.x, 'y': sy(o.y)} for o in screw_ops],
            'pocket_rings': _pocket_rings(mine, colors, flip),
            'programs': [_program_entry(p, settings) for p in mine],
            'drill_tools': _drill_tools(fix_ops, screw_ops, lambda o: tool_by_op[id(o)], settings),
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
            """Drill ops (program frame) -> layout frame -> panel."""
            return [{'x': x, 'y': pw - y} for x, y in
                    (to_panel(b, *to_program(b, settings, o.x, o.y)) for o in ops)]

        blanks.append({'id': b.id, 'x': b.x, 'y': pw - (b.y + h), 'w': w, 'h': h,
                       'width': b.width, 'height': b.height, 'rotated': b.rotated,
                       'shapes': shapes, 'fix': mapped(fix_ops), 'screw': mapped(screw_ops)})
    area = settings.panel.length * settings.panel.width
    waste = panel.waste(settings)
    return {'id': panel.id, 'strips': panel.strips, 'blanks': blanks,
            'cuts': [_cut_data(c, settings) for c in panel.cuts],
            'waste': waste, 'waste_pct': 100 * waste / area}


def preview_data(plan: Plan, programs: list[Program], settings: Settings,
                 pocket_overrides: dict | None = None,
                 groups: list[PocketGroup] | None = None) -> dict:
    """groups: the project's pocket groups, as given to plan_programs (None: found over the
    plan's shapes, as plan_programs does without them)."""
    p, m = settings.panel, settings.machine
    pocket_groups = pocket_groups_data(plan, settings, pocket_overrides, groups)
    if groups is None:
        groups = find_groups(plan_shapes(plan))
    problems = list(plan.problems) + [g['error'] for g in pocket_groups if 'error' in g]
    blanks, holes = [], {}
    for b in plan.blanks:
        data, fix_ops, screw_ops = _blank_data(b, programs, settings, groups)
        blanks.append(data)
        holes[b.id] = (fix_ops, screw_ops)
    return {'panel': {'length': p.length, 'width': p.width, 'thickness': p.thickness,
                      'edge': p.edge, 'kerf': p.kerf},
            'frame': {'x': m.frame_x, 'y': m.frame_y},
            'y_toward': m.y_toward,
            'panels': [_panel_data(pp, holes, settings) for pp in plan.panels],
            'blanks': blanks,
            'pocket_groups': pocket_groups,
            'problems': problems}
