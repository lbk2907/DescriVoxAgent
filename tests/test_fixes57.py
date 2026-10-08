"""Regression round 57: Fetch models for Gemini (v1.9.3).

The Gemini model list was written into the app, so a new Gemini model
needed an app update. Fetch models now asks Google (ListModels, with
the user's own key) and keeps the models that can describe a video.
Google listed 61 models for one key on 1 Oct 2026; 12 qualify. The
fixture below mixes them with every kind that must be left out.
"""

import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import json
import os
import sys
import tempfile
import traceback

if "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
if "pytest" not in sys.modules:
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
sys.path.insert(0, "src")
os.environ.setdefault("ODC_CONFIG_DIR", tempfile.mkdtemp(prefix="odc_t57_"))

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


GEN = ["generateContent", "countTokens"]


def model(name, limit=1048576, methods=GEN, display=""):
    return {
        "name": f"models/{name}",
        "displayName": display or name,
        "inputTokenLimit": limit,
        "supportedGenerationMethods": methods,
    }


LISTING = {
    "models": [
        model("gemini-2.5-flash", display="Gemini 2.5 Flash"),
        model("gemini-3.8-flash", display="Gemini 3.8 Flash"),
        model("gemini-3.1-flash-lite", display="Gemini 3.1 Flash Lite"),
        model("gemini-3.1-pro-preview", display="Gemini 3.1 Pro Preview"),
        model("gemini-3.10-flash", display="Gemini 3.10 Flash"),
        # left out:
        model("gemini-2.5-flash-preview-tts", limit=8192),
        model("gemini-3.8-flash-tts", limit=8192),
        model("gemini-3.1-flash-image", limit=65536),
        model("gemini-omni-1.1-flash", limit=131072),
        model("gemini-flash-latest"),
        model("gemini-3.1-pro-preview-customtools"),
        model("gemini-3.8-live", methods=["bidiGenerateContent"]),
        model("gemini-embedding-2", limit=8192, methods=["embedContent"]),
        model("gemini-robotics-er-2-preview"),
        model("gemma-4-31b-it", limit=262144),
        model("lyria-3.5"),
        model("veo-3.1-generate-preview", limit=480, methods=["predictLongRunning"]),
    ]
}


def test_only_video_models_are_kept_in_order():
    from omni_describer_custom.core.model_catalog import parse_gemini_models

    ids = [r["id"] for r in parse_gemini_models(LISTING)]
    assert ids == [
        "gemini-3.1-flash-lite",  # recommended first
        "gemini-3.10-flash",  # then newest (3.10 > 3.8)
        "gemini-3.8-flash",
        "gemini-2.5-flash",
        "gemini-3.1-pro-preview",
    ], ids  # previews last


def test_price_comes_from_the_openrouter_catalog():
    from omni_describer_custom.core import model_catalog as mc

    real = mc.load_cache
    mc.load_cache = lambda name=mc.CACHE_NAME: (
        [{"id": "google/gemini-3.8-flash", "price_in": 0.75}],
        "",
    )
    try:
        rows = {r["id"]: r for r in mc.parse_gemini_models(LISTING)}
    finally:
        mc.load_cache = real
    assert rows["gemini-3.8-flash"]["price_in"] == 0.75
    assert "price_in" not in rows["gemini-2.5-flash"]


def test_key_goes_in_a_header_not_the_url():
    from omni_describer_custom.core import model_catalog as mc
    import urllib.request

    seen = {}

    class Response(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(request, timeout=0):
        seen["url"] = request.full_url
        seen["key"] = request.get_header("X-goog-api-key")
        return Response(json.dumps(LISTING).encode())

    real = urllib.request.urlopen
    urllib.request.urlopen = fake_urlopen
    try:
        rows = mc.fetch_gemini_models("secret-key")
    finally:
        urllib.request.urlopen = real
    assert len(rows) == 5
    assert seen["key"] == "secret-key"
    assert "secret-key" not in seen["url"], "the key is in the URL (pitfall 51)"


def test_settings_offers_and_remembers_the_list():
    from omni_describer_custom.core import model_catalog as mc
    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.ui.settings_dialog import SettingsDialog

    mc.save_cache(mc.parse_gemini_models(LISTING), mc.GEMINI_CACHE_NAME)
    dlg = SettingsDialog(None, SettingsStore())
    try:
        dlg.select_provider("gemini")
        assert dlg.fetch_models_btn.IsEnabled(), "Fetch models is off for Gemini"
        assert dlg.video_only_hint.IsShown()
        items = dlg.model_choice.GetItems()
        assert "gemini-3.10-flash" in dlg._model_catalog, "the fetched list is not used next time"
        from omni_describer_custom.i18n.strings import t

        assert items[0] == t("settings.model_recommended", label="Gemini 3.1 Flash Lite"), items[0]
        # No key: says so instead of calling Google.
        dlg.api_key_text.SetValue("")
        dlg._on_fetch_models(None)
        assert dlg.test_result.GetLabel() == t("settings.probe_needs_key")
        # Other providers that cannot fetch keep the button off.
        dlg.select_provider("minimax")
        assert not dlg.fetch_models_btn.IsEnabled()
    finally:
        dlg.Destroy()


def main() -> int:
    app = wx.App(False)
    check(
        "only Gemini models that take a video are kept, in order",
        test_only_video_models_are_kept_in_order,
    )
    check(
        "the price comes from the OpenRouter catalog", test_price_comes_from_the_openrouter_catalog
    )
    check("the key goes in a header, not the URL", test_key_goes_in_a_header_not_the_url)
    check(
        "Settings offers Fetch models for Gemini and remembers the list",
        test_settings_offers_and_remembers_the_list,
    )
    del app
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
