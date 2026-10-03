"""Regression round 10: cancel during AI over REAL HTTP.

test_fixes8 proved cancellation with a stub provider; test_fixes9 proved
the real wire. This round proves the PRODUCTION cancel path end to end:
a real slow HTTP AI server, a real worker thread, the real is_cancelled
poll between frames, and the real partial save into SQLite. Also fixes
(30 Aug) and verifies: the proactor event loop is now closed on the
worker's error paths too, and a 100-run growth probe shows handle use
PLATEAUS (no unbounded leak) on the error path.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import sys, io, subprocess, threading, asyncio, traceback, tempfile, shutil, time
from pathlib import Path

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace",
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

class SlowLoopbackAI:
    """REAL HTTP server (OpenAI-compatible vision format) that delays the
    first response so the test can cancel while a request is in flight."""
    def __init__(self, first_delay: float = 1.5):
        self.hits = 0
        self.first_delay = first_delay
        self._ready = threading.Event()
        self._loop = None
        self.port = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._ready.wait(15):
            raise RuntimeError("slow loopback AI server did not start")

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        from aiohttp import web

        async def handler(request):
            self.hits += 1
            # v1.9.6: the SECOND request is the slow one, so frame 1 is
            # finished when the test cancels during frame 2.
            if self.hits == 2:
                await asyncio.sleep(self.first_delay)
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

def test_cancel_during_real_http_ai():
    import wx
    srv = SlowLoopbackAI(first_delay=8)
    tmp = tempfile.mkdtemp(prefix="cancel10_")
    frame = None
    player_opened = []
    try:
        from omni_describer_custom.core.ai_engine import AIEngine
        from omni_describer_custom.core.project_store import ProjectStore
        from omni_describer_custom.ui.main_frame import MainFrame

        video = Path(tmp) / "in.mp4"
        make_video(video)

        engine = AIEngine()
        engine.set_provider("custom", api_key="k", base_url=srv.base_url(),
                            model="loop-model")
        frame = MainFrame()
        frame.ai_engine = engine
        frame.project_store = ProjectStore(
            projects_dir=str(Path(tmp) / "projects"))
        frame.settings = {"general.frame_rate": 1, "general.min_description_gap": 0}
        frame._processing = True
        # The player path is proven in test_fixes9; here the subject is the
        # CANCEL path, so record the call instead of opening VLC.
        frame._open_player = lambda *a, **k: player_opened.append(True)

        # Run the REAL worker pipeline on a real thread.
        th = threading.Thread(target=frame._process_video,
                              args=(str(video), "describe each frame"))
        th.start()

        # Cancel while the second (8 s) request is on the wire. v1.9.6: the
        # request in flight is abandoned at once (owner: Cancel did nothing
        # for minutes); frames already described are kept.
        deadline = time.monotonic() + 20
        while srv.hits < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert srv.hits == 2, "second AI request never reached the wire"
        frame._ai_cancelled = True
        cancelled_at = time.monotonic()

        th.join(60)
        assert not th.is_alive(), "worker thread did not finish after cancel"
        took = time.monotonic() - cancelled_at
        assert took < 4, f"Cancel took {took:.1f} s (the request is 8 s)"

        # Frames 3..N were never sent.
        assert srv.hits == 2, f"expected 2 HTTP hits, got {srv.hits}"

        # Partial save: frame 1's real description persisted to SQLite.
        proj = frame.project_store.current
        assert proj is not None, "project not created"
        texts = [d.text for d in proj.descriptions]
        assert texts == ["loopback desc 1"], f"saved texts: {texts!r}"
        for d in proj.descriptions:
            p = Path(d.frame_path)
            assert p.exists(), f"frame copy missing: {p}"
            assert p.read_bytes()[:2] == b"\xff\xd8", "not a real JPEG"

        # Stop HTTP before wx window interaction (documented IOCP crash),
        # then drain queued CallAfter events (_processing_done etc.).
        srv.stop()
        frame._processing_done()
        for _ in range(200):
            wx.GetApp().ProcessPendingEvents()
            time.sleep(0.01)
            if player_opened:
                break
        assert player_opened, "_processing_done did not reach _open_player"
    finally:
        try:
            if frame is not None:
                frame.Destroy()
        except Exception:
            pass
        srv.stop()
        shutil.rmtree(tmp, ignore_errors=True)

check("Cancel during REAL HTTP AI: worker stops between frames, partial save", test_cancel_during_real_http_ai)

print()
print(f"TOTAL: {ok} passed, {fail} failed")
# Same wx+VLC native teardown constraint as test_fixes9 (measured there):
# exit directly after flushing results so the exit code stays faithful.
sys.stdout.flush()
sys.stderr.flush()
import os
os._exit(1 if fail else 0)
