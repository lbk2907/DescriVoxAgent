"""Stage 2: send ALL frames as base64 in ONE GLM-5.3-Flash request.

The model must READ the burned-in H:MM:SS stamp on each frame (not
infer from order) and output one line per event:
    H:MM:SS - description
Requests above MAX_FRAMES_PER_REQUEST frames are split into batches so
a single request stays inside practical limits; batch results are
merged by timestamp. Zhipu limits: 5 MB per image, 6000x6000 px max.
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import aiohttp

from .parse_output import parse_events

DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_MODEL = "glm-5.3-flash"
MAX_FRAMES_PER_REQUEST = 150
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_DIM = 6000

DESCRIPTOR_PROMPT = (
    "You are a professional audio-description writer for blind "
    "audiences. You are given consecutive frames from ONE video. Each "
    "frame has its timestamp H:MM:SS BURNED INTO the top-left corner "
    "on a dark box. READ that burned-in timestamp for every frame "
    "instead of inferring it from the frame order. Identify the key "
    "visual events and reply with ONE line per event in EXACTLY this "
    "format and nothing else:\n"
    "H:MM:SS - description\n"
    "Rules: use the burned-in timestamps verbatim; one line per "
    "event; descriptions in the same language as any on-screen text "
    "unless told otherwise; no numbering, no markdown, no extra "
    "commentary."
)

# v1.5.2: output-language directives (GUI has its own in ai_engine).
_LANG_DIRECTIVES = {
    "ms": " Write EVERY description in Bahasa Malaysia (Malay); never mix English.",
    "en": " Write EVERY description in English; do not use any other language.",
}


def apply_lang(prompt: str, lang: str) -> str:
    """Append an output-language directive (no-op for unknown)."""
    d = _LANG_DIRECTIVES.get((lang or "").strip().lower())
    return prompt + d if d else prompt


class GLMError(RuntimeError):
    pass


def check_frame_limits(paths: list[Path]) -> None:
    """Raise GLMError when any frame breaks the documented API limits."""
    from PIL import Image

    for p in paths:
        size = p.stat().st_size
        if size > MAX_IMAGE_BYTES:
            raise GLMError(f"{p.name} is {size} bytes (> 5MB limit)")
        with Image.open(p) as im:
            w, h = im.size
        if w > MAX_IMAGE_DIM or h > MAX_IMAGE_DIM:
            raise GLMError(f"{p.name} is {w}x{h} (> 6000x6000 limit)")


def encode_frame(path: str | Path) -> str:
    """Read a frame and return its base64 (no data: prefix) payload."""
    data = Path(path).read_bytes()
    return base64.b64encode(data).decode("ascii")


def _chunks(seq: list, n: int) -> list[list]:
    return [seq[i : i + n] for i in range(0, len(seq), n)]


async def _one_request(
    session: aiohttp.ClientSession,
    api_key: str,
    base_url: str,
    model: str,
    frames: list[Path],
    prompt: str,
    temperature: float,
) -> str:
    content: list[dict] = []
    for f in frames:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{encode_frame(f)}"},
            }
        )
    content.append({"type": "text", "text": prompt})
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [{"role": "user", "content": content}],
    }
    async with session.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=aiohttp.ClientTimeout(total=900),
    ) as resp:
        text = await resp.text()
        if resp.status != 200:
            raise GLMError(f"GLM HTTP {resp.status}: {text[:300]}")
        data = json.loads(text)
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise GLMError(f"unexpected GLM response: {e}: {str(data)[:300]}") from e


async def describe_video(
    frames: list[Path],
    api_key: str,
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    prompt: str = DESCRIPTOR_PROMPT,
    temperature: float = 0.3,
    max_frames_per_request: int = MAX_FRAMES_PER_REQUEST,
) -> list[tuple[float, str]]:
    """Describe frames; returns merged (seconds, text) pairs, sorted."""
    if not api_key:
        raise GLMError("GLM API key not configured")
    check_frame_limits(frames)
    batches = _chunks(frames, max(1, max_frames_per_request))
    if len(batches) == 1:
        async with aiohttp.ClientSession() as session:
            text = await _one_request(
                session, api_key, base_url, model, batches[0], prompt, temperature
            )
        return parse_events(text)

    # Batched: requests run concurrently, results merged by timestamp
    async with aiohttp.ClientSession() as session:
        texts = await asyncio.gather(
            *[
                _one_request(session, api_key, base_url, model, b, prompt, temperature)
                for b in batches
            ]
        )
    merged: list[tuple[float, str]] = []
    for t in texts:
        merged.extend(parse_events(t))
    merged.sort(key=lambda x: x[0])
    return merged
