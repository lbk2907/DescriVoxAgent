"""Debug: apply settings then dump all app top-level windows for 45s.

Ground truth for the 'Settings saved.' message box: hwnd, class,
title, children. If an OK button appears anywhere, click it.
"""
import ctypes
import io
import sys
import time
from ctypes import wintypes

sys.path.insert(0, r"C:\Users\USER\Documents\omni-describer-custom\src")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)

REPO = r"C:\Users\USER\Documents\omni-describer-custom"
user32 = ctypes.windll.user32


def wtitle(h):
    n = user32.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1) if n else ctypes.create_unicode_buffer(2)
    user32.GetWindowTextW(h, buf, n + 1)
    return buf.value


def wclass(h):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, buf, 256)
    return buf.value


def wpid(h):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return pid.value


def tops():
    out = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        out.append(h)
        return True
    user32.EnumWindows(cb, 0)
    return out


def kids(h):
    out = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(c, _):
        out.append(c)
        return True
    user32.EnumChildWindows(h, cb, 0)
    return out


def dump(tag):
    print(f"--- windows ({tag}) ---", flush=True)
    for h in tops():
        if wpid(h) != APP_PID or not user32.IsWindowVisible(h):
            continue
        print(f"  hwnd={h:#x} class={wclass(h)!r} title={wtitle(h)!r}",
              flush=True)
        for c in kids(h):
            print(f"      child class={wclass(c)!r} title={wtitle(c)!r:.60}",
                  flush=True)


from pywinauto import Desktop

# find app pid
APP_PID = 0
for h in tops():
    if wtitle(h) == "Omni Describer Custom":
        APP_PID = wpid(h)
        break
print("app pid:", APP_PID, flush=True)
assert APP_PID

desktop = Desktop(backend="uia")
win = desktop.window(title="Omni Describer Custom", visible_only=False)
win.set_focus()

# open settings
for b in win.descendants(control_type="Button"):
    if b.window_text().startswith("Settings"):
        b.click_input()
        break
time.sleep(2.0)
dlg = win.child_window(title="Settings", control_type="Window")
dlg.wait("visible ready", timeout=15)
dlg.child_window(title="AI Settings", control_type="TabItem").select()
time.sleep(1.0)
for c in dlg.descendants(control_type="ComboBox"):
    if "Provider" in (c.window_text() or ""):
        c.select("OpenRouter")
        break
time.sleep(1.2)
from omni_describer_custom.core.settings_store import SettingsStore
key = SettingsStore().get_ai_provider("glm").get("api_key", "")
for e in dlg.descendants(control_type="Edit"):
    if "API Key" in (e.window_text() or ""):
        e.set_edit_text(key)
        break
for k in dlg.descendants(control_type="CheckBox"):
    if "Full-video mode" in (k.window_text() or ""):
        if int(k.iface_toggle.CurrentToggleState) == 0:
            k.click_input()
        break
for b in dlg.descendants(control_type="Button"):
    if b.window_text() == "Apply":
        b.click_input()
        print("apply clicked", flush=True)
        break

t0 = time.time()
clicked = False
while time.time() - t0 < 45 and not clicked:
    dump(f"t+{time.time()-t0:.0f}s")
    for h in tops():
        if wpid(h) != APP_PID or not user32.IsWindowVisible(h):
            continue
        if wclass(h) != "#32770" or wtitle(h) != "Settings":
            continue
        for c in kids(h):
            if wclass(c) == "Button" and wtitle(c).replace("&", "") == "OK":
                user32.SendMessageTimeoutW(c, 0x00F5, 0, 0, 0x0002, 5000, None)
                print(f">>> clicked OK on {h:#x}", flush=True)
                clicked = True
                break
        if clicked:
            break
    time.sleep(2.0)
print("done, clicked:", clicked, flush=True)
