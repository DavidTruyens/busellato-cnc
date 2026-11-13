"""CNC90 (TPA, SORG\\SRG) source writer. Format: docs/superpowers/specs/2026-09-25-fusion-post-design.md."""
from __future__ import annotations

from ..geometry import Arc
from ..program import ContourOp, DrillOp, Program, ProgramError
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


def _contour(op: ContourOp, program: Program, tool: str, origin: str) -> list[str]:
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
            code = 'G3' if seg.ccw else 'G2'
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
            body += _contour(op, program, tool, origin)
    body.append('M2')
    n = len(body) + 1
    x, y, z = program.stock
    lines = [f'G71X{fmt(x)}Y{fmt(y)}Z{fmt(z)}T00N{n}L{n - 3}'] + body
    return ''.join(line.upper() + '\r\n' for line in lines)
