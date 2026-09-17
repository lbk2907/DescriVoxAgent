@echo off
cd /d "C:\Users\USER\Documents\omni-describer-custom"
set PY=C:\Users\USER\AppData\Local\Programs\Python\Python313\python.exe
set FAIL=0

rem v1.5.5: the suite builds real MainFrames that write provider settings.
rem Without this they landed in the USER's live settings.json (a gate run
rem left Gemini pointing at a dead test loopback URL). Throwaway dir only.
set ODC_CONFIG_DIR=%TEMP%\odc_gate_config

%PY% -m compileall -q src main.py >nul 2>&1 && (echo COMPILEALL_PASS) || (echo COMPILEALL_FAIL & set FAIL=1)

for %%T in (run_checks test_minimal_repro test_fixes test_fixes2 test_fixes3 test_fixes4 test_fixes5 test_fixes6 test_fixes7 test_fixes8 test_fixes9 test_fixes10 test_fixes11 test_fixes12 test_fixes13 test_fixes14 test_fixes15 test_fixes16 test_fixes17 test_fixes18 test_fixes19 test_fixes20 test_chunked_video test_v130_player_srt test_acceptance test_gui_smoke test_timeline_io test_packaging_content test_pipeline) do (
  %PY% -u tests\%%T.py > "%TEMP%\gate_%%T.txt" 2>&1 && (echo %%T: PASS) || (echo %%T: FAIL & type "%TEMP%\gate_%%T.txt" & set FAIL=1)
)

if %FAIL%==1 (echo GATE_FAIL) else (echo GATE_ALL_PASS)
exit /b %FAIL%
