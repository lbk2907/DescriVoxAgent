"""Regression round 79: audio export offsets and bounded silence budgets."""

import isolate  # noqa: F401 (first: keep tests away from the owner's data)
import array
import io
import json
import math
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

if "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from omni_describer_custom.core import timeline_io  # noqa: E402
from omni_describer_custom.core.project_store import Description  # noqa: E402


class TimelineRegressionTests(unittest.TestCase):
    def export_positions(self, starts, suffix=".wav", skipped=()):
        """Model audio as impulse positions; exercise the real export orchestration.

        Only TTS/ffmpeg are replaced. Copies, temporary files, cue ordering,
        chunk grouping, final encoding selection and cancellation are real.
        """
        with tempfile.TemporaryDirectory(prefix="odc_t79_") as directory:
            root = Path(directory)

            class TTS:
                async def speak(self, text, *args):
                    if int(text) in skipped:
                        return None
                    clip = root / f"speech-{text}.json"
                    clip.write_text(json.dumps([[int(text), 0]]), encoding="utf-8")
                    return str(clip)

            def mix(paths, delays, output):
                impulses = []
                for path, delay in zip(paths, delays, strict=True):
                    impulses.extend(
                        [cue, time + delay]
                        for cue, time in json.loads(Path(path).read_text(encoding="utf-8"))
                    )
                Path(output).write_text(json.dumps(impulses), encoding="utf-8")

            def encode(command, **kwargs):
                shutil.copyfile(command[command.index("-i") + 1], command[-1])

            async def await_speech(coro, is_cancelled):
                return await coro

            engine = types.ModuleType("omni_describer_custom.core.ai_engine")
            engine._run_cancellable = await_speech
            output = root / f"result{suffix}"
            with (
                patch.dict(sys.modules, {engine.__name__: engine}),
                patch.object(timeline_io, "_to_wav", side_effect=shutil.copyfile),
                patch.object(timeline_io, "_mix", side_effect=mix),
                patch.object(timeline_io, "_ffmpeg", return_value="fake-ffmpeg"),
                patch.object(timeline_io.subprocess, "run", side_effect=encode),
            ):
                result = timeline_io.export_audio(
                    [Description(text=str(i), start_time=s) for i, s in enumerate(starts)],
                    output,
                    TTS(),
                )
            self.assertEqual(result["skipped"], len(skipped))
            return sorted(json.loads(output.read_text(encoding="utf-8")))

    def test_audio_keeps_absolute_start_times(self):
        for suffix in (".wav", ".mp3"):
            for starts in ([10.0], [20.0, 10.0], [0.0, 10.0], [0.0], [7.25] * 2):
                with self.subTest(suffix=suffix, starts=starts):
                    self.assertEqual(
                        self.export_positions(starts, suffix),
                        [[i, round(s * 1000)] for i, s in enumerate(starts)],
                    )

    def test_audio_keeps_offsets_across_multiple_mixing_levels(self):
        starts = [10.25 + i * 2 for i in range(33)]
        self.assertEqual(
            self.export_positions(starts),
            [[i, round(s * 1000)] for i, s in enumerate(starts)],
        )

    def test_audio_failed_first_cue_preserves_remaining_position(self):
        self.assertEqual(self.export_positions([0.0, 10.0], skipped=(0,)), [[1, 10000]])

    def test_real_audio_preserves_leading_silence(self):
        """Measure decoded samples without playing audio or calling a provider."""
        from omni_describer_custom.core.tools import find_tool, tool_available

        if tool_available("ffmpeg"):
            ffmpeg = find_tool("ffmpeg")
        else:
            try:
                import imageio_ffmpeg
            except ImportError:
                self.skipTest("No ffmpeg available for optional waveform verification")
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

        rate = 44100
        tone = array.array(
            "h", (round(10000 * math.sin(2 * math.pi * 1000 * i / rate)) for i in range(4410))
        )
        if sys.byteorder != "little":
            tone.byteswap()

        async def await_speech(coro, is_cancelled):
            return await coro

        engine = types.ModuleType("omni_describer_custom.core.ai_engine")
        engine._run_cancellable = await_speech
        with tempfile.TemporaryDirectory(prefix="odc_t79_") as directory:
            root = Path(directory)

            class TTS:
                async def speak(self, text, *args):
                    clip = root / f"speech-{text}.wav"
                    with wave.open(str(clip), "wb") as output:
                        output.setnchannels(1)
                        output.setsampwidth(2)
                        output.setframerate(rate)
                        output.writeframes(tone.tobytes())
                    return str(clip)

            for suffix in (".wav", ".mp3"):
                for starts in ([1.0], [1.0, 2.0]):
                    with self.subTest(suffix=suffix, starts=starts):
                        output = root / f"result{suffix}"
                        with (
                            patch.dict(sys.modules, {engine.__name__: engine}),
                            patch.object(timeline_io, "_ffmpeg", return_value=ffmpeg),
                        ):
                            timeline_io.export_audio(
                                [
                                    Description(text=str(i), start_time=start)
                                    for i, start in enumerate(starts)
                                ],
                                output,
                                TTS(),
                            )
                        decoded = subprocess.run(
                            [
                                ffmpeg,
                                "-v",
                                "error",
                                "-i",
                                str(output),
                                "-f",
                                "s16le",
                                "-ac",
                                "1",
                                "-ar",
                                str(rate),
                                "pipe:1",
                            ],
                            capture_output=True,
                            check=True,
                            timeout=30,
                        )
                        samples = array.array("h", decoded.stdout)
                        if sys.byteorder != "little":
                            samples.byteswap()
                        onsets = []
                        previous = -rate
                        for i, sample in enumerate(samples):
                            if abs(sample) > 500:
                                if i - previous > rate * 0.05:
                                    onsets.append(i / rate)
                                previous = i
                        duration = len(samples) / rate
                        print(
                            f"WAVEFORM {suffix} starts={starts}: onsets={onsets}, {duration=:.4f}"
                        )
                        self.assertEqual(len(onsets), len(starts))
                        for measured, expected in zip(onsets, starts, strict=True):
                            self.assertAlmostEqual(measured, expected, delta=0.01)
                        self.assertAlmostEqual(duration, starts[-1] + 0.1, delta=0.03)

    def test_silence_gaps_respect_requested_range(self):
        cases = [
            ([(10, 20), (70, 80)], 0, 30, [(0, 10), (20, 30)]),
            ([(0, 10), (70, 80)], 20, 30, [(20, 30)]),
            ([(0, 25), (24, 27), (29, 40)], 20, 30, [(27, 29)]),
            ([(20, 50)], 20, 30, []),
            ([(30, 40)], 20, 30, [(20, 30)]),
            ([], 20, 30, [(20, 30)]),
            ([(10, 20)], 30, 20, []),
            ([(70, 80)], 30, 30, []),
            ([(10, 20), (30, 40)], 0, None, [(0, 10), (20, 30)]),
            ([(10, 20)], 19.5, 20.5, []),
        ]
        for spans, start, end, expected in cases:
            with self.subTest(spans=spans, start=start, end=end):
                segments = [types.SimpleNamespace(start=a, end=b) for a, b in spans]
                self.assertEqual(timeline_io.silent_gaps(segments, start, end), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
