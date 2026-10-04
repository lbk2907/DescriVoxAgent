"""Regression round 68: owner, 5 Oct 2026.

"Open Project: after opening, nothing happens." The project was opened
but only a line was written to the status log. Now, with descriptions,
the Player opens (as after describing); a Player still showing another
project is closed first. Both ways of opening a project do this: File >
Open Project, and choosing an existing project for a video picked again.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

if "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
sys.path.insert(0, "src")

import wx  # noqa: E402

from omni_describer_custom.core.project_store import Description, ProjectStore  # noqa: E402
from omni_describer_custom.core.tools import find_tool  # noqa: E402

results: list[tuple[str, bool]] = []
TMP = Path(tempfile.mkdtemp(prefix="odc_t67_"))


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def pump(seconds=1.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        wx.Yield()
        time.sleep(0.02)


def video() -> Path:
    out = TMP / "clip.mp4"
    if not out.exists():
        subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi",
                        "-i", "testsrc=size=160x120:rate=5:duration=6",
                        "-c:v", "libx264", str(out)], check=True, timeout=120)
    return out


def players(frame):
    from omni_describer_custom.ui.player_window import PlayerWindow
    return [c for c in frame.GetChildren()
            if isinstance(c, PlayerWindow) and not c.IsBeingDeleted()]


def frame_with_store():
    from omni_describer_custom.ui.main_frame import MainFrame
    frame = MainFrame()
    frame.project_store = ProjectStore(projects_dir=str(TMP / "projects"))
    return frame


def test_opening_a_described_project_opens_the_player():
    frame = frame_with_store()
    try:
        store = frame.project_store
        store.create_project("Described", str(video()))
        store.set_video_duration(6.0)
        store.save_descriptions([Description(start_time=1.0, end_time=2.0,
                                             text="A test pattern.")])
        frame._after_project_opened(store.current)
        pump(1.5)
        assert len(players(frame)) == 1, "no Player opened"
        # opening another project replaces the Player, never a second one
        store.create_project("Second", str(video()))
        store.save_descriptions([Description(start_time=1.0, end_time=2.0,
                                             text="Another.")])
        frame._after_project_opened(store.current)
        pump(1.5)
        open_now = players(frame)
        assert len(open_now) == 1, f"{len(open_now)} Players open"
        assert "Second" in open_now[0].GetTitle(), open_now[0].GetTitle()
    finally:
        for p in players(frame):
            p.Destroy()
        frame.Destroy()
        pump(0.3)


def test_an_empty_project_says_what_to_do():
    frame = frame_with_store()
    said = []
    real = wx.MessageBox
    wx.MessageBox = lambda msg, *a, **k: said.append(msg) or wx.OK
    try:
        store = frame.project_store
        store.create_project("Empty", str(video()))
        frame._after_project_opened(store.current)
        pump(0.8)
        assert said and "Empty" in said[0], said
        assert not players(frame), "a Player opened for a project with nothing to play"
    finally:
        wx.MessageBox = real
        frame.Destroy()
        pump(0.3)


def test_both_ways_of_opening_use_it():
    src = Path("src/omni_describer_custom/ui/main_frame.py").read_text(encoding="utf-8")
    assert src.count("self._after_project_opened(proj)") == 2


def test_one_description_is_singular():
    """Owner heard "Projek Ujian - 1 descriptions" in Open Project."""
    from omni_describer_custom.i18n.strings import I18n, t
    from omni_describer_custom.ui.main_frame import MainFrame
    old = I18n._current_lang
    try:
        I18n.set_language("en")
        row = {"name": "Clip", "count": 1, "updated_at": "2026-10-05 06:01:00"}
        assert MainFrame._project_list_label(row) == "Clip — 1 description — 05/10/2026 06:01"
        row["count"] = 3
        assert "3 descriptions" in MainFrame._project_list_label(row)
        assert t("main.log_generated", count=1) == "Generated 1 description"
        assert t("main.log_generated", count=0) == "Generated 0 descriptions"
        I18n.set_language("ms")
        assert t("main.log_generated", count=1) == "1 penerangan dijana"
    finally:
        I18n.set_language(old)


def main() -> int:
    app = wx.App(False)
    check("a described project opens the Player (one at a time)",
          test_opening_a_described_project_opens_the_player)
    check("an empty project says what to do", test_an_empty_project_says_what_to_do)
    check("both ways of opening a project use it", test_both_ways_of_opening_use_it)
    check("one description is singular", test_one_description_is_singular)
    del app
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
