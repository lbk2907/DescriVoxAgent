"""Regression round 23: the transcript context (v1.6.1).

The default provider cannot hear the video. Probed 20 Sep 2026, GLM
answers "NO AUDIO ACCESS" when asked to transcribe a spoken line. That
made the `foreign` preset — whose entire job is conveying speech —
silently produce ordinary visual descriptions, and it left every other
preset guessing at whatever the soundtrack carried.

The app already had the answer and never used it: VideoProcessor
.get_transcript() fetched subtitles through yt-dlp. It was dead code,
and broken as well — the first line rejected anything that was not an
existing local file, which is exactly the input (a URL) the function
needs. Nothing called it, so nothing noticed.

Wired up and fixed, GLM now READS what it cannot hear. Verified against
the real API: with the transcript supplied, `ms_foreign` produced
"Dia berkata keunikan gajah-gajah ini ialah belalai yang amat panjang"
from English speech — the conveyance that had failed three runs running.
"""
import asyncio
import inspect
import io
import sys
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

from omni_describer_custom.core.ai_engine import (  # noqa: E402
    AIEngine, build_transcript_block)
from omni_describer_custom.core.video_processor import (  # noqa: E402
    TranscriptSegment, VideoProcessor)

ok_count = 0
fail_count = 0


def check(name, fn):
    global ok_count, fail_count
    try:
        fn()
        print(f"PASS: {name}")
        ok_count += 1
    except Exception as e:
        print(f"FAIL: {name}: {e}")
        traceback.print_exc()
        fail_count += 1


def _segs(*rows):
    return [TranscriptSegment(start=s, end=e, text=t) for s, e, t in rows]


# ── The block handed to the model ────────────────────────────────

def test_no_transcript_adds_nothing():
    assert build_transcript_block([]) == ""
    assert build_transcript_block(None) == ""


def test_block_carries_the_words_and_the_rule():
    block = build_transcript_block(_segs((1.2, 3.4, "here we are"),
                                         (5.3, 8.0, "long trunks")))
    assert "here we are" in block and "long trunks" in block
    assert "already audible" in block, "no reason given for the transcript"
    assert "do NOT narrate these lines back" in block, (
        "without this the model reads the dialogue out, which is exactly "
        "what every AD standard forbids")


def test_block_is_limited_to_the_part_window():
    """A chunked video must not hand part 1 the words from part 3."""
    segs = _segs((10.0, 12.0, "first part line"),
                 (700.0, 702.0, "second part line"))
    first = build_transcript_block(segs, start=0.0, end=600.0, offset=0.0)
    assert "first part line" in first
    assert "second part line" not in first, "part 1 leaked part 2's speech"

    second = build_transcript_block(segs, start=600.0, end=1200.0,
                                    offset=600.0)
    assert "second part line" in second
    assert "first part line" not in second


def test_timestamps_are_shifted_into_part_local_time():
    """The model is asked for part-local timestamps, so the transcript
    it is shown must use the same clock or the two disagree."""
    block = build_transcript_block(_segs((605.0, 607.0, "line in part two")),
                                   start=600.0, end=1200.0, offset=600.0)
    assert "[00:05]" in block, f"timestamp not shifted: {block}"
    assert "[10:05]" not in block


def test_long_transcript_is_trimmed_not_dropped():
    """A feature-length video must not blow the context window, and must
    not silently lose its opening either."""
    many = _segs(*[(float(i), float(i) + 1, f"line {i}") for i in range(400)])
    block = build_transcript_block(many, limit=50)
    assert "line 0" in block, "opening lost"
    assert "line 399" in block, "ending lost"
    assert "[...]" in block, "no marker that the middle was dropped"
    assert block.count("\n") < 80, "trimming did not actually shrink it"


# ── Where the transcript comes from ──────────────────────────────

def test_url_and_file_take_different_routes():
    """The old code called the yt-dlp path for local files only, which is
    backwards: subtitles are fetched for URLs."""
    vp = VideoProcessor()
    calls = []

    async def fake_ytdlp(self, source):
        calls.append(("ytdlp", source))
        return _segs((0.0, 1.0, "from subtitles"))

    async def fake_embedded(self, source):
        calls.append(("embedded", source))
        return _segs((0.0, 1.0, "from file"))

    real = (VideoProcessor._ytdlp_subtitles, VideoProcessor._embedded_subtitles)
    VideoProcessor._ytdlp_subtitles = fake_ytdlp
    VideoProcessor._embedded_subtitles = fake_embedded
    try:
        got = asyncio.run(vp.get_transcript("https://youtu.be/abc123"))
        assert calls and calls[-1][0] == "ytdlp", calls
        assert got and got[0].text == "from subtitles"

        got = asyncio.run(vp.get_transcript(r"C:\videos\clip.mp4"))
        assert calls[-1][0] == "embedded", calls
        assert got and got[0].text == "from file"
    finally:
        VideoProcessor._ytdlp_subtitles, VideoProcessor._embedded_subtitles = real


def test_transcript_failure_never_breaks_a_run():
    """No transcript is a smaller loss than no descriptions."""
    vp = VideoProcessor()

    async def boom(self, source):
        raise RuntimeError("network down")

    real = VideoProcessor._ytdlp_subtitles
    VideoProcessor._ytdlp_subtitles = boom
    try:
        assert asyncio.run(vp.get_transcript("https://youtu.be/abc")) == []
    finally:
        VideoProcessor._ytdlp_subtitles = real


def test_ytdlp_path_accepts_urls():
    """The guard that made this function useless must stay gone."""
    src = Path("src/omni_describer_custom/core/video_processor.py").read_text(
        encoding="utf-8")
    start = src.index("async def _ytdlp_subtitles")
    body = src[start:start + 900]
    assert "if not Path(video_path).exists():" not in body, (
        "the local-file guard is back; every URL will be rejected again")


# ── Wiring ───────────────────────────────────────────────────────

def test_engine_accepts_a_transcript():
    sig = inspect.signature(AIEngine.describe_video_full)
    assert "transcript" in sig.parameters, "engine cannot receive a transcript"


def test_transcript_only_goes_to_providers_that_take_one():
    """Gemini hears the audio itself and has no such parameter; passing
    one would raise TypeError mid-run."""
    from omni_describer_custom.core.ai_engine import (GeminiProvider,
                                                      GLMProvider)

    glm = inspect.signature(GLMProvider.describe_video_full).parameters
    assert "transcript" in glm, "GLM is the provider that needs it"
    gem = inspect.signature(GeminiProvider.describe_video_full).parameters
    if "transcript" not in gem:
        src = Path("src/omni_describer_custom/core/ai_engine.py").read_text(
            encoding="utf-8")
        assert "inspect.signature(fn).parameters" in src, (
            "facade passes transcript blindly; Gemini runs would crash")


def test_pipeline_fetches_the_transcript():
    src = Path("src/omni_describer_custom/ui/main_frame.py").read_text(
        encoding="utf-8")
    assert "vp.get_transcript(source" in src, \
        "the pipeline no longer fetches a transcript"
    assert "local_path=resolved" in src, (
        "a URL with no published captions can no longer fall back to "
        "transcribing the file that was just downloaded")
    assert "transcript=transcript" in src, \
        "the transcript is fetched but never passed to the engine"


def test_transcript_phase_is_announced_in_both_languages():
    from omni_describer_custom.i18n.strings import EN_STRINGS, MS_STRINGS

    for lang, table in (("en", EN_STRINGS), ("ms", MS_STRINGS)):
        for key in ("process.transcript_ok", "process.transcript_none",
                    "video.phase_transcript"):
            assert table.get(key), f"{lang}: missing {key}"
        assert "{count}" in table["process.transcript_ok"]


# ── Speech-to-text backends (v1.6.1) ─────────────────────────────
#
# Published captions are exact; machine transcription is not. Measured
# on the same clip: YouTube's captions said "really long TRUNKS", local
# Whisper heard "long hunts". So transcription is a fallback, and the
# order in get_transcript() is deliberate.

class _FakeSettings:
    def __init__(self, backend="auto", xai_key=""):
        self._backend = backend
        self._xai = xai_key

    def get(self, key, default=None):
        if key == "general.transcription_backend":
            return self._backend
        if key == "general.whisper_model":
            return "base"
        return default

    def get_ai_provider(self, name):
        return {"api_key": self._xai} if name == "xai" else {}


def test_transcription_can_be_turned_off():
    vp = VideoProcessor(settings=_FakeSettings(backend="off"))
    assert asyncio.run(vp.transcribe_audio("x.mp4")) == []


def test_grok_is_skipped_without_a_key():
    """Selecting Grok with no key must degrade quietly, not raise."""
    vp = VideoProcessor(settings=_FakeSettings(backend="grok", xai_key=""))
    assert asyncio.run(vp.transcribe_audio("x.mp4")) == []


def test_auto_falls_back_to_whisper_when_no_key():
    vp = VideoProcessor(settings=_FakeSettings(backend="auto", xai_key=""))
    called = []

    async def fake_whisper(self, path):
        called.append(path)
        return _segs((0.0, 1.0, "local"))

    real = VideoProcessor._whisper_transcribe
    VideoProcessor._whisper_transcribe = fake_whisper
    try:
        got = asyncio.run(vp.transcribe_audio("clip.mp4"))
        assert called == ["clip.mp4"], called
        assert got and got[0].text == "local"
    finally:
        VideoProcessor._whisper_transcribe = real


def test_auto_prefers_grok_when_a_key_exists():
    vp = VideoProcessor(settings=_FakeSettings(backend="auto", xai_key="k"))
    order = []

    async def fake_grok(self, path, key):
        order.append("grok")
        return _segs((0.0, 1.0, "from grok"))

    async def fake_whisper(self, path):
        order.append("whisper")
        return []

    real = (VideoProcessor._grok_transcribe, VideoProcessor._whisper_transcribe)
    VideoProcessor._grok_transcribe = fake_grok
    VideoProcessor._whisper_transcribe = fake_whisper
    try:
        got = asyncio.run(vp.transcribe_audio("clip.mp4"))
        assert order == ["grok"], f"whisper ran despite a key: {order}"
        assert got[0].text == "from grok"
    finally:
        VideoProcessor._grok_transcribe, VideoProcessor._whisper_transcribe = real


def test_grok_failure_falls_back_to_whisper_in_auto():
    """A network blip on a paid service must not lose the transcript."""
    vp = VideoProcessor(settings=_FakeSettings(backend="auto", xai_key="k"))

    async def boom(self, path, key):
        raise RuntimeError("HTTP 500")

    async def fake_whisper(self, path):
        return _segs((0.0, 1.0, "rescued locally"))

    real = (VideoProcessor._grok_transcribe, VideoProcessor._whisper_transcribe)
    VideoProcessor._grok_transcribe = boom
    VideoProcessor._whisper_transcribe = fake_whisper
    try:
        got = asyncio.run(vp.transcribe_audio("clip.mp4"))
        assert got and got[0].text == "rescued locally"
    finally:
        VideoProcessor._grok_transcribe, VideoProcessor._whisper_transcribe = real


def test_missing_whisper_package_is_not_an_error():
    """The app must still describe on a machine without faster-whisper."""
    import builtins

    vp = VideoProcessor(settings=_FakeSettings(backend="whisper"))
    real_import = builtins.__import__

    def blocked(name, *a, **k):
        if name.startswith("faster_whisper"):
            raise ImportError("not installed")
        return real_import(name, *a, **k)

    builtins.__import__ = blocked
    try:
        assert asyncio.run(vp.transcribe_audio("clip.mp4")) == []
    finally:
        builtins.__import__ = real_import


def test_subtitles_are_preferred_over_transcription():
    """Captions are exact; a transcriber guesses. Order matters."""
    vp = VideoProcessor(settings=_FakeSettings())
    used = []

    async def fake_ytdlp(self, source):
        used.append("subtitles")
        return _segs((0.0, 1.0, "exact text"))

    async def fake_stt(self, path):
        used.append("stt")
        return _segs((0.0, 1.0, "guessed text"))

    real = (VideoProcessor._ytdlp_subtitles, VideoProcessor.transcribe_audio)
    VideoProcessor._ytdlp_subtitles = fake_ytdlp
    VideoProcessor.transcribe_audio = fake_stt
    try:
        got = asyncio.run(vp.get_transcript("https://youtu.be/x"))
        assert used == ["subtitles"], f"transcribed despite captions: {used}"
        assert got[0].text == "exact text"
    finally:
        VideoProcessor._ytdlp_subtitles, VideoProcessor.transcribe_audio = real


def test_transcription_settings_exist_in_both_languages():
    from omni_describer_custom.i18n.strings import EN_STRINGS, MS_STRINGS

    keys = ("settings.transcription", "settings.transcribe_auto",
            "settings.transcribe_whisper", "settings.transcribe_grok",
            "settings.transcribe_off", "settings.transcription_hint",
            "settings.xai_key")
    for lang, table in (("en", EN_STRINGS), ("ms", MS_STRINGS)):
        for key in keys:
            assert table.get(key), f"{lang}: missing {key}"


# ── Cost estimate before spending (v1.6.1) ───────────────────────
#
# A run died mid-way with "HTTP 402: requires at least $1.00 in balance
# for video". The price was never the issue — measured against live
# OpenRouter pricing, a 2-hour film is about $0.10 — the balance FLOOR
# was. Both numbers are now shown before anything is sent.

def _priced(prompt=0.00000037, completion=0.00000125):
    async def fake_price(model):
        return {"prompt": prompt, "completion": completion}
    return fake_price


def test_estimate_scales_with_duration_and_chunks():
    from omni_describer_custom.core import ai_engine

    real = ai_engine.get_model_price
    ai_engine.get_model_price = _priced()
    try:
        one = asyncio.run(ai_engine.estimate_video_cost(60, "m", 600))
        long = asyncio.run(ai_engine.estimate_video_cost(3600, "m", 600))
        assert one["parts"] == 1, one
        assert long["parts"] == 6, long          # 3600 / 600
        assert long["prompt_tokens"] > one["prompt_tokens"] * 50
        assert long["usd"] > one["usd"] > 0
        # Sanity against the live figure this was calibrated on.
        assert 0.0005 < one["usd"] < 0.01, one["usd"]
    finally:
        ai_engine.get_model_price = real


def test_estimate_survives_an_unreachable_price_list():
    """No pricing must not mean no run."""
    from omni_describer_custom.core import ai_engine

    async def no_price(model):
        return {}

    real = ai_engine.get_model_price
    ai_engine.get_model_price = no_price
    try:
        est = asyncio.run(ai_engine.estimate_video_cost(60, "m", 600))
        assert est["priced"] is False
        assert est["usd"] == 0.0
        assert est["prompt_tokens"] > 0, "token estimate is local maths"
    finally:
        ai_engine.get_model_price = real


def test_balance_floor_is_reported_separately_from_cost():
    """$0.10 of work still fails under a $1.00 balance — so the two are
    reported as different things."""
    from omni_describer_custom.core import ai_engine

    async def fake_balance(key):
        return {"total": 10.0, "used": 9.5, "remaining": 0.5}

    real = (ai_engine.get_model_price, ai_engine.get_credit_balance)
    ai_engine.get_model_price = _priced()
    ai_engine.get_credit_balance = fake_balance
    try:
        est = asyncio.run(ai_engine.estimate_video_cost(60, "m", 600, "key"))
        assert est["affordable"] is True, "50 cents covers a $0.001 job"
        assert est["min_balance_ok"] is False, \
            "under the $1.00 video floor, and the run WILL be refused"
    finally:
        ai_engine.get_model_price, ai_engine.get_credit_balance = real


def test_credit_check_failure_is_not_a_blocker():
    from omni_describer_custom.core import ai_engine

    async def boom(key):
        raise RuntimeError("offline")

    real = (ai_engine.get_model_price, ai_engine.get_credit_balance)
    ai_engine.get_model_price = _priced()
    ai_engine.get_credit_balance = boom
    try:
        est = asyncio.run(ai_engine.estimate_video_cost(60, "m", 600, "key"))
        assert "remaining" not in est, "unknown balance must not be faked"
        assert est["usd"] > 0
    finally:
        ai_engine.get_model_price, ai_engine.get_credit_balance = real


def test_pipeline_reports_cost_in_both_languages():
    from omni_describer_custom.i18n.strings import EN_STRINGS, MS_STRINGS

    src = Path("src/omni_describer_custom/ui/main_frame.py").read_text(
        encoding="utf-8")
    assert "estimate_video_cost" in src, "the pipeline never estimates"
    for lang, table in (("en", EN_STRINGS), ("ms", MS_STRINGS)):
        for key in ("cost.estimate", "cost.balance", "cost.too_low"):
            assert table.get(key), f"{lang}: missing {key}"


# ── Full resolution for text-heavy video (v1.6.1) ────────────────

def test_fitting_chunk_keeps_parts_under_the_limit():
    """Shrinking to 360p makes slides and code unreadable, so an
    oversized video can be cut instead — but only if the pieces really
    do fit."""
    from omni_describer_custom.core.ai_engine import GLMProvider

    class FakePath:
        def __init__(self, size):
            self._size = size

        def stat(self):
            return type("S", (), {"st_size": self._size})()

    limit = 50 * 1024 * 1024
    # 100 MB over 600 s = 170 KB/s; 85% of the limit fits ~255 s.
    seconds = GLMProvider._chunk_seconds_to_fit(FakePath(100 * 1024 * 1024),
                                                600.0, limit)
    assert seconds > 0
    bytes_per_second = (100 * 1024 * 1024) / 600.0
    assert seconds * bytes_per_second < limit, \
        "the computed part would still be rejected"


def test_fitting_chunk_gives_up_rather_than_shredding():
    """A huge, short video cannot be split into anything useful; better
    to compress than to send 60 one-second requests."""
    from omni_describer_custom.core.ai_engine import GLMProvider

    class FakePath:
        def stat(self):
            return type("S", (), {"st_size": 400 * 1024 * 1024})()

    assert GLMProvider._chunk_seconds_to_fit(FakePath(), 5.0,
                                             50 * 1024 * 1024) == 0
    assert GLMProvider._chunk_seconds_to_fit(FakePath(), 0.0,
                                             50 * 1024 * 1024) == 0


def test_preserve_resolution_reaches_the_provider():
    from omni_describer_custom.core.ai_engine import AIEngine, GLMProvider

    assert "preserve_resolution" in inspect.signature(
        GLMProvider.describe_video_full).parameters
    assert "preserve_resolution" in inspect.signature(
        AIEngine.describe_video_full).parameters
    src = Path("src/omni_describer_custom/ui/main_frame.py").read_text(
        encoding="utf-8")
    assert "preserve_resolution=bool(self.settings.get(" in src, \
        "the setting never reaches the engine"


if __name__ == "__main__":
    check("no transcript adds nothing", test_no_transcript_adds_nothing)
    check("block carries words and the rule",
          test_block_carries_the_words_and_the_rule)
    check("block limited to the part window",
          test_block_is_limited_to_the_part_window)
    check("timestamps shifted to part-local time",
          test_timestamps_are_shifted_into_part_local_time)
    check("long transcript trimmed, ends kept",
          test_long_transcript_is_trimmed_not_dropped)
    check("url and file take different routes",
          test_url_and_file_take_different_routes)
    check("transcript failure never breaks a run",
          test_transcript_failure_never_breaks_a_run)
    check("ytdlp path accepts urls", test_ytdlp_path_accepts_urls)
    check("engine accepts a transcript", test_engine_accepts_a_transcript)
    check("transcript only to providers that take one",
          test_transcript_only_goes_to_providers_that_take_one)
    check("pipeline fetches the transcript",
          test_pipeline_fetches_the_transcript)
    check("transcript phase announced EN+BM",
          test_transcript_phase_is_announced_in_both_languages)
    check("transcription can be turned off",
          test_transcription_can_be_turned_off)
    check("grok skipped without a key", test_grok_is_skipped_without_a_key)
    check("auto falls back to whisper",
          test_auto_falls_back_to_whisper_when_no_key)
    check("auto prefers grok with a key",
          test_auto_prefers_grok_when_a_key_exists)
    check("grok failure falls back to whisper",
          test_grok_failure_falls_back_to_whisper_in_auto)
    check("missing whisper package is not an error",
          test_missing_whisper_package_is_not_an_error)
    check("subtitles preferred over transcription",
          test_subtitles_are_preferred_over_transcription)
    check("transcription settings exist EN+BM",
          test_transcription_settings_exist_in_both_languages)
    check("estimate scales with duration and chunks",
          test_estimate_scales_with_duration_and_chunks)
    check("estimate survives no price list",
          test_estimate_survives_an_unreachable_price_list)
    check("balance floor reported apart from cost",
          test_balance_floor_is_reported_separately_from_cost)
    check("credit check failure is not a blocker",
          test_credit_check_failure_is_not_a_blocker)
    check("pipeline reports cost EN+BM",
          test_pipeline_reports_cost_in_both_languages)
    check("fitting chunk keeps parts under the limit",
          test_fitting_chunk_keeps_parts_under_the_limit)
    check("fitting chunk gives up rather than shredding",
          test_fitting_chunk_gives_up_rather_than_shredding)
    check("preserve resolution reaches the provider",
          test_preserve_resolution_reaches_the_provider)
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
