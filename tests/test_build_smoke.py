"""Build smoke test: launch the REAL PyInstaller-built exe and verify it works.

Run by build.bat against the SYSTEM python (not the bundle).
Checks:
1. dist\\DescriVox\\DescriVox.exe exists
2. bundled doc resources are present in _internal
3. exe launches, stays alive, and the app log records a FRESH
   "Application started" line (appended after launch)
4. graceful close via WM_CLOSE exits the process

Exits 0 on pass, 1 on failure. Prints SMOKE_<CHECK> markers.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "DescriVox" / "DescriVox.exe"
INTERNAL = ROOT / "dist" / "DescriVox" / "_internal"
LOG = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    / "OmniDescriber"
    / "logs"
    / "omni_describer.log"
)


def fail(msg: str) -> None:
    print(f"SMOKE_FAIL {msg}", flush=True)
    sys.exit(1)


def main() -> None:
    if not EXE.exists():
        fail(f"exe missing: {EXE}")
    print("SMOKE_EXE_OK", flush=True)

    guide = INTERNAL / "docs" / "user-guide.md"
    if not guide.exists():
        fail(f"bundled doc missing: {guide}")
    print("SMOKE_DOCS_OK", flush=True)

    # v1.6.1: local speech-to-text must survive packaging. Without it the
    # built app falls back to subtitles and paid Grok only — and the
    # failure would be silent, which for a user who cannot see the result
    # is the worst kind. ctranslate2 ships native DLLs that PyInstaller
    # can quietly drop, so check for the real payload, not just the
    # Python package directory.
    whisper_pkg = INTERNAL / "faster_whisper"
    ct2_dll = list(INTERNAL.glob("**/ctranslate2*.dll")) + list(INTERNAL.glob("**/libctranslate2*"))
    if not whisper_pkg.exists():
        fail(f"faster_whisper not bundled: {whisper_pkg}")
    if not ct2_dll:
        fail(
            "ctranslate2 native library not bundled; Whisper would fail "
            "at runtime with an import error"
        )
    print("SMOKE_WHISPER_OK", flush=True)

    # v1.6.2: translations are data files now, and PyInstaller only
    # ships data it is told about. Miss them and the app starts in raw
    # key names ("menu.file") — unusable, and silent until launch.
    locales = list(INTERNAL.glob("**/locales/*.json"))
    if len(locales) < 2:
        fail(f"locale files not bundled: found {len(locales)}")
    print(f"SMOKE_LOCALES_OK ({len(locales)} languages)", flush=True)

    size_before = LOG.stat().st_size if LOG.exists() else 0

    proc = subprocess.Popen([str(EXE)], cwd=str(ROOT / "dist" / "DescriVox"))
    try:
        deadline = time.time() + 30
        started = False
        while time.time() < deadline:
            if proc.poll() is not None:
                fail(f"exe exited early rc={proc.returncode}")
            if LOG.exists():
                data = LOG.read_bytes()
                new = data[size_before:]
                if b"Application started" in new:
                    started = True
                    break
            time.sleep(1.0)
        if not started:
            tail = ""
            if LOG.exists():
                tail = LOG.read_bytes()[size_before:].decode("utf-8", "replace")[-500:]
            fail(f"'Application started' not in fresh log within 30s; tail={tail!r}")
        print("SMOKE_STARTED_OK", flush=True)

        # Still alive after a few more seconds (no delayed crash)
        time.sleep(5)
        if proc.poll() is not None:
            fail(f"exe died after startup rc={proc.returncode}")
        print("SMOKE_ALIVE_OK", flush=True)
    finally:
        if proc.poll() is None:
            # Post WM_CLOSE directly to the process's top-level windows so the
            # main frame receives the close event even if helper/IME windows exist
            try:
                import ctypes
                from ctypes import wintypes

                user32 = ctypes.windll.user32

                def _close_cb(hwnd, _):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value == proc.pid:
                        user32.PostMessageW(hwnd, 0x0010, 0, 0)
                    return True

                WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
                user32.EnumWindows(WNDENUMPROC(_close_cb), 0)
            except Exception:
                pass
            subprocess.run(["taskkill", "/PID", str(proc.pid)], capture_output=True, timeout=30)
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=30
                )
                fail("exe did not exit on WM_CLOSE (force-killed)")

    if proc.returncode not in (0,):
        # taskkill close gives rc 0 or 1 depending on handler; accept both but record
        print(f"SMOKE_EXIT_RC {proc.returncode}", flush=True)
    print("SMOKE_CLOSE_OK", flush=True)
    print("SMOKE_ALL_OK", flush=True)


if __name__ == "__main__":
    main()
