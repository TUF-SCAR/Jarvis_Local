@echo off
setlocal
REM One-click CUDA/cuDNN wiring. This elevates and runs gpu-setup.ps1.

set "SCRIPT_DIR=%~dp0"
set "PSFILE=%SCRIPT_DIR%gpu-setup.ps1"

REM Launch elevated PowerShell that runs the script with ExecutionPolicy Bypass
powershell -NoProfile -Command ^
  "Start-Process PowerShell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','\"%PSFILE%\"'"

echo.
echo If nothing happened, right-click this file and choose "Run as administrator".
pause
