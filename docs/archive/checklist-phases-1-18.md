# Checklist archive (phases 1–18)

Moved from `senarai-semak-v1.7.5.md` (later the live checklist, now `docs/checklist.md`) on
30 Sep 2026 without changes; translated to English on 5 Oct 2026. Open items were copied to
the "Still open" section of the live checklist.

## Phase 1 — owner (not an agent)
- [x] Delete `%APPDATA%\OmniDescriber\settings.json.v1.5.2.bak` (4 XOR keys) — permanently deleted on the
  owner's instruction 28 Sep; the Gemini/GLM keys in settings.json (DPAPI) confirmed still read
- [ ] Replace the Gemini, OpenRouter, custom and Opus keys if still live (OWNER — in each provider's dashboard)

## Phase 2 — verify 1.7.4
- [x] 2.1 `tools/nvda_accessibility_check.py` — main window (build 1.7.4: 20/20 OK)
- [x] 2.2 NVDA check — editor, player, Ask More (new tool `tools/nvda_window_check.py`;
  FIXED: the player slider was read "slider 0" with no name, the video panel was read "video_area";
  now 16/16 OK in every window; gate GATE_ALL_PASS)
- [x] 2.3 A real long-video E2E with GLM (Sintel 14:48, 2 parts): 121 cues,
  completion announced, SRT written, the log confirms cues past a part's end are clamped.
  The E2E tool's "upload copy" check fixed (only for files >50 MB).
  FOUND: 5/121 cues >20 words (GLM model, pitfall 14) — see 4.7.
- [x] 2.4 Editor/player by keyboard: edit → move (Down) → close the player →
  DB: `(5.0, 'EDITED ONE BY KEYBOARD')` — PASS. Small note: the list still read the old
  text until the user moved (see 4.8).

## Phase 3 — tidy
- [x] 3.1 AGENTS.md: 42→47 suites, Current Status rewritten, pitfalls 49–53
- [x] 3.2 Deleted the 1.7.2 and 1.7.3 zips (~890 MB; can be rebuilt from the tags)
- [x] 3.3 `.audit_scan.sh` — deleted (owner's decision; the 1.7.4 audit covers it)

## Phase 4 — bugs + build → 1.7.5
- [x] 4.1 GLM Cancel during a long request — `_run_cancellable`, <1 s (test_fixes38)
- [x] 4.2 Batch mode: one failure → the others are cancelled (test_fixes38)
- [x] 4.3 Part bitrate follows the part length — Sintel 179 → ~350 kbps (test_fixes38)
- [x] 4.4 Removed `torch` + `coverage` — Whisper transcribed Sintel into 12 segments with torch blocked;
  test_packaging_content rejects a build that carries them
- [x] 4.5 Pinned ffmpeg autobuild-2026-09-21-13-55 + yt-dlp 2026.08.19; the official hashes match
  bin/ (10/10 + 1); a changed file → exit code 1, the build stops
- [x] 4.6 Build 1.7.5 BUILD_ALL_OK (zip 446 → 319 MB, no torch); gate 48 suites x2
  GATE_ALL_PASS; frozen Sintel/Gemini E2E 14/15 — the only 'failure' is cue length
  (decision 4.7: leave it), now reported as a note; Whisper in the exe: 15 segments
- [x] 4.8 Editor: the list label is updated while typing — NVDA reads the new text
  (`tools/e2e_editor_flow.py`)
- [x] 4.7 Cues >20 words — owner's decision: LEAVE (the narration pause handles them)

## Phase 5 — new features (ask the owner first)
- [ ] 5.1 Speech profiles — POSTPONED by the owner (28 Sep 2026)

## Phase 6 — friendly project names (v1.7.6, owner's request 28 Sep 2026)
- [x] 6.0 Deleted 14 test projects (confirmed by the owner): 1–10, 32–35 — 27 projects left
- [x] 6.1 The gate uses a temporary `ODC_PROJECTS_DIR`; confirmed: the real folder does not change during the gate
- [x] 6.2 Folders named `Name (id)/project.db`; tested on a copy first, then the real
      projects: 27/27 moved, 0 broken video paths (DB backup in %TEMP%)
- [x] 6.3 Open Project list: "sintel — 79 descriptions — 28/09/2026 11:30" (heard through NVDA)
- [x] 6.4 Rename button (Alt+N, Malay/English, NVDA says "Rename button Alt+ n"); handler tested
      in test_fixes39; the Malay Alt+B clash between Open/Remove fixed (Remove = Alt+A)
- [x] 6.5 17 projects named by URL → their real titles (`tools/fix_project_names.py`)
- [x] 6.7 FOUND during the gate: SAPI `speak_and_wait` lost a start-up race (~1/10)
      — the video could resume over a description; fixed. The NVDA failure in test_fixes26 was proven
      to come from NVDA reading another app; the test now re-measures until quiet
- [x] 6.6 Build 1.7.6 BUILD_ALL_OK; frozen E2E 14/14 (folder `Sintel dialog clip (49)`);
      Open Project dialog heard by NVDA; gate 49 suites x2 GATE_ALL_PASS while NVDA was quiet
- [x] 6.8 Second clean-up (confirmed by the owner): 25 test projects deleted (sintel ×4, zoo ×17,
      video ×2, failed attempts 11 & 26). Left: 27 and 31 (Ocong). 1.1 GB → 361 MB
- [x] 6.9 NVDA bridge tool checked: speech history (100 items: time/text/priority) and the
      `speech`/`foreground` events — NO "speech finished" event, so the audio meter stays the only
      way to measure the end of speech; tests filter their own speech by text
- [x] 6.10 Projects 27 and 31 (Ocong) sent to the Recycle Bin on the owner's instruction — the projects folder
      is now empty. test_fixes16 skips the long-video check (SKIP, not FAIL): 16/16 pass

## Phase 7 — Check for Updates in the app (v1.7.7, agreed by the owner 28 Sep 2026)
- [x] 7.1 `core/updater.py`: checks GitHub, downloads, verifies the official SHA-256 + version, installs outside the bundle
- [x] 7.2 `find_tool` uses an update only while its hash matches; "Use the original version" goes back
- [x] 7.3 Help > Check for Updates (Malay/English, NVDA: "Check again button Alt+c", the result read automatically)
- [x] 7.4 A weekly check while the app is open — announces only
- [x] 7.5 A hint in the log when a YouTube download fails
- [x] 7.6 test_fixes40 7/7 (a real yt-dlp file, no network); a real GitHub test: check,
      download, fingerprint, test, use, revert — all succeeded (in a temporary folder)
- [x] 7.8 FOUND by listening to the exe: the File menu opened on "File" (Settings unreachable
      by keyboard) and Help on "Help" — `Menu.SetTitle` overwrote the first item on Windows.
      Fixed with `SetMenuLabel`; a native menu test fails without the fix, passes with it
- [x] 7.7 Gate 50 suites x2 GATE_ALL_PASS; build 1.7.7 BUILD_ALL_OK; exe heard through NVDA:
      File → "Settings... s", Help → "Check for Updates... u" → the dialog opens and is read

## Phase 8 — small improvements (owner's request 28 Sep 2026)
- [x] 8.1 test_fixes16: the long-video check uses a self-generated 10-minute test video,
      not the owner's project — the 4 skipped checks now pass (20/20)
- [x] 8.2 The E2E tools delete ONLY the projects their own run created (`tools/e2e_projects.py`);
      a real run of exe 1.7.7 + Gemini: 14/14, project 50 removed, the owner's folder unchanged
- [x] 8.3 FOUND: `e2e_gui_phase` and `e2e_gui_v130` still looked for `*.db` (broken since the 1.7.6
      layout) — fixed; `e2e_gui_v130` also checked "project_" in the path
- [x] 8.4 Preset names: the language prefixes come from the locale files, not ("en_", "ms_");
      test_fixes41 fails on the old code (an `id_` preset in the English list), passes now
- [x] 8.5 Gate 51 suites x2 GATE_ALL_PASS
- [x] 8.7 Build 1.7.8 BUILD_ALL_OK; exe heard by NVDA 10/10; real E2E 14/14, test
      project 51 removed by itself; tag v1.7.8
- [ ] 8.6 (not done — owner's choice) ffmpeg in the Check for Updates menu

## Phase 9 — bug reported by the owner (v1.7.9)
- [x] 9.1 The API key box vanished after Show/Hide: rebuilt at (0,0), last in Tab order,
      with no NVDA label. Fixed with EM_SETPASSWORDCHAR on the same control.
      Heard by NVDA: Show → "API Key: edit selected TESTKEY 123", Hide → "edit protected".
      test_fixes42 fails on the old code; gate 52 suites x2 GATE_ALL_PASS
- [x] 9.2 Build 1.7.9 BUILD_ALL_OK; the same flow heard in the frozen exe — same as
      from source; tag v1.7.9

## Phase 10 — multilingual (v1.8.0, agreed by the owner 28 Sep 2026)
- [x] 10.0 Check: EN=MS 366 keys; switching language while running 33/33 controls right
- [x] 10.1 ~15 fixed English texts now go through t() (start-up warnings, error log, About,
      file-type filters NVDA reads)
- [x] 10.2 46 dead keys removed (388 → 342); a test fails if a key is unused
- [x] 10.3 User language folder `%APPDATA%\OmniDescriber\locales` (kept across updates;
      line-by-line corrections)
- [x] 10.4 Help > Translation Report: `<code>.missing.json` with the English text; heard by NVDA
      in Malay: "Bahasa Melayu: semua baris sudah diterjemah"
- [x] 10.5 The adding-a-language guide for exe users; user guides updated
- [x] 10.6 test_fixes43 7/7; on the old code 5/7 failed
- [x] 10.7 Gate 53 suites x2 GATE_ALL_PASS (NVDA quiet); build 1.8.0 BUILD_ALL_OK; Translation
      Report heard in the exe in Malay; tag v1.8.0
- [x] 10.8 (note) The Yes/No buttons in message boxes followed the Windows language, not the app language — done in v1.8.2 (12.6)

## Phase 11 — reliable OpenRouter models + audio per model (v1.8.1)
- [x] 11.1 Research: 4 OpenRouter models hear a video's audio (Qwen3.8-Omni-Flash, MiMo-v2.6-Flash,
      MiMo-v2.5, Nemotron free) — the "pineapple" probe
- [x] 11.2 Fetch models: 85 → 65 (13 :batch, 3 routers, 4 aliases removed); audio first, prices;
      NVDA labels; saved
- [x] 11.3 Test this model: a 6 s clip with colours + a word; heard by NVDA "watches the video and hears
      its sound"; caught Nova ("black, black"); the result overrides the catalog (Seed-2.0-mini)
- [x] 11.4 Audio per model: the compressed copy keeps audio for models that hear (ffprobe);
      the foreign preset warning follows the model; Qwen + MiMo in the default list
- [x] 11.5 test_fixes44 7/7; the old code failed 3 (including "sent a silent video")
- [x] 11.6 Gate 54 x2; build 1.8.1 BUILD_ALL_OK; exe E2E + Qwen via OpenRouter 14/14 (Sintel dialogue clip
      30 s: 1 cue — Qwen and GLM both wrote 1 line; the parser takes them all; the preset
      does not talk over dialogue); Test this model heard by NVDA; tag v1.8.1

## Phase 12 — D/E/F/G (agreed by the owner 29 Sep 2026)
- [x] 12.0 INCIDENT: the Scene Explorer test failed to take focus; keys (arrows, d, l, Enter)
      went to the owner's TeamTalk ("chat together") — a short message may have been sent. Fixed:
      `tools/safe_keys.py` refuses to type unless the foreground window belongs to the test process (confirmed:
      refuses while TeamTalk is in front). Every automation tool uses this guard.
- [x] 12.1 Added `explorer` and `settings` modes to tools/nvda_window_check.py
- [x] 12.2 Settings, General tab: 13/13 controls read by NVDA
- [x] 12.3 Keyboard + NVDA sweep: 7 problems (Esc in the editor/Ask More, a silent 10s, Scene Explorer
      silent/unlabelled, the speed slider read '10', an empty provider for new users), all fixed;
      test_fixes45 passes 0/4 on the old code
- [x] 12.4 E: Sintel + Ocong through the app's engine: GLM + transcript is the only one that conveys dialogue
      (foreign); Gemini 3.8 the most detailed but 503; Qwen too few. Default: OpenRouter/GLM.
      FOUND: video length followed a short audio track (22/23 cues lost) + bin/ at the wrong level, fixed
      (test_fixes46); a 503 now waits 5 s/15 s with a clear message
- [x] 12.5 F: a real custom provider: OpenAI format, auto, Anthropic (Claude Haiku), ask_text passes
- [x] 12.6 G: Yes/No follow the app language (ui/dialogs.ask_yes_no); the player retranslate()
- [x] 12.7 Heard again (EN + MS): arrows/L/D/Tab in Scene Explorer, 10s, Esc, slider 'Kelajuan',
      'Tidak button Alt+T'; gate 56 x2; build 1.8.2; exe: provider OpenRouter, slider Kelajuan; tag.
      FOUND while listening: Tab trapped in the Description box (fixed); letters from
      pywinauto sent as VK_PACKET (a test artefact; use vk_packet=False for letters)
- [x] 12.8 Esc in Yes/No boxes: a Cancel button added (Esc/Cancel = No), v1.8.7 — Windows default
      without a Cancel button; Alt+T picks No

## Phase 13 — long video on the exe (agreed by the owner 29 Sep 2026)
- [x] 13.1 Sintel 888 s on exe 1.8.2: 169 cues, 2 parts. E2E tool: emoji crash (cp1252 log),
      "completion announced" a FALSE PASS (TeamTalk's "Indonesian" contains "done"), no coverage check,
      wrong expectation of a compressed copy for a split video — all fixed (pitfall 64)
- [x] 13.2 YouTube 403 not retried, a raw English error — fixed in v1.8.3 (test_fixes47, pitfall 63)
- [x] 13.3 Gate 57 x2 GATE_ALL_PASS; build 1.8.3 BUILD_ALL_OK; exe E2E 1.8.3 15/15: 81 cues, last cue
      846 s / 888 s, widest gap 82 s, NVDA says "Processing complete! 81 descriptions generated."

## Phase 14 — upload progress + NVDA (reported by the owner 29 Sep 2026, v1.8.4)
- [x] 14.1 The bar sat at 0% during a GLM upload: the body is streamed with a byte count; the wait for the model is estimated
      (core/timing_store: 60 s + a learned ratio); time left shown
- [x] 14.2 Phase changes not read by NVDA: spoken through Prism, without interrupting
- [x] 14.3 "part 1 of 2, 55%" before anything was sent — now 10%
- [x] 14.4 Gate 58 x2; build 1.8.4; exe E2E 16/16: NVDA said "About 8 min left" at 15:29,
      the job finished at 15:37 (an accurate estimate); 98 cues, coverage 882/888 s
- [x] 14.5 FOUND while listening: focus on the dialog -> NVDA repeated the same text every second for 20 s.
      Fixed (text only when it changes); test_fixes48 catches it
- [x] 14.6 Gate 58 x2; build 1.8.4; E2E 50 s clip 17/17: every phase said ONCE (transcript, compress, upload, "About 1 min left", reading the answer, done)

## Phase 15 — model comparison (owner's request 29 Sep 2026, v1.8.5)
- [x] 15.1 tools/model_bench.py: 5 different clips + a truth clip; 7 models x 2 runs; $0.26
- [x] 15.2 Results: docs/model-comparison.md — hearing is not more accurate; GLM & Gemini 3.1 Flash-Lite best
- [x] 15.3 The Ocong transcript was empty (ratio per window) — fixed, test_fixes31
- [x] 15.4 YouTube AV1 could not be opened by MiMo/Nemotron — prefer H.264, test_fixes47
- [x] 15.5 Gate 58 x2 GATE_ALL_PASS; build 1.8.5 (test_fixes14 updated for the "Recommended:" label)
- [x] 15.6 Local AV1/HEVC/VP9 files re-encoded to H.264 (v1.8.7, test_fixes51 with a real clip)
- [ ] 15.7 (OWNER) Gemini key refused by Google — replace in Settings
- [x] 15.8 Owner: GLM stays default; GLM + Gemini 3.1 Flash-Lite listed first, read "Recommended: ..." (test_fixes44)


## Phase 16 — accuracy and reliability of descriptions (SAVED, waiting for the owner — 29 Sep 2026)
The owner: dialogue matters less; what matters is that the video is described ACCURATELY and reliably.
Genres the owner describes: drama/film, cartoon/animation, news/documentary, tutorial/lecture (all four).
Measures: correct (matches the frame), timing, invented, missed, consistent between runs (169 vs 81).
- [x] 16.1 Phase 1 — the ruler is ready (`model_bench.py judge|measure`): a GLM judge calibrated on 99 hand
      labels + 30 blind labels (0/83 false accusations, 13/14 wrong caught); GLM 8% wrong (Gemini judge 13.8%).
      Results in docs/model-comparison.md. Total cost of the phase ~$0.40
- [x] 16.2 Phase 2 — a wider baseline (docs/model-comparison.md): short genres GLM 0 wrong; long
      videos 24.5%/27.5% wrong with 10-minute parts → 12.9%/11.8% with 5 minutes (default now 300 s,
      v1.8.6). FOUND AND FIXED: lost Whisper gaps (word_timestamps), OpenRouter upstream body limits
      (Google 20 MB, GLM 8 MiB), a 504 inside a 200 response. Frame mode: 147-204 descriptions/min
- [x] 16.2b Owner (30 Sep): full-video default; frame mode spaced 4 s + cleaned up.
      A real GLM run, Tears 60 s: 204 → 15 descriptions, 0 markdown (test_fixes50)
- [x] 16.3 Phase 3 — fixes (see 18.1), keep only what raises the numbers: a second review pass (fix/drop/
      move the time), snap to scene changes (ffmpeg scene), fixed temperature for consistency,
      check long gaps for missed events
- [x] 16.4 Phase 4 — the "Check descriptions" setting (see 18.1c), NVDA, documents, gate
Estimate: phases 1-2 ~$0.50-1; a review pass +20-40% cost/time per video (to be measured).

## Phase 17 — release 1.8.6 (continued 30 Sep 2026)
- [x] 17.1 The first gate FAILED 4 suites (1.8.6 work + frame mode mixed, not finished): the frame pipeline
      test set spacing 0; test_fixes23 cut code at a top-level `class`; test_fixes34 tested
      behaviour. FOUND: markdown headings joined to sentences ("Scene A girl...") — fixed
- [x] 17.2 test_fixes50 (frame mode) 5/5; a real GLM run on Tears 60 s: 204 → 15 descriptions
- [x] 17.3 Gate 60 suites x2 GATE_ALL_PASS; a clean 1.8.6 build (1.8.7 work stashed during the build);
      exe heard by NVDA 12/12; tag v1.8.6
- [x] 17.4 Gate 61 suites x2 GATE_ALL_PASS; build 1.8.7; exe NVDA 10/10; Yes/No box (Malay) heard:
      "Sahkan dialog Padam penerangan ini?" → "Tidak button Alt+T", Batal, Ya; Esc → No; tag v1.8.7

## Phase 18 — next (owner's order 30 Sep 2026)
- [x] 18.1 Accuracy plan phase 3 (16.3): the review pass measured (docs/model-comparison.md) —
      independent Gemini judge: wrong 39/209 → 23–27 depending on the option; cost ~$0.014/film
- [x] 18.1b FOUND: the user's chosen model was never used (GLM/Gemini/MiniMax) — fixed in v1.8.8
- [x] 18.1c Phase 4 (16.4): Settings "Check descriptions" OFF by default; Auto/Most accurate/Most descriptions/
      Keep all (owner's choice); the app module tested for real on Tears: wrong 15 → 7
      (Gemini judge), +227 s; test_fixes52 9/9
- [x] 18.1d Gate 62 suites x2 GATE_ALL_PASS; NVDA Settings: "Check descriptions against the video
      (full-video mode): combo box Off collapsed"; build 1.8.8; exe NVDA 10/10; tag v1.8.8
- [ ] 18.1e (not done — OpenRouter credit nearly gone) fixed temperature, snap to scene changes
- [x] 18.2 Agent mode — Phase A: 4 models pass the protocol (tools/agent_bench.py, $0.063)
- [x] 18.2b Phase B: core/agent.py (13 tools, look-first enforced, forced answer, cost cap) — test_fixes53
- [x] 18.2c Phase C: Ask More sends the frame; FOUND AND FIXED: the AI engine was not configured for
      a reopened project ("No AI provider configured")
- [x] 18.2d Phase D: F2/Agent button, pause/resume, Accept all/Review/Reject, SRT copy, Undo,
      Test agent mode — test_fixes54; a real GLM session (Malay, remembers "Hans", transcript) $0.0014
- [x] 18.2e Phase E: heard by NVDA (tools/nvda_agent_check.py): F2 → steps spoken → answer →
      summary → "Accept all button Alt+A" → Esc "No changes made". FOUND while listening:
      the transcript failed inside the agent loop ("Cannot run the event loop...") — fixed + test;
      "1 changes proposed" → "Changes proposed: 1". Gate 64 suites x2 GATE_ALL_PASS
- [x] 18.2f Build 1.9.0 BUILD_ALL_OK (core.agent + ui.agent_dialog in the exe); exe NVDA 10/10; tag v1.9.0
