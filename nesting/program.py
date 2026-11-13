"""Turn a layout plan into CNC programs: drill and cut operations with Z depths, per blank.

The machine runs one blank at a time. Two frames exist for a blank:

- the layout frame (layout.py, dxf.py): origin at the blank's lower-left corner as drawn, y up;
- the program frame, what the machine gets: X0 Y0 at the blank's corner against the pins, X along
  the long side. With `machine.y_toward` 'front' (default) the origin is the blank's back-left
  corner (top left of the picture, operator at the bottom) and Y grows toward the front:
  Y_prog = blank height - y. With 'back' the program frame is the layout frame.

`to_program` / `segs_to_program` are the only place that mapping is made. The contour direction
setting is the turning sense seen from above in that picture; it is applied in the layout frame
(y up, so it is the ordinary mathematical sense there) and the mirror then flips the arcs'
G2/G3 sense in the program numbers. The stack on the cups is scrap + blank; depths are measured
down from the top of the stack. No G-code text is written here.

Per blank: B<nn>D (every hole), B<nn>P (the pockets, when the blank's shapes have any that are
switched on) and B<nn>C (the shape outlines), run in that order.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .dxf import Shape, _inside
from .geometry import (Arc, Line, OffsetError, Pt, Seg, bbox, distance_to_chain, mirror_y,
                       offset_outline, sample, set_direction, split_large_arcs, translate)
from .layout import Blank, Plan
from .pockets import (PocketError, PocketGroup, effective, find_groups, group_for,
                      memo_pocket_rings)
from .settings import Settings

LINE_WARNING = 250
KINDS = ('D', 'P', 'C')         # drill (fixing + screw holes, any tools), pockets, cut
NAME = re.compile(r'[A-Z0-9_-]{1,8}')


@dataclass
class DrillOp:
    x: float
    y: float
    depth: float
    diameter: float
    tool: int | None = None         # this hole's tool; None = the program's tool


@dataclass
class ContourOp:
    segs: list[Seg]
    depth: float
    label: str
    # a pocket op's own tool, spindle speed and feeds; None = the program's
    tool: int | None = None
    spindle_rpm: int | None = None
    plunge_feed: float | None = None
    cut_feed: float | None = None


@dataclass
class Program:
    name: str
    tool: int
    kind: str                       # 'drill', 'pocket' or 'cut'
    description: str
    stock: tuple[float, float, float]
    ops: list = field(default_factory=list)
    spindle_rpm: int | None = None
    plunge_feed: float = 0.0
    cut_feed: float = 0.0
    warnings: list[str] = field(default_factory=list)
    blank: str = ''                 # id of the blank this program is for

    def op_tool(self, op) -> int:
        """The tool an op runs with: a drill or pocket op may carry its own, else the
        program's."""
        t = getattr(op, 'tool', None)
        return self.tool if t is None else t

    @property
    def tools(self) -> list[int]:
        """Every tool the program uses, in the order it first uses them. `tool` is the first
        one (a drill program may mix tools: every G81 line names its own)."""
        out: list[int] = []
        for op in self.ops:
            t = self.op_tool(op)
            if t not in out:
                out.append(t)
        return out or [self.tool]


class ProgramError(ValueError):
    """A program would be unsafe to run (for example a depth into the vacuum cups)."""


def check_depths(p: Program) -> None:
    """Raise ProgramError when an op reaches the top of the cups: depth >= stack top (stock Z)."""
    top = p.stock[2]
    for op in p.ops:
        if op.depth >= top:
            what = (f'contour {op.label}' if isinstance(op, ContourOp)
                    else f'drill at X{op.x:.3f} Y{op.y:.3f}')
            raise ProgramError(f'{p.name}: {what} goes to depth {op.depth:.3f}, at or below '
                               f'the top of the vacuum cups (stack height {top:.3f}); '
                               f'nothing is generated')


def stack_top(settings: Settings) -> float:
    """Scrap plate + blank: the stock Z of every program."""
    return settings.stack


def pass_count(total: float, per_pass: float) -> int:
    return max(1, math.ceil(total / per_pass - 1e-9))


def pass_depths(total: float, per_pass: float) -> list[float]:
    """Cumulative depth of each pass: equal steps down to `total`."""
    n = pass_count(total, per_pass)
    return [total * (i + 1) / n for i in range(n)]


def y_flipped(settings: Settings) -> bool:
    """True when program Y runs opposite to layout y (machine.y_toward 'front')."""
    return settings.machine.y_toward == 'front'


def to_program(blank: Blank, settings: Settings, x: float, y: float) -> Pt:
    """Layout-frame point of a blank -> program frame. Its own inverse."""
    return (x, blank.height - y) if y_flipped(settings) else (x, y)


def segs_to_program(blank: Blank, settings: Settings, segs: list[Seg]) -> list[Seg]:
    """Layout-frame segments of a blank -> program frame (arcs flip ccw when mirrored)."""
    return mirror_y(segs, blank.height) if y_flipped(settings) else list(segs)


def _contour(segs: list[Seg], settings: Settings) -> list[Seg]:
    """Tool-centre path of a layout-frame outline, still in the layout frame. The direction
    setting is the sense seen from above, which is the mathematical sense in the y-up layout
    frame; the offset is outward there."""
    ccw = settings.router.direction == 'ccw'
    out = offset_outline(set_direction(segs, ccw), settings.router_bit.diameter / 2,
                         outward=True)
    return split_large_arcs(set_direction(out, ccw))


def program_name(blank_id: str, kind: str) -> str:
    """B<nn><D|P|C> (drill, pockets, cut): the first character B is the machine folder
    SRG\\B."""
    return f'{blank_id}{kind}'


def group_by_tool(ops: list[DrillOp]) -> list[DrillOp]:
    """Drill ops with each tool's holes together, tools in the order they first appear; a
    stable sort, so the order within a tool (fixing holes before screw holes) is kept."""
    first: dict = {}
    for o in ops:
        first.setdefault(o.tool, len(first))
    return sorted(ops, key=lambda o: first[o.tool])


def _outside_blank(p: Program, blank: Blank, r: float) -> str | None:
    """A warning when the cutter edge (tool centre path widened by the radius r) leaves the
    blank."""
    segs = [s for op in p.ops if isinstance(op, ContourOp) for s in op.segs]
    if not segs:
        return None
    x0, y0, x1, y1 = bbox(segs)
    x0, y0, x1, y1 = x0 - r, y0 - r, x1 + r, y1 + r
    eps = 1e-6
    if x0 >= -eps and y0 >= -eps and x1 <= blank.width + eps and y1 <= blank.height + eps:
        return None
    return (f'{p.name}: cutter reaches X{x0:.1f}..{x1:.1f}, Y{y0:.1f}..{y1:.1f}, '
            f'outside the blank 0..{blank.width:g} x 0..{blank.height:g}')


def _finish(p: Program, blank: Blank, settings: Settings, radius: float | None = None) -> Program:
    """Depth check (hard), cutter-outside-blank and line-count warnings. `radius` is the
    largest cutter radius of the program's contours (default: the outline router's)."""
    check_depths(p)
    r = settings.router_bit.diameter / 2 if radius is None else radius
    outside = _outside_blank(p, blank, r)
    if outside:
        p.warnings.append(outside)
    from .backends import BACKENDS      # late: the backends import this module
    lines = len(BACKENDS['cnc90'](p, settings).splitlines())
    if lines > LINE_WARNING:
        p.warnings.append(f'{p.name}: about {lines} lines, over {LINE_WARNING}')
    return p


def base_label(label: str) -> str:
    """A contour label without its ' pass k/n' suffix."""
    return re.sub(r' pass \d+/\d+$', '', label)


def _pass_ops(segs: list[Seg], label: str, start: float, material: float,
              settings: Settings) -> list[ContourOp]:
    """One ContourOp per pass; passes are counted over the material only."""
    n = pass_count(material, settings.router_bit.depth_per_pass)
    return [ContourOp(segs, start + material * k / n, f'{label} pass {k}/{n}')
            for k in range(1, n + 1)]


# --- pockets --------------------------------------------------------------------

def plan_shapes(plan: Plan) -> list[Shape]:
    """Every shape placed in the plan, once (copies share one Shape)."""
    seen: dict[int, Shape] = {}
    for b in plan.blanks:
        for ps in b.shapes:
            seen.setdefault(id(ps.shape), ps.shape)
    return list(seen.values())


def _clean_ring(ring: list[Seg]) -> list[Seg]:
    """The ring without zero-length lines; a ring made only of them (a round pocket exactly
    the tool diameter) stays one zero-length line: a plunge with no horizontal move."""
    out = [s for s in ring if isinstance(s, Arc) or s.a != s.b]
    return out or [Line(ring[0].a, ring[0].a)]


def _has_winding(ring: list[Seg]) -> bool:
    """False for a ring of lines only that encloses no area (a slot's centre line traversed
    out and back, or a point): it has no turning sense to set."""
    if any(isinstance(s, Arc) for s in ring):
        return True
    area = 0.5 * sum(s.a[0] * s.b[1] - s.b[0] * s.a[1] for s in ring)
    return abs(area) > 1e-6


def _gap(a: list[Seg], b: list[Seg]) -> float:
    """Shortest distance between two closed chains, to within the 0.5 mm sampling step."""
    return min(min(distance_to_chain(p, b) for p in sample(a, 0.5)),
               min(distance_to_chain(p, a) for p in sample(b, 0.5)))


def _boxes_near(a: list[Seg], b: list[Seg], d: float) -> bool:
    ax0, ay0, ax1, ay1 = bbox(a)
    bx0, by0, bx1, by1 = bbox(b)
    return ax0 - d <= bx1 and bx0 - d <= ax1 and ay0 - d <= by1 and by0 - d <= ay1


def _hole_warnings(name: str, blank: Blank, settings: Settings, label: str,
                   outline: list[Seg]) -> list[str]:
    """A warning per screw or fixing hole whose centre is inside the pocket (layout-frame
    outline) or closer than the screw-head clearance (head_dia / 2 + 3) to its edge."""
    clear = settings.blank.head_dia / 2 + 3.0
    poly = sample(outline, 0.5)
    out = []
    for what, holes in (('fixing hole', blank.fix_holes), ('screw hole', blank.screw_holes)):
        for h in holes:
            d = distance_to_chain((h.x, h.y), outline)
            inside = _inside(poly, h.x, h.y)
            if inside or d < clear:
                x, y = to_program(blank, settings, h.x, h.y)
                where = 'inside the pocket' if inside else f'{d:.1f} mm from the pocket edge'
                out.append(f'{name}: {label}: {what} at X{x:.1f} Y{y:.1f} is {where}, closer '
                           f'than the screw-head clearance {clear:g} mm')
    return out


def _pocket_program(blank: Blank, settings: Settings, overrides: dict,
                    groups: list[PocketGroup],
                    rings_of: dict) -> tuple[Program, float] | None:
    """B<nn>P and its largest cutter radius, or None when the blank has no pocket to cut.

    Order: groups by tool (first appearance, stable), within a group for each depth pass every
    pocket of the blank (shape order, then pocket order), for each pocket its rings innermost
    first, the wall ring last. Depths are from the top face of the blank, the top of the stack.
    """
    name = program_name(blank.id, 'P')
    thick, floor = settings.panel.thickness, settings.pockets.min_floor
    ccw_of = {'cw': False, 'ccw': True}
    # (group, settings, [(placed shape, pocket number, pocket)]) in group order
    found: dict[str, tuple] = {}
    for ps in blank.shapes:
        for i, pk in enumerate(ps.shape.pockets, 1):
            g = group_for(pk, groups)
            if g is None:
                raise ProgramError(f'{blank.id} {ps.name}: pocket {i} has no pocket group '
                                   f'(internal error: groups not computed over this shape)')
            if g.id not in found:
                try:
                    gs = effective(g.key, overrides, settings.pockets)
                except ValueError as e:
                    raise ValueError(f'pocket group {g.id}: {e}') from e
                found[g.id] = (g, gs, [])
            found[g.id][2].append((ps, i, pk))
    order = {g.id: n for n, g in enumerate(groups)}
    todo = sorted((v for v in found.values() if v[1].enabled), key=lambda v: order[v[0].id])
    first_tool: dict[int, int] = {}
    for g, gs, _ in todo:
        first_tool.setdefault(gs.tool, len(first_tool))
    todo.sort(key=lambda v: first_tool[v[1].tool])      # stable: group order within a tool

    ops: list[ContourOp] = []
    warnings: list[str] = []
    placed: list[tuple[str, list[Seg], float]] = []     # (label, layout outline, tool diameter)
    radius = 0.0
    for g, gs, pockets in todo:
        ps0 = pockets[0][0]
        if gs.depth > thick - floor:
            raise ProgramError(f'{blank.id} {ps0.name} {g.id}: pocket depth {gs.depth:g} mm '
                               f'leaves less than the minimum floor {floor:g} mm of the '
                               f'{thick:g} mm blank (deepest allowed {thick - floor:g} mm)')
        # pocket_rings is slow on long pockets: computed once per group, tool diameter and
        # stepover (rings_of is shared by the blanks of a plan; memo_pocket_rings also
        # remembers them between plans). The group's pockets match its
        # representative within 0.05 mm in their own shape's frame, so the representative's
        # rings, moved to each placed shape, serve every pocket of the group.
        key = (g.key, g.id, gs.diameter, gs.stepover_pct)
        if key not in rings_of:
            try:
                rings_of[key] = memo_pocket_rings(g.representative.outline, gs.diameter,
                                                  gs.stepover_pct)
            except PocketError as e:
                raise PocketError(f'{blank.id} {ps0.name} {g.id} ({g.width:g} x {g.height:g} '
                                  f'pocket): {e}') from e
        rings = [_clean_ring(r) for r in rings_of[key]]
        radius = max(radius, gs.diameter / 2)
        ccw = ccw_of[gs.direction]
        moved = []
        for ps, i, pk in pockets:
            label = f'{blank.id} {ps.name} #{ps.copy} {g.id} pocket {i}'
            outline = translate(pk.outline, ps.x, ps.y)
            warnings += _hole_warnings(name, blank, settings, label, outline)
            placed.append((label, outline, gs.diameter))
            segs = []
            for r in rings:
                lay = translate(r, ps.x, ps.y)
                if _has_winding(lay):
                    lay = split_large_arcs(set_direction(lay, ccw))
                segs.append(segs_to_program(blank, settings, lay))
            moved.append((label, segs))
        depths = pass_depths(gs.depth, gs.depth_per_pass)
        n, m = len(depths), len(rings)
        for k, depth in enumerate(depths, 1):
            for label, segs in moved:
                for j, s in enumerate(segs, 1):
                    ops.append(ContourOp(s, depth, f'{label} pass {k}/{n} ring {j}/{m}',
                                         gs.tool, int(gs.spindle_rpm), gs.plunge_feed,
                                         gs.cut_feed))
    for i, (la, a, da) in enumerate(placed):
        for lb, b, db in placed[i + 1:]:
            d = max(da, db)
            if _boxes_near(a, b, d) and (gap := _gap(a, b)) < d:
                warnings.append(f'{name}: {la} and {lb} are only {gap:.1f} mm apart, less than '
                                f'the tool diameter {d:g} mm')
    if not ops:
        return None
    o = ops[0]
    top = stack_top(settings)
    p = Program(name, o.tool, 'pocket', 'Pockets', (blank.width, blank.height, top), ops,
                o.spindle_rpm, o.plunge_feed, o.cut_feed, warnings, blank.id)
    return p, radius


def blank_programs(blank: Blank, settings: Settings, pocket_overrides: dict | None = None,
                   groups: list[PocketGroup] | None = None,
                   _rings: dict | None = None) -> list[Program]:
    """Drill, pocket and cut programs of one blank, in the program frame (see the module doc).

    pocket_overrides: per pocket group key, the settings that differ from settings.pockets.
    groups: the plan's or the project's pocket groups (plan_programs passes them, so a group
    has one id and key over the whole plan); None computes them from this blank's shapes alone.
    _rings: a cache of pocket rings that plan_programs shares between the blanks.
    """
    h, r, rbit = settings.heights, settings.router, settings.router_bit
    fix, screw = settings.drill_fix, settings.drill_screw
    fix_bit, screw_bit = settings.fix_bit, settings.screw_bit
    thick = settings.panel.thickness
    top = stack_top(settings)
    stock = (blank.width, blank.height, top)

    fix_depth = thick + h.fix_into_scrap          # through the blank, into the scrap
    screw_depth = thick + screw.depth
    def drill_op(o, depth, d, bit):
        return DrillOp(*to_program(blank, settings, o.x, o.y), depth, bit.diameter, d.tool)

    fix_ops = [drill_op(o, fix_depth, fix, fix_bit) for o in blank.fix_holes]
    screw_ops = [drill_op(o, screw_depth, screw, screw_bit) for o in blank.screw_holes]
    cuts: list[ContourOp] = []
    for ps in blank.shapes:
        label = f'{blank.id} {ps.name} #{ps.copy}'
        try:
            segs = _contour(translate(ps.shape.outline, ps.x, ps.y), settings)
        except OffsetError as e:
            raise OffsetError(f'{label}: {e}') from e
        segs = segs_to_program(blank, settings, segs)
        # through the blank from its top, just into the scrap
        cuts += _pass_ops(segs, label, 0.0, thick + h.into_scrap, settings)

    if groups is None:
        groups = find_groups(list({id(ps.shape): ps.shape for ps in blank.shapes}.values()))
    pocket = _pocket_program(blank, settings, pocket_overrides or {}, groups,
                             {} if _rings is None else _rings)

    progs: list[Program] = []
    radius: dict[str, float] = {}
    drills = group_by_tool(fix_ops + screw_ops)
    if drills:
        desc = ' and '.join(w for w, ops in (('Fixing', fix_ops), ('screw', screw_ops)) if ops)
        desc = desc[0].upper() + desc[1:] + ' holes'
        # one program for every hole of the blank, whatever the tools: each G81 line names its
        # own tool, like many of the machine's own programs. Feeds are not written (the
        # control uses each tool's own feed); plunge/cut feed only fill the record.
        progs.append(Program(program_name(blank.id, 'D'), drills[0].tool, 'drill', desc, stock,
                             drills, None, fix_bit.plunge_feed, fix_bit.plunge_feed,
                             blank=blank.id))
    if pocket:
        progs.append(pocket[0])
        radius[pocket[0].name] = pocket[1]
    if cuts:
        progs.append(Program(program_name(blank.id, 'C'), r.tool, 'cut', 'Shape outlines',
                             stock, cuts, int(rbit.spindle_rpm), rbit.plunge_feed,
                             rbit.cut_feed, blank=blank.id))
    return [_finish(p, blank, settings, radius.get(p.name)) for p in progs]


def tool_diameter_conflict(settings: Settings, overrides: dict, groups: list[PocketGroup],
                           shapes: list[Shape]) -> tuple[str, str] | None:
    """(message, settings field) when one tool number is given two diameters, else None.

    A physical tool has one diameter: the router, both drills and every switched-on pocket
    group that has a pocket on `shapes` (with its effective tool and diameter, so the pocket
    defaults count only when a group uses them) must agree. The field is the one to fix: the
    second user's diameter (a group's own, or the pocket default when the group has no tool or
    diameter of its own). A bad override raises ValueError naming the group.
    """
    users: list[tuple[int, float, str, str]] = [
        (settings.router.tool, settings.router_bit.diameter, 'router', 'router.tool'),
        (settings.drill_fix.tool, settings.fix_bit.diameter, 'fixing drill', 'drill_fix.tool'),
        (settings.drill_screw.tool, settings.screw_bit.diameter, 'screw drill',
         'drill_screw.tool')]
    used = {g.id for sh in shapes for pk in sh.pockets if (g := group_for(pk, groups))}
    for g in groups:
        if g.id not in used:
            continue
        try:
            gs = effective(g.key, overrides, settings.pockets)
        except ValueError as e:
            raise ValueError(f'pocket group {g.id}: {e}') from e
        if not gs.enabled:
            continue
        own = overrides.get(g.key) or {}
        field = (f'pockets.{g.id}.diameter' if 'tool' in own or 'diameter' in own
                 else 'pockets.diameter')
        users.append((gs.tool, gs.diameter, f'pocket group {g.id}', field))
    first: dict[int, tuple[float, str]] = {}
    for tool, dia, who, field in users:
        if tool not in first:
            first[tool] = (dia, who)
            continue
        dia0, who0 = first[tool]
        if abs(dia - dia0) > 1e-9:
            return (f'tool T{tool} is used with diameters {dia0:g} and {dia:g} mm ({who0}, '
                    f'{who}); one tool number must have one diameter', field)
    return None


def plan_programs(plan: Plan, settings: Settings,
                  pocket_overrides: dict | None = None,
                  groups: list[PocketGroup] | None = None) -> list[Program]:
    """Every blank's programs. groups: the project's pocket groups (ids and colours over
    every shape of the project, switched off too, so they do not change when a shape is
    switched off); None finds them once over every shape of the plan. One tool number with
    two diameters (tool_diameter_conflict) is a ProgramError: nothing is planned."""
    shapes = plan_shapes(plan)
    if groups is None:
        groups = find_groups(shapes)
    conflict = tool_diameter_conflict(settings, pocket_overrides or {}, groups, shapes)
    if conflict:
        raise ProgramError(conflict[0])
    rings: dict = {}
    progs = [p for b in plan.blanks
             for p in blank_programs(b, settings, pocket_overrides, groups, rings)]
    names = [p.name for p in progs]
    if len(names) != len(set(names)):       # cannot happen with unique blank ids
        raise ProgramError('two programs would get the same name')
    for name in names:
        if not NAME.fullmatch(name):
            raise ProgramError(f'{name}: not a valid program name (1-8 characters A-Z 0-9 _ -)')
    return progs
