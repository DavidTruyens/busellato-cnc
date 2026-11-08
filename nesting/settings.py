"""Nesting tool settings. Every guessed number lives here as a placeholder default."""
import math
from dataclasses import dataclass, field, fields, is_dataclass, asdict


class SettingsError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


@dataclass
class Panel:
    length: float = 2440
    width: float = 1220
    edge: float = 10


@dataclass
class Heights:
    scrap: float = 18
    template_stock: float = 18
    shape_thickness: float = 18
    into_template: float = 0.3
    into_scrap: float = 0.5
    fix_into_scrap: float = 1


@dataclass
class Router:
    tool: int = 66  # 66 = diameter 8 (post/README.md)
    diameter: float = 8
    spindle_rpm: float = 18000
    plunge_feed: float = 1
    cut_feed: float = 3
    depth_per_pass: float = 9
    clearance: float = 4
    direction: str = "ccw"


@dataclass
class DrillFix:
    tool: int = 1  # placeholder tool number
    diameter: float = 6
    feed: float = 1


@dataclass
class DrillScrew:
    tool: int = 2  # placeholder tool number
    diameter: float = 3
    depth: float = 8
    feed: float = 1


@dataclass
class Template:
    mode: str = "auto"  # 'auto' | 'fixed' | 'none'
    shapes_per: int = 2
    group_by: str = "length"  # 'length' | 'order'
    margin_end: float = 45
    margin_side: float = 45
    fix_inset: float = 15
    head_dia: float = 14
    fixed_width: float = 0
    fixed_height: float = 0


def _build(cls, data):
    """Build dataclass `cls` from dict `data`; unknown keys ignored, missing default."""
    data = data if isinstance(data, dict) else {}
    base = cls()
    kwargs = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        default = getattr(base, f.name)
        if is_dataclass(default):
            kwargs[f.name] = _build(type(default), data[f.name])
        else:
            kwargs[f.name] = data[f.name]
    return cls(**kwargs)


@dataclass
class Settings:
    panel: Panel = field(default_factory=Panel)
    heights: Heights = field(default_factory=Heights)
    router: Router = field(default_factory=Router)
    drill_fix: DrillFix = field(default_factory=DrillFix)
    drill_screw: DrillScrew = field(default_factory=DrillScrew)
    template: Template = field(default_factory=Template)
    origin: str = "G54"

    @classmethod
    def default(cls) -> "Settings":
        return cls()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Settings":
        return _build(cls, d)

    @property
    def gap(self) -> float:
        return self.router.diameter + self.router.clearance

    def _get(self, path: str):
        obj = self
        for p in path.split("."):
            obj = getattr(obj, p)
        return obj

    def validate(self) -> None:
        positive = [
            "panel.length", "panel.width",
            "heights.scrap", "heights.template_stock", "heights.shape_thickness",
            "router.tool", "router.diameter", "router.spindle_rpm",
            "router.plunge_feed", "router.cut_feed", "router.depth_per_pass",
            "drill_fix.tool", "drill_fix.diameter", "drill_fix.feed",
            "drill_screw.tool", "drill_screw.diameter", "drill_screw.depth",
            "drill_screw.feed",
            "template.head_dia",
        ]
        shapes_per = self.template.shapes_per
        if (not isinstance(shapes_per, int) or isinstance(shapes_per, bool)
                or shapes_per < 1):
            raise SettingsError("template.shapes_per",
                                "must be a whole number, 1 or more")
        for path in ("router.tool", "drill_fix.tool", "drill_screw.tool"):
            v = self._get(path)
            if not isinstance(v, int) or isinstance(v, bool) or v < 1:
                raise SettingsError(path, "must be a whole tool number, 1 or more")
        non_negative = [
            "panel.edge",
            "heights.into_template", "heights.into_scrap", "heights.fix_into_scrap",
            "router.clearance",
            "template.margin_end", "template.margin_side", "template.fix_inset",
            "template.fixed_width", "template.fixed_height",
        ]
        for path in positive:
            value = self._get(path)
            if (not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not math.isfinite(value) or not value > 0):
                raise SettingsError(path, "must be a number greater than 0")
        for path in non_negative:
            value = self._get(path)
            if (not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not math.isfinite(value) or not value >= 0):
                raise SettingsError(path, "must be a number, not negative")
        choices = {
            "origin": ("G54", "G55"),
            "router.direction": ("ccw", "cw"),
            "template.mode": ("auto", "fixed", "none"),
            "template.group_by": ("length", "order"),
        }
        for path, allowed in choices.items():
            if self._get(path) not in allowed:
                raise SettingsError(path, f"must be one of {', '.join(allowed)}")
        self._validate_depths()

    def _validate_depths(self) -> None:
        """No written depth may reach the top of the vacuum cups (below the scrap plate)."""
        h = self.heights
        ts = 0.0 if self.template.mode == "none" else h.template_stock
        cups = "deeper reaches the vacuum cups"
        limits = [
            ("heights.into_scrap", h.into_scrap, h.scrap, "heights.scrap", cups),
            ("heights.fix_into_scrap", h.fix_into_scrap, h.scrap, "heights.scrap", cups),
            ("drill_screw.depth", self.drill_screw.depth, h.scrap + ts,
             "heights.scrap" if self.template.mode == "none"
             else "heights.template_stock + heights.scrap", cups),
            ("heights.into_template", h.into_template, h.template_stock,
             "heights.template_stock",
             "deeper cuts through the template, towards the vacuum cups"),
        ]
        for path, value, limit, what, why in limits:
            if not value < limit:
                raise SettingsError(path, f"must be less than {what} ({limit:g} mm): {why}")
