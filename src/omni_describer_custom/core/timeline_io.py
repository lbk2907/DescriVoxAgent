"""
Omni Describer Custom — Timeline import/export.

Import descriptions from SRT / VTT / simple text files, export
descriptions to SRT / VTT, and render one synchronized audio file
(TTS per description placed at its start time via ffmpeg mixing).

Pure logic, no wx — standalone testable.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .project_store import Description

logger = logging.getLogger(__name__)

# ── Time formatting / parsing ────────────────────────────────────

_SRT_TIME = re.compile(
    r"^(?:(\d{1,3}):)?(\d{1,2}):(\d{2})(?:[,.](\d{1,3}))?$"
)

# Hours may run past 99 (fmt_srt_time writes 100:00:00,000) and the
# milliseconds may be absent ("00:00:03 --> 00:00:04", seen in the
# wild). The (?<!\d) stops a search starting inside "100:" at "00:".
_TIME_LINE = re.compile(
    r"(?<!\d)(\d{1,3}:)?(\d{1,2}):(\d{2})(?:[,.](\d{1,3}))?\s*-->\s*"
    r"(\d{1,3}:)?(\d{1,2}):(\d{2})(?:[,.](\d{1,3}))?"
)


def read_timed_text(path: str | Path) -> str:
    """Read a subtitle/text file whatever its encoding.

    Real files arrive as UTF-8 (with or without BOM), UTF-16 (Notepad
    "Unicode", Subtitle Edit) and ANSI/cp1252. Reading everything as
    UTF-8 with errors="replace" returned NO cues for UTF-16 and turned
    "Café" into "Caf" plus a replacement mark for cp1252, silently.
    """
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    # UTF-16 without a BOM: every other byte of ASCII text is NUL.
    if len(raw) >= 4 and raw.count(b"\x00") >= len(raw) // 4:
        enc = "utf-16-le" if raw[1:2] == b"\x00" else "utf-16-be"
        return raw.decode(enc, errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _secs(h: str | None, m: str, s: str, ms: str | None) -> float:
    # Group may arrive with ("00:") or without ("01") the trailing colon
    # depending on which regex captured it.
    hours = int(h.rstrip(":")) if h else 0
    millis = int((ms or "0").ljust(3, "0")[:3]) / 1000.0
    return hours * 3600 + int(m) * 60 + int(s) + millis


def fmt_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp HH:MM:SS,mmm."""
    seconds = max(0.0, seconds)
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def fmt_vtt_time(seconds: float) -> str:
    """Format seconds as WebVTT timestamp HH:MM:SS.mmm."""
    return fmt_srt_time(seconds).replace(",", ".")


def parse_timestamp(value: str) -> float | None:
    """Parse 'HH:MM:SS,mmm' / 'MM:SS.mmm' / 'H:MM:SS' style stamps."""
    value = value.strip()
    m = _SRT_TIME.match(value)
    if m:
        return _secs(m.group(1), m.group(2), m.group(3), m.group(4))
    # Bare seconds "12.5" or "12"
    try:
        return float(value)
    except ValueError:
        return None


# ── SRT / VTT parsing ────────────────────────────────────────────

def _iter_cue_blocks(text: str):
    """Yield (start, end, text_lines) from subtitle cue blocks."""
    block: list[str] = []
    for line in text.splitlines() + [""]:
        if line.strip():
            block.append(line)
            continue
        if block:
            yield _parse_cue_block(block)
            block = []


def _parse_cue_block(block: list[str]):
    for i, line in enumerate(block):
        m = _TIME_LINE.search(line)
        if m:
            start = _secs(m.group(1), m.group(2), m.group(3), m.group(4))
            end = _secs(m.group(5), m.group(6), m.group(7), m.group(8))
            text_lines = [
                re.sub(r"</?[^>]+>", "", l)  # strip basic tags
                for l in block[i + 1:]
                if l.strip()
            ]
            return start, end, "\n".join(text_lines).strip()
    return None


def parse_srt(path: str | Path) -> list[Description]:
    """Parse an SRT file into timed descriptions."""
    text = read_timed_text(path)
    descs = []
    for cue in _iter_cue_blocks(text):
        if cue and cue[2]:
            descs.append(Description(start_time=cue[0], end_time=cue[1], text=cue[2]))
    return descs


def parse_vtt(path: str | Path) -> list[Description]:
    """Parse a WebVTT file into timed descriptions."""
    return parse_srt(path)  # cue blocks are a superset; WEBVTT header yields no cue


# ── Simple text parsing ──────────────────────────────────────────

# "00:05 text", "0:00:05 text", "00:05 - 00:12 text", "90.5 text"
# Bare seconds need a decimal point or an "s" ("90.5", "90s"): a plain
# integer is too often the first word of prose — "2024 was a good year"
# became a cue at 2024 s and stretched the one before it to 33 minutes.
_SIMPLE_STAMP = r"(?:(?:\d{1,3}:)?\d{1,2}:\d{2}(?:[,.]\d{1,3})?|\d+\.\d+s?|\d+s)"
_SIMPLE_LINE = re.compile(
    rf"^\s*({_SIMPLE_STAMP})"
    rf"(?:\s*[-–—]\s*({_SIMPLE_STAMP}))?"
    r"\s+(.+)$"
)


def parse_simple(path: str | Path) -> list[Description]:
    """Parse a simple timed-text file: one description per line.

    Formats: 'TIMESTAMP text' or 'START - END text'.
    TIMESTAMP: H:MM:SS, M:SS, or bare seconds with a decimal point
    or an "s" suffix ("90.5", "90s").
    End time defaults to the next line's start (minimum 1 second).
    """
    descs = []
    for raw in read_timed_text(path).splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        m = _SIMPLE_LINE.match(raw)
        if not m:
            continue
        start = parse_timestamp(m.group(1).rstrip("s"))
        end = parse_timestamp(m.group(2).rstrip("s")) if m.group(2) else None
        if start is None:
            continue
        if end is None or end <= start:
            end = None
        text = re.sub(r"</?[^>]+>", "", m.group(3)).strip()
        descs.append(Description(start_time=start, end_time=end or 0.0,
                                 text=text))
    # Fill missing ends from next start
    for i, d in enumerate(descs):
        if d.end_time <= d.start_time:
            nxt = descs[i + 1].start_time if i + 1 < len(descs) else d.start_time + 8.0
            d.end_time = max(nxt - 0.05, d.start_time + 1.0)
    return descs


def parse_any(path: str | Path) -> list[Description]:
    """Parse SRT/VTT/simple text, dispatching on content and extension."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".srt":
        return parse_srt(p)
    if suffix == ".vtt":
        return parse_vtt(p)
    text = read_timed_text(p)
    # A real cue timing line, not just any "-->": a plain-text file
    # whose description contains an arrow used to be handed to the SRT
    # parser and came back empty.
    if text.lstrip().startswith("WEBVTT") or _TIME_LINE.search(text):
        return parse_srt(p)
    return parse_simple(p)


# ── SRT / VTT writing ────────────────────────────────────────────

def _cue_text(text: str) -> str:
    """Cue text safe inside one SRT/VTT block.

    A blank line ENDS a cue, so a description with a paragraph break
    was cut in half: the second paragraph vanished on re-import and
    other players mis-read the file. Blank lines are dropped and lone
    CRs normalised; the line breaks themselves are kept.
    """
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(ln for ln in text.split("\n") if ln.strip())


def _cue_end(d: Description) -> float:
    """An end time that is really after the start. 0 (or anything
    earlier than the start) used to write an invalid cue such as
    "00:00:10,000 --> 00:00:00,000"."""
    if d.end_time and d.end_time > d.start_time:
        return d.end_time
    return max(0.0, d.start_time) + MIN_CUE_SECONDS


def to_srt(descriptions: list[Description]) -> str:
    out = []
    for i, d in enumerate(sorted(descriptions, key=lambda d: d.start_time), 1):
        out.append(str(i))
        out.append(f"{fmt_srt_time(d.start_time)} --> {fmt_srt_time(_cue_end(d))}")
        out.append(_cue_text(d.text))
        out.append("")
    return "\n".join(out)


def to_vtt(descriptions: list[Description]) -> str:
    out = ["WEBVTT", ""]
    for i, d in enumerate(sorted(descriptions, key=lambda d: d.start_time), 1):
        out.append(str(i))
        out.append(f"{fmt_vtt_time(d.start_time)} --> {fmt_vtt_time(_cue_end(d))}")
        out.append(_cue_text(d.text))
        out.append("")
    return "\n".join(out)


# ── How long a description takes to say ──────────────────────────

# Words per second for a synthesised voice at normal speed. English
# TTS runs at roughly 150 words per minute, which is 2.5 a second; the
# user's own speed multiplier scales it. Used both to size a cue and to
# tell the model how much room a silent gap really holds.
WORDS_PER_SECOND_AT_1X = 2.5

# Below this, a cue is unreadable on the player timeline however short
# its text is.
MIN_CUE_SECONDS = 2.0


def speaking_seconds(text: str, speed: float = 1.0) -> float:
    """Roughly how long this description takes to speak aloud.

    Measured need: the model wrote 97 words for a 50-second clip that
    had 77 words of silence to put them in, and every cue was given a
    fixed three seconds regardless. A 36-word description in a 3-second
    cue overruns by ten seconds and lands on top of the dialogue.
    """
    words = len(str(text).split())
    rate = WORDS_PER_SECOND_AT_1X * max(0.5, float(speed or 1.0))
    return max(MIN_CUE_SECONDS, words / rate)


def silent_gaps(segments, start: float = 0.0, end: float | None = None,
                min_seconds: float = 1.0) -> list[tuple[float, float]]:
    """Stretches of the video where nobody is speaking.

    Built from the transcript the app already fetches. Gaps shorter
    than min_seconds are dropped: there is no useful description that
    fits in half a second, and offering one invites the model to try.
    """
    spans = []
    for seg in segments or []:
        s = float(getattr(seg, "start", 0.0))
        e = float(getattr(seg, "end", s))
        if e > s:
            spans.append((s, e))
    spans.sort()

    gaps: list[tuple[float, float]] = []
    cursor = float(start)
    for s, e in spans:
        if s - cursor >= min_seconds:
            gaps.append((cursor, s))
        cursor = max(cursor, e)
    if end is not None and float(end) - cursor >= min_seconds:
        gaps.append((cursor, float(end)))
    return gaps


# ── Audio export ─────────────────────────────────────────────────

def _ffmpeg() -> str:
    from .tools import find_tool, tool_available
    if not tool_available("ffmpeg"):
        raise RuntimeError(
            "ffmpeg not found — neither bundled with this app nor on "
            "PATH; audio export requires ffmpeg")
    return find_tool("ffmpeg")


def _ffprobe_duration(path: str | Path) -> float:
    from .tools import find_tool
    exe = find_tool("ffprobe")
    try:
        out = subprocess.run(
            [exe, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.strip()
        return float(out.splitlines()[0])
    except Exception:
        # Fall back to wave module for WAV files
        try:
            import wave
            with wave.open(str(path), "rb") as w:
                return w.getnframes() / float(w.getframerate() or 1)
        except Exception:
            return 0.0


def _to_wav(src: str | Path, dst: str | Path) -> None:
    """Normalize any audio to 44.1 kHz stereo PCM WAV for safe mixing."""
    subprocess.run(
        [_ffmpeg(), "-y", "-v", "error", "-i", str(src),
         "-ar", "44100", "-ac", "2", str(dst)],
        check=True, timeout=120,
    )


def _mix(wavs: list[Path], delays_ms: list[int], dst: str | Path) -> None:
    """Mix WAVs, each delayed by its delay (adelay), preserving volume."""
    if len(wavs) == 1:
        d = delays_ms[0]
        filt = f"[0:a]adelay={d}|{d}[a0]" if d else "[0:a]anull[a0]"
        subprocess.run(
            [_ffmpeg(), "-y", "-v", "error", "-i", str(wavs[0]),
             "-filter_complex", filt, "-map", "[a0]", str(dst)],
            check=True, timeout=300,
        )
        return
    parts = []
    inputs = []
    for i, (w, d) in enumerate(zip(wavs, delays_ms)):
        inputs += ["-i", str(w)]
        if d > 0:
            parts.append(f"[{i}:a]adelay={d}|{d}[d{i}]")
        else:
            parts.append(f"[{i}:a]anull[d{i}]")
    concat = "".join(f"[d{i}]" for i in range(len(wavs)))
    parts.append(
        f"{concat}amix=inputs={len(wavs)}:normalize=0:duration=longest[aout]"
    )
    subprocess.run(
        [_ffmpeg(), "-y", "-v", "error", *inputs,
         "-filter_complex", ";".join(parts), "-map", "[aout]", str(dst)],
        check=True, timeout=600,
    )


def export_audio(
    descriptions: list[Description],
    out_path: str | Path,
    tts,  # TTSEngine instance
    engine: str = "",
    voice: str = "",
    speed: float = 0.0,
    progress_cb=None,  # callable(done: int, total: int, skipped: int)
    *,
    is_cancelled=None,  # callable() -> bool; v1.9.6
) -> dict:
    """Render every description to speech and place each clip at its
    start time, producing one synchronized audio file.

    Returns {"path": str, "rendered": int, "skipped": int}.
    Raises RuntimeError on ffmpeg failure, RuntimeError("cancelled") when
    is_cancelled() turns true (checked every cue, before every mix and
    before the final encode; a speech request in flight is abandoned).
    Messages meant for a person are translated; the log keeps English.
    """
    from ..i18n.strings import t

    def check_cancel() -> None:
        if is_cancelled is not None and is_cancelled():
            raise RuntimeError("cancelled")

    descs = sorted(
        [d for d in descriptions if d.text.strip()],
        key=lambda d: d.start_time,
    )
    if not descs:
        logger.error("Audio export: no descriptions with text to render")
        raise ValueError(t("impexp.nothing_to_export"))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="omni_export_") as td:
        tmp = Path(td)
        clips: list[Path] = []
        delays: list[int] = []
        skipped = 0

        import asyncio

        async def _render_all():
            nonlocal skipped
            from .ai_engine import _run_cancellable
            for i, d in enumerate(descs):
                check_cancel()
                audio = await _run_cancellable(
                    tts.speak(d.text, engine, voice, speed), is_cancelled)
                if is_cancelled is not None and is_cancelled():
                    if audio:
                        Path(audio).unlink(missing_ok=True)
                    raise RuntimeError("cancelled")
                if progress_cb:
                    progress_cb(i + 1, len(descs), skipped)
                if not audio:
                    skipped += 1
                    continue
                wav = tmp / f"n{len(clips):05d}.wav"
                try:
                    _to_wav(audio, wav)
                finally:
                    # tts.speak() returns a NamedTemporaryFile(delete=False);
                    # remove the source clip after conversion (v1.5.4: one
                    # orphan WAV/MP3 per cue used to stay behind in
                    # %TEMP%) -- also when the conversion itself fails.
                    try:
                        Path(audio).unlink(missing_ok=True)
                    except OSError:
                        pass
                clips.append(wav)
                delays.append(int(round(d.start_time * 1000)))

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_render_all())
        finally:
            loop.close()
            asyncio.set_event_loop(None)

        if not clips:
            logger.error("Audio export: all TTS clips failed to synthesize")
            raise RuntimeError(t("impexp.all_clips_failed"))

        # Chunked mixing to keep ffmpeg command lines bounded
        chunk_size = 16
        level = [c for _, c in sorted(zip(delays, clips), key=lambda x: x[0])]
        level_delays = sorted(delays)
        stage = 0
        while len(level) > 1:
            nxt: list[Path] = []
            nxt_delays: list[int] = []
            for k in range(0, len(level), chunk_size):
                group = level[k:k + chunk_size]
                gdel = level_delays[k:k + chunk_size]
                base = gdel[0]
                gdel = [d - base for d in gdel]
                outk = tmp / f"mix{stage}_{k // chunk_size:04d}.wav"
                check_cancel()
                _mix(group, gdel, outk)
                nxt.append(outk)
                nxt_delays.append(base)
            level, level_delays = nxt, nxt_delays
            stage += 1

        # Final encode to requested container/format
        check_cancel()
        final_tmp = tmp / f"final{out_path.suffix or '.mp3'}"
        if out_path.suffix.lower() == ".wav":
            shutil.copyfile(level[0], final_tmp)
        else:
            subprocess.run(
                [_ffmpeg(), "-y", "-v", "error", "-i", str(level[0]),
                 "-c:a", "libmp3lame", "-q:a", "4", str(final_tmp)],
                check=True, timeout=600,
            )
        check_cancel()
        try:
            shutil.copyfile(final_tmp, out_path)
        except BaseException:
            out_path.unlink(missing_ok=True)  # never a half-written file
            raise

    return {"path": str(out_path), "rendered": len(descs) - skipped, "skipped": skipped}
