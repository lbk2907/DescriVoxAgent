# AGENTS.md — DescriVox Agent (formerly Omni Describer Custom)

Rules for every coding agent working in this repository (Claude Code, Codex,
Gemini CLI, Cursor, jcode, Hermes, and others). Read this file before making
any change. Detailed lessons live in `docs/pitfalls.md`; this file is the index.

## 1. What this project is

A Windows desktop app (wxPython, Python 3.13) that produces AI audio
description for videos: download or open a video, have an AI describe what is
seen at each moment, then play it with the descriptions spoken in sync (TTS,
SRT, Player window). The owner and main user is blind, uses the NVDA screen
reader, and writes in Malay.

**Accessibility is a requirement, not optional.**

## 2. Working with the owner

These apply to every agent, in every session.

- **Language:** reply with a short summary in Malay first, then the detail in
  English.
- **Plans, not prompts:** the owner is not a prompt expert. Propose a plan and
  ask only the decisions that matter, as a short list of choices with the
  recommended one first.
- **Fix what you find:** bugs found while doing other work are fixed, then
  reported afterwards (what, why, evidence).
- **Be honest:** state mistakes, money spent on API calls, and anything that
  was NOT verified. Never claim PASS without evidence (command output, a test,
  a measurement, a listening check).
- **Verify facts in the code, not from memory.** Do not repeat work that is
  already verified unless something changed (new request, new bug, new commit).
- When checking a release, measure the tagged commit, not HEAD.

## 3. Hard rules (non-negotiable)

1. **Gate before every commit.** Run `run_gate.bat` after every code change;
   commit only on `GATE_ALL_PASS`. Before a release: `GATE_ALL_PASS` twice in a
   row. An intermittent failure is a bug until proven otherwise: run the
   failing suite 10 times before calling it flaky.
2. **Never break accessibility.** Every new widget has an NVDA name (see
   pitfalls 12, 53). Status changes are announced. Accessibility is verified by
   LISTENING with the NVDA tools (section 4, step 7), not by reading code.
3. **API keys never in code, chat, logs or URLs.** Keys come from
   `settings.json` (DPAPI-encrypted) or environment variables.
4. **Never type passwords or tokens anywhere.**
5. **All user-facing text goes through i18n `t()`**, with entries in BOTH
   `src/omni_describer_custom/i18n/locales/en.json` and `ms.json`.
6. **Never touch the untracked file `VEDIO DESCRIBER.PY.txt`** (the owner's
   sketch, origin of `video_describer/`).
7. **Confirm with the owner before deleting anything** and before any
   outward-facing action (messages, uploads, publishing).
8. **The agent never empties the Recycle Bin** and never acts in the owner's
   provider accounts (billing, top-ups, creating or rotating keys).
9. **Before any GUI, keyboard or NVDA automation,** ask the owner to leave the
   PC untouched and NVDA quiet for N minutes, and wait for an explicit OK.
   Keyboard automation only through `tools/safe_keys.py`.
10. **Tests use isolated data, never the owner's real data** — every test imports
    `tests/isolate.py` FIRST (`test_fixes58` enforces it): `ODC_CONFIG_DIR`,
    `ODC_PROJECTS_DIR`, `ODC_TOOLS_DIR`, `ODC_LOCALES_DIR` (and
    `ODC_PRISM_BACKEND` to force a speech backend). `run_gate.bat` sets the
    first, second and fourth. Real-GUI E2E tools deliberately use real
    settings (they need the owner's key); do not set `ODC_CONFIG_DIR` there.
11. **No Opus Proxy provider.** It was removed in v1.5.3; do not reintroduce it.
12. **Version numbering:** the last digit stops at 9 (1.6.9 → 1.7.0, never
    1.6.10). `__version__` in `src/omni_describer_custom/__init__.py` is the
    single source.
13. **Commits are typed:** `feat:`, `fix:`, `test:`, `docs:`, `release:`, short
    message. End with your tool's co-author line if your tooling requires one.
14. **Long jobs (PyInstaller build, 8–10 min) run in the foreground or
    watched.** Background jobs can be orphaned if the agent's server restarts.

## 4. The workflow

How work is actually done here, step by step.

1. **Understand and ask.** Restate the request, propose a plan, ask the
   decisions (choices, recommended first).
2. **Write it down.** Plan into `docs/plan.md`; checklist items into
   `docs/checklist.md`. Tick `[x]` only with evidence written next to it.
3. **Measure first** for any accuracy, model, prompt or cost question:
   - `tools/model_bench.py run` / `measure` (with a judge that is NOT the model
     being judged), also `review`, `snap`, `@think<level>` variants;
   - `tools/agent_levels.py` and `tools/agent_bench.py` for the Player agent;
   - `tools/whisper_bench.py` for transcription (use genuinely different
     videos, pitfall 44).
   Keep a change only if the numbers improve. Record numbers and method in
   `docs/model-comparison.md`.
4. **Implement** in the surrounding style (worker threads touch the UI only via
   `wx.CallAfter`; external programs only via `core/tools.find_tool()`; project
   paths only via `ProjectStore`; new temp prefixes `odc_*` registered in
   `core/housekeeping.py`).
5. **Regression test that FAILS on the old code.** Prove it (e.g. `git stash`
   the `src/` change, run the test, see it fail, restore). Add the suite to the
   list in `run_gate.bat`. A new menu/button handler needs a check in
   `tests/test_fixes21.py`. Test output must be line-buffered (pitfall 9).
   For a **bug fix, write that test FIRST** and see it fail before touching
   `src/` (owner, 6 Oct 2026, from the ECC workflow); a new feature may write
   its tests alongside the code.
6. **Review, then the gate.** Before every commit of a code change, run the
   ECC review agent on the diff (`ecc:python-reviewer`; `ecc:code-reviewer`
   for non-Python) and fix its CRITICAL and HIGH findings (owner, 6 Oct
   2026). Then run the suite, then the full gate (`GATE_ALL_PASS`).
7. **Listen with NVDA** (after asking the owner, rule 9):
   `tools/nvda_accessibility_check.py [--frozen]`,
   `tools/nvda_window_check.py --window player|editor|ask|updates|explorer|settings [--provider X]`,
   `tools/nvda_agent_check.py <video> [--check-all]`, `tools/nvda_progress_check.py`
   (the progress bar's percentages are heard). Without NVDA and its HTTP
   bridge (127.0.0.1:19281) these exit 2, which means "not verified".
8. **Docs.** Every document is in English (owner, 5 Oct 2026): the user guide
   `docs/user-guide.md`, a new pitfall at the end of `docs/pitfalls.md`, the
   checklist, the plan. Talk to the owner in Malay; write the repository in English.
9. **Release.**
   - Bump `__version__`; add "What's new" to `README.md` (keep the newest 3)
     and to `CHANGELOG.md`; update section 9 of this file; add the phase to
     the table in `docs/plan.md` and move "the next one is Phase N".
   - Every change, not only a release: update every document it touches in
     the SAME commit (user guide, checklist, plan, CHANGELOG "Unreleased").
     `tools/check_docs.py` enforces the release part: it fails the gate
     (test_fixes73) and stops `build.bat` when a document is behind the
     version or the checklist, or a link is broken (owner, 6 Oct 2026: "do
     all of this automatically").
   - `run_gate.bat` twice in a row → `GATE_ALL_PASS`.
   - `build.bat` in the foreground or watched → `BUILD_ALL_OK`.
   - Listen to the frozen exe: `tools/nvda_accessibility_check.py --frozen`
     (judged against `contracts/a11y-main.json`).
   - Tick the checklist and commit, then `python tools/release_check.py`
     must say **VERIFIED**, and tag ONLY with `python tools/tag_release.py`
     (never `git tag` by hand). The gate, the build and the NVDA check record
     their own evidence; INCONCLUSIVE is not a pass (contracts/README.md).
   - Publish (owner delegated it, 6 Oct 2026): ask the owner ONE yes for
     this version, then `python tools/publish_release.py --yes` (pushes
     `main` + the tag, creates the GitHub Release with the zip and
     `SHA256SUMS.txt`, which the in-app updater needs). Without that yes,
     only the dry run.
   - Delete the previous zip in `dist/` (ask the owner).
10. **Contracts** (`contracts/`, owner 6 Oct 2026). What "done" means is
    frozen before the work. You may change a contract only with
    `python tools/contracts.py freeze <id> --why "..."`, which records it in
    `contracts/CHANGES.md` — and you MUST tell the owner in the same reply.
    Before measuring a change, copy `contracts/measure-template.json` to
    `measure-<feature>.json`, set the thresholds, and freeze it FIRST;
    `tools/measure_check.py` refuses results older than the freeze.

### Background jobs on Windows

- Never run two writers to the same results file at once (for example
  `tools/model_bench.py`, which writes `%TEMP%\odc_bench\results.json`).
- There is no `pkill`. Stop a process with PowerShell, e.g.
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*model_bench*' } | ForEach-Object { Stop-Process -Id $_.ProcessId }`
- Clean up temp folders your own scripts create (a leftover `odc_probe_*`
  folder from a manual script once failed the gate).
- `model_bench` copies settings into its own folder; make sure that copy is
  fresh (a stale copy once used an old key).

## 5. Architecture

```
main.py                     entry: logging, no_console, missing-tools check, MainFrame
src/omni_describer_custom/
  __init__.py               __version__ (single source)
  core/
    ai_engine.py            providers: OpenRouter ("glm"), Gemini, MiniMax, OpenAI,
                            custom; whole-video and frame modes; parts, retries,
                            compression, body limits
    review.py               check descriptions against the video's frames (v1.8.8)
    agent.py                Player agent (F2): tools, guards, cost cap, probe (v1.9.0)
    model_catalog.py        model lists (OpenRouter, Gemini fetch), RECOMMENDED,
                            "Test this model" probes
    video_processor.py      download (yt-dlp), frames, transcript (Whisper)
    tools.py                the ONLY place that finds ffmpeg/ffprobe/ffplay/yt-dlp
    updater.py              Help > Update YouTube downloader (user-installed yt-dlp)
    app_update.py           Help > Check for Updates: the app updates itself from
                            GitHub Releases (signed SHA256SUMS.txt, folder swap) (2.1.3)
    housekeeping.py         sweeps old odc_* temp folders at startup
    settings_store.py       settings.json, DPAPI keys, one shared state per process
    project_store.py        "<Name> (id)/project.db" + media/
    prompt_manager.py       DEFAULT_PROMPTS: the one source of prompts
    timeline_io.py          SRT/VTT/TXT import/export, synced audio export
    timing_store.py         learned wait estimates per model (timing.json)
    speech.py               Prism speech (announce when no screen reader)
    audio_meter.py          hears when the screen reader stops speaking
    tts_engine.py           TTS engines (SAPI5 via SpFileStream, edge, openai...)
    no_console.py           CREATE_NO_WINDOW default for child processes
  ui/
    main_frame.py           main window, _process_video pipeline, all handlers
    player_window.py        player, subtitle overlay, narration and hold
    agent_dialog.py         Player agent dialog
    settings_dialog.py      tabbed settings (General / AI / Audio)
    editor_window.py        per-cue editor
    ask_more_dialog.py      Ask More
    scene_explorer.py       browse frames and descriptions
    update_dialog.py        Update YouTube downloader (yt-dlp)
    app_update_dialog.py    Check for Updates (the app itself)
    dialogs.py              shared dialogs (ask_yes_no, ...)
  i18n/strings.py           loader and t(); locales/en.json, locales/ms.json
tests/                      one script per regression round; run_gate.bat lists 86
tools/                      benches, NVDA listening checks, E2E drivers, build helpers
hooks/hook-prism.py         PyInstaller hook (pitfall 36)
bin/                        bundled ffmpeg/ffprobe/ffplay/yt-dlp (NOT in git;
                            tools/fetch_binaries.py)
video_describer/            standalone headless CLI/HTTP pipeline; not used by the
                            app and not in the gate
build.bat                   binaries → compile → PyInstaller → dedupe → smoke → zip
```

**Data flow:** `MainFrame._process_video` → project created first, then
download/resolve and transcript (`video_processor`) → AI describes the whole
video in parts, or frame by frame (`ai_engine`) → optional review
(`review.py`) → `Description` records (id, start_time, end_time, text, edited,
created_at, frame_path) → Player, SRT/TTS export, editor, agent.

## 6. Common commands

Python: `C:/Users/USER/AppData/Local/Programs/Python/Python313/python.exe`
(shown as `python` below).

```bat
:: run the app from source
run.bat

:: full gate (compileall + 86 suites) -> GATE_ALL_PASS
run_gate.bat

:: one suite
python -u tests\test_fixes21.py

:: release build -> dist\DescriVox-Agent-<version>-win64.zip, then the source
::   backup Documents\DescriVox-source-backups\DescriVox-Agent-source-v<version>.zip
::   (tools/make_source_zip.py: committed files only, no binaries or keys), BUILD_ALL_OK
build.bat
```

```bat
:: listening checks (ask the owner first; NVDA + HTTP bridge required)
python tools\nvda_accessibility_check.py --steps 12
python tools\nvda_accessibility_check.py --frozen
python tools\nvda_window_check.py --window player
python tools\nvda_window_check.py --window settings --provider gemini
python tools\nvda_progress_check.py
python tools\nvda_agent_check.py <video>
python tools\e2e_full_verify.py --clip <video>
```

```bat
:: measurement (costs money; tell the owner the estimate)
python tools\model_bench.py run --models <ids> --clips <names> --runs 2
python tools\model_bench.py measure --judge <judge model>
python tools\agent_levels.py --provider glm --model <id> --levels low,medium
python tools\agent_bench.py --models <ids>
python tools\whisper_bench.py
```

## 7. Documentation map

| File | Purpose |
|---|---|
| `README.md` | What the app does, newest 3 "What's new", install, build |
| `CHANGELOG.md` | Every release |
| `docs/plan.md` | All plans |
| `docs/checklist.md` | Live checklist and open work. Never write "no open bugs" anywhere else. |
| `docs/pitfalls.md` | The numbered pitfalls (full text) |
| `docs/developer-guide.md` | Developer orientation, isolation variables, rules easy to break |
| `docs/model-comparison.md` | Model measurements, methods, decisions |
| `docs/user-guide.md` | The user guide, shipped with the app (`_internal\docs`) |
| `docs/adding-a-language.md` | How to add a UI language |
| `NOTICE.md` | Third-party licences (ffmpeg GPL obligations) |
| `docs/archive/` | History: old summaries, checklist phases 1–18 |
| `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md` | GitHub community files (setup, private security reports, conduct) |
| `.github/` | CI (light), issue templates, pull request template |
| `contracts/` | Frozen contracts (release, accessibility, measurement), their lock and change log |

Every document is in English (owner's decision, 5 Oct 2026); `doc/` was renamed
`docs/` with English file names, and the Malay user guide was removed.

## 8. Pitfalls by area

Full text: `docs/pitfalls.md`. **Pitfall numbers are referenced from code
comments: never renumber; add new ones at the end (next is 101).** (57b is a
historical double number, kept.) A pitfall may appear in more than one row.

| Area | Pitfalls |
|---|---|
| Accessibility and NVDA verification | 12, 29, 34, 41, 53, 55, 57, 57b, 64, 65, 75, 92, 93 |
| wxPython quirks (MSW) | 8, 10, 11, 12, 34, 53, 57, 57b, 89, 90, 91 |
| Prompts and description accuracy | 1, 2, 13, 14, 16, 43, 69, 73, 74, 78, 81, 86 |
| AI providers and models | 7, 15, 35, 59, 62, 66, 71, 77, 80, 83, 84, 85, 86 |
| Rate limits and upstream errors | 51, 63, 71, 72, 84, 87, 89 |
| Transcript (Whisper) | 15, 42, 44, 45, 67, 70 |
| Video, ffmpeg, download | 20, 30, 31, 32, 33, 37, 52, 61, 63, 68, 76 |
| Settings, projects, files | 19, 38, 39, 50, 54, 56, 58 |
| Speech, TTS, narration hold | 4, 24, 25, 26, 27, 28, 46, 47, 48 |
| Player agent | 79, 82, 84, 86, 87 |
| Testing, gate, GUI automation | 3, 5, 6, 9, 10, 18, 19, 40, 44, 55, 60, 64, 88, 91, 94 |
| Build and packaging | 17, 21, 22, 23, 36, 49 |
| Self-update (cmd script) | 101, 102 |
| Listening checks (NVDA) | 100, 103 |

## 9. Current status (update at each release)

- **Version 2.1.2**, tag `v2.1.2`. Gate: compileall + 85 suites in
  `run_gate.bat`; `GATE_ALL_PASS` twice in a row for 2.1.2; build
  `BUILD_ALL_OK` (+ source backup); frozen exe heard by NVDA (checklist phase 31).
- **Providers:** OpenRouter (`glm`, default model `z-ai/glm-5.3-flash`);
  Gemini direct (model list fetched from Google with Fetch models; recommended
  `gemini-3.1-flash-lite`); MiniMax; OpenAI (frame mode); custom
  OpenAI-compatible. `model_catalog.RECOMMENDED` = GLM 5.3 Flash, Gemini 3.1
  Flash-Lite; change only with new `model_bench.py` measurements.
- **Player agent** works with OpenRouter and Gemini (`AGENT_PROVIDERS`).
- **Open work:** `docs/checklist.md` is the only source.
- **Remote:** `origin` = https://github.com/lbk2907/DescriVoxAgent (public).
- **Backup:** `.git/hooks/post-commit` also bundles the
  whole history to `~/OneDrive/backups/omni-describer-custom.bundle` after
  every commit. The hook is not in git; recreate it after a fresh clone.
  Restore with `git clone <bundle> <dir>`.
- **Code graph:** UML package + module views are in `docs/diagrams/`
  (PlantUML sources; regenerate with `omh codegraph uml`).
 