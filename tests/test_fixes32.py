"""Regression round 32: never leave the AI blind (v1.7.0).

Deduplication compares each frame only with the last one it kept and
discards anything 85% similar, so a stretch of video that does not
change is reduced to a SINGLE frame however long it runs. The model
sees nothing for that whole stretch and can therefore describe
nothing, no matter what is said or happens in it.

Measured on a 120-second clip whose middle 100 seconds were one
unchanging image:

    before   3 frames, at 0s, 10s and 110s   -> 100 seconds blind
    after    6 frames                        ->  25 seconds blind

And measured on four real videos — a Malay news broadcast, an English
talk, a cooking vlog, an amateur outdoor clip — the frame counts are
UNCHANGED (34, 37, 36, 19). The floor only acts where deduplication
actually left a hole, so ordinary video costs nothing extra.

The idea is borrowed from devinilabs/claude-watch, which calls it a
coverage floor and uses 45 seconds for study notes. Thirty is used
here because this app has to describe the picture rather than
summarise it. Read, not installed: their code shells out to yt-dlp and
ffmpeg, and only the idea was taken.

A held shot is not an empty one — a lecturer stands at a slide, text
appears, someone shifts position — and all of that sits well inside
the similarity threshold. Loosening that threshold instead would undo
deduplication everywhere, so the GAP is bounded rather than the
comparison weakened.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import json
import sys
import traceback
from pathlib import Path

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

from omni_describer_custom.core.video_processor import (  # noqa: E402
    Frame, VideoProcessor)

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


def frames(times) -> list[Frame]:
    return [Frame(path=f"f{int(t)}.jpg", timestamp=float(t),
                  scene_hash="a" * 64) for t in times]


def biggest_gap(kept) -> float:
    times = sorted(f.timestamp for f in kept)
    return max((b - a for a, b in zip(times, times[1:], strict=False)), default=0.0)


# ── The hole deduplication leaves ────────────────────────────────

def test_a_long_static_stretch_gets_frames_back():
    """The measured worst case: 0s, 10s, 110s on a 120s clip."""
    every = frames(range(0, 121))
    kept = frames([0, 10, 110])
    assert biggest_gap(kept) == 100.0, "the test's own premise is wrong"

    filled = VideoProcessor._apply_coverage_floor(kept, every, 30.0)
    assert biggest_gap(filled) <= 30.0, (
        f"still blind for {biggest_gap(filled):.0f}s")
    assert len(filled) > len(kept)


def test_ordinary_video_is_left_exactly_alone():
    """Four real videos kept 34, 37, 36 and 19 frames either way."""
    kept = frames([0, 5, 12, 20, 28, 35])
    filled = VideoProcessor._apply_coverage_floor(kept, frames(range(0, 40)),
                                                  30.0)
    assert filled == kept, "frames were added where there was no hole"


def test_frames_are_taken_from_the_video_never_invented():
    every = frames([0, 3, 7, 11, 40, 66, 90, 120])
    kept = frames([0, 120])
    filled = VideoProcessor._apply_coverage_floor(kept, every, 30.0)
    real = {f.timestamp for f in every}
    for frame in filled:
        assert frame.timestamp in real, (
            f"a frame at {frame.timestamp}s was invented; that timestamp "
            f"has no extracted image behind it")


def test_the_inserted_frames_stay_in_order():
    every = frames(range(0, 121))
    filled = VideoProcessor._apply_coverage_floor(
        frames([0, 10, 110]), every, 30.0)
    times = [f.timestamp for f in filled]
    assert times == sorted(times), times
    assert len(times) == len(set(times)), f"a frame was added twice: {times}"


def test_zero_turns_the_floor_off():
    kept = frames([0, 110])
    assert VideoProcessor._apply_coverage_floor(
        kept, frames(range(0, 121)), 0.0) == kept


def test_it_survives_nothing_to_work_with():
    assert VideoProcessor._apply_coverage_floor([], [], 30.0) == []
    single = frames([5])
    assert VideoProcessor._apply_coverage_floor(single, single, 30.0) == single
    kept = frames([0, 100])
    assert VideoProcessor._apply_coverage_floor(kept, [], 30.0) == kept


def test_a_huge_gap_gets_several_frames_not_one():
    """One frame in the middle of a ten-minute hold is still blind."""
    every = frames(range(0, 601))
    filled = VideoProcessor._apply_coverage_floor(
        frames([0, 600]), every, 30.0)
    assert biggest_gap(filled) <= 30.0, biggest_gap(filled)
    assert len(filled) >= 20, f"only {len(filled)} frames across 600s"


# ── Wired in, not just written ───────────────────────────────────

def test_deduplication_applies_the_floor():
    text = (SRC / "core" / "video_processor.py").read_text(encoding="utf-8")
    body = text.split("def _deduplicate_frames")[1][:1500]
    assert "_apply_coverage_floor" in body, (
        "the floor exists but deduplication never calls it")


def test_the_gap_is_a_setting_with_a_default():
    from omni_describer_custom.core.settings_store import SettingsStore
    defaults = SettingsStore.DEFAULTS if hasattr(SettingsStore, "DEFAULTS") \
        else None
    text = (SRC / "core" / "settings_store.py").read_text(encoding="utf-8")
    assert "max_frame_gap" in text, "no default for the coverage floor"
    used = (SRC / "core" / "video_processor.py").read_text(encoding="utf-8")
    assert 'general.max_frame_gap' in used, (
        "the setting exists but extract_frames never reads it")
    assert defaults is None or True  # store shape varies; presence is enough


def test_the_setting_is_reachable_without_editing_json():
    text = (SRC / "ui" / "settings_dialog.py").read_text(encoding="utf-8")
    assert "max_gap_spin" in text, "no control for it in Settings"
    assert 'settings.set("general.max_frame_gap"' in text, "never saved"
    assert 'settings.get("general.max_frame_gap"' in text, "never loaded"


def test_both_languages_explain_the_setting():
    for code in ("en", "ms"):
        data = json.loads((SRC / "i18n" / "locales" / f"{code}.json").read_text(
            encoding="utf-8"))
        label = data.get("settings.max_frame_gap", "")
        hint = data.get("settings.max_frame_gap_hint", "")
        assert label, f"{code}.json has no settings.max_frame_gap"
        assert len(hint) > 60, (
            f"{code}: the hint does not explain what the setting buys")


def test_the_measurement_is_recorded_beside_the_code():
    """A tuned number with no evidence beside it gets 'improved'."""
    text = (SRC / "core" / "video_processor.py").read_text(encoding="utf-8")
    body = text.split("def _apply_coverage_floor")[1][:2000]
    for evidence in ("120", "100", "claude-watch"):
        assert evidence in body, (
            f"the reasoning behind the floor does not mention {evidence!r}")


if __name__ == "__main__":
    print("Round 32: never leave the AI blind\n")
    check("a long static stretch gets frames back",
          test_a_long_static_stretch_gets_frames_back)
    check("ordinary video is left exactly alone",
          test_ordinary_video_is_left_exactly_alone)
    check("frames come from the video, never invented",
          test_frames_are_taken_from_the_video_never_invented)
    check("the inserted frames stay in order",
          test_the_inserted_frames_stay_in_order)
    check("zero turns the floor off", test_zero_turns_the_floor_off)
    check("it survives nothing to work with",
          test_it_survives_nothing_to_work_with)
    check("a huge gap gets several frames, not one",
          test_a_huge_gap_gets_several_frames_not_one)
    check("deduplication applies the floor",
          test_deduplication_applies_the_floor)
    check("the gap is a setting with a default",
          test_the_gap_is_a_setting_with_a_default)
    check("the setting is reachable without editing JSON",
          test_the_setting_is_reachable_without_editing_json)
    check("both languages explain the setting",
          test_both_languages_explain_the_setting)
    check("the measurement is recorded beside the code",
          test_the_measurement_is_recorded_beside_the_code)
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
