import json
import re
import unittest

from nesting.dxf import Hole
from nesting.geometry import Arc
from nesting.layout import PanelPlan, Plan, footprint, to_panel
from nesting.preview import _path, preview_data
from nesting.program import DrillOp, plan_programs
from nesting.settings import Settings
from test_nesting_program import by_name, hand_blank, plan_for, rect


def parse(d):
    """Tokens of a path string: ('M'|'L', x, y) or ('A', r, large, sweep, x, y)."""
    out = []
    for tok in re.findall(r'[MLA][^MLA]*', d):
        parts = tok[1:].replace(',', ' ').split()
        if tok[0] == 'A':
            out.append(('A', float(parts[0]), int(parts[3]), int(parts[4]),
                        float(parts[5]), float(parts[6])))
        else:
            out.append((tok[0], float(parts[0]), float(parts[1])))
    return out


def points(d):
    return [(t[-2], t[-1]) for t in parse(d)]


def build(*shapes, settings=None):
    plan, s = plan_for(*shapes, settings=settings)
    progs = plan_programs(plan, s)
    return plan, progs, s, preview_data(plan, progs, s)


def fix_ops(progs, s):
    """The fixing holes of B01D: the ops with the fixing tool (default settings: tools differ)."""
    return [o for o in by_name(progs)['B01D'].ops if o.tool == s.drill_fix.tool]


def screw_ops(progs, s):
    return [o for o in by_name(progs)['B01D'].ops if o.tool == s.drill_screw.tool]


def close(tc, a, b, ordered=False):
    tc.assertEqual(len(a), len(b))
    for p, q in zip(a if ordered else sorted(a), b if ordered else sorted(b)):
        tc.assertAlmostEqual(p[0], q[0], delta=0.001)
        tc.assertAlmostEqual(p[1], q[1], delta=0.001)


class PreviewTests(unittest.TestCase):
    def test_blank_holes_equal_drill_ops(self):
        # default y_toward 'front': the SVG numbers of the job view are the program numbers
        plan, progs, s, data = build(rect('a', 1000, 230), rect('b', 900, 200))
        (b,) = data['blanks']
        self.assertEqual(data['y_toward'], 'front')
        pr = by_name(progs)
        self.assertEqual([p.name for p in progs], ['B01D', 'B01C'])
        self.assertEqual(len(pr['B01D'].ops), len(b['fix']) + len(b['screw']))
        close(self, [(h['x'], h['y']) for h in b['fix']], [(o.x, o.y) for o in fix_ops(progs, s)])
        close(self, [(h['x'], h['y']) for h in b['screw']], [(o.x, o.y) for o in screw_ops(progs, s)])

    def test_blank_holes_equal_drill_ops_y_toward_back(self):
        s = Settings()
        s.machine.y_toward = 'back'
        plan, progs, s, data = build(rect('a', 1000, 230), rect('b', 900, 200), settings=s)
        (b,) = data['blanks']
        self.assertEqual(data['y_toward'], 'back')
        H = b['height']
        pr = by_name(progs)
        close(self, [(h['x'], H - h['y']) for h in b['fix']], [(o.x, o.y) for o in fix_ops(progs, s)])
        close(self, [(h['x'], H - h['y']) for h in b['screw']], [(o.x, o.y) for o in screw_ops(progs, s)])

    def test_panel_holes_are_the_drill_ops_mapped_onto_the_panel(self):
        s = Settings()
        s.panel.length, s.panel.width = 1220, 2440       # forces a turned blank
        plan, progs, s, data = build(rect('a', 2000, 230), settings=s)
        blank = plan.blanks[0]
        self.assertTrue(blank.rotated)
        pb = data['panels'][0]['blanks'][0]
        pw = s.panel.width
        pr = by_name(progs)
        # program Y runs from the back (blank height - layout y): map back, then onto the panel
        H = blank.height
        close(self, [(h['x'], pw - h['y']) for h in pb['fix']],
              [to_panel(blank, o.x, H - o.y) for o in fix_ops(progs, s)])
        close(self, [(h['x'], pw - h['y']) for h in pb['screw']],
              [to_panel(blank, o.x, H - o.y) for o in screw_ops(progs, s)])
        close(self, [(h['x'], pw - h['y']) for h in pb['fix']],
              [to_panel(blank, h.x, h.y) for h in blank.fix_holes])
        self.assertEqual((pb['w'], pb['h']), footprint(blank))
        self.assertEqual((pb['width'], pb['height']), (blank.width, blank.height))

    def test_op_off_the_layout_is_an_error(self):
        plan, progs, s, _ = build(rect('a', 1000, 230))
        progs[0].ops[0].x += 5
        with self.assertRaises(ValueError):
            preview_data(plan, progs, s)

    def merged(self):
        s = Settings()
        s.drill_screw.tool, s.drill_screw.diameter = s.drill_fix.tool, s.drill_fix.diameter
        plan, progs, s, _ = build(rect('a', 1000, 230), settings=s)
        return plan, progs, s

    def check_split(self, plan, progs, s):
        b = plan.blanks[0]
        out = preview_data(plan, progs, s)['blanks'][0]
        H = b.height
        close(self, [(h['x'], H - h['y']) for h in out['fix']], [(h.x, h.y) for h in b.fix_holes])
        close(self, [(h['x'], H - h['y']) for h in out['screw']], [(h.x, h.y) for h in b.screw_holes])

    def test_merged_drills_split_fix_and_screw(self):
        plan, progs, s = self.merged()
        self.assertEqual(len(progs[0].ops), 6)
        self.check_split(plan, progs, s)

    def test_merged_split_independent_of_op_order(self):
        plan, progs, s = self.merged()
        progs[0].ops.reverse()
        self.check_split(plan, progs, s)

    def test_hole_matching_both_kinds_is_an_error(self):
        plan, progs, s, _ = build(rect('a', 1000, 230))
        b = plan.blanks[0]
        b.screw_holes[0] = Hole(b.fix_holes[0].x, b.fix_holes[0].y, 3)
        with self.assertRaises(ValueError):
            preview_data(plan, progs, s)

    def test_cut_path_matches_contour_ops(self):
        plan, progs, s, data = build(rect('a', 1000, 230))
        cut = by_name(progs)['B01C']
        b = data['blanks'][0]
        shape_ops = [o for o in cut.ops if ' a #1 pass ' in o.label]
        self.assertEqual(len(shape_ops), 3)
        self.assertEqual(len(cut.ops), 3)            # no other contour: no template outline
        self.match(b['shapes'][0]['cut_path'], shape_ops[-1].segs, None)

    def test_cut_path_matches_contour_ops_y_toward_back(self):
        s = Settings()
        s.machine.y_toward = 'back'
        plan, progs, s, data = build(rect('a', 1000, 230), settings=s)
        cut = by_name(progs)['B01C']
        b = data['blanks'][0]
        self.match(b['shapes'][0]['cut_path'], cut.ops[-1].segs, b['height'])

    def match(self, d, segs, flip):
        """The SVG path has the program's numbers (flip=None) or the flipped ones (flip=h)."""
        def fy(y):
            return y if flip is None else flip - y
        toks = parse(d)
        self.assertEqual(toks[0][0], 'M')
        self.assertEqual(len(toks) - 1, len(segs))
        self.assertAlmostEqual(toks[0][1], segs[0].a[0], delta=0.001)
        self.assertAlmostEqual(toks[0][2], fy(segs[0].a[1]), delta=0.001)
        arcs = 0
        for tok, sg in zip(toks[1:], segs):
            self.assertAlmostEqual(tok[-2], sg.b[0], delta=0.001)
            self.assertAlmostEqual(tok[-1], fy(sg.b[1]), delta=0.001)
            if isinstance(sg, Arc):
                arcs += 1
                self.assertEqual(tok[0], 'A')
                self.assertAlmostEqual(tok[1], sg.radius, delta=0.001)
                # SVG sweep 1 = increasing angle in the numbers written
                self.assertEqual(tok[3], int(sg.ccw) if flip is None else int(not sg.ccw))
            else:
                self.assertEqual(tok[0], 'L')
        self.assertGreater(arcs, 0)          # the offset contour has corner arcs

    def test_quarter_circle_flip(self):
        for ccw, sweep in ((True, 0), (False, 1)):
            a, b = ((10, 0), (0, 10)) if ccw else ((0, 10), (10, 0))
            tok = parse(_path([Arc(a, b, (0, 0), 10, ccw)], 100))[1]
            self.assertEqual(tok[2:4], (0, sweep))
            self.assertEqual(tok[4:], (b[0], 100 - b[1]))

    def test_large_arc_flag(self):
        # three quarters of a circle, counter-clockwise
        d = _path([Arc((10, 0), (0, -10), (0, 0), 10, True)], 100)
        self.assertEqual(parse(d)[1][2], 1)

    def test_outline_path_is_unoffset_layout(self):
        plan, progs, s, data = build(rect('a', 1000, 230))
        for sh in (data['blanks'][0]['shapes'][0], data['panels'][0]['blanks'][0]['shapes'][0]):
            xs = [p[0] for p in points(sh['path'])]
            ys = [p[1] for p in points(sh['path'])]
            self.assertAlmostEqual(sorted([max(xs) - min(xs), max(ys) - min(ys)])[1], 1000, delta=0.01)
            self.assertAlmostEqual(sorted([max(xs) - min(xs), max(ys) - min(ys)])[0], 230, delta=0.01)

    def test_json_serialisable_and_no_template(self):
        _, _, _, data = build(rect('a', 1000, 230), rect('b', 900, 200))
        text = json.dumps(data)
        self.assertNotIn('template', text.lower())

    def test_y_flipped_on_the_panel(self):
        plan, progs, s, data = build(rect('a', 1000, 230))
        b = plan.blanks[0]
        out = data['panels'][0]['blanks'][0]
        self.assertAlmostEqual(out['y'], s.panel.width - (b.y + footprint(b)[1]))
        self.assertAlmostEqual(out['x'], b.x)
        self.assertEqual(data['panel'], {'length': 2440, 'width': 1220, 'thickness': 18,
                                         'edge': 10, 'kerf': 4})
        self.assertEqual(data['frame'], {'x': 3072, 'y': 787})
        self.assertEqual(data['y_toward'], 'front')

    def test_saw_cuts_in_the_preview(self):
        plan, progs, s, data = build(rect('a', 1000, 230))
        pan, pp = data['panels'][0], plan.panels[0]
        self.assertEqual(len(pan['cuts']), len(pp.cuts))
        pw, k = s.panel.width, s.panel.kerf
        for c, sc in zip(pan['cuts'], pp.cuts):
            self.assertEqual((c['n'], c['stage'], c['axis'], c['at'], c['frees'], c['blanks']),
                             (sc.n, sc.stage, sc.axis, sc.at, sc.frees, sc.blanks))
            x, y, w, h = c['rect']
            if sc.axis == 'x':
                self.assertEqual((x, w, h), (sc.start, sc.end - sc.start, k))
                self.assertAlmostEqual(y, pw - sc.at - k)
            else:
                self.assertEqual((x, w, h), (sc.at, k, sc.end - sc.start))
        self.assertAlmostEqual(pan['waste'], pp.waste(s))
        self.assertAlmostEqual(pan['waste_pct'], 100 * pp.waste(s) / (2440 * 1220))

    def test_turned_blank_keeps_blank_coordinates_in_the_job_view(self):
        s = Settings()
        plan = Plan([PanelPlan('P1', [hand_blank(rotated=True)])])
        progs = plan_programs(plan, s)
        data = preview_data(plan, progs, s)
        b, pb = data['blanks'][0], data['panels'][0]['blanks'][0]
        self.assertEqual((b['width'], b['height'], b['rotated']), (690, 290, True))
        self.assertEqual((pb['w'], pb['h']), (290, 690))
        self.assertEqual(b['fix'], [{'x': 15, 'y': 290 - 15}])
        self.assertEqual(len(b['screw']), 1)

    def test_programs_lines_and_warning(self):
        plan, progs, s, data = build(rect('a', 1000, 230))
        entry = {p['name']: p for p in data['blanks'][0]['programs']}
        self.assertEqual(set(entry), {'B01D', 'B01C'})
        self.assertEqual((entry['B01D']['tool'], entry['B01D']['tools']), (1, [1, 2]))
        self.assertEqual((entry['B01C']['tool'], entry['B01C']['tools']), (66, [66]))
        self.assertEqual(entry['B01D']['kind'], 'drill')
        from nesting.backends import BACKENDS
        for p in progs:
            n = len(BACKENDS['cnc90'](p, s).splitlines())
            self.assertEqual(entry[p.name]['lines'], n)
        self.assertEqual(entry['B01C']['ops'], len(by_name(progs)['B01C'].ops))

    def test_line_warning_added_once(self):
        plan, progs, s, _ = build(rect('a', 1000, 230))
        fix = by_name(progs)['B01D']
        fix.ops.extend(DrillOp(fix.ops[0].x, fix.ops[0].y, 1, 1) for _ in range(300))     # long program
        data = preview_data(plan, progs, s)
        w = next(p for p in data['blanks'][0]['programs'] if p['name'] == 'B01D')
        self.assertGreater(w['lines'], 250)
        self.assertEqual(len([x for x in w['warnings'] if 'lines' in x]), 1)
        self.assertIn(f"{w['lines']} lines, more than 250", w['warnings'])
        self.assertEqual(fix.warnings, [])

    def test_existing_line_warning_not_duplicated(self):
        plan, progs, s, _ = build(rect('a', 1000, 230))
        fix = by_name(progs)['B01D']
        fix.ops.extend(DrillOp(fix.ops[0].x, fix.ops[0].y, 1, 1) for _ in range(300))
        fix.warnings.append('B01D: about 303 lines, over 250')
        w = next(p for p in preview_data(plan, progs, s)['blanks'][0]['programs']
                 if p['name'] == 'B01D')
        self.assertEqual(w['warnings'], ['B01D: about 303 lines, over 250'])

    def test_z_values(self):
        plan, progs, s, data = build(rect('a', 1000, 230))
        z = data['blanks'][0]['z']
        pr = by_name(progs)
        self.assertEqual(set(z), {'stack_top', 'fixing', 'screw', 'shape_cut'})
        self.assertEqual(z['fixing'], fix_ops(progs, s)[0].depth)
        self.assertEqual(z['screw'], screw_ops(progs, s)[0].depth)
        self.assertEqual(z['shape_cut'], pr['B01C'].ops[-1].depth)
        self.assertEqual(z['stack_top'], pr['B01C'].stock[2])
        self.assertEqual((z['stack_top'], z['fixing'], z['screw']), (36, 19, 26))
        self.assertAlmostEqual(z['shape_cut'], 18.5)

    def test_drill_tools_per_hole_kind(self):
        s = Settings()
        s.drill_fix.feed, s.drill_screw.feed = 2.5, 0.75
        plan, progs, s, data = build(rect('a', 1000, 230), settings=s)
        self.assertEqual(data['blanks'][0]['drill_tools'], [
            {'holes': 'fixing', 'count': 4, 'tool': 1, 'diameter': 6, 'feed': 2.5, 'depth': 19},
            {'holes': 'screw', 'count': 2, 'tool': 2, 'diameter': 3, 'feed': 0.75, 'depth': 26}])

    def test_one_drill_program_shows_both_hole_kinds_with_one_tool(self):
        s = Settings()
        s.drill_screw.tool = s.drill_fix.tool
        plan, progs, s, data = build(rect('a', 1000, 230), settings=s)
        b = data['blanks'][0]
        self.assertEqual([p['name'] for p in b['programs']], ['B01D', 'B01C'])
        self.assertEqual(b['programs'][0]['tools'], [1])
        self.assertEqual((len(b['fix']), len(b['screw'])), (4, 2))
        self.assertEqual([t['tool'] for t in b['drill_tools']], [1, 1])

    def test_problems_passed_through(self):
        plan, progs, s, _ = build(rect('a', 1000, 230))
        plan.problems.append('x')
        self.assertEqual(preview_data(plan, progs, s)['problems'], ['x'])


if __name__ == '__main__':
    unittest.main()
