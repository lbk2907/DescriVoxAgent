"""NVDA smoke check for CI: does NVDA speak this app's window and controls?

Experiment (phase 38.1, 9 Oct 2026, owner: "cuba experiment dulu"). The
listening tools (nvda_*_check.py) need the owner's local NVDA HTTP Bridge
add-on, which is not public. A GitHub runner instead starts a portable NVDA
with the silence synth and `--log-level=12` (input/output), at which NVDA
logs every utterance as `Speaking [...]`. This reads those lines.

    python tools/ci_nvda_smoke.py --log C:\\nvda.log

Exit 0 VERIFIED, 1 FAIL (NVDA ran but did not speak the app),
2 INCONCLUSIVE (no NVDA speech at all, or the app could not be fronted).
Never run on the owner's PC: it starts the app and presses Tab.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import safe_keys  # noqa: E402,F401  (guards every keystroke; import first)
from nvda_accessibility_check import APP_TITLE_HINT, launch  # noqa: E402

TAB_STEPS = 12
SPEECH_WAIT_SECONDS = 1.2
SPEAKING = re.compile(r"^Speaking (\[.*\])\s*$")


class SpeechLog:
    """Reads the `Speaking [...]` lines NVDA appended since the last read."""

    def __init__(self, path: Path):
        self.path = path
        self.offset = path.stat().st_size if path.exists() else 0

    def new_utterances(self) -> list[str]:
        if not self.path.exists():
            return []
        with self.path.open("rb") as f:
            f.seek(self.offset)
            data = f.read()
        # Only whole lines: NVDA may be mid-write, and a half line consumed
        # now would never match later (review, 9 Oct 2026).
        end = data.rfind(b"\n") + 1
        self.offset += end
        text = data[:end].decode("utf-8", errors="replace")
        return [m.group(1) for line in text.splitlines() if (m := SPEAKING.match(line.strip()))]


def front(win) -> bool:
    import win32gui

    try:
        win32gui.SetForegroundWindow(win.handle)
    except Exception as e:
        print(f"SetForegroundWindow: {e}")
        try:
            win.set_focus()
        except Exception as e2:
            print(f"set_focus: {e2}")
    time.sleep(1.5)
    return win32gui.GetForegroundWindow() == win.handle


def walk(log: SpeechLog) -> list[list[str]]:
    from pywinauto.keyboard import send_keys

    heard: list[list[str]] = []
    for step in range(1, TAB_STEPS + 1):
        send_keys("{TAB}")
        time.sleep(SPEECH_WAIT_SECONDS)
        said = log.new_utterances()
        print(f"  Tab {step:2}: {' | '.join(said) or '(silent)'}")
        heard.append(said)
    return heard


def judge(on_open: list[str], heard: list[list[str]]) -> tuple[int, str]:
    everything = on_open + [u for step in heard for u in step]
    if not everything:
        return 2, "INCONCLUSIVE: NVDA logged no speech at all (not running, or wrong log level)"
    if not any(APP_TITLE_HINT.lower() in u.lower() for u in everything):
        return 1, f"FAIL: NVDA never said the window name '{APP_TITLE_HINT}'"
    silent = sum(1 for step in heard if not step)
    if silent > len(heard) // 2:
        return 1, f"FAIL: {silent} of {len(heard)} Tab stops were silent"
    spoken = len(heard) - silent
    # Weak on purpose: any speech after a Tab counts. Names are not checked.
    return 0, f"VERIFIED: window name spoken; speech after {spoken}/{len(heard)} Tabs"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True, type=Path, help="NVDA log file (--log-level=12)")
    args = ap.parse_args()

    log = SpeechLog(args.log)
    try:
        proc, win = launch(frozen=False)
    except SystemExit as e:  # launch() exits with a message when no window appears
        print(f"INCONCLUSIVE: {e}")
        return 2
    try:
        if not front(win):
            print("INCONCLUSIVE: the app window could not be brought to the front")
            return 2
        on_open = log.new_utterances()
        print(f"  on open: {' | '.join(on_open) or '(silent)'}")
        try:
            heard = walk(log)
        except safe_keys.ForeignFocus as e:
            print(f"INCONCLUSIVE: a Tab was refused, the app lost the focus ({e})")
            return 2
        code, verdict = judge(on_open, heard)
        print(verdict)
        return code
    finally:
        # The whole tree: the app may have started speech or agent helpers.
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        proc.wait(timeout=30)


if __name__ == "__main__":
    sys.exit(main())
