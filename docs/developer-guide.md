# Developer guide — DescriVox Agent

For people and coding agents changing the code. `AGENTS.md` holds the
hard rules; the numbered pitfalls are in `docs/pitfalls.md`. Read both
first. Pitfall numbers are referenced from code comments, so they are
never renumbered.

## What the app is for

Audio description for a blind owner who uses NVDA and Malay. Every
change is judged by two questions: is it accessible (heard through a
screen reader, not assumed from code), and is the description accurate
(measured, not assumed).

## Layout

```
main.py                     entry: logging, no_console, missing tools, MainFrame
src/omni_describer_custom/
  __init__.py               __version__ (the only place the version lives)
  core/
    ai_engine.py            providers (OpenRouter "glm", Gemini, MiniMax, OpenAI,
                            custom); whole-video + frame modes; parts, retries,
                            429 handling
    review.py               "Check descriptions against the video" (v1.8.8)
    agent.py                the Player agent: tools, guards, probe, check_all (v1.9.0)
    characters.py           one name per person: rules, cast list, rename (v2.1.0)
    model_catalog.py        OpenRouter + Gemini model lists, RECOMMENDED,
                            "Test this model" results
    video_processor.py      download (yt-dlp), frames, transcript (Whisper/Grok)
    project_store.py        "<Name> (id)/project.db" + media/
    prompt_manager.py       DEFAULT_PROMPTS — the one source of the AD presets
    settings_store.py       settings.json, DPAPI keys, one shared state
    tools.py                the ONLY place that finds ffmpeg/ffprobe/ffplay/yt-dlp
    updater.py              Help > Update YouTube downloader (yt-dlp)
    app_update.py           Help > Check for Updates: the app itself (GitHub Releases)
    housekeeping.py         sweeps old odc_* temp folders at start-up
    timing_store.py         learned "about N min left" estimates per model
    no_console.py           no console windows for child programs (frozen exe)
    speech.py, audio_meter.py, tts_engine.py   speaking and the narration hold
    timeline_io.py          SRT/VTT/TXT import & export, audio export
  ui/
    main_frame.py           main window, the processing pipeline, all handlers
    settings_dialog.py      General / AI Settings / Audio Output tabs
    player_window.py        player, narration, F2
    agent_dialog.py         the agent window (F2), "Check the whole video"
    characters_dialog.py    Player > Characters... (v2.1.0)
    editor_window.py, ask_more_dialog.py, scene_explorer.py,
    update_dialog.py, dialogs.py (Yes/No in the app's language)
  i18n/strings.py           t() and the loader
  i18n/locales/{en,ms}.json every visible string, both languages
tests/                      one script per regression round; run_gate.bat runs all
tools/                      measurement, listening checks, E2E drivers, build helpers
bin/                        bundled binaries (not in git; tools/fetch_binaries.py)
docs/                       every document (English); shipped inside the exe
.github/                    CI (light), issue templates, pull request template
```

## Documentation

| File | What it is |
|---|---|
| `AGENTS.md` | Hard rules for anyone changing the code |
| `docs/pitfalls.md` | The numbered pitfalls (referenced from code comments) |
| `docs/plan.md` | All plans, in one place |
| `docs/checklist.md` | The open checklist — the source for open work |
| `docs/model-comparison.md` | Model measurements and methods |
| `docs/user-guide.md` | The user guide, shipped with the app |
| `docs/adding-a-language.md` | Adding a UI language |
| `CHANGELOG.md` | Every release |
| `docs/archive/` | Archive: finished checklist phases 1-18, v1.5.x summaries |
| `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md` | GitHub community files |
| `.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md` | Forms for issues and pull requests |
| `contracts/` | Frozen contracts: release, accessibility, measurement (`contracts/README.md`) |

All documents are written in English (owner's decision, 5 Oct 2026). The app's
interface stays in English and Malay.

## Running and testing

- Run from source: `run.bat` (Python 3.13).
- The gate: `run_gate.bat` → `GATE_ALL_PASS`. Commit only on that, and run it
  twice before a release: a failure that happens "sometimes" is a bug
  until proven otherwise (AGENTS rule 1).
- Tests are plain scripts that exit non-zero on failure. Several open real
  wx windows and speak through NVDA; run them with the PC left alone and
  NVDA quiet (the NVDA timing suite re-measures while other programs talk,
  then reports "could not measure").
- Isolation — never let a test touch the owner's real data:

| Variable | Isolates |
|---|---|
| `ODC_CONFIG_DIR` | settings.json |
| `ODC_PROJECTS_DIR` | the projects folder |
| `ODC_TOOLS_DIR` | user-installed yt-dlp updates |
| `ODC_UPDATE_DIR` | downloaded app updates and the swap script's log |
| `ODC_RELEASE_KEY` | the release signing key (tests use a temp test key) |
| `ODC_UPDATE_SOURCE` | test only: `http://127.0.0.1:<port>` serves a test release (needs `ODC_UPDATE_DIR` too; no redirects; still signed) |
| `ODC_LOCALES_DIR` | user language files |
| `ODC_PRISM_BACKEND` | forces a speech backend (SAPI, NVDA, OneCore) |

- Style: `ruff format .` (standard style, line length 100) and `ruff check .`
  (bug-catching rules, `pyproject.toml`). CI runs both. The one-off commit
  that formatted the whole repo (phase 37.5) is listed in
  `.git-blame-ignore-revs`; run `git config blame.ignoreRevsFile
  .git-blame-ignore-revs` once so local `git blame` skips it too.
- Type checking is optional and not part of the gate: `pyrightconfig.json`
  tells pyright (and editors or agents that use it as a language server)
  that tests and tools import from `src`, `tools` and `tests`, because the
  scripts add those folders to `sys.path` when they run.

## Accessibility is verified by listening

- `tools/nvda_accessibility_check.py [--frozen]` — the main window.
- `tools/nvda_window_check.py --window player|editor|ask|updates|explorer|settings`;
  `--window settings --provider custom` opens the AI tab on that provider.
- `tools/nvda_agent_check.py` and `tools/nvda_progress_check.py` — F2, a real question, every spoken step.
- `tools/e2e_full_verify.py --clip <video>` — the frozen exe, a whole job.

All need NVDA with the HTTP bridge (127.0.0.1:19281) and exit 2 without it.
`tools/ci_nvda_smoke.py` is the exception: an experiment for GitHub CI only
(phase 38) that reads NVDA's own speech log instead; never run it on a desktop in use.
Keyboard automation must go through `tools/safe_keys.py`, which refuses to
type unless the app under test is in front (keys once landed in the
owner's chat program). Ask the owner before any run that types.

## Accuracy is measured

- `tools/model_bench.py run|judge|measure|review|snap` — describe real
  clips with the app's own engine, judge every description against the
  frames with a calibrated judge (report the WRONG rate), try a review
  pass. Clip variants change one setting: `clip@temp0` (temperature 0),
  `clip@tdef` (the server's default), `clip@think<level>` (thinking
  level, e.g. `@thinklow`, `@thinkdef`; `@thinkcap` = the shipped
  OpenRouter cap), `clip@chunk180` (part length). Gemini-direct runs are
  judged only with `measure --direct`, never by a Gemini judge.
- `tools/agent_levels.py --provider glm|gemini --model <id> --levels ...`
  — does more thinking make the Player agent better?
- `tools/agent_bench.py` — can a model drive the agent's tools at all?
- `tools/whisper_bench.py` — transcription settings across different videos.
- `tools/cast_bench.py run|score|judge` — do the character rules and the cast
  list help (name rate, labels, wrong rate)?

Keep a change only when the numbers improve, measured with a judge other
than the model being judged. Write the rule first: copy
`contracts/measure-template.json`, set the thresholds, freeze it, then run
the bench and judge with `tools/measure_check.py`. Results and methods: `docs/model-comparison.md`.

## Rate limits & keys

- Keys come from `settings.json` (DPAPI-encrypted) or environment
  variables — never from code or chat.
- A Gemini key's tier is per Google Cloud **project**, not per key or
  account: a new key in the same project shares its quota.
- HTTP 429 with a `quotaId` containing `PerDay` is a **daily** quota;
  waiting will not help, so the app stops at once and says it resets at
  midnight Pacific time (`ai_engine.daily_quota`).
- Any other 429: the app waits as long as the server asks (Gemini's
  `retryDelay` in the body, or `Retry-After`), up to `MAX_RETRY_WAIT`
  (65 s); a longer wait is treated as a quota and fails.

## Rules that are easy to break

- Every visible or spoken text goes through `t()` with an English AND a
  Malay entry; dynamic keys are written inline as `t(f"...")` so the
  unused-key test can see them.
- New widgets need an NVDA name: a StaticText created right before the
  control, or `SetName` on a TextCtrl — never `SetLabel` on a TextCtrl or
  Choice (pitfall 12 in `docs/pitfalls.md`).
- Long work runs on a worker thread; the UI is touched only via
  `wx.CallAfter`. A progress text that changes every second is re-read by
  NVDA every second — write it only when it changes.
- External programs only through `core/tools.find_tool()`.
- Paths inside a project only through `ProjectStore.project_dir/media_dir`.
- New temp folders use an `odc_` prefix listed in `core/housekeeping.py`.
- The model chosen in Settings must reach the call (`AIEngine._model_for`).

## Releasing

1. `run_gate.bat` twice → `GATE_ALL_PASS` both times.
2. Bump `__version__` in `src/omni_describer_custom/__init__.py` (last
   digit stops at 9: 1.6.9 → 1.7.0, never 1.6.10).
3. Add "What's new" to `README.md` (keep exactly three) and the entry to
   `CHANGELOG.md`; update the `AGENTS.md` status, `docs/checklist.md` and the
   phase table in `docs/plan.md`. `python tools/check_docs.py` must print
   `DOCS_OK` — the gate (test_fixes73) and `build.bat` run it too.
4. `build.bat` in the foreground → `BUILD_ALL_OK`. After the zip it writes
   `dist/SHA256SUMS.txt`, signs it into `dist/SHA256SUMS.txt.sig` and writes
   `dist/release-notes-<v>.md` (`tools/release_files.py`), which the in-app
   updater needs. Signing uses the owner's Ed25519 key in
   `%USERPROFILE%\.descrivox\release-signing.key` (`tools/release_key.py`;
   made once, never committed, backed up offline). The app holds its public
   half (`core/app_update.RELEASE_PUBLIC_KEY`) and refuses any release whose
   checksum list does not verify; a lost key means users must update by hand
   once to a build with a new public key. Its last step backs up the
   source code (`tools/make_source_zip.py`, committed files only, refused if
   anything looks like a binary or a key) into
   `Documents\DescriVox-source-backups\`.
5. Listen to the frozen exe: `python tools\nvda_accessibility_check.py --frozen`
   (judged against the frozen `contracts/a11y-main.json`).
6. `python tools\release_check.py` must say VERIFIED (the release contract,
   judged on evidence the gate, build and NVDA check recorded themselves);
   tag with `python tools\tag_release.py`, never by hand. See
   `contracts/README.md`.
7. Publish: `python tools\publish_release.py` (dry run) checks VERIFIED,
   the tag at HEAD, the zip against `SHA256SUMS.txt`, the notes, and that
   `gh` is logged in (the owner logs it in once; no token passes through
   an agent), then prints the plan. The owner delegated publishing to the
   agent (6 Oct 2026) but answers ONE yes per version; only then
   `python tools\publish_release.py --yes`: pushes `main` and the tag,
   creates the GitHub Release on `lbk2907/DescriVoxAgent` (title
   `DescriVox Agent <v>`, text = `dist/release-notes-<v>.md`, files = the
   zip, `SHA256SUMS.txt` and `SHA256SUMS.txt.sig`) and reads `releases/latest` back the way the
   in-app updater (`core/app_update.py`) does.
8. Keep only the newest zip in `dist/` (ask the owner before deleting).
