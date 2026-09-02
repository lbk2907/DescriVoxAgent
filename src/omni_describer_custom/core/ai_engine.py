"""
Omni Describer Custom — Multi-provider AI Engine.

Supports: Gemini, OpenAI, Opus Proxy (Anthropic format).
Auto-fallback chain on failure.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import re
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

import aiohttp

logger = logging.getLogger(__name__)


# Full-video mode: the prompt suffix sent with the whole video so the
# provider (Gemini or MiniMax) returns a chronological, machine-parsable
# [MM:SS] description list.
FULL_VIDEO_TS_PROMPT_SUFFIX = (
    "\n\nYou are watching the full video, including its audio. Produce your "
    "description as a chronological list covering the WHOLE video. Each "
    "item MUST start with a timestamp in [MM:SS] or [HH:MM:SS] format, "
    "followed by the description of what is happening at that moment. "
    "Example format:\n"
    "[00:00] A man in a red jacket walks into a bright kitchen.\n"
    "[00:15] He pours coffee while talking on the phone.\n"
    "Describe important visuals AND sounds/speech for a blind viewer. "
    "Do not output any other text."
)

# Parses one timestamped line, e.g.:
#   "[00:05] text" / "- 12:34 - text" / "01:02:03.500 text" / "(0:59) text"
# Deterministic: the timestamp must be followed by a delimiter or
# whitespace before the description, so "12:34" alone never matches.
_TS_LINE_RE = re.compile(
    r"^\s*[-*\u2022]?\s*[\[\(]?\s*"
    r"(?:(?P<h>\d{1,2}):)?(?P<m>\d{1,2}):(?P<s>\d{1,2})(?:[.,](?P<f>\d{1,3}))?"
    r"\s*[\]\)]?"
    r"\s*[-\u2013:\u2022]?"  # optional separator like "-" or ":"
    r"(?P<text>\s\S.*)?$"
)


def parse_gemini_timestamp_lines(text: str) -> list[tuple[float, str]]:
    """Parse Gemini's timestamped output lines into (seconds, text) pairs.

    Tolerates bullet markers, brackets, and optional hours/milliseconds.
    Lines without a leading timestamp are ignored.
    """
    out: list[tuple[float, str]] = []
    for raw in (text or "").splitlines():
        m = _TS_LINE_RE.match(raw)
        if not m:
            continue
        secs = (int(m.group("h") or 0) * 3600
                + int(m.group("m")) * 60 + int(m.group("s")))
        if m.group("f"):
            secs += float("0." + m.group("f"))
        desc = (m.group("text") or "").strip()
        if desc:
            out.append((float(secs), desc))
    return out


_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


def _strip_think(text: str) -> str:
    """Remove MiniMax reasoning blocks (<think>...</think>) from replies.

    MiniMax models (M3) include a reasoning block before the final answer.
    The timestamp parser must only see the final answer text.
    """
    if not text:
        return text
    if "<think>" in text and "</think>" not in text:
        # Truncated mid-thinking: keep only anything before the block.
        return text.split("<think>", 1)[0].strip()
    return _THINK_RE.sub("", text).strip()


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    name: str = "base"
    models: list[str] = []

    @abstractmethod
    async def describe_image(
        self, image_path: str, prompt: str, model: str = ""
    ) -> str:
        """Describe an image/frame. Returns description text."""
        ...

    @abstractmethod
    async def describe_frames_batch(
        self, frames: list[str], prompt: str, model: str = "",
        on_progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[str]:
        """Describe multiple frames in batch. Returns list of descriptions.

        on_progress(done, total) fires after each frame so the UI can show
        real analysis progress instead of a silent multi-minute wait.
        is_cancelled is polled between frames; on cancel the remaining
        frames return "(cancelled)" and the batch ends early.
        """
        ...

    async def ask_about_scene(
        self, image_path: str, question: str, model: str = ""
    ) -> str:
        """Ask a specific question about a scene (default: reuse describe_image)."""
        return await self.describe_image(image_path, question, model)

    def _load_image_b64(self, image_path: str) -> tuple[str, str]:
        """Load image and return (base64_string, mime_type)."""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
        data = base64.b64encode(path.read_bytes()).decode()
        return data, mime


class GeminiProvider(AIProvider):
    name = "gemini"
    models = [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
    ]

    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = api_key
        self.base_url = base_url or "https://generativelanguage.googleapis.com/v1beta"

    async def describe_image(
        self, image_path: str, prompt: str, model: str = ""
    ) -> str:
        if not self.api_key:
            raise ValueError("Gemini API key not configured")
        model = model or self.models[0]
        img_b64, mime = self._load_image_b64(image_path)

        url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": mime,
                                "data": img_b64,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"maxOutputTokens": 1024},
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                data = await resp.json()
                if "error" in data:
                    raise RuntimeError(f"Gemini error: {data['error']}")
                candidates = data.get("candidates", [])
                if not candidates:
                    return "(no response from Gemini)"
                text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return text or "(empty response)"

    async def describe_frames_batch(
        self, frames: list[str], prompt: str, model: str = "",
        on_progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[str]:
        results = []
        for i, frame in enumerate(frames):
            if is_cancelled is not None and is_cancelled():
                results.extend(["(cancelled)"] * (len(frames) - len(results)))
                return results
            try:
                desc = await self.describe_image(frame, prompt, model)
            except Exception as e:
                logger.warning("Gemini frame error: %s", e)
                desc = f"(error: {e})"
            results.append(desc)
            if on_progress:
                try:
                    on_progress(i + 1, len(frames))
                except Exception:
                    logger.debug("on_progress raised", exc_info=True)
        return results

    # ── Full-video mode (native video understanding) ─────────────

    def _video_mime(self, video_path: str) -> str:
        return mimetypes.guess_type(video_path)[0] or "video/mp4"

    async def _upload_video(
        self, video_path: str,
        on_progress: Callable[[float], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> str:
        """Resumable upload of the whole video to the Gemini Files API.

        Returns the file URI. Raises RuntimeError on HTTP failure or cancel.
        """
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")
        size = path.stat().st_size
        mime = self._video_mime(video_path)
        base = self.base_url.rstrip("/")
        url = f"{base}/files?uploadType=resumable&key={self.api_key}"
        headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(size),
            "X-Goog-Upload-Header-Content-Type": mime,
            "Content-Type": "application/json",
        }
        body = {"file": {"display_name": path.name[:80]}}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(
                        f"Gemini upload init HTTP {resp.status}: {text[:200]}")
                upload_url = resp.headers.get("X-Goog-Upload-URL", "")
                if not upload_url:
                    raise RuntimeError("Gemini upload: no upload URL returned")

            # Send the bytes in chunks; the last chunk carries "finalize".
            chunk = 8 * 1024 * 1024  # 8 MiB
            uploaded = 0
            with path.open("rb") as f:
                while True:
                    if is_cancelled is not None and is_cancelled():
                        raise RuntimeError("upload cancelled")
                    data = f.read(chunk)
                    if not data:
                        break
                    is_last = uploaded + len(data) >= size
                    up_headers = {
                        "X-Goog-Upload-Command":
                            "upload, finalize" if is_last else "upload",
                        "X-Goog-Upload-Offset": str(uploaded),
                        "Content-Length": str(len(data)),
                    }
                    async with session.post(upload_url, data=data,
                                            headers=up_headers,
                                            timeout=aiohttp.ClientTimeout(total=600)) as resp:
                        if resp.status not in (200, 201):
                            text = await resp.text()
                            raise RuntimeError(
                                f"Gemini upload HTTP {resp.status}: {text[:200]}")
                        if is_last:
                            payload = await resp.json()
                            fobj = payload.get("file", {})
                            uri = fobj.get("uri") or fobj.get("name", "")
                            if not uri:
                                raise RuntimeError(
                                    "Gemini upload: no file URI in response")
                            if on_progress:
                                try:
                                    on_progress(100.0)
                                except Exception:
                                    logger.debug("upload progress raised", exc_info=True)
                            return uri
                    uploaded += len(data)
                    if on_progress:
                        try:
                            on_progress(uploaded * 100.0 / max(size, 1))
                        except Exception:
                            logger.debug("upload progress raised", exc_info=True)
        raise RuntimeError("Gemini upload: nothing uploaded")

    async def _wait_video_ready(
        self, uri: str, timeout: float = 300.0,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> None:
        """Poll the Files API until the video state is ACTIVE (Gemini
        finished processing it). Raises RuntimeError on FAILED or timeout."""
        import asyncio as _aio
        base = self.base_url.rstrip("/")
        name = uri.split("/v1beta/")[-1] if "/v1beta/" in uri else uri
        url = f"{base}/{name}?key={self.api_key}"
        loop = _aio.get_running_loop()
        deadline = loop.time() + timeout
        async with aiohttp.ClientSession() as session:
            while True:
                if is_cancelled is not None and is_cancelled():
                    raise RuntimeError(
                        "cancelled while waiting for Gemini to process the video")
                async with session.get(url,
                                       timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(
                            f"Gemini file status HTTP {resp.status}: {text[:200]}")
                    data = await resp.json()
                state = data.get("state", "")
                if state == "ACTIVE":
                    return
                if state == "FAILED":
                    raise RuntimeError(
                        "Gemini failed to process the video: "
                        f"{data.get('error', {}).get('message', 'unknown error')}")
                await _aio.sleep(5)
                if loop.time() > deadline:
                    raise RuntimeError(
                        "Timed out waiting for Gemini to process the video")

    async def _generate_with_video(
        self, uri: str, mime: str, prompt: str, model: str,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> str:
        """One generateContent call carrying the whole video."""
        base = self.base_url.rstrip("/")
        url = f"{base}/models/{model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [
                {"text": prompt},
                {"file_data": {"mime_type": mime, "file_uri": uri}},
            ]}],
            "generationConfig": {"maxOutputTokens": 8192},
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload,
                                    timeout=aiohttp.ClientTimeout(total=600)) as resp:
                data = await resp.json()
                if "error" in data:
                    raise RuntimeError(f"Gemini error: {data['error']}")
                candidates = data.get("candidates", [])
                if not candidates:
                    return ""
                return candidates[0].get("content", {}).get("parts", [{}])[0].get(
                    "text", "")

    async def describe_video_full(
        self, video_path: str, prompt: str, model: str = "",
        on_status: Callable[[str], None] | None = None,
        on_upload_progress: Callable[[float], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[tuple[float, str]]:
        """Watch the WHOLE video with Gemini's native video understanding.

        1. Resumable upload (progress reported)
        2. Wait until Gemini finishes processing it (ACTIVE)
        3. generateContent with the video and a timestamped-list prompt
        4. Parse the [MM:SS] lines into (seconds, description) pairs
        """
        if not self.api_key:
            raise ValueError("Gemini API key not configured")
        model = model or self.models[0]

        def status(s: str) -> None:
            if on_status:
                try:
                    on_status(s)
                except Exception:
                    logger.debug("on_status raised", exc_info=True)

        status("uploading")
        uri = await self._upload_video(
            video_path, on_progress=on_upload_progress, is_cancelled=is_cancelled)
        status("processing")
        await self._wait_video_ready(uri, is_cancelled=is_cancelled)
        status("describing")
        text = await self._generate_with_video(
            uri, self._video_mime(video_path),
            prompt + FULL_VIDEO_TS_PROMPT_SUFFIX, model,
            is_cancelled=is_cancelled,
        )
        return parse_gemini_timestamp_lines(text)

    async def ask_text(
        self, question: str, history: list[dict] | None = None, model: str = ""
    ) -> str:
        if not self.api_key:
            raise ValueError("Gemini API key not configured")
        model = model or self.models[0]
        contents: list[dict] = []
        for msg in (history or []):
            role = "user" if msg.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})
        contents.append({"role": "user", "parts": [{"text": question}]})

        url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
        payload = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 1024},
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                data = await resp.json()
                if "error" in data:
                    raise RuntimeError(f"Gemini error: {data['error']}")
                candidates = data.get("candidates", [])
                if not candidates:
                    return "(no response from Gemini)"
                text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return text or "(empty response)"



class OpenAIProvider(AIProvider):
    name = "openai"
    models = [
        "gpt-4o",
        "gpt-4.1",
        "gpt-4.1-mini",
        "o4-mini",
    ]

    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = api_key
        self.base_url = base_url or "https://api.openai.com/v1"

    async def describe_image(
        self, image_path: str, prompt: str, model: str = ""
    ) -> str:
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")
        model = model or self.models[0]
        img_b64, mime = self._load_image_b64(image_path)
        data_url = f"data:{mime};base64,{img_b64}"

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                data = await resp.json()
                if "error" in data:
                    raise RuntimeError(f"OpenAI error: {data['error']}")
                choices = data.get("choices", [])
                if not choices:
                    return "(no response from OpenAI)"
                return choices[0]["message"]["content"]

    async def describe_frames_batch(
        self, frames: list[str], prompt: str, model: str = "",
        on_progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[str]:
        results = []
        for i, frame in enumerate(frames):
            if is_cancelled is not None and is_cancelled():
                results.extend(["(cancelled)"] * (len(frames) - len(results)))
                return results
            try:
                desc = await self.describe_image(frame, prompt, model)
            except Exception as e:
                logger.warning("OpenAI frame error: %s", e)
                desc = f"(error: {e})"
            results.append(desc)
            if on_progress:
                try:
                    on_progress(i + 1, len(frames))
                except Exception:
                    logger.debug("on_progress raised", exc_info=True)
        return results
    async def ask_text(
        self, question: str, history: list[dict] | None = None, model: str = ""
    ) -> str:
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")
        model = model or self.models[0]
        messages: list[dict] = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in (history or [])
        ]
        messages.append({"role": "user", "content": question})
        url = f"{self.base_url}/chat/completions"
        payload = {"model": model, "max_tokens": 1024, "messages": messages}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                data = await resp.json()
                if "error" in data:
                    raise RuntimeError(f"OpenAI error: {data['error']}")
                choices = data.get("choices", [])
                if not choices:
                    return "(no response from OpenAI)"
                return choices[0]["message"]["content"]



class MiniMaxProvider(AIProvider):
    """MiniMax: OpenAI-compatible chat + Files API video upload.

    Frame mode sends images as data URLs like OpenAI. Full-video mode
    uploads the file with purpose=video_understanding, references it as
    mm_file://{file_id} in a video_url content block, and strips the
    <think> reasoning block MiniMax models put in replies.
    """

    name = "minimax"
    models = [
        "MiniMax-M3",
    ]

    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = api_key
        self.base_url = (base_url or "https://api.minimax.io").rstrip("/")

    async def describe_image(
        self, image_path: str, prompt: str, model: str = ""
    ) -> str:
        if not self.api_key:
            raise ValueError("MiniMax API key not configured")
        model = model or self.models[0]
        img_b64, mime = self._load_image_b64(image_path)
        payload = {
            "model": model,
            "max_completion_tokens": 1024,
            "messages": [
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                ]},
            ],
        }
        text = await self._chat(payload, timeout=60)
        return _strip_think(text)

    async def describe_frames_batch(
        self, frames: list[str], prompt: str, model: str = "",
        on_progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[str]:
        results = []
        for i, frame in enumerate(frames):
            if is_cancelled is not None and is_cancelled():
                results.extend(["(cancelled)"] * (len(frames) - len(results)))
                return results
            try:
                desc = await self.describe_image(frame, prompt, model)
            except Exception as e:
                logger.warning("MiniMax frame error: %s", e)
                desc = f"(error: {e})"
            results.append(desc)
            if on_progress:
                try:
                    on_progress(i + 1, len(frames))
                except Exception:
                    logger.debug("on_progress raised", exc_info=True)
        return results

    async def ask_text(
        self, question: str, history: list[dict] | None = None, model: str = ""
    ) -> str:
        if not self.api_key:
            raise ValueError("MiniMax API key not configured")
        model = model or self.models[0]
        messages: list[dict] = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in (history or [])
        ]
        messages.append({"role": "user", "content": question})
        text = await self._chat(
            {"model": model, "max_completion_tokens": 1024,
             "messages": messages}, timeout=120)
        return _strip_think(text)

    async def _chat(
        self, payload: dict, timeout: float,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> str:
        """POST /v1/chat/completions and return choices[0].message.content."""
        if is_cancelled is not None and is_cancelled():
            raise RuntimeError("cancelled")
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                data = await resp.json()
                if resp.status != 200:
                    raise RuntimeError(
                        f"MiniMax HTTP {resp.status}: {str(data)[:200]}")
                base = data.get("base_resp", {}) or {}
                if base.get("status_code", 0) != 0:
                    raise RuntimeError(
                        f"MiniMax error: {base.get('status_msg', data)}")
                choices = data.get("choices", [])
                if not choices:
                    return "(no response from MiniMax)"
                return choices[0]["message"]["content"]

    async def describe_video_full(
        self, video_path: str, prompt: str, model: str = "",
        on_status: Callable[[str], None] | None = None,
        on_upload_progress: Callable[[float], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[tuple[float, str]]:
        """Watch the WHOLE video via the MiniMax Files API.

        1. multipart upload (purpose=video_understanding) -> file_id
        2. chat request referencing mm_file://{file_id}
        3. strip <think> and parse the same [MM:SS] lines as Gemini
        """
        def status(s: str) -> None:
            if on_status:
                try:
                    on_status(s)
                except Exception:
                    logger.debug("on_status raised", exc_info=True)

        if not self.api_key:
            raise ValueError("MiniMax API key not configured")
        model = model or self.models[0]

        status("uploading")
        file_id = await self._upload_video(
            video_path, on_upload_progress=on_upload_progress,
            is_cancelled=is_cancelled)
        status("describing")
        payload = {
            "model": model,
            "max_completion_tokens": 4096,
            "messages": [
                {"role": "user", "content": [
                    {"type": "video_url",
                     "video_url": {"url": f"mm_file://{file_id}"}},
                    {"type": "text",
                     "text": prompt + FULL_VIDEO_TS_PROMPT_SUFFIX},
                ]},
            ],
        }
        text = await self._chat(payload, timeout=600,
                                is_cancelled=is_cancelled)
        return parse_gemini_timestamp_lines(_strip_think(text))

    async def _upload_video(
        self, video_path: str,
        on_upload_progress: Callable[[float], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> str:
        """Multipart upload to /v1/files/upload; returns the file_id.

        The body streams from disk, but Content-Length is set
        explicitly: aiohttp cannot infer the length of a generator body
        and silently falls back to chunked transfer-encoding, which
        some upload endpoints mishandle (the request appears to have
        an empty body).
        """
        path = Path(video_path)
        total = path.stat().st_size

        def progress_cb(current: int) -> None:
            if on_upload_progress and total:
                try:
                    on_upload_progress(round(current / total * 100.0, 1))
                except Exception:
                    logger.debug("on_upload_progress raised", exc_info=True)

        boundary = "----OmniDescriberMiniMax" + uuid.uuid4().hex
        url = f"{self.base_url}/v1/files/upload"

        head1 = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="purpose"\r\n'
            "\r\n"
        ).encode()
        value1 = b"video_understanding\r\n"
        head2 = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; '
            f'filename="{path.name}"\r\n'
            "Content-Type: video/mp4\r\n\r\n"
        ).encode()
        tail = f"\r\n--{boundary}--\r\n".encode()
        content_length = (
            len(head1) + len(value1) + len(head2) + total + len(tail))

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(content_length),
        }

        with open(video_path, "rb") as fh:
            async def gen():
                yield head1
                yield value1
                yield head2
                sent = 0
                while True:
                    chunk = fh.read(1 << 16)
                    if not chunk:
                        break
                    sent += len(chunk)
                    progress_cb(sent)
                    yield chunk
                    if is_cancelled is not None and is_cancelled():
                        raise RuntimeError("upload cancelled")
                yield f"\r\n--{boundary}--\r\n".encode()

            async with aiohttp.ClientSession() as session:
                async with session.post(
                        url, data=gen(), headers=headers,
                        timeout=aiohttp.ClientTimeout(total=600)) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(
                            f"MiniMax upload HTTP {resp.status}: {text[:200]}")
                    data = await resp.json()

        base = data.get("base_resp", {}) or {}
        if base.get("status_code", 0) != 0:
            raise RuntimeError(
                f"MiniMax upload error: {base.get('status_msg', data)}")
        file_id = (data.get("file") or {}).get("file_id", "")
        if not file_id:
            raise RuntimeError(f"MiniMax upload: no file_id in response: {data}")
        progress_cb(total)
        return file_id


class OpusProvider(AIProvider):
    """Opus Proxy — Anthropic Messages API format ONLY for vision."""

    name = "opus"
    models = [
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
    ]

    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = api_key
        self.base_url = base_url or "https://opus.abhibots.com/v1"

    async def describe_image(
        self, image_path: str, prompt: str, model: str = ""
    ) -> str:
        if not self.api_key:
            raise ValueError("Opus Proxy API key not configured")
        model = model or self.models[0]
        img_b64, mime = self._load_image_b64(image_path)

        url = f"{self.base_url}/messages"
        payload = {
            "model": model,
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime,
                                "data": img_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Opus Proxy HTTP {resp.status}: {body[:200]}")
                data = await resp.json()
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        return block["text"]
                return "(no text in Opus response)"

    async def describe_frames_batch(
        self, frames: list[str], prompt: str, model: str = "",
        on_progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[str]:
        results = []
        for i, frame in enumerate(frames):
            if is_cancelled is not None and is_cancelled():
                results.extend(["(cancelled)"] * (len(frames) - len(results)))
                return results
            try:
                desc = await self.describe_image(frame, prompt, model)
            except Exception as e:
                logger.warning("Opus frame error: %s", e)
                desc = f"(error: {e})"
            results.append(desc)
            if on_progress:
                try:
                    on_progress(i + 1, len(frames))
                except Exception:
                    logger.debug("on_progress raised", exc_info=True)
        return results
    async def ask_text(
        self, question: str, history: list[dict] | None = None, model: str = ""
    ) -> str:
        if not self.api_key:
            raise ValueError("Opus Proxy API key not configured")
        model = model or self.models[0]
        messages: list[dict] = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in (history or [])
        ]
        messages.append({"role": "user", "content": question})
        url = f"{self.base_url}/messages"
        payload = {"model": model, "max_tokens": 1024, "messages": messages}
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Opus Proxy HTTP {resp.status}: {body[:200]}")
                data = await resp.json()
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        return block["text"]
                return "(no text in Opus response)"



# Custom provider API format constants
FORMAT_OPENAI = "openai"
FORMAT_ANTHROPIC = "anthropic"
FORMAT_AUTO = "auto"


class CustomProvider(AIProvider):
    """Custom AI provider — user supplies base_url + model name.
    Auto-detects API format (OpenAI-compatible vs Anthropic) from base_url
    or explicit format selector."""

    name = "custom"
    models = []  # Dynamic — user provides their own

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
        api_format: str = FORMAT_AUTO,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.model = model or "custom-model"
        self.api_format = api_format

    def _detect_format(self) -> str:
        """Auto-detect API format from base_url."""
        if self.api_format != FORMAT_AUTO:
            return self.api_format
        url = self.base_url.lower()
        if "anthropic" in url or "claude" in url:
            return FORMAT_ANTHROPIC
        return FORMAT_OPENAI

    async def describe_image(
        self, image_path: str, prompt: str, model: str = ""
    ) -> str:
        if not self.api_key:
            raise ValueError("Custom provider: no API key configured")
        if not self.base_url:
            raise ValueError("Custom provider: no base URL configured")

        model = model or self.model
        fmt = self._detect_format()
        img_b64, mime = self._load_image_b64(image_path)

        if fmt == FORMAT_ANTHROPIC:
            return await self._call_anthropic(model, prompt, img_b64, mime)
        return await self._call_openai(model, prompt, img_b64, mime)

    async def _call_openai(self, model: str, prompt: str, img_b64: str, mime: str) -> str:
        """OpenAI-compatible chat completions (vision)."""
        data_url = f"data:{mime};base64,{img_b64}"
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "max_tokens": 1024,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Custom API HTTP {resp.status}: {body[:200]}")
                data = await resp.json()
                if "error" in data:
                    raise RuntimeError(f"Custom API error: {data['error']}")
                choices = data.get("choices", [])
                if not choices:
                    return "(no response from custom API)"
                return choices[0]["message"]["content"]

    async def _call_anthropic(self, model: str, prompt: str, img_b64: str, mime: str) -> str:
        """Anthropic Messages API format."""
        url = f"{self.base_url}/messages"
        payload = {
            "model": model,
            "max_tokens": 1024,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": mime, "data": img_b64,
                    }},
                    {"type": "text", "text": prompt},
                ],
            }],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Custom API HTTP {resp.status}: {body[:200]}")
                data = await resp.json()
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        return block["text"]
                return "(no text in custom API response)"

    async def describe_frames_batch(
        self, frames: list[str], prompt: str, model: str = "",
        on_progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[str]:
        results = []
        for i, frame in enumerate(frames):
            if is_cancelled is not None and is_cancelled():
                results.extend(["(cancelled)"] * (len(frames) - len(results)))
                return results
            try:
                desc = await self.describe_image(frame, prompt, model)
            except Exception as e:
                logger.warning("Custom provider frame error: %s", e)
                desc = f"(error: {e})"
            results.append(desc)
            if on_progress:
                try:
                    on_progress(i + 1, len(frames))
                except Exception:
                    logger.debug("on_progress raised", exc_info=True)
        return results

    async def ask_about_scene(
        self, image_path: str, question: str, model: str = ""
    ) -> str:
        return await self.describe_image(image_path, question, model)

    async def ask_text(
        self, question: str, history: list[dict] | None = None, model: str = ""
    ) -> str:
        """Free-form text question (no image) via OpenAI- or Anthropic-style API."""
        if not self.api_key:
            raise ValueError("Custom provider: no API key configured")
        if not self.base_url:
            raise ValueError("Custom provider: no base URL configured")
        model = model or self.model
        fmt = self._detect_format()
        messages = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in (history or [])
        ]
        messages.append({"role": "user", "content": question})
        async with aiohttp.ClientSession() as session:
            if fmt == FORMAT_ANTHROPIC:
                url = f"{self.base_url}/messages"
                payload = {"model": model, "max_tokens": 1024, "messages": messages}
                headers = {
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                }
                async with session.post(
                    url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise RuntimeError(f"Custom API HTTP {resp.status}: {body[:200]}")
                    data = await resp.json()
                    for block in data.get("content", []):
                        if block.get("type") == "text":
                            return block["text"]
                    return "(no text in custom API response)"
            url = f"{self.base_url}/chat/completions"
            payload = {"model": model, "max_tokens": 1024, "messages": messages}
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            async with session.post(
                url, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Custom API HTTP {resp.status}: {body[:200]}")
                data = await resp.json()
                if "error" in data:
                    raise RuntimeError(f"Custom API error: {data['error']}")
                choices = data.get("choices", [])
                if not choices:
                    return "(no response from custom API)"
                return choices[0]["message"]["content"]


class AIEngine:
    """
    High-level AI engine with provider management and auto-fallback.
    Usage:
        engine = AIEngine()
        engine.set_provider("opus", api_key="...")
        desc = await engine.describe_frame("frame.jpg", "Describe this in Malay.")
    """

    PROVIDERS = {
        "gemini": GeminiProvider,
        "minimax": MiniMaxProvider,
        "openai": OpenAIProvider,
        "opus": OpusProvider,
        "custom": CustomProvider,
    }

    def __init__(self):
        self._providers: dict[str, AIProvider] = {}
        self._default_provider: str = ""

    def set_provider(self, name: str, api_key: str = "", base_url: str = "", model: str = "", api_format: str = "") -> None:
        """Configure a provider with credentials."""
        if name not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {name}. Available: {list(self.PROVIDERS)}")
        cls = self.PROVIDERS[name]
        if name == "custom":
            self._providers[name] = cls(api_key=api_key, base_url=base_url, model=model, api_format=api_format or FORMAT_AUTO)
        else:
            self._providers[name] = cls(api_key=api_key, base_url=base_url)
        self._default_provider = name
        logger.info("AI provider set: %s (model=%s)", name, model or "default")

    def set_default(self, name: str) -> None:
        """Set which provider to use by default."""
        if name not in self._providers:
            raise ValueError(f"Provider not configured: {name}")
        self._default_provider = name

    def get_available_providers(self) -> list[str]:
        """Return list of configured provider names."""
        return list(self._providers.keys())

    def get_provider(self, name: str) -> AIProvider:
        """Get a specific provider instance."""
        if name not in self._providers:
            raise ValueError(f"Provider not configured: {name}")
        return self._providers[name]

    def _provider_or_raise(self, provider_name: str) -> AIProvider:
        """Resolve the active provider with a clear error, never a KeyError."""
        provider_name = provider_name or self._default_provider
        if not provider_name:
            raise ValueError("No AI provider configured. Call set_provider() first.")
        if provider_name not in self._providers:
            raise ValueError(
                f"Provider not configured: {provider_name}. "
                f"Configured: {list(self._providers) or 'none'}"
            )
        return self._providers[provider_name]

    async def ask(
        self,
        question: str,
        history: list[dict] | None = None,
        provider: str = "",
        model: str = "",
    ) -> str:
        """Free-form text question to the current provider (no image)."""
        prov = self._provider_or_raise(provider or self._default_provider)
        ask_fn = getattr(prov, "ask_text", None)
        if ask_fn is None:
            raise ValueError(f"Provider '{prov.name}' does not support text questions.")
        return await ask_fn(question, history, model)

    async def describe_frame(
        self,
        image_path: str,
        prompt: str,
        provider: str = "",
        model: str = "",
    ) -> str:
        """Describe a single image/frame. Auto-fallback on failure."""
        prov = self._provider_or_raise(provider or self._default_provider)
        return await prov.describe_image(image_path, prompt, model)

    async def describe_frames(
        self,
        frames: list[str],
        prompt: str,
        provider: str = "",
        model: str = "",
        on_progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[str]:
        """Describe multiple frames. Returns list of descriptions."""
        prov = self._provider_or_raise(provider or self._default_provider)
        return await prov.describe_frames_batch(
            frames, prompt, model, on_progress=on_progress, is_cancelled=is_cancelled)

    async def describe_video_full(
        self,
        video_path: str,
        prompt: str,
        provider: str = "",
        model: str = "",
        on_status: Callable[[str], None] | None = None,
        on_upload_progress: Callable[[float], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[tuple[float, str]]:
        """Watch the WHOLE video (Gemini native video understanding).

        Returns (seconds, description) pairs parsed from Gemini's
        timestamped output. Raises ValueError when the configured
        provider does not support full-video mode.
        """
        prov = self._provider_or_raise(provider or self._default_provider)
        fn = getattr(prov, "describe_video_full", None)
        if fn is None:
            raise ValueError(
                f"Provider '{prov.name}' does not support full-video mode. "
                "Use Gemini, or switch back to frame mode.")
        return await fn(
            video_path, prompt, model,
            on_status=on_status,
            on_upload_progress=on_upload_progress,
            is_cancelled=is_cancelled,
        )

    async def ask_about_scene(
        self,
        image_path: str,
        question: str,
        provider: str = "",
        model: str = "",
    ) -> str:
        """Ask a question about a specific frame/scene."""
        prov = self._provider_or_raise(provider or self._default_provider)
        return await prov.ask_about_scene(image_path, question, model)
