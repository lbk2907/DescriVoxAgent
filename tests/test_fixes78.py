"""Regression round 78: Left/Right in the player jumped to the start (user
report via the owner, 13 Oct 2026: "dia bermula dari awal video semula",
with a short video; NVDA said the position was 0).

When the video's length is unknown (ffprobe could not measure it, so
project.video_duration stays 0), the player built its timeline for 0.1 s
and _seek_by clamped every jump to that "end": 0:30 + 5 s became 0:00,
and ffplay restarted from the very beginning (no -ss under 0.5 s). The
playback clock itself kept counting, so the jump looked like a restart.

Now a jump is only held at the end when the end is really known, and the
timeline grows with the position when it is not.
"""

import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

if "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import wx  # noqa: E402

from omni_describer_custom.core import timeline_io  # noqa: E402
from omni_describer_custom.core.project_store import Description, ProjectStore  # noqa: E402
from omni_describer_custom.core.settings_store import SettingsStore  # noqa: E402
from omni_describer_custom.core.tools import find_tool  # noqa: E402

results: list[tuple[str, bool]] = []
TMP = Path(tempfile.mkdtemp(prefix="odc_t78_"))
_app = wx.App(False)


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


def clip() -> Path:
    out = TMP / "clip.mp4"
    if not out.exists():
        subprocess.run(
            [
                find_tool("ffmpeg"),
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=160x120:rate=5:duration=12",
                "-c:v",
                "libx264",
                str(out),
            ],
            check=True,
            timeout=120,
        )
    return out


def player(length_known: bool):
    """A player on a 12 s clip; length_known=False is what a video ffprobe
    cannot measure looks like (video_duration 0)."""
    from omni_describer_custom.core.tts_engine import TTSEngine
    from omni_describer_custom.ui.player_window import PlayerWindow

    settings = SettingsStore()
    store = ProjectStore()
    store.create_project("Seek", str(clip()))
    store.persist_video_file(str(clip()))
    if length_known:
        store.set_video_duration(12.0)
    store.save_descriptions([Description(start_time=200.0, end_time=201.0, text="Late cue.")])
    real = timeline_io._ffprobe_duration
    if not length_known:
        timeline_io._ffprobe_duration = lambda path: 0.0  # the length cannot be measured
    try:
        w = PlayerWindow(None, store, TTSEngine({}), settings=settings)
    finally:
        timeline_io._ffprobe_duration = real
    w._announce = lambda text: w._said.append(text)
    w._said = []
    w._start_ffplay = lambda pos: w._starts.append(round(pos, 2)) or True
    w._starts = []
    return w


def close(w):
    w._playing = False
    w.Destroy()
    pump()


def test_unknown_length_right_moves_forward():
    w = player(length_known=False)
    try:
        assert not w.project.video_duration, "the length should be unknown here"
        w._position = 30.0
        w._seek_by(5)
        assert w._position == 35.0, f"Right from 0:30 went to {w._position}, not 0:35"
        assert "0:35" in w._said[-1], w._said
    finally:
        close(w)


def test_unknown_length_left_moves_back():
    w = player(length_known=False)
    try:
        w._position = 30.0
        w._seek_by(-5)
        assert w._position == 25.0, w._position
        w._position = 3.0
        w._seek_by(-5)
        assert w._position == 0.0, w._position  # still held at the start
    finally:
        close(w)


def test_unknown_length_sound_restarts_at_the_new_place():
    w = player(length_known=False)
    try:
        w._audio_backend, w._playing = "ffplay", True
        w._position = 30.0
        w._seek_by(5)
        w._sound_timer.Stop()
        w._restart_sound_now()
        assert w._starts == [35.0], f"ffplay restarted at {w._starts}, not 35 s"
    finally:
        close(w)


def test_unknown_length_timeline_follows_the_position():
    w = player(length_known=False)
    try:
        w._position = 30.0
        w._seek_by(5)
        assert w.position_slider.GetMax() >= 35, w.position_slider.GetMax()
        assert w.position_slider.GetValue() == 35, w.position_slider.GetValue()
    finally:
        close(w)


def test_known_length_still_stops_at_the_end():
    w = player(length_known=True)
    try:
        w._position = 10.0
        w._seek_by(5)
        assert w._position == 12.0, w._position  # a 12 s clip ends at 12 s
        w._seek_by(-5)
        assert w._position == 7.0, w._position
        assert w.position_slider.GetValue() == 7, w.position_slider.GetValue()
    finally:
        close(w)


class _FakeMedia:
    def get_duration(self):
        return -1  # VLC before it has parsed the file


class _FakeVlc:
    def set_hwnd(self, handle):
        pass

    def set_media(self, media):
        pass

    def media_new(self, path):
        return _FakeMedia()


def test_vlc_unparsed_length_keeps_the_measured_one():
    """Review, 13 Oct 2026: VLC was asked for the length right after
    media_new, before it parsed the file: -1 ms overwrote ffprobe's good
    length, and with VLC installed every video looked like an unknown length
    (the likely trigger of the user's report)."""
    w = player(length_known=True)
    try:
        w._vlc_available = True
        w._vlc = w._vlc_instance = _FakeVlc()
        w._attach_vlc_video()
        assert w.project.video_duration == 12.0, w.project.video_duration
    finally:
        w._vlc_available = False
        w._vlc_media = None
        close(w)


def test_ten_second_buttons_stop_at_the_end_and_move_the_timeline():
    w = player(length_known=True)
    try:
        w._position = 8.0
        w._on_forward(None)
        assert w._position == 12.0, w._position  # was 18 s on a 12 s clip
        assert w.position_slider.GetValue() == 12, w.position_slider.GetValue()
        w._on_rewind(None)
        assert w._position == 2.0, w._position
        assert w.position_slider.GetValue() == 2, w.position_slider.GetValue()
    finally:
        close(w)


def test_unknown_length_agent_jump_and_length():
    w = player(length_known=False)
    try:
        w.seek_to(40.0)  # the agent's or Scene Explorer's jump
        assert w._position == 40.0, w._position
        w.seek_to(float("nan"))  # never a crash on a bad value
        assert w._position == 40.0, w._position
        w._settings.set("ai.default_provider", "glm")
        agent = w._make_agent()
        length = agent.ctx.length
        assert length == 0, f"the agent was told the video is {length} s long"
    finally:
        close(w)


def main() -> int:
    check(
        "unknown length: Right moves forward, not to 0:00", test_unknown_length_right_moves_forward
    )
    check("unknown length: Left moves back", test_unknown_length_left_moves_back)
    check(
        "unknown length: sound restarts at the new place",
        test_unknown_length_sound_restarts_at_the_new_place,
    )
    check(
        "unknown length: the timeline follows the position",
        test_unknown_length_timeline_follows_the_position,
    )
    check("known length: a jump still stops at the end", test_known_length_still_stops_at_the_end)
    check(
        "VLC's unparsed length keeps the measured one",
        test_vlc_unparsed_length_keeps_the_measured_one,
    )
    check(
        "10 s buttons stop at the end and move the timeline",
        test_ten_second_buttons_stop_at_the_end_and_move_the_timeline,
    )
    check("unknown length: agent jump and length", test_unknown_length_agent_jump_and_length)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
