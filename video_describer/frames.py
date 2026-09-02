"""Stage 1: ffmpeg extraction with BURNED-IN H:MM:SS timestamps.

drawtext with %{pts:hms} prints the PRESENTATION timestamp of each
frame as H:MM:SS, so the AI later READS the stamp off the pixels
instead of guessing from frame order. Scale to 720p to keep each JPEG
well under the 5 MB / 6000x6000px API limits.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

# %{pts:hms} in a filter string: keep the escaping ffmpeg needs. We pass
# the args via list (create_subprocess_exec), so cmd-level escaping is
# not needed; the colon inside pts must be escaped for the filter graph.
# fontfile is added at build time: on Windows, drawtext without an
# explicit font file hits fontconfig (no default config -> crash).
_DRAWTEXT_BODY = (
    "text='%{pts\\:hms}':x=10:y=10:fontsize=28:"
    "fontcolor=white:box=1:boxcolor=black@0.6"
)

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/times.ttf",
    "C:/Windows/Fonts/calibri.ttf",
]


def _find_fontfile() -> str | None:
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            return p
    return None


# Width 1280 (720p on 16:9) is far below the 6000px limit while keeping
# stamps legible for the model. fps default 1 (user spec).
# NOTE: build_filter uses an f-string on purpose: the drawtext part has
# literal %{pts\:hms} braces that str.format would misread.


class FrameExtractorError(RuntimeError):
    pass


def _find_ffmpeg() -> str:
    from shutil import which
    found = which("ffmpeg")
    if found:
        return found
    local = Path(__file__).resolve().parent.parent / "bin" / ("ffmpeg.exe" if
        __import__("sys").platform == "win32" else "ffmpeg")
    if local.exists():
        return str(local)
    raise FrameExtractorError("ffmpeg not found on PATH or in bin/")


def build_filter(fps: float) -> str:
    """Return the full -vf value for the given fps (exported for tests).

    Verified against ffmpeg 8.x on Windows: the drive-letter colon must
    be BOTH escaped (C\\:/...) AND single-quoted inside the option, or
    the filtergraph parser rejects the drawtext filter. An explicit
    fontfile is mandatory here: without it drawtext loads fontconfig,
    which crashes (0xC0000005) when no default config exists.
    """
    fontfile = _find_fontfile()
    if not fontfile:
        raise FrameExtractorError(
            "no usable TrueType font found for timestamp burn-in "
            "(searched: " + ", ".join(_FONT_CANDIDATES) + ")")
    font_part = f"fontfile='{fontfile.replace(':', chr(92) + ':')}'"
    drawtext = f"drawtext={font_part}:{_DRAWTEXT_BODY}"
    return f"fps={_fmt_fps(fps)},scale=-2:720,{drawtext}"


def _fmt_fps(fps: float) -> str:
    return str(int(fps)) if float(fps).is_integer() else str(fps)


async def extract_frames(
    video_path: str | Path,
    output_dir: str | Path,
    fps: float = 1.0,
    on_progress=None,
    is_cancelled=None,
) -> list[Path]:
    """Extract frames at `fps` with burned-in H:MM:SS stamps.

    Returns frame paths sorted by number (chronological). Raises
    FrameExtractorError on failure; raises RuntimeError("cancelled")
    when is_cancelled turns True mid-run.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FrameExtractorError(f"video not found: {video_path}")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    ffmpeg = _find_ffmpeg()
    pattern = str(out / "frame_%05d.jpg")
    vf = build_filter(fps)
    cmd = [
        ffmpeg, "-hide_banner", "-nostdin",
        "-i", str(video_path),
        "-vf", vf,
        "-q:v", "3",
        "-y", pattern,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    async def pump(stream, is_err: bool = False) -> None:
        while True:
            line = await stream.readline()
            if not line:
                break
            if on_progress and not is_err:
                try:
                    on_progress(line.decode("utf-8", "replace").strip())
                except Exception:
                    pass

    async def watch_cancel() -> None:
        while True:
            if is_cancelled and is_cancelled():
                proc.kill()
                raise RuntimeError("cancelled")
            await asyncio.sleep(0.25)

    cancel_task = asyncio.create_task(watch_cancel()) if is_cancelled else None
    try:
        await asyncio.gather(
            pump(proc.stdout), pump(proc.stderr, is_err=True), proc.wait())
    finally:
        if cancel_task:
            cancel_task.cancel()

    if proc.returncode != 0:
        # stderr was consumed by pump; rerun quietly to capture the
        # reason (cheap: extraction failed fast anyway)
        cap = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, err = await cap.communicate()
        tail = err.decode("utf-8", "replace")[-500:]
        raise FrameExtractorError(f"ffmpeg failed ({proc.returncode}): {tail}")

    frames = sorted(
        out.glob("frame_*.jpg"), key=lambda p: _frame_index(p.name))
    if not frames:
        raise FrameExtractorError("ffmpeg produced no frames")
    return frames


def _frame_index(name: str) -> int:
    m = re.search(r"(\d+)\.jpg$", name)
    return int(m.group(1)) if m else 0
