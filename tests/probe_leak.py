"""Probe (v2): OS handle growth across repeated REAL failure runs.

Each run drives MainFrame._process_video down a REAL failing path
(SourceError or generic Exception from real subprocesses), which is the
worker exit path suspected of missing loop.close(). Handles are measured
with a correctly prototyped GetProcessHandleCount.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import ctypes, sys, io, tempfile, shutil
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
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

tmp = tempfile.mkdtemp(prefix="leak_probe2_")
try:
    frame = MainFrame()
    frame.ai_engine = type("E", (), {"describe_frames": staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("unreachable")))})()
    frame.project_store = ProjectStore(projects_dir=str(Path(tmp) / "projects"))
    frame.settings = {"general.frame_rate": 1}
    frame._processing = True

    h0 = handles()
    N = 40
    for i in range(N):
        frame._dl_cancelled = False
        frame._ai_cancelled = False
        # REAL failure: URL whose yt-dlp metadata probe fails fast
        # (connection refused on a closed local port), raising SourceError
        # inside get_video_info -> worker except SourceError path.
        frame._process_video("http://127.0.0.1:1/nope.mp4", "prompt")
        wx.GetApp().ProcessPendingEvents()
    h1 = handles()
    print(f"RUNS={N} HANDLES_BEFORE={h0} HANDLES_AFTER={h1} DELTA={h1 - h0}")
    print(f"PER_RUN={(h1 - h0) / N:.2f}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
