"""
Omni Describer Custom — Multi-engine TTS Engine.

Supports: SAPI5 (pyttsx3), Edge TTS (edge-tts), OpenAI TTS.
Fallback chain: Edge → SAPI5 → OpenAI.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TTSEngineBase(ABC):
    """Abstract base class for TTS engines."""

    name: str = "base"
    available: bool = False

    @abstractmethod
    async def speak(self, text: str, voice: str = "", speed: float = 1.0) -> str:
        """Generate speech and return path to audio file. Returns '' if unavailable."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop current speech."""
        ...

    @abstractmethod
    def get_voices(self) -> list[dict]:
        """Return list of available voices [{id, name, lang}]."""
        ...


class SAPI5Engine(TTSEngineBase):
    name = "sapi5"
    _engine = None
    _queue: list[str] = []

    def __init__(self):
        self.available = False
        self._setup()

    def _setup(self):
        try:
            import pyttsx3
            from pyttsx3.drivers.sapi5 import SAPI5Driver

            # Monkey-patch: fix SAPI5 voice ID bug — Language attribute
            # sometimes returns "409;9" instead of just "409"
            original_toVoice = SAPI5Driver._toVoice

            def _patched_toVoice(attr):
                voice_id = attr.Id
                voice_name = attr.GetDescription()
                language_attr = attr.GetAttribute("Language")
                # Handle both str ("409;9") and int (0x409) formats
                if isinstance(language_attr, str):
                    language_attr = language_attr.split(";")[0].strip()
                language_code = int(language_attr)
                primary_sub_code = f"{language_code & 0x3FF}-{(language_code >> 10) & 0x3FF}"
                try:
                    from pyttsx3.drivers.sapi5 import lcid_to_locale
                    languages = [lcid_to_locale(primary_sub_code)]
                except Exception:
                    languages = ["en"]
                gender_attr = attr.GetAttribute("Gender")
                gender_title_case = (gender_attr or "").title()
                gender = gender_title_case if gender_title_case in {"Male", "Female"} else None
                age_attr = attr.GetAttribute("Age")
                age = age_attr if age_attr in {"Child", "Teen", "Adult", "Senior"} else None
                from pyttsx3.drivers.sapi5 import Voice
                return Voice(id=voice_id, name=voice_name, languages=languages, gender=gender, age=age)

            SAPI5Driver._toVoice = _patched_toVoice

            self._engine = pyttsx3.init("sapi5")
            self.available = True
            logger.info("SAPI5 TTS engine initialized (voice ID bug patched)")
        except Exception as e:
            logger.warning("SAPI5 TTS unavailable: %s", e)
            self.available = False

    async def speak(self, text: str, voice: str = "", speed: float = 1.0) -> str:
        if not self.available or not self._engine:
            return ""
        try:
            self._engine.setProperty("rate", int(150 * speed))
            if voice:
                self._engine.setProperty("voice", voice)
            # Use a temp file for async compatibility
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.close()
            self._engine.save_to_file(text, tmp.name)
            self._engine.runAndWait()
            if Path(tmp.name).exists() and Path(tmp.name).stat().st_size > 0:
                return tmp.name
            return ""
        except Exception as e:
            logger.error("SAPI5 speak error: %s", e)
            return ""

    def stop(self) -> None:
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                pass

    def get_voices(self) -> list[dict]:
        """Get list of SAPI5 voices. Uses win32com directly to bypass pyttsx3 voice parsing bug."""
        if not self._engine:
            return []
        try:
            import win32com.client
            tts = win32com.client.Dispatch("SAPI.SpVoice")
            voice_tokens = tts.GetVoices()
            result = []
            for i in range(voice_tokens.Count):
                voice = voice_tokens.Item(i)
                result.append({
                    "id": voice.Id,
                    "name": voice.GetDescription(),
                    "lang": "en",  # Will be refined if needed
                })
            return result
        except Exception as e:
            logger.debug("win32com voice listing failed: %s", e)
            # Fallback: return empty list — engine still works for speaking
            return []


class EdgeTTSEngine(TTSEngineBase):
    name = "edge"
    _subprocess = None

    def __init__(self):
        self.available = False
        self._voices_cache: list[dict] | None = None
        self._setup()

    def _setup(self):
        try:
            import edge_tts
            self.available = True
            logger.info("Edge TTS engine available")
        except ImportError:
            logger.warning("edge-tts not installed")
            self.available = False

    async def speak(self, text: str, voice: str = "", speed: float = 1.0) -> str:
        if not self.available:
            return ""
        try:
            import edge_tts
            voice = voice or "en-US-JennyNeural"
            rate = f"{int((speed - 1) * 100):+d}%"
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.close()
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            await communicate.save(tmp.name)
            if Path(tmp.name).exists() and Path(tmp.name).stat().st_size > 0:
                return tmp.name
            return ""
        except Exception as e:
            logger.error("Edge TTS error: %s", e)
            return ""

    def stop(self) -> None:
        pass  # edge-tts is stateless per request

    async def get_voices(self) -> list[dict]:
        if not self.available:
            return []
        # Cached after first fetch: list_voices is a network call that
        # would otherwise freeze the UI thread on every settings open.
        if self._voices_cache is not None:
            return self._voices_cache
        try:
            import edge_tts
            voices = await edge_tts.list_voices()
            self._voices_cache = [
                {"id": v["ShortName"], "name": v["FriendlyName"], "lang": v["Locale"]}
                for v in voices[:50]  # Limit for performance
            ]
            return self._voices_cache
        except Exception as e:
            logger.error("Edge TTS list_voices error: %s", e)
            return []


class OpenAITTSEngine(TTSEngineBase):
    name = "openai"

    def __init__(self):
        self.available = False
        self._client = None
        self._setup()

    def _setup(self):
        try:
            import openai
            key = os.environ.get("OPENAI_API_KEY", "")
            if key:
                self._client = openai.AsyncOpenAI(api_key=key)
                self.available = True
                logger.info("OpenAI TTS engine available")
        except Exception as e:
            logger.warning("OpenAI TTS unavailable: %s", e)

    async def speak(self, text: str, voice: str = "", speed: float = 1.0) -> str:
        if not self.available or not self._client:
            return ""
        try:
            voice = voice or "alloy"
            response = await self._client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text,
                speed=speed,
            )
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.close()
            await response.astream_to_file(tmp.name)
            if Path(tmp.name).exists() and Path(tmp.name).stat().st_size > 0:
                return tmp.name
            return ""
        except Exception as e:
            logger.error("OpenAI TTS error: %s", e)
            return ""

    def stop(self) -> None:
        pass

    def get_voices(self) -> list[dict]:
        if not self.available:
            return []
        return [
            {"id": "alloy", "name": "Alloy", "lang": "en"},
            {"id": "echo", "name": "Echo", "lang": "en"},
            {"id": "fable", "name": "Fable", "lang": "en"},
            {"id": "onyx", "name": "Onyx", "lang": "en"},
            {"id": "nova", "name": "Nova", "lang": "en"},
            {"id": "shimmer", "name": "Shimmer", "lang": "en"},
        ]


class TTSEngine:
    """
    High-level TTS engine with fallback chain.
    Fallback order: Edge TTS → SAPI5 → OpenAI TTS
    """

    def __init__(self, settings: dict | None = None):
        self.settings = settings or {}
        self._engines: dict[str, TTSEngineBase] = {}
        self._current_engine: str = ""
        self._init_engines()

    def _init_engines(self):
        """Initialize all available TTS engines."""
        edge = EdgeTTSEngine()
        sapi5 = SAPI5Engine()
        openai_tts = OpenAITTSEngine()
        self._engines = {
            "edge": edge,
            "sapi5": sapi5,
            "openai": openai_tts,
        }
        # Prefer configured default, else first available
        preferred = self.settings.get("default_engine", "") if isinstance(self.settings, dict) else ""
        order = ([preferred] if preferred else []) + ["edge", "sapi5", "openai"]
        for name in order:
            if name and name in self._engines and self._engines[name].available:
                self._current_engine = name
                break
        logger.info("TTS engines initialized. Default: %s", self._current_engine)

    def _engine_settings(self, engine_name: str) -> dict:
        """Per-engine settings (voice, speed) from the settings dict."""
        if not isinstance(self.settings, dict):
            return {}
        engines = self.settings.get("engines", {}) or {}
        cfg = engines.get(engine_name, {}) or {}
        return cfg if isinstance(cfg, dict) else {}

    def get_available_engines(self) -> list[str]:
        """Return list of available engine names."""
        return [name for name, eng in self._engines.items() if eng.available]

    def get_voices(self, engine: str = "") -> list[dict]:
        """Get voices for a specific engine (or current default)."""
        engine_name = engine or self._current_engine
        if engine_name not in self._engines:
            return []
        if engine_name == "edge":
            # Edge get_voices is async — run it
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._engines["edge"].get_voices())
            finally:
                loop.close()
        return self._engines[engine_name].get_voices()

    def set_engine(self, name: str) -> bool:
        """Switch to a specific TTS engine. Returns True if successful."""
        if name not in self._engines or not self._engines[name].available:
            return False
        self._current_engine = name
        logger.info("TTS engine switched to: %s", name)
        return True

    async def speak(
        self,
        text: str,
        engine: str = "",
        voice: str = "",
        speed: float = 0.0,
    ) -> str:
        """
        Speak text using specified or default engine.
        Falls back through available engines if primary fails.
        voice/speed default to the configured per-engine settings when
        not explicitly passed (speed=0.0 means "use settings").
        Returns path to generated audio file, or "" on failure.
        """
        engine_name = engine or self._current_engine
        es = self._engine_settings(engine_name)
        if not voice:
            voice = es.get("voice", "") or ""
        if not speed:
            try:
                speed = float(es.get("speed", 1.0) or 1.0)
            except (TypeError, ValueError):
                speed = 1.0

        # Try primary engine first
        engines_to_try = []
        if engine_name and engine_name in self._engines and self._engines[engine_name].available:
            engines_to_try.append(engine_name)

        # Then try current default
        if self._current_engine and self._current_engine not in engines_to_try:
            engines_to_try.append(self._current_engine)

        # Then try all available as fallback
        for name, eng in self._engines.items():
            if eng.available and name not in engines_to_try:
                engines_to_try.append(name)

        for eng_name in engines_to_try:
            try:
                result = await self._engines[eng_name].speak(text, voice, speed)
                if result:
                    logger.debug("TTS spoke via %s: %d chars", eng_name, len(text))
                    return result
            except Exception as e:
                logger.warning("TTS engine %s failed: %s", eng_name, e)
                continue

        logger.error("All TTS engines failed")
        return ""

    def stop(self) -> None:
        """Stop all TTS engines."""
        for eng in self._engines.values():
            try:
                eng.stop()
            except Exception:
                pass

    def announce(self, text: str) -> None:
        """Quick announcement (fire-and-forget, no file output)."""
        if not self._current_engine:
            return
        eng = self._engines.get(self._current_engine)
        if eng and eng.available:
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(eng.speak(text))
                loop.close()
            except Exception as e:
                logger.debug("Announce failed: %s", e)
