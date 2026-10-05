# DescriVox Agent

*Formerly **Omni Describer Custom** (renamed in v2.0.0). Settings,
keys and projects keep their old folders (`%APPDATA%\OmniDescriber`,
`Documents\OmniDescriber`), so nothing is lost or moved.*

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

## What's new in v2.0.2

- **Opening a project opens the Player.** File > Open Project (and
  opening the existing project when you pick the same video again) used
  to only write a line in the Status Log. Now, when the project has
  descriptions, the Player opens with the focus on the video picture; a
  Player still showing another project is closed first, so two videos
  never play at once. An empty project still tells you what to do.
- **"1 description", not "1 descriptions"** in the project list and the
  ten other English messages that count descriptions.

## What's new in v2.0.1

- **Contributor-ready:** `pytest tests/` now runs the whole standalone
  gate (76/76 scripts) through a pytest bridge; CONTRIBUTING.md documents
  setup, the three equivalent gate commands and the repo conventions.
- **Accessibility fix:** queued speech that fails now falls back to the
  focus-announcement path, so a screen reader never misses a message.
- **Diagrams:** UML package + module views (PlantUML sources) live in
  `doc/diagrams/`; rendered PNGs stay out of the source zip.
- Setup files, API keys and projects are untouched — this is a
  developer-facing release.

## What's new in v2.0.0

- **New name: DescriVox Agent** (formerly Omni Describer Custom). The
  app does the same work; the name now says what it is: a voice that
  describes (Descri + Vox), with an agent that can look at the video
  and answer you. The window title, the About box, the program file
  (`DescriVox.exe`) and the download (`DescriVox-Agent-<version>-win64.zip`)
  carry the new name. Your settings, API keys and projects are kept:
  their folders keep the old name (`%APPDATA%\OmniDescriber`,
  `Documents\OmniDescriber`), so nothing has to be moved.
- **Player keys, checked for real:** in the video picture, Up/Down
  change the volume and the focus stays put (it used to jump to the
  status line); Tab and Shift+Tab move on; F2 opens the agent from
  anywhere in the Player and says why when it cannot.

## Installing

Unzip `DescriVox-Agent-<version>-win64.zip` (about 305 MB) anywhere and
run `DescriVox.exe`. Nothing else is needed: ffmpeg, ffprobe,
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
smoke-tests the real exe and writes `dist\DescriVox-Agent-<version>-win64.zip`,
printing `BUILD_ALL_OK`. Before a release: `run_gate.bat` twice
(`GATE_ALL_PASS`), then listen to the built exe with
`python tools\nvda_accessibility_check.py --frozen`. See
`doc/developer-guide.md`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, the test gate and
conventions, and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Licence

DescriVox Agent is free software under the GNU General Public License
version 3 (GPL-3.0-only) — see [LICENSE](LICENSE). Bundled third-party
programs (FFmpeg, VLC, ...) keep their own licences, listed in
[NOTICE.md](NOTICE.md).
