"""Check what NVDA says in the player, the editor and Ask More.

tools/nvda_accessibility_check.py walks the MAIN window only. v1.7.4
changed the editor, the player and Ask More, and pitfall 29
asks for a listening check after any UI change — so this opens each of
those windows on a throwaway project and tabs through it the same way.

    python tools/nvda_window_check.py --window player
    python tools/nvda_window_check.py --window editor
    python tools/nvda_window_check.py --window ask
    python tools/nvda_window_check.py --window updates
    python tools/nvda_window_check.py --window app_update
    python tools/nvda_window_check.py --window explorer
    python tools/nvda_window_check.py --window settings
    python tools/nvda_window_check.py --window settings --provider custom

Runs from source with an isolated ODC_CONFIG_DIR and a temp projects
folder; the user's settings and projects are never touched. Exit 2
without the NVDA bridge, as the main-window check does.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "src"))


def serve(window: str, work: Path) -> None:
    """Child process: open the requested window and run the wx loop."""
    import wx
    from omni_describer_custom.core.project_store import (Description,
                                                          ProjectStore)
    from omni_describer_custom.core.tools import find_tool
    from omni_describer_custom.core.tts_engine import TTSEngine
    from omni_describer_custom.ui.player_window import PlayerWindow

    clip = work / "clip.mp4"
    subprocess.run([find_tool("ffmpeg"), "-y", "-loglevel", "error", "-f",
                    "lavfi", "-i", "color=c=blue:s=320x240:d=30", "-c:v",
                    "libx264", str(clip)], check=True)
    app = wx.App(False)
    # The window speaks the language the (isolated) settings choose.
    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.i18n.strings import I18n
    I18n.set_language(SettingsStore().get("general.language", "en") or "en")
    store = ProjectStore(str(work / "projects"))
    store.create_project("A11y check", str(clip))
    store.save_descriptions([
        Description(start_time=5.0, end_time=8.0, text="A blue screen."),
        Description(start_time=12.0, end_time=15.0, text="Still blue."),
    ])
    player = PlayerWindow(None, store, TTSEngine({}))
    player.Show()
    top = player
    if window == "editor":
        from omni_describer_custom.ui.editor_window import EditorWindow
        top = EditorWindow(player, store, player.tts)
        top.Show()
    elif window == "updates":
        from omni_describer_custom.ui.update_dialog import UpdateDialog
        top = UpdateDialog(player, None)
        top.Show()
    elif window == "app_update":
        # 2.1.3: Help > Check for Updates (the app itself), offering a
        # made-up release so nothing is fetched from GitHub.
        from omni_describer_custom.core.app_update import Release
        from omni_describer_custom.ui.app_update_dialog import AppUpdateDialog
        release = Release(
            version="9.9.9", tag="v9.9.9",
            notes="- The app updates itself.\n- A test release for listening.",
            page_url="https://example.invalid", zip_url="", zip_size=0,
            sums_url="")
        top = AppUpdateDialog(player, None, release=release)
        top.Show()
    elif window == "explorer":
        from omni_describer_custom.ui.scene_explorer import SceneExplorer
        top = SceneExplorer(player, None, str(clip))
        top.Show()
    elif window == "settings":
        from omni_describer_custom.core.settings_store import SettingsStore
        from omni_describer_custom.ui.settings_dialog import SettingsDialog
        top = SettingsDialog(player, SettingsStore())
        top.Show()
        provider = os.environ.get("ODC_A11Y_PROVIDER", "")
        if provider:
            # --provider: start on the AI tab with that provider chosen.
            top.notebook.SetSelection(1)
            top.select_provider(provider)
            top.provider_choice.SetFocus()
    elif window == "ask":
        from omni_describer_custom.ui.ask_more_dialog import AskMoreDialog
        top = AskMoreDialog(player, None, store.current.descriptions, 0.0)
        top.Show()
    top.Raise()
    (work / "title.txt").write_text(top.GetTitle(), encoding="utf-8")
    app.MainLoop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", choices=["player", "editor", "ask", "updates", "explorer",
                                 "settings", "app_update"],
                        required=True)
    parser.add_argument("--steps", type=int, default=16)
    parser.add_argument("--provider", default="",
                        help="settings only: open the AI tab on this provider")
    parser.add_argument("--serve", default="", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.serve:
        serve(args.window, Path(args.serve))
        return 0

    import nvda_accessibility_check as a11y
    alive, detail = a11y.bridge_alive()
    if not alive:
        print(f"NVDA HTTP Bridge not answering: {detail}")
        return 2
    print(f"Bridge up: {detail}")

    work = Path(tempfile.mkdtemp(prefix="odc_a11y_"))
    env = dict(os.environ, ODC_CONFIG_DIR=str(work / "config"),
               ODC_A11Y_PROVIDER=args.provider)
    log = open(work / "app_log.txt", "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, __file__, "--window",
                             args.window, "--serve", str(work)],
                            env=env, stdout=log, stderr=log)
    import safe_keys
    safe_keys.allow(proc.pid)
    try:
        from pywinauto import Desktop
        title_file = work / "title.txt"
        deadline = time.monotonic() + 90
        while not title_file.exists() and time.monotonic() < deadline:
            if proc.poll() is not None:
                log.close()
                print((work / "app_log.txt").read_text(encoding="utf-8"))
                return 1
            time.sleep(0.5)
        title = title_file.read_text(encoding="utf-8")
        # A wx dialog sits UNDER its owner frame in the UIA tree, so look
        # it up by its Win32 handle rather than as a top-level window.
        import win32gui
        hwnd = 0
        while not hwnd and time.monotonic() < deadline + 30:
            hwnd = win32gui.FindWindow(None, title)
            time.sleep(0.5)
        win = Desktop(backend="uia").window(handle=hwnd)
        # Bring it to the front first (as nvda_agent_check does): with
        # another app in front, pywinauto's set_focus alone left the
        # Claude window foreground and safe_keys refused every key.
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            win.set_focus()
        time.sleep(1.5)
        # 6 Oct 2026: the keys reached the dialog, but NVDA kept reporting
        # the Claude window's "Prompt" box for 6 Tabs, and the report said
        # OK for them. Wait until NVDA itself is in this app; if it never
        # is, that is INCONCLUSIVE (pitfall 100), not a pass.
        # NVDA follows only after a key lands in the window; safe_keys has
        # checked the foreground AND keyboard focus are this app's, so
        # these warm-up Tabs (not recorded) cannot reach another program.
        # A positive match on the app under test (it runs from source,
        # so NVDA names it python), not "anything but Claude" (review,
        # 8 Oct 2026: a browser or terminal would have counted).
        for _warm in range(8):
            if a11y.nvda_in(a11y.SOURCE_APP_NAMES):
                break
            try:
                safe_keys.send_keys("{TAB}")
            except Exception as e:
                print(f"warm-up refused: {e}")
                break
            time.sleep(0.9)
        if not a11y.nvda_in(a11y.SOURCE_APP_NAMES):
            print("INCONCLUSIVE: NVDA's focus is not in the window under "
                  "test; nothing was judged")
            return 3
        print(f"Window: {title}")
        seen = a11y.walk_controls(win, args.steps)
        # The main-window pitfall-12 checks look for the preset combo and
        # prompt box, which these windows do not have.
        a11y._check_pitfall_12 = lambda seen: []
        return a11y.report(seen)
    finally:
        proc.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
