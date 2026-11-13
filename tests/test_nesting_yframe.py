"""Program frame of a blank: machine.y_toward 'front' (default) puts X0 Y0 at the blank's back-left
corner (top left of the picture, operator at the bottom) with Y growing toward the front.

These tests check that the drill positions, the contour (points, arcs, G2/G3, U), the turning
sense seen from above and the preview drawing all agree in that frame. Whether the machine
really has Y toward the front, and how it reads G2/G3 then, is NOT verified here: only on the
machine (air cut first).
"""
import math
import re
import unittest

from nesting.backends import BACKENDS
from nesting.dxf import Hole, Shape
from nesting.geometry import Arc, Line, distance_to_chain, translate
from nesting.layout import Blank, PanelPlan, PlacedShape, Plan
from nesting.output import _blank_svg, _runsheet
from nesting.preview import preview_data
from nesting.program import blank_programs, plan_programs, segs_to_program, to_program
from nesting.settings import Settings, SettingsError
from test_nesting_preview import parse

W, H = 690, 290          # blank
SX, SY = 45, 45          # shape corner in the layout frame (y up from the front-left corner)
R_FILLET = 30


def rounded():
    """600 x 200 rectangle, its corner at (600, 200) rounded with R30 (layout frame, y up)."""
    outline = [Line((0, 0), (600, 0)), Line((600, 0), (600, 170)),
               Arc((600, 170), (570, 200), (570, 170), R_FILLET, True),
               Line((570, 200), (0, 200)), Line((0, 200), (0, 0))]
    return Shape('rnd', outline, [Hole(150, 40, 6.6)])


def blank(x=SX, y=SY):
    return Blank('B01', W, H, [PlacedShape('rnd', 1, x, y, rounded())],
                 [Hole(15, 15, 6), Hole(15, H - 15, 6)], [Hole(x + 150, y + 40, 3)], 'P1')


def settings(y_toward='front', direction='ccw'):
    s = Settings()
    s.machine.y_toward, s.router.direction = y_toward, direction
    return s


def progs(s, b=None):
    return {p.name: p for p in blank_programs(b or blank(), s)}


MOVE = re.compile(r'(G88|G1|G2|G3)G90.*?X(-?[\d.]+)Y(-?[\d.]+)(?:Z[\d.]+)?(?:U([\d.]+))?$')


def moves(text):
    """[(code, x, y, u)] of the cut moves, in order, from the emitted program text."""
    out = []
    for line in text.split('\r\n'):
        m = MOVE.match(line)
        if m:
            out.append((m.group(1), float(m.group(2)), float(m.group(3)),
                        float(m.group(4)) if m.group(4) else None))
    return out


def arc_centre(p, q, r, code):
    """Centre of the short arc p -> q of radius r; G3 = counter-clockwise in the numbers."""
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    dx, dy = q[0] - p[0], q[1] - p[1]
    d = math.hypot(dx, dy)
    h = math.sqrt(max(0.0, r * r - (d / 2) ** 2))
    k = 1 if code == 'G3' else -1           # centre to the left of the chord for G3
    return mx - k * h * dy / d, my + k * h * dx / d


def polygon(mv, step=1.0):
    """Points of the first pass of the emitted contour, arcs sampled, in program numbers."""
    pts = [(mv[0][1], mv[0][2])]
    for code, x, y, u in mv[1:]:
        p, q = pts[-1], (x, y)
        if p == q and code == 'G1':
            continue
        if code in ('G2', 'G3'):
            c = arc_centre(p, q, u, code)
            a0, a1 = math.atan2(p[1] - c[1], p[0] - c[0]), math.atan2(q[1] - c[1], q[0] - c[0])
            sweep = (a1 - a0) % (2 * math.pi) if code == 'G3' else -((a0 - a1) % (2 * math.pi))
            n = max(2, math.ceil(abs(sweep) * u / step))
            pts += [(c[0] + u * math.cos(a0 + sweep * i / n), c[1] + u * math.sin(a0 + sweep * i / n))
                    for i in range(1, n + 1)]
        else:
            pts.append(q)
        if len(pts) > 3 and math.dist(pts[-1], pts[0]) < 1e-3:
            break                       # closed: the first pass is done
    return pts


def shoelace(pts):
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))


def inside(pt, pts):
    x, y = pt
    hit = False
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


class ProgramFrameTests(unittest.TestCase):
    def test_default_is_front(self):
        self.assertEqual(Settings().machine.y_toward, 'front')

    def test_drill_positions_measured_from_the_back_edge(self):
        front, back = progs(settings('front')), progs(settings('back'))
        # B01D: the fixing holes (tool 1) then the screw hole (tool 2)
        self.assertEqual([(o.x, o.y) for o in back['B01D'].ops],
                         [(15, 15), (15, H - 15), (SX + 150, SY + 40)])
        self.assertEqual([(o.x, o.y) for o in front['B01D'].ops],
                         [(15, H - 15), (15, 15), (SX + 150, H - (SY + 40))])
        self.assertEqual([o.tool for o in front['B01D'].ops], [1, 1, 2])
        for a, b in zip(front['B01D'].ops, back['B01D'].ops):
            self.assertEqual((a.x, a.y, a.depth, a.diameter), (b.x, H - b.y, b.depth, b.diameter))

    def test_contour_is_the_mirror_of_the_y_up_contour(self):
        front, back = progs(settings('front')), progs(settings('back'))
        self.assertEqual(len(front['B01C'].ops), len(back['B01C'].ops))
        for fo, bo in zip(front['B01C'].ops, back['B01C'].ops):
            self.assertEqual((fo.depth, fo.label), (bo.depth, bo.label))
            self.assertEqual(len(fo.segs), len(bo.segs))
            for f, b in zip(fo.segs, bo.segs):       # same order, same start point
                self.assertEqual(type(f), type(b))
                for pf, pb in ((f.a, b.a), (f.b, b.b)):
                    self.assertAlmostEqual(pf[0], pb[0], places=9)
                    self.assertAlmostEqual(pf[1], H - pb[1], places=9)
                if isinstance(f, Arc):
                    self.assertEqual(f.radius, b.radius)
                    self.assertEqual(f.ccw, not b.ccw)
                    self.assertAlmostEqual(f.center[1], H - b.center[1], places=9)

    def test_emitted_text_has_y_mirrored_and_g2_g3_swapped(self):
        sf, sb = settings('front'), settings('back')
        tf = BACKENDS['cnc90'](progs(sf)['B01C'], sf).split('\r\n')
        tb = BACKENDS['cnc90'](progs(sb)['B01C'], sb).split('\r\n')
        self.assertEqual(len(tf), len(tb))
        self.assertEqual(tf[0], tb[0])                       # header: stock W x H x Z unchanged
        swap = {'G2': 'G3', 'G3': 'G2', 'G1': 'G1', 'G88': 'G88'}
        mf, mb = moves('\r\n'.join(tf)), moves('\r\n'.join(tb))
        self.assertEqual(len(mf), len(mb))
        self.assertIn('G2', [m[0] for m in mf])
        for (cf, xf, yf, uf), (cb, xb, yb, ub) in zip(mf, mb):
            self.assertEqual(cf, swap[cb])
            self.assertAlmostEqual(xf, xb, delta=0.0015)
            self.assertAlmostEqual(yf, H - yb, delta=0.0015)
            self.assertEqual(uf, ub)

    def test_emitted_arcs_rebuild_the_program_geometry(self):
        """G2/G3 + end point + U, read back from the text, give the contour's own arc centres:
        the code is right for the numbers it is written with."""
        for y_toward in ('front', 'back'):
            s = settings(y_toward)
            p = progs(s)['B01C']
            op = p.ops[0]
            mv = moves(BACKENDS['cnc90'](p, s))
            arcs = [sg for sg in op.segs if isinstance(sg, Arc)]
            got = []
            prev = (mv[0][1], mv[0][2])
            for code, x, y, u in mv[1:len(op.segs) + 2]:
                if code in ('G2', 'G3'):
                    got.append((code, arc_centre(prev, (x, y), u, code), u))
                prev = (x, y)
            self.assertEqual(len(got), len(arcs))
            for (code, c, u), sg in zip(got, arcs):
                self.assertEqual(code, 'G3' if sg.ccw else 'G2')
                self.assertAlmostEqual(u, sg.radius, delta=0.001)
                self.assertAlmostEqual(c[0], sg.center[0], delta=0.01)
                self.assertAlmostEqual(c[1], sg.center[1], delta=0.01)

    def test_rounded_corner_arc_is_at_the_back(self):
        """The fillet at layout (570, 170)+(45,45) is near the back edge: program Y small."""
        for direction in ('ccw', 'cw'):
            s = settings('front', direction)
            op = progs(s)['B01C'].ops[0]
            want = (SX + 570, H - (SY + 170))
            fillet = [sg for sg in op.segs if isinstance(sg, Arc)
                      and math.dist(sg.center, want) < 1e-6]
            self.assertEqual(len(fillet), 1)
            self.assertAlmostEqual(fillet[0].radius, R_FILLET + s.router_bit.diameter / 2)
            # ccw from above = clockwise in Y-down numbers = G2
            self.assertEqual(fillet[0].ccw, direction == 'cw')

    def test_walk_seen_from_above_follows_the_direction_setting(self):
        """On a Y-down picture, counter-clockwise as seen means negative shoelace area of the
        picture's numbers. With 'front' the picture's numbers are the program numbers."""
        for y_toward in ('front', 'back'):
            for direction in ('ccw', 'cw'):
                s = settings(y_toward, direction)
                p = progs(s)['B01C']
                pts = polygon(moves(BACKENDS['cnc90'](p, s)))
                screen = pts if y_toward == 'front' else [(x, H - y) for x, y in pts]
                seen_ccw = shoelace(screen) < 0
                self.assertEqual(seen_ccw, direction == 'ccw', (y_toward, direction))

    def test_emitted_path_surrounds_the_shape_in_the_program_frame(self):
        s = settings('front')
        p = progs(s)['B01C']
        pts = polygon(moves(BACKENDS['cnc90'](p, s)))
        outline = segs_to_program(blank(), s, translate(rounded().outline, SX, SY))
        r = s.router_bit.diameter / 2
        for q in pts:
            self.assertAlmostEqual(distance_to_chain(q, outline), r, delta=0.01)
        self.assertTrue(inside((SX + 300, H - (SY + 100)), pts))         # shape centre
        self.assertTrue(inside((SX + 150, H - (SY + 40)), pts))          # its screw hole
        self.assertTrue(inside((SX + 590, H - (SY + 10)), pts))          # square corner, front
        self.assertFalse(inside((SX + 599, H - (SY + 199)), pts))        # cut-off by the fillet
        for corner in ((1, 1), (W - 1, 1), (1, H - 1), (W - 1, H - 1)):
            self.assertFalse(inside(corner, pts))

    def test_preview_cut_path_has_the_emitted_numbers(self):
        s = settings('front')
        b = blank()
        plan = Plan([PanelPlan('P1', [b])])
        pr = {p.name: p for p in plan_programs(plan, s)}
        data = preview_data(plan, list(pr.values()), s)
        mv = moves(BACKENDS['cnc90'](pr['B01C'], s))
        toks = parse(data['blanks'][0]['shapes'][0]['cut_path'])
        n = len(toks)
        # the program repeats the contour per pass; the first pass is G88 + (G1 feed) + segs
        first = mv[1:]
        if first[0][0] == 'G1' and first[0][1:3] == mv[0][1:3]:
            first = first[1:]                   # the feed change G1 to the start point
        self.assertEqual(len(pr['B01C'].ops[0].segs), n - 1)
        self.assertAlmostEqual(toks[0][1], mv[0][1], delta=0.0015)
        self.assertAlmostEqual(toks[0][2], mv[0][2], delta=0.0015)
        for tok, (code, x, y, u) in zip(toks[1:], first[:n - 1]):
            self.assertAlmostEqual(tok[-2], x, delta=0.0015)
            self.assertAlmostEqual(tok[-1], y, delta=0.0015)
            if code in ('G2', 'G3'):
                self.assertEqual(tok[0], 'A')
                self.assertAlmostEqual(tok[1], u, delta=0.0015)
                self.assertEqual(tok[3], 1 if code == 'G3' else 0)     # sweep 1 = G3 in Y-down
            else:
                self.assertEqual(tok[0], 'L')
        # holes drawn at the drilled numbers
        jb = data['blanks'][0]
        self.assertEqual([(h['x'], h['y']) for h in jb['fix']],
                         [(o.x, o.y) for o in pr['B01D'].ops if o.tool == 1])

    def test_picture_is_the_same_in_both_settings(self):
        """Only the numbers change: the drawing of the blank does not."""
        b = blank()
        plan = Plan([PanelPlan('P1', [b])])
        out = {}
        for y_toward in ('front', 'back'):
            s = settings(y_toward)
            out[y_toward] = preview_data(plan, plan_programs(plan, s), s)['blanks'][0]
        f, k = out['front'], out['back']
        self.assertEqual(f['shapes'][0]['path'], k['shapes'][0]['path'])
        self.assertEqual(f['shapes'][0]['cut_path'], k['shapes'][0]['cut_path'])
        self.assertEqual(f['fix'], k['fix'])
        self.assertEqual(f['screw'], k['screw'])

    def test_panel_view_does_not_change(self):
        b = blank()
        plan = Plan([PanelPlan('P1', [b])])
        pans = []
        for y_toward in ('front', 'back'):
            s = settings(y_toward)
            pans.append(preview_data(plan, plan_programs(plan, s), s)['panels'])
        self.assertEqual(pans[0], pans[1])

    def test_to_program_is_its_own_inverse(self):
        s, b = settings('front'), blank()
        self.assertEqual(to_program(b, s, 10, 20), (10, H - 20))
        self.assertEqual(to_program(b, s, *to_program(b, s, 10, 20)), (10, 20))
        self.assertEqual(to_program(b, settings('back'), 10, 20), (10, 20))


class CutterOutsideBlankFrontTests(unittest.TestCase):
    def test_shape_near_the_front_edge_warns_with_program_y_near_the_blank_height(self):
        s = settings('front')
        d = s.router_bit.diameter
        pr = progs(s, blank(y=3))           # 3 mm from the front edge (layout y = 3)
        ws = [w for w in pr['B01C'].warnings if 'cutter reaches' in w]
        self.assertEqual(len(ws), 1, ws)
        m = re.search(r'Y(-?[\d.]+)\.\.(-?[\d.]+),', ws[0])
        self.assertEqual([float(m.group(1)), float(m.group(2))],
                         [round(H - 203 - d, 1), round(H - 3 + d, 1)])
        self.assertGreater(float(m.group(2)), H)            # past the front edge

    def test_shape_near_the_back_edge_warns_with_program_y_below_zero(self):
        s = settings('front')
        pr = progs(s, blank(y=H - 203))     # 3 mm from the back edge
        ws = [w for w in pr['B01C'].warnings if 'cutter reaches' in w]
        self.assertEqual(len(ws), 1, ws)
        m = re.search(r'Y(-?[\d.]+)\.\.', ws[0])
        self.assertLess(float(m.group(1)), 0)

    def test_inside_gives_no_warning(self):
        self.assertEqual(progs(settings('front'))['B01C'].warnings, [])


class YTowardSettingTests(unittest.TestCase):
    def test_validated(self):
        s = Settings()
        s.machine.y_toward = 'up'
        with self.assertRaises(SettingsError) as cm:
            s.validate()
        self.assertEqual(cm.exception.field, 'machine.y_toward')
        for v in ('front', 'back'):
            s.machine.y_toward = v
            s.validate()

    def test_saved_and_loaded(self):
        s = settings('back')
        self.assertEqual(Settings.from_dict(s.to_dict()).machine.y_toward, 'back')
        self.assertEqual(s.to_dict()['machine']['y_toward'], 'back')

    def test_old_project_without_it_loads_with_the_default(self):
        old = Settings().to_dict()
        del old['machine']['y_toward']
        self.assertEqual(Settings.from_dict(old).machine.y_toward, 'front')
        self.assertEqual(Settings.from_dict({'machine': {'frame_x': 3000}}).machine.y_toward,
                         'front')


class RunSheetOriginTests(unittest.TestCase):
    def sheet(self, y_toward):
        s = settings(y_toward)
        plan = Plan([PanelPlan('P1', [blank()])])
        data = preview_data(plan, plan_programs(plan, s), s)
        return data, _runsheet(data, {'name': 'T'})

    def test_front_origin_top_left(self):
        data, html = self.sheet('front')
        self.assertIn('X0 Y0', html)
        self.assertIn('back-left corner', html)
        self.assertIn('Y grows toward the front', html)
        self.assertIn('<circle class="org" cx="0" cy="0"', _blank_svg(data['blanks'][0], 'front'))

    def test_back_origin_bottom_left(self):
        data, html = self.sheet('back')
        self.assertIn('front-left corner', html)
        self.assertIn('Y grows toward the back', html)
        self.assertIn(f'<circle class="org" cx="0" cy="{H}"', _blank_svg(data['blanks'][0], 'back'))


if __name__ == '__main__':
    unittest.main()
