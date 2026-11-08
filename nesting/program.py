"""Turn a layout plan into CNC programs: drill and cut operations with Z depths.

Heights are worked out above the cup top and converted to depths measured down
from the top of the stack (scrap + template stock + thickest shape).
No G-code text is written here.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .geometry import Arc, Line, OffsetError, Seg, offset_outline, set_direction, split_large_arcs, translate
from .layout import PanelPlan, PlacedTemplate, Plan, to_panel
from .settings import Settings

LINE_WARNING = 250


@dataclass
class DrillOp:
    x: float
    y: float
    depth: float
    diameter: float


@dataclass
class ContourOp:
    segs: list[Seg]
    depth: float
    label: str


@dataclass
class Program:
    name: str
    tool: int
    kind: str                       # 'drill' or 'cut'
    description: str
    stock: tuple[float, float, float]
    ops: list = field(default_factory=list)
    spindle_rpm: int | None = None
    plunge_feed: float = 0.0
    cut_feed: float = 0.0
    warnings: list[str] = field(default_factory=list)


def _template_stock(settings: Settings) -> float:
    """Without a template layer (mode 'none') the shapes sit straight on the scrap."""
    return 0.0 if settings.template.mode == 'none' else settings.heights.template_stock


def stack_top(settings: Settings, panel: PanelPlan) -> float:
    h = settings.heights
    thick = [s.thickness for t in panel.templates for s in t.shapes]
    return h.scrap + _template_stock(settings) + (max(thick) if thick else h.shape_thickness)


def pass_count(total: float, per_pass: float) -> int:
    return max(1, math.ceil(total / per_pass - 1e-9))


def pass_depths(total: float, per_pass: float) -> list[float]:
    """Cumulative depth of each pass: equal steps down to `total`."""
    n = pass_count(total, per_pass)
    return [total * (i + 1) / n for i in range(n)]


def _map_seg(s: Seg, t: PlacedTemplate) -> Seg:
    if isinstance(s, Line):
        return Line(to_panel(t, *s.a), to_panel(t, *s.b))
    # a quarter turn keeps the winding, so ccw is unchanged
    return Arc(to_panel(t, *s.a), to_panel(t, *s.b), to_panel(t, *s.center),
               s.radius, s.ccw)


def _contour(segs: list[Seg], settings: Settings) -> list[Seg]:
    r = settings.router
    ccw = r.direction == 'ccw'
    out = offset_outline(set_direction(segs, ccw), r.diameter / 2, outward=True)
    return split_large_arcs(set_direction(out, ccw))


def _panel_number(panel: PanelPlan) -> str:
    digits = ''.join(c for c in panel.id if c.isdigit())
    return digits or panel.id.upper()


def _finish(p: Program, settings: Settings) -> Program:
    from .backends import BACKENDS      # late: the backends import this module
    lines = len(BACKENDS['cnc90'](p, settings).splitlines())
    if lines > LINE_WARNING:
        p.warnings.append(f'{p.name}: about {lines} lines, over {LINE_WARNING}')
    return p


def base_label(label: str) -> str:
    """A contour label without its ' pass k/n' suffix."""
    return re.sub(r' pass \d+/\d+$', '', label)


def _pass_ops(segs: list[Seg], label: str, start: float, material: float,
              settings: Settings) -> list[ContourOp]:
    """One ContourOp per pass; passes are counted over the material only."""
    n = pass_count(material, settings.router.depth_per_pass)
    return [ContourOp(segs, start + material * k / n, f'{label} pass {k}/{n}')
            for k in range(1, n + 1)]


def _rect_segs(t: PlacedTemplate) -> list[Seg]:
    w, h = (t.height, t.width) if t.rotated else (t.width, t.height)
    pts = [(t.x, t.y), (t.x + w, t.y), (t.x + w, t.y + h), (t.x, t.y + h)]
    return [Line(pts[i], pts[(i + 1) % 4]) for i in range(4)]


def _panel_programs(panel: PanelPlan, settings: Settings) -> list[Program]:
    h, r = settings.heights, settings.router
    fix, screw = settings.drill_fix, settings.drill_screw
    top = stack_top(settings, panel)
    stock = (settings.panel.length, settings.panel.width, top)
    n = _panel_number(panel)

    fix_depth = top - (h.scrap - h.fix_into_scrap)
    ts = _template_stock(settings)
    screw_depth = top - (h.scrap + ts - screw.depth)
    # with a template the cut ends just into it; without, just into the scrap
    shape_into = h.into_template if ts else h.into_scrap     # how far a shape cut goes below its bottom

    fix_ops: list[DrillOp] = []
    screw_ops: list[DrillOp] = []
    cuts: list[ContourOp] = []
    outlines: list[ContourOp] = []
    for t in panel.templates:
        for hole in t.fix_holes:
            x, y = to_panel(t, hole.x, hole.y)
            fix_ops.append(DrillOp(x, y, fix_depth, hole.diameter))
        for hole in t.screw_holes:
            x, y = to_panel(t, hole.x, hole.y)
            screw_ops.append(DrillOp(x, y, screw_depth, hole.diameter))
        for ps in t.shapes:
            moved = translate(ps.shape.outline, ps.x, ps.y)
            label = f'{t.id} {ps.name} #{ps.copy}'
            try:
                segs = _contour([_map_seg(s, t) for s in moved], settings)
            except OffsetError as e:
                raise OffsetError(f'{label}: {e}') from e
            t0 = top - (h.scrap + ts + ps.thickness)
            cuts += _pass_ops(segs, label, t0, ps.thickness + shape_into, settings)
        if ts:    # no template layer, no template outline
            outlines += _pass_ops(_contour(_rect_segs(t), settings), f'{t.id} outline',
                                  top - (h.scrap + ts), ts + h.into_scrap, settings)

    progs: list[Program] = []

    def drill(name, tool, ops, desc, feed):
        if ops:
            progs.append(Program(name, tool, 'drill', desc, stock, ops, None, feed, feed))

    if fix.tool == screw.tool and fix.diameter == screw.diameter:
        drill(f'N{n}F', fix.tool, fix_ops + screw_ops, 'Fixing and screw holes', fix.feed)
    else:
        drill(f'N{n}F', fix.tool, fix_ops, 'Fixing holes', fix.feed)
        drill(f'N{n}S', screw.tool, screw_ops, 'Screw holes', screw.feed)
    if cuts or outlines:
        progs.append(Program(f'N{n}C', r.tool, 'cut', 'Shapes and template outlines',
                             stock, cuts + outlines, int(r.spindle_rpm),
                             r.plunge_feed, r.cut_feed))
    return [_finish(p, settings) for p in progs]


def plan_programs(plan: Plan, settings: Settings) -> list[Program]:
    return [p for panel in plan.panels for p in _panel_programs(panel, settings)]
