"""Local web server: the page plus a small JSON API over one project folder.

  python3 -m nesting.server PROJECT_DIR [PORT]

PROJECT_DIR/shapes/*.dxf are the shapes, PROJECT_DIR/project.json holds quantities, on/off
flags and settings, PROJECT_DIR/out/<YYYYMMDD-HHMMSS>/ receives each generated job.
Binds to 127.0.0.1 only.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .backends import BACKENDS
from .dxf import DxfError, Shape, read_dxf
from .geometry import OffsetError
from .layout import ShapeEntry, build_plan
from .output import write_output
from .preview import preview_data
from .program import plan_programs
from .settings import Settings, SettingsError

HOST = '127.0.0.1'
MAX_BODY = 20 * 1024 * 1024
PAGE = Path(__file__).resolve().parent / 'web' / 'index.html'
SAFE_NAME = re.compile(r'[A-Za-z0-9._ -]+')
TOOL_FIELDS = ('router.tool', 'drill_fix.tool', 'drill_screw.tool')


class ApiError(Exception):
    def __init__(self, status: int, body: dict):
        super().__init__(body)
        self.status = status
        self.body = body


def _reject_constant(name):
    raise ValueError(f'{name} is not a number')


def _loads(raw: bytes):
    try:
        return json.loads(raw.decode('utf-8'), parse_constant=_reject_constant)
    except ValueError as e:
        raise ApiError(400, {'error': f'request is not valid JSON: {e}'})


def validate(settings: Settings) -> None:
    settings.validate()
    for path in TOOL_FIELDS:
        v = settings._get(path)
        if isinstance(v, bool) or not isinstance(v, int):
            raise SettingsError(path, 'must be a whole tool number')


def safe_filename(name) -> str:
    """Last path component of `name` if it is a plain `*.dxf` name; else ApiError 400."""
    base = re.split(r'[\\/]', name if isinstance(name, str) else '')[-1].strip()
    if (not SAFE_NAME.fullmatch(base) or not base.lower().endswith('.dxf')
            or base.startswith('.')):
        raise ApiError(400, {'error': f'file name {base or name!r} not allowed: use letters, '
                                      'digits, space, . _ - and the extension .dxf'})
    return base


class Project:
    """The project folder. All access goes through one lock."""

    def __init__(self, folder: Path):
        self.dir = Path(folder)
        self.shapes_dir = self.dir / 'shapes'
        self.file = self.dir / 'project.json'
        self.lock = threading.Lock()
        self._cache: dict[str, tuple[float, Shape]] = {}

    # --- stored state -------------------------------------------------------------------
    def _stored(self) -> dict:
        if not self.file.exists():
            return {'shapes': [], 'settings': Settings().to_dict()}
        data = json.loads(self.file.read_text(encoding='utf-8'))
        return {'shapes': list(data.get('shapes') or []),
                'settings': Settings.from_dict(data.get('settings') or {}).to_dict()}

    def _shapes(self) -> tuple[list[Shape], list[str]]:
        """Shapes read from shapes/*.dxf (cached by mtime), plus a message per unreadable file."""
        shapes, errors = [], []
        files = sorted(self.shapes_dir.glob('*.dxf')) if self.shapes_dir.is_dir() else []
        for path in files:
            mtime = path.stat().st_mtime
            hit = self._cache.get(path.name)
            if hit and hit[0] == mtime:
                shapes.append(hit[1])
                continue
            try:
                shape = read_dxf(path)
            except DxfError as e:
                errors.append(str(e))
                continue
            self._cache[path.name] = (mtime, shape)
            shapes.append(shape)
        return shapes, errors

    def _merged(self):
        """(shapes in list order with qty/enabled, settings dict, dxf errors)."""
        stored = self._stored()
        shapes, errors = self._shapes()
        by_name = {s.name: s for s in shapes}
        rows, seen = [], set()
        for e in stored['shapes']:
            name = e.get('name') if isinstance(e, dict) else None
            if name in by_name and name not in seen:
                seen.add(name)
                rows.append((by_name[name], int(e.get('qty', 1)), bool(e.get('enabled', True))))
        rows += [(s, 1, True) for s in shapes if s.name not in seen]
        return rows, stored['settings'], errors

    def project(self) -> dict:
        rows, settings, _ = self._merged()
        return {'shapes': [{'name': s.name, 'length': round(s.length, 3),
                            'width': round(s.width, 3), 'qty': q, 'enabled': on}
                           for s, q, on in rows],
                'settings': settings}

    def save(self, body) -> dict:
        if not isinstance(body, dict):
            raise ApiError(400, {'error': 'expected an object with shapes and settings'})
        settings = Settings.from_dict(body.get('settings') or {})
        try:
            validate(settings)
        except SettingsError as e:
            raise ApiError(400, {'field': e.field, 'message': e.message})
        shapes = []
        for e in body.get('shapes') or []:
            name = e.get('name') if isinstance(e, dict) else None
            if not isinstance(name, str):
                raise ApiError(400, {'field': 'shapes', 'message': 'every shape needs a name'})
            qty, on = e.get('qty', 1), e.get('enabled', True)
            if isinstance(qty, bool) or not isinstance(qty, int) or qty < 0:
                raise ApiError(400, {'field': f'shapes.{name}.qty',
                                     'message': 'must be a whole number, 0 or more'})
            if not isinstance(on, bool):
                raise ApiError(400, {'field': f'shapes.{name}.enabled',
                                     'message': 'must be true or false'})
            shapes.append({'name': name, 'qty': qty, 'enabled': on})
        self.dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix='.project-', suffix='.json')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump({'shapes': shapes, 'settings': settings.to_dict()}, f, indent=2)
        os.replace(tmp, self.file)
        return self.project()

    # --- shapes ---------------------------------------------------------------------------
    def upload(self, body) -> dict:
        if not isinstance(body, dict) or not isinstance(body.get('text'), str):
            raise ApiError(400, {'error': 'expected {"filename": ..., "text": ...}'})
        name = safe_filename(body.get('filename'))
        self.shapes_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.dir, prefix='.upload-') as tmp:
            path = Path(tmp) / name                 # same name, so messages name the file
            path.write_text(body['text'], encoding='utf-8')
            try:
                shape = read_dxf(path)
            except DxfError as e:
                raise ApiError(400, {'error': str(e)})
            target = self.shapes_dir / name
            replaced = target.exists()
            os.replace(path, target)
        return {'name': shape.name, 'length': round(shape.length, 3),
                'width': round(shape.width, 3), 'holes': len(shape.holes), 'replaced': replaced}

    # --- plan -----------------------------------------------------------------------------
    def compute(self):
        """(settings, plan, programs, problems); raises SettingsError, OffsetError, ValueError."""
        rows, settings_dict, errors = self._merged()
        settings = Settings.from_dict(settings_dict)
        validate(settings)
        entries = [ShapeEntry(s, q, on) for s, q, on in rows]
        plan = build_plan(entries, settings)
        programs = plan_programs(plan, settings)
        return settings, plan, programs, errors + list(plan.problems)

    def plan(self) -> dict:
        try:
            settings = Settings.from_dict(self._stored()['settings'])
        except ValueError as e:        # unreadable project.json
            settings = Settings()
            return self._failed(settings, [f'project.json: {e}'], None)
        try:
            settings, plan, programs, problems = self.compute()
            data = preview_data(plan, programs, settings)
        except SettingsError as e:
            return self._failed(settings, [], {'field': e.field, 'message': e.message})
        except (OffsetError, DxfError, ValueError) as e:
            return self._failed(settings, [str(e)], None)
        data['problems'] = problems
        data['settings_error'] = None
        return data

    @staticmethod
    def _failed(settings: Settings, problems, settings_error) -> dict:
        panel = {'length': settings.panel.length, 'width': settings.panel.width}
        return {'panel': panel, 'panels': [], 'problems': problems,
                'settings_error': settings_error}

    def program_text(self, name: str) -> str:
        try:
            settings, _, programs, _ = self.compute()
        except (OffsetError, ValueError) as e:      # SettingsError is a ValueError
            raise ApiError(400, {'error': str(e)})
        for p in programs:
            if p.name == name:
                return BACKENDS['cnc90'](p, settings)
        raise ApiError(404, {'error': f'no program {name!r} in the current plan'})

    def generate(self) -> dict:
        try:
            settings, plan, programs, problems = self.compute()
        except SettingsError as e:
            raise ApiError(400, {'error': str(e), 'field': e.field})
        except (OffsetError, ValueError) as e:
            raise ApiError(400, {'error': str(e)})
        if not programs:
            raise ApiError(400, {'error': 'nothing to generate: no shape is placed on a panel',
                                 'problems': problems})
        out = self.dir / 'out'
        stamp = time.strftime('%Y%m%d-%H%M%S')
        project = {'name': self.dir.name, 'shapes': self.project()['shapes']}
        for k in range(1, 1000):
            folder = out / (stamp if k == 1 else f'{stamp}-{k}')
            if folder.exists():
                continue
            try:
                files = write_output(folder, plan, programs, settings, project)
            except FileExistsError:
                continue
            return {'folder': str(folder), 'files': [p.name for p in files],
                    'programs': [p.name for p in programs], 'problems': problems}
        raise ApiError(500, {'error': f'no free output folder for {stamp}'})


class Handler(BaseHTTPRequestHandler):
    server_version = 'nesting'
    project: Project            # set on the subclass made by make_server

    def log_message(self, fmt, *args):     # keep the console quiet
        pass

    def _send(self, status: int, body: bytes, ctype: str):
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj):
        self._send(status, json.dumps(obj).encode('utf-8'), 'application/json; charset=utf-8')

    def _body(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            raise ApiError(400, {'error': 'bad Content-Length'})
        if length > MAX_BODY:
            self.close_connection = True
            raise ApiError(413, {'error': f'request larger than {MAX_BODY // (1024 * 1024)} MB'})
        return _loads(self.rfile.read(length)) if length else None

    def _route(self, method: str):
        url = urlsplit(self.path)
        route = (method, url.path)
        try:
            if route == ('GET', '/'):
                return self._send(200, PAGE.read_bytes(), 'text/html; charset=utf-8')
            if not url.path.startswith('/api/'):
                raise ApiError(404, {'error': 'not found'})
            body = self._body() if method in ('PUT', 'POST') else None
            with self.project.lock:
                if route == ('GET', '/api/project'):
                    return self._json(200, self.project.project())
                if route == ('PUT', '/api/project'):
                    return self._json(200, self.project.save(body))
                if route == ('POST', '/api/shapes'):
                    return self._json(200, self.project.upload(body))
                if route == ('GET', '/api/plan'):
                    return self._json(200, self.project.plan())
                if route == ('GET', '/api/program'):
                    name = parse_qs(url.query).get('name', [''])[0]
                    text = self.project.program_text(name)
                    return self._send(200, text.encode('ascii', 'replace'),
                                      'text/plain; charset=us-ascii')
                if route == ('POST', '/api/generate'):
                    return self._json(200, self.project.generate())
            raise ApiError(404, {'error': 'not found'})
        except ApiError as e:
            self._json(e.status, e.body)
        except Exception as e:          # never a stack trace to the page
            self._json(500, {'error': f'{type(e).__name__}: {e}'})

    def do_GET(self):
        self._route('GET')

    def do_PUT(self):
        self._route('PUT')

    def do_POST(self):
        self._route('POST')


def make_server(project_dir: Path, port: int = 8765) -> ThreadingHTTPServer:
    project = Project(Path(project_dir))
    handler = type('ProjectHandler', (Handler,), {'project': project})
    server = ThreadingHTTPServer((HOST, port), handler)
    server.daemon_threads = True
    return server


def main(argv: list[str]) -> int:
    if not 2 <= len(argv) <= 3:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    folder = Path(argv[1]).resolve()
    (folder / 'shapes').mkdir(parents=True, exist_ok=True)
    server = make_server(folder, int(argv[2]) if len(argv) == 3 else 8765)
    print(f'Project {folder}\nOpen http://{HOST}:{server.server_address[1]}/  (Ctrl+C to stop)')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
