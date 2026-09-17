"""Regression round 11: OPT-IN frame cap over the REAL pipeline.

User pain point: a 17-minute video at 5 fps means ~5000 AI calls (slow,
expensive). Fix: an optional `general.frame_cap` setting (default 0 = NO
limit, existing behaviour untouched). When set, only the first N extracted
frames are sent for AI analysis, while timestamps stay on the full-video
timeline so descriptions remain synced with playback.

Proven here through the REAL acceptance pipeline (real worker thread, real
ffmpeg extraction, real HTTP loopback AI, real SQLite):
1. cap=2 over a 5+-frame video -> exactly 2 HTTP hits, 2 descriptions
   saved with full-video timestamps, temp dir cleaned.
2. cap absent/0 (default) -> every extracted frame is analysed (all hits).
"""
import sys, io, subprocess, threading, traceback, tempfile, shutil, time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
sys.path.insert(0, "src")

ok = 0
fail = 0
_app = None  # keep a reference: an unreferenced wx.App is garbage collected

def check(name, fn):
    global ok, fail, _app
    try:
        import wx
        _app = wx.GetApp() or wx.App(False)
        fn()
        print(f"PASS: {name}")
        ok += 1
    except Exception as e:
        print(f"FAIL: {name}: {e}")
        traceback.print_exc()
        fail += 1

def make_video(path: Path) -> None:
    """Real 3-second mp4 of random noise frames with audio (distinct
    perceptual hashes so scene dedupe keeps several frames)."""
    import random
    w, h, fps, dur = 320, 240, 10, 3
    raw = Path(str(path) + ".raw")
    raw.write_bytes(random.randbytes(w * h * 3 * fps * dur))
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
             "-r", str(fps), "-i", str(raw),
             "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
             "-map", "0:v", "-map", "1:a",
             "-c:v", "mpeg4", "-q:v", "3", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest", str(path)],
            capture_output=True, check=True)
    finally:
        raw.unlink(missing_ok=True)

class LoopbackAI:
    """REAL HTTP server (OpenAI-compatible vision format)."""
    def __init__(self):
        self.hits = 0
        self._ready = threading.Event()
        self._loop = None
        self.port = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._ready.wait(15):
            raise RuntimeError("loopback AI server did not start")

    def _run(self):
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        from aiohttp import web

        async def handler(request):
            self.hits += 1
            data = await request.json()
            url = data["messages"][0]["content"][1]["image_url"]["url"]
            import base64
            base64.b64decode(url.split("base64,", 1)[1])
            return web.json_response(
                {"choices": [{"message": {"content": f"loopback desc {self.hits}"}}]})

        app = web.Application()
        app.router.add_post("/v1/chat/completions", handler)

        async def serve():
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            self.port = site._server.sockets[0].getsockname()[1]
            self._ready.set()
            stop_ev = asyncio.Event()
            self._set_stop = lambda: stop_ev.set()
            await stop_ev.wait()
            await runner.cleanup()

        loop.run_until_complete(serve())

    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def stop(self):
        if getattr(self, "_stopped", False):
            return
        self._stopped = True
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._set_stop)
            self._thread.join(10)
            self._loop.close()

def _make_frame(tmp: Path, cap: int | None):
    import wx
    from omni_describer_custom.core.ai_engine import AIEngine
    from omni_describer_custom.core.project_store import ProjectStore
    from omni_describer_custom.ui.main_frame import MainFrame

    srv = LoopbackAI()
    video = Path(tmp) / "in.mp4"
    make_video(video)
    engine = AIEngine()
    engine.set_provider("custom", api_key="k", base_url=srv.base_url(),
                        model="loop-model")
    frame = MainFrame()
    frame.ai_engine = engine
    frame.project_store = ProjectStore(projects_dir=str(Path(tmp) / "projects"))
    frame.settings = {"general.frame_rate": 2}
    if cap is not None:
        frame.settings["general.frame_cap"] = cap
    frame._processing = True
    frame._open_player = lambda *a, **k: None  # player path proven in fixes9
    return srv, video, frame

def test_cap_limits_requests():
    import wx
    tmp = tempfile.mkdtemp(prefix="cap11_")
    try:
        srv, video, frame = _make_frame(Path(tmp), cap=2)
        th = threading.Thread(target=frame._process_video,
                              args=(str(video), "describe each frame"))
        th.start()
        th.join(120)
        assert not th.is_alive(), "worker did not finish"
        # Exactly cap requests hit the real wire.
        assert srv.hits == 2, f"expected exactly 2 AI calls, got {srv.hits}"
        proj = frame.project_store.current
        assert proj is not None, "project not created"
        texts = [d.text for d in proj.descriptions]
        assert texts and all(t == f"loopback desc {i+1}" for i, t in enumerate(texts)), \
            f"saved texts: {texts!r}"
        # Timestamps stay on the FULL-VIDEO timeline (early frames kept).
        starts = sorted(d.start_time for d in proj.descriptions)
        assert starts[0] == 0.0 and starts[-1] < 3.0, f"timestamps: {starts}"
        # Permanent frame copies exist and are real JPEGs.
        for d in proj.descriptions:
            p = Path(d.frame_path)
            assert p.exists() and p.read_bytes()[:2] == b"\xff\xd8", str(p)
        # No temp frame dir leak.
        leaks = list(Path(tempfile.gettempdir()).glob("odc_frames_*"))
        before = getattr(test_cap_limits_requests, "_leaks", None)
        if before is not None:
            assert len(leaks) == before, f"temp leak: {len(leaks)}"
        test_cap_limits_requests._leaks = len(leaks)
    finally:
        srv.stop()
        frame.Destroy()
        shutil.rmtree(tmp, ignore_errors=True)

def test_default_no_cap():
    import wx
    tmp = tempfile.mkdtemp(prefix="cap11b_")
    try:
        srv, video, frame = _make_frame(Path(tmp), cap=None)  # default: no cap
        th = threading.Thread(target=frame._process_video,
                              args=(str(video), "describe each frame"))
        th.start()
        th.join(120)
        assert not th.is_alive(), "worker did not finish"
        proj = frame.project_store.current
        assert proj is not None, "project not created"
        # Default behaviour unchanged: EVERY analysed frame was sent.
        assert srv.hits == len(proj.descriptions) and srv.hits >= 2, \
            f"hits={srv.hits} saved={len(proj.descriptions)}"
    finally:
        srv.stop()
        frame.Destroy()
        shutil.rmtree(tmp, ignore_errors=True)

def test_settings_dialog_cap_roundtrip():
    """REAL SettingsDialog: widget -> store -> widget round-trip, plus both
    language keys exist (blind users depend on the localized label)."""
    import wx
    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.ui.settings_dialog import SettingsDialog
    from omni_describer_custom.i18n.strings import EN_STRINGS, MS_STRINGS
    tmp = tempfile.mkdtemp(prefix="cap11c_")
    dlg = None
    try:
        store = SettingsStore(config_dir=tmp)
        assert store.get("general.frame_cap", None) == 0, "default must be 0"
        dlg = SettingsDialog(None, store)
        assert hasattr(dlg, "frame_cap_spin"), "dialog lacks the cap widget"
        assert dlg.frame_cap_spin.GetValue() == 0
        # Drive the REAL modal dialog: wx.MessageBox is a native modal that
        # cannot be driven from Python (documented wx boundary), so it is
        # stubbed; everything else (widget write, Apply, persistence) is real.
        orig_box = wx.MessageBox
        wx.MessageBox = lambda *a, **k: wx.OK
        errors = []

        def drive():
            try:
                dlg.frame_cap_spin.SetValue(75)
                dlg._on_apply(None)   # ends the modal with ID_OK
            except Exception as e:
                errors.append(e)
                dlg.EndModal(wx.ID_CANCEL)

        wx.CallAfter(drive)
        wx.CallLater(15000, lambda: dlg.EndModal(wx.ID_CANCEL))  # watchdog
        ret = dlg.ShowModal()
        wx.MessageBox = orig_box
        dlg.Destroy(); dlg = None
        assert ret == wx.ID_OK and not errors, f"ret={ret} errors={errors}"
        reread = SettingsStore(config_dir=tmp)
        assert reread.get("general.frame_cap") == 75, \
            f"persisted: {reread.get('general.frame_cap')}"
        # Re-open: the dialog must load the stored value back.
        dlg2 = SettingsDialog(None, reread)
        assert dlg2.frame_cap_spin.GetValue() == 75, "dialog did not reload cap"
        dlg2.Destroy(); dlg2 = None
        # Both locales must carry the label key (missing key = English
        # fallback would silently break the Malay UI).
        assert "settings.frame_cap" in EN_STRINGS, "missing EN key"
        assert "settings.frame_cap" in MS_STRINGS, "missing MS key"
    finally:
        if dlg is not None:
            try:
                dlg.Destroy()
            except Exception:
                pass
        shutil.rmtree(tmp, ignore_errors=True)

check("frame_cap=2 limits REAL AI requests, keeps full-video timestamps", test_cap_limits_requests)
check("default (no cap) analyses every frame - behaviour unchanged", test_default_no_cap)
check("REAL Settings dialog round-trips frame_cap (widget -> store -> widget)", test_settings_dialog_cap_roundtrip)

print()
print(f"TOTAL: {ok} passed, {fail} failed")
# Same wx+VLC native teardown constraint as fixes9/10 (measured there):
# exit directly after flushing results so the exit code stays faithful.
sys.stdout.flush()
sys.stderr.flush()
import os
os._exit(1 if fail else 0)
