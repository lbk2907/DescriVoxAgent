"""Regression round 40: Help > Check for Updates for yt-dlp (v1.7.7).

YouTube changes often enough that an old yt-dlp stops downloading, and
the bundled copy is pinned at build time. The user can now pull a newer
one from the app. What must hold, each pinned here:

  - an update is installed ONLY if its SHA-256 matches the publisher's
    SHA2-256SUMS for that release AND the program reports that version;
  - a refused update leaves what was in use untouched;
  - the update never overwrites the bundled copy, and find_tool uses it
    only while its hash still matches (a tampered file is ignored);
  - "Use bundled version" really goes back;
  - the weekly start-up check only announces, at most once a week.

No network: "downloads" are served from the real bundled yt-dlp.exe,
so the checksum and version checks run against a real program.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import hashlib
import io
import os
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
os.environ.setdefault("ODC_CONFIG_DIR", tempfile.mkdtemp(prefix="odc_t40_cfg_"))
os.environ.setdefault("ODC_PROJECTS_DIR", tempfile.mkdtemp(prefix="odc_t40_prj_"))

from omni_describer_custom.core import tools, updater  # noqa: E402

results: list[tuple[str, bool]] = []
REAL = tools.bundled_tool("yt-dlp")
REAL_BYTES = Path(REAL).read_bytes() if REAL else b""
REAL_SHA = hashlib.sha256(REAL_BYTES).hexdigest()
REAL_VERSION = updater.tool_version(REAL)


def check(name, fn):
    os.environ["ODC_TOOLS_DIR"] = tempfile.mkdtemp(prefix="odc_t40_tools_")
    tools.forget_verification()
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def fake_fetch(sums_sha: str, exe_bytes: bytes):
    def fetch(url: str) -> bytes:
        if url.endswith("SHA2-256SUMS"):
            return (f"{sums_sha}  yt-dlp.exe\n"
                    f"{'0' * 64}  yt-dlp\n").encode()
        if url.endswith("yt-dlp.exe"):
            return exe_bytes
        raise AssertionError(f"unexpected URL {url}")
    return fetch


def test_verified_update_is_installed_and_used():
    version = updater.install(REAL_VERSION,
                              fetch=fake_fetch(REAL_SHA, REAL_BYTES))
    assert version == REAL_VERSION
    installed = tools.user_tools_dir() / "yt-dlp.exe"
    assert installed.is_file()
    assert tools.find_tool("yt-dlp") == str(installed), tools.find_tool("yt-dlp")
    assert Path(REAL).read_bytes() == REAL_BYTES, "the bundled copy changed"
    assert not (tools.user_tools_dir() / "yt-dlp.new.exe").exists()


def test_checksum_mismatch_installs_nothing():
    tampered = REAL_BYTES + b"x"
    try:
        updater.install(REAL_VERSION, fetch=fake_fetch(REAL_SHA, tampered))
        raise AssertionError("a file that fails its checksum was installed")
    except updater.UpdateError as e:
        assert "checksum" in str(e), e
    assert not (tools.user_tools_dir() / "yt-dlp.exe").exists()
    assert tools.find_tool("yt-dlp") == REAL


def test_wrong_version_installs_nothing():
    try:
        updater.install("2099.01.01", fetch=fake_fetch(REAL_SHA, REAL_BYTES))
        raise AssertionError("a program reporting the wrong version was installed")
    except updater.UpdateError as e:
        assert "2099.01.01" in str(e), e
    folder = tools.user_tools_dir()
    assert not (folder / "yt-dlp.exe").exists()
    assert not (folder / "yt-dlp.new.exe").exists(), "staging file left behind"


def test_tampered_update_is_ignored():
    updater.install(REAL_VERSION, fetch=fake_fetch(REAL_SHA, REAL_BYTES))
    installed = tools.user_tools_dir() / "yt-dlp.exe"
    with open(installed, "ab") as f:
        f.write(b"tamper")
    os.utime(installed, (time.time() + 5, time.time() + 5))
    assert tools.find_tool("yt-dlp") == REAL, \
        "a copy that no longer matches its verified hash was used"


def test_revert_goes_back_to_bundled():
    updater.install(REAL_VERSION, fetch=fake_fetch(REAL_SHA, REAL_BYTES))
    assert updater.revert() is True
    assert tools.find_tool("yt-dlp") == REAL
    assert "yt-dlp" not in tools.read_updates_manifest()
    assert updater.revert() is False, "revert claimed to remove nothing"


def test_version_compare_and_weekly_rhythm():
    assert updater.is_newer("2026.10.02", "2026.08.19")
    assert not updater.is_newer("2026.08.19", "2026.08.19")
    assert not updater.is_newer("2026.08.01", "2026.08.19")
    assert updater.is_newer("2026.08.19.1", "2026.08.19")

    class Settings(dict):
        def get(self, k, d=None):
            return super().get(k, d)

        def set(self, k, v):
            self[k] = v

    s = Settings()
    now = 1_800_000_000
    assert updater.weekly_check_due(s, now)
    updater.record_check(s, now)
    assert not updater.weekly_check_due(s, now + 3600)
    assert updater.weekly_check_due(s, now + 7 * 24 * 3600)


def test_menu_dialog_and_weekly_notice():
    import wx
    app = wx.GetApp() or wx.App(False)
    from omni_describer_custom.ui import update_dialog
    from omni_describer_custom.ui.main_frame import MainFrame

    frame = MainFrame()
    try:
        item = frame.GetMenuBar().FindItemById(frame._id_check_updates)
        assert item is not None, "no Check for Updates menu item"

        dlg = update_dialog.UpdateDialog(frame, frame.settings,
                                         check_on_open=False)
        for ctrl in (dlg.check_btn, dlg.update_btn, dlg.revert_btn,
                     dlg.close_btn):
            assert ctrl.GetLabel().replace("&", "").strip(), "unlabelled button"
        assert dlg.status_box.GetName().strip(), "status box has no NVDA name"
        st = {"in_use_version": "2026.08.19", "bundled_version": "2026.08.19",
              "using_update": False, "in_use_path": REAL}
        dlg._check_done(st, "2026.10.02", "2026.10.02", "")
        text = dlg.status_box.GetValue()
        assert "2026.10.02" in text and dlg.update_btn.IsEnabled(), text
        dlg._check_done(st, "", "", "offline")
        assert "offline" in dlg.status_box.GetValue()
        dlg.Destroy()

        # The menu handler itself (pitfall 18): opens and closes.
        real_show = update_dialog.UpdateDialog.ShowModal
        opened = {"n": 0}

        def fake_show(self):
            opened["n"] += 1
            return wx.ID_CLOSE
        update_dialog.UpdateDialog.ShowModal = fake_show
        real_latest = updater.latest_version
        updater.latest_version = lambda fetch=None: "2026.08.19"
        try:
            frame._on_check_updates(None)
        finally:
            update_dialog.UpdateDialog.ShowModal = real_show
        assert opened["n"] == 1

        # Weekly notice: announces, downloads nothing.
        frame.settings.set("updates.last_check", 0)
        real_available = updater.available_update
        updater.available_update = lambda fetch=None: "2026.10.02"
        try:
            frame.check_updates_in_background()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                wx.Yield()
                if "2026.10.02" in frame.GetStatusBar().GetStatusText():
                    break
                time.sleep(0.05)
        finally:
            updater.available_update = real_available
            updater.latest_version = real_latest
        assert "2026.10.02" in frame.GetStatusBar().GetStatusText()
        assert not (tools.user_tools_dir() / "yt-dlp.exe").exists(), \
            "the weekly check downloaded something by itself"
        assert not updater.weekly_check_due(frame.settings), \
            "the check was not recorded, so it would run every start"
    finally:
        for _ in range(30):
            wx.Yield()
            time.sleep(0.02)
        frame.Destroy()
        del app


def test_native_menus_open_on_their_real_first_item():
    """wx.Menu.SetTitle wrote the menu's title INTO the Windows dropdown
    over its first item: File opened on "File" (Settings unreachable by
    keyboard) and Help on "Help" (Check for Updates unreachable). wx's
    own item list still looked right, which is how it hid — so this
    reads the NATIVE menu, as NVDA does."""
    import win32gui
    import wx
    app = wx.GetApp() or wx.App(False)
    from omni_describer_custom.ui.main_frame import MainFrame
    frame = MainFrame()
    try:
        frame.Show()
        for _ in range(10):
            wx.Yield()
        bar = win32gui.GetMenu(frame.GetHandle())
        expect = {0: "Settings", 1: "Check for Updates"}
        for pos, first in expect.items():
            sub = win32gui.GetSubMenu(bar, pos)
            wx_items = frame.GetMenuBar().GetMenu(pos).GetMenuItemCount()
            native = win32gui.GetMenuItemCount(sub)
            import ctypes
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetMenuStringW(sub, 0, buf, 256, 0x400)
            label = buf.value.replace("&", "")
            assert native == wx_items, (
                f"menu {pos}: Windows shows {native} items, wx has {wx_items}")
            assert label.startswith(first), (
                f"menu {pos} opens on {label!r}, not {first!r}")
    finally:
        frame.Destroy()
        for _ in range(10):
            wx.Yield()
        del app


def main() -> int:
    if not REAL or not REAL_VERSION:
        print("FAIL: no runnable bundled yt-dlp to test against")
        return 1
    check("a verified update is installed and used", test_verified_update_is_installed_and_used)
    check("a checksum mismatch installs nothing", test_checksum_mismatch_installs_nothing)
    check("a wrong version installs nothing", test_wrong_version_installs_nothing)
    check("a tampered update is ignored", test_tampered_update_is_ignored)
    check("Use bundled version goes back", test_revert_goes_back_to_bundled)
    check("version compare and the weekly rhythm", test_version_compare_and_weekly_rhythm)
    check("menu, dialog and weekly notice", test_menu_dialog_and_weekly_notice)
    check("menus open on their real first item",
          test_native_menus_open_on_their_real_first_item)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
