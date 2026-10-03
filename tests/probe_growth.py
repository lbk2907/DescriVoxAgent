"""Probe (growth): is handle retention UNBOUNDED across many failing runs?

One process, 100 REAL failing-URL runs (yt-dlp SourceError path), handle
count read every 25 runs. Linear growth = real leak; plateau = transient
retention (subprocess/GC artifacts), not a user-facing leak.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import ctypes, sys, io, tempfile, shutil
from pathlib import Path

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
sys.path.insert(0, "src")
import wx

_app = wx.App(False)

_k32 = ctypes.windll.kernel32
_k32.GetProcessHandleCount.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
_k32.GetProcessHandleCount.restype = ctypes.c_int
_k32.GetCurrentProcess.restype = ctypes.c_void_p
_hproc = _k32.GetCurrentProcess()


def handles() -> int:
    c = ctypes.c_ulong()
    if not _k32.GetProcessHandleCount(_hproc, ctypes.byref(c)):
        raise OSError("GetProcessHandleCount failed")
    return int(c.value)


from omni_describer_custom.core.project_store import ProjectStore
from omni_describer_custom.ui.main_frame import MainFrame

tmp = tempfile.mkdtemp(prefix="leak_grow_")
try:
    frame = MainFrame()
    frame.ai_engine = type("E", (), {"describe_frames": staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("unreachable")))})()
    frame.project_store = ProjectStore(projects_dir=str(Path(tmp) / "projects"))
    frame.settings = {"general.frame_rate": 1}
    frame._processing = True

    readings = []
    N = 100
    for i in range(1, N + 1):
        frame._dl_cancelled = False
        frame._ai_cancelled = False
        frame._process_video("http://127.0.0.1:1/nope.mp4", "prompt")
        wx.GetApp().ProcessPendingEvents()
        if i % 25 == 0:
            readings.append((i, handles()))
    print("GROWTH: " + " ".join(f"after_{i}={h}" for i, h in readings))
    first, last = readings[0][1], readings[-1][1]
    middle = readings[len(readings) // 2][1]
    verdict = "PLATEAU" if abs(last - middle) <= max(6, middle * 0.05) else "GROWING"
    print(f"VERDICT={verdict} (first={first} mid={middle} last={last})")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
