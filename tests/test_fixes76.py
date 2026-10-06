"""Regression round 76: DescriVox updates itself (owner, 6 Oct 2026).

Help > Check for Updates is now the app itself (core/app_update.py):
GitHub Releases of lbk2907/DescriVoxAgent, checked at every start
(owner's choice), downloaded, verified against SHA256SUMS.txt, unpacked
next to the app and swapped in by a script once the app has closed.
yt-dlp keeps its own item, Help > Update YouTube downloader.

The swap script is run for real here against a real waiting process:
the first version of it never waited, because a PATH with Git first
made "find" Git's find (the author's PC).
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile
from pathlib import Path

if "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools"))

from omni_describer_custom.core import app_update as au  # noqa: E402
from omni_describer_custom.core.updater import UpdateError  # noqa: E402

results: list[tuple[str, bool]] = []
WHERE = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "where.exe"


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def release_json(version="2.1.3", assets=True):
    names = [au.zip_name(version), au.SUMS_NAME] if assets else []
    return {"tag_name": f"v{version}", "body": "- New: it updates itself.",
            "html_url": f"https://github.com/{au.REPO}/releases/tag/v{version}",
            "assets": [{"name": n, "size": 1234,
                        "browser_download_url": (f"https://github.com/{au.REPO}/"
                                                 f"releases/download/v{version}/{n}")}
                       for n in names]}


def make_zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return path


def good_members(marker=b"new"):
    return {"DescriVox/DescriVox.exe": b"MZ fake", "DescriVox/marker.txt": marker,
            "DescriVox/_internal/lib.dll": b"x"}


def pump(seconds: float, until=lambda: False) -> None:
    import wx
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and not until():
        wx.Yield()
        time.sleep(0.03)


# ── Checking ─────────────────────────────────────────────────────

def test_parse_and_compare():
    rel = au.parse_release(release_json())
    assert rel.version == "2.1.3" and rel.tag == "v2.1.3"
    assert rel.zip_url.endswith(au.zip_name("2.1.3"))
    assert rel.sums_url.endswith(au.SUMS_NAME) and "updates itself" in rel.notes
    try:
        au.parse_release(release_json(assets=False))
        raise AssertionError("a release without the zip was accepted")
    except UpdateError:
        pass
    fetch = lambda url: json.dumps(release_json("2.1.3")).encode()  # noqa: E731
    assert au.newer_release(fetch, current="2.1.2").version == "2.1.3"
    assert au.newer_release(fetch, current="2.1.3") is None
    assert au.newer_release(fetch, current="2.2.0") is None


# ── Download and unpack ──────────────────────────────────────────

def _fake_net(zip_bytes: bytes, sums_line: str):
    def fetch(url):
        assert url.endswith(au.SUMS_NAME), url
        return sums_line.encode()

    def download_to(url, dest, on_progress=None, max_bytes=0):
        Path(dest).write_bytes(zip_bytes)
        if on_progress:
            on_progress(len(zip_bytes), len(zip_bytes))
    return fetch, download_to


def test_download_verifies_checksum():
    rel = au.parse_release(release_json())
    tmp = Path(tempfile.mkdtemp(prefix="odc_t76_"))
    data = make_zip(tmp / "src.zip", good_members()).read_bytes()
    import dataclasses
    rel = dataclasses.replace(rel, zip_size=len(data))  # as GitHub reports it
    good = hashlib.sha256(data).hexdigest()
    fetch, dl = _fake_net(data, f"{good}  {au.zip_name('2.1.3')}\n")
    seen = []
    path = au.download(rel, fetch=fetch, download_to=dl,
                       on_progress=lambda d, t: seen.append((d, t)))
    assert path.exists() and au.sha256_of(path) == good and seen
    path.unlink()
    fetch, dl = _fake_net(data, f"{'0' * 64}  {au.zip_name('2.1.3')}\n")
    try:
        au.download(rel, fetch=fetch, download_to=dl)
        raise AssertionError("a zip with the wrong checksum was accepted")
    except UpdateError as e:
        assert "checksum" in str(e)
    assert not list(au.update_dir().glob("*.zip*")), "a refused download was kept"


def test_stage_refuses_bad_zips():
    tmp = Path(tempfile.mkdtemp(prefix="odc_t76_"))
    app = tmp / "DescriVox"
    app.mkdir()
    staged = au.stage(make_zip(tmp / "good.zip", good_members()), app)
    assert staged == tmp / "DescriVox.new" / "DescriVox"
    assert (staged / "marker.txt").read_bytes() == b"new"
    for label, members in (
            ("zip slip", {**good_members(), "DescriVox/../../evil.txt": b"x"}),
            ("other folder", {**good_members(), "Other/x.txt": b"x"}),
            ("absolute", {**good_members(), "/DescriVox/x.txt": b"x"}),
            ("no exe", {"DescriVox/marker.txt": b"x"})):
        try:
            au.stage(make_zip(tmp / f"{label}.zip", members), app)
            raise AssertionError(f"{label}: accepted")
        except UpdateError:
            pass
    assert not (tmp.parent / "evil.txt").exists()


def test_can_self_install():
    assert au.can_self_install(None) == (False, "from_source")
    tmp = Path(tempfile.mkdtemp(prefix="odc_t76_"))
    other = tmp / "Other"
    other.mkdir()
    (other / au.EXE_NAME).write_bytes(b"x")
    assert au.can_self_install(other) == (False, "unknown_layout")
    odd = tmp / "100%" / "DescriVox"
    odd.mkdir(parents=True)
    (odd / au.EXE_NAME).write_bytes(b"x")
    assert au.can_self_install(odd) == (False, "path_chars")
    ok = tmp / "DescriVox"
    ok.mkdir()
    (ok / au.EXE_NAME).write_bytes(b"x")
    assert au.can_self_install(ok) == (True, "")
    assert not list(tmp.glob(".descrivox-write-test-*")), "probe left behind"


# ── The swap, for real ───────────────────────────────────────────

def _swap(case: str, new_exists: bool):
    root = Path(tempfile.mkdtemp(prefix="odc t76 ü "))  # space + non-ASCII
    app = root / "DescriVox"
    app.mkdir()
    shutil.copy(WHERE, app / au.EXE_NAME)
    (app / "marker.txt").write_text("old")
    staged = root / "DescriVox.new" / "DescriVox"
    if new_exists:
        staged.mkdir(parents=True)
        shutil.copy(WHERE, staged / au.EXE_NAME)
        (staged / "marker.txt").write_text("new")
    holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3)"])
    script = au.write_apply_script(app, staged, holder.pid)
    au.launch_apply_script(script).wait(timeout=90)
    assert holder.poll() is not None, f"{case}: swapped while the app still ran"
    log = (au.update_dir() / "apply.log").read_text(encoding="utf-8")
    previous = root / "DescriVox.previous" / "marker.txt"
    return (app / "marker.txt").read_text(), \
        (previous.read_text() if previous.exists() else None), log


def test_swap_waits_then_replaces():
    now, previous, log = _swap("ok", new_exists=True)
    assert (now, previous) == ("new", "old"), (now, previous, log)
    assert "updated" in log, log


def test_swap_rolls_back():
    now, previous, log = _swap("rollback", new_exists=False)
    assert now == "old" and previous is None, (now, previous, log)
    assert "rolling back" in log and "started the old version" in log, log


# ── Review findings (ecc:python-reviewer, 6 Oct 2026), test-first ──

def test_review_timeout_starts_nothing():
    """HIGH: the app never exits -> the script must not start a 2nd copy."""
    root = Path(tempfile.mkdtemp(prefix="odc t76 rv "))
    app = root / "DescriVox"
    app.mkdir()
    shutil.copy(WHERE, app / au.EXE_NAME)
    staged = root / "DescriVox.new" / "DescriVox"
    staged.mkdir(parents=True)
    shutil.copy(WHERE, staged / au.EXE_NAME)
    holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(40)"])
    try:
        script = au.write_apply_script(app, staged, holder.pid, wait_seconds=3)
        au.launch_apply_script(script).wait(timeout=60)
        log = (au.update_dir() / "apply.log").read_text(encoding="utf-8")
        assert "timed out" in log and "started" not in log, log
        assert (app / au.EXE_NAME).exists() and staged.exists()
    finally:
        holder.kill()


def test_review_old_folder_locked():
    """MEDIUM: a DescriVox.previous that cannot be removed -> no nesting."""
    root = Path(tempfile.mkdtemp(prefix="odc t76 rv "))
    app = root / "DescriVox"
    app.mkdir()
    shutil.copy(WHERE, app / au.EXE_NAME)
    (app / "marker.txt").write_text("old")
    staged = root / "DescriVox.new" / "DescriVox"
    staged.mkdir(parents=True)
    shutil.copy(WHERE, staged / au.EXE_NAME)
    old = root / "DescriVox.previous"
    old.mkdir()
    held = open(old / "locked.txt", "w")  # an open file: rmdir cannot remove it
    try:
        holder = subprocess.Popen([sys.executable, "-c", "pass"])
        holder.wait()
        script = au.write_apply_script(app, staged, holder.pid)
        au.launch_apply_script(script).wait(timeout=90)
    finally:
        held.close()
    assert not (old / "DescriVox").exists(), "old app nested inside .previous"
    assert (app / "marker.txt").read_text() == "old"


def test_review_success_cleans_staging():
    """MEDIUM: after a good swap the empty DescriVox.new is removed."""
    root = Path(tempfile.mkdtemp(prefix="odc t76 rv "))
    app = root / "DescriVox"
    app.mkdir()
    shutil.copy(WHERE, app / au.EXE_NAME)
    staged = root / "DescriVox.new" / "DescriVox"
    staged.mkdir(parents=True)
    shutil.copy(WHERE, staged / au.EXE_NAME)
    holder = subprocess.Popen([sys.executable, "-c", "pass"])
    holder.wait()
    au.launch_apply_script(au.write_apply_script(app, staged, holder.pid)).wait(timeout=90)
    assert not (root / "DescriVox.new").exists()


def test_review_urls_size_tag():
    """MEDIUM/LOW: only GitHub release URLs of this repo, a plain version
    tag, and a download no bigger than GitHub said."""
    bad = release_json()
    bad["assets"][0]["browser_download_url"] = "https://evil.example/x.zip"
    for data in (bad, {**release_json(), "tag_name": "v2.1.3/../x"}):
        try:
            au.parse_release(data)
            raise AssertionError(f"accepted {data['tag_name']}")
        except UpdateError:
            pass
    good = release_json()
    for a in good["assets"]:
        a["browser_download_url"] = (f"https://github.com/{au.REPO}/releases/"
                                     f"download/v2.1.3/{a['name']}")
    rel = au.parse_release(good)        # size 1234
    tmp = Path(tempfile.mkdtemp(prefix="odc_t76_"))
    data = make_zip(tmp / "big.zip", {**good_members(), "DescriVox/pad.bin": os.urandom(5000)}).read_bytes()
    fetch, dl = _fake_net(data, f"{hashlib.sha256(data).hexdigest()}  {au.zip_name('2.1.3')}\n")
    try:
        au.download(rel, fetch=fetch, download_to=dl)
        raise AssertionError("a download bigger than the release said was kept")
    except UpdateError:
        pass


def test_review_one_install_at_a_time():
    """MEDIUM: a second install while one runs is refused, not interleaved."""
    with au.install_lock():
        try:
            with au.install_lock():
                raise AssertionError("two installs ran at once")
        except UpdateError:
            pass


def test_review_unsafe_update_dir():
    """MEDIUM: the log folder is checked like the app folder."""
    tmp = Path(tempfile.mkdtemp(prefix="odc_t76_"))
    real = os.environ["ODC_UPDATE_DIR"]
    os.environ["ODC_UPDATE_DIR"] = str(tmp / "50%off")
    try:
        try:
            au.write_apply_script(tmp / "DescriVox", tmp / "s", 1)
            raise AssertionError("a % in the update folder was written into the script")
        except UpdateError:
            pass
    finally:
        os.environ["ODC_UPDATE_DIR"] = real


def test_finish_pending():
    from omni_describer_custom.core.settings_store import SettingsStore
    s = SettingsStore()
    assert au.finish_pending(s, "2.1.2") is None
    au.update_dir().mkdir(parents=True, exist_ok=True)
    au.mark_pending(s, "2.1.3")
    assert au.finish_pending(s, "2.1.2") == ("2.1.3", False)
    assert au.update_dir().exists(), "kept the log of a failed update"
    au.mark_pending(s, "2.1.3")
    assert au.finish_pending(s, "2.1.3") == ("2.1.3", True)
    assert not au.update_dir().exists() and s.get("updates.app_pending") == ""


# ── Release files (build.bat) ────────────────────────────────────

def test_release_files():
    import release_files as rf
    log = ("# Changelog\n\n## What's new in v9.9.9\n\n- Updates itself.\n\n"
           "## What's new in v9.9.8\n\n- Old.\n")
    assert rf.notes_for(log, "9.9.9") == "- Updates itself.\n"
    dist = Path(tempfile.mkdtemp(prefix="odc_t76_dist_"))
    archive = make_zip(dist / au.zip_name("9.9.9"), good_members())
    sums, notes = rf.write(dist, "9.9.9", log)
    line = sums.read_text(encoding="utf-8")
    assert au.expected_sha256(line, archive.name) == au.sha256_of(archive)
    assert notes.read_text(encoding="utf-8") == "- Updates itself.\n"
    # The real CHANGELOG must carry the section the build will ask for.
    from omni_describer_custom import __version__
    real = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    assert rf.notes_for(real, __version__).strip()


def test_publish_preflight():
    """tools/publish_release.py refuses anything the updater would refuse."""
    import publish_release as pr
    dist = Path(tempfile.mkdtemp(prefix="odc_t76_pub_"))
    assert any("missing" in p for p in pr.check_files(dist, "9.9.9"))
    archive = make_zip(dist / au.zip_name("9.9.9"), good_members())
    (dist / au.SUMS_NAME).write_text(f"{au.sha256_of(archive)}  {archive.name}\n",
                                     encoding="utf-8")
    (dist / "release-notes-9.9.9.md").write_text("- Updates itself.\n", encoding="utf-8")
    assert pr.check_files(dist, "9.9.9") == []
    (dist / au.SUMS_NAME).write_text(f"{'0' * 64}  {archive.name}\n", encoding="utf-8")
    assert pr.check_files(dist, "9.9.9"), "a zip not matching its checksum passed"

    class Out:
        def __init__(self, stdout="", returncode=0):
            self.stdout, self.returncode = stdout, returncode
    heads = {"HEAD": "abc", "v9.9.9": "abc"}
    run = lambda cmd: Out(heads.get(cmd[-1], "") if cmd[1] != "rev-list"  # noqa: E731
                          else heads.get(cmd[-1], ""))
    assert pr.check_tag("9.9.9", run) == []
    heads["v9.9.9"] = "old"
    assert pr.check_tag("9.9.9", run) == ["tag v9.9.9 is not HEAD"]
    assert pr.check_gh(lambda cmd: Out(returncode=1)), "gh logged out passed"
    steps = pr.plan("9.9.9", dist)
    assert steps[0] == ["git", "push", "origin", "main"]
    assert steps[1] == ["git", "push", "origin", "v9.9.9"]
    create = steps[2]
    assert create[:4] == ["gh", "release", "create", "v9.9.9"]
    assert str(dist / au.zip_name("9.9.9")) in create and \
        str(dist / au.SUMS_NAME) in create and au.REPO in create


# ── The window (accessibility + wiring) ──────────────────────────

def test_gui():
    import wx
    app = wx.GetApp() or wx.App(False)  # noqa: F841
    from omni_describer_custom.i18n.strings import t
    from omni_describer_custom.ui import app_update_dialog as aud
    from omni_describer_custom.ui.main_frame import MainFrame

    frame = MainFrame()
    real_newer = au.newer_release
    try:
        bar = frame.GetMenuBar()
        app_item = bar.FindItemById(frame._id_check_app_updates)
        yt_item = bar.FindItemById(frame._id_check_updates)
        assert app_item is not None and yt_item is not None
        assert app_item.GetItemLabel() == t("menu.check_updates")
        assert yt_item.GetItemLabel() == t("menu.update_ytdlp")

        rel = au.parse_release(release_json())
        dlg = aud.AppUpdateDialog(frame, frame.settings, check_on_open=False)
        for ctrl in (dlg.install_btn, dlg.page_btn, dlg.skip_btn,
                     dlg.check_btn, dlg.close_btn):
            assert ctrl.GetLabel().replace("&", "").strip(), "unlabelled button"
        for ctrl in (dlg.status_box, dlg.notes_box, dlg.gauge):
            assert ctrl.GetName().strip(), "control has no NVDA name"
        assert not dlg.install_btn.IsEnabled(), "install enabled with nothing to install"
        dlg.show_release(rel)
        assert "2.1.3" in dlg.status_box.GetValue()
        assert "updates itself" in dlg.notes_box.GetValue()
        assert dlg.install_btn.IsEnabled() and dlg.skip_btn.IsEnabled()
        dlg._check_done(None, "")
        assert not dlg.install_btn.IsEnabled()
        dlg._check_done(None, "offline")
        assert "offline" in dlg.status_box.GetValue()
        # From source it cannot replace itself: it says so, downloads nothing.
        dlg.show_release(rel)
        dlg.start_install()
        assert dlg.status_box.GetValue() == t("app_update.cannot_from_source")
        assert not dlg._busy and not list(au.update_dir().glob("*.zip"))
        dlg.skip_version()
        assert frame.settings.get("updates.skipped_version") == "2.1.3"
        dlg._progress("2.1.3", 50)
        assert dlg.gauge.GetValue() == 50 and "50%" in dlg.status_box.GetValue()
        dlg.Destroy()

        # The menu handler itself (pitfall 18): opens and closes.
        opened = {"n": 0}
        real_show = aud.AppUpdateDialog.ShowModal

        def fake_show(self):
            opened["n"] += 1
            return wx.ID_CLOSE
        aud.AppUpdateDialog.ShowModal = fake_show
        au.newer_release = lambda fetch=None, current=None: None
        try:
            frame._on_check_app_updates(None)
            pump(0.5)  # its posted check-on-open runs (and is dropped) now
        finally:
            aud.AppUpdateDialog.ShowModal = real_show
        assert opened["n"] == 1

        # Start-up check: off in Settings -> never asks GitHub.
        asked = {"n": 0}

        def counting(fetch=None, current=None):
            asked["n"] += 1
            return rel
        au.newer_release = counting
        frame.settings.set("updates.check_app_at_start", False)
        frame.check_app_update_at_start()
        pump(0.3)
        assert asked["n"] == 0
        # On, but this version was skipped -> asks, offers nothing.
        frame.settings.set("updates.check_app_at_start", True)
        offered = []
        real_offer = frame._offer_app_update
        frame._offer_app_update = lambda r: offered.append(r)
        try:
            frame.check_app_update_at_start()
            pump(5, lambda: asked["n"] == 1)
            pump(0.4)
            assert asked["n"] == 1 and not offered, "offered a skipped version"
            frame.settings.set("updates.skipped_version", "")
            frame.check_app_update_at_start()
            pump(5, lambda: bool(offered))
            assert offered and offered[0].version == "2.1.3"
        finally:
            frame._offer_app_update = real_offer
        # Not in front, or a dialog open: status bar only, no dialog.
        shown = []
        frame._show_app_update = lambda r: shown.append(r)
        frame._offer_app_update(rel)
        assert "2.1.3" in frame.GetStatusBar().GetStatusText()

        # Never restarts while a video is being processed.
        real_box = wx.MessageBox
        boxes = []
        wx.MessageBox = lambda *a, **k: boxes.append(a) or wx.OK
        frame._processing = True
        try:
            assert frame._install_app_update("2.1.3", Path("x")) is False
        finally:
            frame._processing = False
            wx.MessageBox = real_box
        assert boxes and boxes[0][0] == t("app_update.busy")
        assert not frame.settings.get("updates.app_pending")

        # After a restart: says whether it took.
        au.mark_pending(frame.settings, "2.1.3")
        frame.report_app_update_result()
        assert "2.1.3" in frame.GetStatusBar().GetStatusText()
    finally:
        au.newer_release = real_newer
        frame.Destroy()
        pump(0.2)


def test_settings_switch():
    import wx
    app = wx.GetApp() or wx.App(False)  # noqa: F841
    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.ui import settings_dialog as sd
    s = SettingsStore()
    s.set("updates.check_app_at_start", True)
    dlg = sd.SettingsDialog(None, s)
    real_box = wx.MessageBox
    wx.MessageBox = lambda *a, **k: wx.OK
    try:
        cb = dlg.app_update_check_cb
        assert cb.GetLabel().strip() and cb.GetName() == "check_app_updates"
        assert cb.GetValue() is True
        cb.SetValue(False)
        sd.wx.MessageBox = wx.MessageBox
        dlg._on_apply(None)
        assert s.get("updates.check_app_at_start") is False
    finally:
        wx.MessageBox = real_box
        sd.wx.MessageBox = real_box
        if dlg:
            dlg.Destroy()


def main() -> int:
    check("release parsed, newer only when newer", test_parse_and_compare)
    check("download kept only when the checksum matches", test_download_verifies_checksum)
    check("unpack refuses zip slip, other folders, no exe", test_stage_refuses_bad_zips)
    check("self-install only from a writable DescriVox folder", test_can_self_install)
    check("swap waits for the app to exit, then replaces (real)", test_swap_waits_then_replaces)
    check("swap rolls back when the new folder cannot move (real)", test_swap_rolls_back)
    check("review: wait timed out -> nothing started (real)", test_review_timeout_starts_nothing)
    check("review: locked .previous -> no nesting (real)", test_review_old_folder_locked)
    check("review: good swap removes DescriVox.new (real)", test_review_success_cleans_staging)
    check("review: GitHub URLs only, plain tag, size cap", test_review_urls_size_tag)
    check("review: one install at a time", test_review_one_install_at_a_time)
    check("review: unsafe update folder refused", test_review_unsafe_update_dir)
    check("after the restart: took / did not take", test_finish_pending)
    check("build writes SHA256SUMS.txt and release notes", test_release_files)
    check("publish tool refuses what the updater would refuse", test_publish_preflight)
    check("menu, dialog, start-up offer, busy refusal (GUI)", test_gui)
    check("Settings switch for the start-up check", test_settings_switch)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
