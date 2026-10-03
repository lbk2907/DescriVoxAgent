"""Regression round 63: the Player's time, as the owner asked (2 Oct 2026).

"pastikan agent mode betul-betul menghantar masa terkini pada media
player ... betulkan slider mengikut masa yang betul, contoh 1:04 untuk
1 minit 4 saat."

1. Without VLC the position was counted as +0.5 s per timer tick. A wx
   timer fires late whenever the UI is busy, so the position fell behind
   the sound and F2 could give the agent an old time. It now follows the
   real clock.
2. The timeline slider ran 0..1000 (per mille) and NVDA read that bare
   number. It now runs in seconds and is read as "1:04 of 24:30".
3. Every question to the agent carries the player's position at the
   moment it is asked.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
import io
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

import wx  # noqa: E402

from omni_describer_custom.core.project_store import Description, ProjectStore  # noqa: E402
from omni_describer_custom.core.settings_store import SettingsStore  # noqa: E402
from omni_describer_custom.core.tools import find_tool  # noqa: E402
from omni_describer_custom.i18n.strings import t  # noqa: E402

results: list[tuple[str, bool]] = []
TMP = Path(tempfile.mkdtemp(prefix="odc_t63_"))


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
    import time
    for _ in range(n):
        wx.Yield()
        time.sleep(0.01)


def video() -> Path:
    out = TMP / "clip.mp4"
    if not out.exists():
        subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi",
                        "-i", "testsrc=size=160x120:rate=5:duration=20",
                        "-c:v", "libx264", str(out)], check=True, timeout=120)
    return out


def player(duration=1470.0):
    from omni_describer_custom.core.tts_engine import TTSEngine
    from omni_describer_custom.ui.player_window import PlayerWindow
    store = ProjectStore()
    store.create_project("Time test", str(video()))
    store.persist_video_file(str(video()))
    store.set_video_duration(duration)
    store.save_descriptions([Description(start_time=2.0, end_time=4.0,
                                         text="A test pattern.")])
    w = PlayerWindow(None, store, TTSEngine({}), settings=SettingsStore())
    w._vlc_available = False        # the owner's case: ffplay + own clock
    w._audio_backend = "none"
    return w


def test_times_read_as_minutes_and_seconds():
    from omni_describer_custom.ui.player_window import PlayerWindow as P
    assert P._format_time(64) == "1:04"
    assert P._format_time(5) == "0:05"
    assert P._format_time(1470) == "24:30"
    assert P._format_time(3725) == "1:02:05"


def test_position_follows_the_real_clock():
    from omni_describer_custom.ui import player_window as pw
    w = player()
    real = pw.time.monotonic
    now = [1000.0]
    pw.time.monotonic = lambda: now[0]
    try:
        w._position = 60.0
        w._playing = True
        w._start_timer()          # the clock starts at 1000.0
        w._timer.Stop()           # drive the ticks by hand
        now[0] += 2.3             # one LATE tick: 2.3 s really passed
        w._on_timer(None)
        assert abs(w._position - 62.3) < 0.01, \
            f"position {w._position:.2f}; counting ticks would say 60.5"
        now[0] += 0.5
        w._on_timer(None)
        assert abs(w._position - 62.8) < 0.01, w._position
        # Time spent paused is not counted once playing starts again.
        w._playing = False
        now[0] += 30
        w._playing = True
        w._start_timer()
        w._timer.Stop()
        now[0] += 0.5
        w._on_timer(None)
        assert abs(w._position - 63.3) < 0.01, w._position
    finally:
        pw.time.monotonic = real
        w._timer.Stop()
        w.Destroy()
        pump()


def test_the_slider_is_in_seconds_and_spoken_as_time():
    w = player()
    try:
        s = w.position_slider
        assert s.GetMax() == 1470, s.GetMax()
        w._position = 64.0
        w._on_timer(None)
        assert s.GetValue() == 64, s.GetValue()
        acc = s.GetAccessible()
        assert acc is not None, "the slider has no accessible value"
        status, value = acc.GetValue(0)
        assert status == wx.ACC_OK
        assert value == t("player.slider_value", position="1:04", total="24:30"), value
        s.SetValue(90)
        w._on_seek(None)
        assert w._position == 90.0, w._position
        assert s.GetLineSize() == 5 and s.GetPageSize() == 30
    finally:
        w._timer.Stop()
        w.Destroy()
        pump()


def test_every_agent_question_carries_the_position():
    from omni_describer_custom.core import agent as ag
    pos = [64.0]
    ctx = ag.Context(video=str(video()), length=1470.0,
                     descriptions=[(2.0, "A test pattern.")],
                     get_position=lambda: pos[0])
    sent = []

    async def post(payload):
        sent.append([m for m in payload["messages"] if m["role"] == "user"])
        return {"choices": [{"message": {"role": "assistant", "content": "Fine."}}]}
    agent = ag.Agent("k", "m", ctx, post=post)
    asyncio.run(agent.ask("What is happening now?"))
    pos[0] = 125.4
    asyncio.run(agent.ask("And now?"))
    agent.close()
    first = sent[0][-1]["content"]
    second = sent[1][-1]["content"]
    assert "1:04" in first and "64.0 s" in first and "What is happening now?" in first, first
    assert "2:05" in second and "125.4 s" in second, second


def test_an_unknown_length_is_measured():
    """'Play Video with Existing Descriptions' made projects with no
    length, so the slider covered 0.1 s. The Player now measures it."""
    from omni_describer_custom.core.tts_engine import TTSEngine
    from omni_describer_custom.ui.player_window import PlayerWindow
    store = ProjectStore()
    store.create_project("No length", str(video()))
    store.persist_video_file(str(video()))
    store.save_descriptions([Description(start_time=2.0, end_time=4.0,
                                         text="A test pattern.")])
    assert not store.current.video_duration
    w = PlayerWindow(None, store, TTSEngine({}), settings=SettingsStore())
    try:
        assert w.position_slider.GetMax() == 20, w.position_slider.GetMax()
        assert abs(store.current.video_duration - 20.0) < 0.5
    finally:
        w._timer.Stop()
        w.Destroy()
        pump()


def main() -> int:
    app = wx.App(False)
    check("times read as minutes and seconds (1:04)",
          test_times_read_as_minutes_and_seconds)
    check("the position follows the real clock",
          test_position_follows_the_real_clock)
    check("the slider is in seconds and spoken as a time",
          test_the_slider_is_in_seconds_and_spoken_as_time)
    check("every agent question carries the position",
          test_every_agent_question_carries_the_position)
    check("an unknown video length is measured",
          test_an_unknown_length_is_measured)
    del app
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
