# Omni Describer Custom

An accessible audio-description tool for blind and visually impaired
users. It downloads or opens a video and produces timestamped audio
descriptions in two ways: the default frame mode extracts frames and
sends them to an AI vision provider, while the optional full-video
mode (GLM, Gemini or MiniMax) uploads the whole video and lets the AI
watch it (including audio) and timestamp its own descriptions. A
built-in player reads the descriptions in sync with playback.

A full Malay user guide is in `doc/panduan-pengguna.md`; the English
version is `doc/user-guide.md`.

## What's new in v1.6.2

- **Pausing for narration is now a toggle in the player.** Holding the
  video while a description is read helps a slide deck and gets in the
  way of a talking head, so it is a preference rather than a policy —
  and it sits in the player's control row, not two windows away in
  Settings. Unticking it stops the very next hold; toggling it announces
  what playback will now do, because a screen reader says "checked" but
  not what that means.
- **Adding a language now costs one file.** Translations moved from two
  Python dicts in a 782-line module to `locales/<code>.json`, one file
  per language; `strings.py` is a 130-line loader and the `t()` API did
  not change. Each file describes itself — the name shown in the picker
  (in its own language, since NVDA reads it aloud), the language name
  the AI is told to write in, and a default TTS voice — so the Settings
  pickers build themselves from whatever files are present.
  See [doc/menambah-bahasa.md](doc/menambah-bahasa.md).
- **The seven prompt presets stay in English on purpose.** The engine
  appends "write every description in <language>", so a new language
  does not mean translating seven long audio-description prompts.
- Fixed: the pipeline accepted only `ms` or `en` as a description
  language and silently discarded anything else, so a new language would
  have been ignored without warning.
- A broken locale file is skipped with a logged error instead of
  stopping the app, and missing keys fall back to English **per key** —
  a half-finished translation shows English, never raw key names read
  aloud.

## What's new in v1.6.1

**The AI can now know what was said, even though it cannot hear.** Probed
directly: GLM (the default provider) answers "NO AUDIO ACCESS" when asked
to transcribe a spoken line. It sees frames only. That had crippled the
`foreign` preset and left every other preset guessing at whatever the
soundtrack carried.

- **Transcript context.** Before describing, the app fetches what is
  said — published captions for a URL, an embedded subtitle track for a
  local file — and hands the model the words for the part it is
  describing, in part-local time. The block tells it these lines are
  *already audible*, so it must not read them back unless the preset asks
  it to convey speech. Verified on a clip where three earlier runs had
  conveyed nothing: `ms_foreign` produced *"Dia berkata keunikan
  gajah-gajah ini ialah belalai yang amat panjang"* from English speech.
  The function that does this already existed and had never worked — its
  first line rejected every URL, which is the only input it can serve.
- **Speech-to-text fallback** when there are no subtitles at all: local
  `faster-whisper` (free, offline, ~3.7× real time on CPU) or xAI's Grok
  STT ($0.10 per hour of audio, needs a key). Order is measured, not
  assumed — published captions said "really long **trunks**", local
  Whisper heard "long **hunts**", so captions win.
- **Extended description (W3C/WAI).** The player holds the video while a
  cue is spoken and resumes after. Reading one slide's bullets took 9.9 s
  into a 5 s gap, so 3 of 4 cues used to collide and be lost. If you
  press Pause or Stop mid-cue, your decision wins.
- **Cost before spending.** The estimate, your remaining balance, and a
  warning when the balance is under OpenRouter's $1.00 video floor, all
  logged before anything uploads. The floor is the real blocker, not the
  price: a 2-hour film costs about $0.10.
- **Full resolution for text-heavy video.** Optional: cut an oversized
  video into shorter parts at full resolution instead of shrinking it to
  360p, which makes slides, code and charts unreadable.
- **A hard 12-word ceiling on descriptions.** Measured with the real TTS
  voice, the v1.6.0 prompts still overran their gaps 4 times in 6.
  Telling the model to pace itself did not work — it wrote 21-word lines
  into 7-second gaps — but a flat ceiling it obeys.
  `tools/check_narration_fit.py` measures this on any project.
- Two prompt rules were corrected against their sources: film *technique*
  is banned rather than the word "camera" (the Netflix guide explicitly
  allows "turns to the camera"), and the identity rule now matches that
  guide exactly — race, ethnicity, gender — since apparent age is
  ordinary description vocabulary.

Build note: the package now carries local Whisper, so the zip is 344 MB
rather than 260 MB.

## What's new in v1.6.0

**The prompts now follow published audio-description standards.** The old
ones worked against them: the default asked the AI to "describe everything
you see in this video frame in detail", `detailed` asked for "emotional
tone", and the engine appended "describe important visuals AND
sounds/speech" to every request — telling the model to narrate dialogue a
blind listener can already hear.

Sources used: [DCMP Description
Key](https://dcmp.org/learn/227-description-key--how-to-describe), [Netflix
Audio Description Style Guide
v2.1](https://partnerhelp.netflixstudios.com/hc/en-us/articles/215510667-Audio-Description-Style-Guide-v2-1),
[W3C/WAI Audio Description](https://www.w3.org/WAI/media/av/description/),
[ADLAB Guidelines](https://www.adlabproject.eu/Docs/adlab%20book/index.html).
They agree: describe only what is needed to follow the content, skip what
the audio already conveys, present tense and third person, report what is
observable rather than what it means, never guess identity, and keep each
cue short enough to be spoken in the gap.

- **Seven presets, chosen by description strategy** (EN + BM): `default`,
  `tight` (dense dialogue), `extended` (documentary/educational, the W3C
  "extended description" case), `foreign` (conveys foreign speech — the
  recognised *audio subtitling* service), `suspense` (preserves dramatic
  silence), `children` (vocabulary to the age), `onscreen_text` (slides,
  UI, charts read in reading order).
- **No genre presets.** The standards prescribe the same rules for every
  genre and vary only pace and tone; Netflix names exactly two genres,
  which is why `suspense` and `children` exist and "action" does not.
- **Old presets retired** — but only when the stored text is still exactly
  what was shipped. A preset you edited or wrote yourself is never touched.
- Prompts live in one place now (`prompt_manager.DEFAULT_PROMPTS`); a
  second, slightly different copy in `settings_store` is gone.
- `tools/compare_prompts.py` runs one video through two prompts and reports
  cue count, words per cue, and counts of film-technique phrases, speech
  echo ("he says") and interpretation ("seems to"). `--dry-run` prints the
  fully assembled request without calling the API.

Measured on the same 19-second clip, same provider, old prompt vs new:
**22.7 → 14.0 words per cue, longest cue 45 → 25 words.** A 45-word cue
cannot be spoken in a three-second gap; that is the practical difference.
The old prompt also re-described the unchanged background in every cue
("the elephants still visible eating hay", "the concrete barrier and rock
wall framing the scene") and closed with "The video ends with…".

Two rules were corrected after that first real run, because the model
disobeyed one of them and it turned out the rule was wrong, not the model:
the Netflix guide explicitly allows direct address ("She turns to the
camera and winks at us"), so the prompt now bans film *technique* (camera
moves, cuts, zooms) rather than the word "camera"; and the identity rule
now matches its source exactly — race, ethnicity and gender identity —
since apparent age is ordinary description vocabulary.

## What's new in v1.5.7

- **Open works on a fresh launch again (critical)**: on Windows,
  `SetLabel()` eats a control's *state* — it clears a `wx.Choice`
  selection and replaces a `wx.TextCtrl`'s text. v1.5.4 used it to give
  three controls screen-reader names, so every freshly launched app had
  **no preset selected**: pressing Open answered "Please select a prompt
  preset" even though the combo looked populated. Screen-reader names are
  now set without destroying state, and the names are still there.
- **No more invented "User notes" in AI requests (critical)**: the same
  bug left the prompt box holding its own label, "Prompt to send (from
  preset, editable):" — and `_on_preset_open` appends anything in that
  box to the request as "User notes". Every describe was shipping that
  nonsense line to the AI. The box now holds the selected preset, and a
  test asserts the exact string handed to the pipeline.
- "Status Log" is no longer written into the status log as if it had
  been logged.
- The real-GUI E2E verifies its own clicks now: a click that lands
  nowhere is retried and then fails loudly, instead of hanging forever
  waiting for a dialog that can never appear.

## What's new in v1.5.6

- **Dead Open button fixed (critical)**: opening a video that already had
  a project raised `AttributeError` — wxPython Phoenix has no
  `SetYesLabel`/`SetNoLabel`/`SetCancelLabel`, so the "existing project
  found" prompt never appeared and pressing Open did nothing at all, with
  no visible error. Found by the real-GUI E2E; now uses
  `SetYesNoCancelLabels` and is covered by a regression test.
- **The test suite no longer edits your settings**: gate runs built real
  MainFrames that wrote into the live `settings.json`, leaving the Gemini
  provider pointed at a dead test loopback URL with the key `test-key`.
  `run_gate.bat` now points settings at a throwaway dir via
  `ODC_CONFIG_DIR`, and a test fails if that isolation is missing.
- **Real-GUI E2E repaired**: it now answers the dedupe prompt, and its
  chunk expectation matches the GUI (the Settings spin control has
  enforced a 60 s minimum since v1.5.3, so a 19 s clip is one part).
  Full run passes: live download percentages, 12 cues covering the whole
  clip, SRT export, clean exit.

## What's new in v1.5.5

- **Ghost progress dialog fixed (critical)**: `wx.ProgressDialog` pumps
  the event loop inside its own constructor, so the pipeline's cleanup
  could run in there, find no dialog to close, and leave the dialog born
  a moment later owned by nobody. It stayed on screen and kept the main
  window **disabled** — the app looked frozen, with a screen reader stuck
  in a dead dialog. The dialog builder now notices a cleanup that landed
  mid-construction and discards that dialog.
- **Counter thread always stopped**: `_process_video` stops the frame
  counter thread from its outer `finally`, covering failures between the
  thread starting and the per-mode stop points.
- **Gate is reliable again**: `tests/test_fixes12.py` was failing about
  one run in three — sometimes as a hard interpreter crash with an empty
  log, which hid the bug above. Test output is now line-buffered so a
  crash can no longer swallow the evidence, wx frames are torn down after
  their pending events are drained, and `tests/test_fixes20.py` covers
  the dialog race directly. Gate: 29/29 suites PASS.
- **Full-video mode labels name GLM**: the checkbox and the guides said
  "Gemini or MiniMax" while GLM (OpenRouter) has been supported since
  v1.5.3.

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
