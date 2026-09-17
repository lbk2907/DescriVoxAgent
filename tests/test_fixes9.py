"""Regression round 9: REAL acceptance-path evidence.

Closes the honest gap left by test_fixes8 (whose AI calls were stubbed):
1. The CustomProvider talks to a REAL HTTP server (aiohttp on 127.0.0.1).
   The server verifies the real OpenAI-compatible wire format: Bearer
   auth header, JSON model/messages with an image_url data URL whose
   base64 payload decodes to real JPEG bytes, and returns a real
   response. on_progress/is_cancelled are observed over the real wire.
2. End-to-end acceptance pipeline with a REAL video file:
   ffmpeg-rendered mp4 -> MainFrame._process_video -> real ffprobe info
   -> real ffmpeg frame extraction -> real AIEngine -> real HTTP AI
   -> real SQLite project store -> frames copied into the project
   folder -> no temp-dir leak. The only GUI layer not exercised here is
   the modal dialog pump (proven separately on a real dialog in
   test_fixes7/8).
"""
import sys, io, subprocess, threading, asyncio, traceback, tempfile, shutil, time
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

def make_jpeg(path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "color=black:s=64x64:d=0.1", "-frames:v", "1", str(path)],
        capture_output=True, check=True)

def make_video(path: Path) -> None:
    """Render a real 3-second mp4 of RANDOM noise frames with audio.

    Random noise guarantees distinct perceptual hashes, so the production
    scene-change dedupe keeps several frames (uniform synthetic patterns
    like testsrc collapse to one surviving frame - measured in probing).
    """
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
    """A REAL HTTP server that speaks the OpenAI-compatible vision format.

    Runs in its own thread+loop. Records every request so tests can assert
    on the actual wire payload (auth header, model, JPEG bytes).
    """
    def __init__(self):
        self.hits = 0
        self.auth = None
        self.models = []
        self.jpeg_payloads = []
        self._ready = threading.Event()
        self._loop = None
        self.port = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._ready.wait(15):
            raise RuntimeError("loopback AI server did not start")

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        from aiohttp import web

        async def handler(request):
            self.hits += 1
            self.auth = request.headers.get("Authorization")
            data = await request.json()
            self.models.append(data.get("model"))
            url = data["messages"][0]["content"][1]["image_url"]["url"]
            b64 = url.split("base64,", 1)[1]
            import base64
            self.jpeg_payloads.append(base64.b64decode(b64))
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
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._set_stop)
        self._thread.join(10)

# 1. REAL HTTP: CustomProvider (real class, real aiohttp client) vs real server.
def test_real_http_ai_roundtrip():
    srv = LoopbackAI()
    tmp = tempfile.mkdtemp(prefix="http_ai_")
    try:
        paths = []
        for i in range(3):
            p = Path(tmp) / f"frame_{i:04d}.jpg"
            make_jpeg(p)
            paths.append(str(p))

        from omni_describer_custom.core.ai_engine import AIEngine
        engine = AIEngine()
        engine.set_provider("custom", api_key="test-key-123",
                            base_url=srv.base_url(), model="loop-model")

        progress = []
        async def run():
            return await engine.describe_frames(
                paths, "describe this frame",
                on_progress=lambda d, t: progress.append((d, t)),
                is_cancelled=lambda: False)
        descs = asyncio.run(run())

        assert srv.hits == 3, srv.hits
        assert srv.auth == "Bearer test-key-123", srv.auth
        assert srv.models == ["loop-model"] * 3, srv.models
        for i, jpeg in enumerate(srv.jpeg_payloads):
            assert jpeg[:3] == b"\xff\xd8\xff", f"payload {i} not real JPEG"
        assert descs == ["loopback desc 1", "loopback desc 2", "loopback desc 3"], descs
        assert progress == [(1, 3), (2, 3), (3, 3)], progress
    finally:
        srv.stop()
        shutil.rmtree(tmp, ignore_errors=True)
check("REAL HTTP AI: wire format, auth, JPEG bytes, progress over the wire", test_real_http_ai_roundtrip)

# 2. REAL end-to-end acceptance: real video -> real extraction -> real AI
#    HTTP -> real SQLite -> frames copied to project.
def test_full_real_pipeline():
    import wx
    srv = LoopbackAI()
    tmp = tempfile.mkdtemp(prefix="e2e_")
    try:
        video = Path(tmp) / "input.mp4"
        make_video(video)

        from omni_describer_custom.core.ai_engine import AIEngine
        from omni_describer_custom.core.project_store import ProjectStore
        from omni_describer_custom.ui.main_frame import MainFrame

        engine = AIEngine()
        engine.set_provider("custom", api_key="k", base_url=srv.base_url(),
                            model="loop-model")

        frame = MainFrame()
        try:
            frame.ai_engine = engine
            frame.project_store = ProjectStore(
                projects_dir=str(Path(tmp) / "projects"))
            frame.settings = {"general.frame_rate": 2}
            frame._processing = True

            import glob
            before = set(glob.glob(str(Path(tempfile.gettempdir()) / "odc_frames_*")))
            frame._process_video(str(video), "describe each frame")
            after = set(glob.glob(str(Path(tempfile.gettempdir()) / "odc_frames_*")))

            proj = frame.project_store.current
            assert proj is not None, "project not created"
            assert proj.video_duration > 2.9, proj.video_duration  # real ffprobe
            assert proj.descriptions, "no descriptions from real AI"
            texts = [d.text for d in proj.descriptions]
            assert all(t_.startswith("loopback desc") for t_ in texts), texts
            assert srv.hits >= 2, f"expected several real AI calls, got {srv.hits}"
            for d in proj.descriptions:
                fp = Path(d.frame_path)
                assert fp.exists(), f"permanent frame missing: {fp}"
                assert "frames" in str(fp).replace("/", "\\"), fp
                assert fp.read_bytes()[:3] == b"\xff\xd8\xff", "not a real JPEG"
            leaked = after - before
            assert not leaked, f"temp dirs leaked: {leaked}"
        finally:
            try:
                frame.Destroy()
            except Exception:
                pass
    finally:
        srv.stop()
        shutil.rmtree(tmp, ignore_errors=True)
check("REAL pipeline: mp4 -> ffmpeg frames -> HTTP AI -> SQLite -> permanent frames", test_full_real_pipeline)

# 3. THE end-user observable outcome: after the real pipeline, the Player
#    window opens through the REAL _open_player path and shows real AI
#    description text - NOT "No descriptions available." (the user's
#    original complaint: empty player after the frame-deletion bug).
def test_player_shows_real_descriptions():
    import wx
    srv = LoopbackAI()
    tmp = tempfile.mkdtemp(prefix="player_")
    try:
        video = Path(tmp) / "input.mp4"
        make_video(video)

        from omni_describer_custom.core.ai_engine import AIEngine
        from omni_describer_custom.core.project_store import ProjectStore
        from omni_describer_custom.ui.main_frame import MainFrame
        from omni_describer_custom.ui.player_window import PlayerWindow

        engine = AIEngine()
        engine.set_provider("custom", api_key="k", base_url=srv.base_url(),
                            model="loop-model")

        frame = MainFrame()
        player = None
        try:
            frame.ai_engine = engine
            frame.project_store = ProjectStore(
                projects_dir=str(Path(tmp) / "projects"))
            frame.settings = {"general.frame_rate": 2}
            frame._processing = True
            frame._process_video(str(video), "describe each frame")
            assert frame.project_store.current.descriptions, "no descriptions"

            # Stop the HTTP server BEFORE wx window interaction: pumping wx
            # messages while an asyncio proactor thread polls its IOCP has
            # crashed with an access violation on this machine (measured).
            # The player itself needs no further HTTP.
            srv.stop()

            # Real path used by _processing_done: _open_player. We are on
            # the main GUI thread here, so call it synchronously.
            frame._open_player()
            player = next(
                (w for w in wx.GetTopLevelWindows() if isinstance(w, PlayerWindow)),
                None)
            assert player is not None, "PlayerWindow never opened"
            text = player.current_desc_text.GetValue()
            assert text and not text.startswith("No descriptions"), \
                f"player looks EMPTY to the user: {text!r}"
            assert text.startswith("loopback desc"), text
            # Timeline shows the real ffprobe duration
            assert player.project.video_duration > 2.9
        finally:
            try:
                if player is not None:
                    player.Destroy()
            except Exception:
                pass
            try:
                frame.Destroy()
            except Exception:
                pass
    finally:
        srv.stop()
        shutil.rmtree(tmp, ignore_errors=True)
check("Player opens via real path and SHOWS real AI text (not empty)", test_player_shows_real_descriptions)

# 4. THE user's actual first action: a YouTube URL. One continuous run:
#    real yt-dlp download -> real extraction -> loopback AI -> SQLite ->
#    _processing_done auto-opens the real PlayerWindow with real text.
def test_full_url_to_player():
    import subprocess as sp
    try:
        sp.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except Exception:
        print("  (yt-dlp not on PATH, skipping)")
        return
    import wx
    srv = LoopbackAI()
    tmp = tempfile.mkdtemp(prefix="url2player_")
    player = None
    frame = None
    try:
        from omni_describer_custom.core.ai_engine import AIEngine
        from omni_describer_custom.core.project_store import ProjectStore
        from omni_describer_custom.ui.main_frame import MainFrame
        from omni_describer_custom.ui.player_window import PlayerWindow

        engine = AIEngine()
        engine.set_provider("custom", api_key="k", base_url=srv.base_url(),
                            model="loop-model")
        frame = MainFrame()
        frame.ai_engine = engine
        frame.project_store = ProjectStore(
            projects_dir=str(Path(tmp) / "projects"))
        frame.settings = {"general.frame_rate": 1}
        frame._processing = True

        frame._process_video("https://www.youtube.com/watch?v=jNQXAC9IVRw",
                             "describe each frame")
        proj = frame.project_store.current
        assert proj is not None, "project not created from URL"
        assert proj.descriptions, "no descriptions from real URL pipeline"
        assert srv.hits >= 1, "AI server never contacted"
        for d in proj.descriptions:
            assert Path(d.frame_path).exists(), f"frame missing: {d.frame_path}"

        # Stop HTTP before wx window interaction (documented IOCP crash).
        srv.stop()
        # _processing_done auto-opens the player via wx.CallAfter. Full
        # wx.Yield() re-enters window messaging and crashes with VLC COM
        # (measured: RPC_E_DISCONNECTED / access violation), so run the
        # pending event queue with the lighter ProcessPendingEvents API.
        frame._processing_done()
        deadline = time.monotonic() + 8
        while player is None and time.monotonic() < deadline:
            wx.GetApp().ProcessPendingEvents()
            time.sleep(0.02)
            player = next(
                (w for w in wx.GetTopLevelWindows() if isinstance(w, PlayerWindow)),
                None)
        assert player is not None, "player did not auto-open"
        text = player.current_desc_text.GetValue()
        assert text.startswith("loopback desc"), f"player text: {text!r}"
    finally:
        try:
            if player is not None:
                player.Destroy()
        except Exception:
            pass
        try:
            if frame is not None:
                frame.Destroy()
        except Exception:
            pass
        srv.stop()
        shutil.rmtree(tmp, ignore_errors=True)
check("REAL YouTube URL -> download -> extract -> AI -> save -> player auto-opens", test_full_url_to_player)

print()
print(f"TOTAL: {ok} passed, {fail} failed")
# KNOWN CONSTRAINT (measured): wx + VLC native teardown can access-violate
# AFTER all tests pass (crash traced to interpreter shutdown, no Python
# frames). All results are printed above, so exit the process directly to
# keep the real exit code faithful to the test results.
sys.stdout.flush()
sys.stderr.flush()
import os
os._exit(1 if fail else 0)
