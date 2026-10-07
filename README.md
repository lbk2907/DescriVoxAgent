# DescriVox Agent

[![CI (light)](https://github.com/lbk2907/DescriVoxAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/lbk2907/DescriVoxAgent/actions/workflows/ci.yml)
[![Latest tag](https://img.shields.io/github/v/tag/lbk2907/DescriVoxAgent?label=version)](https://github.com/lbk2907/DescriVoxAgent/tags)
[![Licence: GPL-3.0-only](https://img.shields.io/badge/licence-GPL--3.0--only-blue.svg)](LICENSE)
![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)
![Screen reader: NVDA first](https://img.shields.io/badge/screen%20reader-NVDA%20first-green.svg)

**AI audio description for blind and visually impaired people.** DescriVox Agent downloads
or opens a video, has an AI describe what is SEEN at each moment, and plays the video with
the descriptions spoken in sync. Everything is operated by keyboard and announced to the
screen reader; the interface is in English and Malay.

*Formerly **Omni Describer Custom** (renamed in v2.0.0). Settings, keys and projects keep
their old folders (`%APPDATA%\OmniDescriber`, `Documents\OmniDescriber`), so nothing is lost
or moved.*

## Contents

- [Features](#features)
- [Accessibility](#accessibility)
- [Requirements](#requirements)
- [Installing](#installing)
- [Quick start](#quick-start)
- [Documentation](#documentation)
- [What's new](#whats-new-in-v212)
- [Standalone video describer (CLI + HTTP API)](#standalone-video-describer-cli--http-api)
- [Building from source](#building-from-source)
- [Contributing](#contributing)
- [Security](#security)
- [Licence](#licence)

## Features

- **Send the whole video to the AI** (default; Settings > AI): the AI watches the video in
  parts (5 minutes each) and places its own descriptions, given a transcript of the speech
  so it uses the gaps instead of describing what you can already hear. Optionally each
  description is then checked against the frames around it (Settings > General, Off by
  default).
- **Still pictures** (the box unticked): frames are extracted locally and described one by
  one, at most one description every 4 seconds; exact timing, suited to slides and screen
  recordings.
- **One name for every person:** names heard in the dialogue or shown on screen are used
  from start to end; **Player > Characters...** gives someone a real name in every
  description at once.
- **The Player agent (F2):** ask about what you are watching; it looks at the video and
  proposes fixes that you accept or reject. **Check the whole video** goes through every
  description and gives one list of proposals. Nothing changes without your approval, and
  every batch can be undone.
- **Projects, import and export:** every job is saved as a project; descriptions can be
  imported from SRT, WebVTT or timed text, and exported to SRT or WebVTT, or as one spoken
  audio file. A video that already has descriptions plays at once, with no AI pass.
- **Providers:** **OpenRouter** (GLM 5.3 Flash by default; any video-capable model, listed
  with Fetch models), **Gemini** with your own key (Fetch models works here too), MiniMax,
  OpenAI (still pictures) and any OpenAI-compatible endpoint (Custom). **Test this model**
  checks any provider's key and model with a real clip; **Test agent mode** unlocks F2 for
  OpenRouter and Gemini models.

## Accessibility

The main user is blind and uses NVDA, so accessibility is the first requirement, not a
feature:

- every control has a name a screen reader can read, and every status change is announced;
- long jobs show one progress bar with a single percentage that never goes back;
- the Player's video area has its own keys (Space, arrows, Ctrl and Ctrl+Shift for longer
  jumps) and F2 works anywhere in the Player;
- accessibility is verified by **listening** through NVDA with the tools in `tools/`, never
  only by reading the code.

## Requirements

- Windows 10 or 11 (64-bit).
- A screen reader is recommended (built and tested with NVDA); the app also speaks through
  SAPI when no screen reader is running.
- An API key for at least one provider (OpenRouter or Gemini recommended). OpenRouter needs
  a balance of at least 1 USD for video requests.
- About 750 MB of disk space for the app folder.

## Installing

1. Download `DescriVox-Agent-<version>-win64.zip` (about 305 MB).
2. Unzip it anywhere and run `DescriVox.exe`. Nothing else is needed: ffmpeg, ffprobe,
   ffplay and yt-dlp are inside the app folder, and a newer yt-dlp can be installed from
   **Help > Update YouTube downloader**. From the release after 2.1.2 the app updates
   itself: **Help > Check for Updates** (it also checks each time it opens).

The log is `%LOCALAPPDATA%\OmniDescriber\logs\omni_describer.log`.

## Quick start

1. **File > Settings... > AI Settings:** choose a provider, paste your API key, press
   **Test this model** (Alt+T).
2. In the main window choose **Local Video File**, **YouTube Video URL** or **Direct Video
   URL**, pick a prompt preset, and press **Open**.
3. When the descriptions are ready the **Player** opens: Space plays and pauses, the arrows
   move through the video, and **F2** opens the agent.

The full walkthrough is in the [user guide](docs/user-guide.md).

## Documentation

| Document | What it covers |
|---|---|
| [User guide](docs/user-guide.md) | Every window, setting and shortcut (also shipped inside the app folder) |
| [Developer guide](docs/developer-guide.md) | Architecture, isolation variables, rules that are easy to break |
| [AGENTS.md](AGENTS.md) | Hard rules for every contributor and coding agent |
| [Pitfalls](docs/pitfalls.md) | Numbered lessons from real bugs — required reading |
| [Plan](docs/plan.md) and [checklist](docs/checklist.md) | Plans, decisions, and open work |
| [Model comparison](docs/model-comparison.md) | Measurements behind every default |
| [Adding a language](docs/adding-a-language.md) | Translating the interface |
| [CHANGELOG.md](CHANGELOG.md) | What changed in each release |

Version numbers: the last digit stops at 9, so 1.6.9 is followed by 1.7.0 (1.7.0 and 1.7.1
were first tagged 1.6.10 and 1.6.11).

## What's new in v2.1.3

- **DescriVox Agent updates itself.** **Help > Check for Updates** checks for a newer version,
  reads what is new, and with **Download and install** downloads it, checks it, closes the
  app, puts the new version in place and opens it again; your settings and projects are kept
  and the old version is kept as `DescriVox.previous`. It also checks quietly each time the
  app opens (Settings can turn that off). Every release is signed with the author's own key,
  and the app installs nothing else. yt-dlp now has its own item, **Help > Update YouTube
  downloader**. This is the last version you have to download by hand.
- **The agent says when it cannot see something** (F2): "I cannot see that clearly", with the
  times it looked at, instead of a guess.

## What's new in v2.1.2

- **File > New Project is useful now.** It used to make an EMPTY project that nothing used
  (describing a video made another one) and that stayed in Open Project as "0
  descriptions". Now it asks for a name, then for the video (local file, YouTube or a
  direct URL); choose a preset and press Open, and the project gets your name.

## What's new in v2.1.1

- **Documentation to GitHub standard, all in English.** The guide shipped inside the app
  folder is now in `_internal\docs`. On GitHub: `docs/` with English file names, a
  security policy (`SECURITY.md`), issue forms for bug reports (with screen-reader fields)
  and feature requests, and a pull request template. The README has badges, contents,
  requirements and a quick start. The Malay user guide was removed; the app's interface
  is unchanged and stays in English and Malay.

## Standalone video describer (CLI + HTTP API)

`video_describer/` is an independent, headless pipeline that shares no code with the GUI.
It burns an `H:MM:SS` timestamp (dark box, top-left) into every extracted frame, sends ALL
frames base64-encoded in ONE `glm-5.3-flash` request, trusts the model to READ the on-screen
stamps, then regex-parses the reply into an SRT and a JSON file named after the video, in a
folder `<video folder>\<video name>\` (`--out` overrides; auto-batches above 150 frames;
guards 5 MB / 6000 px per frame). Its default endpoint is Zhipu direct
(`https://open.bigmodel.cn/api/paas/v4`), so `GLM_API_KEY` must be a Zhipu key, not an
OpenRouter `sk-or-v1-` key.

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
`{"video_path": "...", "fps": 1, "tts": false}`), `POST /describe/upload?name=v.mp4` (raw
video bytes), and `POST /parse` (parse only). The API key comes from the request body, the
`X-API-Key` header, or the `GLM_API_KEY` environment variable. TTS narration (`--tts`) uses
edge-tts (default `ms-MY-OsmanNeural`) or Windows SAPI5 (`--tts-engine sapi`); one audio file
per cue lands in an `audio\` folder inside the output folder (no combined audio file).

This standalone tool predates the app's current engine and is not part of the test gate;
the app itself does not use it.

## Building from source

Python 3.13 on Windows:

```bat
git clone https://github.com/lbk2907/DescriVoxAgent
cd DescriVoxAgent
py -3.13 -m pip install -e .[dev]
python tools\fetch_binaries.py
run.bat
```

The binaries are not in git; `tools\fetch_binaries.py` downloads them and checks pinned
SHA-256 hashes. `build.bat` checks the binaries, compiles, runs PyInstaller, smoke-tests the
real exe, writes `dist\DescriVox-Agent-<version>-win64.zip`, backs up the source code and
prints `BUILD_ALL_OK`. Before a release: `run_gate.bat` twice (`GATE_ALL_PASS`), then listen
to the built exe with `python tools\nvda_accessibility_check.py --frozen`. See the
[developer guide](docs/developer-guide.md).

## Contributing

Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) (setup, the test
gate, conventions) and [AGENTS.md](AGENTS.md). Use the issue templates for bug reports and
feature requests. Everyone is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Please do not report security problems in public issues. See [SECURITY.md](SECURITY.md).

## Licence

DescriVox Agent is free software under the GNU General Public License version 3
(GPL-3.0-only) — see [LICENSE](LICENSE). Bundled third-party programs (FFmpeg, VLC, ...) keep
their own licences, listed in [NOTICE.md](NOTICE.md).
