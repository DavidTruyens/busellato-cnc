#!/usr/bin/env python3
"""Pair plates into combos, build one template per combo, nest templates on stock panels.

    python3 tools/nest_plates.py [--plates plates/plates.json] [--qty NAME=N ...]
                                 [--out nest/nest.json] [--svg nest/nest.svg]

Model (all millimetres, plate frame as exported by fusion/export_plates.py):
  * a COMBO is up to 2 plates side by side (x along the plates), paired by similar length
    so the template stays short;
  * a TEMPLATE is a rectangle around the combo's bounding boxes. It gets 4 fixing holes
    (screwed to the scrap plate on the vacuum cups) in its corners, outside the plates, and
    one pilot hole under each of the plates' own holes (the plates are screwed to it);
  * templates are cut from 1220 x 2440 stock panels and nested with MaxRects (90 degree
    rotation allowed: the stock has no grain constraint here).

Every number in Config is an assumption until confirmed at the machine.
"""
import argparse
import json
import math
from dataclasses import dataclass, asdict, field
from pathlib import Path

repo = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    panel_l: float = 2440.0       # stock panel, x
    panel_w: float = 1220.0       # stock panel, y
    panel_edge: float = 10.0      # unusable border of the panel
    tool_dia: float = 12.0        # PLACEHOLDER router bit diameter
    clearance: float = 4.0        # extra gap on top of the tool diameter
    margin_end: float = 45.0      # template border beyond the plates, along x
    margin_side: float = 45.0     # template border beyond the plates, along y
    fix_hole_dia: float = 6.0     # screw to the scrap plate
    fix_inset: float = 15.0       # fixing hole centre from the template edges
    head_dia: float = 14.0        # screw head clearance
    pilot_dia: float = 3.0        # pilot hole in the template under each plate hole
    pair_size: int = 2

    @property
    def gap(self):                # between plates in a template, and between templates
        return self.tool_dia + self.clearance


def expand(plates, qty):
    """One entry per physical plate. qty maps name -> count (default 1, 0 skips)."""
    out = []
    for p in plates:
        for i in range(int(qty.get(p['name'], 1))):
            q = dict(p)
            q['length'], q['width'] = p['world_bbox_xy']
            q['copy'] = i + 1
            out.append(q)
    return out


def pair_plates(items, size=2):
    """Sort by length and pair neighbours: for sum-of-max-length this is optimal."""
    s = sorted(items, key=lambda p: (-p['length'], -p['width'], p['name']))
    return [s[i:i + size] for i in range(0, len(s), size)]


def build_template(tid, combo, cfg):
    combo = sorted(combo, key=lambda p: -p['width'])      # widest at the bottom
    length = max(p['length'] for p in combo)
    width = sum(p['width'] for p in combo) + cfg.gap * (len(combo) - 1)
    W = length + 2 * cfg.margin_end
    H = width + 2 * cfg.margin_side
    plates, pilots, y = [], [], cfg.margin_side
    for p in combo:
        x = cfg.margin_end
        plates.append({'name': p['name'], 'copy': p['copy'], 'dxf': p['dxf'],
                       'x': x, 'y': y, 'length': p['length'], 'width': p['width'],
                       'thickness': p['thickness']})
        for h in p['holes']:
            pilots.append({'x': x + h['x'], 'y': y + h['y'], 'diameter': cfg.pilot_dia,
                           'plate': p['name']})
        y += p['width'] + cfg.gap
    i = cfg.fix_inset
    fix = [{'x': fx, 'y': fy, 'diameter': cfg.fix_hole_dia}
           for fx in (i, W - i) for fy in (i, H - i)]
    t = {'id': tid, 'width': W, 'height': H, 'plates': plates,
         'fix_holes': fix, 'pilot_holes': pilots}
    check_template(t, cfg)
    return t


def check_template(t, cfg):
    """Fixing holes must stay clear of the plates, the cutter path and the screw heads."""
    need = cfg.tool_dia / 2 + cfg.head_dia / 2 + 3.0
    for h in t['fix_holes']:
        for p in t['plates']:
            dx = max(p['x'] - h['x'], 0, h['x'] - (p['x'] + p['length']))
            dy = max(p['y'] - h['y'], 0, h['y'] - (p['y'] + p['width']))
            d = math.hypot(dx, dy)
            if d < need:
                raise ValueError('%s: fixing hole (%.0f, %.0f) only %.1f mm from plate %s, need %.1f'
                                 % (t['id'], h['x'], h['y'], d, p['name'], need))


class MaxRects:
    def __init__(self, w, h):
        self.free = [(0.0, 0.0, w, h)]

    def place(self, w, h, rotate=True):
        best = None
        for rw, rh, rot in ((w, h, False),) + (((h, w, True),) if rotate and w != h else ()):
            for fx, fy, fw, fh in self.free:
                if rw <= fw + 1e-9 and rh <= fh + 1e-9:
                    key = (min(fw - rw, fh - rh), max(fw - rw, fh - rh))
                    if best is None or key < best[0]:
                        best = (key, fx, fy, rw, rh, rot)
        if best is None:
            return None
        _, x, y, rw, rh, rot = best
        self._split(x, y, rw, rh)
        return x, y, rot

    def _split(self, x, y, w, h):
        new = []
        for fx, fy, fw, fh in self.free:
            if x >= fx + fw or x + w <= fx or y >= fy + fh or y + h <= fy:
                new.append((fx, fy, fw, fh))
                continue
            if x > fx:
                new.append((fx, fy, x - fx, fh))
            if x + w < fx + fw:
                new.append((x + w, fy, fx + fw - x - w, fh))
            if y > fy:
                new.append((fx, fy, fw, y - fy))
            if y + h < fy + fh:
                new.append((fx, y + h, fw, fy + fh - y - h))
        self.free = [r for i, r in enumerate(new)
                     if not any(j != i and _inside(r, o) and (r != o or j < i)
                                for j, o in enumerate(new))]


def _inside(a, b):
    return a[0] >= b[0] - 1e-9 and a[1] >= b[1] - 1e-9 and \
        a[0] + a[2] <= b[0] + b[2] + 1e-9 and a[1] + a[3] <= b[1] + b[3] + 1e-9


def nest(templates, cfg):
    """Place templates on as few panels as possible. Returns panels with placements."""
    bw = cfg.panel_l - 2 * cfg.panel_edge + cfg.gap
    bh = cfg.panel_w - 2 * cfg.panel_edge + cfg.gap
    panels, bins = [], []
    for t in sorted(templates, key=lambda t: -(t['width'] * t['height'])):
        w, h = t['width'] + cfg.gap, t['height'] + cfg.gap
        if min(w, h) > min(bw, bh) + 1e-9 or max(w, h) > max(bw, bh) + 1e-9:
            raise ValueError('%s (%.0f x %.0f) does not fit on a panel' % (t['id'], t['width'], t['height']))
        for pan, b in zip(panels, bins):
            r = b.place(w, h)
            if r:
                break
        else:
            pan = {'id': 'P%d' % (len(panels) + 1), 'length': cfg.panel_l, 'width': cfg.panel_w,
                   'placements': []}
            b = MaxRects(bw, bh)
            panels.append(pan)
            bins.append(b)
            r = b.place(w, h)
        x, y, rot = r
        pan['placements'].append({'template': t['id'], 'x': x + cfg.panel_edge,
                                  'y': y + cfg.panel_edge, 'rotated': rot})
    return panels


def to_panel(pl, t, x, y):
    """Template-frame point -> panel-frame point. Rotated = 90 degrees counter-clockwise."""
    if pl['rotated']:
        return pl['x'] + t['height'] - y, pl['y'] + x
    return pl['x'] + x, pl['y'] + y


def footprint(pl, t):
    return (t['height'], t['width']) if pl['rotated'] else (t['width'], t['height'])


def run(plates, qty, cfg):
    combos = pair_plates(expand(plates, qty), cfg.pair_size)
    templates = [build_template('T%02d' % (i + 1), c, cfg) for i, c in enumerate(combos)]
    panels = nest(templates, cfg)
    used = sum(t['width'] * t['height'] for t in templates)
    plate_area = sum(p['length'] * p['width'] for t in templates for p in t['plates'])
    total = len(panels) * cfg.panel_l * cfg.panel_w
    return {'config': asdict(cfg), 'templates': templates, 'panels': panels,
            'stats': {'plates': sum(len(t['plates']) for t in templates),
                      'templates': len(templates), 'panels': len(panels),
                      'template_area_of_panels': used / total,
                      'plate_bbox_area_of_panels': plate_area / total}}


def svg(res):
    tmpl = {t['id']: t for t in res['templates']}
    out, y0 = [], 0
    pw, ph = res['config']['panel_l'], res['config']['panel_w']
    for pan in res['panels']:
        g = ['<g transform="translate(0,%d)">' % y0,
             '<rect x="0" y="0" width="%g" height="%g" fill="#f3ead8" stroke="#000" stroke-width="3"/>' % (pw, ph),
             '<text x="20" y="40" font-size="36">%s</text>' % pan['id']]
        for pl in pan['placements']:
            t = tmpl[pl['template']]
            w, h = footprint(pl, t)
            g.append('<rect x="%g" y="%g" width="%g" height="%g" fill="#d9c49a" stroke="#6b4e16" stroke-width="2"/>'
                     % (pl['x'], pl['y'], w, h))
            for p in t['plates']:
                corners = [to_panel(pl, t, p['x'] + dx, p['y'] + dy)
                           for dx, dy in ((0, 0), (p['length'], 0), (p['length'], p['width']), (0, p['width']))]
                g.append('<polygon points="%s" fill="#8fb4d9" stroke="#1d4f8a" stroke-width="2"/>'
                         % ' '.join('%g,%g' % c for c in corners))
                cx, cy = to_panel(pl, t, p['x'] + p['length'] / 2, p['y'] + p['width'] / 2)
                g.append('<text x="%g" y="%g" font-size="26" text-anchor="middle">%s</text>' % (cx, cy + 9, p['name']))
            for h_ in t['fix_holes'] + t['pilot_holes']:
                cx, cy = to_panel(pl, t, h_['x'], h_['y'])
                col = '#c00' if h_ in t['fix_holes'] else '#000'
                g.append('<circle cx="%g" cy="%g" r="%g" fill="none" stroke="%s" stroke-width="2"/>'
                         % (cx, cy, max(h_['diameter'] / 2, 3), col))
        g.append('</g>')
        out += g
        y0 += ph + 60
    # flip y so the preview reads like the machine's x/y plane (y up)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="-20 -20 %g %g">'
            '<g transform="translate(0,%g) scale(1,-1)">%s</g></svg>'
            % (pw + 40, y0 + 20, y0 - 60, ''.join(_unflip_text(out))))


def _unflip_text(parts):
    # text is drawn inside a y-flipped group; flip it back around its own anchor
    import re
    res = []
    for s in parts:
        m = re.match(r'<text x="([-\d.]+)" y="([-\d.]+)"(.*)', s)
        if m:
            x, y = m.group(1), m.group(2)
            s = '<text x="%s" y="%s" transform="translate(0,%s) scale(1,-1) translate(0,%s)"%s' % (x, y, y, '-' + y, m.group(3))
        res.append(s)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--plates', default=str(repo / 'plates' / 'plates.json'))
    ap.add_argument('--qty', nargs='*', default=[], metavar='NAME=N')
    ap.add_argument('--out', default=str(repo / 'nest' / 'nest.json'))
    ap.add_argument('--svg', default=str(repo / 'nest' / 'nest.svg'))
    a = ap.parse_args(argv)
    qty = {k: int(v) for k, v in (s.rsplit('=', 1) for s in a.qty)}
    res = run(json.load(open(a.plates)), qty, Config())
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=1))
    Path(a.svg).write_text(svg(res))
    s = res['stats']
    print('%d plates -> %d templates -> %d panels (templates use %.0f%% of the panel area, plate boxes %.0f%%)'
          % (s['plates'], s['templates'], s['panels'], 100 * s['template_area_of_panels'],
             100 * s['plate_bbox_area_of_panels']))
    for t in res['templates']:
        print(' ', t['id'], '%.0f x %.0f' % (t['width'], t['height']), ' + '.join(p['name'] for p in t['plates']))
    for p in res['panels']:
        print(' ', p['id'], ', '.join('%s%s@(%.0f,%.0f)' % (q['template'], 'R' if q['rotated'] else '', q['x'], q['y'])
                                      for q in p['placements']))


if __name__ == '__main__':
    main()
