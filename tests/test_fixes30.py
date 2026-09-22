"""Regression round 30: descriptions that fit the silence (v1.6.8).

The owner's hunch was that the model must not be getting the dialogue,
or it would not write over it. Testing that turned up something more
specific, and partly proved him right.

The transcript IS sent — 921 characters of timed lines for a 50-second
clip, with an explicit instruction to use the gaps. And the model's
PLACEMENT was mostly good: in two real runs it put most cues in the
quiet stretch and only one or two on top of speech.

What was missing was arithmetic. Nothing ever told the model how much
room a gap holds, so it picked a sensible moment and then wrote text
far too long for it. Measured on a real 50-second clip: about 77 words
of silence available, 97 words written in one run and 99 in the next.
A 36-word cue takes ten seconds to speak at this user's 1.5x and was
given a flat three-second slot.

Two mechanisms, no pleading (AGENTS.md pitfall 14):

  - the prompt now lists each silent gap and how many words fit in it,
    scaled by the user's own speaking rate;
  - a cue lasts as long as its text takes to say, never overlapping
    the next one, and anything still landing on speech is named.

KNOWN LIMIT, measured and not fixed here: the local Whisper transcript
is unreliable on hard audio. The same file, same model, three runs:
first speech reported at 30.0s, 30.0s, then 0.0s; coverage 40%, 32%,
93%. The gap budget is only ever as good as that. Raising beam_size
and enabling the VAD filter was tried and made it WORSE (coverage fell
to 20% and speech was dropped entirely), so nothing was changed.
"""
import io
import json
import re
import sys
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

from omni_describer_custom.core.ai_engine import (  # noqa: E402
    build_transcript_block)
from omni_describer_custom.core.timeline_io import (  # noqa: E402
    MIN_CUE_SECONDS, WORDS_PER_SECOND_AT_1X, silent_gaps, speaking_seconds)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "omni_describer_custom"

ok_count = 0
fail_count = 0


def check(name, fn):
    global ok_count, fail_count
    try:
        fn()
        print(f"  OK   {name}")
        ok_count += 1
    except Exception as e:
        print(f"  FAIL {name}: {e}")
        traceback.print_exc()
        fail_count += 1


class Seg:
    def __init__(self, start, end, text="words"):
        self.start, self.end, self.text = start, end, text


# The speech pattern of the real test clip, as Whisper reported it in
# the run that produced the over-long descriptions.
CLIP = [Seg(30, 32), Seg(32, 34), Seg(34, 37), Seg(38, 40),
        Seg(40, 41), Seg(41, 44), Seg(44, 47), Seg(47, 50)]


# ── How long speech actually takes ───────────────────────────────

def test_a_long_description_takes_longer_than_three_seconds():
    """The flat 3s slot is what let a 36-word cue overrun by ten."""
    thirty_six = " ".join(["word"] * 36)
    assert speaking_seconds(thirty_six, 1.0) > 10.0
    assert speaking_seconds(thirty_six, 1.5) > 8.0


def test_speaking_time_follows_the_users_speed():
    text = " ".join(["word"] * 30)
    slow = speaking_seconds(text, 1.0)
    fast = speaking_seconds(text, 1.5)
    assert fast < slow, (fast, slow)
    assert abs(slow / fast - 1.5) < 0.01, "the rate does not scale linearly"


def test_a_very_short_cue_still_gets_a_readable_length():
    assert speaking_seconds("Yes.", 2.0) == MIN_CUE_SECONDS


def test_a_nonsense_speed_does_not_produce_nonsense_timing():
    for bad in (0, -1, None, "fast"):
        try:
            value = speaking_seconds("one two three", bad)
        except (TypeError, ValueError):
            continue  # rejecting it outright is fine too
        assert value > 0, f"speed {bad!r} gave {value}"


# ── Where the silence actually is ────────────────────────────────

def test_gaps_are_the_spaces_between_speech():
    gaps = silent_gaps(CLIP, start=0.0, end=50.0)
    assert gaps[0] == (0.0, 30.0), gaps
    assert all(b > a for a, b in gaps)


def test_slivers_between_lines_are_not_offered():
    """A half-second gap holds no description worth making."""
    gaps = silent_gaps(CLIP, start=0.0, end=50.0, min_seconds=1.0)
    assert all(b - a >= 1.0 for a, b in gaps), gaps


def test_overlapping_speech_does_not_invent_a_gap():
    overlapping = [Seg(0, 10), Seg(5, 20), Seg(18, 30)]
    gaps = silent_gaps(overlapping, start=0.0, end=30.0)
    assert gaps == [], f"invented silence inside continuous speech: {gaps}"


def test_no_transcript_means_no_claim_about_silence():
    assert silent_gaps([], start=0.0, end=50.0) == [(0.0, 50.0)]


# ── What the model is told ───────────────────────────────────────

def test_the_prompt_states_a_word_budget():
    block = build_transcript_block(CLIP, start=0.0, end=50.0,
                                   words_per_second=2.5)
    assert "HOW MUCH ROOM" in block, "the model is told nothing about room"
    assert re.search(r"about \d+ words fit here", block), block[-400:]
    assert re.search(r"fit in about \d+ words", block), (
        "no overall budget is given")


def test_the_budget_matches_the_silence_available():
    block = build_transcript_block(CLIP, start=0.0, end=50.0,
                                   words_per_second=2.5)
    total = int(re.search(r"fit in about (\d+) words", block).group(1))
    expected = sum(int((b - a) * 2.5)
                   for a, b in silent_gaps(CLIP, 0.0, 50.0))
    assert total == expected, (total, expected)
    # The clip that started this: ~77 words of room, 97 words written.
    assert 60 < total < 90, f"{total} words is not the measured figure"


def test_a_faster_voice_is_given_a_bigger_budget():
    slow = build_transcript_block(CLIP, start=0.0, end=50.0,
                                  words_per_second=2.5)
    fast = build_transcript_block(CLIP, start=0.0, end=50.0,
                                  words_per_second=3.75)
    slow_total = int(re.search(r"fit in about (\d+) words", slow).group(1))
    fast_total = int(re.search(r"fit in about (\d+) words", fast).group(1))
    assert fast_total > slow_total, (slow_total, fast_total)


def test_wall_to_wall_speech_is_said_so_plainly():
    block = build_transcript_block([Seg(0, 50)], start=0.0, end=50.0)
    assert "NO SILENCE" in block, (
        "a part with no gaps still offers gaps to write into")


def test_the_budget_is_left_out_when_the_range_is_unknown():
    """Without an end time the gaps cannot be computed honestly."""
    block = build_transcript_block(CLIP, start=0.0, end=None)
    assert "HOW MUCH ROOM" not in block


def test_the_rate_reaches_the_engine_from_the_users_settings():
    text = (SRC / "ui" / "main_frame.py").read_text(encoding="utf-8")
    assert "_tts_words_per_second" in text
    assert "words_per_second" in text, "the rate never reaches the engine"
    engine = (SRC / "core" / "ai_engine.py").read_text(encoding="utf-8")
    assert "words_per_second=self.words_per_second" in engine, (
        "the transcript block is built with the default rate, not the "
        "user's")


# ── Cue timing, and saying when it still does not fit ────────────

def test_a_cue_lasts_as_long_as_its_words():
    text = (SRC / "ui" / "main_frame.py").read_text(encoding="utf-8")
    assert "secs + 3.0" not in text, (
        "a cue is still given a flat three seconds regardless of length")
    assert "_time_cues_by_length" in text


def test_cues_never_overlap_each_other():
    """Two descriptions at once is no description.

    Seen in a real run: cue 1 ran 0-3s and cue 2 started at 2s.
    """
    text = (SRC / "ui" / "main_frame.py").read_text(encoding="utf-8")
    body = text.split("def _time_cues_by_length")[1][:2000]
    assert "min(end" in body, (
        "nothing stops a long cue running into the next one")


def test_collisions_with_speech_are_reported_not_hidden():
    text = (SRC / "ui" / "main_frame.py").read_text(encoding="utf-8")
    assert "_report_cue_collisions" in text
    for code in ("en", "ms"):
        data = json.loads((SRC / "i18n" / "locales" / f"{code}.json").read_text(
            encoding="utf-8"))
        message = data.get("process.cues_overrun", "")
        assert message, f"{code}.json has no process.cues_overrun"
        for field in ("{count}", "{total}", "{where}"):
            assert field in message, f"{code}: {field} missing"


def test_the_transcript_variable_exists_on_every_path():
    """It was assigned only under "if video_mode" and read under
    "if fast_mode" — a NameError that would have killed every
    fast-mode job with an unexplained "Processing error"."""
    import ast
    source = (SRC / "ui" / "main_frame.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_process_video")

    def branch_depth(target: int) -> int:
        found = []

        def walk(node, depth):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.If):
                    for branch in (child.body, child.orelse):
                        for stmt in branch:
                            if stmt.lineno <= target <= getattr(
                                    stmt, "end_lineno", stmt.lineno):
                                walk(stmt, depth + 1)
                                return
                lo = getattr(child, "lineno", 0)
                hi = getattr(child, "end_lineno", 0)
                if lo <= target <= hi:
                    walk(child, depth)
            found.append(depth)

        walk(fn, 0)
        return found[0] if found else 0

    assigns = [n.lineno for n in ast.walk(fn)
               if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
               and n.id == "transcript"]
    uses = [n.lineno for n in ast.walk(fn)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
            and n.id == "transcript"]
    assert assigns and uses
    first = min(assigns)
    assert branch_depth(first) == 0, (
        "the first assignment to 'transcript' is inside a branch, so a "
        "path that skips it reads an undefined name")
    assert all(u > first for u in uses), "a use precedes the assignment"


if __name__ == "__main__":
    print("Round 30: descriptions that fit the silence\n")
    check("a long description takes longer than three seconds",
          test_a_long_description_takes_longer_than_three_seconds)
    check("speaking time follows the user's speed",
          test_speaking_time_follows_the_users_speed)
    check("a very short cue still gets a readable length",
          test_a_very_short_cue_still_gets_a_readable_length)
    check("a nonsense speed does not produce nonsense timing",
          test_a_nonsense_speed_does_not_produce_nonsense_timing)
    check("gaps are the spaces between speech",
          test_gaps_are_the_spaces_between_speech)
    check("slivers between lines are not offered",
          test_slivers_between_lines_are_not_offered)
    check("overlapping speech does not invent a gap",
          test_overlapping_speech_does_not_invent_a_gap)
    check("no transcript means no claim about silence",
          test_no_transcript_means_no_claim_about_silence)
    check("the prompt states a word budget",
          test_the_prompt_states_a_word_budget)
    check("the budget matches the silence available",
          test_the_budget_matches_the_silence_available)
    check("a faster voice is given a bigger budget",
          test_a_faster_voice_is_given_a_bigger_budget)
    check("wall-to-wall speech is said so plainly",
          test_wall_to_wall_speech_is_said_so_plainly)
    check("the budget is left out when the range is unknown",
          test_the_budget_is_left_out_when_the_range_is_unknown)
    check("the rate reaches the engine from the user's settings",
          test_the_rate_reaches_the_engine_from_the_users_settings)
    check("a cue lasts as long as its words",
          test_a_cue_lasts_as_long_as_its_words)
    check("cues never overlap each other", test_cues_never_overlap_each_other)
    check("collisions with speech are reported, not hidden",
          test_collisions_with_speech_are_reported_not_hidden)
    check("the transcript variable exists on every path",
          test_the_transcript_variable_exists_on_every_path)
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
