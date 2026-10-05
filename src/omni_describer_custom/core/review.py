"""Check descriptions against the picture after the AI writes them (v1.8.8).

Measured in phase 16.3 (docs/model-comparison.md): in full-video mode
most wrong descriptions are the RIGHT event at the WRONG moment. A second
look — 12 frames from 20 s before to 20 s after each description — finds
where it really happens, or that it happens nowhere. On two long films,
judged by an independent model, wrong descriptions fell from 39/209 to
23-27, for about $0.014 per film.

Settings > "Check descriptions against the video" (general.review_mode):

  off       no check (the default; the owner chose it, 30 Sep 2026)
  auto      "accurate" for a video long enough to be split into parts,
            "keep" for a short one (errors there were 0-8%)
  accurate  fewest wrong: leave what is already visible where it is,
            move what is not, remove what is visible nowhere
  most      most correct: move each to where it is clearest, remove
            what is visible nowhere (measured: more correct, a few
            correct ones spoiled)
  keep      never remove; only move what is not visible where it is

Frame mode is never checked: its times come from the frames themselves.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

MODES = ("off", "auto", "accurate", "most", "keep")
SPAN = 20.0              # seconds either side of a description
TILES = 12               # a 4 x 3 sheet
STEP = 2 * SPAN / (TILES - 1)
# An earlier match moves a description back only from 1.5 s: the
# measured sheets had no tile closer than 1.8 s, so smaller nudges were
# never part of what was measured (and are noise from the frame grid).
BACK = 1.5
AHEAD = 3.0              # a later match only when well ahead
CONCURRENCY = 8

PROMPT = (
    "You check one audio description for a blind viewer. The twelve "
    "frames come from the video, in time order, each labelled with its "
    "time. The description is currently placed at {at}.\n\n"
    "Description: \"{text}\"\n\n"
    "First: is what it describes visible in the frames within about four "
    "seconds AFTER {at} (where it is placed now)? Then: find the frame "
    "where it is MOST clearly visible. Judge only what you can see; "
    "ignore sound and style.\n"
    "Reply with JSON only: {{\"here\": true|false, \"best\": \"M:SS.S\" "
    "or \"none\", \"why\": \"<one short sentence>\"}}. Use \"none\" "
    "only if what it describes is visible in NONE of the frames.")


def resolve_mode(mode: str, parts: int) -> str:
    """The rule a job actually uses; "auto" depends on the video."""
    mode = (mode or "off").strip().lower()
    if mode not in MODES:
        return "off"
    if mode == "auto":
        return "accurate" if parts > 1 else "keep"
    return mode


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def _parse_clock(text: str) -> float | None:
    m = re.match(r"\s*(\d+):(\d+(?:\.\d+)?)\s*$", text or "")
    return int(m.group(1)) * 60 + float(m.group(2)) if m else None


def sheet_times(t: float, frame_count: int) -> list[float]:
    """Times of the TILES extracted frames around t: real frame times on
    the STEP grid, so a tile's label is exactly when its picture is from
    (labelling the time ASKED for put labels up to 1.8 s off and moved
    descriptions for nothing — found on the first real run)."""
    first = int(round((t - SPAN) / STEP))
    first = max(0, min(first, max(0, frame_count - TILES)))
    last = max(0, frame_count - 1)
    return [min(first + i, last) * STEP for i in range(TILES)]


def parse_answer(answer: str, times: list[float]) -> dict:
    """{"best": seconds | "none" | "", "here": bool}; "" = unusable."""
    m = re.search(r"\{.*\}", answer or "", re.S)
    try:
        got = json.loads(m.group(0)) if m else {}
    except ValueError:
        got = {}
    here = got.get("here") in (True, "true", "yes")
    best = str(got.get("best", "")).strip().lower()
    if best == "none":
        return {"best": "none", "here": here}
    when = _parse_clock(best)
    if when is None:
        return {"best": "", "here": here}
    # The nearest frame actually shown (models round).
    return {"best": min(times, key=lambda x: abs(x - when)), "here": here}


def decide(mode: str, answer: dict, t: float) -> tuple[str, float]:
    """("keep" | "move" | "drop", time) for one description."""
    best = answer.get("best", "")
    if best == "none":
        return ("keep", t) if mode == "keep" else ("drop", t)
    if not isinstance(best, (int, float)):
        return "keep", t
    early = best < t - BACK
    far = early or best > t + AHEAD
    if mode == "most":
        return ("move", float(best)) if far else ("keep", t)
    # accurate / keep: what is already visible where it is stays put,
    # unless it clearly STARTS earlier (a description should begin at or
    # before what it describes).
    if answer.get("here") and not early:
        return "keep", t
    return ("move", float(best)) if far else ("keep", t)


class FrameStrip:
    """Every STEP seconds of the video, extracted ONCE, as small images.

    A sheet per description would otherwise mean twelve ffmpeg seeks per
    description — about 1,400 for a 15-minute film.
    """

    def __init__(self, video: str, length: float,
                 is_cancelled: Callable[[], bool] | None = None):
        from .tools import find_tool
        self.dir = Path(tempfile.mkdtemp(prefix="odc_review_"))
        self.length = length
        try:
            self._extract(find_tool("ffmpeg"), video,
                          max(600, int(length * 2)), is_cancelled)
        except BaseException:
            self.close()
            raise
        self.frames = sorted(self.dir.glob("f_*.jpg"),
                             key=lambda p: int(p.stem.split("_")[1]))
        if not self.frames:
            raise RuntimeError("no frames could be read from the video")

    def _extract(self, ffmpeg: str, video: str, timeout: float,
                 is_cancelled: Callable[[], bool] | None) -> None:
        """Decode the whole video once. v1.9.6: Popen polled every 0.5 s
        so Cancel stops it (subprocess.run decoded a 24-minute film for
        up to 48 minutes with Cancel ignored)."""
        import time
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            [ffmpeg, "-hide_banner", "-nostdin", "-y", "-v",
             "error", "-i", video, "-vf",
             f"fps=1/{STEP:.4f},scale=400:-2", "-q:v", "5",
             str(self.dir / "f_%05d.jpg")],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            creationflags=flags)
        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    _, err = proc.communicate(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if is_cancelled and is_cancelled():
                    raise RuntimeError("cancelled")
                if time.monotonic() > deadline:
                    raise subprocess.TimeoutExpired(ffmpeg, timeout)
        finally:
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.communicate(timeout=5)
                except Exception:
                    pass
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode, ffmpeg,
                stderr=(err or b"")[-400:])

    def frame_at(self, seconds: float) -> Path:
        index = int(round(seconds / STEP))
        return self.frames[max(0, min(index, len(self.frames) - 1))]

    def sheet(self, t: float, out: Path) -> list[float]:
        """A labelled 4 x 3 sheet around t; returns the tile times."""
        from PIL import Image, ImageDraw, ImageFont
        times = sheet_times(t, len(self.frames))
        # The model reads these times; the measured sheets used 24 px.
        try:
            font = ImageFont.truetype("arial.ttf", 24)
        except OSError:
            font = ImageFont.load_default()
        tiles = [Image.open(self.frame_at(x)).convert("RGB") for x in times]
        w, h = tiles[0].size
        sheet = Image.new("RGB", (w * 4, h * 3))
        draw = ImageDraw.Draw(sheet)
        for i, (tile, at) in enumerate(zip(tiles, times)):
            x, y = (i % 4) * w, (i // 4) * h
            sheet.paste(tile.resize((w, h)), (x, y))
            label = _clock(at)
            box = draw.textbbox((x + 8, y + 6), label, font=font)
            draw.rectangle([box[0] - 4, box[1] - 3, box[2] + 4, box[3] + 3],
                           fill="black")
            draw.text((x + 8, y + 6), label, fill="yellow", font=font)
        sheet.save(out, quality=80)
        return times

    def close(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


async def review(engine, video: str, pairs: list[tuple[float, str]],
                 mode: str, length: float,
                 on_progress: Callable[[int, int], None] | None = None,
                 is_cancelled: Callable[[], bool] | None = None,
                 ) -> tuple[list[tuple[float, str]], dict]:
    """Check each (time, text); return the kept pairs and a summary.

    Never loses the job: a description whose check fails is kept as it
    was. Raises RuntimeError("cancelled") on Cancel.
    """
    summary = {"checked": 0, "moved": 0, "removed": 0, "failed": 0,
               "mode": mode}
    if mode == "off" or not pairs:
        return list(pairs), summary
    strip = await asyncio.to_thread(FrameStrip, video, length, is_cancelled)
    sem = asyncio.Semaphore(CONCURRENCY)
    done = 0
    results: list[tuple[str, float] | None] = [None] * len(pairs)

    async def one(i: int, t: float, text: str) -> None:
        nonlocal done
        async with sem:
            if is_cancelled and is_cancelled():
                raise RuntimeError("cancelled")
            sheet = strip.dir / f"sheet_{i:05d}.jpg"
            times = await asyncio.to_thread(strip.sheet, t, sheet)
            try:
                # v1.9.6: Cancel abandons a look in flight (up to
                # CONCURRENCY of them used to run to the end first).
                from .ai_engine import _run_cancellable
                answer = await _run_cancellable(
                    engine.look(str(sheet),
                                PROMPT.format(at=_clock(t), text=text)),
                    is_cancelled)
                results[i] = decide(mode, parse_answer(answer, times), t)
            except Exception as e:
                if str(e) == "cancelled" or (is_cancelled and is_cancelled()):
                    raise RuntimeError("cancelled") from None
                logger.warning("Review of description %d failed: %s", i, e)
                results[i] = ("failed", t)
            done += 1
            if on_progress:
                on_progress(done, len(pairs))

    tasks = [asyncio.ensure_future(one(i, float(t), text))
             for i, (t, text) in enumerate(pairs)]
    try:
        await asyncio.gather(*tasks)
    finally:
        # A cancelled/failed gather leaves the other checks running;
        # stop them before their frames are deleted.
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        strip.close()
    kept: list[tuple[float, str]] = []
    for (t, text), (action, new_t) in zip(pairs, results):
        summary["checked"] += 1
        if action == "drop":
            summary["removed"] += 1
            continue
        if action == "failed":
            summary["failed"] += 1
        if action == "move":
            summary["moved"] += 1
        kept.append((new_t, text))
    kept.sort(key=lambda p: p[0])
    logger.info("Review (%s): %s", mode, summary)
    return kept, summary
