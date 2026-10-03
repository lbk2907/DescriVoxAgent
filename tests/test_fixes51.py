"""Regression round 51: small local AV1/HEVC videos go up as H.264 (v1.8.6).

YouTube downloads were already asked for H.264 (pitfall 68) because
MiMo and Nemotron answer "Failed to load video" for AV1. A LOCAL file
under the upload limit was still sent exactly as it was. Split or
compressed videos were already re-encoded; this closes the last path.

Real clips are made with the bundled ffmpeg; only the AI call is
replaced, so what is checked is the file that would actually be sent.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
import io
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")
os.environ.setdefault("ODC_CONFIG_DIR", tempfile.mkdtemp(prefix="odc_t51_"))

from omni_describer_custom.core.ai_engine import GLMProvider  # noqa: E402
from omni_describer_custom.core.tools import find_tool  # noqa: E402

results: list[tuple[str, bool]] = []
TMP = Path(tempfile.mkdtemp(prefix="odc_t51_clips_"))


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def make_clip(name: str, codec_args: list[str]) -> Path:
    out = TMP / name
    subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc=size=320x240:rate=10:duration=4",
                    *codec_args, str(out)], check=True, timeout=180)
    return out


def sent_codec(clip: Path, preserve: bool = False) -> tuple[str, bool]:
    """(codec of what would be uploaded, whether it is the original)."""
    prov = GLMProvider(api_key="k")
    seen = {}

    async def fake_part(path, prompt, model, **kw):
        seen["path"] = Path(path)
        seen["codec"] = prov._video_codec(Path(path))
        return [(0.0, "A test pattern.")]

    prov._describe_one_part = fake_part
    asyncio.run(prov.describe_video_full(str(clip), "describe",
                                         preserve_resolution=preserve))
    return seen["codec"], seen["path"] == clip


def test_av1_goes_up_as_h264():
    clip = make_clip("av1.mkv", ["-c:v", "libsvtav1"])
    assert GLMProvider._video_codec(clip) == "av1"
    codec, original = sent_codec(clip)
    assert codec == "h264" and not original, (codec, original)


def test_hevc_goes_up_as_h264_keeping_resolution():
    clip = make_clip("hevc.mp4", ["-c:v", "libx265", "-x265-params",
                                  "log-level=error"])
    assert GLMProvider._video_codec(clip) == "hevc"
    codec, original = sent_codec(clip, preserve=True)
    assert codec == "h264" and not original, (codec, original)


def test_h264_is_sent_untouched():
    clip = make_clip("h264.mp4", ["-c:v", "libx264"])
    codec, original = sent_codec(clip)
    assert codec == "h264" and original, "an H.264 file was re-encoded"


def main() -> int:
    check("AV1 goes up as H.264", test_av1_goes_up_as_h264)
    check("HEVC goes up as H.264 (preserve resolution)",
          test_hevc_goes_up_as_h264_keeping_resolution)
    check("H.264 is sent untouched", test_h264_is_sent_untouched)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
