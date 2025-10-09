@echo off
setlocal
REM Double-click me to install everything globally (no venv).
REM This just forwards to the PowerShell installer with elevation.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
pause
