"""Nesting tool settings. Every guessed number lives here as a placeholder default."""
import copy
import math
from dataclasses import dataclass, field, fields, is_dataclass, asdict


# SettingsError and the stepover limits live in tools.py (which must not import this module).
from .tools import SettingsError, MIN_STEPOVER_PCT, STEPOVER_MESSAGE  # noqa: F401
from .tools import ROUTER_HEADS, Bit, HeadError, ToolTable


@dataclass
class Panel:
    length: float = 2440
    width: float = 1220
    thickness: float = 18   # the blanks are sawn from the panel: shapes have this thickness
    edge: float = 10        # saw trim at every panel border
    kerf: float = 4         # panel saw blade width


@dataclass
class Machine:
    # Work frame a blank must fit in (long side along machine X). PLACEHOLDERS decoded from a
    # control config file, not measured: to verify on the machine's axis parameter screens.
    frame_x: float = 3072
    frame_y: float = 787
    # Program frame of a blank: X0 Y0 is the blank's corner at the pins, X to the right.
    # 'front': Y grows toward the front of the machine (origin = back-left corner, top left of
    # the picture with the operator at the bottom). The user's statement, 2026-11-13; NOT yet
    # verified on the machine. 'back': Y grows toward the back (origin bottom left of the picture).
    y_toward: str = "front"


@dataclass
class Heights:
    scrap: float = 18
    into_scrap: float = 0.5       # how far a shape cut goes below the blank into the scrap
    fix_into_scrap: float = 1


# The router and the drills name a head; the bit in that head (Settings.tools) gives the
# diameter, speeds and feeds.
@dataclass
class Router:
    tool: int = 66  # head; the default table holds Router 8 there (post/README.md)
    clearance: float = 4
    direction: str = "ccw"


@dataclass
class DrillFix:
    tool: int = 1  # placeholder head


@dataclass
class DrillScrew:
    tool: int = 2  # placeholder head
    depth: float = 8    # below the blank, into the scrap


@dataclass
class Pockets:
    # All PLACEHOLDERS, to verify on the machine.
    min_circle_diameter: float = 8   # smallest circle that counts as a pocket
    min_floor: float = 2             # material left under a pocket
    tool: int = 66
    diameter: float = 8
    depth: float = 8
    depth_per_pass: float = 4
    plunge_feed: float = 1
    cut_feed: float = 3
    spindle_rpm: float = 18000
    stepover_pct: float = 40         # of the tool diameter, 10 to 100
    direction: str = "cw"            # turning sense seen from above for pocket walls;
                                     # climb vs conventional is unverified


@dataclass
class Blank:
    shapes_per: int = 2
    group_by: str = "length"  # 'length' | 'order'
    margin_end: float = 45
    margin_side: float = 45
    fix_inset: float = 15
    head_dia: float = 14


def _build(cls, data):
    """Build dataclass `cls` from dict `data`; unknown keys ignored, missing default."""
    data = data if isinstance(data, dict) else {}
    base = cls()
    kwargs = {}
    for f in fields(cls):
        if f.name not in data or f.name == 'tools':    # the table is passed apart
            continue
        default = getattr(base, f.name)
        if is_dataclass(default):
            kwargs[f.name] = _build(type(default), data[f.name])
        else:
            kwargs[f.name] = data[f.name]
    return cls(**kwargs)


def _migrate(d: dict) -> dict:
    """Settings saved before 2026-11-09 (template model): keep the values that still mean the
    same thing. template.* -> blank.*, heights.shape_thickness -> panel.thickness."""
    if not isinstance(d, dict):
        return {}
    d = copy.deepcopy(d)
    if 'blank' not in d and isinstance(d.get('template'), dict):
        d['blank'] = d['template']
    heights = d.get('heights')
    if isinstance(heights, dict) and 'shape_thickness' in heights:
        panel = d.setdefault('panel', {})
        if isinstance(panel, dict) and 'thickness' not in panel:
            panel['thickness'] = heights['shape_thickness']
    return d


@dataclass
class Settings:
    panel: Panel = field(default_factory=Panel)
    machine: Machine = field(default_factory=Machine)
    heights: Heights = field(default_factory=Heights)
    router: Router = field(default_factory=Router)
    drill_fix: DrillFix = field(default_factory=DrillFix)
    drill_screw: DrillScrew = field(default_factory=DrillScrew)
    blank: Blank = field(default_factory=Blank)
    pockets: Pockets = field(default_factory=Pockets)
    origin: str = "G54"
    # The project's tool table; not part of to_dict (project.json stores it apart).
    tools: ToolTable = field(default_factory=ToolTable.default)

    @classmethod
    def default(cls) -> "Settings":
        return cls()

    def to_dict(self) -> dict:
        d = asdict(self)
        del d['tools']
        return d

    @classmethod
    def from_dict(cls, d: dict, tools: ToolTable | None = None) -> "Settings":
        """Settings from a dict (unknown keys, such as the old router diameter, ignored) and
        a tool table (None: the default table)."""
        s = _build(cls, _migrate(d))
        s.tools = ToolTable.default() if tools is None else tools
        return s

    @property
    def router_bit(self) -> Bit:
        return self.tools.resolve(self.router.tool, 'router', 'router.tool', 'router')

    @property
    def fix_bit(self) -> Bit:
        return self.tools.resolve(self.drill_fix.tool, 'fixing drill', 'drill_fix.tool',
                                  'drill')

    @property
    def screw_bit(self) -> Bit:
        return self.tools.resolve(self.drill_screw.tool, 'screw drill', 'drill_screw.tool',
                                  'drill')

    @property
    def gap(self) -> float:
        return self.router_bit.diameter + self.router.clearance

    @property
    def stack(self) -> float:
        """Height of the stack on the cups: scrap plate + blank."""
        return self.heights.scrap + self.panel.thickness

    def _get(self, path: str):
        obj = self
        for p in path.split("."):
            obj = getattr(obj, p)
        return obj

    def validate(self) -> None:
        positive = [
            "panel.length", "panel.width", "panel.thickness",
            "machine.frame_x", "machine.frame_y",
            "heights.scrap",
            "router.tool", "drill_fix.tool", "drill_screw.tool", "drill_screw.depth",
            "blank.head_dia",
            "pockets.min_circle_diameter", "pockets.min_floor", "pockets.diameter",
            "pockets.depth", "pockets.depth_per_pass", "pockets.plunge_feed",
            "pockets.cut_feed", "pockets.spindle_rpm", "pockets.stepover_pct",
        ]
        shapes_per = self.blank.shapes_per
        if (not isinstance(shapes_per, int) or isinstance(shapes_per, bool)
                or shapes_per < 1):
            raise SettingsError("blank.shapes_per",
                                "must be a whole number, 1 or more")
        for path in ("router.tool", "drill_fix.tool", "drill_screw.tool",
                     "pockets.tool"):
            v = self._get(path)
            if not isinstance(v, int) or isinstance(v, bool) or v < 1:
                raise SettingsError(path, "must be a whole tool number, 1 or more")
        non_negative = [
            "panel.edge", "panel.kerf",
            "heights.into_scrap", "heights.fix_into_scrap",
            "router.clearance",
            "blank.margin_end", "blank.margin_side", "blank.fix_inset",
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
            "pockets.direction": ("ccw", "cw"),
            "blank.group_by": ("length", "order"),
            "machine.y_toward": ("front", "back"),
        }
        for path, allowed in choices.items():
            if self._get(path) not in allowed:
                raise SettingsError(path, f"must be one of {', '.join(allowed)}")
        # relies on the positive-number loop above having run: stepover_pct is a number > 0 here
        if not MIN_STEPOVER_PCT <= self.pockets.stepover_pct <= 100:
            raise SettingsError("pockets.stepover_pct", STEPOVER_MESSAGE)
        self._validate_heads()
        self._validate_sizes()
        self._validate_depths()
        self._validate_pocket_depth()

    def _validate_heads(self) -> None:
        """The table itself, then each operation's head (a HeadError names operation and head).
        The pocket default head is only checked to be a router head here (R2): that it holds
        a router bit matters only for a pocket group that uses it."""
        self.tools.validate()
        self.router_bit, self.fix_bit, self.screw_bit   # noqa: B018 -- resolve raises
        t = self.pockets.tool
        if t not in ROUTER_HEADS:
            raise HeadError("pockets.tool", f"pocket default: head T{t} cannot be used here; "
                                            f"the router uses T65 or T66")

    def _validate_sizes(self) -> None:
        """Cross-field checks: the trim, the kerf and the margins must leave room for a shape."""
        p, b, m = self.panel, self.blank, self.machine
        if p.edge and p.edge < p.kerf:
            raise SettingsError("panel.edge", f"must be 0 (no trim) or at least the saw kerf "
                                              f"panel.kerf ({p.kerf:g} mm): the trim cut's kerf "
                                              f"lies in the trimmed edge")
        if not 2 * p.edge + p.kerf < min(p.length, p.width):
            raise SettingsError("panel.edge", f"trim on both sides plus a kerf leaves nothing of "
                                              f"the {min(p.length, p.width):g} mm panel side")
        if not 2 * b.margin_end < m.frame_x:
            raise SettingsError("machine.frame_x", f"must be more than 2 x blank.margin_end "
                                                   f"({2 * b.margin_end:g} mm): no room for a shape")
        if not 2 * b.margin_side < m.frame_y:
            raise SettingsError("machine.frame_y", f"must be more than 2 x blank.margin_side "
                                                   f"({2 * b.margin_side:g} mm): no room for a shape")

    def _validate_pocket_depth(self) -> None:
        pk = self.pockets
        if not pk.depth + pk.min_floor <= self.panel.thickness:
            raise SettingsError("pockets.depth", f"depth plus pockets.min_floor ({pk.min_floor:g} "
                                                 f"mm) must not exceed the panel thickness "
                                                 f"({self.panel.thickness:g} mm)")

    def _validate_depths(self) -> None:
        """No written depth may reach the top of the vacuum cups (below the scrap plate)."""
        h = self.heights
        cups = "deeper reaches the vacuum cups"
        limits = [
            ("heights.into_scrap", h.into_scrap),
            ("heights.fix_into_scrap", h.fix_into_scrap),
            ("drill_screw.depth", self.drill_screw.depth),
        ]
        for path, value in limits:
            if not value < h.scrap:
                raise SettingsError(path, f"must be less than heights.scrap ({h.scrap:g} mm): "
                                          f"{cups}")
