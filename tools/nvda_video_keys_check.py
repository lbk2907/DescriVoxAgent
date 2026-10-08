"""Real test of the Player's video-area keys (v1.9.7, owner's request).

Opens a real Player on a throwaway 2-minute clip with sound (isolated
settings), gives the video picture the focus, then delivers Down, Down,
Up, Space, Down, Up, Right, Left, Space to THAT WINDOW ONLY with
PostMessage(WM_KEYDOWN/WM_KEYUP). Nothing goes through the system
keyboard, so no key can land in another program - on 2 Oct 2026 global
send_keys put arrows and spaces into the Claude app while its foreground
check passed. The messages still go through the Player's own message
loop, where Windows' arrow-key navigation lives (the bug being checked:
arrows moved the focus to a button).

After every key it records which control has the focus, the volume, the
position and what NVDA said.

    python tools/nvda_video_keys_check.py

Ask the owner to leave the PC untouched first (AGENTS.md rule 9).
Exit 2 without the NVDA HTTP bridge.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

CHILD = r"""
import sys, subprocess, wx
from pathlib import Path
sys.path.insert(0, "src")
from omni_describer_custom.core.project_store import Description, ProjectStore
from omni_describer_custom.core.tools import find_tool
from omni_describer_custom.core.tts_engine import TTSEngine
from omni_describer_custom.ui.player_window import PlayerWindow
work = Path(sys.argv[1])
clip = work / "clip.mp4"
subprocess.run([find_tool("ffmpeg"), "-y", "-loglevel", "error", "-f", "lavfi",
                "-i", "testsrc=size=320x240:rate=10:duration=120", "-f", "lavfi",
                "-i", "sine=frequency=330:duration=120", "-shortest",
                "-c:v", "libx264", "-c:a", "aac", str(clip)], check=True)
app = wx.App(False)
store = ProjectStore(str(work / "projects"))
store.create_project("Keys check", str(clip))
store.set_video_duration(120.0)
store.save_descriptions([Description(start_time=100.0, end_time=102.0, text="Late.")])
w = PlayerWindow(None, store, TTSEngine({}))
w.Show()
w.video_panel.SetFocus()
(work / "hwnd.txt").write_text(str(w.video_panel.GetHandle()))

def state():
    f = wx.Window.FindFocus()
    name = f.GetName() if f else "(none)"
    (work / "state.txt").write_text(
        f"{name[:40]}|{w._volume}|{w._position:.1f}|{w._playing}", encoding="utf-8")
    wx.CallLater(150, state)
wx.CallLater(300, state)
app.MainLoop()
"""

WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
VK = {"Down": 0x28, "Up": 0x26, "Right": 0x27, "Left": 0x25, "Space": 0x20}


def post_key(hwnd: int, name: str) -> None:
    import ctypes

    user32 = ctypes.windll.user32
    vk = VK[name]
    # The arrows are "extended" keys (bit 24); without it Windows reports
    # the number-pad arrows instead (first run, 3 Oct 2026).
    lp = 1 | (user32.MapVirtualKeyW(vk, 0) << 16) | ((1 << 24) if name != "Space" else 0)
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, lp)
    user32.PostMessageW(hwnd, WM_KEYUP, vk, lp | (0xC0 << 24))


def main() -> int:
    import nvda_accessibility_check as a11y

    alive, detail = a11y.bridge_alive()
    if not alive:
        print(f"NVDA HTTP Bridge not answering: {detail}")
        return 2
    print(f"Bridge up: {detail}")
    box = Path(tempfile.mkdtemp(prefix="odc_a11y_"))
    env = dict(
        os.environ,
        ODC_CONFIG_DIR=str(box / "config"),
        ODC_PROJECTS_DIR=str(box / "projects"),
        ODC_LOCALES_DIR=str(box / "locales"),
    )
    proc = subprocess.Popen([sys.executable, "-c", CHILD, str(box)], cwd=str(REPO), env=env)
    rows = []
    try:
        deadline = time.monotonic() + 90
        while not (box / "state.txt").exists() and time.monotonic() < deadline:
            time.sleep(0.5)
        hwnd = int((box / "hwnd.txt").read_text())
        time.sleep(2.0)
        print("start:", (box / "state.txt").read_text(encoding="utf-8"))
        for key in ("Down", "Down", "Up", "Space", "Down", "Up", "Right", "Left", "Space"):
            mark = a11y.speech_now()
            post_key(hwnd, key)
            time.sleep(1.8)
            focus, vol, pos, playing = (box / "state.txt").read_text(encoding="utf-8").split("|")
            rows.append((key, focus, int(vol), float(pos), playing, a11y.speech_since(mark)))
    finally:
        proc.terminate()
    print(f"{'key':6} {'focus':26} {'vol':>4} {'pos':>6} playing  NVDA said")
    for key, focus, vol, pos, playing, said in rows:
        print(f"{key:6} {focus[:26]:26} {vol:>4} {pos:>6.1f} {playing:7}  {said}")
    vols = [r[2] for r in rows]
    focus_kept = all(r[1].startswith("Video picture") for r in rows)
    volume_ok = vols[:3] == [90, 80, 90] and vols[4:6] == [80, 90]
    print("\nfocus stayed on the video picture:", focus_kept)
    print("volume followed every key:", volume_ok, vols)
    return 0 if (focus_kept and volume_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
