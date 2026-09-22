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

from .tools import find_tool

logger = logging.getLogger(__name__)

# How the local transcript is decoded. Since v1.6.8 the app spends this
# transcript: it tells the model how many words fit in each silent gap,
# so a transcript that moves between runs moves the budget with it.
#
# Benchmarked across seven genuinely different videos, two runs each
# (tools/whisper_bench.py), against the previous defaults:
#
#                        not deterministic   clean Malay   music clip
#   old (fallback on)         3 of 7             35%      invented 17
#                                                         Korean lines
#   these settings            0 of 7             96%      correctly
#                                                         found silence
#
# temperature=0.0 — the default is a fallback LIST, and every value
#   above zero samples, so a hard passage is re-decoded at random until
#   it passes a threshold. That is the whole source of the drift: the
#   same file reported first speech at 30.0s, 30.0s, then 0.0s.
# condition_on_previous_text=False — stops one bad guess steering the
#   rest of the file.
# vad_filter — Silero decides what is speech BEFORE Whisper sees it.
#   This is what stops music being transcribed into confident nonsense.
#   threshold 0.3 rather than the 0.5 default because the cartoon and
#   news audio here is quiet in places; speech_pad_ms keeps the first
#   and last syllable of each line.
WHISPER_DECODE: dict = {
    "temperature": 0.0,
    "condition_on_previous_text": False,
    "vad_filter": True,
    "vad_parameters": {
        "threshold": 0.3,
        "min_speech_duration_ms": 100,
        "speech_pad_ms": 400,
    },
}

# Whisper's own threshold for "this text is a repeat loop".
WHISPER_COMPRESSION_LIMIT = 2.4


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
    has_audio: bool = False
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

    def __init__(self, ffmpeg_path: str = "", ytdlp_path: str = "",
                 settings=None):
        self.ffmpeg = ffmpeg_path or self._find_ffmpeg()
        self.ytdlp = ytdlp_path or self._find_ytdlp()
        # v1.6.1: transcription needs settings (which backend, which
        # Whisper model, the xAI key). Created here rather than required
        # from callers, so every existing VideoProcessor() still works.
        self._settings = settings
        logger.info("VideoProcessor: ffmpeg=%s, ytdlp=%s", self.ffmpeg, self.ytdlp)

    @property
    def settings(self):
        if self._settings is None:
            from .settings_store import SettingsStore
            self._settings = SettingsStore()
        return self._settings

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
        """ffprobe from the same place ffmpeg came from, else PATH.

        Keeping the pair together matters: a bundled ffmpeg with a
        system ffprobe can disagree about what a file contains.
        """
        if self.ffmpeg.lower().endswith("ffmpeg.exe"):
            candidate = Path(self.ffmpeg).with_name("ffprobe.exe")
            if candidate.exists():
                return str(candidate)
        return find_tool("ffprobe")

    def _find_ffmpeg(self) -> str:
        """Find ffmpeg — bundled copy first, then PATH."""
        return find_tool("ffmpeg")

    def _find_ytdlp(self) -> str:
        """Find yt-dlp — bundled copy first, then PATH."""
        return find_tool("yt-dlp")

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

        # v1.5.1 fix: create the communicate() task ONCE and shield it
        # per poll iteration. Re-calling proc.communicate() after a
        # timeout discards already-buffered stdout, which made the JSON
        # parse fail intermittently ("Expecting value: line 1 column 1").
        comm_task = asyncio.ensure_future(proc.communicate())

        async def _wait_cancellable() -> tuple[bytes, bytes]:
            # Poll loop: kill the subprocess as soon as cancel is noticed
            # (max 0.5s reaction time) instead of waiting out the timeout.
            deadline = 120.0
            waited = 0.0
            while True:
                if is_cancelled is not None and is_cancelled():
                    proc.kill()
                    try:
                        await comm_task
                    except Exception:
                        pass
                    raise SourceError(f"Download cancelled ({url})") from None
                try:
                    return await asyncio.wait_for(
                        asyncio.shield(comm_task), timeout=0.5)
                except asyncio.TimeoutError:
                    waited += 0.5
                    if waited >= deadline:
                        proc.kill()
                        try:
                            await comm_task
                        except Exception:
                            pass
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

    @staticmethod
    def _partial_bytes(out_dir: str) -> int:
        """Bytes already downloaded into out_dir, across .part files.

        Used only to tell the user a resume is happening; yt-dlp finds
        and continues the parts by itself.
        """
        try:
            return sum(p.stat().st_size
                       for p in Path(out_dir).glob("*.part") if p.is_file())
        except OSError:
            return 0

    # Files yt-dlp leaves behind that are not a playable result.
    _NOT_A_VIDEO = {".part", ".ytdl", ".tmp", ".temp"}

    @staticmethod
    def completed_download(out_dir: str) -> str:
        """The finished, MERGED video in out_dir, or "".

        Only the merged output counts. yt-dlp downloads the video and
        audio streams separately, naming them with the format id —
        video.f616.mp4, video.f251.webm — and merges them into
        video.mp4 at the end. An earlier version of this accepted any
        video.* that was not a .part, so an interrupted download whose
        video stream had finished was reported as complete and the app
        would have described a SILENT video while skipping the rest of
        the download. Caught on a real interrupted run, 22 Sep 2026.

        The merged file has exactly one suffix; the intermediates have
        two (.f616 + .mp4), which is what separates them.
        """
        try:
            for candidate in sorted(Path(out_dir).glob("video.*")):
                if not candidate.is_file() or candidate.stat().st_size <= 0:
                    continue
                suffixes = [s.lower() for s in candidate.suffixes]
                if len(suffixes) != 1:
                    continue  # video.f616.mp4, video.mp4.part, ...
                if suffixes[0] in VideoProcessor._NOT_A_VIDEO:
                    continue
                return str(candidate)
        except OSError:
            pass
        return ""

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
        # Only http(s) is supported; the leading "--" stops a crafted
        # URL from being parsed as a yt-dlp option (v1.5.4 hardening;
        # resolve_source() already gates this for the GUI flow, but
        # download_video() is public).
        if not url.lower().startswith(("http://", "https://")):
            raise SourceError(
                f"Unsupported video URL (http/https only): {url[:80]}")
        # v1.6.7: a caller that passes out_dir gets RESUMABLE downloads.
        # yt-dlp continues a .part file by default (-c is its default),
        # but every attempt used to land in a fresh mkdtemp, so the
        # partial from the interrupted attempt was orphaned in a
        # directory nobody looked at again. Measured: interrupted at
        # 4,193,280 bytes, restarted in the same directory, yt-dlp
        # printed "Resuming download at byte 4193280" and finished.
        # A fresh temp dir stays the fallback for callers with nowhere
        # stable to put it, where a restart simply starts over.
        out_dir = out_dir or tempfile.mkdtemp(prefix="odc_video_")
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        resuming = self._partial_bytes(out_dir)
        if resuming:
            logger.info("Resuming an interrupted download: %s already on "
                        "disk in %s", f"{resuming / 1e6:.1f} MB", out_dir)
        out_tmpl = str(Path(out_dir) / "video.%(ext)s")
        args = [
            self.ytdlp,
            "-f", f"bv*[height<={max_height}]+ba/b",  # merge-capable; height cap keeps it fast
            "--merge-output-format", "mp4",
            "-o", out_tmpl,
            "--no-playlist",
            "--newline",  # one progress line per update, parseable
        ]
        # v1.6.5: this format spec downloads video and audio separately
        # and merges them WITH FFMPEG, which yt-dlp looks for on PATH by
        # itself. Bundling ffmpeg is not enough — yt-dlp has to be told
        # where it is, or the download fails at the merge on any machine
        # without a system install.
        if Path(self.ffmpeg).is_absolute():
            args += ["--ffmpeg-location", str(Path(self.ffmpeg).parent)]
        args += ["--", url]
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
        # v1.6.7: this used to be sorted(glob("video.*"))[0], which sorts
        # video.f616.mp4 BEFORE video.mp4 and so returned the video-only
        # stream — a silent video — whenever an intermediate survived.
        # It normally does not, because yt-dlp deletes its own
        # intermediates after merging; but one left by an earlier
        # interrupted run is not yt-dlp's to clean, so making downloads
        # resumable exposed it. Found on a real interrupted run.
        merged = self.completed_download(out_dir)
        if merged:
            logger.info("Downloaded source: %s", merged)
            return merged
        leftovers = sorted(p.name for p in Path(out_dir).glob("video.*"))
        raise SourceError(
            f"Download finished but no merged video file in {out_dir} "
            f"({url}); found only {leftovers or 'nothing'}")

    async def resolve_source(
        self,
        path_or_url: str,
        on_progress: Callable[[DownloadProgress], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        out_dir: str = "",
    ) -> str:
        """
        Resolve a video source. Remote URLs (YouTube etc.) are downloaded
        via yt-dlp; local paths are returned unchanged.

        Pass out_dir — normally the project's media folder — to make the
        download resumable: an interrupted attempt continues from where
        it stopped next time instead of starting over (v1.6.7). Without
        it a throwaway temp dir is used and a restart re-downloads.

        A video already finished in out_dir is returned as-is, so
        reopening a project does not re-download what is already there.

        Raises SourceError with the REAL reason (bad URL, private video,
        network failure) instead of silently returning the URL, which used
        to surface later as a misleading "ERROR: No frames extracted".
        """
        if Path(path_or_url).exists():
            return str(Path(path_or_url).resolve())
        if not (path_or_url.startswith("http://") or path_or_url.startswith("https://")):
            return path_or_url
        if out_dir:
            done = self.completed_download(out_dir)
            if done:
                logger.info("Video already downloaded, skipping: %s", done)
                return done
        return await self.download_video(
            path_or_url, out_dir=out_dir, on_progress=on_progress,
            is_cancelled=is_cancelled)

    async def _probe_source_fps(self, video_path: str) -> float:
        """The video's own frame rate, or 0.0 when it cannot be read.

        Returning 0.0 rather than a guess matters: the caller only
        clamps when it KNOWS the source rate, so an unreadable probe
        leaves the user's setting alone instead of quietly overriding it.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                self._ffprobe_path(), "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            text = out.decode("utf-8", "replace").strip()
            if "/" in text:
                num, den = text.split("/", 1)
                return float(num) / float(den) if float(den) else 0.0
            return float(text) if text else 0.0
        except Exception as e:
            logger.debug("Source fps probe failed: %s", e)
            return 0.0

    async def extract_frames(
        self,
        video_path: str,
        fps: int = 5,
        output_dir: str = "",
        detect_scene_changes: bool = True,
        on_progress: Callable[[DownloadProgress], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        download_dir: str = "",
    ) -> list[Frame]:
        """
        Extract frames at specified FPS.
        Optionally detect scene changes (skip similar consecutive frames).

        Remote URLs are downloaded first (on_progress receives structured
        DownloadProgress: percent, MB downloaded/total, speed, ETA).
        Raises SourceError when the source cannot be resolved.

        download_dir makes that download resumable, the same as passing
        out_dir to resolve_source. v1.6.7 shipped without it for one
        release cycle: frame mode — the DEFAULT path, the one most runs
        take — reaches the download through here rather than calling
        resolve_source itself, so it kept using a throwaway temp dir
        while the full-video paths resumed. Found by cancelling a real
        run and seeing an empty project media folder.
        """
        video_path = await self.resolve_source(
            video_path, on_progress=on_progress, is_cancelled=is_cancelled,
            out_dir=download_dir)
        output = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="odc_frames_"))
        output.mkdir(parents=True, exist_ok=True)

        # Fail fast with a CLEAR reason for local files that do not exist,
        # instead of running ffmpeg and hiding the real error in a banner.
        if not Path(video_path).exists():
            logger.error("Frame extraction aborted: source not found: %s", video_path)
            return []

        # v1.6.3: never ask for more frames than the video contains.
        # Measured on a real 30 fps clip: requesting 60 fps made ffmpeg
        # DUPLICATE frames to reach the rate — 7,200 files and 208 MB of
        # JPEGs for two minutes, against 3,600 and 104 MB at 30 — and the
        # scene dedup then kept exactly the same 85 either way. Twice the
        # time and twice the disk for not one extra pixel of information.
        source_fps = await self._probe_source_fps(video_path)
        if source_fps and fps > source_fps:
            logger.info("Frame rate %d exceeds the source's %.0f fps; "
                        "using %.0f (higher only duplicates frames)",
                        fps, source_fps, source_fps)
            fps = max(1, int(source_fps))

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
            try:
                max_gap = float(self.settings.get(
                    "general.max_frame_gap", 30.0) or 0.0)
            except (TypeError, ValueError):
                max_gap = 30.0
            result = self._deduplicate_frames(result, max_gap=max_gap)

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

    @staticmethod
    def _apply_coverage_floor(kept: list[Frame], every: list[Frame],
                              max_gap: float) -> list[Frame]:
        """Put frames back wherever deduplication left the model blind.

        Deduplication compares each frame only with the last one it
        kept, so a stretch that does not change is reduced to a single
        frame however long it runs. Measured on a 120-second clip whose
        middle 100 seconds were one unchanging image: three frames
        survived, at 0s, 10s and 110s. For a hundred seconds the model
        had nothing to look at and could describe nothing, however much
        was said or happened in that time.

        A held shot is not the same as an empty one: a lecturer stands
        at a slide, text appears, someone shifts position — all of it
        well inside the 85% hash-similarity threshold that discards the
        frame. So the gap is bounded rather than the threshold loosened,
        which would undo deduplication everywhere else.

        Borrowed from devinilabs/claude-watch, which calls it a coverage
        floor and uses 45 seconds for study notes. Thirty is used here
        because this app has to DESCRIBE the picture, not summarise it.

        Frames are taken from `every` — real extracted frames at real
        timestamps — never invented.
        """
        if max_gap <= 0 or len(kept) < 2 or not every:
            return kept
        by_time = sorted(every, key=lambda f: f.timestamp)
        filled: list[Frame] = []
        for index, frame in enumerate(kept):
            filled.append(frame)
            if index + 1 >= len(kept):
                break
            start, end = frame.timestamp, kept[index + 1].timestamp
            span = end - start
            if span <= max_gap:
                continue
            needed = int(span // max_gap)
            for step in range(1, needed + 1):
                target = start + step * (span / (needed + 1))
                nearest = min(by_time, key=lambda f: abs(f.timestamp - target))
                if start < nearest.timestamp < end and nearest not in filled:
                    filled.append(nearest)
        filled.sort(key=lambda f: f.timestamp)
        added = len(filled) - len(kept)
        if added:
            logger.info("Coverage floor added %d frame(s) so no stretch "
                        "longer than %.0fs is left undescribed",
                        added, max_gap)
        return filled

    def _deduplicate_frames(self, frames: list[Frame], threshold: float = 0.85,
                            max_gap: float = 30.0) -> list[Frame]:
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
        return self._apply_coverage_floor(deduped, frames, max_gap)

    async def get_transcript(self, source: str,
                             local_path: str = "") -> list[TranscriptSegment]:
        """Get what is SAID in the video, as timed segments.

        v1.6.1: pass the ORIGINAL source here — the URL for a download,
        the file path for a local video. The two cases need opposite
        treatment, and the old code did neither: it returned early
        unless the argument was an existing local file, then asked
        yt-dlp to fetch subtitles, which only works for a URL. So it
        could never return anything, and nothing called it.

        Why this matters: GLM (the default provider) cannot hear the
        audio at all — probed 20 Sep 2026, it answers "NO AUDIO
        ACCESS". Handing the model a transcript is what lets it know
        what was said, so it can avoid repeating what the listener
        already hears, and so the `foreign` preset can convey speech.
        """
        is_url = "://" in source
        try:
            if is_url:
                segments = await self._ytdlp_subtitles(source)
            else:
                segments = await self._embedded_subtitles(source)
            if segments:
                logger.info("Transcript: %d segments from %s",
                            len(segments), "subtitles" if is_url else "file")
                return segments
        except Exception as e:
            logger.warning("Transcript fetch failed: %s", e)

        # Nothing published and nothing embedded: transcribe the audio.
        # Measured on a 19 s clip — published captions got "really long
        # TRUNKS", local Whisper heard "long hunts" — so this order is
        # deliberate: exact text first, machine transcription only when
        # there is none.
        audio_source = local_path or ("" if is_url else source)
        if audio_source and Path(audio_source).exists():
            try:
                segments = await self.transcribe_audio(audio_source)
                if segments:
                    return segments
            except Exception as e:
                logger.warning("Speech-to-text failed: %s", e)

        logger.info("No transcript available for %s",
                    "URL" if is_url else "local file")
        return []

    async def transcribe_audio(self, video_path: str) -> list[TranscriptSegment]:
        """Turn the spoken audio into timed text.

        Backends, in the order they are tried when set to "auto":

          grok    xAI speech-to-text, $0.10 per hour of audio, fast and
                  the most accurate of the three. Needs an `xai` API key.
          whisper faster-whisper running locally: free, offline, private.
                  Measured here at ~3.7x real time on CPU (base/int8), so
                  a two-hour film takes roughly half an hour.

        Set general.transcription_backend to "grok", "whisper" or "off"
        to pin one; "auto" (the default) uses Grok when a key exists and
        falls back to Whisper.
        """
        backend = str(self.settings.get(
            "general.transcription_backend", "auto") or "auto").lower()
        if backend == "off":
            return []

        if backend in ("auto", "grok"):
            key = (self.settings.get_ai_provider("xai") or {}).get("api_key")
            if key:
                try:
                    return await self._grok_transcribe(video_path, key)
                except Exception as e:
                    logger.warning("Grok STT failed: %s", e)
                    if backend == "grok":
                        return []
            elif backend == "grok":
                logger.info("Grok STT selected but no xai API key is set")
                return []

        if backend in ("auto", "whisper"):
            return await self._whisper_transcribe(video_path)
        return []

    @staticmethod
    def _looks_hallucinated(segment) -> bool:
        """Is this segment text Whisper invented rather than heard?

        Only the repeat loop is caught here, by the compression ratio
        Whisper itself uses to spot one. Measured: a real line scores
        1.7-2.8, while 27 seconds of "Mememememe..." scored 29.7.
        Turning the temperature fallback off removes the randomness but
        gives the model nowhere to retry, so these loops become more
        likely, not less — hence the filter.

        The OTHER kind of hallucination, plausible words invented over
        music, is not detectable this way: seventeen segments of Korean
        text on an English cooking video scored 1.8-1.9, well inside
        the normal range. The VAD filter is what handles that case, by
        never sending music to the model at all.
        """
        try:
            ratio = float(getattr(segment, "compression_ratio", 0.0) or 0.0)
        except (TypeError, ValueError):
            return False
        return ratio > WHISPER_COMPRESSION_LIMIT

    async def _whisper_transcribe(self, video_path: str) -> list[TranscriptSegment]:
        """Local faster-whisper. Imported lazily: the app must still run
        (and describe) on a machine where it was never installed."""
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            logger.info("faster-whisper is not installed; no local "
                        "transcription")
            return []

        size = str(self.settings.get(
            "general.whisper_model", "base") or "base")

        def _run() -> list[TranscriptSegment]:
            model = WhisperModel(size, device="cpu", compute_type="int8")
            segments, info = model.transcribe(
                video_path, beam_size=1, **WHISPER_DECODE)
            kept: list[TranscriptSegment] = []
            dropped = 0
            for s in segments:
                text = (s.text or "").strip()
                if not text:
                    continue
                if self._looks_hallucinated(s):
                    dropped += 1
                    continue
                kept.append(TranscriptSegment(start=float(s.start),
                                              end=float(s.end), text=text))
            logger.info("Whisper(%s): %d segments (%d dropped as "
                        "hallucination), %.0fs of %s audio",
                        size, len(kept), dropped, info.duration, info.language)
            return kept

        # Whisper is CPU-bound and blocks for minutes on a long video;
        # off the event loop it goes, or the cancel button dies with it.
        return await asyncio.get_running_loop().run_in_executor(None, _run)

    async def _grok_transcribe(self, video_path: str,
                               api_key: str) -> list[TranscriptSegment]:
        """xAI speech-to-text (grok-voice-transcribe-2.0).

        POST /v1/stt, multipart, with `file` last — the API requires that
        ordering. Returns word-level segments with start/end times, which
        is exactly the shape this app needs.
        """
        import aiohttp

        path = Path(video_path)
        if path.stat().st_size > 500 * 1024 * 1024:
            logger.warning("Grok STT limit is 500 MB; file is %.0f MB",
                           path.stat().st_size / 1e6)
            return []

        form = aiohttp.FormData()
        form.add_field("model", "grok-voice-transcribe-2.0")
        form.add_field("response_format", "verbose_json")
        form.add_field("file", path.read_bytes(), filename=path.name,
                       content_type="application/octet-stream")
        timeout = aiohttp.ClientTimeout(total=1800)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "https://api.x.ai/v1/stt",
                headers={"Authorization": f"Bearer {api_key}"},
                data=form,
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Grok STT HTTP {resp.status}: "
                                       f"{body[:200]}")
                data = await resp.json()

        segments = data.get("segments") or data.get("words") or []
        out = [
            TranscriptSegment(start=float(s.get("start", 0.0)),
                              end=float(s.get("end", 0.0)),
                              text=str(s.get("text", "")).strip())
            for s in segments if str(s.get("text", "")).strip()
        ]
        if not out and data.get("text"):
            # No timings came back: one block is still better than none.
            out = [TranscriptSegment(start=0.0,
                                     end=float(data.get("duration", 0.0)),
                                     text=str(data["text"]).strip())]
        logger.info("Grok STT: %d segments", len(out))
        return out

    async def _embedded_subtitles(self, video_path: str) -> list[TranscriptSegment]:
        """Pull a subtitle track out of a local file with ffmpeg.

        Many downloaded or ripped files carry one; when they do it is
        exact, free and instant — better than transcribing the audio.
        """
        if not Path(video_path).exists():
            return []
        tmp = tempfile.mkdtemp(prefix="odc_esub_")
        try:
            out = str(Path(tmp) / "track.vtt")
            proc = await asyncio.create_subprocess_exec(
                self.ffmpeg, "-y", "-i", video_path,
                "-map", "0:s:0", "-f", "webvtt", out,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=120)
            if Path(out).exists() and Path(out).stat().st_size > 0:
                return self._parse_vtt(out)
            return []
        except Exception as e:
            logger.debug("No embedded subtitles: %s", e)
            return []
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    async def _ytdlp_subtitles(self, video_url: str) -> list[TranscriptSegment]:
        """Fetch subtitles for a URL (uploaded or auto-generated).

        v1.6.1: the guard here used to be `if not Path(...).exists()`,
        which rejected every URL — the only input this can work on.
        """
        tmp = tempfile.mkdtemp(prefix="odc_sub_")
        try:
            proc = await asyncio.create_subprocess_exec(
                self.ytdlp,
                "--write-auto-sub",
                "--sub-lang", "en,ms,id",
                "--sub-format", "vtt",
                "--skip-download",
                "-o", str(Path(tmp) / "%(id)s.%(ext)s"),
                video_url,
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
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

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
