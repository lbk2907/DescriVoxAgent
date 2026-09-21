"""Speaking through whatever the computer already has.

The app was built around NVDA, because its author uses NVDA. Handed to
someone whose computer has no screen reader, it goes quiet: status
messages are announced by moving focus, which says nothing at all when
nothing is listening.

Prism (https://github.com/ethindp/prism) answers that. It finds the
screen reader that is actually running — NVDA, JAWS, ZDSR, ZoomText,
PC-Talker and others — and falls back to the Windows synthesisers
(SAPI, OneCore) when none is. One call reaches all of them.

What the backends can do differs sharply, and that difference decides
how the app uses them. Measured on this machine, 22 Sep 2026:

    NVDA      speak yes, is_speaking NO, to_memory no, rate no, voice no
    SAPI      speak yes, is_speaking yes, to_memory yes, rate yes, voice yes
    OneCore   speak yes, is_speaking yes, to_memory yes, rate yes, voice yes

A screen reader takes text and returns immediately; it will not say
when it has finished. So it cannot drive the player's narration hold —
the video would resume over the top of its own description. That is
not a limitation to work around, it is the reason the hold asks the
engine first.
"""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

# Backends that are somebody's screen reader rather than a plain
# synthesiser. When one of these is live the app must NOT duplicate
# its announcements: the user already hears the focus change.
_SCREEN_READER_BACKENDS = frozenset({
    "NVDA", "JAWS", "ZDSR", "ZoomText", "BoyPCReader", "PCTalker",
    "SenseReader", "SystemAccess", "WindowEyes", "Orca", "VoiceOver",
    "SpeechDispatcher", "AndroidScreenReader", "UIA",
})


class PrismSpeech:
    """One shared voice, resolved once and reused.

    Prism's Context and Backend both free native resources when
    collected, so both are held for the life of the object rather than
    re-created per call.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ctx = None
        self._backend = None
        self._features = None
        self.available = False
        self.backend_name = ""
        self.unavailable_reason = ""
        self._acquire()

    # ── setting up ───────────────────────────────────────────────

    def _acquire(self) -> None:
        try:
            import prism
        except Exception as e:
            self.unavailable_reason = f"prism not installed ({e})"
            logger.info("Prism speech unavailable: %s", self.unavailable_reason)
            return
        try:
            ctx = prism.Context()
            # ODC_PRISM_BACKEND forces one backend by name ("SAPI",
            # "OneCore", "NVDA"). The no-screen-reader path is otherwise
            # untestable on a developer machine that has NVDA running,
            # and that path is the whole reason this module exists.
            forced = os.environ.get("ODC_PRISM_BACKEND", "").strip()
            if forced:
                backend = ctx.create(ctx.id_of(forced))
                logger.info("Prism backend forced to %s by "
                            "ODC_PRISM_BACKEND", forced)
            else:
                backend = ctx.create_best()
            self._ctx = ctx
            self._backend = backend
            self._features = backend.features
            self.backend_name = backend.name
            self.available = True
            logger.info(
                "Prism speech ready: %s (screen reader: %s, can report "
                "speaking: %s)", self.backend_name, self.is_screen_reader,
                self.can_report_speaking)
        except Exception as e:
            self.unavailable_reason = f"no usable backend ({e})"
            logger.info("Prism speech unavailable: %s", self.unavailable_reason)

    def refresh(self) -> None:
        """Look again — a screen reader may have started or stopped."""
        with self._lock:
            self._ctx = self._backend = self._features = None
            self.available = False
            self.backend_name = ""
            self.unavailable_reason = ""
            self._acquire()

    # ── what this backend can do ─────────────────────────────────

    @property
    def is_screen_reader(self) -> bool:
        """True when the voice belongs to the user's screen reader."""
        return self.backend_name in _SCREEN_READER_BACKENDS

    @property
    def can_report_speaking(self) -> bool:
        """Can it tell us when a sentence has finished?

        False for every screen reader tested. The player's narration
        hold depends on this being true.
        """
        if not self.available or self._features is None:
            return False
        try:
            return bool(self._features.supports_is_speaking)
        except Exception:
            return False

    @property
    def speaking(self) -> bool:
        if not self.can_report_speaking:
            return False
        try:
            with self._lock:
                return bool(self._backend.speaking)
        except Exception:
            return False

    # ── speaking ─────────────────────────────────────────────────

    def speak(self, text: str, interrupt: bool = True) -> bool:
        """Say something. Returns False if nothing could say it.

        Does NOT wait: a screen reader cannot be waited for. Use
        speak_and_wait when the caller needs the end of the sentence.
        """
        if not self.available or not text.strip():
            return False
        try:
            with self._lock:
                self._backend.speak(text, interrupt)
            return True
        except Exception as e:
            logger.warning("Prism speak failed on %s: %s", self.backend_name, e)
            return False

    def speak_and_wait(self, text: str, timeout: float = 120.0) -> bool:
        """Say something and block until it has been said.

        Only honest on a backend that reports speaking state; on a
        screen reader it returns as soon as the text is handed over,
        because there is nothing to wait on. Callers that care must
        check can_report_speaking rather than assume this blocked.
        """
        if not self.speak(text, interrupt=True):
            return False
        if not self.can_report_speaking:
            return True
        deadline = time.monotonic() + timeout
        # Give the backend a moment to raise the flag before polling it,
        # or a fast start looks like an instant finish.
        time.sleep(0.05)
        while self.speaking and time.monotonic() < deadline:
            time.sleep(0.05)
        return True

    def stop(self) -> None:
        if not self.available:
            return
        try:
            with self._lock:
                self._backend.stop()
        except Exception as e:
            logger.debug("Prism stop failed: %s", e)


_shared: PrismSpeech | None = None
_shared_lock = threading.Lock()


def get_speech() -> PrismSpeech:
    """The app's single Prism voice, created on first use."""
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = PrismSpeech()
        return _shared


def announce(text: str) -> bool:
    """Speak a status message, but only when nothing else will.

    With a screen reader running, the app's own focus-move already
    announces the message; speaking it again through Prism would say
    everything twice. This exists for the machine that has no screen
    reader at all, where the focus move is silent.
    """
    speech = get_speech()
    if not speech.available or speech.is_screen_reader:
        return False
    return speech.speak(text, interrupt=True)
