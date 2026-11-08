"""Preview data for the UI, built from the programs the machine will get.

Hole positions and cut paths come from the programs' DrillOp / ContourOp objects.
Only the un-offset shape outlines come from the layout.
Y is flipped for SVG (panel width - y); template x, y are the top-left corner.
"""
from __future__ import annotations

from .backends import BACKENDS
from .geometry import bbox, sample, translate
from .layout import PanelPlan, PlacedTemplate, Plan, footprint
from .program import LINE_WARNING, ContourOp, Program, _map_seg, _panel_number, stack_top
from .settings import Settings

BACKEND = 'cnc90'


def _path(points, flip: float) -> str:
    return ' '.join(f'{"M" if i == 0 else "L"}{x:.3f},{flip - y:.3f}'
                    for i, (x, y) in enumerate(points))


def _inside(t: PlacedTemplate, x: float, y: float) -> bool:
    w, h = footprint(t)
    return t.x <= x <= t.x + w and t.y <= y <= t.y + h


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
    cuts = {o.label: o for p in mine if p.kind == 'cut' for o in p.ops}
    # drill programs list fixing holes first, then screw holes
    n_fix = sum(len(t.fix_holes) for t in panel.templates)
    fix_ops, screw_ops = drills[:n_fix], drills[n_fix:]

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
            shapes.append({'name': ps.name, 'path': _path(sample(moved), pw),
                           'cut_path': _path(sample(op.segs), pw) if op else '',
                           'cx': (x0 + x1) / 2, 'cy': pw - (y0 + y1) / 2})
        outline = cuts.get(f'{t.id} outline')
        templates.append({'id': t.id, 'x': t.x, 'y': pw - (t.y + h), 'w': w, 'h': h,
                          'rotated': t.rotated, 'shapes': shapes,
                          'cut_path': _path(sample(outline.segs), pw) if outline else '',
                          'fix': holes(t, fix_ops), 'screw': holes(t, screw_ops)})

    ops = [o for p in mine for o in p.ops]
    shape_cut = next((o.depth for o in ops if isinstance(o, ContourOp)
                      and not o.label.endswith(' outline')), None)
    z = {'stack_top': stack_top(settings, panel),
         'fixing': fix_ops[0].depth if fix_ops else None,
         'screw': screw_ops[0].depth if screw_ops else None,
         'shape_cut': shape_cut,
         'template_cut': next((o.depth for o in ops if isinstance(o, ContourOp)
                               and o.label.endswith(' outline')), None)}
    return {'id': panel.id, 'templates': templates,
            'programs': [_program_entry(p, settings) for p in mine],
            'z': {k: v for k, v in z.items() if v is not None}}


def preview_data(plan: Plan, programs: list[Program], settings: Settings) -> dict:
    return {'panel': {'length': settings.panel.length, 'width': settings.panel.width},
            'panels': [_panel_data(p, programs, settings) for p in plan.panels],
            'problems': list(plan.problems)}
