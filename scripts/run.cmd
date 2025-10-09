@echo off
setlocal
REM Universal runner: finds jarvis_main.py whether this file is in repo root or scripts/.

set "HERE=%~dp0"
set "ROOT=%HERE%.."

REM Figure out where jarvis_main.py lives.
if exist "%HERE%jarvis_main.py" (
  set "WORK=%HERE%"
) else if exist "%ROOT%\jarvis_main.py" (
  set "WORK=%ROOT%"
) else (
  echo [ERROR] Could not find jarvis_main.py near:
  echo   %HERE%
  echo Move this run.cmd to either the repo root or the scripts folder.
  pause
  exit /b 1
)

pushd "%WORK%"
REM Prefer the Python launcher (py) if present; otherwise fall back to python.
where py >nul 2>nul
if %errorlevel%==0 (
  py -X utf8 jarvis_main.py
) else (
  python -X utf8 jarvis_main.py
)
popd
pause
