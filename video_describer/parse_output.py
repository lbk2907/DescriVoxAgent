"""Stage 3: parse the model's 'H:MM:SS - description' lines + exporters.

Accepted line shapes (lenient on purpose; GLM occasionally decorates):
  00:00:01 - A man enters the room
  0:00:01 - A man enters the room
  [00:00:01] A man enters the room
  1. 00:00:01 - A man enters the room
  00:01 - short form (treated as 00:00:MM:SS-style minutes)
Output: (seconds, text) pairs sorted by time. Export to JSON or SRT.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# H:MM:SS or M:SS or MM:SS, optional [ ] or leading "1." decoration,
# optional "-" separator, then description text.
_EVENT_RE = re.compile(
    r"^\s*(?:\d+[\.\)]\s*)?[\[\(]?\s*"
    r"(?:(?P<h>\d{1,2}):)?(?P<m>\d{1,2}):(?P<s>\d{2})"
    r"[\]\)]?\s*(?:[-–—:]\s*)?(?P<text>.+?)\s*$"
)


class ParseError(ValueError):
    pass


def _to_seconds(h: str | None, m: str, s: str) -> float:
    return (int(h) * 3600 if h else 0) + int(m) * 60 + int(s)


def parse_events(text: str) -> list[tuple[float, str]]:
    """Extract (seconds, description) pairs from model output."""
    events: list[tuple[float, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _EVENT_RE.match(line)
        if not m:
            continue
        text = m.group("text").strip()
        # A bare separator or punctuation is not a description.
        # [^\W_] = any Unicode letter or digit (no \p{L} in Python re)
        if not re.search(r"[^\W_]", text, re.UNICODE):
            continue
        events.append((
            _to_seconds(m.group("h"), m.group("m"), m.group("s")),
            text,
        ))
    events.sort(key=lambda x: x[0])
    return events


def require_events(text: str) -> list[tuple[float, str]]:
    """parse_events + guard: empty result raises ParseError."""
    events = parse_events(text)
    if not events:
        raise ParseError(
            "model output contained no 'H:MM:SS - description' lines")
    return events


def to_srt(events: list[tuple[float, str]]) -> str:
    """SRT cue list; end = next event's time (or start+3s for last)."""
    out: list[str] = []
    for i, (start, text) in enumerate(events):
        end = events[i + 1][0] if i + 1 < len(events) else start + 3.0
        out.append(f"{i + 1}\n{fmt_srt(start)} --> {fmt_srt(end)}\n{text}")
    return "\n\n".join(out) + ("\n" if out else "")


def fmt_srt(seconds: float) -> str:
    seconds = max(0.0, seconds)
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_json(events: list[tuple[float, str]]) -> str:
    return json.dumps(
        [{"start": s, "description": t} for s, t in events],
        ensure_ascii=False, indent=2)


def write_outputs(
    events: list[tuple[float, str]], out_dir: str | Path, stem: str,
) -> dict[str, Path]:
    """Write SRT + JSON next to each other; returns written paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    srt = out / f"{stem}.srt"
    js = out / f"{stem}.json"
    srt.write_text(to_srt(events), encoding="utf-8")
    js.write_text(to_json(events), encoding="utf-8")
    return {"srt": srt, "json": js}
