"""Regression round 55: whole-video requests use temperature 0 (v1.9.1).

Measured (doc/perbandingan-model.md, phase 19.B1): with the server's
default temperature GLM gave 51 correct / 24.2% wrong descriptions and
wildly different runs (a news clip: 3, 15, 14 descriptions); with
temperature 0, 83 correct / 16.8% wrong and half the spread.
"""
import asyncio
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


def main():
    check("whole-video requests use temperature 0", test_default_is_zero)
    check("None sends no temperature", test_none_leaves_it_to_the_server)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
