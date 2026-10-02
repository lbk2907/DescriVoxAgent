"""Regression round 55: whole-video requests use temperature 0 (v1.9.1).

Measured (doc/perbandingan-model.md, phase 19.B1): with the server's
default temperature GLM gave 51 correct / 24.2% wrong descriptions and
wildly different runs (a news clip: 3, 15, 14 descriptions); with
temperature 0, 83 correct / 16.8% wrong and half the spread.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
import json
import io
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")
os.environ.setdefault("ODC_CONFIG_DIR", tempfile.mkdtemp(prefix="odc_t55_"))

from omni_describer_custom.core.ai_engine import GLMProvider  # noqa: E402
from omni_describer_custom.core.tools import find_tool  # noqa: E402

results = []


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def payload_for(temperature="default"):
    clip = Path(tempfile.mkdtemp(prefix="odc_t55_")) / "c.mp4"
    subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc=size=160x120:rate=5:duration=4",
                    "-c:v", "libx264", str(clip)], check=True, timeout=60)
    prov = GLMProvider(api_key="k")
    if temperature != "default":
        prov.TEMPERATURE = temperature
    seen = {}

    async def fake_chat(payload, timeout, **kw):
        seen.update(payload)
        return "[0:00:01] A test pattern."
    prov._chat = fake_chat
    asyncio.run(prov.describe_video_full(str(clip), "describe"))
    return seen


def test_default_is_zero():
    assert GLMProvider.TEMPERATURE == 0.0
    assert payload_for()["temperature"] == 0.0


def test_none_leaves_it_to_the_server():
    assert "temperature" not in payload_for(None)


def gemini_config(temperature):
    """What Gemini's whole-video request carries (phase 20.7)."""
    from omni_describer_custom.core import ai_engine
    from omni_describer_custom.core.ai_engine import GeminiProvider
    prov = GeminiProvider(api_key="k")
    prov.TEMPERATURE = temperature
    seen = {}

    async def fake_http(method, url, **kw):
        seen.update(kw["payload"])
        return {"candidates": [{"content": {"parts": [{"text": "x"}]}}]}
    real = ai_engine._http_json
    ai_engine._http_json = fake_http
    try:
        asyncio.run(prov._generate_with_video("files/u", "video/mp4",
                                              "describe", "gemini-x"))
    finally:
        ai_engine._http_json = real
    return seen["generationConfig"]


def test_gemini_temperature_reaches_the_request():
    from omni_describer_custom.core.ai_engine import GeminiProvider
    assert GeminiProvider.TEMPERATURE == 0.0
    assert gemini_config(0.0)["temperature"] == 0.0
    assert "temperature" not in gemini_config(None)


def gemini_calls(model, refuse_thinking=False, override=None):
    """Every generateContent body Gemini sends for one video request."""
    from omni_describer_custom.core import ai_engine
    from omni_describer_custom.core.ai_engine import GeminiProvider
    prov = GeminiProvider(api_key="k")
    if override is not None:
        prov.THINKING = override
    bodies = []

    async def fake_http(method, url, **kw):
        bodies.append(json.loads(json.dumps(kw["payload"])))
        if refuse_thinking and "thinkingConfig" in kw["payload"]["generationConfig"]:
            raise RuntimeError("Gemini HTTP 400: Invalid value at "
                               "'generation_config.thinking_config.thinking_level'")
        return {"candidates": [{"content": {"parts": [{"text": "x"}]}}]}
    real = ai_engine._http_json
    ai_engine._http_json = fake_http
    try:
        asyncio.run(prov._generate_with_video("files/u", "video/mp4",
                                              "describe", model))
    finally:
        ai_engine._http_json = real
    return [b["generationConfig"] for b in bodies]


def test_gemini_thinking_per_model():
    """Phase 22: 3.1 Flash-Lite thinks at "medium" (wrong 15.8% -> 9.1%);
    models that were not measured keep Google's default."""
    assert gemini_calls("gemini-3.1-flash-lite")[0]["thinkingConfig"] == \
        {"thinkingLevel": "medium"}
    assert "thinkingConfig" not in gemini_calls("gemini-3.8-flash")[0]
    assert "thinkingConfig" not in gemini_calls("gemini-3.1-flash-lite",
                                                override={})[0]


def test_refused_thinking_level_does_not_lose_the_job():
    calls = gemini_calls("gemini-3.1-flash-lite", refuse_thinking=True)
    assert len(calls) == 2, calls
    assert "thinkingConfig" in calls[0] and "thinkingConfig" not in calls[1]


def main():
    check("whole-video requests use temperature 0", test_default_is_zero)
    check("None sends no temperature", test_none_leaves_it_to_the_server)
    check("Gemini direct: the temperature reaches the request",
          test_gemini_temperature_reaches_the_request)
    check("Gemini thinking is set per model",
          test_gemini_thinking_per_model)
    check("a refused thinking level does not lose the job",
          test_refused_thinking_level_does_not_lose_the_job)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
