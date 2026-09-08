# Omni Describer Custom

An accessible audio-description tool for blind and visually impaired
users. It downloads or opens a video and produces timestamped audio
descriptions in two ways: the default frame mode extracts frames and
sends them to an AI vision provider, while the optional full-video
mode (Gemini or MiniMax) uploads the whole video and lets the AI
watch it (including audio) and timestamp its own descriptions. A
built-in player reads the descriptions in sync with playback.

A full Malay user guide is in `doc/panduan-pengguna.md`; the English
version is `doc/user-guide.md`.

## What's new in v1.5.4

- **Narration + data-loss fix (critical)**: saved descriptions kept
  `id=0`, so the player narrated only the first cue and deleting one cue
  in the editor could wipe ALL cues from the project. Real database ids
  are now written back and covered by regression tests
  (`tests/test_fixes19.py`).
- **NVDA announcements everywhere**: Player, Scene Explorer, Editor and
  Ask More windows now announce playing/paused/stopped states, TTS
  results and errors; the main window retranslates instantly on a
  language switch; ~65 hardcoded strings moved to i18n (full EN+BM
  parity: 302 keys).
- **Real API-key protection**: keys are encrypted with Windows DPAPI
  (user-scoped) instead of source-obfuscated XOR; `settings.json` is
  written atomically so a crash can no longer wipe your keys.
- **Cancel works during video compression** (previously ignored for up
  to 30 minutes) and GLM gets `max_tokens=6000` so reasoning replies are
  no longer cut off or empty.
- **Security hardening**: Gemini API key removed from URLs, yt-dlp URL
  scheme validation, temp-file leaks closed, clearer HTTP errors.
- Full audit fix pass — see `doc/rumusan-v1.5.4.md` for the complete
  bilingual rumusan. Gate: 28/28 suites PASS.

## What's new in v1.5.3

- **Continuity between video parts**: long videos split for full-video
  mode now carry context into every part (part X of Y, the part's start
  time, and a short summary of what happened just before). No more
  "the video starts with..." in the middle of a video and no more
  re-introduced characters; the AI keeps one name per person/object.
- **10-minute parts by default**: the part length default is now 600 s
  (10 minutes) everywhere, and the Settings spin control no longer
  accepts tiny values that silently split a video into dozens of
  context-less mini parts.
- **Opus provider removed**: the built-in Opus proxy provider is gone
  (use Custom with any OpenAI-compatible endpoint instead); old Opus
  settings entries are ignored.
- **Fast one-shot mode position note**: batches of frames beyond the
  first now carry a "you are in the middle of the video" note with the
  exact start time from the extraction grid.
- Verified with a real 10-minute video split into 3 parts via GLM
  (OpenRouter): cues cover all parts with consecutive timestamps,
  25 unit/integration checks PASS.

## What's new in v1.5.2

- **Consistent description language**: AI descriptions now follow one
  language instead of randomly mixing Malay and English (the model used
  to pick the language from the video's own content). Choose the
  description language in Settings > General ("Description language"),
  default follows the app language.
- **Malay prompt presets fixed**: Malay presets were stored under names
  the picker never matched (`malay_*` vs `ms_`), so they never showed;
  they now appear when the app language is Malay.
- **Ask-more answers follow the same language** as descriptions.
- **CLI `--lang ms|en`** option on `video_describer describe`.
- Verified with a real end-to-end run: the same video described twice
  produced fully Malay output with `ms` and fully English output with
  `en` (35 unit/integration checks + full gate PASS).

## What's new in v1.5.1

- **Cancel works everywhere**: cancelling a download/processing now
  aborts the metadata probe and the ffmpeg extraction immediately
  (subprocess is killed), no ghost dialogs remain, buttons re-enable,
  and closing the app window during a run shuts down cleanly.
- **Same link reuses the existing project**: pasting a URL that was
  already processed offers to open the existing project instead of
  creating a duplicate (with Remove button in the Open dialog).
- **Named projects**: YouTube downloads now use the video title as the
  project name (sanitized), so projects are easier to tell apart.
- **Real-duration seek bar**: the player slider now covers the full
  video length (previously capped around 100 seconds).
- **Progress heartbeat**: the progress dialog shows elapsed time so a
  quiet download does not look frozen.
- **Narration never silently skipped**: if the online TTS engine fails
  mid-playback, the player falls back to the offline Windows voice and
  retries the cue instead of dropping it.
- **Full video path saved**: when processing finishes, a message box
  shows where the description video/audio was saved.

## Requirements

- Windows with Python 3.13 at
  `C:\Users\USER\AppData\Local\Programs\Python\Python313\python.exe`
- `ffmpeg`, `ffprobe` and `yt-dlp` available on PATH (or in the `bin`
  folder)

## Starting the app

Double-click `run.bat`. It launches `main.py` with the correct Python
interpreter. The log file is written to
`%LOCALAPPDATA%\OmniDescriber\logs\omni_describer.log`.

## Basic workflow

1. Press one of the source buttons: **Local Video File**,
   **Direct Video URL**, or **YouTube Video URL**.
2. Choose a prompt preset (or type your own) and press **Open**.
3. A progress dialog covers the whole pipeline: download (with real
   percentage, MB, speed and ETA), merge, frame extraction, AI analysis
   (live "AI analysis: done/total frames" counter), and saving. In
   full-video mode the dialog also shows real percentages for the
   split/describe phases — the live percentage appears in the dialog
   title too ("Downloading video - 55%"), so screen readers announce
   every change.
4. Press **Cancel** in the dialog at any time. During AI analysis the
   worker stops between frames and keeps whatever is already done.
5. When processing finishes, the described-video player opens
   automatically with the descriptions loaded and the project
   subtitles auto-loaded. The video itself is kept as a permanent
   copy inside the project folder (`media\video.mp4`), so the player
   works again later without re-downloading. Subtitles render as
   on-screen text over the video, and a **Load SRT...** button lets
   you open any external SRT file. One button toggles Play/Pause
   (the label always shows what happens next), and audio plays even
   without VLC installed (ffmpeg's ffplay handles the sound).

## Settings (File menu > Settings...)

- **AI tab**: provider (Gemini, MiniMax, OpenAI, GLM, or
  Custom), API key, model; a **Test** button verifies the connection.
  The GLM entry is shown as **OpenRouter** in the dropdown. For
  OpenRouter the model list shows video-capable models and a
  **Fetch models** button refreshes it from the live public catalog
  (no key or credit needed). Pick model `z-ai/glm-5.3-flash`, paste
  your OpenRouter key (`sk-or-v1-...`); a Zhipu direct key also works
  via the custom
  provider with `https://open.bigmodel.cn/api/paas/v4` as base URL.
  For Gemini and MiniMax, a **Full-video mode** checkbox switches from
  frame extraction to uploading the whole video so the AI watches it
  and timestamps the descriptions itself (one upload, one AI call;
  covers sound and speech as well as visuals).
  For OpenRouter (GLM) there is a **Fast one-shot mode** checkbox: frames are
  extracted locally with a burned-in `H:MM:SS` timestamp (dark box,
  top-left), then ALL frames go to the AI in ONE request (auto-split
  into chunks of 150 images per request for long videos). The model
  reads the on-screen stamps and the app snaps them back onto the
  exact extraction grid, so timestamps stay in sync even if the model
  misreads a stamp. One download, one (or few) AI request(s), frames
  analysed locally. OpenRouter models whose catalog entry includes
  video input (for example `z-ai/glm-5.3-flash`) can also use
  **Full-video mode**: the whole video file is sent as base64 in one
  request (empirically verified: a 60 s clip costs about 9k prompt
  tokens), and the AI watches it itself — including audio — and
  timestamps the descriptions. Long videos are split into parts
  (about 10 minutes each) and described part by part with timestamps
  merged back onto one timeline; parts above ~50 MB are compressed
  before upload (verified against the OpenRouter endpoint:
  50.7 MB uploads succeed, ~98 MB is rejected). The two checkboxes are
  mutually exclusive.
- **TTS tab**: speech engine, voice, speed.
- **General tab**:
  - **Language**: `en` or `ms`.
  - **Frame Rate (FPS)**: how many frames per second of video are
    extracted for analysis (1, 2, 5 or 10).
  - **Chunk length (seconds)**: in full-video mode, videos longer than
    this are split into consecutive parts (default 600 = 10 minutes).
    Each part is described in its own AI request and the timestamps
    are stitched back onto the whole-video timeline, so long videos
    upload reliably. A live "Splitting and describing video: N%" plus
    "Processing part X of Y, overall N%" keeps you informed.
  - **Max frames per video (0 = no limit)**: optional cost limit for
    long videos. Default `0` keeps existing behaviour (every extracted
    frame is analysed). If you set, for example, `100`, only the first
    100 extracted frames are sent to the AI, and the log honestly notes
    "Frame cap reached". Timestamps stay on the full-video timeline, so
    descriptions remain in sync with playback. A 17-minute video at
    5 FPS would otherwise mean about 5000 AI calls.
  - **Output Directory**: where exports are written.

## Projects

Projects are stored in `Documents\OmniDescriber\projects` (one folder
per project with a SQLite database, a permanent copy of every used
frame, and a `media\` folder holding a permanent copy of the source
video plus a `descriptions.srt` sidecar). Use **File** menu items
to create, open, or save projects.

## Standalone video describer (CLI + HTTP API)

`video_describer/` is an independent, headless pipeline that shares no
code with the GUI. It burns an `H:MM:SS` timestamp (dark box, top-left)
into every extracted frame, sends ALL frames base64-encoded in ONE
`glm-5.3-flash` request, trusts the model to READ the on-screen stamps,
then regex-parses the reply into `description.srt` + `description.json`
(auto-batches above 150 frames; guards 5 MB / 6000 px per frame).

```bat
:: describe a local video (SRT + JSON written next to it)
set GLM_API_KEY=your-key
python -m video_describer describe video.mp4 --fps 1 --tts

:: parse model text only (H:MM:SS - description lines)
python -m video_describer parse model_output.txt

:: HTTP API on 127.0.0.1:8765
python -m video_describer serve --port 8765
```

Endpoints: `GET /health`, `POST /describe` (JSON body
`{"video_path": "...", "fps": 1, "tts": false}`),
`POST /describe/upload?name=v.mp4` (raw video bytes), and
`POST /parse` (parse only). The API key comes from the request body,
the `X-API-Key` header, or the `GLM_API_KEY` environment variable.
TTS narration (`--tts`) uses edge-tts (default `ms-MY-OsmanNeural`)
or Windows SAPI5 (`--tts-engine sapi`); cue files and a concat M4A/MP3
land in an `audio/` folder next to the outputs.

## Development

- Run all checks (compileall + every test suite):
  `run_gate.bat` — prints `GATE_ALL_PASS` when everything passes.
- Test suites live in `tests\` as standalone scripts
  (`test_fixes.py` ... `test_fixes19.py`, `test_acceptance.py`,
  `test_chunked_video.py`, `test_gui_smoke.py`, `test_pipeline.py`,
  `test_timeline_io.py`, and more — `run_gate.bat` lists them all and
  is the source of truth). Each exits nonzero on failure.
- i18n audit (every `t("...")` key exists in both EN and MS, no
  unlabeled buttons): `python tests\audit_i18n.py` — prints
  `AUDIT_PASS`.

## Building a distributable exe (deployment)

Run `build.bat`. It does four stages and prints `BUILD_ALL_OK` when all
succeed:

1. **Compile check** of all sources.
2. **PyInstaller** (`--onedir --windowed`) produces `dist\OmniDescriber\`
   with an `OmniDescriber.exe` launcher, bundled `doc\` folder, and all
   TTS/AI/PIL dependencies collected.
3. **Smoke test** launches the real exe, waits for the
   "Application started" log line, confirms the process stays alive,
   then closes it (`tests\test_build_smoke.py`).
4. **Zip**: `dist\OmniDescriber-<version>-win64.zip` (~271 MB, versioned
   from `__init__.py`) ready to copy
   to any Windows 10/11 x64 machine. Recipients do not need Python or
   ffmpeg for playback of local files; YouTube URLs still need
   `yt-dlp` on PATH.

- Tests deliberately exercise real paths: real ffmpeg renders, a real
  localhost HTTP AI server, real SQLite writes, and the real wx dialog
  pipeline. Known environment constraints (documented inside the tests):
  native wx message boxes cannot be driven from Python, and wx + VLC
  native teardown can crash after tests pass, so suites exit via
  `os._exit` after flushing results.
