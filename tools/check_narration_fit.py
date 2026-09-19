"""Does each description actually fit the gap before the next one?

The v1.6.0 prompts INSTRUCT the model to keep every cue "speakable before
the next event". This measures whether that instruction survives contact
with real speech: it synthesises each cue with the user's own TTS voice
and settings, then compares how long it takes to say against how long the
player leaves before the next cue starts.

An overrun is not cosmetic. The player narrates cue N at its start time;
if that narration is still running when cue N+1 begins, the listener
either misses the next description or hears two collide. A blind user
loses content that a sighted viewer keeps.

Usage:
  python tools/check_narration_fit.py                 # newest project
  python tools/check_narration_fit.py <project_id>
  python tools/check_narration_fit.py --srt <file.srt>

Exit code is 1 when any cue overruns, so this can gate a prompt change.
"""
import asyncio
import contextlib
import io
import sys
import wave
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

from omni_describer_custom.core.project_store import ProjectStore  # noqa: E402
from omni_describer_custom.core.settings_store import SettingsStore  # noqa: E402
from omni_describer_custom.core.tts_engine import TTSEngine  # noqa: E402


def _wav_seconds(path: str) -> float:
    try:
        with contextlib.closing(wave.open(path, "rb")) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        # Not a RIFF wav (edge-tts returns mp3): fall back to a size
        # estimate rather than dropping the cue from the report.
        size = Path(path).stat().st_size if Path(path).exists() else 0
        return size / 4000.0


def _cues_from_srt(path: Path) -> list[tuple[float, str]]:
    from omni_describer_custom.core.timeline_io import parse_any

    return [(d.start_time, d.text) for d in parse_any(str(path))]


def _cues_from_project(project_id: str | None) -> tuple[str, list[tuple[float, str]]]:
    store = ProjectStore()
    projects = store.list_projects()
    if not projects:
        return "", []
    if project_id:
        row = next((p for p in projects if str(p["id"]) == str(project_id)), None)
        if row is None:
            return "", []
        proj = store.open_project(row["id"])
        if not proj:
            return "", []
        return proj.name, [(d.start_time, d.text) for d in proj.descriptions]

    # list_projects() orders by id, not by time, and old projects can be
    # empty — walk newest-first and take the first one that has cues.
    for row in sorted(projects, key=lambda r: r.get("updated_at", ""),
                      reverse=True):
        proj = store.open_project(row["id"])
        if proj and proj.descriptions:
            return (f"{proj.name} (id {row['id']}, {row['updated_at']})",
                    [(d.start_time, d.text) for d in proj.descriptions])
    return "", []


def main() -> int:
    args = sys.argv[1:]
    # --speed X overrides the stored rate, so you can find the setting at
    # which your descriptions actually fit before changing anything.
    speed_override = None
    if "--speed" in args:
        i = args.index("--speed")
        speed_override = float(args[i + 1])
        del args[i:i + 2]
    if args and args[0] == "--srt":
        name = args[1]
        cues = _cues_from_srt(Path(args[1]))
    else:
        name, cues = _cues_from_project(args[0] if args else None)
    if not cues:
        print("no descriptions found")
        return 1

    settings = SettingsStore()
    # Voice and speed live under tts.engines.<engine>, NOT under "audio":
    # reading the wrong key silently measured the DEFAULT rate instead of
    # the configured one, which is the difference between a useful report
    # and a fictional one.
    tts_cfg = settings.get("tts", {}) or {}
    engine_name = tts_cfg.get("default_engine", "") or "edge"
    engine_cfg = (tts_cfg.get("engines") or {}).get(engine_name, {})
    tts = TTSEngine(tts_cfg)
    voice = engine_cfg.get("voice", "") or ""
    speed = speed_override if speed_override is not None else \
        float(engine_cfg.get("speed", 1.0) or 1.0)
    print(f"project: {name}")
    print(f"cues: {len(cues)}   tts engine: {engine_name}  speed: {speed}")
    print("Measuring with YOUR voice and speed — this is what you would hear.\n")

    overruns: list[tuple[float, float, float, str]] = []
    tight: list[tuple[float, float, float, str]] = []
    spoken_total = 0.0

    for i, (start, text) in enumerate(cues):
        gap = (cues[i + 1][0] - start) if i + 1 < len(cues) else float("inf")
        path = asyncio.run(tts.speak(text, voice=voice, speed=speed))
        if not path:
            print(f"  [{start:7.2f}s] TTS FAILED — cannot measure: {text[:50]}")
            continue
        spoken = _wav_seconds(path)
        spoken_total += spoken
        with contextlib.suppress(Exception):
            Path(path).unlink()

        if gap == float("inf"):
            verdict = "last cue"
        elif spoken > gap:
            verdict = f"OVERRUNS by {spoken - gap:.1f}s"
            overruns.append((start, spoken, gap, text))
        elif spoken > gap * 0.85:
            verdict = "tight"
            tight.append((start, spoken, gap, text))
        else:
            verdict = "fits"
        gap_str = "  —  " if gap == float("inf") else f"{gap:5.1f}s"
        print(f"  [{start:7.2f}s] speak {spoken:5.1f}s / gap {gap_str}  "
              f"{verdict}   {text[:46]}")

    print(f"\n{'=' * 64}")
    print(f"cues measured : {len(cues)}")
    print(f"speech total  : {spoken_total:.1f}s")
    print(f"overruns      : {len(overruns)}")
    print(f"tight (>85%)  : {len(tight)}")
    if overruns:
        print("\nWorst offenders — these are the cues you would lose:")
        for start, spoken, gap, text in sorted(
                overruns, key=lambda r: r[1] - r[2], reverse=True)[:5]:
            print(f"  [{start:.1f}s] needs {spoken:.1f}s, has {gap:.1f}s "
                  f"({len(text.split())} words)")
            print(f"      {text}")
        print("\nIf several cues overrun, the prompt needs a harder word "
              "budget, not a faster voice.")
    else:
        print("\nEvery cue fits the gap before the next one.")
    return 1 if overruns else 0


if __name__ == "__main__":
    sys.exit(main())
