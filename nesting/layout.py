"""Group shapes into blanks and plan how a panel saw cuts the blanks from the stock panels.

Physical model (corrected 2026-11-09): the machine's work frame is smaller than a panel, so a
panel saw cuts each 1220 x 2440 panel into rectangular blanks. One blank at a time lies on the
scrap plate on the vacuum cups, screwed down through 4 fixing holes in its margin; the shapes
are cut out of the blank and the blank's leftover frame is never cut.

Coordinates: blank (layout) coordinates have the origin at the blank's lower-left corner as
drawn, y up, X along the blank's long side (machine X). The programs use the program frame, which
program.py maps from these (machine.y_toward). Panel coordinates have the origin at the panel's origin corner, X along the
panel length. A blank may lie turned 90 degrees on the panel; that only matters for the saw.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .dxf import Hole, Shape
from .geometry import Pt
from .settings import Settings

EPS = 1e-9
MAX_QTY = 500   # copies per shape: a safety bound for what the UI can ask for


class LayoutError(ValueError):
    """A shape cannot be placed at all (it does not fit a blank alone): nothing is generated."""


@dataclass
class ShapeEntry:
    shape: Shape
    qty: int = 1
    enabled: bool = True


@dataclass
class PlacedShape:
    name: str
    copy: int
    x: float            # shape's bounding-box corner in blank coordinates
    y: float
    shape: Shape


@dataclass
class Blank:
    id: str
    width: float        # along blank X (machine X): the long side
    height: float       # along blank Y (machine Y)
    shapes: list[PlacedShape]
    fix_holes: list[Hole]
    screw_holes: list[Hole]
    panel: str = ''
    x: float = 0.0      # bottom-left of the footprint on the panel
    y: float = 0.0
    rotated: bool = False   # True: blank X runs along panel Y


@dataclass
class SawCut:
    """One straight panel-saw cut, edge to edge through the piece being cut.

    stage 1 cuts the panel into strips, stage 2 cuts a strip into pieces, stage 3 trims a piece
    that is narrower than its strip. `axis` is the direction the cut runs on the panel ('x':
    along the panel length, at a constant y; 'y': along the panel width, at a constant x).
    `at` is the near side of the kerf in mm from the panel's origin corner (the kerf is
    at .. at + kerf); `start`..`end` is the cut's extent along `axis`. The cut frees the piece on
    its origin side: `frees` is 'offcut', 'strip', 'rough' (a blank still to be trimmed in stage
    3) or 'blank'; `size` is that piece's size along panel X and panel Y.
    """
    n: int
    stage: int
    axis: str
    at: float
    start: float
    end: float
    frees: str
    blanks: list[str]
    size: tuple[float, float] | None = None


@dataclass
class PanelPlan:
    id: str
    blanks: list[Blank] = field(default_factory=list)
    cuts: list[SawCut] = field(default_factory=list)
    strips: str = 'x'       # the axis the stage 1 cuts run along

    def waste(self, settings: Settings) -> float:
        """Panel area not in a blank (trim, kerf, offcuts), mm2."""
        p = settings.panel
        return p.length * p.width - sum(b.width * b.height for b in self.blanks)


@dataclass
class Plan:
    panels: list[PanelPlan] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def blanks(self) -> list[Blank]:
        return [b for p in self.panels for b in p.blanks]


class _Unfit(Exception):
    """A group of shapes cannot become a blank (message names the shapes)."""


@dataclass
class _Item:
    shape: Shape
    copy: int

    @property
    def label(self) -> str:
        return self.shape.name


def to_panel(b: Blank, x: float, y: float) -> Pt:
    """Blank-frame point -> panel-frame point. Rotated = 90 degrees counter-clockwise."""
    if b.rotated:
        return b.x + b.height - y, b.y + x
    return b.x + x, b.y + y


def footprint(b: Blank) -> tuple[float, float]:
    return (b.height, b.width) if b.rotated else (b.width, b.height)


def _expand(entries: list[ShapeEntry]) -> list[_Item]:
    items = []
    for e in entries:
        if not e.enabled:
            continue
        items.extend(_Item(e.shape, i + 1) for i in range(max(int(e.qty), 0)))
    return items


def _groups(items: list[_Item], settings: Settings) -> list[list[_Item]]:
    b = settings.blank
    if b.group_by == 'length':
        # neighbours by length: optimal for the sum of the blank lengths
        items = sorted(items, key=lambda i: (-i.shape.length, -i.shape.width, i.shape.name))
    return [items[k:k + b.shapes_per] for k in range(0, len(items), b.shapes_per)]


def _build_blank(group: list[_Item], settings: Settings) -> Blank:
    """Blank around the group; raises _Unfit if a clearance rule or a size limit is not met."""
    b = settings.blank
    gap = settings.gap
    names = ', '.join(i.label for i in group)
    group = sorted(group, key=lambda i: -i.shape.width)       # widest at the bottom
    length = max(i.shape.length for i in group)
    stack = sum(i.shape.width for i in group) + gap * (len(group) - 1)
    mend, mside = b.margin_end, b.margin_side
    # whole mm, so the saw can cut it; the extra (< 1 mm) goes to the far margins
    W, H = math.ceil(length + 2 * mend - 1e-6), math.ceil(stack + 2 * mside - 1e-6)

    placed, screws, y = [], [], mside
    for i in group:
        placed.append(PlacedShape(i.shape.name, i.copy, mend, y, i.shape))
        screws.extend(Hole(mend + h.x, y + h.y, settings.drill_screw.diameter)
                      for h in i.shape.holes)
        y += i.shape.width + gap
    ins = b.fix_inset
    # the head must sit inside the blank, 3 mm clear of its edge
    min_inset = b.head_dia / 2 + 3.0
    if ins < min_inset:
        raise _Unfit(f'{names}: blank fixing hole inset {ins:g} mm is less than '
                     f'head_dia/2 + 3 = {min_inset:g} mm: the screw head would reach '
                     f'the blank edge')
    fix = [Hole(fx, fy, settings.drill_fix.diameter)
           for fx in (ins, W - ins) for fy in (ins, H - ins)]
    # the cutter centre runs a radius outside the shape, so its edge reaches a
    # full diameter from the shape
    need = settings.router.diameter + b.head_dia / 2 + 3.0
    for h in fix:
        for p in placed:
            dx = max(p.x - h.x, 0, h.x - (p.x + p.shape.length))
            dy = max(p.y - h.y, 0, h.y - (p.y + p.shape.width))
            d = math.hypot(dx, dy)
            if d < need:
                raise _Unfit(f'{names}: fixing hole ({h.x:.0f}, {h.y:.0f}) only '
                             f'{d:.1f} mm from {p.name}, need {need:.1f}')
    blank = Blank('', W, H, placed, fix, screws)
    _check_size(blank, names, settings)
    return blank


def _usable(settings: Settings) -> tuple[float, float]:
    p = settings.panel
    return p.length - 2 * p.edge, p.width - 2 * p.edge


def _check_size(b: Blank, names: str, settings: Settings) -> None:
    m = settings.machine
    if b.width > m.frame_x + EPS or b.height > m.frame_y + EPS:
        raise _Unfit(f'{names}: blank {b.width:.0f} x {b.height:.0f} does not fit the machine '
                     f'work frame {m.frame_x:g} x {m.frame_y:g} (machine.frame_x x '
                     f'machine.frame_y; placeholder values, to verify on the machine)')
    ul, uw = _usable(settings)
    if not (min(b.width, b.height) <= min(ul, uw) + EPS
            and max(b.width, b.height) <= max(ul, uw) + EPS):
        raise _Unfit(f'{names}: blank {b.width:.0f} x {b.height:.0f} does not fit the panel '
                     f'({ul:g} x {uw:g} after the edge trim)')


def _check_quantities(entries: list[ShapeEntry]) -> None:
    """Raise ValueError before any copy is made if a quantity is negative or too large."""
    for e in entries:
        if not e.enabled:
            continue
        if e.qty < 0:
            raise ValueError(f'{e.shape.name}: quantity {e.qty} is negative')
        if e.qty > MAX_QTY:
            raise ValueError(f'{e.shape.name}: quantity {e.qty} is more than the '
                             f'{MAX_QTY} allowed')


def build_blanks(entries: list[ShapeEntry], settings: Settings) -> list[Blank]:
    """Blanks for every enabled copy. A group whose blank does not fit (work frame, panel or a
    clearance rule) is split into smaller blanks, down to one shape. A shape that does not fit
    a blank on its own raises LayoutError naming it."""
    _check_quantities(entries)
    blanks: list[Blank] = []
    errors: list[str] = []
    for group in _groups(_expand(entries), settings):
        cur: list[_Item] = []
        for item in group:
            if cur:
                try:
                    _build_blank(cur + [item], settings)
                    cur.append(item)
                    continue
                except _Unfit:
                    blanks.append(_build_blank(cur, settings))
                    cur = []
            try:
                _build_blank([item], settings)
                cur = [item]
            except _Unfit as e:
                if str(e) not in errors:
                    errors.append(str(e))
        if cur:
            blanks.append(_build_blank(cur, settings))
    if errors:
        raise LayoutError('; '.join(errors))
    return blanks


def build_plan(entries: list[ShapeEntry], settings: Settings) -> Plan:
    plan = Plan()
    blanks = build_blanks(entries, settings)
    if blanks:
        plan.panels = saw_plan(blanks, settings)
    return plan


# --- panel saw: two-stage guillotine (shelf) plan -----------------------------------------

@dataclass
class _Piece:
    blank: Blank
    rot: bool
    a: float        # size along the strip
    c: float        # size across the strip


@dataclass
class _Strip:
    c: float                                    # across size (the first, tallest piece)
    pieces: list[_Piece] = field(default_factory=list)

    def used(self, kerf: float) -> float:
        return sum(p.a for p in self.pieces) + kerf * (len(self.pieces) - 1)


def _options(b: Blank, d: str, cap_a: float, cap_c: float) -> list[tuple[bool, float, float]]:
    """(rotated, along, across) choices that fit a strip, long side along the strip first."""
    out = []
    for rot in (False, True):
        fx, fy = (b.height, b.width) if rot else (b.width, b.height)
        a, c = (fx, fy) if d == 'x' else (fy, fx)
        if a <= cap_a + EPS and c <= cap_c + EPS:
            out.append((rot, a, c))
    out.sort(key=lambda o: (o[2], o[0]))
    return out


def _pack(blanks: list[Blank], settings: Settings, d: str) -> list[list[_Strip]] | None:
    """First-fit-decreasing shelf packing with strips along axis `d`; None if a blank cannot
    lie in this direction at all."""
    k = settings.panel.kerf
    ul, uw = _usable(settings)
    cap_a, cap_c = (ul, uw) if d == 'x' else (uw, ul)
    opts = {id(b): _options(b, d, cap_a, cap_c) for b in blanks}
    if any(not o for o in opts.values()):
        return None
    order = sorted(range(len(blanks)),
                   key=lambda i: (-opts[id(blanks[i])][0][2], -opts[id(blanks[i])][0][1], i))
    panels: list[list[_Strip]] = []
    for i in order:
        b = blanks[i]
        best = None
        for pi, strips in enumerate(panels):
            for si, s in enumerate(strips):
                for rot, a, c in opts[id(b)]:
                    if c <= s.c + EPS and s.used(k) + k + a <= cap_a + EPS:
                        key = (s.c - c, pi, si)
                        if best is None or key < best[0]:
                            best = (key, s, _Piece(b, rot, a, c))
        if best:
            best[1].pieces.append(best[2])
            continue
        rot, a, c = opts[id(b)][0]
        for strips in panels:
            used = sum(s.c for s in strips) + k * len(strips)
            if used + c <= cap_c + EPS:
                strips.append(_Strip(c, [_Piece(b, rot, a, c)]))
                break
        else:
            panels.append([_Strip(c, [_Piece(b, rot, a, c)])])
    return panels


def _score(panels: list[list[_Strip]], k: float) -> tuple[int, float]:
    """(panels, slivers): slivers is the area inside the strips that is not a blank (kerf and
    the strip height above narrower blanks). The rest of the waste is the edge trim and the
    offcut left after the last strip, which is one reusable piece."""
    sliver = 0.0
    for strips in panels:
        for s in strips:
            sliver += s.c * s.used(k) - sum(p.a * p.c for p in s.pieces)
    return len(panels), round(sliver, 6)


def saw_plan(blanks: list[Blank], settings: Settings,
             directions: tuple[str, ...] = ('x', 'y')) -> list[PanelPlan]:
    """Try strips along the panel length and along its width; keep the plan with the fewest
    panels, then the least sliver waste, then strips along the length. Blank ids are given in
    cut order: B01, B02, ..."""
    k = settings.panel.kerf
    tries = []
    for d in directions:
        packed = _pack(blanks, settings, d)
        if packed is not None:
            tries.append((_score(packed, k), d, packed))
    if not tries:       # cannot happen: _check_size made every blank fit the panel
        raise LayoutError('a blank does not fit the panel in either direction')
    _, d, packed = min(tries, key=lambda t: (t[0], t[1]))
    out = []
    n = 0
    width = max(2, len(str(len(blanks))))
    for pi, strips in enumerate(packed):
        for s in strips:
            for p in s.pieces:
                n += 1
                p.blank.id = f'B{n:0{width}d}'
        out.append(_place(f'P{pi + 1}', strips, d, settings))
    return out


def _place(pid: str, strips: list[_Strip], d: str, settings: Settings) -> PanelPlan:
    """Positions of the blanks and the ordered cut list of one panel."""
    p = settings.panel
    e, k = p.edge, p.kerf
    len_a, len_c = (p.length, p.width) if d == 'x' else (p.width, p.length)
    ax1 = d                                   # stage 1 and 3 cuts run along the strips
    ax2 = 'y' if d == 'x' else 'x'

    def size(a: float, c: float) -> tuple[float, float]:
        return (a, c) if d == 'x' else (c, a)

    plan = PanelPlan(pid, strips=d)
    cuts: list[tuple] = []

    def cut(stage, axis, at, start, end, frees, blanks, sz=None):
        cuts.append((stage, axis, at, start, end, frees, blanks, sz))

    # stage 1: trim, then one cut after each strip
    c0 = e
    if e:
        cut(1, ax1, e - k, 0, len_a, 'offcut', [], size(len_a, e - k))
    bounds = []
    for s in strips:
        lo, hi = c0, c0 + s.c
        bounds.append((lo, hi))
        ids = [q.blank.id for q in s.pieces]
        if hi < len_c - EPS:
            cut(1, ax1, hi, 0, len_a, 'strip', ids, size(len_a, hi - lo))
        c0 = hi + k
    stage1 = cuts[:]
    # strip extents across, as sawn: from the previous kerf to this one
    cuts = []
    for (lo, hi), s in zip(bounds, strips):
        a0 = e
        if e:
            cut(2, ax2, e - k, lo, hi, 'offcut', [], size(e - k, hi - lo))
        trims = []
        for q in s.pieces:
            b = q.blank
            b.rotated = q.rot
            b.x, b.y = (a0, lo) if d == 'x' else (lo, a0)
            b.panel = pid
            plan.blanks.append(b)
            end = a0 + q.a
            exact = q.c >= s.c - EPS
            if end < len_a - EPS:
                cut(2, ax2, end, lo, hi, 'blank' if exact else 'rough', [b.id],
                    size(q.a, hi - lo))
            if not exact:
                trims.append((lo + q.c, a0, end, b.id, size(q.a, q.c)))
            a0 = end + k
        for at, start, end, bid, sz in trims:
            cut(3, ax1, at, start, end, 'blank', [bid], sz)
    plan.cuts = [SawCut(i + 1, *c) for i, c in enumerate(stage1 + cuts)]
    return plan
