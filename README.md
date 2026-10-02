# Omni Describer Custom

An accessible audio-description tool for blind and visually impaired
users, built around NVDA. It downloads or opens a video, has an AI
describe what is SEEN at each moment, and plays the video with the
descriptions spoken in sync. Everything is operated by keyboard and
announced to the screen reader; the interface is in English and Malay.

- **Send the whole video to the AI** (default; Settings > AI): the AI
  watches the video in parts (5 minutes each) and places its own
  descriptions, given a transcript of the speech so it uses the gaps
  instead of describing what you can already hear. Optionally each
  description is then checked against the frames around it (Settings >
  General, Off by default).
- **Still pictures** (the box unticked): frames are extracted locally
  and described one by one, at most one description every 4 seconds;
  exact timing, suited to slides and screen recordings.
- **The Player agent (F2)**: ask about what you are watching; it looks
  at the video and proposes fixes that you accept or reject. **Check
  the whole video** goes through every description and gives one list
  of proposals.
- **Projects, import and export**: every job is saved as a project;
  descriptions can be imported from SRT, WebVTT or timed text, and
  exported to SRT or WebVTT, or as one spoken audio file. A video that
  already has descriptions plays at once, with no AI pass.

Providers: **OpenRouter** (GLM 5.3 Flash by default; any video-capable
model, listed with Fetch models), **Gemini** with your own key (Fetch
models works here too), MiniMax, OpenAI (still pictures) and any
OpenAI-compatible endpoint (Custom). **Test this model** checks any
provider's key and model with a real clip; **Test agent mode** unlocks
F2 for OpenRouter and Gemini models.

## Documentation

- [User guide (English)](doc/user-guide.md) and
  [Panduan pengguna (Melayu)](doc/panduan-pengguna.md) — also shipped
  inside the app folder (`_internal\doc`).
- [Developer guide](doc/developer-guide.md) and [AGENTS.md](AGENTS.md)
  (hard rules); the numbered pitfalls are in
  [doc/pitfalls.md](doc/pitfalls.md) and are required reading.
- [Plans](doc/plan.md) and the open checklist
  [doc/senarai-semak.md](doc/senarai-semak.md).
- What changed in each release: [CHANGELOG.md](CHANGELOG.md).
- Model measurements: [doc/perbandingan-model.md](doc/perbandingan-model.md).
- Adding a language: [doc/menambah-bahasa.md](doc/menambah-bahasa.md).

Version numbers: the last digit stops at 9, so 1.6.9 is followed by
1.7.0 (1.7.0 and 1.7.1 were first tagged 1.6.10 and 1.6.11).

## What's new in v1.9.7

- **The Player shows the agent OR the two older tools.** When the agent
  is ready (OpenRouter or Gemini, a key, and a model that passed Test
  agent mode), only **Agent (F2)** is shown: it looks at the video and
  answers questions itself. With no agent, **Ask More** and **Explore
  Scene** are shown instead. With a model not yet tested all three are
  shown, and the two older tools go away once the test passes. Changing
  Settings while the Player is open is followed.
- **Keys in the video area of the Player.** Tab to the video picture,
  then: **Space** plays or pauses, **Left/Right** jump 5 seconds
  (**Ctrl** with them: 10 seconds; **Ctrl+Shift**: one minute) and say the new position ("1:09 of
  24:30"), **Up/Down** change the video's volume by 10% and say it. The
  screen reader's own voice is not changed; the volume is remembered.
- **Scene Explorer no longer says "No AI configured" by mistake.** It
  said so while a long video's frames were still loading. It now says it
  is still loading, and a long video loads about 600 frames (a
  24-minute film used to take minutes).

## What's new in v1.9.6

Fixes from the owner's own log of 1 October, checked by two independent
audits so that nothing was left out.

- **Cancel works.** The progress dialog's Cancel was only noticed during
  the download; for a video already on the computer it did nothing for the
  whole job. It now stops every step within seconds: the speech
  transcript, compression, splitting, upload, waiting for the AI, the
  description check, still pictures and fast mode. Audio export has a
  Cancel button. In the Player agent, Ask becomes **Stop asking** while it
  works, and Close/Esc stops its work too. Closing Ask More or the Scene
  Explorer stops what they were doing.
- **The speech transcript is made once per project** and kept, instead of
  again on every attempt (3 to 6 minutes each time on a 24-minute video).
- **File > Open Project works again** (it crashed on every use since 1.7.6).
- **Errors are told in plain words** in the app language, with what to do,
  instead of raw technical text, and a failed job opens a message box that
  the screen reader reads. A provider that refuses the video as too large
  without saying its limit (OpenRouter's Alibaba upstream) now gets a
  smaller video, up to three times. Gemini uploads are retried after a
  dropped connection. OpenRouter now also waits as long as asked after
  "too many requests" and names a used-up daily limit.
- **The Player's time is right.** Without VLC the position could fall
  behind the sound; it now follows the real clock, and every question to
  the agent carries the current position. The timeline slider moves in
  seconds (arrows 5 s, Page Up/Down 30 s) and is read as "1:04 of 24:30";
  times are written 1:04 (and 1:02:05 past an hour).
- **One real progress bar for the whole job.** The screen reader used to
  hear only a seconds counter ("46s") during long steps, and the old
  Windows progress bar was not always reported. The progress window now
  has a standard progress bar (NVDA beeps and/or says the percentage,
  following NVDA's "Progress bar output" setting) with ONE percentage for
  the whole job: download, speech transcript (real Whisper progress), the
  AI step (Gemini's wait is estimated from earlier jobs) and the check. It
  never goes backwards. The step name is still said once when it changes,
  and the time left is shown when known.
- **F2 offers Test agent mode on the spot** when the chosen model has not
  passed it yet, and opens the agent if it passes.
- Closing the main window during a job no longer crashes; open Player and
  Editor windows close properly and keep their edits.
- Settings > General > Output Directory is now where export Save dialogs
  open. The Language box is shown above Description language.
- Tests can no longer change your real settings: one did, and pointed
  Gemini at a test address (repaired in your settings).

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

## Installing

Unzip `OmniDescriber-<version>-win64.zip` (about 305 MB) anywhere and
run `OmniDescriber.exe`. Nothing else is needed: ffmpeg, ffprobe,
ffplay and yt-dlp are inside the app folder, and a newer yt-dlp can be
installed from Help > Check for Updates. An API key is entered in
File > Settings... > AI Settings; press **Test this model** to check it.

To run from source instead: Python 3.13 on Windows, then
`python tools\fetch_binaries.py` once (the binaries are not in git and
are checked against pinned SHA-256 hashes), then `run.bat`. The log is
`%LOCALAPPDATA%\OmniDescriber\logs\omni_describer.log`.

## Standalone video describer (CLI + HTTP API)

`video_describer/` is an independent, headless pipeline that shares no
code with the GUI. It burns an `H:MM:SS` timestamp (dark box, top-left)
into every extracted frame, sends ALL frames base64-encoded in ONE
`glm-5.3-flash` request, trusts the model to READ the on-screen stamps,
then regex-parses the reply into an SRT and a JSON file named after the
video, in a folder `<video folder>\<video name>\` (`--out` overrides;
auto-batches above 150 frames; guards 5 MB / 6000 px per frame). Its
default endpoint is Zhipu direct (`https://open.bigmodel.cn/api/paas/v4`),
so `GLM_API_KEY` must be a Zhipu key, not an OpenRouter `sk-or-v1-` key.

```bat
:: describe a local video (SRT + JSON in <video folder>\<video name>\)
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
or Windows SAPI5 (`--tts-engine sapi`); one audio file per cue lands in
an `audio\` folder inside the output folder (no combined audio file).

This standalone tool predates the app's current engine and is not part
of the test gate; the app itself does not use it.

## Building

`build.bat` checks the pinned binaries, compiles, runs PyInstaller,
smoke-tests the real exe and writes `dist\OmniDescriber-<version>-win64.zip`,
printing `BUILD_ALL_OK`. Before a release: `run_gate.bat` twice
(`GATE_ALL_PASS`), then listen to the built exe with
`python tools\nvda_accessibility_check.py --frozen`. See
`doc/developer-guide.md`.
