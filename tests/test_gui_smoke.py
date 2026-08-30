"""GUI smoke test: build every window/dialog, verify, then auto-close."""
import sys, io, traceback
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "src")
sys.path.insert(0, ".")

import wx

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

def run():
    from omni_describer_custom.ui.main_frame import MainFrame
    from omni_describer_custom.ui.settings_dialog import SettingsDialog
    from omni_describer_custom.ui.player_window import PlayerWindow
    from omni_describer_custom.ui.editor_window import EditorWindow
    from omni_describer_custom.ui.ask_more_dialog import AskMoreDialog
    from omni_describer_custom.ui.scene_explorer import SceneExplorer
    from omni_describer_custom.core.project_store import ProjectStore
    from omni_describer_custom.core.tts_engine import TTSEngine
    from omni_describer_custom.core.ai_engine import AIEngine

    app = wx.App(False)

    # MainFrame
    frame = MainFrame()
    frame.Show(True)
    wx.Yield()
    assert frame.log_text is not None

    # SettingsDialog
    dlg = SettingsDialog(frame, frame.settings)
    dlg.ShowModal() if False else None  # don't block; just constructed
    dlg.Destroy()
    wx.Yield()

    # Player + Editor + AskMore + SceneExplorer with a real temp project
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        ps = ProjectStore(projects_dir=d)
        from omni_describer_custom.core.project_store import Description
        p = ps.create_project("GUITest", "nonexistent.mp4")
        p.video_duration = 60.0
        ps.add_description(Description(start_time=0.0, end_time=5.0, text="Test description"))

        player = PlayerWindow(frame, ps, TTSEngine({}), AIEngine())
        player.Show()
        wx.Yield()
        assert player.current_desc_text.GetValue() == "Test description", player.current_desc_text.GetValue()

        editor = EditorWindow(player, ps, TTSEngine({}))
        editor.Show()
        wx.Yield()

        ask = AskMoreDialog(player, AIEngine())
        ask.Show()  # ShowModal would block
        wx.Yield()
        ask.Close()
        editor.Close()
        player._timer.Stop()  # stop wx.Timer before close (avoid shutdown recursion)
        player.Close()
        wx.Yield()

    explorer = SceneExplorer(frame, AIEngine(), "")
    explorer.Show()
    wx.Yield()
    explorer.Close()

    frame.Close()
    wx.Yield()
    print("ALL GUI WINDOWS CONSTRUCTED OK")

check("GUI windows construct + display", run)

print(f"\nRESULT: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
