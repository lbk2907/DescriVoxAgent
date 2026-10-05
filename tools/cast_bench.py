"""Do the character rules and the cast list help? Measured, not assumed.

Owner, 5 Oct 2026 (checklist phase 29): "the same person is called
different things" and "names heard in the dialogue are not used". Runs
the app's own providers on two full films with named people, with the
v2.1.0 character rules + cast ("on") and without ("off"):

  tears_full   Tears of Steel, 12 min - Celia, Tom (heard in dialogue)
  sintel_full  Sintel, 15 min - Sintel, Scales

GLM (OpenRouter, the app default) splits each film into 5-minute parts,
so it shows whether the cast carries across parts; Gemini watches the
whole film at once.

Scored on the description text alone:
  name rate      of the lines that mention a person, how many use a name
                 heard in the film (higher = better);
  labels         how many DIFFERENT generic phrases name people ("the man",
                 "a young woman in red", ...) - fewer = more consistent;
  other names    capitalised names that are not in the film (made up?).

Uses the bench folder and the bench's copy of the keys (model_bench.py).
Results are saved after every run, so a stopped run resumes.

    python tools/cast_bench.py run [--runs 1]
    python tools/cast_bench.py score
    python tools/cast_bench.py judge [--sample 40]   # share judged WRONG

The judge is model_bench's validated one (GLM, four frames around the
description; never called a correct description wrong, 0/83): a sample
of each run's descriptions, evenly spread, so fewer lines are not bought
with less accurate ones.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_bench as mb  # noqa: E402  (sets the bench config dir first)

RESULTS = mb.BENCH / "cast_results.json"
CLIPS = {"tears_full": ["Celia", "Tom", "Thom"], "sintel_full": ["Sintel", "Scales"]}
MODELS = {"glm": "z-ai/glm-5.3-flash", "gemini": "gemini-3.1-flash-lite"}
PERSON = re.compile(
    r"\b(?:the|a|an|another)\s+((?:[\w-]+\s+){0,3}?"
    r"(?:man|woman|girl|boy|person|figure|soldier|scientist|warrior|child|"
    r"lady|guy|people|couple|lelaki|wanita|budak|gadis))\b", re.IGNORECASE)
NOT_NAMES = {"The", "A", "An", "He", "She", "They", "It", "His", "Her", "In", "On",
             "At", "As", "With", "Text", "Close", "Wide", "Inside", "Outside", "Night",
             "Day", "Title", "Credits", "Camera", "Later", "Back", "Two", "One", "Three",
             "Steel", "Tears", "Blender", "Amsterdam", "Earth", "Then", "Now", "Both"}


def load() -> dict:
    if RESULTS.exists():
        return json.loads(RESULTS.read_text(encoding="utf-8"))
    return {}


def save(results: dict) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


async def describe(provider: str, clip: str, mode: str, keys: dict) -> dict:
    from omni_describer_custom.core.ai_engine import GeminiProvider, GLMProvider
    from omni_describer_custom.core.characters import CHARACTER_RULES
    from omni_describer_custom.core.prompt_manager import DEFAULT_PROMPTS
    prompt = DEFAULT_PROMPTS["default"]
    if mode == "on":
        prompt = prompt + "\n" + CHARACTER_RULES
    video = str(mb.CLIPS / f"{clip}.mp4")
    started = time.monotonic()
    cast_seen: list = []
    try:
        if provider == "gemini":
            prov = GeminiProvider(api_key=keys["gemini"])
            pairs = await prov.describe_video_full(video, prompt, MODELS["gemini"])
        else:
            prov = GLMProvider(api_key=keys["glm"])
            pairs = await prov.describe_video_full(
                video, prompt, MODELS["glm"], transcript=mb._transcript(clip),
                chunk_seconds=300,
                **({"cast": [], "on_cast": cast_seen.append} if mode == "on" else {}))
        return {"cues": [[round(t, 2), d] for t, d in pairs], "error": "",
                "cast": cast_seen[-1] if cast_seen else [],
                "seconds": round(time.monotonic() - started, 1)}
    except Exception as e:
        return {"cues": [], "error": f"{type(e).__name__}: {str(e)[:300]}",
                "seconds": round(time.monotonic() - started, 1)}


def cmd_run(args) -> int:
    keys = mb._prepare_config()
    results = load()
    jobs = [(p, c, m, r) for r in range(args.runs) for c in CLIPS
            for p in MODELS for m in ("off", "on")]
    for provider, clip, mode, run in jobs:
        key = f"{provider}|{clip}|{mode}|{run}"
        if key in results and not results[key].get("error"):
            continue
        print(f"run  {key} ...", flush=True)
        got = asyncio.run(describe(provider, clip, mode, keys))
        results[key] = got
        save(results)
        print(f"     {len(got['cues'])} cues, {got['seconds']} s {got['error'][:120]}", flush=True)
    return 0


def score(cues: list, names: list[str]) -> dict:
    texts = [d for _, d in cues]
    name_re = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b", re.IGNORECASE)
    named = [t for t in texts if name_re.search(t)]
    labels = {m.group(0).lower() for t in texts for m in PERSON.finditer(t)}
    person = [t for t in texts if name_re.search(t) or PERSON.search(t)]
    others = set()
    for t in texts:
        for w in re.findall(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]{2,})\b", t):
            if w not in NOT_NAMES and not name_re.fullmatch(w):
                others.add(w)
    return {"lines": len(texts), "person_lines": len(person), "named_lines": len(named),
            "name_rate": round(len(named) / len(person), 3) if person else 0.0,
            "labels": len(labels), "other_names": sorted(others)[:12]}


def cmd_score(_args) -> int:
    results = load()
    rows = {}
    for key, r in results.items():
        provider, clip, mode, run = key.split("|")
        if r.get("error"):
            print(f"{key}: ERROR {r['error'][:100]}")
            continue
        s = score(r["cues"], CLIPS[clip])
        rows.setdefault((provider, clip, mode), []).append(s)
    print(f"\n{'provider':8} {'clip':12} {'mode':4} {'lines':>5} {'person':>6} "
          f"{'named':>5} {'rate':>5} {'labels':>6}  other capitalised words")
    for (provider, clip, mode), ss in sorted(rows.items()):
        avg = lambda k: sum(s[k] for s in ss) / len(ss)  # noqa: E731
        print(f"{provider:8} {clip:12} {mode:4} {avg('lines'):5.0f} {avg('person_lines'):6.0f} "
              f"{avg('named_lines'):5.0f} {avg('name_rate'):5.2f} {avg('labels'):6.1f}  "
              f"{', '.join(ss[0]['other_names'])}")
    return 0


def cmd_judge(args) -> int:
    keys = mb._prepare_config()
    results = load()
    store = mb.BENCH / "cast_judgements.json"
    done = json.loads(store.read_text(encoding="utf-8")) if store.exists() else {}
    grids = mb.BENCH / "judge_grids"
    grids.mkdir(exist_ok=True)
    items = []
    for key, r in results.items():
        cues = r.get("cues") or []
        if not cues:
            continue
        step = max(1, len(cues) // args.sample)
        provider, clip, mode, run = key.split("|")
        for i in range(0, len(cues), step)[:args.sample]:
            t, text = cues[i]
            grid = grids / f"cast__{provider}__{clip}__{mode}__{run}__{i}.jpg"
            items.append((f"{key}|{i}", clip, float(t), text, grid))
    for _k, clip, t, _x, grid in items:
        mb.judge_grid(clip, t, grid)

    async def run_all():
        sem = asyncio.Semaphore(8)

        async def one(item):
            jkey, _c, _t, text, grid = item
            if done.get(jkey, {}).get("verdict"):
                return
            async with sem:
                done[jkey] = await mb._judge_one("z-ai/glm-5.3-flash", jkey, text,
                                                 grid, keys["glm"])
        await asyncio.gather(*[one(it) for it in items])
    asyncio.run(run_all())
    store.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    table = {}
    for jkey, *_ in items:
        provider, clip, mode, _run, _i = jkey.split("|")
        row = table.setdefault((provider, clip, mode), [0, 0])
        row[0] += 1
        row[1] += done.get(jkey, {}).get("verdict") == "wrong"
    print(f"{'provider':8} {'clip':12} {'mode':4} {'judged':>6} {'wrong%':>7}")
    for (provider, clip, mode), (n, w) in sorted(table.items()):
        print(f"{provider:8} {clip:12} {mode:4} {n:6d} {100 * w / n:6.1f}%")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--runs", type=int, default=1)
    sub.add_parser("score")
    judge = sub.add_parser("judge")
    judge.add_argument("--sample", type=int, default=40)
    args = ap.parse_args()
    return {"run": cmd_run, "score": cmd_score, "judge": cmd_judge}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
