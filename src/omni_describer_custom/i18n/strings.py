"""
Omni Describer Custom — i18n strings.

Translations live in locales/<code>.json, ONE FILE PER LANGUAGE. Adding
a language means dropping a file in that folder — no code change, no
compile step, and it appears in the Settings picker by itself.

Each file carries its own metadata under "_meta": the name to show in
the picker, the language name the AI is told to write in, and a default
TTS voice. So a language is self-describing.

Why JSON and not gettext (.po/.mo): this app keys strings symbolically
("menu.file"), while gettext keys them by the English sentence itself —
using it properly would mean rewriting 700+ call sites. gettext also
needs a msgfmt compile step in build.bat, and its usual editor (Poedit)
is a GUI whose screen-reader support we cannot vouch for. Editing JSON
in a text editor with NVDA is direct and predictable.

Usage is unchanged: from omni_describer_custom.i18n.strings import t
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LOCALES_DIR = Path(__file__).parent / "locales"
FALLBACK_LANG = "en"


def user_locales_dir() -> Path:
    """Where a user keeps their OWN language files (v1.8.0).

    The bundled locales/ folder sits inside the app, which every update
    replaces — a language someone added there was lost on the next
    version. Files here survive updates. A file for a language the app
    already ships (ms.json) corrects it line by line; a new code (id.json)
    adds a language. ODC_LOCALES_DIR isolates tests.
    """
    override = os.environ.get("ODC_LOCALES_DIR", "").strip()
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "OmniDescriber" / "locales"


def _read_locale(path: Path) -> tuple[dict, dict] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        logger.error("Locale %s is unreadable, skipping: %s", path, e)
        return None
    if not isinstance(data, dict):
        logger.error("Locale %s is not a JSON object, skipping", path)
        return None
    meta = data.pop("_meta", None)
    table = {k: v for k, v in data.items() if isinstance(v, str) and not k.startswith("_")}
    return (meta if isinstance(meta, dict) else {}), table


def _load_locales() -> tuple[dict[str, dict[str, str]], dict[str, dict]]:
    """Read the bundled locales, then the user's. A broken file is
    skipped, not fatal: one bad translation must never stop the app."""
    tables: dict[str, dict[str, str]] = {}
    metas: dict[str, dict] = {}
    if not LOCALES_DIR.is_dir():
        logger.error("No locales directory at %s", LOCALES_DIR)
    else:
        for path in sorted(LOCALES_DIR.glob("*.json")):
            loaded = _read_locale(path)
            if loaded:
                code = path.stem
                metas[code] = loaded[0] or {"code": code, "name": code}
                tables[code] = loaded[1]
    user_dir = user_locales_dir()
    if user_dir.is_dir():
        for path in sorted(user_dir.glob("*.json")):
            code = path.stem
            if "." in code:
                continue  # "id.missing.json" is a report, not a language
            loaded = _read_locale(path)
            if not loaded:
                continue
            meta, table = loaded
            # Only non-empty lines override: a half-done file must not
            # blank out what the app already says.
            merged = dict(tables.get(code, {}))
            merged.update({k: v for k, v in table.items() if v.strip()})
            tables[code] = merged
            metas[code] = {**metas.get(code, {"code": code, "name": code}), **meta}
            logger.info("User locale loaded: %s", path)
    logger.info("Locales loaded: %s", ", ".join(sorted(tables)) or "none")
    return tables, metas


# Lines that are the same in every language, so an identical copy of
# the English text is not "untranslated": brand and product names.
_SAME_IN_EVERY_LANGUAGE = ("main.title", "settings.engine_", "settings.provider_")


def missing_report(lang: str) -> dict:
    """What a translator still has to do for `lang`.

    missing:  key -> English text, for every line absent or empty in
              that language (the app shows English there today);
    obsolete: keys the language still has that the app no longer uses.
    """
    english = EN_STRINGS
    table = I18n._translations.get(lang, {})
    missing = {k: v for k, v in english.items() if not (table.get(k) or "").strip()}
    obsolete = sorted(k for k in table if k not in english)
    return {"missing": missing, "obsolete": obsolete}


def write_missing_report(lang: str) -> tuple[Path, int]:
    """Save the report as <lang>.missing.json in the user locales folder.

    The file is in the same format as a language file: translate the
    values, then copy those lines into <lang>.json in the same folder.
    Returns (path, number of lines to translate).
    """
    report = missing_report(lang)
    folder = user_locales_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{lang}.missing.json"
    body: dict = {
        "_about": (
            f"Lines the {lang} language file does not have yet, with the "
            f"English text. Translate the text on the right, then copy "
            f"those lines into {lang}.json in this folder and restart the "
            f"app. Keys (on the left) must stay exactly as they are."
        ),
    }
    if report["obsolete"]:
        body["_obsolete_keys_you_can_delete"] = report["obsolete"]
    body.update(report["missing"])
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path, len(report["missing"])


_TABLES, _METAS = _load_locales()

# Kept as module-level names because the rest of the app and the test
# suite import them directly.
EN_STRINGS: dict[str, str] = _TABLES.get("en", {})
MS_STRINGS: dict[str, str] = _TABLES.get("ms", {})


class I18n:
    """Internationalization manager."""

    _translations: dict[str, dict[str, str]] = _TABLES
    _meta: dict[str, dict] = _METAS
    _current_lang: str = FALLBACK_LANG

    @classmethod
    def set_language(cls, lang: str) -> None:
        """Set current language, falling back to English if unknown."""
        cls._current_lang = lang if lang in cls._translations else FALLBACK_LANG
        logger.info("Language set to: %s", cls._current_lang)

    @classmethod
    def current_language(cls) -> str:
        return cls._current_lang

    @classmethod
    def t(cls, key: str, **kwargs: Any) -> str:
        """Translate a key.

        Falls back PER KEY to English, so a half-finished translation
        shows English for the missing lines instead of raw key names.
        """
        strings = cls._translations.get(cls._current_lang, EN_STRINGS)
        # v2.0.2: "1 descriptions" (owner heard it in Open Project). With
        # count == 1 a "<key>:one" line is used when the language has one;
        # a language without plurals simply keeps its one line. (":one",
        # not "_one": agent.accept_one etc. are ordinary keys.)
        one = key + ":one" if kwargs.get("count") in (1, "1") else None
        text = (
            (one and strings.get(one))
            or strings.get(key)
            or (one and EN_STRINGS.get(one))
            or EN_STRINGS.get(key, key)
        )
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, ValueError):
                pass
        return text

    @classmethod
    def add_translation(cls, lang: str, strings: dict[str, str]) -> None:
        """Add a translation at runtime (used by tests)."""
        cls._translations[lang] = strings

    @classmethod
    def available_languages(cls) -> list[str]:
        """Language codes found in locales/, English first."""
        codes = sorted(cls._translations.keys())
        if FALLBACK_LANG in codes:
            codes.remove(FALLBACK_LANG)
            codes.insert(0, FALLBACK_LANG)
        return codes

    @classmethod
    def language_name(cls, lang: str) -> str:
        """Name to show in the picker, in that language's own words."""
        return cls._meta.get(lang, {}).get("name", lang)

    @classmethod
    def ai_language_name(cls, lang: str) -> str:
        """What to tell the AI to write in, e.g. "Malay"."""
        return cls._meta.get(lang, {}).get("ai_language", "")

    @classmethod
    def default_voice(cls, lang: str, engine: str = "edge") -> str:
        """Default TTS voice for a language, when the file names one."""
        return cls._meta.get(lang, {}).get(f"tts_voice_{engine}", "")


# Convenience function
def t(key: str, **kwargs: Any) -> str:
    """Translate a string key."""
    return I18n.t(key, **kwargs)
