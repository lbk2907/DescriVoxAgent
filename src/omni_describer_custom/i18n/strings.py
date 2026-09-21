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
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LOCALES_DIR = Path(__file__).parent / "locales"
FALLBACK_LANG = "en"


def _load_locales() -> tuple[dict[str, dict[str, str]], dict[str, dict]]:
    """Read every locales/*.json. A broken file is skipped, not fatal:
    one bad translation must never stop the app from starting."""
    tables: dict[str, dict[str, str]] = {}
    metas: dict[str, dict] = {}
    if not LOCALES_DIR.is_dir():
        logger.error("No locales directory at %s", LOCALES_DIR)
        return tables, metas
    for path in sorted(LOCALES_DIR.glob("*.json")):
        code = path.stem
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("Locale %s is unreadable, skipping: %s", path.name, e)
            continue
        metas[code] = data.pop("_meta", {"code": code, "name": code})
        tables[code] = {k: v for k, v in data.items() if isinstance(v, str)}
    logger.info("Locales loaded: %s", ", ".join(sorted(tables)) or "none")
    return tables, metas


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
        text = strings.get(key) or EN_STRINGS.get(key, key)
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
