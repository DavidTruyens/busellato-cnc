"""Turn a layout plan into CNC programs: drill and cut operations with Z depths, per blank.

The machine runs one blank at a time. Two frames exist for a blank:

- the layout frame (layout.py, dxf.py): origin at the blank's lower-left corner as drawn, y up;
- the program frame, what the machine gets: X0 Y0 at the blank's corner against the pins, X along
  the long side. With `machine.y_toward` 'front' (default) the origin is the blank's back-left
  corner (top left of the picture, operator at the bottom) and Y grows toward the front:
  Y_prog = blank height - y. With 'back' the program frame is the layout frame.

`to_program` / `segs_to_program` are the only place that mapping is made. The contour direction
setting is the turning sense seen from above in that picture; it is applied in the layout frame
(y up, so it is the ordinary mathematical sense there) and the mirror then flips the arcs'
G2/G3 sense in the program numbers. The stack on the cups is scrap + blank; depths are measured
down from the top of the stack. No G-code text is written here.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .geometry import (OffsetError, Pt, Seg, bbox, mirror_y, offset_outline, set_direction,
                       split_large_arcs, translate)
from .layout import Blank, Plan
from .settings import Settings

LINE_WARNING = 250
KINDS = ('D', 'C')              # drill (fixing + screw holes, any tools), cut
NAME = re.compile(r'[A-Z0-9_-]{1,8}')


@dataclass
class DrillOp:
    x: float
    y: float
    depth: float
    diameter: float
    tool: int | None = None         # this hole's tool; None = the program's tool


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
    blank: str = ''                 # id of the blank this program is for

    def op_tool(self, op) -> int:
        """The tool an op runs with: a drill op may carry its own, else the program's."""
        t = getattr(op, 'tool', None)
        return self.tool if t is None else t

    @property
    def tools(self) -> list[int]:
        """Every tool the program uses, in the order it first uses them. `tool` is the first
        one (a drill program may mix tools: every G81 line names its own)."""
        out: list[int] = []
        for op in self.ops:
            t = self.op_tool(op)
            if t not in out:
                out.append(t)
        return out or [self.tool]


class ProgramError(ValueError):
    """A program would be unsafe to run (for example a depth into the vacuum cups)."""


def check_depths(p: Program) -> None:
    """Raise ProgramError when an op reaches the top of the cups: depth >= stack top (stock Z)."""
    top = p.stock[2]
    for op in p.ops:
        if op.depth >= top:
            what = (f'contour {op.label}' if isinstance(op, ContourOp)
                    else f'drill at X{op.x:.3f} Y{op.y:.3f}')
            raise ProgramError(f'{p.name}: {what} goes to depth {op.depth:.3f}, at or below '
                               f'the top of the vacuum cups (stack height {top:.3f}); '
                               f'nothing is generated')


def stack_top(settings: Settings) -> float:
    """Scrap plate + blank: the stock Z of every program."""
    return settings.stack


def pass_count(total: float, per_pass: float) -> int:
    return max(1, math.ceil(total / per_pass - 1e-9))


def pass_depths(total: float, per_pass: float) -> list[float]:
    """Cumulative depth of each pass: equal steps down to `total`."""
    n = pass_count(total, per_pass)
    return [total * (i + 1) / n for i in range(n)]


def y_flipped(settings: Settings) -> bool:
    """True when program Y runs opposite to layout y (machine.y_toward 'front')."""
    return settings.machine.y_toward == 'front'


def to_program(blank: Blank, settings: Settings, x: float, y: float) -> Pt:
    """Layout-frame point of a blank -> program frame. Its own inverse."""
    return (x, blank.height - y) if y_flipped(settings) else (x, y)


def segs_to_program(blank: Blank, settings: Settings, segs: list[Seg]) -> list[Seg]:
    """Layout-frame segments of a blank -> program frame (arcs flip ccw when mirrored)."""
    return mirror_y(segs, blank.height) if y_flipped(settings) else list(segs)


def _contour(segs: list[Seg], settings: Settings) -> list[Seg]:
    """Tool-centre path of a layout-frame outline, still in the layout frame. The direction
    setting is the sense seen from above, which is the mathematical sense in the y-up layout
    frame; the offset is outward there."""
    r = settings.router
    ccw = r.direction == 'ccw'
    out = offset_outline(set_direction(segs, ccw), r.diameter / 2, outward=True)
    return split_large_arcs(set_direction(out, ccw))


def program_name(blank_id: str, kind: str) -> str:
    """B<nn><D|C> (drill, cut): the first character B is the machine folder SRG\\B."""
    return f'{blank_id}{kind}'


def group_by_tool(ops: list[DrillOp]) -> list[DrillOp]:
    """Drill ops with each tool's holes together, tools in the order they first appear; a
    stable sort, so the order within a tool (fixing holes before screw holes) is kept."""
    first: dict = {}
    for o in ops:
        first.setdefault(o.tool, len(first))
    return sorted(ops, key=lambda o: first[o.tool])


def _outside_blank(p: Program, blank: Blank, settings: Settings) -> str | None:
    """A warning when the cutter edge (tool centre path widened by the radius) leaves the blank."""
    segs = [s for op in p.ops if isinstance(op, ContourOp) for s in op.segs]
    if not segs:
        return None
    r = settings.router.diameter / 2
    x0, y0, x1, y1 = bbox(segs)
    x0, y0, x1, y1 = x0 - r, y0 - r, x1 + r, y1 + r
    eps = 1e-6
    if x0 >= -eps and y0 >= -eps and x1 <= blank.width + eps and y1 <= blank.height + eps:
        return None
    return (f'{p.name}: cutter reaches X{x0:.1f}..{x1:.1f}, Y{y0:.1f}..{y1:.1f}, '
            f'outside the blank 0..{blank.width:g} x 0..{blank.height:g}')


def _finish(p: Program, blank: Blank, settings: Settings) -> Program:
    check_depths(p)
    outside = _outside_blank(p, blank, settings)
    if outside:
        p.warnings.append(outside)
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


def blank_programs(blank: Blank, settings: Settings) -> list[Program]:
    """Drill and cut programs of one blank, in the program frame (see the module doc)."""
    h, r = settings.heights, settings.router
    fix, screw = settings.drill_fix, settings.drill_screw
    thick = settings.panel.thickness
    top = stack_top(settings)
    stock = (blank.width, blank.height, top)

    fix_depth = thick + h.fix_into_scrap          # through the blank, into the scrap
    screw_depth = thick + screw.depth
    def drill_op(o, depth, d):
        return DrillOp(*to_program(blank, settings, o.x, o.y), depth, d.diameter, d.tool)

    fix_ops = [drill_op(o, fix_depth, fix) for o in blank.fix_holes]
    screw_ops = [drill_op(o, screw_depth, screw) for o in blank.screw_holes]
    cuts: list[ContourOp] = []
    for ps in blank.shapes:
        label = f'{blank.id} {ps.name} #{ps.copy}'
        try:
            segs = _contour(translate(ps.shape.outline, ps.x, ps.y), settings)
        except OffsetError as e:
            raise OffsetError(f'{label}: {e}') from e
        segs = segs_to_program(blank, settings, segs)
        # through the blank from its top, just into the scrap
        cuts += _pass_ops(segs, label, 0.0, thick + h.into_scrap, settings)

    progs: list[Program] = []
    drills = group_by_tool(fix_ops + screw_ops)
    if drills:
        desc = ' and '.join(w for w, ops in (('Fixing', fix_ops), ('screw', screw_ops)) if ops)
        desc = desc[0].upper() + desc[1:] + ' holes'
        # one program for every hole of the blank, whatever the tools: each G81 line names its
        # own tool, like many of the machine's own programs. Feeds are not written (the
        # control uses each tool's own feed); plunge/cut feed only fill the record.
        progs.append(Program(program_name(blank.id, 'D'), drills[0].tool, 'drill', desc, stock,
                             drills, None, fix.feed, fix.feed, blank=blank.id))
    if cuts:
        progs.append(Program(program_name(blank.id, 'C'), r.tool, 'cut', 'Shape outlines',
                             stock, cuts, int(r.spindle_rpm), r.plunge_feed, r.cut_feed,
                             blank=blank.id))
    return [_finish(p, blank, settings) for p in progs]


def plan_programs(plan: Plan, settings: Settings) -> list[Program]:
    progs = [p for b in plan.blanks for p in blank_programs(b, settings)]
    names = [p.name for p in progs]
    if len(names) != len(set(names)):       # cannot happen with unique blank ids
        raise ProgramError('two programs would get the same name')
    for name in names:
        if not NAME.fullmatch(name):
            raise ProgramError(f'{name}: not a valid program name (1-8 characters A-Z 0-9 _ -)')
    return progs
