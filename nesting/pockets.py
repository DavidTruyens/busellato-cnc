"""Pocket groups: pockets with the same shape and place share one set of machining settings."""
from __future__ import annotations

from dataclasses import dataclass, fields

from .dxf import Pocket, Shape
from .geometry import Arc, bbox
from .settings import Pockets

# Distinct from the page colours (blank tan, shape blue, holes red, saw cut black).
PALETTE = ["#00897b", "#8e24aa", "#ef6c00", "#2e7d32", "#00acc1", "#c2185b",
           "#7cb342", "#6a1b9a", "#f9a825", "#00695c"]

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


def find_groups(shapes: list[Shape]) -> list[PocketGroup]:
    groups: dict[str, PocketGroup] = {}
    for shape in shapes:
        for p in shape.pockets:
            key = group_key(p)
            g = groups.get(key)
            if g is None:
                x0, y0, x1, y1 = bbox(p.outline)
                n = len(groups)
                g = groups[key] = PocketGroup(f"G{n + 1}", key, x1 - x0, y1 - y0,
                                              _kind(p, x1 - x0, y1 - y0), 0,
                                              PALETTE[n % len(PALETTE)])
            g.count += 1
    return list(groups.values())


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


_TYPES = {"enabled": bool, "tool": int, "direction": str}


def effective(group_key: str, overrides: dict, defaults: Pockets) -> GroupSettings:
    """Defaults merged with overrides[group_key]; unknown fields ignored."""
    vals = {f.name: getattr(defaults, f.name) for f in fields(GroupSettings)
            if hasattr(defaults, f.name)}
    vals["enabled"] = True
    for name, v in (overrides.get(group_key) or {}).items():
        if name in vals:
            vals[name] = _coerce(name, v)
    return GroupSettings(**vals)


def _coerce(name: str, v):
    kind = _TYPES.get(name, float)
    try:
        if kind is bool:
            if not isinstance(v, bool):
                raise ValueError
            return v
        if kind is str:
            if not isinstance(v, str) or not v:
                raise ValueError
            return v
        if isinstance(v, bool):
            raise ValueError
        out = kind(v)
        if kind is int and out != float(v):
            raise ValueError
        return out
    except (TypeError, ValueError):
        raise ValueError(f"invalid value for {name}: {v!r}") from None
