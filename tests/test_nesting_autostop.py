import threading
import unittest

from nesting.autostop import IdleWatch, run_watch


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


if __name__ == '__main__':
    unittest.main()
