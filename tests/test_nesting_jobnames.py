"""Every generated job gets its own number in the program names (B<job><blank><D|C>), so a
new job never has to replace programs of an earlier one on the machine (2026-11-20: CNC90 kept
the old blank size of a replaced program in its index)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from nesting.dxf import read_dxf
from nesting.layout import ShapeEntry, build_plan
from nesting.program import NAME, plan_programs, program_name
from nesting.server import Project, seed_plates
from nesting.settings import Settings

repo = Path(__file__).resolve().parent.parent


class NameTests(unittest.TestCase):
    def test_without_a_job_the_names_are_per_blank(self):
        self.assertEqual(program_name('B01', 'C'), 'B01C')

    def test_job_number_goes_after_the_folder_letter(self):
        self.assertEqual(program_name('B01', 'D', 7), 'B00701D')
        self.assertEqual(program_name('B12', 'C', 123), 'B12312C')

    def test_more_than_99_blanks_still_fits_8_characters(self):
        name = program_name('B100', 'C', 999)
        self.assertEqual(name, 'B999100C')
        self.assertTrue(NAME.fullmatch(name))

    def test_plan_programs_use_the_job(self):
        s = Settings()
        plan = build_plan([ShapeEntry(read_dxf(p)) for p in sorted((repo / 'plates').glob('*.dxf'))], s)
        names = [p.name for p in plan_programs(plan, s, job=42)]
        self.assertEqual(names[:2], ['B04201D', 'B04201C'])
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(n.startswith('B042') for n in names))


class ProjectJobTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / 'project'
        (self.dir / 'shapes').mkdir(parents=True)
        seed_plates(self.dir)
        self.project = Project(self.dir)

    def stored_job(self):
        return json.loads((self.dir / 'project.json').read_text())['job']

    def names(self):
        return [p['name'] for b in self.project.plan()['blanks'] for p in b['programs']]

    def test_new_project_previews_job_1_and_generate_takes_it(self):
        self.assertEqual(self.names()[:2], ['B00101D', 'B00101C'])
        r = self.project.generate()
        self.assertEqual(r['programs'][:2], ['B00101D', 'B00101C'])
        self.assertEqual(r['job'], 1)
        self.assertTrue((Path(r['folder']) / 'B00101C').is_file())
        self.assertTrue((Path(r['folder']) / 'DISKETTE' / 'SORG' / 'SRG' / 'B' / '00101C').is_file())
        self.assertEqual(self.stored_job(), 1)
        self.assertEqual(self.names()[:1], ['B00201D'])          # the next job's names
        r2 = self.project.generate()
        self.assertEqual((r2['job'], r2['programs'][0]), (2, 'B00201D'))

    def test_program_text_by_the_previewed_name(self):
        text = self.project.program_text('B00101C')
        self.assertTrue(text.startswith('G71'))

    def test_saving_the_project_keeps_the_counter(self):
        self.project.generate()
        body = self.project.project()
        self.project.save({k: body[k] for k in ('shapes', 'settings', 'pockets', 'tools')})
        self.assertEqual(self.stored_job(), 1)
        self.assertEqual(self.names()[0], 'B00201D')

    def test_after_999_it_starts_again_at_1(self):
        self.project.generate()
        data = json.loads((self.dir / 'project.json').read_text())
        data['job'] = 999
        (self.dir / 'project.json').write_text(json.dumps(data))
        self.assertEqual(self.names()[0], 'B00101D')
        self.assertEqual(self.project.generate()['job'], 1)

    def test_failed_generate_does_not_use_up_a_number(self):
        for f in (self.dir / 'shapes').iterdir():
            f.unlink()
        with self.assertRaises(Exception):
            self.project.generate()                 # nothing to generate
        self.assertFalse((self.dir / 'project.json').exists()
                         and 'job' in json.loads((self.dir / 'project.json').read_text()))

    def test_run_sheet_names_the_job(self):
        r = self.project.generate()
        html = (Path(r['folder']) / 'RUNSHEET.html').read_text()
        self.assertIn('Job 001', html)


if __name__ == '__main__':
    unittest.main()
