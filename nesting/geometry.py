"""Plain 2D geometry types: points, lines, arcs and helpers."""
from __future__ import annotations

import math
from dataclasses import dataclass

Pt = tuple[float, float]


@dataclass(frozen=True)
class Line:
    a: Pt
    b: Pt


@dataclass(frozen=True)
class Arc:
    """Arc from a to b around center; ccw says which way it runs."""
    a: Pt
    b: Pt
    center: Pt
    radius: float
    ccw: bool


Seg = Line | Arc


def _angle(center: Pt, p: Pt) -> float:
    return math.atan2(p[1] - center[1], p[0] - center[0])


def _arc_bbox(arc: Arc) -> tuple[float, float, float, float]:
    xs = [arc.a[0], arc.b[0]]
    ys = [arc.a[1], arc.b[1]]
    start = _angle(arc.center, arc.a)
    end = _angle(arc.center, arc.b)
    tau = 2 * math.pi
    if arc.ccw:
        sweep = (end - start) % tau
    else:
        sweep = (start - end) % tau
    for k in range(4):
        ang = k * math.pi / 2
        off = (ang - start) % tau if arc.ccw else (start - ang) % tau
        if off <= sweep:
            xs.append(arc.center[0] + arc.radius * math.cos(ang))
            ys.append(arc.center[1] + arc.radius * math.sin(ang))
    return min(xs), min(ys), max(xs), max(ys)


def bbox(segs: list[Seg]) -> tuple[float, float, float, float]:
    """Exact bounding box (minx, miny, maxx, maxy), including arc extremes."""
    boxes = []
    for s in segs:
        if isinstance(s, Arc):
            boxes.append(_arc_bbox(s))
        else:
            boxes.append((min(s.a[0], s.b[0]), min(s.a[1], s.b[1]),
                          max(s.a[0], s.b[0]), max(s.a[1], s.b[1])))
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def translate(segs: list[Seg], dx: float, dy: float) -> list[Seg]:
    out: list[Seg] = []
    for s in segs:
        a = (s.a[0] + dx, s.a[1] + dy)
        b = (s.b[0] + dx, s.b[1] + dy)
        if isinstance(s, Arc):
            out.append(Arc(a, b, (s.center[0] + dx, s.center[1] + dy),
                           s.radius, s.ccw))
        else:
            out.append(Line(a, b))
    return out


def mirror_y(segs: list[Seg], h: float) -> list[Seg]:
    """Each segment with y -> h - y. A mirror reverses the turning sense, so every arc's ccw
    flag flips; the order of the segments and their start/end points is kept."""
    def m(p: Pt) -> Pt:
        return (p[0], h - p[1])
    return [Arc(m(s.a), m(s.b), m(s.center), s.radius, not s.ccw) if isinstance(s, Arc)
            else Line(m(s.a), m(s.b)) for s in segs]


# --- contour offset ---------------------------------------------------------

TAU = 2 * math.pi
_SNAP = 1e-3     # offset ends closer than this are joined at their midpoint
_DIST_TOL = 2e-3  # allowed error of the offset distance (input jitter)
_TANGENT = 1e-3   # max |sin| of the angle at a join counted as tangent


class OffsetError(Exception):
    """The outline cannot be offset by the tool radius without a bad path."""


def _sweep(arc: Arc) -> float:
    """Angle swept from a to b in the arc's direction, in [0, 2*pi)."""
    start, end = _angle(arc.center, arc.a), _angle(arc.center, arc.b)
    return (end - start) % TAU if arc.ccw else (start - end) % TAU


def _wrap(x: float) -> float:
    """Wrap an angle into (-pi, pi]."""
    x = math.fmod(x + math.pi, TAU)
    if x <= 0:
        x += TAU
    return x - math.pi


def _reverse(s: Seg) -> Seg:
    if isinstance(s, Arc):
        return Arc(s.b, s.a, s.center, s.radius, not s.ccw)
    return Line(s.b, s.a)


def _seg_length(s: Seg) -> float:
    if isinstance(s, Arc):
        return s.radius * _sweep(s)
    return math.dist(s.a, s.b)


def sample(segs: list[Seg], step: float = 0.5) -> list[Pt]:
    """Points along the chain no more than `step` apart, both ends included."""
    pts: list[Pt] = []
    for s in segs:
        n = max(1, math.ceil(_seg_length(s) / step))
        if isinstance(s, Arc):
            start = _angle(s.center, s.a)
            sweep = _sweep(s) if s.ccw else -_sweep(s)
            pts.append(s.a)
            for k in range(1, n):
                t = start + sweep * k / n
                pts.append((s.center[0] + s.radius * math.cos(t),
                            s.center[1] + s.radius * math.sin(t)))
        else:
            for k in range(n):
                pts.append((s.a[0] + (s.b[0] - s.a[0]) * k / n,
                            s.a[1] + (s.b[1] - s.a[1]) * k / n))
    if segs:
        pts.append(segs[-1].b)
    return pts


def _signed_area(segs: list[Seg]) -> float:
    pts = sample(segs, 1.0)
    return 0.5 * sum(x0 * y1 - x1 * y0
                     for (x0, y0), (x1, y1) in zip(pts, pts[1:]))


def set_direction(segs: list[Seg], ccw: bool) -> list[Seg]:
    """The closed chain running counter-clockwise (ccw) or clockwise."""
    if (_signed_area(segs) > 0) == ccw:
        return list(segs)
    return [_reverse(s) for s in reversed(segs)]


def split_large_arcs(segs: list[Seg]) -> list[Seg]:
    """Replace every arc sweeping more than 180 degrees by two equal arcs."""
    out: list[Seg] = []
    for s in segs:
        if isinstance(s, Arc) and _sweep(s) > math.pi + 1e-9:
            half = _sweep(s) / 2
            t = _angle(s.center, s.a) + (half if s.ccw else -half)
            mid = (s.center[0] + s.radius * math.cos(t),
                   s.center[1] + s.radius * math.sin(t))
            out += [Arc(s.a, mid, s.center, s.radius, s.ccw),
                    Arc(mid, s.b, s.center, s.radius, s.ccw)]
        else:
            out.append(s)
    return out


def _dist_to_seg(p: Pt, s: Seg) -> float:
    if isinstance(s, Arc):
        off = _angle(s.center, p) - _angle(s.center, s.a)
        off = off % TAU if s.ccw else -off % TAU
        if off <= _sweep(s):
            return abs(math.dist(p, s.center) - s.radius)
        return min(math.dist(p, s.a), math.dist(p, s.b))
    (ax, ay), (bx, by) = s.a, s.b
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / ll))
    return math.dist(p, (ax + t * dx, ay + t * dy))


def distance_to_chain(p: Pt, segs: list[Seg]) -> float:
    """Shortest distance from p to any segment of the chain."""
    return min(_dist_to_seg(p, s) for s in segs)


def _tangent(s: Seg, at_end: bool) -> Pt:
    """Unit direction of travel at the start (or end) of a segment."""
    if isinstance(s, Arc):
        p = s.b if at_end else s.a
        ux, uy = p[0] - s.center[0], p[1] - s.center[1]
        n = math.hypot(ux, uy)
        return (-uy / n, ux / n) if s.ccw else (uy / n, -ux / n)
    dx, dy = s.b[0] - s.a[0], s.b[1] - s.a[1]
    n = math.hypot(dx, dy)
    return dx / n, dy / n


class _Off:
    """One segment of the outline moved sideways by r, before joining."""

    def __init__(self, seg: Seg, r: float, side: float):
        self.seg = seg
        if isinstance(seg, Arc):
            # The right-hand normal points away from the centre on a ccw arc.
            k = side if seg.ccw else -side
            self.center, self.ccw = seg.center, seg.ccw
            self.radius = seg.radius + k * r
            self.start = _angle(seg.center, seg.a)
            self.sweep = _sweep(seg)
            end = self.start + (self.sweep if self.ccw else -self.sweep)
            self.p0 = self._at(self.start)
            self.p1 = self._at(end)
        else:
            tx, ty = _tangent(seg, False)
            nx, ny = side * ty, -side * tx
            self.radius = None
            self.dir = (tx, ty)
            self.p0 = (seg.a[0] + r * nx, seg.a[1] + r * ny)
            self.p1 = (seg.b[0] + r * nx, seg.b[1] + r * ny)

    def _at(self, t: float) -> Pt:
        return (self.center[0] + self.radius * math.cos(t),
                self.center[1] + self.radius * math.sin(t))

    @property
    def is_arc(self) -> bool:
        return self.radius is not None

    def param(self, p: Pt, at_end: bool) -> float:
        """Position of p along the segment (length units), near one end."""
        if self.is_arc:
            ang = _angle(self.center, p)
            ref = self.start + ((self.sweep if self.ccw else -self.sweep)
                                if at_end else 0.0)
            d = _wrap(ang - ref)
            if not self.ccw:
                d = -d
            return self.radius * ((self.sweep if at_end else 0.0) + d)
        return ((p[0] - self.p0[0]) * self.dir[0]
                + (p[1] - self.p0[1]) * self.dir[1])

    def make(self, a: Pt, b: Pt) -> Seg:
        if self.is_arc:
            return Arc(a, b, self.center, self.radius, self.ccw)
        return Line(a, b)


def _intersect(u: _Off, v: _Off, near: Pt) -> Pt:
    """Intersection of the two (extended) offset curves closest to `near`."""
    if not u.is_arc and not v.is_arc:
        (x1, y1), (dx1, dy1) = u.p0, u.dir
        (x2, y2), (dx2, dy2) = v.p0, v.dir
        den = dx1 * dy2 - dy1 * dx2
        if abs(den) < 1e-9:
            raise OffsetError(f"parallel offset edges cannot be joined near "
                              f"({near[0]:.2f}, {near[1]:.2f})")
        t = ((x2 - x1) * dy2 - (y2 - y1) * dx2) / den
        return (x1 + t * dx1, y1 + t * dy1)
    if u.is_arc and v.is_arc:
        cands = _circle_circle(u.center, u.radius, v.center, v.radius)
    else:
        line, arc = (v, u) if u.is_arc else (u, v)
        cands = _line_circle(line.p0, line.dir, arc.center, arc.radius)
    if not cands:
        raise OffsetError(f"offset curves do not meet near "
                          f"({near[0]:.2f}, {near[1]:.2f}); feature narrower "
                          f"than the tool?")
    return min(cands, key=lambda p: math.dist(p, near))


def _line_circle(p: Pt, d: Pt, c: Pt, r: float) -> list[Pt]:
    fx, fy = p[0] - c[0], p[1] - c[1]
    b = fx * d[0] + fy * d[1]
    disc = b * b - (fx * fx + fy * fy - r * r)
    if disc < 0:
        return []
    s = math.sqrt(disc)
    return [(p[0] + t * d[0], p[1] + t * d[1]) for t in (-b - s, -b + s)]


def _circle_circle(c0: Pt, r0: float, c1: Pt, r1: float) -> list[Pt]:
    d = math.dist(c0, c1)
    if d < 1e-12 or d > r0 + r1 or d < abs(r0 - r1):
        return []
    a = (r0 * r0 - r1 * r1 + d * d) / (2 * d)
    h = math.sqrt(max(0.0, r0 * r0 - a * a))
    ex, ey = (c1[0] - c0[0]) / d, (c1[1] - c0[1]) / d
    mx, my = c0[0] + a * ex, c0[1] + a * ey
    return [(mx - h * ey, my + h * ex), (mx + h * ey, my - h * ex)]


def _crosses(p1: Pt, p2: Pt, q1: Pt, q2: Pt) -> bool:
    """True when segments p1p2 and q1q2 properly cross each other."""
    def orient(a: Pt, b: Pt, c: Pt) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    eps = 1e-12
    d1, d2 = orient(q1, q2, p1), orient(q1, q2, p2)
    d3, d4 = orient(p1, p2, q1), orient(p1, p2, q2)
    return (((d1 > eps and d2 < -eps) or (d1 < -eps and d2 > eps))
            and ((d3 > eps and d4 < -eps) or (d3 < -eps and d4 > eps)))


def _self_intersects(pts: list[Pt], cell: float) -> bool:
    """Whether the closed polyline pts (last point == first) crosses itself."""
    m = len(pts) - 1
    grid: dict[tuple[int, int], list[int]] = {}
    for i in range(m):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        for gx in range(math.floor(min(x0, x1) / cell), math.floor(max(x0, x1) / cell) + 1):
            for gy in range(math.floor(min(y0, y1) / cell), math.floor(max(y0, y1) / cell) + 1):
                grid.setdefault((gx, gy), []).append(i)
    for idx in grid.values():
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                i, j = idx[a], idx[b]
                if j - i <= 1 or (i == 0 and j == m - 1):
                    continue
                if _crosses(pts[i], pts[i + 1], pts[j], pts[j + 1]):
                    return True
    return False


def offset_outline(segs: list[Seg], r: float, outward: bool = True) -> list[Seg]:
    """The closed chain at distance r outside (or inside) a closed outline.

    Lines shift along their normal, arcs change radius about the same centre.
    Convex corners get a tangent arc of radius r around the corner; concave
    corners are trimmed at the intersection. Arcs whose radius shrinks to
    nothing are dropped when they are tangent to both neighbours (a smooth
    fillet). Raises OffsetError rather than returning a path that skips a
    feature, crosses itself or is not exactly r from the outline.
    The result keeps the winding direction of the input.
    """
    if r <= 0:
        raise OffsetError(f"offset distance must be positive, got {r}")
    ccw = _signed_area(segs) > 0
    side = 1.0 if ccw == outward else -1.0   # +1: offset to the right
    offs = [(i, _Off(s, r, side)) for i, s in enumerate(segs)]
    for i, o in offs:
        if o.is_arc and o.radius <= 1e-6 and not _smooth(segs, i):
            c = segs[i].center
            raise OffsetError(f"arc R{segs[i].radius:g} around ({c[0]:.2f}, "
                              f"{c[1]:.2f}) is smaller than the tool and meets "
                              f"its edges at a corner: feature narrower than "
                              f"the tool")
    # Smooth fillets smaller than r vanish into the corner of their neighbours.
    offs = [(i, o) for i, o in offs if not o.is_arc or o.radius > 1e-6]
    if len(offs) < 2:
        raise OffsetError("outline too small for the tool")

    n, m = len(segs), len(offs)
    starts: list[Pt] = [None] * m      # join point at the start of offs[k]
    ends: list[Pt] = [None] * m        # join point at the end of offs[k]
    corners: list[Seg | None] = [None] * m   # corner arc after offs[k]
    for k in range(m):
        i, u = offs[k]
        j, v = offs[(k + 1) % m]
        p, q = u.p1, v.p0
        mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        adjacent = j == (i + 1) % n
        if adjacent and math.dist(p, q) < _SNAP:
            ends[k] = starts[(k + 1) % m] = mid
            continue
        t = _tangent(segs[i], True)
        if adjacent and t[0] * (q[0] - p[0]) + t[1] * (q[1] - p[1]) > 0:
            v0, v1 = segs[i].b, segs[j].a
            vertex = ((v0[0] + v1[0]) / 2, (v0[1] + v1[1]) / 2)
            turn = ((p[0] - vertex[0]) * (q[1] - vertex[1])
                    - (p[1] - vertex[1]) * (q[0] - vertex[0]))
            ends[k], starts[(k + 1) % m] = p, q
            corners[k] = Arc(p, q, vertex, r, turn > 0)
            continue
        x = _intersect(u, v, mid)
        ends[k] = starts[(k + 1) % m] = x

    out: list[Seg] = []
    for k, (i, o) in enumerate(offs):
        if o.param(ends[k], True) - o.param(starts[k], False) <= 1e-6:
            a = segs[i].a
            raise OffsetError(f"edge starting at ({a[0]:.2f}, {a[1]:.2f}) "
                              f"vanishes when offset by {r}: feature narrower "
                              f"than the tool")
        out.append(o.make(starts[k], ends[k]))
        if corners[k] is not None:
            out.append(corners[k])

    _check(out, segs, r, ccw)
    return out


def _smooth(segs: list[Seg], i: int) -> bool:
    """Whether segs[i] runs tangent into both of its neighbours."""
    def tangent(u: Seg, v: Seg) -> bool:
        t, w = _tangent(u, True), _tangent(v, False)
        return (abs(t[0] * w[1] - t[1] * w[0]) < _TANGENT
                and t[0] * w[0] + t[1] * w[1] > 0)
    n = len(segs)
    return tangent(segs[i - 1], segs[i]) and tangent(segs[i], segs[(i + 1) % n])


def _check(out: list[Seg], segs: list[Seg], r: float, ccw: bool) -> None:
    step = min(0.5, r / 4)
    pts = sample(out, step)
    if (_signed_area(out) > 0) != ccw:
        raise OffsetError("offset path turned inside out")
    if _self_intersects(pts, 4 * step):
        raise OffsetError("offset path crosses itself")
    for p in pts:
        d = distance_to_chain(p, segs)
        if d < r - _DIST_TOL:
            raise OffsetError(f"offset path comes closer than {r} to the "
                              f"outline at ({p[0]:.2f}, {p[1]:.2f})")
        if d > r + _DIST_TOL:
            raise OffsetError(f"offset path is {d:.3f} from the outline at "
                              f"({p[0]:.2f}, {p[1]:.2f}) instead of {r}: a "
                              f"feature narrower than the tool was skipped")
