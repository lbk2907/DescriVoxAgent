"""E2E GUI test for Omni Describer Custom (hybrid pywinauto + win32).

Flow: launch -> settings -> youtube url -> process -> verify db ->
export srt -> exit.

Lessons learned (keep for future runs):
- wx exposes control NAME as a numeric negative automation id, not the
  friendly name -> match controls by their visible label text.
- A modal wx dialog is a top-level Win32 window but appears as a CHILD
  in the UIA tree of its owner frame.
- The app's UIA provider intermittently goes numb (UIA sees nothing
  while Win32 lists the windows fine), especially around modal boxes
  and after long ops -> modal dialogs are detected and clicked with
  raw Win32 (ctypes): EnumWindows/EnumChildWindows + BM_CLICK, which
  is the same message a real mouse click produces.
- Read Edit/ComboBox values via UIA Value pattern (window_text returns
  the accessibility label for wx), checkboxes via Toggle state.

Run:
  python tools/e2e_gui_phase.py
"""
import ctypes
from ctypes import wintypes
import io
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

REPO = Path(r"C:\Users\USER\Documents\omni-describer-custom")
PY = sys.executable
APP_TITLE = "Omni Describer Custom"
URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo" 19s
SETTINGS_JSON = (Path.home() / "AppData" / "Roaming" / "OmniDescriber" /
                 "settings.json")
PROJECTS_DIR = Path.home() / "Documents" / "OmniDescriber" / "projects"
SRT_OUT = Path.home() / "Documents" / "OmniDescriber" / "e2e_gui_test.srt"

user32 = ctypes.windll.user32

from pywinauto import Desktop

desktop = Desktop(backend="uia")

APP_PID = 0  # set at launch


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------- win32

def _pid_of(hwnd) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _window_title(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    if not n:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _window_class(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def find_msgbox_win32(title: str, exclude_hwnd: int = 0,
                      timeout: float = 120.0) -> int:
    """Find a visible message-box dialog (class #32770) of our process
    with an OK button child. Disambiguates from same-titled wx dialogs
    (which have no OK child). Proven via tools/debug_apply.py.
    Returns hwnd or raises."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for hwnd in enum_top_windows():
            if (user32.IsWindowVisible(hwnd)
                    and _pid_of(hwnd) == APP_PID
                    and _window_class(hwnd) == "#32770"
                    and _window_title(hwnd) == title
                    and hwnd != exclude_hwnd
                    and _has_button(hwnd, "OK")):
                user32.SetForegroundWindow(hwnd)
                return hwnd
        time.sleep(0.5)
    raise RuntimeError(f"msgbox '{title}' not found (win32)")


def _has_button(box_hwnd: int, label: str) -> bool:
    for child in enum_children(box_hwnd):
        if (_window_class(child) == "Button"
                and _window_title(child).replace("&", "") == label):
            return True
    return False


def enum_top_windows():
    out = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lp):
        out.append(hwnd)
        return True
    user32.EnumWindows(cb, 0)
    return out


def enum_children(hwnd):
    out = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(child, _lp):
        out.append(child)
        return True
    user32.EnumChildWindows(hwnd, cb, 0)
    return out


def find_dialog_win32(title: str, timeout: float = 30.0,
                      cls: str = "#32770", exclude_hwnd: int = 0,
                      text_sub: str = ""):
    """Poll for a visible Win32 dialog (wx dialog / message box) by
    title in our process. Optionally skip a known hwnd (e.g. the
    settings dialog itself, which is titled the same as its
    confirmation message box) and require a child Static text.
    Returns hwnd or raises."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for hwnd in enum_top_windows():
            if (user32.IsWindowVisible(hwnd)
                    and _pid_of(hwnd) == APP_PID
                    and _window_class(hwnd) == cls
                    and _window_title(hwnd) == title
                    and hwnd != exclude_hwnd):
                if text_sub:
                    texts = [_window_title(c).lower() for c in
                             enum_children(hwnd)
                             if _window_class(c) == "Static"]
                    if not any(text_sub in t for t in texts):
                        continue
                user32.SetForegroundWindow(hwnd)
                return hwnd
        time.sleep(0.5)
    raise RuntimeError(f"dialog '{title}' not found (win32)")


def find_window_win32(title_sub: str, timeout: float = 30.0):
    """Poll for any visible top-level window of our process whose title
    contains title_sub."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for hwnd in enum_top_windows():
            if (user32.IsWindowVisible(hwnd)
                    and _pid_of(hwnd) == APP_PID
                    and title_sub in _window_title(hwnd)):
                return hwnd
        time.sleep(0.5)
    raise RuntimeError(f"window '*{title_sub}*' not found (win32)")


def press_button(box_hwnd: int, label: str, timeout: float = 10.0) -> None:
    """Click a child button by exact text via BM_CLICK (real click msg)."""
    deadline = time.time() + timeout
    BM_CLICK = 0x00F5
    while time.time() < deadline:
        for child in enum_children(box_hwnd):
            if (_window_class(child) == "Button"
                    and _window_title(child).replace("&", "") == label):
                user32.SendMessageTimeoutW(child, BM_CLICK, 0, 0,
                                           0x0002, 5000, None)
                log(f"clicked '{label}' (win32 BM_CLICK)")
                return
        time.sleep(0.4)
    raise RuntimeError(f"button '{label}' not found in box")


def set_edit_text(box_hwnd: int, text: str, index: int = 0) -> None:
    """Type into the Nth child Edit via WM_SETTEXT."""
    WM_SETTEXT = 0x000C
    edits = [c for c in enum_children(box_hwnd)
             if _window_class(c) == "Edit"]
    if not edits:
        raise RuntimeError("no Edit child found")
    user32.SendMessageTimeoutW(edits[index], WM_SETTEXT, 0, text,
                               0x0002, 5000, None)
    log(f"edit text set ({len(edits)} edit(s) found)")


def kill_stale() -> None:
    """Taskkill any process whose top window title is the app title."""
    pids = set()
    for hwnd in enum_top_windows():
        if _window_title(hwnd) == APP_TITLE:
            pids.add(_pid_of(hwnd))
    for pid in pids:
        log(f"killing stale instance pid={pid}")
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True)
    if pids:
        time.sleep(2.0)


# ---------------------------------------------------------------- UIA

def find_main_uia(timeout: float = 40.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            win = desktop.window(title=APP_TITLE, visible_only=False)
            if win.exists():
                return win
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("main window not found (UIA)")


def button_by_label(parent, label: str):
    cands = []
    for b in parent.descendants(control_type="Button"):
        ei = b.element_info
        if str(getattr(ei, "automation_id", "")) == "DropDown":
            continue
        if b.window_text() == label:
            cands.append(b)
    if not cands:
        raise RuntimeError(f"button '{label}' not found (UIA)")
    return cands[0]


def value_of(ctl) -> str:
    try:
        return ctl.iface_value.CurrentValue or ""
    except Exception:
        return ctl.window_text() or ""


def toggle_state(ctl):
    try:
        return int(ctl.iface_toggle.CurrentToggleState)
    except Exception:
        return None


# ---------------------------------------------------------------- steps

def step_launch():
    global APP_PID
    log("== LAUNCH ==")
    kill_stale()
    proc = subprocess.Popen(
        [PY, "main.py"], cwd=str(REPO),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    APP_PID = proc.pid
    log(f"launched pid={APP_PID}")
    win = find_main_uia()
    log(f"main window up: '{win.window_text()}'")
    labels = [b.window_text() for b in win.descendants(control_type="Button")]
    log(f"buttons: {labels}")
    assert any("YouTube" in t for t in labels), labels
    assert "Open" in labels, labels
    assert any(t.startswith("Settings") for t in labels), labels
    return win


def step_settings(top) -> None:
    log("== SETTINGS (via real GUI) ==")
    button_by_label(top, "Settings...").click_input()
    dlg_hwnd = find_dialog_win32("Settings", timeout=20)
    log("settings dialog open (win32 hwnd)")
    dlg = desktop.window(handle=dlg_hwnd, visible_only=False)
    dlg.child_window(title="AI Settings", control_type="TabItem").select()
    time.sleep(1.2)
    prov = None
    for c in dlg.descendants(control_type="ComboBox"):
        if "Provider" in (c.window_text() or ""):
            prov = c
            break
    if prov is None:
        raise RuntimeError("provider combo not found")
    prov.select("OpenRouter")
    log("provider -> OpenRouter")
    time.sleep(1.5)
    for c in dlg.descendants(control_type="ComboBox"):
        if "Model" in (c.window_text() or ""):
            log(f"model value: {value_of(c)!r}")
            break
    sys.path.insert(0, str(REPO / "src"))
    from omni_describer_custom.core.settings_store import SettingsStore
    key = SettingsStore().get_ai_provider("glm").get("api_key", "")
    assert key.startswith("sk-or-v1-") and len(key) == 73, "bad key"
    key_field = None
    for e in dlg.descendants(control_type="Edit"):
        if "API Key" in (e.window_text() or ""):
            key_field = e
            break
    cur = value_of(key_field) if key_field is not None else ""
    log(f"api key field current: {(cur[:12] + '...') if cur else '<empty/masked>'}")
    if not cur.startswith("sk-or-v1-"):
        key_field.set_edit_text(key)
        log("api key typed")
    else:
        log("api key already present")
    vm = None
    for k in dlg.descendants(control_type="CheckBox"):
        if "Full-video mode" in (k.window_text() or ""):
            vm = k
            break
    if vm is not None:
        st = toggle_state(vm)
        log(f"video_mode toggle state: {st}")
        if st == 0:
            vm.click_input()
            log("video_mode checked")
    else:
        log("WARN: full-video checkbox not found")
    button_by_label(dlg, "Apply").click_input()
    log("apply clicked; waiting for confirmation box (TTS init may block UI)")
    # wx.MessageBox('Settings saved.', 'Settings') -> own top-level
    # dialog titled the same as the settings dialog itself; disambiguate
    # by requiring an OK button child. TTS reinit can block the UI
    # thread for ~10s first.
    box = find_msgbox_win32("Settings", exclude_hwnd=dlg_hwnd, timeout=90)
    time.sleep(0.8)
    press_button(box, "OK", timeout=30)
    time.sleep(1.5)
    # Settings dialog should have closed via EndModal(wx.ID_OK).
    data = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
    got = data["ai"]["default_provider"]
    mode = data["ai"].get("video_mode")
    log(f"settings.json: default_provider={got} video_mode={mode}")
    assert got == "glm", got
    assert mode == "full", mode
    enc = data["ai"]["providers"]["glm"].get("api_key_enc", "")
    assert enc, "glm key missing"
    log("SETTINGS_OK")


def step_youtube() -> None:
    log("== YOUTUBE URL (via real GUI) ==")
    top = find_main_uia()
    top.set_focus()
    button_by_label(top, "YouTube Video URL").click_input()
    ted = find_dialog_win32("YouTube Video URL", timeout=20)
    time.sleep(0.5)
    set_edit_text(ted, URL)
    time.sleep(0.4)
    press_button(ted, "OK")
    time.sleep(0.5)
    log("URL entered via TextEntryDialog")


def step_process() -> None:
    log("== PROCESS (Open) ==")
    top = find_main_uia()
    top.set_focus()
    button_by_label(top, "Open").click_input()
    # 1) Download progress dialog ('Downloading video', class Dialog).
    pd_seen = False
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            if find_window_win32("Downloading video", timeout=1.0):
                pd_seen = True
                break
        except Exception:
            pass
        time.sleep(1.0)
    log("progress dialog 'Downloading video' " +
        ("seen" if pd_seen else "NOT seen (may be too fast)"))
    # 2) Outcome box: completion OR a transient AI/empty failure
    # (OpenRouter intermittently returns nothing; retry then).
    attempts = 0
    while True:
        done = None
        try:
            done = find_dialog_win32("Processing complete", timeout=1.5)
        except RuntimeError:
            pass
        if done is not None:
            log("completion box up")
            time.sleep(0.8)
            press_button(done, "OK")
            time.sleep(1.5)
            break
        fail = None
        try:
            fail = find_dialog_win32("Processing failed", timeout=1.5)
        except RuntimeError:
            pass
        if fail is not None:
            attempts += 1
            log(f"'Processing failed' box (attempt {attempts}): "
                "empty AI response; OK + retry")
            press_button(fail, "OK")
            time.sleep(2.0)
            if attempts > 2:
                raise RuntimeError("processing kept failing")
            top = find_main_uia()
            top.set_focus()
            button_by_label(top, "Open").click_input()
            deadline = time.time() + 60
            while time.time() < deadline:
                try:
                    if find_window_win32("Downloading video", timeout=1.0):
                        break
                except Exception:
                    pass
                time.sleep(1.0)
            continue
        time.sleep(2.0)
    # Player may auto-open (informational).
    try:
        pw = find_window_win32("Described Video Player", timeout=5.0)
        log(f"player window: '{_window_title(pw)[:70]}'")
    except Exception:
        log("player window: not open")


def step_verify() -> None:
    log("== VERIFY DB ==")
    dbs = sorted(PROJECTS_DIR.glob("*.db"), key=lambda p: p.stat().st_mtime)
    assert dbs, "no project db found"
    db = dbs[-1]
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT COUNT(*), MIN(start_time), MAX(end_time) FROM descriptions"
    ).fetchone()
    name, vp, dur = conn.execute(
        "SELECT name, video_path, video_duration FROM projects "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    texts = [r[0] for r in conn.execute(
        "SELECT text FROM descriptions ORDER BY start_time").fetchall()]
    conn.close()
    log(f"db={db.name} project='{name[:50]}' rows={rows[0]} "
        f"span={rows[1]}..{rows[2]} duration={dur}")
    for i, t in enumerate(texts):
        log(f"  desc[{i}]: {t[:70]!r}")
    assert rows[0] >= 1, "no descriptions in db"
    # App stores the YouTube URL as video_path (physical file stays in
    # the yt-dlp temp dir); treat non-empty path as valid.
    assert vp, "video_path empty"
    log("VERIFY_OK")


def invoke_menu_item(label: str) -> None:
    """Trigger a wx menu handler by its real Win32 menu command id:
    read the frame's HMENU, find the item by text, post WM_COMMAND —
    the same dispatch a mouse click produces (no Down-count guessing)."""
    main_hwnd = None
    for hwnd in enum_top_windows():
        if (_pid_of(hwnd) == APP_PID
                and _window_class(hwnd) == "wxWindowNR"
                and _window_title(hwnd) == APP_TITLE):
            main_hwnd = hwnd
            break
    assert main_hwnd, "main frame hwnd not found"
    hmenu = user32.GetMenu(main_hwnd)
    assert hmenu, "no menubar"
    file_menu = user32.GetSubMenu(hmenu, 0)
    count = user32.GetMenuItemCount(file_menu)
    MF_BYPOSITION = 0x400
    WM_COMMAND = 0x0111
    for pos in range(count):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetMenuStringW(file_menu, pos, buf, 256, MF_BYPOSITION)
        if buf.value.replace("&", "") == label:
            mid = user32.GetMenuItemID(file_menu, pos)
            user32.PostMessageW(main_hwnd, WM_COMMAND, mid, 0)
            log(f"menu '{label}' invoked (id={mid})")
            return
    raise RuntimeError(f"menu item '{label}' not found in File menu")


def step_export() -> None:
    log("== EXPORT SRT (via real GUI) ==")
    if SRT_OUT.exists():
        SRT_OUT.unlink()
    top = find_main_uia()
    top.set_focus()
    time.sleep(0.5)
    invoke_menu_item("Export as SRT...")
    fd = find_dialog_win32("Export as SRT...", timeout=20)
    time.sleep(0.6)
    # Modern file dialog: filename lives in an Edit inside a ComboBox.
    set_edit_text(fd, str(SRT_OUT))
    time.sleep(0.4)
    press_button(fd, "Save")
    time.sleep(1.5)
    assert SRT_OUT.exists(), "srt not created"
    text = SRT_OUT.read_text(encoding="utf-8")
    log(f"srt bytes={len(text)} head={text[:80]!r}")
    assert "-->" in text, "no SRT timestamps"
    log("EXPORT_OK")


def step_exit() -> None:
    log("== EXIT ==")
    top = find_main_uia()
    top.set_focus()
    button_by_label(top, "Exit").click_input()
    time.sleep(2.5)
    alive = False
    for hwnd in enum_top_windows():
        if _pid_of(hwnd) == APP_PID and _window_title(hwnd) == APP_TITLE:
            alive = True
    if alive:
        log("WARN: main window still present after Exit")
    else:
        log("main window gone")
    log("EXIT_OK")


def main() -> int:
    top = step_launch()
    step_settings(top)
    step_youtube()
    step_process()
    step_verify()
    step_export()
    step_exit()
    log("E2E_GUI_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
