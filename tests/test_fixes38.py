"""Regression round 38: GLM Cancel, sibling batches, part bitrate (v1.7.5).

Left open by the v1.7.4 audit:

  1. GLM Cancel was checked only BETWEEN requests. One part may take
     up to 30 minutes and a timeout is retried, so Cancel could wait
     ~90 minutes. _run_cancellable now abandons the request within
     half a second.
  2. Fast batch mode ran its batches with a bare gather(): when one
     failed the others kept running (and billing) in the background.
  3. Split parts got ~1/n of their upload budget: the budget was
     divided by the part count AND spread over the whole video.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
import io
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")
os.environ.setdefault("ODC_CONFIG_DIR", tempfile.mkdtemp(prefix="odc_t38_"))

from omni_describer_custom.core import ai_engine  # noqa: E402
from omni_describer_custom.core.ai_engine import (  # noqa: E402
    GLMProvider, _run_cancellable)

results: list[tuple[str, bool, str]] = []


def check(name, fn):
    try:
        fn()
        results.append((name, True, ""))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False, str(e)))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def test_cancel_abandons_a_long_request():
    cancelled = {"flag": False, "task_cancelled": False}

    async def slow():
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled["task_cancelled"] = True
            raise

    async def main():
        async def press_cancel():
            await asyncio.sleep(0.3)
            cancelled["flag"] = True
        asyncio.ensure_future(press_cancel())
        await _run_cancellable(slow(), lambda: cancelled["flag"])

    start = time.monotonic()
    try:
        asyncio.run(main())
        raise AssertionError("a cancelled request returned normally")
    except RuntimeError as e:
        assert str(e) == "cancelled", str(e)
    took = time.monotonic() - start
    assert took < 2.0, f"Cancel took {took:.1f}s, not under a second"
    assert cancelled["task_cancelled"], "the request itself kept running"


def test_uncancelled_request_returns_its_result():
    async def quick():
        await asyncio.sleep(0.05)
        return "text"
    assert asyncio.run(_run_cancellable(quick(), lambda: False)) == "text"
    assert asyncio.run(_run_cancellable(quick(), None)) == "text"


def test_glm_part_request_is_cancellable():
    src = Path(ai_engine.__file__).read_text(encoding="utf-8")
    # Whitespace-free, so re-wrapping the call (v1.8.4 added on_sent)
    # does not read as "unwrapped".
    flat = "".join(src.split())
    assert "_run_cancellable(self._chat(payload,timeout=1800.0" in flat, \
        "the long GLM part request is not wrapped for Cancel"


def test_failed_batch_cancels_its_siblings():
    from PIL import Image
    work = Path(tempfile.mkdtemp(prefix="odc_t38_frames_"))
    frames = []
    for i in range(160):          # > 150 per batch -> two batches
        f = work / f"frame_{i:04d}.jpg"
        Image.new("RGB", (8, 8)).save(f)
        frames.append(str(f))

    state = {"calls": 0, "sibling_cancelled": False}

    async def fake_chat(payload, timeout):
        state["calls"] += 1
        if state["calls"] == 1:
            await asyncio.sleep(0.1)
            raise RuntimeError("GLM HTTP 402: no credit")
        try:
            await asyncio.sleep(20)
            return ""
        except asyncio.CancelledError:
            state["sibling_cancelled"] = True
            raise

    prov = GLMProvider(api_key="k")
    prov._chat = fake_chat
    start = time.monotonic()
    try:
        asyncio.run(prov.describe_video_frames_batch(frames, "p"))
        raise AssertionError("a failed batch did not fail the job")
    except RuntimeError as e:
        assert "402" in str(e), str(e)
    assert state["calls"] == 2, f"{state['calls']} batches started"
    assert state["sibling_cancelled"], \
        "the other batch kept running after the job failed"
    assert time.monotonic() - start < 5, "waited for the sibling instead"


def test_split_part_gets_its_whole_budget():
    captured = {}

    class StopHere(Exception):
        pass

    real_popen = subprocess.Popen

    def fake_popen(cmd, *a, **k):
        captured["cmd"] = cmd
        raise StopHere()

    work = Path(tempfile.mkdtemp(prefix="odc_t38_split_"))
    video = work / "v.mp4"
    # 39 MB over 888 s, like the Sintel test film: ~351 kbps source.
    with open(video, "wb") as f:
        f.truncate(39_377_164)
    prov = GLMProvider(api_key="k")
    subprocess.Popen = fake_popen
    try:
        try:
            prov._split_into(video, work, 888.0, 600, None, None, None,
                             keep_resolution=False)
        except StopHere:
            pass
    finally:
        subprocess.Popen = real_popen
    cmd = captured["cmd"]
    kbps = int(cmd[cmd.index("-b:v") + 1].rstrip("k"))
    # v1.7.4 gave 171 kbps; the source itself carries ~354 kbps.
    assert kbps >= 340, f"part bitrate {kbps} kbps is still starved"
    assert kbps <= 360, f"part bitrate {kbps} kbps exceeds the source"


def main() -> int:
    check("Cancel abandons a long request within a second",
          test_cancel_abandons_a_long_request)
    check("an uncancelled request returns its result",
          test_uncancelled_request_returns_its_result)
    check("the GLM part request is wrapped for Cancel",
          test_glm_part_request_is_cancellable)
    check("a failed batch cancels its sibling batches",
          test_failed_batch_cancels_its_siblings)
    check("a split part gets its whole upload budget",
          test_split_part_gets_its_whole_budget)
    failed = [r for r in results if not r[1]]
    print(f"\nRESULT: {len(results) - len(failed)} passed, "
          f"{len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
