"""Regression round 20: progress-dialog lifecycle under the wx event pump.

Both bugs here were found by the gate itself: test_fixes12 failed about
one run in three, first as a hard interpreter crash (empty log), then as
"buttons not re-enabled". Neither was test flakiness.

1. GHOST DIALOG. wx.ProgressDialog pumps the event loop inside its own
   constructor, so queued wx.CallAfter handlers run BEFORE
   _ensure_download_progress assigns self._dl_dialog. When the pipeline
   finished meanwhile, _close_download_progress ran in there, saw
   _dl_dialog still None and closed nothing. The dialog born a moment
   later belonged to nobody: it stayed on screen and kept the main
   window DISABLED, so the app looked frozen — the worst outcome for a
   screen-reader user, whose focus lands in a dead dialog.

2. PIPELINE LEAVES NOTHING BEHIND. Invariant check on the same error
   path: no frame-counter thread survives the run, no dialog is left
   open and the main window is usable again. Each mode already stopped
   its own counter thread; _process_video now also stops it from the
   outer finally, covering a failure between the thread starting and
   those points.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
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

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

ok = 0
fail = 0
_app = None


def check(name, fn):
    global ok, fail, _app
    try:
        _app = wx.GetApp() or wx.App(False)
        fn()
        print(f"PASS: {name}")
        ok += 1
    except Exception as e:
        print(f"FAIL: {name}: {e}")
        traceback.print_exc()
        fail += 1


def _drain(rounds: int = 10, delay: float = 0.02) -> None:
    app = wx.GetApp()
    if app is None:
        return
    for _ in range(rounds):
        app.ProcessPendingEvents()
        app.Yield()
        time.sleep(delay)


# ── 1. Cleanup landing inside the dialog constructor ─────────────────

def test_close_during_dialog_construction():
    """The exact race: _close_download_progress runs while the dialog is
    being built. The newborn dialog must be discarded, not adopted."""
    from omni_describer_custom.ui import main_frame as mf
    from omni_describer_custom.ui.main_frame import MainFrame

    frame = MainFrame()
    destroyed = []
    try:
        # v1.9.6: the dialog is AccessibleProgressDialog; the guard must
        # hold for whatever dialog class is built there.
        real_dialog = mf.AccessibleProgressDialog

        class ReentrantDialog:
            """Stands in for a progress dialog whose constructor pumps
            the event loop (wx.ProgressDialog did) and so can run the
            pipeline's cleanup."""

            def __init__(self, *a, **k):
                # This is what the real constructor's nested event pump
                # does when the pipeline has already finished.
                frame._close_download_progress()

            def SetSize(self, *a):
                pass

            def Destroy(self):
                destroyed.append(1)

        mf.AccessibleProgressDialog = ReentrantDialog
        try:
            frame._ensure_download_progress()
        finally:
            mf.AccessibleProgressDialog = real_dialog

        assert frame._dl_dialog is None, (
            f"ghost dialog adopted after cleanup: {frame._dl_dialog!r}")
        assert destroyed, "newborn dialog was never destroyed"
        assert frame.IsEnabled(), "main window left disabled"
    finally:
        _drain()
        try:
            frame.Destroy()
        except Exception:
            pass
        _drain(rounds=5)


def test_close_generation_counter():
    """The guard is the close counter: it must advance even when there
    is no dialog to close, else a mid-construction cleanup is invisible."""
    from omni_describer_custom.ui.main_frame import MainFrame

    frame = MainFrame()
    try:
        assert frame._dl_dialog is None
        before = frame._dl_close_gen
        frame._close_download_progress()  # nothing to close
        assert frame._dl_close_gen == before + 1, (
            "close counter did not advance on an empty close")
    finally:
        _drain()
        try:
            frame.Destroy()
        except Exception:
            pass
        _drain(rounds=5)


# ── 2. Counter thread dies with the pipeline ─────────────────────────

class _FailingStub(BaseHTTPRequestHandler):
    """Gemini Files API loopback that reports FAILED, so the full-video
    pipeline takes its error path quickly and without network."""

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
            body = json.dumps({"file": {"uri": "http://x/v1beta/files/bad1",
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


def _count_frames_threads() -> list[str]:
    # Python names worker threads after their target: "Thread-N (count_frames)"
    return [th.name for th in threading.enumerate()
            if "count_frames" in th.name and th.is_alive()]


def test_failed_run_leaves_nothing_behind():
    """A failed full-video run must leave no counter thread, no open
    dialog and a usable main window."""
    from omni_describer_custom.core.project_store import ProjectStore
    from omni_describer_custom.ui import main_frame as mf
    from omni_describer_custom.ui.main_frame import MainFrame
    import omni_describer_custom.ui.player_window as pw_mod

    assert not _count_frames_threads(), (
        f"counter thread leaked before the test: {_count_frames_threads()}")

    server = HTTPServer(("127.0.0.1", 0), _FailingStub)
    port = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()

    frame = MainFrame()
    try:
        frame.project_store = ProjectStore(
            projects_dir=tempfile.mkdtemp(prefix="odc_f20_proj_"))
        frame.settings.set("ai.video_mode", "full")
        frame.settings.set("ai.default_provider", "gemini")
        frame.settings.set_ai_provider("gemini", {
            "api_key": "test-key",
            "base_url": f"http://127.0.0.1:{port}/v1beta"})
        video = Path(tempfile.mkdtemp(prefix="odc_f20_vid_")) / "clip.mp4"
        video.write_bytes(b"\x00" * 2048)
        frame._current_source = str(video)
        pw_mod.PlayerWindow = lambda *a, **k: None

        async def fake_info(self, source, **k):
            class I:
                width = 640
                height = 360
                duration = 42.0
            return I()

        async def fake_resolve(self, source, **k):
            return str(video)

        mf.VideoProcessor.get_video_info = fake_info
        mf.VideoProcessor.resolve_source = fake_resolve

        frame._start_processing("Describe this video.")
        worker = getattr(frame, "_worker", None)
        deadline = time.time() + 30
        while time.time() < deadline and worker is not None and worker.is_alive():
            wx.GetApp().Yield()
            time.sleep(0.03)
        assert worker is not None and not worker.is_alive(), "worker hung"

        # The thread wakes every 0.7s, so give it a few cycles to notice
        # the stop flag before declaring it leaked.
        gone_by = time.time() + 5
        while time.time() < gone_by and _count_frames_threads():
            wx.GetApp().Yield()
            time.sleep(0.05)
        leaked = _count_frames_threads()
        assert not leaked, f"counter thread outlived the pipeline: {leaked}"

        # The same run must also leave no ghost dialog behind.
        _drain()
        assert frame._dl_dialog is None, "progress dialog left open"
        assert frame.IsEnabled(), "main window left disabled after error"
    finally:
        server.shutdown()
        try:
            frame._close_download_progress()
        except Exception:
            pass
        _drain()
        try:
            frame.Destroy()
        except Exception:
            pass
        _drain(rounds=5)


def test_dedupe_dialog_uses_real_phoenix_api():
    """Opening a source that already has a project must show the dedupe
    dialog, not raise.

    Found by the real-GUI E2E: wxPython Phoenix has no SetYesLabel /
    SetNoLabel / SetCancelLabel (same family as the missing
    MenuBar.SetLabelTop), so _start_processing died with AttributeError
    and the Open button did NOTHING for any video already processed
    once — no dialog, no processing, no error the user could see.
    """
    from omni_describer_custom.core.project_store import ProjectStore
    from omni_describer_custom.ui.main_frame import MainFrame

    frame = MainFrame()
    real_show = wx.MessageDialog.ShowModal
    try:
        source = str(Path(tempfile.mkdtemp(prefix="odc_f20_dup_")) / "clip.mp4")
        Path(source).write_bytes(b"\x00" * 512)
        frame.project_store = ProjectStore(
            projects_dir=tempfile.mkdtemp(prefix="odc_f20_dupproj_"))
        frame.project_store.create_project("Already Done", source)
        assert frame.project_store.find_project_by_source(source), \
            "seeded project not findable by source"

        frame.settings.set("ai.default_provider", "glm")
        frame.settings.set_ai_provider("glm", {"api_key": "sk-or-v1-test",
                                               "model": "m"})
        frame._current_source = source

        # Answer the dedupe dialog with Cancel instead of blocking on a
        # real modal; the labels are set BEFORE ShowModal, so the bug
        # this guards would still fire.
        wx.MessageDialog.ShowModal = lambda self: wx.ID_CANCEL
        frame._start_processing("Describe this video.")

        assert not frame._processing, \
            "Cancel on the dedupe dialog must not start processing"
    finally:
        wx.MessageDialog.ShowModal = real_show
        _drain()
        try:
            frame.Destroy()
        except Exception:
            pass
        _drain(rounds=5)


def test_settings_isolated_from_user_config():
    """The gate must never write to the user's live settings.json."""
    import os
    from omni_describer_custom.core.settings_store import SettingsStore

    override = os.environ.get("ODC_CONFIG_DIR", "").strip()
    assert override, ("ODC_CONFIG_DIR is not set: run this suite through "
                      "run_gate.bat, which points settings at a temp dir")
    store = SettingsStore()
    assert str(store.settings_file).startswith(str(Path(override))), (
        f"settings still resolve to {store.settings_file}, not {override}")


if __name__ == "__main__":
    check("cleanup during dialog construction leaves no ghost",
          test_close_during_dialog_construction)
    check("close counter advances with no dialog",
          test_close_generation_counter)
    check("failed run leaves no thread, dialog or disabled window",
          test_failed_run_leaves_nothing_behind)
    check("dedupe dialog uses real Phoenix label API",
          test_dedupe_dialog_uses_real_phoenix_api)
    check("settings isolated from the user's live config",
          test_settings_isolated_from_user_config)
    print(f"\nRESULT: {ok} passed, {fail} failed")
    sys.exit(1 if fail else 0)
