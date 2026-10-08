"""Listen to the Player agent through NVDA (v1.9.0, pitfall 29).

Opens a Player on a throwaway project (isolated settings and projects
folders; the real OpenRouter key and model are copied in), presses F2,
asks one question by keyboard, and records everything NVDA says: the
dialog, each spoken step, the answer, the proposal summary. The
proposal box is answered with Esc (Reject all), so nothing changes.

Needs NVDA with the HTTP bridge, an OpenRouter key in Settings, and the
bench clip tears_drama.mp4 (tools/model_bench.py make-clips). Costs a
fraction of a cent. The owner must leave the PC alone while it runs.

    python tools/nvda_agent_check.py              # one question
    python tools/nvda_agent_check.py --check-all  # Check the whole video
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import safe_keys  # noqa: E402,F401  (must come before pywinauto keyboard)
import nvda_accessibility_check as a11y  # noqa: E402

CLIP = Path(os.environ["TEMP"]) / "odc_bench" / "clips" / "tears_drama.mp4"
QUESTION = "Is the description at this moment right? Check it."

CHILD = r"""
import sys, wx
sys.path.insert(0, "src")
from omni_describer_custom.core.project_store import Description, ProjectStore
from omni_describer_custom.core.settings_store import SettingsStore
from omni_describer_custom.core.tts_engine import TTSEngine
from omni_describer_custom.ui.player_window import PlayerWindow
app = wx.App(False)
settings = SettingsStore()
store = ProjectStore()
store.create_project("Agent listening check", sys.argv[1])
store.persist_video_file(sys.argv[1])
store.set_video_duration(60.0)
store.save_descriptions([
    Description(start_time=4.0, end_time=7.0, text="A giant robot crashes into a sunny plaza."),
    Description(start_time=20.0, end_time=23.0, text="A woman studies a screen."),
])
w = PlayerWindow(None, store, TTSEngine({}), settings=settings)
w._position = 4.0
w.Show()
app.MainLoop()
"""


def main() -> int:
    alive, detail = a11y.bridge_alive()
    if not alive:
        print(f"NVDA HTTP Bridge not answering: {detail}")
        return 2
    if not CLIP.exists():
        print(f"missing {CLIP}; run tools/model_bench.py make-clips")
        return 2
    work = Path(tempfile.mkdtemp(prefix="odc_agentcheck_"))
    cfg = work / "cfg"
    cfg.mkdir()
    real = Path(os.environ["APPDATA"]) / "OmniDescriber" / "settings.json"
    data = json.loads(real.read_text(encoding="utf-8"))
    data.setdefault("ai", {})["default_provider"] = "glm"
    model = data["ai"].get("providers", {}).get("glm", {}).get("model") or "z-ai/glm-5.3-flash"
    data["ai"]["agent_models"] = [model]
    (cfg / "settings.json").write_text(json.dumps(data), encoding="utf-8")
    env = dict(os.environ, ODC_CONFIG_DIR=str(cfg), ODC_PROJECTS_DIR=str(work / "projects"))
    proc = subprocess.Popen([sys.executable, "-c", CHILD, str(CLIP)], cwd=str(REPO), env=env)
    safe_keys.allow(proc.pid)
    from pywinauto.keyboard import send_keys
    import win32gui

    try:
        hwnd = 0
        deadline = time.monotonic() + 60
        while not hwnd and time.monotonic() < deadline:

            def visit(h, found):
                if "Agent listening check" in win32gui.GetWindowText(h):
                    found.append(h)

            found: list = []
            win32gui.EnumWindows(visit, found)
            hwnd = found[0] if found else 0
            time.sleep(0.5)
        if not hwnd:
            print("the Player never appeared")
            return 1
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            # Windows' foreground lock: pywinauto's focus route (Alt tap)
            from pywinauto import Desktop

            Desktop(backend="uia").window(handle=hwnd).set_focus()
        time.sleep(1.5)
        mark = a11y.speech_now()
        send_keys("{F2}")
        time.sleep(3)
        print("After F2:", a11y.speech_since(mark))
        mark = a11y.speech_now()
        if "--check-all" in sys.argv:
            send_keys("%w")  # Check the whole video
            time.sleep(2)
            send_keys("{ENTER}")  # yes, go ahead (time and cost said)
        else:
            send_keys(QUESTION, with_spaces=True, vk_packet=False, pause=0.02)
            send_keys("{ENTER}")
        heard: list[str] = []
        deadline = time.monotonic() + 150
        summary_seen = False
        while time.monotonic() < deadline:
            time.sleep(2)
            new = a11y.speech_since(mark)
            if new:
                mark = a11y.speech_now()
                heard += new
                for line in new:
                    print("NVDA:", line[:160])
            if any(
                "proposed" in h or "No changes" in h or "Agent:" in h or "checked" in h
                for h in heard
            ) and any("button" in h or "checked" in h for h in heard[-3:]):
                summary_seen = True
                break
        time.sleep(1)
        send_keys("{ESC}")  # proposal box: Reject all
        time.sleep(3)
        for line in a11y.speech_since(mark):
            print("NVDA after Esc:", line[:160])
        send_keys("{ESC}")  # close the agent
        time.sleep(2)
        print("proposal box reached:", summary_seen)
        return 0
    finally:
        proc.terminate()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
