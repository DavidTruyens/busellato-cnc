@echo off
rem Copy the newest generated job to the diskette (double-click). See WINDOWS.md.
rem Copies the DISKETTE folder of the newest job in %USERPROFILE%\nesting-project\out, asks for the
rem drive (or give it: copy-to-diskette.bat A:), erases the diskette after you type YES, checks
rem every file by reading it back.
setlocal
title Copy to diskette
cd /d "%~dp0"
if errorlevel 1 goto nofolder

set "PY="
py -3 --version >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto run
python --version >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto run
echo Python 3 was not found.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
goto done

:run
%PY% -m nesting.diskette "%USERPROFILE%\nesting-project" %*
goto done

:nofolder
echo Cannot open the folder of copy-to-diskette.bat: %~dp0

:done
echo.
pause
endlocal
