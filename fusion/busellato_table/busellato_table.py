"""Busellato S.EASY vacuum table: build beams and pods from user parameters
and set them as fixtures in every setup.
Spec: docs/superpowers/specs/2026-09-26-vacuum-table-design.md (busellato-cnc repo).
"""
import os
import sys
import traceback

import adsk.cam
import adsk.core
import adsk.fusion

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import table_geometry as tg  # noqa: E402

COMPONENT = 'Vacuum table'
MACHINE_FILE = os.path.join(os.path.dirname(HERE), 'busellato-table.json')
ATTR_GROUP, ATTR_NAME = 'busellato', 'table'


def _param_values(des, specs):
    created, values = [], {}
    up = des.userParameters
    for name, unit, start in specs:
        p = up.itemByName(name)
        if p is None:
            text = f'{start:g} mm' if unit == 'mm' else f'{start:g}'
            up.add(name, adsk.core.ValueInput.createByString(text), unit, 'Busellato vacuum table')
            created.append(name)
            p = up.itemByName(name)
        values[name] = p.value * 10.0 if unit == 'mm' else p.value      # Fusion lengths are in cm
    return created, values


def _reference_setup(cam):
    for s in cam.setups:
        if s.models.count > 0:
            return s
    return None


def _frame(setup):
    """WCS origin and axes, origin converted to Fusion's internal cm.

    The CAM API returns the WCS origin in document length units (mm here: S1's
    origin on the 18 mm panel top reads 18.0), while body geometry is in cm.
    """
    o, x, y, z = setup.workCoordinateSystem.getAsCoordinateSystem()
    doc = adsk.core.Application.get().activeDocument
    units = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType')).unitsManager
    to_cm = units.convert(1, units.defaultLengthUnits, 'cm')
    return adsk.core.Point3D.create(o.x * to_cm, o.y * to_cm, o.z * to_cm), x, y, z


def _stock_bottom_g54(setup, frame):
    o, x, y, z = frame
    lowest = None
    for i in range(setup.models.count):
        bb = setup.models.item(i).boundingBox
        for px in (bb.minPoint.x, bb.maxPoint.x):
            for py in (bb.minPoint.y, bb.maxPoint.y):
                for pz in (bb.minPoint.z, bb.maxPoint.z):
                    v = adsk.core.Vector3D.create(px - o.x, py - o.y, pz - o.z)
                    zz = v.dotProduct(z) * 10.0
                    lowest = zz if lowest is None else min(lowest, zz)
    return lowest


def _same_frame(a, b):
    return (a[0].distanceTo(b[0]) < 0.001 and all(a[i].isParallelTo(b[i]) and a[i].dotProduct(b[i]) > 0 for i in (1, 2, 3)))


def _is_table_body(body):
    comp = body.parentComponent
    return comp.name == COMPONENT and comp.attributes.itemByName(ATTR_GROUP, ATTR_NAME) is not None


def _user_fixtures(setup):
    """The setup's fixtures that this script did not create."""
    keep = []
    for i in range(setup.fixtures.count):
        f = setup.fixtures.item(i)
        if f.isValid and not _is_table_body(f):
            keep.append(f)
    return keep


def _set_fixtures(setup, bodies):
    col = adsk.core.ObjectCollection.create()
    for b in bodies:
        col.add(b)
    setup.fixtures = col


def _remove_previous(root):
    for occ in [root.occurrences.item(i) for i in range(root.occurrences.count)]:
        if occ.component.name == COMPONENT and occ.component.attributes.itemByName(ATTR_GROUP, ATTR_NAME):
            occ.deleteMe()


def _box_body(comp, box, frame):
    o, x, y, z = frame
    cx, cy, cz = (box.x0 + box.x1) / 20.0, (box.y0 + box.y1) / 20.0, (box.z0 + box.z1) / 20.0   # mm -> cm
    centre = adsk.core.Point3D.create(o.x + x.x * cx + y.x * cy + z.x * cz,
                                      o.y + x.y * cx + y.y * cy + z.y * cz,
                                      o.z + x.z * cx + y.z * cy + z.z * cz)
    obb = adsk.core.OrientedBoundingBox3D.create(centre, x, y, (box.x1 - box.x0) / 10.0,
                                                 (box.y1 - box.y0) / 10.0, (box.z1 - box.z0) / 10.0)
    temp = adsk.fusion.TemporaryBRepManager.get().createBox(obb)
    design = adsk.fusion.Design.cast(comp.parentDesign)
    if design.designType == adsk.fusion.DesignTypes.ParametricDesignType:
        feature = comp.features.baseFeatures.add()
        feature.startEdit()
        comp.bRepBodies.add(temp, feature)
        feature.finishEdit()
    else:
        comp.bRepBodies.add(temp)
    body = comp.bRepBodies.item(comp.bRepBodies.count - 1)
    body.name = box.name
    return body


def apply(app, machine_path=MACHINE_FILE):
    doc = app.activeDocument
    des = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
    cam_product = doc.products.itemByProductType('CAMProductType')
    report = {'ok': False, 'problems': [], 'warnings': [], 'created_parameters': [], 'bodies': [], 'setups': []}
    cam = adsk.cam.CAM.cast(cam_product) if cam_product else None
    reference = _reference_setup(cam) if cam else None
    if reference is None:
        report['problems'].append('no setup with stock in this document (Manufacture workspace)')
        return report
    machine = tg.load_machine(machine_path)
    report['problems'] += tg.check_machine(machine)
    if report['problems']:
        return report
    specs = tg.parameter_specs(machine)
    missing = [s for s in specs if des.userParameters.itemByName(s[0]) is None]
    if missing:                                    # first run: only create parameters, build nothing
        report['created_parameters'], _ = _param_values(des, specs)
        report['warnings'].append('parameters created with starting values: set them to match the machine, then run again')
        report['ok'] = True
        return report
    _, values = _param_values(des, specs)
    frame = _frame(reference)
    result = tg.build(machine, values, _stock_bottom_g54(reference, frame))
    report['problems'] += result.problems
    if report['problems']:
        return report
    differing = {s.name for s in cam.setups if not _same_frame(frame, _frame(s))}
    report['warnings'] += result.warnings + tg.reference_warnings(reference.name, [s.name for s in cam.setups], differing)

    root = des.rootComponent
    # Detach our old bodies from every setup BEFORE deleting them: deleting bodies
    # that setups still reference as fixtures crashed Fusion (2026-09-30).
    kept = {}
    for s in cam.setups:
        kept[s.name] = _user_fixtures(s)
        _set_fixtures(s, kept[s.name])
    _remove_previous(root)
    occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    comp = occ.component
    comp.name = COMPONENT
    comp.attributes.add(ATTR_GROUP, ATTR_NAME, '1')
    bodies = [_box_body(comp, box, frame) for box in result.boxes]
    report['bodies'] = [b.name for b in bodies]

    proxies = [occ.bRepBodies.itemByName(b.name) or b for b in bodies]
    for s in cam.setups:
        _set_fixtures(s, kept[s.name] + proxies)
        s.fixtureEnabled = True
        report['setups'].append(s.name)
    report['ok'] = True
    return report


def run(context):
    ui = adsk.core.Application.get().userInterface
    try:
        r = apply(adsk.core.Application.get())
        lines = []
        if r['problems']:
            lines.append('Nothing was changed. Problems:')
            lines += ['- ' + p for p in r['problems']]
        else:
            if r['created_parameters']:
                lines.append(f'Created {len(r["created_parameters"])} parameters (Modify > Change Parameters).')
            if r['bodies']:
                lines.append(f'Built {len(r["bodies"])} bodies; fixtures set in: {", ".join(r["setups"])}.')
        if r['warnings']:
            lines.append('Warnings:')
            lines += ['- ' + w for w in r['warnings']]
        ui.messageBox('\n'.join(lines), 'Busellato table')
    except Exception:
        ui.messageBox('Failed:\n' + traceback.format_exc(), 'Busellato table')
