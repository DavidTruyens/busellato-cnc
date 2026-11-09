"""Turn a layout plan into CNC programs: drill and cut operations with Z depths, per blank.

The machine runs one blank at a time: programs are written in blank coordinates (origin at the
blank's corner, X along its long side). The stack on the cups is scrap + blank; depths are
measured down from the top of the stack. No G-code text is written here.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .geometry import (OffsetError, Seg, bbox, offset_outline, set_direction,
                       split_large_arcs, translate)
from .layout import Blank, Plan
from .settings import Settings

LINE_WARNING = 250
KINDS = ('F', 'S', 'C')         # fixing holes, screw holes, cut
NAME = re.compile(r'[A-Z0-9_-]{1,8}')


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
    blank: str = ''                 # id of the blank this program is for


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


def _contour(segs: list[Seg], settings: Settings) -> list[Seg]:
    r = settings.router
    ccw = r.direction == 'ccw'
    out = offset_outline(set_direction(segs, ccw), r.diameter / 2, outward=True)
    return split_large_arcs(set_direction(out, ccw))


def program_name(blank_id: str, kind: str) -> str:
    """B<nn><F|S|C>: the first character B is the machine folder SRG\\B."""
    return f'{blank_id}{kind}'


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
    """Drill and cut programs of one blank, in blank coordinates."""
    h, r = settings.heights, settings.router
    fix, screw = settings.drill_fix, settings.drill_screw
    thick = settings.panel.thickness
    top = stack_top(settings)
    stock = (blank.width, blank.height, top)

    fix_depth = thick + h.fix_into_scrap          # through the blank, into the scrap
    screw_depth = thick + screw.depth
    fix_ops = [DrillOp(o.x, o.y, fix_depth, o.diameter) for o in blank.fix_holes]
    screw_ops = [DrillOp(o.x, o.y, screw_depth, o.diameter) for o in blank.screw_holes]
    cuts: list[ContourOp] = []
    for ps in blank.shapes:
        label = f'{blank.id} {ps.name} #{ps.copy}'
        try:
            segs = _contour(translate(ps.shape.outline, ps.x, ps.y), settings)
        except OffsetError as e:
            raise OffsetError(f'{label}: {e}') from e
        # through the blank from its top, just into the scrap
        cuts += _pass_ops(segs, label, 0.0, thick + h.into_scrap, settings)

    progs: list[Program] = []

    def drill(kind, tool, ops, desc, feed):
        if ops:
            progs.append(Program(program_name(blank.id, kind), tool, 'drill', desc, stock, ops,
                                 None, feed, feed, blank=blank.id))

    if fix.tool == screw.tool and fix.diameter == screw.diameter:
        drill('F', fix.tool, fix_ops + screw_ops, 'Fixing and screw holes', fix.feed)
    else:
        drill('F', fix.tool, fix_ops, 'Fixing holes', fix.feed)
        drill('S', screw.tool, screw_ops, 'Screw holes', screw.feed)
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
