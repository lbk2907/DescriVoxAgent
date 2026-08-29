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
from typing import Any

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
        self, frames: list[str], prompt: str, model: str = ""
    ) -> list[str]:
        """Describe multiple frames in batch. Returns list of descriptions."""
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

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

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
        self, frames: list[str], prompt: str, model: str = ""
    ) -> list[str]:
        results = []
        for frame in frames:
            try:
                desc = await self.describe_image(frame, prompt, model)
            except Exception as e:
                logger.warning("Gemini frame error: %s", e)
                desc = f"(error: {e})"
            results.append(desc)
        return results


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
        self, frames: list[str], prompt: str, model: str = ""
    ) -> list[str]:
        results = []
        for frame in frames:
            try:
                desc = await self.describe_image(frame, prompt, model)
            except Exception as e:
                logger.warning("OpenAI frame error: %s", e)
                desc = f"(error: {e})"
            results.append(desc)
        return results


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
        self, frames: list[str], prompt: str, model: str = ""
    ) -> list[str]:
        results = []
        for frame in frames:
            try:
                desc = await self.describe_image(frame, prompt, model)
            except Exception as e:
                logger.warning("Opus frame error: %s", e)
                desc = f"(error: {e})"
            results.append(desc)
        return results


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
    }

    def __init__(self):
        self._providers: dict[str, AIProvider] = {}
        self._default_provider: str = ""

    def set_provider(self, name: str, api_key: str = "", base_url: str = "", model: str = "") -> None:
        """Configure a provider with credentials."""
        if name not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {name}. Available: {list(self.PROVIDERS)}")
        cls = self.PROVIDERS[name]
        if name == "openai" and base_url:
            self._providers[name] = cls(api_key=api_key, base_url=base_url)
        else:
            self._providers[name] = cls(api_key=api_key, base_url=base_url or model and base_url or "")
        self._default_provider = name
        logger.info("AI provider set: %s", name)

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

    async def describe_frame(
        self,
        image_path: str,
        prompt: str,
        provider: str = "",
        model: str = "",
    ) -> str:
        """Describe a single image/frame. Auto-fallback on failure."""
        provider_name = provider or self._default_provider
        if not provider_name:
            raise ValueError("No AI provider configured. Call set_provider() first.")
        prov = self._providers[provider_name]
        return await prov.describe_image(image_path, prompt, model)

    async def describe_frames(
        self,
        frames: list[str],
        prompt: str,
        provider: str = "",
        model: str = "",
    ) -> list[str]:
        """Describe multiple frames. Returns list of descriptions."""
        provider_name = provider or self._default_provider
        if not provider_name:
            raise ValueError("No AI provider configured.")
        prov = self._providers[provider_name]
        return await prov.describe_frames_batch(frames, prompt, model)

    async def ask_about_scene(
        self,
        image_path: str,
        question: str,
        provider: str = "",
        model: str = "",
    ) -> str:
        """Ask a question about a specific frame/scene."""
        provider_name = provider or self._default_provider
        prov = self._providers[provider_name]
        return await prov.ask_about_scene(image_path, question, model)
