"""Group shapes into templates and nest the templates on stock panels."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .dxf import Hole, Shape
from .geometry import Pt
from .settings import Settings

EPS = 1e-9
MAX_QTY = 500   # copies per shape: a safety bound for what the UI can ask for


@dataclass
class ShapeEntry:
    shape: Shape
    qty: int = 1
    enabled: bool = True
    thickness: float | None = None


@dataclass
class PlacedShape:
    name: str
    copy: int
    x: float
    y: float
    shape: Shape
    thickness: float


@dataclass
class PlacedTemplate:
    id: str
    width: float
    height: float
    shapes: list[PlacedShape]
    fix_holes: list[Hole]
    screw_holes: list[Hole]
    x: float = 0.0          # bottom-left of the footprint on the panel
    y: float = 0.0
    rotated: bool = False


@dataclass
class PanelPlan:
    id: str
    templates: list[PlacedTemplate] = field(default_factory=list)


@dataclass
class Plan:
    panels: list[PanelPlan] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


class _Unfit(Exception):
    """A group of shapes cannot become a template (message names the shapes)."""


@dataclass
class _Item:
    shape: Shape
    copy: int
    thickness: float

    @property
    def label(self) -> str:
        return self.shape.name


def to_panel(t: PlacedTemplate, x: float, y: float) -> Pt:
    """Template-frame point -> panel-frame point. Rotated = 90 degrees counter-clockwise."""
    if t.rotated:
        return t.x + t.height - y, t.y + x
    return t.x + x, t.y + y


def footprint(t: PlacedTemplate) -> tuple[float, float]:
    return (t.height, t.width) if t.rotated else (t.width, t.height)


class _MaxRects:
    def __init__(self, w: float, h: float):
        self.free = [(0.0, 0.0, w, h)]

    def place(self, w: float, h: float):
        best = None
        for rw, rh, rot in ((w, h, False),) + (((h, w, True),) if w != h else ()):
            for fx, fy, fw, fh in self.free:
                if rw <= fw + EPS and rh <= fh + EPS:
                    key = (min(fw - rw, fh - rh), max(fw - rw, fh - rh))
                    if best is None or key < best[0]:
                        best = (key, fx, fy, rw, rh, rot)
        if best is None:
            return None
        _, x, y, rw, rh, rot = best
        self._split(x, y, rw, rh)
        return x, y, rot

    def _split(self, x, y, w, h):
        new = []
        for fx, fy, fw, fh in self.free:
            if x >= fx + fw or x + w <= fx or y >= fy + fh or y + h <= fy:
                new.append((fx, fy, fw, fh))
                continue
            if x > fx:
                new.append((fx, fy, x - fx, fh))
            if x + w < fx + fw:
                new.append((x + w, fy, fx + fw - x - w, fh))
            if y > fy:
                new.append((fx, fy, fw, y - fy))
            if y + h < fy + fh:
                new.append((fx, y + h, fw, fy + fh - y - h))
        self.free = [r for i, r in enumerate(new)
                     if not any(j != i and _inside(r, o) and (r != o or j < i)
                                for j, o in enumerate(new))]


def _inside(a, b):
    return (a[0] >= b[0] - EPS and a[1] >= b[1] - EPS
            and a[0] + a[2] <= b[0] + b[2] + EPS and a[1] + a[3] <= b[1] + b[3] + EPS)


def _expand(entries: list[ShapeEntry], settings: Settings) -> list[_Item]:
    items = []
    for e in entries:
        if not e.enabled:
            continue
        th = e.thickness if e.thickness is not None else settings.heights.shape_thickness
        items.extend(_Item(e.shape, i + 1, th) for i in range(max(int(e.qty), 0)))
    return items


def _groups(items: list[_Item], settings: Settings) -> list[list[_Item]]:
    t = settings.template
    size = 1 if t.mode == 'none' else t.shapes_per
    if t.group_by == 'length' and t.mode != 'none':
        # neighbours by length: optimal for the sum of the template lengths
        items = sorted(items, key=lambda i: (-i.shape.length, -i.shape.width, i.shape.name))
    return [items[k:k + size] for k in range(0, len(items), size)]


def _build_template(group: list[_Item], settings: Settings) -> PlacedTemplate:
    """Template around the group; raises _Unfit if the clearance rules cannot be met."""
    t = settings.template
    gap = settings.gap
    names = ', '.join(i.label for i in group)
    group = sorted(group, key=lambda i: -i.shape.width)       # widest at the bottom
    length = max(i.shape.length for i in group)
    stack = sum(i.shape.width for i in group) + gap * (len(group) - 1)
    if t.mode == 'none':
        mend = mside = 0.0
        W, H = length, stack
    elif t.mode == 'fixed':
        mend, mside = (t.fixed_width - length) / 2, (t.fixed_height - stack) / 2
        W, H = t.fixed_width, t.fixed_height
        if mend < 0 or mside < 0:
            raise _Unfit(f'{names}: does not fit the fixed template '
                         f'{W:g} x {H:g} (needs {length:g} x {stack:g})')
    else:
        mend, mside = t.margin_end, t.margin_side
        W, H = length + 2 * mend, stack + 2 * mside

    placed, screws, y = [], [], mside
    for i in group:
        placed.append(PlacedShape(i.shape.name, i.copy, mend, y, i.shape, i.thickness))
        screws.extend(Hole(mend + h.x, y + h.y, settings.drill_screw.diameter)
                      for h in i.shape.holes)
        y += i.shape.width + gap
    fix: list[Hole] = []
    if t.mode != 'none':
        ins = t.fix_inset
        # the head must sit inside the template, 3 mm clear of its outline cut
        min_inset = t.head_dia / 2 + 3.0
        if ins < min_inset:
            raise _Unfit(f'{names}: template fixing hole inset {ins:g} mm is less than '
                         f'head_dia/2 + 3 = {min_inset:g} mm: the screw head would reach '
                         f'the template outline cut')
        fix = [Hole(fx, fy, settings.drill_fix.diameter)
               for fx in (ins, W - ins) for fy in (ins, H - ins)]
        # the cutter centre runs a radius outside the shape, so its edge reaches a
        # full diameter from the shape
        need = settings.router.diameter + t.head_dia / 2 + 3.0
        for h in fix:
            for p in placed:
                dx = max(p.x - h.x, 0, h.x - (p.x + p.shape.length))
                dy = max(p.y - h.y, 0, h.y - (p.y + p.shape.width))
                d = math.hypot(dx, dy)
                if d < need:
                    raise _Unfit(f'{names}: fixing hole ({h.x:.0f}, {h.y:.0f}) only '
                                 f'{d:.1f} mm from {p.name}, need {need:.1f}')
    return PlacedTemplate('', W, H, placed, fix, screws)


def _fits_panel(t: PlacedTemplate, settings: Settings) -> bool:
    p = settings.panel
    bw = p.length - 2 * p.edge + settings.gap
    bh = p.width - 2 * p.edge + settings.gap
    w, h = t.width + settings.gap, t.height + settings.gap
    return (min(w, h) <= min(bw, bh) + EPS and max(w, h) <= max(bw, bh) + EPS)


def _try_group(group: list[_Item], settings: Settings) -> PlacedTemplate:
    t = _build_template(group, settings)
    if not _fits_panel(t, settings):
        names = ', '.join(i.label for i in group)
        raise _Unfit(f'{names}: template {t.width:.0f} x {t.height:.0f} '
                     f'does not fit on a panel')
    return t


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


def build_plan(entries: list[ShapeEntry], settings: Settings) -> Plan:
    _check_quantities(entries)
    plan = Plan()
    templates: list[PlacedTemplate] = []
    for group in _groups(_expand(entries, settings), settings):
        try:
            templates.append(_try_group(group, settings))
            continue
        except _Unfit as e:
            first = e
        if len(group) == 1:
            plan.problems.append(str(first))
            continue
        for item in group:                  # one bad shape must not sink its partner
            try:
                templates.append(_try_group([item], settings))
            except _Unfit as e:
                plan.problems.append(str(e))
    for k, t in enumerate(templates):
        t.id = 'T%02d' % (k + 1)
    _nest(templates, plan, settings)
    return plan


def _nest(templates: list[PlacedTemplate], plan: Plan, settings: Settings) -> None:
    p, gap = settings.panel, settings.gap
    bw = p.length - 2 * p.edge + gap
    bh = p.width - 2 * p.edge + gap
    bins: list[_MaxRects] = []
    for t in sorted(templates, key=lambda t: -(t.width * t.height)):
        w, h = t.width + gap, t.height + gap
        for pan, b in zip(plan.panels, bins):
            r = b.place(w, h)
            if r:
                break
        else:
            pan = PanelPlan('P%d' % (len(plan.panels) + 1))
            b = _MaxRects(bw, bh)
            plan.panels.append(pan)
            bins.append(b)
            r = b.place(w, h)
        x, y, rot = r
        t.x, t.y, t.rotated = x + p.edge, y + p.edge, rot
        pan.templates.append(t)
