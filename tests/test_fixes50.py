"""Regression round 50: frame mode stops describing every frame (v1.8.6).

Measured in phase 16.2 (docs/model-comparison.md): frame mode, the
default for new users, saved every frame that survived deduplication
as its own one-second description — 147-204 descriptions a MINUTE on
Sintel, AWANI news and Tears of Steel, two or three a second, with
markdown headings and invented "[0:00]" stamps read aloud by TTS.

The owner chose (30 Sep 2026): whole-video mode as the default, and
frame mode fixed so it no longer describes frames one by one.

  1. at most one frame per `general.min_description_gap` seconds (4 s:
     one 12-word line takes about that long to say);
  2. replies cleaned into a speakable line; placeholders dropped; a
     line identical to the previous one not said twice;
  3. new users start in whole-video mode; a saved mode is kept.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

from omni_describer_custom.core.ai_engine import (  # noqa: E402
    clean_frame_text, finalize_frame_descriptions)
from omni_describer_custom.core.video_processor import (  # noqa: E402
    Frame, VideoProcessor)

results: list[tuple[str, bool]] = []


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def _frames(times):
    return [Frame(path=f"f{i}.jpg", timestamp=t)
            for i, t in enumerate(times)]


def test_at_most_one_frame_per_gap():
    # A film: the picture changes on almost every sampled frame (5 fps).
    frames = _frames([i * 0.2 for i in range(300)])          # 60 s
    kept = VideoProcessor.space_frames(frames, 4.0)
    assert len(kept) == 15, f"{len(kept)} frames kept for 60 s"
    gaps = [b.timestamp - a.timestamp for a, b in zip(kept, kept[1:])]
    assert min(gaps) >= 4.0 - 1e-9, gaps
    assert kept[0].timestamp == 0.0, "the first change was dropped"
    # 0 turns it off: every frame is kept, as before.
    # Sparse frames (slides) are untouched.
    slides = _frames([0, 12, 30, 31, 60])
    assert [f.timestamp for f in VideoProcessor.space_frames(slides, 4.0)] \
        == [0, 12, 30, 60]


def test_pipeline_passes_the_setting():
    src = Path("src/omni_describer_custom/ui/main_frame.py").read_text(
        encoding="utf-8")
    assert "min_spacing=float(self.settings.get(" in src
    assert '"general.min_description_gap", 4' in src
    from omni_describer_custom.core.settings_store import SettingsStore
    assert SettingsStore.DEFAULTS["general"]["min_description_gap"] == 4


def test_replies_become_speakable_lines():
    cases = {
        "**Audio description - Excel workbook (sheet 1)**\nA table of sales.":
            "A table of sales.",
        "[0:00] A dragon lands on the rock.": "A dragon lands on the rock.",
        "## Scene\n- A girl climbs a snowy ridge.": "A girl climbs a snowy ridge.",
        "A man waves (no dialogue).": "A man waves.",
        "# A dragon lands": "A dragon lands",
    }
    for raw, want in cases.items():
        got = clean_frame_text(raw)
        assert got == want, f"{raw!r} -> {got!r}"
    assert clean_frame_text("A man (smiling) waves.") == "A man (smiling) waves."


def test_placeholders_and_repeats_are_not_spoken():
    frames = _frames([0, 4, 8, 12, 16])
    texts = ["A girl runs.", "(empty response)", "A girl runs!",
             "(error: 503)", "A dragon flies."]
    kept = finalize_frame_descriptions(frames, texts)
    assert [t for _, t in kept] == ["A girl runs.", "A dragon flies."], kept
    assert [f.timestamp for f, _ in kept] == [0, 16]


def test_new_users_start_in_whole_video_mode():
    from omni_describer_custom.core import settings_store
    fresh = tempfile.mkdtemp(prefix="odc_t50_new_")
    os.environ["ODC_CONFIG_DIR"] = fresh
    store = settings_store.SettingsStore()
    assert store.get("ai.video_mode") == "full", store.get("ai.video_mode")

    kept = tempfile.mkdtemp(prefix="odc_t50_old_")
    Path(kept, "settings.json").write_text(json.dumps(
        {"ai": {"video_mode": "frames"}}), encoding="utf-8")
    os.environ["ODC_CONFIG_DIR"] = kept
    store = settings_store.SettingsStore()
    assert store.get("ai.video_mode") == "frames", \
        "a user's saved frame mode was overwritten"


def main() -> int:
    check("at most one frame per gap", test_at_most_one_frame_per_gap)
    check("the pipeline passes the setting", test_pipeline_passes_the_setting)
    check("replies become speakable lines", test_replies_become_speakable_lines)
    check("placeholders and repeats are not spoken",
          test_placeholders_and_repeats_are_not_spoken)
    check("new users start in whole-video mode",
          test_new_users_start_in_whole_video_mode)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
