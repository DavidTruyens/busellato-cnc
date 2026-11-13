"""Export every plate in the active Fusion design to a flat DXF (plates/<name>.dxf)
plus plates/plates.json.

Run inside Fusion (Scripts and Add-Ins, or via the Fusion MCP execute_python:
    OUT_DIR = '<repo>/plates'; exec(open('<repo>/fusion/export_plates.py').read())).

Per plate (one body per occurrence, flat, ~18 mm thick):
  - the top face is the planar face whose normal points up (+Z) in the document
  - the outer loop goes on layer CONTOUR, circular inner loops on layer HOLES
  - coordinates are millimetres, x = document X, y = document Y, seen from above
    (no mirroring), shifted so the lower-left of the outline bounding box is (0,0);
    arcs stay arcs
Any other inner loop is reported in 'ignored_loops' and not exported.
"""
import json
import math
import os

import adsk.core
import adsk.fusion

try:
    OUT_DIR
except NameError:
    OUT_DIR = os.path.join(os.path.expanduser('~'), 'plates')

MM = 10.0  # Fusion internal unit is cm


def _top_face(occ, body):
    best = None
    for f in body.faces:
        if f.geometry.objectType != adsk.core.Plane.classType():
            continue
        n = f.geometry.normal.copy()
        n.transformBy(occ.transform2)
        if n.z > 0.99 and (best is None or f.area > best.area):
            best = f
    return best


def _basis(occ):
    """Plate frame = the document's world X/Y axes, expressed in component space
    (plates are modelled flat and aligned along X; the top face looks up +Z)."""
    inv = occ.transform2.copy()
    inv.invert()
    u = adsk.core.Vector3D.create(1, 0, 0)
    v = adsk.core.Vector3D.create(0, 1, 0)
    u.transformBy(inv)
    v.transformBy(inv)
    return u, v


def _export(occ):
    comp = occ.component
    face = _top_face(occ, comp.bRepBodies.item(0))
    if face is None:
        raise RuntimeError('%s: no up-facing planar face' % occ.name)
    outer = [lp for lp in face.loops if lp.isOuter][0]
    u, v = _basis(occ)

    def p2(pt):
        return (pt.x * u.x + pt.y * u.y + pt.z * u.z,
                pt.x * v.x + pt.y * v.y + pt.z * v.z)

    ents, pts = [], []   # ents: ('LINE'|'ARC'|'CIRCLE', layer, args) before shift
    holes, ignored = [], 0
    for lp in face.loops:
        if lp.isOuter:
            layer = 'CONTOUR'
        elif lp.edges.count == 1 and lp.edges.item(0).geometry.objectType == adsk.core.Circle3D.classType():
            layer = 'HOLES'
        else:
            ignored += 1
            continue
        for e in lp.edges:
            g = e.geometry
            t = g.objectType
            if t == adsk.core.Line3D.classType():
                a, b = p2(e.startVertex.geometry), p2(e.endVertex.geometry)
                ents.append(('LINE', layer, (a, b)))
                pts += [a, b]
            elif t == adsk.core.Arc3D.classType():
                a, b = p2(e.startVertex.geometry), p2(e.endVertex.geometry)
                ok, pmin, pmax = e.evaluator.getParameterExtents()
                ok, m = e.evaluator.getPointAtParameter((pmin + pmax) / 2)
                m = p2(m)
                c = p2(g.center)
                ents.append(('ARC', layer, (c, g.radius, a, m, b)))
                pts += [a, b, m]
            elif t == adsk.core.Circle3D.classType():
                c = p2(g.center)
                ents.append(('CIRCLE', layer, (c, g.radius)))
                holes.append((c, g.radius))
            else:
                raise RuntimeError('%s: unsupported edge type %s' % (occ.name, t))
    # shift so the CONTOUR bounding box starts at (0,0)
    cp = [p for k, l, a in ents if l == 'CONTOUR' for p in
          ([a[0], a[1]] if k == 'LINE' else [a[2], a[3], a[4]])]
    # include arc extremes would be exact; endpoints+midpoint are enough for the corner (checked
    # against the body bounding box below)
    x0 = min(p[0] for p in cp)
    y0 = min(p[1] for p in cp)

    def sh(p):
        return ((p[0] - x0) * MM, (p[1] - y0) * MM)

    out = []
    for k, layer, a in ents:
        if k == 'LINE':
            out.append((k, layer, (sh(a[0]), sh(a[1]))))
        elif k == 'CIRCLE':
            out.append((k, layer, (sh(a[0]), a[1] * MM)))
        else:
            c, r, p0, pm, p1 = a
            c, p0, pm, p1 = sh(c), sh(p0), sh(pm), sh(p1)
            ang = lambda q: math.degrees(math.atan2(q[1] - c[1], q[0] - c[0])) % 360.0
            # CCW test: (p0-c) x (pm-c) > 0 means p0 -> pm runs counter-clockwise
            cr = (p0[0] - c[0]) * (pm[1] - c[1]) - (p0[1] - c[1]) * (pm[0] - c[0])
            s, e_ = (ang(p0), ang(p1)) if cr > 0 else (ang(p1), ang(p0))
            out.append((k, layer, (c, r * MM, s, e_)))
    return out, holes, ignored, (x0, y0), sh


def _dxf(entities):
    L = ['0', 'SECTION', '2', 'TABLES', '0', 'TABLE', '2', 'LAYER', '70', '2']
    for name, col in (('CONTOUR', 7), ('HOLES', 1)):
        L += ['0', 'LAYER', '2', name, '70', '0', '62', str(col), '6', 'CONTINUOUS']
    L += ['0', 'ENDTAB', '0', 'ENDSEC', '0', 'SECTION', '2', 'ENTITIES']
    for k, layer, a in entities:
        L += ['0', k, '8', layer]
        if k == 'LINE':
            (x1, y1), (x2, y2) = a
            L += ['10', '%.4f' % x1, '20', '%.4f' % y1, '30', '0', '11', '%.4f' % x2, '21', '%.4f' % y2, '31', '0']
        elif k == 'CIRCLE':
            (cx, cy), r = a
            L += ['10', '%.4f' % cx, '20', '%.4f' % cy, '30', '0', '40', '%.4f' % r]
        else:
            (cx, cy), r, s, e = a
            L += ['10', '%.4f' % cx, '20', '%.4f' % cy, '30', '0', '40', '%.4f' % r,
                  '50', '%.4f' % s, '51', '%.4f' % e]
    L += ['0', 'ENDSEC', '0', 'EOF']
    return '\n'.join(L) + '\n'


def run():
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    os.makedirs(OUT_DIR, exist_ok=True)
    plates = []
    for occ in des.rootComponent.allOccurrences:
        if occ.component.bRepBodies.count != 1:
            continue
        name = occ.component.name
        ents, holes, ignored, origin, sh = _export(occ)
        bb = occ.bRepBodies.item(0).boundingBox
        fn = name.replace(' ', '_') + '.dxf'
        with open(os.path.join(OUT_DIR, fn), 'w') as fh:
            fh.write(_dxf(ents))
        plates.append({
            'name': name, 'dxf': fn, 'ignored_loops': ignored,
            'thickness': round((bb.maxPoint.z - bb.minPoint.z) * MM, 3),
            'world_bbox_xy': [round((bb.maxPoint.x - bb.minPoint.x) * MM, 2),
                              round((bb.maxPoint.y - bb.minPoint.y) * MM, 2)],
            'holes': [{'x': sh(c)[0], 'y': sh(c)[1], 'diameter': 2 * r * MM} for c, r in holes],
            'n_contour_entities': sum(1 for k, l, a in ents if l == 'CONTOUR'),
        })
    with open(os.path.join(OUT_DIR, 'plates.json'), 'w') as fh:
        json.dump(plates, fh, indent=2)
    return plates


PLATES = run()
