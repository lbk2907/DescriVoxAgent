"""Regression tests round 8: frame lifecycle + whole-pipeline progress.

Real-path tests:
1. Frames are NOT deleted before the AI step (regression for the
   "Opus frame error: Image not found: frame_4987.jpg" bug where
   _cleanup_dir ran between extraction and AI describe).
2. The AI batch loop honours on_progress/is_cancelled (via the AIEngine
   facade; real CustomProvider code path).
3. Progress dialog shows extraction (frame count), AI (done/total) and
   saving phases through a REAL MainFrame and a REAL wx.ProgressDialog,
   including Cancel pressed on the real dialog.
4. Real MainFrame._process_video pipeline: frames copied into the project
   folder and temp dir cleaned only AFTER AI + save.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import sys, io, subprocess, traceback, tempfile, shutil, time
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
        import wx
        app = wx.GetApp() or wx.App(False)
        fn()
        print(f"PASS: {name}")
        ok += 1
    except Exception as e:
        print(f"FAIL: {name}: {e}")
        traceback.print_exc()
        fail += 1

def make_jpeg(path: Path) -> None:
    """Render a REAL 64x64 JPEG with the system ffmpeg."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "color=black:s=64x64:d=0.1", "-frames:v", "1", str(path)],
        capture_output=True, check=True)

from omni_describer_custom.core.ai_engine import AIEngine, CustomProvider
from omni_describer_custom.ui.main_frame import MainFrame

# 1. Frame lifecycle: AI engine reads real files DURING the batch.
def test_frames_alive_through_ai():
    tmp = tempfile.mkdtemp(prefix="frames_alive_")
    try:
        frame_paths = []
        for i in range(4):
            p = Path(tmp) / f"frame_{i:05d}.jpg"
            make_jpeg(p)
            frame_paths.append(str(p))
        assert all(Path(p).exists() for p in frame_paths)

        seen = {"missing": 0, "progress": []}
        calls = {"n": 0}
        prov = CustomProvider.__new__(CustomProvider)

        async def fake_describe_image(image_path, prompt, model=""):
            calls["n"] += 1
            if not Path(image_path).exists():
                seen["missing"] += 1
                raise FileNotFoundError(f"Image not found: {image_path}")
            time.sleep(0.01)
            return f"desc {calls['n']}"

        prov.describe_image = fake_describe_image
        engine = AIEngine.__new__(AIEngine)
        engine.output_lang = ""
        engine._provider_or_raise = lambda name: prov
        engine._default_provider = "custom"

        async def run():
            return await engine.describe_frames(
                frame_paths, "p",
                on_progress=lambda d, t: seen["progress"].append((d, t)),
                is_cancelled=lambda: False,
            )
        descs = asyncio.run(run())
        assert seen["missing"] == 0, f"{seen['missing']} frames missing during AI"
        assert descs == ["desc 1", "desc 2", "desc 3", "desc 4"], descs
        assert seen["progress"] == [(1, 4), (2, 4), (3, 4), (4, 4)], seen["progress"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
check("Frames exist for every AI call; on_progress fires per frame", test_frames_alive_through_ai)

# 2. Cancellation: batch stops early and marks remaining as (cancelled).
def test_ai_cancel_between_frames():
    prov = CustomProvider.__new__(CustomProvider)
    calls = {"n": 0}

    async def fake_describe_image(image_path, prompt, model=""):
        calls["n"] += 1
        return f"d{calls['n']}"

    prov.describe_image = fake_describe_image
    engine = AIEngine.__new__(AIEngine)
    engine.output_lang = ""
    engine._provider_or_raise = lambda name: prov
    engine._default_provider = "custom"

    async def run():
        return await engine.describe_frames(
            [f"f{i}.jpg" for i in range(6)], "p",
            is_cancelled=lambda: calls["n"] >= 2,
        )
    descs = asyncio.run(run())
    assert descs[:2] == ["d1", "d2"], descs
    assert descs[2:] == ["(cancelled)"] * 4, descs
    assert calls["n"] == 2, calls  # no AI calls after cancel
check("AI batch stops between frames on cancel; remaining marked", test_ai_cancel_between_frames)

# 3. Real MainFrame + real wx dialog: per-phase messages and Cancel.
#    KNOWN CONSTRAINT (honest): this wx build's ProgressDialog is fully
#    native - no Python-visible child buttons, so the physical Cancel
#    button cannot be clicked programmatically. We therefore simulate the
#    click at wx's documented boundary (Update() returning False IS the
#    "user pressed Cancel" signal) on the REAL dialog object, and the
#    end-to-end real-cancel behaviour of the same dialog is already
#    proven against a real yt-dlp kill in test_fixes7.
def test_dialog_phases_via_real_frame():
    import wx
    from omni_describer_custom.i18n.strings import t
    app = wx.GetApp()
    frame = MainFrame()
    msgs = {}
    try:
        frame._ensure_download_progress()
        dlg = frame._dl_dialog
        # v1.9.6: the dialog says the phase (the bar is the progress);
        # the counts are in the status bar, read on demand.
        frame._frame_count_tick(1234)
        assert dlg.GetMessage() == t("status.extracting_frames"), dlg.GetMessage()
        msgs["extract"] = frame.GetStatusBar().GetStatusText()
        frame._ai_progress_tick(7, 120)
        assert dlg.GetMessage() == t("status.analyzing"), dlg.GetMessage()
        msgs["ai"] = frame.GetStatusBar().GetStatusText()
        frame._download_progress_tick_text(t("download.saving"), -1)
        msgs["save"] = dlg.GetMessage()
        # User presses Cancel: wx Update() now returns False.
        orig_update = dlg.Update
        dlg.Update = lambda *a, **k: (False, False)
        frame._ai_progress_tick(8, 120)
        assert getattr(frame, "_ai_cancelled", False) is True, "Cancel not detected"
        dlg.Update = orig_update
        frame._close_download_progress()
        assert frame._dl_dialog is None
    finally:
        try:
            frame.Destroy()
        except Exception:
            pass
    assert "1234" in msgs["extract"], msgs["extract"]
    assert "7/120" in msgs["ai"], msgs["ai"]
    assert "Saving" in msgs["save"] or "Menyimpan" in msgs["save"], msgs["save"]
check("Real dialog: frame count, AI done/total, saving text, Cancel handling", test_dialog_phases_via_real_frame)

# 4. Real MainFrame._process_video: frames copied to project folder, temp
#    dir cleaned only at the end, descriptions reference copied frames.
def test_full_pipeline_copies_frames():
    import wx
    app = wx.GetApp()
    frame = MainFrame()
    tmp_src = tempfile.mkdtemp(prefix="odc8_src_")
    proj_dir = tempfile.mkdtemp(prefix="odc8_proj_")
    try:
        src = Path(tmp_src) / "video.mp4"
        src.write_bytes(b"\x00\x00\x00\x18ftypmp42")

        # Real jpegs used as extracted frames.
        real_frame = Path(tmp_src) / "sample.jpg"
        make_jpeg(real_frame)
        jpeg = real_frame.read_bytes()

        class FakeInfo:
            width, height, duration = 640, 360, 12.0

        class FakeFrame:
            def __init__(self, path, ts):
                self.path, self.timestamp = path, ts

        fake_frames = []
        frame_dir = Path(proj_dir) / "fake_extract"
        frame_dir.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            fp = frame_dir / f"frame_{i:05d}.jpg"
            fp.write_bytes(jpeg)
            fake_frames.append(FakeFrame(str(fp), i * 4.0))

        # Stub VideoProcessor instance used inside _process_video.
        from omni_describer_custom.core.video_processor import VideoProcessor
        vp = VideoProcessor.__new__(VideoProcessor)

        async def gvi(source, **kwargs):
            return FakeInfo()

        # **kwargs so a new argument on the real extract_frames does not
        # fail this stub: v1.6.7 added download_dir and the mismatch
        # surfaced as "no descriptions saved", which names the symptom
        # and hides the cause.
        async def ef(source, fps=5, output_dir="", on_progress=None,
                     is_cancelled=None, **kwargs):
            if on_progress:
                on_progress(None)  # touch the dialog path like download does
            for i in range(3):
                (Path(output_dir) / f"frame_{i:05d}.jpg").write_bytes(jpeg)
            return list(fake_frames)

        vp.get_video_info = gvi
        vp.extract_frames = ef

        import omni_describer_custom.ui.main_frame as mfmod
        orig_vp = mfmod.VideoProcessor
        mfmod.VideoProcessor = lambda *a, **k: vp

        # AI stub that FAILS if any frame was deleted before the AI step
        # and reports progress like the real engine now does.
        engine = AIEngine.__new__(AIEngine)
        engine.output_lang = ""
        seen_missing = []
        async def df(frames, prompt, provider="", model="", on_progress=None, is_cancelled=None):
            out = []
            for i, fp in enumerate(frames):
                if not Path(fp).exists():
                    seen_missing.append(fp)
                if on_progress:
                    on_progress(i + 1, len(frames))
                out.append(f"description {i}")
            return out
        engine.describe_frames = df
        frame.ai_engine = engine

        from omni_describer_custom.core.project_store import ProjectStore
        frame.project_store = ProjectStore(projects_dir=str(Path(proj_dir) / "projects"))
        frame.settings = {"general.frame_rate": 5}
        frame._processing = True
        frame._ai_cancelled = False

        import glob
        before = set(glob.glob(str(Path(tempfile.gettempdir()) / "odc_frames_*")))
        frame._process_video(str(src), "describe this")
        mfmod.VideoProcessor = orig_vp

        proj = frame.project_store.current
        assert proj is not None, "project not created"
        assert proj.descriptions, "no descriptions saved"
        assert not seen_missing, f"frames deleted before AI: {seen_missing}"
        for d in proj.descriptions:
            assert Path(d.frame_path).exists(), f"frame missing after run: {d.frame_path}"
            assert "frames" in d.frame_path.replace("/", "\\"), \
                f"not in project frames dir: {d.frame_path}"
        # This run must not leak a NEW temp frames dir (cleaned AFTER save,
        # not before AI). Pre-existing dirs from old sessions are ignored.
        after = set(glob.glob(str(Path(tempfile.gettempdir()) / "odc_frames_*")))
        leaked = after - before
        assert not leaked, f"temp frame dirs leaked by this run: {leaked}"
    finally:
        try:
            frame.Destroy()
        except Exception:
            pass
        shutil.rmtree(tmp_src, ignore_errors=True)
        shutil.rmtree(proj_dir, ignore_errors=True)
check("Real _process_video: frames copied to project, AI sees files, temp cleaned", test_full_pipeline_copies_frames)

print()
print(f"TOTAL: {ok} passed, {fail} failed")
if "pytest" not in sys.modules: sys.exit(1 if fail else 0)
