import contextlib
import http.client
import http.server
import io
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from nesting import ping
from nesting import server as server_module
from nesting.autostop import IdleWatch, run_watch
from nesting.server import _serve, main, make_server


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


def run(w, c, seconds):
    """Advance 1 s at a time, calling check() each step; first reason or None."""
    for _ in range(int(seconds)):
        c.advance(1)
        reason = w.check()
        if reason:
            return reason
    return None


class IdleWatchTests(unittest.TestCase):
    def setUp(self):
        self.c = FakeClock()
        self.w = IdleWatch(clock=self.c)

    def test_no_page_exits_after_ten_minutes(self):
        self.assertIsNone(run(self.w, self.c, 599))
        self.assertIn('10 minutes', run(self.w, self.c, 1))

    def test_ping_keeps_alive(self):
        for _ in range(180):
            self.w.begin()
            self.w.end()
            self.assertIsNone(run(self.w, self.c, 10))

    def test_grace_after_last_request(self):
        self.w.begin()
        self.w.end()
        self.assertIsNone(run(self.w, self.c, 179))
        self.assertIn('3 minutes', run(self.w, self.c, 1))

    def test_closing_exits_after_twenty_seconds(self):
        self.w.begin()
        self.w.end()
        self.w.begin(closing=True)
        self.w.end()
        self.assertIsNone(run(self.w, self.c, 19))
        self.assertEqual('the page was closed', run(self.w, self.c, 1))

    def test_request_after_closing_cancels_countdown(self):
        self.w.begin()
        self.w.end()
        self.w.begin(closing=True)
        self.w.end()
        self.assertIsNone(run(self.w, self.c, 5))
        self.w.begin()
        self.w.end()
        self.assertIsNone(run(self.w, self.c, 60))

    def test_in_flight_blocks_exit(self):
        self.w.begin()
        self.assertIsNone(run(self.w, self.c, 3600))
        self.w.end()
        self.c.advance(1)
        self.assertIsNotNone(self.w.check())

    def test_sleep_gap_gives_fresh_grace(self):
        self.w.begin()
        self.w.end()
        self.assertIsNone(self.w.check())
        self.c.advance(3600)
        self.assertIsNone(self.w.check())
        self.assertIsNone(run(self.w, self.c, 179))
        self.assertIsNotNone(run(self.w, self.c, 1))

    def test_wait_idle(self):
        self.w.begin()
        self.assertFalse(self.w.wait_idle(0.05))
        self.w.end()
        self.assertTrue(self.w.wait_idle(0.05))

    def test_wait_idle_wakes_on_end(self):
        self.w.begin()
        threading.Timer(0.05, self.w.end).start()
        self.assertTrue(self.w.wait_idle(2))

    def test_seconds_text_under_a_minute(self):
        w = IdleWatch(clock=self.c, no_page=5)
        self.assertIn('5 seconds', run(w, self.c, 5))

    def test_run_watch_shuts_down(self):
        class Server:
            calls = 0

            def shutdown(self):
                self.calls += 1

        server = Server()
        logs = []
        w = IdleWatch(clock=self.c, no_page=5)
        reason = run_watch(server, w, tick=1.0, sleep=self.c.advance,
                           log=logs.append)
        self.assertIn('seconds', reason)
        self.assertEqual(1, server.calls)
        self.assertEqual([f'Stopping: {reason}'], logs)

    def test_run_watch_survives_a_failing_check(self):
        class Server:
            def shutdown(self):
                pass

        class Flaky:
            calls = 0

            def check(self):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError('boom')
                return 'done'

        logs = []
        reason = run_watch(Server(), Flaky(), tick=0, sleep=lambda s: None,
                           log=logs.append)
        self.assertEqual('done', reason)
        self.assertEqual('Auto-stop check failed: boom', logs[0])


class ServerAutoStopTests(unittest.TestCase):
    def start(self, watch=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.server = make_server(Path(tmp.name), port=0, watch=watch)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.thread.join(2)
        self.server.server_close()

    def call(self, method, path, body=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            headers = {}
            data = None
            if body is not None:
                data = json.dumps(body).encode()
                headers['Content-Type'] = 'application/json'
            conn.request(method, path, data, headers)
            r = conn.getresponse()
            return r.status, json.loads(r.read().decode())
        finally:
            conn.close()

    def test_ping_says_it_is_the_tool(self):
        self.start()
        status, body = self.call('GET', '/api/ping')
        self.assertEqual(200, status)
        self.assertEqual('nesting', body['app'])
        self.assertTrue(body['version'])
        self.assertIsInstance(body['version'], str)

    def test_closing_without_watch_is_harmless(self):
        self.start()
        self.assertEqual((200, {'ok': True}),
                         self.call('POST', '/api/closing', {}))
        self.assertEqual(200, self.call('GET', '/api/ping')[0])

    def test_requests_are_tracked(self):
        clock = FakeClock()
        watch = IdleWatch(clock=clock)
        self.start(watch)
        self.call('GET', '/api/ping')
        self.assertEqual(clock.t, watch.last_seen)
        self.assertEqual(0, watch.in_flight)
        clock.advance(5)
        self.call('POST', '/api/closing', {})
        self.assertEqual(clock.t, watch.closing_at)
        self.assertEqual(0, watch.in_flight)

    def test_closing_then_ping_keeps_server(self):
        watch = IdleWatch(grace=5, closing_grace=0.3, no_page=5)
        self.start(watch)
        result = []
        t = threading.Thread(
            target=lambda: result.append(run_watch(self.server, watch,
                                                   tick=0.05)))
        t.start()
        self.call('POST', '/api/closing', {})
        time.sleep(0.1)
        self.call('GET', '/api/ping')
        time.sleep(0.6)
        self.assertEqual(200, self.call('GET', '/api/ping')[0])
        self.call('POST', '/api/closing', {})
        t.join(2)
        self.assertFalse(t.is_alive())
        self.assertEqual(['the page was closed'], result)

    def test_main_exits_when_no_page(self):
        out = io.StringIO()
        code = []
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch('nesting.autostop.NO_PAGE', 0.3), \
                mock.patch('nesting.autostop.TICK', 0.05), \
                contextlib.redirect_stdout(out):
            t = threading.Thread(target=lambda: code.append(
                main(['nesting', tmp, '--port', '0', '--exit-when-closed'])))
            t.start()
            t.join(3)
            alive = t.is_alive()
        self.assertFalse(alive)
        self.assertEqual([0], code)
        self.assertIn('Stopping: no page connected', out.getvalue())
        self.assertIn('Stops by itself when the page is closed.',
                      out.getvalue())

    def test_main_waits_for_in_flight_request(self):
        class Server:
            closed = False

            def serve_forever(self):
                pass

            def server_close(self):
                self.closed = True

        watch = IdleWatch()
        watch.begin()
        threading.Timer(0.2, watch.end).start()
        server = Server()
        start = time.monotonic()
        _serve(server, watch)
        self.assertGreaterEqual(time.monotonic() - start, 0.15)
        self.assertTrue(server.closed)

    def test_without_flag_no_watch(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = make_server(Path(tmp), port=0)
            try:
                self.assertIsNone(server.watch)
            finally:
                server.server_close()


class PingTests(unittest.TestCase):
    def serve(self, server):
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def stop():
            server.shutdown()
            thread.join(2)
            server.server_close()
        self.addCleanup(stop)
        return server.server_address[1]

    def other_server(self, status, body):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(status)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass
        return self.serve(http.server.HTTPServer(('127.0.0.1', 0), Handler))

    def test_ping_running(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        port = self.serve(make_server(Path(tmp.name), port=0))
        self.assertEqual(ping.RUNNING, ping.probe(port))
        self.assertEqual(0, ping.RUNNING)

    def test_app_name_matches_server(self):
        self.assertEqual(server_module.APP, ping.APP)

    def test_ping_free(self):
        s = socket.socket()
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
        s.close()
        self.assertEqual(ping.FREE, ping.probe(port))
        self.assertEqual(1, ping.FREE)

    def test_ping_other_server(self):
        self.assertEqual(ping.OTHER, ping.probe(self.other_server(404, b'no')))
        self.assertEqual(ping.OTHER,
                         ping.probe(self.other_server(200, b'hello')))
        self.assertEqual(ping.OTHER, ping.probe(
            self.other_server(200, b'{"app": "something else"}')))
        self.assertEqual(2, ping.OTHER)

    def test_ping_cli(self):
        s = socket.socket()
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
        s.close()
        root = Path(__file__).resolve().parent.parent
        r = subprocess.run([sys.executable, '-m', 'nesting.ping', str(port)],
                           cwd=root, capture_output=True, text=True,
                           timeout=30)
        self.assertEqual(1, r.returncode)
        self.assertEqual(f'port {port} is free\n', r.stdout)

    def test_main_messages(self):
        for code, text in ((0, 'nesting tool runs on port 7'),
                           (1, 'port 7 is free'),
                           (2, 'port 7 is in use by another program')):
            out = io.StringIO()
            with mock.patch.object(ping, 'probe', return_value=code), \
                    contextlib.redirect_stdout(out):
                self.assertEqual(code, ping.main(['ping', '7']))
            self.assertEqual(text + '\n', out.getvalue())

    def test_main_bad_port_exits_other(self):
        for arg in ('abc', '99999', '0', '-1'):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(ping.OTHER, ping.main(['ping', arg]))
            self.assertIn('usage', err.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ping.OTHER, ping.main(['ping']))

    def test_main_crash_exits_other(self):
        with mock.patch.object(ping, 'probe', side_effect=RuntimeError('x')), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ping.OTHER, ping.main(['ping', '7']))

    def test_probe_out_of_range_is_other(self):
        self.assertEqual(ping.OTHER, ping.probe(99999))

    def test_silent_listener_is_other(self):
        s = socket.socket()
        self.addCleanup(s.close)
        s.bind(('127.0.0.1', 0))
        s.listen(1)
        start = time.monotonic()
        self.assertEqual(ping.OTHER, ping.probe(s.getsockname()[1], 0.5))
        self.assertLess(time.monotonic() - start, 2)


if __name__ == '__main__':
    unittest.main()
