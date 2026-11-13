"""Pins the CNC90 programs of a consistent old-form project (no tool table): the tool-table
work must not change them. The fixture settings are written out in full, not left to defaults."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from nesting.backends import BACKENDS
from nesting.server import Project

repo = Path(__file__).resolve().parent.parent
DATA = repo / 'tests' / 'data' / 'tool_table' / 'consistent'


def programs_of_fixture() -> dict:
    """{program name: CNC90 text} for the fixture project over the 12 plates in plates/."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / 'shapes').mkdir()
        for dxf in (repo / 'plates').glob('*.dxf'):
            shutil.copy(dxf, tmp / 'shapes' / dxf.name)
        shutil.copy(DATA / 'project.json', tmp / 'project.json')
        project = Project(tmp)
        settings, _, programs, _, _ = project.compute(project.snapshot())
        return {prog.name: BACKENDS['cnc90'](prog, settings) for prog in programs}


class BaselineTests(unittest.TestCase):
    def test_fixture_is_old_form(self):
        data = json.loads((DATA / 'project.json').read_text(encoding='utf-8'))
        self.assertNotIn('tools', data)

    def test_consistent_project_programs_unchanged(self):
        expected = json.loads((DATA / 'programs.json').read_text(encoding='utf-8'))
        actual = programs_of_fixture()
        self.assertEqual(set(actual), set(expected))
        for name in sorted(expected):
            self.assertEqual(actual[name], expected[name], msg=name)


if __name__ == '__main__':
    unittest.main()
