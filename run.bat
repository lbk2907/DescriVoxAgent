@echo off
:: Run from this checkout, regardless of the caller's current directory.
setlocal DisableDelayedExpansion
cd /d "%~dp0" || exit /b 1

set "PY="
for /f "usebackq delims=" %%P in (`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\find_python.ps1"`) do set "PY=%%P"
if not defined PY exit /b 1

echo Starting DescriVox Agent...
"%PY%" "%~dp0main.py"
set "RESULT=%errorlevel%"
if not "%RESULT%"=="0" (
    echo [ERROR] Application exited with error code %RESULT%
    pause
)
exit /b %RESULT%
