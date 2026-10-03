"""Regression round 24: multi-language support (v1.6.2).

Translations used to be two Python dicts in a 782-line module. That is
fine for two languages and unpleasant for ten, so they now live in
locales/<code>.json — one file per language, each describing itself:
the name to show in the picker, the language name the AI is told to
write in, and a default TTS voice.

The point of the design is that adding a language costs ONE FILE. No
code change, no compile step, no new prompt translations — the seven
audio-description presets stay in English and the model is told which
language to answer in. These checks pin that promise: a language dropped
into the folder must appear in the picker, reach the AI, and fall back
to English key by key while it is incomplete.

Not gettext (.po/.mo) deliberately: this app keys strings symbolically
("menu.file") while gettext keys them by the English sentence, so using
it properly would mean rewriting 700+ call sites; it also needs a msgfmt
step in the build, and its usual editor is a GUI whose screen-reader
support is unverified.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import json
import sys
import tempfile
import traceback
from pathlib import Path

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

from omni_describer_custom.i18n.strings import (  # noqa: E402
    EN_STRINGS, LOCALES_DIR, I18n, t)

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
    finally:
        I18n.set_language("en")


def _locale_files():
    return sorted(LOCALES_DIR.glob("*.json"))


# ── The files themselves ─────────────────────────────────────────

def test_locale_files_exist_and_parse():
    files = _locale_files()
    assert len(files) >= 2, f"expected at least en + ms, found {files}"
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict) and data, f"{path.name} is empty"


def test_every_locale_describes_itself():
    """A language must carry its own picker name, AI name and voice —
    that is what makes adding one a file drop rather than a code edit."""
    for path in _locale_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        meta = data.get("_meta", {})
        assert meta, f"{path.name}: no _meta block"
        for field in ("code", "name", "ai_language"):
            assert meta.get(field), f"{path.name}: _meta.{field} missing"
        assert meta["code"] == path.stem, \
            f"{path.name}: _meta.code is {meta['code']!r}"


def test_translations_cover_the_english_keys():
    """A gap here is not fatal — t() falls back per key — but it should
    be visible, not discovered by a user hearing English mid-sentence."""
    base = set(EN_STRINGS)
    for code in I18n.available_languages():
        if code == "en":
            continue
        missing = base - set(I18n._translations[code])
        assert not missing, (
            f"{code}: {len(missing)} keys untranslated, e.g. "
            f"{sorted(missing)[:5]}")


def test_no_stray_keys_beyond_english():
    """An extra key means a typo or a string that English lost."""
    base = set(EN_STRINGS)
    for code in I18n.available_languages():
        if code == "en":
            continue
        extra = set(I18n._translations[code]) - base
        assert not extra, f"{code}: keys not in English: {sorted(extra)[:5]}"


# ── Behaviour ────────────────────────────────────────────────────

def test_switching_language_changes_the_words():
    I18n.set_language("en")
    english = t("player.load_srt")
    I18n.set_language("ms")
    malay = t("player.load_srt")
    assert english and malay and english != malay, (english, malay)


def test_unknown_language_falls_back_to_english():
    I18n.set_language("klingon")
    assert I18n.current_language() == "en"
    assert t("player.load_srt") == EN_STRINGS["player.load_srt"]


def test_missing_key_falls_back_per_key_not_per_language():
    """Half a translation must show English for the rest, never raw keys
    like "menu.file" read aloud by a screen reader."""
    I18n.add_translation("zz", {"player.load_srt": "ZZ load"})
    try:
        I18n.set_language("zz")
        assert t("player.load_srt") == "ZZ load"
        assert t("menu.file") == EN_STRINGS["menu.file"], \
            "an untranslated key did not fall back to English"
    finally:
        I18n._translations.pop("zz", None)


def test_placeholders_survive_translation():
    """A translation that drops {count} would crash or mislead."""
    for code in I18n.available_languages():
        table = I18n._translations[code]
        for key, english in EN_STRINGS.items():
            if "{" not in english:
                continue
            translated = table.get(key)
            if not translated:
                continue
            fields = {p.split("}")[0].split(":")[0]
                      for p in english.split("{")[1:]}
            for field in fields:
                assert "{" + field in translated, (
                    f"{code}: {key} lost the {{{field}}} placeholder")


# ── A new language costs one file ────────────────────────────────

def test_a_dropped_file_becomes_a_language():
    """The whole promise of the design, exercised end to end."""
    from omni_describer_custom.i18n import strings as mod

    new = LOCALES_DIR / "zz.json"
    payload = {
        "_meta": {"code": "zz", "name": "Zzedish", "ai_language": "Zzedish",
                  "tts_voice_edge": "zz-ZZ-Test"},
        "player.load_srt": "Zz load",
    }
    new.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        tables, metas = mod._load_locales()
        assert "zz" in tables, "a dropped file did not become a language"
        assert metas["zz"]["name"] == "Zzedish"
    finally:
        new.unlink(missing_ok=True)


def test_a_broken_file_does_not_stop_the_app():
    """One bad translation must not take the program down with it."""
    from omni_describer_custom.i18n import strings as mod

    bad = LOCALES_DIR / "zz.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    try:
        tables, _ = mod._load_locales()
        assert "en" in tables, "a broken locale broke the good ones"
        assert "zz" not in tables
    finally:
        bad.unlink(missing_ok=True)


def test_ai_language_directive_works_for_any_locale():
    """Adding a language must NOT mean translating seven prompts: the
    presets stay English and the model is told what to write in."""
    from omni_describer_custom.core.ai_engine import (apply_output_language,
                                                      language_directive)

    for code in I18n.available_languages():
        directive = language_directive(code)
        assert directive, f"{code}: no directive, AI would pick its own language"
        assert I18n.ai_language_name(code).split()[0] in directive, \
            f"{code}: directive does not name the language"

    prompt = apply_output_language("Describe this.", "ms")
    assert "Describe this." in prompt and "Malay" in prompt
    assert apply_output_language("x", "klingon") == "x", \
        "an unknown code must leave the prompt alone"


def test_default_voice_is_offered_per_language():
    for code in I18n.available_languages():
        assert I18n.default_voice(code, "edge"), \
            f"{code}: no default TTS voice, so speech would stay English"


def test_picker_offers_every_installed_language():
    src = Path("src/omni_describer_custom/ui/settings_dialog.py").read_text(
        encoding="utf-8")
    assert "I18n.available_languages()" in src, \
        "the language picker is hardcoded again"
    assert 'I18n.language_name(code)' in src, \
        "the picker shows raw codes instead of language names"


def test_description_language_accepts_any_locale():
    """It used to check ("ms", "en") and silently discard anything else."""
    src = Path("src/omni_describer_custom/ui/main_frame.py").read_text(
        encoding="utf-8")
    assert 'desc_lang not in I18n.available_languages()' in src, \
        "the pipeline still hardcodes which description languages exist"


def test_build_ships_the_locales():
    build = Path("build.bat").read_text(encoding="utf-8")
    assert "locales" in build, \
        "PyInstaller would drop the translations and the app would show keys"


if __name__ == "__main__":
    check("locale files exist and parse", test_locale_files_exist_and_parse)
    check("every locale describes itself",
          test_every_locale_describes_itself)
    check("translations cover the English keys",
          test_translations_cover_the_english_keys)
    check("no stray keys beyond English", test_no_stray_keys_beyond_english)
    check("switching language changes the words",
          test_switching_language_changes_the_words)
    check("unknown language falls back to English",
          test_unknown_language_falls_back_to_english)
    check("missing key falls back per key",
          test_missing_key_falls_back_per_key_not_per_language)
    check("placeholders survive translation",
          test_placeholders_survive_translation)
    check("a dropped file becomes a language",
          test_a_dropped_file_becomes_a_language)
    check("a broken file does not stop the app",
          test_a_broken_file_does_not_stop_the_app)
    check("AI directive works for any locale",
          test_ai_language_directive_works_for_any_locale)
    check("default voice offered per language",
          test_default_voice_is_offered_per_language)
    check("picker offers every installed language",
          test_picker_offers_every_installed_language)
    check("description language accepts any locale",
          test_description_language_accepts_any_locale)
    check("build ships the locales", test_build_ships_the_locales)
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
