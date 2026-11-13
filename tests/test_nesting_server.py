import http.client
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from nesting.dxf import read_dxf
from nesting.pockets import find_groups
from nesting.program import plan_shapes
from nesting.server import make_server, seed_plates
from nesting.settings import Settings
from helpers import put_bit
from test_nesting_dxf import circle, dxf, line, rect

repo = Path(__file__).resolve().parent.parent
PLATES = sorted((repo / 'plates').glob('*.dxf'))


class ServerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / 'job'
        (self.dir / 'shapes').mkdir(parents=True)
        self.start()

    def start(self):
        self.server = make_server(self.dir, port=0)
        t = threading.Thread(target=self.server.serve_forever, args=(0.05,), daemon=True)
        t.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = 'http://127.0.0.1:%d' % self.server.server_address[1]

    def seed(self, plates):
        for p in plates:
            shutil.copy(p, self.dir / 'shapes' / p.name)

    def call(self, method, path, body=None, headers=None, raw=None):
        data = raw if raw is not None else None if body is None else json.dumps(body).encode()
        h = {'Content-Type': 'application/json'}
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw, status, ctype = r.read(), r.status, r.headers.get('Content-Type', '')
        except urllib.error.HTTPError as e:
            raw, status, ctype = e.read(), e.code, e.headers.get('Content-Type', '')
        if ctype.startswith('application/json'):
            return status, json.loads(raw)
        return status, raw.decode()

    def assertNoTrace(self, body):
        self.assertNotIn('Traceback', json.dumps(body))

    def test_project_roundtrip(self):
        self.seed(PLATES[:2])
        status, proj = self.call('GET', '/api/project')
        self.assertEqual(status, 200)
        self.assertEqual([s['name'] for s in proj['shapes']], [p.stem for p in PLATES[:2]])
        self.assertEqual(proj['settings'], Settings().to_dict())
        first = proj['shapes'][0]
        self.assertEqual((first['qty'], first['enabled']), (1, True))
        self.assertGreater(first['length'], first['width'])
        proj['shapes'][0]['qty'] = 3
        proj['shapes'][1]['enabled'] = False
        proj['settings']['router']['clearance'] = 4.5
        proj['settings']['machine']['frame_y'] = 800
        proj['settings']['panel']['kerf'] = 3.2
        status, put = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 200)
        groups = put.pop('pocket_groups')         # derived: follows qty and enabled
        self.assertEqual([(g['id'], g['count']) for g in groups], [('G1', 3), ('G2', 0)])
        proj.pop('pocket_groups')
        self.assertEqual(put, proj)
        self.assertTrue((self.dir / 'project.json').is_file())
        self.server.shutdown()
        self.server.server_close()
        self.start()                              # a fresh server reads project.json
        status, again = self.call('GET', '/api/project')
        self.assertEqual(again.pop('pocket_groups'), groups)
        self.assertEqual(again, proj)

    def test_put_invalid_settings_is_400_and_not_saved(self):
        self.seed(PLATES[:1])
        _, proj = self.call('GET', '/api/project')
        good = json.loads(json.dumps(proj))
        proj['settings']['router']['clearance'] = -1
        status, body = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 400)
        self.assertEqual(body['field'], 'router.clearance')
        self.assertTrue(body['message'])
        self.assertFalse((self.dir / 'project.json').exists())
        self.assertEqual(self.call('GET', '/api/project')[1], good)
        proj['settings']['router']['clearance'] = 4
        proj['settings']['router']['tool'] = 66.5
        status, body = self.call('PUT', '/api/project', proj)
        self.assertEqual((status, body['field']), (400, 'router.tool'))
        proj['settings']['router']['tool'] = 65                 # an empty head
        status, body = self.call('PUT', '/api/project', proj)
        self.assertEqual((status, body['field']), (400, 'router.tool'))
        self.assertEqual(body['message'], 'router: head T65 holds no bit')
        self.assertFalse((self.dir / 'project.json').exists())
        proj['settings']['router']['tool'] = 66
        proj['shapes'][0]['qty'] = -2
        status, body = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 400)
        self.assertIn('qty', body['field'])
        self.assertFalse((self.dir / 'project.json').exists())

    def test_put_depth_into_the_cups_is_400_with_field(self):
        self.seed(PLATES[:1])
        _, proj = self.call('GET', '/api/project')
        for group, key, value in (('heights', 'into_scrap', 20), ('heights', 'fix_into_scrap', 20),
                                  ('drill_screw', 'depth', 40)):
            with self.subTest(field=f'{group}.{key}'):
                bad = json.loads(json.dumps(proj))
                bad['settings'][group][key] = value
                status, body = self.call('PUT', '/api/project', bad)
                self.assertEqual(status, 400)
                self.assertEqual(body['field'], f'{group}.{key}')
                self.assertIn('cups', body['message'])
        self.assertFalse((self.dir / 'project.json').exists())

    def test_plan_with_depth_into_the_cups_names_the_field(self):
        self.seed(PLATES[:1])
        s = Settings().to_dict()
        s['heights']['into_scrap'] = 20
        (self.dir / 'project.json').write_text(json.dumps({'shapes': [], 'settings': s}))
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200)
        self.assertEqual(plan['settings_error']['field'], 'heights.into_scrap')
        self.assertEqual(plan['panels'], [])
        self.assertNoTrace(plan)

    def test_plan_program_depth_check_is_a_problem_not_a_trace(self):
        # the program-level check is a backstop behind validate(): bypass validate to reach it
        from unittest import mock
        self.seed(PLATES[:1])
        s = Settings().to_dict()
        s['heights']['into_scrap'] = 20
        (self.dir / 'project.json').write_text(json.dumps({'shapes': [], 'settings': s}))
        with mock.patch('nesting.server.validate', lambda settings: None):
            status, plan = self.call('GET', '/api/plan')
            self.assertEqual(status, 200)
            self.assertEqual(plan['panels'], [])
            self.assertIsNone(plan['settings_error'])
            self.assertTrue(any('B01C' in p and 'cups' in p for p in plan['problems']), plan['problems'])
            self.assertNoTrace(plan)
            status, body = self.call('POST', '/api/generate')
            self.assertEqual(status, 400)
            self.assertIn('cups', body['error'])
        self.assertFalse((self.dir / 'out').exists())

    def test_upload_valid_dxf_adds_shape(self):
        text = dxf(rect(0, 0, 500, 200))
        status, body = self.call('POST', '/api/shapes', {'filename': 'part A.dxf', 'text': text})
        self.assertEqual(status, 200)
        self.assertEqual(body['name'], 'part A')
        self.assertAlmostEqual(body['length'], 500)
        self.assertAlmostEqual(body['width'], 200)
        self.assertTrue((self.dir / 'shapes' / 'part A.dxf').is_file())
        names = [s['name'] for s in self.call('GET', '/api/project')[1]['shapes']]
        self.assertEqual(names, ['part A'])

    def test_upload_crlf_dxf_gives_the_same_shape_as_lf(self):
        text = PLATES[0].read_text()
        status, lf = self.call('POST', '/api/shapes', {'filename': 'lf.dxf', 'text': text})
        self.assertEqual(status, 200)
        crlf_text = text.replace('\n', '\r\n')
        status, crlf = self.call('POST', '/api/shapes', {'filename': 'crlf.dxf', 'text': crlf_text})
        self.assertEqual(status, 200, crlf)
        self.assertEqual({k: v for k, v in crlf.items() if k != 'name'},
                         {k: v for k, v in lf.items() if k != 'name'})
        # stored exactly as sent: no newline translation (Windows would write \r\r\n)
        self.assertEqual((self.dir / 'shapes' / 'crlf.dxf').read_bytes(), crlf_text.encode('utf-8'))

    def test_upload_crlf_dxf_survives_windows_newline_translation(self):
        # emulate Windows text mode: '\n' is written as '\r\n' unless newline='' is given
        from unittest import mock
        import builtins
        import io
        real_open = io.open

        def win_open(file, mode='r', buffering=-1, encoding=None, errors=None, newline=None,
                     closefd=True, opener=None):
            if 'w' in mode and 'b' not in mode and newline is None:
                newline = '\r\n'
            return real_open(file, mode, buffering, encoding, errors, newline, closefd, opener)

        text = PLATES[0].read_text().replace('\n', '\r\n')
        with mock.patch.object(io, 'open', win_open), mock.patch.object(builtins, 'open', win_open):
            status, body = self.call('POST', '/api/shapes', {'filename': 'win.dxf', 'text': text})
        self.assertEqual(status, 200, body)
        self.assertEqual((self.dir / 'shapes' / 'win.dxf').read_bytes(), text.encode('utf-8'))

    def test_upload_open_outline_is_400_with_file_name(self):
        text = dxf(line(0, 0, 100, 0), line(100, 0, 100, 50))
        status, body = self.call('POST', '/api/shapes', {'filename': 'broken.dxf', 'text': text})
        self.assertEqual(status, 400)
        self.assertIn('broken.dxf', body['error'])
        self.assertIn('open', body['error'])
        self.assertEqual(list((self.dir / 'shapes').iterdir()), [])
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ['shapes'])

    def test_upload_filename_cannot_escape_shapes_folder(self):
        text = dxf(rect(0, 0, 300, 100))
        status, body = self.call('POST', '/api/shapes', {'filename': '../../evil.dxf', 'text': text})
        self.assertEqual(status, 200)
        self.assertEqual(body['name'], 'evil')
        self.assertTrue((self.dir / 'shapes' / 'evil.dxf').is_file())
        self.assertFalse((self.dir / 'evil.dxf').exists())
        self.assertFalse((self.dir.parent / 'evil.dxf').exists())
        status, body = self.call('POST', '/api/shapes', {'filename': 'C:\\x\\win.dxf', 'text': text})
        self.assertEqual((status, body['name']), (200, 'win'))
        for bad in ('a<b>.dxf', 'part.txt', '.dxf', '..', '', 'x/', 'naïve.dxf'):
            with self.subTest(name=bad):
                status, body = self.call('POST', '/api/shapes', {'filename': bad, 'text': text})
                self.assertEqual(status, 400)
                self.assertIn('error', body)
        self.assertEqual(sorted(p.name for p in (self.dir / 'shapes').iterdir()),
                         ['evil.dxf', 'win.dxf'])

    def test_body_over_20_mb_is_413(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=10)
        conn.putrequest('POST', '/api/shapes')
        conn.putheader('Content-Type', 'application/json')
        conn.putheader('Content-Length', str(20 * 1024 * 1024 + 1))
        conn.endheaders()
        conn.send(b'{"filename"')
        r = conn.getresponse()
        self.assertEqual(r.status, 413)
        r.read()
        conn.close()
        self.assertEqual(list((self.dir / 'shapes').iterdir()), [])

    def test_plan_for_12_plates(self):
        self.seed(PLATES)
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200)
        self.assertEqual(len(plan['panels']), 3)
        self.assertEqual(len(plan['blanks']), 6)
        names = [p['name'] for b in plan['blanks'] for p in b['programs']]
        self.assertEqual(names, [f'B0{n}{k}' for n in range(1, 7) for k in 'DPC'])
        progs = {p['name']: p for b in plan['blanks'] for p in b['programs']}
        self.assertEqual((progs['B01D']['tools'], progs['B01C']['tools']), ([1, 2], [66]))
        self.assertEqual([t['holes'] for t in plan['blanks'][0]['drill_tools']], ['fixing', 'screw'])
        self.assertEqual(plan['problems'], [])
        self.assertIsNone(plan['settings_error'])
        z = plan['blanks'][0]['z']
        self.assertEqual(z, {'stack_top': 36, 'fixing': 19, 'screw': 26, 'shape_cut': 18.5})
        self.assertEqual(plan['frame'], {'x': 3072, 'y': 787})
        panel = plan['panels'][0]
        self.assertEqual([b['id'] for b in panel['blanks']], ['B01', 'B02'])
        self.assertTrue(panel['cuts'])
        self.assertEqual([c['n'] for c in panel['cuts']], list(range(1, len(panel['cuts']) + 1)))

    def test_plan_with_oversize_shape_is_an_error_naming_it(self):
        self.seed(PLATES[:1])
        (self.dir / 'shapes' / 'huge.dxf').write_text(dxf(rect(0, 0, 3000, 100)))
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200)
        self.assertIsNone(plan['settings_error'])
        self.assertEqual(plan['panels'], [])
        self.assertTrue(any('huge' in p for p in plan['problems']), plan['problems'])
        self.assertNoTrace(plan)
        status, body = self.call('POST', '/api/generate')
        self.assertEqual(status, 400)
        self.assertIn('huge', body['error'])
        self.assertFalse((self.dir / 'out').exists())

    def test_plan_with_small_work_frame_names_shape_and_frame(self):
        self.seed(PLATES[:1])
        s = Settings().to_dict()
        s['machine']['frame_y'] = 300
        (self.dir / 'project.json').write_text(json.dumps({'shapes': [], 'settings': s}))
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200)
        self.assertEqual(plan['panels'], [])
        msg = ' '.join(plan['problems'])
        self.assertIn(PLATES[0].stem, msg)
        self.assertIn('work frame 3072 x 300', msg)

    def test_put_invalid_new_settings_is_400_with_field(self):
        self.seed(PLATES[:1])
        _, proj = self.call('GET', '/api/project')
        for group, key, value in (('machine', 'frame_x', 0), ('machine', 'frame_y', -1),
                                  ('panel', 'kerf', -2), ('panel', 'edge', 2),
                                  ('machine', 'frame_y', 80)):
            with self.subTest(field=f'{group}.{key}', value=value):
                bad = json.loads(json.dumps(proj))
                bad['settings'][group][key] = value
                status, body = self.call('PUT', '/api/project', bad)
                self.assertEqual(status, 400)
                self.assertEqual(body['field'], f'{group}.{key}')
        self.assertFalse((self.dir / 'project.json').exists())

    def test_old_project_json_is_read_with_the_new_settings(self):
        self.seed(PLATES[:1])
        old = {'template': {'mode': 'auto', 'shapes_per': 1, 'margin_end': 50},
               'heights': {'scrap': 18, 'template_stock': 18, 'shape_thickness': 18,
                           'into_template': 0.3}}
        (self.dir / 'project.json').write_text(json.dumps({'shapes': [], 'settings': old}))
        status, proj = self.call('GET', '/api/project')
        self.assertEqual(status, 200)
        self.assertEqual(proj['settings']['blank']['margin_end'], 50)
        self.assertNotIn('template', proj['settings'])
        # no `tools`: migrated from the old default settings, whose router and pocket depth
        # per pass disagreed on T66 (R4): one note, shown first in the plan's problems (R6)
        self.assertEqual(len(proj['tools_notes']), 1)
        self.assertTrue(proj['tools_notes'][0].startswith('T66 '))
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(plan['problems'], proj['tools_notes'])
        self.assertEqual(plan['blanks'][0]['width'], round(read_dxf(PLATES[0]).length) + 100)

    def test_plan_with_invalid_setting_returns_field_error(self):
        self.seed(PLATES[:2])
        s = Settings().to_dict()
        s['blank']['shapes_per'] = 0
        (self.dir / 'project.json').write_text(json.dumps({'shapes': [], 'settings': s}))
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200)
        self.assertEqual(plan['settings_error']['field'], 'blank.shapes_per')
        self.assertTrue(plan['settings_error']['message'])
        self.assertEqual(plan['panels'], [])
        self.assertNoTrace(plan)

    def test_plan_with_offset_error_is_a_problem(self):
        self.seed(PLATES[:1])
        st = Settings()
        put_bit(st, 65, diameter=200)          # cannot follow the outline
        s = st.to_dict()
        s['router']['tool'] = 65               # (not the pocket tool T66, which is 8 mm)
        s['blank']['fix_inset'] = 300          # (keeps the fixing holes clear of the shape)
        s['blank']['margin_end'] = s['blank']['margin_side'] = 460
        s['machine']['frame_y'] = 1200
        s['panel']['length'], s['panel']['width'] = 3000, 3000
        (self.dir / 'project.json').write_text(json.dumps(
            {'shapes': [], 'settings': s, 'tools': st.tools.to_dict()}))
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200)
        self.assertEqual(plan['panels'], [])
        self.assertIn('narrower than the tool', ' '.join(plan['problems']))
        self.assertIsNone(plan['settings_error'])
        self.assertNoTrace(plan)

    def test_plan_has_no_cutter_outside_blank_warning_by_default(self):
        self.seed(PLATES[:2])
        status, plan = self.call('GET', '/api/plan')
        warnings = [w for b in plan['blanks'] for p in b['programs'] for w in p['warnings']]
        self.assertFalse(any('cutter reaches' in w for w in warnings), warnings)

    def test_plan_with_unreadable_dxf_in_shapes_is_a_problem(self):
        self.seed(PLATES[:1])
        (self.dir / 'shapes' / 'bad.dxf').write_text(dxf(line(0, 0, 10, 0)))
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200)
        self.assertTrue(any('bad.dxf' in p for p in plan['problems']), plan['problems'])
        self.assertEqual(len(plan['panels']), 1)

    def test_plan_with_no_enabled_shapes_is_empty(self):
        self.seed(PLATES[:1])
        _, proj = self.call('GET', '/api/project')
        proj['shapes'][0]['enabled'] = False
        self.assertEqual(self.call('PUT', '/api/project', proj)[0], 200)
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200)
        self.assertEqual((plan['panels'], plan['problems'], plan['settings_error']), ([], [], None))

    def test_program_text_is_the_emitted_program(self):
        self.seed(PLATES[:2])
        status, text = self.call('GET', '/api/program?name=B01C')
        self.assertEqual(status, 200)
        status, _ = self.call('POST', '/api/generate')
        out = next((self.dir / 'out').iterdir())
        self.assertEqual(text.encode('ascii'), (out / 'B01C').read_bytes())
        status, body = self.call('GET', '/api/program?name=B99Z')
        self.assertEqual(status, 404)

    def test_generate_creates_new_folder_each_time(self):
        self.seed(PLATES)
        status, a = self.call('POST', '/api/generate')
        self.assertEqual(status, 200, a)
        status, b = self.call('POST', '/api/generate')
        self.assertEqual(status, 200, b)
        self.assertNotEqual(a['folder'], b['folder'])
        for res in (a, b):
            folder = Path(res['folder'])
            self.assertEqual(folder.parent, self.dir / 'out')
            self.assertRegex(folder.name, r'^\d{8}-\d{6}(-\d+)?$')
            self.assertEqual(sorted(res['files']), sorted(p.name for p in folder.iterdir()))
            for n in ('B01D', 'B06C', 'LOAD.BAT', 'RUNSHEET.html', 'PROJECT.json'):
                self.assertIn(n, res['files'])
        self.assertEqual(len(list((self.dir / 'out').iterdir())), 2)

    def test_generate_with_nothing_is_an_error_body(self):
        status, body = self.call('POST', '/api/generate')
        self.assertEqual(status, 400)
        self.assertIn('error', body)
        self.assertNoTrace(body)
        self.assertFalse((self.dir / 'out').exists())

    def test_post_without_json_content_type_is_415(self):
        text = dxf(rect(0, 0, 300, 100))
        body = json.dumps({'filename': 'a.dxf', 'text': text}).encode()
        for ctype in ('text/plain', 'application/x-www-form-urlencoded', 'multipart/form-data'):
            with self.subTest(ctype=ctype):
                status, _ = self.call('POST', '/api/shapes', raw=body, headers={'Content-Type': ctype})
                self.assertEqual(status, 415)
        status, _ = self.call('POST', '/api/shapes', raw=b'filename=a.dxf&text=x',
                              headers={'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(status, 415)
        self.assertEqual(list((self.dir / 'shapes').iterdir()), [])
        self.seed(PLATES[:1])
        self.assertEqual(self.call('POST', '/api/generate', raw=b'', headers={'Content-Type': 'text/plain'})[0], 415)
        self.assertFalse((self.dir / 'out').exists())
        _, proj = self.call('GET', '/api/project')
        proj['settings']['heights']['scrap'] = 30
        status, _ = self.call('PUT', '/api/project', raw=json.dumps(proj).encode(),
                              headers={'Content-Type': 'text/plain'})
        self.assertEqual(status, 415)
        self.assertFalse((self.dir / 'project.json').exists())
        status, _ = self.call('POST', '/api/shapes', {'filename': 'a.dxf', 'text': text},
                              headers={'Content-Type': 'application/json; charset=utf-8'})
        self.assertEqual(status, 200)

    def test_foreign_host_or_origin_is_403(self):
        port = self.server.server_address[1]
        text = dxf(rect(0, 0, 300, 100))
        for path in ('/', '/api/project', '/api/plan'):
            with self.subTest(path=path):
                self.assertEqual(self.call('GET', path, headers={'Host': 'evil.example'})[0], 403)
                self.assertEqual(self.call('GET', path, headers={'Host': f'evil.example:{port}'})[0], 403)
                self.assertEqual(self.call('GET', path, headers={'Host': '127.0.0.1:1'})[0], 403)
        status, _ = self.call('POST', '/api/shapes', {'filename': 'a.dxf', 'text': text},
                              headers={'Host': 'evil.example'})
        self.assertEqual(status, 403)
        status, _ = self.call('POST', '/api/shapes', {'filename': 'a.dxf', 'text': text},
                              headers={'Origin': 'http://evil.example'})
        self.assertEqual(status, 403)
        self.assertEqual(self.call('GET', '/api/project', headers={'Origin': f'http://evil.example:{port}'})[0], 403)
        self.assertEqual(list((self.dir / 'shapes').iterdir()), [])
        for host in (f'127.0.0.1:{port}', f'localhost:{port}'):
            with self.subTest(host=host):
                status, _ = self.call('POST', '/api/shapes', {'filename': 'a.dxf', 'text': text},
                                      headers={'Host': host, 'Origin': f'http://{host}'})
                self.assertEqual(status, 200)
                self.assertEqual(self.call('GET', '/api/project', headers={'Host': host})[0], 200)

    def test_put_non_finite_number_is_400(self):
        self.seed(PLATES[:1])
        _, proj = self.call('GET', '/api/project')
        raw = json.dumps(proj).replace('"clearance": 4', '"clearance": 1e400').encode()
        self.assertIn(b'1e400', raw)
        status, body = self.call('PUT', '/api/project', raw=raw)
        self.assertEqual(status, 400)
        self.assertEqual(body['field'], 'router.clearance')
        self.assertFalse((self.dir / 'project.json').exists())
        raw = json.dumps(proj).replace('"qty": 1', '"qty": 1e400').encode()
        status, body = self.call('PUT', '/api/project', raw=raw)
        self.assertEqual(status, 400)
        self.assertIn('qty', body['field'])
        self.assertFalse((self.dir / 'project.json').exists())

    def test_z_values_match_the_program_text(self):
        self.seed(PLATES[:2])
        _, proj = self.call('GET', '/api/project')
        proj['settings']['heights']['into_scrap'] = 0.05
        proj['settings']['panel']['thickness'] = 18.2
        proj['settings']['drill_screw']['depth'] = 8.2
        self.assertEqual(self.call('PUT', '/api/project', proj)[0], 200)
        _, plan = self.call('GET', '/api/plan')
        z = plan['blanks'][0]['z']
        for v in z.values():
            self.assertEqual(v, round(v, 3))
        self.assertEqual(z['stack_top'], 36.2)      # scrap 18 + blank 18.2
        self.assertEqual(z['shape_cut'], 18.25)     # through the blank + 0.05
        self.assertEqual(z['screw'], 26.4)          # 18.2 + 8.2
        _, cut = self.call('GET', '/api/program?name=B01C')
        self.assertIn('Z18.25', cut)
        self.assertRegex(cut.splitlines()[0], r'^G71X\d+Y\d+Z36.2T00')
        _, drill = self.call('GET', '/api/program?name=B01D')
        self.assertRegex(drill, r'G81G90G54P5T0102X[\d.]+Y[\d.]+Z26.4\r')    # screw holes, own tool
        self.assertRegex(drill, r'G81G90G54P5T0101X[\d.]+Y[\d.]+Z19.2\r')    # fixing: 18.2 + 1
        for old in ('B01F', 'B01S'):
            self.assertEqual(self.call('GET', f'/api/program?name={old}')[0], 404)

    def test_upper_case_extension_is_stored_as_lower_case(self):
        text = dxf(rect(0, 0, 300, 100))
        status, body = self.call('POST', '/api/shapes', {'filename': 'PART.DXF', 'text': text})
        self.assertEqual((status, body['name']), (200, 'PART'))
        self.assertEqual([p.name for p in (self.dir / 'shapes').iterdir()], ['PART.dxf'])
        names = [s['name'] for s in self.call('GET', '/api/project')[1]['shapes']]
        self.assertEqual(names, ['PART'])

    def test_name_differing_only_by_case_replaces_that_shape(self):
        self.call('POST', '/api/shapes', {'filename': 'part.dxf', 'text': dxf(rect(0, 0, 300, 100))})
        status, body = self.call('POST', '/api/shapes', {'filename': 'Part.DXF',
                                                         'text': dxf(rect(0, 0, 400, 100))})
        self.assertEqual(status, 200)
        self.assertEqual((body['name'], body['replaced']), ('part', True))
        self.assertEqual([p.name for p in (self.dir / 'shapes').iterdir()], ['part.dxf'])
        shapes = self.call('GET', '/api/project')[1]['shapes']
        self.assertEqual([(s['name'], s['length']) for s in shapes], [('part', 400)])

    def test_put_quantity_over_limit_is_400_and_500_is_fine(self):
        self.seed(PLATES[:1])
        _, proj = self.call('GET', '/api/project')
        name = proj['shapes'][0]['name']
        proj['shapes'][0]['qty'] = 10 ** 30
        status, body = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 400)
        self.assertEqual(body['field'], f'shapes.{name}.qty')
        self.assertIn('500', body['message'])
        self.assertFalse((self.dir / 'project.json').exists())
        proj['shapes'][0]['qty'] = 500
        proj['shapes'][0]['enabled'] = False      # keep the plan cheap; the limit is what counts
        status, body = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 200)
        self.assertEqual(body['shapes'][0]['qty'], 500)

    def test_hand_edited_huge_quantity_is_a_problem_and_server_stays_responsive(self):
        import time
        self.seed(PLATES[:1])
        (self.dir / 'project.json').write_text(json.dumps(
            {'shapes': [{'name': PLATES[0].stem, 'qty': 10 ** 30, 'enabled': True}],
             'settings': Settings().to_dict()}))
        t0 = time.monotonic()
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200)
        self.assertEqual(plan['panels'], [])
        self.assertTrue(any('more than the 500 allowed' in p for p in plan['problems']), plan['problems'])
        self.assertEqual(self.call('GET', '/api/project')[0], 200)
        self.assertLess(time.monotonic() - t0, 2)

    def test_slow_plan_does_not_block_project_requests(self):
        import time
        from unittest import mock
        import nesting.server as srv
        self.seed(PLATES[:1])
        release = threading.Event()
        real = srv.build_plan

        def slow(*a, **kw):
            release.wait(10)
            return real(*a, **kw)

        with mock.patch.object(srv, 'build_plan', side_effect=slow):
            th = threading.Thread(target=self.call, args=('GET', '/api/plan'), daemon=True)
            th.start()
            time.sleep(0.2)                      # the plan request is now inside build_plan
            t0 = time.monotonic()
            status, proj = self.call('GET', '/api/project')
            self.assertEqual(status, 200)
            self.assertEqual(self.call('PUT', '/api/project', proj)[0], 200)
            self.assertLess(time.monotonic() - t0, 2)
            release.set()
            th.join(10)

    # --- pockets ------------------------------------------------------------------------
    def write_project(self, pockets, settings=None):
        (self.dir / 'project.json').write_text(json.dumps(
            {'shapes': [], 'settings': settings or Settings().to_dict(), 'pockets': pockets}))

    def circle_plate(self):
        """600 x 200 plate with two 6.6 mm holes and a 10 mm circle in the middle."""
        (self.dir / 'shapes' / 'round.dxf').write_text(dxf(
            rect(0, 0, 600, 200), circle(50, 100, 3.3), circle(550, 100, 3.3),
            circle(300, 100, 5)))

    def test_project_lists_pocket_groups_with_effective_settings(self):
        self.seed(PLATES[:2])
        status, proj = self.call('GET', '/api/project')
        self.assertEqual(status, 200)
        self.assertEqual(proj['pockets'], {})
        groups = proj['pocket_groups']
        self.assertEqual([g['id'] for g in groups], ['G1', 'G2'])
        d = Settings().pockets
        self.assertEqual((groups[0]['depth'], groups[0]['tool'], groups[0]['enabled']),
                         (d.depth, d.tool, True))
        self.assertEqual(groups[0]['count'], 1)
        proj['shapes'][0]['qty'] = 3
        proj['shapes'][1]['enabled'] = False
        status, put = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 200, put)
        self.assertEqual([(g['id'], g['count']) for g in put['pocket_groups']],
                         [('G1', 3), ('G2', 0)])

    def test_pocket_overrides_round_trip(self):
        self.seed(PLATES[:2])
        _, proj = self.call('GET', '/api/project')
        key = proj['pocket_groups'][0]['key']
        proj['pockets'] = {key: {'depth': 5, 'cut_feed': 2.5},
                           'not-a-group': {'depth': 3}}
        status, put = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 200, put)
        # saving drops the old per-group cut feed (not applied: the bit in the group's head
        # gives it); the rest of the override and the unknown key stay
        proj['pockets'] = {key: {'depth': 5}, 'not-a-group': {'depth': 3}}
        self.assertEqual(put['pockets'], proj['pockets'])
        self.assertEqual((put['pocket_groups'][0]['depth'], put['pocket_groups'][0]['cut_feed']),
                         (5, 3))
        self.assertEqual(put['pocket_groups'][1]['depth'], Settings().pockets.depth)
        stored = json.loads((self.dir / 'project.json').read_text())
        self.assertEqual(stored['pockets'], proj['pockets'])    # unknown key kept
        self.server.shutdown()
        self.server.server_close()
        self.start()
        status, again = self.call('GET', '/api/project')
        self.assertEqual(again, put)
        proj = again
        proj['pockets'] = {key: {'enabled': False}}
        status, put = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 200, put)
        self.assertFalse(put['pocket_groups'][0]['enabled'])

    def plan_group_ids(self):
        """(plan pocket_groups {key: (id, colour)}, drawn pockets [(id, colour)],
        rings [(id, colour)], B..P op labels' group ids) of /api/plan and the programs."""
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200, plan)
        listed = {g['key']: (g['id'], g['color']) for g in plan['pocket_groups']}
        drawn = [(pk['group'], pk['color']) for b in plan['blanks'] for s in b['shapes']
                 for pk in s['pockets']]
        rings = [(r['group'], r['color']) for b in plan['blanks'] for r in b['pocket_rings']]
        project = self.server.RequestHandlerClass.project
        programs = project.compute(project.snapshot())[2]
        labels = {re.search(r' (G\d+) pocket ', o.label).group(1)
                  for p in programs if p.kind == 'pocket' for o in p.ops}
        return listed, drawn, rings, labels

    def test_pocket_group_ids_and_colours_do_not_change_when_a_shape_is_off(self):
        # the settings list numbers the groups of every shape; the plan, the drawing and the
        # B..P programs use the same ids and colours, whichever shapes are switched on
        self.assertEqual(seed_plates(self.dir), 12)
        _, proj = self.call('GET', '/api/project')
        everyone = {g['key']: (g['id'], g['color']) for g in proj.pop('pocket_groups')}
        by_id = {i: c for i, c in everyone.values()}
        self.assertGreater(len(everyone), 2)
        first, _, _, _ = self.plan_group_ids()
        self.assertEqual(first, everyone)
        # switch off the first shape: with groups of the placed shapes only it shifted the ids
        off = next(s for s in proj['shapes'] if s['name'] == '3-1')
        off['enabled'] = False
        status, put = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 200, put)
        self.assertEqual({g['key']: (g['id'], g['color']) for g in put['pocket_groups']},
                         everyone)
        listed, drawn, rings, labels = self.plan_group_ids()
        self.assertTrue(listed)
        # numbered over the placed shapes only, some ids would differ: the case is exercised
        project = self.server.RequestHandlerClass.project
        placed = find_groups(plan_shapes(project.compute(project.snapshot())[1]))
        self.assertTrue(any(g.id != everyone[g.key][0] for g in placed))
        for key, ic in listed.items():
            self.assertEqual(ic, everyone[key])
        for gid, colour in drawn + rings:
            self.assertEqual(colour, by_id[gid])
        self.assertTrue(labels)
        self.assertLessEqual(labels, {i for i, _ in listed.values()})
        # an override keyed by group key still applies to its group, under the same id
        key = next(k for k in listed if everyone[k][0] != 'G1')
        proj['pockets'] = {key: {'depth': 5}}
        status, put = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 200, put)
        _, plan = self.call('GET', '/api/plan')
        g = next(g for g in plan['pocket_groups'] if g['key'] == key)
        self.assertEqual((g['id'], g['depth']), (everyone[key][0], 5))
        # and back on: the same ids again
        off['enabled'] = True
        proj['pockets'] = {}
        self.assertEqual(self.call('PUT', '/api/project', proj)[0], 200)
        self.assertEqual(self.plan_group_ids()[0], everyone)

    def test_missing_pockets_key_means_no_overrides(self):
        self.seed(PLATES[:1])
        (self.dir / 'project.json').write_text(json.dumps(
            {'shapes': [], 'settings': Settings().to_dict()}))
        status, proj = self.call('GET', '/api/project')
        self.assertEqual((status, proj['pockets']), (200, {}))
        _, body = self.call('PUT', '/api/project', {'shapes': [], 'settings': proj['settings']})
        self.assertEqual(body['pockets'], {})

    def test_put_invalid_pocket_override_is_400_with_field_and_not_saved(self):
        self.seed(PLATES[:2])
        _, proj = self.call('GET', '/api/project')
        key = proj['pocket_groups'][1]['key']
        thick = Settings().panel.thickness
        cases = [({key: {'depth': -1}}, 'pockets.G2.depth'),
                 ({key: {'depth': 'deep'}}, 'pockets.G2.depth'),
                 ({key: {'depth': thick}}, 'pockets.G2.depth'),       # leaves no floor
                 ({key: {'tool': 66.5}}, 'pockets.G2.tool'),
                 ({key: {'tool': 0}}, 'pockets.G2.tool'),
                 ({key: {'enabled': 'no'}}, 'pockets.G2.enabled'),
                 ({key: {'direction': 'up'}}, 'pockets.G2.direction'),
                 ({key: 5}, 'pockets.G2'),
                 ('x', 'pockets'),
                 ([], 'pockets')]
        for pockets, field in cases:
            with self.subTest(pockets=pockets):
                bad = json.loads(json.dumps(proj))
                bad['pockets'] = pockets
                status, body = self.call('PUT', '/api/project', bad)
                self.assertEqual(status, 400, body)
                self.assertEqual(body['field'], field)
                self.assertTrue(body['message'])
        self.assertFalse((self.dir / 'project.json').exists())

    def test_put_obsolete_pocket_numbers_are_ignored_quickly(self):
        # stepover, diameter, speeds and feeds belong to the bit now: an old value (even a
        # tiny stepover, which once meant thousands of rings) is ignored, not refused
        self.seed(PLATES[:2])
        _, proj = self.call('GET', '/api/project')
        key = proj['pocket_groups'][0]['key']
        for where, value in (('settings', 1e-9), ('group', 1e-9), ('group', 'bad')):
            with self.subTest(where=where, value=value):
                old = json.loads(json.dumps(proj))
                if where == 'settings':
                    old['settings']['pockets']['stepover_pct'] = value
                else:
                    old['pockets'] = {key: {'stepover_pct': value, 'diameter': value}}
                t0 = time.monotonic()
                status, body = self.call('PUT', '/api/project', old)
                self.assertEqual(status, 200, body)
                self.assertNotIn('stepover_pct', body['settings']['pockets'])
                self.assertEqual((body['pocket_groups'][0]['stepover_pct'],
                                  body['pocket_groups'][0]['diameter']), (40, 8))
                status, plan = self.call('GET', '/api/plan')
                self.assertEqual(status, 200, plan)
                self.assertLess(time.monotonic() - t0, 30)

    def test_save_refuses_empty_group_head(self):
        self.seed(PLATES[:2])
        _, proj = self.call('GET', '/api/project')
        key = proj['pocket_groups'][0]['key']
        bad = json.loads(json.dumps(proj))
        bad['pockets'] = {key: {'tool': 65}}                # T65 is empty in the default table
        status, body = self.call('PUT', '/api/project', bad)
        self.assertEqual(status, 400, body)
        self.assertEqual(body['field'], 'pockets.G1.tool')
        self.assertEqual(body['message'], 'pocket group G1: head T65 holds no bit')
        self.assertFalse((self.dir / 'project.json').exists())
        bad['pockets'] = {}
        bad['settings']['pockets']['tool'] = 65              # the default head
        status, body = self.call('PUT', '/api/project', bad)
        self.assertEqual((status, body['field']), (400, 'pockets.tool'), body)
        self.assertIn('T65', body['message'])
        ok = json.loads(json.dumps(proj))
        ok['pockets'] = {key: {'tool': 65, 'enabled': False}}     # switched off: not used
        self.assertEqual(self.call('PUT', '/api/project', ok)[0], 200)

    def test_hand_edited_empty_group_head_is_a_problem_and_generates_nothing(self):
        self.seed(PLATES[:2])
        key = self.call('GET', '/api/project')[1]['pocket_groups'][0]['key']
        self.write_project({key: {'tool': 65}})
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200, plan)
        self.assertEqual(plan['blanks'], [])
        self.assertIn('pocket group G1: head T65 holds no bit', plan['problems'])
        status, body = self.call('GET', '/api/program?name=B01P')
        self.assertEqual(status, 400, body)
        self.assertIn('T65', body['error'])
        status, body = self.call('POST', '/api/generate', {})
        self.assertEqual(status, 400, body)
        self.assertIn('head T65 holds no bit', body['error'])
        self.assertFalse((self.dir / 'out').exists())

    def test_hand_edited_bad_pockets_is_a_problem_not_a_500(self):
        self.seed(PLATES[:2])
        key = self.call('GET', '/api/project')[1]['pocket_groups'][0]['key']
        cases = [('x', 'pockets'), ([1], 'pockets'), ({key: 'deep'}, 'pockets.G1'),
                 ({key: {'depth': 'deep'}}, 'pockets.G1.depth'),
                 ({key: {'depth': float('nan')}}, 'pockets.G1.depth')]
        for pockets, field in cases:
            with self.subTest(pockets=pockets):
                self.write_project(pockets)
                status, plan = self.call('GET', '/api/plan')
                self.assertEqual(status, 200, plan)
                self.assertEqual(plan['panels'], [])
                self.assertEqual(plan['blanks'], [])
                self.assertTrue(any(field in p for p in plan['problems']), plan['problems'])
                self.assertNoTrace(plan)
                status, proj = self.call('GET', '/api/project')
                self.assertEqual(status, 200, proj)
                bad = [g for g in proj['pocket_groups'] if 'error' in g]
                self.assertTrue(bad)
                self.assertTrue(all(not g['enabled'] for g in bad))
                status, body = self.call('GET', '/api/program?name=B01C')
                self.assertEqual(status, 400)
                self.assertIn(field, body['error'])
                status, body = self.call('POST', '/api/generate')
                self.assertEqual(status, 400)
                self.assertIn(field, body['error'])
        self.assertFalse((self.dir / 'out').exists())

    def test_project_answers_with_overrides_and_hand_edited_bad_settings(self):
        self.seed(PLATES[:1])
        key = self.call('GET', '/api/project')[1]['pocket_groups'][0]['key']
        s = Settings().to_dict()
        s['panel']['thickness'] = 'thick'
        s['pockets']['min_circle_diameter'] = 'big'
        self.write_project({key: {'depth': 5}}, s)
        status, proj = self.call('GET', '/api/project')
        self.assertEqual(status, 200, proj)
        self.assertEqual(proj['pocket_groups'][0]['depth'], 5)
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200, plan)
        self.assertTrue(plan['settings_error'])

    def test_stale_override_count_is_one_warning_line(self):
        self.seed(PLATES[:2])
        _, proj = self.call('GET', '/api/project')
        key = proj['pocket_groups'][0]['key']
        cases = [({}, None), ({key: {'depth': 5}}, None),
                 ({key: {'depth': 5}, 'gone': {'depth': 4}},
                  '1 stored pocket setting matches no current group (kept in project.json, '
                  'not used)'),
                 ({'gone': {'depth': 4}, 'gone2': {}},
                  '2 stored pocket settings match no current group (kept in project.json, '
                  'not used)')]
        for pockets, line in cases:
            with self.subTest(pockets=pockets):
                proj['pockets'] = pockets
                self.assertEqual(self.call('PUT', '/api/project', proj)[0], 200)
                status, plan = self.call('GET', '/api/plan')
                self.assertEqual(status, 200)
                self.assertTrue(plan['blanks'])                  # a warning, never blocks
                stale = [p for p in plan['problems'] if 'match' in p and 'no current group' in p]
                self.assertEqual(stale, [line] if line else [])
        status, body = self.call('POST', '/api/generate', {})
        self.assertEqual(status, 200, body)
        self.assertIn('2 stored pocket settings match no current group (kept in project.json, '
                      'not used)', body['problems'])

    def test_stale_unknown_key_is_kept_and_never_blocks(self):
        self.seed(PLATES[:2])
        _, proj = self.call('GET', '/api/project')
        stale = {'stale-old-key': {'depth': 15}, 'other': 'deep', 'third': {'tool': 'x'}}
        proj['pockets'] = dict(stale)
        status, put = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 200, put)
        self.assertEqual(put['pockets'], stale)
        proj['settings']['panel']['thickness'] = 12
        status, put = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 200, put)
        self.assertEqual(json.loads((self.dir / 'project.json').read_text())['pockets'], stale)
        self.assertTrue(all('error' not in g for g in put['pocket_groups']))
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200)
        self.assertTrue(plan['blanks'], plan['problems'])
        self.assertFalse(any('pockets.' in p for p in plan['problems']), plan['problems'])
        self.assertIn('3 stored pocket settings match no current group (kept in project.json, '
                      'not used)', plan['problems'])
        status, text = self.call('GET', '/api/program?name=B01P')
        self.assertEqual(status, 200, text)
        self.assertTrue(text)
        status, res = self.call('POST', '/api/generate')
        self.assertEqual(status, 200, res)
        self.assertIn('B01P', res['programs'])

    def test_switched_off_shape_group_is_listed_editable_and_checked(self):
        self.seed(PLATES[:2])
        _, proj = self.call('GET', '/api/project')
        proj['shapes'][1]['enabled'] = False
        status, put = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 200, put)
        self.assertEqual([(g['id'], g['count']) for g in put['pocket_groups']],
                         [('G1', 1), ('G2', 0)])
        key = put['pocket_groups'][1]['key']
        self.assertGreater(len(key), 50)
        put['pockets'] = {key: {'depth': 5}}
        status, put = self.call('PUT', '/api/project', put)
        self.assertEqual(status, 200, put)
        self.assertEqual(put['pocket_groups'][1]['depth'], 5)
        put['pockets'] = {key: {'depth': 15}}
        put['settings']['panel']['thickness'] = 12
        status, body = self.call('PUT', '/api/project', put)
        self.assertEqual(status, 400, body)
        self.assertEqual(body['field'], 'pockets.G2.depth')      # the id, never the long key
        stored = json.loads((self.dir / 'project.json').read_text())
        self.assertEqual(stored['pockets'], {key: {'depth': 5}})

    def test_null_override_of_a_group_means_no_override(self):
        self.seed(PLATES[:1])
        _, proj = self.call('GET', '/api/project')
        key = proj['pocket_groups'][0]['key']
        proj['pockets'] = {key: None}
        status, put = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 200, put)
        self.assertEqual(put['pocket_groups'][0]['depth'], Settings().pockets.depth)
        self.assertNotIn('error', put['pocket_groups'][0])
        status, plan = self.call('GET', '/api/plan')
        self.assertTrue(plan['blanks'], plan['problems'])

    def test_circle_warning_once_per_circle_and_not_when_group_is_off(self):
        (self.dir / 'shapes' / 'round.dxf').write_text(dxf(
            rect(0, 0, 600, 200), circle(50, 100, 3.3), circle(550, 100, 3.3),
            circle(300, 100, 5), circle(300, 100, 5), circle(400, 100, 5)))
        _, proj = self.call('GET', '/api/project')
        proj['shapes'][0]['qty'] = 2
        status, proj = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 200, proj)
        _, plan = self.call('GET', '/api/plan')
        warned = [p for p in plan['problems'] if 'treated as a pocket' in p]
        self.assertEqual(len(warned), 2, plan['problems'])         # two places, not 2 x 3
        proj['pockets'] = {g['key']: {'enabled': False} for g in proj['pocket_groups']}
        status, proj = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 200, proj)
        _, plan = self.call('GET', '/api/plan')
        self.assertFalse(any('treated as a pocket' in p for p in plan['problems']),
                         plan['problems'])

    def test_circle_pocket_is_a_warning_and_min_circle_20_makes_it_a_hole(self):
        self.circle_plate()
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200, plan)
        self.assertTrue(any('circle of 10 mm is treated as a pocket' in p
                            for p in plan['problems']), plan['problems'])
        self.assertIn('B01P', [p['name'] for b in plan['blanks'] for p in b['programs']])
        _, proj = self.call('GET', '/api/project')
        self.assertEqual(len(proj['pocket_groups']), 1)
        self.assertEqual(proj['pocket_groups'][0]['kind'], 'round')
        proj['settings']['pockets']['min_circle_diameter'] = 20
        status, proj = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 200, proj)
        self.assertEqual(proj['pocket_groups'], [])
        status, plan = self.call('GET', '/api/plan')
        self.assertFalse(any('treated as a pocket' in p for p in plan['problems']))
        self.assertNotIn('B01P', [p['name'] for b in plan['blanks'] for p in b['programs']])
        proj['settings']['pockets']['min_circle_diameter'] = 8      # and back: read again
        status, proj = self.call('PUT', '/api/project', proj)
        self.assertEqual(len(proj['pocket_groups']), 1)

    def test_generate_writes_pocket_programs_with_the_overrides(self):
        self.seed(PLATES[:2])
        _, proj = self.call('GET', '/api/project')
        status, default_text = self.call('GET', '/api/program?name=B01P')
        self.assertEqual(status, 200)
        proj['pockets'] = {g['key']: {'depth': 5} for g in proj['pocket_groups']}
        self.assertEqual(self.call('PUT', '/api/project', proj)[0], 200)
        status, text = self.call('GET', '/api/program?name=B01P')
        self.assertEqual(status, 200)
        self.assertNotEqual(text, default_text)
        status, plan = self.call('GET', '/api/plan')
        self.assertTrue(all(g['depth'] == 5 for g in plan['pocket_groups']))
        status, res = self.call('POST', '/api/generate')
        self.assertEqual(status, 200, res)
        folder = Path(res['folder'])
        self.assertIn('B01P', res['programs'])
        self.assertEqual((folder / 'B01P').read_bytes(), text.encode('ascii'))
        self.assertTrue((folder / 'DISKETTE').is_dir())
        disk = [p.name for p in (folder / 'DISKETTE').rglob('*')]
        self.assertIn('B01P', disk)
        meta = json.loads((folder / 'PROJECT.json').read_text())
        self.assertEqual(meta['pockets'], proj['pockets'])
        self.assertTrue(all(g['depth'] == 5 for g in meta['pocket_groups']))

    def test_binds_to_localhost_only(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')

    def test_page_is_served_without_external_resources(self):
        status, html = self.call('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn('<title>', html)
        for bad in ('http://', 'https://', '//cdn', 'illustrative sketch'):
            self.assertNotIn(bad, html.replace('http://www.w3.org/2000/svg', ''))
        self.assertIn('below the top of the stack', html)
        self.assertEqual(self.call('GET', '/nope')[0], 404)

    def test_page_and_readme_say_which_drill_settings_are_not_written(self):
        # I2: G81 carries no F and no diameter; both are listed on the run sheet per tool
        status, html = self.call('GET', '/')
        self.assertEqual(status, 200)
        readme = (repo / 'nesting' / 'README.md').read_text()
        feed = "not written to the program (the control uses the tool's own feed)"
        dia = 'not written to the program (the tool number picks the drill); listed per tool on the run sheet'
        for text in (html, readme):
            self.assertIn(feed, text)
            self.assertIn(dia, text)
        # the drill bits' plunge feed and diameter carry the notes on the Tools page
        self.assertIn("note: NOTE_FEED", html)
        self.assertIn("note: NOTE_DIA", html)
        self.assertIn(f"const NOTE_FEED = \"{feed}\"", html)
        self.assertIn(f"const NOTE_DIA = '{dia}'", html)
        for row in ('| drill_fix |', '| drill_screw |'):
            line = next(l for l in readme.splitlines() if l.startswith(row))
            self.assertIn(feed, line)
            self.assertIn(dia, line)

    def first_contour_min_x(self):
        status, text = self.call('GET', '/api/program?name=B01C')
        self.assertEqual(status, 200, text)
        lines = text.splitlines()[2:]               # after G71 and G150()
        xs = []
        for i, line in enumerate(lines):
            if line.startswith('G88') and i:
                break
            m = re.search(r'X(-?[\d.]+)', line)
            if m:
                xs.append(float(m.group(1)))
        return min(xs)

    def test_put_router_diameter_7_8_offsets_by_3_9(self):
        # I4: any diameter can be typed; the contour is offset by half of it
        self.seed(PLATES[:1])
        _, proj = self.call('GET', '/api/project')
        self.assertAlmostEqual(self.first_contour_min_x(), 45 - 4)      # blank coordinates
        bid = proj['tools']['heads']['T66']                  # the bit in T66
        bit = next(b for b in proj['tools']['bits'] if b['id'] == bid)
        bit['diameter'] = 7.8
        status, body = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 200, body)
        self.assertEqual(body['settings']['router']['tool'], 66)
        self.assertAlmostEqual(self.first_contour_min_x(), 45 - 3.9)
        bit['diameter'] = 0
        status, body = self.call('PUT', '/api/project', proj)
        self.assertEqual((status, body['field']), (400, f'tools.bits.{bid}.diameter'))

    def test_page_router_picks_a_head_without_a_preset(self):
        status, html = self.call('GET', '/')
        self.assertNotIn('<select id="tool"', html)
        self.assertRegex(html, r"\['router\.tool', [^\]]*'head'")
        self.assertNotRegex(html, r"\['router\.diameter', ")
        self.assertNotIn('<select id="preset"', html)
        self.assertNotIn('ROUTER_TOOLS', html)

    def test_page_has_a_tools_page_with_bits_and_heads(self):
        status, html = self.call('GET', '/')
        self.assertEqual(status, 200)
        for needle in ('id="toolsPage"', 'id="bitsTable"', 'id="headsTable"'):
            self.assertIn(needle, html)
        for gone in ('router.spindle_rpm', 'router.plunge_feed', 'router.cut_feed',
                     'router.depth_per_pass', 'router.diameter', 'pockets.diameter',
                     'pockets.depth_per_pass', 'pockets.spindle_rpm', 'pockets.plunge_feed',
                     'pockets.cut_feed', 'pockets.stepover_pct', 'drill_fix.feed',
                     'drill_fix.diameter', 'drill_screw.feed', 'drill_screw.diameter',
                     'ROUTER_TOOLS'):
            self.assertNotIn(gone, html)
        group_fields = html.split('const GROUP_FIELDS')[1].split(';')[0]
        for gone in ('diameter', 'depth_per_pass', 'plunge_feed', 'cut_feed', 'stepover_pct'):
            self.assertNotIn(gone, group_fields)
        # heads by fixed label, bits by type; every save sends the table; its errors map
        for needle in ("['drill_fix.tool', ", "['drill_screw.tool', ", "['drill_screw.depth', ",
                       "['pockets.tool', ", 'tools: project.tools', 'tools_error',
                       'tools_notes', 'tool_labels', "'listed only: no program uses this head'",
                       ': empty that head first', "/^tools\\.(bits|heads)\\.",
                       'default ('):
            self.assertIn(needle, html)
        # bit names are user text: never markup
        self.assertNotRegex(html, r'innerHTML\s*=\s*[^;]*name')

    def test_page_has_a_pockets_section_with_defaults_and_group_rows(self):
        status, html = self.call('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn('<h2 id="pockets">Pockets</h2>', html)
        self.assertIn('<div id="pocketGroups">', html)
        for key in ('min_circle_diameter', 'min_floor', 'tool', 'depth', 'direction'):
            self.assertRegex(html, r"\['pockets\.%s', " % key)
        self.assertRegex(html, r"\['pockets\.min_circle_diameter', '[^']*pocket[^']*hole")
        for name in ('tool', 'depth'):
            self.assertIn(f"['{name}', ", html.split('const GROUP_FIELDS')[1].split(';')[0])
        # overrides by group key, saved with the project; field errors of a group's row
        self.assertIn('project.pockets[key]', html)
        self.assertIn('`pockets.${g.id}.${name}`', html)
        self.assertIn(r"/^pockets\.(G\d+)(?:\.(.+))?$/", html)
        # the drawing: pockets in their group colour, the rings in the cut view, B..P listed
        self.assertIn('q.pockets', html)
        self.assertIn('b.pocket_rings', html)
        self.assertIn('pocket (group colour)', html)
        self.assertIn("pocket: 'cut'", html)

    def test_page_sets_no_html_from_data(self):
        # only the SVG drawings are built as markup, every value in them through esc();
        # group colours are checked before they are used
        status, html = self.call('GET', '/')
        script = html.split('<script>')[1]
        uses = re.findall(r'\.innerHTML\s*=\s*([^;]+);', script)
        self.assertEqual(sorted(set(uses)), sorted({'s', "'<text x=\"500\" y=\"100\" font-size=\"32\" text-anchor=\"middle\" fill=\"#667085\">No blank</text>'"}))
        self.assertNotIn('insertAdjacentHTML', script)
        self.assertNotIn('outerHTML', script)
        self.assertIn('const COLOR_RE = /^#[0-9a-f]{6}$/i;', script)
        self.assertIn('swatch.style.backgroundColor = safeColor(g.color)', script)
        self.assertNotRegex(script, r'\$\{(?:pk|r|g)\.color\}')

    def test_end_to_end_12_plates(self):
        self.assertEqual(seed_plates(self.dir), 12)
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200)
        self.assertEqual(len(plan['panels']), 3)
        self.assertEqual(plan['problems'], [])
        status, res = self.call('POST', '/api/generate', {})
        self.assertEqual(status, 200, res)
        folder = Path(res['folder'])
        self.assertEqual(folder.parent, self.dir / 'out')
        names = [f'B0{n}{k}' for n in range(1, 7) for k in 'DPC']
        self.assertEqual(res['programs'], names)
        for name in names + ['LOAD.BAT', 'PROJECT.json', 'RUNSHEET.html']:
            self.assertIn(name, res['files'])
        programs = [f for f in folder.iterdir() if f.name in names]
        self.assertEqual(sorted(f.name for f in programs), sorted(names))
        r = subprocess.run([sys.executable, str(repo / 'tools' / 'check_cnc90.py'),
                            *map(str, programs)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(res['diskette'], str(folder / 'DISKETTE'))
        self.assertIsNone(res['diskette_warning'])
        self.assertIn('DISKETTE', res['files'])
        # depth per pass must not be ignored: each cut contour is cut in several passes
        text = next(f for f in programs if f.name == 'B01C').read_text(encoding='ascii')
        starts = re.findall(r'^G88\S*?(X-?[\d.]+Y-?[\d.]+)Z(-?[\d.]+)$', text, re.M)
        self.assertTrue(starts, text)
        first_zs = [z for xy, z in starts if xy == starts[0][0]]
        self.assertGreater(len(set(first_zs)), 1, first_zs)

    def test_seed_plates_only_into_empty_project(self):
        self.assertEqual(seed_plates(self.dir), 12)
        self.assertEqual(sorted(p.name for p in (self.dir / 'shapes').glob('*.dxf')),
                         sorted(p.name for p in PLATES))
        (self.dir / 'shapes' / 'extra.dxf').write_bytes(b'x')
        (self.dir / 'shapes' / PLATES[0].name).unlink()
        before = sorted(p.name for p in (self.dir / 'shapes').iterdir())
        self.assertEqual(seed_plates(self.dir), 0)
        self.assertEqual(sorted(p.name for p in (self.dir / 'shapes').iterdir()), before)

    def run_main(self, *args):
        import contextlib
        import io
        from nesting.server import main
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = main(['nesting', *args])
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()

    def test_cli_help_exits_zero(self):
        code, out, _ = self.run_main('--help')
        self.assertEqual(code, 0)
        self.assertIn('--seed-plates', out)

    def test_cli_help_names_the_command_that_works_on_windows(self):
        # I5: python.org installs `python` and `py` on Windows; `python3` opens the Store stub
        r = subprocess.run([sys.executable, '-m', 'nesting', '--help'], cwd=repo,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('python -m nesting', r.stdout)
        self.assertIn('py -m nesting', r.stdout)
        self.assertIn('busellato-cnc folder', r.stdout)
        self.assertNotIn('python3', r.stdout)

    def test_no_python3_start_command_anywhere(self):
        texts = {p: p.read_text() for p in (repo / 'README.md', repo / 'nesting' / 'README.md',
                                            repo / 'nesting' / 'server.py',
                                            repo / 'nesting' / '__main__.py')}
        for path, text in texts.items():
            self.assertNotIn('python3 -m nesting', text, path)
        readme = texts[repo / 'nesting' / 'README.md']
        self.assertIn('python -m nesting', readme)
        self.assertIn('py -m nesting', readme)
        self.assertIn('busellato-cnc folder', readme)
        self.assertIn('python -m unittest discover -s tests', readme)

    def test_cli_out_of_range_port_exits_one(self):
        code, out, err = self.run_main(str(self.dir), '--seed-plates', '--port', '99999')
        self.assertEqual(code, 1)
        self.assertIn('Cannot use port 99999', err)
        self.assertNotIn('Traceback', err)
        self.assertEqual(len(list((self.dir / 'shapes').glob('*.dxf'))), 12)

    def test_cli_port_in_use_exits_one(self):
        import socket
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            s.listen()
            port = s.getsockname()[1]
            code, _, err = self.run_main(str(self.dir), '--port', str(port))
        self.assertEqual(code, 1)
        self.assertIn(f'Cannot use port {port}', err)
        self.assertNotIn('Traceback', err)

    def test_cli_open_opens_the_page_once_listening(self):
        server = mock.Mock(server_address=('127.0.0.1', 8800))
        server.serve_forever.side_effect = KeyboardInterrupt
        with mock.patch('nesting.server.make_server', return_value=server), \
                mock.patch('nesting.server.threading.Timer') as timer:
            code, out, _ = self.run_main(str(self.dir), '--port', '8800', '--open')
        self.assertEqual(code, 0)
        timer.assert_called_once()
        self.assertEqual(timer.call_args.args[2], ['http://127.0.0.1:8800/'])
        timer.return_value.start.assert_called_once()
        server.server_close.assert_called_once()

    def test_cli_open_does_nothing_when_the_port_is_taken(self):
        with mock.patch('nesting.server.make_server', side_effect=OSError('in use')), \
                mock.patch('nesting.server.threading.Timer') as timer:
            code, _, _ = self.run_main(str(self.dir), '--port', '8800', '--open')
        self.assertEqual(code, 1)
        timer.assert_not_called()


    # --- the tool table in project.json -----------------------------------------------------
    # the settings of a real project from before the tool table (Task 3's real-project shape)
    OLD_SETTINGS = {
        'router': {'tool': 66, 'diameter': 8, 'spindle_rpm': 18000, 'plunge_feed': 1,
                   'cut_feed': 2, 'depth_per_pass': 9},
        'pockets': {'tool': 66, 'diameter': 8, 'cut_feed': 3, 'depth_per_pass': 4,
                    'stepover_pct': 40},
        'drill_fix': {'tool': 10, 'diameter': 5, 'feed': 1},
        'drill_screw': {'tool': 10, 'diameter': 5, 'feed': 1},
    }

    def write_old_project(self, pockets=None) -> str:
        """project.json in the form before the tool table (no `tools`); returns its text."""
        s = Settings().to_dict()
        for section, values in self.OLD_SETTINGS.items():
            s[section].update(values)
        text = json.dumps({'shapes': [], 'settings': s, 'pockets': pockets or {}}, indent=2)
        (self.dir / 'project.json').write_text(text)
        return text

    def group_keys(self) -> dict:
        _, proj = self.call('GET', '/api/project')
        return {g['id']: g['key'] for g in proj['pocket_groups']}

    def all_programs(self) -> dict:
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200, plan)
        self.assertIsNone(plan['settings_error'])
        names = [p['name'] for b in plan['blanks'] for p in b['programs']]
        self.assertTrue(names)
        return {n: self.call('GET', f'/api/program?name={n}')[1] for n in names}

    def test_old_project_migrates_on_load(self):
        self.seed(PLATES[:1])
        text = self.write_old_project()
        status, proj = self.call('GET', '/api/project')
        self.assertEqual(status, 200, proj)
        self.assertEqual(proj['tools']['heads'], {'T10': 'b2', 'T66': 'b1'})
        self.assertIsNone(proj['tools_error'])
        self.assertEqual(len(proj['tools_notes']), 1)
        note = proj['tools_notes'][0]
        self.assertTrue(note.startswith('T66 '), note)
        self.assertIn('cut feed 3', note)
        self.assertEqual(proj['heads'][0], {'number': 1, 'label': 'drill cross, vertical',
                                            'allows': ['drill']})
        self.assertIn({'number': 66, 'label': 'big spindle', 'allows': ['router']},
                      proj['heads'])
        self.assertEqual([h['number'] for h in proj['heads']],
                         sorted(h['number'] for h in proj['heads']))
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200)
        self.assertIsNone(plan['settings_error'])
        self.assertEqual(plan['problems'][0], note)
        self.assertEqual((self.dir / 'project.json').read_text(), text)   # no write on load

    def test_ignored_override_lines(self):
        self.seed(PLATES[:2])
        keys = self.group_keys()
        self.write_old_project({keys['G1']: {'diameter': 12}, 'gone': {'cut_feed': 2.5}})
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200)
        self.assertIsNone(plan['settings_error'])
        g1 = [p for p in plan['problems'] if 'pocket group G1' in p]
        self.assertEqual(len(g1), 1, plan['problems'])
        self.assertIn('diameter 12', g1[0])
        self.assertIn('ignored', g1[0])
        self.assertIn('pocket group G1: old setting diameter 12 is ignored (speeds and feeds '
                      'come from the bit in its head)', plan['problems'])
        self.assertIn('a stored pocket setting: old setting cut_feed 2.5 is ignored (speeds '
                      'and feeds come from the bit in its head)', plan['problems'])
        _, proj = self.call('GET', '/api/project')
        self.assertEqual(plan['problems'][:len(proj['tools_notes'])], proj['tools_notes'])

    def test_migration_then_save_is_stable(self):
        self.seed(PLATES[:2])
        keys = self.group_keys()
        self.write_old_project({keys['G1']: {'diameter': 12, 'depth': 6},
                                keys['G2']: {'cut_feed': 2}})
        before = self.all_programs()
        status, proj = self.call('GET', '/api/project')
        self.assertTrue(proj['tools_notes'])
        status, body = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 200, body)
        self.assertEqual(body['tools_notes'], [])
        data = json.loads((self.dir / 'project.json').read_text())
        self.assertEqual(set(data), {'shapes', 'settings', 'pockets', 'tools'})
        self.assertEqual(data['tools'], proj['tools'])
        self.assertEqual(data['pockets'], {keys['G1']: {'depth': 6}})   # G2's was all obsolete
        status, again = self.call('GET', '/api/project')
        self.assertEqual(again['tools_notes'], [])
        self.assertEqual([b['id'] for b in again['tools']['bits']],
                         [b['id'] for b in proj['tools']['bits']])
        self.assertEqual(again['tools'], proj['tools'])
        self.assertEqual(self.all_programs(), before)

    def test_save_without_tools_keeps_the_stored_table(self):
        self.seed(PLATES[:1])
        _, proj = self.call('GET', '/api/project')
        bit = next(b for b in proj['tools']['bits'] if b['id'] == 'b1')
        bit['diameter'] = 12
        self.assertEqual(self.call('PUT', '/api/project', proj)[0], 200)
        old_page = {k: proj[k] for k in ('shapes', 'settings', 'pockets')}
        status, body = self.call('PUT', '/api/project', old_page)
        self.assertEqual(status, 200, body)
        _, again = self.call('GET', '/api/project')
        self.assertEqual(next(b for b in again['tools']['bits'] if b['id'] == 'b1')['diameter'],
                         12)
        self.assertEqual(again['tools'], proj['tools'])

    def test_save_without_tools_on_an_old_project_writes_the_migrated_table(self):
        self.seed(PLATES[:1])
        self.write_old_project()
        _, proj = self.call('GET', '/api/project')
        old_page = {k: proj[k] for k in ('shapes', 'settings', 'pockets')}
        self.assertEqual(self.call('PUT', '/api/project', old_page)[0], 200)
        data = json.loads((self.dir / 'project.json').read_text())
        self.assertEqual(data['tools'], proj['tools'])
        self.assertEqual(data['tools']['heads'], {'T10': 'b2', 'T66': 'b1'})

    def test_save_refuses_bad_table(self):
        self.seed(PLATES[:1])
        _, proj = self.call('GET', '/api/project')
        bad = json.loads(json.dumps(proj))
        bad['tools']['heads']['T66'] = 'b9'
        status, body = self.call('PUT', '/api/project', bad)
        self.assertEqual((status, body['field']), (400, 'tools.heads.T66'))
        bad = json.loads(json.dumps(proj))
        bad['tools']['heads']['T1'] = 'b1'                  # the router bit in a drill head
        status, body = self.call('PUT', '/api/project', bad)
        self.assertEqual((status, body['field']), (400, 'tools.heads.T1'))
        bad['tools'] = None
        status, body = self.call('PUT', '/api/project', bad)
        self.assertEqual((status, body['field']), (400, 'tools'))
        self.assertFalse((self.dir / 'project.json').exists())

    def test_save_over_an_unreadable_project_json(self):
        # without `tools` the table to keep is unknown: refused, not a silent default
        self.seed(PLATES[:1])
        _, proj = self.call('GET', '/api/project')
        (self.dir / 'project.json').write_text('{not json')
        old_page = {k: proj[k] for k in ('shapes', 'settings', 'pockets')}
        status, body = self.call('PUT', '/api/project', old_page)
        self.assertEqual((status, body['field']), (400, 'tools'))
        self.assertEqual((self.dir / 'project.json').read_text(), '{not json')
        status, body = self.call('PUT', '/api/project', proj)     # with the table: written
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads((self.dir / 'project.json').read_text())['tools'],
                         proj['tools'])

    def test_bad_tools_in_project_json_is_reported(self):
        self.seed(PLATES[:1])
        good = Settings().to_dict()
        for tools, field in (({'bits': [], 'heads': {'T66': 'b1'}}, 'tools.heads.T66'),
                             ({'bits': 'x', 'heads': {}}, 'tools.bits'),
                             ('x', 'tools'),
                             (None, 'tools')):
            with self.subTest(field=field, tools=tools):
                text = json.dumps({'shapes': [], 'settings': good, 'tools': tools})
                (self.dir / 'project.json').write_text(text)
                status, proj = self.call('GET', '/api/project')
                self.assertEqual(status, 200, proj)
                self.assertEqual(proj['tools_error']['field'], field)
                self.assertEqual(proj['tools'], tools)              # as stored, not a default
                for g in proj['pocket_groups']:
                    self.assertFalse(g['enabled'])
                    self.assertIn(field, g['error'])
                status, plan = self.call('GET', '/api/plan')
                self.assertEqual(status, 200)
                self.assertEqual(plan['settings_error']['field'], field)
                self.assertNoTrace(plan)
                status, body = self.call('POST', '/api/generate', {})
                self.assertEqual((status, body.get('field')), (400, field))
                status, body = self.call('PUT', '/api/project',
                                         {k: proj[k] for k in ('shapes', 'settings', 'pockets')})
                self.assertEqual((status, body.get('field')), (400, field))
                self.assertEqual((self.dir / 'project.json').read_text(), text)
                status, body = self.call('POST', '/api/shapes',
                                         {'filename': 'r.dxf', 'text': dxf(rect(0, 0, 300, 200))})
                self.assertEqual(status, 200, body)

if __name__ == '__main__':
    unittest.main()
