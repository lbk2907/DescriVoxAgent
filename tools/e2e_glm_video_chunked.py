"""E2E: chunked full-video mode against real OpenRouter.
Reuses the ~71 MB 60 s clip; forces 20 s chunks so the video is split
into ~4 parts, each described in its own request, timestamps offset.
Cost ~0.003 USD."""

import asyncio
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
)
sys.path.insert(0, "src")

from omni_describer_custom.core.ai_engine import AIEngine
from omni_describer_custom.core.settings_store import SettingsStore

BIG = Path.home() / "Documents" / "OmniDescriber" / "probe_video" / "e2e_big_60s.mp4"


def main() -> int:
    if not BIG.exists():
        print("E2E_FAIL: missing big clip (run e2e_glm_video_compress first)")
        return 1
    print(f"input: {BIG.name} = {BIG.stat().st_size / 1e6:.1f} MB")
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
    statuses: list[str] = []
    parts: list[tuple[int, int]] = []

    def status(phase: str) -> None:
        statuses.append(phase)
        print(f"  phase: {phase}")

    def on_part(i: int, n: int) -> None:
        parts.append((i, n))
        print(f"  part {i}/{n}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        pairs = loop.run_until_complete(
            engine.describe_video_full(
                str(BIG),
                "Reply with one line per notable event in [H:MM:SS] format.",
                on_status=status,
                on_part=on_part,
                chunk_seconds=20,
            )
        )
    finally:
        loop.close()
    print(f"statuses: {statuses}")
    print(f"parts: {parts}")
    print(f"pairs: {len(pairs)}")
    for secs, text in pairs[:8]:
        print(f"  {secs:6.1f}s  {text[:70]}")
    assert "splitting" in statuses, statuses
    assert parts and parts[-1] == (parts[-1][1], parts[-1][1]), parts
    assert len(pairs) >= 1, "expected parsed events"
    # Timestamps must be monotonically non-decreasing after merge.
    ts = [t for t, _ in pairs]
    assert ts == sorted(ts), ts
    print("E2E_CHUNKED_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
