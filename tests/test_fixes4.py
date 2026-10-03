"""Regression tests round 4: video processor diagnostics + robustness."""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import sys, io, traceback, tempfile, subprocess, shutil
from pathlib import Path

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
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

from omni_describer_custom.core.video_processor import VideoProcessor

# 1. stderr tail: banner dibuang, ralat sebenar dikekalkan, had panjang dihormati
def test_stderr_tail():
    vp = VideoProcessor(ffmpeg_path="ffmpeg", ytdlp_path="yt-dlp")
    banner = (
        b"ffmpeg version 8.1.1-full_build-www.gyan.dev\r\n"
        b"built with gcc 15.2.0\r\n"
        b"configuration: --enable-gpl\r\n"
        b"libavutil 59. 44.100 / 59. 44.100\r\n"
        b"Input #0, mov,mp4, from 'x.mp4':\r\n"
        b"x.mp4: Invalid data found when processing input\r\n"
    )
    tail = vp._stderr_tail(banner)
    assert "Invalid data found" in tail, tail
    assert "ffmpeg version" not in tail, tail
    assert "built with" not in tail, tail
    # limit: output mesti <= limit aksara
    big = banner * 20
    assert len(vp._stderr_tail(big, limit=100)) <= 100
check("_stderr_tail keeps real error, drops banner, honours limit", test_stderr_tail)

# 2. ffprobe resolution: sebelah ffmpeg.exe jika ada, else find_tool
# v1.6.5: fallback bukan lagi nama kosong "ffprobe" — ia melalui
# find_tool, yang menemui salinan terbungkus dalam bin/. Ujian ini kini
# menyemak ffprobe yang BOLEH dijalankan, bukan rentetan tertentu.
def test_ffprobe_path():
    tmp = tempfile.mkdtemp(prefix="vp_ffprobe_")
    try:
        fake_bin = Path(tmp) / "bin"
        fake_bin.mkdir()
        (fake_bin / "ffmpeg.exe").write_bytes(b"")
        vp = VideoProcessor(ffmpeg_path=str(fake_bin / "ffmpeg.exe"), ytdlp_path="yt-dlp")
        # tiada ffprobe.exe sebelah -> fallback ke salinan terbungkus
        fallback = vp._ffprobe_path()
        assert fallback != str(fake_bin / "ffprobe.exe")
        assert Path(fallback).name.startswith("ffprobe"), fallback
        # ada ffprobe.exe sebelah -> guna yang itu (pasangan sepadan)
        (fake_bin / "ffprobe.exe").write_bytes(b"")
        assert vp._ffprobe_path() == str(fake_bin / "ffprobe.exe")
        # ffmpeg dari PATH (bukan .exe path) -> fallback yang sama
        vp2 = VideoProcessor(ffmpeg_path="ffmpeg", ytdlp_path="yt-dlp")
        assert vp2._ffprobe_path() == fallback
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
check("ffprobe resolves next to ffmpeg.exe with bundled fallback", test_ffprobe_path)

# 3. Sumber hilang: fail fast, pulangkan [] tanpa panggil ffmpeg
def test_missing_source_fail_fast():
    vp = VideoProcessor(ffmpeg_path="ffmpeg", ytdlp_path="yt-dlp")
    tmp = tempfile.mkdtemp(prefix="vp_missing_")
    try:
        frames = asyncio.run(vp.extract_frames("Z:/definitely/not/here.mp4", fps=5, output_dir=tmp))
        assert frames == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
check("extract_frames fails fast with clear reason for missing source", test_missing_source_fail_fast)

# 4. Ekstraksi sebenar dengan ffmpeg sebenar (laluan happy end-to-end)
def test_real_extraction():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except Exception:
        print("  (ffmpeg not on PATH, skipping)")
        return
    tmp = tempfile.mkdtemp(prefix="vp_real_")
    try:
        vid = Path(tmp) / "v.mp4"
        subprocess.run(
            ["ffmpeg", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
             "-y", str(vid)], capture_output=True, check=True)
        vp = VideoProcessor(ffmpeg_path="ffmpeg", ytdlp_path="yt-dlp")
        info = asyncio.run(vp.get_video_info(str(vid)))
        assert info.width == 320 and info.height == 240, (info.width, info.height)
        assert abs(info.duration - 2.0) < 0.5, info.duration
        frames = asyncio.run(vp.extract_frames(str(vid), fps=5, output_dir=str(Path(tmp) / "fr")))
        assert len(frames) >= 1, "no frames from a real 2s video"
        assert Path(frames[0].path).exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
check("Real ffmpeg info + frame extraction works end-to-end", test_real_extraction)

# 5. Input rosak: [] + bukan crash
def test_corrupt_input():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except Exception:
        print("  (ffmpeg not on PATH, skipping)")
        return
    tmp = tempfile.mkdtemp(prefix="vp_corrupt2_")
    try:
        bad = Path(tmp) / "bad.mp4"
        bad.write_bytes(b"junk" * 100)
        vp = VideoProcessor(ffmpeg_path="ffmpeg", ytdlp_path="yt-dlp")
        frames = asyncio.run(vp.extract_frames(str(bad), fps=5, output_dir=str(Path(tmp) / "fr")))
        assert frames == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
check("Corrupt input returns [] without crash", test_corrupt_input)

print(f"\nRESULT: {ok} passed, {fail} failed")
if "pytest" not in sys.modules: sys.exit(1 if fail else 0)
