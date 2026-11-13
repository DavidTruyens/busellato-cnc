"""Launcher scripts: start.sh (Linux, macOS).

The script runs with a stub `git` (never a real pull), a stub `notify-send`
and a stub BROWSER (never a real browser), on free ephemeral ports only.
"""
import http.server
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from nesting import ping
from nesting.server import make_server

REPO = Path(__file__).resolve().parent.parent
START_SH = REPO / 'start.sh'


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def write_stub(path, body):
    path.write_text('#!/bin/sh\n' + body + '\n')
    path.chmod(0o755)


@unittest.skipIf(os.name != 'posix' or not shutil.which('bash'), 'start.sh needs bash')
class StartShTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name) / 'home'
        self.home.mkdir()
        self.bin = Path(tmp.name) / 'bin'
        self.bin.mkdir()
        # Stubs first in PATH: the real git, notify-send and python never run.
        write_stub(self.bin / 'git', 'echo "$*" >> "$HOME/git-calls"\n'
                   'echo "GIT_TERMINAL_PROMPT=$GIT_TERMINAL_PROMPT" >> "$HOME/git-calls"\nexit 1')
        write_stub(self.bin / 'notify-send', 'echo "$*" >> "$HOME/notified"')
        self.browser = Path(tmp.name) / 'browser'
        write_stub(self.browser, 'echo "$1" >> "$HOME/opened"')
        self.project = self.home / 'nesting-project'
        self.log = self.project / 'start.log'

    def use_real_python(self):
        os.symlink(sys.executable, self.bin / 'python3')

    def env(self, port):
        return {'HOME': str(self.home),
                'PATH': f'{self.bin}:/usr/bin:/bin',
                'NESTING_PORT': str(port),
                'BROWSER': str(self.browser),
                'LANG': 'C'}

    def run_start(self, port):
        return subprocess.run(['bash', str(START_SH)], env=self.env(port),
                              stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=30)

    def read(self, name):
        p = self.home / name
        return p.read_text() if p.exists() else ''

    def serve(self, server):
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

        def stop():
            server.shutdown()
            t.join(2)
            server.server_close()
        self.addCleanup(stop)
        return server.server_address[1]

    def test_start_sh_already_running(self):
        self.use_real_python()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        port = self.serve(make_server(Path(tmp.name), port=0))
        r = self.run_start(port)
        self.assertEqual(0, r.returncode, self.log.read_text())
        url = f'http://127.0.0.1:{port}/'
        self.assertIn(url, self.read('opened'))
        log = self.log.read_text()
        self.assertIn('already running', log)
        self.assertNotIn('Update skipped', log)   # only short lines on this path
        self.assertNotIn('\a', log)
        self.assertEqual('', self.read('notified'))
        calls = self.read('git-calls')
        self.assertIn('-c credential.interactive=never', calls)
        self.assertIn('pull --ff-only -q', calls)
        self.assertIn('GIT_TERMINAL_PROMPT=0', calls)

    def test_start_sh_second_launch_keeps_the_running_log(self):
        # The running tool's log must not be truncated by a second click on the icon.
        self.use_real_python()
        self.project.mkdir()
        self.log.write_text('MARKER first run\n')
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        port = self.serve(make_server(Path(tmp.name), port=0))
        with open(self.log, 'a') as running:     # the first run's server, still writing
            r = self.run_start(port)
            running.write('server line after\n')
        self.assertEqual(0, r.returncode)
        data = self.log.read_bytes()
        self.assertTrue(data.startswith(b'MARKER first run\n'), data[:200])
        self.assertNotIn(b'\0', data)
        self.assertIn(b'already running', data)
        self.assertIn(b'server line after', data)
        self.assertEqual(['start.log'], sorted(p.name for p in self.project.iterdir()
                                               if p.name.startswith('start.log')))

    def test_start_sh_notice_falls_back_to_zenity(self):
        write_stub(self.bin / 'notify-send', 'exit 1')
        write_stub(self.bin / 'zenity', 'echo "$*" >> "$HOME/zenity"')
        write_stub(self.bin / 'python3', 'exit 127')
        write_stub(self.bin / 'python', 'exit 127')
        r = self.run_start(free_port())
        self.assertEqual(2, r.returncode)
        self.assertIn('Python 3 was not found', self.read('zenity'))
        self.assertIn('Python 3 was not found', self.log.read_text())
        self.assertIn(f'Log: {self.log}', self.log.read_text())
        self.assertFalse(any(p.name.startswith('start.log.') for p in self.project.iterdir()))

    def test_start_sh_port_taken(self):
        self.use_real_python()

        class NotFound(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_error(404)

            def log_message(self, *args):
                pass
        port = self.serve(http.server.HTTPServer(('127.0.0.1', 0), NotFound))
        r = self.run_start(port)
        self.assertEqual(4, r.returncode, self.log.read_text())
        self.assertIn('in use by another program', self.read('notified'))
        self.assertIn('in use by another program', self.log.read_text())
        self.assertIn(f'Log: {self.log}', self.log.read_text())
        self.assertEqual('', self.read('opened'))

    def test_start_sh_old_python(self):
        write_stub(self.bin / 'python3',
                   'if [ "$1" = "--version" ]; then echo "Python 3.9.0"; exit 0; fi\nexit 1')
        r = self.run_start(free_port())
        self.assertEqual(3, r.returncode, self.log.read_text())
        notice = self.read('notified')
        self.assertIn('too old', notice)
        self.assertIn('Python 3.9.0', notice)

    def test_start_sh_no_python(self):
        write_stub(self.bin / 'python3', 'exit 127')
        write_stub(self.bin / 'python', 'exit 127')
        r = self.run_start(free_port())
        self.assertEqual(2, r.returncode, self.log.read_text())
        self.assertIn('Python 3 was not found', self.read('notified'))

    def start_tool(self):
        """Popen start.sh in its own session; return (process, port) once the tool runs."""
        self.use_real_python()
        port = free_port()
        p = subprocess.Popen(['bash', str(START_SH)], env=self.env(port),
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)

        def kill():
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait(5)
        self.addCleanup(kill)
        url = f'http://127.0.0.1:{port}/'
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if (ping.probe(port, timeout=1) == ping.RUNNING
                    and url in self.read('opened')):
                break
            self.assertIsNone(p.poll(), self.log.read_text() if self.log.exists() else '')
            time.sleep(0.1)
        return p, port

    def test_start_sh_starts_the_tool(self):
        p, port = self.start_tool()
        url = f'http://127.0.0.1:{port}/'
        self.assertEqual(ping.RUNNING, ping.probe(port))
        self.assertIn(url, self.read('opened'))
        self.assertIn('Stops by itself when the page is closed.', self.log.read_text())
        self.assertTrue(any((self.project / 'shapes').iterdir()), 'plates seeded')
        self.assertEqual(['start.log'], sorted(p.name for p in self.project.iterdir()
                                               if p.name.startswith('start.log')))

    def test_start_sh_tool_stopped_by_signal_is_not_a_failure(self):
        p, port = self.start_tool()
        children = subprocess.run(['pgrep', '-P', str(p.pid)], capture_output=True,
                                  text=True).stdout.split()
        self.assertEqual(1, len(children), children)
        os.kill(int(children[0]), signal.SIGTERM)    # e.g. logout
        self.assertEqual(0, p.wait(10))
        self.assertIn('The tool was stopped (signal).', self.log.read_text())
        self.assertEqual('', self.read('notified'))

    def test_start_sh_shellcheck(self):
        sc = shutil.which('shellcheck')
        if not sc:
            self.skipTest('shellcheck not installed')
        r = subprocess.run([sc, str(START_SH)], capture_output=True, text=True)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)

    def test_start_sh_runs_from_one_function(self):
        lines = [ln for ln in START_SH.read_text().splitlines() if ln.strip()]
        self.assertEqual('main "$@"; exit $?', lines[-1])

    def test_start_sh_is_executable(self):
        self.assertTrue(os.access(START_SH, os.X_OK))


if __name__ == '__main__':
    unittest.main()
