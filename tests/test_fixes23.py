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
    assert "vp.get_transcript(source)" in src, \
        "the pipeline no longer fetches a transcript"
    assert "transcript=transcript" in src, \
        "the transcript is fetched but never passed to the engine"


def test_transcript_phase_is_announced_in_both_languages():
    from omni_describer_custom.i18n.strings import EN_STRINGS, MS_STRINGS

    for lang, table in (("en", EN_STRINGS), ("ms", MS_STRINGS)):
        for key in ("process.transcript_ok", "process.transcript_none",
                    "video.phase_transcript"):
            assert table.get(key), f"{lang}: missing {key}"
        assert "{count}" in table["process.transcript_ok"]


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
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
