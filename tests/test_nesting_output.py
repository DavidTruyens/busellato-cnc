import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nesting.backends import BACKENDS
from nesting.dxf import read_dxf
from nesting.layout import ShapeEntry, build_plan
from nesting.output import write_output
from nesting.preview import pocket_groups_data, preview_data
from nesting.program import plan_programs
from nesting.settings import Settings
from helpers import put_bit
from test_nesting_program import pocket_shape, rect, rect_loop

repo = Path(__file__).resolve().parent.parent


class OutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Settings()
        cls.entries = [ShapeEntry(read_dxf(p)) for p in sorted((repo / 'plates').glob('*.dxf'))]
        cls.plan = build_plan(cls.entries, cls.s)
        cls.progs = plan_programs(cls.plan, cls.s)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / 'job'

    def write(self, **kw):
        return write_output(self.out, self.plan, self.progs, self.s, kw.pop('project', {'name': 'x'}), **kw)

    def test_files_written_and_loader_present(self):
        files = self.write()
        names = {p.name for p in files}
        for n in ('LOAD.BAT', 'L1.BAT', 'COLLECT.BAT', 'C1.BAT', 'PROJECT.json', 'RUNSHEET.html'):
            self.assertIn(n, names)
        for p in self.progs:
            self.assertIn(p.name, names)
        self.assertEqual({p.name for p in self.out.iterdir()}, names)
        self.assertTrue(all(p.parent == self.out for p in files))
        self.assertEqual(len(files), len(set(files)))
        load = (self.out / 'LOAD.BAT').read_bytes().decode('ascii')
        for p in self.progs:
            self.assertIn(p.name.upper(), load)
        text = (self.out / self.progs[0].name).read_bytes()
        self.assertEqual(text, BACKENDS['cnc90'](self.progs[0], self.s).encode('ascii'))
        self.assertIn(b'\r\n', text)

    def test_existing_folder_is_an_error(self):
        self.out.mkdir()
        (self.out / 'keep.txt').write_text('keep')
        with self.assertRaises(FileExistsError):
            self.write()
        self.assertEqual([p.name for p in self.out.iterdir()], ['keep.txt'])
        self.assertEqual((self.out / 'keep.txt').read_text(), 'keep')

    def test_loader_failure_surfaces_stderr_and_cleans_up(self):
        bad = self.progs[0]
        orig = bad.name
        bad.name = 'Q' + orig[1:]          # no SRG folder Q on the machine
        try:
            with self.assertRaises(RuntimeError) as cm:
                self.write()
        finally:
            bad.name = orig
        self.assertIn('folder', str(cm.exception))
        self.assertFalse(self.out.exists())
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_program_files_pass_check_cnc90(self):
        self.write()
        paths = [str(self.out / p.name) for p in self.progs]
        r = subprocess.run([sys.executable, str(repo / 'tools' / 'check_cnc90.py'), *paths],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_project_json_roundtrips_settings(self):
        self.write(project={'name': 'job <1>', 'shapes': ['a', 'b']})
        data = json.loads((self.out / 'PROJECT.json').read_text(encoding='utf-8'))
        self.assertEqual(data['settings'], self.s.to_dict())
        self.assertEqual(data['project'], {'name': 'job <1>', 'shapes': ['a', 'b']})

    def test_runsheet_mentions_every_program_and_shape(self):
        self.write(project={'name': 'job <b>&'})
        html = (self.out / 'RUNSHEET.html').read_text(encoding='utf-8')
        self.assertIn('<meta charset', html)
        self.assertIn('not yet run on the machine', html.lower())
        for p in self.progs:
            self.assertIn(p.name, html)
        data = preview_data(self.plan, self.progs, self.s)
        for panel in data['panels']:
            self.assertIn(f'Panel {panel["id"]}', html)
            for b in panel['blanks']:
                for sh in b['shapes']:
                    self.assertIn(sh['name'], html)
                    self.assertIn(sh['path'], html)       # drawn on the panel ...
        for b in data['blanks']:
            self.assertIn(f'Blank {b["id"]} (from panel {b["panel"]})', html)
            for sh in b['shapes']:
                self.assertIn(sh['path'], html)           # ... and on its own blank page
            for v in b['z'].values():
                self.assertIn(f'{v:g}', html)
        self.assertIn('<svg', html)
        self.assertNotIn('http://', html.replace('http://www.w3.org/2000/svg', ''))
        self.assertNotIn('https://', html)
        self.assertNotIn('job <b>', html)
        self.assertIn('job &lt;b&gt;&amp;', html)

    def test_runsheet_has_the_saw_cut_list_per_panel(self):
        html = self._sheet(self.s, self.progs)
        for pan in self.plan.panels:
            section = html.split(f'<h2>Panel {pan.id}:')[1].split('</section>')[0]
            rows = re.findall(r'<tr><td class="num">(\d+)</td><td class="num">(\d)</td>'
                              r'<td>[^<]*</td><td>([XY]) = ([\d.]+)</td>', section)
            self.assertEqual([(int(n), int(st), float(at)) for n, st, _, at in rows],
                             [(c.n, c.stage, round(c.at, 1)) for c in pan.cuts])
            for c, row in zip(pan.cuts, rows):
                self.assertEqual(row[2], 'Y' if c.axis == 'x' else 'X')
            for b in pan.blanks:
                self.assertIn(f'<td>{b.id}</td><td>{b.width:g} x {b.height:g}</td>', section)

    def test_runsheet_has_no_template_wording(self):
        html = self._sheet(self.s, self.progs).lower()
        self.assertNotIn('template', html)
        self.assertNotIn('outline: cut last', html)
        self.assertIn('frame is not cut', html)
        self.assertIn('placeholder', html)

    def test_loader_and_project_have_the_d_and_c_programs(self):
        files = {p.name: p for p in self.write()}
        progs = sorted(p.name for p in self.progs)
        self.assertEqual(progs, sorted(f'B0{n}{k}' for n in range(1, 7) for k in 'DPC'))
        for n in progs:
            self.assertIn(n, files)
        self.assertFalse([n for n in files if re.fullmatch(r'B\d\d[FS]', n)])
        load = files['LOAD.BAT'].read_text()
        for n in progs:
            self.assertIn(f'CALL A:\\L1.BAT B {n[1:]} {n}', load)
        collect = files['COLLECT.BAT'].read_text()
        self.assertIn('CALL A:\\C1.BAT B 01D', collect)
        self.assertNotRegex(load + collect, r'B ?\d\d[FS]\b')
        proj = json.loads(files['PROJECT.json'].read_text())
        self.assertEqual(proj['settings']['drill_fix']['tool'], 1)
        self.assertEqual(proj['settings']['drill_screw']['tool'], 2)

    def test_runsheet_blank_steps_in_order(self):
        html = self._sheet(self.s, self.progs)
        section = html.split('<h2>Blank B01 ')[1].split('</section>')[0]
        order = [section.index(x) for x in ('origin corner', 'Clamp it', 'Run <b>B01D</b>',
                                            'Screw the blank', 'each shape',
                                            'Take the clamps off', 'Run <b>B01P</b>',
                                            'Run <b>B01C</b>', 'Unscrew')]
        self.assertEqual(order, sorted(order))
        self.assertIn('the blank still clamped: every hole', section)

    def test_runsheet_lists_each_drill_tool_with_diameter_and_feed(self):
        m = Settings()
        put_bit(m, 10, diameter=6, plunge_feed=2.5)
        put_bit(m, 2, diameter=3, plunge_feed=0.75)
        m.drill_fix.tool, m.drill_screw.tool = 10, 2
        plan = build_plan(self.entries, m)
        progs = plan_programs(plan, m)
        html = self._sheet(m, progs, plan)
        section = html.split('<h2>Blank B01 ')[1].split('</section>')[0]
        self.assertIn('<tr><td>B01D</td><td>T10, T2</td><td>Fixing and screw holes</td></tr>', section)
        self.assertIn('<tr><td>B01C</td><td>T66</td>', section)
        self.assertIn('Feed (m/min, not written)', section)
        self.assertRegex(section, r'<tr><td>fixing</td><td class="num">4</td><td>T10</td>'
                                  r'<td class="num">6</td><td class="num">2.5</td><td class="num">19</td></tr>')
        self.assertRegex(section, r'<tr><td>screw</td><td class="num">\d+</td><td>T2</td>'
                                  r'<td class="num">3</td><td class="num">0.75</td><td class="num">26</td></tr>')

    def test_runsheet_has_no_separate_fixing_or_screw_programs(self):
        same = Settings()
        same.drill_screw.tool = same.drill_fix.tool
        for st in (self.s, same):
            plan = build_plan(self.entries, st)
            progs = plan_programs(plan, st)
            html = self._sheet(st, progs, plan)
            self.assertIsNone(re.search(r'B\d\d[FS]\b', html))
            self.assertNotIn('merged into', html)
            self.assertIn('Run <b>B01D</b>', html)

    def _sheet(self, settings, progs, plan=None):
        out = Path(self.tmp.name) / f'sheet{len(list(Path(self.tmp.name).iterdir()))}'
        write_output(out, plan or self.plan, progs, settings, {})
        return (out / 'RUNSHEET.html').read_text(encoding='utf-8')


    def test_failure_after_loader_leaves_nothing_and_retry_works(self):
        with mock.patch('nesting.output.preview_data', side_effect=ValueError('boom')):
            with self.assertRaises(ValueError):
                self.write()
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])
        files = self.write()
        self.assertTrue(files)

    def test_existing_file_is_an_error_and_unchanged(self):
        self.out.write_text('keep')
        with self.assertRaises(FileExistsError):
            self.write()
        self.assertEqual(self.out.read_text(), 'keep')
        self.assertEqual([p.name for p in Path(self.tmp.name).iterdir()], ['job'])

    def test_returned_paths_exist_inside_out_dir(self):
        for p in self.write():
            self.assertTrue(p.is_dir() if p.name == 'DISKETTE' else p.is_file(), p)
            self.assertEqual(p.parent, self.out)

    def test_heights_say_depth_is_below_top_of_stack(self):
        self.write()
        html = (self.out / 'RUNSHEET.html').read_text(encoding='utf-8')
        self.assertIn('below the top of the stack', html)

    def test_runsheet_pockets_steps_table_and_drawing(self):
        self.write()
        html = (self.out / 'RUNSHEET.html').read_text(encoding='utf-8')
        data = preview_data(self.plan, self.progs, self.s)
        self.assertTrue(data['pocket_groups'])
        self.assertIn('Run <b>B01P</b>', html)
        self.assertLess(html.index('Run <b>B01D</b>'), html.index('Run <b>B01P</b>'))
        self.assertLess(html.index('Run <b>B01P</b>'), html.index('Run <b>B01C</b>'))
        self.assertIn('<b>Pockets</b>', html)
        g = data['pocket_groups'][0]
        self.assertIn(f'<td>{g["id"]}</td><td><span class="sw" style="background:{g["color"]}">', html)
        self.assertIn('<th>Tool</th><th>Tool Ø (mm)</th><th>Depth (mm)</th>', html)
        self.assertIn(f'<td>T{g["tool"]}</td><td class="num">{g["diameter"]:g}</td>', html)
        self.assertIn(f'<path class="pocket" fill="{g["color"]}"', html)

    def test_runsheet_without_pockets_has_no_pocket_table(self):
        plan = build_plan([ShapeEntry(rect('a', 1000, 230))], self.s)
        html = self._sheet(self.s, plan_programs(plan, self.s), plan)
        self.assertNotIn('<b>Pockets</b>', html)
        self.assertNotIn('B01P', html)
        self.assertNotIn('class="pocket"', html)
        self.assertIn('Run <b>B01C</b>', html)

    def test_disabled_group_is_not_in_the_run_sheet(self):
        sh = pocket_shape('p', [rect_loop(100, 50, 40, 30)])
        plan = build_plan([ShapeEntry(sh)], self.s)
        key = pocket_groups_data(plan, self.s)[0]['key']
        ov = {key: {'enabled': False}}
        progs = plan_programs(plan, self.s, ov)
        out = Path(self.tmp.name) / 'off'
        write_output(out, plan, progs, self.s, {}, pocket_overrides=ov)
        html = (out / 'RUNSHEET.html').read_text(encoding='utf-8')
        self.assertNotIn('B01P', html)
        self.assertNotIn('<b>Pockets</b>', html)
        self.assertNotIn('class="pocket"', html)

    def test_project_json_has_pocket_overrides_and_groups(self):
        sh = pocket_shape('p', [rect_loop(100, 50, 40, 30)])
        plan = build_plan([ShapeEntry(sh)], self.s)
        key = pocket_groups_data(plan, self.s)[0]['key']
        ov = {key: {'depth': 5}}
        out = Path(self.tmp.name) / 'ov'
        write_output(out, plan, plan_programs(plan, self.s, ov), self.s, {}, pocket_overrides=ov)
        data = json.loads((out / 'PROJECT.json').read_text(encoding='utf-8'))
        self.assertEqual(data['pockets'], ov)
        self.assertEqual(data['pocket_groups'], pocket_groups_data(plan, self.s, ov))
        self.assertEqual(data['pocket_groups'][0]['depth'], 5)
        self.write()
        self.assertEqual(json.loads((self.out / 'PROJECT.json').read_text())['pockets'], {})

    def test_loader_and_diskette_include_pocket_programs(self):
        self.write()
        names = [p.name for p in self.progs]
        self.assertIn('B01P', names)
        for f in ('LOAD.BAT', 'COLLECT.BAT'):
            text = (self.out / f).read_bytes().decode('ascii')
            for n in names:
                self.assertIn(n.upper() if f == 'LOAD.BAT' else f'{n[0]} {n[1:]}', text, (f, n))
        disk = self.out / 'DISKETTE' / 'SORG'
        self.assertTrue((disk / 'SRG' / 'B' / '01P').is_file())
        self.assertEqual((disk / 'INDICE.PRG').stat().st_size, 82 * len(names))


if __name__ == '__main__':
    unittest.main()
