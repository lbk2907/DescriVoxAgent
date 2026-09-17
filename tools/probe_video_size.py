"""Empirical size-limit probe, round 2 (fixed method).

Round 1 flaw: -b:v alone produced 4 MB files regardless of target, so
only the >=5.3 MB payload point was actually verified.

Fix: encode 60 s of pure noise at 1080p (incompressible) and clamp the
output with ffmpeg's -fs flag, which stops the muxer at the exact size.
Duration and frame count stay fixed (60 frames) so prompt tokens stay
~9k per request (<1 cent each). Climb until rejection.
"""
import base64
import io
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

from omni_describer_custom.core.settings_store import SettingsStore

CHAT = "https://openrouter.ai/api/v1/chat/completions"
TMP = Path.home() / "Documents" / "OmniDescriber" / "probe_video"
TMP.mkdir(parents=True, exist_ok=True)

TARGETS_MB = [8, 24, 48, 96, 150]


def make_video(path: Path, target_mb: int) -> float:
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi",
        "-i", "nullsrc=s=1920x1080:r=1",
        "-vf", "noise=alls=100:allf=t",
        "-t", "60",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "0",
        "-pix_fmt", "yuv420p", "-fs", f"{target_mb}M", str(path),
    ], check=True, timeout=1800)
    return path.stat().st_size / 1e6


def main() -> int:
    store = SettingsStore()
    cfg = store.get_ai_provider("glm")
    key = cfg.get("api_key", "")
    model = cfg.get("model") or "z-ai/glm-5.3-flash"
    if not key:
        print("PROBE_FAIL: no glm key")
        return 1

    for target in TARGETS_MB:
        mp4 = TMP / f"probe2_{target}mb.mp4"
        actual = make_video(mp4, target)
        b64 = base64.b64encode(mp4.read_bytes()).decode()
        payload_mb = len(b64) / 1e6
        payload = {
            "model": model,
            "max_tokens": 3000,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": (
                        "Reply with exactly one line in the format "
                        "'[MM:SS] what you see'. Nothing else.")},
                    {"type": "video_url",
                     "video_url": {"url": f"data:video/mp4;base64,{b64}"}},
                ],
            }],
        }
        headers = {"Authorization": f"Bearer {key}",
                   "Content-Type": "application/json"}
        print(f"== target {target}MB -> file {actual:.1f}MB, "
              f"payload {payload_mb:.1f}MB; uploading...", flush=True)
        t0 = time.time()
        try:
            r = requests.post(CHAT, headers=headers, json=payload,
                              timeout=1800)
        except Exception as e:
            print(f"   TRANSPORT ERROR after {time.time() - t0:.0f}s: "
                  f"{type(e).__name__}: {str(e)[:200]}")
            mp4.unlink(missing_ok=True)
            return 0
        dt = time.time() - t0
        try:
            body = r.json()
        except Exception:
            body = {}
        if r.status_code == 200 and "error" not in body:
            usage = body.get("usage", {})
            cost = usage.get("prompt_tokens", 0) * 0.000000075
            print(f"   HTTP 200 in {dt:.0f}s, "
                  f"prompt_tokens={usage.get('prompt_tokens')} "
                  f"(~${cost:.4f})")
            mp4.unlink(missing_ok=True)
            continue
        err = body.get("error", {})
        print(f"   REJECTED HTTP {r.status_code} code={err.get('code')} "
              f"after {dt:.0f}s: {str(err.get('message') or '')[:300]}")
        mp4.unlink(missing_ok=True)
        return 0
    print("ALL TARGETS OK - limit is above "
          f"{TARGETS_MB[-1]}MB files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
