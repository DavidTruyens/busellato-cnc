"""Pocket groups: pockets with the same shape and place share one set of machining settings."""
from __future__ import annotations

import math
from dataclasses import dataclass, field, fields

from .dxf import Pocket, Shape, _inside
from .geometry import (Arc, Line, OffsetError, Pt, Seg, bbox, distance_to_chain, offset_outline,
                       sample, split_large_arcs)
from .settings import Pockets

# Distinct from the page colours (blank tan, shape blue, holes red, saw cut black, green/amber UI).
PALETTE = ["#00897b", "#8e24aa", "#f57c00", "#d81b60", "#00bcd4",
           "#827717", "#5e35b1", "#7cb342", "#fbc02d"]

_STEP = 0.05
SLOT_ASPECT = 3.0


@dataclass
class PocketGroup:
    id: str
    key: str
    width: float
    height: float
    kind: str
    count: int
    color: str
    representative: Pocket | None = field(default=None, repr=False, compare=False)


def _q(v: float) -> int:
    return round(v / _STEP)


def group_key(p: Pocket) -> str:
    """Signature in the plate's own frame (position, size, vertices); mirroring changes it."""
    x0, y0, x1, y1 = bbox(p.outline)
    parts = [f"{_q(x0)},{_q(y0)},{_q(x1 - x0)},{_q(y1 - y0)}"]
    for s in p.outline:
        if isinstance(s, Arc):
            parts.append(f"A{_q(s.a[0])},{_q(s.a[1])},{_q(s.b[0])},{_q(s.b[1])},"
                         f"{_q(s.center[0])},{_q(s.center[1])},{int(s.ccw)}")
        else:
            parts.append(f"L{_q(s.a[0])},{_q(s.a[1])},{_q(s.b[0])},{_q(s.b[1])}")
    return "|".join(parts)


def _kind(p: Pocket, w: float, h: float) -> str:
    if p.circle is not None:
        return "round"
    short, long_ = min(w, h), max(w, h)
    if short > 0 and long_ / short >= SLOT_ASPECT:
        return "slot"
    return "shape"


TOLERANCE = 0.05  # mm, per coordinate


def _close(p: tuple, q: tuple) -> bool:
    return all(abs(a - b) <= TOLERANCE + 1e-9 for a, b in zip(p, q))


def _seg_nums(s) -> tuple:
    if isinstance(s, Arc):
        return (*s.a, *s.b, *s.center, s.radius)
    return (*s.a, *s.b)


def same_pocket(p: Pocket, q: Pocket) -> bool:
    """Same segment count, kinds and turning sense, every coordinate within TOLERANCE."""
    if len(p.outline) != len(q.outline):
        return False
    for s, t in zip(p.outline, q.outline):
        if isinstance(s, Arc) != isinstance(t, Arc):
            return False
        if isinstance(s, Arc) and s.ccw != t.ccw:
            return False
        if not _close(_seg_nums(s), _seg_nums(t)):
            return False
    return True


def group_for(pocket: Pocket, groups: list[PocketGroup]) -> PocketGroup | None:
    """The group whose representative matches pocket within TOLERANCE, or None.

    This is the match rule. group_key(pocket) alone is only the representative's name
    (the stored override key), not how pockets are matched.
    """
    for g in groups:
        if g.representative is not None and same_pocket(pocket, g.representative):
            return g
    return None


def find_groups(shapes: list[Shape]) -> list[PocketGroup]:
    """Groups in first-seen order over shapes sorted by name (then pocket order), so the
    representative, key and id do not depend on the order of the list. No chaining: a
    pocket is compared with each group's first-seen pocket only."""
    groups: list[PocketGroup] = []
    for shape in sorted(shapes, key=lambda sh: sh.name):
        for p in shape.pockets:
            g = group_for(p, groups)
            if g is None:
                x0, y0, x1, y1 = bbox(p.outline)
                n = len(groups)
                g = PocketGroup(f"G{n + 1}", group_key(p), x1 - x0, y1 - y0,
                                _kind(p, x1 - x0, y1 - y0), 0, PALETTE[n % len(PALETTE)], p)
                groups.append(g)
            g.count += 1
    return groups


@dataclass
class GroupSettings:
    enabled: bool
    tool: int
    diameter: float
    depth: float
    depth_per_pass: float
    plunge_feed: float
    cut_feed: float
    spindle_rpm: float
    stepover_pct: float
    direction: str


def effective(group_key: str, overrides: dict, defaults: Pockets) -> GroupSettings:
    """Defaults merged with overrides[group_key]; unknown fields ignored.

    Override values must be real numbers (no strings, no bool) except `enabled` (bool) and
    `direction` ('cw'/'ccw'); anything else raises ValueError naming the field.
    """
    vals = {f.name: getattr(defaults, f.name) for f in fields(GroupSettings)
            if hasattr(defaults, f.name)}
    vals["enabled"] = True
    ov = overrides.get(group_key)
    if ov is None:
        ov = {}
    if not isinstance(ov, dict):
        raise ValueError(f"invalid overrides for group {group_key!r}")
    for name, v in ov.items():
        if name in vals:
            vals[name] = _coerce(name, v)
    return GroupSettings(**vals)


def _coerce(name: str, v):
    bad = ValueError(f"invalid value for {name}: {v!r}")
    if name == "enabled":
        if not isinstance(v, bool):
            raise bad
        return v
    if name == "direction":
        if v not in ("cw", "ccw") or not isinstance(v, str):
            raise bad
        return v
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise bad
    try:
        if not math.isfinite(v) or v <= 0:
            raise bad
        if name == "tool":
            if v != int(v):
                raise bad
            return int(v)
        if name == "stepover_pct" and v > 100:
            raise bad
    except OverflowError:
        raise bad from None
    return float(v)


# --- cutter rings ------------------------------------------------------------

WIDTH_TOL = 0.01   # mm: a pocket this close to the tool diameter is cut by one centre-line pass
_SNUG = 0.006      # mm: offset margin used to probe for a tool-width pocket (just over WIDTH_TOL / 2)
_MIN_RING = 0.01   # mm: a ring smaller than this across is a point, not a ring
_BISECT = 0.01     # mm: precision of the search for the deepest offset
_MAX_STEP_PCT = 70  # stepover cap, % of the tool diameter (see pocket_rings)
_SHRINK = 0.8      # backstop: stepover factor per retry when the check finds material left
_RETRIES = 10


class PocketError(ValueError):
    """The pocket cannot be cleared with this tool."""


def pocket_rings(outline: list[Seg], tool_diameter: float,
                 stepover_pct: float) -> list[list[Seg]]:
    """Closed tool-centre rings that clear the pocket, innermost first, the wall ring last.

    The wall ring is the outline offset inward by the tool radius r; the other rings are
    further inward offsets spaced stepover apart, for as long as the offset exists.

    stepover = tool_diameter * min(stepover_pct, 70) / 100: stepover_pct is a maximum and
    values above 70 are treated as 70. Reason: at a sharp convex corner the rings have sharp
    corners, and a point on the corner bisector between two rings is farther from both than
    half the spacing; with a 70 % stepover a right-angled corner stays covered.

    Coverage comes from the construction: when the pocket's middle (its deepest offset,
    found by bisection to _BISECT) lies more than r beyond the innermost regular ring, a ring
    at that deepest offset is added (a thin loop around the medial axis). As a backstop the
    result is checked: points on the offset halfway between each pair of rings must be
    within r of one of the two, and a grid (cell r/3) inside the innermost ring within r of
    a ring. If that check fails (sharp acute corners) the stepover is reduced by _SHRINK and
    the rings rebuilt, up to _RETRIES times; a pocket that still cannot be cleared (for
    example one whose inner offsets break into separate islands) raises PocketError rather
    than returning rings that would leave material. The band within r of the outline is
    cleared by the wall ring, except sharp convex corners, which no round cutter reaches.

    Every ring keeps the winding of the outline (direction is applied later), lies in the
    same frame, and is at least r from the outline. Arcs stay arcs; arcs over 180 degrees are
    split. A round pocket (an outline of arcs on one centre and radius) gives concentric
    circles built directly, each ring the outline's arcs scaled about the centre (two
    180-degree arcs for a pocket read from a circle). A ring smaller than _MIN_RING across is
    treated as collapsed: there is no ring at a single point except the case below.

    A pocket as wide as the tool (within WIDTH_TOL) gives one degenerate ring: its straight
    centre line traversed out and back, [Line(p, q), Line(q, p)]. A round pocket of the tool
    diameter gives [Line(c, c), Line(c, c)] with c the centre: two zero-length lines, a plunge
    at the centre with no horizontal move (callers must not ask such a line for a direction).
    A pocket narrower than the tool raises PocketError ("narrower than the tool"); one about
    as wide as the tool that is not a straight slot raises PocketError as well.
    """
    if not (math.isfinite(tool_diameter) and tool_diameter > 0):
        raise PocketError(f"invalid tool diameter {tool_diameter!r}")
    if not (0 < stepover_pct <= 100):
        raise PocketError(f"invalid stepover {stepover_pct!r} %")
    r = tool_diameter / 2
    step = tool_diameter * min(stepover_pct, _MAX_STEP_PCT) / 100
    circle = _circle(outline)
    if circle is not None:
        return _circle_rings(outline, circle, r, step, tool_diameter)

    wall = _offset(outline, r)
    if wall is None or _offset(outline, r + _SNUG) is None:
        line = _centre_line(outline, r)
        if line is not None:
            return [line]
        if wall is None:
            if _offset_any(outline, r - _SNUG) is not None:
                raise PocketError(f"pocket is about as wide as the {tool_diameter:g} mm tool "
                                  f"but is not a straight slot, so it cannot be cut in one pass")
            raise PocketError(f"pocket is narrower than the tool ({tool_diameter:g} mm)")

    for _ in range(_RETRIES):
        levels, rings = [r], [wall]
        while (ring := _offset(outline, levels[-1] + step)) is not None:
            levels.append(levels[-1] + step)
            rings.append(ring)
        if step > r:
            # the middle may lie beyond the reach (r) of the innermost ring
            reach = levels[-1] + r
            probe = _offset(outline, reach)
            if probe is not None:
                level, ring = _deepest(outline, reach, probe, levels[-1] + step)
                levels.append(level)
                rings.append(ring)
        if _covered(outline, levels, rings, r):
            return [split_large_arcs(g) for g in reversed(rings)]
        step *= _SHRINK
    raise PocketError("pocket cannot be cleared with this tool: material would be left "
                      "standing, for example where its inner offsets break into separate "
                      "islands")


def _offset_any(outline: list[Seg], d: float) -> list[Seg] | None:
    """The outline offset inward by d, or None when offset_outline refuses."""
    try:
        return offset_outline(outline, d, outward=False)
    except OffsetError:
        return None


def _offset(outline: list[Seg], d: float) -> list[Seg] | None:
    """Like _offset_any, but a ring smaller than _MIN_RING across counts as collapsed."""
    ring = _offset_any(outline, d)
    if ring is None:
        return None
    x0, y0, x1, y1 = bbox(ring)
    return ring if max(x1 - x0, y1 - y0) >= _MIN_RING else None


def _deepest(outline: list[Seg], lo: float, ring: list[Seg],
             hi: float) -> tuple[float, list[Seg]]:
    """(level, ring) of the deepest inward offset, to within _BISECT, given that the offset
    at lo exists (ring) and the one at hi does not."""
    while hi - lo > _BISECT:
        mid = (lo + hi) / 2
        got = _offset(outline, mid)
        if got is None:
            hi = mid
        else:
            lo, ring = mid, got
    return lo, ring


def _circle(outline: list[Seg]) -> tuple[Pt, float, bool] | None:
    """(centre, radius, ccw) when the outline is arcs on one centre and radius."""
    if not outline or not all(isinstance(s, Arc) for s in outline):
        return None
    a = outline[0]
    for s in outline:
        if (math.dist(s.center, a.center) > 1e-6 or abs(s.radius - a.radius) > 1e-6
                or s.ccw != a.ccw):
            return None
    return a.center, a.radius, a.ccw


def _circle_rings(outline: list[Seg], circle: tuple[Pt, float, bool], r: float, step: float,
                  tool_diameter: float) -> list[list[Seg]]:
    (cx, cy), radius, _ = circle
    if abs(radius - r) <= WIDTH_TOL / 2:
        c = (cx, cy)
        return [[Line(c, c), Line(c, c)]]
    if radius < r:
        raise PocketError(f"pocket is narrower than the tool ({tool_diameter:g} mm)")

    def ring(rho: float) -> list[Seg]:
        k = rho / radius

        def sc(p: Pt) -> Pt:
            return (cx + (p[0] - cx) * k, cy + (p[1] - cy) * k)
        return split_large_arcs([Arc(sc(s.a), sc(s.b), s.center, rho, s.ccw) for s in outline])

    radii = [radius - r]
    while radii[-1] - step >= _MIN_RING / 2:
        radii.append(radii[-1] - step)
    if radii[-1] > r:   # the centre is out of reach of the innermost ring
        radii.append(r)
    return [ring(rho) for rho in reversed(radii)]


def _centre_line(outline: list[Seg], r: float) -> list[Seg] | None:
    """For a pocket as wide as the tool (within WIDTH_TOL): the straight centre line traversed
    out and back, [Line(p, q), Line(q, p)], or None when the pocket is not that shape."""
    thin = _offset_any(outline, r - _SNUG)
    if thin is None:
        return None
    pts = [q for s in thin
           for q in sample([s], max(s.radius / 4, 1e-4) if isinstance(s, Arc) else 0.5)]
    n = len(pts)
    cx, cy = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    sxx = sum((p[0] - cx) ** 2 for p in pts)
    syy = sum((p[1] - cy) ** 2 for p in pts)
    sxy = sum((p[0] - cx) * (p[1] - cy) for p in pts)
    ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
    ux, uy = math.cos(ang), math.sin(ang)
    along = [(p[0] - cx) * ux + (p[1] - cy) * uy for p in pts]
    half = max(abs((p[1] - cy) * ux - (p[0] - cx) * uy) for p in pts)
    lo, hi = min(along) + half, max(along) - half
    if hi - lo < _MIN_RING:
        lo = hi = (lo + hi) / 2
    p = (cx + lo * ux, cy + lo * uy)
    q = (cx + hi * ux, cy + hi * uy)
    line = [Line(p, q), Line(q, p)]
    # straight: the thin offset hugs the line; and the cutter on the line stays in the pocket
    if any(distance_to_chain(t, line[:1]) > half + WIDTH_TOL for t in pts):
        return None
    if any(distance_to_chain(t, outline) < r - WIDTH_TOL for t in sample(line[:1], 0.5)):
        return None
    return line


def _covered(outline: list[Seg], levels: list[float], rings: list[list[Seg]],
             r: float) -> bool:
    """Backstop check that the cutter discs along the rings leave nothing standing deeper
    than the wall ring: the offset halfway between each pair of rings must lie within r of
    one of them (worst case between two rings), and a grid of cell r/3 inside the innermost
    ring must lie within r of a ring (the pocket's middle)."""
    step = max(r / 4, 0.05)
    for (la, ga), (lb, gb) in zip(zip(levels, rings), zip(levels[1:], rings[1:])):
        mid = _offset_any(outline, (la + lb) / 2)
        if mid is None:
            return False
        for p in sample(mid, step):
            if distance_to_chain(p, ga) > r + 1e-6 and distance_to_chain(p, gb) > r + 1e-6:
                return False
    inner = rings[-1]
    x0, y0, x1, y1 = bbox(inner)
    cell = r / 3
    poly = _polygon(inner, min(1.0, r / 4))
    nx, ny = max(1, math.ceil((x1 - x0) / cell)), max(1, math.ceil((y1 - y0) / cell))
    near = [(g, bbox(g)) for g in reversed(rings)]
    for i in range(nx + 1):
        for j in range(ny + 1):
            x, y = x0 + i * (x1 - x0) / nx, y0 + j * (y1 - y0) / ny
            if not _inside(poly, x, y):
                continue
            if not any(b[0] - r <= x <= b[2] + r and b[1] - r <= y <= b[3] + r
                       and distance_to_chain((x, y), g) <= r + 1e-6 for g, b in near):
                return False
    return True


def _polygon(segs: list[Seg], step: float) -> list[Pt]:
    """Closed chain as polygon vertices: line ends, arcs sampled every step."""
    pts: list[Pt] = []
    for s in segs:
        pts += [s.a] if isinstance(s, Line) else sample([s], step)[:-1]
    return pts
