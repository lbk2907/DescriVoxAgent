# Omni Describer Custom — User Guide

An accessible audio-description tool for blind and visually impaired
users. It downloads or opens a video, has an AI describe what is SEEN
at each moment, and plays the video in a built-in player that speaks
the descriptions in sync with playback. Everything works from the
keyboard and is announced to your screen reader.

Versi Bahasa Melayu: `doc/panduan-pengguna.md`.

## Installing the exe version (no Python needed)

On a new computer without Python, use the ready-built package:

1. Get `OmniDescriber-<version>-win64.zip` (for example
   `OmniDescriber-1.9.5-win64.zip`; the version number increases with
   each release so builds are easy to tell apart) and unzip it to any
   folder, for example `C:\OmniDescriber`.
2. Double-click `OmniDescriber.exe` inside it. No installation is
   needed; this guide is also bundled in the `_internal\doc` folder.
3. Nothing else needs installing. ffmpeg, ffprobe, ffplay and yt-dlp
   are bundled in the app's `_internal\bin` folder. Do not delete it —
   without it YouTube downloads, frame extraction and the video's sound
   all stop working. If one of them goes missing (antivirus quarantine,
   for instance) the app tells you when it starts rather than failing
   silently later.
4. Open **File > Settings...**, go to the **AI Settings** tab, paste
   your API key and press **Test this model** (see Settings below).

The developer version (Python scripts) is started with `run.bat` in the
`omni-describer-custom` folder instead.

## The log file

The log is written to:

`%LOCALAPPDATA%\OmniDescriber\logs\omni_describer.log`

If anything odd happens (for example a job fails), that log records
the real cause of every failure.

## Step by step: describing one video

1. In the main window, pick the video source with one of the buttons:
   - **Local Video File**: a video file on your computer.
   - **Direct Video URL**: a direct link to a video file.
   - **YouTube Video URL**: a YouTube page link.
2. Choose an instruction preset from the **Prompt Preset** list. When
   you pick one, its full text immediately appears in the "Prompt to
   send" box below, and the screen reader announces "Preset selected:
   <name>". You can read, edit, or add notes to that text before
   processing. Then press the **Open** button to start processing with
   that instruction. Changing the text in the box does not change the
   original preset.

   The presets follow international audio-description standards (DCMP
   Description Key, Netflix style guide, W3C/WAI, ADLAB). Descriptions
   are deliberately **few and short**: they do not re-describe a
   background that has not changed, and do not repeat dialogue or
   sounds you can already hear. Silence means nothing new to see.

   Choose a preset by the kind of video, not by genre:

   | Preset | When to use it |
   |---|---|
   | `default` | Most videos. Start with this one. |
   | `tight` | Almost non-stop talking; very short gaps. |
   | `extended` | Documentaries, tutorials, slow videos — room for fuller descriptions. |
   | `foreign` | A language you do not understand. Besides the picture, it conveys what is said. |
   | `suspense` | Horror or suspense. Keeps dramatic silences and gives nothing away. |
   | `children` | Children's content: simple words, short sentences. |
   | `onscreen_text` | Slides, menus, code, charts — on-screen text read in order. |

   Each preset has a Malay version. Which version is listed follows the
   app's own language (**Settings > General > Language**); the
   **Description language** setting only decides the language the AI
   writes in.
3. A progress dialog accompanies the whole process: download (real
   percentage, MB, speed, ETA), merging, then either uploading and the
   AI watching the video, or extracting and analysing still pictures,
   and saving.
4. You can press **Cancel** (or Esc) at any time, also after the
   download has finished. The job stops within a few seconds, whatever
   step it is in. What is kept:
   - an unfinished download is kept and continues next time;
   - with still pictures, the descriptions made so far are saved;
   - with the whole video, a cancelled job saves no descriptions, but
     the speech transcript is kept, so the next attempt skips it.
5. When done, the described-video player opens automatically with the
   descriptions loaded. If there are no descriptions, the player says
   "No descriptions available."

## Importing and exporting descriptions (File menu)

The File menu has four timeline functions:

- **Import Descriptions from SRT / VTT / text file...**: pick one
  `.srt`, `.vtt`, or `.txt` file. Each timed line becomes one
  description in a **new project** (project name = file name), so
  existing projects are untouched. Simple text file format: one
  description per line, starting with a time, for example
  `0:05 A man walks into the room` or `00:10 - 00:14 He sits down`.
  Lines starting with `#` are ignored. Times can be written as `M:SS`,
  `H:MM:SS`, or seconds with a decimal point or an `s` (for example
  `90.5` or `90s`). A bare whole number such as `90` is NOT read as a
  time, so a line that starts with a year or a count is ignored.
- **Export as SRT...** and **Export as WebVTT...**: save every
  description of the open project as a timed subtitle file, which can
  be reopened here or used with other video players/editors.
- **Export as Audio (spoken, synchronized)...**: generate a single MP3
  (or WAV) file that speaks every description with your TTS voice at
  the right time. You can listen to it next to the video with any
  media player, without this app. Uses the bundled ffmpeg. Progress is
  shown while generating, with a **Cancel** button (a cancelled export
  leaves no half-written file); voice, speed, and engine follow your
  audio settings.

A common "describe by time" use: accept an SRT of descriptions
provided by someone else (or type your own in the simple text format),
import it, pick the same source video, and the player reads the
descriptions in sync during playback.

### Play a video that already has descriptions

The **"Play Video with Existing Descriptions"** button (second under
Tab, right after "Local Video File") is for a video whose descriptions
already exist — made here earlier, or written by hand.

1. Choose the video.
2. If an `.srt`, `.vtt` or `.txt` with the SAME name sits beside it,
   the app offers that file. Otherwise you pick one yourself.
3. The player opens straight away.

No AI pass, no cost, no waiting. The video is copied into the project
folder, so it still plays if the original is moved or a USB stick is
unplugged.

## Settings (File > Settings..., or the Settings... button)

The dialog has three tabs: **General**, **AI Settings** and **Audio
Output**.

### General tab

- **Language**: the language of the app itself (English, Malay, or a
  language file you added).
- **Description language (AI answers)**: the language the AI writes
  in.
- **Frame Rate (FPS)** and **Max frames per video (0 = no limit)**:
  used only for still pictures (the whole-video box unticked). Higher
  FPS = more pictures, slower and more expensive; the cap limits cost
  on long videos without moving descriptions off the video's timeline.
- **Never leave the AI blind for longer than (seconds, 0 = off)**:
  still pictures only; makes sure a long unchanging shot still gets a
  picture now and then.
- **Video chunk length for AI analysis (seconds per part)**: when the
  whole video is sent, long videos go in parts of this length. The
  default is 300 seconds (5 minutes); shorter parts were measured to
  place descriptions more accurately.
- **Check descriptions against the video (when sending the whole
  video)**: see "Check descriptions against the video" below. **Off**
  by default.
- **Keep full resolution for big videos (split instead of shrinking)**:
  for slides and tutorials, where shrinking would make on-screen text
  unreadable.
- **Speech-to-text (when the video has no subtitles)**: how the app
  gets a transcript of what is said, so the AI knows the dialogue and
  where the silences are. **Automatic** uses Grok if an xAI key is set,
  otherwise **Local Whisper** (free, offline, slower). **Off** describes
  the picture only.
- **Output Directory**: the folder the export Save dialogs (SRT,
  WebVTT, audio) open in. Each export still asks where to save.

The **Language** box is above the **Description language** box (it was
the other way round before 1.9.6).

### AI Settings tab

- **Provider**: **OpenRouter** (the default for new users, model
  `z-ai/glm-5.3-flash`, key starting with `sk-or-v1-`), **Gemini**
  (your own Google key), **MiniMax**, **OpenAI**, or **Custom** (any
  OpenAI-compatible or Anthropic-format endpoint: **Base URL**, **API
  Format**, and a **Model name** box below the Model list).
- **Model**: for OpenRouter and Gemini the list shows only models that
  can watch a video. **Fetch models** reloads it: from the public
  OpenRouter catalog (free, no key or credit needed), or for Gemini by
  asking Google which models your key can use (free, no quota used).
  The list is saved for next time. The recommended models come first
  and are read as "Recommended: ...". Each line gives the model name,
  then (OpenRouter) "watches and hears the video" or "watches only,
  uses a transcript", then the price per million tokens.
- **Test this model** (Alt+T): checks the key and model with a real
  clip, for EVERY provider. OpenRouter, Gemini and MiniMax get a
  6-second test video (does it see and hear it?); OpenAI and Custom get
  one picture. The result is read by your screen reader straight away
  and costs a fraction of a cent. (The old Test Connection button
  was removed in 1.9.2; Test this model replaces it.)
- **Test agent mode** (Alt+A): OpenRouter and Gemini only. Checks
  whether the model can run the Player agent (F2); a model must pass
  before F2 uses it.
- **Send the whole video to the AI (recommended)** — formerly
  "Full-video mode", ticked by default for new users. Enabled for
  OpenRouter, Gemini and MiniMax. Ticked: the AI watches the whole
  video and places each description itself. Unticked: the app sends
  still pictures one at a time (OpenAI and Custom always work this
  way).
- **Fast picture mode (OpenRouter): all pictures in one request**:
  only when the box above is unticked. Each picture gets its `H:MM:SS`
  time burned in (dark box, top-left corner) and all pictures go to the
  AI in one request (batches of at most 150); the app snaps the times
  back onto the exact picture grid. The two boxes exclude each other.

### Audio Output tab

Speech engine (**TTS Engine**: Edge TTS, SAPI5 (Windows), OpenAI TTS
or **My screen reader**), **Voice** and **Speed**.

**"My screen reader"** is labelled with the reader that was found (for
example "My screen reader (NVDA)") and speaks through NVDA, JAWS, ZDSR
or whatever is running. With it selected, Voice and Speed are disabled
— your screen reader owns those; change them in the reader's own
settings. The Player's automatic pause still works: since 1.7.1 the app
listens to the reader's own sound to know when a description has
finished. If it cannot, the Player says so instead of offering a box
that does nothing.

On a computer with **no** screen reader at all, the app speaks status
messages itself through Windows SAPI or OneCore. When a reader is
running it stays quiet, so nothing is read out twice.

## While a video is processed

The progress dialog shows each phase: "Loading video info...",
download (percentage, MB, speed, ETA, separate video and audio
streams), "Merging video and audio with ffmpeg...", then:

- whole video, first: "Looking for a transcript of the speech...";
  when needed "Splitting long video into parts..." and "Preparing video
  for upload (compressing)...". Then it depends on the provider:
  - **OpenRouter**: "Preparing the video for sending...", "Uploading
    video to the AI provider..." with a percentage, "The AI is watching
    the video and writing descriptions..." with a time estimate ("About
    4 min left.") learned from your earlier jobs on the same model, and
    "Reading the AI's answer...". If the AI takes longer than expected,
    the app says "Taking longer than usual; still working."
  - **Gemini** and **MiniMax**: "Uploading video to the AI provider:
    N%", then (Gemini) "The AI is watching the video (processing)..."
    and "The AI is writing descriptions...". There is no time estimate
    here.
  - With the description check on: "Checking the descriptions against
    the video...".
- still pictures: "Extracting frames: N frames", "AI analysis: N/M
  frames".

and finally "Saving project...". **Every change of phase and part is
read automatically by your screen reader** (for example "Part 2 of 2.
Uploading video to the AI provider..."), without interrupting what it
is reading, so you do not need to check the dialog yourself.

When processing finishes, a dialog shows "Processing complete! N
descriptions generated." If the job fails, a message box titled
"Processing failed" opens, so your screen reader reads the reason at
once. The reason is in plain words in the app's language (see "If
something goes wrong" below); an empty project is **not** saved
silently.

If you close the main window while a job is running, the job is
stopped safely and the Player and Editor windows are closed properly,
with your edits saved.

### Cancel stops quickly, everywhere

Since 1.9.6 the progress window has ONE progress bar for the whole job
(download, speech transcript, the AI step, the check). NVDA reports it as
it moves - beeps, the percentage spoken, or both, as set in NVDA's
Settings > Object presentation > Progress bar output. The bar never goes
backwards; for a step with no percentage of its own (Gemini watching the
video) it moves by an estimate learned from earlier jobs. The step name is
said once when it changes, and "About N min left" is shown when known.

Since 1.9.6, Cancel works in every step and does not keep you waiting:

- the progress dialog's **Cancel** (or Esc), also after the download
  has finished;
- the speech transcript stops within a few seconds;
- an upload or a request to the AI stops within about half a second;
- the description check and still-picture analysis stop too;
- **Export as Audio** has its own **Cancel** button;
- closing the **Scene Explorer** stops its loading, and **Cancel** in
  **Ask More** abandons the question;
- in the Player agent, **Stop asking**, **Stop checking**, **Close**
  and Esc stop its work (see "The Player agent (F2)").

### Interrupted downloads

An interrupted download **continues from where it stopped** instead of
starting over. Press Cancel, close the app, or lose the connection —
open the same video again and it carries on. A finished video is never
touched, and a project that already has its video does not re-download
at all.

An interrupted **upload** to the AI is not resumed, with any provider.
A failed Gemini upload is tried again automatically, up to three times
in all, each time from the start. When the app had to compress the
video before sending it (OpenRouter), the compressed copy is kept, so a
retry skips the re-encode.

### The speech transcript is made once

The transcript of the speech is made once per project and kept in the
project folder (`media\transcript.json`). A second attempt on the same
video, after a Cancel or a failure, uses it again instead of
transcribing the video again.

## How processing works (and why)

- **The video is downloaded only once.** One full download (video +
  audio streams merged by ffmpeg) is enough for the whole description.
- **Whole video (default):** the video file is sent (uploaded to the
  Gemini or MiniMax Files API, or sent inline to OpenRouter) and the AI
  watches it and gives its own timestamps. Long videos are split into
  parts (5 minutes by default) and every part carries context into the
  next (part X of Y, its start time, and a short summary of what came
  before), so character names stay consistent. Large parts are
  compressed first. Most models cannot hear the video, so the app
  gives the AI a transcript of the speech (from the video's subtitles,
  or speech-to-text) and a count of how many words fit in each silence.
- **Still pictures:** frames are extracted locally according to your
  FPS setting, and each one is described with its own exact timestamp,
  at most one description every 4 seconds. Best for slides and screen
  recordings; for films it gives far more, choppier descriptions.
- All modes produce the same kind of timestamped descriptions; the
  difference is who decides the times (the extraction versus the AI)
  and what gets sent (pictures versus one video file).

## Projects

Every video you process is saved as a **project**: the video, the AI's
descriptions and the SRT file. Opening a project again does NOT call
the AI again, which saves time and cost.

Projects live in `Documents\OmniDescriber\projects`, one folder per
project, named after it, for example `Sintel (48)`. The number tells
apart two videos with the same title. Inside: `project.db` (the
descriptions) and a `media` folder (the video, `descriptions.srt`
and, after a whole-video job, `transcript.json`, the speech transcript).

**File > Open Project...** lists every project, newest first. Each line
gives the name, how many descriptions it has and the date, for example
"Sintel — 79 descriptions — 28/09/2026 11:30". Buttons:

- **Open** (Alt+O): load it to play, edit or export. (In 1.7.6 to
  1.9.5 this crashed; it works again since 1.9.6.)
- **Rename** (Alt+N): give it a new name; its folder is renamed too. If
  its video is playing at that moment, the folder follows the next time
  the app starts.
- **Remove** (Alt+R): delete the project completely, after confirming.

## Check descriptions against the video (Settings > General)

When the whole video is sent, the AI sometimes describes the right
event at the wrong moment. **Check descriptions against the video**
(**Off** by default) compares each description with the frames around
it, then moves it to the real moment or removes it if it is nowhere to
be seen. Measured on two films: about half as many wrong descriptions.
Adds a few minutes and a small cost. If the check fails, the original
descriptions are kept.

- **Auto (the app chooses)**: Most accurate for long videos, Keep all
  for short ones.
- **Most accurate (may remove a few)**: fewest wrong.
- **Most descriptions**: the most correct ones.
- **Keep all, only fix timing**: nothing is removed.

## Your own language (Help > Translation Report)

Language files you make or correct live in
`%APPDATA%\OmniDescriber\locales\` and survive updates. After an
update, **Help > Translation Report...** says how many lines of your
language are still untranslated and saves exactly those, with the
English text, as `<code>.missing.json` in that folder. Full guide (in
Malay): `doc/menambah-bahasa.md`.

## Check for Updates (Help menu)

YouTube changes often, and an older yt-dlp (the program that downloads
videos) can stop working. **Help > Check for Updates...** says which
yt-dlp is in use and whether a newer one exists; the result is read out
at once.

- **Update** (Alt+U): download the new version straight from yt-dlp's
  official GitHub. It is installed ONLY if its fingerprint (SHA-256)
  matches the publisher's official list and the program reports the
  right version; otherwise nothing changes.
- **Use bundled version** (Alt+B): go back to the yt-dlp shipped with
  the app.

The new version is kept in `%LOCALAPPDATA%\OmniDescriber\tools`; the
app's own copy is never overwritten. Once a week, when the app opens,
it checks quietly and only **announces** an update; nothing is
downloaded unless you choose to. If a YouTube download fails, the log
points to this menu.

## The described-video player

- The player shows the real video duration on the timeline.
- During playback, the current description is spoken and shown as
  text, with the upcoming one below it.
- **Play**, **Stop**, **<< 10s** and **10s >>** control playback;
  **Read Description** speaks the current one again.
- **Pause video while a description is read**: holds the video until
  the description finishes, then carries on — useful for slides,
  tutorials and videos with dense dialogue.
- **Description Editor**, **Ask More...**, **Explore Scene...** and
  **Agent (F2)** open the windows described below.

## The Player agent (F2)

In the Player, press **F2** (or the **Agent (F2)** button) and ask
anything about the video in your own words: "is the description here
right?", "what happens at the bridge?", "the old man is called Hans".
The agent looks at the frames, reads the descriptions and the
dialogue, finds silent gaps and can move the Player. The video pauses
while it is open.

The agent **changes nothing by itself**. It proposes; you hear a
summary, then choose **Accept all**, **Review one by one** or **Reject
all** (Esc rejects). The project's subtitle file is copied aside before
the first change and **Undo last changes** is always there. Every step
is spoken. The conversation is remembered until the Player closes;
character names are remembered for the project. If one question costs
more than a couple of cents, it asks before continuing.

**Check the whole video** (a button in the agent window) goes through
every description, a minute of video at a time, and gives ONE list of
proposals to accept, review or reject. It says the time and cost first.

You can stop the agent at any moment:

- While it works on a question, the **Ask** button becomes **Stop
  asking** (Alt+A). Press it to stop.
- While it checks the whole video, that button becomes **Stop
  checking**.
- **Close** or Esc also stops whatever the agent is doing, so no
  requests go on being paid for after the window has closed.

The agent works with **OpenRouter** models and with **Gemini** models
(your own Gemini key, since 1.9.2) that have passed **Settings > Test
agent mode**. If you press F2 with a model that has not passed it yet,
the Player offers to run the test right there ("The agent has not been
tested with <model> yet. Test it now? It takes about half a minute and
costs a fraction of a cent."). If the test passes, the agent opens. If
you say No, or the test fails, or the provider has no agent, F2 opens
**Ask More** instead, which sends the frame at the Player's position
with your question. In Ask More, **Cancel** (or Esc) abandons a question
that is still waiting for its answer.

## Scene Explorer

From the player, **Explore Scene...** opens the Scene Explorer to
inspect frames one by one: left/right arrow keys move between frames,
`D` gives the full AI description of the current frame, `L` lists the
objects in the frame, Enter describes the nearest object, and `Escape`
closes. Closing the Scene Explorer while it is still loading frames
stops the loading.

## Standalone video describer (command line + HTTP API)

Besides the GUI app, this repository carries a standalone
`video_describer` package (no code shared with the GUI). It burns an
`H:MM:SS` stamp (dark box, top-left corner) onto every frame extracted
by ffmpeg, sends ALL frames base64-encoded in ONE `glm-5.3-flash`
request, lets the model READ the on-screen stamps, then parses the
`H:MM:SS - description` lines into an SRT and a JSON file
(auto-batches above 150 frames; guards of 5 MB and 6000 px per frame).

For `describe`, the output goes into a folder named after the video,
inside the video's folder (`<video folder>\<video name>\`), and the
files are named after the video: `<video name>.srt` and
`<video name>.json` (`--out` chooses another folder).

By default it talks to **Zhipu directly**
(`https://open.bigmodel.cn/api/paas/v4`, model `glm-5.3-flash`), so
`GLM_API_KEY` must be a Zhipu key, not an OpenRouter `sk-or-v1-` key.
`--base-url` and `--model` change this.

```bat
:: Describe one local video (SRT + JSON in <video folder>\<video name>\)
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
Windows SAPI5 (`--tts-engine sapi`); one audio file per description is
placed in an `audio\` folder inside the output folder (no combined
audio file is made).

This standalone tool predates the app's current engine; the app itself
does not use it.

## If something goes wrong

1. Read the log at
   `%LOCALAPPDATA%\OmniDescriber\logs\omni_describer.log`; every
   failure is recorded with its real cause.
2. Check the AI settings (API key, model, base URL) and press **Test
   this model**.
3. Since 1.9.6 the error messages are plain words in the app's
   language, without technical text (the full detail is in the log).
   What they mean and what to do:
   - **"The AI service is busy right now (too many requests). Wait a
     few minutes and try again, or choose another model in Settings >
     AI."** The provider is limiting you (HTTP 429). With every
     provider, OpenRouter included, the app already waits as long as
     the provider asks (up to about a minute) before trying again. If
     you still see this, do what it says.
   - **"The AI provider's daily quota for this model is used up. It
     resets at midnight Pacific time (3 to 4 pm in Malaysia). ..."**
     Your key has used its requests for the day (Gemini's free tier,
     for example). Waiting a few minutes will not help: wait for the
     reset, choose another model or provider, or move the key's project
     to a paid tier, which raises the limit.
   - **"The AI provider refused the video as too large, even after the
     app made it smaller. ..."** With OpenRouter, the app has
     already sent the part again, smaller each time, up to three times.
     Choose another model, or set a shorter **Video chunk length** in
     Settings > General.
   - **"The AI provider refused the API key ..."**: the key is not
     valid, or not allowed for this model. Check it in Settings > AI
     Settings and press **Test this model**.
   - **"The AI provider says there is not enough credit on this
     account. ..."**: top it up on the provider's website, or choose
     another provider.
   - **"Could not reach the AI provider (no connection, or it did not
     answer in time). ..."**: check the internet connection and try
     again.
   - **"Preparing the video for the AI failed (...)"**: try again; if
     it repeats, the video file may be damaged.
   - **"The video site refused the download (HTTP 403), even after
     trying again. ..."**: wait a minute and try again; if it keeps
     happening, update yt-dlp with **Help > Check for Updates**.
4. For long videos sent as still pictures, consider a lower FPS (for
   example 1) or set **Max frames per video**.
