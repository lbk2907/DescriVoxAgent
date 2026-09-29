"""Which video model describes most accurately? Measured, not assumed.

Asked by the owner (29 Sep 2026): models that hear the soundtrack should
describe more accurately — test it, across every model, not only GLM.

Runs the app's OWN engine (GLMProvider for OpenRouter models, the direct
GeminiProvider for Gemini) on genuinely different clips (pitfall 44):

  truth           a clip built here with events at KNOWN times: text,
                  shapes and colour changes, a knock, a voice, a bell
  sintel_dialogue English dialogue + action (Sintel 1:50-2:50, CC-BY)
  ocong           Indonesian cartoon, dense dialogue
  bm_news         Astro AWANI news summary, Malay
  bbb_music       Big Buck Bunny 2:00-3:00: music and sounds, no speech

Each model also answers a HEARING probe on the truth clip without any
transcript: which sounds, when, and what the voice says.

Nothing here touches the screen. Results go to results.json in the bench
folder after every call, so a stopped run resumes where it was.

    python tools/model_bench.py make-clips
    python tools/model_bench.py run [--runs 2] [--models a,b] [--floor 1.15]
    python tools/model_bench.py frames      # frames at each cue, for checking
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
REPO = Path(__file__).resolve().parent.parent
BENCH = Path(os.environ.get("TEMP", ".")) / "odc_bench"
CLIPS = BENCH / "clips"
os.environ["ODC_CONFIG_DIR"] = str(BENCH / "cfg")
sys.path.insert(0, str(REPO / "src"))

from omni_describer_custom.core.tools import find_tool  # noqa: E402

FONT = "C\\:/Windows/Fonts/arial.ttf"

# What the truth clip shows and plays, and when.
TRUTH_VISUAL = [
    ("welcome", 2.0, ["welcome"]),
    ("red square moves", 9.0, ["red"]),
    ("background turns green", 15.0, ["green"]),
    ("yellow square", 26.0, ["yellow"]),
    ("background turns grey", 30.0, ["grey", "gray"]),
    ("text EXIT 7", 36.0, ["exit"]),
    ("screen goes black", 45.0, ["black", "dark"]),
    ("text THE END", 52.0, ["the end", "end"]),
]
TRUTH_AUDIO = [
    ("knock", 20.0, ["knock", "tap", "bang", "thud", "rap", "click", "pop",
                     "thump", "hit", "clap"]),
    ("voice: pineapple", 31.0, ["pineapple"]),
    ("bell", 45.0, ["bell", "ding", "chime", "ring", "tone", "beep"]),
]

OPENROUTER_MODELS = [
    "z-ai/glm-5.3-flash",                                  # deaf, the default
    "qwen/qwen3.8-omni-flash",
    "xiaomi/mimo-v2.6-flash",
    "google/gemini-3.1-flash-lite",
    "google/gemini-2.5-flash-lite",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
]
GEMINI_DIRECT = "gemini-3.8-flash"
CLIP_NAMES = ["truth", "sintel_dialogue", "ocong", "bm_news", "bbb_music"]

HEARING_QUESTION = (
    "Listen to this 60-second test video's SOUNDTRACK. Answer in exactly "
    "two lines and nothing else:\n"
    "SOUNDS: <every non-speech sound you hear, each with its time as "
    "M:SS, or NONE>\n"
    "WORDS: <exactly what the voice says, or NONE if you hear no voice>")


# ── clips ────────────────────────────────────────────────────────

def make_truth_clip(out: Path) -> None:
    from omni_describer_custom.core.model_catalog import _speak_to_wav
    work = out.parent
    voice = work / "truth_voice.wav"
    if not _speak_to_wav("The password is pineapple.", voice):
        raise SystemExit("No SAPI voice: the truth clip needs one")
    ffmpeg = find_tool("ffmpeg")

    def text(t, start, end, size=64):
        return (f"drawtext=fontfile='{FONT}':text='{t}':fontsize={size}:"
                f"fontcolor=white:x=(w-tw)/2:y=(h-th)/2:"
                f"enable='between(t,{start},{end})'")

    video = (
        "[0][1][2][3]concat=n=4:v=1[bg];"
        "[bg][4]overlay=x='(t-9)*110':y=150:enable='between(t,9,14)'[a1];"
        "[a1][5]overlay=x=30:y=30:enable='between(t,26,33)'[a2];"
        f"[a2]{text('WELCOME', 2, 8)},{text('EXIT 7', 36, 44)},"
        f"{text('THE END', 52, 58)}[v]")
    audio = (
        "[6]volume=0.9,adelay=20000|20000[k1];"
        "[7]volume=0.9,adelay=20400|20400[k2];"
        "[8]volume=0.9,adelay=20800|20800[k3];"
        "[9]adelay=31000|31000[vo];"
        "[10]afade=t=out:st=0.2:d=1.3,volume=4.0,adelay=45000|45000[bell];"
        "[11][k1][k2][k3][vo][bell]amix=inputs=6:duration=first:"
        "normalize=0[a]")
    colour = lambda c: ["-f", "lavfi", "-i", f"color=c={c}:s=640x360:r=24:d=15"]
    knock = ["-f", "lavfi", "-i",
             "anoisesrc=d=0.08:c=brown:a=0.9,lowpass=f=400"]
    cmd = [ffmpeg, "-y", "-loglevel", "error",
           *colour("blue"), *colour("green"), *colour("gray"), *colour("black"),
           "-f", "lavfi", "-i", "color=c=red:s=80x80:r=24:d=60",
           "-f", "lavfi", "-i", "color=c=yellow:s=90x90:r=24:d=60",
           *knock, *knock, *knock,
           "-i", str(voice),
           "-f", "lavfi", "-i", "sine=frequency=880:duration=1.5",
           "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=60",
           "-filter_complex", video + ";" + audio,
           "-map", "[v]", "-map", "[a]", "-t", "60",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
           str(out)]
    subprocess.run(cmd, check=True, timeout=300)


def cmd_make_clips(_args) -> int:
    CLIPS.mkdir(parents=True, exist_ok=True)
    truth = CLIPS / "truth.mp4"
    make_truth_clip(truth)
    for name in CLIP_NAMES:
        path = CLIPS / f"{name}.mp4"
        print(f"{name:16s} {'ok' if path.exists() else 'MISSING'}")
    return 0


# ── settings for the bench (copies of the user's own keys) ──────

def _prepare_config() -> dict:
    cfg = BENCH / "cfg"
    cfg.mkdir(parents=True, exist_ok=True)
    user = Path(os.environ["APPDATA"]) / "OmniDescriber" / "settings.json"
    if not (cfg / "settings.json").exists():
        shutil.copy2(user, cfg / "settings.json")
    from omni_describer_custom.core.settings_store import SettingsStore
    store = SettingsStore()
    keys = {"glm": (store.get_ai_provider("glm") or {}).get("api_key", ""),
            "gemini": (store.get_ai_provider("gemini") or {}).get("api_key", "")}
    return keys


async def _balance(key: str) -> float | None:
    from omni_describer_custom.core.ai_engine import get_credit_balance
    got = await get_credit_balance(key)
    return got.get("remaining")


def _transcript(name: str) -> list:
    cache = BENCH / "transcripts" / f"{name}.json"
    from omni_describer_custom.core.video_processor import (
        TranscriptSegment, VideoProcessor)
    if cache.exists():
        return [TranscriptSegment(**s) for s in
                json.loads(cache.read_text(encoding="utf-8"))]
    clip = str(CLIPS / f"{name}.mp4")
    segs = asyncio.run(VideoProcessor().get_transcript(clip, local_path=clip))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps([s.__dict__ for s in segs], ensure_ascii=False,
                                indent=1), encoding="utf-8")
    return segs


# ── the runs ────────────────────────────────────────────────────

def _load_results() -> dict:
    path = BENCH / "results.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save_results(results: dict) -> None:
    path = BENCH / "results.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(results, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(path)


async def _describe(model: str, clip: str, keys: dict, transcript) -> dict:
    from omni_describer_custom.core.ai_engine import GeminiProvider, GLMProvider
    from omni_describer_custom.core.prompt_manager import DEFAULT_PROMPTS
    prompt = DEFAULT_PROMPTS["default"]
    started = time.monotonic()
    try:
        if model == GEMINI_DIRECT:
            prov = GeminiProvider(api_key=keys["gemini"])
            pairs = await prov.describe_video_full(
                str(CLIPS / f"{clip}.mp4"), prompt, model)
        else:
            prov = GLMProvider(api_key=keys["glm"])
            pairs = await prov.describe_video_full(
                str(CLIPS / f"{clip}.mp4"), prompt, model,
                transcript=transcript)
        return {"cues": [[round(t, 2), d] for t, d in pairs], "error": "",
                "seconds": round(time.monotonic() - started, 1)}
    except Exception as e:
        return {"cues": [], "error": f"{type(e).__name__}: {str(e)[:300]}",
                "seconds": round(time.monotonic() - started, 1)}


async def _hearing(model: str, keys: dict) -> dict:
    """The truth clip with NO transcript: does the model hear it?"""
    import base64
    from omni_describer_custom.core.ai_engine import GLMProvider
    or_model = "google/gemini-3.8-flash" if model == GEMINI_DIRECT else model
    data = base64.b64encode((CLIPS / "truth.mp4").read_bytes()).decode()
    payload = {"model": or_model, "max_tokens": 4000,
               "reasoning": {"max_tokens": 1500},
               "messages": [{"role": "user", "content": [
                   {"type": "video_url",
                    "video_url": {"url": f"data:video/mp4;base64,{data}"}},
                   {"type": "text", "text": HEARING_QUESTION}]}]}
    started = time.monotonic()
    try:
        answer = await GLMProvider(api_key=keys["glm"])._chat(payload, timeout=300)
        return {"answer": answer.strip(), "error": "",
                "seconds": round(time.monotonic() - started, 1)}
    except Exception as e:
        return {"answer": "", "error": f"{type(e).__name__}: {str(e)[:300]}",
                "seconds": round(time.monotonic() - started, 1)}


async def _run_model(model, jobs, keys, results, lock, stop):
    for job in jobs:
        if stop.is_set():
            return
        kind, clip, run = job
        key = f"{model}|{kind}|{clip}|{run}"
        if key in results and not results[key].get("error"):
            continue
        if kind == "hear":
            got = await _hearing(model, keys)
        else:
            got = await _describe(model, clip, keys,
                                  _transcript(clip) if model != GEMINI_DIRECT else None)
        async with lock:
            results[key] = got
            _save_results(results)
        shown = got.get("error") or (f"{len(got['cues'])} cues" if "cues" in got
                                     else got["answer"][:60].replace("\n", " | "))
        print(f"{model[:34]:34s} {kind:5s} {clip:16s} run{run} "
              f"{got['seconds']:6.1f}s  {shown}", flush=True)


async def _watch_balance(keys, floor, stop):
    while not stop.is_set():
        left = await _balance(keys["glm"])
        if left is not None and left < floor:
            print(f"\nBALANCE ${left:.2f} is below the floor ${floor:.2f}: "
                  "stopping after the calls in flight.", flush=True)
            stop.set()
            return
        await asyncio.sleep(20)


def cmd_run(args) -> int:
    keys = _prepare_config()
    # The catalog decides who hears (pitfall 59): cache it where the
    # engine looks, so each model gets the soundtrack it can use.
    from omni_describer_custom.core import model_catalog as mc
    catalog = BENCH / "catalog.json"
    if catalog.exists():
        mc.save_cache(mc.parse_catalog(json.loads(catalog.read_text(encoding="utf-8"))))
    for name in CLIP_NAMES:          # transcripts once, before the clock starts
        _transcript(name)
    models = (args.models.split(",") if args.models
              else OPENROUTER_MODELS + [GEMINI_DIRECT])
    jobs = [("hear", "truth", 1)] + [
        ("desc", clip, run) for run in range(1, args.runs + 1)
        for clip in CLIP_NAMES]
    results = _load_results()

    async def main():
        before = await _balance(keys["glm"])
        print(f"OpenRouter balance before: ${before:.2f}" if before is not None
              else "balance unknown", flush=True)
        stop, lock = asyncio.Event(), asyncio.Lock()
        watcher = asyncio.ensure_future(_watch_balance(keys, args.floor, stop))
        await asyncio.gather(*[_run_model(m, jobs, keys, results, lock, stop)
                               for m in models])
        stop.set()
        watcher.cancel()
        after = await _balance(keys["glm"])
        if before is not None and after is not None:
            print(f"OpenRouter balance after: ${after:.2f} "
                  f"(spent ${before - after:.2f})", flush=True)
    asyncio.run(main())
    return 0


# ── frames for checking each description by eye ──────────────────

def cmd_frames(args) -> int:
    """One contact sheet per model and clip: the frame at every cue."""
    results = _load_results()
    out = BENCH / "sheets"
    out.mkdir(exist_ok=True)
    ffmpeg = find_tool("ffmpeg")
    for key, got in results.items():
        model, kind, clip, run = key.split("|")
        if kind != "desc" or run != str(args.run) or not got.get("cues"):
            continue
        safe = model.replace("/", "_").replace(":", "_")
        folder = out / f"{clip}__{safe}"
        folder.mkdir(exist_ok=True)
        for i, (t, _d) in enumerate(got["cues"]):
            frame = folder / f"{i:02d}.jpg"
            if not frame.exists():
                label = (f"drawtext=fontfile='{FONT}':text='{i:02d}  {t:.0f}s':"
                         "fontsize=22:fontcolor=yellow:box=1:boxcolor=black:x=6:y=6")
                subprocess.run([ffmpeg, "-y", "-loglevel", "error",
                                "-ss", f"{max(0.0, t + 0.5):.2f}",
                                "-i", str(CLIPS / f"{clip}.mp4"),
                                "-frames:v", "1",
                                "-vf", f"scale=320:180,{label}",
                                str(frame)], timeout=60)
        count = len(got["cues"])
        cols = 4
        rows = (count + cols - 1) // cols
        sheet = out / f"{clip}__{safe}.jpg"
        subprocess.run([ffmpeg, "-y", "-loglevel", "error",
                        "-framerate", "1", "-i", str(folder / "%02d.jpg"),
                        "-vf", f"tile={cols}x{rows}:padding=4",
                        "-frames:v", "1", str(sheet)], timeout=120)
        (folder / "cues.txt").write_text(
            "\n".join(f"{i:02d} [{t:6.1f}s] {d}"
                      for i, (t, d) in enumerate(got["cues"])),
            encoding="utf-8")
    print(f"sheets in {out}")
    return 0


# ── scoring (what can be scored without a person) ────────────────

import re  # noqa: E402

# Things the truth clip does not contain: a description naming them
# invented it.
_ABSENT = ["person", "man", "woman", "people", "girl", "boy", "animal", "dog",
           "cat", "car", "tree", "building", "room", "door", "face", "hand",
           "logo", "circle", "ball", "star"]
# Describing what the listener already hears breaks the AD rules the
# preset gives (pitfall 13).
_AUDIBLE = re.compile(r"\b(says?|said|speaks?|speaking|asks?|replies|"
                      r"shouts?|music|song|sings?|sound|hear[sd]?|voice|"
                      r"narrat\w*)\b", re.I)
# (Quoted words are NOT counted: reading on-screen text aloud is
# required by the same rules, and it is usually quoted.)


def _mmss(text: str) -> list[float]:
    return [int(m) * 60 + int(s) for m, s in re.findall(r"(\d+):(\d{2})", text)]


def score_truth(cues: list) -> dict:
    hits, errors = 0, []
    for _name, when, words in TRUTH_VISUAL:
        near = [t for t, d in cues if any(w in d.lower() for w in words)]
        if near:
            hits += 1
            errors.append(min(abs(t - when) for t in near))
    invented = sum(1 for _t, d in cues
                   if any(re.search(rf"\b{w}s?\b", d.lower()) for w in _ABSENT))
    return {"events": hits, "of": len(TRUTH_VISUAL),
            "timing": round(sum(errors) / len(errors), 1) if errors else None,
            "invented": invented}


def score_hearing(answer: str) -> dict:
    """Heard = a sound reported within 4 s of a real one, named or not
    (Gemini called the bell a "car horn": heard, misnamed)."""
    text = answer.lower()
    sounds = text.split("words:")[0].replace("sounds:", "")
    words = text.split("words:")[-1] if "words:" in text else ""
    items = [s for s in re.split(r"[,;\n]", sounds)
             if s.strip() and "none" not in s]
    heard, named, invented = set(), set(), 0
    for item in items:
        times = _mmss(item)
        hit = False
        for name, when, kws in (TRUTH_AUDIO[0], TRUTH_AUDIO[2]):
            close = any(abs(t - when) < 2 for t in times)
            is_named = any(k in item for k in kws)
            if close or (is_named and not times):
                heard.add(name)
                hit = True
                if is_named:
                    named.add(name)
        if not hit:
            invented += 1
    return {"knock": "knock" in heard, "bell": "bell" in heard,
            "named": len(named), "word": "pineapple" in words,
            "invented_sounds": invented}


def score_rules(cues: list) -> dict:
    if not cues:
        return {"cues": 0, "long": 0, "audible": 0}
    return {"cues": len(cues),
            "long": sum(1 for _t, d in cues if len(d.split()) > 12),
            "audible": sum(1 for _t, d in cues if _AUDIBLE.search(d))}


def cmd_score(_args) -> int:
    results = _load_results()
    models = sorted({k.split("|")[0] for k in results})
    rows = []
    for model in models:
        mine = {k: v for k, v in results.items() if k.startswith(model + "|")}
        hear = next((v for k, v in mine.items() if "|hear|" in k), {})
        h = score_hearing(hear.get("answer", "")) if hear.get("answer") else None
        truth = [score_truth(v["cues"]) for k, v in mine.items()
                 if "|desc|truth|" in k and v.get("cues")]
        descs = [v for k, v in mine.items() if "|desc|" in k]
        failed = sum(1 for v in descs if v.get("error") or not v.get("cues"))
        rules = [score_rules(v["cues"]) for v in descs if v.get("cues")]
        n = sum(r["cues"] for r in rules) or 1
        counts = {}
        for k, v in mine.items():
            if "|desc|" in k and v.get("cues"):
                clip = k.split("|")[2]
                counts.setdefault(clip, []).append(len(v["cues"]))
        spread = [max(c) / max(1, min(c)) for c in counts.values() if len(c) > 1]
        rows.append({
            "model": model,
            "hears": (None if h is None else
                      f"knock {'Y' if h['knock'] else '-'} bell "
                      f"{'Y' if h['bell'] else '-'} word "
                      f"{'Y' if h['word'] else '-'} +{h['invented_sounds']} fake"),
            "truth_events": (f"{sum(t['events'] for t in truth) / len(truth):.1f}"
                             f"/{TRUTH_VISUAL.__len__()}" if truth else "-"),
            "timing_s": (round(sum(t["timing"] for t in truth if t["timing"] is not None)
                               / max(1, sum(1 for t in truth if t["timing"] is not None)), 1)
                         if truth else None),
            "invented": sum(t["invented"] for t in truth),
            "runs_failed": f"{failed}/{len(descs)}",
            "long_pct": round(100 * sum(r["long"] for r in rules) / n),
            "audible_pct": round(100 * sum(r["audible"] for r in rules) / n),
            "run_spread": round(max(spread), 1) if spread else None,
            "mean_s": round(sum(v["seconds"] for v in descs) / max(1, len(descs))),
        })
    out = BENCH / "scores.json"
    out.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    head = ["model", "hears", "truth_events", "timing_s", "invented",
            "runs_failed", "long_pct", "audible_pct", "run_spread", "mean_s"]
    print(" | ".join(head))
    for r in rows:
        print(" | ".join(str(r[h]) for h in head))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("make-clips")
    run = sub.add_parser("run")
    run.add_argument("--runs", type=int, default=2)
    run.add_argument("--models", default="")
    run.add_argument("--floor", type=float, default=1.15,
                     help="stop when OpenRouter credit falls below this "
                          "(video requests fail under $1)")
    frames = sub.add_parser("frames")
    frames.add_argument("--run", type=int, default=1)
    sub.add_parser("score")
    args = parser.parse_args()
    return {"make-clips": cmd_make_clips, "run": cmd_run,
            "frames": cmd_frames, "score": cmd_score}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
