"""Regression round 22: the prompts must follow audio-description standards.

Until v1.6.0 the shipped presets told the AI to "describe everything you
see in this video frame in detail" and to report "emotional tone", and
the engine appended "Describe important visuals AND sounds/speech". Every
published standard says the opposite:

  DCMP Description Key      objective, no interpretation or comment;
                            present tense, active voice, third person;
                            only what is essential to follow the content
  Netflix AD Style Guide    skip what dialogue already conveys; never
                            describe over dialogue; don't guess race,
                            ethnicity or gender; read on-screen text
  W3C/WAI                   convey the visual information needed; no need
                            to describe what is apparent from the audio
  ADLAB (EU)                prioritise focal characters, actions, space

These checks pin the RULES, not the prose: a future edit may reword a
preset, but it may not quietly reintroduce "describe everything in
detail", drop the ban on narrating dialogue, or start asking the model
for emotional interpretation.
"""
import io
import sys
import tempfile
import traceback

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

from omni_describer_custom.core.prompt_manager import (  # noqa: E402
    DEFAULT_PROMPTS, LEGACY_PROMPTS, PromptManager)
from omni_describer_custom.core.settings_store import SettingsStore  # noqa: E402

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


EN_PRESETS = [n for n in DEFAULT_PROMPTS if not n.startswith("ms_")]
MS_PRESETS = [n for n in DEFAULT_PROMPTS if n.startswith("ms_")]


def test_every_preset_carries_the_core_rules():
    """Each preset builds on the same AD core, whatever its speciality."""
    for name in EN_PRESETS:
        text = DEFAULT_PROMPTS[name].lower()
        assert "blind" in text, f"{name}: does not say who it is for"
        assert "present tense" in text, f"{name}: no tense rule"
        assert "third person" in text, f"{name}: no person rule"
        assert "one sentence" in text or "short phrase" in text, \
            f"{name}: nothing keeps cues speakable"
    for name in MS_PRESETS:
        text = DEFAULT_PROMPTS[name].lower()
        assert "buta" in text, f"{name}: does not say who it is for"
        assert "kala kini" in text, f"{name}: no tense rule"
        assert "orang ketiga" in text, f"{name}: no person rule"


def test_no_preset_asks_for_everything_in_detail():
    """The single most common mistake, and the old default's exact words."""
    banned = ("describe everything", "in detail", "comprehensive",
              "all visual details", "huraikan semua", "terperinci")
    for name, text in DEFAULT_PROMPTS.items():
        low = text.lower()
        for phrase in banned:
            assert phrase not in low, f"{name} asks for {phrase!r}"


def test_no_preset_asks_the_model_to_interpret():
    """"Emotional tone" was in the old `detailed` preset. AD reports what
    is observable and lets the listener draw the conclusion."""
    banned = ("emotional tone", "how they feel", "emosi", "perasaan")
    for name, text in DEFAULT_PROMPTS.items():
        low = text.lower()
        for phrase in banned:
            assert phrase not in low, f"{name} asks for {phrase!r}"


def test_speech_is_only_described_where_it_is_the_service():
    """Narrating dialogue wastes a gap the listener already has — except
    in `foreign`, where conveying speech IS the point (audio subtitling)."""
    for name in EN_PRESETS:
        text = DEFAULT_PROMPTS[name]
        assert "Never describe dialogue" in text, \
            f"{name}: lost the rule against narrating audible content"
    convey = DEFAULT_PROMPTS["foreign"].lower()
    assert "convey what is said" in convey, \
        "foreign preset no longer conveys speech, so it has no purpose"
    assert "convey what is said" not in DEFAULT_PROMPTS["default"].lower(), \
        "the standard preset must not narrate speech"


def test_identity_is_not_guessed():
    """Netflix is explicit: do not assume racial, ethnic or gender identity."""
    for name in EN_PRESETS:
        low = DEFAULT_PROMPTS[name].lower()
        assert "never guess race" in low, f"{name}: identity guard missing"
    for name in MS_PRESETS:
        low = DEFAULT_PROMPTS[name].lower()
        assert "teka bangsa" in low, f"{name}: identity guard missing"


def test_meta_language_is_banned():
    """"In this frame we see a camera shot of..." is unusable narration."""
    for name in EN_PRESETS:
        low = DEFAULT_PROMPTS[name].lower()
        assert "never mention the camera" in low, f"{name}: no meta ban"


def test_language_parity():
    """House rule: every user-facing string exists in EN and BM."""
    en = set(EN_PRESETS)
    ms = {n[len("ms_"):] for n in MS_PRESETS}
    assert en == ms, f"EN/BM presets differ: only EN={en - ms}, only BM={ms - en}"


def test_engine_does_not_force_sound_narration():
    """The suffix the engine appends must not re-add what the presets ban."""
    from omni_describer_custom.core import ai_engine

    suffix = ai_engine.FULL_VIDEO_TS_PROMPT_SUFFIX
    assert "AND sounds/speech" not in suffix, \
        "engine still forces sound/speech narration into every request"
    assert "VISUALS" in suffix, "engine no longer steers toward visuals"


# ── Migration: retire the old set without eating user edits ───────

def test_legacy_presets_are_retired():
    with tempfile.TemporaryDirectory() as td:
        store = SettingsStore(config_dir=td)
        for name, text in LEGACY_PROMPTS.items():
            store.set_prompt(name.replace("_alt", ""), text)
        PromptManager(store)
        left = store.get_prompts()
        for gone in ("detailed", "minimal", "accessibility", "characters",
                     "text_ocr", "ms_accessibility"):
            assert gone not in left, f"obsolete preset {gone!r} survived"
        assert "default" in left and "describe everything" not in \
            left["default"].lower(), "default was not upgraded"


def test_user_edited_presets_are_never_touched():
    """The migration may only remove text we shipped ourselves."""
    with tempfile.TemporaryDirectory() as td:
        store = SettingsStore(config_dir=td)
        store.set_prompt("minimal", "MY OWN wording, keep it")
        store.set_prompt("my_style", "Describe like a radio play.")
        PromptManager(store)
        left = store.get_prompts()
        assert left.get("minimal") == "MY OWN wording, keep it", \
            "an edited preset was deleted by the migration"
        assert left.get("my_style") == "Describe like a radio play.", \
            "a user's own preset was deleted by the migration"


def test_presets_reach_the_ui_in_both_languages():
    with tempfile.TemporaryDirectory() as td:
        pm = PromptManager(SettingsStore(config_dir=td))
        pm.language = "en"
        en_names = pm.get_preset_names()
        for expected in ("default", "tight", "extended", "foreign",
                         "suspense", "children", "onscreen_text"):
            assert expected in en_names, f"{expected} missing: {en_names}"
        assert "Huraikan" not in pm.get_preset("default")

        pm.language = "ms"
        ms_names = pm.get_preset_names()
        for expected in ("default", "tight", "extended", "foreign",
                         "suspense", "children", "onscreen_text"):
            assert expected in ms_names, f"{expected} missing: {ms_names}"
        assert "Huraikan" in pm.get_preset("default"), \
            "ms default is not in Malay"


def test_presets_are_valid_and_speakable():
    """Prompts must pass the app's own validator and stay a sane size."""
    with tempfile.TemporaryDirectory() as td:
        pm = PromptManager(SettingsStore(config_dir=td))
        for name, text in DEFAULT_PROMPTS.items():
            valid, err = pm.validate(text)
            assert valid, f"{name} rejected by validate(): {err}"
            assert len(text) < 3000, f"{name} is {len(text)} chars"


if __name__ == "__main__":
    check("every preset carries the core rules",
          test_every_preset_carries_the_core_rules)
    check("no preset asks for everything in detail",
          test_no_preset_asks_for_everything_in_detail)
    check("no preset asks the model to interpret",
          test_no_preset_asks_the_model_to_interpret)
    check("speech described only where that is the service",
          test_speech_is_only_described_where_it_is_the_service)
    check("identity is never guessed", test_identity_is_not_guessed)
    check("meta language is banned", test_meta_language_is_banned)
    check("EN/BM preset parity", test_language_parity)
    check("engine does not force sound narration",
          test_engine_does_not_force_sound_narration)
    check("legacy presets are retired", test_legacy_presets_are_retired)
    check("user-edited presets are never touched",
          test_user_edited_presets_are_never_touched)
    check("presets reach the UI in both languages",
          test_presets_reach_the_ui_in_both_languages)
    check("presets are valid and speakable",
          test_presets_are_valid_and_speakable)
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
