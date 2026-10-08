"""Pipeline orchestration: frames -> GLM (one request, all frames) ->
parse -> SRT/JSON (+ optional TTS narration).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from .frames import extract_frames
from .glm_describe import describe_video
from .parse_output import write_outputs


@dataclass
class PipelineResult:
    events: list[tuple[float, str]] = field(default_factory=list)
    frames: list[Path] = field(default_factory=list)
    output_dir: Path | None = None
    srt_path: Path | None = None
    json_path: Path | None = None
    audio_dir: Path | None = None
    batches: int = 1


async def run_pipeline(
    video_path: str | Path,
    out_dir: str | Path,
    api_key: str,
    base_url: str = "https://open.bigmodel.cn/api/paas/v4",
    model: str = "glm-5.3-flash",
    fps: float = 1.0,
    prompt: str | None = None,
    tts: bool = False,
    tts_engine: str = "edge",
    tts_voice: str = "ms-MY-OsmanNeural",
    max_frames_per_request: int = 150,
    lang: str = "",
    keep_frames: bool = True,
) -> PipelineResult:
    """Full pipeline. Raises on any stage failure (clear messages)."""
    video_path = Path(video_path)
    out = Path(out_dir)
    frames_dir = out / "frames"
    result = PipelineResult()

    # Stage 1: extraction with burned-in stamps
    result.frames = await extract_frames(video_path, frames_dir, fps=fps)
    if not result.frames:
        raise RuntimeError("no frames extracted")

    # Stage 2+3: one (auto-batched) GLM request + regex parse
    from .glm_describe import DESCRIPTOR_PROMPT, apply_lang

    result.batches = max(1, -(-len(result.frames) // max(1, max_frames_per_request)))
    result.events = await describe_video(
        result.frames,
        api_key,
        base_url=base_url,
        model=model,
        prompt=apply_lang(prompt or DESCRIPTOR_PROMPT, lang),
        max_frames_per_request=max_frames_per_request,
    )

    # Stage 4: outputs
    written = write_outputs(result.events, out, video_path.stem)
    result.output_dir = out
    result.srt_path = written["srt"]
    result.json_path = written["json"]

    if tts:
        from .tts_narrator import synthesize_events

        audio_dir = out / "audio"
        await synthesize_events(result.events, audio_dir, engine=tts_engine, voice=tts_voice)
        result.audio_dir = audio_dir

    if not keep_frames:
        import shutil

        shutil.rmtree(frames_dir, ignore_errors=True)
        result.frames = []
    return result


def run_pipeline_sync(*args, **kwargs) -> PipelineResult:
    """Blocking wrapper for scripts and the stdlib API server."""
    return asyncio.new_event_loop().run_until_complete(run_pipeline(*args, **kwargs))
