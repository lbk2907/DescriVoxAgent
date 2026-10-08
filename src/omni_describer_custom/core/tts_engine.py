"""
Omni Describer Custom — Multi-engine TTS Engine.

Supports: SAPI5 (pyttsx3), Edge TTS (edge-tts), OpenAI TTS.
Fallback chain: Edge → SAPI5 → OpenAI.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import threading
import time
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _usable_or_discard(path: str | None) -> str:
    """Return `path` if it holds audio; otherwise delete it and return "".

    v1.7.4: engines create the temp file BEFORE synthesis, so every
    failed call (offline Edge, bad key) left an empty file in %TEMP% —
    one per cue, and the player retries failed cues every tick.
    """
    if not path:
        return ""
    try:
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            return path
    except OSError:
        pass
    _discard(path)
    return ""


def _discard(path: str | None) -> None:
    """Delete a temp file after a failed synthesis (may be partial)."""
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


class TTSEngineBase(ABC):
    """Abstract base class for TTS engines."""

    name: str = "base"
    available: bool = False

    # v1.6.6: an engine that speaks through something else — a screen
    # reader — produces no file to play. speak() cannot serve it, so
    # speak_and_play routes past the file path entirely.
    speaks_directly: bool = False

    # Whether the player may hold the video for a whole description.
    # True for engines that render to a file we play to completion,
    # because those finish when we say they finish.
    supports_hold: bool = True

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
    _lock = threading.Lock()

    def __init__(self):
        self.available = False
        self._setup()

    def _setup(self):
        try:
            import pyttsx3
            from pyttsx3.drivers.sapi5 import SAPI5Driver

            # Monkey-patch: fix SAPI5 voice ID bug — Language attribute
            # sometimes returns "409;9" instead of just "409"
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
        if not self.available:
            return ""
        tmp = None
        try:
            # Serialize COM access: SAPI5 is not thread-safe and the UI can
            # trigger overlapping speaks (Read button + playback narration).
            with self._lock:
                import pythoncom
                import win32com.client

                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp.close()
                pythoncom.CoInitialize()
                try:
                    # Render straight to a WAV file via SAPI's own file
                    # stream. This deliberately avoids pyttsx3's
                    # runAndWait(), whose second call on a cached engine
                    # can block forever.
                    stream = win32com.client.Dispatch("SAPI.SpFileStream")
                    stream.Open(tmp.name, 3, False)  # 3 = SSFMCreateForWrite
                    try:
                        tts = win32com.client.Dispatch("SAPI.SpVoice")
                        if voice:
                            tokens = tts.GetVoices()
                            for i in range(tokens.Count):
                                if tokens.Item(i).Id == voice:
                                    tts.Voice = tokens.Item(i)
                                    break
                        # speed 1.0 == normal rate; SAPI rate range is -10..10
                        tts.Rate = max(-10, min(10, int(round((speed - 1) * 10))))
                        tts.AudioOutputStream = stream
                        tts.Speak(text, 0)  # synchronous render to file
                    finally:
                        # Always close: if Speak raises, an open COM stream
                        # keeps the WAV locked past CoUninitialize (v1.5.4).
                        stream.Close()
                finally:
                    pythoncom.CoUninitialize()
            return _usable_or_discard(tmp.name)
        except Exception as e:
            logger.error("SAPI5 speak error: %s", e)
            _discard(tmp.name if tmp else None)
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
        tmp = None
        try:
            import edge_tts
            voice = voice or "en-US-JennyNeural"
            rate = f"{int((speed - 1) * 100):+d}%"
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.close()
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            await communicate.save(tmp.name)
            return _usable_or_discard(tmp.name)
        except Exception as e:
            logger.error("Edge TTS error: %s", e)
            _discard(tmp.name if tmp else None)
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
        tmp = None
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
            return _usable_or_discard(tmp.name)
        except Exception as e:
            logger.error("OpenAI TTS error: %s", e)
            _discard(tmp.name if tmp else None)
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


class PrismEngine(TTSEngineBase):
    """The voice the user already has: their screen reader.

    Added in v1.6.6 for a concrete complaint — handing the app to
    someone without NVDA left them with software they could not use.
    Prism reaches NVDA, JAWS, ZDSR, ZoomText, PC-Talker and the rest,
    and falls back to SAPI or OneCore on a machine with no reader at
    all, so there is always a voice.

    It speaks; it does not hand back a file. Voice and speed belong to
    the screen reader's own settings and are deliberately not fought
    over here — a blind user has already tuned their reader, and
    overriding that would be rude as well as usually impossible (NVDA
    reports supports_set_rate False).
    """

    name = "screen_reader"
    speaks_directly = True

    def __init__(self):
        from .speech import get_speech
        self._speech = get_speech()
        self.available = self._speech.available
        # Asked of the live backend rather than assumed: Prism on SAPI
        # can report speaking state, Prism on NVDA cannot.
        self.supports_hold = self._speech.can_report_speaking

    @property
    def backend_name(self) -> str:
        return self._speech.backend_name

    async def speak(self, text: str, voice: str = "", speed: float = 1.0) -> str:
        """No file is produced — see speak_direct.

        Returning "" rather than raising keeps the fallback chain in
        TTSEngine.speak() intact: callers that need a file (audio
        export) move on to an engine that can make one.
        """
        return ""

    def speak_direct(self, text: str) -> bool:
        """Say it, waiting only where waiting means something."""
        return self._speech.speak_and_wait(text)

    def stop(self) -> None:
        self._speech.stop()

    def get_voices(self) -> list[dict]:
        """Screen readers do not expose their voice list; they own it."""
        return []


# Engines that synthesise to a file the app plays itself, and so know
# when a description has finished being spoken. The player's automatic
# pause depends on that: see TTSEngine.supports_narration_hold.
# Kept as the fallback answer; an engine instance that knows better
# (PrismEngine asks its live backend) overrides it.
HOLD_CAPABLE_ENGINES = frozenset({"edge", "sapi5", "openai"})


class TTSEngine:
    """
    High-level TTS engine with fallback chain.
    Fallback order: Edge TTS → SAPI5 → OpenAI TTS
    """

    def __init__(self, settings: dict | None = None):
        self.settings = settings or {}
        self._engines: dict[str, TTSEngineBase] = {}
        self._current_engine: str = ""
        # v1.7.4: what is playing right now, so stop() can silence it.
        # stop() used to reach only the engines, never the playback, so
        # "Read Description" overlapped narration and closing the player
        # left a description talking.
        self._play_lock = threading.Lock()
        self._mci_aliases: set[str] = set()
        self._ffplay_procs: set = set()
        self._alias_seq = 0
        self._stop_gen = 0  # bumped by stop(); ends an async WAV wait
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
            "screen_reader": PrismEngine(),
        }
        # Prefer configured default, else first available. The screen
        # reader is not in the automatic order: it is a deliberate
        # choice, and picking it for someone who did not ask would
        # override the narration voice they had already set.
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

    def supports_narration_hold(self, engine: str = "") -> bool:
        """Can the player pause the video for the whole of a description?

        Only for engines that render speech to a file we then play to
        completion — there, speak_and_play returns when the sentence has
        actually finished, so the video can resume at the right moment.

        An engine that hands text to a screen reader returns as soon as
        the text is queued. Since v1.7.1 it can still hold when the
        reader's own audio can be listened to (`speech.can_report_speaking`,
        core/audio_meter.py, pitfall 46); when it cannot, there is no
        automatic hold and the player says so rather than offering a
        checkbox that does nothing.
        """
        name = engine or self._current_engine
        instance = self._engines.get(name)
        if instance is not None:
            return bool(getattr(instance, "supports_hold", True))
        return name in HOLD_CAPABLE_ENGINES

    def set_engine(self, name: str) -> bool:
        """Switch to a specific TTS engine. Returns True if successful."""
        if name not in self._engines or not self._engines[name].available:
            return False
        self._current_engine = name
        logger.info("TTS engine switched to: %s", name)
        return True

    # ── Real audio playback ─────────────────────────────────────

    def _play_file(self, path: str, start_gen: int | None = None) -> bool:
        """Play an audio file and block until finished. Returns True if played.

        start_gen (v1.9.6): the stop() generation the caller started
        under; a stop() since then ends playback at once (speak_and_play
        passes the one from BEFORE generating the speech).

        Playback chain (Windows-first):
        1. winsound for WAV files (built-in, reliable)
        2. Windows Media Control Interface (winmm.dll) for MP3/other formats
        3. ffplay (ffmpeg) if installed
        """
        if not path or not os.path.isfile(path):
            return False
        ext = os.path.splitext(path)[1].lower()

        if ext == ".wav" and sys.platform == "win32":
            try:
                import winsound
                duration = None
                try:
                    import wave
                    with wave.open(path, "rb") as wf:
                        duration = wf.getnframes() / float(wf.getframerate())
                except Exception:
                    duration = None
                if duration is None or not hasattr(self, "_play_lock"):
                    winsound.PlaySound(path, winsound.SND_FILENAME)  # blocks
                    return True
                # v1.7.4: async + wait on the known length, so stop()
                # can end it. A synchronous PlaySound cannot be stopped
                # from another thread (measured: PlaySound(None) did not
                # release it), and callers rely on this call blocking
                # until the audio finishes (the narration hold).
                with self._play_lock:
                    gen = self._stop_gen if start_gen is None else start_gen
                if self._stop_gen != gen:
                    return True  # stopped before it began
                winsound.PlaySound(
                    path, winsound.SND_FILENAME | winsound.SND_ASYNC
                    | winsound.SND_NODEFAULT)
                end = time.monotonic() + duration + 0.15
                while time.monotonic() < end:
                    if self._stop_gen != gen:
                        break
                    time.sleep(0.05)
                return True
            except Exception as e:
                logger.warning("winsound playback failed: %s", e)

        if sys.platform == "win32":
            try:
                import ctypes
                winmm = ctypes.windll.winmm
                with self._play_lock:
                    self._alias_seq += 1
                    alias = f"omni_tts_{os.getpid()}_{self._alias_seq}"
                cmd = f'open "{path}" type mpegvideo alias {alias}'
                if winmm.mciSendStringW(cmd, None, 0, 0) == 0:
                    # v1.7.4: no 'play ... wait'. An MCI device answers
                    # only the thread that opened it, so stop() from the
                    # UI thread could not end a blocking wait (measured).
                    # Play, then poll here until it ends or stop() bumps
                    # the generation; this thread also closes it.
                    with self._play_lock:
                        self._mci_aliases.add(alias)
                        gen = (self._stop_gen if start_gen is None
                               else start_gen)
                    try:
                        if winmm.mciSendStringW(f"play {alias}", None, 0, 0) == 0:
                            buf = ctypes.create_unicode_buffer(64)
                            deadline = time.monotonic() + 600
                            time.sleep(0.05)
                            while time.monotonic() < deadline:
                                if self._stop_gen != gen:
                                    winmm.mciSendStringW(
                                        f"stop {alias}", None, 0, 0)
                                    break
                                if winmm.mciSendStringW(
                                        f"status {alias} mode", buf, 64, 0) != 0:
                                    break
                                if buf.value == "stopped":
                                    break
                                time.sleep(0.05)
                    finally:
                        winmm.mciSendStringW(f"close {alias}", None, 0, 0)
                        with self._play_lock:
                            self._mci_aliases.discard(alias)
                    return True
            except Exception as e:
                logger.warning("MCI playback failed: %s", e)

        from .tools import find_tool
        for player in (find_tool("ffplay"),):
            try:
                proc = subprocess.Popen(
                    [player, "-nodisp", "-autoexit", "-loglevel", "quiet", path],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                with self._play_lock:
                    self._ffplay_procs.add(proc)
                    stopped = (start_gen is not None
                               and self._stop_gen != start_gen)
                if stopped:
                    proc.kill()  # stop() came before it was registered
                try:
                    proc.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    proc.kill()
                finally:
                    with self._play_lock:
                        self._ffplay_procs.discard(proc)
                return True
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.warning("%s playback failed: %s", player, e)
        return False

    def speak_and_play(self, text: str, engine: str = "", voice: str = "", speed: float = 0.0) -> bool:
        """Generate speech, play it through the speakers, and clean up.

        This is the audible path: the UI buttons should call this (directly
        or from a background thread) so the user actually hears the text.
        Returns True if audio was generated and played.

        v1.5.1: if generation fails (e.g. Edge TTS needs internet per
        sentence and the request times out), retry IMMEDIATELY with
        SAPI5 (offline Windows voice) so playback narration is never
        silently skipped.
        """
        # v1.6.6: a screen-reader engine speaks for itself; there is no
        # file to generate or play. Branch BEFORE speak(), because
        # speak() treats an empty path as failure and would fall
        # through to a different voice than the user chose.
        engine_name = engine or self._current_engine
        chosen = self._engines.get(engine_name)
        if chosen is not None and getattr(chosen, "speaks_directly", False):
            if not chosen.available:
                logger.warning("TTS engine %s is not available", engine_name)
                return False
            return chosen.speak_direct(text)

        # v1.9.6: the stop() generation BEFORE generating. Edge TTS is a
        # network round trip; a stop() pressed meanwhile was lost because
        # _play_file only read the generation afterwards, so the whole
        # clip still played (e.g. after closing the player).
        start_gen = getattr(self, "_stop_gen", 0)
        audio_path = ""
        try:
            loop = asyncio.new_event_loop()
            try:
                audio_path = loop.run_until_complete(self.speak(text, engine, voice, speed))
            finally:
                loop.close()
        except Exception as e:
            logger.error("speak_and_play generation failed: %s", e)
            return False
        if not audio_path:
            # speak() already falls back through EVERY available engine,
            # including offline SAPI5; retrying SAPI5 here only doubled
            # the delay before "nothing played" (v1.5.4 fix).
            return False
        try:
            if getattr(self, "_stop_gen", 0) != start_gen:
                # Stopped while the speech was generated: a deliberate
                # stop is not a failure (no retry, no "failed" message).
                logger.info("Speech stopped before playback; not played")
                return True
            played = self._play_file(audio_path, start_gen)
        finally:
            try:
                os.remove(audio_path)
            except OSError:
                pass
        return played

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
        """Stop all TTS engines AND any audio this engine is playing."""
        for eng in self._engines.values():
            try:
                eng.stop()
            except Exception:
                pass
        self._stop_playback()

    def _stop_playback(self) -> None:
        """Silence winsound, MCI and ffplay playback started by _play_file."""
        if not hasattr(self, "_play_lock"):
            return  # built without __init__ (tests); nothing was played
        with self._play_lock:
            self._stop_gen += 1
        if sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(None, 0)  # stops a sync SND_FILENAME play
            except Exception as e:
                logger.debug("winsound stop failed: %s", e)
            # MCI playback is stopped and closed by its own thread when it
            # sees _stop_gen change (see _play_file).
        with self._play_lock:
            procs = list(self._ffplay_procs)
        for proc in procs:
            try:
                proc.terminate()
            except Exception:
                pass

    def announce(self, text: str) -> None:
        """Quick announcement (fire-and-forget, no file output)."""
        if not self._current_engine:
            return
        eng = self._engines.get(self._current_engine)
        if eng and eng.available:
            try:
                if getattr(eng, "speaks_directly", False):
                    eng.speak_direct(text)
                    return
                loop = asyncio.new_event_loop()
                loop.run_until_complete(eng.speak(text))
                loop.close()
            except Exception as e:
                logger.debug("Announce failed: %s", e)
