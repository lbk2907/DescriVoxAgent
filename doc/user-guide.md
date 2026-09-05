# Omni Describer Custom — User Guide

An accessible audio-description tool for blind and visually impaired
users. It downloads or opens a video, extracts frames, sends them to an
AI vision provider, and plays the video in a built-in player that reads
the AI descriptions in sync with playback.

Versi Bahasa Melayu: `doc/panduan-pengguna.md`.

## Installing the exe version (no Python needed)

On a new computer without Python, use the ready-built package:

1. Get `OmniDescriber-<version>-win64.zip` (for example
   `OmniDescriber-1.5.3-win64.zip`; the version number increases with
   each release so builds are easy to tell apart) and unzip it to any
   folder, for example `C:\OmniDescriber`.
2. Double-click `OmniDescriber.exe` inside it. No installation is
   needed; this guide is also bundled in the `doc` folder.
3. For local video playback nothing else is required. For YouTube
   links, install `yt-dlp` and make sure it can be found through PATH.

The developer version (Python scripts) can still be started with
`run.bat` as described below.

## Starting the app

Double-click `run.bat` in the `omni-describer-custom` folder. The app
opens with its main window. The log file is written to:

`C:\Users\USER\AppData\Local\OmniDescriber\logs\omni_describer.log`

If anything odd happens (for example descriptions fail for some
frames), that log records the real cause of every failure.

## Step by step: describing one video

1. In the main window, pick the video source with one of the buttons:
   - **Local Video File**: a video file on your computer.
   - **Direct Video URL**: a direct link to a video file.
   - **YouTube Video URL**: a YouTube page link.
2. Choose an instruction preset (prompt) from the dropdown under
   "Preset Arahan". When you pick one, the full preset text immediately
   appears in the "Arahan untuk dihantar" box below, and the screen
   reader announces "Preset dipilih: <name>". You can read, edit, or
   add notes to that text before processing. The "default" preset
   explains everything visible in each frame in detail; other presets
   are shorter or focus on something specific (characters, on-screen
   text, and so on). Then press the **Open** button to start processing
   with that instruction. Changing the text in the box does not change
   the original preset.
3. A progress dialog accompanies the whole process and keeps updating:
   download (real percentage, MB, speed, ETA), merging, frame
   extraction ("Extracting frames: N"), AI analysis ("AI analysis:
   7/120 frames"), and saving.
4. You can press **Cancel** at any time. During AI analysis the process
   stops between frames and everything already finished is kept.
5. When done, the described-video player opens automatically with the
   descriptions loaded. If there are no descriptions, the player says
   "No descriptions available."

## Importing and exporting descriptions (File menu)

The File menu has four timeline functions:

- **Import descriptions from an SRT / VTT / text file**: pick one
  `.srt`, `.vtt`, or `.txt` file. Each timed line becomes one
  description in a **new project** (project name = file name), so
  existing projects are untouched. Simple text file format: one
  description per line, starting with a time, for example
  `0:05 A man walks into the room` or `00:10 - 00:14 He sits down`.
  Lines starting with `#` are ignored. Times can be written as `M:SS`,
  `H:MM:SS`, or plain seconds (for example `90.5`).
- **Export as SRT** and **Export as WebVTT**: save every description of
  the open project as a timed subtitle file, which can be reopened
  here or used with other video players/editors.
- **Export as Audio (spoken, synchronised)**: generate a single MP3
  (or WAV) file that speaks every description with your TTS voice at
  the right time. You can listen to it next to the video with any
  media player, without this app. Requires ffmpeg on PATH. Progress is
  shown while generating; voice, speed, and engine follow your TTS
  settings.

A common "describe by time" use: accept an SRT of descriptions
provided by someone else (or type your own in the simple text format),
import it, pick the same source video, and the player reads the
descriptions in sync during playback.

## Settings (File menu > Settings..., or the Settings... button)

- **General tab** (now the first tab):
  - **Language**: `en` (English) or `ms` (Malay).
  - **Frame Rate (FPS)**: how many frames per second of video are
    extracted for analysis (1, 2, 5, or 10). Higher FPS = more
    descriptions but slower and more expensive.
  - **Max frames per video (0 = no limit)**: an optional cost limit
    for long videos. The default `0` means no limit: every extracted
    frame is analysed (the original behaviour). If you set, for
    example, `100`, only the first 100 frames are sent to the AI, and
    the log notes "Frame cap reached". Timestamps stay on the full
    video timeline, so descriptions remain in sync with playback.
    Example: a 17-minute video at 5 FPS means about 5000 AI calls
    without a limit.
  - **Output Directory**: where exports are written.
- **AI tab**: provider (Gemini, MiniMax, OpenAI, GLM, or Custom), API
  key, model. **GLM** runs through OpenRouter by default: pick the
  `glm` provider, model `z-ai/glm-5.3-flash`, and paste your
  OpenRouter key (starting with `sk-or-v1-`); a direct Zhipu key also
  works through the Custom provider with base URL
  `https://open.bigmodel.cn/api/paas/v4`. The **Test Connection**
  button checks whether the settings you typed actually work: it sends
  one tiny question to the AI service using that key (no need to
  process a video). The result appears as text below the form and
  keyboard focus moves there so the screen reader keeps reading it.
  "OK: ..." means the key is valid; "Error: ..." means the key is
  wrong, there is no internet, or the base URL is wrong. The button
  tests the current form values, so you can test before pressing
  Apply.
  - **Full-video mode**: this checkbox is only enabled when the
    **Gemini or MiniMax** provider is selected. When enabled, the AI
    receives the **whole video file** (audio + visual), the AI watches
    it itself, and returns its own timestamped list of descriptions.
    No frames are extracted and there is no per-frame AI call — one
    upload and one call, so it is usually faster and cheaper for long
    videos, and descriptions cover sound/speech too, not just images.
    Status is announced throughout: "Uploading video to AI provider...",
    "AI is watching the video (processing)...", and "AI is writing
    descriptions...".
  The **GLM** provider is displayed as **OpenRouter** in the list. For
  OpenRouter, the model list only shows models that support video, and
  the **Fetch models** button reloads that list from the public
  OpenRouter catalog (free, no key or credit needed).
  - **Fast one-shot mode**: this checkbox is only enabled when the
    **OpenRouter (GLM)** provider is selected. Frames are extracted
    locally with a **burned-in H:MM:SS time stamp** on each frame
    (dark box, top-left corner), then **all frames go to the AI in ONE
    call** (for long videos, auto-split into batches of 150 images
    each). The AI reads those on-screen stamps itself, and the app
    snaps the times back onto the exact frame grid — so even if the AI
    misreads a stamp, description timestamps stay in sync with
    playback. One download, one (or few) AI calls, and frames are
    analysed locally. This is the fastest and cheapest way to use GLM.
  - **Full-video mode is also available for OpenRouter**: models whose
    catalog lists video input (for example `z-ai/glm-5.3-flash`) can
    accept **one full video file** in one request (empirically
    verified: a 60-second video used about 9k tokens). The AI watches
    it itself, including sound and speech, and gives its own
    timestamps. Long videos are split into parts (default about 10
    minutes each) and sent part by part; timestamps are stitched back
    into one timeline. Large parts (above about 50 MB) are compressed
    first — verified against OpenRouter: a 50.7 MB video uploaded
    successfully, about 98 MB is rejected. The two checkboxes are
    mutually exclusive.
- **TTS tab**: speech engine, voice, speech speed.

Processing notice: when processing finishes, a dialog shows
"Processing finished! N descriptions generated." If the AI fails or
returns no usable text, an error dialog explains the follow-up steps
(check the API key via Test Connection), an empty project is **not**
saved silently, and opening a project without descriptions warns with
the same follow-up steps.

The progress dialog shows the phases clearly from start to end:
"Loading video information..." (metadata check, can take a few seconds
for URLs), "Download: percentage, MB, speed, ETA" (separate video and
audio streams), "Merging video and audio with ffmpeg...", "Extracting
frames: N frames", "AI analysis: N/M frames", "Saving project...", and
"Download finished" once the streams are done. In full-video mode the
frame extraction/analysis phases are replaced by "Uploading video to
AI provider: percent", "AI is watching the video (processing)...", and
"AI is writing descriptions..." — no frame phrases are announced
because no frames are involved.

## How processing works (and why)

- **The video is downloaded only once.** The app never "downloads per
  frame". One full download (video + audio streams merged by ffmpeg)
  is enough for the whole description.
- **Frame mode (default):** frames are extracted locally from that
  video according to your FPS setting. Each frame carries its own
  timestamp, for example 0.0s, 0.2s, 0.4s at 5 FPS. Only the frames
  (images), not the full video file, are sent to the AI; the app
  attaches each frame's timestamp to the text the AI returns.
- **Full-video mode (Gemini or MiniMax, checkbox in the AI tab):** one
  full video file is uploaded (to the Gemini Files API or MiniMax
  Files API), the AI watches the video (including audio) itself, and
  timestamps come from the AI as well. This suits descriptions that
  cover sound and speech, or when you want a one-step process. Other
  providers (OpenAI, Custom) do not accept local video files, so this
  mode is not available for them.
- **Fast one-shot mode (GLM, checkbox in the AI tab):** frames are
  extracted locally like frame mode, but each frame is labelled with a
  burned-in `H:MM:SS` stamp on top of the image. All frames go in one
  AI call (batches of at most 150 images), the AI reads the stamps,
  and the app corrects the times onto the exact frame grid before
  saving. Good when you want frame-mode speed with AI call costs close
  to full-video mode.
- In full-video mode with OpenRouter (GLM), long videos are split into
  consecutive parts and every part carries context into the next one
  (part X of Y, the part's start time, and a short summary of what
  happened just before). This keeps character names consistent and
  avoids phrases like "the video starts with..." in the middle of a
  video. All modes produce the same kind of timestamped descriptions
  in sync with playback; the difference is only who decides the times
  (the extraction process versus the AI) and what gets sent (images
  versus one video file).

## Projects

Projects are stored in `Documents\OmniDescriber\projects` (one folder
per project with a SQLite database and a permanent copy of every frame
used, so the player keeps working after cleanup). Use the **File**
menu to create, open, or save projects.

## The described-video player

- The player shows the real video duration on the timeline.
- During playback, the current frame's description is spoken (TTS) and
  shown as text.
- Use the player controls to pause, seek, and navigate descriptions.

## Scene Explorer

From the player you can open the Scene Explorer to inspect frames one
by one: press the left/right arrow keys to move between frames, `D`
for the full AI description of the current frame, `L` for the list of
objects in the frame, and `Escape` to close.

## Standalone video describer (command line + HTTP API)

Besides the GUI app, this repository carries a standalone
`video_describer` package (no code shared with the GUI). It burns an
`H:MM:SS` stamp (dark box, top-left corner) onto every frame extracted
by ffmpeg, sends ALL frames base64-encoded in ONE `glm-5.3-flash`
request, lets the model READ the on-screen stamps, then parses the
`H:MM:SS - description` lines into `description.srt` and
`description.json` (auto-batches above 150 frames; guards of 5 MB and
6000 px per frame).

```bat
:: Describe one local video (SRT + JSON written next to it)
set GLM_API_KEY=your-key
python -m video_describer describe video.mp4 --fps 1 --tts

:: Parse model text only (H:MM:SS - description lines)
python -m video_describer parse model_output.txt

:: HTTP API on 127.0.0.1:8765
python -m video_describer serve --port 8765
```

API endpoints: `GET /health`, `POST /describe` (JSON body
`{"video_path": "...", "fps": 1, "tts": false}`),
`POST /describe/upload?name=v.mp4` (raw video bytes), and
`POST /parse` (parse only). The API key comes from the request body,
the `X-API-Key` header, or the `GLM_API_KEY` environment variable.
TTS narration (`--tts`) uses edge-tts (default `ms-MY-OsmanNeural`) or
Windows SAPI5 (`--tts-engine sapi`); cue audio files and the combined
audio are placed in an `audio/` folder next to the output.

## If something goes wrong

1. Read the log at
   `C:\Users\USER\AppData\Local\OmniDescriber\logs\omni_describer.log`;
   every frame error is recorded with its real cause.
2. Check the AI settings (API key, model, base URL) and press
   **Test**.
3. For long videos, consider a lower FPS (for example 1) or set **Max
   frames per video**.
