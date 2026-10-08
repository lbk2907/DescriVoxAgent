"""Regression tests round 6: YouTube DASH download fix + honest SourceError.

Real-path tests: they run the actual yt-dlp binary against an actual URL
("Me at the zoo", the first YouTube video, 19s — extremely stable and tiny).
No mocks substitute for the real acceptance path.
"""

import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import sys, io, traceback, tempfile, subprocess, shutil
from pathlib import Path

if "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
if "pytest" not in sys.modules:
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
sys.path.insert(0, "src")

import asyncio

ok = 0
fail = 0


def check(name, fn):
    global ok, fail
    try:
        fn()
        print(f"PASS: {name}")
        ok += 1
    except Exception as e:
        print(f"FAIL: {name}: {e}")
        traceback.print_exc()
        fail += 1


from omni_describer_custom.core.video_processor import VideoProcessor, SourceError


# 1. _ytdlp_error_text: baris ERROR sebenar + URL, fallback tanpa ERROR
def test_ytdlp_error_text():
    vp = VideoProcessor(ffmpeg_path="ffmpeg", ytdlp_path="yt-dlp")
    stderr = b"[youtube] xyz: Requested format is not available\r\nERROR: [youtube] xyz: Requested format is not available\r\n"
    msg = vp._ytdlp_error_text("https://youtu.be/xyz", stderr)
    assert "ERROR:" in msg and "xyz" in msg and "https://youtu.be/xyz" in msg, msg
    msg2 = vp._ytdlp_error_text(
        "https://youtu.be/xyz", b"some warning\n", fallback="download failed"
    )
    assert "download failed" in msg2, msg2


check("_ytdlp_error_text surfaces real yt-dlp ERROR line", test_ytdlp_error_text)


# 2. URL mati: extract_frames raise SourceError dengan mesej sebenar (BUKAN [] senyap)
def test_dead_url_raises_sourceerror():
    vp = VideoProcessor(ffmpeg_path="ffmpeg", ytdlp_path="yt-dlp")
    tmp = tempfile.mkdtemp(prefix="vp_dead_")
    try:
        try:
            asyncio.run(vp.extract_frames("https://youtu.be/ZZZZZZZZZZZ", fps=1, output_dir=tmp))
        except SourceError as e:
            assert "ERROR:" in str(e) or "metadata" in str(e), str(e)
            return
        raise AssertionError("expected SourceError for a dead URL, got silent []")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


check("Dead YouTube URL raises SourceError with the real reason", test_dead_url_raises_sourceerror)


# 3. yt-dlp binary hilang: SourceError jelas (bukan senyap, bukan traceback)
def test_missing_ytdlp_binary_clear_error():
    vp = VideoProcessor(ffmpeg_path="ffmpeg", ytdlp_path="Z:/no/such/yt-dlp.exe")
    tmp = tempfile.mkdtemp(prefix="vp_nobin_")
    try:
        try:
            asyncio.run(
                vp.download_video("https://youtu.be/argcheck", out_dir=str(Path(tmp) / "dl"))
            )
        except SourceError as e:
            assert "yt-dlp download failed" in str(e), str(e)
            return
        raise AssertionError("expected SourceError when yt-dlp binary is missing")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


check("Missing yt-dlp binary raises clear SourceError", test_missing_ytdlp_binary_clear_error)

# 4. Metadata URL sebenar melalui get_video_info (yt-dlp --dump-json)
ZOO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo", 19s


def test_url_metadata_real():
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except Exception:
        print("  (yt-dlp not on PATH, skipping)")
        return
    vp = VideoProcessor(ffmpeg_path="ffmpeg", ytdlp_path="yt-dlp")
    info = asyncio.run(vp.get_video_info(ZOO))
    assert info.title, "no title from yt-dlp metadata"
    assert 10.0 < info.duration < 60.0, info.duration  # ~19s


check("get_video_info returns real YouTube metadata", test_url_metadata_real)


# 5. END-TO-END SEBENAR: muat turun YouTube + ekstrak frame dari fail yang dimuat turun
def test_real_youtube_download_and_frames():
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except Exception:
        print("  (yt-dlp not on PATH, skipping)")
        return
    vp = VideoProcessor(ffmpeg_path="ffmpeg", ytdlp_path="yt-dlp")
    tmp = tempfile.mkdtemp(prefix="vp_ytreal_")
    try:
        path = asyncio.run(vp.download_video(ZOO, out_dir=str(Path(tmp) / "dl"), max_height=360))
        assert Path(path).exists() and Path(path).stat().st_size > 100_000, path
        frames = asyncio.run(vp.extract_frames(path, fps=1, output_dir=str(Path(tmp) / "fr")))
        assert len(frames) >= 3, f"expected several frames from a 19s video, got {len(frames)}"
        assert Path(frames[0].path).exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


check("REAL YouTube download + frame extraction end-to-end", test_real_youtube_download_and_frames)

print(f"\nRESULT: {ok} passed, {fail} failed")
if "pytest" not in sys.modules:
    sys.exit(1 if fail else 0)
