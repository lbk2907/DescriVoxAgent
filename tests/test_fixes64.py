"""Regression round 64: ONE real progress bar for the whole job, read by
NVDA, and no periodic spoken reports (owner's decision, 2 Oct 2026).

The owner's NVDA reads progress bars itself ("Progress bar output: Speak
and beep"). wx.ProgressDialog on Windows has no real progress bar (its
bar is DirectUI-drawn, pitfall 3), each step restarted its own 0-100%,
and a spoken report every 30 s was not wanted. Now:

(a) AccessibleProgressDialog has a real wx.Gauge (msctls_progress32),
    named for NVDA by the StaticText created just before it; the bar
    never moves backwards; Cancel/Esc are recorded, not destroying it.
(b) A whole job moves ONE overall bar, monotonically, through download
    -> transcript -> upload -> wait -> review, each in its own slice.
(c) Gemini's silent wait (no percentage) moves the bar by time, never
    to the end of the AI stage before the answer.
(d) The heartbeat speaks nothing and leaves the dialog text alone.
(e) Whisper reports how far it is through the audio.

Every check here fails on the code before this round.
"""

import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
import ctypes
import io
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

if "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
if "pytest" not in sys.modules:
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
sys.path.insert(0, "src")

import wx  # noqa: E402

from omni_describer_custom.i18n.strings import t  # noqa: E402

results: list[tuple[str, bool]] = []
TMP = Path(tempfile.mkdtemp(prefix="odc_t64_"))


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def _drain(rounds=12):
    app = wx.GetApp()
    for _ in range(rounds):
        app.ProcessPendingEvents()
        app.Yield()
        time.sleep(0.02)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class RecordingDialog:
    """Progress dialog stand-in that records every text it is given."""

    def __init__(self):
        self.texts = []
        self.value = 0

    def _take(self, args):
        if args and args[0]:
            self.texts.append(args[0])
        return (True, False)

    def Pulse(self, *args):
        return self._take(args)

    def Update(self, value, *args):
        self.value = value
        return self._take(args)

    def WasCancelled(self):
        return False

    def SetTitle(self, *a):
        pass

    def Destroy(self):
        pass


def _main_frame():
    from omni_describer_custom.ui import main_frame as mf

    frame = mf.MainFrame()
    spoken = []
    frame._speak_progress = lambda text: spoken.append(text)
    frame._dl_done = frame._dl_cancelled = False
    return frame, spoken


def _close(frame):
    try:
        frame._dl_done = True
        frame._close_download_progress()
    except Exception:
        pass
    _drain()
    frame.Destroy()
    _drain()


# ── (a) the dialog itself ─────────────────────────────────────────────


def test_a_dialog_has_a_real_bar_that_never_goes_back():
    from omni_describer_custom.ui.progress_dialog import AccessibleProgressDialog

    owner = wx.Frame(None)
    owner.Show()
    dlg = AccessibleProgressDialog("Job", "first", maximum=100, parent=owner)
    try:
        _drain(3)
        gauges = [c for c in dlg.GetChildren() if isinstance(c, wx.Gauge)]
        assert len(gauges) == 1, f"no real progress bar: {dlg.GetChildren()}"
        gauge = gauges[0]
        buf = ctypes.create_unicode_buffer(64)
        ctypes.windll.user32.GetClassNameW(gauge.GetHandle(), buf, 64)
        assert buf.value == "msctls_progress32", buf.value

        # Named for NVDA: the StaticText created just before it (pitfall
        # 34/53; Windows takes the name from the previous window).
        kids = list(dlg.GetChildren())
        before = kids[kids.index(gauge) - 1]
        assert isinstance(before, wx.StaticText), type(before)
        assert before.GetLabel().strip(), "the bar's label is empty"
        GW_HWNDPREV = 3
        prev = ctypes.windll.user32.GetWindow(gauge.GetHandle(), GW_HWNDPREV)
        assert prev == before.GetHandle(), "label is not the window before the bar"
        assert isinstance(kids[-1], wx.Button), "Cancel is not last in tab order"

        assert not owner.IsEnabled(), "the main window stays usable (not app-modal)"

        assert dlg.Update(40, "second") == (True, False)
        assert gauge.GetValue() == 40 and dlg.GetValue() == 40
        dlg.Update(10)
        assert gauge.GetValue() == 40, f"the bar went back to {gauge.GetValue()}"
        dlg.Pulse("third")
        assert gauge.GetValue() == 40, "Pulse moved the bar"
        assert dlg.GetMessage() == "third"

        # Text is written only when it changes (pitfall 65).
        calls = []
        real = dlg._text.SetLabelText
        dlg._text.SetLabelText = lambda s: calls.append(s) or real(s)
        dlg.Update(41, "third")
        dlg.Pulse("third")
        assert calls == [], f"unchanged text rewritten: {calls}"
        dlg._text.SetLabelText = real

        # Cancel: recorded, the dialog stays until its owner closes it.
        button = dlg.FindWindowById(wx.ID_CANCEL)
        evt = wx.CommandEvent(wx.wxEVT_BUTTON, wx.ID_CANCEL)
        evt.SetEventObject(button)
        button.GetEventHandler().ProcessEvent(evt)
        _drain(3)
        assert dlg.WasCancelled()
        assert dlg.Update(50) == (False, False)
        assert dlg.Pulse() == (False, False)
        assert bool(dlg), "Cancel destroyed the dialog"
    finally:
        dlg.Destroy()
        _drain(3)
    assert owner.IsEnabled(), "the main window was not given back"

    dlg = AccessibleProgressDialog("Job", "esc", parent=owner)
    try:
        key = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        key.SetKeyCode(wx.WXK_ESCAPE)
        button = dlg.FindWindowById(wx.ID_CANCEL)
        key.SetEventObject(button)
        button.GetEventHandler().ProcessEvent(key)
        _drain(3)
        assert dlg.WasCancelled(), "Esc did not cancel"
    finally:
        dlg.Destroy()
        owner.Destroy()
        _drain(3)


# ── (b) one overall bar through a whole job ───────────────────────────


def test_b_a_whole_job_moves_one_bar():
    from omni_describer_custom.core.video_processor import DownloadProgress
    from omni_describer_custom.ui import main_frame as mf

    frame, _ = _main_frame()
    clock = Clock()
    real_mono, mf.time.monotonic = mf.time.monotonic, clock
    seen = []  # (stage, overall, bar)

    def note(stage):
        dlg = frame._dl_dialog
        seen.append((stage, frame._overall_pct(), dlg.GetValue()))

    try:
        frame._ensure_download_progress()
        dlg = frame._dl_dialog
        assert dlg is not None and isinstance(
            [c for c in dlg.GetChildren() if isinstance(c, wx.Gauge)][0], wx.Gauge
        )
        for phase in ("video", "audio"):
            for pct in (0, 25, 50, 75, 100):
                frame._download_progress_tick(
                    DownloadProgress(phase=phase, percent=pct, downloaded_mb=1, total_mb=4)
                )
                note("download")
        frame._download_progress_tick(
            DownloadProgress(phase="merge", percent=-1, downloaded_mb=-1, total_mb=-1)
        )
        note("download")
        frame._video_status_tick("transcript")
        for f in (0.1, 0.5, 0.9, 1.0):
            frame._transcript_tick(f)
            note("transcript")
        frame._wait_basis = ("", 120.0, False)
        frame._video_status_tick("uploading")
        for pct in (0, 30, 60, 100):
            frame._video_upload_tick(pct)
            note("upload")
        frame._video_status_tick("processing")
        for _ in range(60):
            clock.now += 1.0
            frame._hb_tick(None)
            note("wait")
        frame._video_status_tick("describing")
        for _ in range(60):
            clock.now += 1.0
            frame._hb_tick(None)
            note("wait")
        frame._stage_tick("ai", 1.0)  # the answer is in
        note("answer")
        frame._video_status_tick("reviewing")
        for done in range(1, 5):
            frame._review_tick(done, 4)
            note("review")
    finally:
        mf.time.monotonic = real_mono
        _close(frame)

    ranges = {
        "download": (0, 15),
        "transcript": (15, 30),
        "upload": (30, 63),
        "wait": (62, 94),
        "answer": (95, 95),
        "review": (95, 99),
    }
    values = [v for _, v, _ in seen]
    assert values == sorted(values), f"the bar went backwards: {values}"
    for stage, overall, bar in seen:
        lo, hi = ranges[stage]
        assert lo <= overall <= hi, f"{stage} at {overall}% (expected {lo}-{hi})"
        assert bar == overall, f"bar {bar} != overall {overall}"
    assert values[-1] >= 95 and max(values) < 100, values[-1]
    assert values[0] == 0, values[0]


def test_b_openrouter_retry_never_pulls_the_bar_back():
    frame, _ = _main_frame()
    try:
        frame._dl_dialog = RecordingDialog()
        frame._video_status_tick("transcript")
        frame._transcript_tick(1.0)
        frame._video_split_tick(10.0)
        assert frame._overall_pct() == 36, frame._overall_pct()  # 30 + 65*0.10
        frame._video_part_tick(1, 2)
        frame._video_eta_tick(50.0, 100.0)
        high = frame._overall_pct()
        frame._video_eta_tick(20.0, 300.0)  # the part is retried
        assert frame._overall_pct() == high, "the bar went back on a retry"
        assert frame._dl_dialog.value == high
        frame._video_part_tick(2, 2)
        frame._video_eta_tick(100.0, 0.0)
        assert frame._overall_pct() == 95, frame._overall_pct()
    finally:
        frame._dl_dialog = None
        _close(frame)


# ── (c) Gemini: no percentage, the bar moves by time ──────────────────


def test_c_gemini_wait_moves_by_time_and_stops_short():
    from omni_describer_custom.ui import main_frame as mf

    frame, _ = _main_frame()
    clock = Clock()
    real_mono, mf.time.monotonic = mf.time.monotonic, clock
    try:
        dlg = frame._dl_dialog = RecordingDialog()
        frame._wait_basis = ("", 600.0, False)  # 60 + 0.5 * 600 = 360 s
        frame._video_status_tick("uploading")
        frame._video_upload_tick(100.0)
        start = frame._overall_pct()
        assert start == 62, start  # half of the AI stage
        frame._video_status_tick("processing")
        values = []
        for _ in range(360):
            clock.now += 1.0
            frame._hb_tick(None)
            values.append(frame._overall_pct())
        assert values == sorted(values), "the bar went back"
        assert values[0] <= start + 1, values[0]
        assert 80 <= values[-1] <= 90, f"at the estimate: {values[-1]}%"
        assert t("video.eta_minutes", minutes=6) in "".join(dlg.texts), dlg.texts
        for _ in range(100):
            clock.now += 1000.0
            frame._hb_tick(None)
        assert frame._overall_pct() < 95, (
            f"the wait reached {frame._overall_pct()}% before the answer"
        )
        assert t("video.eta_over") in dlg.texts[-1], dlg.texts[-1]
        # A hundred heartbeats with the same words wrote the text once.
        assert dlg.texts.count(dlg.texts[-1]) == 1, dlg.texts
        # The answer: the stage ends, and the wait stops writing.
        frame._stage_tick("ai", 1.0)
        assert frame._overall_pct() == 95, frame._overall_pct()
        n = len(dlg.texts)
        frame._download_progress_tick_text(t("download.saving"), -1)
        for _ in range(5):
            clock.now += 60.0
            frame._hb_tick(None)
        assert dlg.texts[n:] == [t("download.saving")], dlg.texts[n:]
    finally:
        mf.time.monotonic = real_mono
        frame._dl_dialog = None
        _close(frame)


# ── (d) no periodic speech, no changing seconds ──────────────────────


def test_d_the_heartbeat_says_nothing():
    from omni_describer_custom.ui import main_frame as mf

    frame, spoken = _main_frame()
    clock = Clock()
    real_mono, mf.time.monotonic = mf.time.monotonic, clock
    try:
        announced = []
        real_announce = frame._announce_progress

        def announce(text, part=False):
            announced.append(text)
            real_announce(text, part)

        frame._announce_progress = announce
        dlg = frame._dl_dialog = RecordingDialog()
        frame._hb_start_timer(t("video.phase_transcript"))
        frame._hb_timer.Stop()
        frame._video_status_tick("transcript")  # a phase change: said once
        # The 0.8 s CallLater does not fire without a main loop here.
        frame._announce_timer.Stop()
        frame._announce_flush()
        assert announced == [t("video.phase_transcript")], announced
        assert len(spoken) == 1, spoken
        before = len(dlg.texts)
        for _ in range(120):
            clock.now += 1.0
            frame._hb_tick(None)
        timer = getattr(frame, "_announce_timer", None)
        if timer is not None and timer.IsRunning():
            timer.Stop()
            frame._announce_flush()
        assert len(spoken) == 1 and len(announced) == 1, (
            f"the heartbeat spoke: {spoken[1:] + announced[1:]}"
        )
        changed = dlg.texts[before:]
        assert not changed, f"the dialog text changed {len(changed)} times: {changed[:3]}"
    finally:
        mf.time.monotonic = real_mono
        frame._dl_dialog = None
        _close(frame)


# ── (e) Whisper reports its position ─────────────────────────────────


class FakeWhisper:
    """faster-whisper stand-in (as in test_fixes59): 1000 one-second
    segments of a 1000 s video."""

    def __init__(self, *a, **k):
        pass

    def transcribe(self, path, **kw):
        def gen():
            for i in range(1000):
                yield types.SimpleNamespace(start=float(i), end=i + 0.9, text=f"line {i}")

        return gen(), types.SimpleNamespace(duration=1000.0, language="en")


def test_e_whisper_reports_progress():
    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.core.video_processor import VideoProcessor

    sys.modules["faster_whisper"] = types.SimpleNamespace(WhisperModel=FakeWhisper)
    SettingsStore().set("general.transcription_backend", "whisper")
    clip = TMP / "e.mp4"
    clip.write_bytes(b"x")
    cache = TMP / "proj" / "media" / "transcript.json"
    got = []
    segs = asyncio.run(
        VideoProcessor().get_transcript(
            str(clip), local_path=str(clip), cache_path=cache, on_progress=got.append
        )
    )
    assert len(segs) == 1000
    assert len(got) == 1000, len(got)
    assert got == sorted(got) and got[0] < 0.01 and got[-1] >= 0.99, (got[:3], got[-3:])
    # The project cache answers at once: nothing to report, no error.
    got.clear()
    again = asyncio.run(
        VideoProcessor().get_transcript(
            str(clip), local_path=str(clip), cache_path=cache, on_progress=got.append
        )
    )
    assert len(again) == 1000 and got == [], got


def main() -> int:
    app = wx.App(False)
    check(
        "(a) the dialog has a real, labelled bar that never goes back; Cancel and Esc are recorded",
        test_a_dialog_has_a_real_bar_that_never_goes_back,
    )
    check("(b) a whole job moves ONE bar through every stage", test_b_a_whole_job_moves_one_bar)
    check(
        "(b) an OpenRouter retry never pulls the bar back",
        test_b_openrouter_retry_never_pulls_the_bar_back,
    )
    check(
        "(c) Gemini's wait moves by time and stops short of the end",
        test_c_gemini_wait_moves_by_time_and_stops_short,
    )
    check(
        "(d) the heartbeat says nothing and leaves the text alone",
        test_d_the_heartbeat_says_nothing,
    )
    check("(e) Whisper reports how far it is", test_e_whisper_reports_progress)
    _drain()
    del app
    import shutil

    shutil.rmtree(TMP, ignore_errors=True)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
