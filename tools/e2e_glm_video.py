"""E2E: GLMProvider.describe_video_full against the real OpenRouter API
with the small synthetic video. Verifies the GUI's new send-video path
returns parsed timestamped descriptions. Cost: ~0.1 cents."""
import asyncio
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, "src")

from omni_describer_custom.core.ai_engine import AIEngine
from omni_describer_custom.core.settings_store import SettingsStore

VIDEO = Path.home() / "Documents" / "OmniDescriber" / "probe_video" / "probe_60s.mp4"


def main() -> int:
    store = SettingsStore()
    cfg = store.get_ai_provider("glm")
    if not cfg.get("api_key"):
        print("E2E_FAIL: no glm key")
        return 1
    engine = AIEngine()
    engine.set_provider("glm", api_key=cfg["api_key"],
                        base_url=cfg.get("base_url") or "",
                        model=cfg.get("model") or "")
    statuses = []

    def status(phase: str) -> None:
        statuses.append(phase)
        print(f"  phase: {phase}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        pairs = loop.run_until_complete(engine.describe_video_full(
            str(VIDEO), "Describe what happens in this video.",
            on_status=status))
    finally:
        loop.close()
    print(f"statuses: {statuses}")
    print(f"pairs ({len(pairs)}):")
    for secs, text in pairs:
        print(f"  {secs:6.1f}s  {text[:90]}")
    assert statuses and statuses[0] == "encoding", statuses
    assert len(pairs) >= 3, f"expected >=3 events, got {len(pairs)}"
    times = [p[0] for p in pairs]
    assert times == sorted(times), "events must be time-sorted"
    assert all(t2 >= 0 and t2 <= 65 for t2 in times), times
    print("E2E_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
