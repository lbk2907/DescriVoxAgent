"""Can this model drive the Player agent? Measured, not assumed (phase A).

The OpenRouter catalogue says every candidate "supports tools". Pitfall
59 says a catalogue claim is not evidence. This gives each model the
agent's real job on a real film (Tears of Steel, bench clip) through
OpenAI-style tool calls:

  wrong   a description the independent judge marked WRONG — the model
          must look, then propose a fix (move / edit / remove)
  right   a description judged CORRECT — the model must look, then
          leave it alone (propose "keep", or no change)

Scored per run:
  protocol   the reply used real tool calls (not JSON pasted as text)
  looked     it looked at frames BEFORE proposing anything
  valid      every proposal had a known action, a time inside the film,
             and text of at most 20 words where text is needed
  outcome    wrong -> proposed a change; right -> proposed no change
  steps      finished within 8 model turns

Tool results that are images go back as a user message after the tool
message (most OpenRouter models cannot take an image inside a tool
result). Cost is read from the OpenRouter balance before and after.

    python tools/agent_bench.py [--models a,b] [--runs 2]
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import model_bench as mb  # noqa: E402  (bench folder, keys, clips)

from omni_describer_custom.core.tools import find_tool  # noqa: E402

URL = "https://openrouter.ai/api/v1/chat/completions"
CLIP = mb.CLIPS / "tears_full.mp4"
LENGTH = 734.0
OUT = mb.BENCH / "agent_bench.json"
FRAMES = mb.BENCH / "agent_frames"
MODELS = ["z-ai/glm-5.3-flash", "google/gemini-3.1-flash-lite",
          "qwen/qwen3.8-omni-flash", "google/gemini-3.8-flash"]
MAX_TURNS = 8

SYSTEM_V1 = (
    "You help a blind person improve the audio descriptions of a video "
    "they are watching in a player. You can only change descriptions by "
    "calling propose_change; the person approves every change. ALWAYS "
    "look at the frames (look_at or look_between) before proposing "
    "anything. Keep description text to 12 words or fewer, present tense, "
    "only what is visible. When you are done, answer in one or two short "
    "sentences.")

SYSTEM_V2 = SYSTEM_V1 + (
    " Only propose a change when the description is CLEARLY wrong about "
    "what is visible, or placed at a clearly different moment. Different "
    "wording, a more precise word, or a detail one frame cannot confirm "
    "is NOT a reason: then propose \"keep\". Before deciding, look at "
    "several moments around it (look_between a few seconds either side), "
    "not a single frame.")
PROMPTS = {"v1": SYSTEM_V1, "v2": SYSTEM_V2}
SYSTEM = SYSTEM_V2

TOOLS = [
    {"type": "function", "function": {
        "name": "current_position",
        "description": "The player's current position in seconds.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "read_descriptions",
        "description": "Descriptions between two times, with their index.",
        "parameters": {"type": "object", "properties": {
            "start": {"type": "number"}, "end": {"type": "number"}},
            "required": ["start", "end"]}}},
    {"type": "function", "function": {
        "name": "look_at",
        "description": "See the video frame at a time (seconds).",
        "parameters": {"type": "object", "properties": {
            "seconds": {"type": "number"}}, "required": ["seconds"]}}},
    {"type": "function", "function": {
        "name": "look_between",
        "description": "See six frames spread between two times, each "
                       "labelled with its time.",
        "parameters": {"type": "object", "properties": {
            "start": {"type": "number"}, "end": {"type": "number"}},
            "required": ["start", "end"]}}},
    {"type": "function", "function": {
        "name": "propose_change",
        "description": "Propose a change for the person to approve.",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string",
                       "enum": ["keep", "move", "edit", "remove", "add"]},
            "index": {"type": "integer",
                      "description": "description index (not for add)"},
            "time": {"type": "number", "description": "seconds"},
            "text": {"type": "string"},
            "reason": {"type": "string"}},
            "required": ["action", "reason"]}}},
]


def _frame(seconds: float) -> Path:
    FRAMES.mkdir(parents=True, exist_ok=True)
    seconds = max(0.0, min(seconds, LENGTH - 0.2))
    out = FRAMES / f"f_{seconds:08.2f}.jpg"
    if not out.exists():
        label = (f"drawtext=fontfile='{mb.FONT}':text='{int(seconds // 60)}\\:"
                 f"{seconds % 60:04.1f}':fontsize=26:fontcolor=yellow:box=1:"
                 "boxcolor=black:x=8:y=8")
        subprocess.run([find_tool("ffmpeg"), "-y", "-loglevel", "error",
                        "-ss", f"{seconds:.2f}", "-i", str(CLIP),
                        "-frames:v", "1", "-vf", f"scale=640:-2,{label}",
                        str(out)], timeout=60, check=True)
    return out


def _sheet(start: float, end: float) -> Path:
    start, end = max(0.0, start), min(LENGTH - 0.2, max(start + 1, end))
    out = FRAMES / f"s_{start:08.2f}_{end:08.2f}.jpg"
    if not out.exists():
        times = [start + i * (end - start) / 5 for i in range(6)]
        tiles = [_frame(x) for x in times]
        inputs = []
        for tile in tiles:
            inputs += ["-i", str(tile)]
        subprocess.run([find_tool("ffmpeg"), "-y", "-loglevel", "error",
                        *inputs, "-filter_complex",
                        "[0][1][2]hstack=3[a];[3][4][5]hstack=3[b];"
                        "[a][b]vstack,scale=1280:-2", str(out)],
                       timeout=60, check=True)
    return out


def _image_message(path: Path, note: str) -> dict:
    data = base64.b64encode(path.read_bytes()).decode()
    return {"role": "user", "content": [
        {"type": "text", "text": note},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}}]}


async def _post(session, key: str, payload: dict) -> dict:
    async with session.post(URL, json=payload, timeout=180,
                            headers={"Authorization": f"Bearer {key}"}) as r:
        return await r.json(content_type=None)


async def run_task(model: str, task: dict, cues: list, key: str) -> dict:
    import aiohttp
    messages = [{"role": "system", "content": PROMPTS[task.get("prompt", "v2")]},
                {"role": "user", "content": task["ask"]}]
    score = {"protocol": False, "looked": False, "valid": True,
             "proposals": [], "turns": 0, "error": "", "answer": ""}
    looked_first = None
    async with aiohttp.ClientSession() as session:
        for turn in range(MAX_TURNS):
            score["turns"] = turn + 1
            try:
                data = await _post(session, key, {
                    "model": model, "messages": messages, "tools": TOOLS,
                    "temperature": 0, "max_tokens": 3000,
                    "reasoning": {"max_tokens": 1000}})
            except Exception as e:
                score["error"] = f"{type(e).__name__}: {e}"[:200]
                break
            if "error" in data:
                score["error"] = json.dumps(data["error"])[:200]
                break
            msg = (data.get("choices") or [{}])[0].get("message") or {}
            calls = msg.get("tool_calls") or []
            messages.append({k: v for k, v in msg.items()
                             if k in ("role", "content", "tool_calls")})
            if not calls:
                score["answer"] = (msg.get("content") or "")[:300]
                if '"name"' in score["answer"] and "propose_change" in score["answer"]:
                    score["protocol"] = False   # tools pasted as text
                break
            score["protocol"] = True
            images = []
            for call in calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args, score["valid"] = {}, False
                if name == "current_position":
                    result = f"{task['position']:.1f}"
                elif name == "read_descriptions":
                    s, e = float(args.get("start", 0)), float(args.get("end", 0))
                    result = "\n".join(f"[{i}] {t:.1f}s: {x}" for i, (t, x)
                                       in enumerate(cues) if s <= t <= e) or "none"
                elif name == "look_at":
                    at = float(args.get("seconds", task["position"]))
                    images.append(_image_message(_frame(at), f"Frame at {at:.1f}s:"))
                    result = "The frame is in the next message."
                    looked_first = True if looked_first is None else looked_first
                elif name == "look_between":
                    s, e = float(args.get("start", 0)), float(args.get("end", 0))
                    images.append(_image_message(_sheet(s, e),
                                                 f"Six frames {s:.1f}s to {e:.1f}s:"))
                    result = "The frames are in the next message."
                    looked_first = True if looked_first is None else looked_first
                elif name == "propose_change":
                    if looked_first is None:
                        looked_first = False
                    score["proposals"].append(args)
                    act = args.get("action")
                    t_ = args.get("time")
                    words = len(str(args.get("text", "")).split())
                    if act not in ("keep", "move", "edit", "remove", "add"):
                        score["valid"] = False
                    if act in ("move", "add") and not (
                            isinstance(t_, (int, float)) and 0 <= t_ <= LENGTH):
                        score["valid"] = False
                    if act in ("edit", "add") and not (0 < words <= 20):
                        score["valid"] = False
                    result = "Proposal recorded for the person to approve."
                else:
                    result = f"Unknown tool {name}"
                    score["valid"] = False
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                 "content": result})
            messages.extend(images)
    score["looked"] = bool(looked_first)
    changes = [p for p in score["proposals"] if p.get("action") != "keep"]
    score["outcome"] = bool(changes) if task["kind"] == "wrong" else not changes
    return score


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default=",".join(MODELS))
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--prompt", default="v2", choices=sorted(PROMPTS))
    args = parser.parse_args()
    keys = mb._prepare_config()
    results = mb._load_results()
    cues = [(float(t), x) for t, x in
            results["z-ai/glm-5.3-flash|desc|tears_full@chunk300|1"]["cues"]]
    wrong_i = next(i for i, (t, x) in enumerate(cues) if "giant robot crashes" in x)
    right_i = next(i for i, (t, x) in enumerate(cues) if "rocket engines" in x
                   or "40 Years" in x)
    tasks = []
    for kind, i in (("wrong", wrong_i), ("right", right_i)):
        t, text = cues[i]
        tasks.append({"kind": kind, "position": t, "prompt": args.prompt, "ask": (
            f"The description [{i}] at {t:.1f}s says: \"{text}\". Is it right "
            f"for what is on screen then? Check it and fix it if needed.")})
    done = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}

    async def all_runs():
        before = await mb._balance(keys["glm"])
        for model in args.models.split(","):
            for task in tasks:
                for run in range(1, args.runs + 1):
                    k = f"{model}|{task['kind']}|{run}"
                    if args.prompt != "v1":
                        k = f"{args.prompt}|{k}"
                    if k in done and not done[k].get("error"):
                        continue
                    t0 = time.monotonic()
                    done[k] = await run_task(model, task, cues, keys["glm"])
                    done[k]["seconds"] = round(time.monotonic() - t0, 1)
                    OUT.write_text(json.dumps(done, indent=1, ensure_ascii=False),
                                   encoding="utf-8")
                    s = done[k]
                    print(f"{model:32} {task['kind']:5} r{run}  protocol={s['protocol']} "
                          f"looked={s['looked']} valid={s['valid']} "
                          f"outcome={s['outcome']} turns={s['turns']} "
                          f"{s['seconds']}s {s['error'][:60]}", flush=True)
        after = await mb._balance(keys["glm"])
        if before is not None and after is not None:
            print(f"spent ${before - after:.3f}")
    asyncio.run(all_runs())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
