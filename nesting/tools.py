"""The tool table: the machine's fixed heads, the bits that sit in them, and the checks.

This module owns SettingsError and the stepover limits (settings.py re-exports them) so that
it never has to import settings.py.
"""
import math
import re
from dataclasses import dataclass, field


# Smallest stepover, % of the tool diameter: a tiny one gives thousands of rings (a plan that
# never ends); 10 % already gives 10 rings per tool diameter of pocket width.
MIN_STEPOVER_PCT = 10
STEPOVER_MESSAGE = "must be between 10 and 100 (percent of the tool diameter)"


class SettingsError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


class HeadError(SettingsError):
    """An operation's head is not usable: unknown, wrong kind, empty or holding the wrong bit."""


@dataclass(frozen=True)
class Head:
    number: int
    label: str
    allows: tuple


def _build_heads() -> dict:
    heads = {}
    for n in (65, 66):
        heads[n] = Head(n, "big spindle", ('router',))
    for n in range(1, 31):
        heads[n] = Head(n, "drill cross, vertical", ('drill',))
    for n in (53, 56):
        heads[n] = Head(n, "drill cross, horizontal", ('drill',))
    heads[60] = Head(60, "blade/drill in X", ('drill', 'blade'))
    heads[61] = Head(61, "blade/drill in Y", ('drill', 'blade'))
    return dict(sorted(heads.items()))


HEADS = _build_heads()
# The heads the programs use (R1); the other heads can hold a bit but no operation may name them.
ROUTER_HEADS = (65, 66)
DRILL_HEADS = tuple(range(1, 31))

BIT_TYPES = ('router', 'drill', 'blade')
REQUIRED = {
    'router': ('diameter', 'spindle_rpm', 'plunge_feed', 'cut_feed', 'depth_per_pass',
               'stepover_pct'),
    'drill': ('diameter', 'plunge_feed'),
    'blade': ('diameter',),
}
OPTIONAL = {
    'router': (),
    'drill': ('spindle_rpm',),
    'blade': ('spindle_rpm', 'cut_feed'),
}

_ID_RE = re.compile(r'[A-Za-z0-9_-]{1,20}')
_HEAD_KEY_RE = re.compile(r'T(\d+)')


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


@dataclass
class Bit:
    id: str
    name: str
    type: str
    diameter: object
    spindle_rpm: object = None
    plunge_feed: object = None
    cut_feed: object = None
    depth_per_pass: object = None
    stepover_pct: object = None

    def applicable(self) -> tuple:
        """Fields this bit's type uses (empty for an unknown type)."""
        return REQUIRED.get(self.type, ()) + OPTIONAL.get(self.type, ()) \
            if isinstance(self.type, str) else ()


@dataclass
class ToolTable:
    bits: list = field(default_factory=list)
    heads: dict = field(default_factory=dict)   # head number -> bit id; an empty head is absent

    @classmethod
    def default(cls) -> "ToolTable":
        return cls(
            bits=[Bit('b1', 'Router 8', 'router', 8, spindle_rpm=18000, plunge_feed=1,
                      cut_feed=3, depth_per_pass=9, stepover_pct=40),
                  Bit('b2', 'Drill 6', 'drill', 6, plunge_feed=1),
                  Bit('b3', 'Drill 3', 'drill', 3, plunge_feed=1)],
            heads={66: 'b1', 1: 'b2', 2: 'b3'})

    @classmethod
    def from_dict(cls, d) -> "ToolTable":
        """Lenient on values (validate() judges them), strict on structure and heads."""
        if not isinstance(d, dict):
            raise SettingsError("tools", "must be an object with bits and heads")
        raw_bits = d.get('bits')
        if not isinstance(raw_bits, list):
            raise SettingsError("tools.bits", "must be a list of bits")
        bits = []
        seen = set()
        for i, rb in enumerate(raw_bits):
            if not isinstance(rb, dict):
                raise SettingsError("tools.bits", f"entry {i + 1} must be an object")
            bit_id = rb.get('id', '')
            if not isinstance(bit_id, str):
                raise SettingsError("tools.bits", f"entry {i + 1}: id must be text")
            if bit_id in seen:
                raise SettingsError("tools.bits", f"two bits share the id {bit_id}")
            seen.add(bit_id)
            btype = rb.get('type')
            if not isinstance(btype, str):
                raise SettingsError(f"tools.bits.{bit_id}.type",
                                    f"must be one of {', '.join(BIT_TYPES)}")
            keep = REQUIRED.get(btype, ()) + OPTIONAL.get(btype, ())
            values = {k: rb.get(k) for k in keep if k != 'diameter'}
            bits.append(Bit(id=bit_id, name=rb.get('name', ''), type=btype,
                            diameter=rb.get('diameter'), **values))
        raw_heads = d.get('heads')
        if not isinstance(raw_heads, dict):
            raise SettingsError("tools.heads", "must be an object of head to bit id")
        heads = {}
        for key, value in raw_heads.items():
            m = _HEAD_KEY_RE.fullmatch(key) if isinstance(key, str) else None
            number = int(m.group(1)) if m else None
            if number not in HEADS:
                raise SettingsError(f"tools.heads.{key}", f"{key} is not a machine head")
            if value is None:
                continue
            if not isinstance(value, str):
                raise SettingsError(f"tools.heads.{key}", "must be a bit id or null")
            heads[number] = value
        table = cls(bits, dict(sorted(heads.items())))
        table._check_heads()
        return table

    def to_dict(self) -> dict:
        bits = []
        for b in self.bits:
            item = {'id': b.id, 'name': b.name, 'type': b.type, 'diameter': b.diameter}
            for k in (REQUIRED.get(b.type, ()) if isinstance(b.type, str) else ()):
                if k != 'diameter':
                    item[k] = getattr(b, k)
            for k in (OPTIONAL.get(b.type, ()) if isinstance(b.type, str) else ()):
                if getattr(b, k) is not None:
                    item[k] = getattr(b, k)
            bits.append(item)
        return {'bits': bits,
                'heads': {f"T{n}": bid for n, bid in sorted(self.heads.items())}}

    def bit(self, bit_id):
        for b in self.bits:
            if b.id == bit_id:
                return b
        return None

    def bit_in(self, head: int):
        bid = self.heads.get(head)
        return None if bid is None else self.bit(bid)

    def heads_of(self, bit_id: str) -> list:
        return sorted(n for n, bid in self.heads.items() if bid == bit_id)

    def new_id(self) -> str:
        ids = {b.id for b in self.bits}
        n = 1
        while f"b{n}" in ids:
            n += 1
        return f"b{n}"

    def label(self, head: int) -> str:
        b = self.bit_in(head)
        return f"T{head} {b.name}" if b else f"T{head} (empty)"

    def validate(self) -> None:
        seen = set()
        for b in self.bits:
            if not isinstance(b.id, str):
                raise SettingsError("tools.bits", "every bit id must be text")
            if b.id in seen:
                raise SettingsError("tools.bits", f"two bits share the id {b.id}")
            seen.add(b.id)
            self._validate_bit(b)
        self._check_heads()

    def _validate_bit(self, b: Bit) -> None:
        path = f"tools.bits.{b.id}"
        if not isinstance(b.id, str) or not _ID_RE.fullmatch(b.id):
            raise SettingsError(f"{path}.id", "must be 1 to 20 letters, digits, - or _")
        if not isinstance(b.name, str) or not 1 <= len(b.name.strip()) <= 40:
            raise SettingsError(f"{path}.name", "must be 1 to 40 characters")
        if b.type not in BIT_TYPES:
            raise SettingsError(f"{path}.type", f"must be one of {', '.join(BIT_TYPES)}")
        for k in REQUIRED[b.type] + OPTIONAL[b.type]:
            v = getattr(b, k)
            if v is None and k in OPTIONAL[b.type]:
                continue
            if not _is_number(v) or not v > 0:
                raise SettingsError(f"{path}.{k}", "must be a number greater than 0")
        if b.type == 'router' and not MIN_STEPOVER_PCT <= b.stepover_pct <= 100:
            raise SettingsError(f"{path}.stepover_pct", STEPOVER_MESSAGE)

    def _check_heads(self) -> None:
        for n, bid in sorted(self.heads.items()):
            path = f"tools.heads.T{n}"
            if n not in HEADS:
                raise SettingsError(path, f"T{n} is not a machine head")
            b = self.bit(bid)
            if b is None:
                raise SettingsError(path, f"T{n} names bit {bid}, which is not in the table")
            if b.type in BIT_TYPES and b.type not in HEADS[n].allows:
                raise SettingsError(
                    path, f"T{n} takes {' or '.join(HEADS[n].allows)} bits, "
                          f"not the {b.type} bit {b.name}")

    def resolve(self, head: int, who: str, field: str, kind: str) -> Bit:
        """The bit an operation cuts with, or a HeadError naming the operation and the head."""
        def fail(message):
            raise HeadError(field, f"{who}: {message}")

        if head not in HEADS:
            fail(f"T{head} is not a machine head")
        allowed, rule = ((ROUTER_HEADS, "router uses T65 or T66") if kind == 'router'
                         else (DRILL_HEADS, "drills use T1 to T30"))
        if head not in allowed:
            if head in (53, 56, 60, 61):
                fail(f"head T{head}: programs do not use T{head}")
            fail(f"head T{head} cannot be used here; {rule}")
        b = self.bit_in(head)
        if b is None:
            fail(f"head T{head} holds no bit")
        if b.type != kind:
            fail(f"head T{head} holds {b.type} bit {b.name}; "
                 f"the {'router' if kind == 'router' else 'drill'} needs a {kind} bit")
        return b


# ---- Migration from the settings before the tool table ----

# Old per-group pocket override fields; they are not applied any more (the server words a line
# for each one found).
OBSOLETE_GROUP_FIELDS = ('diameter', 'depth_per_pass', 'plunge_feed', 'cut_feed', 'spindle_rpm',
                         'stepover_pct')

# The defaults of the settings before the tool table (old settings.py), used for any key a
# saved project does not have: (section, key) -> number. Do not import settings.py here.
_OLD_DEFAULTS = {
    'router': {'tool': 66, 'diameter': 8, 'spindle_rpm': 18000, 'plunge_feed': 1,
               'cut_feed': 3, 'depth_per_pass': 9},
    'pockets': {'tool': 66, 'diameter': 8, 'depth_per_pass': 4, 'plunge_feed': 1,
                'cut_feed': 3, 'spindle_rpm': 18000, 'stepover_pct': 40},
    'drill_fix': {'tool': 1, 'diameter': 6, 'feed': 1},
    'drill_screw': {'tool': 2, 'diameter': 3, 'feed': 1},
}

_FIELD_WORDS = {
    'diameter': ('diameter', 'mm'), 'depth_per_pass': ('depth per pass', 'mm'),
    'plunge_feed': ('plunge feed', 'm/min'), 'cut_feed': ('cut feed', 'm/min'),
    'spindle_rpm': ('spindle speed', 'rpm'), 'stepover_pct': ('stepover', '%'),
}


def _words(field_name: str, value) -> str:
    word, unit = _FIELD_WORDS[field_name]
    return f"{word} {value:g} {unit}"


def migrate(settings: dict, pockets):
    """Build a tool table from the raw settings dict and the raw pocket group overrides of a
    project saved before the tool table. Pure: no I/O.

    Returns (table, notes, ignored). Candidates are taken in the order router, pocket default,
    fixing drill, screw drill; one bit per head; the first candidate wins every number that
    differs and one note per head says what was taken and what was dropped. A candidate whose
    head cannot hold its kind of bit gets its bit created but not placed, and a note. `ignored`
    lists the old per-group override values as (group key, field, value)."""
    settings = settings if isinstance(settings, dict) else {}
    notes = []

    def value(section, key, what):
        raw = settings.get(section)
        raw = raw.get(key, _OLD_DEFAULTS[section][key]) if isinstance(raw, dict) \
            else _OLD_DEFAULTS[section][key]
        if key == 'tool':
            return raw
        if not _is_number(raw):
            default = _OLD_DEFAULTS[section][key]
            fname = 'plunge_feed' if key == 'feed' else key
            notes.append(f"The old {what} {_FIELD_WORDS[fname][0]} {raw!r} is not a number; "
                         f"the old default {default:g} {_FIELD_WORDS[fname][1]} was used.")
            return default
        return raw

    pocket_head = value('pockets', 'tool', "pocket default")
    router_head = value('router', 'tool', "router")
    candidates = []   # (who, kind, head, {bit field: value})
    r = {k: value('router', k, "router") for k in
         ('diameter', 'spindle_rpm', 'plunge_feed', 'cut_feed', 'depth_per_pass')}
    p = {k: value('pockets', k, "pocket default") for k in
         ('diameter', 'depth_per_pass', 'plunge_feed', 'cut_feed', 'spindle_rpm',
          'stepover_pct')}
    # The old router had no stepover: it takes the pocket default's only when they share a head.
    r['stepover_pct'] = p['stepover_pct'] if pocket_head == router_head \
        else _OLD_DEFAULTS['pockets']['stepover_pct']
    candidates.append(("router", 'router', router_head, r))
    candidates.append(("pocket default", 'router', pocket_head, p))
    for section, who in (('drill_fix', "fixing drill"), ('drill_screw', "screw drill")):
        candidates.append((who, 'drill', value(section, 'tool', who),
                           {'diameter': value(section, 'diameter', who),
                            'plunge_feed': value(section, 'feed', who)}))

    table = ToolTable()
    on_head = {}   # head -> (bit, taken fields of that bit's first candidate, who, dropped)
    for who, kind, head, nums in candidates:
        usable = isinstance(head, int) and not isinstance(head, bool) and head in HEADS \
            and kind in HEADS[head].allows
        if not usable:
            bit = _new_bit(table, kind, nums)
            table.bits.append(bit)
            if isinstance(head, int) and not isinstance(head, bool) and head in HEADS:
                reason = f"T{head} takes {' or '.join(HEADS[head].allows)} bits"
                shown = f"T{head}"
            else:
                shown = f"T{head}" if isinstance(head, int) else repr(head)
                reason = f"{shown} is not a machine head"
            notes.append(f"The {who}'s head {shown} cannot hold a {kind} bit ({reason}), so "
                         f"its bit {bit.name} was created but not placed in any head; pick a "
                         f"head for it.")
            continue
        if head not in on_head:
            bit = _new_bit(table, kind, nums)
            table.bits.append(bit)
            table.heads[head] = bit.id
            on_head[head] = [bit, who, nums, {}]
            continue
        bit, first_who, first, dropped = on_head[head]
        for k, v in nums.items():
            if k in first and first[k] != v and k in _FIELD_WORDS:
                dropped.setdefault(who, []).append((k, _words(k, v)))
    for head, (bit, first_who, first, dropped) in on_head.items():
        if not dropped:
            continue
        differing = []
        for _, items in dropped.items():
            for k, _text in items:
                if k not in differing:
                    differing.append(k)
        taken = ", ".join(_words(k, first[k]) for k in differing)
        lost = "; ".join(f"the {w}'s " + ", ".join(t for _k, t in items)
                         for w, items in dropped.items())
        notes.append(f"T{head} was used by more than one setting with different numbers, so "
                     f"it holds one bit, {bit.name}. Taken from the {first_who}: {taken}. "
                     f"Dropped: {lost}.")

    ignored = []
    if isinstance(pockets, dict):
        for key, over in pockets.items():
            if isinstance(over, dict):
                ignored.extend((key, f, over[f]) for f in OBSOLETE_GROUP_FIELDS if f in over)
    return table, notes, ignored


def _new_bit(table: ToolTable, kind: str, nums: dict) -> Bit:
    d = nums['diameter']
    if kind == 'router':
        return Bit(table.new_id(), f"Router {d:g}", 'router', d,
                   spindle_rpm=nums['spindle_rpm'], plunge_feed=nums['plunge_feed'],
                   cut_feed=nums['cut_feed'], depth_per_pass=nums['depth_per_pass'],
                   stepover_pct=nums['stepover_pct'])
    return Bit(table.new_id(), f"Drill {d:g}", 'drill', d, plunge_feed=nums['plunge_feed'])
