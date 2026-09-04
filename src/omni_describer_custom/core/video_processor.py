"""
Omni Describer Custom — Video Processor.

Handles: video loading, frame extraction, scene change detection, transcript.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class SourceError(RuntimeError):
    """Raised when a video source (URL or file) cannot be resolved/downloaded.

    Carries a user-presentable message so the UI can show the REAL reason
    instead of a generic "No frames extracted".
    """


@dataclass
class VideoInfo:
    """Video metadata."""
    path: str
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    title: str = ""
    has_audio: bool = True
    file_size_mb: float = 0.0


@dataclass
class Frame:
    """Extracted video frame."""
    path: str
    timestamp: float  # seconds
    scene_hash: str = ""  # for change detection


@dataclass
class TranscriptSegment:
    """Transcript segment with timing."""
    start: float
    end: float
    text: str


@dataclass
class DownloadProgress:
    """Parsed yt-dlp progress for one download phase (video/audio/merge)."""
    phase: str            # "preparing", "video", "audio", "merge"
    percent: float        # 0..100; -1 when unknown
    downloaded_mb: float  # -1 when unknown
    total_mb: float       # -1 when unknown
    speed: str = ""       # human-readable, e.g. "3.51MiB/s"
    eta: str = ""         # human-readable, e.g. "00:10"


class VideoProcessor:
    """
    Video processing: frame extraction, scene detection, transcripts.
    Uses yt-dlp for download + ffmpeg for frame extraction.
    """

    def __init__(self, ffmpeg_path: str = "", ytdlp_path: str = ""):
        self.ffmpeg = ffmpeg_path or self._find_ffmpeg()
        self.ytdlp = ytdlp_path or self._find_ytdlp()
        logger.info("VideoProcessor: ffmpeg=%s, ytdlp=%s", self.ffmpeg, self.ytdlp)

    @staticmethod
    def _stderr_tail(stderr: bytes, limit: int = 500) -> str:
        """Extract the useful part of ffmpeg/ffprobe stderr.

        ffmpeg prints its banner FIRST and the actual error LAST, so the
        tail (not the head) carries the diagnostic information.
        """
        text = stderr.decode("utf-8", errors="replace")
        lines = [
            ln for ln in text.splitlines()
            if ln.strip() and not ln.startswith((
                "ffmpeg version", "ffprobe version", "built with",
                "configuration:", "libav", "  ",
            ))
        ]
        return "\n".join(lines)[-limit:]

    @staticmethod
    def sanitize_project_name(title: str, fallback: str = "video") -> str:
        """v1.5.1: turn a video TITLE into a safe Windows folder/DB name.

        YouTube titles contain characters that are illegal in paths
        (\\ / : * ? " < > |) and can be arbitrarily long or empty. This
        strips/replaces illegal chars, trims length to 80, and falls
        back when nothing usable remains.
        """
        import re as _re
        text = (title or "").strip()
        if not text:
            return fallback
        # Replace path-illegal characters with a space, collapse whitespace
        text = _re.sub(r'[\\/:*?"<>|]+', " ", text)
        text = _re.sub(r"\s+", " ", text).strip(" .")
        if not text:
            return fallback
        return text[:80].rstrip(" .") or fallback

    def _ffprobe_path(self) -> str:
        """ffprobe next to ffmpeg when possible, else PATH."""
        if self.ffmpeg.lower().endswith("ffmpeg.exe"):
            candidate = Path(self.ffmpeg).with_name("ffprobe.exe")
            if candidate.exists():
                return str(candidate)
        return "ffprobe"

    def _find_ffmpeg(self) -> str:
        """Find ffmpeg in bundled bin or PATH."""
        candidates = [
            Path(__file__).parent.parent.parent / "bin" / "ffmpeg.exe",
            Path(__file__).parent.parent / "bin" / "ffmpeg.exe",
            Path.cwd() / "bin" / "ffmpeg.exe",
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        # Try PATH
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            return "ffmpeg"
        except Exception:
            pass
        return "ffmpeg"  # Hope for the best

    def _find_ytdlp(self) -> str:
        """Find yt-dlp."""
        candidates = [
            Path(__file__).parent.parent.parent / "bin" / "yt-dlp.exe",
            Path(__file__).parent.parent / "bin" / "yt-dlp.exe",
            Path.cwd() / "bin" / "yt-dlp.exe",
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return "yt-dlp"

    async def _probe_url(
            self, url: str,
            is_cancelled: Callable[[], bool] | None = None) -> dict:
        """Fetch remote metadata via yt-dlp --dump-json (no download).

        v1.5.1: honours is_cancelled — the probe can block up to 120s
        (slow YouTube pages), and previously Cancel had NO effect during
        it: the dialog kept "Loading video info..." forever (bug seen on
        the 9-minute video test).
        """
        proc = await asyncio.create_subprocess_exec(
            self.ytdlp,
            "--dump-json", "--no-playlist", "--no-warnings",
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def _wait_cancellable() -> tuple[bytes, bytes]:
            # Poll loop: kill the subprocess as soon as cancel is noticed
            # (max 0.5s reaction time) instead of waiting out the timeout.
            deadline = 120.0
            waited = 0.0
            while True:
                if is_cancelled is not None and is_cancelled():
                    proc.kill()
                    raise SourceError(f"Download cancelled ({url})") from None
                try:
                    return await asyncio.wait_for(
                        proc.communicate(), timeout=0.5)
                except asyncio.TimeoutError:
                    waited += 0.5
                    if waited >= deadline:
                        proc.kill()
                        raise SourceError(
                            f"Could not reach video metadata for {url} (timeout)") from None

        try:
            stdout, stderr = await _wait_cancellable()
        except asyncio.TimeoutError:
            proc.kill()
            raise SourceError(f"Could not reach video metadata for {url} (timeout)") from None
        if proc.returncode != 0:
            raise SourceError(
                self._ytdlp_error_text(url, stderr, fallback="video metadata unavailable"))
        try:
            return json.loads(stdout.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as e:
            raise SourceError(f"Could not parse video metadata for {url}: {e}") from e

    async def get_video_info(
            self, path_or_url: str,
            is_cancelled: Callable[[], bool] | None = None) -> VideoInfo:
        """Get video metadata using ffprobe (local) or yt-dlp (remote URL).

        v1.5.1: is_cancelled is forwarded to the yt-dlp metadata probe so
        Cancel reacts during the (up to 120s) info-loading phase.
        """
        info = VideoInfo(path=path_or_url)

        if path_or_url.startswith(("http://", "https://")) and not Path(path_or_url).exists():
            # Remote: use yt-dlp metadata. This also surfaces the REAL error
            # (e.g. private video, network failure) instead of a later crash.
            try:
                # v1.5.1: pass the cancel flag into the metadata probe so
                # Cancel reacts within ~0.5s even before the download starts.
                meta = await self._probe_url(
                    path_or_url,
                    is_cancelled=is_cancelled)
            except SourceError as e:
                logger.error("yt-dlp metadata failed: %s", e)
                raise
            info.title = str(meta.get("title", "")) or "video"
            info.duration = float(meta.get("duration") or 0.0)
            if meta.get("filesize") or meta.get("filesize_approx"):
                info.file_size_mb = float(meta.get("filesize") or meta.get("filesize_approx")) / (1024 * 1024)
            return info

        if Path(path_or_url).exists():
            info.path = str(Path(path_or_url).resolve())
            info.file_size_mb = Path(path_or_url).stat().st_size / (1024 * 1024)

        ffprobe = self._ffprobe_path()

        try:
            proc = await asyncio.create_subprocess_exec(
                ffprobe,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                info.path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            data = json.loads(stdout)
            fmt = data.get("format", {})
            info.duration = float(fmt.get("duration", 0))
            info.file_size_mb = float(fmt.get("size", 0)) / (1024 * 1024)
            info.title = fmt.get("tags", {}).get("title", "")

            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    info.width = stream.get("width", 0)
                    info.height = stream.get("height", 0)
                    rate = stream.get("r_frame_rate", "0/1")
                    try:
                        num, _, den = rate.partition("/")
                        info.fps = float(num) / float(den or 1)
                    except (ValueError, ZeroDivisionError):
                        info.fps = 0.0
                elif stream.get("codec_type") == "audio":
                    info.has_audio = True

        except Exception as e:
            logger.error("ffprobe error (%s): %s", ffprobe, e)
            info.has_audio = False

        return info

    @staticmethod
    def _ytdlp_error_text(url: str, stderr: bytes, fallback: str = "download failed") -> str:
        """User-presentable message from yt-dlp stderr (skip download progress lines)."""
        lines = [ln.strip() for ln in stderr.decode("utf-8", errors="replace").splitlines() if ln.strip()]
        for ln in reversed(lines):
            if ln.startswith("ERROR:"):
                return f"{ln} ({url})"
        return f"{fallback} ({url}): {lines[-1][:200] if lines else 'no details'}"

    @staticmethod
    def _parse_ytdlp_progress(line: str) -> "DownloadProgress | None":
        """Parse a yt-dlp --newline progress line.

        Real formats seen (captured from an actual download):
          [download]   0.5% of  218.53KiB at   62.49KiB/s ETA 00:03
          [download]  45.2% of ~ 51.02MiB at 3.51MiB/s ETA 00:10   (unknown total)
          [download] 100% of  218.53KiB in 00:00:00 at 703.57KiB/s  (finished)
        """
        m = re.match(
            r"\[download\]\s+(?P<pct>[\d.]+)% of\s+(?P<tilde>~)?\s*(?P<amt>[\d.]+)\s*(?P<unit>KiB|MiB|GiB)"
            r"(?: at\s+(?P<spd>[\d.]+)\s*(?P<spdu>KiB|MiB|GiB)/s)?"
            r"(?: ETA (?P<eta>\S+))?,?",
            line,
        )
        if not m:
            return None
        units = {"KiB": 1.0 / 1024, "MiB": 1.0, "GiB": 1024.0}
        amt_mb = float(m.group("amt")) * units[m.group("unit")]
        speed = ""
        if m.group("spd"):
            speed = f"{m.group('spd')}{m.group('spdu')}/s"
        return DownloadProgress(
            phase="preparing",
            percent=float(m.group("pct")),
            downloaded_mb=amt_mb if m.group("tilde") is None else amt_mb * float(m.group("pct")) / 100.0,
            total_mb=-1.0 if m.group("tilde") else amt_mb,
            speed=speed,
            eta=m.group("eta") or "",
        )

    async def download_video(
        self,
        url: str,
        out_dir: str = "",
        on_progress: Callable[[DownloadProgress], None] | None = None,
        max_height: int = 1080,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> str:
        """Download a remote video via yt-dlp and return the local file path.

        - Format selector ``bv*[height<=1080]+ba/b`` picks separate best video
          (capped at ``max_height`` to keep descriptions fast) + audio and lets
          yt-dlp merge them with ffmpeg. The old ``best[ext=mp4]/best``
          selector FAILED on modern YouTube because most videos no longer
          offer a combined video+audio stream
          ("Requested format is not available").
        - Raises SourceError with the real yt-dlp message instead of silently
          returning the URL.
        - on_progress is called with short status lines for the UI.
        """
        out_dir = out_dir or tempfile.mkdtemp(prefix="odc_video_")
        out_tmpl = str(Path(out_dir) / "video.%(ext)s")
        args = [
            self.ytdlp,
            "-f", f"bv*[height<={max_height}]+ba/b",  # merge-capable; height cap keeps it fast
            "--merge-output-format", "mp4",
            "-o", out_tmpl,
            "--no-playlist",
            "--newline",  # one progress line per update, parseable
            url,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            err_lines: list[str] = []
            phase = ["preparing"]
            cancel_flag = [False]
            timed_out = [False]

            def _on_line(text: str, is_err: bool) -> None:
                if is_err:
                    err_lines.append(text)
                    return
                if text.startswith("[download] Destination:"):
                    # First destination = video stream, second = audio stream
                    phase[0] = "audio" if phase[0] == "video" else "video"
                    return
                if text.startswith("[Merger]"):
                    phase[0] = "merge"
                    return
                p = self._parse_ytdlp_progress(text)
                if p:
                    p.phase = phase[0]
                    try:
                        if on_progress:
                            on_progress(p)
                    except Exception:
                        logger.debug("on_progress callback raised", exc_info=True)

            async def pump(stream, is_err: bool = False) -> None:
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace").strip()
                    if text:
                        _on_line(text, is_err)

            def _kill() -> None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass

            task = asyncio.ensure_future(asyncio.gather(
                pump(proc.stdout), pump(proc.stderr, True), proc.wait()))
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 1800
            try:
                while not task.done():
                    if is_cancelled is not None and is_cancelled():
                        cancel_flag[0] = True
                        _kill()
                    if loop.time() > deadline:
                        timed_out[0] = True
                        _kill()
                    try:
                        await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
                    except asyncio.TimeoutError:
                        pass
                await task
            except Exception as e:
                raise SourceError(f"yt-dlp download failed ({url}): {e}") from e
            if cancel_flag[0]:
                raise SourceError(f"Download cancelled ({url})")
            if timed_out[0]:
                raise SourceError(f"Download timed out after 30 minutes ({url})")
            if proc.returncode != 0:
                msg = self._ytdlp_error_text(
                    url, "\n".join(err_lines).encode("utf-8", "replace"))
                raise SourceError(msg)
        except SourceError:
            raise
        except Exception as e:
            raise SourceError(f"yt-dlp download failed ({url}): {e}") from e
        files = sorted(Path(out_dir).glob("video.*"))
        if files:
            logger.info("Downloaded source: %s", files[0])
            return str(files[0])
        raise SourceError(f"Download finished but no video file found in {out_dir} ({url})")

    async def resolve_source(
        self,
        path_or_url: str,
        on_progress: Callable[[DownloadProgress], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> str:
        """
        Resolve a video source. Remote URLs (YouTube etc.) are downloaded
        via yt-dlp into a temp dir; local paths are returned unchanged.

        Raises SourceError with the REAL reason (bad URL, private video,
        network failure) instead of silently returning the URL, which used
        to surface later as a misleading "ERROR: No frames extracted".
        """
        if Path(path_or_url).exists():
            return str(Path(path_or_url).resolve())
        if not (path_or_url.startswith("http://") or path_or_url.startswith("https://")):
            return path_or_url
        return await self.download_video(
            path_or_url, on_progress=on_progress, is_cancelled=is_cancelled)

    async def extract_frames(
        self,
        video_path: str,
        fps: int = 5,
        output_dir: str = "",
        detect_scene_changes: bool = True,
        on_progress: Callable[[DownloadProgress], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[Frame]:
        """
        Extract frames at specified FPS.
        Optionally detect scene changes (skip similar consecutive frames).

        Remote URLs are downloaded first (on_progress receives structured
        DownloadProgress: percent, MB downloaded/total, speed, ETA).
        Raises SourceError when the source cannot be resolved.
        """
        video_path = await self.resolve_source(
            video_path, on_progress=on_progress, is_cancelled=is_cancelled)
        output = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="odc_frames_"))
        output.mkdir(parents=True, exist_ok=True)

        # Fail fast with a CLEAR reason for local files that do not exist,
        # instead of running ffmpeg and hiding the real error in a banner.
        if not Path(video_path).exists():
            logger.error("Frame extraction aborted: source not found: %s", video_path)
            return []

        # ffmpeg frame extraction
        pattern = str(output / "frame_%04d.jpg")
        try:
            proc = await asyncio.create_subprocess_exec(
                self.ffmpeg,
                "-i", video_path,
                "-vf", f"fps={fps},scale=512:-1",
                "-q:v", "4",
                "-y",
                pattern,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # v1.5.1: killable ffmpeg — extraction of a long video can run
            # for minutes; Cancel must stop it immediately, not after the
            # whole run finishes.
            cancelled_ff = False
            # ONE communicate task for the whole loop: shielding a fresh
            # coroutine each iteration would leave the previous read
            # waiting ("read() called while another coroutine is already
            # waiting for incoming data").
            comm_task = asyncio.ensure_future(proc.communicate())
            try:
                while True:
                    if is_cancelled is not None and is_cancelled():
                        cancelled_ff = True
                        try:
                            proc.kill()
                        except ProcessLookupError:
                            pass
                        # kill closes the pipes, so comm_task ends promptly
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(comm_task), timeout=1.0)
                        break
                    except asyncio.TimeoutError:
                        continue
                if cancelled_ff:
                    raise SourceError(
                        f"Download cancelled ({video_path})")
                _, stderr = comm_task.result()
                if proc.returncode != 0:
                    # Log the TAIL of stderr: ffmpeg puts the real error last,
                    # the head is only the version banner.
                    logger.error(
                        "ffmpeg error (rc=%d): %s",
                        proc.returncode,
                        self._stderr_tail(stderr))
                    return []
            except SourceError:
                raise
            except Exception as e:
                logger.error("Frame extraction failed: %s", e)
                return []
        except SourceError:
            # v1.5.1: cancellation (and probe errors) propagate so the UI
            # shows "cancelled" instead of "no frames".
            raise
        except Exception as e:
            logger.error("Frame extraction failed: %s", e)
            return []

        frames = sorted(output.glob("frame_*.jpg"))
        result = []

        for i, frame_path in enumerate(frames):
            timestamp = i / fps
            frame_hash = ""
            if detect_scene_changes:
                frame_hash = self._hash_frame(frame_path)
            result.append(Frame(
                path=str(frame_path),
                timestamp=timestamp,
                scene_hash=frame_hash,
            ))

        # Deduplicate similar frames if scene detection enabled
        if detect_scene_changes and result:
            result = self._deduplicate_frames(result)

        logger.info("Extracted %d frames at %d FPS", len(result), fps)
        return result

    def _hash_frame(self, frame_path: str) -> str:
        """Simple perceptual hash for scene change detection."""
        try:
            from PIL import Image
            img = Image.open(frame_path)
            # Downscale to 16x16 grayscale for fast comparison
            small = img.resize((16, 16)).convert("L")
            pixels = list(small.getdata())
            avg = sum(pixels) / len(pixels)
            bits = "".join("1" if p > avg else "0" for p in pixels)
            # Fixed 64-char hex so leading zero bits are preserved
            return f"{int(bits, 2):064x}"
        except Exception:
            return ""

    def _deduplicate_frames(self, frames: list[Frame], threshold: float = 0.85) -> list[Frame]:
        """Remove near-duplicate consecutive frames based on hash similarity."""
        if len(frames) < 2:
            return frames

        def similarity(h1: str, h2: str) -> float:
            if not h1 or not h2:
                # Unknown hashes: never treat frames as duplicates,
                # otherwise all frames would be dropped.
                return 0.0
            matches = sum(c1 == c2 for c1, c2 in zip(h1, h2))
            return matches / max(len(h1), len(h2))

        deduped = [frames[0]]
        for frame in frames[1:]:
            if similarity(deduped[-1].scene_hash, frame.scene_hash) < threshold:
                deduped.append(frame)
            # else: near-duplicate of previous frame, skip

        removed = len(frames) - len(deduped)
        if removed > 0:
            logger.info("Dedup removed %d similar frames (%d → %d)", removed, len(frames), len(deduped))
        return deduped

    async def get_transcript(self, video_path: str) -> list[TranscriptSegment]:
        """
        Get transcript via yt-dlp subtitles or Whisper fallback.
        For local files, try embedded subtitles first.
        """
        # Try yt-dlp subtitles
        try:
            segments = await self._ytdlp_subtitles(video_path)
            if segments:
                return segments
        except Exception as e:
            logger.warning("yt-dlp subtitle fetch failed: %s", e)

        # TODO: Whisper fallback
        logger.info("No transcript available")
        return []

    async def _ytdlp_subtitles(self, video_path: str) -> list[TranscriptSegment]:
        """Extract subtitles using yt-dlp."""
        if not Path(video_path).exists():
            return []

        tmp = tempfile.mkdtemp(prefix="odc_sub_")
        try:
            proc = await asyncio.create_subprocess_exec(
                self.ytdlp,
                "--write-auto-sub",
                "--sub-lang", "en,ms,id",
                "--sub-format", "vtt",
                "--skip-download",
                "-o", str(Path(tmp) / "%(id)s.%(ext)s"),
                video_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            # Find subtitle files
            subs = list(Path(tmp).glob("*.vtt"))
            if not subs:
                return []

            # Parse first available subtitle
            segments = self._parse_vtt(subs[0])
            return segments
        except Exception as e:
            logger.warning("yt-dlp subtitle error: %s", e)
            return []

    def _parse_vtt(self, vtt_path: str) -> list[TranscriptSegment]:
        """Parse WebVTT subtitle file (block-based, tolerant of cue ids/settings)."""
        segments: list[TranscriptSegment] = []
        try:
            text = Path(vtt_path).read_text(encoding="utf-8", errors="replace")
            # Cues are separated by blank lines; each block may contain an
            # optional identifier line, a timestamp line, and cue text lines.
            blocks = re.split(r"\n\s*\n", text)
            for block in blocks:
                lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
                if not lines:
                    continue
                ts_idx = next((i for i, ln in enumerate(lines) if "-->" in ln), -1)
                if ts_idx == -1:
                    continue  # header, NOTE, STYLE, REGION, cue id without cue, etc.
                parts = lines[ts_idx].split("-->")
                start = self._parse_time(parts[0].strip())
                # Strip trailing cue settings (e.g. "align:start position:50%")
                end_raw = parts[1].strip().split()[0] if parts[1].strip() else "00:00:00.000"
                end = self._parse_time(end_raw)
                cue_text = " ".join(lines[ts_idx + 1:]).strip()
                if cue_text:
                    segments.append(TranscriptSegment(start=start, end=end, text=cue_text))
        except Exception as e:
            logger.error("VTT parse error: %s", e)
        return segments

    @staticmethod
    def _parse_time(timestamp: str) -> float:
        """Parse HH:MM:SS.mmm to seconds."""
        timestamp = timestamp.strip()
        parts = timestamp.split(":")
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        return float(parts[0])


# JSON is imported at the top of the file
