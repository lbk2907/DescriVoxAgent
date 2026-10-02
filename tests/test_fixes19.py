# -*- coding: utf-8 -*-
"""Regression tests for the v1.5.4 fix pass (full-project audit fixes).

Covers:
1. save_descriptions() writes real DB ids back into the in-memory
   Description objects (v1.5.3 bug: all ids stayed 0, which made the
   player narrate only the first cue and let a single editor delete
   wipe every cue from the project).
2. SettingsStore: DEFAULTS isolation (deep copy), atomic save (no
   .json.tmp left behind), DPAPI-protected keys with legacy XOR
   compat.
3. PromptManager: universal presets with underscores (text_ocr) are
   reachable; language-prefixed presets still work.
4. snap_timestamps merges two model lines that snap onto the same
   grid slot instead of emitting duplicate cues.
5. download_video() rejects non-http(s) URLs with SourceError before
   touching yt-dlp.
6. VideoInfo.has_audio defaults to False and only becomes True when
   ffprobe sees an audio stream.
7. AIEngine._run_ffmpeg_cancellable actually honours is_cancelled.
8. i18n EN/MS key parity after the v1.5.4 string additions.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omni_describer_custom.core.project_store import (  # noqa: E402
    ProjectStore, Description,
)
from omni_describer_custom.core.settings_store import (  # noqa: E402
    SettingsStore, _protect_secret, _unprotect_secret, _simple_encrypt,
)
from omni_describer_custom.core.prompt_manager import PromptManager  # noqa: E402
from omni_describer_custom.core.ai_engine import snap_timestamps  # noqa: E402
from omni_describer_custom.core.video_processor import (  # noqa: E402
    VideoProcessor, VideoInfo, SourceError,
)
from omni_describer_custom.i18n.strings import EN_STRINGS, MS_STRINGS  # noqa: E402

PASS = []


def ok(name, cond, extra=""):
    if cond:
        PASS.append(name)
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        raise AssertionError(name + " " + extra)


def test_p1_ids():
    print("1. save_descriptions assigns real DB ids (P1)")
    with tempfile.TemporaryDirectory() as td:
        ps = ProjectStore(projects_dir=td)
        ps.create_project("t", "v.mp4")
        descs = [
            Description(start_time=0.0, end_time=1.0, text="a"),
            Description(start_time=1.0, end_time=2.0, text="b"),
            Description(start_time=2.0, end_time=3.0, text="c"),
        ]
        ps.save_descriptions(descs)
        ok("ids assigned after save", [d.id for d in descs] == [1, 2, 3],
           str([d.id for d in descs]))
        # Player dedup simulation: with distinct ids every cue narrates.
        narrated = set()
        for d in descs:
            if d.id in narrated:
                continue
            narrated.add(d.id)
        ok("player dedup narrates every cue", len(narrated) == 3)
        # Editor delete-one simulation: exactly one cue goes.
        ps.delete_description(descs[0].id)
        ok("delete removes exactly one cue",
           len(ps.current.descriptions) == 2
           and [d.id for d in ps.current.descriptions] == [2, 3])
        # Reload from disk: same ids come back.
        ps2 = ProjectStore(projects_dir=td)
        p2 = ps2.open_project(1)
        ok("reloaded ids match DB",
           [d.id for d in p2.descriptions] == [2, 3])


def test_settings_store():
    print("2. SettingsStore: isolation, atomic save, DPAPI")
    with tempfile.TemporaryDirectory() as td:
        s = SettingsStore(config_dir=td)
        s.set("general.language", "xx")
        ok("DEFAULTS not polluted", SettingsStore.DEFAULTS["general"]["language"] == "en")
        s2 = SettingsStore(config_dir=td)
        ok("second instance sees saved value", s2.get("general.language") == "xx")
        ok("no .json.tmp left after save",
           not (Path(td) / "settings.json.tmp").exists())
        # Key protection round trip
        s.set_ai_provider("glm", {"api_key": "sk-test-12345", "model": "m"})
        raw = json.loads((Path(td) / "settings.json").read_text(encoding="utf-8"))
        enc = raw["ai"]["providers"]["glm"]["api_key_enc"]
        ok("key not stored in plaintext", "sk-test-12345" not in enc)
        if sys.platform == "win32":
            try:
                import win32crypt  # noqa: F401
                ok("DPAPI format used", enc.startswith("dpapi:"), enc[:10])
            except ImportError:
                pass
        s3 = SettingsStore(config_dir=td)
        ok("key round-trips through file",
           s3.get_ai_provider("glm")["api_key"] == "sk-test-12345")
        ok("legacy XOR value still decryptable",
           _unprotect_secret(_simple_encrypt("legacy-key-1")) == "legacy-key-1")


def test_prompt_manager():
    print("3. PromptManager: onscreen_text reachable, language presets intact")
    with tempfile.TemporaryDirectory() as td:
        pm = PromptManager(SettingsStore(config_dir=td))
        pm.language = "en"
        names_en = pm.get_preset_names()
        # A universal preset whose NAME contains an underscore must not be
        # mistaken for a language-prefixed one (the v1.5.4 bug; the preset
        # carrying that property is called onscreen_text since v1.6.0).
        ok("onscreen_text listed (en)", "onscreen_text" in names_en,
           str(names_en))
        ok("extended listed (en)", "extended" in names_en)
        pm.language = "ms"
        names_ms = pm.get_preset_names()
        ok("onscreen_text listed (ms)", "onscreen_text" in names_ms,
           str(names_ms))
        ok("ms_default surfaces as default (ms)",
           "default" in names_ms and "ms_default" not in names_ms)
        ok("ms_extended surfaces as extended (ms)",
           "extended" in names_ms and "ms_extended" not in names_ms)


def test_snap_timestamps():
    print("4. snap_timestamps merges same-slot duplicates")
    grid = [0.0, 2.0, 4.0, 6.0]
    events = [(1.9, "first"), (2.1, "second"), (5.9, "third")]
    out = snap_timestamps(events, grid)
    ok("no duplicate timestamps", len(out) == 2, str(out))
    ok("texts merged in order", out[0][1] == "first second", str(out))
    ok("sorted output", out[1][0] == 6.0)


def test_download_url_guard():
    print("5. download_video rejects non-http(s) URLs")
    vp = VideoProcessor()
    async def run():
        try:
            await vp.download_video("ftp://example.invalid/x.mp4")
            return "no-error"
        except SourceError:
            return "source-error"
        except Exception as e:  # noqa: BLE001
            return f"other:{type(e).__name__}"
    res = asyncio.run(run())
    ok("SourceError raised without network", res == "source-error", res)
    ok("VideoInfo.has_audio defaults to False", VideoInfo(path="x").has_audio is False)


def test_ffmpeg_cancellable():
    print("6. _run_ffmpeg_cancellable honours cancel")
    from omni_describer_custom.core.ai_engine import GLMProvider
    # _run_ffmpeg_cancellable lives on GLMProvider; skip __init__
    eng = GLMProvider.__new__(GLMProvider)
    tick = {"n": 0}

    def cancel_soon():
        tick["n"] += 1
        return True  # deterministic: cancel from the first poll on

    t0 = time.monotonic()
    try:
        eng._run_ffmpeg_cancellable(
            ["ffmpeg", "-hide_banner", "-nostdin", "-f", "lavfi",
             "-i", "testsrc=duration=30", "-f", "null", "-"],
            cancel_soon, 60)
        ok("cancel raises", False, "no exception raised")
    except RuntimeError as e:
        dt = time.monotonic() - t0
        ok("cancel raises RuntimeError('cancelled')", "cancel" in str(e), str(e))
        ok("cancel is fast (<10 s)", dt < 10, f"{dt:.1f}s")
    # Sanity: without cancel it completes and returns a code.
    ret, tail = eng._run_ffmpeg_cancellable(
        ["ffmpeg", "-hide_banner", "-nostdin", "-f", "lavfi",
         "-i", "testsrc=duration=1", "-f", "null", "-"],
        None, 60)
    ok("uncancelled ffmpeg completes", ret == 0, f"ret={ret} tail={tail[-80:]!r}")


def test_i18n_parity():
    print("7. i18n EN/MS parity")
    en, ms = set(EN_STRINGS), set(MS_STRINGS)
    ok("key sets identical", en == ms,
       f"en-only={sorted(en - ms)[:5]} ms-only={sorted(ms - en)[:5]}")
    ok("dead key main.no_video removed", "main.no_video" not in en)
    ok("new a11y keys exist",
       {"player.ended", "scene.no_ai", "editor.confirm_delete",
        "ask.empty_question", "settings.saved"} <= en)


if __name__ == "__main__":
    test_p1_ids()
    test_settings_store()
    test_prompt_manager()
    test_snap_timestamps()
    test_download_url_guard()
    test_ffmpeg_cancellable()
    test_i18n_parity()
    print(f"ALL {len(PASS)} CHECKS PASS")
