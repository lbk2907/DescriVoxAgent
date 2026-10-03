"""Unit tests for chunked full-video mode (split long videos into
parts, upload part by part, offset timestamps by part start).
Run: python tests/test_chunked_video.py  → prints PASS lines."""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
import base64
import io
import json
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

from omni_describer_custom.core.ai_engine import (
    AIEngine,
    GLMProvider,
    parse_gemini_timestamp_lines,
)


def _make_video(seconds: int) -> str:
    d = tempfile.mkdtemp(prefix="odc_chunktest_")
    out = Path(d) / f"clip{seconds}.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", f"testsrc=duration={seconds}:size=320x240:rate=10",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         str(out)],
        check=True, timeout=120)
    return str(out)


class _Loopback(HTTPServer):
    """Records the last request body for assertions."""
    last_body = None


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        _Loopback.last_body = json.loads(
            self.rfile.read(n).decode("utf-8"))
        # Reply with lines at part-local times 0:01 and 0:03.
        body = {
            "id": "x", "choices": [{"message": {
                "content": "[0:01] part event a\n[0:03] part event b"}}]}
        data = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def main() -> int:
    video = _make_video(7)
    assert Path(video).stat().st_size > 0
    srv = _Loopback(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    threading_ok = __import__("threading").Thread(
        target=srv.serve_forever, daemon=True)
    threading_ok.start()

    eng = AIEngine()
    prov = GLMProvider(api_key="k", base_url=f"http://127.0.0.1:{port}")
    eng._providers["glm"] = prov
    eng.set_default("glm")

    statuses: list[str] = []
    parts: list[tuple[int, int]] = []
    splits: list[float] = []

    async def run() -> list[tuple[float, str]]:
        return await eng.describe_video_full(
            video, "p",
            on_status=statuses.append,
            on_part=lambda i, n: parts.append((i, n)),
            on_split_progress=splits.append,
            chunk_seconds=3,
        )

    pairs = asyncio.new_event_loop().run_until_complete(run())

    # 7 s clip with 2 s forced keyframes → keyframe-aligned parts
    # (verified: 3 parts at offsets 0/4/6). on_part fires per part.
    assert parts and parts[0] == (1, 3), parts
    assert len(parts) == 3, parts
    assert len(pairs) >= 2, pairs
    times = sorted(t for t, _ in pairs)
    assert times[0] == 1.0, times  # part 1 local 0:01 + offset 0
    # At least one pair must come from a later part (offset applied).
    assert any(t > 3.0 for t in times), times
    # The loopback returns fixed part-local lines for every part, so
    # merged times can exceed the true duration; just bound sanity.
    for t, _ in pairs:
        assert 0.0 <= t <= 10.0, (t, pairs)
    # The recorded request must carry a video_url data URL.
    body = _Loopback.last_body
    blocks = body["messages"][0]["content"]
    vids = [b for b in blocks if b.get("type") == "video_url"]
    assert vids and vids[0]["video_url"]["url"].startswith(
        "data:video/mp4;base64,"), "no video_url in request"
    b64 = vids[0]["video_url"]["url"].split(",", 1)[1]
    raw = base64.b64decode(b64)
    # MP4 boxes: 4-byte size then 'ftyp' (brand may be isom/mp42/...).
    assert raw[4:8] == b"ftyp", ("uploaded part is not an mp4", raw[:16])
    # v1.4.1: REAL split progress. ffmpeg out_time ticks fire during the
    # split (0..100 over the whole clip), then each described part adds
    # a tick at 10 + 90*done/total; the FINAL tick must be exactly 100.
    assert splits, "no on_split_progress ticks at all"
    assert splits[-1] == 100.0, splits[-5:]
    assert all(a <= b for a, b in zip(splits, splits[1:])), (
        "non-monotonic split progress", splits)
    # Part-completion ticks must be present: 3 parts → 40, 70, 100
    # (the split phase itself already reaches ~10%).
    for expected in (40.0, 70.0, 100.0):
        assert expected in splits, (expected, splits)
    # At least one REAL ffmpeg out_time tick below 10% must exist.
    assert splits[0] < 10.0, splits
    print("PASS: chunked full-video loopback (parts, offsets, mp4 body)")
    print(f"  parts={parts} times={times}")
    print(f"  split ticks n={len(splits)} last={splits[-1]} part ticks OK")
    srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
