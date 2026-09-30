"""Regression round 49: gaps that exist, and parts that fit (v1.8.6).

Found by the accuracy baseline (phase 16.2, 29 Sep 2026):

  1. faster-whisper stretches each segment to the start of the next, so
     the transcript claimed 58.5 s of speech in a 60 s Tears of Steel
     clip (29.0 s by its words). Told there was no room, GLM and Gemini
     both wrote ONE description for a minute of robots and people.
     word_timestamps=True aligns segment times to the words: 12 -> 30
     GLM descriptions over four runs, none judged wrong.
  2. OpenRouter hands a request to the model's own provider. Google AI
     Studio refuses a body over 20,000,000 bytes, and the app allowed
     50 MB for every OpenRouter model: Gemini 3.1 Flash-Lite, just marked
     "Recommended", failed on a 10-minute part with HTTP 413.
"""
import asyncio
import io
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from omni_describer_custom.core.ai_engine import GLMProvider  # noqa: E402
from omni_describer_custom.core.tools import find_tool  # noqa: E402
from omni_describer_custom.core.video_processor import WHISPER_DECODE  # noqa: E402

results: list[tuple[str, bool]] = []

GOOGLE_413 = ('GLM HTTP 413: {"error":{"message":"Request body exceeds the '
              'provider maximum size: 29647078 bytes exceeds the 20000000 '
              'byte limit for Google AI Studio","code":413}}')


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def test_segment_times_come_from_the_words():
    assert WHISPER_DECODE.get("word_timestamps") is True, \
        "segments keep their stretched times and the gaps disappear"
    src = (ROOT / "src" / "omni_describer_custom" / "core" /
           "video_processor.py").read_text(encoding="utf-8")
    call = src.split("model.transcribe(")[1][:200]
    assert "WHISPER_DECODE" in call, "the setting never reaches Whisper"


def test_google_models_get_googles_limit():
    prov = GLMProvider(api_key="k")
    prov._limits_for("google/gemini-3.1-flash-lite")
    body = prov.MAX_VIDEO_BYTES * 4 / 3 + 200_000     # base64 + prompt
    assert body < 20_000_000, f"a {prov.MAX_VIDEO_BYTES} B video overflows 20 MB"
    assert prov.COMPRESS_TARGET_BYTES < prov.MAX_VIDEO_BYTES
    prov._limits_for("z-ai/glm-5.3-flash")
    assert prov.MAX_VIDEO_BYTES == GLMProvider.MAX_VIDEO_BYTES, \
        "one Gemini job must not shrink the next GLM job"


def test_the_limit_is_read_from_a_refusal():
    assert GLMProvider.body_limit_from_error(GOOGLE_413) == 20_000_000
    assert GLMProvider.body_limit_from_error("GLM HTTP 401: bad key") == 0
    assert GLMProvider.body_limit_from_error("GLM HTTP 413: too big") == 0
    # The same GLM model, a different OpenRouter upstream, 29 Sep 2026:
    routed = ("GLM API error: {'message': 'Request body exceeds the 8 MiB "
              "limit.', 'code': 413, 'metadata': {'error_type': "
              "'payload_too_large'}}")
    assert GLMProvider.body_limit_from_error(routed) == 8 * 1024 * 1024
    assert GLMProvider.body_limit_from_error(
        "HTTP 413: body exceeds the 20 MB limit") == 20_000_000


def _clip(seconds: int) -> Path:
    path = Path(tempfile.mkdtemp(prefix="odc_t49_")) / "clip.mp4"
    subprocess.run([find_tool("ffmpeg"), "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", f"testsrc=size=160x120:rate=5:duration={seconds}",
                    "-c:v", "libx264", str(path)], check=True, timeout=120)
    return path


def test_an_unknown_limit_is_learned_and_the_part_retried():
    prov = GLMProvider(api_key="k")
    calls = []

    async def part(path, prompt, model, **kw):
        calls.append(prov.MAX_VIDEO_BYTES)
        if len(calls) == 1:
            raise RuntimeError(GOOGLE_413.replace("Google AI Studio", "Somewhere"))
        return [(1.0, "a thing")]
    prov._describe_one_part = part
    pairs = asyncio.run(prov.describe_video_full(str(_clip(6)), "p",
                                                 "someone/new-model"))
    assert pairs == [(1.0, "a thing")], pairs
    assert len(calls) == 2, f"{len(calls)} attempts"
    assert calls[1] < 20_000_000 * 0.75, "the retry was not made to fit"


def test_a_refusal_that_cannot_be_helped_still_fails():
    prov = GLMProvider(api_key="k")

    async def part(path, prompt, model, **kw):
        raise RuntimeError("GLM HTTP 402: no credit")
    prov._describe_one_part = part
    try:
        asyncio.run(prov.describe_video_full(str(_clip(6)), "p", "z-ai/glm-5.3-flash"))
        raise AssertionError("a 402 was swallowed")
    except RuntimeError as e:
        assert "402" in str(e)


def test_a_timeout_inside_a_reply_is_retried():
    """OpenRouter sends an upstream 504 inside a 200 reply; it ended the
    whole 15-minute job instead of being tried again."""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    replies = [{"error": {"message": "The operation was aborted", "code": 504}},
               {"choices": [{"message": {"content": "[00:01] ok"}}]}]
    seen = []

    class Chat(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            body = json.dumps(replies[min(len(seen), 1)]).encode()
            seen.append(1)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Chat)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    prov = GLMProvider(api_key="k",
                       base_url=f"http://127.0.0.1:{server.server_address[1]}")
    prov._RETRY_BACKOFF_SECONDS = 0.01
    try:
        text = asyncio.run(prov._chat({"model": "m"}, timeout=30))
    finally:
        server.shutdown()
    assert text == "[00:01] ok" and len(seen) == 2, (text, len(seen))


def test_parts_default_to_five_minutes_once():
    """600 s parts halved accuracy on two long films; the saved 600 (the
    old default, written by the Settings dialog) becomes 300 ONCE. A
    value chosen after that is left alone, even 600."""
    import json
    import os
    folder = Path(tempfile.mkdtemp(prefix="odc_t49_cfg_"))
    (folder / "settings.json").write_text(json.dumps(
        {"general": {"chunk_seconds": 600}}), encoding="utf-8")
    old = os.environ.get("ODC_CONFIG_DIR")
    os.environ["ODC_CONFIG_DIR"] = str(folder)
    try:
        from omni_describer_custom.core import settings_store as ss
        store = ss.SettingsStore()
        assert store.get("general.chunk_seconds") == 300, store.get("general.chunk_seconds")
        store.set("general.chunk_seconds", 600)          # the user's own choice
        saved = json.loads((folder / "settings.json").read_text(encoding="utf-8"))
        assert "chunk_300" in saved.get("migrated", []), saved.get("migrated")
        data = dict(saved)
        ss._migrate(data)
        assert data["general"]["chunk_seconds"] == 600, "a user's choice was changed"
        assert ss.SettingsStore.DEFAULTS["general"]["chunk_seconds"] == 300
    finally:
        if old is None:
            os.environ.pop("ODC_CONFIG_DIR", None)
        else:
            os.environ["ODC_CONFIG_DIR"] = old


def main() -> int:
    check("segment times come from the words", test_segment_times_come_from_the_words)
    check("google/* models get Google's 20 MB limit", test_google_models_get_googles_limit)
    check("a provider's limit is read from its 413", test_the_limit_is_read_from_a_refusal)
    check("an unknown limit is learned and the part retried",
          test_an_unknown_limit_is_learned_and_the_part_retried)
    check("other refusals still fail", test_a_refusal_that_cannot_be_helped_still_fails)
    check("a timeout inside a reply is retried", test_a_timeout_inside_a_reply_is_retried)
    check("parts default to five minutes, migrated once", test_parts_default_to_five_minutes_once)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
