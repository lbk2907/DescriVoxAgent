"""Regression round 21: every main-window handler gets pressed.

Why this suite exists: an audit on 17 Sep 2026 found that NOT ONE of the
main window's menu/button handlers was referenced by any test. The
windows they open were instantiated in tests, but the handlers were not
called — which is exactly how the v1.5.1 dedupe bug survived for months
(_on_preset_open raised AttributeError on a wx API that does not exist
in Phoenix, so the Open button silently did nothing).

A handler that crashes on a missing wx method, a bad kwarg or a renamed
helper cannot be caught by unit-testing the window it was supposed to
open. So every entry point is invoked here for real, with only the modal
dialogs replaced by canned answers, and real files written to temp dirs.
"""
import io
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path

import wx

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

ok = 0
fail = 0
_app = None


def check(name, fn):
    global ok, fail, _app
    try:
        _app = wx.GetApp() or wx.App(False)
        fn()
        print(f"PASS: {name}")
        ok += 1
    except Exception as e:
        print(f"FAIL: {name}: {e}")
        traceback.print_exc()
        fail += 1


@contextmanager
def stub_modals(path: str = "", text: str = "", file_result=None,
                entry_result=None):
    """Answer every modal this app can raise, without showing one.

    Patches the wx module itself (one object shared by every importer),
    and restores it afterwards so a failure cannot leak into later
    checks.
    """
    import wx.adv

    real = {
        "FileDialog": wx.FileDialog,
        "TextEntryDialog": wx.TextEntryDialog,
        "MessageDialog": wx.MessageDialog,
        "MessageBox": wx.MessageBox,
        "AboutBox": wx.adv.AboutBox,
    }
    boxes: list[tuple[str, str]] = []

    class FakeFileDialog:
        def __init__(self, *a, **k):
            pass

        def ShowModal(self):
            return wx.ID_OK if file_result is None else file_result

        def GetPath(self):
            return path

        def GetPaths(self):
            return [path]

        def SetFilterIndex(self, *a):
            pass

        def GetFilterIndex(self):
            return 0

        def Destroy(self):
            pass

    class FakeTextEntryDialog:
        def __init__(self, *a, **k):
            pass

        def ShowModal(self):
            return wx.ID_OK if entry_result is None else entry_result

        def GetValue(self):
            return text

        def SetValue(self, *a):
            pass

        def Destroy(self):
            pass

    class FakeMessageDialog:
        def __init__(self, *a, **k):
            pass

        def SetYesNoCancelLabels(self, *a):
            pass

        def SetYesNoLabels(self, *a):
            pass

        def ShowModal(self):
            return wx.ID_CANCEL

        def Destroy(self):
            pass

    def fake_messagebox(message="", caption="", *a, **k):
        boxes.append((str(caption), str(message)))
        return wx.OK

    wx.FileDialog = FakeFileDialog
    wx.TextEntryDialog = FakeTextEntryDialog
    wx.MessageDialog = FakeMessageDialog
    wx.MessageBox = fake_messagebox
    wx.adv.AboutBox = lambda *a, **k: None
    try:
        yield boxes
    finally:
        wx.FileDialog = real["FileDialog"]
        wx.TextEntryDialog = real["TextEntryDialog"]
        wx.MessageDialog = real["MessageDialog"]
        wx.MessageBox = real["MessageBox"]
        wx.adv.AboutBox = real["AboutBox"]


def _frame():
    """A MainFrame with its project store pointed at a temp dir."""
    from omni_describer_custom.core.project_store import ProjectStore
    from omni_describer_custom.ui.main_frame import MainFrame

    f = MainFrame()
    f.project_store = ProjectStore(
        projects_dir=tempfile.mkdtemp(prefix="odc_f21_proj_"))
    return f


def _close(f):
    app = wx.GetApp()
    for _ in range(6):
        app.ProcessPendingEvents()
        app.Yield()
    try:
        f.Destroy()
    except Exception:
        pass
    for _ in range(4):
        app.ProcessPendingEvents()
        app.Yield()


def _seed_descriptions(f, name="Demo"):
    from omni_describer_custom.core.project_store import Description

    f.project_store.create_project(name, "demo.mp4")
    f.project_store.add_description(
        Description(start_time=0.0, end_time=2.0, text="First cue"))
    f.project_store.add_description(
        Description(start_time=3.0, end_time=5.0, text="Second cue"))
    return f.project_store.current


# ── Source handlers ──────────────────────────────────────────────

def test_local_file_sets_source():
    f = _frame()
    try:
        video = str(Path(tempfile.mkdtemp(prefix="odc_f21_vid_")) / "clip.mp4")
        Path(video).write_bytes(b"\x00" * 64)
        with stub_modals(path=video):
            f._on_local_file(None)
        assert f._current_source == video, f._current_source
    finally:
        _close(f)


def test_direct_url_sets_source():
    f = _frame()
    try:
        with stub_modals(text="https://example.com/clip.mp4"):
            f._on_direct_url(None)
        assert f._current_source == "https://example.com/clip.mp4", \
            f._current_source
    finally:
        _close(f)


def test_youtube_url_sets_source():
    f = _frame()
    try:
        with stub_modals(text="https://www.youtube.com/watch?v=jNQXAC9IVRw"):
            f._on_youtube_url(None)
        assert "youtube.com" in f._current_source, f._current_source
    finally:
        _close(f)


def test_cancelled_dialog_leaves_source_untouched():
    """Pressing Cancel must not arm the app with a stale source."""
    f = _frame()
    try:
        f._current_source = "keep-me"
        with stub_modals(text="ignored", entry_result=wx.ID_CANCEL):
            f._on_direct_url(None)
        with stub_modals(path="ignored.mp4", file_result=wx.ID_CANCEL):
            f._on_local_file(None)
        assert f._current_source == "keep-me", f._current_source
    finally:
        _close(f)


# ── Project handlers ─────────────────────────────────────────────

def test_new_project_creates_it():
    f = _frame()
    try:
        with stub_modals(text="My New Project"):
            f._on_new_project(None)
        names = [p["name"] for p in f.project_store.list_projects()]
        assert "My New Project" in names, names
    finally:
        _close(f)


def test_save_project_without_project_is_safe():
    f = _frame()
    try:
        with stub_modals() as boxes:
            f._on_save_project(None)
        assert boxes, "no project: the user must be told, not ignored"
    finally:
        _close(f)


def test_save_project_with_project():
    f = _frame()
    try:
        _seed_descriptions(f)
        with stub_modals():
            f._on_save_project(None)
        cur = f.project_store.open_project(f.project_store.current.id)
        assert cur is not None and len(cur.descriptions) == 2, cur
    finally:
        _close(f)


def test_open_project_with_none_saved():
    f = _frame()
    try:
        with stub_modals() as boxes:
            f._on_open_project(None)
        assert boxes, "empty project list must be announced"
    finally:
        _close(f)


def test_about_box_builds():
    """_on_about reads __version__ and builds wx.adv.AboutDialogInfo."""
    f = _frame()
    try:
        with stub_modals():
            f._on_about(None)
    finally:
        _close(f)


# ── Export / import handlers ─────────────────────────────────────

def test_export_srt_writes_real_file():
    f = _frame()
    try:
        _seed_descriptions(f)
        out = str(Path(tempfile.mkdtemp(prefix="odc_f21_srt_")) / "out.srt")
        with stub_modals(path=out):
            f._on_export_srt(None)
        text = Path(out).read_text(encoding="utf-8")
        assert "-->" in text, text[:200]
        assert "First cue" in text and "Second cue" in text, text[:200]
    finally:
        _close(f)


def test_export_vtt_writes_real_file():
    f = _frame()
    try:
        _seed_descriptions(f)
        out = str(Path(tempfile.mkdtemp(prefix="odc_f21_vtt_")) / "out.vtt")
        with stub_modals(path=out):
            f._on_export_vtt(None)
        text = Path(out).read_text(encoding="utf-8")
        assert text.lstrip().startswith("WEBVTT"), text[:120]
        assert "First cue" in text, text[:200]
    finally:
        _close(f)


def test_export_without_descriptions_is_announced():
    """Exporting an empty project must explain, not write a junk file."""
    f = _frame()
    try:
        out = str(Path(tempfile.mkdtemp(prefix="odc_f21_empty_")) / "x.srt")
        with stub_modals(path=out) as boxes:
            f._on_export_srt(None)
        assert boxes, "no descriptions: the user must be told"
        assert not Path(out).exists(), "wrote a file with nothing in it"
    finally:
        _close(f)


def test_import_descriptions_round_trip():
    """Export then import: the cues must survive the trip."""
    f = _frame()
    try:
        _seed_descriptions(f)
        srt = Path(tempfile.mkdtemp(prefix="odc_f21_imp_")) / "in.srt"
        with stub_modals(path=str(srt)):
            f._on_export_srt(None)
        assert srt.exists(), "export step did not produce the file"

        with stub_modals(path=str(srt)):
            f._on_import_descriptions(None)
        cur = f.project_store.current
        assert cur is not None, "import created no project"
        texts = [d.text for d in cur.descriptions]
        assert "First cue" in texts and "Second cue" in texts, texts
    finally:
        _close(f)


def test_import_rejects_garbage_file():
    f = _frame()
    try:
        junk = Path(tempfile.mkdtemp(prefix="odc_f21_junk_")) / "junk.srt"
        junk.write_text("this is not a subtitle file at all",
                        encoding="utf-8")
        with stub_modals(path=str(junk)) as boxes:
            f._on_import_descriptions(None)
        assert boxes, "a garbage import must be reported, not silent"
    finally:
        _close(f)


def test_export_audio_wiring():
    """Drive _on_export_audio with the renderer stubbed: the handler,
    its progress dialog and the done_cb/ui() closure must survive."""
    import time
    from omni_describer_custom.core import timeline_io

    f = _frame()
    real_export = timeline_io.export_audio
    try:
        _seed_descriptions(f)
        out = str(Path(tempfile.mkdtemp(prefix="odc_f21_aud_")) / "out.mp3")

        def fake_export(descs, path, tts, progress_cb=None, **k):
            if progress_cb:
                progress_cb(1, len(descs), 0)
            Path(path).write_bytes(b"\x00" * 128)
            return {"path": path, "rendered": len(descs), "skipped": 0}

        timeline_io.export_audio = fake_export
        with stub_modals(path=out):
            f._on_export_audio(None)
            deadline = time.time() + 15
            while time.time() < deadline and getattr(f, "_exporting", False):
                wx.GetApp().ProcessPendingEvents()
                wx.GetApp().Yield()
                time.sleep(0.05)
        assert not getattr(f, "_exporting", False), \
            "_exporting stuck True: the UI would refuse every later export"
        assert Path(out).exists(), "no audio file written"
    finally:
        timeline_io.export_audio = real_export
        _close(f)


# ── Editor window handlers ───────────────────────────────────────
#
# Every handler in editor_window.py was untested before this suite, and
# the editor is where v1.5.4's data-loss bug lived: because saved cues
# all kept id=0, deleting ONE cue deleted the lot. That bug is guarded
# at store level in test_fixes19; here it is guarded at the level the
# user actually meets it — selecting a row and pressing Delete.

@contextmanager
def _messagebox_answer(answer):
    real = wx.MessageBox
    seen = []

    def fake(message="", caption="", *a, **k):
        seen.append(str(message))
        return answer

    wx.MessageBox = fake
    try:
        yield seen
    finally:
        wx.MessageBox = real


def _editor(f):
    from omni_describer_custom.ui.editor_window import EditorWindow
    return EditorWindow(f, f.project_store, f.tts_engine)


def test_editor_delete_removes_only_the_selected_cue():
    f = _frame()
    ed = None
    try:
        from omni_describer_custom.core.project_store import Description
        _seed_descriptions(f)
        f.project_store.add_description(
            Description(start_time=6.0, end_time=8.0, text="Third cue"))
        ed = _editor(f)
        ed.desc_list.Select(1)
        ed._on_select(None)

        with _messagebox_answer(wx.YES):
            ed._on_delete(None)

        left = [d.text for d in f.project_store.current.descriptions]
        assert left == ["First cue", "Third cue"], left
        reopened = f.project_store.open_project(f.project_store.current.id)
        assert [d.text for d in reopened.descriptions] == \
            ["First cue", "Third cue"], "delete did not survive a reload"
    finally:
        if ed is not None:
            try:
                ed.Destroy()
            except Exception:
                pass
        _close(f)


def test_editor_delete_respects_no():
    """Answering No must leave every cue in place."""
    f = _frame()
    ed = None
    try:
        _seed_descriptions(f)
        ed = _editor(f)
        ed.desc_list.Select(0)
        ed._on_select(None)
        with _messagebox_answer(wx.NO) as asked:
            ed._on_delete(None)
        assert asked, "Delete must ask before destroying a cue"
        assert len(f.project_store.current.descriptions) == 2, \
            "No means no: cues were deleted anyway"
    finally:
        if ed is not None:
            try:
                ed.Destroy()
            except Exception:
                pass
        _close(f)


def test_editor_add_then_close_saves_edit():
    f = _frame()
    ed = None
    try:
        _seed_descriptions(f)
        ed = _editor(f)
        before = len(f.project_store.current.descriptions)
        ed._on_add(None)
        assert len(f.project_store.current.descriptions) == before + 1, \
            "Add did not create a cue"

        ed.desc_list.Select(0)
        ed._on_select(None)
        ed.text_ctrl.SetValue("Edited by the user")
        ed._on_close(None)          # saves and destroys
        ed = None

        reopened = f.project_store.open_project(f.project_store.current.id)
        texts = [d.text for d in reopened.descriptions]
        assert "Edited by the user" in texts, texts
    finally:
        if ed is not None:
            try:
                ed.Destroy()
            except Exception:
                pass
        _close(f)


def test_editor_tts_on_empty_text_is_announced():
    f = _frame()
    ed = None
    try:
        _seed_descriptions(f)
        ed = _editor(f)
        ed.text_ctrl.SetValue("   ")
        ed._on_tts(None)            # must not raise, must not speak
        assert ed.status_text.GetLabel(), \
            "empty text must be announced, not silently ignored"
    finally:
        if ed is not None:
            try:
                ed.Destroy()
            except Exception:
                pass
        _close(f)


if __name__ == "__main__":
    check("local file handler sets source", test_local_file_sets_source)
    check("direct url handler sets source", test_direct_url_sets_source)
    check("youtube url handler sets source", test_youtube_url_sets_source)
    check("cancel leaves source untouched",
          test_cancelled_dialog_leaves_source_untouched)
    check("new project handler creates it", test_new_project_creates_it)
    check("save with no project is announced",
          test_save_project_without_project_is_safe)
    check("save project persists descriptions", test_save_project_with_project)
    check("open project with none saved", test_open_project_with_none_saved)
    check("about box builds", test_about_box_builds)
    check("export srt writes real file", test_export_srt_writes_real_file)
    check("export vtt writes real file", test_export_vtt_writes_real_file)
    check("export with no descriptions is announced",
          test_export_without_descriptions_is_announced)
    check("import round trip keeps cues", test_import_descriptions_round_trip)
    check("import rejects garbage", test_import_rejects_garbage_file)
    check("export audio wiring survives", test_export_audio_wiring)
    check("editor delete removes only the selected cue",
          test_editor_delete_removes_only_the_selected_cue)
    check("editor delete respects No", test_editor_delete_respects_no)
    check("editor add + close saves the edit",
          test_editor_add_then_close_saves_edit)
    check("editor TTS announces empty text",
          test_editor_tts_on_empty_text_is_announced)
    print(f"\nRESULT: {ok} passed, {fail} failed")
    sys.exit(1 if fail else 0)
