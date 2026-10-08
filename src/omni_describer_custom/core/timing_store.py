"""How long a model takes to watch a video, learned from real jobs (v1.8.4).

The upload itself can be measured byte by byte; what follows cannot. The
model watches the video and writes its answer in one silent wait that
lasts minutes (29 Sep 2026, Sintel on GLM: 295 s for a 10-minute part,
247 s for a 4.8-minute one). The only honest estimate is what the same
model took before, per second of video, so that is what is kept here.

An estimate is a guess and is presented as one: the progress bar never
reaches the end on it, and a wait that runs past it is said to be
"taking longer than usual" instead of counting below zero.
"""

from __future__ import annotations

import json
import logging
import threading

logger = logging.getLogger(__name__)

# Every request costs about a minute whatever its length, then some
# time per second of video. Measured on GLM (29 Sep 2026): 50 s of video
# took 80 s, 288 s took 247 s, 600 s took 295 s. A plain "seconds per
# second" promised 30 s for the 50 s clip.
OVERHEAD_SECONDS = 60.0
# Seconds of waiting per second of video beyond the overhead, before
# any job on this model was measured.
DEFAULT_RATIO = 0.4
# How much one new job moves the estimate (exponential average).
_WEIGHT = 0.5
_MIN_RATIO, _MAX_RATIO = 0.05, 10.0
_lock = threading.Lock()


def _path():
    from .settings_store import _get_config_dir

    return _get_config_dir() / "timing.json"


def _load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def ratio(key: str) -> float:
    """Seconds of waiting per second of video for this model."""
    try:
        value = float(_load().get(key, DEFAULT_RATIO))
    except (TypeError, ValueError):
        return DEFAULT_RATIO
    return min(_MAX_RATIO, max(_MIN_RATIO, value))


def expected_seconds(key: str, media_seconds: float) -> float:
    """How long the wait for this much video should take; 0 = unknown."""
    if media_seconds <= 0:
        return 0.0
    return OVERHEAD_SECONDS + ratio(key) * media_seconds


def record(key: str, media_seconds: float, took_seconds: float) -> None:
    """Learn from one finished wait. Never raises: it only improves a guess."""
    if media_seconds < 5 or took_seconds <= 0:
        return
    measured = min(_MAX_RATIO, max(_MIN_RATIO, (took_seconds - OVERHEAD_SECONDS) / media_seconds))
    with _lock:
        try:
            data = _load()
            old = data.get(key)
            new = measured if old is None else ((1 - _WEIGHT) * float(old) + _WEIGHT * measured)
            data[key] = round(new, 4)
            path = _path()
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
            tmp.replace(path)
        except Exception:
            logger.debug("timing record failed", exc_info=True)
