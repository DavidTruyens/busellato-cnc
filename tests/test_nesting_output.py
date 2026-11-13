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
from nesting.preview import preview_data
from nesting.program import plan_programs
from nesting.settings import Settings

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

    def test_runsheet_blank_steps_in_order(self):
        html = self._sheet(self.s, self.progs)
        section = html.split('<h2>Blank B01 ')[1].split('</section>')[0]
        order = [section.index(x) for x in ('origin corner', 'B01F', 'Screw the blank', 'B01S',
                                            'Screw each shape', 'B01C')]
        self.assertEqual(order, sorted(order))

    def test_runsheet_says_screw_holes_merged(self):
        html = self._sheet(self.s, self.progs)
        self.assertNotIn('merged into', html)
        self.assertIn('B01S', html)
        m = Settings()
        m.drill_screw.tool, m.drill_screw.diameter = m.drill_fix.tool, m.drill_fix.diameter
        plan = build_plan(self.entries, m)
        progs = plan_programs(plan, m)
        self.assertFalse(any(p.name.endswith('S') for p in progs))
        html = self._sheet(m, progs, plan)
        self.assertIn('merged into B01F', html)
        self.assertNotIn('Drill <b>B01S', html)

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
            self.assertTrue(p.is_file())
            self.assertEqual(p.parent, self.out)

    def test_heights_say_depth_is_below_top_of_stack(self):
        self.write()
        html = (self.out / 'RUNSHEET.html').read_text(encoding='utf-8')
        self.assertIn('below the top of the stack', html)


if __name__ == '__main__':
    unittest.main()
