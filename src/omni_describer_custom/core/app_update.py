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
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
import zipfile
from contextlib import contextmanager
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
SIG_NAME = SUMS_NAME + ".sig"
# Ed25519 public key of the owner's release key (tools/release_key.py,
# made 6 Oct 2026; the secret half never leaves the owner's PC).
# SHA256SUMS.txt must carry a valid signature by it, so a release
# published with a stolen GitHub login is refused (review, HIGH).
RELEASE_PUBLIC_KEY = "024569f63cd6d1f9e0ea5c32de162eb440cb4224059bf449924ead8ee061d560"
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
    sig_url: str = ""


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
              on_progress: Callable[[int, int], None] | None = None,
              max_bytes: int = 0) -> None:
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
            done += len(chunk)
            if max_bytes and done > max_bytes:
                raise UpdateError("the download is bigger than the release "
                                  "says; nothing was installed")
            out.write(chunk)
            if on_progress:
                on_progress(done, total)


# ── Checking ─────────────────────────────────────────────────────

# Review (6 Oct 2026): fetch only this repo's release files, and only a
# plain version tag, whatever the API answer says.
_ASSET_PREFIX = f"https://github.com/{REPO}/releases/download/"
_VERSION_RE = re.compile(r"^\d+(\.\d+){1,3}$")


def parse_release(data: dict) -> Release:
    """A GitHub release (API JSON) -> Release; UpdateError if unusable."""
    tag = (data.get("tag_name") or "").strip()
    version = tag.lstrip("vV")
    if not _VERSION_RE.match(version):
        raise UpdateError(f"GitHub did not report a usable release ({tag!r})")
    assets = {a.get("name"): a for a in data.get("assets") or []}
    zip_asset = assets.get(zip_name(version))
    sums_asset = assets.get(SUMS_NAME)
    sig_asset = assets.get(SIG_NAME)
    if not zip_asset or not sums_asset or not sig_asset:
        raise UpdateError(f"release {tag} lacks {zip_name(version)}, "
                          f"{SUMS_NAME} or {SIG_NAME}")
    zip_url = zip_asset.get("browser_download_url") or ""
    sums_url = sums_asset.get("browser_download_url") or ""
    sig_url = sig_asset.get("browser_download_url") or ""
    for url in (zip_url, sums_url, sig_url):
        if not url.startswith(_ASSET_PREFIX):
            raise UpdateError(f"release {tag} points outside {REPO}: {url}")
    return Release(
        version=version, tag=tag,
        notes=(data.get("body") or "").strip(),
        page_url=data.get("html_url") or RELEASES_PAGE,
        zip_url=zip_url,
        zip_size=int(zip_asset.get("size") or 0),
        sums_url=sums_url, sig_url=sig_url)


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
    if _UNSAFE_PATH_CHARS & (set(str(folder)) | set(str(update_dir()))):
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


def verify_signature(data: bytes, sig_text: bytes,
                     public_key: str | None = None) -> None:
    """UpdateError unless `sig_text` (hex) is the release key's Ed25519
    signature of `data`. No crypto library -> refused, never skipped."""
    try:
        from nacl.exceptions import BadSignatureError
        from nacl.signing import VerifyKey
    except ImportError as e:
        raise UpdateError("cannot check the release signature (PyNaCl is "
                          "missing); nothing was installed") from e
    try:
        signature = bytes.fromhex(sig_text.decode("ascii").strip())
        VerifyKey(bytes.fromhex(public_key or RELEASE_PUBLIC_KEY)).verify(
            data, signature)
    except (BadSignatureError, ValueError, UnicodeDecodeError) as e:
        raise UpdateError("the release signature is not valid: it was not "
                          "published with the owner's key; nothing was "
                          "installed") from e


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
    The checksum list itself is trusted only with a valid signature by
    the owner's release key, checked BEFORE anything else is fetched.
    """
    sums = fetch(release.sums_url)
    if not release.sig_url:
        raise UpdateError(f"release {release.tag} is not signed; "
                          f"nothing was installed")
    verify_signature(sums, fetch(release.sig_url))
    expected = expected_sha256(sums.decode("utf-8", errors="replace"),
                               zip_name(release.version))
    folder = update_dir()
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / zip_name(release.version)
    partial = folder / (zip_name(release.version) + ".part")
    try:
        download_to(release.zip_url, partial, on_progress,
                    max_bytes=release.zip_size)
        size = partial.stat().st_size
        if release.zip_size and size != release.zip_size:
            raise UpdateError(
                f"the download is {size} bytes, the release says "
                f"{release.zip_size}; nothing was installed")
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
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
    if sum(m.file_size for m in members) > MAX_UNPACKED_BYTES:
        raise UpdateError("the update unpacks to more than 4 GB; nothing "
                          "was installed")
    return members


MAX_UNPACKED_BYTES = 4 * 1024 ** 3   # the real app unpacks to about 900 MB
_install_lock = threading.Lock()


@contextmanager
def install_lock():
    """One download-and-unpack at a time (review, 6 Oct 2026): a dialog
    closed mid-download keeps its worker running, and a second install
    would unpack into the same DescriVox.new."""
    if not _install_lock.acquire(blocking=False):
        raise UpdateError("an update is already being downloaded")
    try:
        yield
    finally:
        _install_lock.release()


def stage(zip_path: Path, folder: Path) -> Path:
    """Unpack next to the app folder `folder`; returns the staged folder.

    Same disk as the app, so the swap is a rename, not a copy.
    """
    staged_root = folder.parent / f"{folder.name}{STAGED_SUFFIX}"
    shutil.rmtree(staged_root, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as archive:
        members = _safe_members(archive)
        try:
            staged_root.mkdir(parents=True)
        except OSError as e:
            raise UpdateError(f"could not clear the previous unpacked "
                              f"update ({staged_root}): {e}") from e
        archive.extractall(staged_root, members)
    staged = staged_root / APP_FOLDER
    if not (staged / EXE_NAME).exists():
        raise UpdateError("the update did not unpack; nothing was installed")
    return staged


# ── The swap ─────────────────────────────────────────────────────

def write_apply_script(folder: Path, staged: Path, pid: int,
                       exe_name: str = EXE_NAME,
                       wait_seconds: int = 120) -> Path:
    """The cmd script that swaps the folders once process `pid` exits.

    Each way out writes its own line to apply.log. If the app has not
    exited after `wait_seconds`, it changes and starts NOTHING: the old
    app is still running, and starting it again would make two (review,
    6 Oct 2026). If the old folder cannot be moved, the old version is
    started again; if the new one cannot, the old one is moved back.
    """
    previous = folder.parent / f"{folder.name}{PREVIOUS_SUFFIX}"
    staged_root = staged.parent
    work = update_dir()
    unsafe = _UNSAFE_PATH_CHARS & set(f"{folder}{staged}{work}")
    if unsafe:
        raise UpdateError(f"a folder path contains {''.join(sorted(unsafe))}, "
                          f"which the installer cannot handle")
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
        f'set "NEWROOT={staged_root}"',
        f'set "OLD={previous}"',
        f'set "LOG={log}"',
        f'set "EXE={exe_name}"',
        f'echo waiting for {pid} > "%LOG%"',
        "set /a N=0",
        ":wait",
        rf'"%SYS%\tasklist.exe" /FI "PID eq {pid}" /NH 2>nul | "%SYS%\find.exe" " {pid} " >nul',
        "if errorlevel 1 goto gone",
        "set /a N+=1",
        f"if %N% GEQ {max(1, int(wait_seconds))} goto timed_out",
        r'"%SYS%\ping.exe" -n 2 127.0.0.1 >nul',
        "goto wait",
        ":timed_out",
        f'echo timed out: process {pid} did not exit; nothing changed >> "%LOG%"',
        "goto end",
        ":gone",
        r'"%SYS%\ping.exe" -n 2 127.0.0.1 >nul',
        'if exist "%OLD%" rmdir /s /q "%OLD%"',
        # If it is still there, "move" would put the app INSIDE it.
        'if exist "%OLD%" goto cannot_move_old',
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
        'rmdir "%NEWROOT%" >nul 2>&1',
        # Started from its own folder, as Explorer would: a working
        # folder inside update_dir() would stop finish_pending()
        # removing it (Windows will not delete a process's cwd).
        'cd /d "%APP%"',
        'start "" "%APP%\\%EXE%"',
        "goto end",
        ":rollback",
        'echo could not move the new version, rolling back >> "%LOG%"',
        'move "%OLD%" "%APP%" >nul 2>&1',
        "if not errorlevel 1 goto start_old",
        'echo ROLLBACK FAILED: the old version is in "%OLD%" >> "%LOG%"',
        "goto end",
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


def finish_pending(settings, current: str = __version__,
                   folder: Path | None = None) -> tuple[str, bool] | None:
    """(version, ok) if an update was just attempted, else None.

    Removes the downloaded zip once the new version is running; when it
    did not take, removes the unpacked copy left next to `folder` (the
    log in update_dir() is kept, it says why).
    """
    pending = str(settings.get("updates.app_pending", "") or "")
    if not pending:
        return None
    settings.set("updates.app_pending", "")
    ok = not is_newer(pending, current)
    if ok:
        shutil.rmtree(update_dir(), ignore_errors=True)
    elif folder is not None:
        leftover = folder.parent / f"{folder.name}{STAGED_SUFFIX}"
        shutil.rmtree(leftover, ignore_errors=True)
        if leftover.exists():
            logger.warning("Could not remove the unpacked update %s", leftover)
    return pending, ok


__all__ = ["APP_FOLDER", "EXE_NAME", "RELEASES_PAGE", "Release", "SUMS_NAME",
           "UpdateError", "app_dir", "can_self_install", "download",
           "expected_sha256", "finish_pending", "install_lock", "latest_release",
           "launch_apply_script", "mark_pending", "newer_release",
           "parse_release", "sha256_of", "stage", "update_dir",
           "verify_signature",
           "write_apply_script", "zip_name"]
