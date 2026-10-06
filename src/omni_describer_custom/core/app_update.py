"""Help > Check for Updates: a newer DescriVox Agent, verified, reversible.

Owner, 6 Oct 2026: users check for a new version of the app itself, and
the app downloads and installs it. The source is the GitHub Releases of
REPO; each release carries the zip that build.bat makes and SHA256SUMS.txt
(tools/release_files.py). Nothing is installed unless:

  1. the zip's SHA-256 matches its line in that release's SHA256SUMS.txt,
  2. the zip holds only paths under DescriVox/ (no "..", no drive), and
     DescriVox/DescriVox.exe is there, and
  3. the user said yes, with no work running.

Installing swaps folders, never overwrites files in place: the new build
is unpacked NEXT to the app (same disk, so a move is a rename), the app
closes, and a small script (write_apply_script) waits for it to exit,
renames the app folder to DescriVox.previous, renames the new one into
place and starts it. If the second rename fails it renames the old folder
back and starts that. Settings and projects live elsewhere (%APPDATA%,
Documents) and are not touched. On the next start, finish_pending() says
whether the update took.

Network calls here are synchronous; the UI runs them on a worker thread.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

from .. import __version__
from .updater import UpdateError, is_newer

logger = logging.getLogger(__name__)

REPO = "lbk2907/DescriVoxAgent"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
APP_FOLDER = "DescriVox"
EXE_NAME = "DescriVox.exe"
SUMS_NAME = "SHA256SUMS.txt"
PREVIOUS_SUFFIX = ".previous"
STAGED_SUFFIX = ".new"
# cmd.exe cannot carry these safely inside a quoted SET; such a folder
# gets the download page instead of a self-install.
_UNSAFE_PATH_CHARS = set('%"!^')


def zip_name(version: str) -> str:
    return f"DescriVox-Agent-{version}-win64.zip"


@dataclass(frozen=True)
class Release:
    version: str
    tag: str
    notes: str
    page_url: str
    zip_url: str
    zip_size: int
    sums_url: str


def update_dir() -> Path:
    """Where downloads wait (ODC_UPDATE_DIR isolates tests)."""
    override = os.environ.get("ODC_UPDATE_DIR", "").strip()
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "OmniDescriber" / "update"


def _fetch(url: str, timeout: float = 30.0) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "DescriVox-update-check",
                      "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _download(url: str, dest: Path,
              on_progress: Callable[[int, int], None] | None = None) -> None:
    request = urllib.request.Request(
        url, headers={"User-Agent": "DescriVox-update-check"})
    with urllib.request.urlopen(request, timeout=60) as response, \
            open(dest, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if on_progress:
                on_progress(done, total)


# ── Checking ─────────────────────────────────────────────────────

def parse_release(data: dict) -> Release:
    """A GitHub release (API JSON) -> Release; UpdateError if unusable."""
    tag = (data.get("tag_name") or "").strip()
    version = tag.lstrip("vV")
    if not version:
        raise UpdateError("GitHub did not report a DescriVox release")
    assets = {a.get("name"): a for a in data.get("assets") or []}
    zip_asset = assets.get(zip_name(version))
    sums_asset = assets.get(SUMS_NAME)
    if not zip_asset or not sums_asset:
        raise UpdateError(
            f"release {tag} has no {zip_name(version)} and {SUMS_NAME}")
    return Release(
        version=version, tag=tag,
        notes=(data.get("body") or "").strip(),
        page_url=data.get("html_url") or RELEASES_PAGE,
        zip_url=zip_asset.get("browser_download_url") or "",
        zip_size=int(zip_asset.get("size") or 0),
        sums_url=sums_asset.get("browser_download_url") or "")


def latest_release(fetch: Callable[[str], bytes] = _fetch) -> Release:
    return parse_release(json.loads(fetch(LATEST_API).decode("utf-8")))


def newer_release(fetch: Callable[[str], bytes] = _fetch,
                  current: str = __version__) -> Release | None:
    """The latest release if it is newer than `current`, else None."""
    release = latest_release(fetch)
    return release if is_newer(release.version, current) else None


# ── Where the app is, and whether it may replace itself ──────────

def app_dir() -> Path | None:
    """The DescriVox folder of a built copy; None when run from source."""
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve().parent


def can_self_install(folder: Path | None) -> tuple[bool, str]:
    """(True, "") or (False, why) — why is an i18n key suffix."""
    if folder is None:
        return False, "from_source"
    if folder.name.lower() != APP_FOLDER.lower() or \
            not (folder / EXE_NAME).exists():
        return False, "unknown_layout"
    if _UNSAFE_PATH_CHARS & set(str(folder)):
        return False, "path_chars"
    probe = folder.parent / f".descrivox-write-test-{os.getpid()}"
    try:
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False, "not_writable"
    return True, ""


# ── Download, verify, unpack ─────────────────────────────────────

def expected_sha256(sums_text: str, name: str) -> str:
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            return parts[0].lower()
    raise UpdateError(f"{name} is not listed in {SUMS_NAME}")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(release: Release, fetch: Callable[[str], bytes] = _fetch,
             download_to: Callable[..., None] = _download,
             on_progress: Callable[[int, int], None] | None = None) -> Path:
    """Download the release zip and check it. Returns its path.

    Raises UpdateError (and deletes the file) on a checksum mismatch.
    """
    expected = expected_sha256(
        fetch(release.sums_url).decode("utf-8", errors="replace"),
        zip_name(release.version))
    folder = update_dir()
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / zip_name(release.version)
    partial = folder / (zip_name(release.version) + ".part")
    download_to(release.zip_url, partial, on_progress)
    actual = sha256_of(partial)
    if actual != expected:
        partial.unlink(missing_ok=True)
        raise UpdateError(
            f"checksum mismatch: the download does not match the one "
            f"published for {release.tag}; nothing was installed")
    os.replace(partial, dest)
    return dest


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    for info in members:
        name = info.filename.replace("\\", "/")
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or ":" in name or \
                not path.parts or path.parts[0] != APP_FOLDER:
            raise UpdateError(
                f"the update contains an unexpected path ({info.filename}); "
                f"nothing was installed")
    names = {m.filename.replace("\\", "/") for m in members}
    if f"{APP_FOLDER}/{EXE_NAME}" not in names:
        raise UpdateError(f"the update has no {EXE_NAME}; nothing was installed")
    return members


def stage(zip_path: Path, folder: Path) -> Path:
    """Unpack next to the app folder `folder`; returns the staged folder.

    Same disk as the app, so the swap is a rename, not a copy.
    """
    staged_root = folder.parent / f"{folder.name}{STAGED_SUFFIX}"
    shutil.rmtree(staged_root, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as archive:
        members = _safe_members(archive)
        staged_root.mkdir(parents=True)
        archive.extractall(staged_root, members)
    staged = staged_root / APP_FOLDER
    if not (staged / EXE_NAME).exists():
        raise UpdateError("the update did not unpack; nothing was installed")
    return staged


# ── The swap ─────────────────────────────────────────────────────

def write_apply_script(folder: Path, staged: Path, pid: int,
                       exe_name: str = EXE_NAME) -> Path:
    """The cmd script that swaps the folders once process `pid` exits.

    Waits at most ~2 minutes for the app to close; if it does not, or
    the old folder cannot be moved, it starts the old version again.
    """
    previous = folder.parent / f"{folder.name}{PREVIOUS_SUFFIX}"
    work = update_dir()
    work.mkdir(parents=True, exist_ok=True)
    log = work / "apply.log"
    script = work / "apply_update.cmd"
    lines = [
        "@echo off",
        # Full paths: a PATH with Git or Cygwin first finds THEIR find and
        # ping (seen on the author's PC: the wait never saw the app).
        r'set "SYS=%SystemRoot%\System32"',
        r'"%SYS%\chcp.com" 65001 >nul',
        "setlocal",
        f'set "APP={folder}"',
        f'set "NEW={staged}"',
        f'set "OLD={previous}"',
        f'set "LOG={log}"',
        f'set "EXE={exe_name}"',
        f'echo waiting for {pid} > "%LOG%"',
        "set /a N=0",
        ":wait",
        rf'"%SYS%\tasklist.exe" /FI "PID eq {pid}" /NH 2>nul | "%SYS%\find.exe" " {pid} " >nul',
        "if errorlevel 1 goto gone",
        "set /a N+=1",
        "if %N% GEQ 120 goto start_old",
        r'"%SYS%\ping.exe" -n 2 127.0.0.1 >nul',
        "goto wait",
        ":gone",
        r'"%SYS%\ping.exe" -n 2 127.0.0.1 >nul',
        'if exist "%OLD%" rmdir /s /q "%OLD%"',
        # An antivirus scan can hold a file for a moment: try a few times.
        "set /a T=0",
        ":move_old",
        'move "%APP%" "%OLD%" >nul 2>&1',
        "if not errorlevel 1 goto move_new",
        "set /a T+=1",
        "if %T% GEQ 10 goto cannot_move_old",
        r'"%SYS%\ping.exe" -n 2 127.0.0.1 >nul',
        "goto move_old",
        ":cannot_move_old",
        'echo could not move the old version >> "%LOG%"',
        "goto start_old",
        ":move_new",
        'move "%NEW%" "%APP%" >nul 2>&1',
        "if errorlevel 1 goto rollback",
        'echo updated >> "%LOG%"',
        # Started from its own folder, as Explorer would: a working
        # folder inside update_dir() would stop finish_pending()
        # removing it (Windows will not delete a process's cwd).
        'cd /d "%APP%"',
        'start "" "%APP%\\%EXE%"',
        "goto end",
        ":rollback",
        'echo could not move the new version, rolling back >> "%LOG%"',
        'move "%OLD%" "%APP%" >nul 2>&1',
        ":start_old",
        'echo started the old version >> "%LOG%"',
        'cd /d "%APP%"',
        'start "" "%APP%\\%EXE%"',
        ":end",
        "endlocal",
    ]
    script.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return script


def launch_apply_script(script: Path) -> subprocess.Popen:
    """Start the swap script with no window; it outlives the app."""
    flags = (getattr(subprocess, "CREATE_NO_WINDOW", 0)
             | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    # Not inside the app folder (it is about to be renamed) nor inside
    # update_dir() (removed after the update): Windows' own folder.
    neutral = os.environ.get("SystemRoot") or str(Path.home())
    return subprocess.Popen(["cmd.exe", "/c", str(script)],
                            creationflags=flags, close_fds=True, cwd=neutral)


# ── After the restart ────────────────────────────────────────────

def mark_pending(settings, version: str) -> None:
    settings.set("updates.app_pending", version)


def finish_pending(settings, current: str = __version__) -> tuple[str, bool] | None:
    """(version, ok) if an update was just attempted, else None.

    Removes the downloaded zip once the new version is running.
    """
    pending = str(settings.get("updates.app_pending", "") or "")
    if not pending:
        return None
    settings.set("updates.app_pending", "")
    ok = not is_newer(pending, current)
    if ok:
        shutil.rmtree(update_dir(), ignore_errors=True)
    return pending, ok


__all__ = ["APP_FOLDER", "EXE_NAME", "RELEASES_PAGE", "Release", "SUMS_NAME",
           "UpdateError", "app_dir", "can_self_install", "download",
           "expected_sha256", "finish_pending", "latest_release",
           "launch_apply_script", "mark_pending", "newer_release",
           "parse_release", "sha256_of", "stage", "update_dir",
           "write_apply_script", "zip_name"]
