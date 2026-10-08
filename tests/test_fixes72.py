"""Regression round 72: owner, 6 Oct 2026 - "what is New Project for?"

File > New Project made an EMPTY project that nothing used: describing a
video created another project, Import created its own, and the empty one
stayed in Open Project as "0 descriptions". Now New Project asks for a
name, then for the video (local file, YouTube, direct URL), and the
project is created with that name when Open starts the work.
"""

import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import sys
import tempfile
import traceback
from pathlib import Path

if "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
sys.path.insert(0, "src")

import wx  # noqa: E402

from omni_describer_custom.core.project_store import ProjectStore  # noqa: E402

results: list[tuple[str, bool]] = []
TMP = Path(tempfile.mkdtemp(prefix="odc_t72_"))


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


class FakeText:
    answer = "Kisah Pak Ali"
    ok = True

    def __init__(self, *a, **k):
        pass

    def ShowModal(self):
        return wx.ID_OK if FakeText.ok else wx.ID_CANCEL

    def GetValue(self):
        return FakeText.answer

    def Destroy(self):
        pass


class FakeChoice:
    pick = 0

    def __init__(self, parent, message, caption, choices):
        FakeChoice.seen = (message, list(choices))

    def ShowModal(self):
        return wx.ID_OK if FakeChoice.pick >= 0 else wx.ID_CANCEL

    def GetSelection(self):
        return FakeChoice.pick

    def Destroy(self):
        pass


def frame():
    from omni_describer_custom.ui.main_frame import MainFrame

    f = MainFrame()
    f.project_store = ProjectStore(projects_dir=str(TMP / f"p{id(f)}"))
    f._speak_progress = lambda text: None
    return f


def with_fakes(fn):
    real = (wx.TextEntryDialog, wx.SingleChoiceDialog)
    wx.TextEntryDialog, wx.SingleChoiceDialog = FakeText, FakeChoice
    try:
        fn()
    finally:
        wx.TextEntryDialog, wx.SingleChoiceDialog = real


def test_name_then_video_then_the_named_project():
    def run():
        f = frame()
        try:
            video = str(TMP / "clip.mp4")
            Path(video).write_bytes(b"x")
            f._on_local_file = lambda e: setattr(f, "_current_source", video)
            FakeText.ok, FakeChoice.pick = True, 0
            f._on_new_project(None)
            assert "Kisah Pak Ali" in FakeChoice.seen[0], FakeChoice.seen
            assert len(FakeChoice.seen[1]) == 3
            assert f.project_store.list_projects() == [], "an empty project was made"
            assert f._pending_project_name == (video, "Kisah Pak Ali")
            assert f._current_source == video
            f._ensure_project_for(video)
            projects = f.project_store.list_projects()
            assert [p["name"] for p in projects] == ["Kisah Pak Ali"], projects
            assert f._pending_project_name is None
        finally:
            f.Destroy()

    with_fakes(run)


def test_cancelled_source_changes_nothing():
    def run():
        f = frame()
        try:
            f._current_source = "earlier.mp4"
            f._on_youtube_url = lambda e: None  # the URL box cancelled
            FakeText.ok, FakeChoice.pick = True, 1
            f._on_new_project(None)
            assert f._current_source == "earlier.mp4"
            assert not getattr(f, "_pending_project_name", None)
            assert f.project_store.list_projects() == []
            FakeChoice.pick = -1  # the source list cancelled
            f._on_new_project(None)
            FakeText.ok = False  # the name box cancelled
            f._on_new_project(None)
            assert f.project_store.list_projects() == []
        finally:
            FakeText.ok = True
            f.Destroy()

    with_fakes(run)


def test_the_name_is_only_for_its_own_video():
    def run():
        f = frame()
        try:
            f._on_direct_url = lambda e: setattr(f, "_current_source", "https://a.example/v.mp4")
            FakeChoice.pick = 2
            f._on_new_project(None)
            f._ensure_project_for("https://b.example/other.mp4")
            names = [p["name"] for p in f.project_store.list_projects()]
            assert "Kisah Pak Ali" not in names, names
        finally:
            f.Destroy()

    with_fakes(run)


def main() -> int:
    app = wx.App(False)
    check(
        "a name, then the video, then the named project",
        test_name_then_video_then_the_named_project,
    )
    check("a cancelled step changes nothing", test_cancelled_source_changes_nothing)
    check("the name is only for its own video", test_the_name_is_only_for_its_own_video)
    del app
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
