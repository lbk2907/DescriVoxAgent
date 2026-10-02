"""Regression round 65: owner, 2 Oct 2026.

1. "Scene Explorer says no AI is configured" - it said so whenever there
   were no frames yet; a long video was still loading (2 frames a second
   of the whole film) and the AI was fine. Each case now has its words,
   and a long video loads about 600 frames.
2. "If the agent is there, Ask More and Scene Explorer go away; if there
   is no agent, those two come back." Untested model: all three.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

import wx  # noqa: E402

from omni_describer_custom.core.project_store import Description, ProjectStore  # noqa: E402
from omni_describer_custom.core.settings_store import SettingsStore  # noqa: E402
from omni_describer_custom.core.tools import find_tool  # noqa: E402
from omni_describer_custom.i18n.strings import t  # noqa: E402

results: list[tuple[str, bool]] = []
TMP = Path(tempfile.mkdtemp(prefix="odc_t65_"))


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def pump(n=20):
    for _ in range(n):
        wx.Yield()
        time.sleep(0.01)


def video() -> Path:
    out = TMP / "clip.mp4"
    if not out.exists():
        subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi",
                        "-i", "testsrc=size=160x120:rate=5:duration=12",
                        "-c:v", "libx264", str(out)], check=True, timeout=120)
    return out


def player(provider="glm", passed=True, key=True):
    from omni_describer_custom.core.tts_engine import TTSEngine
    from omni_describer_custom.ui.player_window import PlayerWindow
    settings = SettingsStore()
    settings.set("ai.default_provider", provider)
    settings.set_ai_provider(provider, {"api_key": "k-test" if key else "",
                                        "model": "some/model"})
    settings.set("ai.agent_models", ["some/model"] if passed else [])
    settings.set("player.volume", 100)
    store = ProjectStore()
    store.create_project("Modes", str(video()))
    store.persist_video_file(str(video()))
    store.set_video_duration(12.0)
    store.save_descriptions([Description(start_time=2.0, end_time=4.0,
                                         text="A test pattern.")])
    w = PlayerWindow(None, store, TTSEngine({}), settings=settings)
    return w


def shown(w):
    return (w.agent_btn.IsShown(), w.ask_btn.IsShown(), w.explore_btn.IsShown())


def test_agent_ready_hides_the_two_older_tools():
    w = player()
    try:
        assert shown(w) == (True, False, False), shown(w)
    finally:
        w.Destroy()
        pump()


def test_untested_model_shows_all_three():
    w = player(passed=False)
    opened = []
    w._open_agent_dialog = lambda: opened.append(True)
    try:
        assert shown(w) == (True, True, True), shown(w)
        w._agent_test_done("some/model", {"ok": True})
        assert opened, "the agent did not open after the passing test"
        assert shown(w) == (True, False, False), "a passing test did not hide them"
    finally:
        w.Destroy()
        pump()


def test_no_agent_shows_ask_more_and_explorer():
    for kwargs in ({"provider": "minimax"}, {"key": False}):
        w = player(**kwargs)
        try:
            assert shown(w) == (False, True, True), (kwargs, shown(w))
        finally:
            w.Destroy()
            pump()


def test_settings_change_is_followed():
    w = player()
    try:
        w._settings.set("ai.default_provider", "minimax")
        w._refresh_mode_buttons()
        assert shown(w) == (False, True, True), shown(w)
    finally:
        w.Destroy()
        pump()


def test_explorer_says_why():
    from omni_describer_custom.ui.scene_explorer import SceneExplorer
    said = []
    ex = SceneExplorer(None, object(), "")
    try:
        ex._announce = lambda text: said.append(text)
        ex._loading, ex.frames = True, []
        assert not ex._ready_to_ask() and said[-1] == t("scene.still_loading")
        ex._loading = False
        assert not ex._ready_to_ask() and said[-1] == t("scene.no_frames")
        ex.ai = None
        assert not ex._ready_to_ask() and said[-1] == t("scene.no_ai")
    finally:
        ex._closing = True
        ex.Destroy()
        pump()


def test_a_long_video_loads_about_600_frames():
    from omni_describer_custom.ui import scene_explorer as se
    from omni_describer_custom.core import timeline_io
    real = timeline_io._ffprobe_duration
    try:
        timeline_io._ffprobe_duration = lambda p: 1440.0
        assert abs(se.SceneExplorer._frames_per_second("x.mp4") - 600 / 1440) < 0.01
        timeline_io._ffprobe_duration = lambda p: 120.0
        assert se.SceneExplorer._frames_per_second("x.mp4") == 2.0
    finally:
        timeline_io._ffprobe_duration = real


def _key(code, ctrl=False, shift=False):
    ev = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
    ev.SetKeyCode(code)
    ev.SetControlDown(ctrl)
    ev.SetShiftDown(shift)
    return ev


def test_keys_in_the_video_area():
    """v1.9.7 (owner): Space play/pause, Left/Right 5 s, Ctrl 10 s,
    Up/Down video volume, each said."""
    w = player()
    said, toggles = [], []
    w._announce = lambda text: said.append(text)
    w._on_play_toggle = lambda e: toggles.append(True)
    try:
        assert w.video_panel.GetWindowStyleFlag() & wx.WANTS_CHARS
        w._position = 4.0
        w._on_video_key(_key(wx.WXK_SPACE))
        assert toggles == [True]
        w._on_video_key(_key(wx.WXK_RIGHT))
        assert w._position == 9.0 and said[-1] == t(
            "player.slider_value", position="0:09", total="0:12"), (w._position, said)
        w._on_video_key(_key(wx.WXK_LEFT, ctrl=True))
        assert w._position == 0.0, w._position          # clamped at the start
        w._on_video_key(_key(wx.WXK_RIGHT, ctrl=True))
        w._on_video_key(_key(wx.WXK_RIGHT, ctrl=True))
        assert w._position == 12.0, w._position         # clamped at the end
        assert w.position_slider.GetValue() == 12
        w._slider_dur = 600.0                           # a 10-minute video
        w._position = 100.0
        w._on_video_key(_key(wx.WXK_RIGHT, ctrl=True, shift=True))
        assert w._position == 160.0, w._position        # Ctrl+Shift: one minute
        w._on_video_key(_key(wx.WXK_LEFT, ctrl=True, shift=True))
        assert w._position == 100.0, w._position
        w._on_video_key(_key(wx.WXK_DOWN))
        w._on_video_key(_key(wx.WXK_DOWN))
        assert w._volume == 80 and said[-1] == t("player.volume", pct=80)
        assert w._settings.get("player.volume") == 80
        for _ in range(5):
            w._on_video_key(_key(wx.WXK_UP))
        assert w._volume == 100, w._volume              # never above 100
    finally:
        w.Destroy()
        pump()


def test_video_keys_are_taken_before_navigation():
    """First try bound EVT_KEY_DOWN on the panel: Windows used the arrows
    to move the focus to a button first (owner, 2 Oct 2026). The keys are
    now taken in the window's CHAR_HOOK, and only while the video area
    has the focus."""
    w = player()
    said = []
    w._announce = lambda text: said.append(text)
    try:
        hook = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        hook.SetKeyCode(wx.WXK_DOWN)
        w._video_has_focus = lambda: True
        w._on_char_hook(hook)
        assert w._volume == 90 and said[-1] == t("player.volume", pct=90), said
        w._video_has_focus = lambda: False
        w._on_char_hook(hook)
        assert w._volume == 90, "a key outside the video area changed the volume"
        src = Path("src/omni_describer_custom/ui/player_window.py").read_text(encoding="utf-8")
        assert "self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)" in src
        # a key that reaches the panel itself is handled there too
        down = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
        down.SetKeyCode(wx.WXK_UP)
        w._on_video_key_down(down)
        assert w._volume == 100, w._volume
    finally:
        w.Destroy()
        pump()


def test_quick_keys_restart_the_sound_once():
    """Each volume or seek key restarted ffplay; quick presses stuttered."""
    w = player()
    starts = []
    w._announce = lambda text: None
    w._start_ffplay = lambda pos: starts.append(pos) or True
    try:
        w._audio_backend, w._playing = "ffplay", True
        for _ in range(3):
            w._change_volume(-10)
        w._seek_by(5)
        assert starts == [], starts
        assert w._sound_timer.IsRunning()      # one restart, waiting
        w._sound_timer.Stop()
        w._restart_sound_now()                  # what the timer does
        assert starts == [w._position], starts
        assert w._volume == 70
    finally:
        w._playing = False
        w.Destroy()
        pump()


def test_video_keys_keep_the_focus():
    """Real test 3 Oct 2026: after the first key the focus was on the
    status line (_announce moves it there), so the next arrow went to
    another control. In the video area the words are spoken in place."""
    from omni_describer_custom.core import speech
    w = player()
    spoken = []
    real = speech.get_speech
    speech.get_speech = lambda: type("S", (), {"speak": lambda self, m, interrupt=True:
                                               spoken.append(m) or True})()
    try:
        w._video_has_focus = lambda: True
        moved = []
        w.status_text.SetFocus = lambda: moved.append(True)
        w._change_volume(-10)
        w._seek_by(5)
        assert spoken == [t("player.volume", pct=90), t(
            "player.slider_value", position="0:05", total="0:12")], spoken
        assert not moved, "the focus left the video picture"
        assert w.status_text.GetLabel() == spoken[-1]
    finally:
        speech.get_speech = real
        w.Destroy()
        pump()


def test_ffplay_gets_the_volume():
    src = Path("src/omni_describer_custom/ui/player_window.py").read_text(encoding="utf-8")
    assert '"-volume", str(self._volume)' in src


def main() -> int:
    app = wx.App(False)
    check("agent ready: only the Agent button", test_agent_ready_hides_the_two_older_tools)
    check("untested model: all three, then the agent alone",
          test_untested_model_shows_all_three)
    check("no agent: Ask More and Explore Scene", test_no_agent_shows_ask_more_and_explorer)
    check("a Settings change is followed", test_settings_change_is_followed)
    check("Scene Explorer says why it cannot describe", test_explorer_says_why)
    check("a long video loads about 600 frames", test_a_long_video_loads_about_600_frames)
    check("keys in the video area", test_keys_in_the_video_area)
    check("ffplay gets the volume", test_ffplay_gets_the_volume)
    check("quick keys restart the sound once", test_quick_keys_restart_the_sound_once)
    check("video keys keep the focus", test_video_keys_keep_the_focus)
    check("video keys are taken before navigation",
          test_video_keys_are_taken_before_navigation)
    del app
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
