"""Regression round 44: a model list you can trust, and models that hear (v1.8.1).

Found 28 Sep 2026 by sending each listed model a 6-second clip the way
the app sends video:
  - 13 ":batch" variants: HTTP 404 on chat/completions, always;
  - routers ("openrouter/auto") answered with another model (GLM);
  - amazon/nova-2-lite-v1 said "black, white" for red then blue;
  - the list was alphabetical ids, forgot itself when Settings closed,
    and never said which models also HEAR the soundtrack.
And the app treated all of OpenRouter as deaf because GLM is, so it
stripped audio from compressed uploads even for Qwen3.8-Omni-Flash,
which heard the probe word.

No network here: the catalog is a fixture, the probe's HTTP is a local
server, and the audio check reads the real ffmpeg output with ffprobe.
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")
os.environ["ODC_CONFIG_DIR"] = tempfile.mkdtemp(prefix="odc_t44_cfg_")
os.environ.setdefault("ODC_PROJECTS_DIR", tempfile.mkdtemp(prefix="odc_t44_prj_"))

from omni_describer_custom.core import model_catalog as mc  # noqa: E402
from omni_describer_custom.core.tools import find_tool  # noqa: E402

results: list[tuple[str, bool]] = []

CATALOG = {"data": [
    {"id": "qwen/qwen3.8-omni-flash", "name": "Qwen: Qwen3.8 Omni Flash",
     "architecture": {"input_modalities": ["text", "image", "audio", "video"]},
     "pricing": {"prompt": "0.00000015", "completion": "0.00000047"}},
    {"id": "google/gemini-3.8-flash", "name": "Google: Gemini 3.8 Flash",
     "architecture": {"input_modalities": ["text", "audio", "video"]},
     "pricing": {"prompt": "0.00000075", "completion": "0.00000375"}},
    {"id": "bytedance-seed/seed-2.0-mini", "name": "Seed 2.0 Mini",
     "architecture": {"input_modalities": ["text", "image", "video"]},
     "pricing": {"prompt": "0.00000005", "completion": "0.0000002"}},
    {"id": "z-ai/glm-5.3-flash:batch", "name": "GLM batch",
     "architecture": {"input_modalities": ["text", "video"]},
     "pricing": {"prompt": "0.0000001", "completion": "0.0000001"}},
    {"id": "openrouter/auto", "name": "Auto",
     "architecture": {"input_modalities": ["text", "audio", "video"]},
     "pricing": {"prompt": "-1", "completion": "-1"}},
    {"id": "~google/gemini-flash-latest", "name": "latest",
     "architecture": {"input_modalities": ["text", "audio", "video"]},
     "pricing": {"prompt": "0.00000075", "completion": "0.00000375"}},
    {"id": "text/only", "architecture": {"input_modalities": ["text"]},
     "pricing": {"prompt": "0", "completion": "0"}},
]}


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def test_list_drops_what_never_works_and_sorts_hearing_first():
    rows = mc.parse_catalog(CATALOG)
    ids = [r["id"] for r in rows]
    assert ids == ["qwen/qwen3.8-omni-flash", "google/gemini-3.8-flash",
                   "bytedance-seed/seed-2.0-mini"], ids
    assert rows[0]["audio"] and rows[0]["price_in"] == 0.15


def test_list_is_kept_between_visits():
    rows = mc.parse_catalog(CATALOG)
    mc.save_cache(rows)
    kept, fetched = mc.load_cache()
    assert [r["id"] for r in kept] == [r["id"] for r in rows] and fetched


def test_hearing_is_per_model_and_a_test_beats_the_catalog():
    from omni_describer_custom.core.ai_engine import provider_hears_audio
    mc.save_cache(mc.parse_catalog(CATALOG))
    assert provider_hears_audio("glm", "qwen/qwen3.8-omni-flash")
    assert not provider_hears_audio("glm", "z-ai/glm-5.3-flash")
    assert not provider_hears_audio("glm")
    assert provider_hears_audio("gemini")
    # Listed without audio, but it heard the probe word (28 Sep 2026).
    assert not provider_hears_audio("glm", "bytedance-seed/seed-2.0-mini")
    mc.record_probe("bytedance-seed/seed-2.0-mini",
                    {"sees": True, "hears": True, "error": ""})
    assert provider_hears_audio("glm", "bytedance-seed/seed-2.0-mini")
    mc.record_probe("qwen/qwen3.8-omni-flash",
                    {"sees": False, "hears": None, "error": "HTTP 429"})
    assert provider_hears_audio("glm", "qwen/qwen3.8-omni-flash"), \
        "a failed (busy) test must not overwrite what is known"


def test_probe_judges_seeing_and_hearing():
    assert mc.judge("COLOURS: red, blue\nWORD: pineapple", True) == \
        {"sees": True, "hears": True}
    assert mc.judge("COLOURS: black, white\nWORD: NONE", True) == \
        {"sees": False, "hears": False}
    assert mc.judge("COLOURS: blue, red\nWORD: pineapple", True)["sees"] is False
    assert mc.judge("COLOURS: red then blue\nWORD: NONE", False)["hears"] is None


def test_probe_sends_a_real_clip_and_reports_errors():
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen["body"] = body
            parts = body["messages"][0]["content"]
            if body["model"] == "broken:batch":
                reply, code = {"error": {"message": "cannot be used with chat"}}, 404
            else:
                reply, code = {"choices": [{"message": {
                    "content": "COLOURS: red, blue\nWORD: pineapple"}}]}, 200
            seen["video"] = parts[0]["video_url"]["url"]
            data = json.dumps(reply).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/chat"
    try:
        ok = mc.probe_model("k", "qwen/qwen3.8-omni-flash", url=url)
        assert ok["sees"] and ok["error"] == "", ok
        assert seen["video"].startswith("data:video/mp4;base64,"), \
            "the clip must travel the way the app sends video"
        assert len(seen["video"]) > 2000, "the clip was empty"
        bad = mc.probe_model("k", "broken:batch", url=url)
        assert bad["error"].startswith("HTTP 404") and not bad["sees"], bad
    finally:
        server.shutdown()
    leftovers = [p for p in Path(tempfile.gettempdir()).glob("odc_probe_*")
                 if p.is_dir()]
    assert not leftovers, f"probe folders left behind: {leftovers[:2]}"


def _has_audio(path: Path) -> bool:
    out = subprocess.run([find_tool("ffprobe"), "-v", "error",
                          "-select_streams", "a", "-show_entries",
                          "stream=codec_type", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, timeout=60)
    return "audio" in out.stdout


def test_compressed_upload_keeps_sound_only_for_a_model_that_hears():
    from omni_describer_custom.core.ai_engine import GLMProvider
    work = Path(tempfile.mkdtemp(prefix="odc_t44_v_"))
    src = work / "clip.mp4"
    subprocess.run([find_tool("ffmpeg"), "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=640x480:rate=25:duration=4",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                    "-shortest", "-c:v", "libx264", "-c:a", "aac", str(src)],
                   check=True, timeout=120)
    prov = GLMProvider(api_key="k")
    prov._keep_audio = True
    heard = prov.compress_video_for_upload(src, 300_000, cache_dir=str(work))
    assert _has_audio(heard), "a model that hears was sent a silent video"
    prov._keep_audio = False
    deaf = prov.compress_video_for_upload(src, 300_000, cache_dir=str(work))
    assert not _has_audio(deaf), "the deaf path should still drop audio"
    assert heard.name != deaf.name, "one cached copy served both models"


def test_recommended_models_come_first_and_say_so():
    """v1.8.5: measured (doc/perbandingan-model.md). The old order put
    the two worst models of seven at the top of the list."""
    from omni_describer_custom.i18n.strings import t
    from omni_describer_custom.ui.settings_dialog import SettingsDialog
    extra = {"data": CATALOG["data"] + [
        {"id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
         "name": "Nemotron", "architecture": {"input_modalities":
                                              ["text", "image", "video", "audio"]},
         "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "google/gemini-3.1-flash-lite", "name": "Gemini 3.1 Flash Lite",
         "architecture": {"input_modalities": ["text", "image", "video", "audio"]},
         "pricing": {"prompt": "0.00000025", "completion": "0.0000015"}},
        {"id": "z-ai/glm-5.3-flash", "name": "GLM 5.3 Flash",
         "architecture": {"input_modalities": ["text", "image", "video"]},
         "pricing": {"prompt": "0.00000015", "completion": "0.0000005"}},
    ]}
    ids = [r["id"] for r in mc.parse_catalog(extra)]
    assert ids[:2] == ["z-ai/glm-5.3-flash", "google/gemini-3.1-flash-lite"], ids
    label = SettingsDialog._model_label(None, {"id": "google/gemini-3.1-flash-lite",
                                               "name": "Gemini 3.1 Flash Lite",
                                               "audio": True, "price_in": 0.25})
    assert label.startswith(t("settings.model_recommended", label="").strip()), label
    assert "Gemini 3.1 Flash Lite" in label
    plain = SettingsDialog._model_label(None, {"id": "x/y", "name": "Y",
                                               "audio": False, "price_in": 1})
    assert not plain.startswith(t("settings.model_recommended", label="").strip())


def test_settings_labels_save_ids_and_offer_a_test():
    import wx
    app = wx.GetApp() or wx.App(False)
    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.ui.settings_dialog import SettingsDialog
    mc.save_cache(mc.parse_catalog(CATALOG))
    store = SettingsStore()
    store.set_ai_provider("glm", {"api_key": "k", "model": "google/gemini-3.8-flash"})
    dlg = SettingsDialog(None, store)
    try:
        dlg.select_provider("glm")
        items = dlg.model_choice.GetItems()
        assert any("Qwen3.8 Omni Flash" in i and "0.15" in i for i in items), items
        assert dlg._choice_value(dlg.model_choice) == "google/gemini-3.8-flash"
        assert dlg.probe_model_btn.IsEnabled()
        dlg.model_choice.SetSelection(0)
        assert dlg._choice_value(dlg.model_choice) == "qwen/qwen3.8-omni-flash", \
            "the saved value must be the id, not the spoken label"
        # v1.9.2: Test this model works for every provider (test_fixes56).
        dlg.select_provider("gemini")
        assert dlg.probe_model_btn.IsEnabled()
        # v1.9.3: Fetch models asks Google for Gemini (test_fixes57).
        assert dlg.fetch_models_btn.IsEnabled()
        dlg.select_provider("minimax")
        assert not dlg.fetch_models_btn.IsEnabled()
    finally:
        dlg.Destroy()
        del app


def main() -> int:
    check("the list drops what never works; hearing models first",
          test_list_drops_what_never_works_and_sorts_hearing_first)
    check("the list is kept between visits", test_list_is_kept_between_visits)
    check("recommended models come first and say so",
          test_recommended_models_come_first_and_say_so)
    check("hearing is per model; a test beats the catalog",
          test_hearing_is_per_model_and_a_test_beats_the_catalog)
    check("the probe judges seeing and hearing", test_probe_judges_seeing_and_hearing)
    check("the probe sends a real clip and reports errors",
          test_probe_sends_a_real_clip_and_reports_errors)
    check("compressed uploads keep sound only for a model that hears",
          test_compressed_upload_keeps_sound_only_for_a_model_that_hears)
    check("Settings labels models, saves ids and offers a test",
          test_settings_labels_save_ids_and_offer_a_test)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
