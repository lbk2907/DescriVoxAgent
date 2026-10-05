"""
Omni Describer Custom — Settings Store.

Encrypted JSON settings for API keys, preferences, and configuration.

v1.7.4 hardening (tests/test_fixes36.py):
  - saves are atomic (temp file + os.replace), so a crash mid-write can
    no longer leave a half-written settings.json;
  - a settings.json that cannot be parsed is set aside as
    settings.json.corrupt-<timestamp> instead of being silently
    overwritten with defaults (which used to wipe every saved key);
  - a key DPAPI cannot decrypt (profile moved to another PC, SID
    change) keeps its original blob on disk instead of being dropped;
  - every SettingsStore for the same file in this process shares ONE
    in-memory state and lock. The main window, player window and video
    processor each make their own store; they used to save their own
    stale snapshot over each other's changes;
  - DEFAULTS are deep-merged on load and non-dict sections repaired;
  - on Windows a DPAPI failure no longer falls back to the reversible
    XOR form: the key stays in memory for this session but is not
    written. Old XOR blobs are still READ so they migrate to DPAPI.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_config_dir() -> Path:
    """Get the application config directory.

    ODC_CONFIG_DIR overrides it, and run_gate.bat sets it (v1.5.5). The
    suite builds real MainFrames that write provider settings, and those
    writes used to land in the USER's live settings.json: after a gate
    run the app pointed its Gemini provider at a dead test loopback URL
    with the key "test-key". Tests now get their own throwaway dir.
    """
    override = os.environ.get("ODC_CONFIG_DIR", "").strip()
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", "")) / "OmniDescriber"
    else:
        base = Path.home() / ".config" / "omni-describer"
    base.mkdir(parents=True, exist_ok=True)
    return base


_DPAPI_PREFIX = "dpapi:"

try:
    import win32crypt  # type: ignore  # pywin32; Windows only
except ImportError:  # non-Windows or headless environments
    win32crypt = None  # type: ignore[assignment]


class SecretProtectError(Exception):
    """The key could not be protected; it must not be written."""


class SecretUnprotectError(Exception):
    """A stored key blob could not be decrypted."""


def _simple_encrypt(text: str, key: str = "odc-default-key-2026") -> str:
    """XOR obfuscation fallback (not real encryption; non-Windows only)."""
    result = []
    key = key * (len(text) // len(key) + 1)
    for i, char in enumerate(text):
        result.append(chr(ord(char) ^ ord(key[i])))
    return "".join(result)


def _simple_decrypt(encoded: str, key: str = "odc-default-key-2026") -> str:
    """Decrypt using same XOR operation."""
    return _simple_encrypt(encoded, key)  # XOR is symmetric


def _protect_secret_strict(text: str) -> str:
    """Protect an API key at rest, or raise SecretProtectError.

    Windows: DPAPI only. The XOR form is reversible by anyone who reads
    this source, so on Windows a DPAPI failure means "do not write the
    key", never "write it weakly".
    Elsewhere: legacy XOR obfuscation (no DPAPI exists).
    """
    if win32crypt is not None:
        try:
            blob = win32crypt.CryptProtectData(text.encode("utf-8"), "OmniDescriber", None, None, None, 0)
            return _DPAPI_PREFIX + base64.b64encode(blob).decode("ascii")
        except Exception as e:
            raise SecretProtectError(f"DPAPI protect failed: {e}") from e
    if sys.platform == "win32":
        raise SecretProtectError("DPAPI (pywin32) is not available")
    return _simple_encrypt(text)


def _protect_secret(text: str) -> str:
    """Protect an API key at rest (compat wrapper; "" if it cannot)."""
    try:
        return _protect_secret_strict(text)
    except SecretProtectError as e:
        logger.error("API key not protected: %s", e)
        return ""


def _unprotect_secret_strict(encoded: str) -> str:
    """Recover a stored key, or raise SecretUnprotectError."""
    if encoded.startswith(_DPAPI_PREFIX):
        if win32crypt is None:
            raise SecretUnprotectError("DPAPI blob but DPAPI is unavailable")
        try:
            blob = base64.b64decode(encoded[len(_DPAPI_PREFIX):])
            _desc, value = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
            return value.decode("utf-8") if isinstance(value, bytes) else str(value)
        except Exception as e:
            raise SecretUnprotectError(f"DPAPI unprotect failed: {e}") from e
    return _simple_decrypt(encoded)  # legacy XOR: read so it migrates


def _unprotect_secret(encoded: str) -> str:
    """Recover an API key stored by _protect_secret or by legacy XOR."""
    try:
        return _unprotect_secret_strict(encoded)
    except SecretUnprotectError as e:
        logger.error("%s", e)
        return ""


def _deep_copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _merge_defaults(data: dict, defaults: dict, path: tuple = ()) -> None:
    """Fill in missing keys from defaults, repairing non-dict sections.

    Individual provider configs (ai.providers.<name>) are left exactly
    as saved: set_ai_provider stores a whole dict, and injecting e.g. a
    default base_url into it would change which endpoint a user's
    provider talks to. Missing providers are still added.
    """
    for key, dval in defaults.items():
        if key not in data:
            data[key] = _deep_copy(dval)
        elif isinstance(dval, dict):
            if not isinstance(data[key], dict):
                logger.warning("Settings: section %s was %s, not a table; "
                               "reset to defaults", ".".join(path + (key,)),
                               type(data[key]).__name__)
                data[key] = _deep_copy(dval)
            elif path + (key,) != ("ai", "providers"):
                _merge_defaults(data[key], dval, path + (key,))
            else:
                for pname, pdefault in dval.items():
                    if pname not in data[key]:
                        data[key][pname] = _deep_copy(pdefault)


class _SharedState:
    """One settings file's state, shared by every store in the process."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.data: dict[str, Any] | None = None
        self.last_bytes: bytes | None = None  # what we last read/wrote
        # provider -> the original api_key_enc blob we could not decrypt.
        self.undecryptable: dict[str, str] = {}
        # Set when a corrupt file could not be set aside: writing would
        # destroy it, so saves are refused until it is dealt with.
        self.save_blocked = False


_SHARED: dict[str, _SharedState] = {}
_SHARED_LOCK = threading.Lock()


def _shared_for(path: Path) -> _SharedState:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = Path(os.path.abspath(path))
    key = os.path.normcase(str(resolved))
    with _SHARED_LOCK:
        state = _SHARED.get(key)
        if state is None:
            state = _SharedState()
            _SHARED[key] = state
        return state


def _migrate(data: dict) -> None:
    """One-time changes to values that were only ever the OLD default.

    Each step runs once, marked in "migrated", so a value the user sets
    afterwards — even the old one — is never changed again.
    """
    done = data.setdefault("migrated", [])
    if not isinstance(done, list):
        done = data["migrated"] = []
    general = data.get("general")
    if "chunk_300" not in done and isinstance(general, dict):
        # 600 was the default until v1.8.6 and was saved into every
        # settings.json by the Settings dialog; it halves accuracy.
        if general.get("chunk_seconds") == 600:
            general["chunk_seconds"] = 300
        done.append("chunk_300")


class SettingsStore:
    """
    Manages application settings with encrypted API key storage.
    Settings file: %APPDATA%/OmniDescriber/settings.json
    """

    DEFAULTS = {
        "ai": {
            "default_provider": "",
            "fast_mode": False,
            # v2.1.0: one name per person (core/characters.py), measured
            # 5 Oct 2026 (tools/cast_bench.py); on unless switched off.
            "characters": True,
            # v1.8.7: whole-video mode for new users. Frame mode, the old
            # default, described each frame separately — 147-204 lines a
            # minute on films (docs/model-comparison.md). A mode already
            # saved in settings.json is kept.
            "video_mode": "full",
            "providers": {
                "gemini": {"api_key": "", "model": "gemini-3.8-flash"},
                "openai": {"api_key": "", "model": "gpt-4o", "base_url": ""},
                "glm": {"api_key": "", "model": "z-ai/glm-5.3-flash", "base_url": "https://openrouter.ai/api/v1"},
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
        # v1.6.1 W3C extended description: hold the video while a
        # cue is spoken, so a long description cannot be cut off by the
        # next one. Measured: without it, 3 of 4 cues collided on a
        # slide deck even at TTS speed 1.5.
        "player": {
            "pause_for_narration": True,
        },
        "general": {
            "language": "en",
            "frame_rate": 5,
            # Optional cap on analysed frames per video (0 = no limit).
            # Default keeps existing behaviour unchanged.
            "frame_cap": 0,
            # Longest stretch the AI may be left with no frame at all.
            # 0 disables it; see VideoProcessor._apply_coverage_floor.
            "max_frame_gap": 30,
            # v1.8.7: seconds between frame-mode descriptions (one 12-word
            # line takes ~4 s to speak).
            "min_description_gap": 4,
            # v1.8.8: check each description against the picture after
            # full-video mode (core/review.py). Off unless chosen: it adds
            # minutes and a little cost (owner's choice, 30 Sep 2026).
            "review_mode": "off",
            # Seconds per part when a long video is split for the AI
            # (full-video mode). 600 = 10 minutes (user request v1.5.3).
            # v1.8.6: 300, not 600. Measured on two long films with the
            # accuracy ruler: 10-minute parts put 24.5% / 27.5% of the
            # descriptions at the wrong moment, 5-minute parts 12.9% /
            # 11.8% — and finished sooner (docs/model-comparison.md).
            "chunk_seconds": 300,
            "output_dir": str(Path.home() / "Documents" / "OmniDescriber" / "output"),
            "chunk_long_videos": True,
            "auto_save": True,
        },
        # v1.6.0: prompts live in ONE place now — prompt_manager.
        # DEFAULT_PROMPTS. This file used to carry a second, slightly
        # different copy of the same presets, so the wording a user got
        # depended on which module happened to seed the file first.
        # PromptManager._ensure_defaults() fills this in on first use.
        "prompts": {},
    }

    def __init__(self, config_dir: str = ""):
        self.config_dir = Path(config_dir) if config_dir else _get_config_dir()
        self.settings_file = self.config_dir / "settings.json"
        self._shared = _shared_for(self.settings_file)
        with self._shared.lock:
            try:
                disk = self._read_disk_bytes()
            except OSError as e:
                # Exists but unreadable right now (locked, permissions):
                # NOT corrupt, so never set aside or overwrite it.
                logger.error("Settings read error: %s", e)
                if self._shared.data is None:
                    self._data = _deep_copy(self.DEFAULTS)
                    self._shared.save_blocked = True
                return
            # Reload when this is the first store for the file, or the
            # file changed behind our back (another process, a hand
            # edit, a test rewriting it). Otherwise join the live state.
            if self._shared.data is None or disk != self._shared.last_bytes:
                self._load(disk)

    # All stores for one file see the same dict; assignment replaces
    # its CONTENTS so no other store is left holding a stale copy.
    @property
    def _data(self) -> dict[str, Any]:
        return self._shared.data  # type: ignore[return-value]

    @_data.setter
    def _data(self, value: dict[str, Any]) -> None:
        with self._shared.lock:
            if self._shared.data is None:
                self._shared.data = {}
            self._shared.data.clear()
            self._shared.data.update(value)

    def _read_disk_bytes(self) -> bytes | None:
        """File bytes, None if absent; other OSErrors propagate."""
        try:
            return self.settings_file.read_bytes()
        except FileNotFoundError:
            return None

    def _set_aside_corrupt(self) -> None:
        """Keep an unreadable settings file under a new name."""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = self.settings_file.with_name(f"settings.json.corrupt-{stamp}")
        n = 1
        while target.exists():
            target = self.settings_file.with_name(
                f"settings.json.corrupt-{stamp}-{n}")
            n += 1
        try:
            os.replace(self.settings_file, target)
        except OSError:
            try:
                shutil.copy2(self.settings_file, target)
            except OSError as e:
                logger.error("Settings file is corrupt and could not be "
                             "set aside (%s); it will NOT be overwritten", e)
                self._shared.save_blocked = True
                return
        logger.warning("Settings file was unreadable; kept it as %s and "
                       "started from defaults", target.name)

    def _load(self, disk: bytes | None = None):
        """Load settings from file (caller holds the shared lock)."""
        state = self._shared
        state.undecryptable = {}
        state.save_blocked = False
        if disk is None:
            self._data = _deep_copy(self.DEFAULTS)
            state.last_bytes = None
            self._save()
            return
        try:
            loaded = json.loads(disk.decode("utf-8-sig"))
            if not isinstance(loaded, dict):
                raise ValueError(f"top level is {type(loaded).__name__}, "
                                 "not an object")
        except Exception as e:
            logger.error("Settings load error: %s", e)
            self._set_aside_corrupt()
            self._data = _deep_copy(self.DEFAULTS)
            state.last_bytes = None
            if not state.save_blocked:
                self._save()
            return

        _merge_defaults(loaded, self.DEFAULTS)
        _migrate(loaded)
        providers = loaded["ai"]["providers"]
        for provider, cfg in providers.items():
            if not isinstance(cfg, dict):
                continue
            enc_key = cfg.pop("api_key_enc", "")
            if not enc_key:
                continue
            try:
                cfg["api_key"] = _unprotect_secret_strict(enc_key)
            except SecretUnprotectError as e:
                logger.error("API key for %s could not be decrypted (%s); "
                             "the stored key is kept, re-enter it in "
                             "Settings to replace it", provider, e)
                cfg["api_key"] = ""
                state.undecryptable[provider] = enc_key
        self._data = loaded
        state.last_bytes = disk
        logger.info("Settings loaded from %s", self.settings_file)

    def _save(self):
        """Save settings to file (with encrypted API keys), atomically."""
        state = self._shared
        with state.lock:
            if state.save_blocked:
                logger.error("Settings not saved: the settings file is "
                             "corrupt and could not be set aside")
                return
            tmp_name = ""
            try:
                data = _deep_copy(self._data)
                for provider, cfg in data.get("ai", {}).get("providers", {}).items():
                    if not isinstance(cfg, dict):
                        continue
                    api_key = cfg.pop("api_key", "")
                    if api_key:
                        try:
                            cfg["api_key_enc"] = _protect_secret_strict(api_key)
                        except SecretProtectError as e:
                            logger.error("API key for %s NOT saved: %s",
                                         provider, e)
                            old = state.undecryptable.get(provider)
                            if old:
                                cfg["api_key_enc"] = old
                    elif provider in state.undecryptable:
                        # Never drop a key blob just because this
                        # machine cannot read it.
                        cfg["api_key_enc"] = state.undecryptable[provider]
                payload = json.dumps(data, indent=2).encode("utf-8")
                self.config_dir.mkdir(parents=True, exist_ok=True)
                fd, tmp_name = tempfile.mkstemp(
                    prefix="settings.json.", suffix=".tmp",
                    dir=str(self.config_dir))
                with os.fdopen(fd, "wb") as f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
                for attempt in range(5):
                    try:
                        os.replace(tmp_name, self.settings_file)
                        break
                    except PermissionError:
                        # Antivirus / indexer briefly holding the file.
                        if attempt == 4:
                            raise
                        time.sleep(0.05 * (attempt + 1))
                tmp_name = ""
                state.last_bytes = payload
                logger.debug("Settings saved")
            except Exception as e:
                logger.error("Settings save error: %s", e)
            finally:
                if tmp_name:
                    try:
                        os.unlink(tmp_name)
                    except OSError:
                        pass

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
        with self._shared.lock:
            target = self._data
            for key in keys[:-1]:
                if not isinstance(target.get(key), dict):
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
        with self._shared.lock:
            if not isinstance(self._data.get("ai"), dict):
                self._data["ai"] = {}
            if not isinstance(self._data["ai"].get("providers"), dict):
                self._data["ai"]["providers"] = {}
            self._data["ai"]["providers"][name] = dict(config)
            if config.get("api_key"):
                # A new key replaces the one we could not decrypt.
                self._shared.undecryptable.pop(name, None)
            self._save()

    def get_prompts(self) -> dict[str, str]:
        """Get all prompt presets."""
        return dict(self._data.get("prompts", {}))

    def get_prompt(self, name: str, default: str = "") -> str:
        """Get a specific prompt preset."""
        return self._data.get("prompts", {}).get(name, default)

    def set_prompt(self, name: str, text: str) -> None:
        """Set a prompt preset."""
        with self._shared.lock:
            if not isinstance(self._data.get("prompts"), dict):
                self._data["prompts"] = {}
            self._data["prompts"][name] = text
            self._save()

    def delete_prompt(self, name: str) -> bool:
        """Delete a prompt preset. Returns True if existed."""
        with self._shared.lock:
            prompts = self._data.get("prompts", {})
            if name in prompts:
                del prompts[name]
                self._save()
                return True
            return False

    def reset(self) -> None:
        """Reset all settings to defaults."""
        with self._shared.lock:
            self._data = _deep_copy(self.DEFAULTS)
            self._shared.undecryptable = {}
            self._save()
