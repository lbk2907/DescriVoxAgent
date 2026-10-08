"""Phase 22.5: does more thinking make the Player agent better?

Runs the app's OWN agent engine (core/agent.py, the code F2 uses) on
Tears of Steel with eight descriptions both independent judges agreed
on: four WRONG (the agent should propose a change) and four CORRECT (it
should leave them alone). Only the thinking setting changes between
levels; everything else is the shipped agent.

    python tools/agent_levels.py --provider glm --model z-ai/glm-5.3-flash \
        --levels cap,low,high
    python tools/agent_levels.py --provider gemini --model gemini-3.8-flash \
        --levels low,medium,high

Level names: "cap" = the shipped OpenRouter setting (1000 reasoning
tokens); "shipped" = whatever the app sends today; anything else is
reasoning.effort (OpenRouter) or reasoning_effort (Gemini).
Results: odc_bench/agent_levels.json (resumable).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import model_bench as mb  # noqa: E402  (bench folder, keys, clips)

from omni_describer_custom.core import agent as ag  # noqa: E402

CLIP = mb.CLIPS / "tears_full.mp4"
LENGTH = 734.0
OUT = mb.BENCH / "agent_levels.json"
SOURCE = "z-ai/glm-5.3-flash|desc|tears_full@chunk300|1"
# Both judges (GLM and Gemini) agreed, run 1 of the chunk300 bench.
WRONG = (16, 24, 28, 72)
RIGHT = (6, 21, 42, 61)
CAP = ag.COST_CAP


def make_agent(provider: str, model: str, key: str, level: str, cues, at):
    ctx = ag.Context(
        video=str(CLIP),
        length=LENGTH,
        descriptions=cues,
        get_position=lambda: at,
        language="English",
    )
    agent = ag.Agent(key, model, ctx, provider=provider)
    if level == "shipped":
        return agent
    real = agent._payload

    def payload(tools: bool) -> dict:
        body = real(tools)
        if provider == "gemini":
            body["reasoning_effort"] = level
        elif level == "cap":
            body["reasoning"] = {"max_tokens": 1000}
        else:
            body["reasoning"] = {"effort": level}
        return body

    agent._payload = payload
    return agent


async def one(provider, model, key, level, cues, index, kind) -> dict:
    at, text = cues[index]
    agent = make_agent(provider, model, key, level, cues, at)
    started = time.monotonic()
    try:
        reply = await agent.ask(
            cost_cap=CAP,
            question=f'The description [{index}] at {at:.1f}s says: "{text}". Is it '
            "right for what is on screen then? Check it and fix it if needed.",
        )
    finally:
        agent.close()
    changes = [p for p in reply.proposals if p.action != "keep"]
    # Stopped at the cost cap = no decision, not "kept" (1 Oct 2026: Gemini
    # 3.8 Flash looked 8 times, hit $0.02, and was scored as keeping).
    decided = not reply.needs_confirmation and not reply.error
    return {
        "kind": kind,
        "index": index,
        "looked": agent._looked,
        "changes": [p.__dict__ for p in changes],
        "outcome": decided and (bool(changes) if kind == "wrong" else not changes),
        "answer": reply.answer[:300],
        "error": reply.error[:200],
        "cost": round(reply.cost, 5),
        "seconds": round(time.monotonic() - started, 1),
        "stopped_at_cap": reply.needs_confirmation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("glm", "gemini"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--levels", required=True)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument(
        "--cap",
        type=float,
        default=ag.COST_CAP,
        help="cost cap per question (the app asks 'continue?' there)",
    )
    parser.add_argument("--tag", default="", help="suffix for the level key")
    args = parser.parse_args()
    global CAP
    CAP = args.cap
    keys = mb._prepare_config()
    key = keys["glm"] if args.provider == "glm" else keys["gemini"]
    cues = [(float(t), x) for t, x in mb._load_results()[SOURCE]["cues"]]
    done = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    tasks = [("wrong", i) for i in WRONG] + [("right", i) for i in RIGHT]

    async def run_all():
        for level in args.levels.split(","):
            for run in range(1, args.runs + 1):
                for kind, index in tasks:
                    k = f"{args.model}|{level}{args.tag}|{kind}{index}|{run}"
                    if k in done and not done[k].get("error"):
                        continue
                    done[k] = await one(args.provider, args.model, key, level, cues, index, kind)
                    OUT.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
                    r = done[k]
                    print(
                        f"{args.model[:24]:24} {level:7} {kind:5} [{index:2}] "
                        f"outcome={r['outcome']!s:5} looked={r['looked']!s:5} "
                        f"${r['cost']:.4f} {r['seconds']:5.1f}s {r['error'][:50]}",
                        flush=True,
                    )
        summary(args.model)

    asyncio.run(run_all())
    return 0


def summary(model: str) -> None:
    done = json.loads(OUT.read_text(encoding="utf-8"))
    rows: dict = {}
    for k, r in done.items():
        m, level, _task, _run = k.split("|")
        if m != model:
            continue
        s = rows.setdefault(
            level,
            {
                "n": 0,
                "ok": 0,
                "wrong_ok": 0,
                "right_ok": 0,
                "looked": 0,
                "cost": 0.0,
                "sec": 0.0,
                "err": 0,
            },
        )
        s["n"] += 1
        s["ok"] += r["outcome"] and not r["error"]
        s["wrong_ok"] += r["kind"] == "wrong" and r["outcome"] and not r["error"]
        s["right_ok"] += r["kind"] == "right" and r["outcome"] and not r["error"]
        s["looked"] += r["looked"]
        s["cost"] += r["cost"]
        s["sec"] += r["seconds"]
        s["err"] += bool(r["error"]) or bool(r.get("stopped_at_cap"))
    print(f"\n{model}")
    print("level    n  right-call  wrong-fixed  correct-kept  looked  err/cap  cost     avg s")
    for level, s in rows.items():
        print(
            f"{level:7} {s['n']:2}  {s['ok']:>10}  {s['wrong_ok']:>11}  "
            f"{s['right_ok']:>12}  {s['looked']:>6}  {s['err']:>6}  "
            f"${s['cost']:.4f}  {s['sec'] / max(1, s['n']):5.1f}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
