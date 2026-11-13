"""Auto-stop logic for the nesting tool's web server.

When the server is started with the auto-stop flag, it watches how long ago
the web page last talked to it and stops by itself once the page is gone.
The page pings the server regularly and sends a "closing" request when the
tab is closed.

The grace after the last request is long (3 minutes) because browsers slow
timers in background tabs, so a page that is merely hidden may ping rarely.
A closing notice shortens the wait to 20 seconds, but any later request
cancels it (a reload also sends a closing notice). A server that never sees
a page stops after 10 minutes. If the computer sleeps, the clock jumps; the
gap is skipped so the page gets a fresh grace on wake-up.

All times are in seconds.
"""

import threading
import time

GRACE = 180
CLOSING_GRACE = 20
NO_PAGE = 600
SLEEP_GAP = 30
TICK = 1.0


def _duration(seconds):
    if seconds >= 60:
        n = round(seconds / 60)
        return f'{n} minute{"" if n == 1 else "s"}'
    n = round(seconds)
    return f'{n} second{"" if n == 1 else "s"}'


class IdleWatch:
    def __init__(self, clock=time.monotonic, grace=None, closing_grace=None,
                 no_page=None, sleep_gap=None):
        self.clock = clock
        self.grace = GRACE if grace is None else grace
        self.closing_grace = (CLOSING_GRACE if closing_grace is None
                              else closing_grace)
        self.no_page = NO_PAGE if no_page is None else no_page
        self.sleep_gap = SLEEP_GAP if sleep_gap is None else sleep_gap
        self._cond = threading.Condition()
        self.in_flight = 0
        self.seen_any = False
        self.started = clock()
        self.last_seen = None  # until the first non-closing request
        self.closing_at = None
        self._last_check = None

    def begin(self, closing=False):
        with self._cond:
            now = self.clock()
            self.in_flight += 1
            self.seen_any = True
            if closing:
                self.closing_at = now
            else:
                self.last_seen = now
                self.closing_at = None

    def end(self):
        with self._cond:
            self.in_flight -= 1
            self._cond.notify_all()

    def check(self):
        with self._cond:
            now = self.clock()
            if self._last_check is not None:
                gap = now - self._last_check
                if gap > self.sleep_gap:
                    self.started += gap
                    if self.last_seen is not None:
                        self.last_seen += gap
                    if self.closing_at is not None:
                        self.closing_at += gap
            self._last_check = now
            if self.in_flight > 0:
                return None
            if not self.seen_any and now - self.started >= self.no_page:
                return f'no page connected for {_duration(self.no_page)}'
            if (self.closing_at is not None
                    and now - self.closing_at >= self.closing_grace):
                return 'the page was closed'
            if (self.last_seen is not None
                    and now - self.last_seen >= self.grace):
                return f'no page for {_duration(self.grace)}'
            return None

    def wait_idle(self, timeout=None):
        with self._cond:
            return self._cond.wait_for(lambda: self.in_flight == 0, timeout)


def run_watch(server, watch, tick=None, sleep=time.sleep, log=print):
    tick = TICK if tick is None else tick
    while True:
        sleep(tick)
        reason = watch.check()
        if reason:
            log(f'Stopping: {reason}')
            server.shutdown()
            return reason
