"""E2E: describe_video_full auto-compression path with a real >50MB
video. Generates a ~70 MB 60 s clip (above the verified upload limit),
then verifies: compressing status fires, compressed file passes the
guard, upload succeeds, parsed pairs return. Cost ~0.001 USD."""

import asyncio
import io
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
)
sys.path.insert(0, "src")

from omni_describer_custom.core.ai_engine import AIEngine
from omni_describer_custom.core.settings_store import SettingsStore

TMP = Path.home() / "Documents" / "OmniDescriber" / "probe_video"
TMP.mkdir(parents=True, exist_ok=True)
BIG = TMP / "e2e_big_60s.mp4"


def main() -> int:
    if not BIG.exists() or BIG.stat().st_size < 50 * 1024 * 1024:
        print("generating ~70MB test video (720p noise, 60s)...")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "nullsrc=s=1280x720:r=1",
                "-vf",
                "noise=alls=100:allf=t",
                "-t",
                "60",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "0",
                "-pix_fmt",
                "yuv420p",
                "-fs",
                "70M",
                str(BIG),
            ],
            check=True,
            timeout=1800,
        )
    mb = BIG.stat().st_size / 1e6
    print(f"input: {BIG.name} = {mb:.1f} MB")

    store = SettingsStore()
    cfg = store.get_ai_provider("glm")
    if not cfg.get("api_key"):
        print("E2E_FAIL: no glm key")
        return 1
    engine = AIEngine()
    engine.set_provider(
        "glm",
        api_key=cfg["api_key"],
        base_url=cfg.get("base_url") or "",
        model=cfg.get("model") or "",
    )
    statuses = []

    def status(phase: str) -> None:
        statuses.append(phase)
        print(f"  phase: {phase}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        pairs = loop.run_until_complete(
            engine.describe_video_full(
                str(BIG),
                "Reply with one line per notable event in [H:MM:SS] format.",
                on_status=status,
            )
        )
    finally:
        loop.close()
    print(f"statuses: {statuses}")
    print(f"pairs: {len(pairs)}")
    for secs, text in pairs[:5]:
        print(f"  {secs:6.1f}s  {text[:80]}")
    assert "compressing" in statuses, statuses
    assert len(pairs) >= 1, "expected parsed events"
    print("E2E_COMPRESS_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
