# Developer guide — Omni Describer Custom

For people and coding agents changing the code. `AGENTS.md` (Malay) holds
the hard rules and the numbered pitfalls; read it first. Pitfall numbers
are referenced from code comments, so they are never renumbered.

## What the app is for

Audio description for a blind owner who uses NVDA and Malay. Every
change is judged by two questions: is it accessible (heard through a
screen reader, not assumed from code), and is the description accurate
(measured, not assumed).

## Layout

```
main.py                     entry: logging, no_console, missing tools, MainFrame
src/omni_describer_custom/
  core/
    ai_engine.py            providers (OpenRouter "glm", Gemini, MiniMax, OpenAI,
                            custom); whole-video + frame modes; parts, retries
    review.py               "Check descriptions against the video" (v1.8.8)
    agent.py                the Player agent: tools, guards, probe (v1.9.0)
    video_processor.py      download (yt-dlp), frames, transcript (Whisper)
    project_store.py        "<Name> (id)/project.db" + media/
    settings_store.py       settings.json, DPAPI keys, one shared state
    tools.py                the ONLY place that finds ffmpeg/ffprobe/ffplay/yt-dlp
    updater.py              Help > Check for Updates (yt-dlp)
    model_catalog.py        OpenRouter model list + "Test this model"
    speech.py, audio_meter.py, tts_engine.py   speaking and the narration hold
    timeline_io.py          SRT/VTT/TXT import & export, audio export
  ui/                       main_frame, player_window, agent_dialog,
                            settings_dialog, editor_window, ask_more_dialog,
                            update_dialog, scene_explorer, dialogs
  i18n/locales/{en,ms}.json every visible string, both languages
tests/                      one script per regression round; run_gate.bat runs all
tools/                      measurement, listening checks, E2E drivers, build helpers
bin/                        bundled binaries (not in git; tools/fetch_binaries.py)
```

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
- `tools/nvda_window_check.py --window player|editor|ask|updates`.
- `tools/nvda_agent_check.py` — F2, a real question, every spoken step.
- `tools/e2e_full_verify.py --clip <video>` — the frozen exe, a whole job.

All need NVDA with the HTTP bridge (127.0.0.1:19281) and exit 2 without it.
Keyboard automation must go through `tools/safe_keys.py`, which refuses to
type unless the app under test is in front (keys once landed in the
owner's chat program). Ask the owner before any run that types.

## Accuracy is measured

- `tools/model_bench.py run|measure|review` — describe real clips with the
  app's own engine, judge every description against the frames with a
  calibrated judge (report the WRONG rate), try a review pass.
- `tools/agent_bench.py` — can a model drive the agent's tools?
- `tools/whisper_bench.py` — transcription settings across different videos.

Keep a change only when the numbers improve, measured with a judge other
than the model being judged. Results and methods: `doc/perbandingan-model.md`.

## Rules that are easy to break

- Every visible or spoken text goes through `t()` with an English AND a
  Malay entry; dynamic keys are written inline as `t(f"...")` so the
  unused-key test can see them.
- New widgets need an NVDA name: a StaticText created right before the
  control, or `SetName` on a TextCtrl — never `SetLabel` on a TextCtrl or
  Choice (pitfall 12).
- Long work runs on a worker thread; the UI is touched only via
  `wx.CallAfter`. A progress text that changes every second is re-read by
  NVDA every second — write it only when it changes.
- External programs only through `core/tools.find_tool()`.
- Paths inside a project only through `ProjectStore.project_dir/media_dir`.
- New temp folders use an `odc_` prefix listed in `core/housekeeping.py`.
- The model chosen in Settings must reach the call (`AIEngine._model_for`).

## Releasing

1. `run_gate.bat` twice → `GATE_ALL_PASS`.
2. Bump `__version__` in `src/omni_describer_custom/__init__.py` (last
   digit stops at 9), add "What's new" to README (keep three) and to
   `CHANGELOG.md`, update `AGENTS.md` status and the checklist.
3. `build.bat` → `BUILD_ALL_OK`; listen to the exe
   (`nvda_accessibility_check.py --frozen`); tag `vX.Y.Z`; keep only the
   newest zip in `dist/`.
