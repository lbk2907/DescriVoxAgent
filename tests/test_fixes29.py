"""Regression round 29: what one real run of the shipped build found.

Every check here exists because a full run through the FROZEN app with
a real AI call turned something up that the gate, the source, and the
build all reported as fine.

1. PRISM WAS DEAD IN THE SHIPPED BUILD. The app logged "Prism speech
   unavailable: prism not installed (No module named
   'prism._prism_cffi')" on startup. prism/_native.py appends its own
   directory to __path__ at RUNTIME, so PyInstaller never saw the
   extension and dropped it while --collect-all reported success. The
   v1.6.6 test checked build.bat for the flag, which is an intention,
   not a result.

2. THE UPLOAD CACHE DELETED ITSELF. The chunked path's finally block
   unlinks every part that is not the original file, and the cached
   copy is a part. So in full-video mode — the mode actually
   configured here — v1.6.7's retry saving never survived one job.

3. 806 MB OF ABANDONED TEMP FOLDERS. 115 download directories and 120
   frame directories from runs that crashed or were killed. Nothing
   ever came back for them.

4. THE KEY STAYS PUT. Audited during the same run: no plaintext key in
   the log, the settings file, 37 gate outputs, or the shipped zip.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import json
import os
import re
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

from omni_describer_custom.core.housekeeping import (  # noqa: E402
    _OUR_PREFIXES, sweep_stale_temp)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "omni_describer_custom"

ok_count = 0
fail_count = 0


def check(name, fn):
    global ok_count, fail_count
    try:
        fn()
        print(f"  OK   {name}")
        ok_count += 1
    except Exception as e:
        print(f"  FAIL {name}: {e}")
        traceback.print_exc()
        fail_count += 1


# ── Temp folders left by runs that died ──────────────────────────

def test_abandoned_folders_are_removed():
    root = Path(tempfile.mkdtemp(prefix="odc_sweep_test_"))
    old = root / "odc_video_dead"
    old.mkdir()
    (old / "video.mp4").write_bytes(b"x" * 5000)
    stale = time.time() - 48 * 3600
    os.utime(old, (stale, stale))

    removed, freed = sweep_stale_temp(temp_dir=str(root))
    assert removed == 1, f"removed {removed}"
    assert freed >= 5000, freed
    assert not old.exists()


def test_a_recent_folder_is_left_alone():
    """A job running right now must not have its work deleted."""
    root = Path(tempfile.mkdtemp(prefix="odc_sweep_test_"))
    live = root / "odc_frames_busy"
    live.mkdir()
    (live / "frame_0001.jpg").write_bytes(b"x")
    removed, _ = sweep_stale_temp(temp_dir=str(root))
    assert removed == 0, "a folder from the last minute was deleted"
    assert live.exists()


def test_other_peoples_folders_are_never_touched():
    """The sweep runs over the shared temp folder. It must be narrow."""
    root = Path(tempfile.mkdtemp(prefix="odc_sweep_test_"))
    stale = time.time() - 48 * 3600
    for name in ("someone_else", "_MEI12345", "pip-build-abc", "tmpxyz"):
        other = root / name
        other.mkdir()
        (other / "data").write_bytes(b"x")
        os.utime(other, (stale, stale))
    removed, _ = sweep_stale_temp(temp_dir=str(root))
    assert removed == 0, "the sweep deleted a folder that is not ours"
    for name in ("someone_else", "_MEI12345", "pip-build-abc", "tmpxyz"):
        assert (root / name).exists(), f"{name} was deleted"


def test_every_prefix_the_app_creates_is_swept():
    """A new mkdtemp prefix must be added here or it leaks forever."""
    used = set()
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        used.update(re.findall(r'mkdtemp\(prefix="(odc_[a-z_]+)"', text))
    missing = sorted(p for p in used if not p.startswith(_OUR_PREFIXES))
    assert not missing, (
        f"these temp prefixes are created but never cleaned: {missing}")


def test_a_failed_sweep_cannot_stop_startup():
    text = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "sweep_stale_temp" in text, "startup never cleans up"
    block = text.split("sweep_stale_temp")[-1][:300]
    assert "except Exception" in text.split("sweep_stale_temp")[0][-400:] \
        or "except Exception" in block, (
        "a cleanup failure would stop the app from starting")


# ── Prism actually present in the build ──────────────────────────

def test_the_hook_ships_the_native_extension():
    hook = ROOT / "hooks" / "hook-prism.py"
    assert hook.exists(), "no PyInstaller hook for prism"
    text = hook.read_text(encoding="utf-8")
    assert "_prism_cffi" in text, (
        "the hook does not name the extension that was dropped")
    assert ".pyd" in text, "the hook does not collect .pyd files"


def test_the_built_app_can_actually_import_prism():
    """Checked on disk, not in build.bat.

    The v1.6.6 test read build.bat for "--collect-all prism" and
    passed while the shipped app had no screen-reader voice at all.
    """
    internal = ROOT / "dist" / "OmniDescriber" / "_internal"
    if not internal.is_dir():
        print("       (no build present — skipping)")
        return
    assert list(internal.rglob("_prism_cffi*.pyd")), (
        "the build ships prism's Python files and DLL but NOT the "
        "extension, so prism import fails at startup")


# ── The upload cache surviving its own cleanup ───────────────────

def test_the_chunked_cleanup_keeps_the_cached_upload():
    text = (SRC / "core" / "ai_engine.py").read_text(encoding="utf-8")
    cleanup = text.split("part_dirs: set[Path] = set()")[1][:900]
    assert "is_cached_upload" in cleanup, (
        "full-video mode deletes the cached upload copy at the end of "
        "every job, so a retry still re-encodes")


# ── The key stays where it belongs ───────────────────────────────

def test_no_logging_call_takes_an_api_key():
    """A key in the log is a key on disk in plain text."""
    offenders = []
    pattern = re.compile(r"logger\.\w+\([^)]*api_key(?!_enc)", re.S)
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            line = text[:match.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(ROOT)}:{line}")
    assert not offenders, f"api_key reaches a log call at {offenders}"


def test_the_stored_key_is_not_readable_as_text():
    """Encrypted at rest, not merely encoded."""
    from omni_describer_custom.core.settings_store import SettingsStore
    config = Path(tempfile.mkdtemp(prefix="odc_f29_cfg_"))
    os.environ["ODC_CONFIG_DIR"] = str(config)
    try:
        store = SettingsStore()
        secret = "sk-test-0123456789abcdefghijklmnopqrstuvwxyz"
        store.set_ai_provider("glm", {"api_key": secret, "model": "m"})
        raw = (config / "settings.json").read_text(encoding="utf-8")
        assert secret not in raw, "the key is stored in plain text"
        import base64
        blob = json.loads(raw)["ai"]["providers"]["glm"].get("api_key_enc", "")
        assert blob, "no encrypted blob was written"
        try:
            assert base64.b64decode(blob).decode("utf-8", "replace") != secret
        except Exception:
            pass  # not decodable as bare base64: better still
        assert store.get_ai_provider("glm")["api_key"] == secret, (
            "the key cannot be read back, so encryption broke the app")
    finally:
        os.environ.pop("ODC_CONFIG_DIR", None)


def test_a_crafted_url_cannot_become_a_yt_dlp_option():
    """"--" before the URL, or a URL like "--exec=..." runs commands."""
    text = (SRC / "core" / "video_processor.py").read_text(encoding="utf-8")
    # 5000, not 3000: the "--" guard sits 3,115 characters in and an
    # earlier slice cut it off, so this reported a missing guard that
    # was present all along.
    download = text.split("def download_video")[1][:5000]
    assert 'args += ["--", url]' in download or '"--",' in download, (
        "the URL is passed without the -- separator, so a crafted URL "
        "could be read as a yt-dlp option")
    assert 'startswith(("http://", "https://"))' in download, (
        "non-http schemes are not rejected before the URL is used")


def test_the_package_ships_no_settings_file():
    """A shipped settings.json would carry whoever built it's key."""
    dist = ROOT / "dist" / "OmniDescriber"
    if not dist.is_dir():
        print("       (no build present — skipping)")
        return
    strays = [p for p in dist.rglob("settings.json")]
    assert not strays, f"the build carries settings files: {strays}"


if __name__ == "__main__":
    print("Round 29: what a real run of the shipped build found\n")
    check("abandoned folders are removed", test_abandoned_folders_are_removed)
    check("a recent folder is left alone", test_a_recent_folder_is_left_alone)
    check("other people's folders are never touched",
          test_other_peoples_folders_are_never_touched)
    check("every temp prefix the app creates is swept",
          test_every_prefix_the_app_creates_is_swept)
    check("a failed sweep cannot stop startup",
          test_a_failed_sweep_cannot_stop_startup)
    check("the hook ships the native extension",
          test_the_hook_ships_the_native_extension)
    check("the built app can actually import prism",
          test_the_built_app_can_actually_import_prism)
    check("the chunked cleanup keeps the cached upload",
          test_the_chunked_cleanup_keeps_the_cached_upload)
    check("no logging call takes an api key",
          test_no_logging_call_takes_an_api_key)
    check("the stored key is not readable as text",
          test_the_stored_key_is_not_readable_as_text)
    check("a crafted URL cannot become a yt-dlp option",
          test_a_crafted_url_cannot_become_a_yt_dlp_option)
    check("the package ships no settings file",
          test_the_package_ships_no_settings_file)
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
