"""Regression round 34: the AI engine audit (v1.7.4).

Each check below reproduced a real fault before its fix; all run
offline against a loopback aiohttp server or unittest.mock.

  1. Gemini's key sat in the URL; an HTML 503 page raised an aiohttp
     error whose text carried the URL, and that text was logged and
     saved as the frame's "description".
  2. Only GLM retried 429/5xx; one rate limit lost a Gemini job.
  3. "(empty response)" / "(no response from ...)" were saved as cues
     and read aloud.
  4. A part's length was taken as chunk_seconds (600), so a 60 s clip
     was offered ~1,300 words of "silence" after it had ended.
  5. The preserve-resolution split still scaled to 360p, and each
     part saw the next parts' speech.
  6. Cue times past a part's end landed in the next part.
  7. A cancelled split left its temp folder behind.
  8. "1. [00:05] ...", "**[00:05]** ...", "[00:05]A dog" were dropped.
  9. Only the first text part of a Gemini reply was read.
 10. prompt_manager: a universal preset could not be deleted; a null
     in an import file crashed.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
import glob
import io
import logging
import os
import sys
import tempfile
import traceback
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

from aiohttp import web  # noqa: E402

from omni_describer_custom.core import ai_engine as ae  # noqa: E402
from omni_describer_custom.core.ai_engine import (  # noqa: E402
    CustomProvider, GeminiProvider, GLMProvider, MiniMaxProvider,
    OpenAIProvider, build_transcript_block, is_placeholder_text,
    parse_gemini_timestamp_lines)

SECRET = "SECRETKEY123"
TMP = Path(tempfile.mkdtemp(prefix="odc_t34_"))
IMG = TMP / "x.jpg"
IMG.write_bytes(b"\xff\xd8\xff")


class Stub:
    """Loopback server that plays a scripted list of replies."""

    def __init__(self):
        self.script: list = []
        self.requests: list = []

    async def handle(self, req):
        self.requests.append((req.method, str(req.rel_url),
                              dict(req.headers)))
        kind, status, body = (self.script.pop(0) if self.script
                              else ("json", 200, {}))
        if kind == "html":
            return web.Response(status=status, text=body,
                                content_type="text/html")
        return web.json_response(body, status=status)


async def with_stub(fn):
    stub = Stub()
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", stub.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        return await fn(stub, f"http://127.0.0.1:{port}")
    finally:
        await runner.cleanup()


def run(fn):
    with mock.patch.object(ae, "HTTP_RETRY_BACKOFF_SECONDS", 0.0):
        return asyncio.run(with_stub(fn))


OK_GEMINI = ("json", 200, {"candidates": [{"content": {"parts": [
    {"text": "A cat."}]}}]})


# 1 ──────────────────────────────────────────────────────────────────
def test_gemini_key_never_in_url_log_or_text():
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    logging.getLogger().addHandler(handler)
    try:
        async def body(stub, base):
            stub.script = [("html", 503, "<html>down</html>")] * 3
            p = GeminiProvider(api_key=SECRET, base_url=base + "/v1beta")
            res = await p.describe_frames_batch([str(IMG)], "d")
            return stub, res
        stub, res = run(body)
    finally:
        logging.getLogger().removeHandler(handler)
    assert SECRET not in res[0], res[0]
    assert SECRET not in buf.getvalue(), "key reached the log"
    for _m, url, headers in stub.requests:
        assert SECRET not in url, url
        assert headers.get("x-goog-api-key") == SECRET, headers


def test_gemini_upload_and_status_use_header():
    async def body(stub, base):
        p = GeminiProvider(api_key=SECRET, base_url=base + "/v1beta")
        stub.script = [("json", 200, {"state": "ACTIVE"})]
        await p._wait_video_ready("files/abc")
        return stub
    stub = run(body)
    _m, url, headers = stub.requests[0]
    assert SECRET not in url and headers.get("x-goog-api-key") == SECRET
    src = Path("src/omni_describer_custom/core/ai_engine.py").read_text(
        encoding="utf-8")
    assert "key={self.api_key}" not in src, "a key is still put in a URL"


# 2 ──────────────────────────────────────────────────────────────────
def _retry_case(make, ok_reply):
    async def body(stub, base):
        stub.script = [("json", 429, {"error": "slow down"}),
                       ("html", 503, "<html>busy</html>"), ok_reply]
        out = await make(base).describe_image(str(IMG), "d")
        return stub, out
    stub, out = run(body)
    assert len(stub.requests) == 3, len(stub.requests)
    return out


def test_every_provider_retries_transient_errors():
    oa = ("json", 200, {"choices": [{"message": {"content": "A cat."}}]})
    assert _retry_case(lambda b: GeminiProvider(SECRET, b + "/v1beta"),
                       OK_GEMINI) == "A cat."
    assert _retry_case(lambda b: OpenAIProvider("k", b), oa) == "A cat."
    assert _retry_case(lambda b: MiniMaxProvider("k", b), oa) == "A cat."
    assert _retry_case(lambda b: CustomProvider("k", b, "m"), oa) == "A cat."
    assert _retry_case(
        lambda b: CustomProvider("k", b, "m", api_format="anthropic"),
        ("json", 200, {"content": [{"type": "text", "text": "A cat."}]}),
    ) == "A cat."


def test_client_errors_are_not_retried_and_cancel_stops_backoff():
    async def body(stub, base):
        stub.script = [("json", 401, {"error": "bad key"})]
        try:
            await OpenAIProvider("k", base).describe_image(str(IMG), "d")
        except RuntimeError as e:
            assert "401" in str(e)
        else:
            raise AssertionError("401 should raise")
        return stub
    assert len(run(body).requests) == 1

    async def body2(stub, base):
        stub.script = [("json", 503, {})] * 3
        try:
            await ae._http_json("GET", base, label="X",
                                is_cancelled=lambda: len(stub.requests) >= 1)
        except RuntimeError as e:
            assert "cancelled" in str(e), e
        return stub
    assert len(run(body2).requests) == 1


def test_429_waits_as_long_as_the_server_says():
    """v1.9.5: a per-minute limit says how long to wait; 5 s then 15 s
    was not enough. A daily quota (hours) is not waited for at all."""
    slept = []

    async def fake_sleep(seconds, is_cancelled):
        slept.append(seconds)

    async def body(stub, base):
        stub.script = [("json", 429, {"error": {"details": [
            {"@type": "type.googleapis.com/google.rpc.RetryInfo",
             "retryDelay": "37s"}]}}), ("json", 200, {"ok": 1})]
        assert await ae._http_json("GET", base, label="X") == {"ok": 1}
        stub.script = [("json", 429, {"error": {"details": [
            {"retryDelay": "43200s"}]}})] * 3
        try:
            await ae._http_json("GET", base, label="X")
        except RuntimeError as e:
            assert "429" in str(e)
        else:
            raise AssertionError("a daily quota must fail")
        return stub
    with mock.patch.object(ae, "_sleep_cancellable", fake_sleep):
        stub = run(body)
    assert slept == [38.0], slept
    assert len(stub.requests) == 3, "a daily quota was retried"
    assert ae._server_wait("", "12") == 12.0
    assert ae._server_wait("", None) is None

    # Google's real daily-quota answer still says "retry in 53s".
    daily = {"error": {"code": 429, "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId":
                         "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                         "quotaValue": "20"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo",
         "retryDelay": "53s"}]}}

    async def body3(stub, base):
        stub.script = [("json", 429, daily)] * 3
        try:
            await ae._http_json("GET", base, label="Gemini")
        except RuntimeError as e:
            assert "daily quota" in str(e) and "FreeTier" in str(e), e
        else:
            raise AssertionError("a daily quota must fail")
        return stub
    slept.clear()
    with mock.patch.object(ae, "_sleep_cancellable", fake_sleep):
        stub = run(body3)
    assert len(stub.requests) == 1 and slept == [], (len(stub.requests), slept)


def test_daily_quota_is_told_apart_from_busy():
    """v1.9.6: found in review — the daily-quota error from _http_json
    reached the user as the generic "busy, wait a few minutes"."""
    from omni_describer_custom.i18n.strings import t
    daily = ("Gemini HTTP 429: daily quota used up "
             "(GenerateRequestsPerDayPerProjectPerModel-FreeTier). It resets "
             "at midnight Pacific time; a paid tier raises it.")
    assert ae.is_daily_quota_error(daily) and ae.is_busy_error(daily)
    assert ae.user_error_text(daily) == t("error.ai_daily_quota")
    assert ae.user_error_text("Gemini HTTP 503: high demand") == t("error.ai_busy")
    # v1.9.6: every failure is translated; none is read out raw.
    assert ae.user_error_text("GLM HTTP 401: invalid key") == t("error.ai_key")
    owner_413 = ('GLM HTTP 413: {"error":{"message":"Provider returned error",'
                 '"code":413},"user_id":"user_3FfsFSgsvnGKAlJHZrrWW8rMjKG"}')
    assert ae.user_error_text(owner_413) == t("error.ai_too_large")
    odd = ae.user_error_text('X failed: {"a": 1} https://h/p?key=SECRET user_ABCDEFG123')
    assert "{" not in odd and "SECRET" not in odd and "user_ABC" not in odd, odd
    assert ae.user_error_text("Cannot connect to host 127.0.0.1:12144 ssl:default")         == t("error.ai_network")
    from omni_describer_custom.ui.agent_dialog import AgentDialog
    assert AgentDialog._error_text(daily) == t("error.ai_daily_quota")
    assert "{" not in AgentDialog._error_text('GLM HTTP 500: {"x": 1}')
    src = open(os.path.join("src", "omni_describer_custom", "ui",
                            "main_frame.py"), encoding="utf-8").read()
    assert "user_error_text(" in src


# 3 ──────────────────────────────────────────────────────────────────
def test_placeholders_are_not_descriptions():
    async def body(stub, base):
        stub.script = [("json", 200, {"candidates": [
            {"finishReason": "SAFETY"}]})]
        p = GeminiProvider(api_key=SECRET, base_url=base + "/v1beta")
        return await p.describe_image(str(IMG), "d")
    out = run(body)
    assert is_placeholder_text(out), out
    for t in ["", "  ", "(cancelled)", "(error: x)", "(empty response)",
              "(no response from GLM)", "(no text in custom API response)"]:
        assert is_placeholder_text(t), t
    assert not is_placeholder_text("A man (smiling) waves.")
    # v1.8.6: the frame pipeline filters through finalize_frame_descriptions
    # (which also cleans markdown); check it still drops placeholders.
    src = Path("src/omni_describer_custom/ui/main_frame.py").read_text(
        encoding="utf-8")
    assert "finalize_frame_descriptions(frames, descriptions)" in src
    from omni_describer_custom.core.ai_engine import (
        finalize_frame_descriptions)
    kept = finalize_frame_descriptions(["a", "b", "c"], [
        "(empty response)", "A real line.", "(no response from GLM)"])
    assert [t for _, t in kept] == ["A real line."], kept


# 4 + 5 + 6 ─────────────────────────────────────────────────────────
def test_single_part_uses_real_length():
    p = GLMProvider(api_key="k")
    vid = TMP / "short.mp4"
    vid.write_bytes(b"\0" * 10)
    seen = {}

    async def fake_one(path, prompt, model, **kw):
        seen.update(kw)
        return []
    with mock.patch.object(p, "_probe_duration", return_value=60.0), \
            mock.patch.object(p, "_describe_one_part", side_effect=fake_one):
        asyncio.run(p.describe_video_full(str(vid), "d", chunk_seconds=600))
    assert seen["part_seconds"] == 60.0, seen["part_seconds"]
    # And what that means in the prompt: no room after the video ends.
    segs = [NS(start=i, end=i + 1.9, text=f"w{i}") for i in range(0, 58, 2)]
    block = build_transcript_block(segs, start=0, end=60, offset=0)
    assert "10:00" not in block and "1355" not in block


def test_preserve_split_keeps_pixels_window_and_clamps():
    p = GLMProvider(api_key="k")
    p.MAX_VIDEO_BYTES = 5
    vid = TMP / "big.mp4"
    vid.write_bytes(b"\0" * 10)
    split_kw = {}

    def fake_split(path, secs, **kw):
        split_kw.update(kw)
        parts = []
        for i in range(3):
            f = TMP / f"part_{i}.mp4"
            f.write_bytes(b"\0")
            parts.append(f)
        return [0.0, 100.0, 200.0], parts
    prompts = []

    async def fake_chat(payload, timeout):
        prompts.append(payload["messages"][0]["content"][0]["text"])
        return "[0:00:05] ok\n[0:12:00] invented late cue"
    segs = [NS(start=50, end=52, text="LINE_AT_50"),
            NS(start=150, end=152, text="LINE_AT_150"),
            NS(start=250, end=252, text="LINE_AT_250")]
    with mock.patch.object(p, "_probe_duration", return_value=300.0), \
            mock.patch.object(p, "_chunk_seconds_to_fit", return_value=100), \
            mock.patch.object(p, "split_video_for_upload",
                              side_effect=fake_split), \
            mock.patch.object(p, "_chat", side_effect=fake_chat):
        res = asyncio.run(p.describe_video_full(
            str(vid), "d", chunk_seconds=600, transcript=segs,
            preserve_resolution=True))
    assert split_kw.get("keep_resolution") is True, split_kw
    assert "LINE_AT_50" in prompts[0]
    assert "LINE_AT_150" not in prompts[0], "part 1 saw part 2's speech"
    assert "LINE_AT_250" not in prompts[0]
    assert [t for t, _ in res] == [5.0, 105.0, 205.0], res


class _FakeProc:
    cmd: list = []

    def __init__(self, cmd, **kw):
        _FakeProc.cmd = cmd
        self.stdout = iter([b"out_time_us=1000000\n"])
        self.stderr = mock.MagicMock()
        self.stderr.readline = lambda: b""
        self.returncode = 0

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


def _split(keep, cancelled):
    p = GLMProvider(api_key="k")
    vid = TMP / "split.mp4"
    vid.write_bytes(b"\0" * 10)
    before = set(glob.glob(os.path.join(tempfile.gettempdir(),
                                        "odc_vsplit_*")))
    with mock.patch.object(p, "_probe_duration", return_value=300.0), \
            mock.patch.object(p, "_ffmpeg", return_value="ffmpeg"), \
            mock.patch("subprocess.Popen", _FakeProc):
        try:
            p.split_video_for_upload(vid, 100, keep_resolution=keep,
                                     is_cancelled=lambda: cancelled)
        except RuntimeError:
            pass
    after = set(glob.glob(os.path.join(tempfile.gettempdir(),
                                       "odc_vsplit_*")))
    return _FakeProc.cmd, after - before


def test_split_scale_and_cleanup():
    cmd, leaked = _split(keep=True, cancelled=True)
    assert "scale=-2:360" not in cmd, cmd
    assert not leaked, f"cancelled split left {leaked}"
    cmd, leaked = _split(keep=False, cancelled=False)  # "no parts" error
    assert "scale=-2:360" in cmd
    assert not leaked, f"failed split left {leaked}"


# 8 + 9 ─────────────────────────────────────────────────────────────
def test_parser_tolerates_what_models_write():
    cases = {
        "**[00:05]** A dog barks.": (5.0, "A dog barks."),
        "1. [00:05] A dog.": (5.0, "A dog."),
        "[00:05]A dog.": (5.0, "A dog."),
        "- **00:07** - Cat": (7.0, "Cat"),
        "[00:05]: A dog.": (5.0, "A dog."),
        "[1:02:03] x": (3723.0, "x"),
        "01:02:03.500 Frac": (3723.5, "Frac"),
    }
    for line, want in cases.items():
        got = parse_gemini_timestamp_lines(line)
        assert got == [want], (line, got)
    assert parse_gemini_timestamp_lines("12:34") == []
    assert parse_gemini_timestamp_lines("12:345 x") == []


def test_gemini_joins_all_text_parts():
    async def body(stub, base):
        stub.script = [("json", 200, {"candidates": [{"content": {"parts": [
            {"text": "thinking...", "thought": True},
            {"text": "[00:00] A man enters.\n"},
            {"text": "[00:30] He sits down.\n"}]}}]})]
        p = GeminiProvider(api_key=SECRET, base_url=base + "/v1beta")
        return await p._generate_with_video("files/a", "video/mp4", "p", "m")
    pairs = parse_gemini_timestamp_lines(run(body))
    assert pairs == [(0.0, "A man enters."), (30.0, "He sits down.")], pairs


# 10 ────────────────────────────────────────────────────────────────
def test_prompt_manager_small_ones():
    from omni_describer_custom.core.prompt_manager import PromptManager

    class S:
        def __init__(self):
            self.d = {}

        def get_prompts(self):
            return dict(self.d)

        def set_prompt(self, n, t):
            self.d[n] = t

        def delete_prompt(self, n):
            return self.d.pop(n, None) is not None
    pm = PromptManager(S())
    pm.language = "en"
    pm.settings.set_prompt("mine", "x")
    assert pm.delete_preset("mine") is True
    assert "mine" not in pm.get_preset_names()
    assert pm.import_prompts({"a": None, "b": "ok", "c": 3}) == 1


if __name__ == "__main__":
    ok_count = fail_count = 0

    def check(name, fn):
        global ok_count, fail_count
        try:
            fn()
            ok_count += 1
            print(f"PASS  {name}")
        except Exception:
            fail_count += 1
            print(f"FAIL  {name}")
            traceback.print_exc()

    check("gemini key never in url, log or text",
          test_gemini_key_never_in_url_log_or_text)
    check("gemini upload and status use the header",
          test_gemini_upload_and_status_use_header)
    check("every provider retries transient errors",
          test_every_provider_retries_transient_errors)
    check("client errors not retried; cancel stops backoff",
          test_client_errors_are_not_retried_and_cancel_stops_backoff)
    check("429 waits as long as the server says",
          test_429_waits_as_long_as_the_server_says)
    check("a daily quota is told apart from busy",
          test_daily_quota_is_told_apart_from_busy)
    check("placeholders are not descriptions",
          test_placeholders_are_not_descriptions)
    check("single part uses its real length",
          test_single_part_uses_real_length)
    check("preserve split keeps pixels, window, clamps cues",
          test_preserve_split_keeps_pixels_window_and_clamps)
    check("split scale and cleanup", test_split_scale_and_cleanup)
    check("parser tolerates what models write",
          test_parser_tolerates_what_models_write)
    check("gemini joins all text parts", test_gemini_joins_all_text_parts)
    check("prompt manager small ones", test_prompt_manager_small_ones)
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
