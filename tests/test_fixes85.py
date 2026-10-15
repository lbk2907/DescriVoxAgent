"""Backward seeks rearm narration without replaying already-ended cues."""

import isolate  # noqa: F401
import ast
import logging
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parent.parent


class SeekNarrationTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / "src/omni_describer_custom/ui/player_window.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PlayerWindow")
        names = {"_rearm_narration_for_seek", "_move_to", "_on_seek", "seek_to", "_maybe_narrate"}
        nodes = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
        scope = {"threading": threading, "logger": logging.getLogger(__name__)}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)
        player = type("HeadlessPlayer", (), {k: scope[k] for k in names if k in scope})
        self.p = player()
        self.p.project = SimpleNamespace(
            descriptions=[
                SimpleNamespace(id=1, start_time=2, end_time=5, text="Earlier"),
                SimpleNamespace(id=2, start_time=8, end_time=12, text="At destination"),
                SimpleNamespace(id=3, start_time=20, end_time=25, text="Later"),
                SimpleNamespace(id=4, start_time=50, end_time=55, text="Furthest"),
            ]
        )
        self.p._position = 50.0
        self.p._narrated = {1, 2, 3, 4}
        self.p._vlc_available = True
        self.p._vlc_media = object()
        self.p._vlc = Mock()
        self.p._audio_backend = "vlc"
        self.p._playing = True
        self.p._clamp_position = lambda p: max(0.0, min(60.0, p))
        self.p._update_desc_display = Mock()
        self.p._show_on_timeline = Mock()
        self.p._restart_sound_soon = Mock()
        self.p._start_ffplay = Mock()
        self.p.position_slider = Mock()
        self.p.position_slider.GetValue.return_value = 10

    def test_all_seek_routes_rearm_active_and_future_cues(self):
        for route in ("buttons", "slider", "agent"):
            with self.subTest(route=route):
                self.p._position = 50
                self.p._narrated = {1, 2, 3, 4}
                if route == "buttons":
                    self.p._move_to(10)
                elif route == "slider":
                    self.p._on_seek(None)
                else:
                    self.p.seek_to(10)
                self.assertEqual(self.p._narrated, {1})
                self.p._vlc.set_time.assert_called_with(10000)

    def test_forward_and_same_position_do_not_rearm(self):
        for destination in (50, 60):
            self.p._move_to(destination)
            self.assertEqual(self.p._narrated, {1, 2, 3, 4})

    def test_gap_keeps_expired_cue_marked(self):
        self.p._move_to(15)
        self.assertEqual(self.p._narrated, {1, 2})

    def test_exact_end_keeps_expired_cue_marked(self):
        self.p._move_to(12)
        self.assertEqual(self.p._narrated, {1, 2})

    def test_seek_to_start_rearms_every_cue(self):
        self.p.seek_to(-10)
        self.assertEqual(self.p._position, 0)
        self.assertEqual(self.p._narrated, set())

    def test_paused_ffplay_slider_does_not_start_audio(self):
        self.p._vlc_available = False
        self.p._audio_backend = "ffplay"
        self.p._playing = False
        self.p._on_seek(None)
        self.assertEqual(self.p._narrated, {1})
        self.p._start_ffplay.assert_not_called()
        self.p._restart_sound_soon.assert_not_called()

    def test_rewound_cue_reaches_tts_once(self):
        self.p._move_to(10)
        self.p._current_desc_idx = 1
        self.p.pause_narration_check = Mock()
        self.p.pause_narration_check.GetValue.return_value = False
        self.p.tts = Mock()
        self.p.tts.speak_and_play.return_value = True
        self.p._maybe_narrate()
        if hasattr(self.p, "_tts_thread"):
            self.p._tts_thread.join(timeout=2)
        self.p.tts.speak_and_play.assert_called_once_with("At destination")
        self.p._maybe_narrate()
        self.p.tts.speak_and_play.assert_called_once()


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    unittest.main(verbosity=2)
