"""Write the job folder: program files, loader batch files, PROJECT.json and the printable run sheet."""
from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path

from .backends import BACKENDS
from .importdisk import NAME as DISKETTE, write_diskette
from .layout import Plan
from .preview import preview_data
from .program import Program, pass_count
from .settings import Settings

LOADER = Path(__file__).resolve().parent.parent / 'tools' / 'make-loader.py'

Z_LABELS = [('stack_top', 'Stack height (scrap plate + blank, above the cups)'),
            ('fixing', 'Fixing holes: drill depth below the top of the stack'),
            ('screw', 'Screw holes: drill depth below the top of the stack'),
            ('shape_cut', 'Shapes: cut depth below the top of the stack')]

CSS = """body{font-family:Arial,sans-serif;margin:12mm;color:#000}
h1{font-size:18pt;margin:0 0 4mm}h2{font-size:14pt;margin:0 0 3mm}h3{font-size:12pt;margin:4mm 0 2mm}
.warn{border:2px solid #b00;padding:3mm;margin:0 0 6mm;font-weight:bold}
section{page-break-after:always;margin-bottom:10mm}
svg{width:100%;height:auto;border:1px solid #000;background:#fff}
.blank{fill:#eef;stroke:#339;stroke-width:2}.shape{fill:#fd9;stroke:#640;stroke-width:1.5}.pocket{fill-opacity:.35;stroke-width:1.5}
.sw{display:inline-block;width:5mm;height:5mm;border:1px solid #000;vertical-align:middle}
.kerf{fill:#c00}.cutn{font-size:40px;font-weight:bold;fill:#c00}.org{fill:#000}
.fix{fill:none;stroke:#c00;stroke-width:2}.screw{fill:none;stroke:#060;stroke-width:2}
.lbl{font-size:28px;text-anchor:middle;fill:#000}.bid{font-size:40px;fill:#339;font-weight:bold}
ol li{margin:1.5mm 0}table{border-collapse:collapse;margin:2mm 0}td,th{border:1px solid #000;padding:1mm 3mm;text-align:left}
td.num{text-align:right}
@media print{body{margin:8mm}}"""

AXIS = {'x': 'along the length (X)', 'y': 'along the width (Y)'}
FREES = {'offcut': 'offcut (trim)', 'strip': 'strip', 'rough': 'blank, still to trim',
         'blank': 'blank'}


def _g(v: float) -> str:
    return f'{round(v, 1):g}' if isinstance(v, (int, float)) else str(v)


def _panel_svg(data: dict, panel: dict) -> str:
    L, W = data['panel']['length'], data['panel']['width']
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_g(L)} {_g(W)}">',
           f'<rect x="0" y="0" width="{_g(L)}" height="{_g(W)}" fill="none" stroke="#000" stroke-width="3"/>',
           f'<circle class="org" cx="0" cy="{_g(W)}" r="14"/>']
    for b in panel['blanks']:
        out.append(f'<rect class="blank" x="{_g(b["x"])}" y="{_g(b["y"])}" width="{_g(b["w"])}" '
                   f'height="{_g(b["h"])}"/>')
        for s in b['shapes']:
            out.append(f'<path class="shape" d="{escape(s["path"])}"/>')
        out.append(f'<text class="bid" x="{_g(b["x"] + b["w"] / 2)}" y="{_g(b["y"] + b["h"] / 2 + 14)}" '
                   f'text-anchor="middle">{escape(b["id"])}</text>')
    for c in panel['cuts']:
        x, y, w, h = c['rect']
        out.append(f'<rect class="kerf" x="{_g(x)}" y="{_g(y)}" width="{_g(w)}" height="{_g(h)}"/>')
        out.append(f'<text class="cutn" x="{_g(x + 8)}" y="{_g(y + 40 if c["axis"] == "y" else y - 6)}">{c["n"]}</text>')
    out.append('</svg>')
    return '\n'.join(out)


ORIGIN = {
    'front': ('X0 Y0 is the blank\'s back-left corner (top left in the drawing, black dot), '
              'against the X and Y pins; X grows to the right, Y grows toward the front '
              '(down in the drawing)'),
    'back': ('X0 Y0 is the blank\'s front-left corner (bottom left in the drawing, black dot), '
             'against the X and Y pins; X grows to the right, Y grows toward the back '
             '(up in the drawing)'),
}


def _blank_svg(b: dict, y_toward: str, cut_groups: set[str] = frozenset()) -> str:
    """The blank as seen from above, operator at the bottom; numbers from preview_data, which
    already holds the program frame drawn for SVG (y down)."""
    L, W = b['width'], b['height']
    oy = 0 if y_toward == 'front' else W
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-20 -20 {_g(L + 40)} {_g(W + 40)}">',
           f'<rect class="blank" x="0" y="0" width="{_g(L)}" height="{_g(W)}"/>',
           f'<circle class="org" cx="0" cy="{_g(oy)}" r="12"/>']
    for s in b['shapes']:
        out.append(f'<path class="shape" d="{escape(s["path"])}"/>')
        for pk in s.get('pockets', []):
            if pk['group'] in cut_groups:
                c = escape(pk['color'])
                out.append(f'<path class="pocket" fill="{c}" stroke="{c}" d="{escape(pk["path"])}"/>')
        out.append(f'<text class="lbl" x="{_g(s["cx"])}" y="{_g(s["cy"])}">{escape(s["name"])}</text>')
    for h in b['fix']:
        out.append(f'<circle class="fix" cx="{_g(h["x"])}" cy="{_g(h["y"])}" r="8"/>')
    for h in b['screw']:
        out.append(f'<circle class="screw" cx="{_g(h["x"])}" cy="{_g(h["y"])}" r="5"/>')
    out.append('</svg>')
    return '\n'.join(out)


def _cut_table(panel: dict) -> str:
    rows = ['<table><tr><th>Cut</th><th>Stage</th><th>Runs</th><th>At (mm from the origin corner)</th>'
            '<th>From .. to (mm)</th><th>Frees</th><th>Piece size (X x Y, mm)</th></tr>']
    for c in panel['cuts']:
        across = 'Y' if c['axis'] == 'x' else 'X'
        what = FREES[c['frees']] + (' ' + ', '.join(c['blanks']) if c['blanks'] else '')
        size = f'{_g(c["size"][0])} x {_g(c["size"][1])}' if c['size'] else ''
        rows.append(f'<tr><td class="num">{c["n"]}</td><td class="num">{c["stage"]}</td>'
                    f'<td>{AXIS[c["axis"]]}</td><td>{across} = {_g(c["at"])}</td>'
                    f'<td>{_g(c["start"])} .. {_g(c["end"])}</td><td>{escape(what)}</td>'
                    f'<td>{size}</td></tr>')
    rows.append('</table>')
    return ''.join(rows)


def _steps(bid: str, names: set[str], y_toward: str) -> list[str]:
    d, pk, c = f'{bid}D', f'{bid}P', f'{bid}C'
    corner = 'back-left' if y_toward == 'front' else 'front-left'
    steps = [f'Lay blank <b>{escape(bid)}</b> on the scrap plate, its origin corner (black dot, '
             f'the {corner} corner) against the X and Y pins, long side along machine X. '
             'Clamp it.']
    if d in names:
        steps.append(f'Run <b>{escape(d)}</b>, the blank still clamped: every hole of the blank '
                     '(fixing holes through the blank into the scrap, screw holes at the '
                     'shapes\' holes), each with its own tool.')
        steps.append('Screw the blank to the scrap plate through the fixing holes, and each shape '
                     'down through its screw holes.')
    steps.append('Take the clamps off.')
    if pk in names:
        steps.append(f'Run <b>{escape(pk)}</b> (cuts the pockets into the shapes, from the top '
                     'face of the blank).')
    if c in names:
        steps.append(f'Run <b>{escape(c)}</b> (cuts the shape outlines out of the blank; the '
                     'blank\'s frame is not cut).')
    steps.append('Unscrew the shapes and the frame; the frame is left over. Next blank.')
    return steps


def _pocket_table(b: dict, groups: dict) -> str:
    """The pocket groups cut on this blank (empty string when none)."""
    seen: dict[str, int] = {}
    for s in b['shapes']:
        for pk in s.get('pockets', []):
            if groups.get(pk['group'], {}).get('enabled'):
                seen[pk['group']] = seen.get(pk['group'], 0) + 1
    if not seen:
        return ''
    rows = ['<p><b>Pockets</b></p><table><tr><th>Group</th><th>Colour</th><th>Size (mm)</th>'
            '<th>Pockets</th><th>Tool</th><th>Tool Ø (mm)</th><th>Depth (mm)</th><th>Passes</th>'
            '</tr>']
    for gid, n in seen.items():
        g = groups[gid]
        rows.append(f'<tr><td>{escape(gid)}</td>'
                    f'<td><span class="sw" style="background:{escape(g["color"])}"></span></td>'
                    f'<td>{_g(g["width"])} x {_g(g["height"])}</td><td class="num">{n}</td>'
                    f'<td>T{g["tool"]}</td><td class="num">{round(g["diameter"], 3):g}</td>'
                    f'<td class="num">{round(g["depth"], 3):g}</td>'
                    f'<td class="num">{pass_count(g["depth"], g["depth_per_pass"])}</td></tr>')
    rows.append('</table>')
    return ''.join(rows)


def _tools(p: dict) -> str:
    return ', '.join(f'T{t}' for t in p.get('tools') or [p['tool']])


def _drill_table(b: dict) -> str:
    if not b.get('drill_tools'):
        return ''
    rows = ['<p><b>Drill tools</b> (diameter and feed are the settings, not written to the '
            'program: the control uses each tool\'s own feed; check the tool really has that '
            'diameter)</p><table><tr><th>Holes</th><th>Count</th><th>Tool</th>'
            '<th>Diameter (mm)</th><th>Feed (m/min, not written)</th><th>Depth (mm)</th></tr>']
    for t in b['drill_tools']:
        rows.append(f'<tr><td>{escape(t["holes"])}</td><td class="num">{t["count"]}</td>'
                    f'<td>T{t["tool"]}</td><td class="num">{t["diameter"]:g}</td>'
                    f'<td class="num">{t["feed"]:g}</td><td class="num">{round(t["depth"], 3):g}</td></tr>')
    rows.append('</table>')
    return ''.join(rows)


def _runsheet(data: dict, project: dict) -> str:
    title = str(project.get('name') or 'Run sheet')
    fr = data['frame']
    parts = ['<!DOCTYPE html>', '<html lang="en"><head><meta charset="utf-8">',
             f'<title>{escape(title)}</title>', f'<style>{CSS}</style></head><body>',
             f'<h1>{escape(title)}</h1>',
             '<div class="warn">These programs have not yet run on the machine. '
             'Check every program in the simulator and run the first blank without material '
             f'before cutting. The machine work frame ({_g(fr["x"])} x {_g(fr["y"])} mm) is a '
             'placeholder, not yet verified on the machine.</div>']
    for p in data['problems']:
        parts.append(f'<p class="warn">{escape(p)}</p>')
    pn = data['panel']
    for panel in data['panels']:
        ids = ', '.join(b['id'] for b in panel['blanks'])
        parts.append(f'<section><h2>Panel {escape(panel["id"])}: saw into blanks {escape(ids)}</h2>')
        parts.append(f'<p>Panel {_g(pn["length"])} x {_g(pn["width"])} x {_g(pn["thickness"])} mm, '
                     f'saw kerf {_g(pn["kerf"])} mm, edge trim {_g(pn["edge"])} mm. Origin corner: '
                     'black dot (bottom left). Waste '
                     f'{panel["waste"] / 1e6:.2f} m² ({panel["waste_pct"]:.0f}%). Cut in this order; '
                     'stage 1 cuts go right across the panel, stage 2 across a strip, stage 3 trims '
                     'one piece.</p>')
        parts.append(_panel_svg(data, panel))
        parts.append(_cut_table(panel))
        parts.append('<table><tr><th>Blank</th><th>Size (mm)</th><th>On the panel</th><th>Shapes</th></tr>')
        for b in panel['blanks']:
            shapes = ', '.join(s['name'] for s in b['shapes'])
            parts.append(f'<tr><td>{escape(b["id"])}</td><td>{_g(b["width"])} x {_g(b["height"])}</td>'
                         f'<td>{"turned 90°" if b["rotated"] else "long side along the panel length"}</td>'
                         f'<td>{escape(shapes)}</td></tr>')
        parts.append('</table></section>')
    yt = data['y_toward']
    groups = {g['id']: g for g in data.get('pocket_groups', [])}
    for b in data['blanks']:
        names = {p['name'] for p in b['programs']}
        parts.append(f'<section><h2>Blank {escape(b["id"])} (from panel {escape(b["panel"])}), '
                     f'{_g(b["width"])} x {_g(b["height"])} mm</h2>')
        parts.append(f'<p>Program coordinates: {escape(ORIGIN[yt])}. Drawing seen from above, '
                     'operator at the bottom. Not yet verified on the machine.</p>')
        parts.append(_blank_svg(b, yt, {g for g, v in groups.items() if v['enabled']}))
        parts.append('<ol>' + ''.join(f'<li>{s}</li>' for s in _steps(b['id'], names, yt))
                     + '</ol>')
        parts.append('<table><tr><th>Program</th><th>Tools</th><th>Description</th></tr>')
        for p in b['programs']:
            parts.append(f'<tr><td>{escape(p["name"])}</td><td>{_tools(p)}</td>'
                         f'<td>{escape(p["description"])}</td></tr>')
        parts.append('</table>')
        parts.append(_drill_table(b))
        parts.append(_pocket_table(b, groups))
        parts.append('<p><b>Heights (mm)</b></p><table>')
        for key, label in Z_LABELS:
            if key in b['z']:
                parts.append(f'<tr><td>{escape(label)}</td><td>{b["z"][key]:g}</td></tr>')
        parts.append('</table></section>')
    parts.append('</body></html>')
    return '\n'.join(parts)


def write_output(out_dir: Path, plan: Plan, programs: list[Program], settings: Settings,
                 project: dict, backend: str = 'cnc90',
                 today: datetime.date | None = None,
                 pocket_overrides: dict | None = None,
                 groups: list | None = None) -> list[Path]:
    """Write the job folder `out_dir` (all or nothing). Returns its entries: the program files,
    loader, PROJECT.json, RUNSHEET.html and the DISKETTE folder (see nesting/importdisk.py).
    groups: the project's pocket groups, as given to plan_programs (see preview_data)."""
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(f'{out_dir} already exists; choose a new folder')
    emit = BACKENDS[backend]
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    # build everything beside out_dir, publish with one rename as the last step
    stage = Path(tempfile.mkdtemp(dir=out_dir.parent, prefix='.' + out_dir.name + '-'))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            staged = []
            for p in programs:
                path = Path(tmp) / p.name
                path.write_bytes(emit(p, settings).encode('ascii'))
                staged.append(str(path))
            r = subprocess.run([sys.executable, str(LOADER), str(stage), *staged],
                               capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f'make-loader.py failed ({r.returncode}): {r.stderr.strip()}')
        write_diskette(stage / DISKETTE, stage, [p.name for p in programs], today)
        data = preview_data(plan, programs, settings, pocket_overrides, groups)
        (stage / 'PROJECT.json').write_text(
            json.dumps({'settings': settings.to_dict(), 'tools': settings.tools.to_dict(),
                        'project': project,
                        'pockets': pocket_overrides or {},
                        'pocket_groups': data['pocket_groups']}, indent=2), encoding='utf-8')
        (stage / 'RUNSHEET.html').write_text(_runsheet(data, project), encoding='utf-8')
        if out_dir.exists():
            raise FileExistsError(f'{out_dir} already exists; choose a new folder')
        os.rename(stage, out_dir)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return sorted(out_dir.iterdir())
