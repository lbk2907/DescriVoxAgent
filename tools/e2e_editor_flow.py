"""Keyboard flow through the editor, checked in the database.

Edit description 1 by keyboard, arrow to description 2, close the
PLAYER (the editor's parent), then read the project .db. v1.7.4 lost
the edit on both moves; v1.7.5 also checks the list row speaks the new
text before moving. Needs NVDA with the HTTP bridge.

    python tools/e2e_editor_flow.py
"""
import os, sys, subprocess, tempfile, time, sqlite3, glob
from pathlib import Path
REPO = Path(r"C:\Users\USER\Documents\omni-describer-custom")
sys.path.insert(0, str(REPO / "tools"))
import win32gui, win32con
from pywinauto import Desktop
import safe_keys  # noqa: E402  (guards every keystroke; import first)
from pywinauto.keyboard import send_keys
import nvda_accessibility_check as a11y

work = Path(tempfile.mkdtemp(prefix="odc_a11y_"))
env = dict(os.environ, ODC_CONFIG_DIR=str(work / "config"))
proc = subprocess.Popen([sys.executable, str(REPO / "tools" / "nvda_window_check.py"),
                         "--window", "editor", "--serve", str(work)], env=env)
safe_keys.allow(proc.pid)
t0 = time.monotonic()
while not (work / "title.txt").exists() and time.monotonic() - t0 < 90:
    time.sleep(0.5)
title = (work / "title.txt").read_text(encoding="utf-8")
hwnd = win32gui.FindWindow(None, title)
win = Desktop(backend="uia").window(handle=hwnd)
win.set_focus(); time.sleep(1.5)

def focus_name():
    return (a11y.focus_object().get("name") or "")

# Tab until the description text box has focus.
for _ in range(10):
    send_keys("{TAB}"); time.sleep(0.6)
    if focus_name().startswith("Description Text"):
        break
print("focused:", focus_name())
send_keys("^a"); time.sleep(0.3)
send_keys("EDITED ONE BY KEYBOARD", with_spaces=True); time.sleep(0.5)
# Tab to the list, move to the second description.
for _ in range(10):
    send_keys("{TAB}"); time.sleep(0.6)
    if "Select Description" in " ".join(a11y.speech_since("")[-2:]) or focus_name().startswith("5.0s") or focus_name().startswith("12.0s"):
        break
print("list focus:", focus_name())
send_keys("{DOWN}"); time.sleep(1.0)
print("after down:", focus_name())
# Close the PLAYER (the editor's parent), as a user closing the player would.
player = win32gui.FindWindow(None, None)
titles = []
def visit(h, _):
    t = win32gui.GetWindowText(h)
    if "Player" in t and win32gui.IsWindowVisible(h): titles.append(h)
win32gui.EnumWindows(visit, None)
print("player windows:", len(titles))
win32gui.PostMessage(titles[0], win32con.WM_CLOSE, 0, 0)
time.sleep(3)
proc.terminate(); time.sleep(1)
db = (glob.glob(str(work / "projects" / "*" / "project.db"))
      + glob.glob(str(work / "projects" / "project_*.db")))[0]
rows = sqlite3.connect(db).execute("select start_time, text from descriptions order by start_time").fetchall()
print("DB:", rows)
ok = any(t == "EDITED ONE BY KEYBOARD" for _, t in rows)
print("RESULT:", "PASS - edit survived move + player close" if ok else "FAIL - edit lost")
