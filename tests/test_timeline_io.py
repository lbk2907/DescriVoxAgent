"""Timeline import/export tests: SRT/VTT/simple parse, round-trip,
and a REAL audio export through the real TTS engine + ffmpeg mix.

Standalone script; exits 0 on success, 1 on failure.
"""

import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import os
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, "src")

from omni_describer_custom.core.timeline_io import (  # noqa: E402
    fmt_srt_time,
    fmt_vtt_time,
    parse_timestamp,
    parse_srt,
    parse_vtt,
    parse_simple,
    parse_any,
    to_srt,
    to_vtt,
    export_audio,
)
from omni_describer_custom.core.project_store import (  # noqa: E402
    Description,
    ProjectStore,
)

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


def test_timestamps():
    assert fmt_srt_time(3661.5) == "01:01:01,500", fmt_srt_time(3661.5)
    assert fmt_vtt_time(3661.5) == "01:01:01.500"
    assert abs(parse_timestamp("01:01:01,500") - 3661.5) < 0.001
    assert abs(parse_timestamp("1:01.5") - 61.5) < 0.001
    assert abs(parse_timestamp("90.5") - 90.5) < 0.001
    assert parse_timestamp("abc") is None


SRT = """1
00:00:01,000 --> 00:00:03,000
Hello world

2
00:00:04,000 --> 00:00:06,500
Second <b>line</b> with tags

"""


def _mkfile(tmp, name, content):
    p = Path(tmp) / name
    p.write_text(content, encoding="utf-8")
    return p


def test_parse_srt(tmp):
    p = _mkfile(tmp, "a.srt", SRT)
    d = parse_srt(p)
    assert len(d) == 2, d
    assert abs(d[0].start_time - 1.0) < 0.001 and abs(d[0].end_time - 3.0) < 0.001
    assert d[0].text == "Hello world"
    assert d[1].text == "Second line with tags", d[1].text  # tags stripped


def test_parse_vtt(tmp):
    p = _mkfile(tmp, "a.vtt", "WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\nFrom VTT\n")
    d = parse_vtt(p)
    assert len(d) == 1 and d[0].text == "From VTT"
    assert abs(d[0].start_time - 1.0) < 0.001


def test_parse_simple(tmp):
    content = (
        "# comment line\n"
        "0:05 A man enters the room\n"
        "00:10 - 00:14 He sits down\n"
        "20.5 <b>The screen shows text</b>\n"
        "not a timed line at all\n"
    )
    p = _mkfile(tmp, "a.txt", content)
    d = parse_simple(p)
    assert len(d) == 3, d
    assert abs(d[0].start_time - 5.0) < 0.001
    assert d[0].end_time > d[0].start_time  # filled from next start
    assert abs(d[1].start_time - 10.0) < 0.001
    assert abs(d[1].end_time - 14.0) < 0.001
    assert abs(d[2].start_time - 20.5) < 0.001
    assert d[2].text == "The screen shows text", d[2].text


def test_parse_any_dispatch(tmp):
    p1 = _mkfile(tmp, "b.txt", SRT)  # srt content in .txt
    assert len(parse_any(p1)) == 2
    p2 = _mkfile(tmp, "c.txt", "0:03 just text\n")
    d = parse_any(p2)
    assert len(d) == 1 and abs(d[0].start_time - 3.0) < 0.001


def test_roundtrip(tmp):
    descs = [
        Description(start_time=1.0, end_time=3.0, text="First"),
        Description(start_time=4.5, end_time=6.0, text="Second, with comma"),
    ]
    srt_path = Path(tmp) / "rt.srt"
    srt_path.write_text(to_srt(descs), encoding="utf-8")
    back = parse_srt(srt_path)
    assert len(back) == 2
    assert abs(back[0].start_time - 1.0) < 0.001 and back[0].text == "First"
    assert abs(back[1].start_time - 4.5) < 0.001 and back[1].text == "Second, with comma"

    vtt_path = Path(tmp) / "rt.vtt"
    vtt_path.write_text(to_vtt(descs), encoding="utf-8")
    back2 = parse_any(vtt_path)
    assert len(back2) == 2 and back2[1].text == "Second, with comma"


def test_project_store_roundtrip(tmp):
    """Import -> project store -> reopen gives the same timed entries."""
    p = _mkfile(tmp, "imp.srt", SRT)
    descs = parse_any(p)
    ps = ProjectStore(projects_dir=str(Path(tmp) / "projects"))
    ps.create_project("Imported", "")
    ps.save_descriptions(descs)
    pid = ps.current.id
    ps2 = ProjectStore(projects_dir=str(Path(tmp) / "projects"))
    proj = ps2.open_project(pid)
    assert len(proj.descriptions) == 2
    assert proj.descriptions[0].text == "Hello world"


def test_export_audio_real(tmp):
    """Real TTS (SAPI5, offline) -> ffmpeg mix -> synchronized output."""
    from omni_describer_custom.core.tts_engine import TTSEngine

    eng = TTSEngine({})
    avail = eng.get_available_engines()
    assert "sapi5" in avail, avail
    descs = [
        Description(start_time=0.0, end_time=2.5, text="Beginning of the timeline."),
        Description(start_time=3.0, end_time=5.5, text="Middle entry for mixing."),
        Description(start_time=6.0, end_time=9.0, text="Final spoken entry here."),
    ]
    out = Path(tmp) / "described.wav"
    result = export_audio(descs, out, eng, engine="sapi5", progress_cb=lambda d, t, s: None)
    assert result["rendered"] == 3, result
    assert result["skipped"] == 0, result
    assert out.exists() and out.stat().st_size > 10000, out.stat().st_size

    # Duration must reach past the last clip's start (>= 6s)
    import subprocess

    dur_out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    duration = float(dur_out.stdout.strip())
    assert duration >= 6.0, duration

    # MP3 variant must also work
    out_mp3 = Path(tmp) / "described.mp3"
    export_audio(descs, out_mp3, eng, engine="sapi5")
    assert out_mp3.exists() and out_mp3.stat().st_size > 5000


def main():
    with tempfile.TemporaryDirectory() as tmp:
        check("timestamps format/parse", test_timestamps)
        check("parse srt", lambda: test_parse_srt(tmp))
        check("parse vtt", lambda: test_parse_vtt(tmp))
        check("parse simple text", lambda: test_parse_simple(tmp))
        check("parse_any dispatch", lambda: test_parse_any_dispatch(tmp))
        check("srt/vtt round-trip", lambda: test_roundtrip(tmp))
        check("project store import round-trip", lambda: test_project_store_roundtrip(tmp))
        check("REAL audio export (sapi5+ffmpeg mix, wav+mp3)", lambda: test_export_audio_real(tmp))
    print(f"\nRESULT: {ok} passed, {fail} failed")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(1 if fail else 0)


if __name__ == "__main__":
    main()
