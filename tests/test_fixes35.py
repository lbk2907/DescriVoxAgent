"""Regression round 35: UI / TTS audit fixes (v1.7.4).

Each check reproduces a defect found by running the real windows
headlessly, not by reading code:

  1. Editor: selecting another description discarded the edit.
  2. Editor: closing the player (its parent) destroyed the editor
     without saving.
  3. Player kept its OWN SettingsStore; each store's save overwrote the
     other's keys (pause toggle wiped a new API key, and vice versa).
  4. Player narrated the first cue at 0:00, before its start time.
  5. Past the last cue the player showed the FIRST cue as current.
  6. Failed TTS synthesis leaked an empty temp file per call.
  7. TTSEngine.stop() never stopped audio already playing.
  8. Ask More sent the question twice and ignored the seconds field.
  9. "Read Description" button label was hardcoded English.
 10. Added descriptions were out of time order and never narrated.
 11. VLC Pause during a narration hold toggled the video back ON.
 12. Settings voice list lost its "Default" entry.
"""
import io
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

os.environ["ODC_CONFIG_DIR"] = tempfile.mkdtemp(prefix="odc35_")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "omni_describer_custom"
sys.path.insert(0, str(ROOT / "src"))

import wx  # noqa: E402

app = wx.App(False)

from omni_describer_custom.core.project_store import Description  # noqa: E402
from omni_describer_custom.ui import player_window as pw  # noqa: E402
from omni_describer_custom.ui.editor_window import EditorWindow  # noqa: E402
from omni_describer_custom.ui.ask_more_dialog import AskMoreDialog  # noqa: E402


class _Proj:
    def __init__(self):
        self.name = "t"
        self.id = 1
        self.video_path = ""
        self.video_duration = 60.0
        self.descriptions = [
            Description(id=1, start_time=5, end_time=8, text="first at 5s"),
            Description(id=2, start_time=20, end_time=25, text="second at 20s"),
        ]


class _Store:
    def __init__(self):
        self.current = _Proj()
        self.projects_dir = tempfile.mkdtemp()
        self.saved = None
        self._next = 100

    def project_dir(self, project_id):
        # v1.7.6: the player asks the store where a project lives.
        return Path(self.projects_dir) / f"Project ({project_id})"

    def save_descriptions(self, d):
        self.saved = [(x.start_time, x.text) for x in d]

    def add_description(self, d):
        self._next += 1
        d.id = self._next
        self.current.descriptions.append(d)
        return d

    def delete_description(self, i):
        self.current.descriptions = [
            x for x in self.current.descriptions if x.id != i]


class _TTS:
    def __init__(self):
        self.spoken = []

    def speak_and_play(self, text):
        self.spoken.append(text)
        return True

    def stop(self):
        pass

    def supports_narration_hold(self):
        return False


class _Settings:
    def __init__(self):
        self.data = {}

    def get(self, k, default=None):
        return self.data.get(k, default)

    def set(self, k, v):
        self.data[k] = v


def _drain():
    for _ in range(5):
        wx.YieldIfNeeded()
        app.ProcessPendingEvents()


def _player(store=None, tts=None, **kw):
    w = pw.PlayerWindow(None, store or _Store(), tts or _TTS(), **kw)
    w._vlc_available = False
    w._timer.Stop()
    return w


def test_editor_keeps_edit_when_selection_moves():
    store = _Store()
    w = _player(store)
    ed = EditorWindow(w, store, _TTS())
    ed.text_ctrl.SetValue("EDITED first")
    ed.desc_list.Select(1)
    ed._on_select(None)
    ed.desc_list.Select(0)
    ed._on_select(None)
    assert store.current.descriptions[0].text == "EDITED first", (
        store.current.descriptions[0].text)
    assert ed.text_ctrl.GetValue() == "EDITED first"
    ed.Destroy()
    w.Destroy()
    _drain()


def test_player_close_saves_open_editor():
    store = _Store()
    w = _player(store)
    ed = EditorWindow(w, store, _TTS())
    ed.text_ctrl.SetValue("EDIT2")
    w._on_close(None)
    _drain()
    assert store.saved is not None, "editor edits not saved on player close"
    assert (5, "EDIT2") in store.saved, store.saved


def test_player_uses_shared_settings():
    shared = _Settings()
    w = _player(settings=shared)
    assert w._settings is shared
    w.pause_narration_check.SetValue(False)
    w._on_pause_narration_toggle(None)
    assert shared.data.get("player.pause_for_narration") is False
    w.Destroy()
    # Fallback: parent's settings, then a private store.
    parent = wx.Frame(None)
    parent.settings = shared
    w2 = pw.PlayerWindow(parent, _Store(), _TTS())
    w2._timer.Stop()
    assert w2._settings is shared
    w2.Destroy()
    parent.Destroy()
    w3 = _player()
    assert w3._settings is not None
    w3.Destroy()
    _drain()
    main = (SRC / "ui" / "main_frame.py").read_text(encoding="utf-8")
    assert "settings=self.settings" in main, "main frame does not share settings"


def test_first_cue_not_narrated_before_start():
    tts = _TTS()
    w = _player(tts=tts)
    w._playing = True
    w._position = 0.0
    w._update_desc_display()
    w._maybe_narrate()
    time.sleep(0.2)
    assert tts.spoken == [], f"narrated early: {tts.spoken}"
    w._position = 5.0
    w._update_desc_display()
    w._maybe_narrate()
    time.sleep(0.3)
    assert tts.spoken == ["first at 5s"], tts.spoken
    w._playing = False
    w.Destroy()
    _drain()


def test_after_last_cue_last_is_current():
    w = _player()
    w._position = 40.0
    w._update_desc_display()
    assert w.current_desc_text.GetValue() == "second at 20s", (
        w.current_desc_text.GetValue())
    w.Destroy()
    _drain()


def test_failed_tts_leaves_no_temp_file():
    import asyncio
    import glob
    import edge_tts
    from omni_describer_custom.core.tts_engine import EdgeTTSEngine

    class Boom:
        def __init__(self, *a, **k):
            pass

        async def save(self, p):
            raise OSError("offline")

    orig = edge_tts.Communicate
    edge_tts.Communicate = Boom
    try:
        pattern = os.path.join(tempfile.gettempdir(), "*.mp3")
        before = set(glob.glob(pattern))
        e = EdgeTTSEngine()
        e.available = True
        for _ in range(3):
            assert asyncio.run(e.speak("hi")) == ""
        new = set(glob.glob(pattern)) - before
        assert not new, f"leaked {len(new)} temp files"
    finally:
        edge_tts.Communicate = orig


def _silent_wav(seconds=4.0):
    import wave
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))
    return path


def test_stop_ends_playback():
    """Silent WAV so nothing is heard. Both winsound and MCI paths."""
    import threading
    from omni_describer_custom.core.tts_engine import TTSEngine
    eng = TTSEngine({})
    short = _silent_wav(1.0)
    try:
        # Unstopped playback must still block for the audio's length:
        # the narration hold waits on it.
        t0 = time.monotonic()
        assert eng._play_file(short)
        took = time.monotonic() - t0
        assert 0.9 <= took < 2.0, f"blocking play took {took:.2f}s"
    finally:
        os.remove(short)
    path = _silent_wav()
    try:
        # winsound path (.wav)
        t0 = time.monotonic()
        th = threading.Thread(target=eng._play_file, args=(path,))
        th.start()
        time.sleep(0.5)
        eng.stop()
        th.join(3)
        assert not th.is_alive() and time.monotonic() - t0 < 2.5, (
            "winsound playback not stopped")
        # MCI path: same audio renamed so winsound is skipped
        mp = path[:-4] + ".mci"
        os.replace(path, mp)
        path = mp
        # Unstopped MCI playback still blocks for the audio's length.
        t1 = time.monotonic()
        short = _silent_wav(1.0)
        short_mci = short[:-4] + ".mci"
        os.replace(short, short_mci)
        try:
            assert eng._play_file(short_mci)
        finally:
            os.remove(short_mci)
        took = time.monotonic() - t1
        assert 0.9 <= took < 2.5, f"blocking MCI play took {took:.2f}s"
        t0 = time.monotonic()
        th = threading.Thread(target=eng._play_file, args=(path,))
        th.start()
        time.sleep(0.8)
        assert eng._mci_aliases, "MCI alias not tracked"
        eng.stop()
        th.join(3)
        assert not th.is_alive() and time.monotonic() - t0 < 2.8, (
            "MCI playback not stopped")
        assert not eng._mci_aliases
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_ask_more_sends_question_once_with_context():
    got = []

    class AI:
        output_lang = ""

        async def ask(self, q, h):
            got.append((q, h))
            return "ans"

    descs = [Description(id=1, start_time=5, end_time=8, text="red car"),
             Description(id=2, start_time=50, end_time=55, text="far away")]
    dlg = AskMoreDialog(None, AI(), descriptions=descs, position=6.0)
    dlg.seconds_ctrl.SetValue("10")
    dlg.question_text.SetValue("what colour is the car?")
    dlg._on_submit(None)
    time.sleep(0.5)
    _drain()
    q, h = got[0]
    assert h is None, f"question echoed in history: {h}"
    assert "red car" in q and "far away" not in q, q
    assert q.rstrip().endswith("what colour is the car?"), q
    dlg.question_text.SetValue("and the driver?")
    dlg._on_submit(None)
    time.sleep(0.5)
    _drain()
    q2, h2 = got[1]
    assert [m["role"] for m in h2] == ["user", "assistant"], h2
    assert "and the driver?" not in str(h2)
    dlg.Destroy()
    _drain()


def test_read_description_label_translated():
    import json
    for code, want in (("en", "Read Description"), ("ms", "Baca Penerangan")):
        data = json.loads((SRC / "i18n" / "locales" / f"{code}.json")
                          .read_text(encoding="utf-8"))
        assert data.get("player.read_description") == want, code
        assert "{position}" in data.get("ask.context", ""), code
    text = (SRC / "ui" / "player_window.py").read_text(encoding="utf-8")
    assert '" Read Description"' not in text


def test_added_description_kept_in_time_order():
    store = _Store()
    w = _player(store)
    ed = EditorWindow(w, store, _TTS())
    ed._on_add(None)
    starts = [d.start_time for d in store.current.descriptions]
    assert starts == sorted(starts), starts
    # The new (0 s) entry is selected and shown in the fields.
    assert ed.desc_list.GetFirstSelected() == 0
    assert ed.text_ctrl.GetValue() == ""
    ed.Destroy()
    w.Destroy()
    _drain()


def test_vlc_pause_during_hold_stays_paused():
    calls = []

    class FakeVLC:
        def set_pause(self, v):
            calls.append(("set_pause", v))

        def pause(self):
            calls.append(("pause",))

        def play(self):
            calls.append(("play",))

        def is_playing(self):
            return False

        def stop(self):
            pass

    w = _player()
    w._vlc_available = True
    w._vlc = FakeVLC()
    w._vlc_media = object()
    w._playing = True
    w._pause_for_narration()
    w._do_pause()
    assert ("pause",) not in calls, "toggle pause() used"
    assert w._playing is False
    w._resume_after_narration()
    assert not w._timer.IsRunning()
    w._do_play()
    assert w._timer.IsRunning(), "timer not restarted by Play after a hold"
    w._timer.Stop()
    w._vlc_available = False
    w.Destroy()
    _drain()


def test_voice_list_keeps_default():
    text = (SRC / "ui" / "settings_dialog.py").read_text(encoding="utf-8")
    assert 'SetItems(["Default"] + names)' in text


ok_count = 0
fail_count = 0


def check(name, fn):
    global ok_count, fail_count
    try:
        fn()
        ok_count += 1
        print(f"PASS  {name}")
    except Exception:
        fail_count += 1
        print(f"FAIL  {name}")
        traceback.print_exc()


if __name__ == "__main__":
    check("editor keeps edit when selection moves",
          test_editor_keeps_edit_when_selection_moves)
    check("player close saves open editor", test_player_close_saves_open_editor)
    check("player uses shared settings", test_player_uses_shared_settings)
    check("first cue not narrated before start",
          test_first_cue_not_narrated_before_start)
    check("after last cue the last is current",
          test_after_last_cue_last_is_current)
    check("failed tts leaves no temp file", test_failed_tts_leaves_no_temp_file)
    check("stop ends playback", test_stop_ends_playback)
    check("ask more sends question once with context",
          test_ask_more_sends_question_once_with_context)
    check("read description label translated",
          test_read_description_label_translated)
    check("added description kept in time order",
          test_added_description_kept_in_time_order)
    check("vlc pause during hold stays paused",
          test_vlc_pause_during_hold_stays_paused)
    check("voice list keeps default", test_voice_list_keeps_default)
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
