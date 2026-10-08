"""Measure transcription settings against clips, not against opinion.

The local transcript decides where the app believes the silence is,
and v1.6.8 spends that belief: it tells the model how many words fit
in each gap. A transcript that moves between runs moves the budget
with it, so "which settings" stopped being a matter of taste.

What was already measured on ONE 50-second clip, which is not enough
to change a default on:

    base, temperature fallback   segments 14, 33, 13   coverage 92/86/40%
    small, temperature=0 + VAD   segments 24, 24       coverage 77/77%

This runs the same comparison across several clips, including two
built from text-to-speech where the true speech and silence are known
exactly — so accuracy can be measured, not just agreement between
runs.

    python tools/whisper_bench.py --build     # make the clips
    python tools/whisper_bench.py             # run the comparison

Everything lands in %TEMP%/odc_whisper_bench.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

BENCH = Path(os.environ.get("TEMP", "/tmp")) / "odc_whisper_bench"

# Sentences with the silence between them chosen on purpose, so the
# gaps the app must recover are known to the second.
SCRIPTS = {
    "tts_english": {
        "voice": "en-US-AriaNeural",
        "lines": [
            (1.0, "The red car pulls up outside the old house."),
            (9.0, "She opens the gate and walks up the path."),
            (20.0, "Nobody answers the door."),
            (31.0, "She turns around and the lights go out."),
        ],
    },
    "tts_malay": {
        "voice": "ms-MY-OsmanNeural",
        "lines": [
            (1.0, "Kereta merah itu berhenti di hadapan rumah lama."),
            (9.0, "Dia membuka pagar dan berjalan ke pintu."),
            (20.0, "Tiada siapa menjawab."),
            (31.0, "Dia berpaling dan lampu terpadam."),
        ],
    },
}

VAD = {"threshold": 0.3, "min_speech_duration_ms": 100, "speech_pad_ms": 400}

CONFIGS = [
    ("base  current", "base", dict(beam_size=1)),
    (
        "base  temp0+VAD",
        "base",
        dict(
            beam_size=1,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters=VAD,
        ),
    ),
    (
        "small temp0+VAD",
        "small",
        dict(
            beam_size=1,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters=VAD,
        ),
    ),
]

# Whisper's own threshold for "this text is a repeat loop".
COMPRESSION_LIMIT = 2.4
RUNS = 2


# ── Building the clips ───────────────────────────────────────────


async def _speak(text: str, voice: str, out: Path) -> None:
    import edge_tts

    await edge_tts.Communicate(text, voice).save(str(out))


def _ffmpeg() -> str:
    from omni_describer_custom.core.tools import find_tool

    return find_tool("ffmpeg")


def build_tts_clip(name: str, spec: dict) -> Path:
    """Speech at known times over a still picture, silence between."""
    work = BENCH / name
    work.mkdir(parents=True, exist_ok=True)
    pieces = []
    for index, (at, line) in enumerate(spec["lines"]):
        mp3 = work / f"line{index}.mp3"
        if not mp3.exists():
            asyncio.run(_speak(line, spec["voice"], mp3))
        pieces.append((at, mp3))

    # Lay each line at its own start time on one silent track.
    inputs: list[str] = []
    filters: list[str] = []
    for index, (at, mp3) in enumerate(pieces):
        inputs += ["-i", str(mp3)]
        # +1 because input 0 is the still picture; pointing the filter
        # at [0:a] asked the video for an audio track it does not have
        # and ffmpeg failed the whole command.
        filters.append(f"[{index + 1}:a]adelay={int(at * 1000)}|{int(at * 1000)}[d{index}]")
    mix = "".join(f"[d{i}]" for i in range(len(pieces)))
    filters.append(f"{mix}amix=inputs={len(pieces)}:normalize=0[a]")

    out = BENCH / f"{name}.mp4"
    cmd = [
        _ffmpeg(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=navy:s=320x240:d=40",
    ]
    cmd += inputs
    cmd += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "0:v",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-t",
        "40",
        "-shortest",
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    (BENCH / f"{name}.truth.json").write_text(
        json.dumps({"lines": spec["lines"], "duration": 40.0}, indent=2), encoding="utf-8"
    )
    return out


def build_clips(source: str = "") -> list[Path]:
    BENCH.mkdir(parents=True, exist_ok=True)
    built = []
    for name, spec in SCRIPTS.items():
        clip = BENCH / f"{name}.mp4"
        if not clip.exists() or clip.stat().st_size == 0:
            print(f"  building {name} ...", flush=True)
            clip = build_tts_clip(name, spec)
        elif not (BENCH / f"{name}.truth.json").exists():
            # Clip kept, ground truth missing: write it, or the
            # accuracy column reads "-" and nobody notices why.
            (BENCH / f"{name}.truth.json").write_text(
                json.dumps({"lines": spec["lines"], "duration": 40.0}, indent=2), encoding="utf-8"
            )
        built.append(clip)

    # Every other clip already in the folder. Cutting three pieces out
    # of ONE video was the first attempt and it is not a test of
    # anything: the same speaker, the same recording, the same noise.
    # Put genuinely separate videos here instead — different
    # languages, studio against amateur, speech over music.
    names = {c.stem for c in built}
    for clip in sorted(BENCH.glob("*.mp4")):
        if clip.stem not in names and clip.stat().st_size > 0:
            built.append(clip)
    return built


# ── Measuring ────────────────────────────────────────────────────


def transcribe(clip: Path, model_size: str, kw: dict):
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(clip), **kw)
    return [s for s in segments if s.text and s.text.strip()]


def _duration(clip: Path) -> float:
    """Real length, because the clips are no longer all the same."""
    from omni_describer_custom.core.tools import find_tool

    out = subprocess.run(
        [
            find_tool("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(clip),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(out.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        return 60.0


def truth_gaps(name: str) -> list[tuple[float, float]] | None:
    path = BENCH / f"{name}.truth.json"
    if not path.exists():
        return None
    truth = json.loads(path.read_text())
    # Each line is spoken from its start time; treat the spoken span as
    # the words at a measured 2.5 per second, which is how the app
    # itself budgets.
    spans = []
    for at, line in truth["lines"]:
        spans.append((at, at + len(line.split()) / 2.5))
    gaps, cursor = [], 0.0
    for a, b in spans:
        if a - cursor >= 1.0:
            gaps.append((cursor, a))
        cursor = max(cursor, b)
    if truth["duration"] - cursor >= 1.0:
        gaps.append((cursor, truth["duration"]))
    return gaps


def gap_error(found, name: str, duration: float) -> str:
    """How wrong the recovered silence is, where truth is known."""
    expected = truth_gaps(name)
    if expected is None:
        return "  -  "
    from omni_describer_custom.core.timeline_io import silent_gaps

    class S:
        def __init__(self, a, b):
            self.start, self.end = a, b

    got = silent_gaps([S(s.start, s.end) for s in found], 0.0, duration, 1.0)
    # Seconds the app would call silent that are really speech, which
    # is the error that puts a description on top of dialogue.
    wrong = 0.0
    for a, b in got:
        for x, y in [(p, q) for p, q in _speech_spans(name)]:
            wrong += max(0.0, min(b, y) - max(a, x))
    return f"{wrong:4.1f}s"


def _speech_spans(name: str) -> list[tuple[float, float]]:
    path = BENCH / f"{name}.truth.json"
    truth = json.loads(path.read_text())
    return [(at, at + len(line.split()) / 2.5) for at, line in truth["lines"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="only build the clips")
    parser.add_argument("--source", default="", help="a real video to cut extra clips from")
    args = parser.parse_args()

    print("Building clips ...", flush=True)
    clips = build_clips(args.source)
    print(f"  {len(clips)} clips in {BENCH}\n", flush=True)
    if args.build:
        return 0

    print(
        f"{'clip':<14}{'config':<18}{'segments':>12}{'coverage':>16}"
        f"{'spread':>8}{'halluc':>8}{'false silence':>15}{'secs':>7}",
        flush=True,
    )
    print("-" * 100, flush=True)

    for clip in clips:
        duration = _duration(clip)
        for label, size, kw in CONFIGS:
            counts, covs, halluc, errs = [], [], 0, "  -  "
            t0 = time.monotonic()
            for _ in range(RUNS):
                try:
                    found = transcribe(clip, size, kw)
                except Exception as e:
                    print(
                        f"{clip.stem:<14}{label:<18}  ERROR {type(e).__name__}: {str(e)[:40]}",
                        flush=True,
                    )
                    found = []
                counts.append(len(found))
                covs.append(sum(s.end - s.start for s in found) / duration * 100)
                halluc += sum(
                    1 for s in found if getattr(s, "compression_ratio", 0) > COMPRESSION_LIMIT
                )
                errs = gap_error(found, clip.stem, duration)
            spread = max(covs) - min(covs) if covs else 0
            print(
                f"{clip.stem:<14}{label:<18}{str(counts):>12}"
                f"{str([round(c) for c in covs]):>16}{spread:7.0f}pp"
                f"{halluc:8d}{errs:>15}{time.monotonic() - t0:7.0f}",
                flush=True,
            )
        print(flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
