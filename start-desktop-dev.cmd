@echo off
setlocal

cd /d "%~dp0"

set "PS_ARGS="
if /I "%~1"=="--dry-run" set "PS_ARGS=-DryRun"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-tauri-dev.ps1" %PS_ARGS%
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo start-desktop-dev failed with exit code %EXITCODE%.
    pause
)

exit /b %EXITCODE%
