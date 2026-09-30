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

Version numbers: the last digit stops at 9, so 1.6.9 is followed by
1.7.0. The releases now called 1.7.0 and 1.7.1 were first tagged
1.6.10 and 1.6.11; an older zip with those names is the same code.

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

## What's new in v1.8.8

- **The model you choose is the model that runs.** The model picked in
  Settings was saved but never used for OpenRouter, Gemini or MiniMax:
  every request asked for no model in particular, and the provider's
  first built-in one answered. Choosing "Recommended: Gemini 3.1
  Flash-Lite" still ran GLM. It now reaches every request.
- **New: check descriptions against the video** (Settings, full-video
  mode, **off** unless you turn it on). After the AI writes the
  descriptions, each one is compared with the frames 20 seconds either
  side: moved to where it really happens, or removed if it is nowhere
  to be seen. Measured on two long films by an independent model:
  wrong descriptions roughly halved (Tears of Steel 15 → 7). Adds a
  few minutes per film and a very small cost. Choose Most accurate,
  Most descriptions, Keep all (only fix timing), or Auto (Most accurate
  for long videos, Keep all for short ones).

## What's new in v1.8.7

- **Esc now closes Yes/No questions.** Windows switches Esc off in a
  message box that has no Cancel button, so Esc did nothing and you had
  to find No. The boxes now have a Cancel button: Esc and Cancel mean
  "no", nothing happens. They are still the standard Windows boxes,
  which NVDA reads in full.
- **Your own AV1, HEVC or VP9 videos work with every model.** A small
  local file used to be sent exactly as it was, and some models (MiMo,
  Nemotron) cannot open AV1. It is now re-encoded to H.264 first, the
  same way a large file already was; H.264 files are sent untouched.

## What's new in v1.8.6

**Found by measuring accuracy across genres and long videos**
(`doc/perbandingan-model.md`, phase 16.2).

- **Long videos are described twice as accurately.** Full-video mode now
  sends 5-minute parts instead of 10-minute ones. Measured on two films:
  descriptions at the wrong moment fell from 24.5% to 12.9% and from
  27.5% to 11.8%, and jobs finished sooner. A saved setting of 600 s
  (the old default) moves to 300 s once; a value you choose later is
  kept.
- **Scenes with dialogue get described.** The transcript used to stretch
  every sentence up to the next one, so the app believed a scene had no
  pauses and the AI wrote one description for a whole minute of action.
  Sentence times now come from the words: 12 → 30 descriptions on the
  test clips, none judged wrong.
- **Gemini through OpenRouter works on long videos.** Google refuses
  requests over 20 MB, and one of GLM's servers over 8 MiB; the app now
  knows these limits, learns others from the refusal, and resends the
  part compressed instead of failing.
- **A server timeout no longer throws the whole job away.** An upstream
  "504" hidden inside a normal reply is now retried like other busy
  errors.
- **New users start in whole-video mode.** Frame mode, the old
  default, described every frame on its own: on films that was 147-204
  descriptions a minute, two or three a second. If you already chose a
  mode, it is kept.
- **Frame mode no longer describes frame by frame.** It keeps at most
  one frame every 4 seconds (the time a short description takes to say)
  and cleans each reply into one spoken line — no markdown headings,
  no made-up timestamps, no line repeated twice in a row. Measured on a
  one-minute film clip: 204 → 15 descriptions.

## What's new in v1.8.5

**Found by comparing seven video models on five different clips**
(`doc/perbandingan-model.md`).

- **Speech in cartoons and dialogue was sometimes thrown away.** A
  character repeating a sound ("Bra, bra, bra") made the transcriber's
  hallucination check reject every real line around it — the Ocong
  transcript came out empty, so GLM got no dialogue. Each line is now
  judged on its own.
- **YouTube downloads prefer H.264.** YouTube's default was AV1, which
  some models (MiMo, Nemotron) cannot open. Same resolution.
- Measured answer to "do models that hear describe better?": not in this
  app. GLM (deaf, but given the transcript) was as accurate as any model
  that hears; Gemini 3.1 Flash-Lite is the best of those that hear.
- **Settings > AI (OpenRouter): the two measured best models come first
  and are read as "Recommended: ..."** — GLM 5.3 Flash (still the
  default) and Gemini 3.1 Flash-Lite. The old order put the two worst of
  the seven at the top.

## What's new in v1.8.4

**Reported by the owner after the long-video test.**

- **The progress bar moves while a video is sent to the AI** (it sat at
  0% with only a seconds counter). The upload is counted in bytes; the
  AI's wait that follows is estimated from how long the same model took
  on your earlier videos, with the time left: "About 4 min left".
- **Every change of phase is spoken by your screen reader** ("Part 2 of
  2. Uploading video...", "The AI is watching the video... About 3 min
  left"). Before, the text changed in the dialog but NVDA said nothing,
  because focus stays on Cancel.
- Fixed: at the start of part 1 of 2 the app said "overall 55%".
- "Preparing the video" and "Reading the AI's answer" are now named as
  such; both used to say "The AI is watching the video".

## What's new in v1.8.3

- **YouTube downloads** that are refused with "HTTP Error 403" are tried
  again (up to three times, continuing the partial file). This error
  often clears on the next attempt. If it doesn't, the app explains
  what to do in your language, including updating yt-dlp from
  Help > Check for Updates, instead of showing the raw error.
- A full 15-minute video was described end to end by the released app
  (Sintel, 2 parts): descriptions to 14:06 of 14:48 (the rest is
  credits), and NVDA announced the finish. The same model gave 169
  descriptions on one run and 81 on the next; the count is the
  model's, not the app's.

## What's new in v1.8.2

**Found by pressing every button with the keyboard and listening.**

- **Esc** now closes the Description Editor (saving your edits) and the
  Ask More window.
- **<< 10s / 10s >>** in the player say where you landed ("Position 0:20
  of 1:30") and keep focus on the button, so you can press again.
- **Scene Explorer** says every frame as you arrow through it, answers
  L even without an AI, and names its objects box.
- **Settings:** the speech speed slider is read as "Speed" (it was "10"),
  with the value shown as 1.0x; a new user starts on OpenRouter instead
  of an empty provider.
- **Yes/No buttons** follow the app's language, and an open player
  switches language with the rest of the app.
- **A video whose sound ends early** keeps all its descriptions. Its
  length was sometimes measured from the audio track, and every
  description after the sound stopped was dropped.
- **When the AI service is busy** (HTTP 503/429) the app waits longer
  between attempts and then says so in plain words, suggesting another
  model, instead of showing raw JSON.
- The "custom" provider was tested for real in both OpenAI and
  Anthropic formats (through OpenRouter).

## What's new in v1.8.1

**More models that watch AND hear the video, and a list you can trust.**

- Through your OpenRouter key, **Qwen3.8-Omni-Flash** and **MiMo-v2.6-
  Flash** now receive the video's own sound, like Gemini — tested on 28
  Sep 2026 with a clip whose voice says a secret word. Qwen costs about
  a fifth of Gemini 3.8 Flash per input token. Both are in the list by
  default.
- **Fetch models** keeps only models that can work: the 13 ":batch"
  variants (always refused), routers that pick a model for you, and
  aliases are gone. Models that hear come first, then cheapest, and
  NVDA reads each as "name — watches and hears the video — $0.15 per
  million tokens". The list is saved for next time.
- **Test this model** (Alt+T) sends the chosen model a 6-second clip
  and says whether it really watches the video and hears its sound —
  for under a tenth of a cent. It caught a model listed for video that
  answered "black, black" for red then blue. A test result overrides
  the catalog's claim.

## What's new in v1.8.0

**Languages you can keep up to date yourself.**

- **Everything is translatable.** About 15 texts were written straight
  into the code in English: the start-up warnings, several log errors,
  the About box and the file-type lists NVDA reads in Open and Save
  dialogs. They now follow the chosen language.
- **Your own language files survive updates.** Put them in
  `%APPDATA%\OmniDescriber\locales\`. A new language code adds a
  language; a file for an existing one (ms.json) corrects it line by line.
- **Help > Translation Report** says how many lines of your language
  are still untranslated after an update, and saves exactly those lines,
  with the English text, ready to translate.
- **46 unused strings removed**, so no one translates text the app never
  shows. A test now fails if English is written into the UI again or a
  string stops being used.

Guide: `doc/menambah-bahasa.md`.

## What's new in v1.7.9

**The API key box no longer disappears.** In Settings > AI, pressing
Show or Hide next to the API key made the key box vanish: it was
rebuilt in the wrong place, last in the Tab order and without its
label, so NVDA could not find it again. The same box now simply shows
or hides its text. Heard through NVDA: after Show it reads the key,
after Hide it reads "protected".

## What's new in v1.7.8

Housekeeping behind the scenes, found while checking 1.7.7:

- Preset names now follow the app's language files, so a third language
  added later keeps its presets out of the English and Malay lists.
- The long-video tests make their own 10-minute clip instead of using a
  project from your Documents folder.
- The real-app test tools remove the project each run creates, so test
  videos no longer pile up in your Open Project list; two of them had
  been unable to read the project folders since 1.7.6 and are fixed.

## What's new in v1.7.7

**Help > Check for Updates** keeps yt-dlp working when YouTube changes.
It says which version is in use and whether a newer one exists, and
installs it only if its SHA-256 matches the publisher's own checksum
list and the program reports that version. The update is kept apart
from the app (`%LOCALAPPDATA%\OmniDescriber\tools`), so **Use bundled
version** always goes back. Once a week the app checks at start-up and
only announces what it found. Verified against the real GitHub release:
check, download, checksum, test, use and revert.

## What's new in v1.7.6

**Projects you can recognise.** In File Explorer a project was only
`project_24` beside `project_24.db`. Each project is now one folder
named after it, such as `Sintel (48)`, with `project.db` and `media`
inside. Existing projects move by themselves the first time 1.7.6
starts, and the video and frame paths stored inside them are updated
so the player still finds everything.

- **Open Project** now reads "Sintel — 79 descriptions — 28/09/2026
  11:30", newest first, and has a **Rename** button (Alt+N) that
  renames the folder too.
- Old projects named after a link ("https://www.youtube.com/...") can
  be given their real titles with `tools/fix_project_names.py`.
- The test gate no longer writes into your projects folder; 14 test
  projects it had left there were removed.
- With a Windows (SAPI/OneCore) voice, the narration pause sometimes
  let the video run on at once, because it checked for speech before
  the voice had started. It now waits for the voice to begin.

## What's new in v1.7.5

**Checked by listening, and ~365 MB smaller.**

- **Every window heard through NVDA**, not just the main one. The
  player's position slider said only "slider 0" and the video area read
  out an internal name; both now say what they are. In the editor, the
  list now speaks your edit as you type, not the old text.
- **Cancel works during a long GLM request.** It used to wait for the
  request to finish, which could take many minutes. In fast batch mode,
  one failed batch now stops the others instead of leaving them running
  and billing.
- **Better picture for long videos split into parts.** Each part now
  gets its full upload budget (Sintel: 171 → ~350 kbps).
- **Smaller download.** The build no longer carries `torch` (365 MB),
  which the app never used; local Whisper transcription still works.
- **Verified tools.** ffmpeg and yt-dlp are pinned to exact releases and
  checked against their published SHA-256 on every build.

## What's new in v1.7.4

**A full audit, checked on a 15-minute film.** A real run of the shipped
build on Sintel (14:48, Gemini full-video) produced 83 timed
descriptions. It also exposed the worst bug fixed here:

- **No more console windows.** The windowed exe opened a console for
  every ffmpeg and yt-dlp call; NVDA announced "terminal" and read out
  the ffmpeg path in the middle of a job.
- **Safer keys.** The Gemini key is sent in a header, never in the URL
  (an HTML error page used to put it in the log). A half-written
  settings file no longer wipes every key; a key that cannot be
  decrypted is kept; the player no longer overwrites Settings.
- **Transient errors are retried** (429/5xx) for Gemini, OpenAI,
  MiniMax and custom, instead of losing a whole video on one 503.
- **Long videos:** frames past number 9,999 are in the right order
  (10 fps, over 16:40); each part is described with its real length.
- **Editor and player:** edits survive moving between descriptions and
  closing the player; the first description waits for its moment;
  Stop really stops speech; Ask More sends the question once.
- **Subtitles:** blank lines no longer cut a cue; UTF-16 and ANSI files
  import; placeholder text such as "(empty response)" is never spoken.

## What's new in v1.7.3

**Gemini now defaults to `gemini-3.8-flash`.** Google limits the 2.5
models to accounts that used them before, so a new user entering a
Gemini key got an error on the old default, `gemini-2.5-flash`. The
list now reads `gemini-3.8-flash`, `gemini-3.5-flash-lite`, then
`gemini-2.5-flash`; a saved choice of 2.5 is kept. Both new models
were checked in full-video mode and hear the video's audio.

## What's new in v1.7.2

**Google Gemini API full-video mode restored.** Resolved an upload
endpoint issue where Google Files API resumable uploads omitted the
`/upload/` subpath, causing Google to return HTTP 200 without the
`X-Goog-Upload-URL` header and blocking Gemini video descriptions.
Updated the Gemini model catalog to active models (`gemini-2.5-flash`,
`gemini-3.8-flash`, and `gemini-3.5-flash-lite`).

Enhanced the build test harness (`test_build_smoke.py`) to deliver
`WM_CLOSE` messages directly to top-level application windows across
helper and IME frames.

## What's new in v1.7.1

**The narration pause now works with NVDA, on any NVDA version.** The
player can hold the video while a description is spoken and resume it
when the speech ends. For voices the app plays itself that was always
easy. For a screen-reader voice it was refused outright in v1.6.6,
because NVDA hands back control the moment text is queued and never
says when it finished.

Measured in the real player, NVDA 2025.3, screen-reader voice selected:

| description | video held for |
|---|---|
| 5 words | 1.43 s |
| 26 words | 4.64 s |

The video stops as the description starts and resumes the moment NVDA
falls silent.

**How: it listens.** Windows keeps a peak-level meter on every audio
session, and every session belongs to a process. When NVDA's process
goes quiet for 0.6 s, the sentence is over. That asks nothing of NVDA,
so it holds on every NVDA version. It is also ready for JAWS; other
readers keep the previous behaviour until their process can be
checked.

**Why not NVDA's own API.** NVDA 2024.1 added a synchronous
`speakSsml` meant to block until speech ends. On NVDA 2025.3 it
**hung on the very first call** and never returned — a race NV Access
fixed only in NVDA 2026.2
([nvaccess/nvda#20220](https://github.com/nvaccess/nvda/pull/20220)),
triggered by something as ordinary as a keypress. `isSpeaking` arrives
in NVDA 2026.3, which is not yet released. An API answer would have
worked only for people on the newest NVDA. No controller-client DLL is
needed for this.

**Three mistakes found by measuring, each now tested:**
- Searching only the default output device found no NVDA at all. NVDA
  here is routed to its own device, apart from media — common for a
  blind user — so every device is searched.
- Finding NVDA's process with `tasklist` took 0.83 s, longer than a
  three-word description takes to say at this user's rate, so short
  descriptions were reported as silent. It now takes about 0.03 s.
- Looking the meter up after speaking missed short sentences for the
  same reason; it is now ready before the speech starts.

If NVDA's audio cannot be heard — muted, or an unusual audio path —
the pause falls back to waiting as long as the text should take,
estimated slowly so the video waits a little too long rather than
resuming over the end of the sentence. It never waits indefinitely.

## What's new in v1.7.0

**The AI is never left blind for long.** Frame deduplication compares
each frame only with the last one it kept and discards anything 85%
similar, so a stretch of video that does not change was reduced to a
*single* frame however long it ran. The model then had nothing to look
at for that whole stretch and could describe nothing in it.

Measured on a 120-second clip whose middle 100 seconds were one
unchanging image:

| | frames | longest stretch with no frame |
|---|---|---|
| before | 3 — at 0s, 10s, 110s | **100 s** |
| v1.7.0 | 6 | **25 s** |

On four real videos — a Malay news broadcast, an English talk, a
cooking vlog and an amateur outdoor clip — the frame counts are
**unchanged** (34, 37, 36, 19). The floor only acts where
deduplication actually left a hole, so ordinary video costs nothing.

A held shot is not an empty one: a lecturer stands at a slide, text
appears, someone shifts position, and all of that sits inside the
similarity threshold. Loosening that threshold would undo
deduplication everywhere, so the *gap* is bounded instead. Inserted
frames are real extracted frames at real timestamps — never invented.

Settings › General has **"Never leave the AI blind for longer than"**,
default 30 seconds, 0 to switch it off. It is the floor to the frame
cap already there, which is the ceiling.

The idea is borrowed from
[devinilabs/claude-watch](https://github.com/devinilabs/claude-watch),
which calls it a coverage floor and uses 45 seconds for study notes;
30 is used here because this app has to describe the picture rather
than summarise it. Their code was read, not installed.

## What's new in v1.6.9

**The transcript now says the same thing twice.** Since v1.6.8 the app
spends the local transcript — it tells the model how many words fit in
each silent gap — so a transcript that changed between runs changed
the budget with it. It did: the same file, same model, three runs
reported first speech at 30.0s, 30.0s, then 0.0s.

Benchmarked across **seven genuinely different videos**, two runs each
(`tools/whisper_bench.py`): a Malay news broadcast, an English talk, a
cooking vlog with a music bed, two Indonesian cartoons, an amateur
outdoor clip, and two text-to-speech clips whose speech times are
known exactly.

| | not deterministic | clean Malay | the music clip |
|---|---|---|---|
| old defaults | 3 of 7 | 35% | invented 17 lines of Korean |
| v1.6.9 | **0 of 7** | **96%** | correctly found silence |

- `temperature=0.0` — the library default is a *list* of temperatures,
  and every value above zero samples, so a hard passage was re-decoded
  at random until it passed a threshold. That was the entire source of
  the drift.
- `condition_on_previous_text=False` — one bad guess no longer steers
  the rest of the file.
- **Voice activity detection**, tuned (`threshold` 0.3 rather than the
  0.5 default, with padding so first and last syllables survive). This
  is what stops music being transcribed into confident nonsense.
- **Repeat loops are dropped.** Turning the fallback off removes the
  randomness but leaves the model nowhere to retry, so it can loop
  instead: 27 seconds of "Mememememe" scored 29.7 on Whisper's own
  compression ratio where real lines score 1.7–2.8. Those are filtered
  and counted in the log.

**The model was NOT changed, and that is a correction.** An earlier,
weaker benchmark took three cuts from *one* video and made the `small`
model look like the answer — 0 hallucinations against 32. On genuinely
separate videos it reversed: `small` produced twelve hallucinated
segments where `base` produced two. Measuring one video three times
measures one video. `base` also stays free of a 464 MB download and
runs about four times faster.

**What is still not solved.** Neither setting is clean on hard cartoon
audio — a couple of invented segments survive. And the compression
filter catches repeat loops only: the seventeen Korean segments scored
1.8–1.9, indistinguishable from real speech by that measure. The VAD
prevents that case rather than detecting it, which means a video where
VAD wrongly rejects real speech would go silently untranscribed.

## What's new in v1.6.8

**Descriptions are written to fit the silence.** This started from the
owner's hunch that the model must not be getting the dialogue, or it
would not write over it. Testing that turned up something more precise,
and partly proved him right.

The transcript *is* sent — 921 characters of timed lines for a
50-second clip, with an explicit instruction to use the gaps — and the
model's *placement* was mostly good. What was missing was arithmetic.
Nothing ever told it how much room a gap holds, so it picked a sensible
moment and then wrote far too much for it. Measured: about **77 words**
of silence available in that clip, **97 words** written in one run and
**99** in the next.

- **The prompt now lists every silent gap and how many words fit in
  it**, scaled by your own TTS speed — at 1.5x you are offered more
  words than a listener at 1.0x, instead of a figure that suits
  neither. This is arithmetic rather than a plea; asking for "12 words
  maximum" had already failed twice.
- **A cue now lasts as long as its text takes to say.** Every cue used
  to get a flat three seconds, so a 36-word description overran by ten
  seconds and collided with both the next cue and the dialogue. In one
  real run cue 1 (0–3s) and cue 2 (2–5s) overlapped outright. Cues are
  now sized from their word count and never run into the next one.
- **Anything still landing on speech is named in the log**, with the
  time and word count, so you can shorten it in the editor or switch
  on the narration pause.

**A known limit, measured and deliberately not "fixed".** The local
Whisper transcript is unreliable on hard audio. The same file, same
model, three runs: first speech reported at 30.0s, 30.0s, then 0.0s;
coverage 40%, 32%, 93%. The gap budget is only ever as good as that.
Raising `beam_size` and enabling the VAD filter was tried and made it
**worse** — coverage fell to 20% and real speech was dropped — so
nothing was changed. If this is worth attacking, it needs measurement
first, not a setting that ought to help.

## Verified end to end, 22 September 2026

One complete run of the **shipped exe** — real video, real AI call —
watched through NVDA via the local bridge, plus a leak and security
audit. It found four things that the gate, the source and the build
had all reported as fine.

- **Prism was dead in the shipped build.** The app logged `No module
  named 'prism._prism_cffi'` at startup: the whole screen-reader voice
  added in v1.6.6 did nothing for anyone who installed it.
  `prism/_native.py` appends its own directory to `__path__` at
  *runtime*, so PyInstaller never saw the extension and dropped it
  while `--collect-all prism` reported success. The v1.6.6 test read
  `build.bat` for that flag — an intention, not a result.
  `hooks/hook-prism.py` fixes it, and the test now reads `dist/`.
- **The upload cache deleted itself.** The chunked path has a *second*
  cleanup that unlinks every part, and the cached copy is a part — so
  v1.6.7's retry saving never survived a single job in full-video
  mode, which is the mode actually configured here. The app even
  logged "kept for retries" as it happened, because the log printed
  only the file name and not where it went.
- **806 MB of abandoned temp folders**: 115 download directories and
  120 frame directories from runs that crashed or were killed, which
  nothing ever came back for. `core/housekeeping.py` now sweeps our
  own `odc_*` folders older than a day at startup; the first run
  freed 414 MB.
- **Nothing leaked.** No plaintext key in the log, the settings file,
  37 gate outputs or the shipped zip; the key is encrypted at rest and
  still readable back; the package ships no `settings.json`; the app
  opens no network port; and the NVDA bridge binds to `127.0.0.1`
  only.

**Prism reaches nine Windows screen readers** — NVDA, JAWS, ZDSR,
ZoomText, PC-Talker, BoyPCReader, SenseReader, SystemAccess and
WindowEyes — and falls back to SAPI or OneCore when none is running.
Measured on this machine: `create_best()` picked NVDA (priority 103,
the highest), and every backend was classified correctly as reader or
synthesiser.

**Two honest quality findings from the descriptions themselves.** The
model exceeded its own 12-word ceiling on 3 of 5 cues, the worst being
36 words — about 14 seconds of speech into a 3-second slot. And cues
are given a fixed 3-second length, so two cues less than 3s apart
overlap: here cue 1 (0–3s) and cue 2 (2–5s) did. With the narration
pause on, both are heard in full; with it off, the second is trampled.
Neither is new in v1.6.7 and neither is fixed by asking the model more
firmly (see AGENTS.md pitfall 14).

## What's new in v1.6.7

**Interrupted work survives.** A download that dies halfway now carries
on from where it stopped, and a failed upload no longer throws away the
expensive part.

- **Downloads resume.** yt-dlp has continued `.part` files by default
  all along — the app was throwing that away by downloading into a
  fresh random temp folder every attempt, orphaning the partial where
  nothing would look for it again. Downloads go to the project's media
  folder now, so the project is created *before* the download rather
  than after the AI finishes. Measured on a real interrupted run:
  stopped at 4,193,280 bytes, restarted, yt-dlp reported
  `Resuming download at byte 4193280` and finished a valid file. A
  finished video is left byte-for-byte alone on a re-run, and reopening
  a project no longer re-downloads at all.
- **Uploads: the honest answer differs by provider.** Gemini's upload
  was already resumable. GLM sends the video base64 inside one chat
  request, and OpenRouter has no resumable upload endpoint — that
  cannot be fixed from this side, and claiming otherwise would be a
  lie. What *is* recoverable is the re-encode that precedes it, which
  used to be deleted in a `finally` block and redone from scratch on
  every retry. It is kept in the project folder now. Measured on a
  60-second clip: 16.2s the first time, 0.00s the second — for a
  ten-minute video that is about 2.7 minutes back per retry.
- **New button: Play Video with Existing Descriptions.** Pick a video,
  and if an `.srt`/`.vtt`/`.txt` sits beside it with the same name the
  app offers it; otherwise you choose one. It plays straight away — no
  AI pass, no cost, no waiting. The pieces existed before but nothing
  joined them: importing an SRT made a project with *no video*, so the
  player opened with descriptions over silence.

**Three faults this work exposed, all found by running rather than
reading:**

1. Making downloads resumable uncovered a latent bug: the finished file
   was picked with `sorted(glob("video.*"))[0]`, and `video.f616.mp4`
   sorts before `video.mp4`. With an intermediate stream left over from
   an interrupted run, the app would have described a **silent video**
   while skipping the rest of the download. A fresh temp dir had hidden
   it, because yt-dlp deletes its own intermediates.
2. The compression failure paths called `rmtree(out_dir)`. That was a
   private temp dir before and is the **project's media folder** now —
   it would have deleted the downloaded video to tidy up after a failed
   encode.
3. Staging the encode as `.part` broke ffmpeg outright, which picks its
   muxer from the file extension.

## What's new in v1.6.6

**The app speaks through whatever the computer already has.** This
answers a specific complaint: give the app to someone whose computer
has no NVDA and they cannot use it. Two separate gaps hid behind that
sentence, and both are closed by [Prism](https://github.com/ethindp/prism),
which reaches NVDA, JAWS, ZDSR, ZoomText, PC-Talker and the rest, and
falls back to SAPI or OneCore when no reader is running.

- **"My screen reader" is now a narration voice.** Settings › Audio
  offers it alongside Edge, SAPI5 and OpenAI, labelled with the reader
  it actually found — "My screen reader (NVDA)" — so you can see it was
  detected rather than hope. It is never selected automatically; that
  would override a voice you had already chosen.
- **Status messages are spoken when nothing else would speak them.**
  The app announces by moving keyboard focus, which a screen reader
  reads aloud and a computer without one passes over in silence. All
  four windows now also speak the message through Prism *only* when no
  screen reader is running, so nothing is ever said twice.

**What a screen reader cannot do, and what the app does about it.**
Measured, not assumed:

| Backend | speak | reports when finished | set rate | set voice |
|---|---|---|---|---|
| NVDA | yes | **no** | no | no |
| SAPI / OneCore | yes | yes | yes | yes |

A screen reader returns the moment text is queued; it never says when
it finished. So with it selected, the player's automatic narration
pause is disabled with a reason, and the Voice and Speed controls are
disabled too — your reader owns those, and offering settings that do
nothing is worse than not offering them. The app reads this from the
live backend rather than from the engine's name, so Prism running on
SAPI does get the pause.

**Accessibility is now verified by listening.** `tools/nvda_accessibility_check.py`
tabs through the real window and asks NVDA what it announced. Reading
the source is what let v1.5.4 ship a broken preset combo; this hears
it instead. See Development below.

The custom AI provider entry has been emptied, so that slot is yours
to configure.

## What's new in v1.6.5

**The app now carries its own tools.** Every previous version assumed
ffmpeg, ffprobe, ffplay and yt-dlp were already installed. On this
machine they were, so it never showed — but given to anyone else, the
app failed one phase at a time with errors that named no cause, and the
player read descriptions over a silent video. The v1.6.4 note below
even described that as deliberate. It is not any more.

- **ffmpeg, ffprobe, ffplay and yt-dlp ship inside the package.** No
  separate install, nothing to put on PATH.
- **One function decides where they are.** Five places used to look
  separately, and only one of them knew about the `bin` folder — which
  is exactly why the packaged player was silent while the rest of the
  app worked. They all go through `core/tools.py` now, and a test fails
  the build if a new call site does its own lookup.
- **A missing tool is reported at startup**, by name, with what it
  costs you, instead of surfacing as an unexplained failure later.
- **The automatic narration pause is limited to voices the app plays
  itself** (Edge, Windows SAPI5, OpenAI). A voice spoken by a screen
  reader returns as soon as the text is queued rather than when it has
  been heard, so the video would resume over its own narration. With
  such a voice the checkbox is disabled and says why.

The bundled ffmpeg is the **GPL** build, because the app encodes upload
copies with libx264, which LGPL builds do not include. Passing this app
to someone else therefore means passing on FFmpeg's source offer too —
see `NOTICE.md`, and keep `bin/FFMPEG-LICENSE.txt` in the folder.

The binaries add **102 MB** to the download — measured, not estimated:
the zip goes from 344 MB (v1.6.4) to 446 MB. The first attempt came out
at 520 MB because PyInstaller recognises the ffmpeg DLLs as libraries
and wrote a second copy of all seven next to the Python extensions;
`tools/dedupe_build.py` removes those (avcodec alone was 118 MB), and a
packaging check now fails the build if they come back.

The binaries are not kept in git. `tools/fetch_binaries.py` downloads
them into `bin/`, and `build.bat` runs it before packaging, so a fresh
clone cannot quietly produce a build with none.

## What's new in v1.6.4

Two faults found by using the v1.6.3 build, both of which made the app
lie to the person using it.

- **The video had no sound while descriptions were read.** This was a
  regression in the v1.6.1 narration hold: pausing for a description
  stopped the audio *and* cleared the flag that the resume then checked,
  so the sound died about half a second after Play and never came back.
  Narration carried on working, which is why it looked like a player
  with no audio rather than a broken pause. The player now remembers
  what was playing before the hold and restores it. Manual Pause and
  Play were never affected, which is why this hid for a version.
- **The progress dialog reported a phase that had finished minutes
  earlier.** It read "Downloading video - 100%" in the title and
  "Working: Loading video info... (808s)" in the body, thirteen minutes
  into an AI upload. The phase text was written once at startup and
  never updated, the counter measured the age of the whole job rather
  than the current phase, and the correct line — which was being written
  — got overwritten a second and a half later by the stale one. All
  three are fixed: the title follows the phase, the counter is per
  phase, and a phase update counts as progress.
- The player now logs which audio route it started, and says plainly
  when ffplay is missing from PATH. "No sound" should never again need
  diagnosing from scratch.

Note for anyone else running this: the package deliberately ships no
ffmpeg, ffplay, yt-dlp or VLC. They must be installed separately, and
without ffplay the player will have descriptions but no video audio.
*(No longer true as of v1.6.5 — all but VLC are bundled.)*

## What's new in v1.6.3

Everything here came from running one real video the user supplied — a
ten-minute Indonesian clip, 189 MB, no captions. The transcript fallback
and the standard preset worked first time; three other things did not,
and all three failed silently.

- **The `foreign` preset returned nothing, twice, with no explanation.**
  Captured from the API: the model had spent 15,995 of its 16,000
  completion tokens on internal reasoning, leaving five for the answer.
  Raising the limit does not help — it simply thinks more — so the
  budget is now split rather than enlarged. An empty reply is also
  logged with its finish reason and token breakdown, because "no
  descriptions" with no reason is the worst possible report for someone
  who cannot see the screen.
- **Descriptions came back out of order.** Asked for speech and visuals
  together, the model answered in two passes — 00:00, 00:04, 00:12,
  00:30, then back to 00:16 — and both the SRT writer and the player
  assume time order, so the story arrived shuffled. Now sorted, as the
  Gemini path already was.
- **A dropped connection lost the whole job.** Two failures in a row on
  one 16 MB upload. Three attempts with backoff now, retrying only what
  is worth retrying: a bad key or an oversized payload fails the same
  way three times, so those are not retried.
- **Uploads are about three times smaller.** Measured on that video:
  3.4 MB for two minutes at 30 fps with audio, against 1.1 MB at 5 fps
  without — and the leaner file described *better*, still reading the
  gravestone text. A describing model samples frames rather than
  watching at 30, and this provider cannot hear audio at all, which
  since v1.6.1 travels separately as a transcript.
- **The frame cap no longer throws away the end of the video.** It kept
  the first N frames, so a cap of 30 on a ten-minute video described the
  opening two minutes and left the other eight silent. It now samples
  evenly across the whole thing.
- **Frame rates above the source are clamped.** Asking 60 fps of a 30 fps
  video made ffmpeg duplicate frames: 7,200 files and 208 MB of JPEGs
  against 3,600 and 104 MB, with the scene dedup keeping exactly the
  same 85 frames either way.
- Presets now ask for descriptions to be placed in the gaps between
  speech. Measured honestly, the model obeys this only weakly — given a
  transcript with a deliberate silent half it still chose the talky half
  56% of the time — so for dialogue-heavy content the reliable answer
  remains the player's pause-for-narration toggle, which holds the video
  whatever moment the model picked.

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
- The external binaries in `bin/`. They are not in git; fetch them once
  after cloning:

  ```
  python tools\fetch_binaries.py
  ```

  This downloads ffmpeg, ffprobe, ffplay (GPL shared build, ~86 MB) and
  yt-dlp. A system install on PATH is used as a fallback, but the
  bundled copies are the ones that get tested and shipped.
- VLC is still optional and separate; without it the player uses ffplay
  for sound.

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
- **Accessibility, verified by listening rather than by reading:**

  ```bash
  python tools/nvda_accessibility_check.py --steps 12
  ```

  This tabs through the real window and asks NVDA what it announced,
  through the local [NVDA HTTP Bridge](https://127.0.0.1:19281) plugin.
  It needs NVDA running; without the bridge it exits 2 rather than
  reporting a pass it cannot justify, so "not verified" is never
  mistaken for "fine".

  It exists because reading the source is what let v1.5.4 ship: three
  controls whose accessible name was set with `SetLabel()` looked
  correct in code, silently lost their state, and reached a real user.
  The two controls that broke then are now checked by name — the
  preset combo must announce a selected value, and the prompt box must
  announce the preset text rather than its own label. The judgement
  logic is a pure function covered by `tests\test_fixes27.py`, because
  a detector nobody has seen fail is not a detector.

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
