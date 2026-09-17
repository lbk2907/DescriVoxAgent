"""Regression tests round 5: AIEngine first-run errors + SceneExplorer async loading."""
import sys, io, traceback, tempfile, subprocess, shutil, time, asyncio
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
sys.path.insert(0, "src")

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

def pump(app, ms):
    """Pump the real wx event loop."""
    import wx
    end = time.time() + ms / 1000.0
    while time.time() < end:
        wx.Yield()
        time.sleep(0.02)

# 1. First-run AI errors are clear ValueError, bukan KeyError crash
def test_ai_no_provider_clear_error():
    from omni_describer_custom.core.ai_engine import AIEngine
    eng = AIEngine()  # tiada provider dikonfigurasi
    for coro_fn in (
        lambda: eng.describe_frame("x.jpg", "p"),
        lambda: eng.describe_frames(["x.jpg"], "p"),
        lambda: eng.ask("hi"),
        lambda: eng.ask_about_scene("x.jpg", "q"),
    ):
        try:
            asyncio.run(coro_fn())
            raise AssertionError("expected ValueError")
        except ValueError as e:
            assert "No AI provider configured" in str(e), str(e)
check("AIEngine raises clear ValueError without provider (no KeyError)", test_ai_no_provider_clear_error)

# 2. describe_frames dengan provider tak dikonfigurasi: ValueError, bukan KeyError
def test_ai_describe_frames_no_provider():
    from omni_describer_custom.core.ai_engine import AIEngine
    eng = AIEngine()
    try:
        asyncio.run(eng.describe_frames(["a.jpg"], "p", provider="gemini"))
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "gemini" in str(e), str(e)
    except KeyError as e:
        raise AssertionError(f"KeyError leaked to caller: {e}")
check("describe_frames raises clean ValueError for unconfigured provider", test_ai_describe_frames_no_provider)

# 3. SceneExplorer: latar belakang ekstraksi dengan video sebenar
def test_scene_explorer_async_load():
    import wx
    from omni_describer_custom.ui.scene_explorer import SceneExplorer
    from omni_describer_custom.core.ai_engine import AIEngine

    if subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0:
        print("  (ffmpeg not on PATH, skipping)")
        return

    app = wx.GetApp() or wx.App(False)
    tmp = tempfile.mkdtemp(prefix="se_test_")
    try:
        vid = Path(tmp) / "v.mp4"
        subprocess.run(
            ["ffmpeg", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
             "-y", str(vid)], capture_output=True, check=True)

        win = SceneExplorer(None, AIEngine(), str(vid))
        # window harus terus responsif semasa loading (tak sekat)
        pump(app, 300)
        deadline = time.time() + 30
        while time.time() < deadline and not win.frames:
            pump(app, 200)
        assert win.frames, "frames not loaded in background"
        print(f"  loaded {len(win.frames)} frames asynchronously")

        # The bitmap display is set by a SEPARATE UI step after the frames
        # list fills (measured flaky here when asserted immediately), so
        # pump the real event loop until the real widget shows it.
        deadline = time.time() + 10
        while time.time() < deadline and not win.frame_display.GetBitmap().IsOk():
            pump(app, 100)

        # Frame mesti benar-benar dipaparkan (dahulu: blank kerana bug _pil_to_wx)
        bmp = win.frame_display.GetBitmap()
        assert bmp.IsOk(), "frame_display bitmap not ok - frame not shown"
        assert bmp.GetWidth() > 0 and bmp.GetHeight() > 0
        info_label = win.frame_info.GetLabel()
        assert "Frame 1 /" in info_label, info_label

        # tutup: mesti bersihkan dir sementara
        frames_dir = win._frames_dir
        assert frames_dir and Path(frames_dir).exists(), frames_dir
        win.Close()
        pump(app, 300)
        assert not Path(frames_dir).exists(), "temp frames dir not cleaned on close"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
check("SceneExplorer loads frames in background and cleans temp dir", test_scene_explorer_async_load)

# 4. SceneExplorer tanpa video: mesej jelas, tiada crash
def test_scene_explorer_no_video():
    import wx
    from omni_describer_custom.ui.scene_explorer import SceneExplorer
    from omni_describer_custom.core.ai_engine import AIEngine

    app = wx.GetApp() or wx.App(False)
    win = SceneExplorer(None, AIEngine(), "Z:/nope/video.mp4")
    pump(app, 300)
    assert win.frames == []
    label = win.status_text.GetLabel()
    assert "No video" in label or "Could not" in label, label
    win.Close()
    pump(app, 200)
check("SceneExplorer shows clear message without video", test_scene_explorer_no_video)

print(f"\nRESULT: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
