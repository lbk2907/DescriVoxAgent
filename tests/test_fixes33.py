"""Regression round 33: hearing when a screen reader stops (v1.7.1).

The narration hold pauses the video while a description is spoken. For
a screen-reader voice that needs the END of the speech, and NVDA gives
no usable signal on the version this user runs:

  - Prism's NVDA backend reports supports_is_speaking False;
  - NVDA's synchronous speakSsml HUNG on the first call on NVDA 2025.3,
    a race fixed only in 2026.2 (nvaccess/nvda#20220);
  - isSpeaking arrives in NVDA 2026.3, not yet released.

core/audio_meter.py listens instead: the reader's process falls silent
when the sentence ends, and Windows meters every process's audio. That
asks nothing of NVDA, so it holds on every NVDA version.

These checks run against a scripted fake meter so the logic is tested
on any machine, NVDA or not. The real-NVDA measurements live in round
26. Three faults were found building this, each pinned here:

  1. Default output device only -> found no NVDA session at all. NVDA
     here is routed to device 0; the Windows default is device 1.
  2. tasklist to find the process -> 0.83 s, longer than a three-word
     sentence lasts at this user's NVDA rate, so short descriptions
     were reported as "no sound".
  3. Meter looked up AFTER speaking -> the same miss, from the order.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import sys
import time
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

from omni_describer_custom.core import audio_meter  # noqa: E402

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


class FakeMeter:
    """Peak level follows a script of (seconds_from_start, level)."""

    def __init__(self, script):
        self.script = sorted(script)
        self.t0 = None

    def GetPeakValue(self):
        if self.t0 is None:
            self.t0 = time.monotonic()
        now = time.monotonic() - self.t0
        level = 0.0
        for at, value in self.script:
            if now >= at:
                level = value
        return level


class Fast:
    """Shrink the timings so a test takes a fraction of a second."""

    def __init__(self, **overrides):
        self.overrides = {"START_GRACE": 0.3, "SILENCE_TO_FINISH": 0.15,
                          "_POLL": 0.01, **overrides}
        self.saved = {}

    def __enter__(self):
        for key, value in self.overrides.items():
            self.saved[key] = getattr(audio_meter, key)
            setattr(audio_meter, key, value)
        return self

    def __exit__(self, *exc):
        for key, value in self.saved.items():
            setattr(audio_meter, key, value)


def run(script, timeout=3.0, speak_result=True, meters=None):
    """Drive ReaderMeter with fake sessions; return (outcome, seconds)."""
    fake = [FakeMeter(script)] if meters is None else meters
    original = audio_meter._meters
    audio_meter._meters = lambda names: list(fake)
    try:
        meter = audio_meter.ReaderMeter(("nvda.exe",))
        t0 = time.monotonic()
        outcome = meter._listen(list(fake), timeout) if speak_result is None \
            else meter.speak_and_wait(lambda: speak_result, timeout)
        return outcome, time.monotonic() - t0
    finally:
        audio_meter._meters = original


# ── The four answers ─────────────────────────────────────────────

def test_speech_then_silence_is_finished():
    with Fast():
        outcome, secs = run([(0.0, 0.0), (0.05, 0.3), (0.5, 0.0)])
    assert outcome == "finished", outcome
    assert 0.5 <= secs < 1.2, f"finished after {secs:.2f}s"


def test_a_pause_at_a_comma_does_not_end_the_sentence():
    """A reader breathes at punctuation; that is not the end."""
    with Fast(SILENCE_TO_FINISH=0.3):
        # sound, a 0.15 s pause, sound again, then real silence
        outcome, secs = run([(0.0, 0.3), (0.2, 0.0), (0.35, 0.3),
                             (0.8, 0.0)])
    assert outcome == "finished", outcome
    assert secs >= 0.8, (
        f"ended at {secs:.2f}s, inside the comma pause — the video would "
        f"resume before the second half of the sentence")


def test_hearing_nothing_says_so():
    """Muted, routed elsewhere, odd audio path: fall back, do not hang."""
    with Fast():
        outcome, secs = run([(0.0, 0.0)])
    assert outcome == "no-sound", outcome
    assert secs < 1.0, f"waited {secs:.2f}s for sound that never came"


def test_a_reader_that_never_stops_is_cut_off_at_the_limit():
    """The player must never freeze on a meter that stays loud."""
    with Fast():
        outcome, secs = run([(0.0, 0.3)], timeout=0.6)
    assert outcome == "timeout", outcome
    assert secs < 1.0, f"overran the limit: {secs:.2f}s"


def test_a_failed_speak_is_reported_not_waited_on():
    with Fast():
        outcome, _ = run([(0.0, 0.3)], speak_result=False)
    assert outcome == "not-spoken", outcome


# ── The three faults found building it ───────────────────────────

def test_the_meter_is_found_before_the_speech_starts():
    """Fault 3: looking it up afterwards missed short sentences."""
    order = []
    original = audio_meter._meters

    def fake_meters(names):
        order.append("meters")
        return [FakeMeter([(0.0, 0.0), (0.02, 0.3), (0.2, 0.0)])]

    audio_meter._meters = fake_meters
    try:
        with Fast():
            audio_meter.ReaderMeter(("nvda.exe",)).speak_and_wait(
                lambda: order.append("speak") or True, 2.0)
    finally:
        audio_meter._meters = original
    assert order[:2] == ["meters", "speak"], (
        f"order was {order}; the meter must be ready before the speech")


def test_no_slow_process_listing_in_the_hot_path():
    """Fault 2: tasklist took 0.83 s, longer than a short sentence."""
    # Checked on the syntax tree, not the text: the first version of
    # this test searched for the word and failed on the docstring that
    # explains WHY tasklist was removed.
    import ast
    text = (SRC / "core" / "audio_meter.py").read_text(encoding="utf-8")
    tree = ast.parse(text)
    imported = {alias.name for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names}
    imported |= {node.module for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom) and node.module}
    assert "subprocess" not in imported, (
        "the meter spawns a process to find the reader again")
    assert "QueryFullProcessImageNameW" in text, (
        "process names are not read straight from Win32")


def test_every_output_device_is_searched():
    """Fault 1: NVDA on device 0, the Windows default on device 1."""
    text = (SRC / "core" / "audio_meter.py").read_text(encoding="utf-8")
    body = text.split("def _meters(")[1].split("class ReaderMeter")[0]
    assert "EnumAudioEndpoints" in body, (
        "only the default device is searched; a reader routed to its "
        "own device is never found")
    assert "GetDefaultAudioEndpoint" not in body


def test_a_session_that_appears_late_is_still_found():
    """A reader has no session until it first speaks since starting."""
    calls = {"n": 0}
    original = audio_meter._meters

    def late(names):
        calls["n"] += 1
        return [] if calls["n"] < 3 else [
            FakeMeter([(0.0, 0.3), (0.2, 0.0)])]

    audio_meter._meters = late
    try:
        with Fast(START_GRACE=1.0):
            outcome = audio_meter.ReaderMeter(("nvda.exe",)).speak_and_wait(
                lambda: True, 3.0)
    finally:
        audio_meter._meters = original
    assert outcome == "finished", outcome


# ── Safe everywhere ──────────────────────────────────────────────

def test_without_audio_metering_it_says_so():
    saved = audio_meter._AVAILABLE
    audio_meter._AVAILABLE = False
    try:
        outcome = audio_meter.ReaderMeter(("nvda.exe",)).speak_and_wait(
            lambda: True, 1.0)
    finally:
        audio_meter._AVAILABLE = saved
    assert outcome == "no-meter", outcome


def test_a_meter_that_throws_does_not_throw_out():
    class Broken:
        def GetPeakValue(self):
            raise OSError("device unplugged mid-sentence")

    with Fast():
        outcome, _ = run(None, meters=[Broken()])
    assert outcome == "no-meter", outcome


def test_prism_falls_back_to_an_estimate_when_it_hears_nothing():
    """"no-sound" must still pause the video for about the right time."""
    text = (SRC / "core" / "speech.py").read_text(encoding="utf-8")
    body = text.split("def speak_and_wait")[1][:3000]
    assert "_estimate_seconds" in body, "no fallback when the meter is deaf"
    assert '"no-sound"' in body or "no-sound" in body


def test_only_named_readers_are_metered():
    """A process name is not claimed without a reason to believe it."""
    from omni_describer_custom.core.speech import _READER_PROCESSES
    assert _READER_PROCESSES.get("NVDA") == ("nvda.exe",)
    for name, images in _READER_PROCESSES.items():
        assert all(i.endswith(".exe") for i in images), (name, images)


if __name__ == "__main__":
    print("Round 33: hearing when a screen reader stops\n")
    check("speech then silence is finished",
          test_speech_then_silence_is_finished)
    check("a pause at a comma does not end the sentence",
          test_a_pause_at_a_comma_does_not_end_the_sentence)
    check("hearing nothing says so", test_hearing_nothing_says_so)
    check("a reader that never stops is cut off at the limit",
          test_a_reader_that_never_stops_is_cut_off_at_the_limit)
    check("a failed speak is reported, not waited on",
          test_a_failed_speak_is_reported_not_waited_on)
    check("the meter is found before the speech starts",
          test_the_meter_is_found_before_the_speech_starts)
    check("no slow process listing in the hot path",
          test_no_slow_process_listing_in_the_hot_path)
    check("every output device is searched",
          test_every_output_device_is_searched)
    check("a session that appears late is still found",
          test_a_session_that_appears_late_is_still_found)
    check("without audio metering it says so",
          test_without_audio_metering_it_says_so)
    check("a meter that throws does not throw out",
          test_a_meter_that_throws_does_not_throw_out)
    check("prism falls back to an estimate when it hears nothing",
          test_prism_falls_back_to_an_estimate_when_it_hears_nothing)
    check("only named readers are metered",
          test_only_named_readers_are_metered)
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
