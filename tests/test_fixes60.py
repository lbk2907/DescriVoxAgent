"""Regression round 60: Cancel, closing the window, and error text (v1.9.6).

From an audit of ui/main_frame.py:
1. Cancel in the progress dialog was registered by only three ticks
   (download, frame count, frame-mode AI). Every full-video phase tick,
   the phase-text tick and the 1 s heartbeat threw Update()/Pulse()'s
   answer away, so for a local or already-downloaded video Cancel did
   nothing for the whole job.
2. The heartbeat now asks the dialog WasCancelled() first, every second.
3. Closing the main window during a job: the worker's later wx.CallAfter
   calls hit the deleted frame ("wrapped C/C++ object of type MainFrame
   has been deleted", the owner's log), and open Player/Editor windows
   were destroyed without their EVT_CLOSE (unsaved edits lost).
4. A failed job showed the provider's raw text: an HTTP 413 was read out
   as a JSON body with an OpenRouter user id.
5. Download 403s are raised as SourceError, whose branch never tested
   for them, so error.download_forbidden was unreachable.
Also: fast-mode ffmpeg ignored Cancel (subprocess.run, 900 s), and an
empty ai.default_provider meant "gemini" here but "glm" in Settings.

Every check here fails on the old main_frame.py.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import sys
from pathlib import Path
import threading
import time
import traceback

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

import wx  # noqa: E402

results: list[tuple[str, bool]] = []

# What the owner's log showed for a too-large upload (shape kept, id fake).
OWNER_413 = ('HTTP 413: {"error":{"message":"Request Entity Too Large",'
             '"code":413,"metadata":{"provider_name":"Z.AI","raw":'
             '"{\\"error\\":\\"payload too large\\"}"}},'
             '"user_id":"user_2xYzAbCdEf1234567"}')
YT_403 = ("yt-dlp download failed (https://www.youtube.com/watch?v=abc123): "
          "ERROR: [youtube] abc123: Unable to download video data: "
          "HTTP Error 403: Forbidden")


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def _drain_events(rounds: int = 12, delay: float = 0.02) -> None:
    """Dispatch queued wx.CallAfter calls (see test_fixes12, pitfall 10)."""
    app = wx.GetApp()
    if app is None:
        return
    for _ in range(rounds):
        app.ProcessPendingEvents()
        app.Yield()
        time.sleep(delay)


def _destroy_frame(frame) -> None:
    _drain_events()
    try:
        frame.Destroy()
    except Exception:
        pass
    _drain_events(rounds=6)


class FakeDialog:
    """Stands in for wx.ProgressDialog: no window, answers on demand."""

    def __init__(self, cancel: bool = True, was_cancelled: bool = False):
        self.cancel = cancel
        self.was_cancelled = was_cancelled
        self.destroyed = False

    def Pulse(self, *args):
        return (not self.cancel, False)

    def Update(self, *args):
        return (not self.cancel, False)

    def WasCancelled(self):
        return self.was_cancelled

    def SetTitle(self, *args):
        pass

    def Destroy(self):
        self.destroyed = True


def _frame():
    from omni_describer_custom.ui.main_frame import MainFrame
    frame = MainFrame()
    # Phase announcements go to the speech backend; keep the test silent.
    frame._speak_progress = lambda text: None
    return frame


def _arm(frame, dlg) -> None:
    frame._dl_cancelled = False
    frame._dl_done = False
    frame._ai_cancelled = False
    frame._frame_ai_phase = False
    frame._dl_dialog = dlg


# ── 1. every tick registers Cancel ─────────────────────────────────────

def test_every_tick_registers_cancel():
    frame = _frame()
    try:
        ticks = {
            "_video_status_tick": lambda: frame._video_status_tick("uploading"),
            "_video_eta_tick": lambda: frame._video_eta_tick(50.0, 30.0),
            "_video_upload_tick": lambda: frame._video_upload_tick(40.0),
            "_video_split_tick": lambda: frame._video_split_tick(30.0),
            "_video_part_tick": lambda: frame._video_part_tick(1, 2),
            "_download_progress_tick_text (pulse)":
                lambda: frame._download_progress_tick_text("phase", -1),
            "_download_progress_tick_text (update)":
                lambda: frame._download_progress_tick_text("phase", 50),
        }
        missed = []
        for name, call in ticks.items():
            dlg = FakeDialog(cancel=True)
            _arm(frame, dlg)
            call()
            if not (frame._dl_cancelled and frame._dl_done
                    and dlg.destroyed and frame._dl_dialog is None):
                missed.append(name)
        assert not missed, f"Cancel ignored by: {', '.join(missed)}"
    finally:
        _arm(frame, None)
        _destroy_frame(frame)


# ── 2. the heartbeat asks WasCancelled() before anything else ──────────

def test_heartbeat_checks_was_cancelled():
    frame = _frame()
    try:
        dlg = FakeDialog(cancel=False, was_cancelled=True)
        _arm(frame, dlg)
        # Real progress "just arrived": the old tick returned right here.
        frame._last_progress_at = time.monotonic()
        frame._hb_tick(None)
        assert frame._dl_cancelled, "heartbeat did not notice Cancel"
        assert frame._dl_done and dlg.destroyed

        # Frame mode, AI pass: Cancel still means "keep what is done".
        dlg = FakeDialog(cancel=False, was_cancelled=True)
        _arm(frame, dlg)
        frame._frame_ai_phase = True
        frame._hb_tick(None)
        assert frame._ai_cancelled, "frame-mode cancel lost its meaning"
        assert not frame._dl_cancelled, "frame-mode cancel threw work away"
    finally:
        _arm(frame, None)
        _destroy_frame(frame)


# ── 3. a closed window ignores the worker's late calls ─────────────────

def test_dead_frame_ignores_late_calls():
    errors: list[str] = []
    old_hook = sys.excepthook

    def hook(kind, value, tb):
        errors.append(f"{kind.__name__}: {value}")

    sys.excepthook = hook
    try:
        # Posted while alive, run after Destroy (the owner's crash).
        frame = _frame()
        frame._ui(frame.SetStatusText, "late")
        frame._ui(frame._log, "late")
        frame.Destroy()
        _drain_events()
        # Called after the frame is gone.
        frame._processing_done()
        frame._close_download_progress()
        frame._video_status_tick("uploading")
        frame._download_progress_tick_text("late", -1)
        frame._ui(frame.SetStatusText, "late")
        _drain_events()
    finally:
        sys.excepthook = old_hook
    assert not errors, f"late calls raised: {errors}"


def test_close_runs_child_close_handlers():
    frame = _frame()
    closed: list[str] = []
    player = wx.Frame(frame, title="player")
    editor = wx.Frame(player, title="editor")

    def on_close(name, win):
        def handler(event):
            closed.append(name)
            win.Destroy()
        return handler

    player.Bind(wx.EVT_CLOSE, on_close("player", player))
    editor.Bind(wx.EVT_CLOSE, on_close("editor", editor))
    _drain_events(rounds=3)
    frame._on_close_window(None)
    _drain_events()
    assert closed == ["editor", "player"], (
        f"child close handlers run: {closed} (expected editor, player)")


# ── 4/5. what the user is told when a job fails ────────────────────────

def _run_failing_job(error: Exception, shown: bool = False):
    """Run the real pipeline with a video probe that raises `error`.
    Returns (new log text, message boxes shown)."""
    import omni_describer_custom.ui.main_frame as mf

    class FailingVP:
        ffmpeg = "ffmpeg"

        async def get_video_info(self, *args, **kwargs):
            raise error

    boxes: list[tuple] = []
    old_vp, old_box = mf.VideoProcessor, wx.MessageBox
    mf.VideoProcessor = FailingVP
    wx.MessageBox = lambda *a, **k: boxes.append(a) or wx.OK
    frame = _frame()
    try:
        frame._ensure_download_progress = lambda: None  # no real dialog
        if shown:
            frame.IsShown = lambda: True
        before = frame.log_text.GetValue()
        frame._processing = True
        frame._process_video("C:/no/such/video.mp4", "describe")
        _drain_events()
        return frame.log_text.GetValue()[len(before):], boxes
    finally:
        mf.VideoProcessor = old_vp
        wx.MessageBox = old_box
        _destroy_frame(frame)


def test_owner_413_is_told_in_words():
    from omni_describer_custom.i18n.strings import t
    log, _ = _run_failing_job(RuntimeError(OWNER_413))
    assert log.strip(), "nothing was logged"
    assert "{" not in log, f"raw JSON reached the user: {log!r}"
    assert "user_" not in log, f"account id reached the user: {log!r}"
    assert t("error.ai_too_large") in log, f"413 not explained: {log!r}"
    # Same rule for a frame-mode placeholder.
    from omni_describer_custom.ui.main_frame import MainFrame
    text = MainFrame._error_text(OWNER_413)
    assert "{" not in text and "user_" not in text, text


def test_failure_is_shown_in_a_message_box():
    from omni_describer_custom.i18n.strings import t
    _, boxes = _run_failing_job(RuntimeError(OWNER_413), shown=True)
    titles = [a[1] for a in boxes if len(a) > 1]
    assert t("process.failed_title") in titles, (
        f"no failure message box (NVDA reads it): {boxes}")


def test_source_error_403_is_forbidden_message():
    from omni_describer_custom.core.video_processor import SourceError
    from omni_describer_custom.i18n.strings import t
    log, _ = _run_failing_job(SourceError(YT_403))
    assert t("error.download_forbidden") in log, (
        f"403 not explained: {log!r}")
    assert "https://" not in log, f"URL reached the user: {log!r}"


# ── smaller fixes ──────────────────────────────────────────────────────

def test_fast_mode_ffmpeg_obeys_cancel():
    frame = _frame()
    try:
        _arm(frame, None)
        timer = threading.Timer(0.4, lambda: setattr(frame, "_dl_cancelled",
                                                     True))
        timer.start()
        started = time.monotonic()
        try:
            frame._run_cancellable(
                [sys.executable, "-c", "import time; time.sleep(30)"], 900)
            raise AssertionError("a cancelled run returned normally")
        except RuntimeError as e:
            assert str(e) == "cancelled", e
        took = time.monotonic() - started
        assert took < 5, f"Cancel took {took:.1f} s"
    finally:
        _arm(frame, None)
        _destroy_frame(frame)


def test_empty_provider_means_glm():
    frame = _frame()
    try:
        frame.settings.set("ai.default_provider", "")
        assert frame._provider_name() == "glm", frame._provider_name()
    finally:
        _destroy_frame(frame)


def test_exports_open_in_the_output_folder():
    """v1.9.6: Settings > General > Output Directory was stored and used
    nowhere; the export Save dialogs now open there."""
    import tempfile
    frame = _frame()
    try:
        folder = tempfile.mkdtemp(prefix="odc_t60out_")
        frame.settings = {"general.output_dir": folder}
        assert frame._export_dir() == folder
        frame.settings = {"general.output_dir": folder + "_missing"}
        assert frame._export_dir() == ""
        frame.settings = {}
        assert frame._export_dir() == ""
        src = Path("src/omni_describer_custom/ui/main_frame.py").read_text(encoding="utf-8")
        assert src.count("defaultDir=self._export_dir()") == 3
    finally:
        frame.Destroy()
        _drain_events()


def main() -> int:
    app = wx.App(False)
    check("every progress tick registers Cancel",
          test_every_tick_registers_cancel)
    check("the heartbeat checks WasCancelled() first",
          test_heartbeat_checks_was_cancelled)
    check("a closed main window ignores late worker calls",
          test_dead_frame_ignores_late_calls)
    check("closing the main window runs Player/Editor close handlers",
          test_close_runs_child_close_handlers)
    check("the owner's HTTP 413 is told in words (no JSON, no user id)",
          test_owner_413_is_told_in_words)
    check("a failed job is shown in a message box",
          test_failure_is_shown_in_a_message_box)
    check("a download 403 (SourceError) says error.download_forbidden",
          test_source_error_403_is_forbidden_message)
    check("fast-mode ffmpeg is killed on Cancel",
          test_fast_mode_ffmpeg_obeys_cancel)
    check("an empty provider means glm, as in Settings",
          test_empty_provider_means_glm)
    check("exports open in the output folder",
          test_exports_open_in_the_output_folder)
    _drain_events()
    del app
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
