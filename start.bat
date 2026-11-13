@echo off
rem Start the nesting tool on Windows (double-click). See WINDOWS.md.
rem 1. update from GitHub if possible (never waits for a password, never stops on failure)
rem 2. find Python, 3. open the page if the tool already runs, else start it on port 8800
rem and open the page in the browser.
rem Quiet mode (NESTING_QUIET=1, set by start-quiet.vbs, the desktop shortcut): no pause, no
rem wait, output goes to the log the launcher redirects it to, and the tool stops by itself
rem when the page is closed (--exit-when-closed). An environment variable, not an argument,
rem so that it survives the re-call after an update.
rem Exit codes: 0 ok or already running (page opened), 1 cannot open the folder of this file,
rem 2 no Python, 3 Python older than 3.11, 4 port taken by another program, 5 the tool did not
rem start or stopped with an error. Every way out ends with "exit /b N" as the last command run:
rem only then does "cmd /c start.bat" (the launcher) reliably return N.
setlocal
set "QUIET="
if "%NESTING_QUIET%"=="1" set "QUIET=1"
rem The log is a file: Python then writes UTF-8 to it, so a path with letters outside the
rem Windows code page cannot crash a print (not tested on Windows).
if defined QUIET set "PYTHONUTF8=1"
title Nesting tool
cd /d "%~dp0"
if errorlevel 1 goto nofolder

set "PORT=8800"
set "PROJECT=%USERPROFILE%\nesting-project"
set "URL=http://127.0.0.1:%PORT%/"
if defined QUIET echo Nesting tool, started %DATE% %TIME%

rem ---- update -------------------------------------------------------------------------------
rem cmd reads a batch file while it runs it, and the pull may change this file: so after a pull
rem the rest runs from a fresh start of the new file (call ... --updated), all on one parsed line.
rem "exit /b" with no number keeps the ERRORLEVEL the new file ended with, so its exit code
rem passes through to the launcher (no delayed expansion needed).
if "%~1"=="--updated" goto updated
rem Never wait for a password or a host key, and give up on a stalled download (less than
rem 1000 bytes/s for 30 s), as start.sh does: the quiet start has no window to answer in.
rem ssh only when no other ssh program is set up (not tested on Windows).
set "GIT_TERMINAL_PROMPT=0"
set "GCM_INTERACTIVE=never"
if not defined GIT_SSH if not defined GIT_SSH_COMMAND set "GIT_SSH_COMMAND=ssh -o BatchMode=yes"
where git >nul 2>nul
if errorlevel 1 goto nogit
echo Checking for updates...
git -c credential.interactive=never -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=30 pull --ff-only -q >nul 2>nul && (call "%~f0" --updated & exit /b)
echo Update skipped (offline, local changes or no access): starting the version on this PC.
goto version
:nogit
echo Git not found: no update, starting the version on this PC.
goto version
:updated
echo Update: up to date with GitHub.
:version
echo Nesting tool in %CD%
git --no-pager log -1 "--format=Version %%h of %%cs" 2>nul

rem ---- Python -------------------------------------------------------------------------------
:findpython
set "PY="
py -3 --version >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto checkpython
python --version >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto checkpython
goto nopython
:checkpython
%PY% -c "import sys; sys.exit(sys.version_info < (3, 11))"
if errorlevel 1 goto oldpython

rem ---- already running? ---------------------------------------------------------------------
rem nesting.ping exits 0 when the tool answers, 1 when the port is free, 2 when something else
rem holds it. Anything other than 0 or 1 counts as "something else" (start nothing).
%PY% -m nesting.ping %PORT%
set "PING=%ERRORLEVEL%"
if "%PING%"=="0" goto running
if not "%PING%"=="1" goto busy

rem ---- start --------------------------------------------------------------------------------
rem The launcher creates the project folder for its log, so look for the shapes folder.
set "SEED="
if not exist "%PROJECT%\shapes\" set "SEED=--seed-plates"
set "STOP="
if defined QUIET set "STOP=--exit-when-closed"
echo.
echo Project folder: %PROJECT%
echo The page opens in your browser: %URL%
if defined QUIET echo Stops by itself when the page is closed.
if not defined QUIET echo Keep this window open while you work. Close it to stop the tool.
echo.
%PY% -m nesting "%PROJECT%" --port %PORT% --open %STOP% %SEED%
rem Any code but 0 (a crash gives a negative one, which "if errorlevel 1" would miss).
if not "%ERRORLEVEL%"=="0" goto toolfailed
if defined QUIET echo The tool has stopped.
goto end

:running
echo.
echo Port %PORT% is in use by the tool: it is already running (in another window or from the icon).
echo Opening the page %URL%
start "" "%URL%"
if not defined QUIET timeout /t 10 >nul
goto end

:busy
echo.
echo Port %PORT% is in use by another program (or an old copy of the tool still runs in a window: close it). Nothing was started.
set "CODE=4"
goto fail

:nopython
echo.
echo Python 3 was not found.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
echo then double-click start.bat again.
set "CODE=2"
goto fail

:oldpython
echo.
echo This Python is too old (3.11 or newer is needed):
%PY% --version
echo Install the latest Python 3 from https://www.python.org/downloads/
set "CODE=3"
goto fail

:toolfailed
rem Two clicks at once: both found the port free and the other click's tool got it. That is
rem no failure: open the page (not tested on Windows).
%PY% -m nesting.ping %PORT%
if "%ERRORLEVEL%"=="0" goto otherclick
echo.
echo The tool did not start or stopped with an error.
set "CODE=5"
goto fail

:otherclick
echo The tool is already running (started by another click).
goto running

:nofolder
echo Cannot open the folder of start.bat: %~dp0
set "CODE=1"
goto fail

:fail
echo.
echo Stopped (code %CODE%). Read the message above.
if not defined QUIET pause
exit /b %CODE%

:end
exit /b 0
