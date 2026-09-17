"""Minimal repro: which window causes the shutdown RecursionError?"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
sys.path.insert(0, "src")
sys.path.insert(0, ".")

import wx

app = wx.App(False)

from omni_describer_custom.ui.main_frame import MainFrame
from omni_describer_custom.ui.scene_explorer import SceneExplorer
from omni_describer_custom.ui.player_window import PlayerWindow
from omni_describer_custom.ui.editor_window import EditorWindow
from omni_describer_custom.ui.ask_more_dialog import AskMoreDialog
from omni_describer_custom.core.project_store import ProjectStore, Description
from omni_describer_custom.core.tts_engine import TTSEngine
from omni_describer_custom.core.ai_engine import AIEngine
import tempfile

frame = MainFrame()
frame.Show(True)
wx.Yield()
print("frame OK")

d = tempfile.mkdtemp()
ps = ProjectStore(projects_dir=d)
p = ps.create_project("RTest", "x.mp4")
p.video_duration = 60.0
ps.add_description(Description(start_time=0.0, end_time=5.0, text="T"))

player = PlayerWindow(frame, ps, TTSEngine({}), AIEngine())
player.Show()
wx.Yield()
print("player OK")

editor = EditorWindow(player, ps, TTSEngine({}))
editor.Show()
wx.Yield()
print("editor OK")

ask = AskMoreDialog(player, AIEngine())
ask.Show()
wx.Yield()
ask.Close()
print("ask OK")

explorer = SceneExplorer(frame, AIEngine(), "")
explorer.Show()
wx.Yield()
print("explorer OK")

explorer.Close()
editor.Close()
player._timer.Stop()
player.Close()
frame.Close()
wx.Yield()
print("all closed, exiting cleanly")
app.ProcessPendingEvents()
del app
print("DONE")
