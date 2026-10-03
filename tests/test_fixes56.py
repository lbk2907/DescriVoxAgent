"""Regression round 56: Settings > AI, three reports from the owner (v1.9.2).

1. Custom provider: Tab reached an edit NVDA read with no name. The
   custom model box was created right after the Test agent mode button,
   and NVDA names a text box after the static text created just before
   it. It now has its own "Model name:" label. The base URL box also
   had SetLabel on a TextCtrl (pitfall 12).
2. Test Connection is gone: it only asked for "OK"; Test this model and
   Test agent mode do a real check.
3. "Full-video mode (GLM, Gemini or MiniMax)" named provider ids the
   Provider list does not show (GLM is shown as OpenRouter) and did not
   say what unticking means.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import os
import sys
import tempfile
import traceback

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")
os.environ.setdefault("ODC_CONFIG_DIR", tempfile.mkdtemp(prefix="odc_t56_"))

import wx  # noqa: E402

results: list[tuple[str, bool]] = []


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def _dialog():
    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(None, SettingsStore())
    dlg.Show()
    for _ in range(10):
        wx.Yield()
    return dlg


def test_custom_boxes_follow_a_visible_label():
    dlg = _dialog()
    try:
        dlg.select_provider("custom")
        for _ in range(5):
            wx.Yield()
        for box in (dlg.custom_model_text, dlg.base_url_text):
            assert box.IsShown(), box.GetName()
            kids = list(box.GetParent().GetChildren())
            before = kids[kids.index(box) - 1]
            assert isinstance(before, wx.StaticText), \
                f"{box.GetName()} follows {type(before).__name__}; NVDA reads it unnamed"
            assert before.IsShown() and before.GetLabel().strip(), \
                f"{box.GetName()}: its label is hidden or empty"
        for btn in (dlg.fetch_models_btn, dlg.test_agent_btn):
            assert not btn.IsEnabled(), \
                f"{btn.GetLabel()} is live for Custom but does nothing"
        assert dlg.probe_model_btn.IsEnabled(), \
            "Test this model works for Custom since 1.9.2"
        assert dlg.base_url_text.GetValue() != dlg.base_url_text.GetParent() \
            .FindWindowByName("base_url_label").GetLabel(), \
            "the base URL label was written into the box (pitfall 12)"
        dlg.select_provider("glm")
        for _ in range(5):
            wx.Yield()
        assert not dlg.custom_model_label.IsShown(), \
            "the custom model label stays on screen for other providers"
    finally:
        dlg.Destroy()


def test_no_test_connection_button():
    dlg = _dialog()
    try:
        assert not hasattr(dlg, "test_btn")
        assert dlg.FindWindowByName("test_connection") is None
        # The result line is still there for the other test buttons.
        assert dlg.test_result is not None
    finally:
        dlg.Destroy()


def test_video_box_says_what_it_does():
    from omni_describer_custom.i18n.strings import I18n
    for lang in ("en", "ms"):
        I18n.set_language(lang)
        from omni_describer_custom.i18n.strings import t
        label = t("settings.video_mode")
        assert "GLM" not in label and "MiniMax" not in label, (lang, label)
        hint = t("settings.video_mode_hint")
        assert "OpenRouter" in hint, (lang, hint)
    I18n.set_language("en")


class _FakeEngine:
    """Stands in for AIEngine: answers like a model that sees."""

    def __init__(self, video: bool, answer: str):
        self.video, self.answer, self.calls = video, answer, []

    def watches_video(self, provider=""):
        return self.video

    async def ask_about_video(self, path, question, provider="", model=""):
        self.calls.append(("video", os.path.exists(path), provider, model))
        return self.answer

    async def look(self, path, question, provider="", model=""):
        from PIL import Image
        colour = Image.open(path).convert("RGB").getpixel((10, 10))
        self.calls.append(("picture", colour, provider, model))
        return self.answer


def test_probe_every_provider():
    from omni_describer_custom.core.model_catalog import probe_engine
    eng = _FakeEngine(True, "COLOURS: red, then blue\nWORD: pineapple")
    r = probe_engine(eng, "gemini", "gemini-x")
    assert r["sees"] and not r["error"] and not r.get("picture"), r
    assert eng.calls[0][0] == "video" and eng.calls[0][1], eng.calls
    assert eng.calls[0][2:] == ("gemini", "gemini-x"), eng.calls

    eng = _FakeEngine(False, "Red.")
    r = probe_engine(eng, "custom", "my-model")
    assert r["sees"] and r["picture"] and r["hears"] is None, r
    red = eng.calls[0][1]
    assert red[0] > 200 and red[2] < 60, f"the frame sent is not the red one: {red}"

    r = probe_engine(_FakeEngine(False, "Green"), "custom", "m")
    assert not r["sees"] and not r["error"], r

    class Broken(_FakeEngine):
        async def look(self, *a, **k):
            raise RuntimeError("HTTP 401: bad key")
    r = probe_engine(Broken(False, ""), "openai", "m")
    assert "401" in r["error"] and not r["sees"], r


def test_probe_handler_reports_missing_fields():
    from omni_describer_custom.i18n.strings import t
    dlg = _dialog()
    try:
        dlg.select_provider("custom")
        dlg.custom_model_text.SetValue("")
        dlg._on_probe_model(None)
        assert dlg.test_result.GetLabel() == t("settings.probe_needs_model")
        dlg.custom_model_text.SetValue("m")
        dlg.base_url_text.SetValue("")
        dlg._on_probe_model(None)
        assert dlg.test_result.GetLabel() == t("settings.probe_needs_url")
        dlg.base_url_text.SetValue("http://127.0.0.1:9/v1")
        dlg.api_key_text.SetValue("")
        dlg._on_probe_model(None)
        assert dlg.test_result.GetLabel() == t("settings.probe_needs_key")
        assert dlg.probe_model_btn.IsEnabled()
    finally:
        dlg.Destroy()


def main() -> int:
    app = wx.App(False)
    check("custom provider boxes each follow a visible label",
          test_custom_boxes_follow_a_visible_label)
    check("Test Connection is gone", test_no_test_connection_button)
    check("the whole-video box says what it does",
          test_video_box_says_what_it_does)
    check("Test this model works for every provider",
          test_probe_every_provider)
    check("Test this model says what is missing",
          test_probe_handler_reports_missing_fields)
    del app
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
