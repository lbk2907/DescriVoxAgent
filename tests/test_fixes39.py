"""Regression round 39: readable project folders (v1.7.6).

The owner browses projects in File Explorer, where they were only
"project_24", "project_24.db", "project_25"... Each project is now one
folder named after it — "Sintel (48)" — holding project.db and media/.

What can go wrong, each pinned here:
  - the DB stores ABSOLUTE paths to the video and frames; a renamed
    folder without rewriting them leaves the player unable to find the
    video;
  - a folder whose video is open (the player) cannot be renamed on
    Windows; the name must still change and the folder follow later;
  - Windows refuses some names ("CON", "a:b");
  - tests wrote into the owner's real projects folder (14 leftovers).
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import os
import sqlite3
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")
os.environ.setdefault("ODC_CONFIG_DIR", tempfile.mkdtemp(prefix="odc_t39_cfg_"))

from omni_describer_custom.core.project_store import (  # noqa: E402
    Description, ProjectStore)

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


def fresh() -> ProjectStore:
    return ProjectStore(tempfile.mkdtemp(prefix="odc_t39_"))


def test_new_project_gets_a_named_folder():
    s = fresh()
    p = s.create_project("Sintel", "C:/v.mp4")
    folder = s.projects_dir / f"Sintel ({p.id})"
    assert (folder / "project.db").exists(), list(s.projects_dir.iterdir())
    assert s.media_dir(p.id) == folder / "media"
    assert not list(s.projects_dir.glob("project_*")), "old layout written"


def test_windows_unsafe_names():
    lab = ProjectStore.folder_label
    assert lab("CON", 5) == "CON (5)"
    assert lab('a:b/c*d?', 2) == "a b c d (2)"
    assert lab("  trailing dots... ", 3) == "trailing dots (3)"
    assert lab("", 4) == "Video (4)"
    assert lab("x\u202egnp.exe", 6) == "xgnp.exe (6)"
    assert len(lab("y" * 200, 7)) <= 60 + len(" (7)")


def _legacy_project(root: Path, pid: int, name: str) -> Path:
    """Build a project the way v1.7.5 and older stored it."""
    media = root / f"project_{pid}" / "media"
    media.mkdir(parents=True)
    video = media / "video.mp4"
    video.write_bytes(b"VIDEO")
    frame = root / f"project_{pid}" / "frames" / "f1.jpg"
    frame.parent.mkdir()
    frame.write_bytes(b"JPG")
    db = root / f"project_{pid}.db"
    # closing(): sqlite3's own "with" commits but leaves the file open,
    # and an open .db cannot be moved on Windows.
    from contextlib import closing
    with closing(sqlite3.connect(str(db))) as conn:
        conn.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, name "
                     "TEXT, video_path TEXT, video_duration REAL DEFAULT 0, "
                     "provider TEXT DEFAULT '', model TEXT DEFAULT '', "
                     "created_at TEXT, updated_at TEXT, metadata TEXT)")
        conn.execute("CREATE TABLE descriptions (id INTEGER PRIMARY KEY, "
                     "project_id INTEGER, start_time REAL, end_time REAL, "
                     "text TEXT, edited INTEGER DEFAULT 0, created_at TEXT, "
                     "frame_path TEXT DEFAULT '')")
        conn.execute("INSERT INTO projects VALUES (?,?,?,0,'','',?,?,'{}')",
                     (pid, name, str(video), "2026-09-01 10:00:00",
                      "2026-09-01 10:00:00"))
        conn.execute("INSERT INTO descriptions (project_id, start_time, "
                     "end_time, text, frame_path) VALUES (?,1,2,'A cue',?)",
                     (pid, str(frame)))
        conn.commit()
    return video


def test_old_projects_move_and_keep_their_video():
    s = fresh()
    _legacy_project(s.projects_dir, 24, "Me at the zoo")
    assert s.migrate_layout() == 1
    folder = s.projects_dir / "Me at the zoo (24)"
    assert (folder / "project.db").exists()
    assert not (s.projects_dir / "project_24").exists()
    assert not (s.projects_dir / "project_24.db").exists()
    p = s.open_project(24)
    assert Path(p.video_path).exists(), f"video lost: {p.video_path}"
    assert Path(p.video_path).parent == folder / "media"
    assert Path(p.descriptions[0].frame_path).exists(), "frame path stale"
    assert s.migrate_layout() == 0, "a second start moved things again"


def test_rename_moves_folder_and_paths_not_the_date():
    s = fresh()
    _legacy_project(s.projects_dir, 3, "https://youtu.be/x")
    s.migrate_layout()
    before = s.list_projects()[0]["updated_at"]
    assert s.rename_project(3, "Me at the zoo")
    folder = s.projects_dir / "Me at the zoo (3)"
    assert folder.is_dir(), list(s.projects_dir.iterdir())
    p = s.open_project(3)
    assert p.name == "Me at the zoo"
    assert Path(p.video_path).exists(), p.video_path
    assert s.list_projects()[0]["updated_at"] == before, \
        "a rename reordered the Open Project list"


def test_rename_of_an_open_video_follows_later():
    s = fresh()
    _legacy_project(s.projects_dir, 9, "old")
    s.migrate_layout()
    video = s.projects_dir / "old (9)" / "media" / "video.mp4"
    handle = open(video, "rb")          # the player has it open
    try:
        assert s.rename_project(9, "new")
        assert s.open_project(9).name == "new", "the name must change now"
        still_old = (s.projects_dir / "old (9)").is_dir()
    finally:
        handle.close()
    if still_old:                       # Windows refused, as expected
        assert s.migrate_layout() == 1, "next start did not catch up"
    assert (s.projects_dir / "new (9)" / "project.db").exists()
    assert Path(s.open_project(9).video_path).exists()


def test_ids_never_reused_across_layouts():
    s = fresh()
    _legacy_project(s.projects_dir, 7, "a")
    s.migrate_layout()
    p = s.create_project("b", "x")
    assert p.id == 8, p.id
    s.delete_project(8)
    assert not (s.projects_dir / "b (8)").exists(), "delete left the folder"
    assert s.create_project("c", "x").id == 9


def test_list_rows_carry_count_and_newest_first():
    s = fresh()
    a = s.create_project("First", "x")
    s.save_descriptions([Description(start_time=1, end_time=2, text="t"),
                         Description(start_time=3, end_time=4, text="u")])
    time.sleep(1.1)
    s.create_project("Second", "y")
    rows = s.list_projects()
    assert [r["name"] for r in rows] == ["Second", "First"], rows
    assert rows[1]["count"] == 2 and rows[1]["id"] == a.id


def test_tests_can_isolate_the_projects_folder():
    iso = tempfile.mkdtemp(prefix="odc_t39_env_")
    old = os.environ.get("ODC_PROJECTS_DIR")
    os.environ["ODC_PROJECTS_DIR"] = iso
    try:
        assert ProjectStore().projects_dir == Path(iso)
    finally:
        if old is None:
            os.environ.pop("ODC_PROJECTS_DIR", None)
        else:
            os.environ["ODC_PROJECTS_DIR"] = old
    gate = (Path(__file__).parent.parent / "run_gate.bat").read_text()
    assert "set ODC_PROJECTS_DIR=" in gate, "the gate does not isolate projects"


def test_open_dialog_label_and_rename_handler():
    import wx
    os.environ["ODC_PROJECTS_DIR"] = tempfile.mkdtemp(prefix="odc_t39_ui_")
    app = wx.GetApp() or wx.App(False)
    from omni_describer_custom.ui.main_frame import MainFrame
    label = MainFrame._project_list_label(
        {"name": "Sintel", "count": 79, "updated_at": "2026-09-28 11:30:05"})
    assert "Sintel" in label and "79" in label and "28/09/2026 11:30" in label, label

    frame = MainFrame()
    try:
        store = frame.project_store
        p = store.create_project("https://youtu.be/abc", "https://youtu.be/abc")

        class FakeEntry:
            def __init__(self, *a, **k):
                pass

            def ShowModal(self):
                return wx.ID_OK

            def GetValue(self):
                return "Ocang debat"

            def Destroy(self):
                pass

        real = wx.TextEntryDialog
        wx.TextEntryDialog = FakeEntry
        try:
            renamed = frame._rename_project_row({"id": p.id, "name": p.name})
        finally:
            wx.TextEntryDialog = real
        assert renamed, "the Rename handler reported no change"
        assert (store.projects_dir / f"Ocang debat ({p.id})").is_dir()
    finally:
        wx.CallAfter(frame.Destroy)
        for _ in range(20):
            wx.Yield()
        del app


def main() -> int:
    check("a new project gets a named folder", test_new_project_gets_a_named_folder)
    check("names Windows refuses are made safe", test_windows_unsafe_names)
    check("old projects move and keep their video and frames",
          test_old_projects_move_and_keep_their_video)
    check("rename moves the folder, rewrites paths, keeps the date",
          test_rename_moves_folder_and_paths_not_the_date)
    check("renaming a project whose video is open catches up next start",
          test_rename_of_an_open_video_follows_later)
    check("ids are never reused across layouts", test_ids_never_reused_across_layouts)
    check("list rows carry a count, newest first",
          test_list_rows_carry_count_and_newest_first)
    check("tests can isolate the projects folder",
          test_tests_can_isolate_the_projects_folder)
    check("Open Project label and the Rename handler",
          test_open_dialog_label_and_rename_handler)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
