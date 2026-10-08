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


def provider_hears_audio(provider: str, model: str = "") -> bool:
    """True when this provider's video mode ingests the audio track.

    v1.8.1: per MODEL for OpenRouter ("glm"). GLM itself is deaf, but
    Qwen3.8-Omni-Flash, MiMo and Gemini behind the same key hear the
    soundtrack (probed 28 Sep 2026), so the provider alone cannot say.
    """
    provider = (provider or "").strip().lower()
    if provider in AUDIO_CAPABLE_PROVIDERS:
        return True
    if provider == "glm" and model:
        from .model_catalog import openrouter_model_hears_audio
        return openrouter_model_hears_audio(model)
    return False


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
                              chunk_seconds: int = 300,
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
    not a plan (pitfall 14). This gives arithmetic instead of
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


# v1.8.7: frame mode describes each still frame on its own, with the
# video preset. Measured (29 Sep 2026): GLM answered a single frame with
# ~41 words, markdown headings ("**Audio description**") and invented
# timestamps ("[0:00] ... [0:06]") in 51% of replies — all read aloud.
# FORMAT only, per pitfall 16: nothing here about WHAT to describe.
FRAME_FORMAT_SUFFIX = (
    "\n\nThis is ONE still frame from the video. Answer with one plain "
    "sentence of at most 12 words: no markdown, no headings, no "
    "timestamps, no lists.")

_MARKDOWN = re.compile(r"\*\*|__|^\s*#+\s*|^\s*[-*\u2022]\s+", re.M)
_HEADING_LINE = re.compile(r"^[ \t]*#+[^\n]*(?:\n|$)", re.M)
_STAMPS = re.compile(r"\[\s*\d{1,2}:\d{2}(?::\d{2})?\s*\]")
_HEADINGS = re.compile(r"^\s*(audio description|description)\b[^\n:]*[:\n]\s*",
                       re.I)


def clean_frame_text(text: str) -> str:
    """A frame reply as a line that can be spoken: no markdown, no
    headings, no timestamps the model made up for a single frame."""
    t = _STAMPS.sub(" ", text or "")
    # A markdown heading line ("## Scene") is a label, not part of the
    # sentence — stripping only its "#" read "Scene A girl climbs..."
    # aloud. Dropped whole, unless it is all the reply has.
    body = _HEADING_LINE.sub("", t)
    if body.strip():
        t = body
    # A bold heading ("**Audio description - Excel workbook (...)**") goes
    # whole, before the bold markers are stripped from the rest.
    t = re.sub(r"\*\*[^*]*(audio )?description[^*]*\*\*", " ", t, flags=re.I)
    t = _MARKDOWN.sub("", t)
    t = _HEADINGS.sub("", t.strip())
    t = re.sub(r"\s*\(no dialogue[^)]*\)", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip(" -:\u2014")


def finalize_frame_descriptions(frames, texts) -> list[tuple]:
    """(frame, cleaned text) pairs worth keeping: placeholders dropped,
    and a line identical to the previous one not said twice."""
    kept, last = [], ""
    for frame, text in zip(frames, texts):
        if is_placeholder_text(text):
            continue
        line = clean_frame_text(text)
        norm = re.sub(r"\W+", " ", line.lower()).strip()
        if not line or norm == last:
            continue
        last = norm
        kept.append((frame, line))
    return kept


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
HTTP_RETRY_BACKOFF_SECONDS = 5.0


class _TransientHTTPError(Exception):
    """A status worth another attempt (rate limit, overload)."""

    def __init__(self, message: str, wait: float | None = None):
        super().__init__(message)
        self.wait = wait


# v1.9.5: how long a 429 says to wait. Google puts it in the body
# ("retryDelay": "37s"); others send a Retry-After header in seconds.
# Waiting only 5 s then 15 s failed the Gemini agent on per-MINUTE
# limits (1 Oct 2026), which clear within the minute.
_RETRY_DELAY = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')
# Longer than this is a daily quota, not a minute's wait: stop at once
# and say so rather than hold the job for hours.
MAX_RETRY_WAIT = 65.0


# Google still says "retry in 53s" when the DAILY free quota is gone
# (seen 1 Oct 2026: GenerateRequestsPerDayPerProjectPerModel-FreeTier,
# 20 a day for gemini-3.8-flash). The quota id is the truth.
_DAILY_QUOTA = re.compile(r'"quotaId"\s*:\s*"([^"]*PerDay[^"]*)"')


def daily_quota(body: str) -> str:
    """The daily quota a 429 hit ("" if it was not a daily one)."""
    found = _DAILY_QUOTA.search(body or "")
    if found:
        return found.group(1)
    # OpenRouter: "Rate limit exceeded: free-models-per-day".
    found = re.search(r"[\w-]*per-day[\w-]*", body or "")
    return found.group(0) if found else ""


def _server_wait(body: str, retry_after: str | None) -> float | None:
    if daily_quota(body):
        return float("inf")
    found = _RETRY_DELAY.search(body or "")
    if found:
        return float(found.group(1))
    try:
        return float(retry_after) if retry_after else None
    except ValueError:
        return None


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
        # v1.9.6: the request itself is abandoned within 0.5 s of a
        # Cancel (Gemini generate could hold a job for 600 s).
        async def _once() -> dict:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method, url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    body = await resp.text()
                    if resp.status == 429 and daily_quota(body):
                        raise RuntimeError(
                            f"{label} HTTP 429: daily quota used up "
                            f"({daily_quota(body)}). It resets at midnight "
                            "Pacific time; a paid tier raises it.")
                    if resp.status in _TRANSIENT_STATUSES:
                        raise _TransientHTTPError(
                            f"HTTP {resp.status}: {body[:120]}",
                            _server_wait(body, resp.headers.get("Retry-After"))
                            if resp.status == 429 else None)
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

        try:
            return await _run_cancellable(_once(), is_cancelled)
        except (_TransientHTTPError, aiohttp.ClientError,
                asyncio.TimeoutError, OSError) as e:
            last = e
            if attempt >= HTTP_RETRIES:
                break
            # v1.8.2: 5 s then 15 s (was 3 s, 6 s). Gemini's "high demand"
            # 503 outlasted the old waits on 29 Sep 2026 and whole jobs
            # failed; the longer gap gives a busy service time to recover.
            wait = HTTP_RETRY_BACKOFF_SECONDS * (3 ** (attempt - 1))
            asked = getattr(e, "wait", None)
            if asked is not None:
                if asked > MAX_RETRY_WAIT:
                    break           # a daily quota: waiting will not help
                wait = max(wait, asked + 1.0)
            logger.warning("%s: %s on attempt %d/%d; retrying in %.0fs",
                           label, str(e) or type(e).__name__,
                           attempt, HTTP_RETRIES, wait)
            await _sleep_cancellable(wait, is_cancelled)
    raise RuntimeError(
        f"{label} request failed after {HTTP_RETRIES} attempts: "
        f"{str(last) or type(last).__name__}")


def is_daily_quota_error(message: str) -> bool:
    """True when a provider's DAILY quota is used up (v1.9.5,
    `_http_json`). Waiting minutes does not help, so the user is told
    when it resets instead of "busy, try again"."""
    return "daily quota used up" in (message or "").lower()


_URL = re.compile(r"\b(?:https?|wss?)://\S+")
_USER_ID = re.compile(r"user_[A-Za-z0-9]{6,}")


def short_error(message: str, limit: int = 160) -> str:
    """A raw error cut to something a person can hear: no JSON body, no
    URL (they can carry tokens), no OpenRouter user id."""
    text = str(message or "").strip()
    if "{" in text:
        text = text[:text.index("{")].rstrip(" :")
    text = _URL.sub("<url>", text)
    text = _USER_ID.sub("<id>", text)
    return text[:limit] or "?"


def user_error_text(message: str) -> str:
    """The words a person hears for a failure (v1.9.6: ONE translator,
    used wherever an error reaches the user). Known kinds are explained
    with what to do, in the app language; anything else is shortened by
    short_error() so no JSON, URL or account id is read out."""
    from ..i18n.strings import t
    text = str(message or "")
    low = text.lower()
    if text == "cancelled":
        return t("error.cancelled")
    if is_daily_quota_error(text):
        return t("error.ai_daily_quota")
    if is_busy_error(text):
        return t("error.ai_busy")
    if ("http 413" in low or "payload too large" in low
            or "payload_too_large" in low):
        return t("error.ai_too_large")
    if re.search(r"\bhttp (401|403)\b", low) and "youtube" not in low:
        return t("error.ai_key")
    if re.search(r"\bhttp 402\b", low) or "insufficient credit" in low:
        return t("error.ai_credit")
    # Before the network check: "ffmpeg timed out" is not a network fault.
    if any(k in low for k in ("video split failed", "video compression failed",
                              "video preparation failed", "ffmpeg exit code",
                              "ffmpeg timed out", "ffmpeg failed")):
        return t("error.video_prepare", detail=short_error(text, 120))
    if any(k in low for k in ("cannot connect to host", "getaddrinfo",
                              "name or service not known", "connection reset",
                              "connection aborted", "server disconnected",
                              "timed out", "timeouterror", "winerror 10060",
                              "winerror 10061", "winerror 1236", "winerror 64")):
        return t("error.ai_network")
    return t("error.ai_generic", detail=short_error(text))


def is_busy_error(message: str) -> bool:
    """True for "the service is overloaded, try later" failures (429 /
    503 / "high demand"), which the user can act on by waiting or by
    picking another model -- unlike a bad key or a broken file."""
    text = (message or "").lower()
    return ("http 503" in text or "http 429" in text
            or "high demand" in text or "overloaded" in text
            or "rate limit" in text)


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

    # Providers that take a whole video file set this (and override
    # ask_about_video); the others are sent still pictures.
    watches_video: bool = False

    async def ask_about_video(
        self, video_path: str, question: str, model: str = ""
    ) -> str:
        """One plain question about a whole video, through the same upload
        path the app uses for descriptions ("Test this model", v1.9.2)."""
        raise NotImplementedError(f"{self.name} does not take a video")

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
        # Recommended (phase 36, 8 Oct 2026): wrong 19.9% -> 11.7% against
        # 3.1 Flash-Lite, same coverage and speed (contracts/measure-gemini-*).
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.8-flash",
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
                desc = await _run_cancellable(
                    self.describe_image(frame, prompt, model), is_cancelled)
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
        """The upload, tried up to HTTP_RETRIES times (v1.9.6).

        It had no retry at all: one dropped connection ended the job with
        a raw "Cannot connect to host ..." (owner's report, 1 Oct 2026).
        A retry starts a new upload session; Cancel is honoured within
        0.5 s, also in the middle of an 8 MiB chunk.
        """
        last: Exception | None = None
        for attempt in range(1, HTTP_RETRIES + 1):
            try:
                return await _run_cancellable(
                    self._upload_video_once(video_path, on_progress,
                                            is_cancelled), is_cancelled)
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                if isinstance(e, FileNotFoundError):
                    raise
                last = e
            except RuntimeError as e:
                if not re.search(r"HTTP (429|5\d\d)", str(e)):
                    raise
                last = e
            if attempt < HTTP_RETRIES:
                wait = HTTP_RETRY_BACKOFF_SECONDS * (3 ** (attempt - 1))
                logger.warning("Gemini upload: %s on attempt %d/%d; retrying "
                               "in %.0fs", last, attempt, HTTP_RETRIES, wait)
                await _sleep_cancellable(wait, is_cancelled)
        raise RuntimeError(f"Gemini upload failed after {HTTP_RETRIES} "
                           f"attempts: {last}")

    async def _upload_video_once(
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
                        raise RuntimeError("cancelled")
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
                raise RuntimeError("cancelled")
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
        config = {"maxOutputTokens": 8192}
        if self.TEMPERATURE is not None:
            config["temperature"] = self.TEMPERATURE
        thinking = (self.THINKING if self.THINKING is not None
                    else self.THINKING_BY_MODEL.get(model))
        if thinking:
            config["thinkingConfig"] = dict(thinking)
        payload = {
            "contents": [{"parts": [
                {"text": prompt},
                {"file_data": {"mime_type": mime, "file_uri": uri}},
            ]}],
            "generationConfig": config,
        }
        try:
            data = await _http_json("POST", url, label="Gemini",
                                    headers=self._auth_headers(),
                                    payload=payload, timeout=600,
                                    is_cancelled=is_cancelled)
        except RuntimeError as e:
            # Thinking levels differ per model and a level a model does
            # not take is HTTP 400 (phase 22: 3.8 Flash refuses
            # "minimal"). Never lose the job to it: once more without.
            if not (thinking and "400" in str(e) and "thinking" in str(e).lower()):
                raise
            logger.warning("Gemini refused thinking %s for %s; retrying "
                           "with the model's default", thinking, model)
            config.pop("thinkingConfig", None)
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
        chunk_seconds: int = 300,
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

    watches_video = True
    # Whole-video temperature (v1.9.2, pitfall 83). Measured on Gemini
    # 3.1 Flash-Lite, 4 clips x 3 runs, GLM judge: wrong 14.7% -> 14.2%
    # (no accuracy change), run-to-run spread 23 -> 12. Owner's choice.
    TEMPERATURE: float | None = 0.0
    # Whole-video thinking, PER MODEL (v1.9.4, pitfall 86). Measured
    # 4 clips x 3 runs, GLM judge, Gemini 3.1 Flash-Lite: the default
    # (no thinking at all) 15.8% wrong, low 12.7%, MEDIUM 9.1% (and the
    # fastest, 36 s a clip), high 10.7%. Models not listed keep Google's
    # default: they differ (3.8 Flash already thinks by default and
    # refuses "minimal") and were not measured.
    THINKING_BY_MODEL: dict[str, dict] = {
        "gemini-3.1-flash-lite": {"thinkingLevel": "medium"},
    }
    # Override for tests and tools/model_bench.py: None = the table above,
    # {} = send no thinking setting at all.
    THINKING: dict | None = None

    async def ask_about_video(
        self, video_path: str, question: str, model: str = ""
    ) -> str:
        if not self.api_key:
            raise ValueError("Gemini API key not configured")
        uri = await self._upload_video(video_path)
        await self._wait_video_ready(uri)
        return await self._generate_with_video(
            uri, self._video_mime(video_path), question,
            model or self.models[0])

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
                desc = await _run_cancellable(
                    self.describe_image(frame, prompt, model), is_cancelled)
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
                desc = await _run_cancellable(
                    self.describe_image(frame, prompt, model), is_cancelled)
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
        chunk_seconds: int = 300,
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

    watches_video = True

    async def ask_about_video(
        self, video_path: str, question: str, model: str = ""
    ) -> str:
        if not self.api_key:
            raise ValueError("MiniMax API key not configured")
        file_id = await self._upload_video(video_path)
        payload = {
            "model": model or self.models[0],
            "max_completion_tokens": 2048,
            "messages": [{"role": "user", "content": [
                {"type": "video_url",
                 "video_url": {"url": f"mm_file://{file_id}"}},
                {"type": "text", "text": question}]}],
        }
        return _strip_think(await self._chat(payload, timeout=300))

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
                        raise RuntimeError("cancelled")
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
    # Share of a part's progress bar given to the upload; the rest is
    # the model's wait. Measured on Sintel: the upload was well under a
    # tenth of each part's time.
    UPLOAD_SHARE = 0.1

    # Bytes handed to the socket per step while streaming a request.
    _SEND_CHUNK = 256 * 1024

    async def _chat(self, payload: dict, timeout: float,
                    on_sent: Callable[[float], None] | None = None) -> str:
        """POST a chat request; with on_sent, report the share uploaded.

        v1.8.4: a video part is ~40 MB of base64 in one JSON body, and
        json=payload sends it with no way to tell how far it got - the
        bar sat at 0% for the whole upload. The body is now streamed in
        chunks with an explicit Content-Length (without it aiohttp falls
        back to chunked transfer-encoding; see MiniMax _upload_video).
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = json.dumps(payload).encode("utf-8") if on_sent else None
        if body is not None:
            headers["Content-Length"] = str(len(body))
        chunk = self._SEND_CHUNK

        async def stream():
            for start in range(0, len(body), chunk):
                yield body[start:start + chunk]
                try:
                    on_sent(min(1.0, (start + chunk) / len(body)))
                except Exception:
                    logger.debug("on_sent raised", exc_info=True)

        last_error: Exception | None = None
        for attempt in range(1, self._NETWORK_RETRIES + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    send = ({"data": stream()} if body is not None
                            else {"json": payload})
                    async with session.post(
                        url, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                        **send,
                    ) as resp:
                        if resp.status in (429, 500, 502, 503, 504):
                            # Provider-side wobble: worth another go.
                            body = await resp.text()
                            # v1.9.6: the same 429 rules as _http_json —
                            # a daily quota ends at once and says so, a
                            # per-minute one waits as long as asked.
                            if resp.status == 429 and daily_quota(body):
                                raise RuntimeError(
                                    f"GLM HTTP 429: daily quota used up "
                                    f"({daily_quota(body)}). It resets at "
                                    "midnight UTC; adding credit raises it.")
                            raise _TransientHTTPError(
                                f"HTTP {resp.status}: {body[:120]}",
                                _server_wait(body, resp.headers.get("Retry-After"))
                                if resp.status == 429 else None)
                        if resp.status != 200:
                            # 4xx (bad key, no credit, payload too big):
                            # retrying cannot help and would burn time.
                            body = await resp.text()
                            raise RuntimeError(
                                f"GLM HTTP {resp.status}: {body[:200]}")
                        # Decoded by hand: resp.json() on a wrong content
                        # type raises with the request URL in its text.
                        raw = await resp.text()
                        try:
                            data = json.loads(raw)
                        except ValueError:
                            raise RuntimeError(
                                f"GLM: reply was not JSON: {raw[:200]}") from None
                        if "error" in data:
                            err = data["error"]
                            code = err.get("code") if isinstance(err, dict) else None
                            if code in (429, 500, 502, 503, 504):
                                # v1.8.6: OpenRouter reports an upstream
                                # timeout INSIDE a 200 reply. It used to
                                # end the whole job — a 504 after 15
                                # minutes threw away every finished part
                                # (29 Sep 2026). Busy/timeout: retry.
                                raise aiohttp.ClientError(
                                    f"HTTP {code} in reply: {str(err)[:120]}")
                            raise RuntimeError(f"GLM API error: {err}")
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
            except (_TransientHTTPError, aiohttp.ClientError,
                    asyncio.TimeoutError, OSError) as e:
                last_error = e
                if attempt >= self._NETWORK_RETRIES:
                    break
                wait = self._RETRY_BACKOFF_SECONDS * attempt
                asked = getattr(e, "wait", None)
                if asked is not None:
                    if asked > MAX_RETRY_WAIT:
                        break       # a daily limit: waiting will not help
                    wait = max(wait, asked + 1.0)
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
            # answer; 1024 truncated/emptied replies (pitfall 7).
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
    # v1.9.1: temperature 0 for whole-video requests. Measured (phase
    # 19.B1, GLM 5.3 Flash, 4 clips x 3 runs, independent Gemini judge):
    # server default 51 correct / 24.2% wrong, temperature 0 83 correct /
    # 16.8% wrong, and half the run-to-run spread (one news run had 3
    # descriptions against 15). None = leave it to the server.
    TEMPERATURE: float | None = 0.0
    MAX_VIDEO_BYTES = 50 * 1024 * 1024
    COMPRESS_TARGET_BYTES = 40 * 1024 * 1024
    # v1.8.6: OpenRouter passes a request on to the model's OWN provider,
    # and those limits differ. Google AI Studio (every google/* model)
    # refuses a body over 20,000,000 bytes: a 10-minute Sintel part,
    # 29.6 MB once base64-encoded, failed with HTTP 413 (29 Sep 2026).
    # Limits are on the REQUEST BODY; base64 makes the video 4/3 larger.
    BODY_LIMITS = (("google/", 20_000_000),)

    def _base_limits(self) -> tuple[int, int]:
        """The limits this provider started with — the class values, or
        whatever was set on the instance before its first job."""
        current = (self.MAX_VIDEO_BYTES, self.COMPRESS_TARGET_BYTES)
        if current != self.__dict__.get("_limits_we_set"):
            # Not values we lowered: someone set them (or the class
            # default is still in place) — that is the starting point.
            self.__dict__["_base_limits_pair"] = current
        return self.__dict__["_base_limits_pair"]

    def _apply_limits(self, max_bytes: int, compress_bytes: int) -> None:
        self.MAX_VIDEO_BYTES, self.COMPRESS_TARGET_BYTES = max_bytes, compress_bytes
        self.__dict__["_limits_we_set"] = (max_bytes, compress_bytes)

    def _set_upload_limits(self, body_limit: int) -> None:
        """Video size limits that keep the base64 request under body_limit.
        Only ever LOWERS them."""
        base_max, base_compress = self._base_limits()
        raw = int(body_limit * 0.72)          # 3/4 for base64, less the prompt
        self._apply_limits(min(base_max, raw), min(base_compress, int(raw * 0.8)))

    def _limits_for(self, model: str) -> None:
        # Back to the starting limits first: one Gemini job must not
        # shrink the next GLM job on the same provider.
        self._apply_limits(*self._base_limits())
        for prefix, limit in self.BODY_LIMITS:
            if (model or "").startswith(prefix):
                self._set_upload_limits(limit)

    @staticmethod
    def is_too_large_error(error) -> bool:
        """An HTTP 413 refusal, whether or not it names a limit."""
        text = str(error).lower()
        return ("http 413" in text or "payload too large" in text
                or "payload_too_large" in text or '"code":413' in text)

    @staticmethod
    def body_limit_from_error(error) -> int:
        """The byte limit a 413 names ("... exceeds the 20000000 byte
        limit ..."), or 0. Lets an unknown provider's limit be learned
        from its first refusal instead of failing the job."""
        text = str(error)
        if "413" not in text and "payload_too_large" not in text:
            return 0
        m = re.search(r"(\d{6,})\s*byte limit", text)
        if m:
            return int(m.group(1))
        # OpenRouter routes one model to several upstreams with DIFFERENT
        # limits: a GLM part passed at 29 MB, the next was refused with
        # "Request body exceeds the 8 MiB limit" (29 Sep 2026).
        m = re.search(r"(\d+(?:\.\d+)?)\s*(MiB|MB)\s*limit", text)
        if m:
            unit = 1024 * 1024 if m.group(2) == "MiB" else 1_000_000
            return int(float(m.group(1)) * unit)
        return 0

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
        chunk_seconds: int = 300,
        on_part: Callable[[int, int], None] | None = None,
        on_split_progress: Callable[[float], None] | None = None,
        transcript: list | None = None,
        preserve_resolution: bool = False,
        on_eta: Callable[[float, float | None], None] | None = None,
        cast: list | None = None,
        on_cast: Callable[[list], None] | None = None,
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
        self._limits_for(model or self.models[0])
        # v1.8.1: a model that hears (Qwen/MiMo/Gemini via OpenRouter)
        # keeps the soundtrack when the upload has to be compressed.
        self._keep_audio = provider_hears_audio("glm", model or self.models[0])
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
                    codec = self._video_codec(path)
                    if codec and codec not in self._SAFE_CODECS:
                        # v1.8.6: a small local AV1/HEVC/VP9 file went up
                        # as it was, and some models cannot open it
                        # (MiMo, Nemotron: "Failed to load video").
                        # Re-encode to H.264 the same way a big file is.
                        logger.info("Video codec %s: re-encoding to H.264 "
                                    "for upload", codec)
                        parts = []
                        if preserve_resolution and duration > 0:
                            if on_status:
                                on_status("splitting")
                            starts, parts = self.split_video_for_upload(
                                path, int(duration) + 2,
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
            # v2.1.0: the cast travels through EVERY part (characters.py);
            # the last six lines alone let part 3 rename part 1's people.
            from . import characters as _ch
            # None = no cast work at all (the engine's CHARACTERS off).
            cast_now = list(cast) if cast is not None else None
            # v1.8.4: one bar for the whole job. Splitting is the first
            # 10%, each part's share of the rest follows its length.
            from . import timing_store
            weights = ([max(1.0, x) for x in part_lens]
                       if part_lens and all(x > 0 for x in part_lens)
                       else [1.0] * total)
            ratio = timing_store.ratio(f"{self.name}:{model or self.models[0]}")

            def part_progress(i: int):
                def cb(fraction: float, eta: float | None) -> None:
                    done = sum(weights[:i]) + weights[i] * fraction
                    overall = 10.0 + 90.0 * done / sum(weights)
                    later = sum(timing_store.OVERHEAD_SECONDS + x * ratio
                                for x in part_lens[i + 1:])
                    if eta is not None and eta >= 0:
                        eta += later
                    try:
                        on_eta(overall, eta)
                    except Exception:
                        logger.debug("on_eta raised", exc_info=True)
                return cb

            for i, (part, offset) in enumerate(zip(parts, starts)):
                if is_cancelled and is_cancelled():
                    raise RuntimeError("cancelled")
                if on_part:
                    on_part(i + 1, total)
                part_len = part_lens[i] if i < len(part_lens) else 0.0
                part_prompt = prompt + ("\n" + _ch.cast_block(cast_now)
                                        if cast_now else "")
                # v1.5.3: pass a short summary of the previous part so
                # the model keeps its bearings (no "the video starts
                # with" at minute 20) and keeps one name per character.
                try:
                    pairs = await self._describe_one_part(
                        part, part_prompt, model, on_status=on_status,
                        is_cancelled=is_cancelled, offset=offset,
                        part_index=i + 1, part_total=total,
                        prev_summary=prev_summary, transcript=transcript,
                        part_seconds=part_len,
                        on_part_progress=part_progress(i) if on_eta else None)
                except RuntimeError as e:
                    # v1.8.6: a provider we have no limit for refused the
                    # size. Learn its limit from the refusal and send the
                    # part again, compressed to fit. v1.9.6: an upstream
                    # that names NO limit ("Payload Too Large", Alibaba
                    # behind OpenRouter, 1 Oct 2026) gets a part 40%
                    # smaller than the refused one, up to three times.
                    pairs, err = None, e
                    for _attempt in range(3):
                        limit = self.body_limit_from_error(err)
                        if not limit and self.is_too_large_error(err):
                            limit = int(getattr(self, "_last_body_bytes", 0) * 0.6)
                        if not limit or self.MAX_VIDEO_BYTES <= int(limit * 0.72):
                            raise err  # noqa: B904 - the provider's own error, as it came
                        logger.warning("part %d/%d: provider limit is %d bytes; "
                                       "compressing to fit and retrying",
                                       i + 1, total, limit)
                        self._set_upload_limits(limit)
                        try:
                            pairs = await self._describe_one_part(
                                part, part_prompt, model, on_status=on_status,
                                is_cancelled=is_cancelled, offset=offset,
                                part_index=i + 1, part_total=total,
                                prev_summary=prev_summary, transcript=transcript,
                                part_seconds=part_len,
                                on_part_progress=part_progress(i) if on_eta else None)
                            break
                        except RuntimeError as again:
                            err = again
                    else:
                        raise err
                if not pairs:
                    # v1.5.0: a part that parses to zero cues means the
                    # rest of the video is silently dropped. Retry once
                    # before giving up on this part.
                    logger.warning(
                        "part %d/%d returned no cues; retrying once",
                        i + 1, total)
                    pairs = await self._describe_one_part(
                        part, part_prompt, model, on_status=on_status,
                        is_cancelled=is_cancelled, offset=offset,
                        part_index=i + 1, part_total=total,
                        prev_summary=prev_summary, transcript=transcript,
                        part_seconds=part_len)
                if pairs:
                    prev_summary = "; ".join(
                        txt for _, txt in pairs[-6:])
                if pairs and cast_now is not None:
                    # v2.1.0: one text-only request brings the cast up to
                    # date; a failure keeps the cast as it was.
                    spoken_part = ""
                    if transcript:
                        spoken_part = build_transcript_block(
                            transcript, start=offset,
                            end=(offset + part_len) if part_len else None,
                            offset=offset,
                            words_per_second=self.words_per_second)
                    cast_now = await _ch.update_cast(
                        lambda q: _run_cancellable(
                            self._ask_capped(q, model), is_cancelled),
                        cast_now, [txt for _, txt in pairs], spoken_part)
                    if on_cast:
                        try:
                            on_cast(list(cast_now))
                        except Exception:
                            logger.debug("on_cast raised", exc_info=True)
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
        on_part_progress: Callable[[float, float | None], None] | None = None,
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
        # v1.9.6: what was sent, so a 413 that names no limit can still
        # be answered with a smaller part (see _describe_parts).
        self._last_body_bytes = len(b64)
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
            **({"temperature": self.TEMPERATURE}
               if self.TEMPERATURE is not None else {}),
            "max_tokens": 16000,
            # v1.6.3: CAP THE THINKING. Measured on a real 45-second
            # clip with the `foreign` preset: the model spent 15,995 of
            # its 16,000 completion tokens on internal reasoning, leaving
            # FIVE for the answer, and returned empty content with
            # finish_reason "length". The app reported "no descriptions"
            # with no reason given. With the cap: 17 reasoning tokens,
            # finish_reason "stop", a full correct answer.
            #
            # This is pitfall 7 one level up — raising
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
        # v1.8.4: the part's progress is its upload (the first
        # UPLOAD_SHARE, measured in bytes) and then the model's silent
        # wait, estimated from what this model took before
        # (core/timing_store). Never reported as finished on a guess.
        import time as _time
        from . import timing_store
        timing_key = f"{self.name}:{model or self.models[0]}"
        media = part_seconds or 0.0
        expected = timing_store.expected_seconds(timing_key, media)
        sent_at: list[float] = []

        def report(fraction: float, eta: float | None) -> None:
            if on_part_progress:
                try:
                    on_part_progress(fraction, eta)
                except Exception:
                    logger.debug("on_part_progress raised", exc_info=True)

        def on_sent(share: float) -> None:
            report(self.UPLOAD_SHARE * share, None)
            if share >= 1.0 and not sent_at:
                sent_at.append(_time.monotonic())
                if on_status:
                    on_status("waiting")

        async def tick_wait() -> None:
            while True:
                await asyncio.sleep(1.0)
                if not sent_at:
                    continue
                waited = _time.monotonic() - sent_at[0]
                # eta: seconds left; None = past the estimate ("taking
                # longer than usual"); -1 = no estimate (length unknown).
                if expected > 0:
                    share = min(0.95, waited / expected)
                    eta = expected - waited if waited < expected else None
                else:
                    share, eta = 0.0, -1.0
                report(self.UPLOAD_SHARE + (1 - self.UPLOAD_SHARE) * share,
                       eta)

        ticker = asyncio.ensure_future(tick_wait()) if on_part_progress else None
        try:
            # v1.7.5: Cancel is honoured DURING the request, not only
            # between requests — one part may take 30 minutes (and GLM
            # retries a timeout), so Cancel used to wait up to ~90 minutes.
            text = await _run_cancellable(
                self._chat(payload, timeout=1800.0,
                           **({"on_sent": on_sent} if on_part_progress
                              else {})),
                is_cancelled)
        finally:
            if ticker is not None:
                ticker.cancel()
        if sent_at:
            timing_store.record(timing_key, media,
                                _time.monotonic() - sent_at[0])
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
            running = proc.poll() is None
            if running:
                proc.kill()
            else:
                # v1.9.6: ffmpeg has ended, so its stderr is at EOF; let the
                # reader finish BEFORE closing, or the reason is lost (the
                # same race as the empty "video split failed: ").
                t.join(timeout=2.0)
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
        if getattr(self, "_keep_audio", False):
            # v1.8.1: a copy made for a deaf model has no soundtrack, so
            # it must never be served to a model that hears.
            recipe += ":audio"
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
        duration = 1.0
        try:
            _ret, stderr_tail = self._run_ffmpeg_cancellable(
                [self._ffmpeg(), "-hide_banner", "-nostdin", "-i",
                 str(path), "-f", "null", "-"],
                is_cancelled, 600)
            m = None
            for m in re.finditer(  # noqa: B007 - keeps the LAST match
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
            # v1.8.1: only a model that cannot hear loses the soundtrack;
            # Qwen/MiMo/Gemini through OpenRouter are given it.
            *(["-c:a", "aac", "-b:a", "48k", "-ac", "1"]
              if getattr(self, "_keep_audio", False) else ["-an"]),
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
        """Return the video duration in seconds.

        v1.8.2: container metadata first (ffprobe), longest of the file
        and its streams. Decoding and reading ffmpeg's last "time=" was
        the only method, and it depends on the ffmpeg build: for a clip
        whose AUDIO ends early (60 s of video, 9.25 s of sound) one build
        reported 60 s, another 9.25 s — and every cue after 9.2 s was
        then dropped as "past the end". Decoding stays as the fallback,
        limited to the video stream, for files without a duration.

        Cancellable via is_cancelled (v1.5.4): the decode pass can run
        for minutes on long videos.
        """
        probed = self._ffprobe_duration(path)
        if probed > 0:
            return probed
        try:
            _ret, stderr_tail = self._run_ffmpeg_cancellable(
                [self._ffmpeg(), "-hide_banner", "-nostdin", "-i",
                 str(path), "-map", "0:v:0?", "-f", "null", "-"],
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

    @staticmethod
    def _video_codec(path: Path) -> str:
        """Codec of the first video stream ("h264", "av1", ...), or ""."""
        import subprocess as _sp
        from .tools import find_tool
        try:
            out = _sp.run(
                [find_tool("ffprobe"), "-v", "error", "-select_streams",
                 "v:0", "-show_entries", "stream=codec_name", "-of",
                 "default=nw=1:nk=1", str(path)],
                capture_output=True, text=True, timeout=60)
            return (out.stdout or "").strip().lower()
        except Exception:
            return ""

    # Codecs every OpenRouter video model has been seen to open. MiMo and
    # Nemotron answer "Failed to load video" for AV1 (pitfall 68).
    _SAFE_CODECS = ("h264",)

    @staticmethod
    def _ffprobe_duration(path: Path) -> float:
        """Longest of the container's and the streams' declared
        durations, or 0.0 when none is declared (or ffprobe is absent)."""
        import subprocess as _sp
        from .tools import find_tool
        try:
            out = _sp.run(
                [find_tool("ffprobe"), "-v", "error", "-show_entries",
                 "format=duration:stream=codec_type,duration", "-of", "json",
                 str(path)], capture_output=True, text=True, timeout=60)
            data = json.loads(out.stdout or "{}")
        except Exception:
            return 0.0
        values = [(data.get("format") or {}).get("duration")]
        values += [s.get("duration") for s in data.get("streams") or []
                   if s.get("codec_type") == "video"]
        best = 0.0
        for v in values:
            try:
                best = max(best, float(v))
            except (TypeError, ValueError):
                continue
        return best

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

        drain = _threading.Thread(target=_drain_err, daemon=True)
        drain.start()
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
            # v1.9.6: read the reason only after the reader has finished;
            # the owner got "video split failed: " with nothing after it.
            drain.join(timeout=5)
            tail = b"".join(stderr_tail).decode("utf-8", "replace").strip()[-300:]
            raise RuntimeError(
                f"video split failed (ffmpeg exit code {proc.returncode})"
                + (f": {tail}" if tail else ""))
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
                desc = await _run_cancellable(
                    self.describe_image(frame, prompt, model), is_cancelled)
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
        # answer; 1024 truncated/emptied replies (pitfall 7).
        payload = {"model": model, "max_tokens": 6000, "messages": messages}
        return _strip_think(await self._chat(payload, timeout=120))

    async def _ask_capped(self, question: str, model: str = "") -> str:
        """A text request with the thinking capped as for descriptions.
        The cast update through ask_text came back EMPTY once (5 Oct
        2026): 6,358 reasoning tokens, no answer (pitfall 7)."""
        payload = {"model": model or self.models[0], "max_tokens": 4000,
                   "reasoning": {"max_tokens": self._REASONING_BUDGET},
                   "messages": [{"role": "user", "content": question}]}
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
    # v1.8.1: filtered — no ":batch", routers or aliases (see
    # core/model_catalog.py for what each of those did when tested).
    from .model_catalog import parse_catalog
    return sorted(row["id"] for row in parse_catalog(data))


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
                desc = await _run_cancellable(
                    self.describe_image(frame, prompt, model), is_cancelled)
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
    # v2.1.0: name rules + cast in full-video prompts. False = the prompt
    # as before (tools/model_bench.py measures both).
    CHARACTERS = True
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
        self._models: dict[str, str] = {}   # chosen in Settings, per provider
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
        # v1.8.8: remember the model chosen in Settings. It was logged and
        # then dropped for every provider but "custom", so each call went
        # out with model="" and the provider used its FIRST built-in model:
        # choosing Gemini 3.1 Flash-Lite ("Recommended") still ran GLM.
        self._models[name] = model or ""
        logger.info("AI provider set: %s (model=%s)", name, model or "default")

    def _model_for(self, provider: str, model: str) -> str:
        """The model a call should use: the one passed, else the one
        chosen in Settings for that provider, else "" (provider default)."""
        if model:
            return model
        name = provider or self._default_provider
        return getattr(self, "_models", {}).get(name, "")

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
        model = self._model_for(provider, model)
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
        model = self._model_for(provider, model)
        prompt = apply_output_language(prompt, output_lang or self.output_lang)
        return await prov.describe_image(image_path, prompt, model)

    def watches_video(self, provider: str = "") -> bool:
        """Does this provider take a whole video (else still pictures)?"""
        prov = self._provider_or_raise(provider or self._default_provider)
        return bool(getattr(prov, "watches_video", False))

    async def ask_about_video(self, video_path: str, question: str,
                              provider: str = "", model: str = "") -> str:
        prov = self._provider_or_raise(provider or self._default_provider)
        model = self._model_for(provider, model)
        return await prov.ask_about_video(video_path, question, model)

    async def look(self, image_path: str, prompt: str, provider: str = "",
                   model: str = "") -> str:
        """Ask about an image WITHOUT the description-language wrapper:
        for the app's own checks (core/review.py), which want JSON back."""
        prov = self._provider_or_raise(provider or self._default_provider)
        model = self._model_for(provider, model)
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
        model = self._model_for(provider, model)
        prompt = apply_output_language(prompt, output_lang or self.output_lang)
        prompt += FRAME_FORMAT_SUFFIX
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
        chunk_seconds: int = 300,
        on_part: Callable[[int, int], None] | None = None,
        on_split_progress: Callable[[float], None] | None = None,
        transcript: list | None = None,
        preserve_resolution: bool = False,
        on_eta: Callable[[float, float | None], None] | None = None,
        cast: list | None = None,
        on_cast: Callable[[list], None] | None = None,
    ) -> list[tuple[float, str]]:
        """Watch the WHOLE video (Gemini native video understanding).

        Returns (seconds, description) pairs parsed from Gemini's
        timestamped output. Raises ValueError when the configured
        provider does not support full-video mode.
        """
        prov = self._provider_or_raise(provider or self._default_provider)
        model = self._model_for(provider, model)
        fn = getattr(prov, "describe_video_full", None)
        if fn is None:
            raise ValueError(
                f"Provider '{prov.name}' does not support full-video mode. "
                "Use Gemini, or switch back to frame mode.")
        prompt = apply_output_language(prompt, output_lang or self.output_lang)
        # v2.1.0: one name per person (core/characters.py). A provider
        # that splits the video carries the cast from part to part
        # itself; one that watches it whole gets the known cast here.
        carries = "cast" in inspect.signature(fn).parameters
        if self.CHARACTERS:
            from .characters import CHARACTER_RULES, cast_block
            prompt = prompt + "\n" + CHARACTER_RULES
            if cast and not carries:
                prompt += "\n" + cast_block(cast)
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
            # v1.8.4: overall percentage + time left, where the provider
            # can measure it (GLM/OpenRouter).
            **({"on_eta": on_eta}
               if on_eta and "on_eta" in
               inspect.signature(fn).parameters else {}),
            **({"cast": list(cast or []), "on_cast": on_cast}
               if carries and self.CHARACTERS else {}),
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
        model = self._model_for(provider, model)
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
        model = self._model_for(provider, model)
        return await prov.ask_about_scene(image_path, question, model)
