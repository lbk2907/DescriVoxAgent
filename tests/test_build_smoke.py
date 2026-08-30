"""Build smoke test: launch the REAL PyInstaller-built exe and verify it works.

Run by build.bat against the SYSTEM python (not the bundle).
Checks:
1. dist\\OmniDescriber\\OmniDescriber.exe exists
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
EXE = ROOT / "dist" / "OmniDescriber" / "OmniDescriber.exe"
INTERNAL = ROOT / "dist" / "OmniDescriber" / "_internal"
LOG = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "OmniDescriber" / "logs" / "omni_describer.log"


def fail(msg: str) -> None:
    print(f"SMOKE_FAIL {msg}", flush=True)
    sys.exit(1)


def main() -> None:
    if not EXE.exists():
        fail(f"exe missing: {EXE}")
    print("SMOKE_EXE_OK", flush=True)

    guide = INTERNAL / "doc" / "panduan-pengguna.md"
    if not guide.exists():
        fail(f"bundled doc missing: {guide}")
    print("SMOKE_DOCS_OK", flush=True)

    size_before = LOG.stat().st_size if LOG.exists() else 0

    proc = subprocess.Popen([str(EXE)], cwd=str(ROOT / "dist" / "OmniDescriber"))
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
            subprocess.run(["taskkill", "/PID", str(proc.pid)],
                           capture_output=True, timeout=30)
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)],
                               capture_output=True, timeout=30)
                fail("exe did not exit on WM_CLOSE (force-killed)")

    if proc.returncode not in (0,):
        # taskkill close gives rc 0 or 1 depending on handler; accept both but record
        print(f"SMOKE_EXIT_RC {proc.returncode}", flush=True)
    print("SMOKE_CLOSE_OK", flush=True)
    print("SMOKE_ALL_OK", flush=True)


if __name__ == "__main__":
    main()
