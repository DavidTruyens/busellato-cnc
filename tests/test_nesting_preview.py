import json
import re
import unittest

from nesting.dxf import Hole
from nesting.geometry import Line, sample
from nesting.layout import ShapeEntry, build_plan, footprint
from nesting.preview import preview_data
from nesting.program import ContourOp, DrillOp, plan_programs
from nesting.settings import Settings
from test_nesting_program import by_name, hand_panel, plan_for, rect
from nesting.layout import Plan


def points(d):
    return [(float(a), float(b)) for a, b in re.findall(r'[ML]\s*(-?[\d.]+),\s*(-?[\d.]+)', d)]


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

    def test_holes_follow_ops_not_layout(self):
        plan, progs, s, _ = build(rect('a', 1000, 230))
        for o in progs[0].ops:
            o.x += 5
        data = preview_data(plan, progs, s)
        pw = s.panel.width
        got = [(h['x'], pw - h['y']) for t in data['panels'][0]['templates'] for h in t['fix']]
        close(self, got, [(o.x, o.y) for o in progs[0].ops])

    def test_merged_drills_split_fix_and_screw(self):
        s = Settings()
        s.drill_screw.tool, s.drill_screw.diameter = s.drill_fix.tool, s.drill_fix.diameter
        plan, progs, s, data = build(rect('a', 1000, 230), settings=s)
        t = data['panels'][0]['templates'][0]
        self.assertEqual((len(t['fix']), len(t['screw'])), (4, 2))

    def test_cut_path_matches_contour_ops(self):
        plan, progs, s, data = build(rect('a', 1000, 230))
        pw = s.panel.width
        cut = by_name(progs)['N1C']
        t = data['panels'][0]['templates'][0]
        shape_op = next(o for o in cut.ops if o.label.endswith('a #1'))
        outline_op = next(o for o in cut.ops if o.label.endswith('outline'))
        flip = lambda pts: [(x, pw - y) for x, y in pts]
        close(self, flip(points(t['shapes'][0]['cut_path'])), sample(shape_op.segs), ordered=True)
        close(self, flip(points(t['cut_path'])), sample(outline_op.segs), ordered=True)

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
        fix.ops.extend(DrillOp(1, 1, 1, 1) for _ in range(300))     # long program
        data = preview_data(plan, progs, s)
        w = next(p for p in data['panels'][0]['programs'] if p['name'] == 'N1F')
        self.assertGreater(w['lines'], 250)
        self.assertEqual(len([x for x in w['warnings'] if 'lines' in x]), 1)
        self.assertIn(f"{w['lines']} lines, more than 250", w['warnings'])
        self.assertEqual(fix.warnings, [])

    def test_existing_line_warning_not_duplicated(self):
        plan, progs, s, _ = build(rect('a', 1000, 230))
        fix = by_name(progs)['N1F']
        fix.ops.extend(DrillOp(1, 1, 1, 1) for _ in range(300))
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
