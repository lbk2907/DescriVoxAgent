# Developer guide — DescriVox Agent

For people and coding agents changing the code. `AGENTS.md` holds the
hard rules; the numbered pitfalls are in `doc/pitfalls.md`. Read both
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
    model_catalog.py        OpenRouter + Gemini model lists, RECOMMENDED,
                            "Test this model" results
    video_processor.py      download (yt-dlp), frames, transcript (Whisper/Grok)
    project_store.py        "<Name> (id)/project.db" + media/
    prompt_manager.py       DEFAULT_PROMPTS — the one source of the AD presets
    settings_store.py       settings.json, DPAPI keys, one shared state
    tools.py                the ONLY place that finds ffmpeg/ffprobe/ffplay/yt-dlp
    updater.py              Help > Check for Updates (yt-dlp)
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
    editor_window.py, ask_more_dialog.py, scene_explorer.py,
    update_dialog.py, dialogs.py (Yes/No in the app's language)
  i18n/strings.py           t() and the loader
  i18n/locales/{en,ms}.json every visible string, both languages
tests/                      one script per regression round; run_gate.bat runs all
tools/                      measurement, listening checks, E2E drivers, build helpers
bin/                        bundled binaries (not in git; tools/fetch_binaries.py)
```

## Documentation

| File | What it is |
|---|---|
| `AGENTS.md` | Hard rules for anyone changing the code |
| `doc/pitfalls.md` | The numbered pitfalls (referenced from code comments) |
| `doc/plan.md` | All plans, in one place (EN + BM) |
| `doc/senarai-semak.md` | The open checklist — the source for open work |
| `doc/perbandingan-model.md` | Model measurements and methods |
| `doc/user-guide.md`, `doc/panduan-pengguna.md` | User guides (EN, BM), shipped with the app |
| `doc/menambah-bahasa.md` | Adding a language (BM) |
| `CHANGELOG.md` | Every release |
| `doc/arkib/` | Archive: finished checklist phases 1-18, v1.5.x summaries |

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
| `ODC_LOCALES_DIR` | user language files |
| `ODC_PRISM_BACKEND` | forces a speech backend (SAPI, NVDA, OneCore) |

## Accessibility is verified by listening

- `tools/nvda_accessibility_check.py [--frozen]` — the main window.
- `tools/nvda_window_check.py --window player|editor|ask|updates|explorer|settings`;
  `--window settings --provider custom` opens the AI tab on that provider.
- `tools/nvda_agent_check.py` and `tools/nvda_progress_check.py` — F2, a real question, every spoken step.
- `tools/e2e_full_verify.py --clip <video>` — the frozen exe, a whole job.

All need NVDA with the HTTP bridge (127.0.0.1:19281) and exit 2 without it.
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

Keep a change only when the numbers improve, measured with a judge other
than the model being judged. Results and methods: `doc/perbandingan-model.md`.

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
  Choice (pitfall 12 in `doc/pitfalls.md`).
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
   `CHANGELOG.md`; update the `AGENTS.md` status and `doc/senarai-semak.md`.
4. `build.bat` in the foreground → `BUILD_ALL_OK`.
5. Listen to the frozen exe: `python tools\nvda_accessibility_check.py --frozen`.
6. Tag `vX.Y.Z` on the release commit.
7. Keep only the newest zip in `dist/`.
