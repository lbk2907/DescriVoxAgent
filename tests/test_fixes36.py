"""Regression round 36: settings.json must never lose the user's keys.

Audit findings (Sep 2026), each reproduced before the fix:

  1. A settings.json that failed to parse (crash mid-write) was replaced
     by defaults on the next save: every saved API key gone. Saves were
     a plain write_text, so a crash could produce exactly that file.
  2. A key DPAPI could not decrypt (profile restored on another PC) came
     back "" and the next save dropped its blob for good.
  3. main_frame, player_window and video_processor each made their own
     SettingsStore; each saved its own stale snapshot, so toggling
     "pause for narration" in the player undid a key saved meanwhile.
  4. set() crashed with TypeError on a section of the wrong type.
  5. On Windows a DPAPI failure silently fell back to XOR, which anyone
     with the source can reverse.

Run: python tests/test_fixes36.py   (exits non-zero on any failure)
"""
import io
import json
import os
import sys
import tempfile
import threading
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

_CFG = tempfile.mkdtemp(prefix="odc_f36_env_")
os.environ["ODC_CONFIG_DIR"] = _CFG

from omni_describer_custom.core import settings_store as ss  # noqa: E402
from omni_describer_custom.core.settings_store import SettingsStore  # noqa: E402

ok_count = 0
fail_count = 0
FAKE = "fake-test-key-0123456789"


def check(name, fn):
    global ok_count, fail_count
    try:
        fn()
        print(f"  PASS  {name}")
        ok_count += 1
    except Exception:
        print(f"  FAIL  {name}")
        traceback.print_exc()
        fail_count += 1


def _dir():
    return Path(tempfile.mkdtemp(prefix="odc_f36_"))


def _raw(d):
    return json.loads((d / "settings.json").read_text(encoding="utf-8"))


def test_truncated_file_is_kept_not_overwritten():
    d = _dir()
    SettingsStore(str(d)).set_ai_provider("glm", {"api_key": FAKE, "model": "m"})
    text = (d / "settings.json").read_text(encoding="utf-8")
    half = text[: len(text) // 2]
    (d / "settings.json").write_text(half, encoding="utf-8")
    s = SettingsStore(str(d))
    s.set("general.language", "ms")
    kept = list(d.glob("settings.json.corrupt-*"))
    assert len(kept) == 1, f"corrupt file not set aside: {list(d.iterdir())}"
    assert kept[0].read_text(encoding="utf-8") == half, "corrupt copy altered"
    assert _raw(d)["general"]["language"] == "ms", "new file not usable"


def test_non_object_top_level_is_set_aside():
    d = _dir()
    (d / "settings.json").write_text("[1, 2]", encoding="utf-8")
    s = SettingsStore(str(d))
    assert s.get("general.frame_rate") == 5
    assert list(d.glob("settings.json.corrupt-*")), "list file not kept"


def test_save_is_atomic_and_leaves_no_temp():
    d = _dir()
    s = SettingsStore(str(d))
    real_replace = os.replace
    calls = []

    def spy(src, dst):
        calls.append((str(src), str(dst)))
        return real_replace(src, dst)
    ss.os.replace = spy
    try:
        s.set("general.language", "xx")
    finally:
        ss.os.replace = real_replace
    assert calls and calls[-1][1].endswith("settings.json"), calls
    assert not list(d.glob("*.tmp")), list(d.iterdir())


def test_failed_write_keeps_old_file():
    d = _dir()
    s = SettingsStore(str(d))
    s.set_ai_provider("glm", {"api_key": FAKE, "model": "m"})
    before = (d / "settings.json").read_bytes()
    real_replace = os.replace

    def boom(src, dst):
        raise OSError("disk full (simulated)")
    ss.os.replace = boom
    try:
        s.set("general.language", "zz")
    finally:
        ss.os.replace = real_replace
    assert (d / "settings.json").read_bytes() == before, "file damaged"
    assert not list(d.glob("*.tmp")), "temp file left behind"


def test_undecryptable_key_blob_is_kept():
    d = _dir()
    SettingsStore(str(d)).set_ai_provider("glm", {"api_key": FAKE, "model": "m"})
    raw = _raw(d)
    raw["ai"]["providers"]["glm"]["api_key_enc"] = "dpapi:AAAA"
    (d / "settings.json").write_text(json.dumps(raw), encoding="utf-8")
    s = SettingsStore(str(d))
    assert s.get_ai_provider("glm")["api_key"] == "", "getter must give ''"
    s.set("general.language", "ms")
    assert _raw(d)["ai"]["providers"]["glm"].get("api_key_enc") == "dpapi:AAAA", \
        "blob dropped on save"
    # Entering a new key replaces it.
    s.set_ai_provider("glm", {"api_key": FAKE, "model": "m"})
    assert _raw(d)["ai"]["providers"]["glm"]["api_key_enc"] != "dpapi:AAAA"
    assert SettingsStore(str(d)).get_ai_provider("glm")["api_key"] == FAKE


def test_instances_share_state_no_lost_update():
    d = _dir()
    main = SettingsStore(str(d))
    player = SettingsStore(str(d))       # opened before the key is set
    main.set_ai_provider("gemini", {"api_key": FAKE, "model": "m"})
    player.set("player.pause_for_narration", False)
    fresh = SettingsStore(str(d))
    assert fresh.get_ai_provider("gemini").get("api_key") == FAKE, \
        "player save lost the key"
    assert fresh.get("player.pause_for_narration") is False
    main.set("general.language", "ms")
    assert SettingsStore(str(d)).get("player.pause_for_narration") is False, \
        "main save undid the player toggle"


def test_file_changed_on_disk_is_reloaded():
    d = _dir()
    SettingsStore(str(d)).set("general.language", "en")
    raw = _raw(d)
    raw["general"]["language"] = "ms"
    (d / "settings.json").write_text(json.dumps(raw), encoding="utf-8")
    assert SettingsStore(str(d)).get("general.language") == "ms"


def test_odc_config_dir_env_still_used():
    s = SettingsStore()
    assert Path(s.settings_file).parent == Path(_CFG), s.settings_file
    s.set("general.language", "ms")
    assert (Path(_CFG) / "settings.json").exists()


def test_threads_do_not_corrupt():
    d = _dir()
    stores = [SettingsStore(str(d)) for _ in range(4)]
    errs = []

    def work(i):
        try:
            for k in range(25):
                stores[i].set(f"x.k{i}", k)
        except Exception as e:  # pragma: no cover
            errs.append(repr(e))
    ts = [threading.Thread(target=work, args=(i,)) for i in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errs, errs
    raw = _raw(d)
    assert all(raw["x"][f"k{i}"] == 24 for i in range(4)), raw["x"]


def test_defaults_merged_and_bad_sections_repaired():
    d = _dir()
    (d / "settings.json").write_text(json.dumps({
        "general": "oops",
        "ai": {"providers": {"glm": {"api_key": "", "model": "mine"}}},
    }), encoding="utf-8")
    s = SettingsStore(str(d))
    assert s.get("general.chunk_seconds") == 300   # v1.8.6 default
    assert s.get("player.pause_for_narration") is True
    assert s.get_ai_provider("glm") == {"api_key": "", "model": "mine"}, \
        "saved provider config must not be altered"
    assert "gemini" in s.get("ai.providers")
    s.set("general.language", "ms")          # used to raise TypeError
    s.set("general.language.sub", 1)          # scalar in the way
    assert s.get("general.language.sub") == 1
    assert not list(d.glob("settings.json.corrupt-*")), \
        "a valid file must not be treated as corrupt"


def test_dpapi_failure_does_not_write_xor():
    if sys.platform != "win32":
        return
    d = _dir()
    s = SettingsStore(str(d))
    real = ss.win32crypt

    class Broken:
        @staticmethod
        def CryptProtectData(*a, **k):
            raise RuntimeError("simulated DPAPI failure")

        CryptUnprotectData = staticmethod(
            getattr(real, "CryptUnprotectData", lambda *a: None))
    ss.win32crypt = Broken
    try:
        s.set_ai_provider("glm", {"api_key": FAKE, "model": "m"})
    finally:
        ss.win32crypt = real
    glm = _raw(d)["ai"]["providers"]["glm"]
    assert "api_key_enc" not in glm and "api_key" not in glm, glm
    assert FAKE not in (d / "settings.json").read_text(encoding="utf-8")
    assert s.get_ai_provider("glm")["api_key"] == FAKE, "session lost key"


def test_legacy_xor_blob_still_read_and_migrated():
    d = _dir()
    (d / "settings.json").write_text(json.dumps({"ai": {"providers": {
        "glm": {"api_key_enc": ss._simple_encrypt(FAKE), "model": "m"}}}}),
        encoding="utf-8")
    s = SettingsStore(str(d))
    assert s.get_ai_provider("glm")["api_key"] == FAKE
    s.set("general.language", "ms")
    enc = _raw(d)["ai"]["providers"]["glm"]["api_key_enc"]
    if sys.platform == "win32" and ss.win32crypt is not None:
        assert enc.startswith("dpapi:"), "legacy key not migrated to DPAPI"


if __name__ == "__main__":
    print("test_fixes36: settings store safety")
    check("truncated file is kept, not overwritten",
          test_truncated_file_is_kept_not_overwritten)
    check("non-object top level is set aside",
          test_non_object_top_level_is_set_aside)
    check("save is atomic and leaves no temp", test_save_is_atomic_and_leaves_no_temp)
    check("failed write keeps old file", test_failed_write_keeps_old_file)
    check("undecryptable key blob is kept", test_undecryptable_key_blob_is_kept)
    check("instances share state (no lost update)",
          test_instances_share_state_no_lost_update)
    check("file changed on disk is reloaded", test_file_changed_on_disk_is_reloaded)
    check("ODC_CONFIG_DIR still honoured", test_odc_config_dir_env_still_used)
    check("threads do not corrupt", test_threads_do_not_corrupt)
    check("defaults merged, bad sections repaired",
          test_defaults_merged_and_bad_sections_repaired)
    check("DPAPI failure does not write XOR", test_dpapi_failure_does_not_write_xor)
    check("legacy XOR blob read and migrated",
          test_legacy_xor_blob_still_read_and_migrated)
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
