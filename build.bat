@echo off
:: Build a distributable Windows bundle with PyInstaller.
:: Output: dist\DescriVox\  (folder distribution - start with DescriVox.exe)
:: Full pipeline: compile check -> PyInstaller -> exe smoke test -> zip

setlocal
cd /d "C:\Users\USER\Documents\omni-describer-custom"
set PY=C:\Users\USER\AppData\Local\Programs\Python\Python313\python.exe

echo === [1/6] external binaries ===
:: ffmpeg/ffprobe/ffplay/yt-dlp are shipped inside the bundle (v1.6.5).
:: They are ~217 MB so they are not in git; this fetches them into bin\
:: when absent and fails the build rather than shipping a broken app.
%PY% tools\fetch_binaries.py
if errorlevel 1 (echo BINARIES_FAIL & exit /b 1)
echo BINARIES_OK

echo === [2/6] compile check ===
%PY% -m compileall -q src main.py >nul 2>&1 && (echo COMPILE_PASS) || (echo COMPILE_FAIL & exit /b 1)

:: NOTE: the flags below are the source of truth. PyInstaller
:: REGENERATES DescriVox.spec from them on every run, so editing
:: the spec by hand achieves nothing (learned the hard way, v1.6.1).
:: faster_whisper + ctranslate2 + onnxruntime add ~110 MB: local,
:: free speech-to-text for a provider that cannot hear the video.
echo === [3/6] PyInstaller ===
if not exist %PY% (echo NO_PYTHON & exit /b 1)
%PY% -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name DescriVox ^
  --paths src ^
  --add-data "doc;doc" ^
  --add-data "bin;bin" ^
  --add-data "NOTICE.md;." ^
  --add-data "src/omni_describer_custom/i18n/locales;omni_describer_custom/i18n/locales" ^
  --collect-submodules omni_describer_custom ^
  --hidden-import pywin32_system32 ^
  --hidden-import win32timezone ^
  --hidden-import comtypes.stream ^
  --collect-all pyttsx3 ^
  --collect-all prism ^
  --additional-hooks-dir hooks ^
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
  --exclude-module torch ^
  --exclude-module coverage ^
  main.py > "%TEMP%\pyinstaller_odc.log" 2>&1
if errorlevel 1 (echo PYINSTALLER_FAIL & type "%TEMP%\pyinstaller_odc.log" & exit /b 1)
echo PYINSTALLER_OK

:: PyInstaller writes a SECOND copy of every ffmpeg DLL into _internal\
:: because it recognises them as libraries. 189 MB of duplicate. Run
:: this BEFORE the smoke test, so the test proves the app still starts
:: without them.
%PY% tools\dedupe_build.py
if errorlevel 1 (echo DEDUPE_FAIL & exit /b 1)

echo === [4/6] exe smoke test ===
if not exist "dist\DescriVox\DescriVox.exe" (echo EXE_MISSING & type "%TEMP%\pyinstaller_log" & exit /b 1)
%PY% -u tests\test_build_smoke.py
if errorlevel 1 (echo SMOKE_FAIL & exit /b 1)
echo SMOKE_OK

:: GPL compliance: the notice has to be where someone opening the
:: folder will see it, not buried in _internal where PyInstaller puts
:: --add-data. Copied next to the exe as well.
copy /y NOTICE.md "dist\DescriVox\NOTICE.md" >nul
if errorlevel 1 (echo NOTICE_COPY_FAIL & exit /b 1)

echo === [5/6] zip ===
%PY% -c "import sys; sys.path.insert(0, 'src'); from omni_describer_custom import __version__ as v; import shutil; shutil.make_archive(f'dist/DescriVox-Agent-{v}-win64', 'zip', 'dist', 'DescriVox')" && (echo ZIP_OK) || (echo ZIP_FAIL & exit /b 1)
dir dist\DescriVox-Agent-*-win64.zip
echo === [6/6] source backup ===
:: Owner, 3 Oct 2026: every release also backs up its source code -
:: committed files only (git archive), checked for binaries and keys.
%PY% tools\make_source_zip.py
if errorlevel 1 (echo SOURCE_ZIP_FAIL & exit /b 1)
echo BUILD_ALL_OK
