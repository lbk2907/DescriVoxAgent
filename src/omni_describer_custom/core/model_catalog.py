"""The OpenRouter model list: what can watch video, what can also hear it.

v1.8.1. "Fetch models" used to list every catalog entry that declared
video input — 85 of them on 28 Sep 2026 — alphabetically, by raw id,
and forgot them when Settings closed. Tested that day by sending each a
6-second clip the way the app sends video:

  - all 13 ":batch" variants fail (HTTP 404: not usable with chat);
  - the 3 routers ("openrouter/auto") pick a model for you, silently;
  - "~...-latest" aliases change without notice;
  - amazon/nova-2-lite-v1 answered "black, white" for red then blue;
  - nothing said which 20 models also HEAR the soundtrack.

So the list is filtered, sorted (hears audio first, then cheapest),
labelled for a screen reader, cached, and a model can be tested with a
short clip before a long video is spent on it (probe_model).
"""

from __future__ import annotations

import base64
import json
import logging
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

CATALOG_URL = "https://openrouter.ai/api/v1/models"
CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
CACHE_NAME = "openrouter_models.json"

# Measured best on the app's own engine: 7 models x 5 different clips,
# every description checked against the frame at its time (29 Sep 2026,
# doc/perbandingan-model.md). GLM is the default; Gemini 3.1 Flash-Lite
# is the best of the models that hear. Listed first and marked in
# Settings, because the plain "hears first, then cheapest" order put the
# two WORST at the top: Nemotron (free; 3 of 8 runs failed) and Gemini
# 2.5 Flash-Lite (heard nothing, invented actions).
RECOMMENDED = ("z-ai/glm-5.3-flash", "google/gemini-3.1-flash-lite")


def recommended_rank(model: str) -> int:
    """Position among the recommended models; len(RECOMMENDED) if not one."""
    return RECOMMENDED.index(model) if model in RECOMMENDED else len(RECOMMENDED)


# Models known to hear a video's audio track, checked with the probe
# (28 Sep 2026: all answered the spoken word). Used when no fetched
# catalog is cached yet.
KNOWN_AUDIO_PREFIXES = (
    "google/gemini",
    "qwen/qwen3.8-omni",
    "qwen/qwen3.5-omni",
    "xiaomi/mimo-v2",
    "nvidia/nemotron-3-nano-omni",
)


def _usable(entry: dict) -> bool:
    mid = entry.get("id") or ""
    mods = (entry.get("architecture") or {}).get("input_modalities") or []
    if "video" not in mods:
        return False
    if mid.endswith(":batch"):
        return False            # 404 on chat/completions
    if mid.startswith("~"):
        return False            # alias: the model behind it changes
    if mid.startswith("openrouter/") or "router" in mid:
        return False            # picks another model for you
    try:
        if float((entry.get("pricing") or {}).get("prompt") or 0) < 0:
            return False        # routers carry a -1 sentinel price
    except (TypeError, ValueError):
        return False
    return True


def _row(entry: dict) -> dict:
    pricing = entry.get("pricing") or {}
    mods = (entry.get("architecture") or {}).get("input_modalities") or []
    return {
        "id": entry["id"],
        "name": entry.get("name") or entry["id"],
        "audio": "audio" in mods,
        "price_in": round(float(pricing.get("prompt") or 0) * 1e6, 4),
        "price_out": round(float(pricing.get("completion") or 0) * 1e6, 4),
        "context": int(entry.get("context_length") or 0),
    }


def parse_catalog(data: dict) -> list[dict]:
    """Usable video models: recommended first, then those that hear
    audio, then cheapest."""
    rows = [_row(e) for e in data.get("data", []) if _usable(e)]
    rows.sort(key=lambda r: (recommended_rank(r["id"]), not r["audio"],
                             r["price_in"], r["id"]))
    return rows


def fetch_catalog(url: str = CATALOG_URL, timeout: float = 60.0) -> list[dict]:
    request = urllib.request.Request(
        url, headers={"User-Agent": "OmniDescriber", "Accept-Encoding": "identity"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"catalog HTTP {response.status}")
        return parse_catalog(json.loads(response.read().decode("utf-8")))


def _cache_path() -> Path:
    from .settings_store import _get_config_dir
    return _get_config_dir() / CACHE_NAME


def save_cache(models: list[dict]) -> None:
    try:
        _cache_path().write_text(json.dumps(
            {"fetched": time.strftime("%Y-%m-%d"), "models": models},
            indent=1), encoding="utf-8")
    except OSError as e:
        logger.warning("Could not save the model list: %s", e)


def load_cache() -> tuple[list[dict], str]:
    """(models, date fetched) — ([], "") when nothing is cached."""
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
        return list(data.get("models") or []), str(data.get("fetched") or "")
    except (OSError, ValueError):
        return [], ""


def openrouter_model_hears_audio(model: str) -> bool:
    """Whether this OpenRouter model takes in a video's soundtrack.

    A tested answer (Settings > Test this model) wins over the catalog:
    bytedance-seed/seed-2.0-mini is listed without audio input yet
    heard the probe word, 28 Sep 2026.
    """
    model = (model or "").strip()
    if not model:
        return False
    for row in load_cache()[0]:
        if row.get("id") == model:
            if row.get("tested") and row.get("hears") is not None:
                return bool(row["hears"])
            return bool(row.get("audio"))
    return model.startswith(KNOWN_AUDIO_PREFIXES)


def record_probe(model: str, result: dict) -> None:
    """Keep a probe's verdict with the cached list, so the label and the
    audio decision follow what was measured. Errors are not recorded:
    a busy free model says nothing about what it can do."""
    if result.get("error"):
        return
    models, _fetched = load_cache()
    for row in models:
        if row.get("id") == model:
            break
    else:
        row = {"id": model, "name": model, "audio": False,
               "price_in": 0.0, "price_out": 0.0, "context": 0}
        models.append(row)
    row["tested"] = time.strftime("%Y-%m-%d")
    row["sees"] = bool(result.get("sees"))
    row["hears"] = result.get("hears")
    save_cache(models)


# ── Test this model ─────────────────────────────────────────────

PROBE_WORD = "pineapple"
PROBE_QUESTION = (
    "This is a 6-second test video. Answer in exactly two lines and "
    "nothing else:\n"
    "COLOURS: <the two background colours, in the order they appear>\n"
    "WORD: <the secret word the voice says, or NONE if you hear no voice>")


def _speak_to_wav(text: str, path: Path) -> bool:
    """Windows SAPI to a WAV file; False where SAPI is unavailable."""
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            stream = win32com.client.Dispatch("SAPI.SpFileStream")
            stream.Open(str(path), 3)          # SSFMCreateForWrite
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            voice.AudioOutputStream = stream
            voice.Speak(text)
            stream.Close()
        finally:
            pythoncom.CoUninitialize()
        return path.exists() and path.stat().st_size > 1000
    except Exception as e:
        logger.info("No SAPI voice for the model test: %s", e)
        return False


def make_probe_clip(folder: Path) -> tuple[Path, bool]:
    """Red for 3 s, then blue for 3 s; a voice says the probe word when
    Windows can speak. Returns (clip, has_voice)."""
    from .tools import find_tool
    wav = folder / "voice.wav"
    has_voice = _speak_to_wav(f"The secret word is {PROBE_WORD}.", wav)
    clip = folder / "probe.mp4"
    def colour(name: str) -> str:
        return f"color=c={name}:s=320x240:d=3,format=yuv420p"
    cmd = [find_tool("ffmpeg"), "-y", "-loglevel", "error",
           "-f", "lavfi", "-i", colour("red"),
           "-f", "lavfi", "-i", colour("blue")]
    if has_voice:
        cmd += ["-i", str(wav), "-filter_complex",
                "[0][1]concat=n=2:v=1[v];[2]apad=whole_dur=6[a]",
                "-map", "[v]", "-map", "[a]", "-c:a", "aac"]
    else:
        cmd += ["-filter_complex", "[0][1]concat=n=2:v=1[v]", "-map", "[v]"]
    cmd += ["-c:v", "libx264", "-t", "6", str(clip)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    return clip, has_voice


def judge(answer: str, has_voice: bool) -> dict:
    """Read the model's two lines into verdicts."""
    text = (answer or "").lower()
    colours = ""
    word = ""
    for line in text.splitlines():
        if line.strip().startswith("colours") or line.strip().startswith("colors"):
            colours = line.split(":", 1)[-1]
        elif line.strip().startswith("word"):
            word = line.split(":", 1)[-1]
    red, blue = colours.find("red"), colours.find("blue")
    sees = red != -1 and blue != -1 and red < blue
    hears = (PROBE_WORD in word) if has_voice else None
    return {"sees": sees, "hears": hears}


def probe_model(api_key: str, model: str, url: str = CHAT_URL,
                timeout: float = 150.0) -> dict:
    """Send the probe clip to `model`, the way the app sends video.

    Returns {"sees": bool, "hears": bool|None, "answer": str,
    "error": str, "seconds": float}. hears is None when no voice could
    be recorded on this machine. Costs a fraction of a cent.
    """
    folder = Path(tempfile.mkdtemp(prefix="odc_probe_"))
    started = time.monotonic()
    try:
        clip, has_voice = make_probe_clip(folder)
        data = base64.b64encode(clip.read_bytes()).decode()
        body = {"model": model, "max_tokens": 3000, "messages": [{
            "role": "user", "content": [
                {"type": "video_url",
                 "video_url": {"url": f"data:video/mp4;base64,{data}"}},
                {"type": "text", "text": PROBE_QUESTION}]}]}
        request = urllib.request.Request(
            url, json.dumps(body).encode("utf-8"),
            {"Authorization": f"Bearer {api_key}",
             "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                reply = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            try:
                detail = json.loads(detail)["error"]["message"]
            except Exception:
                pass
            return {"sees": False, "hears": None, "answer": "",
                    "error": f"HTTP {e.code}: {str(detail)[:160]}",
                    "seconds": time.monotonic() - started}
        choices = reply.get("choices") or []
        answer = ((choices[0].get("message") or {}).get("content") or ""
                  ) if choices else ""
        if not answer:
            err = (reply.get("error") or {}).get("message") or "empty reply"
            return {"sees": False, "hears": None, "answer": "",
                    "error": str(err)[:160],
                    "seconds": time.monotonic() - started}
        verdict = judge(answer, has_voice)
        return {**verdict, "answer": answer.strip(), "error": "",
                "seconds": time.monotonic() - started}
    except Exception as e:
        return {"sees": False, "hears": None, "answer": "",
                "error": f"{type(e).__name__}: {str(e)[:160]}",
                "seconds": time.monotonic() - started}
    finally:
        shutil.rmtree(folder, ignore_errors=True)


PICTURE_QUESTION = ("What is the one colour that fills this picture? "
                    "Answer with the colour name only.")


def probe_engine(engine, provider: str, model: str = "") -> dict:
    """"Test this model" for Gemini, MiniMax, OpenAI and Custom (v1.9.2).

    Goes through the app's own engine, so the key, base URL, model and
    upload path are the ones a real job uses. Video providers get the
    same clip and question as the OpenRouter probe; picture providers
    get one red frame. Adds "picture": True for those. Blocking: call
    it from a worker thread.
    """
    import asyncio
    folder = Path(tempfile.mkdtemp(prefix="odc_probe_"))
    started = time.monotonic()
    loop = asyncio.new_event_loop()
    try:
        clip, has_voice = make_probe_clip(folder)
        if engine.watches_video(provider):
            answer = loop.run_until_complete(engine.ask_about_video(
                str(clip), PROBE_QUESTION, provider, model))
            verdict = judge(answer, has_voice)
            picture = False
        else:
            from .tools import find_tool
            frame = folder / "frame.jpg"
            subprocess.run([find_tool("ffmpeg"), "-y", "-loglevel", "error",
                            "-ss", "1", "-i", str(clip), "-frames:v", "1",
                            str(frame)], check=True, capture_output=True,
                           timeout=60)
            answer = loop.run_until_complete(engine.look(
                str(frame), PICTURE_QUESTION, provider, model))
            verdict = {"sees": "red" in (answer or "").lower(), "hears": None}
            picture = True
        if not (answer or "").strip():
            return {"sees": False, "hears": None, "answer": "",
                    "error": "empty reply", "picture": picture,
                    "seconds": time.monotonic() - started}
        return {**verdict, "answer": answer.strip(), "error": "",
                "picture": picture, "seconds": time.monotonic() - started}
    except Exception as e:
        return {"sees": False, "hears": None, "answer": "",
                "error": f"{type(e).__name__}: {str(e)[:160]}",
                "seconds": time.monotonic() - started}
    finally:
        loop.close()
        shutil.rmtree(folder, ignore_errors=True)
