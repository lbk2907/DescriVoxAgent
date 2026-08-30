# Omni Describer Custom

An accessible audio-description tool for blind and visually impaired
users. It downloads or opens a video, extracts frames, sends them to an
AI vision provider, and plays the video in a built-in player that reads
out the AI descriptions in sync with playback.

A full Malay user guide is in `doc/panduan-pengguna.md`.

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
   (live "AI analysis: done/total frames" counter), and saving.
4. Press **Cancel** in the dialog at any time. During AI analysis the
   worker stops between frames and keeps whatever is already done.
5. When processing finishes, the described-video player opens
   automatically with the descriptions loaded.

## Settings (System menu > Settings...)

- **AI tab**: provider (Gemini, OpenAI, Opus Proxy, or Custom), API key,
  model; a **Test** button verifies the connection.
- **TTS tab**: speech engine, voice, speed.
- **General tab**:
  - **Language**: `en` or `ms`.
  - **Frame Rate (FPS)**: how many frames per second of video are
    extracted for analysis (1, 2, 5 or 10).
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
per project with a SQLite database and a permanent copy of every used
frame). Use **File** menu items to create, open, or save projects.

## Development

- Run all checks (compileall + every test suite):
  `run_gate.bat` — prints `GATE_ALL_PASS` when everything passes.
- Test suites live in `tests\` as standalone scripts
  (`test_fixes.py` ... `test_fixes11.py`, `test_acceptance.py`,
  `test_gui_smoke.py`, `run_checks.py`). Each exits nonzero on failure.
- Tests deliberately exercise real paths: real ffmpeg renders, a real
  localhost HTTP AI server, real SQLite writes, and the real wx dialog
  pipeline. Known environment constraints (documented inside the tests):
  native wx message boxes cannot be driven from Python, and wx + VLC
  native teardown can crash after tests pass, so suites exit via
  `os._exit` after flushing results.
