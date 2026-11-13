@echo off
rem Start the nesting tool on Windows (double-click). See WINDOWS.md.
rem 1. update from GitHub if possible (never waits for a password, never stops on failure)
rem 2. find Python, 3. start the tool on port 8800 and open the page in the browser.
setlocal
title Nesting tool
cd /d "%~dp0"
if errorlevel 1 goto nofolder

set "PORT=8800"
set "PROJECT=%USERPROFILE%\nesting-project"
set "URL=http://127.0.0.1:%PORT%/"

rem ---- update -------------------------------------------------------------------------------
rem cmd reads a batch file while it runs it, and the pull may change this file: so after a pull
rem the rest runs from a fresh start of the new file (call ... --updated), all on one parsed line.
if "%~1"=="--updated" goto updated
set "GIT_TERMINAL_PROMPT=0"
set "GCM_INTERACTIVE=never"
where git >nul 2>nul
if errorlevel 1 goto nogit
echo Checking for updates...
git pull --ff-only -q >nul 2>nul && (call "%~f0" --updated & exit /b)
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
echo.
echo Python 3 was not found.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
echo then double-click start.bat again.
goto fail
:checkpython
%PY% -c "import sys; sys.exit(sys.version_info < (3, 11))"
if errorlevel 1 goto oldpython

rem ---- already running? ---------------------------------------------------------------------
%PY% -c "import socket, sys; s = socket.socket(); s.settimeout(2); sys.exit(1 if s.connect_ex(('127.0.0.1', %PORT%)) == 0 else 0)"
if errorlevel 1 goto running

rem ---- start --------------------------------------------------------------------------------
set "SEED="
if not exist "%PROJECT%\" set "SEED=--seed-plates"
echo.
echo Project folder: %PROJECT%
echo The page opens in your browser: %URL%
echo Keep this window open while you work. Close it to stop the tool.
echo.
%PY% -m nesting "%PROJECT%" --port %PORT% --open %SEED%
if errorlevel 1 goto fail
goto end

:running
echo.
echo Port %PORT% is in use: the tool may already be running in another window.
echo Opening the page %URL%
start "" "%URL%"
timeout /t 10 >nul
goto end

:oldpython
echo.
echo This Python is too old (3.11 or newer is needed):
%PY% --version
echo Install the latest Python 3 from https://www.python.org/downloads/
goto fail

:nofolder
echo Cannot open the folder of start.bat: %~dp0
goto fail

:fail
echo.
echo Stopped. Read the message above.
pause
exit /b 1

:end
endlocal
