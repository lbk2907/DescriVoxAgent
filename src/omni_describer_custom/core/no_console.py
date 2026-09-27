"""Keep ffmpeg, ffprobe and yt-dlp from opening console windows.

The shipped build is a windowed exe with no console of its own, so
Windows gives every console child (ffmpeg, ffprobe, yt-dlp) a fresh
console window. It opens in front of the app and takes focus: NVDA
announced "terminal" and read out the ffmpeg path in the middle of a
job (real run, v1.7.3, 15-minute video). Run from source the children
share python.exe's console, which is why no test ever saw it.

install() makes CREATE_NO_WINDOW the default for every child process,
including those started through asyncio, unless a caller passes its
own creationflags.
"""

from __future__ import annotations

import subprocess
import sys

_installed = False


def install() -> None:
    global _installed
    if _installed or sys.platform != "win32":
        return
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    original = subprocess.Popen.__init__

    def __init__(self, *args, **kwargs):
        if not kwargs.get("creationflags"):
            kwargs["creationflags"] = no_window
        original(self, *args, **kwargs)

    subprocess.Popen.__init__ = __init__
    _installed = True
