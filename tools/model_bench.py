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
    (
        "knock",
        20.0,
        ["knock", "tap", "bang", "thud", "rap", "click", "pop", "thump", "hit", "clap"],
    ),
    ("voice: pineapple", 31.0, ["pineapple"]),
    ("bell", 45.0, ["bell", "ding", "chime", "ring", "tone", "beep"]),
]

OPENROUTER_MODELS = [
    "z-ai/glm-5.3-flash",  # deaf, the default
    "qwen/qwen3.8-omni-flash",
    "xiaomi/mimo-v2.6-flash",
    "google/gemini-3.1-flash-lite",
    "google/gemini-2.5-flash-lite",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
]
GEMINI_DIRECT = "gemini-3.8-flash"
CLIP_NAMES = ["truth", "sintel_dialogue", "ocong", "bm_news", "bbb_music"]
# Phase 16.2 (29 Sep 2026): the owner's four genres, one more each, and
# a long video that is split into parts.
GENRE_CLIPS = ["tears_drama", "nasa_doc", "excel_tutorial"]
LONG_CLIP = "sintel_full"

HEARING_QUESTION = (
    "Listen to this 60-second test video's SOUNDTRACK. Answer in exactly "
    "two lines and nothing else:\n"
    "SOUNDS: <every non-speech sound you hear, each with its time as "
    "M:SS, or NONE>\n"
    "WORDS: <exactly what the voice says, or NONE if you hear no voice>"
)


# ── clips ────────────────────────────────────────────────────────


def make_truth_clip(out: Path) -> None:
    from omni_describer_custom.core.model_catalog import _speak_to_wav

    work = out.parent
    voice = work / "truth_voice.wav"
    if not _speak_to_wav("The password is pineapple.", voice):
        raise SystemExit("No SAPI voice: the truth clip needs one")
    ffmpeg = find_tool("ffmpeg")

    def text(t, start, end, size=64):
        return (
            f"drawtext=fontfile='{FONT}':text='{t}':fontsize={size}:"
            f"fontcolor=white:x=(w-tw)/2:y=(h-th)/2:"
            f"enable='between(t,{start},{end})'"
        )

    video = (
        "[0][1][2][3]concat=n=4:v=1[bg];"
        "[bg][4]overlay=x='(t-9)*110':y=150:enable='between(t,9,14)'[a1];"
        "[a1][5]overlay=x=30:y=30:enable='between(t,26,33)'[a2];"
        f"[a2]{text('WELCOME', 2, 8)},{text('EXIT 7', 36, 44)},"
        f"{text('THE END', 52, 58)}[v]"
    )
    audio = (
        "[6]volume=0.9,adelay=20000|20000[k1];"
        "[7]volume=0.9,adelay=20400|20400[k2];"
        "[8]volume=0.9,adelay=20800|20800[k3];"
        "[9]adelay=31000|31000[vo];"
        "[10]afade=t=out:st=0.2:d=1.3,volume=4.0,adelay=45000|45000[bell];"
        "[11][k1][k2][k3][vo][bell]amix=inputs=6:duration=first:"
        "normalize=0[a]"
    )
    colour = lambda c: ["-f", "lavfi", "-i", f"color=c={c}:s=640x360:r=24:d=15"]
    knock = ["-f", "lavfi", "-i", "anoisesrc=d=0.08:c=brown:a=0.9,lowpass=f=400"]
    cmd = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        *colour("blue"),
        *colour("green"),
        *colour("gray"),
        *colour("black"),
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=80x80:r=24:d=60",
        "-f",
        "lavfi",
        "-i",
        "color=c=yellow:s=90x90:r=24:d=60",
        *knock,
        *knock,
        *knock,
        "-i",
        str(voice),
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=880:duration=1.5",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=stereo:d=60",
        "-filter_complex",
        video + ";" + audio,
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-t",
        "60",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(out),
    ]
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
    copy = cfg / "settings.json"
    # Refresh when the real settings are newer: a stale copy kept a
    # replaced Gemini key and every run hit the old key's free quota
    # (1 Oct 2026).
    if not copy.exists() or user.stat().st_mtime > copy.stat().st_mtime:
        shutil.copy2(user, copy)
    from omni_describer_custom.core.settings_store import SettingsStore

    store = SettingsStore()
    keys = {
        "glm": (store.get_ai_provider("glm") or {}).get("api_key", ""),
        "gemini": (store.get_ai_provider("gemini") or {}).get("api_key", ""),
    }
    return keys


async def _balance(key: str) -> float | None:
    from omni_describer_custom.core.ai_engine import get_credit_balance

    got = await get_credit_balance(key)
    return got.get("remaining")


def _transcript(name: str) -> list:
    name = name.split("@")[0]
    cache = BENCH / "transcripts" / f"{name}.json"
    from omni_describer_custom.core.video_processor import TranscriptSegment, VideoProcessor

    if cache.exists():
        return [TranscriptSegment(**s) for s in json.loads(cache.read_text(encoding="utf-8"))]
    clip = str(CLIPS / f"{name}.mp4")
    segs = asyncio.run(VideoProcessor().get_transcript(clip, local_path=clip))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps([s.__dict__ for s in segs], ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return segs


# ── the runs ────────────────────────────────────────────────────


def _load_results() -> dict:
    path = BENCH / "results.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save_results(results: dict) -> None:
    path = BENCH / "results.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _agentic_generator(prov):
    """A drop-in for GeminiProvider._generate_with_video that uses the
    Interactions API with agentic video processing (phase 36). Runs in
    the background and is polled, as Google advises for long videos."""
    from omni_describer_custom.core.ai_engine import _http_json

    async def generate(uri, mime, prompt, model, is_cancelled=None):
        base = prov.base_url.rstrip("/")
        config = {}
        if prov.TEMPERATURE is not None:
            config["temperature"] = prov.TEMPERATURE
        level = (
            prov.THINKING if prov.THINKING is not None else prov.THINKING_BY_MODEL.get(model) or {}
        ).get("thinkingLevel")
        if level:
            config["thinking_level"] = level
        # Not "background": True - with it the same file URI came back as
        # "Unsupported file uri: blobstore:///..." (8 Oct 2026); the 60 s
        # bench clips finish within one request. Polled below if not.
        payload = {
            "model": model,
            "input": [
                {"type": "text", "text": prompt},
                {"type": "video", "uri": uri, "mime_type": mime, "processing": "agentic"},
            ],
        }
        if config:
            payload["generation_config"] = config
        data = await _http_json(
            "POST",
            f"{base}/interactions",
            label="Gemini",
            headers=prov._auth_headers(),
            payload=payload,
            timeout=900,
        )
        ident = data.get("id") or data.get("name", "").split("/")[-1]
        deadline = time.monotonic() + 1800
        while data.get("status") in ("in_progress", None, "") and time.monotonic() < deadline:
            await asyncio.sleep(5)
            data = await _http_json(
                "GET",
                f"{base}/interactions/{ident}",
                label="Gemini",
                headers=prov._auth_headers(),
                timeout=60,
            )
        if data.get("status") != "completed":
            raise RuntimeError(
                f"agentic interaction {data.get('status')}: {str(data.get('error') or data)[:300]}"
            )
        texts = [
            c.get("text", "")
            for s in data.get("steps") or []
            if s.get("type") == "model_output"
            for c in s.get("content") or []
            if c.get("text")
        ]
        if not texts:
            raise RuntimeError(f"agentic interaction had no text: {str(data)[:300]}")
        return texts[-1]

    return generate


async def _describe(model: str, clip: str, keys: dict, transcript) -> dict:
    from omni_describer_custom.core.ai_engine import GeminiProvider, GLMProvider
    from omni_describer_custom.core.prompt_manager import DEFAULT_PROMPTS

    prompt = DEFAULT_PROMPTS["default"]
    started = time.monotonic()
    try:
        if model == GEMINI_DIRECT or model.startswith("gemini-"):
            # Gemini with the user's own key; "@temp0"/"@tdef" as below
            # (phase 20.7).
            base, _, variant = clip.partition("@")
            prov = GeminiProvider(api_key=keys["gemini"])
            if variant.startswith("temp"):
                prov.TEMPERATURE = float(variant[4:] or 0)
            elif variant == "tdef":
                prov.TEMPERATURE = None
            elif variant.startswith("think"):
                # "@thinklow" etc. = thinkingConfig.thinkingLevel (phase 22);
                # "@thinkdef" = the model's own default.
                level = variant[5:]
                prov.THINKING = {} if level == "def" else {"thinkingLevel": level}
            elif variant == "agentic":
                # Phase 36 (8 Oct 2026): the same prompt and parser, but the
                # video goes through the Interactions API with
                # "processing": "agentic" (the model inspects the timeline
                # itself). "@new" = the app's usual path on today's clips.
                prov._generate_with_video = _agentic_generator(prov)
            pairs = await prov.describe_video_full(str(CLIPS / f"{base}.mp4"), prompt, model)
        else:
            # "clip@chunk180" = the same video in 180-second parts.
            base, _, variant = clip.partition("@")
            chunk = int(variant[5:]) if variant.startswith("chunk") else 600
            prov = GLMProvider(api_key=keys["glm"])
            # "clip@temp0" = temperature 0 (phase 19.B1); "@tdef" = the
            # server default, run fresh alongside it for a fair comparison.
            if variant.startswith("temp"):
                prov.TEMPERATURE = float(variant[4:] or 0)
            elif variant == "tdef":
                prov.TEMPERATURE = None  # the server's own default
            elif variant.startswith("think"):
                # "@thinklow"/"@thinkhigh"/... = reasoning.effort instead of
                # the app's 2000-token cap; "@thinkcap" = the cap (phase 22).
                level = variant[5:]
                if level != "cap":
                    send = prov._chat

                    async def effort_chat(payload, *a, _send=send, _lvl=level, **k):
                        payload = dict(payload, reasoning={"effort": _lvl})
                        return await _send(payload, *a, **k)

                    prov._chat = effort_chat
            pairs = await prov.describe_video_full(
                str(CLIPS / f"{base}.mp4"),
                prompt,
                model,
                transcript=transcript,
                chunk_seconds=chunk,
            )
        return {
            "cues": [[round(t, 2), d] for t, d in pairs],
            "error": "",
            "seconds": round(time.monotonic() - started, 1),
        }
    except Exception as e:
        return {
            "cues": [],
            "error": f"{type(e).__name__}: {str(e)[:300]}",
            "seconds": round(time.monotonic() - started, 1),
        }


async def _describe_frames(model: str, clip: str, keys: dict) -> dict:
    """The app's DEFAULT path: frames at 5 fps, similar ones dropped, each
    kept frame described on its own (MainFrame frame mode)."""
    from omni_describer_custom.core.ai_engine import GLMProvider
    from omni_describer_custom.core.prompt_manager import DEFAULT_PROMPTS
    from omni_describer_custom.core.video_processor import VideoProcessor

    started = time.monotonic()
    try:
        folder = BENCH / "frames" / clip
        frames = await VideoProcessor().extract_frames(
            str(CLIPS / f"{clip}.mp4"), fps=5, output_dir=str(folder)
        )
        texts = await GLMProvider(api_key=keys["glm"]).describe_frames_batch(
            [f.path for f in frames], DEFAULT_PROMPTS["default"], model
        )
        cues = [
            [round(f.timestamp, 2), txt.strip()]
            for f, txt in zip(frames, texts, strict=False)
            if txt and not txt.startswith("(error")
        ]
        errors = sum(1 for txt in texts if not txt or txt.startswith("(error"))
        return {
            "cues": cues,
            "error": "" if cues else f"{errors} frame errors",
            "frames": len(frames),
            "frame_errors": errors,
            "seconds": round(time.monotonic() - started, 1),
        }
    except Exception as e:
        return {
            "cues": [],
            "error": f"{type(e).__name__}: {str(e)[:300]}",
            "seconds": round(time.monotonic() - started, 1),
        }


async def _hearing(model: str, keys: dict) -> dict:
    """The truth clip with NO transcript: does the model hear it?"""
    import base64
    from omni_describer_custom.core.ai_engine import GLMProvider

    or_model = "google/gemini-3.8-flash" if model == GEMINI_DIRECT else model
    data = base64.b64encode((CLIPS / "truth.mp4").read_bytes()).decode()
    payload = {
        "model": or_model,
        "max_tokens": 4000,
        "reasoning": {"max_tokens": 1500},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{data}"}},
                    {"type": "text", "text": HEARING_QUESTION},
                ],
            }
        ],
    }
    started = time.monotonic()
    try:
        answer = await GLMProvider(api_key=keys["glm"])._chat(payload, timeout=300)
        return {
            "answer": answer.strip(),
            "error": "",
            "seconds": round(time.monotonic() - started, 1),
        }
    except Exception as e:
        return {
            "answer": "",
            "error": f"{type(e).__name__}: {str(e)[:300]}",
            "seconds": round(time.monotonic() - started, 1),
        }


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
        elif kind == "frame":
            got = await _describe_frames(model, clip, keys)
        else:
            got = await _describe(
                model, clip, keys, None if model.startswith("gemini-") else _transcript(clip)
            )
        async with lock:
            results[key] = got
            _save_results(results)
        shown = got.get("error") or (
            f"{len(got['cues'])} cues" if "cues" in got else got["answer"][:60].replace("\n", " | ")
        )
        print(
            f"{model[:34]:34s} {kind:5s} {clip:16s} run{run} {got['seconds']:6.1f}s  {shown}",
            flush=True,
        )


async def _watch_balance(keys, floor, stop):
    while not stop.is_set():
        left = await _balance(keys["glm"])
        if left is not None and left < floor:
            print(
                f"\nBALANCE ${left:.2f} is below the floor ${floor:.2f}: "
                "stopping after the calls in flight.",
                flush=True,
            )
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
    clips = args.clips.split(",") if args.clips else CLIP_NAMES
    for name in clips:  # transcripts once, before the clock starts
        _transcript(name)
    models = args.models.split(",") if args.models else OPENROUTER_MODELS + [GEMINI_DIRECT]
    modes = args.modes.split(",")
    jobs = ([("hear", "truth", 1)] if "hear" in modes else []) + [
        (kind, clip, run)
        for run in range(1, args.runs + 1)
        for clip in clips
        for kind in (("desc",) if "full" in modes else ())
        + (("frame",) if "frame" in modes and run == 1 else ())
    ]
    results = _load_results()

    async def main():
        before = await _balance(keys["glm"])
        print(
            f"OpenRouter balance before: ${before:.2f}"
            if before is not None
            else "balance unknown",
            flush=True,
        )
        stop, lock = asyncio.Event(), asyncio.Lock()
        watcher = asyncio.ensure_future(_watch_balance(keys, args.floor, stop))
        await asyncio.gather(*[_run_model(m, jobs, keys, results, lock, stop) for m in models])
        stop.set()
        watcher.cancel()
        after = await _balance(keys["glm"])
        if before is not None and after is not None:
            print(
                f"OpenRouter balance after: ${after:.2f} (spent ${before - after:.2f})", flush=True
            )

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
                label = (
                    f"drawtext=fontfile='{FONT}':text='{i:02d}  {t:.0f}s':"
                    "fontsize=22:fontcolor=yellow:box=1:boxcolor=black:x=6:y=6"
                )
                subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-loglevel",
                        "error",
                        "-ss",
                        f"{max(0.0, t + 0.5):.2f}",
                        "-i",
                        str(CLIPS / f"{clip}.mp4"),
                        "-frames:v",
                        "1",
                        "-vf",
                        f"scale=320:180,{label}",
                        str(frame),
                    ],
                    timeout=60,
                )
        count = len(got["cues"])
        cols = 4
        rows = (count + cols - 1) // cols
        sheet = out / f"{clip}__{safe}.jpg"
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-framerate",
                "1",
                "-i",
                str(folder / "%02d.jpg"),
                "-vf",
                f"tile={cols}x{rows}:padding=4",
                "-frames:v",
                "1",
                str(sheet),
            ],
            timeout=120,
        )
        (folder / "cues.txt").write_text(
            "\n".join(f"{i:02d} [{t:6.1f}s] {d}" for i, (t, d) in enumerate(got["cues"])),
            encoding="utf-8",
        )
    print(f"sheets in {out}")
    return 0


# ── scoring (what can be scored without a person) ────────────────

import re  # noqa: E402

# Things the truth clip does not contain: a description naming them
# invented it.
_ABSENT = [
    "person",
    "man",
    "woman",
    "people",
    "girl",
    "boy",
    "animal",
    "dog",
    "cat",
    "car",
    "tree",
    "building",
    "room",
    "door",
    "face",
    "hand",
    "logo",
    "circle",
    "ball",
    "star",
]
# Describing what the listener already hears breaks the AD rules the
# preset gives (pitfall 13).
_AUDIBLE = re.compile(
    r"\b(says?|said|speaks?|speaking|asks?|replies|"
    r"shouts?|music|song|sings?|sound|hear[sd]?|voice|"
    r"narrat\w*)\b",
    re.I,
)
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
    invented = sum(1 for _t, d in cues if any(re.search(rf"\b{w}s?\b", d.lower()) for w in _ABSENT))
    return {
        "events": hits,
        "of": len(TRUTH_VISUAL),
        "timing": round(sum(errors) / len(errors), 1) if errors else None,
        "invented": invented,
    }


def score_hearing(answer: str) -> dict:
    """Heard = a sound reported within 4 s of a real one, named or not
    (Gemini called the bell a "car horn": heard, misnamed)."""
    text = answer.lower()
    sounds = text.split("words:")[0].replace("sounds:", "")
    words = text.split("words:")[-1] if "words:" in text else ""
    items = [s for s in re.split(r"[,;\n]", sounds) if s.strip() and "none" not in s]
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
    return {
        "knock": "knock" in heard,
        "bell": "bell" in heard,
        "named": len(named),
        "word": "pineapple" in words,
        "invented_sounds": invented,
    }


def score_rules(cues: list) -> dict:
    if not cues:
        return {"cues": 0, "long": 0, "audible": 0}
    return {
        "cues": len(cues),
        "long": sum(1 for _t, d in cues if len(d.split()) > 12),
        "audible": sum(1 for _t, d in cues if _AUDIBLE.search(d)),
    }


def cmd_score(_args) -> int:
    results = _load_results()
    models = sorted({k.split("|")[0] for k in results})
    rows = []
    for model in models:
        mine = {k: v for k, v in results.items() if k.startswith(model + "|")}
        hear = next((v for k, v in mine.items() if "|hear|" in k), {})
        h = score_hearing(hear.get("answer", "")) if hear.get("answer") else None
        truth = [
            score_truth(v["cues"]) for k, v in mine.items() if "|desc|truth|" in k and v.get("cues")
        ]
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
        rows.append(
            {
                "model": model,
                "hears": (
                    None
                    if h is None
                    else f"knock {'Y' if h['knock'] else '-'} bell "
                    f"{'Y' if h['bell'] else '-'} word "
                    f"{'Y' if h['word'] else '-'} +{h['invented_sounds']} fake"
                ),
                "truth_events": (
                    f"{sum(t['events'] for t in truth) / len(truth):.1f}/{TRUTH_VISUAL.__len__()}"
                    if truth
                    else "-"
                ),
                "timing_s": (
                    round(
                        sum(t["timing"] for t in truth if t["timing"] is not None)
                        / max(1, sum(1 for t in truth if t["timing"] is not None)),
                        1,
                    )
                    if truth
                    else None
                ),
                "invented": sum(t["invented"] for t in truth),
                "runs_failed": f"{failed}/{len(descs)}",
                "long_pct": round(100 * sum(r["long"] for r in rules) / n),
                "audible_pct": round(100 * sum(r["audible"] for r in rules) / n),
                "run_spread": round(max(spread), 1) if spread else None,
                "mean_s": round(sum(v["seconds"] for v in descs) / max(1, len(descs))),
            }
        )
    out = BENCH / "scores.json"
    out.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    head = [
        "model",
        "hears",
        "truth_events",
        "timing_s",
        "invented",
        "runs_failed",
        "long_pct",
        "audible_pct",
        "run_spread",
        "mean_s",
    ]
    print(" | ".join(head))
    for r in rows:
        print(" | ".join(str(r[h]) for h in head))
    return 0


# ── the ruler: a second model checks each description against frames ──

LABELS = REPO / "tools" / "bench_labels.json"
# Where the frames are taken, relative to the description's time: the
# moment it is placed, and the few seconds it is spoken over.
JUDGE_OFFSETS = (-0.5, 1.0, 2.5, 4.0)
JUDGE_PROMPT = (
    "You check audio descriptions written for a blind viewer. The four "
    "frames were taken from the video at the times printed on them, "
    "starting where this description is placed.\n\n"
    'Description: "{text}"\n\n'
    "Judge ONLY what is visible in these frames. Ignore style.\n"
    "- correct: everything the description states is visible here.\n"
    "- partial: the main point is visible, but a detail is wrong, or it "
    "happens just outside these frames.\n"
    "- wrong: the main thing it states is NOT in these frames (invented, "
    "misidentified, or at a clearly different time).\n"
    'Reply with JSON only: {{"verdict": "correct|partial|wrong", '
    '"reason": "<one short sentence>"}}'
)


def judge_grid(clip: str, t: float, out: Path) -> Path:
    """Four frames around a description's time, labelled, as one image."""
    if out.exists():
        return out
    ffmpeg = find_tool("ffmpeg")
    src = CLIPS / f"{clip.split('@')[0]}.mp4"  # "clip@variant" = same video
    length = float(
        subprocess.run(
            [
                find_tool("ffprobe"),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(src),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout.strip()
        or 0
    )
    tiles = []
    for i, off in enumerate(JUDGE_OFFSETS):
        at = min(max(0.0, t + off), max(0.0, length - 0.1))
        tile = out.with_name(f"{out.stem}_{i}.jpg")
        label = (
            f"drawtext=fontfile='{FONT}':text='{int(at // 60)}\\:{at % 60:04.1f}':"
            "fontsize=26:fontcolor=yellow:box=1:boxcolor=black:x=8:y=8"
        )
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-ss",
                f"{at:.2f}",
                "-i",
                str(src),
                "-frames:v",
                "1",
                "-vf",
                f"scale=480:270,{label}",
                str(tile),
            ],
            timeout=60,
        )
        tiles.append(tile)
    inputs = []
    for tile in tiles:
        inputs += ["-i", str(tile)]
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            *inputs,
            "-filter_complex",
            "[0][1]hstack[a];[2][3]hstack[b];[a][b]vstack",
            "-q:v",
            "4",
            str(out),
        ],
        timeout=60,
    )
    for tile in tiles:
        tile.unlink(missing_ok=True)
    return out


async def _judge_one(judge: str, key: str, text: str, grid: Path, api_key: str) -> dict:
    import base64
    from omni_describer_custom.core.ai_engine import GLMProvider

    data = base64.b64encode(grid.read_bytes()).decode()
    payload = {
        "model": judge,
        "max_tokens": 2000,
        "reasoning": {"max_tokens": 800},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}},
                    {"type": "text", "text": JUDGE_PROMPT.format(text=text)},
                ],
            }
        ],
    }
    try:
        answer = await GLMProvider(api_key=api_key)._chat(payload, timeout=180)
    except Exception as e:
        return {"verdict": "", "reason": f"ERROR {str(e)[:120]}"}
    m = re.search(r"\{.*\}", answer, re.S)
    try:
        got = json.loads(m.group(0)) if m else {}
    except ValueError:
        got = {}
    verdict = str(got.get("verdict", "")).lower().strip()
    if verdict not in ("correct", "partial", "wrong"):
        low = answer.lower()
        verdict = next((v for v in ("wrong", "partial", "correct") if v in low), "")
    return {"verdict": verdict, "reason": str(got.get("reason", answer))[:200]}


def cmd_judge(args) -> int:
    """Judge the hand-labelled descriptions and report agreement."""
    keys = _prepare_config()
    source = REPO / "tools" / args.labels if args.labels else LABELS
    labels = {
        k: v
        for k, v in json.loads(source.read_text(encoding="utf-8")).items()
        if not k.startswith("_")
    }
    run_no = "2" if "blind" in source.name else "1"
    results = _load_results()
    grids = BENCH / "judge_grids"
    grids.mkdir(exist_ok=True)
    store = BENCH / "judgements.json"
    done = json.loads(store.read_text(encoding="utf-8")) if store.exists() else {}
    items = []
    for key in labels:
        clip, rest = key.split("|", 1)
        model, idx = rest.rsplit("|", 1)
        t, text = results[f"{model}|desc|{clip}|{run_no}"]["cues"][int(idx)]
        safe = f"r{run_no}__" + key.replace("/", "_").replace(":", "_").replace("|", "__")
        items.append((key, clip, float(t), text, grids / f"{safe}.jpg"))
    for _key, clip, t, _text, grid in items:
        judge_grid(clip, t, grid)

    async def run():
        sem = asyncio.Semaphore(6)

        async def one(judge, item):
            key, _clip, _t, text, grid = item
            jkey = f"{judge}||{run_no}||{key}"
            if jkey in done and done[jkey].get("verdict"):
                return
            async with sem:
                done[jkey] = await _judge_one(judge, key, text, grid, keys["glm"])

        before = await _balance(keys["glm"])
        await asyncio.gather(*[one(j, it) for j in args.judges.split(",") for it in items])
        after = await _balance(keys["glm"])
        if before is not None and after is not None:
            print(f"spent ${before - after:.3f}")

    asyncio.run(run())
    store.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")

    short = {"correct": "c", "partial": "p", "wrong": "w"}
    for judge in args.judges.split(","):
        pairs = [
            (labels[k], short.get(done.get(f"{judge}||{run_no}||{k}", {}).get("verdict"), "?"))
            for k in labels
        ]
        n = len(pairs)
        exact = sum(1 for a, b in pairs if a == b)
        wrongs = [b for a, b in pairs if a == "w"]
        rights = [b for a, b in pairs if a == "c"]
        caught = sum(1 for b in wrongs if b == "w")
        false_alarm = sum(1 for b in rights if b == "w")
        loose = sum(1 for a, b in pairs if (a == "w") == (b == "w"))
        print(
            f"{judge:32s} exact {exact}/{n} ({100 * exact // n}%)  "
            f"wrong caught {caught}/{len(wrongs)}  "
            f"false 'wrong' on correct {false_alarm}/{len(rights)}  "
            f"wrong-vs-not agreement {100 * loose // n}%  "
            f"unparsed {sum(1 for _, b in pairs if b == '?')}"
        )
    return 0


def cmd_measure(args) -> int:
    """The ruler on EVERY description: share judged wrong, per model.

    Validated first (bench_labels.json, then 30 blind labels): the GLM
    judge never called a correct description wrong (0/83) and caught 13
    of 14 wrong ones. "correct" vs "partial" is fuzzy even between two
    people, so the number to trust is the WRONG rate.
    """
    keys = _prepare_config()
    results = _load_results()
    grids = BENCH / "judge_grids"
    grids.mkdir(exist_ok=True)
    store = BENCH / "judgements.json"
    done = json.loads(store.read_text(encoding="utf-8")) if store.exists() else {}
    items = []
    for rkey, got in results.items():
        model, kind, clip, run = rkey.split("|")
        if kind not in ("desc", "frame") or not got.get("cues"):
            continue
        # Gemini direct only on request (--direct, phase 20.7), and never
        # judged by Gemini itself.
        if model.startswith("gemini-") and not (
            getattr(args, "direct", False) and "gemini" not in args.judge
        ):
            continue
        if args.clips and clip not in args.clips.split(","):
            continue
        for i, (t, text) in enumerate(got["cues"]):
            key = f"{clip}|{model}|{i}" if kind == "desc" else f"{clip}|{model}#frame|{i}"
            safe = f"r{run}__" + key.replace("/", "_").replace(":", "_").replace("|", "__")
            label = model if kind == "desc" else f"{model} [frame]"
            items.append((run, key, label, clip, float(t), text, grids / f"{safe}.jpg"))
    for _r, _k, _m, clip, t, _x, grid in items:
        judge_grid(clip, t, grid)

    async def run_all():
        sem = asyncio.Semaphore(8)

        async def one(item):
            run, key, _m, _c, _t, text, grid = item
            jkey = f"{args.judge}||{run}||{key}"
            if jkey in done and done[jkey].get("verdict"):
                return
            async with sem:
                done[jkey] = await _judge_one(args.judge, key, text, grid, keys["glm"])

        before = await _balance(keys["glm"])
        await asyncio.gather(*[one(it) for it in items])
        after = await _balance(keys["glm"])
        if before is not None and after is not None:
            print(f"spent ${before - after:.3f}")

    asyncio.run(run_all())
    store.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")

    table: dict = {}
    for run, key, model, clip, _t, _x, _g in items:
        v = done.get(f"{args.judge}||{run}||{key}", {}).get("verdict", "?")
        row = table.setdefault(
            model, {"n": 0, "wrong": 0, "partial": 0, "correct": 0, "?": 0, "clips": {}}
        )
        row["n"] += 1
        row[v if v in row else "?"] += 1
        c = row["clips"].setdefault(clip, [0, 0])
        c[0] += 1
        c[1] += v == "wrong"
    out = BENCH / "accuracy.json"
    out.write_text(json.dumps(table, indent=1), encoding="utf-8")
    print(
        f"{'model':34s} {'n':>4s} {'wrong%':>7s} {'partial%':>9s} {'correct%':>9s}   wrong by clip"
    )
    for model, r in sorted(table.items(), key=lambda kv: kv[1]["wrong"] / kv[1]["n"]):
        n = r["n"]
        per = "  ".join(f"{c[:6]} {w}/{t}" for c, (t, w) in sorted(r["clips"].items()))
        print(
            f"{model[:34]:34s} {n:4d} {100 * r['wrong'] / n:6.1f}% "
            f"{100 * r['partial'] / n:8.1f}% {100 * r['correct'] / n:8.1f}%   {per}"
        )
    return 0


# ── phase 16.3: a review pass that moves or drops descriptions ─────

REVIEW_SPAN = 20.0  # seconds either side of the description
REVIEW_TILES = 12  # 4 x 3 sheet
REVIEW_PROMPT = (
    "You check one audio description for a blind viewer. The twelve "
    "frames come from the video, in time order, each labelled with its "
    "time. The description is currently placed at {at}.\n\n"
    'Description: "{text}"\n\n'
    "First: is what it describes visible in the frames within about four "
    "seconds AFTER {at} (where it is placed now)? Then: find the frame "
    "where it is MOST clearly visible. Judge only what you can see; "
    "ignore sound and style.\n"
    'Reply with JSON only: {{"here": true|false, "best": "M:SS.S" '
    'or "none", "why": "<one short sentence>"}}. Use "none" '
    "only if what it describes is visible in NONE of the frames."
)


def review_sheet(clip: str, t: float, out: Path) -> tuple[Path, list[float]]:
    """Twelve labelled frames from t-20 s to t+20 s as one 4x3 image."""
    src = CLIPS / f"{clip.split('@')[0]}.mp4"
    length = float(
        subprocess.run(
            [
                find_tool("ffprobe"),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(src),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout.strip()
        or 0
    )
    step = 2 * REVIEW_SPAN / (REVIEW_TILES - 1)
    times = [
        min(max(0.0, t - REVIEW_SPAN + i * step), max(0.0, length - 0.1))
        for i in range(REVIEW_TILES)
    ]
    if out.exists():
        return out, times
    ffmpeg = find_tool("ffmpeg")
    tiles = []
    for i, at in enumerate(times):
        tile = out.with_name(f"{out.stem}_{i}.jpg")
        label = (
            f"drawtext=fontfile='{FONT}':text='{int(at // 60)}\\:{at % 60:04.1f}':"
            "fontsize=24:fontcolor=yellow:box=1:boxcolor=black:x=6:y=6"
        )
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-ss",
                f"{at:.2f}",
                "-i",
                str(src),
                "-frames:v",
                "1",
                "-vf",
                f"scale=400:225,{label}",
                str(tile),
            ],
            timeout=60,
        )
        tiles.append(tile)
    inputs = []
    for tile in tiles:
        inputs += ["-i", str(tile)]
    rows = ";".join(
        f"[{r * 4}][{r * 4 + 1}][{r * 4 + 2}][{r * 4 + 3}]hstack=4[r{r}]" for r in range(3)
    )
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            *inputs,
            "-filter_complex",
            f"{rows};[r0][r1][r2]vstack=3",
            "-q:v",
            "4",
            str(out),
        ],
        timeout=60,
    )
    for tile in tiles:
        tile.unlink(missing_ok=True)
    return out, times


def _parse_mss(text: str) -> float | None:
    m = re.match(r"\s*(\d+):(\d+(?:\.\d+)?)\s*$", text or "")
    return int(m.group(1)) * 60 + float(m.group(2)) if m else None


async def _review_one(
    model: str, clip: str, t: float, text: str, sheet: Path, times: list[float], api_key: str
) -> dict:
    import base64
    from omni_describer_custom.core.ai_engine import GLMProvider

    data = base64.b64encode(sheet.read_bytes()).decode()
    at = f"{int(t // 60)}:{t % 60:04.1f}"
    payload = {
        "model": model,
        "max_tokens": 2000,
        "temperature": 0,
        "reasoning": {"max_tokens": 800},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}},
                    {"type": "text", "text": REVIEW_PROMPT.format(at=at, text=text)},
                ],
            }
        ],
    }
    try:
        answer = await GLMProvider(api_key=api_key)._chat(payload, timeout=180)
    except Exception as e:
        return {"action": "keep", "why": f"ERROR {str(e)[:100]}"}
    m = re.search(r"\{.*\}", answer, re.S)
    try:
        got = json.loads(m.group(0)) if m else {}
    except ValueError:
        got = {}
    best = str(got.get("best", "")).strip().lower()
    why = str(got.get("why", ""))[:160]
    if best == "none":
        return {"best": "none", "why": why}
    when = _parse_mss(best)
    if when is None:
        return {"best": "", "why": "unparsed: " + answer[:100]}
    # The nearest tile actually shown (the model sometimes rounds).
    when = min(times, key=lambda x: abs(x - when))
    return {"best": round(when, 1), "why": why, "here": got.get("here") in (True, "true", "yes")}


def review_action(r: dict, t: float, back: float, ahead: float) -> tuple:
    """("drop"|"move"|"keep", new time). A description should start AT
    or just before what it describes, so an earlier match moves it back
    even a little; a later match only when it is well ahead."""
    best = r.get("best", "")
    if best == "none":
        return "drop", t
    # v2: already visible where it is -> leave it (v1 moved correct ones
    # to a "clearer" frame and broke them), unless what it describes
    # clearly STARTS earlier: a description should begin at or before it.
    if r.get("here") and not (isinstance(best, (int, float)) and best < t - back):
        return "keep", t
    if not isinstance(best, (int, float)):
        return "keep", t
    if best < t - back or best > t + ahead:
        return "move", float(best)
    return "keep", t


def cmd_review(args) -> int:
    """Phase 16.3 experiment: move or drop each description after looking
    at 40 s of frames around it. Writes a new variant "<clip>@<tag>" that
    `measure` can judge; judgements of unchanged descriptions are copied
    from the base so only what moved is paid for again."""
    keys = _prepare_config()
    results = _load_results()
    sheets = BENCH / "review_sheets"
    sheets.mkdir(exist_ok=True)
    log_path = BENCH / "review_log.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    judgements_path = BENCH / "judgements.json"
    judgements = json.loads(judgements_path.read_text(encoding="utf-8"))
    for clip in args.clips.split(","):
        base_key = f"{args.model}|desc|{clip}|1"
        cues = results[base_key]["cues"]
        jobs = []
        for i, (t, text) in enumerate(cues):
            safe = f"{clip}__{i}".replace("@", "_")
            sheet, times = review_sheet(clip, float(t), sheets / f"{safe}.jpg")
            jobs.append((i, float(t), text, sheet, times))

        async def run_all():
            sem = asyncio.Semaphore(8)

            async def one(job):
                i, t, text, sheet, times = job
                lkey = f"{args.reviewer}|{args.version}|{clip}|{i}"  # noqa: B023 (used in this iteration only)
                if lkey in log:
                    return
                async with sem:
                    log[lkey] = await _review_one(
                        args.reviewer,
                        clip,  # noqa: B023 (used in this iteration only)
                        t,
                        text,
                        sheet,
                        times,
                        keys["glm"],
                    )

            before = await _balance(keys["glm"])
            await asyncio.gather(*[one(j) for j in jobs])  # noqa: B023 (used in this iteration only)
            after = await _balance(keys["glm"])
            if before is not None and after is not None:
                print(f"review spent ${before - after:.3f}", flush=True)

        asyncio.run(run_all())
        log_path.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")

        new_cues, moved, dropped = [], 0, 0
        origin = {}
        for i, (t, text) in enumerate(cues):
            r = log[f"{args.reviewer}|{args.version}|{clip}|{i}"]
            action, nt = review_action(r, float(t), args.back, args.ahead)
            if action == "drop" and not args.no_drop:
                dropped += 1
                continue
            moved += action == "move"
            origin[len(new_cues)] = (i, nt == t)
            new_cues.append([nt, text])
        order = sorted(range(len(new_cues)), key=lambda k: new_cues[k][0])
        variant = f"{clip.split('@')[0]}@{args.tag}"
        results[f"{args.model}|desc|{variant}|1"] = {
            "cues": [new_cues[k] for k in order],
            "error": "",
        }
        # Carry verdicts for descriptions whose time did not change.
        for new_i, k in enumerate(order):
            old_i, same = origin[k]
            if not same:
                continue
            for judge in ("z-ai/glm-5.3-flash", "google/gemini-3.8-flash"):
                src = judgements.get(f"{judge}||1||{clip}|{args.model}|{old_i}")
                if src and src.get("verdict"):
                    judgements[f"{judge}||1||{variant}|{args.model}|{new_i}"] = src
        print(
            f"{clip}: {len(cues)} descriptions -> kept {len(cues) - dropped} "
            f"(moved {moved}), dropped {dropped}  => {variant}",
            flush=True,
        )
    _save_results(results)
    judgements_path.write_text(
        json.dumps(judgements, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return 0


# ── phase 19.B2: snap descriptions to scene changes ──────────────────


def scene_cuts(clip: str, threshold: float) -> list[float]:
    """Times of shot changes (ffmpeg scene score), cached per clip."""
    cache = BENCH / f"cuts_{clip.split('@')[0]}_{threshold}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    src = CLIPS / f"{clip.split('@')[0]}.mp4"
    out = subprocess.run(
        [
            find_tool("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-i",
            str(src),
            "-vf",
            f"select='gt(scene,{threshold})',showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=3600,
    )
    cuts = [float(m.group(1)) for m in re.finditer(r"pts_time:([0-9.]+)", out.stderr)]
    cache.write_text(json.dumps(cuts), encoding="utf-8")
    return cuts


def cmd_snap(args) -> int:
    """Move each description to the nearest scene change within
    --window seconds; writes "<clip>@<tag>" with unchanged verdicts
    carried over, for `measure`."""
    results = _load_results()
    jpath = BENCH / "judgements.json"
    judgements = json.loads(jpath.read_text(encoding="utf-8"))
    for clip in args.clips.split(","):
        cues = results[f"{args.model}|desc|{clip}|{args.run}"]["cues"]
        cuts = scene_cuts(clip, args.threshold)
        new, moved = [], 0
        for i, (t, text) in enumerate(cues):
            near = [c for c in cuts if abs(c - t) <= args.window]
            nt = min(near, key=lambda c: abs(c - t)) if near else t
            moved += abs(nt - t) > 0.05
            new.append([round(nt, 2), text, i])
        new.sort(key=lambda x: x[0])
        variant = f"{clip.split('@')[0]}@{args.tag}"
        results[f"{args.model}|desc|{variant}|1"] = {
            "cues": [[t, x] for t, x, _ in new],
            "error": "",
        }
        for new_i, (t, _x, old_i) in enumerate(new):
            if abs(t - cues[old_i][0]) > 0.05:
                continue
            for judge in ("z-ai/glm-5.3-flash", "google/gemini-3.8-flash"):
                src = judgements.get(f"{judge}||{args.run}||{clip}|{args.model}|{old_i}")
                if src and src.get("verdict"):
                    judgements[f"{judge}||1||{variant}|{args.model}|{new_i}"] = src
        print(f"{clip}: {len(cuts)} cuts, {moved}/{len(cues)} moved => {variant}")
    _save_results(results)
    jpath.write_text(json.dumps(judgements, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


def cmd_compare(args) -> int:
    """Phase 36: one candidate against the baseline, as measure_check reads it.

    --base / --cand are "model@variant" (e.g. gemini-3.1-flash-lite@new,
    gemini-3.7-flash@agentic). Over the given clips and every run that has
    results: wrong_rate (GLM judge verdicts), descriptions per run, and
    seconds per run. off = base, on = candidate.
    """
    import datetime

    results = _load_results()
    store = BENCH / "judgements.json"
    done = json.loads(store.read_text(encoding="utf-8")) if store.exists() else {}
    clips = args.clips.split(",")

    def stats(spec: str) -> dict:
        model, _, variant = spec.partition("@")
        n = wrong = judged = 0
        runs = []
        seconds = []
        per_clip: dict[str, int] = {c: 0 for c in clips}
        for rkey, got in results.items():
            m, kind, clip, run = rkey.split("|")
            base, _, var = clip.partition("@")
            if m != model or kind != "desc" or var != variant or base not in clips:
                continue
            if got.get("error"):
                continue
            per_clip[base] += 1
            runs.append(len(got.get("cues") or []))
            if got.get("seconds"):
                seconds.append(got["seconds"])
            for i in range(len(got.get("cues") or [])):
                v = done.get(f"{args.judge}||{run}||{clip}|{model}|{i}", {}).get("verdict")
                n += 1
                if v:
                    judged += 1
                    wrong += v == "wrong"
        return {
            "wrong_rate": round(100 * wrong / judged, 2) if judged else None,
            "descriptions": round(sum(runs) / len(runs), 2) if runs else None,
            "seconds": round(sum(seconds) / len(seconds), 1) if seconds else None,
            "runs": len(runs),
            "judged": judged,
            "n": n,
            # Review (8 Oct): the FEWEST successful runs of any clip,
            # not the total divided by the clips.
            "runs_per_clip": min(per_clip.values()) if per_clip else 0,
        }

    off, on = stats(args.base), stats(args.cand)
    for side, s in (("base", off), ("cand", on)):
        if s["judged"] != s["n"]:
            print(
                f"NOTE: {side} has {s['n'] - s['judged']} of {s['n']} "
                f"descriptions without a verdict (judge returned nothing)"
            )
    metrics = {
        k: {"off": off[k], "on": on[k]}
        for k in ("wrong_rate", "descriptions", "seconds")
        if off[k] is not None and on[k] is not None
    }
    per_clip_runs = min(off["runs_per_clip"], on["runs_per_clip"])
    out = {
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "runs": per_clip_runs,
        "metrics": metrics,
        "counts": {"off": off, "on": on},
    }
    print(json.dumps(out, indent=1))
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("make-clips")
    run = sub.add_parser("run")
    run.add_argument("--runs", type=int, default=2)
    run.add_argument("--models", default="")
    run.add_argument("--clips", default="", help="comma list; default the five original clips")
    run.add_argument(
        "--modes",
        default="hear,full",
        help="hear, full (whole video) and/or frame (app default frame mode, one run only)",
    )
    run.add_argument(
        "--floor",
        type=float,
        default=1.15,
        help="stop when OpenRouter credit falls below this (video requests fail under $1)",
    )
    frames = sub.add_parser("frames")
    frames.add_argument("--run", type=int, default=1)
    sub.add_parser("score")
    judge = sub.add_parser("judge")
    judge.add_argument(
        "--labels", default="", help="labels file in tools/ (default bench_labels.json)"
    )
    judge.add_argument(
        "--judges",
        default="google/gemini-3.8-flash,z-ai/glm-5.3-flash,google/gemini-3.1-flash-lite",
    )
    measure = sub.add_parser("measure")
    measure.add_argument("--judge", default="z-ai/glm-5.3-flash")
    measure.add_argument("--clips", default="", help="only these clips")
    measure.add_argument(
        "--direct",
        action="store_true",
        help="also judge Gemini-direct runs (not with a Gemini judge)",
    )
    review = sub.add_parser("review")
    review.add_argument("--clips", required=True)
    review.add_argument(
        "--model", default="z-ai/glm-5.3-flash", help="whose descriptions to review"
    )
    review.add_argument("--reviewer", default="z-ai/glm-5.3-flash")
    review.add_argument("--tag", default="review")
    review.add_argument("--back", type=float, default=0.5)
    review.add_argument("--ahead", type=float, default=3.0)
    review.add_argument("--no-drop", action="store_true")
    review.add_argument(
        "--version", default="v2", help="prompt version; answers are cached per version"
    )
    compare = sub.add_parser("compare")
    compare.add_argument("--base", required=True)
    compare.add_argument("--cand", required=True)
    compare.add_argument("--clips", required=True)
    compare.add_argument("--judge", default="z-ai/glm-5.3-flash")
    compare.add_argument("--json", default="")
    snap = sub.add_parser("snap")
    snap.add_argument("--clips", required=True)
    snap.add_argument("--model", default="z-ai/glm-5.3-flash")
    snap.add_argument("--run", default="1")
    snap.add_argument("--window", type=float, default=2.0)
    snap.add_argument("--threshold", type=float, default=0.3)
    snap.add_argument("--tag", default="snap")
    args = parser.parse_args()
    return {
        "make-clips": cmd_make_clips,
        "run": cmd_run,
        "frames": cmd_frames,
        "score": cmd_score,
        "judge": cmd_judge,
        "measure": cmd_measure,
        "review": cmd_review,
        "snap": cmd_snap,
        "compare": cmd_compare,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
