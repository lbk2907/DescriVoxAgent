"""Regression round 45: what a keyboard sweep heard through NVDA (v1.8.2).

Every button in the player, editor, Scene Explorer and Settings was
pressed by keyboard and listened to (29 Sep 2026). Seven faults:

  1. Esc did not close the Description Editor or Ask More;
  2. "<< 10s" / "10s >>" were silent — no idea where the jump landed;
  3. Scene Explorer arrows were silent: frame changes were never said,
     and a second announcement into the label that already had focus
     is not re-read by NVDA;
  4. Scene Explorer "L" did nothing, silently, without an AI;
  5. its objects box had no label — NVDA said nothing on it;
  6. Settings speed slider was read "10 slider 33": wx.SL_LABELS makes
     static "5"/"20"/"10" labels right before the trackbar;
  7. a new user's Provider box was empty ("" in settings.json meant
     the default never applied), hiding half the AI tab.

All checked here without sending a single keystroke.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import os
import sys
import tempfile
import time
import traceback

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")
os.environ["ODC_CONFIG_DIR"] = tempfile.mkdtemp(prefix="odc_t45_cfg_")
os.environ.setdefault("ODC_PROJECTS_DIR", tempfile.mkdtemp(prefix="odc_t45_prj_"))

import wx  # noqa: E402

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


def pump(n=10):
    for _ in range(n):
        wx.Yield()
        time.sleep(0.01)


class _Key:
    def __init__(self, code):
        self.code, self.skipped = code, False

    def GetKeyCode(self):
        return self.code

    def Skip(self):
        self.skipped = True


def _store_with_project():
    from omni_describer_custom.core.project_store import Description, ProjectStore
    store = ProjectStore(tempfile.mkdtemp(prefix="odc_t45_p_"))
    store.create_project("t45", "C:/none.mp4")
    store.set_video_duration(90.0)
    store.save_descriptions([Description(start_time=5, end_time=8, text="A.")])
    return store


def test_escape_closes_editor_and_ask_more():
    from omni_describer_custom.core.tts_engine import TTSEngine
    from omni_describer_custom.ui.ask_more_dialog import AskMoreDialog
    from omni_describer_custom.ui.editor_window import EditorWindow
    store = _store_with_project()
    ed = EditorWindow(None, store, TTSEngine({}))
    ed.Show()
    pump()
    closed = {"n": 0}
    ed.Bind(wx.EVT_CLOSE, lambda e: closed.update(n=closed["n"] + 1) or e.Skip())
    other = _Key(ord("a"))
    ed._on_char_hook(other)
    assert other.skipped and closed["n"] == 0, "a normal key must pass through"
    ed._on_char_hook(_Key(wx.WXK_ESCAPE))
    pump()
    assert closed["n"] == 1, "Esc did not close the editor"
    ask = AskMoreDialog(None, None, [], 0.0)
    try:
        assert ask.GetEscapeId() == ask.cancel_btn.GetId(), \
            "Esc is not wired to Ask More's Cancel button"
    finally:
        ask.Destroy()


def test_ten_second_jumps_say_where_they_landed():
    from omni_describer_custom.core.tts_engine import TTSEngine
    from omni_describer_custom.ui.player_window import PlayerWindow
    store = _store_with_project()
    player = PlayerWindow(None, store, TTSEngine({}))
    player.Show()
    pump()
    try:
        player._on_forward(None)
        pump()
        said = player.status_text.GetLabel()
        assert "0:10" in said and "1:30" in said, said
        player._on_rewind(None)
        pump()
        assert "0:00" in player.status_text.GetLabel()
    finally:
        player._timer.Stop()
        player.Destroy()


def test_scene_explorer_speaks_every_frame_and_names_its_boxes():
    from omni_describer_custom.ui.scene_explorer import SceneExplorer
    from PIL import Image
    folder = tempfile.mkdtemp(prefix="odc_t45_f_")
    frames = []
    for i, colour in enumerate(("red", "blue", "green")):
        path = os.path.join(folder, f"f{i}.png")
        Image.new("RGB", (64, 48), colour).save(path)
        frames.append({"path": path, "time": i * 0.5})
    ex = SceneExplorer(None, None, "")
    ex.Show()
    pump(20)
    ex.frames = frames
    try:
        spoken = []
        for idx in (1, 0, 1):
            ex._show_frame(idx)
            pump()
            focused = wx.Window.FindFocus()
            assert focused in (ex.status_text, ex._status_alt), \
                "the frame change did not move focus to a status label"
            spoken.append((focused, focused.GetLabel()))
        assert spoken[0][0] is not spoken[1][0] and spoken[1][0] is not spoken[2][0], \
            "consecutive announcements reused the focused label; NVDA stays silent"
        assert all(str(i) in label for (_, label), i in zip(spoken, (2, 1, 2)))
        ex._list_objects()
        pump()
        assert "AI" in wx.Window.FindFocus().GetLabel(), "L was silent without an AI"
        class _Tab(_Key):
            def __init__(self, shift=False):
                super().__init__(wx.WXK_TAB)
                self.shift = shift

            def ShiftDown(self):
                return self.shift
        ex.desc_text.SetFocus()
        pump()
        ex._on_key(_Tab())
        pump()
        assert wx.Window.FindFocus() is ex.objects_text,             "Tab stayed in the Description box; the objects box is unreachable"
        ex._on_key(_Tab(shift=True))
        pump()
        assert wx.Window.FindFocus() is ex.desc_text, "Shift+Tab did not go back"
        kids = list(ex.objects_text.GetParent().GetChildren())
        before = kids[kids.index(ex.objects_text) - 1]
        assert isinstance(before, wx.StaticText) and before.GetLabel().strip(), \
            "the objects box has no label for NVDA"
    finally:
        ex.Destroy()


def test_speed_slider_is_named_speed_and_new_user_gets_a_provider():
    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.i18n.strings import t
    from omni_describer_custom.ui.settings_dialog import SettingsDialog
    store = SettingsStore()
    store.set("ai.default_provider", "")
    dlg = SettingsDialog(None, store)
    try:
        kids = list(dlg.speed_slider.GetParent().GetChildren())
        before = kids[kids.index(dlg.speed_slider) - 1]
        assert isinstance(before, wx.StaticText) and \
            before.GetLabel().strip() == t("settings.speed").strip(), \
            f"NVDA would name the slider {before.GetLabel()!r}"
        assert not dlg.speed_slider.GetWindowStyleFlag() & wx.SL_LABELS
        dlg.speed_slider.SetValue(15)
        dlg.speed_slider.ProcessWindowEvent(
            wx.CommandEvent(wx.EVT_SLIDER.typeId, dlg.speed_slider.GetId()))
        assert dlg.speed_value.GetLabel() == "1.5x", dlg.speed_value.GetLabel()
        assert dlg._selected_provider() == "glm", \
            f"a new user's provider is {dlg._selected_provider()!r}"
    finally:
        dlg.Destroy()


def test_yes_no_buttons_speak_the_app_language():
    from omni_describer_custom.i18n.strings import I18n
    from omni_describer_custom.ui import dialogs
    labels = {}

    class Fake:
        def __init__(self, parent, message, title, flags):
            labels["flags"] = flags

        def SetYesNoCancelLabels(self, yes, no, cancel):
            labels["yes"], labels["no"], labels["cancel"] = yes, no, cancel

        def ShowModal(self):
            return labels.get("answer", wx.ID_YES)

        def Destroy(self):
            pass

    real = wx.MessageDialog
    wx.MessageDialog = Fake
    I18n.set_language("ms")
    try:
        assert dialogs.ask_yes_no(None, "Padam?", "Tajuk", default_no=True) is True
        assert labels["yes"].replace("&", "") == "Ya", labels
        assert labels["no"].replace("&", "") == "Tidak", labels
        assert labels["flags"] & wx.NO_DEFAULT
        # v1.8.6: a Cancel button, so Esc works (Windows disables Esc in
        # a message box without one); Cancel/Esc mean "no".
        assert labels["flags"] & wx.CANCEL, "no Cancel, so Esc does nothing"
        assert labels["cancel"] == "Batal", labels
        labels["answer"] = wx.ID_CANCEL
        assert dialogs.ask_yes_no(None, "Padam?", "Tajuk") is False
    finally:
        wx.MessageDialog = real
        I18n.set_language("en")


def test_open_player_follows_a_language_switch():
    from omni_describer_custom.core.tts_engine import TTSEngine
    from omni_describer_custom.i18n.strings import I18n, t
    from omni_describer_custom.ui.player_window import PlayerWindow
    I18n.set_language("en")
    player = PlayerWindow(None, _store_with_project(), TTSEngine({}))
    try:
        english = player.load_srt_btn.GetLabel()
        I18n.set_language("ms")
        player.retranslate()
        assert player.load_srt_btn.GetLabel() == t("player.load_srt") != english
        assert player.explore_btn.GetLabel() == t("player.explore")
        assert player._timeline_label.GetLabel().startswith(t("player.timeline"))
        assert t("player.title") in player.GetTitle()
    finally:
        I18n.set_language("en")
        player._timer.Stop()
        player.Destroy()


def main() -> int:
    app = wx.App(False)
    check("Esc closes the editor and Ask More", test_escape_closes_editor_and_ask_more)
    check("10-second jumps say where they landed",
          test_ten_second_jumps_say_where_they_landed)
    check("Scene Explorer speaks every frame and names its boxes",
          test_scene_explorer_speaks_every_frame_and_names_its_boxes)
    check("speed slider is named Speed; a new user gets a provider",
          test_speed_slider_is_named_speed_and_new_user_gets_a_provider)
    check("Yes/No buttons speak the app language",
          test_yes_no_buttons_speak_the_app_language)
    check("an open player follows a language switch",
          test_open_player_follows_a_language_switch)
    del app
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
