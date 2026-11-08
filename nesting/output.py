"""Write the job folder: program files, loader batch files, PROJECT.json and the printable run sheet."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path

from .backends import BACKENDS
from .layout import Plan
from .preview import preview_data
from .program import Program, _panel_number
from .settings import Settings

LOADER = Path(__file__).resolve().parent.parent / 'tools' / 'make-loader.py'

Z_LABELS = [('stack_top', 'Stack height (top of stack above the cups)'),
            ('fixing', 'Fixing holes: drill depth'),
            ('screw', 'Screw holes: drill depth'),
            ('shape_cut', 'Shapes: cut depth'),
            ('template_cut', 'Templates: cut depth')]

CSS = """body{font-family:Arial,sans-serif;margin:12mm;color:#000}
h1{font-size:18pt;margin:0 0 4mm}h2{font-size:14pt;margin:0 0 3mm}
.warn{border:2px solid #b00;padding:3mm;margin:0 0 6mm;font-weight:bold}
section.panel{page-break-after:always;margin-bottom:10mm}
svg{width:100%;height:auto;border:1px solid #000;background:#fff}
.tpl{fill:#eef;stroke:#339;stroke-width:2}.shape{fill:#fd9;stroke:#640;stroke-width:1.5}
.fix{fill:none;stroke:#c00;stroke-width:2}.screw{fill:none;stroke:#060;stroke-width:2}
.lbl{font-size:28px;text-anchor:middle;fill:#000}.tid{font-size:24px;fill:#339}
ol li{margin:1.5mm 0}table{border-collapse:collapse}td,th{border:1px solid #000;padding:1mm 3mm;text-align:left}
@media print{body{margin:8mm}}"""


def _g(v: float) -> str:
    return f'{v:g}' if isinstance(v, (int, float)) else str(v)


def _svg(data: dict, panel: dict) -> str:
    L, W = data['panel']['length'], data['panel']['width']
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_g(L)} {_g(W)}">',
           f'<rect x="0" y="0" width="{_g(L)}" height="{_g(W)}" fill="none" stroke="#000" stroke-width="3"/>']
    for t in panel['templates']:
        out.append(f'<rect class="tpl" x="{_g(t["x"])}" y="{_g(t["y"])}" width="{_g(t["w"])}" '
                   f'height="{_g(t["h"])}"/>')
        out.append(f'<text class="tid" x="{_g(t["x"] + 6)}" y="{_g(t["y"] + 26)}">{escape(t["id"])}</text>')
        for s in t['shapes']:
            out.append(f'<path class="shape" d="{escape(s["path"])}"/>')
            out.append(f'<text class="lbl" x="{_g(s["cx"])}" y="{_g(s["cy"])}">{escape(s["name"])}</text>')
        for h in t['fix']:
            out.append(f'<circle class="fix" cx="{_g(h["x"])}" cy="{_g(h["y"])}" r="8"/>')
        for h in t['screw']:
            out.append(f'<circle class="screw" cx="{_g(h["x"])}" cy="{_g(h["y"])}" r="5"/>')
    out.append('</svg>')
    return '\n'.join(out)


def _steps(n: str, names: set[str]) -> list[str]:
    f, s, c = f'N{n}F', f'N{n}S', f'N{n}C'
    steps = []
    if f in names:
        steps.append(f'Drill <b>{escape(f)}</b> (fixing holes).')
        steps.append('Screw the panel to the scrap plate through the fixing holes.')
    steps.append('Place the shapes as drawn (red circles: fixing holes, green circles: screw holes).')
    if s in names:
        steps.append(f'Drill <b>{escape(s)}</b> (screw holes).')
    elif f in names:
        steps.append(f'Screw holes: no separate program, merged into {escape(f)}.')
    steps.append('Screw the shapes down.')
    if c in names:
        steps.append(f'Run <b>{escape(c)}</b> (cut).')
    return steps


def _runsheet(data: dict, project: dict, plan: Plan) -> str:
    title = str(project.get('name') or 'Run sheet')
    parts = ['<!DOCTYPE html>', '<html lang="en"><head><meta charset="utf-8">',
             f'<title>{escape(title)}</title>', f'<style>{CSS}</style></head><body>',
             f'<h1>{escape(title)}</h1>',
             '<div class="warn">These programs have not yet run on the machine. '
             'Check every program in the simulator and run the first panel without material '
             'before cutting.</div>']
    for p in data['problems']:
        parts.append(f'<p class="warn">{escape(p)}</p>')
    for panel, pp in zip(data['panels'], plan.panels):
        n = _panel_number(pp)
        names = {p['name'] for p in panel['programs']}
        parts.append(f'<section class="panel"><h2>Panel {escape(panel["id"])}</h2>')
        parts.append(_svg(data, panel))
        parts.append('<ol>' + ''.join(f'<li>{s}</li>' for s in _steps(n, names)) + '</ol>')
        parts.append('<table><tr><th>Program</th><th>Tool</th><th>Description</th></tr>')
        for p in panel['programs']:
            parts.append(f'<tr><td>{escape(p["name"])}</td><td>T{p["tool"]}</td>'
                         f'<td>{escape(p["description"])}</td></tr>')
        parts.append('</table>')
        parts.append('<p><b>Heights (mm)</b></p><table>')
        for key, label in Z_LABELS:
            if key in panel['z']:
                parts.append(f'<tr><td>{escape(label)}</td><td>{_g(panel["z"][key])}</td></tr>')
        parts.append('</table></section>')
    parts.append('</body></html>')
    return '\n'.join(parts)


def write_output(out_dir: Path, plan: Plan, programs: list[Program], settings: Settings,
                 project: dict, backend: str = 'cnc90') -> list[Path]:
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(f'{out_dir} already exists; choose a new folder')
    emit = BACKENDS[backend]
    with tempfile.TemporaryDirectory() as tmp:
        staged = []
        for p in programs:
            path = Path(tmp) / p.name
            path.write_bytes(emit(p, settings).encode('ascii'))
            staged.append(str(path))
        r = subprocess.run([sys.executable, str(LOADER), str(out_dir), *staged],
                           capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f'make-loader.py failed ({r.returncode}): {r.stderr.strip()}')
    (out_dir / 'PROJECT.json').write_text(
        json.dumps({'settings': settings.to_dict(), 'project': project}, indent=2), encoding='utf-8')
    data = preview_data(plan, programs, settings)
    (out_dir / 'RUNSHEET.html').write_text(_runsheet(data, project, plan), encoding='utf-8')
    return sorted(out_dir.iterdir())
