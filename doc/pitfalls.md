# Pitfalls — DescriVox Agent

Lessons learned the hard way, each with the evidence that taught it. Read
the ones for the area you are changing before you change it (the index by
area is in `AGENTS.md`, section 8).

**Code comments cite these as "pitfall N". Never renumber, merge or delete
an entry; add new ones at the end (the next number is 95).** 57b is a
historical double number, kept as is. Moved here from `AGENTS.md` and
translated from Malay on 1 Oct 2026; the original Malay text is in the git
history of `AGENTS.md` (tag v1.9.5).

### 1. Full-video mode ≠ exact timestamps
Frame mode = timestamps that we determine (exact); full-video = the AI guesses them itself. Do not mix EXPECTATIONS between these two modes in tests.

### 2. Chunked processing needs context between parts
Part X of Y + a summary of the previous part + a prohibition on "video starts with" + consistent character names. If you add a new mode, copy this pattern (v1.5.3).

### 3. The DirectUI progress bar has no msctls_progress32
E2E reads the percent via `GetWindowTextW` (the dialog title) + a `PrintWindow` pixel scan, NOT `PBM_GETPOS`.

### 4. TTS SAPI5: use win32com `SpFileStream` directly, NOT `runAndWait`
In the past `runAndWait` caused no sound to come out.

### 5. wx GUI tests need pytest-style wx app init
See `test_fixes15` as the correct example. GUI tests in the gate instantiate real dialogs.

### 6. Monaco/CodeMirror do not exist in this GUI (wxPython)
Browser automation tools are irrelevant; for GUI automation use pywinauto UIA + raw Win32 (see `tools/` and the E2E tests).

### 7. Large reasoning models (GLM) need max_tokens ~6000
The timeout has already been bumped; do not reduce it without a real test.

### 8. `wx.ProgressDialog` PUMPS the event loop in its constructor
Queued `wx.CallAfter` handlers can run INSIDE that constructor, before `self._dl_dialog` is assigned. That is why `_ensure_download_progress` uses the `_dl_close_gen` counter: if cleanup happens while the dialog is being built, that new dialog is discarded (v1.5.5). The same pattern is needed for any new modal dialog created from a CallAfter.

### 9. Test output MUST be line-buffered
A hand-built `io.TextIOWrapper(...)` ignores `python -u`; when the process crashes, the buffer is lost and the gate prints an EMPTY log (v1.5.5: a crash hidden for months). All files in `tests/` use `line_buffering=True`.

### 10. A wx frame must be drained before Destroy in tests
Worker threads still have `wx.CallAfter` calls queued; Destroy first = access violation. See `_drain_events`/`_destroy_frame` in `tests/test_fixes12.py`.

### 11. wxPython Phoenix: there is NO `SetYesLabel`/`SetNoLabel`/`SetCancelLabel`
Use `SetYesNoCancelLabels(yes, no, cancel)`. v1.5.5 bug: the Open button DID NOTHING for a video that already had a project (AttributeError in `_start_processing`). Same family as `MenuBar.SetLabelTop`. **Check `hasattr` first before using a rarely used wx API.**

### 12. `SetLabel()` EATS the control's state on MSW
`wx.Choice` loses its SELECTION; a `wx.TextCtrl`'s text is REPLACED by that label. v1.5.4 used SetLabel for the NVDA name on 3 controls → every fresh launch had no preset selected (Open answered "Please select a prompt preset") and the prompt box contained its own label, which was sent to the AI as "User notes". Use `MainFrame._set_accessible_name()` (v1.5.6/1.5.7). **For a TextCtrl use `SetName`, not `SetLabel`.**

### 13. Prompts MUST follow audio description standards, not "describe everything"
Sources: DCMP Description Key, Netflix AD Style Guide v2.1, W3C/WAI, ADLAB. Core: describe only what is needed to understand; DO NOT describe what is already audible (dialogue/music/sound); present tense, third person; report what is visible, not interpretation; do not guess race/gender; short enough to be spoken. Presets follow STRATEGY, not genre — the standards use the same rules for all genres (Netflix names only two: children's, horror/suspense). `prompt_manager.DEFAULT_PROMPTS` = the ONE source of prompts; `tests/test_fixes22.py` locks these rules. Old presets are removed only if their text is still our original text (user edits are never touched).

### 14. The model DOES NOT obey cue-placement requests — use a mechanism
The v1.6.3 prompt asked it to place descriptions in the gaps between speech (the transcript has timestamps). Measured: given a transcript with a deliberate 55-second hole, it placed 9 cues in the speaking half and 7 in the silent half — 56% still in the noisy one. It chooses where something HAPPENS visually, not where the audio is free.

**The reliable answer = the player pause toggle** (`player.pause_for_narration`), not a sentence in the prompt. The prompt rule is kept because it is correct and free, not because it is effective. For dialogue-dense + fast-action content (example: the Ocong video, 91% speech), automatic pausing really is the right approach — that is the W3C *extended description* case.

### 15. GLM CANNOT HEAR the video's audio
Probed 20 Sep 2026: asked to transcribe the first sentence, it answered "NO AUDIO ACCESS". It sees frames only. That is why the `foreign` preset is impossible without a transcript, and the old instruction "describe visuals AND sounds/speech" was never actually achieved. Solution: `VideoProcessor.get_transcript()` (subtitles → embedded subtitles → Grok STT/Whisper) + `build_transcript_block()`. `provider_hears_audio()` stores this capability per provider.

### 16. The engine suffix is APPENDED AFTER the prompt, so what it says WINS
It must not have an opinion about WHAT is described — twice it silently overrode a preset (v1.6.0: "AND sounds/speech", then "important VISUALS", which killed `foreign`). Format only there.

### 17. `DescriVox.spec` (was `OmniDescriber.spec`) is REGENERATED by PyInstaller
From the flags in `build.bat` every time. Editing it is pointless — change `build.bat`.

### 18. Handlers = the surface most often missed
Before `tests/test_fixes21.py` (17 Sep 2026) NOT ONE main-window menu/button handler was called by any test — the windows were tested, the handlers that open them were not. That is where the dead Open button bug was hiding. **Adding a new handler = adding a check in test_fixes21.**

### 19. Tests MUST use isolated settings
`run_gate.bat` sets `ODC_CONFIG_DIR=%TEMP%\odc_gate_config`; `SettingsStore` honours that env var. Before v1.5.5 the gate wrote to the user's REAL `settings.json` (the Gemini provider became `http://127.0.0.1:.../v1beta` + key `test-key`). Do not remove this env var, and do not set it in E2E tools — E2E really does need the real settings (the GLM key).

### 20. Find external programs ONLY through `core/tools.py:find_tool()`
Before v1.6.5 there were FIVE separate places (`video_processor`, `player_window`, `tts_engine`, `timeline_io`, `ai_engine`) and only one knew about the `bin/` folder. That is why the bundled player was silent even though the rest of the app worked. `tests/test_fixes25.py` fails the gate if any call site does its own lookup — verified to catch all 11 lines of the old version.

### 21. External binaries are NOT in git (217 MB)
`tools/fetch_binaries.py` downloads them to `bin/`; `build.bat` step [1/5] runs it. A fresh clone WITHOUT this step produces an app that looks finished but fails on the first download.

### 22. The bundled ffmpeg is a GPL build, not LGPL
`ai_engine` encodes with `libx264`, which only exists in the GPL build. If someone switches to LGPL to save on obligations, upload compression will break. The obligations are recorded in `NOTICE.md`; do not remove `bin/FFMPEG-LICENSE.txt` or `bin/FFMPEG-VERSION.txt`.

### 23. PyInstaller DUPLICATES every .dll in `--add-data`
It recognises the file as a library and writes a second copy to `_internal\` in addition to the one in `bin\` — 189 MB wasted in the first 1.6.5 build (avcodec alone 118 MB). `tools/dedupe_build.py` removes BYTE-IDENTICAL copies only and fails the build if they differ. `test_packaging_content.py` guards against this coming back.

### 24. Narration hold only for engines that know when a sentence ends
`HOLD_CAPABLE_ENGINES` = the FALLBACK answer (edge, sapi5, openai) when there is no engine object to ask. Since v1.6.6 `supports_narration_hold` asks the instance first (`supports_hold`), so Prism-on-SAPI gets the hold and Prism-on-NVDA does not.

### 25. Prism = the voice on machines WITHOUT a screen reader
`core/speech.py`. `_announce` uses MSAA/UIA focus (works with ALL screen readers, not just NVDA) — but is SILENT if there is no screen reader at all. `speech.announce()` speaks ONLY in that case; if a screen reader is present it stays quiet so as not to speak twice.

### 26. Prism backend capabilities DIFFER greatly — do not assume
Measured 22 Sep 2026: NVDA `supports_is_speaking=False`, `set_rate=False`, `set_voice=False`, `speak_to_memory=False`. SAPI/OneCore are all True. That is why Voice and Speed are disabled when `screen_reader` is selected. Read from the LIVE backend (`features`), not from the engine name.

**CORRECTED v1.7.1:** this entry used to say narration hold was also NOT POSSIBLE for screen readers. That was too absolute — see pitfall 46. NVDA itself indeed does not report it, but its sound can be heard stopping.

### 27. `ODC_PRISM_BACKEND` forces one backend by name
("SAPI", "NVDA", "OneCore"). Without this the "no screen reader" branch CANNOT be tested on the owner's machine (NVDA is always running). `test_fixes26.py` uses a subprocess because the `PrismSpeech` singleton binds the backend on first use.

### 28. Engines that are `speaks_directly` DO NOT produce a file
`speak_and_play` must branch BEFORE `speak()`, because `speak()` treats an empty path as failure and falls through to another engine — the voice the user chose would be silently replaced. Audio export still uses file-based engines.

### 29. ACCESSIBILITY IS VERIFIED BY LISTENING, not by reading code
`tools/nvda_accessibility_check.py` tabs around the real window and asks NVDA what was announced, via the NVDA HTTP Bridge (`http://127.0.0.1:19281`, plugin in the NVDA scratchpad; repo at `C:\Users\USER\nvda-http-bridge`). Pitfall 12 slipped through earlier PRECISELY BECAUSE the code looked correct. Run after any UI change:
```
python tools/nvda_accessibility_check.py --steps 12
```
Requires NVDA running; without the bridge it exits with code 2 (NOT 0) so that "not verified" is not misread as "passed". The evaluation logic is a pure function and is tested in `test_fixes27.py` — a detector never seen failing is not a detector.

Verified 22 Sep 2026: the combo says "combo box default collapsed" (the preset really is selected), the prompt box speaks the actual AD text, not its own label.

### 30. Downloads MUST go into the project's media folder
yt-dlp resumes `.part` by default; before v1.6.7 each attempt used a new `mkdtemp`, so partial files were orphaned. That is why the project is now created BEFORE the download (`_ensure_project_for`), not after the AI finishes. Do not revert that ordering.

**There are THREE download ENTRY POINTS, not one.** Two call `vp.resolve_source(...)` directly (full-video mode); the THIRD is frame mode — the DEFAULT path — which calls `vp.extract_frames(source)` and resolves the URL inside it. Patching only the first two looks correct in the diff and is still wrong: frame mode still uses a temp dir. `test_fixes28` counts entry points against those wired up so that a fourth entry point cannot be added silently.

### 31. DO NOT pick the downloaded file with `sorted(glob("video.*"))[0]`
`video.f616.mp4` (video-only stream, not yet merged) sorts BEFORE `video.mp4` alphabetically — the app would describe a SILENT video. Use `VideoProcessor.completed_download()`: the merged file has EXACTLY one suffix, intermediate ones have two.

### 32. `_compress_to` out_dir can now be the project's media folder
DO NOT `rmtree(out_dir)` on failure — that would delete the user's video. Delete only the output file (`out.unlink`).

### 33. ffmpeg staging files MUST keep the real extension
ffmpeg picks the muxer by extension; `.part` fails outright with "Error initializing the muxer ... Invalid argument". Use `name.partial.mp4`, not `name.part`.

### 34. wx Tab order follows CREATION order, not sizer order
A new button added in the middle of a sizer still becomes LAST under Tab. Use `MoveAfterInTabOrder(previous_control)` then verify with `tools/nvda_accessibility_check.py`.

### 35. Performance hints MUST NOT kill the job
`upload_cache_dir` is set from inside the processing pipeline; the original setter used `self._providers` directly and blew up on `AIEngine.__new__()` — the whole job died with "no descriptions saved". Use `getattr` + try/except for anything that is merely an optimisation.

### 36. Build flags ≠ build output. CHECK the REAL `dist/`
v1.6.6 shipped Prism with `--collect-all prism` and the test checked that flag in `build.bat` — passed. The shipped app logged "No module named 'prism._prism_cffi'" and the screen-reader voice feature was COMPLETELY DEAD. The reason is that `prism/_native.py` adds a folder to `__path__` at RUNTIME, so PyInstaller does not see that extension. `hooks/hook-prism.py` fixes it. **Packaging tests MUST read files in `dist/`, not flags in `build.bat`.**

### 37. There are TWO cleanup places for video parts, not one
`_describe_video_part` (single part) AND the `finally` block in the chunked path that `unlink`s every `part != path`. The second deleted the upload cache copy, so the v1.6.7 cache never survived a single job in full-video mode. Both now check `is_cached_upload()`.

### 38. Logs MUST print the FULL PATH, not the file name
"Compressed upload copy kept for retries: upload_xxx.mp4" looks correct while the file was written then deleted — a name alone cannot distinguish "kept" from "kept then discarded".

### 39. Abandoned temp folders were NEVER cleaned up
Before v1.6.7: 115 download folders = 806 MB on the owner's machine. `core/housekeeping.py` sweeps `odc_*` prefixes older than 24 hours when the app opens. **Add any new `mkdtemp` prefix to `_OUR_PREFIXES`** — `test_fixes29` fails the gate if you forget.

### 40. GUI automation: THREE ways to "succeed" without doing anything
(a) UIA `invoke()` — wx buttons do not execute it; (b) `click_input()` with the app in the background — the click lands on another window; (c) `click_input()` even when in the foreground — the Open button is only **15 pixels wide** (the preset combo takes that row). Use Tab navigation + verify focus via the NVDA bridge, then Enter. See `tools/e2e_full_verify.py:focus_and_activate`.

### 41. Raw NVDA bridge endpoints have NO `data` wrapper
Only the CLI adds it. `r.get("data", r)`, not `r["data"]`.

### 42. Local Whisper transcripts WERE nondeterministic (fixed v1.6.9)
Same file, same model (`base`), three runs through `get_transcript`: the first dialogue was reported at 30.0s, 30.0s, then 0.0s; coverage 40%, 32%, 93%. The cause was faster-whisper's temperature fallback, which SAMPLES randomly when the logprob threshold fails. **The gap budget (v1.6.8) is only as good as this transcript** — do not assume the reported gaps are certain.

**FAILED ATTEMPT, do not repeat:** `beam_size=5 + vad_filter=True` made it WORSE — coverage dropped to 20% and VAD discarded real speech (first dialogue reported at 40.0s, not 30.0s). Measured 22 Sep 2026. If you want to fix it, measure first; do not change settings because they "should be better".

### 43. The model KNOWS where the dialogue is, but does NOT know how much room there is
Checked: the transcript really is sent (921 characters, timestamped lines + instruction to use the gaps), and cue placement is actually good. What is missing is arithmetic — a 50s clip has ~77 words of room, the model wrote 97 then 99. `_gap_budget_block()` now lists each gap and the number of words that fit, scaled by the user's TTS speed. This is the pitfall 14 pattern: give numbers, not requests.

### 44. TEST ON GENUINELY DIFFERENT VIDEOS, not cuts from one video
The first benchmark took three pieces from ONE video and concluded the `small` model was the answer (0 hallucinations vs 32). On seven separate videos it REVERSED — `small` gave 12 hallucinations, `base` gave 2. Measuring one video three times is measuring one video. `tools/whisper_bench.py` has the correct set: Malay news, an English lecture, a music vlog, two Indonesian cartoons, an amateur recording, two TTS clips with known ground truth.

### 45. TWO kinds of Whisper hallucination, only one can be filtered
(a) Repetition loop — "Mememe..." for 27 seconds, compression_ratio 29.7; genuine lines 1.7-2.8. `_looks_hallucinated()` catches this.
(b) Music fantasy — 17 lines of KOREAN text on an English cooking vlog, compression_ratio 1.8-1.9, **indistinguishable** by ratio. Only VAD prevents it, by not sending music to the model at all. DO NOT turn off `vad_filter` thinking it is only an optimisation.

### 46. Screen-reader speech end = LISTEN to the sound, not ask the API
`core/audio_meter.py` reads the Windows peak meter on the screen reader process's audio session. Silence ≥0.6s = sentence finished. Measured in the real player with NVDA 2025.3: 5 words → video paused 1.43s, 26 words → 4.64s. Works on ALL NVDA versions because it asks nothing of NVDA.
**API path REJECTED, do not try again without measuring:** synchronous `speakSsml` (controller client v2, NVDA 2024.1+) HANGS on the first call in NVDA 2025.3 — a race fixed only in NVDA 2026.2 (nvaccess/nvda#20220), triggered by an ordinary keypress. `isSpeaking` exists only in NVDA 2026.3 (not yet stable). The controller client DLL is NOT needed for this feature.

### 47. Three meter mistakes, all found by measuring
(a) searching the DEFAULT device only → no NVDA session at all; here NVDA is routed to device 0, the Windows default is device 1. Search ALL devices.
(b) `tasklist` to find the process → 0.83s, longer than a 3-word sentence at the user's NVDA rate (~6 words/second). Use `QueryFullProcessImageNameW` (~0.03s total).
(c) finding the meter AFTER speaking → short sentences are missed. Set it up BEFORE `speak()`; `ReaderMeter.speak_and_wait(speak_fn, ...)`.

### 48. The copy of `nvdaControllerClient64.dll` in the project root is NOT signed
(API v1.0, 4 functions only). The official 2026.2 version is signed by NV Access Limited via GlobalSign. It is not used by any code; the owner placed it there on 23 Sep 2026.

### 49. Console windows appear ONLY in the frozen build
A `--windowed` exe has no console, so Windows gives EVERY child (ffmpeg, ffprobe, yt-dlp) a new console window that steals focus — NVDA says "terminal" and reads the ffmpeg path mid-job (real run, 28 Sep 2026, 15-minute video). From source, children share python.exe's console, so NO test ever saw it. `core/no_console.install()` (called early in `main.py`) makes `CREATE_NO_WINDOW` the default; `test_no_console` proves it with a `pythonw` parent. **Test the exe in `dist/`, not src.**

### 50. ALL `SettingsStore` instances in one process SHARE one state
(keyed by file path) since v1.7.4. Before that, the player created its own store and then wrote an old snapshot — a key just saved in Settings was lost. Saving is now atomic (tmp + `os.replace`); a corrupt file is set aside as `settings.json.corrupt-<time>`, NOT overwritten; a key blob that DPAPI cannot open is KEPT, not discarded. Do not bring back the XOR fallback on Windows.

### 51. API keys MUST NOT be in the URL
Gemini used to use `?key=`; an HTML 503 error page made `resp.json()` raise an error containing the full URL — the key went into the log AND was saved as a "description". Use the `x-goog-api-key` header; `_http_json` checks status before decoding and retries 429/5xx.

### 52. Sort frames by NUMBER, not text
`frame_%04d.jpg` past 9999 becomes `frame_10000.jpg`, which sorts between 1000 and 1001 — every frame after it gets the wrong time (10 fps, video >16:40).

### 53. `SetLabel()` on `wx.Slider` does NOT reach NVDA
Heard as "slider 0". Windows names a trackbar after the StaticText CREATED IMMEDIATELY before it. `tools/nvda_window_check.py --window player|editor|ask` checks windows other than the main window; wx dialogs sit UNDER their owner in the UIA tree, so they are found by Win32 handle.

### 54. Project folders are NAMED since v1.7.6: `Name (id)/project.db`
The old layout (`project_48.db` + `project_48/`) is migrated by `ProjectStore.migrate_layout()` when MainFrame opens. The DB stores ABSOLUTE paths of the video and frames — every folder rename MUST go through `_move_folder`, which rewrites those paths. **Do not build `project_{id}` paths yourself** — use `store.project_dir(id)` / `media_dir(id)` / `_db_path(id)`. A folder whose video is currently open cannot be renamed on Windows; the DB name still changes and the folder follows on the next open. `ODC_PROJECTS_DIR` isolates projects in tests (the gate used to leave 14 test projects in the owner's Documents).

### 55. Tests that LISTEN to NVDA are disturbed when NVDA reads another app
The meter hears ALL NVDA speech. Proven 28 Sep 2026 via the bridge: every `test_fixes26` failure happened while NVDA was reading the owner's game (up to 100 other utterances); every quiet run passed. The test now re-measures until quiet. DO NOT loosen its threshold to "fix" failures like this.

### 56. yt-dlp can be updated by the USER (v1.7.7), outside the bundle
`core/updater.py` installs to `%LOCALAPPDATA%\OmniDescriber\tools` only when the SHA-256 matches that release's `SHA2-256SUMS` AND `--version` equals the tag. `find_tool()` prefers that copy ONLY as long as its hash still matches `updates.json`; a modified file is ignored. The bundled copy is never overwritten (the build pin in `fetch_binaries.py` stays). The weekly check ONLY announces. Tests use `ODC_TOOLS_DIR`; do not let tests write to LOCALAPPDATA. `updater.status()` runs yt-dlp (1-3 s) — do not call it on the UI thread.

### 57. `wx.Menu.SetTitle` on a menu in the menubar BREAKS that menu on Windows
It writes the title INTO the dropdown, overwriting the first item. Since `_retranslate_menu` used it, File opened on "File" (Settings not reachable by keyboard) and Help on "Help". The wx item list STILL looks correct, so only NVDA / the real Win32 menu shows it (found 28 Sep 2026, v1.7.7). Use `menubar.SetMenuLabel(i, label)`. `test_fixes40` reads the NATIVE menu (GetMenuItemCount / GetMenuStringW), not the wx list.

### 57b. DO NOT recreate a control to change its style
The API key Show/Hide used to build a new TextCtrl to flip `TE_PASSWORD`: the new box fell into the panel's top-left corner (only the dialog was laid out, not the notebook page), so it was LAST in Tab order, and lost its NVDA label — the owner reported "api key input just disappears" (28 Sep 2026). The old test checked the VALUE only, so it passed. On Windows change the style on the SAME control (`EM_SETPASSWORDCHAR`). **UI tests must check position, Tab order and same object, not value only** (`test_fixes42`). Automation note: pywinauto `send_keys(" ")` DROPS spaces — use `{SPACE}`.

### 58. User languages live in `%APPDATA%\OmniDescriber\locales`
(v1.8.0), because the app's `locales/` folder is replaced on every update. New code file = new language; existing code file = line-by-line corrections (empty lines ignored). `*.missing.json` is a report, NOT a language. `ODC_LOCALES_DIR` isolates tests. **Every text the user sees/hears goes through `t()`** — `test_fixes43` fails on English text in the UI or unused keys (46 dead keys removed in v1.8.0). Adding a key = add to `en.json` AND `ms.json`.

### 59. Audio capability is per MODEL, not per provider (v1.8.1)
OpenRouter ("glm") used to be treated as deaf because GLM is deaf, so compressed video had its audio stripped even for Qwen3.8-Omni-Flash, which HEARS ("pineapple" probe, 28 Sep 2026). `provider_hears_audio(provider, model)`; `core/model_catalog.py` stores the filtered list (no `:batch` — 404, routers, aliases) and the results of **Test this model**, which OVERRIDE the catalog: Seed-2.0-mini is not listed as audio but hears; Nova-2-Lite is listed as video but answers "black, black". The catalog is a claim, the probe is proof. Compressed copies for deaf and hearing models have different cache names.

### 60. Keyboard automation ONLY through `tools/safe_keys.py`
On 29 Sep 2026 the Scene Explorer test failed to take focus and the keys (d, l, Enter) went into the owner's TeamTalk. `safe_keys` refuses to type unless the foreground window belongs to the test process (`allow(pid)`). Import it BEFORE `from pywinauto.keyboard import send_keys`. And: ASK the owner not to touch the PC first (memory ask-before-gui-automation).

### 61. Video length = ffprobe metadata, NOT `time=` from decoding
The `time=` value depends on the ffmpeg build: a 60 s clip with 9.25 s of audio measured 60 s with the bundled ffmpeg and 9.25 s with the PATH ffmpeg, so the v1.7.4 clamp discarded 22/23 cues. `tools.py` also looked for `bin/` one level too low (src/bin), so scripts outside the repo root silently used the PATH ffmpeg. `test_fixes46`.

### 62. "Hearing audio" is not "conveying dialogue"
Comparison 29 Sep 2026 (Sintel + Ocong, real app engine): with the `foreign` preset only GLM + transcript conveyed what was SAID; Qwen and Gemini (hearing) only described visuals. Gemini 3.8 Flash was the most detailed but often 503. New-user default = OpenRouter/GLM. Do not recommend a model "because it hears" without measuring real output.

### 63. YouTube sometimes returns a 403 that disappears on the second attempt
29 Sep 2026: yt-dlp failed with "HTTP Error 403: Forbidden"; the same command a second later downloaded all 888 s. `download_video` now retries 403 ONLY (3 times, partial file resumed), then `error.download_forbidden` tells the user to wait / update yt-dlp. Other errors (private video, etc.) are NOT retried. `test_fixes47`.

### 64. E2E speech checks must match APP TEXT, not keywords
NVDA reads all programs; the bridge does not say who is speaking. "Indonesian" (a TeamTalk notification) contains "done", so "completion was announced" PASSED on another program's speech. `e2e_full_verify` now matches the `status.processing_complete` prefix in each language, and checks cue coverage across the whole video (pitfall 61). Videos longer than one part are SPLIT, not compressed — there is no `upload_*.mp4` copy to keep in that case.

### 65. Changing text in the progress dialog is NOT read by NVDA
Focus stays on Cancel; screen readers do not read changes outside focus. The owner had to check manually (29 Sep 2026). Phase transitions are now spoken through Prism (`_announce_progress`, not `speech.announce()`, which is deliberately silent when a screen reader is present), `interrupt=False`, consecutive phases within 0.8 s merged. **New phase = add to `phase_keys`**; a phase without a key falls back to "AI is watching" (`encoding`/`parsing` used to do so).
**Write dialog text ONLY when it changes.** Heard in a 1.8.4 run: when focus was on the dialog itself, NVDA read the SAME text every second for 20 seconds because `Update(pct, line)` was called every tick. Use `Update(pct)` without text when nothing changed.

### 66. GLM upload = one ~40 MB JSON body; `json=payload` has no progress
`_chat(on_sent=...)` streams the body in 256 KB chunks with an explicit `Content-Length` (without it aiohttp uses chunked). Verified against real OpenRouter. Waiting for the model = estimate from `core/timing_store` (60 s overhead + per-second ratio, learned per model in `timing.json`); the bar never passes 95% of a part on a guess. A "seconds per second" ratio alone is wrong for short clips (50 s video = 80 s wait). `test_fixes48`.

### 67. faster-whisper gives `compression_ratio` per 30 s WINDOW, not per segment
One repeated line ("Bra, bra, bra, bra") raised the whole window to 2.79 and the filter discarded 8 real sentences — the Ocong transcript was EMPTY, so GLM had no dialogue at all (29 Sep 2026). `_looks_hallucinated` now computes the ratio from that segment's own text (Whisper formula). `test_fixes31`.

### 68. YouTube downloads pick AV1 + Opus by default
MiMo and Nemotron failed ("Failed to load video"); GLM/Qwen/Gemini work. `-S vcodec:h264,res,acodec:m4a` — H.264 at the same height. LOCAL AV1/HEVC files are still sent as-is (not yet converted).

### 69. Hearing models are NOT more accurate in this app
Measured on 7 models × 5 different clips (`doc/perbandingan-model.md`, `tools/model_bench.py`). The app gives a transcript to all of them; AD forbids describing audio; accuracy = vision. The catalog is also wrong: Gemini 2.5 Flash-Lite "hears" but hears nothing. `model_catalog.RECOMMENDED` (GLM 5.3 Flash, Gemini 3.1 Flash-Lite) is sorted first and read as "Recommended: ..." — change it ONLY with new measurements from `model_bench.py`, not because of the catalog.

### 70. Whisper segments are stretched to the next segment — gaps vanish
Tears of Steel: 58.5 s of "speech" in 60 s (29.0 s by words); the model was told there was no room and wrote ONE description per minute. `WHISPER_DECODE["word_timestamps"] = True` (same text, correct timing): GLM 12 → 30 descriptions, 0 wrong. `test_fixes49`.

### 71. OpenRouter routes one model to SEVERAL upstream servers, each with its own body limit
Google AI Studio 20 MB (every `google/*`); one GLM upstream 8 MiB even though a 29 MB part was accepted by another upstream — jobs failed RANDOMLY. `GLMProvider.BODY_LIMITS` + `body_limit_from_error()` learn the limit from a 413, then compress & resend that part. The limit is only LOWERED, and resets to the baseline for the next job (a limit set on the instance by a test is respected).

### 72. Upstream errors arrive INSIDE a 200 response
(`{"error": {"code": 504}}`). It used to be an immediate RuntimeError — a 504 after 15 minutes discarded all finished parts. 429/5xx codes in the body are now retried.

### 73. Part length = accuracy
The ruler (`model_bench.py measure`) on TWO long films: 10-minute parts 24.5% / 27.5% wrong descriptions (right event, wrong time; + an 85 s hole at the end of the part), 5-minute parts 12.9% / 11.8%, and faster. Default is now 300 s; a one-time migration (`settings_store._migrate`, marker `migrated`) changes a stored 600 to 300 — the user's choice after that is not touched.

### 74. Frame mode (the new-user DEFAULT) is not suitable for films
Every frame that passed dedup was saved as a 1 s description: 147–204 descriptions PER MINUTE for Sintel/news/Tears, with markdown junk ("**Audio description**", "[0:00]") read by TTS; GLM ~20 s per frame (60 s clip > 10 minutes). Only static content (slides, Excel: 31) was reasonable. **Decided by the owner 30 Sep 2026:** new-user default = full video (`ai.video_mode: "full"`; stored mode not touched), and frame mode is now spaced (`general.min_description_gap` 4 s, `VideoProcessor.space_frames`) and cleaned (`finalize_frame_descriptions`): Tears 60 s 204 → 15 descriptions, 0 markdown. Markdown headings (`## Scene`) are removed as a WHOLE LINE, not just the `#` — otherwise TTS reads "Scene A girl...". `test_fixes50`. The old frame-pipeline tests (9, 11) set the gap to 0.

### 75. Yes/No boxes have a Cancel button so Esc works (v1.8.7)
Windows DISABLES Esc in a MessageBox without Cancel. `ask_yes_no` uses YES_NO|CANCEL (Cancel = No); the box stays native so NVDA reads the full question. Do not switch to a home-made dialog without listening with NVDA.

### 76. Local non-H.264 files are re-encoded before upload (v1.8.7)
Only the "small single-part file" path used to send the original file; splitting and compression already produce H.264. `_video_codec` + `_SAFE_CODECS`. `test_fixes51` uses real AV1/HEVC clips from the bundled ffmpeg.

### 77. The user's chosen model NEVER reached the provider before v1.8.8
`set_provider()` only logged the model (except "custom"), and `describe_video_full`/`describe_frame` were called with `model=""`, so the provider used `models[0]` — choosing Gemini 3.1 Flash-Lite still ran GLM. The bench was not affected (it passes the model explicitly). `AIEngine._models` + `_model_for()`; every engine method fills in the model. `test_fixes52` fails on the old code.

### 78. Description review (`core/review.py`, v1.8.8) follows measurement 16.3 (checklist phase 16)
Frames are extracted ONCE every 3.64 s (not 12 seeks per description). **Tile labels MUST be the actual frame time** — labels with the REQUESTED time were off by ±1.8 s and the model moved 27 descriptions for no reason (first real run). `BACK = 1.5`: the closest tile in the measurement was 1.8 s, so smaller shifts were never measured. Default mode is OFF (owner). A failed review keeps the original descriptions; it never discards work. Frame mode is not reviewed.

### 79. Player agent (`core/agent.py`, `ui/agent_dialog.py`, v1.9.0)
Measured first (`tools/agent_bench.py`): all 4 models make real tool calls. Rules ENFORCED by the engine, not hoped for from the model: a proposal before looking at a frame is REJECTED; at the turn limit the model is FORCED to answer without tools (Gemini 3.8 once went silent); cost limit $0.02 → ask "continue?". The agent has NO writing tool — only `propose_change`; the Player applies ACCEPTED proposals (`apply_agent_changes`), copies the SRT once per session, Undo. The instruction "only if CLEARLY wrong" stopped 3 models from rewriting correct descriptions. Images to the model are sent as a user message after the tool message. Dynamic i18n keys must be written literally inside `t(f"...")` so `test_fixes43` sees them as used.

### 80. The AI engine was only configured during processing before v1.9.0
Ask More / Explore Scene on a reopened project failed with "No AI provider configured". `MainFrame.configure_ai()` is now called at startup, after Settings, and during processing.

### 81. Temperature 0 for OpenRouter full video (`GLMProvider.TEMPERATURE`, v1.9.1)
Measured: correct 51 → 83, wrong 24.2% → 16.8% (Gemini judge), run-to-run difference halved. Direct Gemini not yet measured — do not copy the setting there without measuring. Snapping to scene changes was TESTED and REJECTED (no clear improvement; `model_bench.py snap`).

### 82. "Check whole video" (`Agent.check_all`)
Starts a NEW conversation for every 60 s of video (the user's session is restored afterwards), one proposal list, one proposal per description. An `edit` with the same text is REJECTED (heard in the first real run).

### 83. "Test this model" for all providers (v1.9.2)
Through the app's own engine (`model_catalog.probe_engine`): video providers (Gemini, MiniMax) get the same 6 s clip through the real upload path (`ask_about_video`); image providers (OpenAI, Custom) get one red frame. The Test Connection button was REMOVED (it only asked for "OK"). Temperature 0 also for direct Gemini full video: measured NOT more accurate (wrong 14.7% → 14.2%) but more stable (run difference 23 → 12); owner's decision.

### 84. Agent for direct Gemini
Uses Google's OpenAI-compatible endpoint (`agent.GEMINI_URL`), without OpenRouter-specific fields (`usage`, `reasoning`). Google does NOT return cost: `_cost` computes it from tokens × the OpenRouter catalog price (`google/<model>`), or `FALLBACK_PRICE`, which is deliberately high so the $0.02 limit stops early, not late. Free Gemini keys quickly hit a 429 quota — that is not a bug.

### 85. The Gemini model list is fetched from Google
(v1.9.3, `model_catalog.fetch_gemini_models`, cache `gemini_models.json`). Google has no "accepts video" field: filter = `gemini-*`, `generateContent`, context >= 1 million tokens, exclude tts/image/live/robotics/customtools/"latest". On 1 Oct 2026: 61 → 12. If Google names new models differently, check the filter against the real list, not guesses. The built-in list (`PROVIDER_MODELS`) remains as a fallback before the first Fetch.

### 86. Thinking level is set PER MODEL, only for those measured
(v1.9.4, phase 22). Models differ: Gemini 3.1 Flash-Lite does not think by default, 3.8 Flash thinks and REJECTS "minimal" (HTTP 400); GLM's thinking cannot be turned off. `GeminiProvider.THINKING_BY_MODEL` (3.1 Flash-Lite: medium, wrong 15.8% → 9.1%) and `agent.AGENT_REASONING` (GLM: effort low, 8/16 → 11/16 correct answers). A rejected level is retried WITHOUT thinking — work is not lost. `max` for GLM video was TESTED and REJECTED (19 minutes for a 1-minute clip, one empty answer). Do not copy levels to other models without measuring (`model_bench.py @think<level>`, `tools/agent_levels.py`).

### 87. Google 429: read `quotaId`, not just `retryDelay` (v1.9.5)
The daily limit (`...PerDay...FreeTier`) STILL says "retry in 53s" — waiting does not help; `daily_quota()` fails immediately with a clear message. Per-minute limit: wait as long as requested (`retryDelay` / `Retry-After`, maximum 65 s), not 5 s then 15 s. The tier is per key PROJECT; a top-up on a billing account not linked to the key's project has no effect. Bench: `model_bench._prepare_config` re-copies settings when the real settings are newer (a stale copy once used an old key). The Gemini 3.8 Flash agent is WEAK (0/4 corrections, kept looking until the cost limit); 3.1 Flash-Lite 4/4 — see `doc/perbandingan-model.md`.

### 88. A test run on its own wrote the owner's REAL settings (v1.9.6)
Thirteen test scripts relied on `run_gate.bat` to set `ODC_CONFIG_DIR`. Run
directly (by an agent), one wrote a loopback Gemini URL
(`http://127.0.0.1:12144/v1beta`) into the owner's settings.json, and every
Gemini job failed with "Cannot connect to host 127.0.0.1" until it was found in
the owner's log. Every test now imports `tests/isolate.py` FIRST (config,
projects, locales and tools in temp folders); `test_fixes58` fails the gate if
one does not. GUI E2E tools run the app in a sandbox copy of the settings.

### 89. Progress-dialog Cancel was only noticed during the DOWNLOAD (v1.9.6)
wx latches Cancel and reports it only through the bool returned by
`Update()`/`Pulse()` (or `WasCancelled()`). Only the download/frame/AI ticks
looked at it; every later phase threw it away, so for a local or already
downloaded video Cancel did nothing for the whole job (owner: "many Cancel
buttons don't work"). Every Update/Pulse goes through `_dialog_ok`, and the 1 s
heartbeat checks `WasCancelled()` first. A long blocking step must ALSO poll
the flag (Whisper per segment, subtitles, uploads via `_run_cancellable`).

### 90. `wx.CallAfter` to a window that is gone crashes (v1.9.6)
Closing the main window during a job: the worker kept posting
`SetStatusText`/`_processing_done`, "wrapped C/C++ object ... has been
deleted". Worker calls go through `MainFrame._ui()`, which checks `bool(self)`
and `IsBeingDeleted()` when the call RUNS; handlers start with
`if not self: return`. Same pattern in the Player, Settings, Ask More, Scene
Explorer and agent dialog.

### 91. A wx name that does not exist passes every test that mocks the dialog
`wx.EVT_DOUBLECLICK` (it is `EVT_LISTBOX_DCLICK`) crashed File > Open Project
on every use from 1.7.6 to 1.9.5; the handler test replaced the dialog, so the
line never ran. `test_fixes58` checks every `wx.<Name>` in `src` against the
installed wxPython.

### 92. The Player's clock without VLC is the REAL clock (v1.9.6)
Simulated playback (ffplay sound) added 0.5 s per timer tick. A wx timer fires
late whenever the UI is busy, so the position fell behind the sound and the
agent could get an old time. The position now adds the monotonic time that
passed; `_start_timer()` and `_start_ffplay()` reset the clock. The timeline
slider is in SECONDS and its accessible value is "1:04 of 24:30"
(`_TimeSliderAccessible`); verify by listening, not by the value. A project with no recorded length ("Play Video with Existing
Descriptions") is measured with ffprobe when the Player opens (`_ensure_duration`).

### 93. Progress is ONE real progress bar for the whole job (v1.9.6)
The progress dialog was `wx.ProgressDialog` (a DirectUI bar NVDA may not report,
see pitfall 3), most phases had no percentage, and the heartbeat rewrote
"Working: <phase> (46s)" every second, so NVDA read only "46s" (owner, 2 Oct
2026). The owner chose a progress bar over spoken reports. Now
`ui/progress_dialog.AccessibleProgressDialog` holds a real `wx.Gauge`
(msctls_progress32, labelled by the StaticText created before it), and
`MainFrame.STAGES` maps every step onto ONE overall percentage that never
goes back: download 0-15, transcript/extraction 15-30 (Whisper reports
segment end / duration), AI 30-95 (Gemini/MiniMax "processing" advances by
time from `timing_store`, easing out, never reaching the stage end), check
95-99; 100 is never sent. Every tick goes through `_advance(stage,
fraction)`. Phase changes are still announced once (pitfall 65); there is no
periodic speech. A new step that knows its progress calls `_advance`.

### 94. `wx.Yield()` does not fire wx timers without a running event loop
`wx.ProgressDialog` ran its own loop and hid this: tests that pumped with
`wx.Yield()` saw heartbeat timers fire. With a modeless dialog they do not;
`test_fixes48`'s `pump()` runs a real `wx.GUIEventLoop`. Use one when a test
depends on a `wx.Timer` or `wx.CallLater`.


### 95. Keys in a focusable area: `_announce` moves the focus
`PlayerWindow._announce` moves the focus to the status line so NVDA reads
it. The 1.9.7 video-area keys used it, so after the first key the focus sat
on `player_status` and the next arrow went to another control; the owner
heard "focus moves, volume changes only sometimes". While the video picture
has the focus, `_announce` now speaks through Prism (`_say_in_video_area`)
and leaves the focus where it is. Any new keyboard area must do the same.
Also: ffplay takes the volume and start point only when it starts, so
volume/seek keys restart it ONCE, 0.35 s after the last key
(`_restart_sound_soon`). Found only by the real test
`tools/nvda_video_keys_check.py`; a unit test that calls the handler
cannot see it.

### 96. Global key automation can type into another program
On 2 Oct 2026 a diagnostic sent arrows and spaces with `send_keys` while the
foreground check passed; they landed in the Claude app. `safe_keys` now also
checks the keyboard-focus control (`GetGUIThreadInfo`). Prefer posting
WM_KEYDOWN/WM_KEYUP to the app's own HWND (`nvda_video_keys_check.py`); it
can never reach another program.

### 97. Posted keys: set the extended bit, and CHAR_HOOK does not see them
`PostMessage(WM_KEYDOWN)` for an arrow without bit 24 of lParam arrives as a
number-pad arrow (`WXK_NUMPAD_DOWN`). wx's `EVT_CHAR_HOOK` is not raised for
posted keys at all, so the video panel also binds `EVT_KEY_DOWN` (a key
handled in CHAR_HOOK never reaches it, so nothing runs twice).
The same panel swallowed F2 (the Player's only shortcut). F2 is now a
window accelerator (`SetAcceleratorTable`), translated before any control
sees the key; posted keys are translated too, so it can be tested. When F2
opens Ask More instead of the agent, the reason is spoken 0.9 s later
(`_speak_queued`): a focus-move announcement is lost when a dialog takes
the focus at once.
