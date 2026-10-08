"""Empirical probe: send a small base64 video to OpenRouter via video_url.

Steps:
1. Load the user's GLM (OpenRouter) key from the app's settings store.
2. Check the catalog: does the chosen model accept video input?
3. Generate a tiny synthetic test video with ffmpeg (1 min, 640x360).
4. POST it as a video_url content block and report status/error/usage.

No GUI involved. Prints everything needed to decide size limits.
"""

import base64
import io
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
)
sys.path.insert(0, "src")

from omni_describer_custom.core.settings_store import SettingsStore

CATALOG = "https://openrouter.ai/api/v1/models"
CHAT = "https://openrouter.ai/api/v1/chat/completions"
TMP = Path.home() / "Documents" / "OmniDescriber" / "probe_video"
TMP.mkdir(parents=True, exist_ok=True)


def main() -> int:
    store = SettingsStore()
    key = store.get("ai.providers.glm.api_key", "")
    model = store.get("ai.providers.glm.model", "z-ai/glm-5.3-flash")
    if not key:
        print("PROBE_FAIL: no GLM/OpenRouter key in settings")
        return 1
    print(f"[1] key found ({len(key)} chars), model = {model}")

    # 2. catalog modality check (free, no credit used)
    cat = requests.get(CATALOG, timeout=60).json()
    entry = next((m for m in cat["data"] if m["id"] == model), None)
    if not entry:
        print(f"PROBE_FAIL: model {model} not in catalog")
        return 1
    mods = entry["architecture"]["input_modalities"]
    print(f"[2] catalog input_modalities = {mods}")
    if "video" not in mods:
        print(
            "PROBE_NOTE: catalog says NO video input for this model; "
            "continuing anyway to observe the live error"
        )

    # 3. tiny synthetic video: 60 s, 640x360, 1 fps, h264
    mp4 = TMP / "probe_60s.mp4"
    if not mp4.exists() or mp4.stat().st_size < 10_000:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=60:size=640x360:rate=1",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "30",
                "-pix_fmt",
                "yuv420p",
                str(mp4),
            ],
            check=True,
            timeout=300,
        )
    size_mb = mp4.stat().st_size / 1e6
    print(f"[3] test video: {mp4.name} = {size_mb:.2f} MB")

    b64 = base64.b64encode(mp4.read_bytes()).decode()
    data_url = f"data:video/mp4;base64,{b64}"
    print(f"[4] base64 data URL length = {len(data_url) / 1e6:.2f} MB")

    payload = {
        "model": model,
        "max_tokens": 6000,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "This is a 60-second synthetic test pattern video. "
                            "Reply with 3 short lines, each in the format "
                            "'[MM:SS] description', describing what the pattern "
                            "shows at those moments."
                        ),
                    },
                    {"type": "video_url", "video_url": {"url": data_url}},
                ],
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    t0 = time.time()
    try:
        r = requests.post(CHAT, headers=headers, json=payload, timeout=600)
    except Exception as e:
        print(f"PROBE_TRANSPORT_ERROR after {time.time() - t0:.0f}s: {e!r}")
        return 1
    dt = time.time() - t0
    print(f"[5] HTTP {r.status_code} in {dt:.0f}s, response bytes = {len(r.content)}")
    try:
        body = r.json()
    except Exception:
        print("PROBE_FAIL: non-JSON response:", r.text[:500])
        return 1

    if r.status_code != 200:
        err = body.get("error", {})
        print(f"PROBE_REJECTED: code={err.get('code')} message={err.get('message', '')[:400]}")
        meta = body.get("metadata") or {}
        if meta:
            print(f"    metadata={json.dumps(meta)[:400]}")
        return 1

    msg = body["choices"][0]["message"]
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning") or ""
    usage = body.get("usage", {})
    print("[6] SUCCESS — model reply:")
    print("----")
    print(content[:1200])
    print("----")
    if reasoning:
        print(f"(reasoning field present, {len(reasoning)} chars, preview: {reasoning[:300]!r})")
    print(
        f"usage: prompt={usage.get('prompt_tokens')} "
        f"completion={usage.get('completion_tokens')} "
        f"total={usage.get('total_tokens')} "
        f"details={json.dumps(usage.get('prompt_tokens_details', {}))}"
    )
    print("PROBE_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
