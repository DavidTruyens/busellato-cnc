# Start the nesting tool without a terminal — design

Date: 2026-11-13
Status: design, not built. Builds on `main` (nesting tool with pockets, PR #8).

## Goal

The person at the shop starts the tool by clicking an icon and nothing else: no black window, no terminal. The page opens, and when the page is closed the tool stops by itself. Windows and the Linux CNC PC are the targets.

Why: today `start.bat` leaves a black window open that must stay open and be closed to stop the tool, and the Linux PC has a start script that was made by hand outside the repo. A person who only wants to nest and generate programs should not have to run or watch a program.

## What exists (build on it)

- `python -m nesting [PROJECT_DIR] [--port N] [--seed-plates] [--open]` (`nesting/server.py`, `main`) serves the page, binds the port, and with `--open` opens the browser once the socket listens. It runs until it is killed.
- `start.bat` (Windows): `git pull --ff-only` (never asks for a password), finds Python 3.11 or newer, checks whether the port is already in use (then only opens the page), starts the tool in the foreground with `--open`, and shows errors in the window and waits for a key. `WINDOWS.md` describes it.
- The Linux CNC PC has `~/bin/start-nesting.sh` and `~/bin/update-nesting.sh`, made by hand and not in the repo. That PC is offline at the moment.
- The page saves its settings to the server as they change (existing behaviour). There is no unsaved-changes guard and none is added here.

## Decisions (the user's, unless marked "my call")

1. **Not a PWA.** A PWA cannot start the Python server and Firefox on desktop (the Linux PC) cannot install one. The goal is starting without a terminal, so launchers and an auto-stop are built instead.
2. **The tool stops by itself** when the last page is closed. No Quit button.
3. **An icon starts it** on Windows and on the Linux PC. The icon starts the tool, opens the page in the default browser, and does nothing visible beyond that.

## My calls (change any)

- **How the server knows the page is closed:** the page sends a small "still here" request to the server every 10 seconds while it is open. A new server flag `--exit-when-closed` makes the server exit when no such request has arrived for 3 minutes (browsers slow the timers of background tabs, so the grace must be long). When the page is closed or reloaded it also sends a "closing" note (`sendBeacon`); if no new request arrives within 20 seconds after it, the server exits. A reload sends the first request again within a second or two, so it does not stop the tool. Numbers are defaults the builder may change.
- **Never stops in the middle of work:** the server does not exit while a request is in progress (generate, save, upload).
- **When no page ever connects** (the browser failed to open), the server exits after 10 minutes so it does not run forever, unseen.
- **The old way stays:** without `--exit-when-closed` the server behaves as today (runs until killed), so `python -m nesting`, `start.bat` run from a terminal by a developer and the existing tests are unchanged. Only the launchers pass the flag.
- **Windows:**
  - `start.bat` gets a quiet mode used by the icon: no output to a window, everything written to `%USERPROFILE%\nesting-project\start.log`, and the tool started with `--exit-when-closed`.
  - A small launcher script (VBScript or PowerShell, whichever runs on a default Windows without installing anything) starts `start.bat` in quiet mode with no visible window. If `start.bat` fails, a message box says what happened (no Python, Python too old, port busy with something else, the tool did not start) and where the log is; a failed update never stops the start, it is only written to the log. If the tool already runs, the launcher only opens the page.
  - A one-time script `make-shortcut` creates a "Nesting tool" shortcut on the desktop that runs the launcher. The existing `start.bat` (double-click, with a window) stays as it is for troubleshooting.
  - The update from GitHub still happens at each start, with the same rules (never waits for a password, never stops the start on failure).
- **Linux:**
  - A `start.sh` in the repo does what `start.bat` does: update with `git pull --ff-only` (never waits for a password, never stops the start), find Python 3.11 or newer, start the tool with `--open --exit-when-closed`, write to `~/nesting-project/start.log`, show an error as a desktop notification (`notify-send` or `zenity`, whichever exists) and in the log. If the tool already runs, only open the page.
  - `install-launcher.sh` writes a desktop entry (`~/.local/share/applications/nesting-tool.desktop`, and a copy on the Desktop) that runs `start.sh` without a terminal.
  - The hand-made scripts in `~/bin` on the CNC PC can then be removed; replacing them is done by the user when the PC is online, not by this work.
- **macOS:** only `start.sh` (works there as well); no icon launcher.
- **Docs:** `WINDOWS.md` and `nesting/README.md` describe the icon, the log file, the self-stop, and how to start the old way for troubleshooting.

## More calls, from the builder check (mine; change any)

- **Last request time, no tab tracking:** the server keeps one "last seen" time. Any request (the "still here" ping, a save, a generate) sets it. A "closing" note only starts the 20-second countdown, and any later request cancels it. Two tabs, a reload and a stale tab all just keep the tool up until nothing has been seen for the grace time.
- **Identity probe:** the server answers `GET /api/ping` with a small JSON that says it is the nesting tool (and its version). The launchers use it to tell "the tool is already running" (open the page) from "something else holds the port" (message box). The probe counts as a request, so a launch during the 20-second countdown keeps the tool alive.
- **Quiet mode of `start.bat`:** no `pause`, no output to a window; each failure ends with a distinct exit code (no Python, Python too old, port taken by something else, tool did not start) and a reason line in the log. The launcher shows the message box from the exit code and the last lines of the log.
- **Paths:** `make-shortcut` stores the absolute path of this clone and sets the shortcut's working directory to it; the launcher finds the repo from its own location. Paths with spaces must work. If the folder moves, run `make-shortcut` again.
- **Updating the scripts while they run:** `start.bat` keeps its re-call trick. `start.sh` is written as one function that is read in full before it runs, so a pull cannot change it midway. A change to the launcher script itself takes effect from the next start.
- **A stopped tool is visible:** when several pings in a row fail, the page shows a banner "The tool has stopped. Start it again with the icon, then reload this page."

## Constraints

- Nothing here has run on Windows or on the Linux PC. The scripts are written and checked on a Mac (syntax, dry runs of the logic); each step is marked "not tested on Windows/Linux" in the docs, as `WINDOWS.md` already does. The auto-stop logic in Python has tests.
- The repo is public: no names of the shop operator, no hostnames, emails, IPs or customer names in files, commits or PR text.
- No dependency beyond what the tool needs now (Python standard library; Git on the PCs). The desktop entry and the Windows launcher use only what a default install has.
- The page, the programs and the diskette copy do not change.

## Non-goals

- A PWA, a Quit button, an app-style browser window, a system tray icon, starting at login, or running the tool as a service.
- An icon launcher for macOS.
- Stopping the tool from a second place (a "stop" script) beyond closing the page; killing the process still works.
- Changing how the tool is installed the first time (Python, Git, clone).

## Anti-goals

- The tool stopping while someone is working: a reload, a background tab, a long generate, or a laptop sleeping briefly must not stop it.
- A tool that never stops after the browser failed to open.
- A silent failure: any reason the icon does nothing must show a message and be in the log.
- A second copy of the tool started on another port when one already runs.

## Left to the builder

- The exact endpoint names and the timing numbers; how the server tracks the last request; how tests control time.
- VBScript or PowerShell for the Windows launcher, and how the quiet mode of `start.bat` is passed in.
- How `start.sh` and `start.bat` share logic, if at all (they may stay separate).
- The icon image (a generic one is fine).

## Open items (need the machine or the user)

1. Whether the Windows launcher and the shortcut work on the shop operator's PC; whether antivirus complains about a hidden script.
2. Whether the Linux desktop on the CNC PC shows the entry and has `notify-send` or `zenity`.
3. Whether 3 minutes and 20 seconds feel right in use.
