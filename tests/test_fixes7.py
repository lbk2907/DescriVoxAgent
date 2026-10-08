"""Regression tests round 7: download progress dialog (percent, MB, speed, ETA).

Real-path tests: parser is validated against lines captured from an ACTUAL
yt-dlp download, and the end-to-end tests run the real yt-dlp binary.
"""

import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import sys, io, traceback, tempfile, subprocess, shutil, time
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


from omni_describer_custom.core.video_processor import VideoProcessor, SourceError, DownloadProgress

ZOO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo", 19s


# 1. Parser: baris SEBENAR dari muat turun yt-dlp (dicap 30 Ogos)
def test_parse_real_lines():
    vp = VideoProcessor(ffmpeg_path="ffmpeg", ytdlp_path="yt-dlp")
    p = vp._parse_ytdlp_progress("[download]   0.5% of  218.53KiB at   62.49KiB/s ETA 00:03")
    assert p is not None, "normal progress line not parsed"
    assert abs(p.percent - 0.5) < 0.001, p.percent
    assert abs(p.total_mb - 218.53 / 1024) < 1e-6, p.total_mb
    assert p.speed == "62.49KiB/s" and p.eta == "00:03", (p.speed, p.eta)
    # Unknown total (tilde): downloaded = total * pct
    p2 = vp._parse_ytdlp_progress("[download]  45.2% of ~ 51.02MiB at 3.51MiB/s ETA 00:10")
    assert p2 is not None and p2.total_mb == -1.0, (p2, p2.total_mb if p2 else None)
    assert abs(p2.downloaded_mb - 51.02 * 45.2 / 100) < 0.01, p2.downloaded_mb
    # Finished line (no ETA)
    p3 = vp._parse_ytdlp_progress("[download] 100% of  246.27KiB in 00:00:00 at 1.61MiB/s")
    assert p3 is not None and p3.percent == 100.0
    # Non-progress lines: ignored
    assert vp._parse_ytdlp_progress("[youtube] abc: Downloading webpage") is None
    assert vp._parse_ytdlp_progress("[download] Destination: C:\\x\\y.f395.mp4") is None
    assert vp._parse_ytdlp_progress('[Merger] Merging formats into "x.mp4"') is None


check("Progress parser handles real yt-dlp lines (KB/MB/tilde/finished)", test_parse_real_lines)


# 2. _format_progress: peratusan + MB + kelajuan + ETA dalam satu baris
def test_format_progress():
    from omni_describer_custom.ui.main_frame import MainFrame

    mf = MainFrame.__new__(MainFrame)  # methods under test touch no wx state
    p = DownloadProgress(
        phase="video",
        percent=45.2,
        downloaded_mb=23.06,
        total_mb=51.02,
        speed="3.51MiB/s",
        eta="00:10",
    )
    line = mf._format_progress(p)
    assert "45.2%" in line, line
    assert "23.1/51.0 MB" in line, line
    assert "3.51MiB/s" in line and "ETA 00:10" in line, line
    line2 = mf._format_progress(
        DownloadProgress(phase="merge", percent=-1, downloaded_mb=-1, total_mb=-1)
    )
    assert "Merging" in line2 or "Menggabung" in line2, line2
    line3 = mf._format_progress(
        DownloadProgress(phase="audio", percent=12.0, downloaded_mb=-1, total_mb=-1)
    )
    assert "12.0%" in line3, line3


check("_format_progress renders percent, MB of MB, speed, ETA", test_format_progress)


# 3. Dialog wx SEBENAR dicipta, dikemas kini dan ditutup melalui kaedah MainFrame
def test_dialog_lifecycle():
    import wx
    from omni_describer_custom.ui.main_frame import MainFrame

    _app = wx.GetApp() or wx.App(False)
    frame = MainFrame()
    try:
        assert frame._dl_dialog is None, "dialog must start closed"
        frame._ensure_download_progress()
        assert frame._dl_dialog is not None, "progress dialog was not created"
        frame._download_progress_tick(
            DownloadProgress(
                phase="video",
                percent=50,
                downloaded_mb=5.0,
                total_mb=10.0,
                speed="1.00MiB/s",
                eta="00:05",
            )
        )
        frame._download_progress_tick(
            DownloadProgress(phase="merge", percent=-1, downloaded_mb=-1, total_mb=-1)
        )
        frame._close_download_progress()
        assert frame._dl_dialog is None
        # Tick selepas tutup: no-op tanpa crash
        frame._download_progress_tick(
            DownloadProgress(phase="video", percent=90, downloaded_mb=9, total_mb=10)
        )
        # Lazy creation lagi sekali selepas tutup
        frame._ensure_download_progress()
        assert frame._dl_dialog is not None
        frame._close_download_progress()
    finally:
        frame._close_download_progress()
        frame.Destroy()


check("Real wx ProgressDialog lifecycle via real MainFrame", test_dialog_lifecycle)


# 4. End-to-end SEBENAR: fasa video+audio dilihat, peratusan naik ke ~100
def test_real_download_progress_events():
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except Exception:
        print("  (yt-dlp not on PATH, skipping)")
        return
    vp = VideoProcessor(ffmpeg_path="ffmpeg", ytdlp_path="yt-dlp")
    tmp = tempfile.mkdtemp(prefix="vp_prog_")
    try:
        events: list[DownloadProgress] = []
        path = asyncio.run(
            vp.download_video(
                ZOO, out_dir=str(Path(tmp) / "dl"), max_height=360, on_progress=events.append
            )
        )
        assert Path(path).exists(), path
        phases = {e.phase for e in events}
        assert "video" in phases and "audio" in phases, phases
        assert max(e.percent for e in events) >= 99.0
        assert any(e.speed for e in events), "no speed reported"
        assert all(-1 <= e.percent <= 100 for e in events)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


check(
    "REAL download reports video+audio phases with rising percent",
    test_real_download_progress_events,
)


# 5. Batal: is_cancelled membunuh proses dengan pantas + mesej jelas
def test_real_download_cancel():
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except Exception:
        print("  (yt-dlp not on PATH, skipping)")
        return
    vp = VideoProcessor(ffmpeg_path="ffmpeg", ytdlp_path="yt-dlp")
    tmp = tempfile.mkdtemp(prefix="vp_cancel_")
    try:
        t0 = time.monotonic()
        try:
            asyncio.run(
                vp.download_video(
                    ZOO, out_dir=str(Path(tmp) / "dl"), max_height=360, is_cancelled=lambda: True
                )
            )
            raise AssertionError("expected SourceError for cancelled download")
        except SourceError as e:
            assert "cancel" in str(e).lower(), str(e)
        elapsed = time.monotonic() - t0
        assert elapsed < 60, f"cancel took {elapsed:.1f}s (process not killed promptly)"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


check("Cancellation kills the download promptly with a clear message", test_real_download_cancel)

print(f"\nRESULT: {ok} passed, {fail} failed")
if "pytest" not in sys.modules:
    sys.exit(1 if fail else 0)
