@echo off
:: DescriVox Agent launcher — uses Python 3.13 explicitly
:: This ensures aiohttp and all deps are found

set PYTHON=C:\Users\USER\AppData\Local\Programs\Python\Python313\python.exe

if not exist "%PYTHON%" (
    echo [ERROR] Python 3.13 not found at %PYTHON%
    pause
    exit /b 1
)

echo Starting DescriVox Agent...
"%PYTHON%" "%~dp0main.py"
if errorlevel 1 (
    echo [ERROR] Application exited with error code %errorlevel%
    pause
)
