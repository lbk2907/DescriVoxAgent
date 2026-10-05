# Full session summary — audit + fixes + release v1.5.4

Date: 8 September 2026
Project: Omni Describer Custom (now DescriVox Agent)
Final state: v1.5.4 RELEASED (commit `c8a9916`, tag `v1.5.4`,
zip `dist/OmniDescriber-1.5.4-win64.zip`, gate 28/28 PASS, no open bugs).

*Translated to English on 5 Oct 2026; the content is unchanged.*

---

## 1. Phase 1: full project check

Request: check the WHOLE project with 3-5 sub-agents.

Five audit agents ran in parallel:

1. **gate-runner** — ran `run_gate.bat` in the foreground.
   Result: **GATE_ALL_PASS, 27/27 suites, 4 min 18 s.** Confirmed independently
   (27 gate_*.txt evidence files in TEMP). Note: `test_build_smoke.py` is not
   in the gate (it runs in build.bat phase 3 — not a coverage hole).
2. **security-auditor** — scan for secrets, encryption, dangerous patterns.
   Result: no real secrets, no command injection. Main findings:
   API keys only XOR-obfuscated with a hard-coded key (MEDIUM); the Gemini key
   in the URL (LOW-MEDIUM); yt-dlp without scheme validation; .gitignore
   without key entries. Positives: 0 eval/exec/shell=True in 81 files; all 37
   subprocess sites use list argv; Opus truly removed.
3. **docs-i18n-auditor** — EN/MS i18n + version consistency + docs accuracy.
   Result: PASS with small clean-ups — all 160 USED keys have EN+MS; version
   1.5.3 consistent in every file; 3 LOW findings (dead key `main.no_video`,
   gettext + 12 empty locale folders, the README suite list undercounted).
4. **ui-a11y-auditor** — NVDA accessibility in src/ui/.
   Result: **NOT OK — 2 HIGH, 7 MEDIUM, 2 LOW.** HIGH: main window labels
   hard-coded in English + no retranslate after switching language; status in 4
   secondary windows silent (SetLabel not announced by NVDA). MEDIUM: shortcuts
   trapped in a text control, delete without confirmation, choices showing raw
   IDs ("ms", "edge"), missing labels, Test button re-entrancy, no default
   button, etc.
5. **core-auditor** — code quality of src/core/ + main.py.
   Result: **1 HIGH, 6 MEDIUM, ~10 LOW.** HIGH (the most important):
   `save_descriptions()` did not write back `lastrowid` → every `desc.id=0`
   → the player narrated only the first cue; deleting 1 cue in the editor deleted
   ALL cues and deleted the project from SQLite (data loss).

All 5 reports were kept; the HIGH bugs were confirmed independently by the parent
agent by reading the code (project_store.py:240-268, player_window.py:485,
:302-305, editor_window.py:174) before the final report.

## 2. Phase 2: "fix all"

Strategy: the parent agent fixed the core first (the P1 bug, settings_store,
all the new i18n keys), then 3 fix sub-agents ran in parallel on the UI files
(split by file so there were no conflicts):

- **fix-settings-dialog** (done, full report): friendly choice labels
  ("Bahasa Melayu"/"Edge TTS"), Enter = Apply (SetDefault), Test button
  re-entrancy guard, slider label, t("settings.show"/"hide"/"select_dir"/
  "model_hint"/"saved"). Heads-up: test_fixes2 has to read raw IDs.
- **fix-main-frame** (done, confirmed by the parent — 22 checks PASS):
  every label/dialog/log string → i18n, `_retranslate_ui()` +
  `_retranslate_menu()` methods, 3 missing NVDA labels added.
- **fix-secondary-windows** (done, full report): `_announce()`
  (SetLabel+SetFocus) in Player/SceneExplorer/Editor/AskMore; 500 ms timer
  change guard; EVT_CHAR_HOOK; per-language prompts; editor delete
  confirmation; new status StaticText for the Editor + AskMore.

Parent fixes:

- **P1**: `project_store.save_descriptions()` writes `cursor.lastrowid` +
  sqlite try/finally (create_project, save_descriptions).
- **settings_store**: a deep copy of DEFAULTS; atomic save (tmp +
  `os.replace`); **real DPAPI** (`win32crypt`, `dpapi:` prefix) with the
  old XOR fallback — old keys can still be read (probed + tested).
- **ai_engine**: GLM `max_tokens` 1024→6000 (pitfall #7); the Gemini key
  out of the URL → `x-goog-api-key` header (5 sites); HTTP status checked
  before `resp.json()` (Gemini ×2, OpenAI ×2, full-video ×1); ffmpeg
  **cancellable** (new `_run_ffmpeg_cancellable` — 1 s poll);
  `_probe_duration` cancellable; leaked compressed files closed (unlink +
  rmdir of the `odc_vcompress_`/`odc_vsplit_` mkdtemp dirs); `snap_timestamps` merges
  cues at the same time; duplicate imports removed.
- **timeline_io**: the source TTS clip deleted after the WAV conversion (a %TEMP%
  leak per cue).
- **video_processor**: `has_audio` defaults to False + is meaningful; `download_video`
  rejects non-http(s) + a `"--"` guard; `odc_sub_` dirs cleaned up.
- **tts_engine**: `stream.Close()` in try/finally; a redundant second SAPI5
  attempt removed (speak() already falls back through every engine).
- **prompt_manager**: `text_ocr` reachable (underscore filter fixed;
  language-prefixed presets still work).
- **main.py**: a `sys.stdout is None` guard (windowed exe) + `sys.excepthook`
  logs unhandled exceptions.
- **i18n/strings.py**: 74 new EN+MS keys; dead key `main.no_video`
  removed; docstring fixed; full parity of 302 keys.
- **repo**: `locale/` (12 empty folders) deleted; .gitignore + secret entries;
  pyproject yt-dlp >=2025.6.9; README suite list + a "What's new" section;
  AGENTS.md status.

## 3. Phase 3: tests

- **tests/test_fixes19.py** (new, 27 checks): IDs after save, player
  dedup, delete 1 cue, reload; DEFAULTS isolation + atomic save + DPAPI
  format + old XOR keys; text_ocr (en/ms); snap_timestamps merge; download
  URL guard; `has_audio` default; `_run_ffmpeg_cancellable` fast cancel
  (<10 s) + a full run; i18n parity. Registered in `run_gate.bat`
  → **28 suites**.
- `test_fixes2.py`: reads raw engine IDs via `dlg._choice_value(...)`.
- `test_fixes12.py`: waits for GUI clean-up event-driven (a
  wx.CallAfter race caught by the gate).

Gate runs during this phase:

1. **GATE_FAIL** — caught: `wx.MenuBar.SetLabelTop` does not exist in wxPython
   Phoenix (fixed: `menubar.GetMenu(i).SetTitle(...)`); my cancel test
   raced a fast ffmpeg (fixed: a deterministic cancel).
2. **GATE_FAIL** — `test_fixes12` race: a fixed 150 ms window after the worker
   died (fixed: event-driven wait, every assertion kept).
3. **GATE_ALL_PASS — 28/28.**
4. GATE_ALL_PASS again after the version bump (before the commit).

Also: `tests/audit_i18n.py` — 233 keys used, 0 missing, 0 buttons without a
label.

## 4. Phase 4: release (with permission: "1 commit, 1 summary, 1 release")

- `docs/archive/summary-v1.5.4.md` — the summary of the fix pass.
- `__version__` 1.5.3 → **1.5.4** (single source; pyproject dynamic).
- README: a "What's new in v1.5.4" section. AGENTS.md: v1.5.4 status.
- **Commit `c8a9916`** — `release: v1.5.4 audit fix pass (P1 id bug, a11y,
  security, reliability)` — 25 files, +1166/−242; `VEDIO DESCRIBER.PY.txt`
  NOT touched.
- **Tag `v1.5.4`** (annotated).
- **build.bat BUILD_ALL_OK** — 4 phases, 899 s in the foreground; the exe smoke test
  passed; new zip `dist/OmniDescriber-1.5.4-win64.zip` (271 MB).
- The old `OmniDescriber-1.5.3-win64.zip` deleted (rule: keep the latest).

## 5. Session numbers

- Sub-agents: 5 audit + 3 fix = 8; all removed when done.
- Files changed in the commit: 25 (23 modified + 2 new).
- i18n keys: +74 new → 302 keys, full EN+MS parity.
- Test suites: 27 → 28; new checks: 27.
- Gate: 4 full runs during the fix/release phases; final GATE_ALL_PASS.
- Build: 899 s; zip 271,464,404 bytes.

## 6. Deliberately unchanged

- The "openai" provider stays in Settings (confirm if it should go).
- The player buttons "<< 10s" / "10s >>" stay (short form, the same in both languages).
- Settings: Escape closes without checking for changes (deferred).
- `video_describer/` (the old CLI package) stays — still referenced by the README; local
  server on 127.0.0.1 only.

## 7. New gotchas recorded

- wxPython Phoenix: `MenuBar.SetLabelTop` does NOT exist — use
  `menubar.GetMenu(i).SetTitle(...)`.
- A dialog with friendly choice labels must map back through
  `_choice_labels` (see settings_dialog.py) — GetStringSelection() now
  returns the LABEL, not the ID.
- Tests that wait for GUI clean-up from a thread must be event-driven,
  not a fixed time window.
