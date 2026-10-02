"""Regression round 54: the Player agent's window and changes (v1.9.0).

Phase D of the agent plan (memory agent-coeditor-design):
  - F2 in the Player opens the agent; a model that has not passed
    Settings > Test agent mode gets Ask More instead (owner's rule);
  - the video pauses while the agent is open and resumes afterwards;
  - proposals: Accept all / Review one by one / Reject all (Esc);
  - accepted changes are saved to the project and its SRT, the SRT is
    copied aside before the first change, Undo restores the last batch,
    and a subtitle file loaded from elsewhere is never written;
  - Test agent mode records which models passed;
  - Ask More sends the frame at the player's position.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import os
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
os.environ["ODC_CONFIG_DIR"] = tempfile.mkdtemp(prefix="odc_t54_cfg_")
os.environ["ODC_PROJECTS_DIR"] = tempfile.mkdtemp(prefix="odc_t54_prj_")

import wx  # noqa: E402

from omni_describer_custom.core.agent import Proposal  # noqa: E402
from omni_describer_custom.core.project_store import (  # noqa: E402
    Description, ProjectStore)
from omni_describer_custom.core.settings_store import SettingsStore  # noqa: E402
from omni_describer_custom.core.tools import find_tool  # noqa: E402

results: list[tuple[str, bool]] = []
APP = wx.App(False)
TMP = Path(tempfile.mkdtemp(prefix="odc_t54_"))


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
                        "-i", "testsrc=size=320x240:rate=10:duration=30",
                        "-c:v", "libx264", str(out)], check=True, timeout=120)
    return out


def player(model_passed=True, provider="glm"):
    from omni_describer_custom.core.tts_engine import TTSEngine
    from omni_describer_custom.ui.player_window import PlayerWindow
    settings = SettingsStore()
    settings.set("ai.default_provider", provider)
    settings.set_ai_provider("glm", {"api_key": "k-test",
                                     "model": "z-ai/glm-5.3-flash"})
    settings.set("ai.agent_models", ["z-ai/glm-5.3-flash"] if model_passed else [])
    store = ProjectStore()
    proj = store.create_project("Agent test", str(video()))
    store.persist_video_file(str(video()))
    store.set_video_duration(30.0)
    store.save_descriptions([
        Description(start_time=2.0, end_time=4.0, text="A test pattern."),
        Description(start_time=10.0, end_time=12.0, text="A red dragon flies."),
        Description(start_time=20.0, end_time=22.0, text="Colour bars."),
    ])
    w = PlayerWindow(None, store, TTSEngine({}), settings=settings)
    return w, store, proj


def test_f2_and_the_fallback():
    """Declining the offered test still gives Ask More."""
    from omni_describer_custom.ui import dialogs
    w, _s, _p = player(model_passed=False)
    real = dialogs.ask_yes_no
    asked = []
    dialogs.ask_yes_no = lambda *a, **k: asked.append(a[1]) or False
    try:
        opened = []
        w._on_ask = lambda e: opened.append("ask")
        ev = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        ev.SetKeyCode(wx.WXK_F2)
        w._on_char_hook(ev)
        assert asked, "an untested model was not offered the test"
        assert opened == ["ask"], "an untested model did not get Ask More"
        assert w.agent_available() == (False, "untested")
    finally:
        dialogs.ask_yes_no = real
        w.Destroy()
        pump()


def test_f2_offers_the_test_and_opens_the_agent():
    """v1.9.6, owner: "agentic mode tidak work" — after changing model, F2
    only said "not available". It now offers Test agent mode on the spot,
    and a pass opens the agent."""
    from omni_describer_custom.core import agent as ag
    from omni_describer_custom.ui import dialogs
    w, _s, _p = player(model_passed=False)
    real_ask, real_probe = dialogs.ask_yes_no, ag.probe
    dialogs.ask_yes_no = lambda *a, **k: True

    async def passing(key, model, post=None, provider="glm"):
        return {"ok": True, "error": ""}
    ag.probe = passing
    try:
        opened = []
        w._open_agent_dialog = lambda: opened.append("agent")
        w._on_ask = lambda e: opened.append("ask")
        w.open_agent()
        for _ in range(100):
            pump(2)
            if opened:
                break
            time.sleep(0.05)
        assert opened == ["agent"], opened
        assert "z-ai/glm-5.3-flash" in w._settings.get("ai.agent_models", [])
    finally:
        dialogs.ask_yes_no, ag.probe = real_ask, real_probe
        w.Destroy()
        pump()


def test_agent_opens_and_video_resumes():
    w, _s, _p = player()
    try:
        assert w.agent_available() == (True, ""), w.agent_available()
        calls = []
        w._do_pause = lambda: calls.append("pause")
        w._do_play = lambda: calls.append("play")
        w._playing = True
        from omni_describer_custom.ui import agent_dialog
        real = agent_dialog.AgentDialog.ShowModal
        agent_dialog.AgentDialog.ShowModal = lambda self: wx.ID_CLOSE
        try:
            w.open_agent()
        finally:
            agent_dialog.AgentDialog.ShowModal = real
        assert calls == ["pause", "play"], calls
        assert w._agent is not None and w._agent.model == "z-ai/glm-5.3-flash"
        assert w._agent.ctx.length == 30.0
        assert [x for _, x in w._agent.ctx.descriptions][1] == "A red dragon flies."
    finally:
        w.Close()
        pump()


def test_changes_are_saved_backed_up_and_undone():
    w, store, proj = player()
    try:
        srt = w._project_srt_path()
        srt.parent.mkdir(parents=True, exist_ok=True)
        srt.write_text("1\n00:00:02,000 --> 00:00:04,000\nold\n", encoding="utf-8")
        external = TMP / "someone_elses.srt"
        external.write_text("1\n00:00:01,000 --> 00:00:02,000\nkeep me\n",
                            encoding="utf-8")
        before_external = external.read_bytes()
        applied = w.apply_agent_changes([
            Proposal("edit", "wrong", index=0, text="Colour bars and a clock."),
            Proposal("move", "later", index=1, time=15.0),
            Proposal("remove", "not there", index=2),
            Proposal("add", "missed", time=25.0, text="The picture freezes."),
        ])
        assert applied == 4, applied
        texts = [(round(d.start_time, 1), d.text) for d in proj.descriptions]
        assert texts == [(2.0, "Colour bars and a clock."),
                         (15.0, "A red dragon flies."),
                         (25.0, "The picture freezes.")], texts
        reopened = ProjectStore().open_project(proj.id)
        assert [d.text for d in reopened.descriptions][-1] == "The picture freezes."
        assert "Colour bars and a clock." in srt.read_text(encoding="utf-8")
        backups = list(srt.parent.glob("descriptions.before-agent-*.srt"))
        assert len(backups) == 1 and "old" in backups[0].read_text(encoding="utf-8")
        w.apply_agent_changes([Proposal("edit", "x", index=0, text="Bars.")])
        assert len(list(srt.parent.glob("descriptions.before-agent-*.srt"))) == 1, \
            "a second backup was made in the same session"
        assert w.undo_agent_changes()
        assert proj.descriptions[0].text == "Colour bars and a clock."
        assert w.undo_agent_changes()
        assert [d.text for d in proj.descriptions] == [
            "A test pattern.", "A red dragon flies.", "Colour bars."]
        assert not w.undo_agent_changes()
        assert external.read_bytes() == before_external
    finally:
        w.Destroy()
        pump()


def test_accept_review_reject():
    from omni_describer_custom.ui import agent_dialog
    w, _s, proj = player()
    w._agent = w._make_agent()
    dlg = agent_dialog.AgentDialog(w, w._agent)
    answers = []

    class FakeBox:
        def __init__(self, *a, **k):
            pass

        def SetYesNoCancelLabels(self, *a):
            pass

        def ShowModal(self):
            return answers.pop(0)

        def Destroy(self):
            pass
    real = wx.MessageDialog
    wx.MessageDialog = FakeBox
    try:
        props = [Proposal("edit", "a", index=0, text="One."),
                 Proposal("edit", "b", index=1, text="Two.")]
        answers[:] = [wx.ID_CANCEL]                       # Reject all / Esc
        assert dlg.decide(props) == 0
        answers[:] = [wx.ID_NO, wx.ID_NO, wx.ID_YES]      # review: skip, accept
        assert dlg.decide(props) == 1
        assert [d.text for d in proj.descriptions][:2] == ["A test pattern.", "Two."]
        answers[:] = [wx.ID_YES]                          # accept all
        assert dlg.decide(props) == 2
        assert [d.text for d in proj.descriptions][:2] == ["One.", "Two."]
        answers[:] = [wx.ID_NO, wx.ID_CANCEL]             # review: stop at once
        assert dlg.decide(props) == 0
    finally:
        wx.MessageDialog = real
        dlg.Destroy()
        w.Close()
        pump()


def test_test_agent_mode_is_recorded():
    from omni_describer_custom.ui.settings_dialog import SettingsDialog
    store = SettingsStore()
    dlg = SettingsDialog(None, store)
    try:
        dlg._test_agent_done("m/one", {"ok": True})
        assert "m/one" in store.get("ai.agent_models")
        dlg._test_agent_done("m/one", {"ok": False, "error": ""})
        assert "m/one" not in store.get("ai.agent_models")
        assert dlg.test_agent_btn.GetLabel().replace("&", "")
    finally:
        dlg.Destroy()
        pump()


def test_ask_more_sends_the_frame():
    from omni_describer_custom.ui.ask_more_dialog import AskMoreDialog
    seen = {}

    class Engine:
        output_lang = ""

        async def ask_about_scene(self, image, question):
            seen["image"], seen["q"] = image, question
            return "A clock."

        async def ask(self, q, history=None):
            seen["text_only"] = True
            return "?"
    dlg = AskMoreDialog(None, Engine(), descriptions=[], position=5.0,
                        video_path=str(video()))
    try:
        dlg.question_text.SetValue("What is shown?")
        dlg._on_submit(None)
        deadline = time.monotonic() + 30
        while "image" not in seen and time.monotonic() < deadline:
            pump(5)
        assert "image" in seen and "text_only" not in seen, seen
        assert Path(seen["image"]).stat().st_size > 1000
        assert "What is shown?" in seen["q"]
    finally:
        pump(20)
        dlg.Destroy()


def test_transcript_works_inside_the_agents_loop():
    """Heard in the first NVDA run: the agent calls the transcript from
    inside its running event loop, and a second run_until_complete there
    failed, so the agent never had the dialogue."""
    import asyncio
    from types import SimpleNamespace
    from omni_describer_custom.core import video_processor
    w, store, proj = player()
    real = video_processor.VideoProcessor.get_transcript

    async def fake(self, source, local_path="", **kw):
        await asyncio.sleep(0)
        return [SimpleNamespace(start=1.0, end=2.0, text="Hello.")]
    video_processor.VideoProcessor.get_transcript = fake
    try:
        folder = store.project_dir(proj.id)

        async def inside_agent_loop():
            return w._transcript_for_agent(folder)
        segs = asyncio.run(inside_agent_loop())
        assert [s.text for s in segs] == ["Hello."], segs
        assert (folder / "media" / "transcript.json").exists(), "not cached"
    finally:
        video_processor.VideoProcessor.get_transcript = real
        w.Destroy()
        pump()


def test_gemini_agent():
    """v1.9.2: the agent opens for Gemini with the user's own key."""
    w, _s, _p = player(provider="gemini")
    try:
        w._settings.set_ai_provider("gemini", {"api_key": "g-test",
                                               "model": "gemini-3.1-flash-lite"})
        assert w.agent_available() == (False, "untested")
        w._settings.set("ai.agent_models", ["gemini-3.1-flash-lite"])
        assert w.agent_available() == (True, ""), w.agent_available()
        agent = w._make_agent()
        assert agent.provider == "gemini" and agent.api_key == "g-test"
        assert agent.model == "gemini-3.1-flash-lite"
        agent.close()
        w._settings.set("ai.default_provider", "minimax")
        assert w.agent_available() == (False, "provider")
    finally:
        w.Destroy()
        pump()


def main() -> int:
    check("F2 and the Ask More fallback", test_f2_and_the_fallback)
    check("F2 offers Test agent mode and opens the agent",
          test_f2_offers_the_test_and_opens_the_agent)
    check("the agent works with Gemini direct", test_gemini_agent)
    check("the agent opens; the video pauses and resumes",
          test_agent_opens_and_video_resumes)
    check("changes are saved, backed up and undone",
          test_changes_are_saved_backed_up_and_undone)
    check("Accept all / Review one by one / Reject all", test_accept_review_reject)
    check("Test agent mode is recorded", test_test_agent_mode_is_recorded)
    check("Ask More sends the frame", test_ask_more_sends_the_frame)
    check("the transcript works inside the agent's loop",
          test_transcript_works_inside_the_agents_loop)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
