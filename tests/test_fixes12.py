"""Regression round 12: Gemini full-video mode.

User request: AI that WATCHES the video itself and returns its own
timestamped descriptions (Gemini native video understanding), instead of
the app extracting frames and describing them one by one.

Covered here WITHOUT any network access:
1. parse_gemini_timestamp_lines parses the documented [MM:SS] output
   format (bullets, brackets, hours, milliseconds) and ignores noise.
2. GeminiProvider.describe_video_full drives the full flow against a
   local HTTP loopback that mimics the Files API (resumable upload ->
   ACTIVE state -> generateContent with timestamped text) and returns
   parsed (seconds, text) pairs in order.
3. Unsupported providers raise a clear ValueError from AIEngine.
4. Settings dialog: the checkbox exists in the AI tab, is disabled for
   non-Gemini providers, enabled for Gemini, and persists ai.video_mode.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
import ctypes
import io
import json
import sys
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import wx

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
sys.path.insert(0, "src")

ok = 0
fail = 0
_app = None


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


def _drain_events(rounds: int = 12, delay: float = 0.02) -> None:
    """Dispatch every queued wx.CallAfter before a frame is destroyed.

    The worker thread posts UI updates (_log, SetStatusText,
    _processing_done) right up to its last line. Destroying the frame
    while those events are still queued makes the NEXT Yield() dispatch
    them against a freed C++ window: an access violation that killed the
    interpreter on roughly one gate run in three, with no output at all.
    Draining first, then again after Destroy(), lets wx finish the
    deferred deletion while the handlers still have a live window.
    """
    app = wx.GetApp()
    if app is None:
        return
    for _ in range(rounds):
        app.ProcessPendingEvents()
        app.Yield()
        time.sleep(delay)


def _destroy_frame(frame) -> None:
    """Tear a MainFrame down the way wx expects: drain, destroy, drain."""
    _drain_events()
    try:
        frame.Destroy()
    except Exception:
        pass
    _drain_events(rounds=6)


# ── 1. Parser ────────────────────────────────────────────────────────

def test_parser():
    from omni_describer_custom.core.ai_engine import parse_gemini_timestamp_lines

    text = (
        "Here is the description:\n"
        "[00:00] A man in a red jacket enters a bright kitchen.\n"
        "- 00:15 - He pours coffee while talking on the phone.\n"
        "[01:02:03.500] Hours format with milliseconds works too.\n"
        "* (12:34) Bracketed minutes only.\n"
        "This line has no timestamp and must be ignored.\n"
        "[00:05]\n"  # timestamp with no text -> ignored
    )
    pairs = parse_gemini_timestamp_lines(text)
    assert pairs == [
        (0.0, "A man in a red jacket enters a bright kitchen."),
        (15.0, "He pours coffee while talking on the phone."),
        (3723.5, "Hours format with milliseconds works too."),
        (754.0, "Bracketed minutes only."),
    ], pairs
    assert parse_gemini_timestamp_lines("") == []
    assert parse_gemini_timestamp_lines("no timestamps at all") == []


# ── 2. Full flow over a loopback that mimics the Gemini API ─────────

class _GeminiStub(BaseHTTPRequestHandler):
    posted_bodies: list[bytes] = []

    def log_message(self, *a):  # silence
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _GeminiStub.posted_bodies.append(body)
        # Step 1: resumable init -> hand back an upload URL on this server
        if "uploadType=resumable" in self.path:
            self.send_response(200)
            self.send_header("X-Goog-Upload-URL",
                             f"http://127.0.0.1:{self.server.server_port}/upload")
            self.end_headers()
            return
        # Step 2: chunk upload (finalize) -> file resource
        if self.path.startswith("/upload"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "file": {
                    "uri": ("http://generativelanguage.googleapis.com/v1beta/"
                            "files/demoabc123"),
                    "name": "files/demoabc123",
                    "state": "PROCESSING",
                }
            }).encode())
            return
        # Step 3: generateContent -> timestamped description text
        if ":generateContent" in self.path:
            payload = json.loads(body)
            parts = payload["contents"][0]["parts"]
            assert any("file_data" in p for p in parts), parts
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "candidates": [{"content": {"parts": [
                    {"text": "[00:00] A red car drives past green hills.\n"
                             "[00:10] The narrator greets the audience."}
                ]}}]
            }).encode())
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        # Files API status poll -> ACTIVE
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"name": "files/demoabc123",
                                     "state": "ACTIVE"}).encode())


def test_full_video_flow():
    from omni_describer_custom.core.ai_engine import GeminiProvider

    server = HTTPServer(("127.0.0.1", 0), _GeminiStub)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # Tiny real file as the upload payload
        tmp = Path(tempfile.mkdtemp(prefix="odc_test_")) / "video.mp4"
        tmp.write_bytes(b"\x00" * 4096)

        statuses: list[str] = []
        progress: list[float] = []

        async def run():
            prov = GeminiProvider(api_key="test-key",
                                  base_url=f"http://127.0.0.1:{port}/v1beta")
            return await prov.describe_video_full(
                str(tmp), "Describe this video.",
                on_status=statuses.append,
                on_upload_progress=progress.append)

        pairs = asyncio.new_event_loop().run_until_complete(run())
        assert statuses == ["uploading", "processing", "describing"], statuses
        assert pairs == [
            (0.0, "A red car drives past green hills."),
            (10.0, "The narrator greets the audience."),
        ], pairs
        assert any(p == 100.0 for p in progress), progress
    finally:
        server.shutdown()


def test_engine_rejects_non_gemini():
    from omni_describer_custom.core.ai_engine import AIEngine, OpenAIProvider  # noqa: F401 (checks the name still exists)

    engine = AIEngine()
    engine.set_provider("openai", api_key="k")
    loop = asyncio.new_event_loop()
    try:
        try:
            loop.run_until_complete(
                engine.describe_video_full("x.mp4", "p"))
        except ValueError as e:
            assert "full-video" in str(e), e
        else:
            raise AssertionError("expected ValueError for non-Gemini provider")
    finally:
        loop.close()


# ── 4. Settings UI ───────────────────────────────────────────────────

def test_settings_video_mode():
    from unittest.mock import patch

    import wx

    from omni_describer_custom.ui.settings_dialog import SettingsDialog
    from omni_describer_custom.core.settings_store import SettingsStore

    tmpdir = tempfile.mkdtemp(prefix="odc_settings_")
    store = SettingsStore(config_dir=tmpdir)
    dlg = SettingsDialog(None, store)

    # _on_apply pops a modal MessageBox; in tests nobody can click OK,
    # so stub it (no app-level change needed).
    mb_patch = patch.object(wx, "MessageBox", lambda *a, **k: wx.OK)
    mb_patch.start()

    try:
        _run_settings_checks(dlg, store)
    finally:
        mb_patch.stop()
        dlg.Destroy()


def _run_settings_checks(dlg, store) -> None:
    # Checkbox lives in the AI tab (parent chain: AI tab panel)
    cb = dlg.video_mode_cb
    assert cb.GetName() == "video_mode"
    ai_page = dlg.notebook.GetPage(1)
    parent = cb.GetParent()
    assert parent is ai_page, type(parent).__name__

    # Disabled for non-Gemini, enabled for Gemini
    dlg.select_provider("openai")
    assert not cb.IsEnabled()
    assert not cb.GetValue()
    dlg.select_provider("gemini")
    assert cb.IsEnabled()

    # Persist on apply
    dlg.select_provider("gemini")
    cb.SetValue(True)
    store.set("ai.default_provider", "gemini")
    store.set_ai_provider("gemini", {"api_key": "k", "model": "gemini-2.5-flash"})
    dlg._on_apply(None)
    assert store.get("ai.video_mode") == "full", store.get("ai.video_mode")
    cb.SetValue(False)
    dlg._on_apply(None)
    assert store.get("ai.video_mode") == "frames"
    dlg.Destroy()


def _video_phase_text(frame, phase: str) -> str:
    """Drive one status tick and return the status bar text."""
    frame._video_status_tick(phase)
    return frame.GetStatusBar().GetStatusText()


# ── 5. MainFrame video tick handlers (real frame, no network) ────────

def test_video_ticks_on_main_frame():
    from omni_describer_custom.i18n.strings import t
    from omni_describer_custom.ui.main_frame import MainFrame

    frame = MainFrame()
    try:
        assert frame._dl_dialog is None  # no dialog: must not crash

        for phase in ("uploading", "processing", "describing"):
            text = _video_phase_text(frame, phase)
            assert text and text != phase, (phase, text)
            expected = t(f"video.phase_{phase}")
            assert text == expected, (phase, text, expected)

        # Every phase is announced with DISTINCT wording so screen
        # reader users can tell exactly which stage is running
        texts = {_video_phase_text(frame, p) for p in
                 ("uploading", "processing", "describing")}
        assert len(texts) == 3, texts

        # Unknown phase falls back safely instead of raising
        unknown = _video_phase_text(frame, "nonsense")
        assert unknown == t("video.phase_processing")

        # Upload percentage reaches dialog path and status bar without
        # a dialog present
        frame._dl_dialog = None
        frame._video_upload_tick(37.4)
        assert frame.GetStatusBar().GetStatusText() == t(
            "video.uploading_progress").format(pct=37)

        # Announced, not silent: status text is non-empty at every step
        assert all(_video_phase_text(frame, p) for p in
                   ("uploading", "processing", "describing"))

        # v1.4.1 regression: the dialog must stay VISIBLE until
        # _close_download_progress destroys it, and the bar moves with
        # the overall percentage. v1.9.6: the dialog is
        # AccessibleProgressDialog (a real progress bar NVDA reads), the
        # bar is ONE percentage for the whole job (AI stage = 30-95 of
        # it), and it never goes back.
        from omni_describer_custom.ui.progress_dialog import (
            AccessibleProgressDialog)
        frame._progress_reset()
        dlg = AccessibleProgressDialog("Downloading video", "x",
                                       maximum=100, parent=frame)
        frame._dl_dialog = dlg
        try:
            user32 = ctypes.windll.user32
            visible = lambda: bool(
                user32.IsWindowVisible(dlg.GetHandle()))
            appear = time.time() + 5
            while time.time() < appear and not visible():
                wx.GetApp().Yield()
                time.sleep(0.02)
            assert visible(), "progress dialog never became visible"
            frame._video_part_tick(1, 2)
            assert visible(), "dialog auto-hidden before completion"
            # v1.8.4: part N STARTS here, so part 1 of 2 is 10% of the
            # AI step (30 + 65*0.10 = 36 overall), part 2 of 2 is 55%
            # (30 + 65*0.55 = 65 overall).
            assert dlg.GetValue() == 36, dlg.GetValue()
            assert t("video.part_start", part=1, total=2) in dlg.GetMessage(), (
                dlg.GetMessage())
            frame._video_part_tick(2, 2)
            assert dlg.GetValue() == 65, dlg.GetValue()
            assert t("video.part_start", part=2, total=2) in dlg.GetMessage(), (
                dlg.GetMessage())
            # The end of the AI step is the end of its stage (95), never
            # 100 while saving still runs.
            frame._video_eta_tick(100.0, 0.0)
            assert visible(), "dialog hidden at the end of the AI step"
            assert dlg.GetValue() == 95, dlg.GetValue()
            frame._video_split_tick(9.9)
            assert dlg.GetValue() == 95, f"the bar went back: {dlg.GetValue()}"
            assert visible(), "dialog vanished after split tick"
        finally:
            frame._dl_dialog = None
            try:
                dlg.Destroy()
            except Exception:
                pass
    finally:
        _destroy_frame(frame)


# ── 6. Full-value integration: main_frame branch end to end ──────────

def test_process_video_full_branch_integration():
    """Drive MainFrame._process_video (full-video branch) through the real
    engine chain (AIEngine -> GeminiProvider -> stub loopback) into the
    isolated project store. Only fakes: VideoProcessor metadata/resolve
    (observation), PlayerWindow (observer); real user data untouched.
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from omni_describer_custom.core.project_store import ProjectStore
    from omni_describer_custom.i18n.strings import t
    from omni_describer_custom.ui import main_frame as mf
    from omni_describer_custom.ui.main_frame import MainFrame
    import omni_describer_custom.ui.player_window as pw_mod

    class Stub(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            if "uploadType=resumable" in self.path:
                self.send_response(200)
                self.send_header(
                    "X-Goog-Upload-URL",
                    f"http://127.0.0.1:{self.server.server_port}/upload")
                self.end_headers()
                return
            if self.path.startswith("/upload"):
                body = json.dumps({"file": {
                    "uri": ("http://generativelanguage.googleapis.com"
                            "/v1beta/files/demoabc123"),
                    "name": "files/demoabc123",
                    "state": "PROCESSING"}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
                return
            if ":generateContent" in self.path:
                body = json.dumps({"candidates": [{"content": {"parts": [
                    {"text": "[00:00] A red car drives past green hills.\n"
                             "[00:10] The narrator greets the audience."
                     }]}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def do_GET(self):
            body = json.dumps({"name": "files/demoabc123",
                               "state": "ACTIVE"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), Stub)
    port = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()

    tmp_projects = tempfile.mkdtemp(prefix="odc_integ_proj_")
    video = Path(tempfile.mkdtemp(prefix="odc_integ_vid_")) / "clip.mp4"
    video.write_bytes(b"\x00" * 2048)

    resolve_seen: list[str] = []
    frame = MainFrame()
    try:
        # Isolate user data BEFORE anything processes
        frame.project_store = ProjectStore(projects_dir=tmp_projects)
        frame.settings.set("ai.video_mode", "full")
        frame.settings.set("ai.default_provider", "gemini")
        frame.settings.set_ai_provider("gemini", {
            "api_key": "test-key",
            "base_url": f"http://127.0.0.1:{port}/v1beta"})
        frame._current_source = str(video)

        opened: list[int] = []

        class FakePlayer:
            def __init__(self, *a, **k):
                opened.append(1)

            def __getattr__(self, name):
                return lambda *a, **k: None

        # _open_player imports locally from the player_window module, so
        # the patch must land on THAT module, not main_frame's attribute
        pw_mod.PlayerWindow = FakePlayer

        async def fake_info(self, source, **k):
            class I:
                width = 640
                height = 360
                duration = 42.0
            return I()

        async def fake_resolve(self, source, **k):
            resolve_seen.append(source)
            return str(video)

        mf.VideoProcessor.get_video_info = fake_info
        mf.VideoProcessor.resolve_source = fake_resolve

        # Record every status announcement (observer only): transient
        # phase texts can be overwritten faster than the event loop is
        # sampled, so reading the bar afterwards is unreliable
        real_set_status = frame.SetStatusText
        status_seen: list[str] = []

        def recording_set_status(text, *a, **k):
            status_seen.append(text)
            return real_set_status(text, *a, **k)

        frame.SetStatusText = recording_set_status

        frame._start_processing("Describe this video.")

        deadline = time.time() + 30
        while time.time() < deadline:
            wx.GetApp().Yield()
            time.sleep(0.03)
            worker = getattr(frame, "_worker", None)
            if opened and worker is not None and not worker.is_alive():
                for _ in range(5):
                    wx.GetApp().Yield()
                    time.sleep(0.03)
                break

        failures: list[str] = []
        try:
            if resolve_seen != [str(video)]:
                failures.append(f"resolve calls: {resolve_seen}")
            # processing can finish within one event-loop sample, so it
            # is asserted at unit level (check 5) instead of here
            for key in ("video.phase_uploading", "video.phase_describing"):
                if t(key) not in status_seen:
                    failures.append(
                        f"status not announced: {key}: {set(status_seen)}")
            if not opened:
                failures.append("PlayerWindow was never auto-opened")
            cur = frame.project_store.current
            if cur is None:
                failures.append("no current project after processing")
            else:
                descs = cur.descriptions
                if len(descs) != 2:
                    failures.append(
                        f"expected 2 descriptions, got {len(descs)}")
                else:
                    if [d.start_time for d in descs] != [0.0, 10.0]:
                        failures.append(
                            f"times: {[d.start_time for d in descs]}")
                    if descs[0].text != "A red car drives past green hills.":
                        failures.append(f"text0: {descs[0].text!r}")
                    if any(d.frame_path for d in descs):
                        failures.append("frame_path should be empty")
                    # v1.6.8: a cue lasts as long as its text takes to
                    # say, not a flat 3 seconds. The first line here is
                    # seven words and the second twelve, so their ends
                    # differ — what matters is that each one covers its
                    # own speech and never reaches the next cue.
                    from omni_describer_custom.core.timeline_io import (
                        speaking_seconds)
                    for i, d in enumerate(descs):
                        needed = speaking_seconds(d.text, 1.0)
                        room = (descs[i + 1].start_time - d.start_time
                                if i + 1 < len(descs) else needed)
                        want = min(needed, room)
                        if abs((d.end_time - d.start_time) - want) > 0.35:
                            failures.append(
                                f"cue {i} lasts "
                                f"{d.end_time - d.start_time:.1f}s, needs "
                                f"{want:.1f}s for {len(d.text.split())} words")
                        if i + 1 < len(descs) and \
                                d.end_time > descs[i + 1].start_time + 0.01:
                            failures.append(
                                f"cue {i} runs into the next one")
                if not Path(frame.project_store._db_path(cur.id)).exists():
                    failures.append("sqlite db missing in isolated dir")
        finally:
            server.shutdown()
            if failures:
                raise AssertionError("; ".join(failures))
    finally:
        try:
            frame._close_download_progress()
        except Exception:
            pass
        _destroy_frame(frame)


def test_error_path_failed_state():
    """Gemini returns FAILED for the uploaded file: the worker must end,
    the error must be announced, buttons re-enabled, no project left
    behind, and no misleading frame wording in full-video mode."""
    from omni_describer_custom.core.project_store import ProjectStore
    from omni_describer_custom.ui.main_frame import MainFrame

    class FailingStub(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            if "uploadType=resumable" in self.path:
                self.send_response(200)
                self.send_header(
                    "X-Goog-Upload-URL",
                    f"http://127.0.0.1:{self.server.server_port}/upload")
                self.end_headers()
                return
            if self.path.startswith("/upload"):
                body = json.dumps({"file": {
                    "uri": "http://x/v1beta/files/bad1",
                    "name": "files/bad1",
                    "state": "PROCESSING"}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def do_GET(self):
            body = json.dumps({"name": "files/bad1", "state": "FAILED",
                               "error": {"message": "unsupported codec"}})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())

    server = HTTPServer(("127.0.0.1", 0), FailingStub)
    port = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()

    frame = MainFrame()
    try:
        frame.project_store = ProjectStore(
            projects_dir=tempfile.mkdtemp(prefix="odc_err_proj_"))
        frame.settings.set("ai.video_mode", "full")
        frame.settings.set("ai.default_provider", "gemini")
        frame.settings.set_ai_provider("gemini", {
            "api_key": "test-key",
            "base_url": f"http://127.0.0.1:{port}/v1beta"})
        video = Path(tempfile.mkdtemp(prefix="odc_err_vid_")) / "clip.mp4"
        video.write_bytes(b"\x00" * 2048)
        frame._current_source = str(video)

        import omni_describer_custom.ui.player_window as pw_mod
        pw_mod.PlayerWindow = lambda *a, **k: None

        # Same observation fakes as the happy-path check (idempotent)
        async def fake_info(self, source, **k):
            class I:
                width = 640
                height = 360
                duration = 42.0
            return I()

        async def fake_resolve(self, source, **k):
            return str(video)

        from omni_describer_custom.ui import main_frame as mf
        mf.VideoProcessor.get_video_info = fake_info
        mf.VideoProcessor.resolve_source = fake_resolve

        real_set_status = frame.SetStatusText
        status_seen: list[str] = []

        def rec(text, *a, **k):
            status_seen.append(text)
            return real_set_status(text, *a, **k)

        frame.SetStatusText = rec
        frame._start_processing("Describe this video.")

        deadline = time.time() + 30
        worker = getattr(frame, "_worker", None)
        while time.time() < deadline and worker is not None and worker.is_alive():
            wx.GetApp().Yield()
            time.sleep(0.03)
        # The GUI-side cleanup (button re-enable, dialog teardown) is
        # posted from the worker thread via wx.CallAfter; wait for it
        # instead of a fixed 150 ms window (flaky under gate load).
        cleanup_deadline = time.time() + 10
        while time.time() < cleanup_deadline and not frame.btn_preset_open.Enabled:
            wx.GetApp().Yield()
            time.sleep(0.03)

        assert worker is not None and not worker.is_alive(), "worker hung"
        assert any("unsupported codec" in s or "Gemini failed" in s
                   for s in status_seen), set(status_seen)
        # FIX (1 Sep): no frame wording may be announced in full mode
        assert not any("Extracting frames" in s or "Analyzing frames" in s
                       for s in status_seen), set(status_seen)
        assert not frame._processing, "_processing stuck True"
        assert frame.btn_preset_open.Enabled, (
            "buttons not re-enabled: "
            f"worker_alive={worker.is_alive() if worker else None} "
            f"processing={frame._processing} "
            f"btn_own_flag={frame.btn_preset_open.IsThisEnabled()} "
            f"frame_enabled={frame.IsEnabled()} "
            f"dl_dialog={frame._dl_dialog!r} "
            f"dl_cancelled={frame._dl_cancelled} dl_done={frame._dl_done} "
            f"status_tail={status_seen[-3:]}")
        assert frame._dl_dialog is None, "progress dialog left open"
        assert frame.project_store.current is None, \
            "project should not be created on failure"
    finally:
        server.shutdown()
        try:
            frame._close_download_progress()
        except Exception:
            pass
        _destroy_frame(frame)


if __name__ == "__main__":
    check("gemini timestamp parser", test_parser)
    check("gemini full-video flow (loopback)", test_full_video_flow)
    check("non-gemini rejected clearly", test_engine_rejects_non_gemini)
    check("settings video-mode checkbox", test_settings_video_mode)
    check("mainframe video tick handlers", test_video_ticks_on_main_frame)
    check("process_video full branch end-to-end",
          test_process_video_full_branch_integration)
    check("error path FAILED state announced + UI recovers",
          test_error_path_failed_state)
    print(f"\nRESULT: {ok} passed, {fail} failed")
    sys.exit(1 if fail else 0)
