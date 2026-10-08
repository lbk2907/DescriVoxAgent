"""Stage 4 (optional): TTS narration of the descriptions.

Uses the same engines as the GUI app: edge-tts (online, natural) or
pyttsx3/SAPI5 (offline Windows). Writes one WAV/MP3 per description
for players that read cue audio, plus optional concatenation.
"""
from __future__ import annotations

from pathlib import Path


async def synthesize_events(
    events: list[tuple[float, str]],
    out_dir: str | Path,
    engine: str = "edge",
    voice: str = "ms-MY-OsmanNeural",
    rate: str = "+0%",
) -> list[Path]:
    """Write one audio file per event; returns paths sorted by time.

    engine: "edge" (edge-tts, needs internet) or "sapi" (pyttsx3,
    offline). Files are named cue_%04d.ext in event order.
    """
    out = Path(out_dir)
    if engine not in ("edge", "sapi"):
        raise ValueError(f"unknown TTS engine: {engine}")
    out.mkdir(parents=True, exist_ok=True)
    if not events:
        return []
    if engine == "edge":
        return await _edge(events, out, voice, rate)
    if engine == "sapi":
        return _sapi(events, out)
    raise ValueError(f"unknown TTS engine: {engine}")


async def _edge(events, out: Path, voice: str, rate: str) -> list[Path]:
    import edge_tts
    paths: list[Path] = []
    for i, (_, text) in enumerate(events):
        p = out / f"cue_{i:04d}.mp3"
        await edge_tts.Communicate(text, voice, rate=rate).save(str(p))
        paths.append(p)
    return paths


def _sapi(events, out: Path) -> list[Path]:
    import pyttsx3
    eng = pyttsx3.init()
    paths: list[Path] = []
    try:
        for i, (_, text) in enumerate(events):
            p = out / f"cue_{i:04d}.wav"
            eng.save_to_file(text, str(p))
            eng.runAndWait()
            paths.append(p)
    finally:
        try:
            eng.stop()
        except Exception:
            pass
    return paths


def concat_audio(paths: list[Path], out_path: str | Path) -> Path:
    """Concatenate cue audio files with ffmpeg (gapless narration)."""
    if not paths:
        raise ValueError("no audio paths to concatenate")
    from shutil import which
    import subprocess
    ffmpeg = which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")
    list_file = Path(out_path).with_suffix(".txt")
    list_file.write_text(
        "".join(f"file '{p.as_posix()}'\n" for p in paths), encoding="utf-8")
    subprocess.run(
        [ffmpeg, "-hide_banner", "-y", "-f", "concat", "-safe", "0",
         "-i", str(list_file), "-c", "copy", str(out_path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    list_file.unlink(missing_ok=True)
    return Path(out_path)
