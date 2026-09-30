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

## What's new in v1.9.2

- **Settings > AI is clearer.** The Custom provider's model box now has
  a name ("Model name") for screen readers; the full-video checkbox is
  now **Send the whole video to the AI (recommended)** and its hint says
  what unticking does. Buttons that did nothing for Custom are greyed out.
- **Test this model works for every provider**, replacing Test
  Connection (which only asked the AI to say "OK"). Gemini and MiniMax
  get a 6-second clip through the real upload path (does it see and
  hear?); OpenAI and Custom get one picture.
- **The Player agent (F2) works with your own Gemini key**, not only
  OpenRouter. Pass **Test agent mode** once with the Gemini model.
- **Gemini gives steadier results**: whole-video requests use
  temperature 0. Measured: the same accuracy (14.7% → 14.2% wrong) and
  half the difference between runs of the same video.
- Gemini 3.1 Flash-Lite (recommended) added to the Gemini model list.

## What's new in v1.9.1

- **More accurate and steadier descriptions** (OpenRouter models).
  Whole-video requests now ask for temperature 0. Measured on four
  different clips, three runs each: correct descriptions 51 → 83,
  wrong 24% → 17% (independent judge), and runs of the same video agree
  far more (a news clip used to give 3, 15 or 14 descriptions; now 16–18).
- **Check the whole video with the agent.** In the Player agent (F2), the
  new **Check the whole video** button goes through every description a
  minute of video at a time and gathers ONE list of proposed fixes, which
  you then accept, review or reject as usual. It tells you the time and
  cost first, says each part as it goes, and the same button stops it.
  Tested on 3 minutes of a film: 22 descriptions, 6 proposals, $0.005.
- The agent no longer offers an "edit" that keeps the same text.

## What's new in v1.9.0

**The Player agent (F2).** In the Player, press F2 (or the Agent button)
and ask about what you are watching, in your own words: "is the
description here right?", "what happens at the bridge?", "the old man
is called Hans". The agent looks at the video frames, reads the
descriptions and the dialogue, finds silent gaps, and can move the
player. It **changes nothing by itself**: it proposes, you hear a
summary, and you choose Accept all, Review one by one, or Reject all.
The project's subtitle file is copied aside before the first change,
and Undo is always there. Every step is spoken; the video pauses while
the agent is open. It remembers the conversation until you close the
Player, and remembers character names for the project.

- Works with OpenRouter models that pass **Settings > Test agent mode**
  (measured first: GLM 5.3 Flash, Gemini 3.1 Flash-Lite, Qwen3.8-Omni
  and Gemini 3.8 all pass). A question typically costs a fraction of a
  cent; above $0.02 it asks before continuing.
- **Ask More now looks at the picture.** It used to answer from the
  description text alone; it now sends the frame at the player's
  position with your question.
- **Fixed: Ask More and Explore Scene failed on a project opened later**
  ("No AI provider configured") unless a video had been processed in
  the same session. The AI is now set up when the app starts and after
  Settings.

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
