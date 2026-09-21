# Third-party components shipped with Omni Describer Custom

This app bundles programs written by other people. Their licences are
listed here, with the obligations that come with passing the app on to
someone else.

## FFmpeg — ffmpeg.exe, ffprobe.exe, ffplay.exe and the av*/sw* DLLs

- **Version shipped:** see `bin/FFMPEG-VERSION.txt`
- **Build:** BtbN FFmpeg-Builds, `win64-gpl-shared`
- **Licence:** GNU GPL version 3 — full text in `bin/FFMPEG-LICENSE.txt`
- **Upstream source:** <https://github.com/FFmpeg/FFmpeg>
- **Build recipe:** <https://github.com/BtbN/FFmpeg-Builds>

This is the GPL build, not the LGPL one, because the app encodes its
upload copies with `libx264`, and libx264 exists only in GPL builds.

**What that means when you share this app.** Handing the whole folder
or zip to another person is distributing FFmpeg, so whoever does that
also has to make FFmpeg's corresponding source available — pointing at
the two links above satisfies this, provided the version matches what
`bin/FFMPEG-VERSION.txt` records. Keep `bin/FFMPEG-LICENSE.txt` in the
folder; do not strip it out.

The app runs FFmpeg as a separate program (`subprocess`), never as a
linked library. That is the arrangement the GPL treats as aggregation,
so the GPL applies to the FFmpeg binaries, not to this app's own code.

## yt-dlp — yt-dlp.exe

- **Licence:** Unlicense (public domain)
- **Source:** <https://github.com/yt-dlp/yt-dlp>

No obligations attach to passing it on.

## Python packages

Installed from PyPI and collected into the bundle by PyInstaller:
wxPython (wxWindows Library Licence), openai, edge-tts, pyttsx3,
faster-whisper, ctranslate2, onnxruntime, tokenizers, av, Pillow,
aiohttp, huggingface-hub — each under its own permissive licence (MIT,
BSD or Apache 2.0). PyInstaller's bootloader carries a GPL exception
that permits distributing the frozen app under any licence.

## This app's own code

No licence is declared yet — the repository has no `LICENSE` file, so
by default nobody but the copyright holder has permission to
redistribute the app's own source. That is a choice still to be made;
it does not affect the FFmpeg obligations above, which apply to the
FFmpeg binaries regardless.
