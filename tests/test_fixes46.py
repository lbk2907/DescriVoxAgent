"""Regression round 46: a video whose sound ends early kept its length (v1.8.2).

Found while comparing models (29 Sep 2026) on a 60-second clip whose
AUDIO track ran only 9.25 seconds:

  1. GLMProvider measured duration by decoding and reading ffmpeg's last
     "time=". That number depends on the ffmpeg build: the bundled one
     said 60 s, the one on PATH said 9.25 s — and since v1.7.4 every cue
     "past the end" of a part is dropped, so 22 of 23 descriptions
     vanished. Duration now comes from ffprobe metadata first.
  2. It was the PATH ffmpeg because core/tools.py looked for the repo's
     bin/ three folders up (src/bin) instead of four: anything run from
     outside the repo root silently used a different ffmpeg.
"""

import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

if "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
if "pytest" not in sys.modules:
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from omni_describer_custom.core.ai_engine import GLMProvider  # noqa: E402
from omni_describer_custom.core.tools import find_tool  # noqa: E402

results: list[tuple[str, bool]] = []


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def _clip_with_short_audio() -> Path:
    path = Path(tempfile.mkdtemp(prefix="odc_t46_")) / "short_audio.mp4"
    subprocess.run(
        [
            find_tool("ffmpeg"),
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x120:rate=10:duration=12",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        timeout=120,
    )
    return path


def test_short_audio_does_not_shorten_the_video():
    clip = _clip_with_short_audio()
    prov = GLMProvider(api_key="k")
    assert abs(prov._probe_duration(clip) - 12.0) < 0.5, prov._probe_duration(clip)

    # Whatever the decode pass would say, metadata wins.
    prov._run_ffmpeg_cancellable = lambda *a, **k: (0, b"time=00:00:03.00")
    assert abs(prov._probe_duration(clip) - 12.0) < 0.5, (
        "the duration still follows a decode that stopped with the audio"
    )


def test_cues_after_the_sound_ends_are_kept():
    import asyncio

    clip = _clip_with_short_audio()
    prov = GLMProvider(api_key="k")

    async def reply(payload, timeout):
        return "[00:01] start\n[00:06] after the sound ends\n[00:11] near the end"

    prov._chat = reply
    cues = asyncio.run(prov.describe_video_full(str(clip), "p"))
    assert [t for t, _ in cues] == [1.0, 6.0, 11.0], cues


def test_bundled_ffmpeg_is_found_from_any_folder():
    here = os.getcwd()
    os.chdir(tempfile.gettempdir())
    try:
        found = Path(find_tool("ffmpeg"))
    finally:
        os.chdir(here)
    assert found.parent == ROOT / "bin", (
        f"from another folder the app used {found}, not the pinned bin/"
    )


def test_a_busy_service_is_waited_for_and_named():
    import asyncio
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from omni_describer_custom.core import ai_engine as ae

    class Busy(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            body = b'{"error": {"code": 503, "message": "high demand"}}'
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Busy)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    waits = []

    async def no_wait(seconds, is_cancelled=None):
        waits.append(seconds)

    real = ae._sleep_cancellable
    ae._sleep_cancellable = no_wait
    try:
        try:
            asyncio.run(
                ae._http_json(
                    "POST",
                    f"http://127.0.0.1:{server.server_address[1]}/x",
                    label="Gemini",
                    headers={},
                    payload={},
                    timeout=10,
                )
            )
            raise AssertionError("a busy service did not fail the call")
        except RuntimeError as e:
            message = str(e)
    finally:
        ae._sleep_cancellable = real
        server.shutdown()
    assert waits == [5.0, 15.0], f"waited {waits}; a busy service needs longer"
    assert ae.is_busy_error(message), message
    assert not ae.is_busy_error("GLM HTTP 401: invalid key")


def main() -> int:
    check(
        "a short audio track does not shorten the video",
        test_short_audio_does_not_shorten_the_video,
    )
    check("cues after the sound ends are kept", test_cues_after_the_sound_ends_are_kept)
    check(
        "the bundled ffmpeg is found from any folder", test_bundled_ffmpeg_is_found_from_any_folder
    )
    check("a busy service is waited for, and named", test_a_busy_service_is_waited_for_and_named)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
