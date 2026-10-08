"""Check the narration hold in the SHIPPED build, with the user's reader.

The narration hold pauses the video while a description is spoken and
resumes it when the speech ends. For a screen-reader voice the end is
found by listening to the reader's audio (core/audio_meter.py). That
was measured from source; this checks the frozen exe, because the
source working has not meant the build working before — Prism once
shipped dead while every test passed.

Drives the real app the way its user does, by keyboard, confirming
each step through NVDA: Play Video with Existing Descriptions, pick the
clip, accept the subtitle file found beside it, press Play. Then reads
the app's own log for how long the video waited and whether the meter
heard the end.

    python tools/e2e_player_hold.py

Needs NVDA running with the nvdaHttpBridge plugin, and a build in dist/.
NVDA will speak the test description aloud — that is the point.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import safe_keys  # noqa: E402  (guards every keystroke; import first)

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from e2e_full_verify import (  # noqa: E402
    answer_file_dialog,
    bridge_ready,
    focus_and_activate,
)

WORK = Path(os.environ["TEMP"]) / "odc_frozen_hold"
LOG = Path(os.environ["LOCALAPPDATA"]) / "OmniDescriber" / "logs" / "omni_describer.log"


def main() -> int:
    clip = WORK / "hold_test.mp4"
    config = WORK / "cfg"
    exe = REPO / "dist" / "DescriVox" / "DescriVox.exe"
    for needed in (clip, config / "settings.json", exe):
        if not needed.exists():
            print(f"missing: {needed}")
            return 2
    ready, detail = bridge_ready()
    if not ready:
        print(f"NVDA bridge not answering: {detail}")
        return 2
    print(f"Bridge up: {detail}")

    log_start = LOG.stat().st_size if LOG.exists() else 0
    env = dict(os.environ, ODC_CONFIG_DIR=str(config))
    proc = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env)
    safe_keys.allow(proc.pid)

    from pywinauto import Desktop

    desktop = Desktop(backend="uia")
    win = None
    for _ in range(120):
        try:
            candidate = desktop.window(title_re=".*DescriVox Agent.*")
            if candidate.exists() and candidate.is_visible():
                win = candidate
                break
        except Exception:
            pass
        time.sleep(1)
    if win is None:
        proc.terminate()
        print("app never appeared")
        return 2
    time.sleep(2)

    try:
        ok, detail = focus_and_activate(win, "Play Video with Existing")
        print(f"  [{'OK  ' if ok else 'FAIL'}] opened the play-existing flow — {detail}")
        if not ok:
            return 1
        ok, detail = answer_file_dialog(clip, proc.pid)
        print(f"  [{'OK  ' if ok else 'FAIL'}] chose the clip — {detail}")
        if not ok:
            return 1

        # "Found hold_test.srt next to this video. Use it?" — Enter takes
        # the default, which is "Use this file".
        from pywinauto.keyboard import send_keys

        time.sleep(2.0)
        send_keys("{ENTER}")
        time.sleep(4.0)

        player = None
        for _ in range(20):
            try:
                candidate = desktop.window(title_re=".*(Player|Pemain).*")
                if candidate.exists() and candidate.is_visible():
                    player = candidate
                    break
            except Exception:
                pass
            time.sleep(0.5)
        print(f"  [{'OK  ' if player else 'FAIL'}] player window opened")
        if player is None:
            return 1

        ok, detail = focus_and_activate(player, "Play")
        print(f"  [{'OK  ' if ok else 'FAIL'}] pressed Play — {detail}")
        if not ok:
            return 1

        # The description sits at 1 s and is 26 words long.
        deadline = time.monotonic() + 40
        released = meter = None
        while time.monotonic() < deadline and not released:
            time.sleep(1.0)
            if not LOG.exists():
                continue
            with open(LOG, "rb") as f:
                f.seek(log_start)
                fresh = f.read().decode("utf-8", "replace")
            meter = meter or re.search(
                r"Speech end via audio meter on (\w+): (\S+) \(([\d.]+)s\)", fresh
            )
            released = re.search(r"Narration hold released after ([\d.]+)s \(voice: (\S+)\)", fresh)
    finally:
        proc.terminate()

    print()
    if meter:
        print(f"  meter: {meter.group(1)} -> {meter.group(2)} after {meter.group(3)}s")
    else:
        print("  meter: no line in the log")
    if released:
        held, voice = float(released.group(1)), released.group(2)
        print(f"  hold:  video waited {held:.2f}s (voice: {voice})")
    else:
        print("  hold:  no release line in the log")

    passed = bool(
        released
        and meter
        and released.group(2) == "screen_reader"
        and meter.group(2) == "finished"
        and 2.0 < float(released.group(1)) < 20.0
    )
    print(
        "\nRESULT:",
        "PASS — the shipped build holds the video while NVDA speaks, and resumes when it stops"
        if passed
        else "FAIL",
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
