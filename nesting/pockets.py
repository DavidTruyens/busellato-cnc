"""Pocket groups: pockets with the same shape and place share one set of machining settings."""
from __future__ import annotations

import math
from dataclasses import dataclass, field, fields

from .dxf import Pocket, Shape
from .geometry import Arc, bbox
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
