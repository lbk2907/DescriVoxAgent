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
when it has finished. v1.6.6 treated that as the end of the matter and
refused the narration hold for any screen-reader voice.

That was too absolute. v1.7.1 listens for the end instead: the
reader's own process falls silent when the sentence is over, and
Windows meters every process's audio (core/audio_meter.py). That works
on any NVDA version, because it asks nothing of NVDA. The API route —
NVDA's synchronous speakSsml — was measured and rejected: on NVDA
2025.3 it hung on the first call, a race fixed only in NVDA 2026.2.
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
_SCREEN_READER_BACKENDS = frozenset(
    {
        "NVDA",
        "JAWS",
        "ZDSR",
        "ZoomText",
        "BoyPCReader",
        "PCTalker",
        "SenseReader",
        "SystemAccess",
        "WindowEyes",
        "Orca",
        "VoiceOver",
        "SpeechDispatcher",
        "AndroidScreenReader",
        "UIA",
    }
)


# Process image names for screen readers whose audio can be metered to
# tell when a sentence ends (core/audio_meter.py). NVDA is measured on
# this machine. JAWS runs as jfw.exe, which Freedom Scientific documents.
# Readers not listed simply get no narration hold, as before.
_READER_PROCESSES: dict[str, tuple[str, ...]] = {
    "NVDA": ("nvda.exe",),
    "JAWS": ("jfw.exe",),
}


# How long a synthesiser may take to START speaking before a wait gives
# up on it. Matches audio_meter.START_GRACE.
START_GRACE_SECONDS = 1.5


def _estimate_seconds(text: str) -> float:
    """How long to wait when nothing can say the sentence is over.

    Deliberately slow (normal speed, 2.5 words a second) — this user's
    NVDA was measured at about 6 — because waiting too long costs a
    moment of paused video and waiting too little talks over the end of
    the description.
    """
    from .timeline_io import speaking_seconds

    return speaking_seconds(text, 1.0)


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
                logger.info("Prism backend forced to %s by ODC_PRISM_BACKEND", forced)
            else:
                backend = ctx.create_best()
            self._ctx = ctx
            self._backend = backend
            self._features = backend.features
            self.backend_name = backend.name
            self.available = True
            logger.info(
                "Prism speech ready: %s (screen reader: %s, can report speaking: %s)",
                self.backend_name,
                self.is_screen_reader,
                self.can_report_speaking,
            )
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
    def _natively_reports(self) -> bool:
        """The backend itself says when it is speaking (SAPI, OneCore)."""
        if not self.available or self._features is None:
            return False
        try:
            return bool(self._features.supports_is_speaking)
        except Exception:
            return False

    @property
    def _meter(self):
        """An audio meter on this screen reader's process, if one fits.

        Only readers whose process name is known are listed. A wrong
        name would simply find nothing and fall back, but a name is not
        claimed here without a reason to believe it.
        """
        names = _READER_PROCESSES.get(self.backend_name)
        if not names:
            return None
        from . import audio_meter

        if not audio_meter.available():
            return None
        return audio_meter.ReaderMeter(names)

    @property
    def can_report_speaking(self) -> bool:
        """Can the app tell when a sentence has finished?

        True for synthesisers that report it themselves, and — since
        v1.7.1 — for screen readers whose process can be listened to.
        NVDA gives no such signal on any released version that does not
        hang (see core/audio_meter.py), so the answer for NVDA comes
        from its audio, not from NVDA.
        """
        return self._natively_reports or self._meter is not None

    @property
    def speaking(self) -> bool:
        if not self._natively_reports:
            return False
        try:
            with self._lock:
                return bool(self._backend.speaking)
        except Exception:
            return False

    # ── speaking ─────────────────────────────────────────────────

    def speak(self, text: str, interrupt: bool = True) -> bool:
        """Say something. Returns False if nothing could say it.

        Does NOT wait. Use speak_and_wait when the caller needs the end
        of the sentence.
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

        Three ways to know, best first:

          1. the backend reports it (SAPI, OneCore);
          2. the screen reader's audio is heard falling silent;
          3. neither is possible — wait as long as the text should take
             to say, estimated slowly so the video waits a little too
             long rather than resuming over the end of the sentence.

        Never waits past `timeout`, so a reader that keeps talking —
        or a meter that misreads — cannot freeze the player.
        """
        t0 = time.monotonic()
        meter = None if self._natively_reports else self._meter
        if meter is not None:
            # The meter must be ready BEFORE the speech starts, so it is
            # handed the speak call rather than following it.
            limit = min(timeout, max(15.0, _estimate_seconds(text) * 3))
            outcome = meter.speak_and_wait(lambda: self.speak(text, interrupt=True), limit)
            # INFO, not DEBUG: whether the meter heard the end or fell
            # back to an estimate is the first question any report of
            # "the pause was wrong" will need answering.
            logger.info(
                "Speech end via audio meter on %s: %s (%.1fs)",
                self.backend_name,
                outcome,
                time.monotonic() - t0,
            )
            if outcome == "not-spoken":
                return False
            if outcome in ("finished", "timeout"):
                return True
            # "no-sound" / "no-meter": the meter could not hear this
            # reader, so fall back to the estimate below.
            remaining = _estimate_seconds(text) - (time.monotonic() - t0)
            if remaining > 0:
                time.sleep(min(remaining, timeout))
            return True

        if not self.speak(text, interrupt=True):
            return False

        if self._natively_reports:
            deadline = t0 + timeout
            # Wait for the flag to go UP before waiting for it to go
            # down, or a slow start looks like an instant finish. A fixed
            # 0.05 s head start lost that race about 1 run in 10 (v1.7.6,
            # test_fixes26: returned after 0.08 s) — the player would
            # resume the video over the description.
            start_by = min(deadline, time.monotonic() + START_GRACE_SECONDS)
            while not self.speaking and time.monotonic() < start_by:
                time.sleep(0.02)
            while self.speaking and time.monotonic() < deadline:
                time.sleep(0.05)
            return True

        remaining = _estimate_seconds(text) - (time.monotonic() - t0)
        if remaining > 0:
            time.sleep(min(remaining, timeout))
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
