@echo off
:: Build a distributable Windows bundle with PyInstaller.
:: Output: dist\OmniDescriber\  (folder distribution - start with OmniDescriber.exe)
:: Full pipeline: compile check -> PyInstaller -> exe smoke test -> zip

setlocal
cd /d "C:\Users\USER\Documents\omni-describer-custom"
set PY=C:\Users\USER\AppData\Local\Programs\Python\Python313\python.exe

echo === [1/4] compile check ===
%PY% -m compileall -q src main.py >nul 2>&1 && (echo COMPILE_PASS) || (echo COMPILE_FAIL & exit /b 1)

:: NOTE: the flags below are the source of truth. PyInstaller
:: REGENERATES OmniDescriber.spec from them on every run, so editing
:: the spec by hand achieves nothing (learned the hard way, v1.6.1).
:: faster_whisper + ctranslate2 + onnxruntime add ~110 MB: local,
:: free speech-to-text for a provider that cannot hear the video.
echo === [2/4] PyInstaller ===
if not exist %PY% (echo NO_PYTHON & exit /b 1)
%PY% -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name OmniDescriber ^
  --paths src ^
  --add-data "doc;doc" ^
  --add-data "src/omni_describer_custom/i18n/locales;omni_describer_custom/i18n/locales" ^
  --collect-submodules omni_describer_custom ^
  --hidden-import pywin32_system32 ^
  --hidden-import win32timezone ^
  --hidden-import comtypes.stream ^
  --collect-all pyttsx3 ^
  --collect-all edge_tts ^
  --collect-all openai ^
  --collect-all aiohttp ^
  --collect-all PIL ^
  --collect-all faster_whisper ^
  --collect-all ctranslate2 ^
  --collect-all onnxruntime ^
  --collect-all tokenizers ^
  --collect-all av ^
  --collect-all huggingface_hub ^
  --exclude-module google.generativeai ^
  --exclude-module accessible_output2 ^
  --exclude-module pytest ^
  main.py > "%TEMP%\pyinstaller_odc.log" 2>&1
if errorlevel 1 (echo PYINSTALLER_FAIL & type "%TEMP%\pyinstaller_odc.log" & exit /b 1)
echo PYINSTALLER_OK

echo === [3/4] exe smoke test ===
if not exist "dist\OmniDescriber\OmniDescriber.exe" (echo EXE_MISSING & type "%TEMP%\pyinstaller_log" & exit /b 1)
%PY% -u tests\test_build_smoke.py
if errorlevel 1 (echo SMOKE_FAIL & exit /b 1)
echo SMOKE_OK

echo === [4/4] zip ===
%PY% -c "import sys; sys.path.insert(0, 'src'); from omni_describer_custom import __version__ as v; import shutil; shutil.make_archive(f'dist/OmniDescriber-{v}-win64', 'zip', 'dist', 'OmniDescriber')" && (echo ZIP_OK) || (echo ZIP_FAIL & exit /b 1)
dir dist\OmniDescriber-*-win64.zip
echo BUILD_ALL_OK
