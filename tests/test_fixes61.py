"""Regression round 61: the agent window can be stopped (v1.9.6).

Found in the v1.9.6 audit (F4, F5, C):
  - Close / Esc on the agent window ended the dialog but left "Check the
    whole video" running in the background, paying for every stretch;
  - "Ask" had no Stop, and closing did not stop it either: the old ask
    went on, and F2 again started a SECOND ask on the same Agent and the
    same conversation;
  - errors were shown raw (JSON, account ids) unless they were a busy
    service or a used-up quota.
Now Close/Esc/Alt+F4 set the stop flag before the window ends, Ask turns
into "Stop asking" while it runs, a second run on the same Agent is
refused, and every error goes through ai_engine.user_error_text.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
import io
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")
os.environ["ODC_CONFIG_DIR"] = tempfile.mkdtemp(prefix="odc_t61_cfg_")
os.environ["ODC_PROJECTS_DIR"] = tempfile.mkdtemp(prefix="odc_t61_prj_")

import wx  # noqa: E402

from omni_describer_custom.core.project_store import (  # noqa: E402
    Description, ProjectStore)
from omni_describer_custom.core.settings_store import SettingsStore  # noqa: E402
from omni_describer_custom.core.tools import find_tool  # noqa: E402
from omni_describer_custom.i18n.strings import t  # noqa: E402
from omni_describer_custom.ui import agent_dialog  # noqa: E402

results: list[tuple[str, bool]] = []
APP = wx.App(False)
TMP = Path(tempfile.mkdtemp(prefix="odc_t61_"))
SPOKEN: list[str] = []
agent_dialog.speak = SPOKEN.append        # silent: nothing reaches NVDA


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


def wait_for(condition, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        pump(2)
    return condition()


def video() -> Path:
    out = TMP / "clip.mp4"
    if not out.exists():
        subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi",
                        "-i", "testsrc=size=320x240:rate=10:duration=30",
                        "-c:v", "libx264", str(out)], check=True, timeout=120)
    return out


def player():
    from omni_describer_custom.core.tts_engine import TTSEngine
    from omni_describer_custom.ui.player_window import PlayerWindow
    settings = SettingsStore()
    settings.set("ai.default_provider", "glm")
    settings.set_ai_provider("glm", {"api_key": "k-test",
                                     "model": "z-ai/glm-5.3-flash"})
    settings.set("ai.agent_models", ["z-ai/glm-5.3-flash"])
    store = ProjectStore()
    store.create_project("Agent stop test", str(video()))
    store.persist_video_file(str(video()))
    store.set_video_duration(30.0)
    store.save_descriptions([
        Description(start_time=2.0, end_time=4.0, text="A test pattern."),
        Description(start_time=10.0, end_time=12.0, text="A red dragon flies."),
    ])
    w = PlayerWindow(None, store, TTSEngine({}), settings=settings)
    w._agent = w._make_agent()
    return w


class SlowPost:
    """A request that hangs; records when it was abandoned."""

    def __init__(self, seconds=30.0):
        self.seconds = seconds
        self.started = self.cancelled = 0

    async def __call__(self, payload):
        self.started += 1
        try:
            await asyncio.sleep(self.seconds)
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        return {"choices": [{"message": {"role": "assistant",
                                         "content": "Late answer."}}]}


def modal(dlg):
    """Pretend the dialog is modal and record EndModal, without a real
    modal loop (no keyboard, no NVDA)."""
    ended = []
    dlg.IsModal = lambda: True
    dlg.EndModal = ended.append
    return ended


def click(button):
    button.GetEventHandler().ProcessEvent(
        wx.CommandEvent(wx.wxEVT_BUTTON, button.GetId()))


def test_close_stops_the_ask():
    w = player()
    slow = SlowPost()
    w._agent._post = slow
    dlg = agent_dialog.AgentDialog(w, w._agent)
    try:
        ended = modal(dlg)
        dlg.submit("Is [1] right?")
        assert wait_for(lambda: slow.started == 1, 5), "the ask never started"
        assert dlg.GetEscapeId() == wx.ID_CLOSE, "Esc does not press Close"
        click(dlg.close_btn)                 # Close, and Esc through it
        assert ended == [wx.ID_CLOSE], ended
        assert wait_for(lambda: slow.cancelled == 1, 2), \
            "the ask kept running after the window closed"
        assert wait_for(lambda: not w._agent.busy, 2)
    finally:
        pump(20)
        dlg.Destroy()
        w.Destroy()
        pump()


def test_close_stops_check_all():
    from omni_describer_custom.ui import dialogs
    w = player()
    slow = SlowPost()
    w._agent._post = slow
    dlg = agent_dialog.AgentDialog(w, w._agent)
    real = dialogs.ask_yes_no
    dialogs.ask_yes_no = lambda *a, **k: True
    try:
        ended = modal(dlg)
        dlg.check_all()
        assert wait_for(lambda: slow.started == 1, 5), "the check never started"
        click(dlg.close_btn)
        assert ended == [wx.ID_CLOSE], ended
        assert wait_for(lambda: slow.cancelled == 1, 2), \
            "Check the whole video kept running after the window closed"
        time.sleep(0.6)
        assert slow.started == 1, f"{slow.started} requests after Close"
    finally:
        dialogs.ask_yes_no = real
        pump(20)
        dlg.Destroy()
        w.Destroy()
        pump()


def test_ask_becomes_stop():
    w = player()
    slow = SlowPost()
    w._agent._post = slow
    dlg = agent_dialog.AgentDialog(w, w._agent)
    try:
        SPOKEN.clear()
        dlg.submit("Is [1] right?")
        assert wait_for(lambda: slow.started == 1, 5)
        assert dlg.ask_btn.GetLabel() == t("agent.ask_stop_btn"), \
            dlg.ask_btn.GetLabel()
        assert dlg.ask_btn.IsEnabled(), "Stop asking cannot be pressed"
        assert not dlg.check_all_btn.IsEnabled()
        click(dlg.ask_btn)
        assert t("agent.stopping") in SPOKEN, SPOKEN
        assert wait_for(lambda: slow.cancelled == 1, 2), "Stop did not stop"
        assert wait_for(lambda: dlg.ask_btn.GetLabel() == t("agent.ask_btn"), 2)
        assert dlg.check_all_btn.IsEnabled()
        log = dlg.log.GetValue()
        assert t("agent.stopped") in log, log
        assert "error" not in log.lower(), log
    finally:
        pump(20)
        dlg.Destroy()
        w.Destroy()
        pump()


def test_second_window_cannot_ask_twice():
    """The old ask still running (closed window, or still stopping): F2
    again must not start a second ask on the same Agent."""
    w = player()
    slow = SlowPost(seconds=1.0)
    w._agent._post = slow
    first = agent_dialog.AgentDialog(w, w._agent)
    second = agent_dialog.AgentDialog(w, w._agent)
    try:
        first.submit("first question")
        assert wait_for(lambda: slow.started == 1, 5)
        SPOKEN.clear()
        second.submit("second question")
        pump(30)
        assert slow.started == 1, f"{slow.started} asks ran at once"
        assert t("agent.still_working") in SPOKEN, SPOKEN
        assert not any(m.get("content") == "second question"
                       for m in w._agent.messages)
        assert wait_for(lambda: not w._agent.busy, 5)
    finally:
        pump(20)
        first.Destroy()
        second.Destroy()
        w.Destroy()
        pump()


def test_errors_are_words():
    from omni_describer_custom.core.ai_engine import user_error_text
    daily = ("Gemini HTTP 429: daily quota used up "
             "(GenerateRequestsPerDayPerProjectPerModel-FreeTier).")
    assert agent_dialog.AgentDialog._error_text(daily) == t("error.ai_daily_quota")
    raw = 'OpenRouter error: {"code": 400, "message": "bad", "user": "user_2abcDEF123"}'
    shown = agent_dialog.AgentDialog._error_text(raw)
    assert shown == user_error_text(raw), shown
    assert "{" not in shown and "user_2abc" not in shown, shown
    w = player()

    async def error_reply(payload):
        return {"error": {"code": 400, "message": "Provider returned error",
                          "metadata": {"raw": '{"x": 1}'}}}
    w._agent._post = error_reply
    dlg = agent_dialog.AgentDialog(w, w._agent)
    try:
        dlg.submit("q")
        assert wait_for(lambda: dlg.ask_btn.GetLabel() == t("agent.ask_btn")
                        and not dlg._busy, 5)
        log = dlg.log.GetValue()
        assert "Provider returned error" in log and "{" not in log, log
    finally:
        pump(20)
        dlg.Destroy()
        w.Destroy()
        pump()


def main() -> int:
    check("Close/Esc stops the ask", test_close_stops_the_ask)
    check("Close/Esc stops Check the whole video", test_close_stops_check_all)
    check("Ask becomes Stop asking while it runs", test_ask_becomes_stop)
    check("a second window cannot ask at the same time",
          test_second_window_cannot_ask_twice)
    check("errors are words, never JSON", test_errors_are_words)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
