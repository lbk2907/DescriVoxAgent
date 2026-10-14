"""Video-volume regressions without windows, audio devices or owner settings."""

import isolate  # noqa: F401
import ast
import logging
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parent.parent


def player_type():
    path = ROOT / "src/omni_describer_custom/ui/player_window.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PlayerWindow")
    names = {"_change_volume", "_apply_vlc_volume", "_do_play", "_on_timer"}
    nodes = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    scope = {"math": math, "logger": logging.getLogger(__name__), "t": lambda k, **kw: (k, kw)}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)
    return type("HeadlessPlayer", (), {name: scope[name] for name in names if name in scope})


class VolumeTests(unittest.TestCase):
    def setUp(self):
        self.p = player_type()()
        self.p._volume = 20
        self.p._vlc_available = True
        self.p._vlc = Mock()
        self.p._vlc.audio_set_volume.return_value = 0
        self.p._vlc.is_playing.return_value = True
        self.p._vlc.get_time.return_value = 0
        self.p._vlc_media = object()
        self.p._settings = Mock()
        self.p._audio_backend = "vlc"
        self.p._playing = True
        self.p._position = 0
        self.p._last_slider_val = 0
        self.p._vlc_volume_pending = False
        self.p.project = None
        for name in (
            "_announce",
            "_set_play_label",
            "_start_timer",
            "_restart_sound_soon",
            "_learn_length_from_vlc",
            "_update_desc_display",
            "_update_sub_overlay",
            "_maybe_narrate",
        ):
            setattr(self.p, name, Mock())

    def test_ten_percent_is_approximately_ten_percent_signal_gain(self):
        self.p._change_volume(-10)
        sent = self.p._vlc.audio_set_volume.call_args.args[0]
        self.assertAlmostEqual((sent / 100) ** 3, 0.1, delta=0.005)
        self.p._settings.set.assert_called_once_with("player.volume", 10)
        self.p._announce.assert_called_once_with(("player.volume", {"pct": 10}))

    def test_entire_range_is_monotonic_with_exact_silence_and_full_volume(self):
        levels = []
        for pct in range(101):
            self.p._volume = pct
            self.p._change_volume(0)
            level = self.p._vlc.audio_set_volume.call_args.args[0]
            levels.append(level)
            self.assertAlmostEqual((level / 100) ** 3, pct / 100, delta=0.015)
        self.assertEqual(levels, sorted(levels))
        self.assertEqual((levels[0], levels[-1]), (0, 100))

    def test_play_applies_saved_volume_and_reapplies_after_audio_starts(self):
        self.p._volume = 10
        self.p._do_play()
        self.p._vlc.audio_set_volume.assert_called_with(46)
        self.assertTrue(self.p._vlc_volume_pending)
        self.p._vlc.audio_set_volume.reset_mock()
        self.p._on_timer(None)
        self.p._vlc.audio_set_volume.assert_called_once_with(46)
        self.assertFalse(self.p._vlc_volume_pending)
        self.p._on_timer(None)
        self.p._vlc.audio_set_volume.assert_called_once()

    def test_failed_volume_request_retries_with_latest_value(self):
        self.p._vlc.audio_set_volume.return_value = -1
        self.p._change_volume(-10)
        self.assertTrue(self.p._vlc_volume_pending)
        self.p._volume = 50
        self.p._on_timer(None)
        self.assertTrue(self.p._vlc_volume_pending)
        self.p._vlc.audio_set_volume.return_value = 0
        self.p._on_timer(None)
        self.p._vlc.audio_set_volume.assert_called_with(79)
        self.assertFalse(self.p._vlc_volume_pending)

    def test_exception_retries_without_losing_saved_volume(self):
        self.p._vlc.audio_set_volume.side_effect = RuntimeError("audio not ready")
        self.p._change_volume(-10)
        self.assertTrue(self.p._vlc_volume_pending)
        self.assertEqual(self.p._volume, 10)
        self.p._vlc.audio_set_volume.side_effect = None
        self.p._on_timer(None)
        self.assertFalse(self.p._vlc_volume_pending)

    def test_ffplay_keeps_linear_percentage_and_restart(self):
        self.p._vlc_available = False
        self.p._audio_backend = "ffplay"
        self.p._change_volume(-10)
        self.assertEqual(self.p._volume, 10)
        self.p._restart_sound_soon.assert_called_once()
        self.p._vlc.audio_set_volume.assert_not_called()

    def test_bounds_stay_zero_to_one_hundred(self):
        self.p._change_volume(-1000)
        self.p._vlc.audio_set_volume.assert_called_with(0)
        self.assertEqual(self.p._volume, 0)
        self.p._change_volume(1000)
        self.p._vlc.audio_set_volume.assert_called_with(100)
        self.assertEqual(self.p._volume, 100)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    unittest.main(verbosity=2)
