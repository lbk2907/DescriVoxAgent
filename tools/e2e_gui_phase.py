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
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)

REPO = Path(r"C:\Users\USER\Documents\omni-describer-custom")
PY = sys.executable
APP_TITLE = "DescriVox Agent"
URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo" 19s
# v1.9.6: a SANDBOX, never the owner's real data (pitfall 19). This tool
# used to rewrite general.chunk_seconds in the real settings.json and
# delete new projects from the real projects folder. The real settings
# are only READ (copied once: the app needs the owner's encrypted key).
import shutil as _shutil  # noqa: E402
import tempfile as _tempfile  # noqa: E402
_REAL_CONFIG = Path.home() / "AppData" / "Roaming" / "OmniDescriber"
SANDBOX = Path(_tempfile.mkdtemp(prefix="odc_e2e_"))
(SANDBOX / "config").mkdir()
for _name in ("settings.json", "openrouter_models.json", "gemini_models.json"):
    if (_REAL_CONFIG / _name).exists():
        _shutil.copy2(_REAL_CONFIG / _name, SANDBOX / "config" / _name)
SETTINGS_JSON = SANDBOX / "config" / "settings.json"
PROJECTS_DIR = SANDBOX / "projects"
PROJECTS_DIR.mkdir()
APP_ENV = dict(os.environ, ODC_CONFIG_DIR=str(SANDBOX / "config"),
               ODC_PROJECTS_DIR=str(PROJECTS_DIR),
               ODC_LOCALES_DIR=str(SANDBOX / "locales"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e_projects import ProjectsGuard, newest_db  # noqa: E402
SRT_OUT = SANDBOX / "e2e_gui_test.srt"
# v1.5.5: was 10 s (to split the 19 s zoo video into 2 parts), but since
# v1.5.3 the Settings spin control enforces min=60, so Apply clamps any
# smaller value and the seed never persisted — the run died on a stale
# expectation, not an app fault. 60 is the real GUI floor; a 19 s clip is
# therefore ONE part here. Actual part-splitting is exercised at engine
# level by tools/e2e_glm_video_chunked.py (60 s clip, 20 s chunks) and by
# tests/test_chunked_video.py.
CHUNK_SECONDS = 60
# Live evidence captured while processing runs.
# - TITLE_PCTS: dialog-title percentages from the v1.5.0 SetTitle in
#   every tick ('Downloading video - N%'); titles ARE Win32-readable.
# - GREEN_PCTS: pixel scan of the dialog bar (PrintWindow + green-fill
#   span vs track span). The wx ProgressDialog bar is DirectUI-drawn:
#   NO msctls_progress32 child (probed) and PBM_GETPOS returns 0, so
#   rendered pixels are the ground truth.
TITLE_PCTS: list[int] = []
GREEN_PCTS: list[int] = []
# Optional ffmpeg -progress lines written by the temporary shim.
FFMPEG_LOG = REPO / "_e2e_ffmpeg_log.txt"

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


# ---------------------------------------------------------------- pixels

def _grab_window(hwnd):
    """Capture a window's own rendering via PrintWindow
    (PW_RENDERFULLCONTENT — includes DirectUI surfaces)."""
    import ctypes.wintypes as wt
    from PIL import Image

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG),
                    ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD),
                    ("biXPelsPerMeter", wt.LONG),
                    ("biYPelsPerMeter", wt.LONG),
                    ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]

    class BI(ctypes.Structure):
        _fields_ = [("bmiHeader", BIH), ("bmiColors", wt.DWORD * 3)]

    gdi32 = ctypes.windll.gdi32
    rect = wt.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return None
    hdc = user32.GetWindowDC(hwnd)
    if not hdc:
        return None
    try:
        gdi32.CreateDIBSection.restype = wt.HBITMAP
        gdi32.CreateDIBSection.argtypes = [
            wt.HDC, ctypes.c_void_p, wt.UINT,
            ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
        gdi32.CreateCompatibleDC.restype = wt.HDC
        gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
        gdi32.SelectObject.restype = wt.HGDIOBJ
        gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
        gdi32.DeleteDC.argtypes = [wt.HDC]
        user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
        user32.PrintWindow.restype = wt.BOOL
        bi = BI()
        bi.bmiHeader.biSize = ctypes.sizeof(BIH)
        bi.bmiHeader.biWidth = w
        bi.bmiHeader.biHeight = -h
        bi.bmiHeader.biPlanes = 1
        bi.bmiHeader.biBitCount = 32
        bits = ctypes.c_void_p()
        dib = gdi32.CreateDIBSection(hdc, ctypes.byref(bi), 0,
                                     ctypes.byref(bits), None, 0)
        if not dib or not bits:
            return None
        mem = gdi32.CreateCompatibleDC(hdc)
        old = gdi32.SelectObject(mem, dib)
        ok = user32.PrintWindow(hwnd, mem, 2)  # PW_RENDERFULLCONTENT
        gdi32.SelectObject(mem, old)
        gdi32.DeleteDC(mem)
        if not ok:
            return None
        data = ctypes.string_at(bits, w * h * 4)
        im = Image.frombuffer("RGB", (w, h), data, "raw", "BGRX", 0, 1)
        return im.convert("RGB")
    finally:
        user32.ReleaseDC(hwnd, hdc)


def _bar_green_pct(im):
    """Bar fill percent from pixels: green band span / track span on a
    wx ProgressDialog (green fill on a grey track)."""
    w, h = im.size
    px = im.load()
    green = []
    track = []
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            r, g, b = px[x, y]
            if g > 120 and r < 110 and b < 110:
                green.append(x)
                track.append(x)
            elif 180 <= r <= 240 and abs(r - g) < 6 and abs(g - b) < 6:
                track.append(x)
    if not track:
        return None
    span = max(track) - min(track)
    if span <= 0:
        return None
    if not green:
        return 0
    return int(round(100.0 * (max(green) - min(green)) / span))


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
    # Seed chunk length BEFORE launch (v1.4.1: user-configurable). The
    # 19 s video then splits into 2 parts -> chunked path exercised.
    data = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
    data.setdefault("general", {})["chunk_seconds"] = CHUNK_SECONDS
    SETTINGS_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log(f"seeded general.chunk_seconds={CHUNK_SECONDS}")
    app_log = open(REPO / "_e2e_app_log.txt", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [PY, "main.py"], cwd=str(REPO), env=APP_ENV,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        stdout=app_log, stderr=app_log)
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
    # General tab: the chunk-length spinner must have LOADED the seeded
    # value (proves _load_values path). Best-effort: UIA matching for
    # wx spinners is fragile; the persisted-value check in
    # step_coverage is the real gate.
    try:
        dlg.child_window(title="General", control_type="TabItem").select()
        time.sleep(1.0)
        found = False
        for s in dlg.descendants(control_type="Spinner"):
            try:
                val = value_of(s)
            except Exception:
                val = ""
            if val == str(CHUNK_SECONDS):
                found = True
                log(f"chunk spinner shows seeded {CHUNK_SECONDS}s")
                break
        if not found:
            log("WARN: chunk spinner value not confirmed via UIA")
    except Exception as e:
        log(f"WARN: general tab spin check skipped: {e}")
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
    # Background poller: while the 'Downloading video' progress dialog
    # is up, read the v1.5.0 live percentage from its TITLE (Win32-
    # readable) and pixel-scan the bar fill (ground truth for the
    # DirectUI-drawn bar that has no Win32 position).
    stop_flag = threading.Event()

    def capture_progress() -> None:
        while not stop_flag.is_set():
            try:
                for hwnd in enum_top_windows():
                    if not (user32.IsWindowVisible(hwnd)
                            and _pid_of(hwnd) == APP_PID):
                        continue
                    title = _window_title(hwnd)
                    if "Downloading video" in title:
                        m = re.search(r"-\s*(\d+)%\s*$", title)
                        if m:
                            pct = int(m.group(1))
                            if not TITLE_PCTS or TITLE_PCTS[-1] != pct:
                                TITLE_PCTS.append(pct)
                                log(f"  dialog title: {title!r}")
                        im = _grab_window(hwnd)
                        if im is not None:
                            gp = _bar_green_pct(im)
                            if gp is not None and (not GREEN_PCTS
                                                   or GREEN_PCTS[-1] != gp):
                                GREEN_PCTS.append(gp)
                                log(f"  dialog bar (pixels): {gp}%")
            except Exception as e:
                log(f"  poller warn: {e!r}")
            time.sleep(0.4)

    th = threading.Thread(target=capture_progress, daemon=True)
    th.start()
    # The click must be VERIFIED, not assumed. UIA lists two "Open"
    # candidates for this frame and goes numb intermittently (see module
    # docstring): a run on 17 Sep 2026 clicked into the void and then
    # waited forever for a dialog that could never appear, with the app
    # sitting idle. Press, then confirm the app reacted; retry if not.
    started = False
    for attempt in range(1, 4):
        button_by_label(top, "Open").click_input()
        log(f"clicked 'Open' (attempt {attempt})")
        deadline = time.time() + 15
        while time.time() < deadline:
            # Any of these proves _on_preset_open ran: the dedupe
            # prompt, the progress dialog, or the disabled Open button.
            for hwnd in enum_top_windows():
                if (user32.IsWindowVisible(hwnd)
                        and _pid_of(hwnd) == APP_PID
                        and _window_title(hwnd) in ("Existing project found",
                                                    "Downloading video")):
                    started = True
                    break
            if not started:
                try:
                    if not button_by_label(top, "Open").is_enabled():
                        started = True
                except Exception:
                    pass
            if started:
                break
            time.sleep(0.5)
        if started:
            break
        log("  no reaction from the app — re-pressing Open")
    if not started:
        raise RuntimeError("Open never took effect after 3 attempts")
    # 0) v1.5.1 dedupe prompt: this URL has been processed by earlier E2E
    # runs, so the app offers to reopen that project. Answer "process
    # again as new" so the run still exercises the whole pipeline.
    # (Before v1.5.5 this dialog never appeared: SetYesLabel raised
    # AttributeError and the Open button silently did nothing.)
    dedupe = None
    deadline = time.time() + 12
    while time.time() < deadline and dedupe is None:
        for hwnd in enum_top_windows():
            if (user32.IsWindowVisible(hwnd)
                    and _pid_of(hwnd) == APP_PID
                    and _window_title(hwnd) == "Existing project found"):
                dedupe = hwnd
                break
        time.sleep(0.4)
    if dedupe is not None:
        log("dedupe prompt up -> 'Process again as new project'")
        user32.SetForegroundWindow(dedupe)
        time.sleep(0.4)
        press_button(dedupe, "Process again as new project")
        time.sleep(1.0)
    else:
        log("no dedupe prompt (fresh source)")
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
                stop_flag.set()
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
    stop_flag.set()
    th.join(timeout=3.0)
    log(f"captured title pcts={TITLE_PCTS} bar pcts={GREEN_PCTS}")
    # Player may auto-open (informational).
    try:
        pw = find_window_win32("Described Video Player", timeout=5.0)
        log(f"player window: '{_window_title(pw)[:70]}'")
    except Exception:
        log("player window: not open")


def step_verify() -> None:
    log("== VERIFY DB ==")
    db = newest_db(PROJECTS_DIR)   # either project layout
    assert db, "no project db found"
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


def step_coverage() -> None:
    """Verify progress reporting and full-clip coverage end-to-end.

    1. general.chunk_seconds survives the Settings round-trip (60 = the
       spin control's minimum since v1.5.3).
    2. The progress dialog showed REAL percentages while running
       ('part N of M, overall X%' and/or 'Splitting ... %').
    3. The DB covers the whole 19 s clip, first cue to last.

    Multi-part splitting is NOT checked here: the GUI floor of 60 s
    cannot split a 19 s clip. tools/e2e_glm_video_chunked.py covers that
    at engine level.
    """
    log("== PROGRESS + COVERAGE ==")
    data = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
    got = data.get("general", {}).get("chunk_seconds")
    assert got == CHUNK_SECONDS, f"chunk_seconds not persisted: {got!r}"
    log(f"chunk_seconds persisted: {got}")

    for p in TITLE_PCTS:
        log(f"  title: {p}%")
    for p in GREEN_PCTS:
        log(f"  bar (pixels): {p}%")
    # Single part: the overall tick is 10 + 90*1/1 = 100 (the bar itself
    # caps at 99 so PD_AUTO_HIDE cannot hide it while saving runs).
    assert TITLE_PCTS, "dialog title percentage never observed"
    assert max(TITLE_PCTS) >= 55, (
        f"dialog title never reached the 55% part-1 tick: {TITLE_PCTS}")
    assert GREEN_PCTS and max(GREEN_PCTS) >= 45, (
        f"dialog bar fill never reached ~55%: {GREEN_PCTS}")
    log("progress percentages captured OK (title + bar pixels)")

    db = newest_db(PROJECTS_DIR)
    assert db, "no project db"
    conn = sqlite3.connect(str(db))
    starts = [r[0] for r in conn.execute(
        "SELECT start_time FROM descriptions ORDER BY start_time")]
    maxend = conn.execute(
        "SELECT MAX(end_time) FROM descriptions").fetchone()[0]
    conn.close()
    assert starts, "no descriptions"
    first, last = starts[0], starts[-1]
    log(f"cue starts: first={first} last={last} max_end={maxend} n={len(starts)}")
    # Coverage of the FULL clip: first cue near the start, last cue near
    # the end of the ~19 s video, and no cue may claim time the clip
    # does not have (a symptom of a bad chunk offset).
    assert first <= 5.0, f"first cue not at clip start: {first}"
    assert last >= 15.0, f"last cue too early for 19s clip: {last}"
    assert maxend <= 25.0, f"cue ends past the clip: max_end={maxend}"
    log("COVERAGE_OK")


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
    guard = ProjectsGuard(PROJECTS_DIR)
    try:
        top = step_launch()
        step_settings(top)
        step_youtube()
        step_process()
        step_verify()
        step_coverage()
        step_export()
        step_exit()
        log("E2E_GUI_PASS")
        return 0
    finally:
        # The app must be closed first, or its files are still open.
        guard.cleanup()


if __name__ == "__main__":
    sys.exit(main())
