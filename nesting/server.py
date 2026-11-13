"""Local web server: the page plus a small JSON API over one project folder.

  python -m nesting [PROJECT_DIR] [--port N] [--seed-plates] [--open]

Run it from the busellato-cnc folder (on Windows `py -m nesting` also works).

PROJECT_DIR/shapes/*.dxf are the shapes, PROJECT_DIR/project.json holds quantities, on/off
flags and settings, PROJECT_DIR/out/<YYYYMMDD-HHMMSS>/ receives each generated job.
Binds to 127.0.0.1 only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import webbrowser
from dataclasses import fields
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from .backends import BACKENDS
from .dxf import DxfError, Shape, read_dxf
from .geometry import OffsetError
from .importdisk import NAME as DISKETTE, size_warning
from .layout import MAX_QTY, ShapeEntry, build_plan
from .output import write_output
from .pockets import GroupSettings, PocketGroup, effective, find_groups, group_for
from .preview import pocket_groups_data, preview_data
from .program import plan_programs, plan_shapes
from .settings import Pockets, Settings, SettingsError

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


_POCKET_MESSAGES = {'enabled': 'must be true or false',
                    'direction': 'must be one of cw, ccw',
                    'tool': 'must be a whole tool number, 1 or more',
                    'stepover_pct': 'must be a number from above 0 up to 100'}
_POCKET_FIELDS = {f.name for f in fields(GroupSettings)}


def pocket_override_error(key: str, override, settings: Settings,
                          floor: bool = True) -> tuple[str, str] | None:
    """(field below the group, message) for the first bad value of one group's override
    ('' for the override itself), or None. Checked like pockets.effective, plus (floor True,
    settings already validated) the floor the depth must leave, like Settings.validate
    checks the default depth."""
    if override is None:                            # like effective: no override
        return None
    if not isinstance(override, dict):
        return '', 'must be an object of pocket group settings'
    for name, value in override.items():
        if name not in _POCKET_FIELDS:
            continue                                # unknown fields are ignored, like effective
        try:
            effective(key, {key: {name: value}}, settings.pockets)
        except ValueError:
            return name, _POCKET_MESSAGES.get(name, 'must be a number greater than 0')
    if not floor:
        return None
    gs = effective(key, {key: override}, settings.pockets)
    least, thick = settings.pockets.min_floor, settings.panel.thickness
    if not gs.depth + least <= thick:
        return 'depth', (f'depth plus pockets.min_floor ({least:g} mm) must not exceed the '
                         f'panel thickness ({thick:g} mm)')
    return None


def check_pockets(pockets, settings: Settings, groups: list[PocketGroup]) -> None:
    """SettingsError('pockets.<group id>.<field>', ...) for the first bad override of a
    current group. Keys that match no group (stale: a DXF edit changes a group's key) are
    kept as they are and not checked: they are never used and the page cannot show them."""
    if not isinstance(pockets, dict):
        raise SettingsError('pockets', 'must be an object: pocket group key -> settings')
    for g in groups:
        bad = pocket_override_error(g.key, pockets.get(g.key), settings)
        if bad:
            name = f'pockets.{g.id}'
            raise SettingsError(f'{name}.{bad[0]}' if bad[0] else name, bad[1])


def _min_circle(settings: dict) -> float:
    """pockets.min_circle_diameter if it is a valid number, else the default (a bad value
    stops every plan through validate(), so shapes read with the default are only listed)."""
    v = (settings.get('pockets') or {}).get('min_circle_diameter')
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 < v < float('inf'):
        return Pockets().min_circle_diameter
    return float(v)


def safe_filename(name) -> str:
    """Last path component of `name` if it is a plain `*.dxf` name; else ApiError 400."""
    base = re.split(r'[\\/]', name if isinstance(name, str) else '')[-1].strip()
    if (not SAFE_NAME.fullmatch(base) or not base.lower().endswith('.dxf')
            or base.startswith('.')):
        raise ApiError(400, {'error': f'file name {base or name!r} not allowed: use letters, '
                                      'digits, space, . _ - and the extension .dxf'})
    return base[:-4] + '.dxf'                   # stored with a lower-case extension


class Project:
    """The project folder. Files and the shape cache are only touched under `lock`;
    plans are computed from a snapshot taken under the lock, after releasing it."""

    def __init__(self, folder: Path):
        self.dir = Path(folder)
        self.shapes_dir = self.dir / 'shapes'
        self.file = self.dir / 'project.json'
        self.lock = threading.Lock()
        self.out_lock = threading.Lock()     # picks and writes one output folder at a time
        # file name -> (mtime, pockets.min_circle_diameter, shape)
        self._cache: dict[str, tuple[float, float, Shape]] = {}

    # --- stored state -------------------------------------------------------------------
    def _stored(self) -> dict:
        """shapes, settings and pockets (the group overrides, as stored: checked later)."""
        if not self.file.exists():
            return {'shapes': [], 'settings': Settings().to_dict(), 'pockets': {}}
        data = json.loads(self.file.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('expected an object')
        return {'shapes': list(data.get('shapes') or []),
                'settings': Settings.from_dict(data.get('settings') or {}).to_dict(),
                'pockets': data.get('pockets', {})}

    def _files(self) -> list[Path]:
        if not self.shapes_dir.is_dir():
            return []
        return sorted(p for p in self.shapes_dir.iterdir()
                      if p.suffix.lower() == '.dxf' and p.is_file())

    def _shapes(self, min_circle: float) -> tuple[list[Shape], list[str]]:
        """Shapes read from shapes/*.dxf, plus a message per unreadable file. Cached by mtime
        and min_circle (which circles are pockets): changing either reads the file again."""
        shapes, errors = [], []
        files = self._files()
        for path in files:
            mtime = path.stat().st_mtime
            hit = self._cache.get(path.name)
            if hit and hit[:2] == (mtime, min_circle):
                shapes.append(hit[2])
                continue
            try:
                shape = read_dxf(path, min_pocket_circle=min_circle)
            except DxfError as e:
                errors.append(str(e))
                continue
            self._cache[path.name] = (mtime, min_circle, shape)
            shapes.append(shape)
        return shapes, errors

    def _merged(self, stored: dict | None = None):
        """(shapes in list order with qty/enabled, settings dict, dxf errors, pockets)."""
        stored = self._stored() if stored is None else stored
        shapes, errors = self._shapes(_min_circle(stored['settings']))
        by_name = {s.name: s for s in shapes}
        rows, seen = [], set()
        for e in stored['shapes']:
            name = e.get('name') if isinstance(e, dict) else None
            if name in by_name and name not in seen:
                seen.add(name)
                rows.append((by_name[name], int(e.get('qty', 1)), bool(e.get('enabled', True))))
        rows += [(s, 1, True) for s in shapes if s.name not in seen]
        return rows, stored['settings'], errors, stored['pockets']

    @staticmethod
    def _listing(rows) -> list[dict]:
        return [{'name': s.name, 'length': round(s.length, 3), 'width': round(s.width, 3),
                 'qty': q, 'enabled': on} for s, q, on in rows]

    def project(self) -> dict:
        with self.lock:
            return self._project()

    def _project(self) -> dict:
        rows, settings, _, pockets = self._merged()
        return {'shapes': self._listing(rows), 'settings': settings, 'pockets': pockets,
                'pocket_groups': self._pocket_groups(rows, settings, pockets)}

    @staticmethod
    def _pocket_groups(rows, settings_dict: dict, pockets) -> list[dict]:
        """pocket_groups_data over every shape of the project (switched off too, so their
        overrides stay editable) with the stored overrides; count is the number of pockets
        on switched-on shapes (0 for a group of switched-off shapes only). A group whose
        override is bad gets enabled False and `error`."""
        settings = Settings.from_dict(settings_dict)
        try:
            validate(settings)
            settings_ok = True
        except SettingsError:           # /api/plan names it; no arithmetic on bad values here
            settings_ok = False
        on = [(s, q) for s, q, enabled in rows if enabled and q > 0]
        # enough of a Plan for pocket_groups_data: each shape once (not qty times: a
        # hand-edited qty can be huge); the counts are then set from the quantities
        listed = SimpleNamespace(blanks=[SimpleNamespace(
            shapes=[SimpleNamespace(shape=sh) for sh, _, _ in rows])])
        ok = isinstance(pockets, dict)
        out = pocket_groups_data(listed, settings, pockets if ok else {})
        counts = {g['id']: 0 for g in out}
        groups = Project._groups(rows)
        for sh, q in on:
            for pk in sh.pockets:
                if (g := group_for(pk, groups)) is not None:
                    counts[g.id] += q
        for g in out:
            g['count'] = counts[g['id']]
        for g in out:
            if not ok:
                error = 'pockets: must be an object: pocket group key -> settings'
            elif 'error' in g:
                continue
            elif bad := pocket_override_error(g['key'], pockets.get(g['key']), settings,
                                             settings_ok):
                field = f'pockets.{g["id"]}' + (f'.{bad[0]}' if bad[0] else '')
                error = f'{field}: {bad[1]}'
            else:
                continue
            g['enabled'] = False
            g['error'] = error
        return out

    def save(self, body) -> dict:
        if not isinstance(body, dict):
            raise ApiError(400, {'error': 'expected an object with shapes and settings'})
        pockets = body.get('pockets', {})
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
            if isinstance(qty, bool) or not isinstance(qty, int) or not 0 <= qty <= MAX_QTY:
                raise ApiError(400, {'field': f'shapes.{name}.qty',
                                     'message': f'must be a whole number from 0 to {MAX_QTY}'})
            if not isinstance(on, bool):
                raise ApiError(400, {'field': f'shapes.{name}.enabled',
                                     'message': 'must be true or false'})
            shapes.append({'name': name, 'qty': qty, 'enabled': on})
        stored = {'shapes': shapes, 'settings': settings.to_dict(), 'pockets': pockets}
        with self.lock:
            rows = self._merged(stored)[0]          # group ids as the new project gives them
            try:
                check_pockets(pockets, settings, self._groups(rows))
            except SettingsError as e:
                raise ApiError(400, {'field': e.field, 'message': e.message})
            self.dir.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.dir, prefix='.project-', suffix='.json')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(stored, f, indent=2)
            os.replace(tmp, self.file)
            return self._project()

    @staticmethod
    def _groups(rows) -> list[PocketGroup]:
        """Pocket groups over every shape of the project, switched on or not (the plan's own
        groups, over the placed shapes, are found by plan_programs)."""
        return find_groups([s for s, _, _ in rows])

    # --- shapes ---------------------------------------------------------------------------
    def upload(self, body) -> dict:
        if not isinstance(body, dict) or not isinstance(body.get('text'), str):
            raise ApiError(400, {'error': 'expected {"filename": ..., "text": ...}'})
        name = safe_filename(body.get('filename'))
        with self.lock:
            return self._upload(name, body['text'])

    def _upload(self, name: str, text: str) -> dict:
        self.shapes_dir.mkdir(parents=True, exist_ok=True)
        # a name that differs only by case is the same shape: replace that file
        same = [p for p in self._files() if p.name.lower() == name.lower()]
        if same:
            name = same[0].name
        with tempfile.TemporaryDirectory(dir=self.dir, prefix='.upload-') as tmp:
            path = Path(tmp) / name                 # same name, so messages name the file
            path.write_text(text, encoding='utf-8', newline='')   # as sent: no \r\r\n on Windows
            try:
                stored = self._stored()
            except ValueError:                      # bad project.json: still check the file
                stored = {'settings': {}}
            try:
                shape = read_dxf(path, min_pocket_circle=_min_circle(stored['settings']))
            except DxfError as e:
                raise ApiError(400, {'error': str(e)})
            target = self.shapes_dir / name
            replaced = bool(same)
            os.replace(path, target)
        return {'name': shape.name, 'length': round(shape.length, 3),
                'width': round(shape.width, 3), 'holes': len(shape.holes), 'replaced': replaced}

    # --- plan -----------------------------------------------------------------------------
    def snapshot(self):
        """(rows, settings dict, dxf errors, pockets) read under the lock; ValueError if
        project.json is bad."""
        with self.lock:
            return self._merged()

    def compute(self, snap):
        """(settings, plan, programs, problems) from a snapshot, without the lock.
        Raises SettingsError, OffsetError, ValueError (a bad pocket override in project.json
        is a ValueError naming the field: the page cannot have sent it)."""
        rows, settings_dict, errors, pockets = snap
        settings = Settings.from_dict(settings_dict)
        validate(settings)
        try:
            check_pockets(pockets, settings, self._groups(rows))
        except SettingsError as e:
            raise ValueError(f'project.json: {e.field}: {e.message}') from None
        entries = [ShapeEntry(s, q, on) for s, q, on in rows]
        plan = build_plan(entries, settings)
        programs = plan_programs(plan, settings, pockets)
        problems = errors + list(plan.problems)
        problems += self._circle_warnings(plan, settings, pockets)
        return settings, plan, programs, problems

    @staticmethod
    def _circle_warnings(plan, settings: Settings, pockets: dict) -> list[str]:
        """One warning per distinct circle (place and size) per placed shape that is read as
        a pocket, unless its pocket group is switched off (then it is not cut)."""
        mc = settings.pockets.min_circle_diameter
        shapes = plan_shapes(plan)
        groups = find_groups(shapes)
        out = []
        for shape in shapes:
            seen = set()
            for pk in shape.pockets:
                if not pk.from_circle:
                    continue
                c = pk.circle
                where = (round(c.x, 3), round(c.y, 3), round(c.diameter, 3))
                if where in seen:
                    continue
                seen.add(where)
                g = group_for(pk, groups)
                try:
                    on = g is None or effective(g.key, pockets, settings.pockets).enabled
                except ValueError:
                    on = True
                if on:
                    out.append(f'{shape.name}: circle of {c.diameter:g} mm is treated as a '
                               f'pocket (over pockets.min_circle_diameter {mc:g} mm); raise '
                               f'the minimum above it to make it a hole')
        return out

    def plan(self) -> dict:
        try:
            snap = self.snapshot()
        except ValueError as e:        # unreadable project.json
            return self._failed(Settings(), [f'project.json: {e}'], None)
        settings = Settings.from_dict(snap[1])
        try:
            settings, plan, programs, problems = self.compute(snap)
            data = preview_data(plan, programs, settings, snap[3])
        except SettingsError as e:
            return self._failed(settings, [], {'field': e.field, 'message': e.message})
        except (OffsetError, DxfError, ValueError) as e:
            return self._failed(settings, [str(e)], None)
        for blank in data['blanks']:      # the emitter writes 3 decimals; so does the page
            blank['z'] = {k: round(v, 3) for k, v in blank['z'].items()}
        data['problems'] = problems
        data['settings_error'] = None
        return data

    @staticmethod
    def _failed(settings: Settings, problems, settings_error) -> dict:
        p, m = settings.panel, settings.machine
        panel = {'length': p.length, 'width': p.width, 'thickness': p.thickness,
                 'edge': p.edge, 'kerf': p.kerf}
        return {'panel': panel, 'frame': {'x': m.frame_x, 'y': m.frame_y},
                'y_toward': m.y_toward, 'panels': [],
                'blanks': [], 'problems': problems, 'settings_error': settings_error}

    def program_text(self, name: str) -> str:
        try:
            settings, _, programs, _ = self.compute(self.snapshot())
        except (OffsetError, ValueError) as e:      # SettingsError is a ValueError
            raise ApiError(400, {'error': str(e)})
        for p in programs:
            if p.name == name:
                return BACKENDS['cnc90'](p, settings)
        raise ApiError(404, {'error': f'no program {name!r} in the current plan'})

    def generate(self) -> dict:
        snap = self.snapshot()
        try:
            settings, plan, programs, problems = self.compute(snap)
        except SettingsError as e:
            raise ApiError(400, {'error': str(e), 'field': e.field})
        except (OffsetError, ValueError) as e:
            raise ApiError(400, {'error': str(e)})
        if not programs:
            raise ApiError(400, {'error': 'nothing to generate: no shape is placed on a blank',
                                 'problems': problems})
        out = self.dir / 'out'
        stamp = time.strftime('%Y%m%d-%H%M%S')
        project = {'name': self.dir.name, 'shapes': self._listing(snap[0])}
        with self.out_lock:
            return self._write(out, stamp, plan, programs, settings, project, problems, snap[3])

    def _write(self, out, stamp, plan, programs, settings, project, problems,
               pockets) -> dict:
        for k in range(1, 1000):
            folder = out / (stamp if k == 1 else f'{stamp}-{k}')
            if folder.exists():
                continue
            try:
                files = write_output(folder, plan, programs, settings, project,
                                     pocket_overrides=pockets)
            except FileExistsError:
                continue
            disk = folder / DISKETTE
            return {'folder': str(folder), 'files': [p.name for p in files],
                    'programs': [p.name for p in programs], 'problems': problems,
                    'diskette': str(disk), 'diskette_warning': size_warning(disk)}
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

    def _check_request(self, method: str):
        """Only this machine's own page may talk to the server (no cross-site, no DNS rebinding)."""
        port = self.server.server_address[1]
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if (self.headers.get('Host') or '').strip().lower() not in hosts:
            raise ApiError(403, {'error': 'wrong Host header'})
        origin = self.headers.get('Origin')
        if origin is not None and origin.strip().lower() not in {'http://' + h for h in hosts}:
            raise ApiError(403, {'error': 'requests from other sites are not allowed'})
        if method in ('PUT', 'POST'):
            ctype = (self.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            if ctype != 'application/json':
                self.close_connection = True
                raise ApiError(415, {'error': 'Content-Type must be application/json'})

    def _route(self, method: str):
        url = urlsplit(self.path)
        route = (method, url.path)
        try:
            self._check_request(method)
            if route == ('GET', '/'):
                return self._send(200, PAGE.read_bytes(), 'text/html; charset=utf-8')
            if not url.path.startswith('/api/'):
                raise ApiError(404, {'error': 'not found'})
            body = self._body() if method in ('PUT', 'POST') else None
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


def seed_plates(project_dir: Path, plates_dir: Path | None = None) -> int:
    """Copy plates/*.dxf into PROJECT_DIR/shapes, only if that folder has no files yet.

    Returns the number of files copied (0 when the project already has shapes).
    """
    shapes = Path(project_dir) / 'shapes'
    shapes.mkdir(parents=True, exist_ok=True)
    if any(shapes.iterdir()):
        return 0
    plates_dir = Path(plates_dir) if plates_dir else Path(__file__).resolve().parent.parent / 'plates'
    files = sorted(plates_dir.glob('*.dxf'))
    for f in files:
        shutil.copyfile(f, shapes / f.name)
    return len(files)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog='python -m nesting',
        description='Plan the blanks a panel saw cuts from the panels and write CNC90 programs per blank (local web page, 127.0.0.1 only).',
        epilog='Run it from the busellato-cnc folder. On Windows `py -m nesting` also works.')
    ap.add_argument('project_dir', nargs='?', default='nesting-project',
                    help='project folder, created if missing (default: ./nesting-project)')
    ap.add_argument('--port', type=int, default=8765, help='port (default 8765)')
    ap.add_argument('--seed-plates', action='store_true',
                    help="copy plates/*.dxf into the project's shapes/ if that is empty")
    ap.add_argument('--open', action='store_true',
                    help='open the page in the default browser once the server listens')
    args = ap.parse_args(argv[1:])
    folder = Path(args.project_dir).resolve()
    (folder / 'shapes').mkdir(parents=True, exist_ok=True)
    if args.seed_plates:
        n = seed_plates(folder)
        print(f'Seeded {n} plate shapes' if n else 'Project already has shapes: nothing seeded')
    try:
        server = make_server(folder, args.port)
    except (OverflowError, OSError) as e:
        print(f'Cannot use port {args.port}: {e}', file=sys.stderr)
        return 1
    url = f'http://{HOST}:{server.server_address[1]}/'
    print(f'Project {folder}\nOpen {url}  (Ctrl+C to stop)', flush=True)
    if args.open:          # the socket is bound and listening: the request waits for serve_forever
        threading.Timer(0.3, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
