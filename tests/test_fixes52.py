"""Regression round 52: the chosen model is used; descriptions can be
checked against the picture (v1.8.8).

1. The model picked in Settings never reached GLM/OpenRouter, Gemini or
   MiniMax: set_provider logged it and dropped it, every call went out
   with model="", and the provider used its FIRST built-in model.
   Choosing "Recommended: Gemini 3.1 Flash-Lite" still ran GLM.
2. Phase 16.3 measured a second look at each description (12 frames,
   20 s either side): wrong descriptions roughly halved on two long
   films. core/review.py; Settings "Check descriptions against the
   video", off by default (owner, 30 Sep 2026).
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
os.environ.setdefault("ODC_CONFIG_DIR", tempfile.mkdtemp(prefix="odc_t52_cfg_"))
os.environ.setdefault("ODC_PROJECTS_DIR", tempfile.mkdtemp(prefix="odc_t52_prj_"))

from omni_describer_custom.core import review  # noqa: E402
from omni_describer_custom.core.ai_engine import AIEngine  # noqa: E402
from omni_describer_custom.core.tools import find_tool  # noqa: E402

results: list[tuple[str, bool]] = []
TMP = Path(tempfile.mkdtemp(prefix="odc_t52_"))


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


# 1 ─────────────────────────────────────────────────────────────────
def test_chosen_model_reaches_every_call():
    e = AIEngine()
    e.set_provider("glm", api_key="k", model="qwen/qwen3.8-omni-flash")
    prov = e.get_provider("glm")
    seen = []

    async def video(path, prompt, model, **kw):
        seen.append(model)
        return []

    async def image(path, prompt, model=""):
        seen.append(model)
        return "x"
    prov.describe_video_full = video
    prov.describe_image = image
    asyncio.run(e.describe_video_full("v.mp4", "p"))
    asyncio.run(e.describe_frame("a.jpg", "p"))
    asyncio.run(e.look("a.jpg", "p"))
    assert seen == ["qwen/qwen3.8-omni-flash"] * 3, seen
    # An explicit model still wins; no choice still means provider default.
    asyncio.run(e.describe_frame("a.jpg", "p", model="other/model"))
    assert seen[-1] == "other/model"
    e.set_provider("gemini", api_key="k")
    assert e._model_for("", "") == ""


# 2 ─────────────────────────────────────────────────────────────────
def test_modes_and_auto():
    assert review.resolve_mode("off", 3) == "off"
    assert review.resolve_mode("auto", 3) == "accurate"
    assert review.resolve_mode("auto", 1) == "keep"
    assert review.resolve_mode("most", 1) == "most"
    assert review.resolve_mode("bogus", 2) == "off"
    assert review.resolve_mode("", 2) == "off"


def test_decisions_match_what_was_measured():
    t = 100.0
    here = {"best": 101.8, "here": True}
    early = {"best": 95.0, "here": True}
    later = {"best": 110.0, "here": False}
    nowhere = {"best": "none", "here": False}
    # accurate (v2): visible in place stays; earlier start moves back;
    # far away moves; nowhere removed.
    assert review.decide("accurate", here, t) == ("keep", t)
    assert review.decide("accurate", early, t) == ("move", 95.0)
    assert review.decide("accurate", later, t) == ("move", 110.0)
    assert review.decide("accurate", nowhere, t) == ("drop", t)
    # a nudge smaller than 1.5 s is not a move
    assert review.decide("accurate", {"best": 99.0, "here": False}, t) == ("keep", t)
    # most (v1): moves to the clearest frame even when visible in place
    assert review.decide("most", {"best": 110.0, "here": True}, t) == ("move", 110.0)
    assert review.decide("most", nowhere, t) == ("drop", t)
    # keep: never removes
    assert review.decide("keep", nowhere, t) == ("keep", t)
    assert review.decide("keep", later, t) == ("move", 110.0)
    # an answer that cannot be read changes nothing
    assert review.decide("accurate", {"best": ""}, t) == ("keep", t)


def test_answers_are_read_onto_real_frame_times():
    times = review.sheet_times(100.0, 1000)
    assert len(times) == review.TILES
    assert all(abs((x / review.STEP) - round(x / review.STEP)) < 1e-9 for x in times)
    assert times[0] <= 100.0 - review.SPAN + review.STEP
    got = review.parse_answer('```json\n{"here": false, "best": "1:50.1", "why": "x"}\n```', times)
    assert got["best"] in times and abs(got["best"] - 110.1) < review.STEP
    assert review.parse_answer('{"best": "none"}', times)["best"] == "none"
    assert review.parse_answer("no idea", times)["best"] == ""
    # near the start the sheet does not go below zero
    assert review.sheet_times(3.0, 1000)[0] == 0.0


# 3 ─────────────────────────────────────────────────────────────────
def _video() -> Path:
    out = TMP / "clip.mp4"
    if not out.exists():
        subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi",
                        "-i", "testsrc=size=320x240:rate=10:duration=60",
                        "-c:v", "libx264", str(out)], check=True, timeout=180)
    return out


class FakeEngine:
    """Answers by the description text; counts calls."""

    def __init__(self, answers, fail=()):
        self.answers, self.fail, self.calls = answers, fail, 0

    async def look(self, image, prompt):
        self.calls += 1
        assert Path(image).exists() and Path(image).stat().st_size > 1000
        for key, answer in self.answers.items():
            if f'"{key}"' in prompt:
                if key in self.fail:
                    raise RuntimeError("HTTP 503")
                return answer
        return '{"here": true, "best": "0:00.0"}'


def test_review_moves_removes_and_never_loses_the_job():
    pairs = [(10.0, "A kept line."), (20.0, "A moved line."),
             (30.0, "An invented line."), (40.0, "A failed check.")]
    engine = FakeEngine({
        "A kept line.": '{"here": true, "best": "0:11.0"}',
        "A moved line.": '{"here": false, "best": "0:36.4"}',
        "An invented line.": '{"here": false, "best": "none"}',
        "A failed check.": "",
    }, fail=("A failed check.",))
    before = set(Path(tempfile.gettempdir()).glob("odc_review_*"))
    kept, summary = asyncio.run(review.review(engine, str(_video()), pairs,
                                              "accurate", 60.0))
    texts = [x for _, x in kept]
    assert "An invented line." not in texts
    assert "A failed check." in texts, "a failed check lost a description"
    moved = dict((x, t) for t, x in kept)["A moved line."]
    assert abs(moved - 36.4) < review.STEP, moved
    assert [t for t, _ in kept] == sorted(t for t, _ in kept)
    assert summary == {"checked": 4, "moved": 1, "removed": 1, "failed": 1,
                       "mode": "accurate"}, summary
    assert engine.calls == 4
    after = set(Path(tempfile.gettempdir()).glob("odc_review_*"))
    assert after <= before, "the frame folder was left behind"


def test_off_does_nothing_and_cancel_stops():
    pairs = [(5.0, "x")]
    kept, summary = asyncio.run(review.review(None, "none.mp4", pairs, "off", 60))
    assert kept == pairs and summary["checked"] == 0
    try:
        asyncio.run(review.review(FakeEngine({}), str(_video()), pairs,
                                  "accurate", 60.0, is_cancelled=lambda: True))
        raise AssertionError("Cancel did not stop the check")
    except RuntimeError as e:
        assert "cancelled" in str(e)


# 4 ─────────────────────────────────────────────────────────────────
def test_setting_is_off_by_default_and_saved():
    from omni_describer_custom.core.settings_store import SettingsStore
    assert SettingsStore.DEFAULTS["general"]["review_mode"] == "off"
    import wx
    app = wx.GetApp() or wx.App(False)
    from omni_describer_custom.ui.settings_dialog import SettingsDialog
    store = SettingsStore()
    dlg = SettingsDialog(None, store)
    real_box = wx.MessageBox
    wx.MessageBox = lambda *a, **k: wx.OK   # native modal (test_fixes11)
    errors = []
    try:
        assert dlg.review_choice.GetSelection() == 0, "not Off for a new user"
        assert dlg.review_choice.GetCount() == 5

        def drive():
            try:
                dlg.review_choice.SetSelection(2)   # Most accurate
                dlg._on_apply(None)                 # ends the modal
            except Exception as e:
                errors.append(e)
                dlg.EndModal(wx.ID_CANCEL)
        wx.CallAfter(drive)
        dlg.ShowModal()
    finally:
        wx.MessageBox = real_box
        dlg.Destroy()
    assert not errors, errors
    assert SettingsStore().get("general.review_mode") == "accurate"
    store.set("general.review_mode", "off")
    del app


def test_pipeline_runs_the_check_only_when_asked():
    import wx
    app = wx.GetApp() or wx.App(False)
    from omni_describer_custom.ui.main_frame import MainFrame
    frame = MainFrame()
    try:
        logged = []
        frame._log = logged.append
        frame.ai_engine = FakeEngine({"B": '{"here": false, "best": "none"}'})
        pairs = [(10.0, "A"), (20.0, "B")]
        loop = asyncio.new_event_loop()
        frame.settings = {"general.review_mode": "off"}
        assert frame._review_pairs(loop, str(_video()), pairs, 60.0, 1) == pairs
        frame.settings = {"general.review_mode": "accurate"}
        got = frame._review_pairs(loop, str(_video()), pairs, 60.0, 1)
        loop.close()
        assert [x for _, x in got] == ["A"], got
        for _ in range(40):
            wx.Yield()
            time.sleep(0.02)
        assert any("1 removed" in m or "1 dibuang" in m for m in logged), logged
    finally:
        frame.Destroy()
        for _ in range(10):
            wx.Yield()
        del app


def test_temp_folders_are_swept():
    from omni_describer_custom.core import housekeeping
    assert "odc_review_" in housekeeping._OUR_PREFIXES


def main() -> int:
    check("the chosen model reaches every call", test_chosen_model_reaches_every_call)
    check("modes and auto", test_modes_and_auto)
    check("decisions match what was measured", test_decisions_match_what_was_measured)
    check("answers are read onto real frame times",
          test_answers_are_read_onto_real_frame_times)
    check("the check moves, removes and never loses the job",
          test_review_moves_removes_and_never_loses_the_job)
    check("off does nothing; Cancel stops", test_off_does_nothing_and_cancel_stops)
    check("the setting is off by default and saved",
          test_setting_is_off_by_default_and_saved)
    check("the pipeline checks only when asked",
          test_pipeline_runs_the_check_only_when_asked)
    check("temp folders are swept", test_temp_folders_are_swept)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
