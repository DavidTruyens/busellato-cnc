"""Minimal ASCII DXF reader for plate outlines (stdlib only)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from .geometry import Arc, Line, Pt, Seg, bbox, translate

JOIN_TOL = 0.01


class DxfError(Exception):
    def __init__(self, path, message: str):
        self.path = str(path)
        self.message = message
        super().__init__(f"{Path(path).name}: {message}")


@dataclass(frozen=True)
class Hole:
    x: float
    y: float
    diameter: float


@dataclass
class Pocket:
    """A recess cut part-way into the plate, in the shape's own frame (outline lower-left at 0,0).

    outline: closed chain of lines and arcs.
    circle: set for a round pocket (a CIRCLE entity bigger than the hole limit); the outline is
        then two 180-degree counter-clockwise arcs (right point -> left point -> right point)
        so downstream code can offset it without splitting arcs.
    from_circle: True when the pocket came from a circle.
    """
    outline: list[Seg]
    circle: Hole | None = None
    from_circle: bool = False


@dataclass
class Shape:
    name: str
    outline: list[Seg]
    holes: list[Hole]
    pockets: list[Pocket] = field(default_factory=list)

    @property
    def length(self) -> float:
        x0, _, x1, _ = bbox(self.outline)
        return x1 - x0

    @property
    def width(self) -> float:
        _, y0, _, y1 = bbox(self.outline)
        return y1 - y0


def _pairs(text: str) -> list[tuple[int, str]]:
    lines = text.splitlines()
    out = []
    for i in range(0, len(lines) - 1, 2):
        out.append((int(lines[i].strip()), lines[i + 1].strip()))
    return out


def _entities(pairs: list[tuple[int, str]]) -> list[tuple[str, list[tuple[int, str]]]]:
    """Return (type, group codes) for each entity in the ENTITIES section."""
    ents: list[tuple[str, list[tuple[int, str]]]] = []
    in_ents = False
    cur = None
    for i, (code, val) in enumerate(pairs):
        if code == 0 and val == "SECTION":
            in_ents = i + 1 < len(pairs) and pairs[i + 1] == (2, "ENTITIES")
            cur = None
        elif code == 0 and val == "ENDSEC":
            in_ents = False
            cur = None
        elif in_ents:
            if code == 0:
                cur = (val, [])
                ents.append(cur)
            elif cur is not None:
                cur[1].append((code, val))
    return ents


def _get(codes, code, default=None):
    for c, v in codes:
        if c == code:
            return v
    return default


def _bulge_seg(p: Pt, q: Pt, bulge: float) -> Seg | None:
    d = math.dist(p, q)
    if d < 1e-9:
        return None
    if abs(bulge) < 1e-12:
        return Line(p, q)
    theta = 4 * math.atan(bulge)
    radius = d / 2 / abs(math.sin(theta / 2))
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    nx, ny = -(q[1] - p[1]) / d, (q[0] - p[0]) / d
    off = d / 2 * (1 - bulge * bulge) / (2 * bulge)
    return Arc(p, q, (mx + nx * off, my + ny * off), radius, bulge > 0)


def _poly_segs(verts: list[tuple[float, float, float]], closed: bool) -> list[Seg]:
    segs: list[Seg] = []
    n = len(verts)
    for i in range(n if closed else n - 1):
        x0, y0, b = verts[i]
        x1, y1, _ = verts[(i + 1) % n]
        s = _bulge_seg((x0, y0), (x1, y1), b)
        if s is not None:
            segs.append(s)
    return segs


def _verts(codes) -> list[tuple[float, float, float]]:
    """Vertices from the group codes of an LWPOLYLINE."""
    verts: list[list[float]] = []
    for c, v in codes:
        if c == 10:
            verts.append([float(v), 0.0, 0.0])
        elif c == 20 and verts:
            verts[-1][1] = float(v)
        elif c == 42 and verts:
            verts[-1][2] = float(v)
    return [(x, y, b) for x, y, b in verts]


def _parse(ents):
    """Return (segs as (layer, seg) list, circles as (layer, x, y, r) list)."""
    segs: list[tuple[str, Seg]] = []
    circles: list[tuple[str, float, float, float]] = []
    i = 0
    while i < len(ents):
        kind, codes = ents[i]
        layer = _get(codes, 8, "0")
        if kind == "LINE":
            a = (float(_get(codes, 10)), float(_get(codes, 20)))
            b = (float(_get(codes, 11)), float(_get(codes, 21)))
            segs.append((layer, Line(a, b)))
        elif kind == "ARC":
            cx, cy = float(_get(codes, 10)), float(_get(codes, 20))
            r = float(_get(codes, 40))
            a0 = math.radians(float(_get(codes, 50)))
            a1 = math.radians(float(_get(codes, 51)))
            segs.append((layer, Arc((cx + r * math.cos(a0), cy + r * math.sin(a0)),
                                    (cx + r * math.cos(a1), cy + r * math.sin(a1)),
                                    (cx, cy), r, True)))
        elif kind == "CIRCLE":
            circles.append((layer, float(_get(codes, 10)), float(_get(codes, 20)),
                            float(_get(codes, 40))))
        elif kind == "LWPOLYLINE":
            closed = bool(int(_get(codes, 70, "0")) & 1)
            for s in _poly_segs(_verts(codes), closed):
                segs.append((layer, s))
        elif kind == "POLYLINE":
            closed = bool(int(_get(codes, 70, "0")) & 1)
            verts = []
            while i + 1 < len(ents) and ents[i + 1][0] == "VERTEX":
                vc = ents[i + 1][1]
                verts.append((float(_get(vc, 10)), float(_get(vc, 20)),
                              float(_get(vc, 42, "0"))))
                i += 1
            for s in _poly_segs(verts, closed):
                segs.append((layer, s))
        i += 1
    return segs, circles


def _near(p: Pt, q: Pt) -> bool:
    return math.dist(p, q) <= JOIN_TOL


def _reverse(s: Seg) -> Seg:
    if isinstance(s, Arc):
        return Arc(s.b, s.a, s.center, s.radius, not s.ccw)
    return Line(s.b, s.a)


def _chains(segs: list[Seg]) -> list[list[Seg]]:
    """Group segments into head-to-tail chains by endpoint matching."""
    rest = list(segs)
    chains = []
    while rest:
        chain = [rest.pop(0)]
        grew = True
        while grew:
            grew = False
            for j, s in enumerate(rest):
                end, start = chain[-1].b, chain[0].a
                if _near(s.a, end):
                    chain.append(s)
                elif _near(s.b, end):
                    chain.append(_reverse(s))
                elif _near(s.b, start):
                    chain.insert(0, s)
                elif _near(s.a, start):
                    chain.insert(0, _reverse(s))
                else:
                    continue
                rest.pop(j)
                grew = True
                break
        chains.append(chain)
    return chains


def _closed(chain: list[Seg]) -> bool:
    return _near(chain[0].a, chain[-1].b)


def _area(chain: list[Seg]) -> float:
    x0, y0, x1, y1 = bbox(chain)
    return (x1 - x0) * (y1 - y0)


def _sample(outline: list[Seg]) -> list[Pt]:
    """Polygon approximating the outline; arcs sampled every ~2 degrees."""
    pts: list[Pt] = []
    for s in outline:
        pts.append(s.a)
        if isinstance(s, Arc):
            a0 = math.atan2(s.a[1] - s.center[1], s.a[0] - s.center[0])
            a1 = math.atan2(s.b[1] - s.center[1], s.b[0] - s.center[0])
            sweep = (a1 - a0) % (2 * math.pi) if s.ccw else -((a0 - a1) % (2 * math.pi))
            n = max(2, int(abs(sweep) / math.radians(2)) + 1)
            for k in range(1, n):
                t = a0 + sweep * k / n
                pts.append((s.center[0] + s.radius * math.cos(t),
                            s.center[1] + s.radius * math.sin(t)))
    return pts


def _inside(poly: list[Pt], x: float, y: float) -> bool:
    """Ray casting point-in-polygon test."""
    inside = False
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def _round_pocket(cx: float, cy: float, r: float) -> Pocket:
    right, left = (cx + r, cy), (cx - r, cy)
    return Pocket([Arc(right, left, (cx, cy), r, True), Arc(left, right, (cx, cy), r, True)],
                  Hole(cx, cy, 2 * r), True)


def read_dxf(path: str | Path, min_pocket_circle: float = 8.0) -> Shape:
    path = Path(path)
    try:
        # explicit UTF-8 (a BOM is dropped); a stray byte must not stop the outline being read
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as e:
        raise DxfError(path, f"cannot open file: {e.strerror or e}") from e
    try:
        segs, circles = _parse(_entities(_pairs(text)))
    except (ValueError, TypeError) as e:
        raise DxfError(path, f"cannot parse DXF (no outline readable): {e}") from e

    contour = [s for layer, s in segs if layer == "CONTOUR"]
    candidates = contour if contour else [s for layer, s in segs if layer != "POCKET"]
    chains = _chains(candidates)
    closed = [c for c in chains if _closed(c)]
    if contour:
        if len(chains) > len(closed):
            raise DxfError(path, "outline is open (endpoints do not join)")
        if len(closed) > 1:
            raise DxfError(path, "more than one outline on layer CONTOUR")
    if not closed:
        if chains:
            raise DxfError(path, "outline is open (endpoints do not join)")
        raise DxfError(path, "no outline found")
    outline = max(closed, key=_area)

    x0, y0, x1, y1 = bbox(outline)
    poly = _sample(outline)
    on_holes = [c for c in circles if c[0] == "HOLES"]
    if on_holes:
        chosen = on_holes
    else:
        chosen = [c for c in circles if c[0] != "POCKET" and _inside(poly, c[1], c[2])]
    holes: list[Hole] = []
    pockets: list[Pocket] = []
    for _, cx, cy, r in chosen:
        if 2 * r > min_pocket_circle:
            pockets.append(_round_pocket(cx - x0, cy - y0, r))
        else:
            holes.append(Hole(cx - x0, cy - y0, 2 * r))
    # a circle on layer POCKET is a round pocket whatever its size
    for layer, cx, cy, r in circles:
        if layer == "POCKET":
            pockets.append(_round_pocket(cx - x0, cy - y0, r))

    pocket_segs = [s for layer, s in segs if layer == "POCKET"]
    if pocket_segs:
        loops = _chains(pocket_segs)
        for c in loops:
            if not _closed(c):
                raise DxfError(path, "pocket outline on layer POCKET is open (endpoints do not join)")
            if not _inside(poly, c[0].a[0], c[0].a[1]):
                raise DxfError(path, "pocket on layer POCKET lies outside the outline")
    else:
        if contour:
            others = _chains([s for layer, s in segs if layer != "CONTOUR"])
        else:
            others = [c for c in chains if c is not outline]
        loops = [c for c in others if _closed(c) and _inside(poly, c[0].a[0], c[0].a[1])]
    for c in loops:
        pockets.append(Pocket(translate(c, -x0, -y0)))
    return Shape(path.stem, translate(outline, -x0, -y0), holes, pockets)
