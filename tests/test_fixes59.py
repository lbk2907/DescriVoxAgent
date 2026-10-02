"""Regression round 59: the owner's bug report of 2 Oct 2026 (v1.9.6).

From the owner's own log (1 Oct 2026, frozen 1.9.5):
1. Cancel did nothing while the speech transcript was being made: the
   job stopped only when Whisper finished, 1.5 to 6 minutes later.
2. The transcript was made AGAIN on every attempt: one 24-minute video
   was transcribed four times, 3-6 minutes each.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
import io
import json
import sys
import tempfile
import traceback
import types
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

from omni_describer_custom.core.video_processor import (  # noqa: E402
    TranscriptSegment, VideoProcessor)

results: list[tuple[str, bool]] = []
TMP = Path(tempfile.mkdtemp(prefix="odc_t59_"))


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


class FakeWhisper:
    """faster-whisper stand-in: yields segments one at a time, like the
    real decoder, and counts how many were decoded."""
    decoded = 0

    def __init__(self, *a, **k):
        pass

    def transcribe(self, path, **kw):
        def gen():
            for i in range(1000):
                FakeWhisper.decoded += 1
                yield types.SimpleNamespace(start=float(i), end=i + 0.9,
                                            text=f"line {i}")
        info = types.SimpleNamespace(duration=1000.0, language="en")
        return gen(), info


def _processor(backend="whisper"):
    from omni_describer_custom.core.settings_store import SettingsStore
    SettingsStore().set("general.transcription_backend", backend)
    return VideoProcessor()


def test_cancel_stops_whisper_within_a_segment():
    sys.modules["faster_whisper"] = types.SimpleNamespace(WhisperModel=FakeWhisper)
    FakeWhisper.decoded = 0
    clip = TMP / "a.mp4"
    clip.write_bytes(b"x")
    vp = _processor()
    try:
        asyncio.run(vp.get_transcript(str(clip), local_path=str(clip),
                                      is_cancelled=lambda: FakeWhisper.decoded >= 3))
        raise AssertionError("Cancel was swallowed; the job would go on")
    except RuntimeError as e:
        assert str(e) == "cancelled", e
    assert FakeWhisper.decoded <= 4, f"{FakeWhisper.decoded} segments after Cancel"


def test_the_transcript_is_kept_in_the_project():
    sys.modules["faster_whisper"] = types.SimpleNamespace(WhisperModel=FakeWhisper)
    clip = TMP / "b.mp4"
    clip.write_bytes(b"x")
    cache = TMP / "proj" / "media" / "transcript.json"
    vp = _processor()
    FakeWhisper.decoded = 0
    first = asyncio.run(vp.get_transcript(str(clip), local_path=str(clip),
                                          cache_path=cache))
    assert len(first) == 1000 and cache.is_file()
    FakeWhisper.decoded = 0
    second = asyncio.run(vp.get_transcript(str(clip), local_path=str(clip),
                                           cache_path=cache))
    assert FakeWhisper.decoded == 0, "the video was transcribed again"
    assert [(s.start, s.text) for s in second] == [(s.start, s.text) for s in first]
    assert isinstance(second[0], TranscriptSegment)
    # The Player agent's existing file format is read the same way.
    rows = json.loads(cache.read_text(encoding="utf-8"))
    assert set(rows[0]) == {"start", "end", "text"}


def test_a_broken_cache_is_replaced_not_fatal():
    sys.modules["faster_whisper"] = types.SimpleNamespace(WhisperModel=FakeWhisper)
    clip = TMP / "c.mp4"
    clip.write_bytes(b"x")
    cache = TMP / "broken.json"
    cache.write_text("{not json", encoding="utf-8")
    got = asyncio.run(_processor().get_transcript(str(clip), local_path=str(clip),
                                                  cache_path=cache))
    assert len(got) == 1000
    assert json.loads(cache.read_text(encoding="utf-8"))[0]["text"] == "line 0"


def test_the_pipeline_passes_cancel_and_the_cache():
    src = Path("src/omni_describer_custom/ui/main_frame.py").read_text(encoding="utf-8")
    block = src[src.index("vp.get_transcript("):][:400]
    assert "is_cancelled=" in block and "cache_path=self._transcript_cache_path()" in block


def test_a_request_in_flight_is_abandoned_on_cancel():
    """Gemini generate could hold a job for 600 s after Cancel."""
    import time
    from aiohttp import web
    from omni_describer_custom.core import ai_engine as ae

    async def body():
        async def slow(request):
            await asyncio.sleep(20)
            return web.json_response({})
        app = web.Application()
        app.router.add_route("*", "/{t:.*}", slow)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        started = time.monotonic()
        try:
            await ae._http_json("GET", f"http://127.0.0.1:{port}/x", label="X",
                                timeout=60, is_cancelled=lambda:
                                time.monotonic() - started > 0.3)
            raise AssertionError("not cancelled")
        except RuntimeError as e:
            assert str(e) == "cancelled", e
            took = time.monotonic() - started   # before the server shuts down
        finally:
            await runner.cleanup()
        return took
    took = asyncio.run(body())
    assert took < 2.5, f"Cancel took {took:.1f} s"


def test_the_gemini_upload_is_retried():
    import aiohttp
    from omni_describer_custom.core import ai_engine as ae
    prov = ae.GeminiProvider(api_key="k")
    calls = []

    async def once(path, on_progress, is_cancelled):
        calls.append(1)
        if len(calls) == 1:
            raise aiohttp.ClientConnectionError("Cannot connect to host x")
        return "files/abc"
    prov._upload_video_once = once

    async def no_wait(seconds, is_cancelled):
        return None
    real = ae._sleep_cancellable
    ae._sleep_cancellable = no_wait
    try:
        assert asyncio.run(prov._upload_video("v.mp4")) == "files/abc"
        assert len(calls) == 2

        async def refused(path, on_progress, is_cancelled):
            calls.append(1)
            raise RuntimeError("Gemini upload HTTP 400: bad request")
        prov._upload_video_once = refused
        calls.clear()
        try:
            asyncio.run(prov._upload_video("v.mp4"))
            raise AssertionError("a 400 was retried or swallowed")
        except RuntimeError as e:
            assert "400" in str(e) and len(calls) == 1
    finally:
        ae._sleep_cancellable = real


def test_subtitle_steps_stop_on_cancel():
    import time
    vp = VideoProcessor()

    async def body():
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", "import time; time.sleep(30)",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        started = time.monotonic()
        try:
            await vp._communicate_cancellable(
                proc, 60, lambda: time.monotonic() - started > 0.3)
            raise AssertionError("not cancelled")
        except RuntimeError as e:
            assert str(e) == "cancelled"
        assert proc.returncode is not None, "the process was left running"
        return time.monotonic() - started
    assert asyncio.run(body()) < 3


def test_openrouter_daily_limit_is_named():
    from omni_describer_custom.core import ai_engine as ae
    body = '{"error":{"message":"Rate limit exceeded: free-models-per-day.","code":429}}'
    assert ae.daily_quota(body) == "free-models-per-day"
    assert ae.daily_quota('{"error":{"code":429}}') == ""


def main() -> int:
    check("Cancel stops Whisper within a segment",
          test_cancel_stops_whisper_within_a_segment)
    check("the transcript is kept in the project",
          test_the_transcript_is_kept_in_the_project)
    check("a broken transcript cache is replaced",
          test_a_broken_cache_is_replaced_not_fatal)
    check("the pipeline passes Cancel and the cache",
          test_the_pipeline_passes_cancel_and_the_cache)
    check("a request in flight is abandoned on Cancel",
          test_a_request_in_flight_is_abandoned_on_cancel)
    check("the Gemini upload is retried", test_the_gemini_upload_is_retried)
    check("subtitle steps stop on Cancel", test_subtitle_steps_stop_on_cancel)
    check("OpenRouter's daily limit is named", test_openrouter_daily_limit_is_named)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
