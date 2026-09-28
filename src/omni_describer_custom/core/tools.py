"""Finding the external programs the app cannot work without.

ffmpeg, ffprobe, ffplay and yt-dlp do the actual work of downloading,
cutting, compressing and playing video. Until v1.6.5 the packaged app
shipped none of them and never checked: on a machine without ffmpeg it
simply failed, phase by phase, saying nothing useful — and on a machine
without ffplay the player had descriptions but no sound, which is
exactly how one real user met it.

They are bundled now. This module is the single place that knows where
to look, so the answer is the same for every caller, and
`missing_tools()` lets the app say plainly what is absent instead of
leaving the user to guess.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Everything the app shells out to, with what breaks without it. The
# text is shown to the user, so it says what they lose, not what the
# program is called internally.
REQUIRED_TOOLS: dict[str, str] = {
    "ffmpeg": "extracting frames, compressing video for upload, "
              "reading embedded subtitles",
    "ffprobe": "reading a video's duration and frame rate",
    "ffplay": "playing the video's own sound in the player",
    "yt-dlp": "downloading from YouTube and fetching captions",
}

_EXE = ".exe" if sys.platform == "win32" else ""


def _bundle_dirs() -> list[Path]:
    """Places a bundled binary may live, most specific first.

    In a PyInstaller build __file__ sits under the extracted bundle, so
    the relative walk still works; sys._MEIPASS is checked first anyway
    because it is the one the packager guarantees.
    """
    here = Path(__file__).resolve()
    dirs: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        dirs.append(Path(meipass) / "bin")
    dirs += [
        here.parent.parent.parent / "bin",   # repo layout: src/../bin
        here.parent.parent / "bin",
        Path(sys.executable).parent / "bin",  # next to the .exe
        Path.cwd() / "bin",
    ]
    return dirs


# ── Updates the user chose to install (v1.7.7) ──────────────────
#
# Help > Check for Updates can fetch a newer yt-dlp, because YouTube
# changes often enough to break an old one. The update lives OUTSIDE
# the bundle, so the shipped copy is never touched, works from a
# read-only install folder, and "Use bundled version" is just a delete.
# It is used only while its SHA-256 still matches the one recorded when
# it was verified against the publisher's own checksum list.

UPDATES_MANIFEST = "updates.json"
# The one tool Help > Check for Updates can update (core/updater.py).
UPDATABLE_TOOL = "yt-dlp"


def user_tools_dir() -> Path:
    override = os.environ.get("ODC_TOOLS_DIR", "").strip()
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "OmniDescriber" / "tools"


def read_updates_manifest() -> dict:
    import json
    try:
        return json.loads((user_tools_dir() / UPDATES_MANIFEST)
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_verified_cache: dict[str, tuple[tuple[int, int], bool]] = {}


def _user_copy(name: str) -> str:
    """The user-installed update of `name`, if present and intact."""
    entry = read_updates_manifest().get(name) or {}
    path = user_tools_dir() / f"{name}{_EXE}"
    expected = entry.get("sha256", "")
    if not expected or not path.is_file():
        return ""
    stat = path.stat()
    key = (stat.st_size, int(stat.st_mtime))
    cached = _verified_cache.get(str(path))
    if cached and cached[0] == key:
        return str(path) if cached[1] else ""
    import hashlib
    ok = hashlib.sha256(path.read_bytes()).hexdigest() == expected
    if not ok:
        logger.error("Updated %s at %s no longer matches its verified "
                     "SHA-256; using the bundled copy", name, path)
    _verified_cache[str(path)] = (key, ok)
    return str(path) if ok else ""


def forget_verification() -> None:
    """Drop cached checks after an update is installed or removed."""
    _verified_cache.clear()


def bundled_tool(name: str) -> str:
    """The copy shipped with the app only (no update, no PATH), or ""."""
    filename = f"{name}{_EXE}"
    for directory in _bundle_dirs():
        candidate = directory / filename
        if candidate.exists():
            return str(candidate)
    return ""


def find_tool(name: str) -> str:
    """Absolute path to a tool: a verified user update first, then the
    bundled copy, else its bare name for PATH.

    Returning the bare name rather than "" keeps the old behaviour for
    anyone running from source with ffmpeg on PATH: the subprocess call
    still works, and the failure (if any) surfaces where it always did.
    """
    updated = _user_copy(name)
    if updated:
        return updated
    filename = f"{name}{_EXE}"
    for directory in _bundle_dirs():
        candidate = directory / filename
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name)
    return found or name


def tool_available(name: str) -> bool:
    """True when the tool can actually be run from somewhere."""
    path = find_tool(name)
    return os.path.isabs(path) or shutil.which(path) is not None


def missing_tools() -> list[tuple[str, str]]:
    """(name, what it is needed for) for every tool that is absent."""
    return [(name, why) for name, why in REQUIRED_TOOLS.items()
            if not tool_available(name)]


def log_tool_status() -> None:
    """Record where each tool came from — bundled, PATH, or nowhere.

    Written at startup so that a bug report of "it does nothing" can be
    answered from the log instead of a diagnosis session.
    """
    for name in REQUIRED_TOOLS:
        path = find_tool(name)
        if os.path.isabs(path):
            source = ("updated by user" if path == _user_copy(name) else
                      "bundled" if any(str(d) in path for d in _bundle_dirs())
                      else "system")
            logger.info("Tool %s: %s (%s)", name, path, source)
        elif shutil.which(path):
            logger.info("Tool %s: %s (PATH)", name, shutil.which(path))
        else:
            logger.error("Tool %s: NOT FOUND — needed for %s",
                         name, REQUIRED_TOOLS[name])
