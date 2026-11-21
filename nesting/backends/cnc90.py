"""CNC90 (TPA, SORG\\SRG) source writer. Format: docs/superpowers/specs/2026-09-25-fusion-post-design.md."""
from __future__ import annotations

from ..geometry import Arc
from ..program import ContourOp, DrillOp, Program, ProgramError, y_flipped
from ..settings import Settings


def fmt(v: float) -> str:
    """Up to 3 decimals, trailing zeros and a trailing dot removed."""
    s = f'{round(v, 3):.3f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def _xy(p) -> str:
    return f'X{fmt(p[0])}Y{fmt(p[1])}'


def _own(op: ContourOp, program: Program, name: str):
    """The op's own spindle speed or feed when it carries one (pocket ops), else the program's."""
    v = getattr(op, name)
    return getattr(program, name) if v is None else v


def _contour(op: ContourOp, program: Program, tool: str, origin: str,
             flipped: bool = False) -> list[str]:
    z = f'Z{fmt(op.depth)}'
    start = op.segs[0].a
    plunge, cut = _own(op, program, 'plunge_feed'), _own(op, program, 'cut_feed')
    out = [f'G88G90{origin}P5{tool}S{int(_own(op, program, "spindle_rpm"))}'
           f'F{fmt(plunge)}{_xy(start)}{z}']
    feed = plunge
    first = True
    for seg in op.segs:
        f = ''
        if first and cut != feed:
            if isinstance(seg, Arc):
                out.append(f'G1G90F{fmt(cut)}{_xy(start)}{z}')
            else:
                f = f'F{fmt(cut)}'
            feed = cut
        first = False
        if isinstance(seg, Arc):
            # G2 = clockwise, G3 = counter-clockwise as seen from above on the machine, not
            # in the program's numbers: with Y toward the front (numbers mirrored) the sense
            # of the numbers is the opposite one. Seen 2026-11-20 on the first cut: with the
            # code taken from the numbers every arc bulged to the wrong side.
            code = 'G3' if seg.ccw != flipped else 'G2'
            u = fmt(seg.radius)
            if u == '0':        # the control would get an arc of radius 0
                raise ProgramError(f'{program.name}: {op.label}: arc of radius {seg.radius:.6f} '
                                   f'mm would be written as U0; nothing is generated')
            out.append(f'{code}G90G17{_xy(seg.b)}U{u}')
        else:
            out.append(f'G1G90{f}{_xy(seg.b)}{z}')
    return out


def emit(program: Program, settings: Settings) -> str:
    origin = settings.origin
    body: list[str] = ['G150()']
    for op in program.ops:
        tool = f'T01{program.op_tool(op):02d}'      # every block names its own tool
        if isinstance(op, DrillOp):
            body.append(f'G81G90{origin}P5{tool}{_xy((op.x, op.y))}Z{fmt(op.depth)}')
        else:
            body += _contour(op, program, tool, origin, y_flipped(settings))
    lift = settings.router.end_lift
    if lift and program.ops and isinstance(program.ops[-1], ContourOp):
        # straight up from the last point to above the blank before M2 (the machine's own
        # programs use a negative Z for above the top too)
        body.append(f'G1G90{_xy(program.ops[-1].segs[-1].b)}Z{fmt(-lift)}')
    body.append('M2')
    n = len(body) + 1
    x, y, z = program.stock
    lines = [f'G71X{fmt(x)}Y{fmt(y)}Z{fmt(z)}T00N{n}L{n - 3}'] + body
    return ''.join(line.upper() + '\r\n' for line in lines)
