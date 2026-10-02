"""Regression tests round 2: duration persist, TTS settings, VLC fallback."""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import sys, io, traceback, tempfile, sqlite3
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

# 1. set_video_duration persists to DB and survives reopen
def test_duration_persist():
    from omni_describer_custom.core.project_store import ProjectStore
    with tempfile.TemporaryDirectory() as d:
        ps = ProjectStore(projects_dir=d)
        p = ps.create_project("DurPersist", "video.mp4")
        ps.set_video_duration(125.5)
        assert ps.current.video_duration == 125.5
        ps2 = ProjectStore(projects_dir=d)
        p2 = ps2.open_project(p.id)
        assert p2 is not None, "reopen failed"
        assert p2.video_duration == 125.5, f"duration lost: {p2.video_duration}"
check("video_duration persists across reopen", test_duration_persist)

# 2. TTSEngine honors configured default engine
def test_tts_default_engine():
    from omni_describer_custom.core.tts_engine import TTSEngine
    # sapi5 is always available on Windows; force it as preferred
    eng = TTSEngine({"default_engine": "sapi5", "engines": {}})
    assert eng._current_engine == "sapi5", eng._current_engine
check("TTSEngine prefers configured default engine", test_tts_default_engine)

# 3. TTSEngine per-engine settings lookup
def test_tts_engine_settings():
    from omni_describer_custom.core.tts_engine import TTSEngine
    eng = TTSEngine({
        "default_engine": "edge",
        "engines": {
            "edge": {"voice": "en-US-AriaNeural", "speed": 1.5},
        },
    })
    es = eng._engine_settings("edge")
    assert es.get("voice") == "en-US-AriaNeural"
    assert es.get("speed") == 1.5
    assert eng._engine_settings("sapi5") == {}
    assert eng._engine_settings("nonexistent") == {}
check("TTSEngine _engine_settings lookup", test_tts_engine_settings)

# 4. PlayerWindow falls back gracefully without VLC
def test_player_vlc_fallback():
    import wx
    from omni_describer_custom.ui.player_window import PlayerWindow
    from omni_describer_custom.core.project_store import ProjectStore, Description
    from omni_describer_custom.core.tts_engine import TTSEngine
    from omni_describer_custom.core.ai_engine import AIEngine

    app = wx.App(False) if not wx.GetApp() else None
    try:
        with tempfile.TemporaryDirectory() as d:
            ps = ProjectStore(projects_dir=d)
            ps.create_project("VLCFallback", "nonexistent.mp4")
            ps.add_description(Description(start_time=0.0, end_time=5.0, text="D1"))
            frame_holder = {}
            pw = PlayerWindow(None, ps, TTSEngine({}), AIEngine())
            # VLC not installed on this machine -> must fall back
            assert pw._vlc_available is False, "VLC unexpectedly available?"
            # Simulated playback works
            pw._do_play()
            assert pw._playing is True
            pw._on_timer(None)
            assert pw._position > 0
            pw._do_pause()
            assert pw._playing is False
            assert pw.play_btn.GetLabel() == "Play", pw.play_btn.GetLabel()
            pw._on_forward(None)
            assert pw._position >= 10.0, pw._position   # v1.9.6: real clock, not +0.5 a tick
            pw._on_rewind(None)
            pw._on_stop(None)
            assert pw._position == 0.0
            pw._timer.Stop()
            pw.Close()
    finally:
        if app:
            app.Destroy()
check("PlayerWindow simulated playback without VLC", test_player_vlc_fallback)

# 5. Settings dialog accepts tts_engine kwarg and voice list populates
def test_settings_voice_list():
    import wx
    from omni_describer_custom.ui.settings_dialog import SettingsDialog
    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.core.tts_engine import TTSEngine

    app = wx.GetApp() or wx.App(False)
    with tempfile.TemporaryDirectory() as d:
        s = SettingsStore(config_dir=d)
        tts = TTSEngine({})
        dlg = SettingsDialog(None, s, tts)
        # Voice list should contain real voices (edge/sapi5 available)
        items = [dlg.voice_choice.GetString(i) for i in range(dlg.voice_choice.GetCount())]
        assert len(items) >= 1, "voice list empty"
        # API key toggle round-trip: recreate control preserving value
        dlg.api_key_text.SetValue("secret-123")
        class _Ev:
            def IsChecked(self):
                return True
        def masked(ctrl):
            # v1.7.9: the SAME control is switched natively on Windows,
            # so ask Windows, not wx's creation-time style flag.
            if sys.platform == "win32":
                import ctypes
                return bool(ctypes.windll.user32.GetWindowLongW(
                    ctrl.GetHandle(), -16) & 0x20)  # GWL_STYLE, ES_PASSWORD
            return bool(ctrl.GetWindowStyleFlag() & wx.TE_PASSWORD)
        dlg._on_toggle_key(_Ev())
        assert not masked(dlg.api_key_text), "still masked"
        assert dlg.api_key_text.GetValue() == "secret-123", "value lost on toggle"
        dlg._on_toggle_key(_Ev())
        assert masked(dlg.api_key_text), "not re-masked"
        assert dlg.api_key_text.GetValue() == "secret-123", "value lost on re-toggle"
        dlg.Destroy()
check("SettingsDialog voice list + API key toggle", test_settings_voice_list)

# 6. Settings dialog persists voice/speed per engine
def test_settings_persist_voice_speed():
    import wx
    from omni_describer_custom.ui.settings_dialog import SettingsDialog
    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.core.tts_engine import TTSEngine

    app = wx.GetApp() or wx.App(False)
    with tempfile.TemporaryDirectory() as d:
        s = SettingsStore(config_dir=d)
        tts = TTSEngine({})
        dlg = SettingsDialog(None, s, tts)
        dlg.speed_slider.SetValue(13)  # 1.3x
        # Simulate apply for TTS portion only
        # v1.5.4: the choice now shows friendly labels; store the raw id.
        tts_engine = dlg._choice_value(dlg.tts_engine_choice)
        s.set(f"tts.engines.{tts_engine}.speed", dlg.speed_slider.GetValue() / 10.0)
        dlg.Destroy()
        assert s.get(f"tts.engines.{tts_engine}.speed") == 1.3
check("TTS speed persists via settings", test_settings_persist_voice_speed)

print(f"\nRESULT: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
