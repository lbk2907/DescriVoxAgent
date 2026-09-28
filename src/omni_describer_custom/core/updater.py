"""Help > Check for Updates: a newer yt-dlp, verified, reversible.

YouTube changes often enough that a months-old yt-dlp stops
downloading. The copy bundled with the app is pinned and hash-checked
at build time (tools/fetch_binaries.py); this lets the user pull a
newer one between releases without rebuilding anything.

An update is installed only when:
  1. its SHA-256 matches the line for yt-dlp.exe in the SHA2-256SUMS
     file published with that same release, and
  2. the downloaded program runs and reports exactly that version.

It is saved to core.tools.user_tools_dir(), never over the bundled
copy. core.tools.find_tool() prefers it only while its hash still
matches, and revert() removes it.

Network calls here are synchronous; the UI runs them on a worker thread.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import time
import urllib.request
from typing import Callable

from . import tools

logger = logging.getLogger(__name__)

TOOL = tools.UPDATABLE_TOOL
LATEST_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
RELEASE_FILE = "https://github.com/yt-dlp/yt-dlp/releases/download/{tag}/{name}"
EXE_NAME = "yt-dlp.exe"
CHECK_EVERY_SECONDS = 7 * 24 * 3600


class UpdateError(Exception):
    """Why an update was refused. Nothing was changed when this is raised."""


def _fetch(url: str, timeout: float = 120.0) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "OmniDescriber-update-check"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def tool_version(path: str) -> str:
    """What the program at `path` says its version is ("" if it won't run)."""
    if not path:
        return ""
    try:
        out = subprocess.run([path, "--version"], capture_output=True,
                             text=True, timeout=60)
        lines = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
        return lines[-1] if out.returncode == 0 and lines else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _version_key(version: str) -> tuple[int, ...]:
    parts = []
    for piece in version.strip().lstrip("v").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(candidate: str, current: str) -> bool:
    if not candidate:
        return False
    if not current:
        return True
    return _version_key(candidate) > _version_key(current)


def status() -> dict:
    """What is in use now, and what shipped with the app."""
    in_use = tools.find_tool(TOOL)
    bundled = tools.bundled_tool(TOOL)
    return {
        "in_use_path": in_use,
        "in_use_version": tool_version(in_use),
        "bundled_version": tool_version(bundled),
        "using_update": bool(tools._user_copy(TOOL)),
    }


def latest_version(fetch: Callable[[str], bytes] = _fetch) -> str:
    data = json.loads(fetch(LATEST_API).decode("utf-8"))
    tag = (data.get("tag_name") or "").strip()
    if not tag:
        raise UpdateError("GitHub did not report a latest yt-dlp release")
    return tag


def _expected_sha256(sums_text: str) -> str:
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == EXE_NAME:
            return parts[0].lower()
    raise UpdateError(f"{EXE_NAME} is not listed in the release checksums")


def install(tag: str, fetch: Callable[[str], bytes] = _fetch,
            on_status: Callable[[str], None] | None = None) -> str:
    """Download, verify and install yt-dlp `tag`. Returns the version.

    Raises UpdateError, leaving whatever was in use untouched, when the
    checksum or the version does not match.
    """
    def say(key: str) -> None:
        if on_status:
            on_status(key)

    say("checksums")
    sums = fetch(RELEASE_FILE.format(tag=tag, name="SHA2-256SUMS"))
    expected = _expected_sha256(sums.decode("utf-8", errors="replace"))
    say("downloading")
    data = fetch(RELEASE_FILE.format(tag=tag, name=EXE_NAME))
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise UpdateError(
            f"checksum mismatch: the download does not match the one the "
            f"publisher lists for {tag}; nothing was installed")

    folder = tools.user_tools_dir()
    folder.mkdir(parents=True, exist_ok=True)
    staging = folder / "yt-dlp.new.exe"
    target = folder / EXE_NAME
    staging.write_bytes(data)
    try:
        say("testing")
        version = tool_version(str(staging))
        if version != tag:
            raise UpdateError(
                f"the downloaded program reports version {version or 'none'}, "
                f"not {tag}; nothing was installed")
        os.replace(staging, target)
    finally:
        if staging.exists():
            try:
                staging.unlink()
            except OSError:
                pass

    manifest = tools.read_updates_manifest()
    manifest[TOOL] = {"version": version, "sha256": actual,
                      "installed": time.strftime("%Y-%m-%d %H:%M:%S")}
    (folder / tools.UPDATES_MANIFEST).write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    tools.forget_verification()
    logger.info("yt-dlp %s installed at %s (SHA-256 verified)", version, target)
    return version


def revert() -> bool:
    """Go back to the bundled yt-dlp. True if an update was removed."""
    folder = tools.user_tools_dir()
    removed = False
    exe = folder / EXE_NAME
    if exe.exists():
        exe.unlink()
        removed = True
    manifest = tools.read_updates_manifest()
    if manifest.pop(TOOL, None) is not None:
        (folder / tools.UPDATES_MANIFEST).write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")
        removed = True
    tools.forget_verification()
    if removed:
        logger.info("Reverted to the bundled yt-dlp")
    return removed


def weekly_check_due(settings, now: float | None = None) -> bool:
    last = settings.get("updates.last_check", 0) or 0
    try:
        last = float(last)
    except (TypeError, ValueError):
        last = 0.0
    return (now or time.time()) - last >= CHECK_EVERY_SECONDS


def record_check(settings, now: float | None = None) -> None:
    settings.set("updates.last_check", int(now or time.time()))


def available_update(fetch: Callable[[str], bytes] = _fetch) -> str:
    """The newer version if there is one, else ""."""
    latest = latest_version(fetch)
    current = tool_version(tools.find_tool(TOOL))
    return latest if is_newer(latest, current) else ""


__all__ = ["UpdateError", "available_update", "install", "is_newer",
           "latest_version", "record_check", "revert", "status",
           "tool_version", "weekly_check_due"]
