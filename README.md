# Omni Describer Custom

An accessible audio-description tool for blind and visually impaired
users, built around NVDA. It downloads or opens a video, has an AI
describe what is SEEN at each moment, and plays the video with the
descriptions spoken in sync. Everything is operated by keyboard and
announced to the screen reader; the interface is in English and Malay.

- **Whole-video mode** (default): the AI watches the video in parts
  (5 minutes each) and places its own descriptions, told where the
  dialogue is so it can use the gaps. Optionally each description is
  then checked against the frames around it (Settings).
- **Frame mode**: frames are extracted locally and described one by
  one, at most one description every 4 seconds; exact timing, suited to
  slides and screen recordings.
- **The Player agent (F2)**: ask about what you are watching; it looks
  at the video and proposes fixes that you accept or reject.

Providers: **OpenRouter** (GLM 5.3 Flash by default; any video-capable
model, tested with Settings > Test this model / Test agent mode),
Gemini, MiniMax, OpenAI (frame mode) and any OpenAI-compatible endpoint.

## Documentation

- User guide: `doc/panduan-pengguna.md` (Malay), `doc/user-guide.md`
  (English) — also shipped inside the app folder.
- What changed in each release: `CHANGELOG.md`.
- Developers and coding agents: `doc/developer-guide.md` and
  `AGENTS.md` (Malay; the list of pitfalls is required reading).
- Model measurements: `doc/perbandingan-model.md`.

Version numbers: the last digit stops at 9, so 1.6.9 is followed by
1.7.0 (1.7.0 and 1.7.1 were first tagged 1.6.10 and 1.6.11).

## What's new in v1.9.5

- **Clearer, steadier handling of "too many requests" (HTTP 429).** When
  a provider says how long to wait (Gemini does, per minute), the app now
  waits that long instead of giving up after 5 and 15 seconds. When a
  DAILY quota is used up, it stops at once and says so ("daily quota used
  up ... resets at midnight Pacific time") instead of waiting for nothing.
- Measured: for the Player agent (F2) with your own Gemini key, **Gemini
  3.1 Flash-Lite** is the better choice. It fixed 4 of 4 wrong
  descriptions at about $0.003 a question; Gemini 3.8 Flash fixed none
  and cost about ten times more.

## What's new in v1.9.4

- **Gemini 3.1 Flash-Lite describes more accurately.** It now thinks at
  a "medium" level before writing. Measured on four different clips,
  three runs each: wrong descriptions 15.8% → 9.1%, and it is faster.
- **The Player agent (F2) is better with GLM.** Its thinking setting was
  measured and changed: right decisions 8 → 11 out of 16, and answers
  come about twice as fast. It rewrites fewer descriptions that were
  already correct.
- Thinking levels are set only for the models that were measured. If a
  model refuses a level, the app retries without it instead of failing.
- Measured and NOT used: more thinking for GLM whole-video (no clear
  gain; the highest level took 19 minutes on a one-minute clip and once
  returned nothing).

## What's new in v1.9.3

- **Fetch models works for Gemini.** With the Gemini provider, Fetch
  models asks Google which models your key can use and lists the ones
  that can watch a video (12 of 61 on the day it was written), the
  recommended one first, with its price. New Gemini models appear
  without an app update. Listing models is free and uses no quota.

## Installing

Unzip `OmniDescriber-<version>-win64.zip` (about 305 MB) anywhere and
run `OmniDescriber.exe`. Nothing else is needed: ffmpeg, ffprobe,
ffplay and yt-dlp are inside the app folder, and a newer yt-dlp can be
installed from Help > Check for Updates. An API key is entered in
File > Settings.

To run from source instead: Python 3.13 on Windows, then
`python tools\fetch_binaries.py` once (the binaries are not in git and
are checked against pinned SHA-256 hashes), then `run.bat`. The log is
`%LOCALAPPDATA%\OmniDescriber\logs\omni_describer.log`.

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

This standalone tool predates the app's current engine and is not part
of the test gate; the app itself does not use it.

## Building

`build.bat` checks the pinned binaries, compiles, runs PyInstaller,
smoke-tests the real exe and writes `dist\OmniDescriber-<version>-win64.zip`,
printing `BUILD_ALL_OK`. Before a release: `run_gate.bat` twice
(`GATE_ALL_PASS`), then listen to the built exe with
`python tools\nvda_accessibility_check.py --frozen`. See
`doc/developer-guide.md`.
