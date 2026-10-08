"""Standalone video describer pipeline.

Pipeline: ffmpeg frame extraction with BURNED-IN timestamps (drawtext)
-> ALL frames base64 in ONE GLM-5.3-Flash request (auto-batched above
150 frames) -> model reads the on-screen H:MM:SS stamps -> regex parse
-> SRT/JSON output, optional TTS narration audio.

CLI:
    python -m video_describer describe VIDEO [--fps 1] [--tts]
    python -m video_describer serve [--port 8765]

API server (stdlib only):
    GET  /health
    POST /describe        {"video_path": ..., "fps": 1, "tts": false}
    POST /describe/upload?name=v.mp4&fps=1&tts=0   (raw video bytes)
    POST /parse           {"text": "00:00:01 - ..."}  (parse only)
"""

from .pipeline import run_pipeline, PipelineResult

__all__ = ["run_pipeline", "PipelineResult"]
__version__ = "0.1.0"
