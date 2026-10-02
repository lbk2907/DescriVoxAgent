"""Regression round 31: a transcript that says the same thing twice.

Since v1.6.8 the app spends the local transcript: it tells the model
how many words fit in each silent gap. A transcript that changes
between runs changes the budget with it, so the decode settings
stopped being a matter of taste and became a measured choice.

Benchmarked across SEVEN genuinely different videos, two runs each
(tools/whisper_bench.py) — a Malay news broadcast, an English talk, a
cooking vlog with a music bed, two Indonesian cartoons, an amateur
outdoor clip, and two text-to-speech clips with known speech times:

                        not deterministic   clean Malay   the music clip
    old defaults             3 of 7             35%       invented 17
                                                          lines of Korean
    these settings           0 of 7             96%       correctly found
                                                          silence

An earlier, weaker benchmark took three cuts from ONE video and made
the `small` model look like the answer. On genuinely separate videos
that reversed — `small` produced twelve hallucinated segments where
`base` produced two — so the model was left alone and only the decode
settings changed. Measuring one video three times measures one video.

Two kinds of invention, and only one is caught by the filter:

  repeat loop     "Mememememe..." for 27 seconds, compression 29.7
                  -> dropped here; real lines score 1.7 to 2.8
  music fantasy   Korean text over an English cooking video,
                  compression 1.8 to 1.9, indistinguishable by ratio
                  -> prevented instead by the VAD, which never lets
                     music reach the model
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import sys
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

from omni_describer_custom.core.video_processor import (  # noqa: E402
    WHISPER_COMPRESSION_LIMIT, WHISPER_DECODE, VideoProcessor)

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
    def __init__(self, text, compression_ratio=2.0, start=0.0, end=1.0):
        self.text, self.compression_ratio = text, compression_ratio
        self.start, self.end = start, end


# ── The settings that stop the drift ─────────────────────────────

def test_the_temperature_fallback_is_off():
    """The single source of run-to-run drift.

    The library default is a LIST of temperatures and every value above
    zero samples, so a hard passage is re-decoded at random until it
    passes a threshold. Same file, three runs, old settings: first
    speech at 30.0s, 30.0s, then 0.0s.
    """
    temperature = WHISPER_DECODE.get("temperature")
    assert temperature == 0.0, f"temperature is {temperature!r}"
    assert not isinstance(temperature, (list, tuple)), (
        "a sequence here IS the fallback; any element above 0.0 samples")


def test_one_bad_guess_cannot_steer_the_rest():
    assert WHISPER_DECODE.get("condition_on_previous_text") is False


def test_music_never_reaches_the_model():
    """Whisper transcribes music into confident nonsense.

    Seventeen Korean segments on an English cooking video, and their
    compression ratios were normal, so no filter could have caught
    them. The VAD decides what is speech before Whisper sees it.
    """
    assert WHISPER_DECODE.get("vad_filter") is True
    params = WHISPER_DECODE.get("vad_parameters") or {}
    assert params.get("threshold") == 0.3, (
        "0.5 is the library default and was too strict for the quiet "
        "passages in the cartoon and news audio")
    assert params.get("speech_pad_ms", 0) >= 200, (
        "without padding the first and last syllable of a line are cut")


def test_the_settings_actually_reach_whisper():
    """A constant nobody passes is decoration."""
    text = (SRC / "core" / "video_processor.py").read_text(encoding="utf-8")
    assert "**WHISPER_DECODE" in text, (
        "WHISPER_DECODE is defined but never handed to transcribe()")
    call = text.split("model.transcribe(")[1][:200]
    assert "WHISPER_DECODE" in call, call


# ── The filter, and what it deliberately does not catch ──────────

def test_a_repeat_loop_is_dropped():
    """27 seconds of "Mememememe" scored 29.7 on a real run."""
    assert VideoProcessor._looks_hallucinated(
        Seg("Me" * 150, compression_ratio=29.7)) is True


def test_real_speech_is_kept():
    for ratio in (1.7, 2.0, 2.3):
        assert VideoProcessor._looks_hallucinated(
            Seg("Kabar kamu gimana, Ocong?", compression_ratio=ratio)) is False, ratio


def test_a_real_line_survives_its_windows_ratio():
    """v1.8.5: faster-whisper gives every segment its 30 s WINDOW's
    ratio. On Ocong the whole first window scored 2.79 because one
    character says "Bra, bra, bra, bra", and all eight real lines in it
    were dropped. The ratio is judged per line now."""
    window = 2.79
    for line in ("Kabar kamu gimana, Ocong?", "Aku kangen sama kamu, Ocong.",
                 "Bra, bra, bra, bra, tolong, berhenti, talinya putus berhenti."):
        assert VideoProcessor._looks_hallucinated(
            Seg(line, compression_ratio=window)) is False, line


def test_the_limit_is_whispers_own():
    assert WHISPER_COMPRESSION_LIMIT == 2.4


def test_a_segment_with_no_ratio_is_kept():
    """A backend that reports no ratio must not lose every segment."""
    class Bare:
        text = "hello"
    assert VideoProcessor._looks_hallucinated(Bare()) is False
    assert VideoProcessor._looks_hallucinated(
        Seg("hello", compression_ratio=None)) is False
    assert VideoProcessor._looks_hallucinated(
        Seg("hello", compression_ratio="broken")) is False


def test_the_filter_is_applied_and_counted():
    text = (SRC / "core" / "video_processor.py").read_text(encoding="utf-8")
    body = text.split("def _whisper_transcribe")[1][:2500]
    assert "_looks_hallucinated" in body, (
        "the filter exists but nothing calls it")
    assert "dropped" in body, (
        "segments are discarded without saying how many, so a filter "
        "that eats a whole transcript would look like silence")


def test_the_reason_for_each_setting_is_written_down():
    """A tuned constant with no measurement beside it gets 'improved'.

    beam_size=5 with the VAD was tried once and made things worse;
    without the numbers in the file, the next person tries it again.
    """
    text = (SRC / "core" / "video_processor.py").read_text(encoding="utf-8")
    block = text.split("WHISPER_DECODE")[0][-2000:]
    for evidence in ("7", "35%", "Korean"):
        assert evidence in block, (
            f"the measurement behind these settings does not mention "
            f"{evidence!r}")


if __name__ == "__main__":
    print("Round 31: a transcript that says the same thing twice\n")
    check("the temperature fallback is off",
          test_the_temperature_fallback_is_off)
    check("one bad guess cannot steer the rest",
          test_one_bad_guess_cannot_steer_the_rest)
    check("music never reaches the model", test_music_never_reaches_the_model)
    check("the settings actually reach whisper",
          test_the_settings_actually_reach_whisper)
    check("a repeat loop is dropped", test_a_repeat_loop_is_dropped)
    check("real speech is kept", test_real_speech_is_kept)
    check("a real line survives its window's ratio", test_a_real_line_survives_its_windows_ratio)
    check("the limit is whisper's own", test_the_limit_is_whispers_own)
    check("a segment with no ratio is kept",
          test_a_segment_with_no_ratio_is_kept)
    check("the filter is applied and counted",
          test_the_filter_is_applied_and_counted)
    check("the reason for each setting is written down",
          test_the_reason_for_each_setting_is_written_down)
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
