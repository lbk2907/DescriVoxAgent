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
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

import aiohttp

logger = logging.getLogger(__name__)


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
