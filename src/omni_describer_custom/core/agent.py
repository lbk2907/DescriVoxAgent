"""The Player agent: looks at the video, proposes fixes, never writes.

Designed with the owner (29-30 Sep 2026, memory agent-coeditor-design):
the agent lives in the Player (F2), can see the frames, read the
descriptions and transcript, find gaps, search, seek, remember character
names — and can change NOTHING. Every change is a proposal the person
accepts or rejects. It never downloads, never touches Settings, never
deletes files, never writes an external SRT.

Measured before it was built (tools/agent_bench.py, phase A):
  - every candidate model used real tool calls, looked before proposing
    and gave valid arguments (32/32 runs);
  - without "change only what is CLEARLY wrong" three models rewrote a
    correct description every time — so the system prompt says it;
  - Gemini 3.8 sometimes looks until the turn limit and never answers —
    so at the limit the agent is made to answer without tools.

OpenRouter (OpenAI-style tool calls) only, for now. Images go back as a
user message after the tool message: most models cannot take an image
inside a tool result.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_TURNS = 10
COST_CAP = 0.02          # dollars per question before asking "continue?"
MAX_WORDS = 12           # the app's audio-description rule
PROPOSAL_WORD_LIMIT = 20  # hard refusal above this
ACTIONS = ("keep", "move", "edit", "remove", "add")
ZOOM_AREAS = ("top-left", "top-right", "bottom-left", "bottom-right",
              "centre", "center")

SYSTEM = (
    "You help a blind person improve the audio descriptions of a video "
    "they are watching in a player. You can only change descriptions by "
    "calling propose_change; the person approves every change. ALWAYS "
    "look at the frames (look_at, look_between, zoom or search_video) "
    "before proposing anything. Keep description text to 12 words or "
    "fewer, present tense, only what is visible, never what can be heard. "
    "Use check_rules before proposing new or edited text. Only propose a "
    "change when a description is CLEARLY wrong about what is visible, or "
    "placed at a clearly different moment. Different wording, a more "
    "precise word, or a detail one frame cannot confirm is NOT a reason. "
    "Before deciding, look at several moments around it, not a single "
    "frame. Use the character names you have been told (characters). "
    "When you are done, answer in one to three short sentences, in "
    "{language}.")

TOOLS: list[dict] = [
    {"name": "current_position",
     "description": "The player's current position in seconds.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "read_descriptions",
     "description": "Descriptions between two times, each with its index.",
     "parameters": {"type": "object", "properties": {
         "start": {"type": "number"}, "end": {"type": "number"}},
         "required": ["start", "end"]}},
    {"name": "search_descriptions",
     "description": "Descriptions containing some words.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string"}}, "required": ["query"]}},
    {"name": "look_at",
     "description": "See the video frame at a time (seconds).",
     "parameters": {"type": "object", "properties": {
         "seconds": {"type": "number"}}, "required": ["seconds"]}},
    {"name": "look_between",
     "description": "See six frames spread between two times, each "
                    "labelled with its time.",
     "parameters": {"type": "object", "properties": {
         "start": {"type": "number"}, "end": {"type": "number"}},
         "required": ["start", "end"]}},
    {"name": "zoom",
     "description": "See one quarter (or the centre) of a frame enlarged.",
     "parameters": {"type": "object", "properties": {
         "seconds": {"type": "number"},
         "area": {"type": "string", "enum": list(ZOOM_AREAS[:5])}},
         "required": ["seconds", "area"]}},
    {"name": "search_video",
     "description": "Twelve frames spread over a long stretch, to find "
                    "where something happens. Narrow down with smaller "
                    "stretches.",
     "parameters": {"type": "object", "properties": {
         "start": {"type": "number"}, "end": {"type": "number"}},
         "required": ["start", "end"]}},
    {"name": "seek",
     "description": "Move the player to a time so the person can listen "
                    "there.",
     "parameters": {"type": "object", "properties": {
         "seconds": {"type": "number"}}, "required": ["seconds"]}},
    {"name": "transcript",
     "description": "What is said between two times, with times.",
     "parameters": {"type": "object", "properties": {
         "start": {"type": "number"}, "end": {"type": "number"}},
         "required": ["start", "end"]}},
    {"name": "find_gap",
     "description": "Stretches with no speech between two times, where a "
                    "description can be heard.",
     "parameters": {"type": "object", "properties": {
         "start": {"type": "number"}, "end": {"type": "number"}},
         "required": ["start", "end"]}},
    {"name": "check_rules",
     "description": "Check a description before proposing it: word "
                    "count, and whether it fits the silence at that time.",
     "parameters": {"type": "object", "properties": {
         "text": {"type": "string"}, "time": {"type": "number"}},
         "required": ["text", "time"]}},
    {"name": "characters",
     "description": "Remembered character names for this video. action "
                    "'list' to read them, 'remember' to store one the "
                    "person told you.",
     "parameters": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["list", "remember"]},
         "name": {"type": "string"},
         "description": {"type": "string"}},
         "required": ["action"]}},
    {"name": "propose_change",
     "description": "Propose a change for the person to approve. action: "
                    "keep, move (index + time), edit (index + text), "
                    "remove (index), add (time + text).",
     "parameters": {"type": "object", "properties": {
         "action": {"type": "string", "enum": list(ACTIONS)},
         "index": {"type": "integer"},
         "time": {"type": "number"},
         "text": {"type": "string"},
         "reason": {"type": "string"}},
         "required": ["action", "reason"]}},
]
LOOKING_TOOLS = ("look_at", "look_between", "zoom", "search_video")


@dataclass
class Proposal:
    action: str
    reason: str
    index: int | None = None
    time: float | None = None
    text: str = ""


@dataclass
class Reply:
    answer: str = ""
    proposals: list[Proposal] = field(default_factory=list)
    cost: float = 0.0
    needs_confirmation: bool = False   # cost cap reached: ask "continue?"
    error: str = ""


@dataclass
class Context:
    """What the agent may see and the one thing it may do (seek)."""
    video: str
    length: float
    descriptions: list[tuple[float, str]]
    get_position: Callable[[], float] = lambda: 0.0
    seek: Callable[[float], None] = lambda s: None
    get_transcript: Callable[[], list] = lambda: []
    characters_file: str = ""
    language: str = "English"


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


class Frames:
    """Frames from the video as labelled JPEG bytes."""

    def __init__(self, video: str, length: float):
        self.video, self.length = video, length
        self.dir = Path(tempfile.mkdtemp(prefix="odc_agent_"))

    def _grab(self, seconds: float, width: int = 640):
        from PIL import Image
        from .tools import find_tool
        seconds = max(0.0, min(seconds, max(0.0, self.length - 0.2)))
        out = self.dir / f"f_{seconds:09.2f}_{width}.jpg"
        if not out.exists():
            subprocess.run([find_tool("ffmpeg"), "-hide_banner", "-nostdin",
                            "-y", "-v", "error", "-ss", f"{seconds:.2f}",
                            "-i", self.video, "-frames:v", "1",
                            "-vf", f"scale={width}:-2", str(out)],
                           timeout=60, check=True)
        return Image.open(out).convert("RGB"), seconds

    @staticmethod
    def _label(image, text: str):
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("arial.ttf", 24)
        except OSError:
            font = ImageFont.load_default()
        box = draw.textbbox((8, 6), text, font=font)
        draw.rectangle([box[0] - 4, box[1] - 3, box[2] + 4, box[3] + 3],
                       fill="black")
        draw.text((8, 6), text, fill="yellow", font=font)
        return image

    @staticmethod
    def _jpeg(image) -> bytes:
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=80)
        return buf.getvalue()

    def one(self, seconds: float) -> tuple[bytes, float]:
        image, at = self._grab(seconds)
        return self._jpeg(self._label(image, _clock(at))), at

    def sheet(self, start: float, end: float, count: int) -> tuple[bytes, list]:
        from PIL import Image
        start = max(0.0, start)
        end = min(max(start + 1.0, end), max(1.0, self.length - 0.2))
        times = [start + i * (end - start) / (count - 1) for i in range(count)]
        tiles = []
        for x in times:
            image, at = self._grab(x, width=400)
            tiles.append(self._label(image, _clock(at)))
        cols = 3 if count == 6 else 4
        w, h = tiles[0].size
        rows = (count + cols - 1) // cols
        sheet = Image.new("RGB", (w * cols, h * rows))
        for i, tile in enumerate(tiles):
            sheet.paste(tile.resize((w, h)), ((i % cols) * w, (i // cols) * h))
        return self._jpeg(sheet), times

    def zoom(self, seconds: float, area: str) -> tuple[bytes, float]:
        image, at = self._grab(seconds, width=1280)
        w, h = image.size
        boxes = {"top-left": (0, 0, w // 2, h // 2),
                 "top-right": (w // 2, 0, w, h // 2),
                 "bottom-left": (0, h // 2, w // 2, h),
                 "bottom-right": (w // 2, h // 2, w, h)}
        box = boxes.get(area, (w // 4, h // 4, 3 * w // 4, 3 * h // 4))
        crop = image.crop(box)   # already 640 wide from a 1280 frame
        return self._jpeg(self._label(crop, f"{_clock(at)} {area}")), at

    def close(self) -> None:
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)


class Agent:
    """One Player session: remembers the conversation until closed."""

    def __init__(self, api_key: str, model: str, ctx: Context,
                 post: Callable | None = None,
                 on_step: Callable[[str, dict], None] | None = None):
        self.api_key, self.model, self.ctx = api_key, model, ctx
        self.frames = Frames(ctx.video, ctx.length)
        self.on_step = on_step or (lambda code, args: None)
        self._post = post or self._http_post
        self.messages: list[dict] = [{"role": "system", "content":
                                      SYSTEM.format(language=ctx.language)}]
        self._transcript: list | None = None
        self._looked = False
        self._pending: Reply | None = None

    # ── transport ────────────────────────────────────────────────
    async def _http_post(self, payload: dict) -> dict:
        from .ai_engine import _http_json
        return await _http_json(
            "POST", URL, label="OpenRouter", payload=payload, timeout=180,
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"})

    def _payload(self, tools: bool) -> dict:
        payload = {"model": self.model, "messages": self.messages,
                   "temperature": 0, "max_tokens": 3000,
                   "reasoning": {"max_tokens": 1000},
                   "usage": {"include": True}}
        if tools:
            payload["tools"] = [{"type": "function", "function": f}
                                for f in TOOLS]
        return payload

    # ── the conversation ─────────────────────────────────────────
    async def ask(self, question: str, cost_cap: float = COST_CAP) -> Reply:
        """Answer one question; may stop at the cost cap for "continue?"."""
        self._forget_old_images()
        self._looked = False
        self.messages.append({"role": "user", "content": question})
        return await self._loop(Reply(), cost_cap)

    async def resume(self, cost_cap: float = COST_CAP) -> Reply:
        """The person said "continue": carry on from where it stopped."""
        reply = self._pending or Reply()
        reply.needs_confirmation = False
        return await self._loop(reply, reply.cost + cost_cap)

    async def _loop(self, reply: Reply, cap: float) -> Reply:
        self._pending = None
        for _turn in range(MAX_TURNS):
            try:
                data = await self._post(self._payload(tools=True))
            except Exception as e:
                reply.error = str(e)[:300]
                return reply
            reply.cost += float(((data.get("usage") or {}).get("cost")) or 0.0)
            if "error" in data:
                reply.error = json.dumps(data["error"])[:300]
                return reply
            msg = (data.get("choices") or [{}])[0].get("message") or {}
            calls = msg.get("tool_calls") or []
            self.messages.append({k: v for k, v in msg.items()
                                  if k in ("role", "content", "tool_calls")})
            if not calls:
                reply.answer = (msg.get("content") or "").strip()
                if reply.answer:
                    return reply
                break           # an empty answer: ask for one below
            images = []
            for call in calls:
                result, image = self._run_tool(call, reply)
                self.messages.append({"role": "tool",
                                      "tool_call_id": call.get("id", ""),
                                      "content": result})
                if image:
                    images.append(image)
            self.messages.extend(images)
            if reply.cost >= cap:
                reply.needs_confirmation = True
                self._pending = reply
                return reply
        # Turn limit (or an empty answer): make it answer, no more tools.
        self.messages.append({"role": "user", "content": (
            "Stop using tools now and answer in one to three sentences: "
            "what you found and what you proposed, or that you could not "
            "decide.")})
        try:
            data = await self._post(self._payload(tools=False))
            reply.cost += float(((data.get("usage") or {}).get("cost")) or 0.0)
            msg = (data.get("choices") or [{}])[0].get("message") or {}
            reply.answer = (msg.get("content") or "").strip()
            self.messages.append({"role": "assistant", "content": reply.answer})
        except Exception as e:
            reply.error = str(e)[:300]
        return reply

    def _forget_old_images(self) -> None:
        """Keep words from earlier questions, drop their pictures: the
        whole conversation is sent with every request."""
        for m in self.messages:
            if m.get("role") == "user" and isinstance(m.get("content"), list):
                texts = [c.get("text", "") for c in m["content"]
                         if c.get("type") == "text"]
                m["content"] = " ".join(texts) + " [image no longer shown]"

    # ── tools ────────────────────────────────────────────────────
    def _image_message(self, jpeg: bytes, note: str) -> dict:
        data = base64.b64encode(jpeg).decode()
        return {"role": "user", "content": [
            {"type": "text", "text": note},
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{data}"}}]}

    def _run_tool(self, call: dict, reply: Reply) -> tuple[str, dict | None]:
        fn = call.get("function") or {}
        name = fn.get("name", "")
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            return "The arguments were not valid JSON.", None
        try:
            return self._dispatch(name, args, reply)
        except Exception as e:
            logger.warning("Agent tool %s failed: %s", name, e)
            return f"{name} failed: {str(e)[:160]}", None

    def _num(self, args: dict, key: str, default: float = 0.0) -> float:
        try:
            return max(0.0, min(float(args.get(key, default)), self.ctx.length))
        except (TypeError, ValueError):
            return default

    def _dispatch(self, name: str, args: dict, reply: Reply):
        ctx = self.ctx
        if name == "current_position":
            return f"{ctx.get_position():.1f}", None
        if name == "read_descriptions":
            s, e = self._num(args, "start"), self._num(args, "end", ctx.length)
            self.on_step("reading", {"start": s, "end": e})
            rows = [f"[{i}] {t:.1f}s: {x}" for i, (t, x)
                    in enumerate(ctx.descriptions) if s <= t <= e]
            return "\n".join(rows) or "No descriptions there.", None
        if name == "search_descriptions":
            words = [w for w in re.findall(r"\w+", str(args.get("query", "")).lower())
                     if len(w) > 2]
            rows = [f"[{i}] {t:.1f}s: {x}" for i, (t, x) in enumerate(ctx.descriptions)
                    if words and all(w in x.lower() for w in words)]
            return "\n".join(rows[:30]) or "None found.", None
        if name in LOOKING_TOOLS:
            self._looked = True
            if name == "look_at":
                jpeg, at = self.frames.one(self._num(args, "seconds"))
                self.on_step("looking", {"at": at})
                return "The frame is in the next message.", \
                    self._image_message(jpeg, f"Frame at {_clock(at)}:")
            if name == "zoom":
                area = str(args.get("area", "centre"))
                jpeg, at = self.frames.zoom(self._num(args, "seconds"), area)
                self.on_step("looking", {"at": at})
                return "The enlarged area is in the next message.", \
                    self._image_message(jpeg, f"{area} of {_clock(at)}:")
            s, e = self._num(args, "start"), self._num(args, "end", ctx.length)
            count = 12 if name == "search_video" else 6
            jpeg, times = self.frames.sheet(s, e, count)
            self.on_step("searching" if count == 12 else "looking",
                         {"at": times[0], "end": times[-1]})
            return "The frames are in the next message.", self._image_message(
                jpeg, f"{count} frames {_clock(times[0])} to {_clock(times[-1])}:")
        if name == "seek":
            at = self._num(args, "seconds")
            ctx.seek(at)
            self.on_step("seek", {"at": at})
            return f"The player is now at {_clock(at)}.", None
        if name == "transcript":
            s, e = self._num(args, "start"), self._num(args, "end", ctx.length)
            rows = [f"{seg.start:.1f}-{seg.end:.1f}s: {seg.text}"
                    for seg in self._speech() if seg.end >= s and seg.start <= e]
            return "\n".join(rows) or "Nothing is said there.", None
        if name == "find_gap":
            s, e = self._num(args, "start"), self._num(args, "end", ctx.length)
            gaps = self._gaps(s, e)
            return ("\n".join(f"{a:.1f}-{b:.1f}s ({b - a:.1f} s)" for a, b in gaps)
                    or "No silence of 1.5 s or more there."), None
        if name == "check_rules":
            return self._check_rules(str(args.get("text", "")),
                                     self._num(args, "time")), None
        if name == "characters":
            return self._characters(args), None
        if name == "propose_change":
            return self._propose(args, reply), None
        return f"There is no tool called {name}.", None

    def _speech(self) -> list:
        if self._transcript is None:
            self.on_step("transcript", {})
            try:
                self._transcript = list(self.ctx.get_transcript() or [])
            except Exception as e:
                logger.warning("Agent transcript failed: %s", e)
                self._transcript = []
        return self._transcript

    def _gaps(self, start: float, end: float, minimum: float = 1.5) -> list:
        spans = sorted((seg.start, seg.end) for seg in self._speech()
                       if seg.end >= start and seg.start <= end)
        gaps, cursor = [], start
        for a, b in spans:
            if a - cursor >= minimum:
                gaps.append((cursor, a))
            cursor = max(cursor, b)
        if end - cursor >= minimum:
            gaps.append((cursor, end))
        return gaps

    def _check_rules(self, text: str, time: float) -> str:
        words = _words(text)
        from .timeline_io import WORDS_PER_SECOND_AT_1X
        needs = words / WORDS_PER_SECOND_AT_1X
        gap = next((b - time for a, b in self._gaps(max(0.0, time - 0.5),
                                                   min(self.ctx.length, time + 30))
                    if a <= time + 0.5 < b), 0.0)
        lines = [f"{words} words (limit {MAX_WORDS}): "
                 f"{'OK' if words <= MAX_WORDS else 'TOO LONG'}",
                 f"takes about {needs:.1f} s to say"]
        if self._speech():
            lines.append(f"silence from here: {gap:.1f} s — "
                         f"{'fits' if gap >= needs else 'does NOT fit, speech follows'}")
        if re.search(r"\b(says?|said|shouts?|hear|sound|music)\b", text, re.I):
            lines.append("mentions sound or speech — describe only what is seen")
        return "\n".join(lines)

    def _characters(self, args: dict) -> str:
        path = Path(self.ctx.characters_file) if self.ctx.characters_file else None
        known = {}
        if path and path.exists():
            try:
                known = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                known = {}
        if args.get("action") == "remember" and args.get("name"):
            known[str(args["name"])[:60]] = str(args.get("description", ""))[:200]
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(known, ensure_ascii=False, indent=1),
                                encoding="utf-8")
            return f"Remembered {args['name']}."
        return ("\n".join(f"{k}: {v}" for k, v in known.items())
                or "No characters remembered yet.")

    def _propose(self, args: dict, reply: Reply) -> str:
        if not self._looked:
            return ("Refused: look at the frames first (look_at, look_between, "
                    "zoom or search_video), then propose.")
        action = str(args.get("action", ""))
        if action not in ACTIONS:
            return f"Refused: action must be one of {', '.join(ACTIONS)}."
        index = args.get("index")
        count = len(self.ctx.descriptions)
        if action in ("move", "edit", "remove", "keep"):
            if not isinstance(index, int) or not 0 <= index < count:
                return f"Refused: index must be 0 to {count - 1}."
        time = args.get("time")
        if action in ("move", "add"):
            if not isinstance(time, (int, float)) or not 0 <= time <= self.ctx.length:
                return f"Refused: time must be 0 to {self.ctx.length:.0f} seconds."
        text = str(args.get("text", "")).strip()
        if action in ("edit", "add"):
            if not text:
                return "Refused: this change needs the new text."
            if _words(text) > PROPOSAL_WORD_LIMIT:
                return (f"Refused: {_words(text)} words; keep it to "
                        f"{MAX_WORDS} or fewer.")
        proposal = Proposal(action=action, reason=str(args.get("reason", ""))[:300],
                            index=index if isinstance(index, int) else None,
                            time=float(time) if isinstance(time, (int, float)) else None,
                            text=text)
        if action != "keep":
            reply.proposals.append(proposal)
        self.on_step("proposing", {"action": action})
        return "Proposal recorded for the person to approve."

    def close(self) -> None:
        self.frames.close()


# ── Settings > "Test agent mode" ───────────────────────────────────

def make_test_clip(folder: Path) -> tuple[Path, float]:
    """12 s: red with the word RED for 6 s, then blue with BLUE."""
    from .tools import find_tool
    out = folder / "agent_test.mp4"
    font = "C\\:/Windows/Fonts/arial.ttf"

    def part(colour: str, word: str) -> str:
        return (f"color=c={colour}:s=640x360:d=6,drawtext=fontfile='{font}':"
                f"text='{word}':fontsize=90:fontcolor=white:x=(w-tw)/2:y=(h-th)/2")
    subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error",
                    "-f", "lavfi", "-i", part("red", "RED"),
                    "-f", "lavfi", "-i", part("blue", "BLUE"),
                    "-filter_complex", "[0][1]concat=n=2:v=1[v]", "-map", "[v]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)],
                   check=True, timeout=120)
    return out, 12.0


async def probe(api_key: str, model: str, post: Callable | None = None) -> dict:
    """Can this model drive the agent? Judged on behaviour we can check,
    not on its opinion: real tool calls, looked before proposing, valid
    arguments, and a final answer (phase A findings)."""
    folder = Path(tempfile.mkdtemp(prefix="odc_agent_"))
    try:
        clip, length = make_test_clip(folder)
        ctx = Context(video=str(clip), length=length,
                      descriptions=[(1.0, "A blue screen shows the word BLUE.")],
                      get_position=lambda: 1.0)
        agent = Agent(api_key, model, ctx, post=post)
        used_tools = {"n": 0}
        original = agent._run_tool

        def counting(call, reply):
            used_tools["n"] += 1
            return original(call, reply)
        agent._run_tool = counting
        reply = await agent.ask(
            "Description [0] at 1.0 s says: \"A blue screen shows the word "
            "BLUE.\" Is it right? Check it and fix it if needed.")
        agent.close()
        ok = (used_tools["n"] > 0 and agent._looked and not reply.error
              and bool(reply.answer))
        return {"ok": ok, "tools": used_tools["n"], "looked": agent._looked,
                "proposals": [p.__dict__ for p in reply.proposals],
                "answer": reply.answer[:300], "error": reply.error,
                "cost": round(reply.cost, 5)}
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


__all__ = ["Agent", "Context", "Proposal", "Reply", "TOOLS", "probe"]
