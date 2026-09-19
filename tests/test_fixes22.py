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
        # Measured on a real project with the user's own voice: cues were
        # overrunning their gaps 4 times out of 6 even AFTER the v1.6.0
        # rewrite, because the model spaced events 2-3 seconds apart while
        # each line took 6-7 seconds to speak. Brevity alone is not enough;
        # the model has to pace the timestamps too.
        assert "two words per second" in text, \
            f"{name}: no speech-pacing rule, so cues will collide"
        # The model could not do the arithmetic reliably — asked to pace
        # itself it still wrote 21-word lines into 7-second gaps. A flat
        # ceiling it obeys. Measured after adding it: longest line 12
        # words, and at TTS speed 1.25 nothing overruns at all.
        assert "hard limit: 12 words" in text, \
            f"{name}: no hard word ceiling"
    for name in MS_PRESETS:
        text = DEFAULT_PROMPTS[name].lower()
        assert "buta" in text, f"{name}: does not say who it is for"
        assert "kala kini" in text, f"{name}: no tense rule"
        assert "dua patah perkataan sesaat" in text, \
            f"{name}: no speech-pacing rule"
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
    """Netflix: "do not guess or assume racial, ethnic or gender identity".

    Note the list stops there — apparent age is ordinary AD vocabulary
    ("a young man"), so the prompt must not ban it.
    """
    for name in EN_PRESETS:
        low = DEFAULT_PROMPTS[name].lower()
        assert "race, ethnicity or gender identity" in low, \
            f"{name}: identity guard missing"
    for name in MS_PRESETS:
        low = DEFAULT_PROMPTS[name].lower()
        assert "bangsa, etnik atau identiti" in low, \
            f"{name}: identity guard missing"


def test_film_technique_is_banned_but_direct_address_is_not():
    """Narrating cuts and zooms is caption voice, not description — but
    the Netflix guide explicitly ALLOWS direct address ("She turns to the
    camera and winks at us"), so a blanket ban on the word camera would
    contradict the standard and be disobeyed anyway."""
    for name in EN_PRESETS:
        low = DEFAULT_PROMPTS[name].lower()
        assert "do not narrate film technique" in low, \
            f"{name}: no film-technique ban"
        assert "to camera is fine" in low, \
            f"{name}: direct address must stay allowed"
        assert "never mention the camera" not in low, \
            f"{name}: blanket camera ban contradicts the Netflix guide"


def test_language_parity():
    """House rule: every user-facing string exists in EN and BM."""
    en = set(EN_PRESETS)
    ms = {n[len("ms_"):] for n in MS_PRESETS}
    assert en == ms, f"EN/BM presets differ: only EN={en - ms}, only BM={ms - en}"


def test_language_parity_of_RULES_not_just_names():
    """Matching names are not matching instructions.

    The Malay twins of `extended`, `foreign` and `onscreen_text` were
    shipped WITHOUT the raised word ceiling their English versions carry,
    so a Malay user was held to 12 words exactly where the content needs
    room — and `ms_foreign` duly produced no conveyed speech at all. The
    name check passed the whole time.
    """
    def raised(text: str) -> bool:
        return any(marker in text for marker in
                   ("25 words", "25 patah", "exceed 12 words",
                    "melebihi 12 patah"))

    for name in EN_PRESETS:
        twin = DEFAULT_PROMPTS[f"ms_{name}"]
        assert raised(DEFAULT_PROMPTS[name]) == raised(twin), (
            f"{name}: EN and BM disagree on the word ceiling")


def test_engine_suffix_defers_to_the_prompt():
    """The suffix is appended AFTER the preset, so whatever it says wins.

    It must therefore have no opinion about WHAT to describe. v1.6.0
    first swapped "describe visuals AND sounds/speech" for a visuals-only
    line, which then silently overrode the `foreign` preset: a real run
    conveyed no speech at all, the one thing that preset exists for.
    """
    from omni_describer_custom.core import ai_engine

    suffix = ai_engine.FULL_VIDEO_TS_PROMPT_SUFFIX
    assert "AND sounds/speech" not in suffix, \
        "engine forces sound narration into every request"
    assert "important VISUALS" not in suffix, \
        "engine forces visuals-only, overriding presets that need speech"
    assert "Follow the description rules given in the prompt above" in suffix, \
        "engine suffix no longer defers to the preset"


def test_audio_capability_is_known_per_provider():
    """A frame-only provider cannot do audio subtitling, and failing
    silently is the worst outcome for someone who cannot see the result.

    Probed 20 Sep 2026: GLM answers "NO AUDIO ACCESS" when asked to
    transcribe speech.
    """
    from omni_describer_custom.core.ai_engine import provider_hears_audio

    assert not provider_hears_audio("glm"), \
        "GLM was probed and cannot hear audio"
    assert not provider_hears_audio(""), "unknown provider must not claim audio"
    assert provider_hears_audio("gemini"), "gemini processes the audio track"
    assert provider_hears_audio("GEMINI"), "capability check must be case-safe"


def test_foreign_preset_warning_exists_in_both_languages():
    from omni_describer_custom.i18n.strings import EN_STRINGS, MS_STRINGS

    for lang, table in (("en", EN_STRINGS), ("ms", MS_STRINGS)):
        msg = table.get("preset.needs_audio", "")
        assert msg, f"{lang}: no warning string for the foreign preset"
        assert "{provider}" in msg, f"{lang}: warning does not name the provider"
        assert "Gemini" in msg, f"{lang}: warning does not say what to use"


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


def test_both_historical_wordings_are_retired():
    """Two modules shipped the same presets with different wording, so an
    upgrade sees either. A live install was still offering the "emotional
    tone" preset because only one wording was listed as legacy."""
    variants = {
        "detailed": "Provide a comprehensive description of this frame. "
                    "Include all visual details, text visible, colors, "
                    "lighting, and emotional tone.",
        "default": "Describe everything you see in this video frame in "
                   "detail. Focus on visual elements, actions, and context.",
    }
    with tempfile.TemporaryDirectory() as td:
        store = SettingsStore(config_dir=td)
        for name, text in variants.items():
            store.set_prompt(name, text)
        PromptManager(store)
        left = store.get_prompts()
        assert "detailed" not in left, \
            "the settings_store wording of `detailed` survived the upgrade"
        assert "emotional tone" not in " ".join(left.values()).lower(), \
            "a preset still asks the model for emotional tone"


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
    check("film technique banned, direct address allowed",
          test_film_technique_is_banned_but_direct_address_is_not)
    check("EN/BM preset parity", test_language_parity)
    check("EN/BM parity of rules, not just names",
          test_language_parity_of_RULES_not_just_names)
    check("engine suffix defers to the prompt",
          test_engine_suffix_defers_to_the_prompt)
    check("audio capability known per provider",
          test_audio_capability_is_known_per_provider)
    check("foreign-preset warning exists EN+BM",
          test_foreign_preset_warning_exists_in_both_languages)
    check("legacy presets are retired", test_legacy_presets_are_retired)
    check("both historical wordings are retired",
          test_both_historical_wordings_are_retired)
    check("user-edited presets are never touched",
          test_user_edited_presets_are_never_touched)
    check("presets reach the UI in both languages",
          test_presets_reach_the_ui_in_both_languages)
    check("presets are valid and speakable",
          test_presets_are_valid_and_speakable)
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
