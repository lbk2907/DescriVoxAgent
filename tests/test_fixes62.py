"""Regression round 62: Cancel that really stops, windows that close safely (v1.9.6).

Found in an audit of the secondary windows:
  - review.FrameStrip decoded the WHOLE film with subprocess.run and
    ignored its is_cancelled (up to 48 minutes for a 24-minute film), and
    up to eight in-flight engine.look() calls had to finish first;
  - timeline_io.export_audio had no way to be cancelled at all;
  - Settings, the Player, Ask More and the Scene Explorer let a worker's
    wx.CallAfter reach a window that had already been destroyed
    (RuntimeError: wrapped C/C++ object has been deleted);
  - TTSEngine.speak_and_play lost a stop() pressed while the speech was
    being generated (Edge = a network round trip), so the clip played
    in full — e.g. after the player was closed.

Every check below fails on the code before v1.9.6.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
import io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import wave

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

import wx  # noqa: E402

results: list[tuple[str, bool]] = []
_WORK = tempfile.mkdtemp(prefix="odc_t62_w_")


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def _drain(rounds: int = 12, delay: float = 0.02) -> None:
    """Dispatch queued wx.CallAfter calls (pitfall 10)."""
    app = wx.GetApp()
    if app is None:
        return
    for _ in range(rounds):
        app.ProcessPendingEvents()
        app.Yield()
        time.sleep(delay)


class _Errors:
    """Collect exceptions raised inside wx callbacks.

    wxPython prints an exception from a CallAfter handler through
    sys.excepthook and carries on, so a test would never see it."""

    def __init__(self):
        self.seen: list[BaseException] = []

    def __enter__(self):
        self._old = sys.excepthook
        sys.excepthook = lambda tp, val, tb: self.seen.append(val)
        return self

    def __exit__(self, *exc):
        sys.excepthook = self._old
        return False


def _ffmpeg() -> str:
    from omni_describer_custom.core.tools import find_tool
    return find_tool("ffmpeg")


def _clip(name: str, seconds: int) -> str:
    """A small test clip made with the bundled ffmpeg (lavfi testsrc)."""
    path = os.path.join(_WORK, name)
    if not os.path.exists(path):
        subprocess.run(
            [_ffmpeg(), "-hide_banner", "-nostdin", "-y", "-v", "error",
             "-f", "lavfi", "-i", f"testsrc=size=320x240:rate=25:d={seconds}",
             "-c:v", "mpeg4", "-q:v", "5", path],
            check=True, timeout=120)
    return path


def _long_video(name: str = "long.ffconcat") -> str:
    """A very long video that is quick to make: an ffconcat list that
    repeats a 10-second clip 900 times (2.5 hours). ffmpeg detects the
    list by its header, so FrameStrip opens it like any video file."""
    _clip("c.mp4", 10)
    path = os.path.join(_WORK, name)
    with open(path, "w", encoding="ascii") as f:
        f.write("ffconcat version 1.0\n")
        for _ in range(900):
            f.write("file c.mp4\n")
    return path


def _kill_strays() -> None:
    """Old code leaves its ffmpeg decoding; do not leave it running."""
    if sys.platform != "win32":
        return
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='ffmpeg.exe'\" | "
         f"Where-Object {{ $_.CommandLine -like '*{os.path.basename(_WORK)}*' }} | "
         "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
        capture_output=True, timeout=60)


# ── 1. Review: Cancel stops the frame extraction ───────────────────

def test_frame_strip_stops_on_cancel():
    from omni_describer_custom.core.review import FrameStrip
    video = _long_video()
    before = set(os.listdir(tempfile.gettempdir()))
    flag = {"cancel": False}
    outcome = {}

    def work():
        try:
            FrameStrip(video, 9000.0, lambda: flag["cancel"])
            outcome["error"] = "finished"
        except Exception as e:
            outcome["error"] = str(e)

    th = threading.Thread(target=work, daemon=True)
    th.start()
    time.sleep(1.0)
    assert th.is_alive(), "extraction ended before Cancel (clip too short?)"
    flag["cancel"] = True
    pressed = time.monotonic()
    th.join(timeout=8)
    try:
        assert not th.is_alive(), \
            "FrameStrip kept decoding the whole video after Cancel"
        took = time.monotonic() - pressed
        assert took < 2.5, f"Cancel took {took:.1f}s to stop ffmpeg"
        assert outcome.get("error") == "cancelled", outcome
        left = [n for n in set(os.listdir(tempfile.gettempdir())) - before
                if n.startswith("odc_review_")]
        assert not left, f"cancelled extraction left {left}"
    finally:
        _kill_strays()


def test_review_abandons_looks_in_flight():
    from omni_describer_custom.core import review as R
    video = _clip("short.mp4", 12)
    flag = {"cancel": False}

    class SlowEngine:
        async def look(self, path, prompt):
            await asyncio.sleep(30)
            return '{"here": true, "best": "0:01.0"}'

    pairs = [(float(i), f"cue {i}") for i in range(1, 9)]
    outcome = {}

    def work():
        try:
            asyncio.run(R.review(SlowEngine(), video, pairs, "accurate",
                                 12.0, is_cancelled=lambda: flag["cancel"]))
            outcome["error"] = "finished"
        except Exception as e:
            outcome["error"] = str(e)

    th = threading.Thread(target=work, daemon=True)
    th.start()
    time.sleep(3.0)          # frames extracted, the looks are waiting
    flag["cancel"] = True
    pressed = time.monotonic()
    th.join(timeout=10)
    assert not th.is_alive(), "review waited for the looks in flight"
    took = time.monotonic() - pressed
    assert took < 2.5, f"Cancel took {took:.1f}s"
    assert outcome.get("error") == "cancelled", outcome


# ── 2. Audio export can be cancelled ───────────────────────────────

def test_export_audio_cancels():
    from omni_describer_custom.core import timeline_io as T
    from omni_describer_custom.core.project_store import Description

    class FakeTTS:
        calls = 0

        async def speak(self, text, engine="", voice="", speed=0.0):
            FakeTTS.calls += 1
            fd, path = tempfile.mkstemp(suffix=".wav", prefix="odc_t62_")
            os.close(fd)
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(b"\0\0" * 1600)
            return path

    out = os.path.join(_WORK, "export.mp3")
    descs = [Description(start_time=i, end_time=i + 1, text=f"cue {i}")
             for i in range(5)]
    try:
        T.export_audio(descs, out, FakeTTS(), is_cancelled=lambda: True)
    except RuntimeError as e:
        assert str(e) == "cancelled", f"wrong error: {e}"
    except TypeError as e:
        raise AssertionError(f"export_audio cannot be cancelled: {e}")
    else:
        raise AssertionError("export_audio finished despite Cancel")
    assert FakeTTS.calls == 0, f"{FakeTTS.calls} cue(s) rendered after Cancel"
    assert not os.path.exists(out), "a cancelled export left a file"


# ── 3. Settings closed while a worker is still running ─────────────

def test_settings_results_after_close():
    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(None, SettingsStore())
    dlg.Show()
    _drain()
    dlg.Destroy()
    _drain(rounds=6)
    # What a Fetch models / Test worker queues when it finishes late.
    dlg._show_test_result("late result")
    dlg._apply_fetched_models([{"id": "a/b", "name": "B", "audio": False,
                                "price_in": 0.1}])
    with _Errors() as errs:
        wx.CallAfter(dlg._show_test_result, "late")
        if hasattr(dlg, "_fetch_done"):
            wx.CallAfter(dlg._fetch_done)
        _drain(rounds=4)
    assert not errs.seen, f"late Settings results raised: {errs.seen!r}"


def test_settings_language_boxes_in_tab_order():
    """Pitfall 34: on screen in creation order, each box under its label."""
    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(None, SettingsStore())
    try:
        dlg.Show()
        _drain(rounds=4)
        sizer = dlg.lang_choice.GetContainingSizer()
        shown = [i.GetWindow() for i in sizer.GetChildren() if i.GetWindow()]
        lang, desc = shown.index(dlg.lang_choice), shown.index(dlg.desc_lang_choice)
        assert lang < desc, "Language box is laid out below Description language"
        assert shown[lang - 1].GetName() == "general_lang_label"
        assert shown[desc - 1].GetName() == "desc_lang_label"
        y = dlg.lang_choice.GetPosition().y
        assert y < dlg.desc_lang_choice.GetPosition().y
    finally:
        _drain()
        dlg.Destroy()
        _drain(rounds=4)


# ── 4. Player: an announcement after the window closed ─────────────

def _store():
    from omni_describer_custom.core.project_store import Description, ProjectStore
    store = ProjectStore(tempfile.mkdtemp(prefix="p_", dir=_WORK))
    store.create_project("t62", "C:/none.mp4")
    store.set_video_duration(90.0)
    store.save_descriptions([Description(start_time=5, end_time=8, text="A.")])
    return store


def test_player_announce_after_close():
    from omni_describer_custom.core.tts_engine import TTSEngine
    from omni_describer_custom.ui.player_window import PlayerWindow
    player = PlayerWindow(None, _store(), TTSEngine({}))
    player.Show()
    _drain(rounds=4)
    player._timer.Stop()
    player.Destroy()
    _drain(rounds=6)
    player._announce("spoken")          # a speech thread finishing late
    with _Errors() as errs:
        wx.CallAfter(lambda: player._announce("tts failed"))
        _drain(rounds=4)
    assert not errs.seen, f"late player announcement raised: {errs.seen!r}"


# ── 5. Ask More: the answer arrives after Cancel ───────────────────

def test_ask_more_reply_after_close():
    from omni_describer_custom.ui.ask_more_dialog import AskMoreDialog

    class SlowAI:
        output_lang = ""
        finished = threading.Event()

        async def ask(self, q, history=None):
            await asyncio.sleep(0.4)
            SlowAI.finished.set()
            return "a late answer"

    dlg = AskMoreDialog(None, SlowAI(), [], 0.0)
    dlg.Show()
    _drain(rounds=4)
    dlg.question_text.SetValue("what is on screen?")
    with _Errors() as errs:
        dlg._on_submit(None)
        dlg._on_cancel(None)            # Esc: not modal here, so Destroy
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            _drain(rounds=2)
        _drain()
    assert not errs.seen, f"the late answer reached a closed dialog: {errs.seen!r}"


# ── 6. stop() during generation is not lost ────────────────────────

def test_stop_during_generation_skips_playback():
    from omni_describer_custom.core.tts_engine import TTSEngine
    eng = TTSEngine({})
    played = []

    async def slow_speak(text, engine="", voice="", speed=0.0):
        await asyncio.sleep(0.5)        # Edge TTS: a network round trip
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="odc_t62_")
        os.close(fd)
        return path

    eng.speak = slow_speak
    eng._play_file = lambda path, *a, **k: played.append(path) or True
    th = threading.Thread(target=eng.speak_and_play, args=("hello", "sapi5"),
                          daemon=True)
    th.start()
    time.sleep(0.15)
    eng.stop()                          # the user pressed Stop / closed
    th.join(timeout=5)
    assert not th.is_alive()
    assert not played, "the clip played in full after stop()"


def test_scene_explorer_close_while_loading():
    """Closing during extraction stops it and leaves no odc_explorer_."""
    from omni_describer_custom.ui.scene_explorer import SceneExplorer
    # A video extension, so it is treated as a local file and goes
    # straight to the ffmpeg extraction (ffmpeg still reads the list).
    video = _long_video("long.mp4")
    before = set(os.listdir(tempfile.gettempdir()))
    with _Errors() as errs:
        ex = SceneExplorer(None, None, video)
        ex.Show()
        _drain(rounds=4)
        time.sleep(1.0)
        ex.Close()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            _drain(rounds=2)
            left = [n for n in set(os.listdir(tempfile.gettempdir())) - before
                    if n.startswith("odc_explorer_")]
            if not left:
                break
        _drain()
    _kill_strays()
    assert not left, f"closed explorer left {left}"
    assert not errs.seen, f"explorer raised after close: {errs.seen!r}"


def main() -> int:
    app = wx.App(False)
    try:
        check("review: Cancel stops the frame extraction",
              test_frame_strip_stops_on_cancel)
        check("review: Cancel abandons the looks in flight",
              test_review_abandons_looks_in_flight)
        check("audio export can be cancelled", test_export_audio_cancels)
        check("Settings: late worker results after close",
              test_settings_results_after_close)
        check("Settings: language boxes laid out in Tab order",
              test_settings_language_boxes_in_tab_order)
        check("Player: announcement after close", test_player_announce_after_close)
        check("Ask More: answer after Cancel", test_ask_more_reply_after_close)
        check("TTS: stop() during generation skips playback",
              test_stop_during_generation_skips_playback)
        check("Scene Explorer: close while loading",
              test_scene_explorer_close_while_loading)
    finally:
        _kill_strays()
        _drain()
        del app
        shutil.rmtree(_WORK, ignore_errors=True)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
