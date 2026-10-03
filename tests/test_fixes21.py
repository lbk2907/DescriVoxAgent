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
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path

import wx

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
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

    # v1.8.2: Yes/No questions go through ui.dialogs.ask_yes_no, whose
    # buttons follow the app language; answer it the same way.
    from omni_describer_custom.ui import dialogs
    real_ask = dialogs.ask_yes_no

    def fake_ask(parent, message, *a, **k):
        seen.append(str(message))
        return answer == wx.YES

    wx.MessageBox = fake
    dialogs.ask_yes_no = fake_ask
    try:
        yield seen
    finally:
        wx.MessageBox = real
        dialogs.ask_yes_no = real_ask


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


# ── Player window handlers ───────────────────────────────────────
#
# The player is where a blind user spends the session, yet _on_play_
# toggle, _on_speak, _on_load_srt and the three "open another window"
# buttons had no test. TTS is stubbed: these checks are about the
# handlers being wired correctly, not about hearing audio (real speech
# is exercised separately).

@contextmanager
def _silent_tts(engine, spoken: list, result: bool = True):
    """Swap speak_and_play for a recorder, so nothing plays out loud."""
    real_speak = getattr(engine, "speak_and_play", None)
    real_stop = getattr(engine, "stop", None)

    def fake_speak(text, *a, **k):
        spoken.append(text)
        return result

    engine.speak_and_play = fake_speak
    engine.stop = lambda *a, **k: None
    try:
        yield
    finally:
        if real_speak is not None:
            engine.speak_and_play = real_speak
        if real_stop is not None:
            engine.stop = real_stop


def _player(f):
    from omni_describer_custom.ui.player_window import PlayerWindow
    return PlayerWindow(f, f.project_store, f.tts_engine, f.ai_engine)


def test_player_play_pause_toggle():
    """One button, two states: the label must follow what happens next,
    or a screen reader announces the wrong action (v1.4.0)."""
    f = _frame()
    p = None
    try:
        _seed_descriptions(f)
        p = _player(f)
        assert not p._playing, "player should start paused"
        start_label = p.play_btn.GetLabel()

        p._on_play_toggle(None)
        assert p._playing, "first press did not start playback"
        playing_label = p.play_btn.GetLabel()
        assert playing_label != start_label, \
            f"button label never changed: {start_label!r}"

        p._on_play_toggle(None)
        assert not p._playing, "second press did not pause"
        assert p.play_btn.GetLabel() == start_label, \
            f"label did not return to {start_label!r}"
    finally:
        if p is not None:
            try:
                p._on_stop(None)
            except Exception:
                pass
            try:
                p.Destroy()
            except Exception:
                pass
        _close(f)


def test_player_speak_reads_current_cue():
    f = _frame()
    p = None
    try:
        _seed_descriptions(f)
        p = _player(f)
        p.current_desc_text.SetValue("Read this line out loud")
        spoken: list[str] = []
        with _silent_tts(f.tts_engine, spoken):
            p._on_speak(None)
            deadline = __import__("time").time() + 10
            while __import__("time").time() < deadline and not spoken:
                wx.GetApp().ProcessPendingEvents()
                wx.GetApp().Yield()
                __import__("time").sleep(0.05)
        assert spoken == ["Read this line out loud"], spoken
    finally:
        if p is not None:
            try:
                p.Destroy()
            except Exception:
                pass
        _close(f)


def test_player_speak_ignores_empty_text():
    f = _frame()
    p = None
    try:
        _seed_descriptions(f)
        p = _player(f)
        p.current_desc_text.SetValue("   ")
        spoken: list[str] = []
        with _silent_tts(f.tts_engine, spoken):
            p._on_speak(None)
            for _ in range(6):
                wx.GetApp().Yield()
                __import__("time").sleep(0.03)
        assert spoken == [], f"spoke blank text: {spoken}"
    finally:
        if p is not None:
            try:
                p.Destroy()
            except Exception:
                pass
        _close(f)


def test_player_load_external_srt():
    """Loading someone else's subtitle file must replace the cues."""
    f = _frame()
    p = None
    try:
        _seed_descriptions(f)
        p = _player(f)
        srt = Path(tempfile.mkdtemp(prefix="odc_f21_extsrt_")) / "ext.srt"
        srt.write_text(
            "1\n00:00:01,000 --> 00:00:03,000\nExternal cue one\n\n"
            "2\n00:00:04,000 --> 00:00:06,000\nExternal cue two\n",
            encoding="utf-8")
        with stub_modals(path=str(srt)):
            p._on_load_srt(None)
        loaded = getattr(p, "_sub_cues", None)
        assert loaded, "no cues loaded from the external SRT"
        texts = " ".join(getattr(c, "text", str(c)) for c in loaded)
        assert "External cue one" in texts, texts[:200]
        assert "External cue two" in texts, texts[:200]
        # The load must be announced: a screen reader user gets no other
        # feedback that the file arrived.
        assert p.status_text.GetLabel(), "subtitle load was not announced"
    finally:
        if p is not None:
            try:
                p.Destroy()
            except Exception:
                pass
        _close(f)


def test_player_opens_editor_explorer_and_ask():
    """The three buttons that open other windows must actually open
    them — each was untested, and each imports its window lazily."""
    f = _frame()
    p = None
    opened = []
    try:
        _seed_descriptions(f)
        p = _player(f)

        import omni_describer_custom.ui.editor_window as ed_mod
        import omni_describer_custom.ui.scene_explorer as se_mod
        import omni_describer_custom.ui.ask_more_dialog as am_mod
        real = (ed_mod.EditorWindow, se_mod.SceneExplorer,
                am_mod.AskMoreDialog)

        def fake(name):
            class Fake:
                def __init__(self, *a, **k):
                    opened.append(name)

                def Show(self, *a, **k):
                    pass

                def ShowModal(self, *a, **k):
                    return wx.ID_CANCEL

                def Destroy(self, *a, **k):
                    pass
            return Fake

        ed_mod.EditorWindow = fake("editor")
        se_mod.SceneExplorer = fake("explorer")
        am_mod.AskMoreDialog = fake("ask")
        try:
            p._on_edit(None)
            p._on_explore(None)
            p._on_ask(None)
        finally:
            ed_mod.EditorWindow, se_mod.SceneExplorer, am_mod.AskMoreDialog = real

        assert opened == ["editor", "explorer", "ask"], opened
    finally:
        if p is not None:
            try:
                p.Destroy()
            except Exception:
                pass
        _close(f)


# ── Extended description: hold the video while a cue is read ─────
#
# W3C/WAI calls this extended description, and it is needed when the
# natural gaps are too short. Measured on a slide deck: reading one
# slide's bullets took 9.9s into a 5s gap, so 3 of 4 cues collided and
# the listener lost them. v1.6.1 pauses playback for the duration.

def _player_with_cue(f, text="A long description that takes time to say"):
    from omni_describer_custom.core.project_store import Description
    from omni_describer_custom.ui.player_window import PlayerWindow

    f.project_store.create_project("Pause test", "clip.mp4")
    f.project_store.add_description(
        Description(start_time=0.0, end_time=2.0, text=text))
    p = PlayerWindow(f, f.project_store, f.tts_engine, f.ai_engine)
    p._playing = True
    p._current_desc_idx = 0
    return p


def test_narration_holds_playback_then_resumes():
    import time
    f = _frame()
    p = None
    try:
        # Set it explicitly: ODC_CONFIG_DIR isolates the suite from the
        # USER's settings, but every run shares one file, so a later
        # test that switches this off would silently disable it here on
        # the next run.
        f.settings.set("player.pause_for_narration", True)
        p = _player_with_cue(f)
        p._settings = f.settings
        states = []

        def slow_speak(text, *a, **k):
            states.append(("speaking", p._auto_paused))
            time.sleep(0.2)
            return True

        f.tts_engine.speak_and_play = slow_speak
        p._maybe_narrate()
        deadline = time.time() + 10
        while time.time() < deadline and (p._tts_thread and
                                          p._tts_thread.is_alive()):
            wx.GetApp().Yield()
            time.sleep(0.02)
        for _ in range(10):
            wx.GetApp().ProcessPendingEvents()
            wx.GetApp().Yield()
            time.sleep(0.02)

        assert states and states[0][1] is True, \
            "playback was not held while the cue was being spoken"
        assert not p._auto_paused, "hold was never released after the cue"
    finally:
        if p is not None:
            try:
                p.Destroy()
            except Exception:
                pass
        _close(f)


def test_auto_hold_is_not_the_user_pressing_pause():
    """Using _do_pause() here would flip the Play button and strand the
    video paused forever."""
    f = _frame()
    p = None
    try:
        p = _player_with_cue(f)
        p._pause_for_narration()
        assert not p._paused_by_user, \
            "an automatic hold was recorded as the user's own pause"
        assert p._auto_paused
    finally:
        if p is not None:
            try:
                p.Destroy()
            except Exception:
                pass
        _close(f)


def test_user_pause_during_narration_wins():
    """If they press Pause while a cue is read, it must stay paused."""
    f = _frame()
    p = None
    try:
        p = _player_with_cue(f)
        p._pause_for_narration()
        p._paused_by_user = True          # the user intervenes
        p._resume_after_narration()
        assert not p._playing or p._paused_by_user, \
            "resume overrode a deliberate pause"
    finally:
        if p is not None:
            try:
                p.Destroy()
            except Exception:
                pass
        _close(f)


def test_player_has_a_visible_toggle_for_holding():
    """The choice belongs in the player, not buried in Settings: whether
    holding helps depends on the video in front of you."""
    f = _frame()
    p = None
    try:
        p = _player_with_cue(f)
        assert hasattr(p, "pause_narration_check"), \
            "no toggle in the player window"
        assert p.pause_narration_check.GetLabel(), \
            "toggle has no label for a screen reader to read"
    finally:
        if p is not None:
            try:
                p.Destroy()
            except Exception:
                pass
        _close(f)


def test_toggle_takes_effect_on_the_next_cue():
    """Unticking it must stop the very next hold, not wait for a restart."""
    f = _frame()
    p = None
    before = f.settings.get("player.pause_for_narration", True)
    try:
        p = _player_with_cue(f)
        p._settings = f.settings
        f.tts_engine.speak_and_play = lambda text, *a, **k: True

        p.pause_narration_check.SetValue(False)
        p._on_pause_narration_toggle(None)
        p._narrated.clear()
        p._maybe_narrate()
        assert not p._auto_paused, "held despite the toggle being off"
        assert f.settings.get("player.pause_for_narration") is False, \
            "the choice was not remembered"

        p.pause_narration_check.SetValue(True)
        p._on_pause_narration_toggle(None)
        p._narrated.clear()
        p._playing = True
        p._maybe_narrate()
        assert p._auto_paused, "did not hold after the toggle was switched on"
    finally:
        f.settings.set("player.pause_for_narration", before)
        if p is not None:
            try:
                p.Destroy()
            except Exception:
                pass
        _close(f)


def test_toggle_is_announced_not_just_checked():
    """A screen reader says "checked"; it does not say what that does."""
    f = _frame()
    p = None
    before = f.settings.get("player.pause_for_narration", True)
    try:
        p = _player_with_cue(f)
        p._settings = f.settings
        p.pause_narration_check.SetValue(False)
        p._on_pause_narration_toggle(None)
        assert p.status_text.GetLabel(), "switching it off said nothing"
        off_text = p.status_text.GetLabel()
        p.pause_narration_check.SetValue(True)
        p._on_pause_narration_toggle(None)
        assert p.status_text.GetLabel() != off_text, \
            "on and off are announced identically"
    finally:
        f.settings.set("player.pause_for_narration", before)
        if p is not None:
            try:
                p.Destroy()
            except Exception:
                pass
        _close(f)


def test_saved_preference_is_what_the_player_opens_with():
    """v1.6.1: the checkbox is the live source of truth, so the stored
    preference decides what the player STARTS with, not what it does
    mid-session (the toggle covers that)."""
    f = _frame()
    p = None
    before = f.settings.get("player.pause_for_narration", True)
    try:
        f.settings.set("player.pause_for_narration", False)
        p = _player_with_cue(f)
        assert p.pause_narration_check.GetValue() is False,             "player ignored the saved preference when it opened"
        spoken = []
        f.tts_engine.speak_and_play = lambda text, *a, **k: spoken.append(text)
        p._maybe_narrate()
        assert not p._auto_paused, \
            "playback was held even though the preference is off"
    finally:
        if p is not None:
            try:
                p.Destroy()
            except Exception:
                pass
        _close(f)


# ── Reported by the user on the v1.6.3 build ─────────────────────

def test_video_audio_returns_after_a_description():
    """The player went silent after the first cue and stayed silent.

    _pause_for_narration called _stop_ffplay(), which sets
    _audio_backend to "none" — and _resume_after_narration then tested
    that same flag to decide whether to restart. It never matched, so
    the video audio died half a second after Play and never came back.
    Narration kept working, which is exactly what the user reported:
    descriptions read aloud, video silent.
    """
    f = _frame()
    p = None
    try:
        p = _player_with_cue(f)
        p._audio_backend = "ffplay"       # as if ffplay were playing
        started = []
        p._start_ffplay = lambda pos: (started.append(pos), True)[1]
        p._stop_ffplay = lambda: setattr(p, "_audio_backend", "none")

        p._pause_for_narration()
        assert p._audio_backend == "none", "the hold did not stop the audio"
        assert p._paused_backend == "ffplay", \
            "the player forgot what it was playing before the hold"

        p._resume_after_narration()
        assert started, "audio was never restarted after the description"
    finally:
        if p is not None:
            try:
                p.Destroy()
            except Exception:
                pass
        _close(f)


def test_a_silent_video_says_why_in_the_log():
    """"No sound" had to be diagnosed from scratch because a missing
    ffplay produced no log line at all."""
    src = Path("src/omni_describer_custom/ui/player_window.py").read_text(
        encoding="utf-8")
    # v1.6.5: ffplay now ships with the app, so the log says "neither
    # bundled nor on PATH" — PATH alone is no longer the whole story.
    assert "ffplay not found" in src, \
        "a missing player is silent about being missing"
    assert "Audio via ffplay" in src, \
        "the log never records which audio route started"


def test_stop_ffplay_is_defined_once():
    """It was defined twice; the second shadowed the first."""
    src = Path("src/omni_describer_custom/ui/player_window.py").read_text(
        encoding="utf-8")
    assert src.count("    def _stop_ffplay(self)") == 1, \
        "duplicate definition is back"


def test_progress_dialog_follows_the_real_phase():
    """The dialog said "Loading video info... (808s)" while the title
    said "Downloading video - 100%", thirteen minutes into an AI upload.

    _hb_phase was written once, at the start, and never updated; and the
    phase ticks did not mark themselves as progress, so the heartbeat
    overwrote the correct line 1.5 seconds later.
    """
    import time as _time

    f = _frame()
    try:
        f._hb_phase = "Loading video info..."
        f._hb_start = _time.monotonic() - 800     # an old, stale phase

        f._video_status_tick("uploading")
        assert f._hb_phase != "Loading video info...", \
            "the heartbeat still repeats the first phase forever"
        assert _time.monotonic() - f._hb_start < 5, \
            "the counter still shows the age of the whole job"

        # A phase tick counts as progress, so the heartbeat stands down.
        f._last_progress_at = 0.0
        f._video_upload_tick(42.0)
        assert _time.monotonic() - f._last_progress_at < 5, \
            "upload progress does not hold the heartbeat off"
    finally:
        _close(f)


def test_the_dialog_title_stops_claiming_to_download():
    """A stand-in dialog, not a real wx.ProgressDialog.

    Building one here segfaulted the suite: its constructor pumps the
    event loop (pitfall 8), and the pending events then land
    on a frame the test is tearing down. The title logic is what matters
    and it needs no real window.
    """
    class FakeDialog:
        def __init__(self):
            self.title = "Downloading video - 100%"

        def SetTitle(self, text):
            self.title = text

        def Pulse(self, *a):
            pass

        def Update(self, *a):
            return (True, False)      # (continue, skipped), as wx returns

    f = _frame()
    try:
        fake = FakeDialog()
        f._dl_dialog = fake
        f._video_status_tick("processing")
        assert "Downloading" not in fake.title, (
            "still claims to be downloading during the AI phase: "
            f"{fake.title!r}")
        assert fake.title.strip(), "the title went blank"

        # v1.9.6: the title carries the ONE overall percentage of the job
        # (the upload is the first half of the AI stage, 30-95).
        f._video_upload_tick(42.0)
        assert f._overall_pct() == 43, f._overall_pct()
        assert "43%" in fake.title, \
            f"overall progress is missing from the title: {fake.title!r}"
    finally:
        f._dl_dialog = None       # never let the frame destroy the stub
        _close(f)


# ── Scene explorer + Ask More handlers ───────────────────────────

def test_scene_explorer_arrow_keys_stay_in_range():
    """Left/Right at the ends must clamp, not raise IndexError."""
    from omni_describer_custom.ui.scene_explorer import SceneExplorer

    f = _frame()
    se = None
    try:
        se = SceneExplorer(f, f.ai_engine, "")
        se.frames = [{"path": "a.jpg", "time": 0.0},
                     {"path": "b.jpg", "time": 1.0}]
        se._current_idx = 0

        class KeyEvent:
            def __init__(self, code):
                self.code = code

            def GetKeyCode(self):
                return self.code

            def Skip(self, *a):
                pass

        se._on_key(KeyEvent(wx.WXK_LEFT))     # already at the first frame
        assert se._current_idx == 0, se._current_idx
        se._on_key(KeyEvent(wx.WXK_RIGHT))
        se._on_key(KeyEvent(wx.WXK_RIGHT))    # already at the last frame
        assert se._current_idx == len(se.frames) - 1, se._current_idx
    finally:
        if se is not None:
            try:
                se.Destroy()
            except Exception:
                pass
        _close(f)


def test_ask_more_cancel_closes_cleanly():
    from omni_describer_custom.ui.ask_more_dialog import AskMoreDialog

    f = _frame()
    dlg = None
    try:
        dlg = AskMoreDialog(f, f.ai_engine)
        dlg._on_cancel(None)      # must not raise
    finally:
        if dlg is not None:
            try:
                dlg.Destroy()
            except Exception:
                pass
        _close(f)


# ── Fresh-launch state (v1.5.6) ──────────────────────────────────
#
# Found by the player E2E: on MSW, SetLabel() eats a control's STATE —
# it clears a wx.Choice selection and REPLACES a wx.TextCtrl's text.
# v1.5.4 used it to give three controls screen-reader names, so a
# freshly launched app had:
#   - no preset selected: pressing Open answered "Please select a
#     prompt preset" although the combo looked populated
#   - the prompt box holding the label "Prompt to send (from preset,
#     editable):", which _on_preset_open appends to the request as
#     "User notes" — nonsense instructions on every describe
#   - "Status Log" sitting in the log as if it had been logged

def test_fresh_launch_has_a_preset_selected():
    f = _frame()
    try:
        assert f.prompt_choice.GetSelection() != wx.NOT_FOUND, \
            "no preset selected on a fresh launch: Open would refuse"
        assert f.prompt_choice.GetStringSelection(), \
            "preset selection is empty"
    finally:
        _close(f)


def test_prompt_box_holds_the_preset_not_a_label():
    f = _frame()
    try:
        value = f.custom_prompt.GetValue().strip()
        name = f.prompt_choice.GetStringSelection()
        expected = f.prompt_mgr.get_preset(name).strip()
        assert value == expected, (
            f"prompt box does not hold preset {name!r}: {value[:80]!r}")
        assert not f.log_text.GetValue().startswith("Status Log"), \
            "the log's own label was written into the log"
    finally:
        _close(f)


def test_open_sends_the_preset_without_invented_notes():
    """The exact string handed to the pipeline must be the preset."""
    f = _frame()
    try:
        sent: list[str] = []
        f._start_processing = lambda prompt: sent.append(prompt)
        f._current_source = "clip.mp4"
        with stub_modals() as boxes:
            f._on_preset_open(None)
        assert sent, f"Open did not start processing; boxes={boxes}"
        assert "User notes" not in sent[0], (
            f"a label leaked into the AI request: {sent[0][-120:]!r}")
        name = f.prompt_choice.GetStringSelection()
        assert sent[0].strip() == f.prompt_mgr.get_preset(name).strip(), \
            sent[0][:120]
    finally:
        _close(f)


def test_accessible_names_survive_the_fix():
    """The fix must not buy correctness by dropping NVDA names."""
    f = _frame()
    try:
        assert f.prompt_choice.GetLabel(), "preset combo lost its NVDA name"
        assert f.custom_prompt.GetName(), "prompt box lost its NVDA name"
        assert f.log_text.GetName(), "log lost its NVDA name"
        # The visible StaticText labels are what NVDA reads out loud.
        assert f.preset_label.GetLabel(), "preset label text missing"
        assert f.custom_prompt_label.GetLabel(), "prompt label text missing"
    finally:
        _close(f)


def test_language_switch_keeps_preset_and_prompt():
    """_retranslate_ui is the exact path that broke this: re-running it
    must leave the selection and the prompt box intact."""
    f = _frame()
    try:
        before_sel = f.prompt_choice.GetStringSelection()
        before_prompt = f.custom_prompt.GetValue()
        f._retranslate_ui()
        assert f.prompt_choice.GetStringSelection() == before_sel, \
            "retranslate cleared the preset selection"
        assert f.custom_prompt.GetValue() == before_prompt, \
            "retranslate overwrote the prompt box"
    finally:
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
    check("player play/pause toggles state and label",
          test_player_play_pause_toggle)
    check("player speak reads the current cue",
          test_player_speak_reads_current_cue)
    check("player speak ignores empty text",
          test_player_speak_ignores_empty_text)
    check("player loads an external SRT", test_player_load_external_srt)
    check("player opens editor, explorer and ask",
          test_player_opens_editor_explorer_and_ask)
    check("narration holds playback then resumes",
          test_narration_holds_playback_then_resumes)
    check("auto hold is not a user pause",
          test_auto_hold_is_not_the_user_pressing_pause)
    check("user pause during narration wins",
          test_user_pause_during_narration_wins)
    check("player has a visible toggle",
          test_player_has_a_visible_toggle_for_holding)
    check("toggle takes effect on the next cue",
          test_toggle_takes_effect_on_the_next_cue)
    check("toggle is announced, not just checked",
          test_toggle_is_announced_not_just_checked)
    check("saved preference is what the player opens with",
          test_saved_preference_is_what_the_player_opens_with)
    check("video audio returns after a description",
          test_video_audio_returns_after_a_description)
    check("a silent video says why in the log",
          test_a_silent_video_says_why_in_the_log)
    check("_stop_ffplay defined once", test_stop_ffplay_is_defined_once)
    check("progress dialog follows the real phase",
          test_progress_dialog_follows_the_real_phase)
    check("dialog title stops claiming to download",
          test_the_dialog_title_stops_claiming_to_download)
    check("scene explorer arrow keys clamp",
          test_scene_explorer_arrow_keys_stay_in_range)
    check("ask more cancel closes cleanly",
          test_ask_more_cancel_closes_cleanly)
    check("fresh launch has a preset selected",
          test_fresh_launch_has_a_preset_selected)
    check("prompt box holds the preset, not a label",
          test_prompt_box_holds_the_preset_not_a_label)
    check("Open sends the preset without invented notes",
          test_open_sends_the_preset_without_invented_notes)
    check("accessible names survive the fix",
          test_accessible_names_survive_the_fix)
    check("language switch keeps preset and prompt",
          test_language_switch_keeps_preset_and_prompt)
    print(f"\nRESULT: {ok} passed, {fail} failed")
    sys.exit(1 if fail else 0)
