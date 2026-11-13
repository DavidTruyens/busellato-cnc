# Start the nesting tool without a terminal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An icon starts the nesting tool with no visible window on Windows and on the Linux PC, opens the page, and the tool stops by itself when the page is closed.

**Architecture:** A new module `nesting/autostop.py` holds the "last seen" logic (injectable clock, no threads in the core) and a watcher loop that calls `server.shutdown()`. `nesting/server.py` gets a flag `--exit-when-closed`, `GET /api/ping`, `POST /api/closing` and request tracking, all small additions. A new module `nesting/ping.py` (`python -m nesting.ping PORT`) tells "our tool runs" / "port free" / "something else" for both launchers. The page pings every 10 s, sends a closing beacon on `pagehide`, and shows a banner when pings fail. Windows: `start.bat` quiet mode (env `NESTING_QUIET=1`), `start-quiet.vbs` (hidden launcher, message box), `make-shortcut.vbs`. Linux/macOS: `start.sh`, `install-launcher.sh`.

**Tech Stack:** Python 3.11 standard library, `unittest`; cmd batch; VBScript (Windows Script Host); bash; freedesktop desktop entry.

**Spec:** `docs/superpowers/specs/2026-11-13-start-without-terminal-design.md` (binding, including "More calls, from the builder check").

## Global Constraints

- Without `--exit-when-closed` the server behaves exactly as today (runs until killed). `python -m nesting` and the existing tests unchanged.
- Python standard library only; on the PCs only what a default install has (Git, Python, cmd, Windows Script Host; bash, `notify-send`/`zenity` if present).
- The repo is public: never name the shop operator (write "the person at the shop"), no hostnames, emails, IPs, customer names in files, commits or PR text. No AI mention in commits.
- Nothing can run on Windows or the Linux PC: every Windows and Linux step in the docs is marked "not tested on Windows/Linux". Never claim they work.
- Another branch (`tool-table`) edits `nesting/server.py`, `nesting/web/index.html` and settings: keep edits there small, in separate blocks; put new server tests in a new test file, not in `tests/test_nesting_server.py`.
- Timings (module constants in `nesting/autostop.py`): `GRACE = 180` s (no request), `CLOSING_GRACE = 20` s (after a closing note), `NO_PAGE = 600` s (no request ever), `SLEEP_GAP = 30` s (watcher tick gap treated as the PC sleeping), watcher tick 1 s. Page ping every 10 s; banner after 3 failed pings in a row.
- Banner text exactly: `The tool has stopped. Start it again with the icon, then reload this page.`
- Port 8800, project `%USERPROFILE%\nesting-project` / `~/nesting-project`, log `start.log` in the project folder (overwritten at each start).
- Exit codes of `start.bat` (quiet mode) and `start.sh`: 0 ok or already running (page opened), 1 cannot open the repo folder, 2 no Python, 3 Python older than 3.11, 4 port taken by something else, 5 the tool did not start / exited with an error.
- `python -m nesting.ping PORT` exit codes: 0 the nesting tool answers, 1 nothing listens, 2 something else listens.
- Test command: `python -m unittest discover -s tests` (469 tests on the base). No test waits more than a couple of seconds.

## Review Focus

1. **A long Generate when the grace runs out**: the server must not exit while a request is in flight, and must not exit the process under a request that started just before shutdown (main waits for in-flight requests after `serve_forever` returns). Test: `test_in_flight_blocks_exit` and `test_main_waits_for_in_flight_request` (Task 1/2).
2. **Reload**: closing note then a new request within 20 s keeps the tool up. Test: `test_request_after_closing_cancels_countdown` (Task 1) and `test_closing_then_ping_keeps_server` (Task 2).
3. **PC sleep**: a watcher tick gap > `SLEEP_GAP` shifts all times forward, so waking does not stop the tool before the page pings again. Test: `test_sleep_gap_gives_fresh_grace` (Task 1).
4. **An old tool (no `/api/ping`) or another program on port 8800**: the launchers report "something else" (exit 4) and never start a second copy on another port. Test: `test_ping_other_server` (Task 3), `test_start_sh_port_taken` (Task 5).
5. **Paths with spaces**: the desktop entry and the launchers quote the repo path. Test: `test_install_launcher_path_with_spaces` (Task 6); Windows quoting reviewed by hand (Task 7).

---

### Task 1: Auto-stop logic (`nesting/autostop.py`)

**Files:**
- Create: `nesting/autostop.py`
- Test: `tests/test_nesting_autostop.py`

**Interfaces:**
- Produces:
  - constants `GRACE`, `CLOSING_GRACE`, `NO_PAGE`, `SLEEP_GAP`, `TICK = 1.0`
  - `class IdleWatch(clock=time.monotonic, grace=None, closing_grace=None, no_page=None, sleep_gap=None)`; a `None` takes the module constant at construction time (so tests can patch the constants); thread-safe (one `threading.Condition`); `started = clock()` at construction.
    - `begin(closing: bool = False) -> None`: a request starts. `in_flight += 1`. Not closing: `last_seen = now`, `closing_at = None`, `seen_any = True`. Closing: `closing_at = now`, `seen_any = True` (does not touch `last_seen`).
    - `end() -> None`: `in_flight -= 1`, notify.
    - `check() -> str | None`: called by the watcher each tick. First the sleep check: if the previous `check` was more than `sleep_gap` ago, shift `started`, `last_seen`, `closing_at` forward by that gap. Then: `None` if `in_flight > 0`; `'no page connected for 10 minutes'` (text from `no_page`) if never seen and `now - started >= no_page`; `'the page was closed'` if `closing_at` set and `now - closing_at >= closing_grace`; `'no page for 3 minutes'` if `now - last_seen >= grace`; else `None`. Texts derive minutes from the numbers (seconds when under 60).
    - `wait_idle(timeout: float | None = None) -> bool`: block until `in_flight == 0`.
  - `run_watch(server, watch: IdleWatch, tick: float | None = None, sleep=time.sleep, log=print) -> str` (`None` → module `TICK` at call time): loop `sleep(tick)`; `reason = watch.check()`; when set: `log(f'Stopping: {reason}')`, `server.shutdown()`, return reason. Meant for a daemon thread.

- [ ] **Step 1: Write the failing tests** in `tests/test_nesting_autostop.py`, class `IdleWatchTests`, with a `FakeClock` (`t` attribute, `__call__` returns it, `advance(s)`). Each test builds `IdleWatch(clock=c)` and calls `check()` once per simulated tick where the sleep check matters (advance in steps ≤ 1 s via a helper `run(w, c, seconds)` that advances 1 s and calls `check()` each step, returning the first non-None reason):
  - `test_no_page_exits_after_ten_minutes`: no request; `run(599)` → None; one more second → reason contains `'10 minutes'`.
  - `test_ping_keeps_alive`: `begin(); end()` every 10 s for 30 minutes → never a reason.
  - `test_grace_after_last_request`: one request, then `run(179)` None, at 180 reason contains `'3 minutes'`.
  - `test_closing_exits_after_twenty_seconds`: request, then `begin(closing=True); end()`; `run(19)` None, at 20 reason `'the page was closed'`.
  - `test_request_after_closing_cancels_countdown`: closing, 5 s later a request; `run(60)` → None.
  - `test_in_flight_blocks_exit`: `begin()` without `end()`; `run(3600)` → None; `end()`; next `check()` returns a reason.
  - `test_sleep_gap_gives_fresh_grace`: request at t=0, `check()` at t=1, advance 3600 at once, `check()` → None; then `run(179)` None, at 180 a reason.
  - `test_wait_idle`: `begin()`; `wait_idle(0.05)` is False; `end()`; `wait_idle(0.05)` is True.
  - `test_run_watch_shuts_down`: a stub server with `shutdown()` that records the call, `IdleWatch(clock=c, no_page=5)`, `sleep` that advances the fake clock by the tick; `run_watch(...)` returns the reason, `shutdown` called once, log got `'Stopping: ...'`.

- [ ] **Step 2: Run** `python -m unittest discover -s tests -p 'test_nesting_autostop.py'` → fails (module missing).
- [ ] **Step 3: Implement** `nesting/autostop.py` per the Interfaces block. Module docstring: what the flag does and why the grace is long (background tabs slow timers).
- [ ] **Step 4: Run** the same command → all pass.
- [ ] **Step 5: Commit** `git add nesting/autostop.py tests/test_nesting_autostop.py && git commit -m "Auto-stop logic: last request time, closing countdown, no-page limit"`

### Task 2: Server: `--exit-when-closed`, `/api/ping`, `/api/closing`

**Files:**
- Modify: `nesting/server.py` (imports; `Handler.do_GET/do_PUT/do_POST` + new `_tracked`; two routes in `_route`; `make_server` gets `watch=None`; `main` gets the flag)
- Test: `tests/test_nesting_autostop.py` (new class `ServerAutoStopTests`)

**Interfaces:**
- Consumes: `IdleWatch`, `run_watch`, `TICK` from Task 1.
- Produces:
  - `APP = 'nesting'`; `version() -> str` (cached; `git log -1 --format=%h %cs` run in the repo folder, `'unknown'` on any failure, `CREATE_NO_WINDOW` creationflags on Windows).
  - `GET /api/ping` → 200 `{"app": "nesting", "version": "<version()>"}`. Always available (also without the flag).
  - `POST /api/closing` (body `{}` or empty, Content-Type `application/json`) → 200 `{"ok": true}`. Without a watch it does nothing else.
  - `make_server(project_dir, port=8765, watch: IdleWatch | None = None)`; sets `server.watch = watch`.
  - `Handler._tracked(method)`: if `self.server.watch` is set, `watch.begin(closing=(method == 'POST' and path == '/api/closing'))`, then `self._route(method)` in `try/finally: watch.end()`. `do_GET/do_PUT/do_POST` call `_tracked`.
  - `main`: `--exit-when-closed` ("stop by itself when the page has been closed (used by the launchers)"). With it: `watch = IdleWatch()`, passed to `make_server`, a daemon thread runs `run_watch(server, watch)`, an extra printed line `Stops by itself when the page is closed.`; after `serve_forever` returns, `watch.wait_idle()` before `server_close()`. Exit code 0 on an auto-stop. Without the flag: unchanged.

- [ ] **Step 1: Write the failing tests** (`ServerAutoStopTests`, reusing the `make_server(..., port=0)` + thread pattern from `tests/test_nesting_server.py`, with a helper `call(method, path, body=None)`):
  - `test_ping_says_it_is_the_tool`: without a watch, `GET /api/ping` → 200, `app == 'nesting'`, `version` is a non-empty string.
  - `test_closing_without_watch_is_harmless`: `POST /api/closing` `{}` → 200; server still answers ping.
  - `test_requests_are_tracked`: with `IdleWatch(clock=FakeClock)`: a `GET /api/ping` sets `last_seen`, a `POST /api/closing` sets `closing_at`, and `in_flight` is 0 after each.
  - `test_closing_then_ping_keeps_server`: real clock, `IdleWatch(grace=5, closing_grace=0.3, no_page=5)`, `run_watch(server, watch, tick=0.05)` in a thread: closing, then a ping within 0.1 s; after 0.6 s the server still answers ping. Then closing again with no ping → the watch thread finishes within 2 s and returns `'the page was closed'`.
  - `test_main_exits_when_no_page`: patch `nesting.autostop.NO_PAGE` to 0.3 and `TICK` to 0.05 (IdleWatch/run_watch must read the module constants at call time, i.e. defaults as `None` resolved in the body), run `main(['nesting', tmpdir, '--port', '0', '--exit-when-closed'])` in a thread with stdout captured via `contextlib.redirect_stdout`; it returns 0 within 3 s and the output contains `Stopping: no page connected`.
  - `test_main_waits_for_in_flight_request`: with a `watch` whose `begin()` was called once (simulated in-flight request) and `run_watch` stopping the server, the code path after `serve_forever` (factor it as `_serve(server, watch)`) does not return until `watch.end()` is called from another thread after 0.2 s.
  - `test_without_flag_no_watch`: `make_server(dir, port=0).watch is None`.
- [ ] **Step 2: Run** `python -m unittest discover -s tests -p 'test_nesting_autostop.py'` → new tests fail.
- [ ] **Step 3: Implement** the Interfaces block in `nesting/server.py`. Routes for ping and closing go right before the `('GET', '/api/project')` line. Update the module docstring usage line and `main`'s argparse.
- [ ] **Step 4: Run** the full suite `python -m unittest discover -s tests` → all pass (469 + new).
- [ ] **Step 5: Commit** `git commit -m "Server: --exit-when-closed, /api/ping and the closing note"`

### Task 3: Identity probe (`python -m nesting.ping PORT`)

**Files:**
- Create: `nesting/ping.py`
- Test: `tests/test_nesting_autostop.py` (class `PingTests`)

**Interfaces:**
- Consumes: `GET /api/ping` from Task 2.
- Produces: `probe(port: int, timeout: float = 3.0) -> int` returning `RUNNING = 0`, `FREE = 1`, `OTHER = 2`; `main(argv) -> int` (`python -m nesting.ping PORT`, prints one line: `nesting tool runs on port N` / `port N is free` / `port N is in use by another program`). Logic: TCP connect to 127.0.0.1:port; refused/timeout → FREE; else `GET http://127.0.0.1:port/api/ping` (urllib, timeout) and JSON `app == 'nesting'` → RUNNING; anything else (404, not JSON, HTTP error, connection reset) → OTHER. Guarded by `if __name__ == '__main__': sys.exit(main(sys.argv))`.

- [ ] **Step 1: Failing tests:** `test_ping_running` (nesting `make_server` on port 0 → 0), `test_ping_free` (bind a socket to port 0, take its number, close it → 1), `test_ping_other_server` (a stdlib `HTTPServer` with a handler that answers 404 → 2; and one that answers 200 `hello` → 2), `test_ping_cli` (subprocess `sys.executable -m nesting.ping <free port>` from the repo root → exit 1 and `is free` in stdout).
- [ ] **Step 2: Run** `-p 'test_nesting_autostop.py'` → fail.
- [ ] **Step 3: Implement** `nesting/ping.py`.
- [ ] **Step 4: Run** → pass.
- [ ] **Step 5: Commit** `git commit -m "Identity probe: python -m nesting.ping PORT"`

### Task 4: The page: ping, closing note, "tool stopped" banner

**Files:**
- Modify: `nesting/web/index.html` (one `<div>` after `</header>`, one script block just before `</script>`)
- Test: `tests/test_nesting_autostop.py` (class `PageTests`)

**Interfaces:**
- Consumes: `GET /api/ping`, `POST /api/closing` (Task 2).
- Produces: in the page, `<div class="banner" id="stopped" hidden>The tool has stopped. Start it again with the icon, then reload this page.</div>` placed right after `</header>` (a `[hidden]` rule so `.banner` does not override it, if needed). Script block `// ---- keep the tool running while the page is open ----`: `ping()` every 10 000 ms via `setInterval` and on `visibilitychange` to visible; `fetch('/api/ping', {cache: 'no-store'})`; ok → failures = 0, banner hidden; failure (reject or not ok) → `failures += 1`, banner shown when `failures >= 3`. On `pagehide`: `navigator.sendBeacon('/api/closing', new Blob(['{}'], {type: 'application/json'}))`. No other change to the page.

- [ ] **Step 1: Failing tests:** `test_page_pings_and_says_when_stopped`: `GET /` contains `'/api/ping'`, `'/api/closing'`, `'sendBeacon'`, `'pagehide'` and the exact banner text. `test_page_script_parses`: if `shutil.which('node')`, extract the text between `<script>` and `</script>` and run `node --check` on it in a temp `.js` file → exit 0 (skip otherwise).
- [ ] **Step 2: Run** → fail.
- [ ] **Step 3: Implement** the block.
- [ ] **Step 4: Run** the full suite → pass. Also open the page by hand is not possible here; the test above is the check.
- [ ] **Step 5: Commit** `git commit -m "Page: ping the tool, send a closing note, show when the tool has stopped"`

### Task 5: `start.sh` (Linux, macOS)

**Files:**
- Create: `start.sh` (mode 755)
- Modify: `.gitattributes` (add `/*.sh text eol=lf`)
- Test: `tests/test_launchers.py` (class `StartShTests`, skipped when not POSIX)

**Interfaces:**
- Consumes: `python -m nesting.ping PORT` (Task 3), `--exit-when-closed` (Task 2).
- Produces: `start.sh`. Env knobs: `NESTING_PORT` (default 8800), `NESTING_PROJECT` (default `$HOME/nesting-project`). Structure: everything in `main() { ... }`, last line `main "$@"; exit $?` (bash reads the function in full, so a pull that rewrites the file cannot change it midway). Steps:
  1. `cd` to the script's folder (`${BASH_SOURCE[0]}`), else exit 1.
  2. `mkdir -p "$PROJECT"`; log to `$PROJECT/start.log` (overwrite); when stdout is a terminal, also show it (`exec > >(tee "$LOG") 2>&1`), else `exec >"$LOG" 2>&1`.
  3. Update: if `git` exists, `GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/false SSH_ASKPASS=/bin/false git -c credential.interactive=never pull --ff-only -q </dev/null`; on failure log `Update skipped (offline, local changes or no access): starting the version on this PC.`; never stops. Log `git --no-pager log -1 --format='Version %h of %cs'`.
  4. Python: first of `python3`, `python` that runs; none → `fail 2 "Python 3 was not found. Install Python 3.11 or newer."`; `-c 'import sys; sys.exit(sys.version_info < (3, 11))'` fails → `fail 3 "This Python is too old (3.11 or newer is needed): <version>"`.
  5. `"$PY" -m nesting.ping "$PORT"`: 0 → log `The tool is already running: opening the page $URL` and open it with `"$PY" -m webbrowser "$URL"`, exit 0; 2 → `fail 4 "Port $PORT is in use by another program (or an old copy of the tool still runs in a window: close it). Nothing was started."`; 1 → continue.
  6. `--seed-plates` when `$PROJECT/shapes` does not exist. Run `"$PY" -m nesting "$PROJECT" --port "$PORT" --open --exit-when-closed $SEED` in the foreground; non-zero → `fail 5 "The tool did not start or stopped with an error."`.
  - `fail CODE MESSAGE`: log the message and `Log: $LOG`; desktop notice with `notify-send "Nesting tool" "$msg"` or `zenity --error --title="Nesting tool" --text="$msg"`, whichever exists (when neither, only the log/terminal); `return CODE`.

- [ ] **Step 1: Failing tests** (`tests/test_launchers.py`). Helper `run_start(env_extra, path_dir)`: runs `bash <repo>/start.sh` with `HOME` = temp dir, `PATH` = a temp bin dir first (holding a stub `git` that exits 1, a `python3` symlink to `sys.executable`, stub `notify-send` that appends its args to `$HOME/notified`) then `/usr/bin:/bin`, `NESTING_PORT`, `BROWSER` = a stub script that appends its arg to `$HOME/opened`; timeout 30 s.
  - `test_start_sh_already_running`: nesting `make_server` on port 0 → exit 0, `opened` contains `http://127.0.0.1:<port>/`, log says `already running`.
  - `test_start_sh_port_taken`: a 404-only HTTPServer on the port → exit 4, `notified` and `start.log` contain `in use by another program`.
  - `test_start_sh_old_python`: bin dir with a `python3` stub that exits 1 on `-c` and prints `Python 3.9.0` for `--version`, and no `python` → exit 3, notice contains `too old`.
  - `test_start_sh_starts_the_tool`: free port; `Popen` the script (new session); within 15 s `nesting.ping.probe(port) == 0`; `opened` contains the URL (from the server's `--open` via `BROWSER`); the server process command line has `--exit-when-closed` (check via the log line `Stops by itself when the page is closed.`); then kill the process group.
  - `test_start_sh_shellcheck`: if `shutil.which('shellcheck')`, `shellcheck start.sh` exits 0 (skip otherwise).
  - `test_start_sh_runs_from_one_function`: the last non-empty line of `start.sh` is `main "$@"; exit $?`.
- [ ] **Step 2: Run** `python -m unittest discover -s tests -p 'test_launchers.py'` → fail.
- [ ] **Step 3: Implement** `start.sh`, `chmod 755`, `.gitattributes` line.
- [ ] **Step 4: Run** → pass; `shellcheck start.sh` clean.
- [ ] **Step 5: Commit** `git commit -m "start.sh: update, find Python, start the tool that stops by itself"`

### Task 6: `install-launcher.sh` (Linux desktop entry)

**Files:**
- Create: `install-launcher.sh` (mode 755)
- Test: `tests/test_launchers.py` (class `InstallLauncherTests`)

**Interfaces:**
- Consumes: `start.sh` (Task 5).
- Produces: `install-launcher.sh` writes `${XDG_DATA_HOME:-$HOME/.local/share}/applications/nesting-tool.desktop` and a copy in the desktop folder (`xdg-user-dir DESKTOP` if it exists and returns a folder, else `$HOME/Desktop` if it exists; skip with a message when none). Both `chmod 755`; on the desktop copy try `gio set FILE metadata::trusted true` (ignore failure). Runs `update-desktop-database` on the applications folder if present (ignore failure). Content:
  ```
  [Desktop Entry]
  Type=Application
  Version=1.0
  Name=Nesting tool
  Comment=Plan the blanks and write the programs (stops by itself when the page is closed)
  Exec=/bin/bash "<abs path of start.sh, escaped>"
  Path=<abs repo path>
  Icon=applications-engineering
  Terminal=false
  Categories=Utility;
  ```
  Escaping for `Exec` inside double quotes: `\` → `\\\\`, `"` → `\\"`, `` ` `` → ``\\` ``, `$` → `\\$`; `%` → `%%` (desktop entry spec: the value's string escapes first, then the quoting rules). Prints where it wrote and `Run it again if the folder moves.`

- [ ] **Step 1: Failing tests:** copy `start.sh` and `install-launcher.sh` into `<tmp>/my repo/`; run `bash "<tmp>/my repo/install-launcher.sh"` with `HOME=<tmp>/home` (with a `Desktop` folder), `XDG_DATA_HOME` unset, PATH without `xdg-user-dir`.
  - `test_install_launcher_path_with_spaces`: the applications file and the Desktop copy exist, are executable, contain `Exec=/bin/bash "<tmp>/my repo/start.sh"`, `Terminal=false`, `Path=<tmp>/my repo`.
  - `test_install_launcher_escapes_dollar`: a repo folder named `a$b` → `Exec` contains `a\\$b`.
  - `test_install_launcher_shellcheck`: as in Task 5.
  - `test_install_launcher_validates`: if `desktop-file-validate` exists, it accepts the file (skip otherwise).
- [ ] **Step 2: Run** → fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → pass.
- [ ] **Step 5: Commit** `git commit -m "install-launcher.sh: desktop entry that runs start.sh without a terminal"`

### Task 7: Windows: quiet `start.bat`, `start-quiet.vbs`, `make-shortcut.vbs`

**Files:**
- Modify: `start.bat`
- Create: `start-quiet.vbs`, `make-shortcut.vbs` (ASCII only, CRLF)
- Modify: `.gitattributes` (add `/*.vbs text eol=crlf`)
- Test: `tests/test_launchers.py` (class `WindowsFilesTests`: static checks only)

**Interfaces:**
- Consumes: `python -m nesting.ping` (Task 3), `--exit-when-closed` (Task 2), exit codes from Global Constraints.
- Produces:
  - `start.bat`: quiet mode when env `NESTING_QUIET` is `1` (an env var survives the `--updated` re-call). Changes: the "already running" check becomes `%PY% -m nesting.ping %PORT%` (0 → open the page `start "" "%URL%"`; in normal mode keep the `timeout /t 10`, skip it in quiet mode; exit 0. 2 → `:busy` message "Port 8800 is in use by another program (or an old copy of the tool still runs in a window: close it). Nothing was started." exit 4. 1 → start). Seed check becomes `if not exist "%PROJECT%\shapes\"` (the launcher creates the project folder for the log). In quiet mode the tool starts with `--exit-when-closed` and the "keep this window open" lines are replaced by "Stops by itself when the page is closed.". Each failure label sets its exit code (`:nofolder` 1, no Python 2, `:oldpython` 3, `:busy` 4, tool exits non-zero 5) and goes to `:fail`, which does `pause` only when not quiet and `exit /b %CODE%`. Normal (double-click) mode otherwise unchanged in behaviour.
  - `start-quiet.vbs`: repo = folder of `WScript.ScriptFullName`; project = `%USERPROFILE%\nesting-project` (create if missing); log = project `\start.log`; set process env `NESTING_QUIET=1`; `code = shell.Run("cmd /c """"" & repo & "\start.bat"" > """ & log & """ 2>&1""", 0, True)`; code 0 → quit silently. Else `MsgBox` (vbExclamation, title "Nesting tool") with a sentence per code (2 "Python 3 was not found. Install it from python.org (tick Add python.exe to PATH).", 3 "This Python is too old: 3.11 or newer is needed.", 4 "Port 8800 is in use by another program, or an old window of the tool is still open: close it.", 5 "The tool did not start or stopped with an error.", other "The tool could not be started (code N).") + blank line + the last 12 lines of the log + "Log: " & log. `On Error Resume Next` only around reading the log. If `start.bat` is missing: message box saying so.
  - `make-shortcut.vbs`: creates `<Desktop>\Nesting tool.lnk` (`shell.SpecialFolders("Desktop")`) with `TargetPath = %WINDIR%\System32\wscript.exe`, `Arguments = """" & repo & "\start-quiet.vbs"""`, `WorkingDirectory = repo`, `IconLocation = "%SystemRoot%\System32\shell32.dll,21"`, `Description`; then a message box "Shortcut made on the desktop: Nesting tool. Run make-shortcut again if this folder moves."

- [ ] **Step 1: Failing tests (static):** `test_bat_and_vbs_are_crlf_ascii` (`git check-attr eol` gives `crlf` for `start.bat`, `start-quiet.vbs`, `make-shortcut.vbs`; the files are ASCII), `test_start_bat_quiet_mode` (start.bat mentions `NESTING_QUIET`, `--exit-when-closed`, `nesting.ping`, `exit /b %CODE%`, and the labels `:busy`, `:oldpython`, `:nofolder`), `test_vbs_codes_match_bat` (every exit code 2..5 appears in `start-quiet.vbs` messages; the vbs refers to `start.bat`, `NESTING_QUIET`, `start.log`), `test_make_shortcut_targets_launcher` (`start-quiet.vbs`, `wscript.exe`, `WorkingDirectory` in `make-shortcut.vbs`).
- [ ] **Step 2: Run** → fail.
- [ ] **Step 3: Implement.** Re-read the cmd quoting by hand (`cmd /c ""a b\start.bat" > "c d\start.log" 2>&1"`: first and last quote stripped).
- [ ] **Step 4: Run** the full suite → pass.
- [ ] **Step 5: Commit** `git commit -m "Windows: quiet start.bat, hidden launcher with a message box, desktop shortcut"`

### Task 8: Docs

**Files:**
- Modify: `WINDOWS.md`, `nesting/README.md`
- Test: `tests/test_launchers.py` (`DocsTests`)

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `WINDOWS.md`: section "Once: make the icon" (double-click `make-shortcut.vbs`; antivirus may warn about a script; run again if the folder moves); "Every time: start the tool" now says click the **Nesting tool** icon; no window; the page opens; the tool stops by itself about 20 seconds after the page is closed (3 minutes if the browser was closed without a note; 10 minutes if no page ever opened); a reload does not stop it; a banner says when it has stopped; a message box on failure, with the log `%USERPROFILE%\nesting-project\start.log`. "Troubleshooting: the old way": double-click `start.bat` (window, runs until the window is closed). Each new step marked **not tested on Windows**. Note that VBScript is an optional Windows feature Microsoft plans to remove in a future Windows version; then `start.bat` still works.
  - `nesting/README.md`: the usage line gains `[--exit-when-closed]`; a bullet for it (timings, never during a request, `/api/ping`); a "Linux and macOS" section (`./start.sh`, `./install-launcher.sh`, log `~/nesting-project/start.log`, `NESTING_PORT`/`NESTING_PROJECT`, the hand-made scripts in `~/bin` on the CNC PC can be removed by the user once this works; marked **not tested on Linux**; macOS: `start.sh` only, no icon); the Windows section mentions the icon.
- [ ] **Step 1: Failing test:** `test_docs_mark_untested`: `WINDOWS.md` contains `make-shortcut.vbs`, `start.log` and `not tested on Windows`; `nesting/README.md` contains `--exit-when-closed`, `install-launcher.sh` and `not tested on Linux`.
- [ ] **Step 2: Run** → fail.
- [ ] **Step 3: Write the docs.**
- [ ] **Step 4: Run** the full suite → pass.
- [ ] **Step 5: Commit** `git commit -m "Docs: the icon, the log, the self-stop, the old way"`
