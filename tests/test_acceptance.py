"""Acceptance test: exercise the app's REAL public paths end-to-end.

Unlike the regression suites (which stub engines), this drives:
  - real SettingsStore disk persistence (settings.json round-trip)
  - real TTSEngine with real edge/sapi5 engines and real Windows audio
    playback (speak_and_play -> file -> winsound/MCI)
  - real ProjectStore SQLite persistence
  - real MainFrame + PlayerWindow: press Play, pump the real wx event
    loop, and confirm descriptions are narrated during playback

Network note: edge TTS needs internet; if offline the engine's own
fallback chain uses sapi5 (offline). Either way sound must be produced.
"""
import sys, io, time, tempfile, shutil, os, traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
sys.path.insert(0, "src")

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

def pump(ms):
    """Pump the real wx event loop for ms milliseconds."""
    import wx
    end = time.time() + ms / 1000.0
    while time.time() < end:
        wx.Yield()
        time.sleep(0.02)

# ── 1. Settings: real disk persistence round-trip ─────────────────
def test_settings_persist_on_disk():
    from omni_describer_custom.core.settings_store import SettingsStore

    tmp = tempfile.mkdtemp(prefix="omni_acc_cfg_")
    try:
        s1 = SettingsStore(config_dir=tmp)
        s1.set("tts.default_engine", "sapi5")
        s1.set("tts.engines.sapi5.voice", "")
        s1.set("tts.engines.sapi5.speed", 1.3)

        f = Path(tmp) / "settings.json"
        assert f.exists(), "settings.json not written to disk"
        import json
        raw = json.loads(f.read_text(encoding="utf-8"))
        assert raw["tts"]["default_engine"] == "sapi5", raw

        # Fresh instance (as on app restart) must read the same values
        s2 = SettingsStore(config_dir=tmp)
        assert s2.get("tts.default_engine") == "sapi5"
        assert abs(s2.get("tts.engines.sapi5.speed") - 1.3) < 1e-9
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
check("Settings persist to disk and reload (real SettingsStore)", test_settings_persist_on_disk)

# ── 2. TTS: real engines, real audible playback ───────────────────
def test_real_tts_speak_and_play():
    from omni_describer_custom.core.tts_engine import TTSEngine

    eng = TTSEngine({})  # real settings-less engine, real engines
    avail = eng.get_available_engines()
    print(f"  available engines: {avail}")
    assert avail, "no TTS engine available on this machine"

    t0 = time.time()
    played = eng.speak_and_play("Ujian ketercapaian: implementasi audio sebenar.")
    dt = time.time() - t0
    print(f"  speak_and_play returned {played} in {dt:.1f}s")
    assert played, "speak_and_play did not produce audible playback"
check("TTSEngine.speak_and_play produces real audible audio", test_real_tts_speak_and_play)

# ── 3. Project store: real SQLite persistence ─────────────────────
def test_project_store_sqlite():
    from omni_describer_custom.core.project_store import ProjectStore, Description

    tmp = tempfile.mkdtemp(prefix="omni_acc_prj_")
    try:
        store = ProjectStore(projects_dir=tmp)
        proj = store.create_project("ACCEPTANCE", "C:/nonexistent/video.mp4")
        store.add_description(Description(start_time=0.0, end_time=30.0, text="A dragon flies over the mountains."))

        # Reopen as a fresh store would on restart
        store2 = ProjectStore(projects_dir=tmp)
        loaded = store2.open_project(proj.id)
        assert loaded is not None
        assert len(loaded.descriptions) == 1
        assert loaded.descriptions[0].text.startswith("A dragon")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
check("ProjectStore persists and reloads via SQLite", test_project_store_sqlite)

# ── 4. Full GUI path: MainFrame -> PlayerWindow -> Play -> narration ──
def test_gui_play_narrates():
    import wx
    from omni_describer_custom.ui.main_frame import MainFrame
    from omni_describer_custom.core.project_store import Description

    app = wx.GetApp() or wx.App(False)

    frame = MainFrame()
    assert frame.tts_engine is not None
    assert frame.project_store is not None

    # Create a real project through the app's own store, as the
    # processing pipeline would, then open the player through the
    # app's own entry point.
    store = frame.project_store
    proj = store.create_project("ACCEPTANCE_TEST - delete me", "C:/nonexistent/video.mp4")
    store.set_video_duration(60.0)
    store.add_description(Description(start_time=0.0, end_time=30.0, text="Acceptance narration one."))
    store.add_description(Description(start_time=35.0, end_time=60.0, text="Acceptance narration two."))

    # Wrap the real engine's speak_and_play so we can observe narration
    # requests while the REAL generation+playback chain still runs.
    real_speak_and_play = frame.tts_engine.speak_and_play
    spoken = []
    def observing_speak_and_play(text, *a, **kw):
        spoken.append(text)
        return real_speak_and_play(text, *a, **kw)
    frame.tts_engine.speak_and_play = observing_speak_and_play

    try:
        frame._open_player()  # the app's real player entry point
        # PlayerWindow registers itself as a child; find it
        player = None
        for child in frame.GetChildren():
            if child.GetName() == "player_panel" or type(child).__name__ == "PlayerWindow":
                player = child
                break
        assert player is not None, "PlayerWindow did not open via _open_player"

        # Drive the REAL wx event loop: press Play now, inspect state in
        # ~4s, then stop and exit the loop. Timer ticks and the narration
        # thread run exactly as a user session would.
        result = {}

        def do_play():
            player._do_play()  # simulate pressing Play (VLC unavailable -> simulated)

        def do_inspect():
            result["position"] = player._position
            result["spoken"] = list(spoken)
            result["status"] = player.status_text.GetLabel()
            player._on_stop(None)

        def do_exit():
            try:
                player.Close()
            except Exception:
                pass
            wx.CallAfter(app.ExitMainLoop)

        wx.CallLater(100, do_play)
        wx.CallLater(4000, do_inspect)
        wx.CallLater(4600, do_exit)
        app.MainLoop()

        print(f"  position after ~4s: {result['position']:.1f}s (status: {result['status']})")
        print(f"  narration requests: {result['spoken']}")
        assert result["position"] >= 3.0, f"playback did not advance: {result['position']}"
        assert result["spoken"], "no description was narrated during playback"
        assert any("Acceptance narration" in s for s in result["spoken"]), result["spoken"]
        assert not player._narrated, "narrated set not cleared on stop"
    finally:
        pump(200)
        frame.Destroy()
        # Clean up the acceptance project from the real projects dir
        try:
            db = Path(store.projects_dir) / f"project_{proj.id}.db"
            if db.exists():
                db.unlink()
        except Exception:
            pass
check("Playback narrates descriptions aloud through real windows", test_gui_play_narrates)

print(f"\nRESULT: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
