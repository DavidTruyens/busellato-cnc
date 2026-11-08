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
