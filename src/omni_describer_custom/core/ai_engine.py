"""
Omni Describer Custom — Multi-provider AI Engine.

Supports: Gemini, MiniMax, OpenAI, GLM (OpenRouter), Custom.
Auto-fallback chain on failure.
"""

from __future__ import annotations

import asyncio
import base64
import bisect
import hashlib
import json
import inspect
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
# Providers whose video understanding includes the AUDIO track.
#
# Probed directly on 20 Sep 2026: asked to transcribe the first spoken
# sentence or reply "NO AUDIO ACCESS", GLM (z-ai/glm-5.3-flash via
# OpenRouter) replied NO AUDIO ACCESS. It sees frames only. That is why
# the pre-v1.6.0 instruction "describe important visuals AND
# sounds/speech" never produced any speech: it was asking for something
# the provider cannot do.
#
# This matters for the `foreign` preset, whose entire job is conveying
# speech the listener cannot understand. With a frame-only provider it
# silently degrades into an ordinary visual description — the worst
# outcome for a blind user, who has no way to see that it failed.
AUDIO_CAPABLE_PROVIDERS = frozenset({"gemini"})


async def _run_cancellable(coro, is_cancelled, poll: float = 0.5):
    """Await `coro`, abandoning it within `poll` seconds of a Cancel.

    Raises RuntimeError("cancelled") — the same signal the pipeline
    already uses between requests.
    """
    if is_cancelled is None:
        return await coro
    task = asyncio.ensure_future(coro)
    while True:
        done, _ = await asyncio.wait({task}, timeout=poll)
        if done:
            return task.result()
        if is_cancelled():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            raise RuntimeError("cancelled")


def provider_hears_audio(provider: str) -> bool:
    """True when this provider's video mode ingests the audio track."""
    return (provider or "").strip().lower() in AUDIO_CAPABLE_PROVIDERS


# Measured against OpenRouter + z-ai/glm-5.3-flash (probe, 2026-09): a
# 60 s video costs ~9200 prompt tokens, so roughly 153 tokens per second
# of video. Completion is small by comparison — a 12-word ceiling per
# cue — but counted so the estimate errs high rather than low.
TOKENS_PER_VIDEO_SECOND = 9200 / 60.0
# OpenRouter rejects video requests below this balance regardless of what
# the job actually costs (observed: HTTP 402 on a 19-second clip).
VIDEO_MIN_BALANCE_USD = 1.00
COMPLETION_TOKENS_PER_PART = 600


async def get_credit_balance(api_key: str) -> dict:
    """Remaining OpenRouter credit, or {} when it cannot be read.

    Returned as a dict so a caller can tell "no balance" (0.0) apart
    from "could not check" ({}) — the first is worth blocking on, the
    second is not.
    """
    import aiohttp

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                "https://openrouter.ai/api/v1/credits",
                headers={"Authorization": f"Bearer {api_key}"},
            ) as resp:
                if resp.status != 200:
                    return {}
                data = (await resp.json()).get("data", {})
        total = float(data.get("total_credits", 0.0))
        used = float(data.get("total_usage", 0.0))
        return {"total": total, "used": used, "remaining": total - used}
    except Exception as e:
        logger.debug("Credit check failed: %s", e)
        return {}


async def get_model_price(model: str) -> dict:
    """Per-token prices for a model from the public OpenRouter catalog."""
    import aiohttp

    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                    "https://openrouter.ai/api/v1/models") as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()
        for entry in data.get("data", []):
            if entry.get("id") == model:
                pricing = entry.get("pricing", {})
                return {"prompt": float(pricing.get("prompt", 0.0) or 0.0),
                        "completion": float(pricing.get("completion", 0.0) or 0.0)}
    except Exception as e:
        logger.debug("Price lookup failed: %s", e)
    return {}


async def estimate_video_cost(duration_seconds: float, model: str,
                              chunk_seconds: int = 600,
                              api_key: str = "") -> dict:
    """What this video will cost before a penny is spent.

    v1.6.1: added after a run died mid-way with HTTP 402 ("requires at
    least $1.00 in balance for video"). Knowing beforehand is the
    difference between choosing to spend and finding out afterwards.
    """
    duration = max(0.0, float(duration_seconds or 0.0))
    parts = max(1, int(-(-duration // max(1, chunk_seconds))))
    prompt_tokens = duration * TOKENS_PER_VIDEO_SECOND
    completion_tokens = parts * COMPLETION_TOKENS_PER_PART

    price = await get_model_price(model) if model else {}
    usd = (prompt_tokens * price.get("prompt", 0.0)
           + completion_tokens * price.get("completion", 0.0)) if price else 0.0

    out = {
        "duration": duration,
        "parts": parts,
        "prompt_tokens": int(prompt_tokens),
        "usd": usd,
        "priced": bool(price),
    }
    if api_key:
        # Belt and braces: get_credit_balance() swallows its own errors,
        # but an estimate must never be the reason a run does not start.
        try:
            balance = await get_credit_balance(api_key)
        except Exception as e:
            logger.debug("Balance check raised: %s", e)
            balance = {}
        if balance:
            out["remaining"] = balance["remaining"]
            out["affordable"] = balance["remaining"] >= usd
            # The real blocker is not the price. A 2-hour film costs
            # about $0.10, but OpenRouter refuses ANY video request
            # under a $1.00 balance — which is how a run died mid-way
            # with "HTTP 402: requires at least $1.00 in balance for
            # video". Cost is rarely the problem; this floor is.
            out["min_balance_ok"] = balance["remaining"] >= VIDEO_MIN_BALANCE_USD
    return out


def build_transcript_block(segments, start: float = 0.0,
                           end: float | None = None,
                           offset: float = 0.0, limit: int = 120,
                           words_per_second: float = 2.5) -> str:
    """Render the words spoken in a time range, for the prompt.

    v1.6.1: this is how a provider that cannot hear (GLM) still knows
    what was said. Two things follow from having it, and both are what
    the AD standards ask for: the model can avoid re-describing what the
    listener already hears, and the `foreign` preset has something to
    convey.

    `segments` are TranscriptSegment-like (start, end, text) in WHOLE
    video time; `offset` shifts them into part-local time so a chunked
    request sees its own slice starting at 00:00.
    """
    if not segments:
        return ""
    picked = []
    for seg in segments:
        s = float(getattr(seg, "start", 0.0))
        e = float(getattr(seg, "end", s))
        if e < start:
            continue
        if end is not None and s > end:
            continue
        text = str(getattr(seg, "text", "")).strip()
        if text:
            picked.append((max(0.0, s - offset), text))
    if not picked:
        return ""
    if len(picked) > limit:
        # Keep the ends: the opening sets the scene and the close
        # usually resolves it. Dropping the middle beats blowing the
        # context window on a long video.
        head, tail = picked[:limit // 2], picked[-(limit // 2):]
        picked = head + [(head[-1][0], "[...]")] + tail
    lines = "\n".join(f"[{int(t) // 60:02d}:{int(t) % 60:02d}] {txt}"
                      for t, txt in picked)
    return (
        "\n\nWHAT IS SAID IN THIS VIDEO, WITH THE TIMES IT IS SAID "
        "(already audible to the listener). Use it three ways: to "
        "understand what is happening; to avoid repeating information "
        "they already have; and to CHOOSE YOUR MOMENTS — put your "
        "descriptions in the gaps between these lines rather than over "
        "them. Do NOT narrate these lines back unless the prompt above "
        "asks you to convey speech:\n"
        f"{lines}\n"
        + _gap_budget_block(segments, start, end, offset, words_per_second)
    )


def _gap_budget_block(segments, start: float, end: float | None,
                      offset: float, words_per_second: float) -> str:
    """Name each silent gap and how many words actually fit in it.

    Asking for "12 words maximum" did not work, and asking harder is
    not a plan (AGENTS.md pitfall 14). This gives arithmetic instead of
    a plea. Measured on a real 50-second clip: it holds 77 words of
    silence, and the model wrote 97 and then 99 — about a quarter more
    than there was room for — because nothing ever told it the budget.

    The rate follows the user's own TTS speed, so a listener at 1.5x
    is offered more words than one at 1.0x rather than a figure that
    suits neither.
    """
    if end is None:
        return ""
    from .timeline_io import silent_gaps

    gaps = silent_gaps(segments, start=start, end=end, min_seconds=1.0)
    if not gaps:
        return (
            "\n\nTHERE IS NO SILENCE IN THIS PART. Someone is speaking "
            "throughout. Describe only what cannot be understood from "
            "the words alone, and keep it to a few words.\n")

    rows = []
    total = 0
    for a, b in gaps:
        words = int((b - a) * words_per_second)
        if words < 1:
            continue
        total += words
        rows.append(
            f"  {int((a - offset) // 60):02d}:{int((a - offset) % 60):02d}"
            f"-{int((b - offset) // 60):02d}:{int((b - offset) % 60):02d}"
            f"  about {words} words fit here")
    if not rows:
        return ""
    listing = "\n".join(rows)
    return (
        "\n\nHOW MUCH ROOM YOU ACTUALLY HAVE. These are the silent "
        "stretches, with the number of words that can be SPOKEN ALOUD "
        "in each before the next line of dialogue starts. This is "
        "measured, not a style preference: text longer than this is "
        "still being read out when the speech begins, and the listener "
        "loses both.\n"
        f"{listing}\n"
        f"Your whole answer must fit in about {total} words across all "
        "of these gaps. Start each description inside a gap and make it "
        "short enough to finish inside the SAME gap. If something will "
        "not fit, leave it out rather than overrun.\n")


FULL_VIDEO_TS_PROMPT_SUFFIX = (
    "\n\nYou are watching the full video, including its audio. Produce your "
    "description as a chronological list covering the WHOLE video. Each "
    "item MUST start with a timestamp in [MM:SS] or [HH:MM:SS] format, "
    "followed by the description of what is happening at that moment. "
    "Example format:\n"
    "[00:00] A man in a red jacket walks into a bright kitchen.\n"
    "[00:15] He pours coffee while talking on the phone.\n"
    # v1.6.0: this used to demand "important visuals AND sounds/speech".
    # A blind viewer HEARS the soundtrack: describing it spends the gap
    # on what they already have, which every AD standard warns against
    # (Netflix: skip description when dialogue already carries it). The
    # "foreign" preset opts speech back in, because conveying dialogue
    # the listener cannot understand is a different, recognised service.
    # The suffix must not have an opinion about WHAT to describe: it is
    # appended after the preset, so whatever it says wins. v1.6.0 first
    # replaced "describe visuals AND sounds/speech" with a visuals-only
    # line, which then silently overrode the `foreign` preset — a real
    # run produced no conveyed speech at all, the one thing that preset
    # exists for. Format here, content in the prompt.
    "Follow the description rules given in the prompt above. "
    "Narrative rules: describe only what happens AT each timestamp; "
    "never say 'the video starts with' or 'the video begins with' "
    "unless the timestamp is truly 00:00 of the whole video. Use ONE "
    "consistent name for the same person or object throughout.\n"
    "Write every description in the SAME LANGUAGE as the user prompt "
    "above; never mix languages. "
    "Do not output any other text."
)

# v1.5.3: anti-drift rules shared by every description mode. Without
# them each request reads as the START of the video ("The video starts
# with...") even at minute 37, and recurring people get renamed.
CONTINUITY_RULES = (
    "Narrative rules: describe only what happens AT each timestamp. "
    "Never say 'the video starts with', 'the video begins with' or "
    "'the video opens with' unless the timestamp is truly the start "
    "of the whole video. Use ONE consistent name for the same person, "
    "object or place throughout; keep characters established earlier "
    "instead of re-describing them from scratch every time."
)



# v1.5.2: explicit output-language directives. Without one, models pick
# the language from the video CONTENT (speech/on-screen text), which
# made descriptions randomly switch between Malay and English.
_LANGUAGE_DIRECTIVES = {
    "ms": ("\n\nIMPORTANT: Write EVERY description in Bahasa Malaysia "
           "(Malay). Never mix English words into the descriptions."),
    "en": ("\n\nIMPORTANT: Write EVERY description in English. "
           "Do not use any other language."),
}


def language_directive(lang: str) -> str:
    """Return the output-language directive for a language code.

    v1.6.2: any language with a locale file works, not just the two
    written out above. This is what makes a new language cheap — the
    seven audio-description presets stay in English and the model is
    simply told which language to write in, so adding Indonesian does
    NOT mean translating seven long prompts.

    An unknown code returns "" (model decides), as before.
    """
    code = (lang or "").strip().lower()
    if code in _LANGUAGE_DIRECTIVES:
        return _LANGUAGE_DIRECTIVES[code]
    try:
        from ..i18n.strings import I18n

        name = I18n.ai_language_name(code)
    except Exception:       # i18n is not a hard dependency of the engine
        name = ""
    if not name:
        return ""
    return (f"\n\nIMPORTANT: Write EVERY description in {name}. "
            "Do not use any other language.")


def apply_output_language(prompt: str, lang: str) -> str:
    """Append the output-language directive to a user prompt (once)."""
    directive = language_directive(lang)
    if not directive or not prompt:
        return prompt
    if directive.strip() in prompt:
        return prompt  # already applied
    return prompt + directive

# Parses one timestamped line, e.g.:
#   "[00:05] text" / "- 12:34 - text" / "01:02:03.500 text" / "(0:59) text"
# Deterministic: the timestamp must be followed by a delimiter or
# whitespace before the description, so "12:34" alone never matches.
# v1.7.4: also tolerates what models actually emit despite being told
# not to \u2014 "1. [00:05] ...", "**[00:05]** ...", "[00:05]A dog" \u2014 which
# used to be dropped silently. Text glued to the stamp must not start
# with a digit, so "12:345" is never read as 12:34 + "5".
_TS_LINE_RE = re.compile(
    r"^\s*(?:\d{1,3}[.)]\s+)?[-*\u2022]?\s*(?:\*\*|__)?\s*[\[\(]?\s*"
    r"(?:(?P<h>\d{1,2}):)?(?P<m>\d{1,2}):(?P<s>\d{1,2})(?:[.,](?P<f>\d{1,3}))?"
    r"\s*[\]\)]?\s*(?:\*\*|__)?"
    r"\s*[-\u2013:\u2022]?"  # optional separator like "-" or ":"
    r"(?:\s+(?P<text>\S.*)|(?P<glued>[^\s\d:.,\])].*))?$"
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
        desc = (m.group("text") or m.group("glued") or "").strip()
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


# v1.7.4: placeholders a provider returns instead of a description.
# They are fine in the chat window, but a frame whose "description" is
# "(empty response)" was saved as a cue and read aloud to the listener.
_PLACEHOLDER_PREFIXES = ("(error:", "(no response", "(no text",
                         "(empty response")


def is_placeholder_text(text: str) -> bool:
    """True when text is not a real description and must not be spoken."""
    t = (text or "").strip()
    return (not t or t == "(cancelled)"
            or t.lower().startswith(_PLACEHOLDER_PREFIXES))


# v1.7.4: every provider retries a provider-side wobble, not just GLM.
# One HTTP 429 used to throw away a Gemini full-video job after the
# upload and processing had already been paid for.
_TRANSIENT_STATUSES = (429, 500, 502, 503, 504)
HTTP_RETRIES = 3
HTTP_RETRY_BACKOFF_SECONDS = 3.0


class _TransientHTTPError(Exception):
    """A status worth another attempt (rate limit, overload)."""


async def _sleep_cancellable(seconds: float,
                             is_cancelled: Callable[[], bool] | None) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + seconds
    while True:
        if is_cancelled is not None and is_cancelled():
            raise RuntimeError("cancelled")
        left = end - loop.time()
        if left <= 0:
            return
        await asyncio.sleep(min(0.5, left))


async def _http_json(
    method: str, url: str, *, label: str,
    headers: dict | None = None, payload: Any = None,
    timeout: float = 60.0,
    is_cancelled: Callable[[], bool] | None = None,
) -> dict:
    """One JSON request with retries on 429/5xx and network errors.

    The status is checked BEFORE the body is decoded: an HTML error
    page used to raise aiohttp's ContentTypeError, whose text carries
    the full request URL — and with it any key in the query string.
    Error messages here name the provider and status, never the URL.
    """
    last: Exception | None = None
    for attempt in range(1, HTTP_RETRIES + 1):
        if is_cancelled is not None and is_cancelled():
            raise RuntimeError("cancelled")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method, url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    body = await resp.text()
                    if resp.status in _TRANSIENT_STATUSES:
                        raise _TransientHTTPError(
                            f"HTTP {resp.status}: {body[:120]}")
                    if resp.status != 200:
                        raise RuntimeError(
                            f"{label} HTTP {resp.status}: {body[:200]}")
                    try:
                        data = json.loads(body)
                    except ValueError:
                        raise RuntimeError(
                            f"{label}: reply was not JSON: {body[:200]}"
                        ) from None
                    if not isinstance(data, dict):
                        raise RuntimeError(
                            f"{label}: unexpected reply: {body[:200]}")
                    return data
        except (_TransientHTTPError, aiohttp.ClientError,
                asyncio.TimeoutError, OSError) as e:
            last = e
            if attempt >= HTTP_RETRIES:
                break
            wait = HTTP_RETRY_BACKOFF_SECONDS * attempt
            logger.warning("%s: %s on attempt %d/%d; retrying in %.0fs",
                           label, str(e) or type(e).__name__,
                           attempt, HTTP_RETRIES, wait)
            await _sleep_cancellable(wait, is_cancelled)
    raise RuntimeError(
        f"{label} request failed after {HTTP_RETRIES} attempts: "
        f"{str(last) or type(last).__name__}")


def _gemini_text(data: dict) -> str:
    """Join every visible text part of a Gemini reply.

    Taking parts[0] only dropped the rest of a reply that arrived in
    several parts; thought parts are the model's reasoning, not the
    answer. Returns "" (with the reason logged) when nothing came back,
    e.g. a safety block.
    """
    candidates = data.get("candidates") or []
    if not candidates:
        logger.warning("Gemini returned no candidates (blockReason=%s)",
                       (data.get("promptFeedback") or {}).get("blockReason"))
        return ""
    cand = candidates[0] or {}
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts
                   if isinstance(p, dict) and not p.get("thought"))
    if not text.strip():
        logger.warning("Gemini returned no text (finishReason=%s)",
                       cand.get("finishReason"))
    return text


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    name: str = "base"
    models: list[str] = []

    # Where to keep the compressed upload copy so a retry does not
    # re-encode the video (v1.6.7). Set by AIEngine to the project's
    # media folder; empty means "use a throwaway temp dir", which is
    # how every provider behaved before.
    upload_cache_dir: str = ""

    # How fast the descriptions will actually be spoken, so the model
    # can be told how many words fit in each silent gap (v1.6.8). The
    # default matches a synthesised voice at normal speed; the GUI
    # overrides it from the user's own TTS speed setting.
    words_per_second: float = 2.5

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
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
        # Google limits 2.5 to accounts that used it before; kept
        # last so an existing saved choice stays selectable.
        "gemini-2.5-flash",
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

        url = f"{self.base_url}/models/{model}:generateContent"
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

        data = await _http_json("POST", url, label="Gemini",
                                headers=self._auth_headers(),
                                payload=payload, timeout=60)
        if "error" in data:
            raise RuntimeError(f"Gemini error: {data['error']}")
        return _gemini_text(data) or "(empty response)"

    def _auth_headers(self) -> dict:
        # v1.7.4: the key travels in a header, never in the URL, so it
        # cannot surface in an exception text, a log line or a cue.
        return {"x-goog-api-key": self.api_key}

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
        if "generativelanguage.googleapis.com" in base and "/upload" not in base:
            upload_base = base.replace(
                "generativelanguage.googleapis.com",
                "generativelanguage.googleapis.com/upload",
            )
        else:
            upload_base = base
        url = f"{upload_base}/files?uploadType=resumable"
        headers = {
            **self._auth_headers(),
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
                            # Decoded by hand: resp.json() on a wrong
                            # content type raises with the URL in it.
                            try:
                                payload = json.loads(await resp.text())
                            except ValueError:
                                payload = {}
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
        url = f"{base}/{name}"
        loop = _aio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            if is_cancelled is not None and is_cancelled():
                raise RuntimeError(
                    "cancelled while waiting for Gemini to process the video")
            data = await _http_json("GET", url, label="Gemini file status",
                                    headers=self._auth_headers(),
                                    timeout=60, is_cancelled=is_cancelled)
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
        url = f"{base}/models/{model}:generateContent"
        payload = {
            "contents": [{"parts": [
                {"text": prompt},
                {"file_data": {"mime_type": mime, "file_uri": uri}},
            ]}],
            "generationConfig": {"maxOutputTokens": 8192},
        }
        data = await _http_json("POST", url, label="Gemini",
                                headers=self._auth_headers(),
                                payload=payload, timeout=600,
                                is_cancelled=is_cancelled)
        if "error" in data:
            raise RuntimeError(f"Gemini error: {data['error']}")
        return _gemini_text(data)

    async def describe_video_full(
        self, video_path: str, prompt: str, model: str = "",
        on_status: Callable[[str], None] | None = None,
        on_upload_progress: Callable[[float], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        chunk_seconds: int = 600,
        on_part: Callable[[int, int], None] | None = None,
        # Accepted for interface parity with chunked providers; these
        # providers never split, so the callback stays unused here.
        on_split_progress: Callable[[float], None] | None = None,
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

        url = f"{self.base_url}/models/{model}:generateContent"
        payload = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 1024},
        }
        data = await _http_json("POST", url, label="Gemini",
                                headers=self._auth_headers(),
                                payload=payload, timeout=60)
        if "error" in data:
            raise RuntimeError(f"Gemini error: {data['error']}")
        return _gemini_text(data) or "(empty response)"



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

        data = await _http_json("POST", url, label="OpenAI", headers=headers,
                                payload=payload, timeout=60)
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
        data = await _http_json("POST", url, label="OpenAI", headers=headers,
                                payload=payload, timeout=60)
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
        data = await _http_json("POST", url, label="MiniMax", headers=headers,
                                payload=payload, timeout=timeout,
                                is_cancelled=is_cancelled)
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
        chunk_seconds: int = 600,
        on_part: Callable[[int, int], None] | None = None,
        # Accepted for interface parity with chunked providers; these
        # providers never split, so the callback stays unused here.
        on_split_progress: Callable[[float], None] | None = None,
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


class GLMProvider(AIProvider):
    """GLM (Zhipu) via OpenRouter — OpenAI-compatible chat format.

    Default base URL is OpenRouter (https://openrouter.ai/api/v1) with
    the vendor-prefixed model id z-ai/glm-5.3-flash; a Zhipu direct key
    also works by storing base_url https://open.bigmodel.cn/api/paas/v4
    and the bare model id. Frame mode sends images as data URLs like
    OpenAI (one request per frame, matching the GUI's per-frame
    description model), and ask_text reuses the same endpoint.
    """

    name = "glm"
    models = [
        "z-ai/glm-5.3-flash",
    ]

    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = api_key
        self.base_url = (base_url or "https://openrouter.ai/api/v1").rstrip("/")

    # v1.6.3: a video request uploads tens of megabytes and then waits
    # minutes for the answer, so a dropped connection is not a rare
    # event — two in a row were seen on a 16 MB upload (WinError 64,
    # then WinError 121). Without a retry the whole job is lost at
    # whatever percent it died, after the user already paid the time.
    _NETWORK_RETRIES = 3
    _RETRY_BACKOFF_SECONDS = 5.0
    # Tokens the model may spend thinking before it must start writing.
    # 2000 measured as ample: the run that produced a full answer used 17.
    _REASONING_BUDGET = 2000
    # Upload encoding. Raising these costs upload time on a slow link
    # and buys nothing a describing model uses; lowering them starts to
    # lose on-screen text, which IS used. 360p/5fps measured as the
    # point where description quality stopped improving.
    _UPLOAD_HEIGHT = 360
    _UPLOAD_FPS = 5

    async def _chat(self, payload: dict, timeout: float) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(1, self._NETWORK_RETRIES + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url, json=payload, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                    ) as resp:
                        if resp.status in (429, 500, 502, 503, 504):
                            # Provider-side wobble: worth another go.
                            body = await resp.text()
                            raise aiohttp.ClientError(
                                f"HTTP {resp.status}: {body[:120]}")
                        if resp.status != 200:
                            # 4xx (bad key, no credit, payload too big):
                            # retrying cannot help and would burn time.
                            body = await resp.text()
                            raise RuntimeError(
                                f"GLM HTTP {resp.status}: {body[:200]}")
                        data = await resp.json()
                        if "error" in data:
                            raise RuntimeError(f"GLM API error: {data['error']}")
                        choices = data.get("choices", [])
                        if not choices:
                            return "(no response from GLM)"
                        choice = choices[0]
                        content = choice.get("message", {}).get("content") or ""
                        if not content.strip():
                            # An empty reply used to surface as "no
                            # descriptions" with no explanation. Name the
                            # cause: usually the reasoning budget ate the
                            # whole allowance (finish_reason "length").
                            usage = data.get("usage", {}) or {}
                            reasoning = (usage.get("completion_tokens_details")
                                         or {}).get("reasoning_tokens")
                            logger.error(
                                "GLM returned EMPTY content "
                                "(finish_reason=%s, completion_tokens=%s, "
                                "reasoning_tokens=%s). The model spent its "
                                "budget thinking instead of answering.",
                                choice.get("finish_reason"),
                                usage.get("completion_tokens"), reasoning)
                        return content
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                last_error = e
                if attempt >= self._NETWORK_RETRIES:
                    break
                wait = self._RETRY_BACKOFF_SECONDS * attempt
                logger.warning(
                    "Network error on attempt %d/%d (%s); retrying in %.0fs",
                    attempt, self._NETWORK_RETRIES, e, wait)
                await asyncio.sleep(wait)
        raise RuntimeError(
            f"GLM request failed after {self._NETWORK_RETRIES} attempts: "
            f"{last_error}")

    async def describe_image(
        self, image_path: str, prompt: str, model: str = ""
    ) -> str:
        if not self.api_key:
            raise ValueError("GLM API key not configured")
        model = model or self.models[0]
        img_b64, mime = self._load_image_b64(image_path)
        payload = {
            "model": model,
            # GLM reasoning models burn tokens thinking before the visible
            # answer; 1024 truncated/emptied replies (AGENTS.md pitfall 7).
            "max_tokens": 6000,
            "messages": [
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                ]},
            ],
        }
        return _strip_think(await self._chat(payload, timeout=120))

    # Empirically verified against OpenRouter (probe, 2026-09): a
    # 50.7 MB video (67.6 MB base64 payload) is accepted; 97.6 MB is
    # rejected with HTTP 502. Guard sits at the verified point; larger
    # videos are auto-compressed to 360p before upload.
    MAX_VIDEO_BYTES = 50 * 1024 * 1024
    COMPRESS_TARGET_BYTES = 40 * 1024 * 1024

    @staticmethod
    def _chunk_seconds_to_fit(path: Path, duration: float,
                              limit_bytes: int) -> int:
        """Seconds per part that keep each piece under the upload limit
        at FULL resolution. 0 when the maths does not work out.

        Uses the file's own average bitrate, with 15% headroom because a
        cut piece carries its own container overhead and a keyframe.
        """
        try:
            size = path.stat().st_size
            if duration <= 0 or size <= 0:
                return 0
            bytes_per_second = size / duration
            seconds = int((limit_bytes * 0.85) / bytes_per_second)
            # Below ~20s per part the request count (and the continuity
            # cost between parts) outweighs the quality gain.
            return seconds if seconds >= 20 else 0
        except Exception:
            return 0

    async def describe_video_full(
        self, video_path: str, prompt: str, model: str = "",
        on_status: Callable[[str], None] | None = None,
        on_upload_progress: Callable[[float], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        chunk_seconds: int = 600,
        on_part: Callable[[int, int], None] | None = None,
        on_split_progress: Callable[[float], None] | None = None,
        transcript: list | None = None,
        preserve_resolution: bool = False,
    ) -> list[tuple[float, str]]:
        """Upload a video file as base64 via OpenRouter video_url.

        Videos longer than chunk_seconds are split into consecutive
        parts (split_video_for_upload); each part is described in its
        own request and the model's part-local timestamps are shifted
        by the part's start offset. Empirically verified against
        OpenRouter + z-ai/glm-5.3-flash (probe, 2026-09): a 60 s video
        costs ~9.2k prompt tokens; 50.7 MB uploads succeed, ~98 MB is
        rejected.
        """
        path = Path(video_path)
        try:
            duration = self._probe_duration(path, is_cancelled=is_cancelled)
        except RuntimeError:
            # Undecodable/unreadable container: still try one part.
            # The size guard and ffmpeg itself will surface a clear
            # error later if the file is truly broken.
            logger.debug("duration probe failed; using one part",
                         exc_info=True)
            duration = 0.0
        parts: list[Path] = []
        try:
            if duration > chunk_seconds + 1.0:
                if on_status:
                    on_status("splitting")
                starts, parts = self.split_video_for_upload(
                    path, chunk_seconds,
                    is_cancelled=is_cancelled, on_status=on_status,
                    on_split_progress=on_split_progress)
            else:
                starts = [0.0]
                if path.stat().st_size > self.MAX_VIDEO_BYTES:
                    if is_cancelled and is_cancelled():
                        raise RuntimeError("cancelled")
                    # v1.6.1: an oversized video can be made to fit two
                    # ways — shrink the picture, or cut it into shorter
                    # pieces. Compression scales to 360p, which is fine
                    # for a talking head and useless for slides, code or
                    # a chart: the text stops being legible, so the
                    # description of it stops being right. Splitting
                    # keeps every pixel and costs one extra request per
                    # part.
                    if preserve_resolution:
                        fitting = self._chunk_seconds_to_fit(
                            path, duration, self.MAX_VIDEO_BYTES)
                        if fitting and duration > 0:
                            if on_status:
                                on_status("splitting")
                            # keep_resolution: the split used to scale
                            # to 360p anyway, undoing this whole branch.
                            starts, parts = self.split_video_for_upload(
                                path, fitting,
                                is_cancelled=is_cancelled,
                                on_status=on_status,
                                on_split_progress=on_split_progress,
                                keep_resolution=True)
                    if not parts:
                        if on_status:
                            on_status("compressing")
                        parts = [self.compress_video_for_upload(
                            path, self.COMPRESS_TARGET_BYTES,
                            is_cancelled=is_cancelled,
                            cache_dir=self.upload_cache_dir)]
                else:
                    parts = [path]
            total = len(parts)
            # v1.7.4: each part's REAL length. chunk_seconds was passed
            # instead, so a 60 s clip was described as if it ran to
            # 10:00 — the gap budget offered ~1,300 words of "silence"
            # after the video ended, and a preserve-resolution part got
            # the next parts' speech. 0 = unknown (probe failed).
            ends = list(starts[1:len(parts)]) + [duration]
            part_lens = [max(0.0, e - s) if duration > 0 else 0.0
                         for s, e in zip(starts, ends)]
            merged: list[tuple[float, str]] = []
            done_parts = 0
            prev_summary = ""
            for i, (part, offset) in enumerate(zip(parts, starts)):
                if is_cancelled and is_cancelled():
                    raise RuntimeError("cancelled")
                if on_part:
                    on_part(i + 1, total)
                part_len = part_lens[i] if i < len(part_lens) else 0.0
                # v1.5.3: pass a short summary of the previous part so
                # the model keeps its bearings (no "the video starts
                # with" at minute 20) and keeps one name per character.
                pairs = await self._describe_one_part(
                    part, prompt, model, on_status=on_status,
                    is_cancelled=is_cancelled, offset=offset,
                    part_index=i + 1, part_total=total,
                    prev_summary=prev_summary, transcript=transcript,
                    part_seconds=part_len)
                if not pairs:
                    # v1.5.0: a part that parses to zero cues means the
                    # rest of the video is silently dropped. Retry once
                    # before giving up on this part.
                    logger.warning(
                        "part %d/%d returned no cues; retrying once",
                        i + 1, total)
                    pairs = await self._describe_one_part(
                        part, prompt, model, on_status=on_status,
                        is_cancelled=is_cancelled, offset=offset,
                        part_index=i + 1, part_total=total,
                        prev_summary=prev_summary, transcript=transcript,
                        part_seconds=part_len)
                if pairs:
                    prev_summary = "; ".join(
                        txt for _, txt in pairs[-6:])
                merged.extend(pairs)
                done_parts += 1
                if on_split_progress:
                    try:
                        # Overall percentage across ALL parts: splitting
                        # counts as the first 10%, each described part
                        # shares the remaining 90% equally.
                        on_split_progress(
                            10.0 + 90.0 * done_parts / max(1, total))
                    except Exception:
                        logger.debug("on_split_progress raised", exc_info=True)
            # v1.6.3: sort before returning, as the Gemini path already
            # did. Observed on a real run: asked for BOTH speech and
            # visuals, the model answered in two passes — 00:00, 00:04,
            # 00:12, 00:30, 00:48, then back to 00:16, 00:17, 00:22.
            # Unsorted cues reach the SRT and the player, which both
            # assume chronological order, so the listener gets the story
            # out of sequence.
            merged.sort(key=lambda pair: pair[0])
            return merged
        finally:
            import shutil as _shutil
            part_dirs: set[Path] = set()
            for p in parts:
                try:
                    # A cached upload copy is kept ON PURPOSE so a retry
                    # skips the re-encode (v1.6.7). This loop deleted it
                    # anyway, which made the whole cache pointless in the
                    # full-video path — the one actually configured here.
                    # Only found by watching a real run: the app logged
                    # "Compressed upload copy kept for retries" and the
                    # file was not on disk afterwards.
                    if p != path and not self.is_cached_upload(p):
                        p.unlink(missing_ok=True)
                        if p.parent.name.startswith(
                                ("odc_vcompress_", "odc_vsplit_")):
                            part_dirs.add(p.parent)
                except OSError:
                    pass
            for d in part_dirs:
                _shutil.rmtree(d, ignore_errors=True)

    async def _describe_one_part(
        self, path: Path, prompt: str, model: str,
        on_status: Callable[[str], None] | None,
        is_cancelled: Callable[[], bool] | None,
        offset: float = 0.0,
        part_index: int = 0, part_total: int = 0,
        prev_summary: str = "",
        transcript: list | None = None,
        part_seconds: float = 0.0,
    ) -> list[tuple[float, str]]:
        """Describe one video part and shift timestamps by offset.

        part_index/part_total + prev_summary give the model its place
        in the WHOLE video (v1.5.3 continuity fix).
        """
        size = path.stat().st_size
        if size > self.MAX_VIDEO_BYTES:
            if on_status:
                on_status("compressing")
            if is_cancelled and is_cancelled():
                raise RuntimeError("cancelled")
            path = self.compress_video_for_upload(
                path, self.COMPRESS_TARGET_BYTES,
                is_cancelled=is_cancelled,
                cache_dir=self.upload_cache_dir)
            try:
                if is_cancelled and is_cancelled():
                    raise RuntimeError("cancelled")
                if on_status:
                    on_status("encoding")
                b64 = base64.b64encode(path.read_bytes()).decode()
            finally:
                # A throwaway copy lives in its own mkdtemp dir and is
                # NOT in the caller's parts list; without this cleanup an
                # oversized part leaked ~40 MB per part in %TEMP%.
                # A CACHED copy is kept on purpose (v1.6.7) so a retry
                # after a failed upload does not re-encode the video.
                if not self.is_cached_upload(path):
                    try:
                        path.unlink(missing_ok=True)
                        path.parent.rmdir()
                    except OSError:
                        pass
        else:
            if is_cancelled and is_cancelled():
                raise RuntimeError("cancelled")
            if on_status:
                on_status("encoding")
            b64 = base64.b64encode(path.read_bytes()).decode()
        data_url = f"data:video/mp4;base64,{b64}"
        # v1.5.3: position notice so part 2+ is never treated as the
        # beginning of the video.
        position = ""
        if part_total > 1 and part_index > 0:
            position = (
                f"CONTEXT: You are describing part {part_index} of "
                f"{part_total} of ONE longer video. This part begins at "
                f"{offset / 60.0:.1f} minutes into the full video; the "
                "timestamps you output must be part-local (00:00 = the "
                "start of THIS part) and are shifted automatically.\n")
            if prev_summary:
                position += (
                    "What happened just before this part (end of the "
                    f"previous part): {prev_summary}\n"
                    "Continue the story smoothly; do NOT restart the "
                    "narrative and do NOT say the video starts here.\n")
        # v1.6.1: this provider cannot hear the video (probed: "NO AUDIO
        # ACCESS"), so the words spoken in THIS part are supplied as
        # text. Timestamps are shifted to part-local time to match the
        # ones the model is asked to output.
        spoken = ""
        if transcript:
            part_end = offset + part_seconds if part_seconds else None
            spoken = build_transcript_block(
                transcript, start=offset, end=part_end, offset=offset,
                words_per_second=self.words_per_second)
        payload = {
            "model": model or self.models[0],
            "max_tokens": 16000,
            # v1.6.3: CAP THE THINKING. Measured on a real 45-second
            # clip with the `foreign` preset: the model spent 15,995 of
            # its 16,000 completion tokens on internal reasoning, leaving
            # FIVE for the answer, and returned empty content with
            # finish_reason "length". The app reported "no descriptions"
            # with no reason given. With the cap: 17 reasoning tokens,
            # finish_reason "stop", a full correct answer.
            #
            # This is AGENTS.md pitfall 7 one level up — raising
            # max_tokens does not help, because the model simply thinks
            # more. The budget has to be split, not enlarged.
            "reasoning": {"max_tokens": self._REASONING_BUDGET},
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": (
                        "You are given a full video file. Describe it "
                        "for a blind viewer.\n"
                        "Watch the WHOLE video including audio/speech.\n"
                        "Output one event per line, each line EXACTLY in "
                        "this format:\n"
                        "[H:MM:SS] description\n"
                        "Rules:\n"
                        "- Timestamps are when the event happens in the "
                        "video.\n"
                        "- Order lines by time.\n"
                        "- WHAT to describe is decided by the prompt "
                        "above; follow it exactly. Do not add dialogue or "
                        "sound narration unless it asks for them (v1.6.0: "
                        "a rule here silently overrode the preset).\n"
                        "- Use ONE consistent name for the same person, "
                        "object or place.\n"
                        "- Never say 'the video starts with' unless this "
                        "really is the first part.\n"
                        "- No numbering, no extra text before or after "
                        "the lines.\n"
                        + position + spoken)},
                    {"type": "video_url", "video_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            }],
        }
        if is_cancelled and is_cancelled():
            raise RuntimeError("cancelled")
        if on_status:
            on_status("uploading")
        # v1.7.5: Cancel is honoured DURING the request, not only
        # between requests — one part may take 30 minutes (and GLM
        # retries a timeout), so Cancel used to wait up to ~90 minutes.
        text = await _run_cancellable(
            self._chat(payload, timeout=1800.0), is_cancelled)
        if is_cancelled and is_cancelled():
            raise RuntimeError("cancelled")
        if on_status:
            on_status("parsing")
        pairs = parse_gemini_timestamp_lines(_strip_think(text))
        if part_seconds and part_seconds > 0:
            # v1.7.4: a time the model invents past the end of this part
            # used to land inside the NEXT part, or after the video had
            # ended. A second of slack covers rounding at the cut.
            kept = [(min(t, part_seconds), d) for (t, d) in pairs
                    if t <= part_seconds + 1.0]
            if len(kept) < len(pairs):
                logger.warning("part %d: dropped %d cue(s) past its end "
                               "(%.1f s)", part_index,
                               len(pairs) - len(kept), part_seconds)
            pairs = kept
        return [(t + offset, d) for (t, d) in pairs]

    @staticmethod
    def _ffmpeg() -> str:
        from .tools import find_tool, tool_available
        if not tool_available("ffmpeg"):
            raise RuntimeError(
                "ffmpeg not found — neither bundled with this app nor on "
                "PATH; video compression cannot run")
        return find_tool("ffmpeg")

    def _run_ffmpeg_cancellable(
        self, cmd: list[str],
        is_cancelled: Callable[[], bool] | None,
        timeout: float,
    ) -> tuple[int, bytes]:
        """Run an ffmpeg command while polling is_cancelled every second
        so the GUI Cancel button takes effect mid-run (v1.5.4: the old
        blocking _sp.run could ignore Cancel for up to 30 minutes).

        Returns (returncode, stderr tail). Raises RuntimeError on cancel
        or timeout. stderr is drained by a daemon thread and only the
        last 8 KiB are kept.
        """
        import subprocess as _sp
        import threading as _threading
        import time as _time
        proc = _sp.Popen(cmd, stdout=_sp.DEVNULL, stderr=_sp.PIPE)
        stderr_tail = bytearray()
        deadline = _time.monotonic() + timeout

        def _drain() -> None:
            try:
                for line in iter(proc.stderr.readline, b""):
                    stderr_tail.extend(line)
                    del stderr_tail[:-8192]
            except Exception:
                pass

        t = _threading.Thread(target=_drain, daemon=True)
        t.start()
        ret: int | None = None
        try:
            while True:
                if is_cancelled is not None and is_cancelled():
                    proc.kill()
                    raise RuntimeError("cancelled")
                ret = proc.poll()
                if ret is not None:
                    break
                if _time.monotonic() > deadline:
                    proc.kill()
                    raise RuntimeError(
                        f"ffmpeg timed out after {int(timeout)} s")
                _time.sleep(1.0)
        finally:
            if proc.poll() is None:
                proc.kill()
            try:
                proc.stderr.close()
            except Exception:
                pass
            t.join(timeout=2.0)
        return ret, bytes(stderr_tail)

    def upload_cache_name(self, path: Path, target_bytes: int) -> str:
        """A name that changes whenever the compressed result would.

        Keyed on the source file's identity and on every encode setting
        that affects the output, so a cached copy is only reused when it
        is genuinely the same job. Bumping _UPLOAD_HEIGHT or _UPLOAD_FPS
        therefore invalidates old copies instead of silently serving
        video encoded to the old settings.
        """
        try:
            stat = path.stat()
            identity = f"{path.name}:{stat.st_size}:{int(stat.st_mtime)}"
        except OSError:
            identity = path.name
        recipe = (f"{identity}:{target_bytes}:{self._UPLOAD_HEIGHT}"
                  f":{self._UPLOAD_FPS}")
        digest = hashlib.sha256(recipe.encode("utf-8")).hexdigest()[:16]
        return f"upload_{digest}.mp4"

    def compress_video_for_upload(
        self, path: Path, target_bytes: int,
        is_cancelled: Callable[[], bool] | None = None,
        cache_dir: str = "",
    ) -> Path:
        """Re-encode a video down to about target_bytes (360p).

        Single-pass bitrate fit; quality is good enough for AI viewing
        and far better than failing the whole run.

        With cache_dir — normally the project's media folder — the
        result is kept and reused (v1.6.7). GLM sends video base64
        inside one chat request, so an interrupted upload cannot be
        resumed at the protocol level; but the expensive half is this
        re-encode, which used to be thrown away on every failure and
        redone from scratch on every retry. Caching it makes a retry
        cost one upload instead of an upload plus minutes of ffmpeg.

        Returns a path the caller must NOT delete when it is cached;
        callers should compare against is_cached_upload().
        """
        import tempfile as _tf
        import shutil as _shutil
        if cache_dir:
            cached = Path(cache_dir) / self.upload_cache_name(
                path, target_bytes)
            if cached.exists() and cached.stat().st_size > 0:
                logger.info("Reusing the compressed upload copy (%.1f MB): "
                            "%s", cached.stat().st_size / 1e6, cached.name)
                return cached
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            # Encode beside the final name, then rename. A compression
            # killed halfway (Cancel, crash, power loss) must not leave
            # a truncated file that the next run happily uploads as if
            # it were the whole video.
            # ".partial.mp4", not ".part": ffmpeg picks the muxer from
            # the extension, and an unknown one fails outright with
            # "Error initializing the muxer ... Invalid argument".
            staging = cached.with_name(
                f"{cached.stem}.partial{cached.suffix}")
            staging.unlink(missing_ok=True)
            self._compress_to(path, staging, target_bytes, is_cancelled)
            staging.replace(cached)
            # Full path, not just the name: with only the name, "it was
            # kept" could not be told apart from "it was kept somewhere
            # else and then deleted", which is what happened.
            logger.info("Compressed upload copy kept for retries: %s "
                        "(%.1f MB)", cached, cached.stat().st_size / 1e6)
            return cached
        out_dir = Path(_tf.mkdtemp(prefix="odc_vcompress_"))
        try:
            return self._compress_to(path, out_dir / path.name,
                                     target_bytes, is_cancelled)
        except Exception:
            _shutil.rmtree(out_dir, ignore_errors=True)
            raise

    @staticmethod
    def is_cached_upload(path: Path) -> bool:
        """True when this compressed copy is kept for retries.

        Callers delete their temporary compressed file; deleting a
        cached one would undo the whole point of caching it.
        """
        # ".partial." is a half-written encode, never something to keep
        # or to upload; it only escapes here if a crash left one behind.
        return (path.name.startswith("upload_")
                and ".partial." not in path.name)

    def _compress_to(
        self, path: Path, out: Path, target_bytes: int,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Path:
        """Encode path into out at the upload settings. Raises on failure."""
        import shutil as _shutil
        out_dir = out.parent
        duration = 1.0
        try:
            _ret, stderr_tail = self._run_ffmpeg_cancellable(
                [self._ffmpeg(), "-hide_banner", "-nostdin", "-i",
                 str(path), "-f", "null", "-"],
                is_cancelled, 600)
            m = None
            for m in re.finditer(
                    r"time=(\d+):(\d+):(\d+(?:\.\d+)?)",
                    stderr_tail.decode("utf-8", "replace")):
                pass  # keep the LAST time= (real duration, not the first)
            if m:
                duration = (int(m.group(1)) * 3600
                            + int(m.group(2)) * 60
                            + float(m.group(3)))
        except RuntimeError:
            # Only the half-written output goes, never the directory:
            # since v1.6.7 out_dir can be the PROJECT'S media folder,
            # which holds the downloaded video. rmtree here would have
            # deleted the user's video to clean up a failed encode.
            out.unlink(missing_ok=True)
            raise
        except Exception:
            logger.debug("duration probe failed", exc_info=True)
        total_bits = target_bytes * 8 * 0.95
        kbps = max(80, int(total_bits / max(duration, 1.0) / 1000))
        ret, stderr_tail = self._run_ffmpeg_cancellable([
            self._ffmpeg(), "-hide_banner", "-nostdin", "-y", "-v",
            "error", "-i", str(path),
            # v1.6.3: encode for a DESCRIBER, not for a viewer.
            #
            # -an: this provider cannot hear the video at all (probed:
            # "NO AUDIO ACCESS"), and since v1.6.1 the words are sent
            # separately as a transcript. Every audio byte uploaded was
            # therefore paying postage on something nobody receives.
            #
            # fps=5: a describing model samples frames; it does not
            # watch at 30. Measured on a real 2-minute clip: 3.4 MB at
            # 30 fps with audio versus 1.1 MB at 5 fps without, and the
            # leaner file produced MORE detail, not less — it still read
            # the gravestone text and caught a minibus crossing frame.
            #
            # On a 72 KB/s link, which is what the user actually had,
            # that is the difference between a 5-minute upload and a
            # 90-second one.
            "-vf", f"scale=-2:{self._UPLOAD_HEIGHT},fps={self._UPLOAD_FPS}",
            "-an",
            "-c:v", "libx264", "-preset", "veryfast",
            "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.4)}k",
            "-bufsize", f"{int(kbps * 2)}k",
            "-pix_fmt", "yuv420p", str(out),
        ], is_cancelled, 1800)
        if ret != 0 or not out.exists():
            tail = stderr_tail.decode("utf-8", "replace")[-300:]
            out.unlink(missing_ok=True)  # never the directory: see above
            raise RuntimeError(f"video compression failed: {tail}")
        if out.stat().st_size > target_bytes * 1.3:
            logger.warning("compressed video still large: %.1f MB",
                           out.stat().st_size / 1e6)
        return out

    def _probe_duration(
        self, path: Path,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> float:
        """Return the video duration in seconds via ffmpeg decode.

        Cancellable via is_cancelled (v1.5.4): the decode pass can run
        for minutes on long videos.
        """
        try:
            _ret, stderr_tail = self._run_ffmpeg_cancellable(
                [self._ffmpeg(), "-hide_banner", "-nostdin", "-i",
                 str(path), "-f", "null", "-"],
                is_cancelled, 900)
            best = 0.0
            for m in re.finditer(
                    r"time=(\d+):(\d+):(\d+(?:\.\d+)?)",
                    stderr_tail.decode("utf-8", "replace")):
                t = (int(m.group(1)) * 3600 + int(m.group(2)) * 60
                     + float(m.group(3)))
                best = max(best, t)
            if best <= 0.0:
                raise RuntimeError("ffmpeg could not read duration")
            return best
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"ffmpeg duration probe failed: {e}") from e

    def split_video_for_upload(
        self, path: Path, chunk_seconds: int,
        is_cancelled: Callable[[], bool] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_split_progress: Callable[[float], None] | None = None,
        keep_resolution: bool = False,
    ) -> tuple[list[float], list[Path]]:
        """Split a video into consecutive parts of about chunk_seconds.

        Uses ffmpeg segment muxer with one re-encode at the target
        bitrate (keyframe-aligned cuts, uniform parts). Returns
        (start_offsets_seconds, part_paths). Parts live in a temp dir;
        the caller deletes them when done.

        keep_resolution (v1.7.4): no 360p scale, and the source's own
        bitrate — the caller already chose a part length that fits.
        """
        import shutil as _shutil
        import tempfile as _tf
        duration = self._probe_duration(path, is_cancelled=is_cancelled)
        if duration <= 0:
            raise RuntimeError("cannot split an unreadable video")
        out_dir = Path(_tf.mkdtemp(prefix="odc_vsplit_"))
        try:
            return self._split_into(path, out_dir, duration, chunk_seconds,
                                    is_cancelled, on_status,
                                    on_split_progress, keep_resolution)
        except BaseException:
            # v1.7.4: on cancel or failure the caller never receives the
            # part list, so nobody else can delete these parts.
            _shutil.rmtree(out_dir, ignore_errors=True)
            raise

    def _split_into(
        self, path: Path, out_dir: Path, duration: float,
        chunk_seconds: int,
        is_cancelled: Callable[[], bool] | None,
        on_status: Callable[[str], None] | None,
        on_split_progress: Callable[[float], None] | None,
        keep_resolution: bool,
    ) -> tuple[list[float], list[Path]]:
        import subprocess as _sp
        # v1.7.5: each PART is uploaded on its own, so its budget is the
        # per-upload target spread over the PART's length. This used to
        # divide the budget by the part count AND spread it over the whole
        # video, leaving each part ~1/n of what it could carry (Sintel,
        # 2 parts: 171 kbps). Never above the source's own bitrate, and
        # 360p needs no more than ~1 Mbps.
        part_seconds = max(1.0, min(float(chunk_seconds), duration))
        budget_kbps = int(self.COMPRESS_TARGET_BYTES * 8 * 0.95
                          / part_seconds / 1000)
        try:
            source_kbps = int(path.stat().st_size * 8 / duration / 1000)
        except OSError:
            source_kbps = budget_kbps
        kbps = max(80, min(budget_kbps, source_kbps, 1000))
        scale: list[str] = ["-vf", "scale=-2:360"]
        if keep_resolution:
            scale = []
            try:
                kbps = max(80, int(path.stat().st_size * 8 / duration
                                   / 1000))
            except OSError:
                pass
        pattern = out_dir / "part_%04d.mp4"
        cmd = [
            self._ffmpeg(), "-hide_banner", "-nostdin", "-y", "-v",
            "error", "-progress", "pipe:1", "-i", str(path),
            *scale,
            "-c:v", "libx264", "-preset", "veryfast",
            "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.4)}k",
            "-bufsize", f"{int(kbps * 2)}k",
            "-pix_fmt", "yuv420p",
            # The segment muxer only cuts at keyframes; without this,
            # x264's default 250-frame GOP makes cuts up to ~8 s late
            # (or produces a single part for short clips).
            "-force_key_frames", "expr:gte(t,n_forced*2)",
            "-f", "segment",
            "-segment_time", str(chunk_seconds),
            "-reset_timestamps", "1",
            str(pattern),
        ]
        import threading as _threading
        proc = _sp.Popen(cmd, stdout=_sp.PIPE, stderr=_sp.PIPE)
        stderr_tail: list[bytes] = []

        def _drain_err() -> None:
            try:
                for line in iter(proc.stderr.readline, b""):
                    stderr_tail.append(line)
                    if len(stderr_tail) > 16:
                        stderr_tail.pop(0)
            except Exception:
                pass

        _threading.Thread(target=_drain_err, daemon=True).start()
        # Parse ffmpeg key=value progress lines (out_time_us) for a
        # REAL split percentage. Splitting counts as the FIRST 10%
        # of the overall progress (each described part then shares
        # the remaining 90%), so scale 0..100 → 0..10 to keep the
        # whole stream monotonic.
        for line in proc.stdout:
            if is_cancelled and is_cancelled():
                try:
                    proc.kill()
                    # Windows keeps the open part locked until ffmpeg
                    # has really exited; the cleanup needs it gone.
                    proc.wait(timeout=10)
                except Exception:
                    pass
                raise RuntimeError("cancelled")
            if (on_split_progress and line.startswith(b"out_time_us=")
                    and duration > 0):
                try:
                    us = int(line.split(b"=", 1)[1].strip())
                    on_split_progress(min(
                        10.0, max(0.0, us / 1e6 / duration * 10.0)))
                except ValueError:
                    pass
        proc.wait(timeout=3600)
        if proc.returncode != 0:
            tail = b"".join(stderr_tail).decode("utf-8", "replace")[-300:]
            raise RuntimeError(f"video split failed: {tail}")
        parts = sorted(out_dir.glob("part_*.mp4"))
        if not parts:
            raise RuntimeError("video split produced no parts")
        # Actual part durations → start offsets (last part is shorter;
        # keyframe-aligned cuts make real lengths drift from nominal).
        starts: list[float] = []
        acc = 0.0
        for p in parts:
            starts.append(acc)
            acc += self._probe_duration(p)
        if on_status:
            on_status("splitting")
        return starts, parts

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
                logger.warning("GLM frame error: %s", e)
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
            raise ValueError("GLM API key not configured")
        model = model or self.models[0]
        messages: list[dict] = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in (history or [])
        ]
        messages.append({"role": "user", "content": question})
        # GLM reasoning models burn tokens thinking before the visible
        # answer; 1024 truncated/emptied replies (AGENTS.md pitfall 7).
        payload = {"model": model, "max_tokens": 6000, "messages": messages}
        return _strip_think(await self._chat(payload, timeout=120))

    async def describe_video_frames_batch(
        self, frames: list[str], prompt: str, model: str = "",
        on_status: Callable[[str], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        expected_times: list[float] | None = None,
    ) -> list[tuple[float, str]]:
        """One-shot mode: ALL frames in ONE request; the model READS the
        burned-in H:MM:SS stamps instead of receiving per-frame times.

        Frames are split into <=150-image batches (1 batch = 1 request,
        requests run concurrently when more than one is needed); replies
        are parsed for timestamped lines and snapped onto the known
        extraction grid so a model misread of a stamp cannot desync the
        player timeline.
        """
        if is_cancelled is not None and is_cancelled():
            raise RuntimeError("cancelled")
        if not self.api_key:
            raise ValueError("GLM API key not configured")
        model = model or self.models[0]

        def status(s: str) -> None:
            if on_status:
                try:
                    on_status(s)
                except Exception:
                    logger.debug("on_status raised", exc_info=True)

        status("describing")
        batches = [frames[i:i + MAX_IMAGES_PER_REQUEST]
                   for i in range(0, len(frames), MAX_IMAGES_PER_REQUEST)]

        def _batch_note(idx: int) -> str:
            # v1.5.3: batches beyond the first run as separate requests;
            # without a position note each one reads as the START of the
            # video ("The video starts with..."). expected_times carries
            # the exact extraction grid, so the first frame of batch i
            # sits at expected_times[i * MAX_IMAGES_PER_REQUEST].
            if idx == 0 or not expected_times:
                return ""
            first = idx * MAX_IMAGES_PER_REQUEST
            if first >= len(expected_times):
                return ""
            t0 = float(expected_times[first])
            m, sec = divmod(int(t0), 60)
            return (
                f"CONTEXT: these frames are from {m:02d}:{sec:02d} "
                "onwards in the middle of a longer video - they are NOT "
                "the beginning. Read the burned-in timestamps and "
                "describe only what happens at each moment.\n")

        # v1.7.5: the batches run together; when one fails (or the user
        # cancels) the rest are cancelled too. A bare gather() left them
        # running — and billing — after the job had already failed.
        tasks = [asyncio.ensure_future(self._chat({
                    "model": model,
                    "temperature": 0.3,
                    "messages": [{"role": "user",
                                  "content": _fast_batch_content(
                                      [Path(f) for f in batch], prompt,
                                      batch_note=_batch_note(bi))}],
                }, timeout=900))
                 for bi, batch in enumerate(batches)]
        try:
            texts = await _run_cancellable(asyncio.gather(*tasks),
                                           is_cancelled)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        merged: list[tuple[float, str]] = []
        for text in texts:
            merged.extend(parse_gemini_timestamp_lines(_strip_think(text)))
        merged = snap_timestamps(merged, expected_times)
        merged.sort(key=lambda x: x[0])
        return merged


# ── Fast one-shot batch mode (burned-in timestamps) ──────────────────
#
# ffmpeg drawtext recipe VERIFIED on ffmpeg 8.x/Windows: the drive-letter
# colon must be BOTH escaped AND single-quoted inside the option, and an
# explicit fontfile is mandatory (without it drawtext loads fontconfig,
# which crashes 0xC0000005 when no default config exists).
FAST_BATCH_TS_PROMPT_SUFFIX = (
    "\n\nEvery image above is a frame from ONE video and has its "
    "timestamp H:MM:SS BURNED INTO the top-left corner on a dark box. "
    "READ that burned-in timestamp on every frame instead of guessing "
    "from the order. Reply with ONE line per notable event, in EXACTLY "
    "this format and nothing else:\n"
    "H:MM:SS - description\n"
    "Use the burned-in timestamps verbatim. Cover the whole video in "
    "chronological order. Write descriptions for a blind viewer. "
    + CONTINUITY_RULES +
    " No numbering, no markdown, no extra commentary."
)
_FAST_BATCH_FONTS = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/times.ttf",
    "C:/Windows/Fonts/calibri.ttf",
]
MAX_IMAGES_PER_REQUEST = 150


def _find_fast_batch_font() -> str:
    for p in _FAST_BATCH_FONTS:
        if Path(p).exists():
            return p
    raise RuntimeError(
        "no TrueType font found for timestamp burn-in (searched: "
        + ", ".join(_FAST_BATCH_FONTS) + ")")


def build_fast_batch_filter(fps: float) -> str:
    """Full -vf value: fps -> 720p scale -> burned-in H:MM:SS stamp."""
    font = _find_fast_batch_font()
    font_part = f"fontfile='{font.replace(':', chr(92) + ':')}'"
    drawtext = f"drawtext={font_part}:{_FAST_BATCH_DRAWTEXT_BODY}"
    fps_s = str(int(fps)) if float(fps).is_integer() else str(fps)
    return f"fps={fps_s},scale=-2:720,{drawtext}"


_FAST_BATCH_DRAWTEXT_BODY = (
    "text='%{pts\\:hms}':x=10:y=10:fontsize=28:"
    "fontcolor=white:box=1:boxcolor=black@0.6"
)


def _fast_batch_content(
    frames: list[Path], prompt: str, batch_note: str = "",
) -> list[dict]:
    """OpenAI-compatible multipart content: every frame as a data URL,
    the burn-in reading instructions as the final text block."""
    content: list[dict] = []
    for f in frames:
        b64 = base64.b64encode(f.read_bytes()).decode("ascii")
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    content.append({"type": "text",
                    "text": batch_note + prompt
                    + FAST_BATCH_TS_PROMPT_SUFFIX})
    return content


def snap_timestamps(
    events: list[tuple[float, str]], grid: list[float] | None,
    max_gap: float = 1.5,
) -> list[tuple[float, str]]:
    """Snap model-read timestamps onto the known extraction grid.

    The pipeline knows every frame's exact time (frame i of fps N sits
    at i/N seconds), so a model misread of a burned-in stamp is
    corrected to the nearest real frame time; entries with no frame
    within max_gap seconds are dropped. grid must be sorted ascending;
    returns a new sorted list.
    """
    if not grid:
        return sorted(events, key=lambda x: x[0])
    times = sorted(set(grid))
    out: list[tuple[float, str]] = []
    for secs, text in events:
        if not text:
            continue
        i = bisect.bisect_left(times, secs)
        best = times[i] if i < len(times) else None
        if i > 0 and (best is None
                      or abs(times[i - 1] - secs) < abs(best - secs)):
            best = times[i - 1]
        if best is not None and abs(best - secs) <= max_gap:
            out.append((float(best), text))
    out.sort(key=lambda x: x[0])
    # Two model lines can misread onto the same grid slot; merge them
    # instead of emitting duplicate same-time cues (v1.5.4).
    merged: list[tuple[float, str]] = []
    for secs, text in out:
        if merged and merged[-1][0] == secs:
            merged[-1] = (secs, merged[-1][1] + " " + text)
        else:
            merged.append((secs, text))
    return merged


async def fetch_openrouter_video_models(
    catalog_url: str = "https://openrouter.ai/api/v1/models",
) -> list[str]:
    """Return OpenRouter model ids whose catalog entry lists video input.

    Used by the settings dialog "Fetch models" button so users only see
    models that can actually watch a video. Cheap and safe: the public
    catalog needs no API key and no credit, and "video in input
    modalities" is OpenRouter's own capability declaration.
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(
            catalog_url, timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"catalog HTTP {resp.status}")
            data = await resp.json()
    models: list[str] = []
    for entry in data.get("data", []):
        arch = entry.get("architecture") or {}
        mods = arch.get("input_modalities") or []
        if "video" in mods and entry.get("id"):
            models.append(entry["id"])
    return sorted(models)


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
        return await self._post_openai(payload)

    async def _call_anthropic(self, model: str, prompt: str, img_b64: str, mime: str) -> str:
        """Anthropic Messages API format."""
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
        return await self._post_anthropic(payload)

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
        if fmt == FORMAT_ANTHROPIC:
            return await self._post_anthropic(
                {"model": model, "max_tokens": 1024, "messages": messages})
        return await self._post_openai(
            {"model": model, "max_tokens": 1024, "messages": messages})

    async def _post_openai(self, payload: dict) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = await _http_json("POST", f"{self.base_url}/chat/completions",
                                label="Custom API", headers=headers,
                                payload=payload, timeout=120)
        if "error" in data:
            raise RuntimeError(f"Custom API error: {data['error']}")
        choices = data.get("choices", [])
        if not choices:
            return "(no response from custom API)"
        return choices[0]["message"]["content"]

    async def _post_anthropic(self, payload: dict) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        data = await _http_json("POST", f"{self.base_url}/messages",
                                label="Custom API", headers=headers,
                                payload=payload, timeout=120)
        for block in data.get("content", []):
            if block.get("type") == "text":
                return block["text"]
        return "(no text in custom API response)"


class AIEngine:
    """
    High-level AI engine with provider management and auto-fallback.
    Usage:
        engine = AIEngine()
        engine.set_provider("glm", api_key="...")
        desc = await engine.describe_frame("frame.jpg", "Describe this in Malay.")
    """

    PROVIDERS = {
        "gemini": GeminiProvider,
        "minimax": MiniMaxProvider,
        "openai": OpenAIProvider,
        "glm": GLMProvider,
        "custom": CustomProvider,
    }

    def __init__(self):
        self._providers: dict[str, AIProvider] = {}
        self._default_provider: str = ""
        # v1.5.2: default output language for descriptions ('' = model decides).
        self.output_lang: str = ""
        self._upload_cache_dir: str = ""

    @property
    def upload_cache_dir(self) -> str:
        """Folder that keeps compressed upload copies between attempts."""
        return getattr(self, "_upload_cache_dir", "")

    @upload_cache_dir.setter
    def upload_cache_dir(self, value: str) -> None:
        """Set it here and every provider follows.

        Providers are created lazily by set_provider(), so the value is
        stored and re-applied there too — setting it before the
        provider exists must not silently do nothing.

        getattr rather than self._providers: this is a speed hint, and
        it is set from inside the processing pipeline. An engine built
        with __new__ (as the tests do) has no _providers, and the
        AttributeError took the WHOLE JOB down — "no descriptions
        saved" from a failed cache hint. Nothing here is worth that.
        """
        self._upload_cache_dir = value or ""
        for provider in getattr(self, "_providers", {}).values():
            try:
                provider.upload_cache_dir = self._upload_cache_dir
            except Exception:  # a provider stub with no such attribute
                logger.debug("provider %s rejected the upload cache dir",
                             getattr(provider, "name", "?"))

    @property
    def words_per_second(self) -> float:
        """Speaking rate used to budget words against silent gaps."""
        return getattr(self, "_words_per_second", 2.5)

    @words_per_second.setter
    def words_per_second(self, value: float) -> None:
        """Set it here and every provider follows.

        Same guarded shape as upload_cache_dir, and for the same
        reason: this is set from inside the processing pipeline, and a
        hint about pacing must never take the whole job down.
        """
        try:
            rate = float(value)
        except (TypeError, ValueError):
            rate = 2.5
        self._words_per_second = max(0.5, rate)
        for provider in getattr(self, "_providers", {}).values():
            try:
                provider.words_per_second = self._words_per_second
            except Exception:
                logger.debug("provider %s rejected the speaking rate",
                             getattr(provider, "name", "?"))

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
        # A provider created after upload_cache_dir was set would
        # otherwise miss it and quietly fall back to a temp dir.
        self._providers[name].upload_cache_dir = self.upload_cache_dir
        self._providers[name].words_per_second = self.words_per_second
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
        output_lang: str = "",
        provider: str = "",
        model: str = "",
    ) -> str:
        """Describe a single image/frame. Auto-fallback on failure."""
        prov = self._provider_or_raise(provider or self._default_provider)
        prompt = apply_output_language(prompt, output_lang or self.output_lang)
        return await prov.describe_image(image_path, prompt, model)

    async def describe_frames(
        self,
        frames: list[str],
        prompt: str,
        output_lang: str = "",
        provider: str = "",
        model: str = "",
        on_progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[str]:
        """Describe multiple frames. Returns list of descriptions."""
        prov = self._provider_or_raise(provider or self._default_provider)
        prompt = apply_output_language(prompt, output_lang or self.output_lang)
        return await prov.describe_frames_batch(
            frames, prompt, model, on_progress=on_progress, is_cancelled=is_cancelled)

    async def describe_video_full(
        self,
        video_path: str,
        prompt: str,
        output_lang: str = "",
        provider: str = "",
        model: str = "",
        on_status: Callable[[str], None] | None = None,
        on_upload_progress: Callable[[float], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        chunk_seconds: int = 600,
        on_part: Callable[[int, int], None] | None = None,
        on_split_progress: Callable[[float], None] | None = None,
        transcript: list | None = None,
        preserve_resolution: bool = False,
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
        prompt = apply_output_language(prompt, output_lang or self.output_lang)
        return await fn(
            video_path, prompt, model,
            on_status=on_status,
            on_upload_progress=on_upload_progress,
            is_cancelled=is_cancelled,
            chunk_seconds=chunk_seconds,
            on_part=on_part,
            on_split_progress=on_split_progress,
            # Only providers that accept a transcript get one: Gemini
            # hears the audio itself and has no such parameter.
            **({"transcript": transcript}
               if transcript and "transcript" in
               inspect.signature(fn).parameters else {}),
            **({"preserve_resolution": True}
               if preserve_resolution and "preserve_resolution" in
               inspect.signature(fn).parameters else {}),
        )

    async def describe_video_frames_batch(
        self,
        frames: list[str],
        prompt: str,
        output_lang: str = "",
        provider: str = "",
        model: str = "",
        expected_times: list[float] | None = None,
        on_status: Callable[[str], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[tuple[float, str]]:
        """Fast one-shot mode: ALL frames in ONE request; the model
        reads the burned-in H:MM:SS stamps and returns event lines that
        are snapped onto the known extraction grid. Raises ValueError
        when the configured provider does not support this mode."""
        prov = self._provider_or_raise(provider or self._default_provider)
        fn = getattr(prov, "describe_video_frames_batch", None)
        if fn is None:
            raise ValueError(
                f"Provider '{prov.name}' does not support the one-shot "
                "batch mode. Use GLM, or switch back to frame mode.")
        prompt = apply_output_language(prompt, output_lang or self.output_lang)
        return await fn(
            frames, prompt, model,
            on_status=on_status,
            is_cancelled=is_cancelled,
            expected_times=expected_times,
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
