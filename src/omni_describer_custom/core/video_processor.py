"""
Omni Describer Custom — Video Processor.

Handles: video loading, frame extraction, scene change detection, transcript.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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


class VideoProcessor:
    """
    Video processing: frame extraction, scene detection, transcripts.
    Uses yt-dlp for download + ffmpeg for frame extraction.
    """

    def __init__(self, ffmpeg_path: str = "", ytdlp_path: str = ""):
        self.ffmpeg = ffmpeg_path or self._find_ffmpeg()
        self.ytdlp = ytdlp_path or self._find_ytdlp()
        logger.info("VideoProcessor: ffmpeg=%s, ytdlp=%s", self.ffmpeg, self.ytdlp)

    def _find_ffmpeg(self) -> str:
        """Find ffmpeg in bundled bin or PATH."""
        candidates = [
            Path(__file__).parent.parent.parent / "bin" / "ffmpeg.exe",
            Path(__file__).parent.parent / "bin" / "ffmpeg.exe",
            Path("C:/Users/USER/Documents/omni_describer/bin/ffmpeg.exe"),
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
            Path("C:/Users/USER/Documents/omni_describer/bin/yt-dlp.exe"),
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return "yt-dlp"

    async def get_video_info(self, path_or_url: str) -> VideoInfo:
        """Get video metadata using ffprobe."""
        info = VideoInfo(path=path_or_url)

        if Path(path_or_url).exists():
            info.path = str(Path(path_or_url).resolve())
            info.file_size_mb = Path(path_or_url).stat().st_size / (1024 * 1024)

        ffprobe = self.ffmpeg.replace("ffmpeg.exe", "ffprobe.exe")
        if not Path(ffprobe).exists():
            ffprobe = "ffprobe"

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
                    info.fps = eval(stream.get("r_frame_rate", "0/1"))
                elif stream.get("codec_type") == "audio":
                    info.has_audio = True

        except Exception as e:
            logger.error("ffprobe error: %s", e)
            info.has_audio = False

        return info

    async def extract_frames(
        self,
        video_path: str,
        fps: int = 5,
        output_dir: str = "",
        detect_scene_changes: bool = True,
    ) -> list[Frame]:
        """
        Extract frames at specified FPS.
        Optionally detect scene changes (skip similar consecutive frames).
        """
        output = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="odc_frames_"))
        output.mkdir(parents=True, exist_ok=True)

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
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode != 0:
                logger.error("ffmpeg error: %s", stderr.decode()[:200])
                return []
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
            return hex(int(bits, 2))[2:].zfill(4)
        except Exception:
            return ""

    def _deduplicate_frames(self, frames: list[Frame], threshold: float = 0.85) -> list[Frame]:
        """Remove near-duplicate consecutive frames based on hash similarity."""
        if len(frames) < 2:
            return frames

        def similarity(h1: str, h2: str) -> float:
            if not h1 or not h2:
                return 1.0
            matches = sum(c1 == c2 for c1, c2 in zip(h1, h2))
            return matches / max(len(h1), len(h2))

        deduped = [frames[0]]
        for frame in frames[1:]:
            if similarity(deduped[-1].scene_hash, frame.scene_hash) < threshold:
                deduped.append(frame)
            else:
                # Keep but mark as duplicate
                frame.scene_hash = deduped[-1].scene_hash + "_dup"

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
        """Parse WebVTT subtitle file."""
        segments = []
        try:
            text = Path(vtt_path).read_text(encoding="utf-8")
            for line in text.split("\n"):
                line = line.strip()
                if "-->" in line:
                    # Timestamp line
                    parts = line.split("-->")
                    start = self._parse_time(parts[0].strip())
                    end = self._parse_time(parts[1].strip())
                elif line and not line.startswith("WEBVTT") and not line.startswith("Kind"):
                    segments.append(TranscriptSegment(start=start, end=end, text=line))
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
