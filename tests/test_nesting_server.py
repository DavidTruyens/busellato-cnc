import http.client
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from nesting.server import make_server, seed_plates
from nesting.settings import Settings
from test_nesting_dxf import dxf, line, rect

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
        proj['settings']['router']['cut_feed'] = 4.5
        proj['settings']['template']['mode'] = 'none'
        status, put = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 200)
        self.assertEqual(put, proj)
        self.assertTrue((self.dir / 'project.json').is_file())
        self.server.shutdown()
        self.server.server_close()
        self.start()                              # a fresh server reads project.json
        status, again = self.call('GET', '/api/project')
        self.assertEqual(again, proj)

    def test_put_invalid_settings_is_400_and_not_saved(self):
        self.seed(PLATES[:1])
        _, proj = self.call('GET', '/api/project')
        good = json.loads(json.dumps(proj))
        proj['settings']['router']['depth_per_pass'] = -1
        status, body = self.call('PUT', '/api/project', proj)
        self.assertEqual(status, 400)
        self.assertEqual(body['field'], 'router.depth_per_pass')
        self.assertTrue(body['message'])
        self.assertFalse((self.dir / 'project.json').exists())
        self.assertEqual(self.call('GET', '/api/project')[1], good)
        proj['settings']['router']['depth_per_pass'] = 9
        proj['settings']['router']['tool'] = 66.5
        status, body = self.call('PUT', '/api/project', proj)
        self.assertEqual((status, body['field']), (400, 'router.tool'))
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
            self.assertTrue(any('N1C' in p and 'cups' in p for p in plan['problems']), plan['problems'])
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
        names = [p['name'] for panel in plan['panels'] for p in panel['programs']]
        self.assertEqual(len(names), 9)
        self.assertEqual(plan['problems'], [])
        self.assertIsNone(plan['settings_error'])
        z = plan['panels'][0]['z']
        self.assertEqual(set(z), {'stack_top', 'fixing', 'screw', 'shape_cut', 'template_cut'})

    def test_plan_reports_oversize_shape_not_error(self):
        self.seed(PLATES[:1])
        (self.dir / 'shapes' / 'huge.dxf').write_text(dxf(rect(0, 0, 3000, 100)))
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200)
        self.assertIsNone(plan['settings_error'])
        self.assertTrue(any('huge' in p for p in plan['problems']), plan['problems'])
        self.assertEqual(len(plan['panels']), 1)
        self.assertNoTrace(plan)

    def test_plan_with_invalid_setting_returns_field_error(self):
        self.seed(PLATES[:2])
        s = Settings().to_dict()
        s['template']['shapes_per'] = 0
        (self.dir / 'project.json').write_text(json.dumps({'shapes': [], 'settings': s}))
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200)
        self.assertEqual(plan['settings_error']['field'], 'template.shapes_per')
        self.assertTrue(plan['settings_error']['message'])
        self.assertEqual(plan['panels'], [])
        self.assertNoTrace(plan)

    def test_plan_with_offset_error_is_a_problem(self):
        self.seed(PLATES[:1])
        s = Settings().to_dict()
        s['router']['diameter'] = 200          # cannot follow the outline
        s['template']['mode'] = 'none'
        (self.dir / 'project.json').write_text(json.dumps({'shapes': [], 'settings': s}))
        status, plan = self.call('GET', '/api/plan')
        self.assertEqual(status, 200)
        self.assertEqual(plan['panels'], [])
        self.assertIn('narrower than the tool', ' '.join(plan['problems']))
        self.assertIsNone(plan['settings_error'])
        self.assertNoTrace(plan)

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
        status, text = self.call('GET', '/api/program?name=N1C')
        self.assertEqual(status, 200)
        status, _ = self.call('POST', '/api/generate')
        out = next((self.dir / 'out').iterdir())
        self.assertEqual(text.encode('ascii'), (out / 'N1C').read_bytes())
        status, body = self.call('GET', '/api/program?name=N9Z')
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
            for n in ('N1F', 'N3C', 'LOAD.BAT', 'RUNSHEET.html', 'PROJECT.json'):
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
        raw = json.dumps(proj).replace('"cut_feed": 3', '"cut_feed": 1e400').encode()
        self.assertIn(b'1e400', raw)
        status, body = self.call('PUT', '/api/project', raw=raw)
        self.assertEqual(status, 400)
        self.assertEqual(body['field'], 'router.cut_feed')
        self.assertFalse((self.dir / 'project.json').exists())
        raw = json.dumps(proj).replace('"qty": 1', '"qty": 1e400').encode()
        status, body = self.call('PUT', '/api/project', raw=raw)
        self.assertEqual(status, 400)
        self.assertIn('qty', body['field'])
        self.assertFalse((self.dir / 'project.json').exists())

    def test_z_values_match_the_program_text(self):
        self.seed(PLATES[:2])
        _, proj = self.call('GET', '/api/project')
        proj['settings']['heights']['into_template'] = 0.05
        proj['settings']['heights']['shape_thickness'] = 18.2
        proj['settings']['drill_screw']['depth'] = 8.2
        self.assertEqual(self.call('PUT', '/api/project', proj)[0], 200)
        _, plan = self.call('GET', '/api/plan')
        z = plan['panels'][0]['z']
        for v in z.values():
            self.assertEqual(v, round(v, 3))
        self.assertEqual(z['shape_cut'], 18.25)
        self.assertEqual(z['screw'], 26.4)          # 54.2 - (36 - 8.2)
        _, cut = self.call('GET', '/api/program?name=N1C')
        self.assertIn('Z18.25', cut)
        _, screw = self.call('GET', '/api/program?name=N1S')
        self.assertIn('Z26.4\r', screw)

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
        names = [f'N{n}{k}' for n in (1, 2, 3) for k in 'FSC']
        self.assertEqual(res['programs'], names)
        for name in names + ['LOAD.BAT', 'PROJECT.json', 'RUNSHEET.html']:
            self.assertIn(name, res['files'])
        programs = [f for f in folder.rglob('*') if f.name in names]
        self.assertEqual(sorted(f.name for f in programs), sorted(names))
        r = subprocess.run([sys.executable, str(repo / 'tools' / 'check_cnc90.py'),
                            *map(str, programs)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # depth per pass must not be ignored: each cut contour is cut in several passes
        text = next(f for f in programs if f.name == 'N1C').read_text(encoding='ascii')
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


if __name__ == '__main__':
    unittest.main()
