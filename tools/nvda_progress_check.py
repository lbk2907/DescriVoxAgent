"""Listen to the progress window: is the bar reported by NVDA? (v1.9.6)

Opens ui/progress_dialog.AccessibleProgressDialog in a child process
(isolated settings), moves the overall bar 0 -> 90 % in steps of 10 with
a phase change half way, then prints every utterance NVDA made meanwhile.
The owner's NVDA reports progress bars as "Speak and beep"; a pass here
means percentages were heard, not only that the gauge value changed.

    python tools/nvda_progress_check.py

Exit 2 without the NVDA HTTP bridge (not verified, never "passed").
Ask the owner to leave the PC untouched first (AGENTS.md rule 9).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "src"))

CHILD = r'''
import sys, wx
sys.path.insert(0, "src")
from omni_describer_custom.i18n.strings import t
from omni_describer_custom.ui.progress_dialog import AccessibleProgressDialog
app = wx.App(False)
frame = wx.Frame(None, title="Progress check owner")
frame.Show()
dlg = AccessibleProgressDialog(t("download.dialog_title"),
                               t("video.phase_transcript"), maximum=100,
                               parent=frame)
dlg.Show()
steps = list(range(0, 100, 10))

def step(i=0):
    if i >= len(steps):
        wx.CallLater(2500, lambda: (dlg.Destroy(), frame.Destroy(), app.ExitMainLoop()))
        return
    text = t("video.phase_transcript") if steps[i] < 50 else t("video.phase_waiting")
    dlg.Update(steps[i], text)
    wx.CallLater(1800, step, i + 1)

wx.CallLater(2500, step)
app.MainLoop()
'''


def main() -> int:
    import nvda_accessibility_check as a11y
    alive, detail = a11y.bridge_alive()
    if not alive:
        print(f"NVDA HTTP Bridge not answering: {detail}")
        return 2
    print(f"Bridge up: {detail}")
    box = Path(tempfile.mkdtemp(prefix="odc_a11y_"))
    env = dict(os.environ, ODC_CONFIG_DIR=str(box / "config"),
               ODC_PROJECTS_DIR=str(box / "projects"),
               ODC_LOCALES_DIR=str(box / "locales"))
    mark = a11y.speech_now()
    proc = subprocess.run([sys.executable, "-c", CHILD], cwd=str(REPO),
                          env=env, timeout=120)
    time.sleep(1.0)
    heard = a11y.speech_since(mark)
    print("NVDA said:")
    for line in heard:
        print("   ", line)
    percents = sorted({int(m) for line in heard
                       # NVDA says "40 percent"; a % sign is accepted too.
                       for m in re.findall(r"\b(\d{1,3})\s*(?:%|percent|peratus)",
                                           line)})
    print(f"\npercentages heard: {percents}")
    ok = proc.returncode == 0 and len(percents) >= 3
    print("OK: the bar is reported by NVDA" if ok
          else "NOT OK: fewer than 3 percentages were heard")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
