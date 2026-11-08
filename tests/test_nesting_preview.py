import json
import re
import unittest

from nesting.dxf import Hole
from nesting.geometry import Arc
from nesting.layout import Plan, footprint, to_panel
from nesting.preview import _path, preview_data
from nesting.program import DrillOp, plan_programs
from nesting.settings import Settings
from test_nesting_program import by_name, hand_panel, plan_for, rect


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


def close(tc, a, b, ordered=False):
    tc.assertEqual(len(a), len(b))
    for p, q in zip(a if ordered else sorted(a), b if ordered else sorted(b)):
        tc.assertAlmostEqual(p[0], q[0], delta=0.001)
        tc.assertAlmostEqual(p[1], q[1], delta=0.001)


class PreviewTests(unittest.TestCase):
    def test_holes_equal_drill_ops(self):
        plan, progs, s, data = build(rect('a', 1000, 230), rect('b', 900, 200))
        pw = s.panel.width
        tpls = [t for p in data['panels'] for t in p['templates']]
        fix = [(h['x'], pw - h['y']) for t in tpls for h in t['fix']]
        screw = [(h['x'], pw - h['y']) for t in tpls for h in t['screw']]
        pr = by_name(progs)
        close(self, fix, [(o.x, o.y) for o in pr['N1F'].ops])
        close(self, screw, [(o.x, o.y) for o in pr['N1S'].ops])

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
        t = plan.panels[0].templates[0]
        pw = s.panel.width
        out = preview_data(plan, progs, s)['panels'][0]['templates'][0]
        close(self, [(h['x'], pw - h['y']) for h in out['fix']],
              [to_panel(t, h.x, h.y) for h in t.fix_holes])
        close(self, [(h['x'], pw - h['y']) for h in out['screw']],
              [to_panel(t, h.x, h.y) for h in t.screw_holes])

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
        t = plan.panels[0].templates[0]
        t.screw_holes[0] = Hole(t.fix_holes[0].x, t.fix_holes[0].y, 3)
        with self.assertRaises(ValueError):
            preview_data(plan, progs, s)

    def test_cut_path_matches_contour_ops(self):
        plan, progs, s, data = build(rect('a', 1000, 230))
        pw = s.panel.width
        cut = by_name(progs)['N1C']
        t = data['panels'][0]['templates'][0]
        shape_op = next(o for o in cut.ops if o.label.endswith('a #1'))
        outline_op = next(o for o in cut.ops if o.label.endswith('outline'))
        self.match(t['shapes'][0]['cut_path'], shape_op.segs, pw)
        self.match(t['cut_path'], outline_op.segs, pw)

    def match(self, d, segs, pw):
        toks = parse(d)
        self.assertEqual(toks[0][0], 'M')
        self.assertEqual(len(toks) - 1, len(segs))
        self.assertAlmostEqual(toks[0][1], segs[0].a[0], delta=0.001)
        self.assertAlmostEqual(toks[0][2], pw - segs[0].a[1], delta=0.001)
        arcs = 0
        for tok, sg in zip(toks[1:], segs):
            self.assertAlmostEqual(tok[-2], sg.b[0], delta=0.001)
            self.assertAlmostEqual(tok[-1], pw - sg.b[1], delta=0.001)
            if isinstance(sg, Arc):
                arcs += 1
                self.assertEqual(tok[0], 'A')
                self.assertAlmostEqual(tok[1], sg.radius, delta=0.001)
                self.assertEqual(tok[3], 0 if sg.ccw else 1)
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
        sh = data['panels'][0]['templates'][0]['shapes'][0]
        xs = [p[0] for p in points(sh['path'])]
        ys = [p[1] for p in points(sh['path'])]
        self.assertAlmostEqual(sorted([max(xs) - min(xs), max(ys) - min(ys)])[1], 1000, delta=0.01)
        self.assertAlmostEqual(sorted([max(xs) - min(xs), max(ys) - min(ys)])[0], 230, delta=0.01)

    def test_json_serialisable(self):
        _, _, _, data = build(rect('a', 1000, 230), rect('b', 900, 200))
        json.dumps(data)

    def test_y_flipped(self):
        plan, progs, s, data = build(rect('a', 1000, 230))
        t = plan.panels[0].templates[0]
        out = data['panels'][0]['templates'][0]
        self.assertAlmostEqual(out['y'], s.panel.width - (t.y + footprint(t)[1]))
        self.assertAlmostEqual(out['x'], t.x)
        self.assertEqual(data['panel'], {'length': s.panel.length, 'width': s.panel.width})

    def test_rotated_template(self):
        s = Settings()
        plan = Plan([hand_panel('P1', rotated=True)])
        progs = plan_programs(plan, s)
        data = preview_data(plan, progs, s)
        t = data['panels'][0]['templates'][0]
        self.assertEqual((t['w'], t['h']), (290, 690))
        self.assertEqual(len(t['fix']), 1)
        self.assertEqual(len(t['screw']), 1)

    def test_programs_lines_and_warning(self):
        plan, progs, s, data = build(rect('a', 1000, 230))
        entry = {p['name']: p for p in data['panels'][0]['programs']}
        self.assertEqual(set(entry), {'N1F', 'N1S', 'N1C'})
        from nesting.backends import BACKENDS
        for p in progs:
            n = len(BACKENDS['cnc90'](p, s).splitlines())
            self.assertEqual(entry[p.name]['lines'], n)
        self.assertEqual(entry['N1C']['ops'], len(by_name(progs)['N1C'].ops))

    def test_line_warning_added_once(self):
        plan, progs, s, _ = build(rect('a', 1000, 230))
        fix = by_name(progs)['N1F']
        fix.ops.extend(DrillOp(fix.ops[0].x, fix.ops[0].y, 1, 1) for _ in range(300))     # long program
        data = preview_data(plan, progs, s)
        w = next(p for p in data['panels'][0]['programs'] if p['name'] == 'N1F')
        self.assertGreater(w['lines'], 250)
        self.assertEqual(len([x for x in w['warnings'] if 'lines' in x]), 1)
        self.assertIn(f"{w['lines']} lines, more than 250", w['warnings'])
        self.assertEqual(fix.warnings, [])

    def test_existing_line_warning_not_duplicated(self):
        plan, progs, s, _ = build(rect('a', 1000, 230))
        fix = by_name(progs)['N1F']
        fix.ops.extend(DrillOp(fix.ops[0].x, fix.ops[0].y, 1, 1) for _ in range(300))
        fix.warnings.append('N1F: about 303 lines, over 250')
        w = next(p for p in preview_data(plan, progs, s)['panels'][0]['programs']
                 if p['name'] == 'N1F')
        self.assertEqual(w['warnings'], ['N1F: about 303 lines, over 250'])

    def test_z_values(self):
        plan, progs, s, data = build(rect('a', 1000, 230))
        z = data['panels'][0]['z']
        pr = by_name(progs)
        self.assertEqual(z['fixing'], pr['N1F'].ops[0].depth)
        self.assertEqual(z['screw'], pr['N1S'].ops[0].depth)
        self.assertEqual(z['shape_cut'], pr['N1C'].ops[0].depth)
        self.assertEqual(z['template_cut'], pr['N1C'].ops[-1].depth)
        self.assertIn('stack_top', z)

    def test_problems_passed_through(self):
        plan, progs, s, _ = build(rect('a', 1000, 230))
        plan.problems.append('x')
        self.assertEqual(preview_data(plan, progs, s)['problems'], ['x'])


if __name__ == '__main__':
    unittest.main()
