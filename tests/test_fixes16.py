# -*- coding: utf-8 -*-
"""v1.5.1 fixes test suite (unit + real-GUI E2E, zero cost).

Covers:
  1. sanitize_project_name (TITLE -> safe project name)
  2. find_project_by_source (dedupe: same link -> existing project)
  3. Cancel during metadata probe reacts (SourceError 'cancelled')
  4. Cancel during ffmpeg extraction kills the process promptly
  5. _dl_done guards: no ghost dialog re-creation, no player auto-open
     after cancel; _processing_done leaves status Ready
  6. Heartbeat timer exists and stops when done/cancelled
  7. Player slider maps 0..1000 over the REAL duration (9-minute video:
     seek to end must land at ~540s, the old code capped at 100s)
  8. SRT stays standard-format (index, HH:MM:SS,mmm, CRLF) - regression
  9. i18n: new keys exist in both EN and BM
Run: python tests\\test_fixes16.py
"""

from __future__ import annotations

import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

PASS = 0
FAIL = 0
FAIL_NAMES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        FAIL_NAMES.append(name)
        print(f"FAIL {name} {detail}")


# ── 1. sanitize_project_name ────────────────────────────────────────
from omni_describer_custom.core.video_processor import VideoProcessor, SourceError

vp = VideoProcessor()
check(
    "1a sanitize illegal chars",
    VideoProcessor.sanitize_project_name("My: Cool/Video?") == "My Cool Video",
)
check(
    "1b sanitize empty -> fallback",
    VideoProcessor.sanitize_project_name("", fallback="video") == "video",
)
check(
    "1c sanitize only-illegal -> fallback", VideoProcessor.sanitize_project_name("???") == "video"
)
check("1d sanitize length cap 80", len(VideoProcessor.sanitize_project_name("A" * 200)) == 80)
check("1e sanitize trims dots/spaces", VideoProcessor.sanitize_project_name("  Name . ") == "Name")

# ── 2. dedupe ───────────────────────────────────────────────────────
from omni_describer_custom.core.project_store import ProjectStore

tmp_store = tempfile.mkdtemp(prefix="odc_t16_store_")
store = ProjectStore(projects_dir=tmp_store)
p = store.create_project("T16 Project", "https://example.com/watch?v=t16")
row = store.find_project_by_source("https://example.com/watch?v=t16")
check("2a dedupe finds existing", bool(row) and row["id"] == p.id)
check(
    "2b dedupe misses other",
    store.find_project_by_source("https://example.com/watch?v=other") is None,
)


# ── 3. cancel during metadata probe ─────────────────────────────────
async def _t3() -> bool:
    calls = {"n": 0}

    def cancelled() -> bool:
        calls["n"] += 1
        return calls["n"] > 3  # cancel after ~1.5s

    try:
        await vp._probe_url("https://httpbin.org/delay/30", is_cancelled=cancelled)
        return False
    except SourceError as e:
        return "cancel" in str(e).lower()
    except Exception:
        return False


check("3 probe cancel raises cancelled", asyncio.run(_t3()))

LONG_SECONDS = 600


def _long_video() -> str:
    """A 10-minute video made here, so these checks never depend on
    what happens to be in the owner's projects folder.

    They used the owner's Ocong project (project 27) until v1.7.7; once
    that was deleted, 4a/4b and 7a/7b were silently skipped on every
    run. A synthetic clip is made once and reused (low resolution, so
    it takes seconds). Returns "" only if ffmpeg itself is missing.
    """
    from omni_describer_custom.core.tools import find_tool

    path = os.path.join(tempfile.gettempdir(), "odc_t16_long_600s.mp4")
    if os.path.exists(path) and os.path.getsize(path) > 100_000:
        return path
    try:
        subprocess.run(
            [
                find_tool("ffmpeg"),
                "-y",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"testsrc=size=320x240:rate=25:duration={LONG_SECONDS}",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                path,
            ],
            check=True,
            timeout=300,
        )
    except Exception as e:
        print(f"could not make the long test video: {e}")
        return ""
    return path


# ── 4. cancel during ffmpeg extraction kills promptly ───────────────
async def _t4() -> tuple[bool, float]:
    src = _long_video()
    if not src:
        return True, -1.0  # skipped: ffmpeg missing
    out = tempfile.mkdtemp(prefix="odc_t16_ff_")
    state = {"t0": 0.0, "elapsed": 0.0}

    def cancelled() -> bool:
        return time.monotonic() - state["t0"] > 3.0

    async def run():
        state["t0"] = time.monotonic()
        try:
            await vp.extract_frames(src, fps=5, output_dir=out, is_cancelled=cancelled)
            return False  # should NOT return normally
        except SourceError as e:
            state["elapsed"] = time.monotonic() - state["t0"]
            return "cancel" in str(e).lower()
        except Exception:
            return False

    return await run(), state["elapsed"]


ok4, elapsed = asyncio.run(_t4())
if elapsed >= 0:
    check("4a extraction cancel raises cancelled", ok4)
    check("4b extraction cancel fast (<15s)", elapsed < 15.0, f"elapsed={elapsed:.1f}s")
else:
    print("SKIP 4a/4b (ffmpeg missing, no long test video)")


# ── 5+6. GUI: guards, heartbeat, player slider (REAL wx app) ────────
def _t_gui() -> None:
    import wx
    import wx.adv  # noqa: F401  (MainFrame imports wx.adv at module import)
    from omni_describer_custom.ui.main_frame import MainFrame
    from omni_describer_custom.ui.player_window import PlayerWindow

    app = wx.App(False)
    frame = MainFrame()
    frame.Show(False)

    # 6: heartbeat fields exist
    check("6a heartbeat fields", hasattr(frame, "_hb_timer") and hasattr(frame, "_hb_start"))

    # 5a: _ensure_download_progress is a no-op after _dl_done
    frame._dl_done = True
    frame._ensure_download_progress()
    check("5a no ghost dialog after done", frame._dl_dialog is None)

    # 5b: _processing_done after cancel -> status Ready, no player call
    opened = {"n": 0}
    frame._open_player = lambda: opened.__setitem__("n", opened["n"] + 1)  # type: ignore[method-assign]
    frame._dl_cancelled = True
    frame._dl_done = True
    frame._processing_done()
    check("5b status Ready after cancel", frame.GetStatusBar().GetStatusText() == "Ready")
    check("5c no player auto-open after cancel", opened["n"] == 0)

    # 5d: buttons re-enabled after cancel (app stays usable)
    check("5d buttons enabled after cancel", frame.btn_local.Enabled and frame.btn_youtube.Enabled)

    # 7: player slider over the REAL duration of a long video
    long_src = _long_video()
    if long_src:
        long_store = ProjectStore(tempfile.mkdtemp(prefix="odc_t16_prj_"))
        long_store.create_project("Long test video", long_src)
        long_store.set_video_duration(float(LONG_SECONDS))
        win = PlayerWindow(frame, long_store, frame.tts_engine, frame.ai_engine)
        dur = win._slider_dur
        check("7a player slider duration real (>=500s)", dur >= 500.0, f"dur={dur:.1f}")
        # simulate seek to slider end
        win.position_slider.SetValue(win.position_slider.GetMax())  # v1.9.6: seconds
        win._on_seek(None)
        check(
            "7b seek to end lands at duration",
            abs(win._position - dur) < 1.0,
            f"pos={win._position:.1f}",
        )
        win.Destroy()
    else:
        print("SKIP 7a/7b (ffmpeg missing, no long test video)")

    # 8: SRT regression (format standard)
    from omni_describer_custom.core.timeline_io import to_srt, parse_any, Description

    descs = [
        Description(id=1, start_time=0.0, end_time=3.0, text="Hello"),
        Description(id=2, start_time=61.5, end_time=64.0, text="Second"),
    ]
    pth = os.path.join(tempfile.mkdtemp(prefix="odc_t16_srt_"), "a.srt")
    with open(pth, "w", encoding="utf-8") as f:
        f.write(to_srt(descs))
    raw = open(pth, "rb").read()
    cues = parse_any(pth)
    check("8a srt standard timestamps", b"00:01:01,500 --> 00:01:04,000" in raw)
    check("8b srt roundtrip", len(cues) == 2 and abs(cues[1].start_time - 61.5) < 0.01)

    # 9: i18n keys exist (EN current language)
    from omni_describer_custom.i18n.strings import t, I18n  # noqa: F401 (checks the name still exists)

    keys = [
        "project.remove_btn",
        "project.dedupe_open",
        "log.video_saved_at",
        "download.loading_info",
        "process.complete_with_video",
    ]
    check("9 i18n keys present", all(t(k) != k for k in keys))

    frame.Destroy()
    app.Destroy()


try:
    _t_gui()
except Exception:
    traceback.print_exc()
    FAIL += 1
    FAIL_NAMES.append("gui-suite")

# ── summary ─────────────────────────────────────────────────────────
print(f"\nRESULT: PASS={PASS} FAIL={FAIL}")
if FAIL_NAMES:
    print("Failed:", ", ".join(FAIL_NAMES))

# cleanup
shutil.rmtree(tmp_store, ignore_errors=True)
if "pytest" not in sys.modules:
    sys.exit(1 if FAIL else 0)
