"""
Omni Describer Custom — Prompt Manager.

Manages prompt presets: CRUD, per-language, validation.
"""

from __future__ import annotations

import logging
from typing import Any

from .settings_store import SettingsStore

logger = logging.getLogger(__name__)

# Default prompt presets
DEFAULT_PROMPTS = {
    "default": "Describe everything you see in this video frame in detail. Focus on visual elements, actions, context, and any text visible.",
    "detailed": "Provide a comprehensive description of this frame. Include all visual details, colors, lighting, emotional tone, and spatial relationships.",
    "minimal": "Brief description of this frame in one sentence.",
    "accessibility": "Describe this frame for a blind or visually impaired user. Be specific about spatial relationships, text content, and important visual information. Use clear, concise language.",
    "characters": "Identify and describe all people or characters in this frame. Include their appearance, actions, expressions, and positions.",
    "text_ocr": "Transcribe and describe any text visible in this frame. Include signs, subtitles, on-screen graphics, and written content.",
    "malay_default": "Huraikan semua yang anda lihat dalam kerangka video ini dengan terperinci. Fokus pada elemen visual, aksi, konteks, dan sebarang teks yang kelihatan.",
    "malay_accessibility": "Huraikan kerangka ini untuk pengguna buta atau kurang upaya penglihatan. Tekankan hubungan ruang, kandungan teks, dan maklumat visual penting.",
}

DEFAULT_LANGUAGE = "en"


class PromptManager:
    """
    Manages prompt presets with per-language support.
    Prompts are stored in SettingsStore but managed through this class.
    """

    def __init__(self, settings: SettingsStore | None = None):
        self.settings = settings or SettingsStore()
        self._language = DEFAULT_LANGUAGE
        self._ensure_defaults()

    def _ensure_defaults(self):
        """Ensure default prompts exist."""
        existing = self.settings.get_prompts()
        for name, text in DEFAULT_PROMPTS.items():
            if name not in existing:
                self.settings.set_prompt(name, text)

    @property
    def language(self) -> str:
        return self._language

    @language.setter
    def language(self, lang: str):
        self._language = lang or DEFAULT_LANGUAGE

    def get_presets(self) -> dict[str, str]:
        """Get all prompt presets for current language."""
        all_prompts = self.settings.get_prompts()
        # Filter prompts relevant to current language
        lang_prefix = f"{self._language}_"
        filtered = {}
        for name, text in all_prompts.items():
            # Include language-specific or universal prompts
            if name.startswith(lang_prefix) or "_" not in name:
                # Strip language prefix for display
                display_name = name[len(lang_prefix):] if name.startswith(lang_prefix) else name
                filtered[display_name] = text
        return filtered

    def get_preset(self, name: str) -> str:
        """Get a specific prompt preset."""
        # Try language-specific first
        lang_key = f"{self._language}_{name}"
        all_prompts = self.settings.get_prompts()
        if lang_key in all_prompts:
            return all_prompts[lang_key]
        return all_prompts.get(name, "")

    def get_preset_names(self) -> list[str]:
        """Get list of available preset names for current language."""
        return list(self.get_presets().keys())

    def set_preset(self, name: str, text: str) -> None:
        """Create or update a prompt preset."""
        lang_key = f"{self._language}_{name}"
        self.settings.set_prompt(lang_key, text)
        logger.info("Prompt preset saved: %s", lang_key)

    def delete_preset(self, name: str) -> bool:
        """Delete a prompt preset. Returns True if existed."""
        lang_key = f"{self._language}_{name}"
        return self.settings.delete_prompt(lang_key)

    def get_default_prompt(self) -> str:
        """Get the default prompt for current language."""
        return self.get_preset("default")

    def validate(self, text: str) -> tuple[bool, str]:
        """Validate prompt text. Returns (is_valid, error_message)."""
        if not text or not text.strip():
            return False, "Prompt cannot be empty"
        if len(text) > 5000:
            return False, "Prompt too long (max 5000 characters)"
        return True, ""

    def export_prompts(self) -> dict[str, str]:
        """Export all prompts as a dict."""
        return self.settings.get_prompts()

    def import_prompts(self, prompts: dict[str, str]) -> int:
        """Import prompts dict. Returns count of imported prompts."""
        count = 0
        for name, text in prompts.items():
            if text.strip():
                self.settings.set_prompt(name, text)
                count += 1
        return count
