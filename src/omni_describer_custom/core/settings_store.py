"""
Omni Describer Custom — Settings Store.

Encrypted JSON settings for API keys, preferences, and configuration.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_config_dir() -> Path:
    """Get the application config directory."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", "")) / "OmniDescriber"
    else:
        base = Path.home() / ".config" / "omni-describer"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _simple_encrypt(text: str, key: str = "odc-default-key-2026") -> str:
    """Simple XOR encryption for API keys (not military-grade, but obfuscates)."""
    result = []
    key = key * (len(text) // len(key) + 1)
    for i, char in enumerate(text):
        result.append(chr(ord(char) ^ ord(key[i])))
    return "".join(result)


def _simple_decrypt(encoded: str, key: str = "odc-default-key-2026") -> str:
    """Decrypt using same XOR operation."""
    return _simple_encrypt(encoded, key)  # XOR is symmetric


class SettingsStore:
    """
    Manages application settings with encrypted API key storage.
    Settings file: %APPDATA%/OmniDescriber/settings.json
    """

    DEFAULTS = {
        "ai": {
            "default_provider": "",
            "providers": {
                "gemini": {"api_key": "", "model": "gemini-2.5-flash"},
                "openai": {"api_key": "", "model": "gpt-4o", "base_url": ""},
                "opus": {"api_key": "", "model": "claude-opus-4-8", "base_url": "https://opus.abhibots.com/v1"},
                "custom": {"api_key": "", "model": "", "base_url": "", "api_format": "auto"},
            },
        },
        "tts": {
            "default_engine": "edge",
            "engines": {
                "edge": {"voice": "en-US-JennyNeural", "speed": 1.0},
                "sapi5": {"voice": "", "speed": 1.0},
                "openai": {"voice": "alloy", "speed": 1.0},
            },
        },
        "general": {
            "language": "en",
            "frame_rate": 5,
            # Optional cap on analysed frames per video (0 = no limit).
            # Default keeps existing behaviour unchanged.
            "frame_cap": 0,
            "output_dir": str(Path.home() / "Documents" / "OmniDescriber" / "output"),
            "chunk_long_videos": True,
            "auto_save": True,
        },
        "prompts": {
            "default": "Describe everything you see in this video frame in detail. Focus on visual elements, actions, and context.",
            "detailed": "Provide a comprehensive description of this frame. Include all visual details, text visible, colors, lighting, and emotional tone.",
            "minimal": "Brief description of this frame in one sentence.",
            "accessibility": "Describe this frame for a blind or visually impaired user. Be specific about spatial relationships, text content, and important visual information.",
        },
    }

    def __init__(self, config_dir: str = ""):
        self.config_dir = Path(config_dir) if config_dir else _get_config_dir()
        self.settings_file = self.config_dir / "settings.json"
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self):
        """Load settings from file."""
        if self.settings_file.exists():
            try:
                self._data = json.loads(self.settings_file.read_text(encoding="utf-8"))
                # Decrypt API keys
                for provider in self._data.get("ai", {}).get("providers", {}):
                    if isinstance(self._data["ai"]["providers"][provider], dict):
                        enc_key = self._data["ai"]["providers"][provider].get("api_key_enc", "")
                        if enc_key:
                            self._data["ai"]["providers"][provider]["api_key"] = _simple_decrypt(enc_key)
                            del self._data["ai"]["providers"][provider]["api_key_enc"]
                logger.info("Settings loaded from %s", self.settings_file)
            except Exception as e:
                logger.error("Settings load error: %s", e)
                self._data = dict(self.DEFAULTS)
        else:
            self._data = dict(self.DEFAULTS)
            self._save()

    def _save(self):
        """Save settings to file (with encrypted API keys)."""
        try:
            data = json.loads(json.dumps(self._data))  # Deep copy
            # Encrypt API keys
            for provider in data.get("ai", {}).get("providers", {}):
                if isinstance(data["ai"]["providers"][provider], dict):
                    api_key = data["ai"]["providers"][provider].get("api_key", "")
                    if api_key:
                        data["ai"]["providers"][provider]["api_key_enc"] = _simple_encrypt(api_key)
                        del data["ai"]["providers"][provider]["api_key"]
            self.settings_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.debug("Settings saved")
        except Exception as e:
            logger.error("Settings save error: %s", e)

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get a setting by dot-path (e.g. 'ai.default_provider')."""
        keys = key_path.split(".")
        value = self._data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def set(self, key_path: str, value: Any) -> None:
        """Set a setting by dot-path."""
        keys = key_path.split(".")
        target = self._data
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value
        self._save()

    def get_ai_provider(self, name: str) -> dict:
        """Get AI provider config (with decrypted API key)."""
        providers = self._data.get("ai", {}).get("providers", {})
        if name not in providers:
            return {}
        return dict(providers[name])

    def set_ai_provider(self, name: str, config: dict) -> None:
        """Set AI provider config (API key will be encrypted on save)."""
        if "ai" not in self._data:
            self._data["ai"] = {}
        if "providers" not in self._data["ai"]:
            self._data["ai"]["providers"] = {}
        self._data["ai"]["providers"][name] = dict(config)
        self._save()

    def get_prompts(self) -> dict[str, str]:
        """Get all prompt presets."""
        return dict(self._data.get("prompts", {}))

    def get_prompt(self, name: str, default: str = "") -> str:
        """Get a specific prompt preset."""
        return self._data.get("prompts", {}).get(name, default)

    def set_prompt(self, name: str, text: str) -> None:
        """Set a prompt preset."""
        if "prompts" not in self._data:
            self._data["prompts"] = {}
        self._data["prompts"][name] = text
        self._save()

    def delete_prompt(self, name: str) -> bool:
        """Delete a prompt preset. Returns True if existed."""
        prompts = self._data.get("prompts", {})
        if name in prompts:
            del prompts[name]
            self._save()
            return True
        return False

    def reset(self) -> None:
        """Reset all settings to defaults."""
        self._data = json.loads(json.dumps(self.DEFAULTS))
        self._save()
