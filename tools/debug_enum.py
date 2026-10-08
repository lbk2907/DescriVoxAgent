"""Raw truth: EnumWindows via ctypes + hung check."""

import sys
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
pid_target = int(sys.argv[1]) if len(sys.argv) > 1 else 27764

results = []


@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def cb(hwnd, lparam):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == pid_target:
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        vis = user32.IsWindowVisible(hwnd)
        hung = user32.IsHungAppWindow(hwnd)
        results.append((hwnd, buf.value, cls.value, bool(vis), bool(hung)))
    return True


user32.EnumWindows(cb, 0)
print(f"windows for PID {pid_target}: {len(results)}")
for hwnd, title, cls, vis, hung in results:
    print(f"  hwnd={hwnd:#x} class={cls!r} title={title!r} visible={vis} hung={hung}")

if not results:
    print("NO top-level windows for this PID at all (win32 truth)")
