"""Regression round 37: timeline files, frame order, projects, paths.

Each check pins a defect found by running it, not by reading:

  1. Frames past 9,999 sorted as TEXT (frame_10000 between frame_1000
     and frame_1001): a 17-minute video at 10 fps had its ending
     described at 100 s and every later frame shifted.
  2. A description with a blank line split its SRT/VTT cue in two; the
     second paragraph vanished on re-import.
  3. UTF-16 subtitle files imported as nothing; cp1252 ones silently
     turned accented letters into replacement marks.
  4. A SQLite connection left open on an error path kept the .db
     locked on Windows (WinError 32), so it could not be deleted.
  5. A deleted project's id was handed out again, and the new project
     picked up the old project's video.mp4 as its own download.
  6. Subtitle fetches that timed out left yt-dlp/ffmpeg running.
  7. yt-dlp subtitle call: no "--", no --no-playlist, no --write-subs.
  8. .txt import: any "-->" sent the file to the SRT parser (empty
     result); "2024 was..." became a cue at 2024 s.
  Minor: end <= start exported an invalid cue; VTT cues without
  milliseconds were dropped; a failed TTS conversion leaked its clip.
  Also: reserved Windows device names and invisible format characters
  in project names taken from video titles.

No network. bin/ffmpeg.exe synthesises the one real video used.
"""
import asyncio
import io
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
TMP = Path(tempfile.mkdtemp(prefix="odc_fixes37_"))
os.environ.setdefault("ODC_CONFIG_DIR", str(TMP / "config"))

from omni_describer_custom.core import timeline_io as T  # noqa: E402
from omni_describer_custom.core import video_processor as VPM  # noqa: E402
from omni_describer_custom.core.project_store import (  # noqa: E402
    Description as D, ProjectStore)
from omni_describer_custom.core.video_processor import VideoProcessor  # noqa: E402

FFMPEG = ROOT / "bin" / "ffmpeg.exe"

ok_count = 0
fail_count = 0


def check(name, fn):
    global ok_count, fail_count
    try:
        fn()
        ok_count += 1
        print(f"  OK   {name}")
    except Exception:
        fail_count += 1
        print(f"  FAIL {name}")
        traceback.print_exc()


class _Settings:
    def get(self, key, default=None):
        return default

    def get_ai_provider(self, name):
        return {}


def _vp(**kw):
    return VideoProcessor(ffmpeg_path=str(FFMPEG), settings=_Settings(), **kw)


def _write(name, data):
    p = TMP / name
    if isinstance(data, bytes):
        p.write_bytes(data)
    else:
        p.write_text(data, encoding="utf-8")
    return p


# 1 ────────────────────────────────────────────────────────────────
def test_frames_past_9999_keep_their_order():
    import subprocess
    if not FFMPEG.exists():
        raise AssertionError(f"bundled ffmpeg missing: {FFMPEG}")
    src = TMP / "hf.mp4"
    # 1000 fps for 10.02 s = 10,020 frames: past 9,999 in seconds.
    subprocess.run([str(FFMPEG), "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=gray:size=16x16:rate=1000:duration=10.02",
                    "-c:v", "libx264", "-preset", "ultrafast", str(src)],
                   check=True, timeout=120)
    frames = asyncio.run(_vp().extract_frames(
        str(src), fps=1000, output_dir=str(TMP / "hf_frames"),
        detect_scene_changes=False))
    assert len(frames) > 9999, len(frames)
    for i, f in enumerate(frames):
        number = int(Path(f.path).stem.split("_")[1])
        assert number == i + 1, (i, Path(f.path).name, f.timestamp)
    last = frames[-1]
    assert Path(last.path).name == f"frame_{len(frames)}.jpg", last.path
    assert abs(last.timestamp - (len(frames) - 1) / 1000) < 1e-9


def test_frame_sort_key_is_numeric():
    names = ["frame_1001.jpg", "frame_10000.jpg", "frame_1000.jpg",
             "frame_0002.jpg"]
    got = [p.name for p in sorted((Path(n) for n in names),
                                  key=VideoProcessor._frame_number)]
    assert got == ["frame_0002.jpg", "frame_1000.jpg", "frame_1001.jpg",
                   "frame_10000.jpg"], got


# 2 ────────────────────────────────────────────────────────────────
def test_paragraph_break_survives_srt_and_vtt():
    descs = [D(start_time=3661.9996, end_time=3665.5,
               text="First para.\r\n\r\nSecond para.\rThird line.")]
    for name, writer in (("para.srt", T.to_srt), ("para.vtt", T.to_vtt)):
        p = _write(name, writer(descs))
        back = T.parse_any(p)
        assert len(back) == 1, (name, back)
        assert back[0].text == "First para.\nSecond para.\nThird line.", \
            (name, back[0].text)
        assert abs(back[0].start_time - 3662.0) < 1e-6, back[0].start_time


# 3 ────────────────────────────────────────────────────────────────
SRT_BODY = "1\r\n00:00:01,000 --> 00:00:02,000\r\nCafé naïve\r\n"


def test_utf16_with_bom_imports():
    p = _write("u16.srt", SRT_BODY.encode("utf-16"))
    back = T.parse_srt(p)
    assert [d.text for d in back] == ["Café naïve"], back


def test_utf16_without_bom_imports():
    p = _write("u16le.srt", SRT_BODY.encode("utf-16-le"))
    back = T.parse_srt(p)
    assert [d.text for d in back] == ["Café naïve"], back


def test_cp1252_keeps_accents():
    p = _write("ansi.srt", SRT_BODY.encode("cp1252"))
    back = T.parse_srt(p)
    assert [d.text for d in back] == ["Café naïve"], back


def test_utf8_bom_crlf_no_trailing_blank_still_imports():
    p = _write("bom.srt", b"\xef\xbb\xbf" + SRT_BODY.rstrip().encode("utf-8"))
    back = T.parse_srt(p)
    assert [d.text for d in back] == ["Café naïve"], back


# 4 ────────────────────────────────────────────────────────────────
def test_broken_project_db_is_not_left_locked():
    import sqlite3
    store = ProjectStore(str(TMP / "ps_lock"))
    store.create_project("fine", "src")
    bad = store.projects_dir / "project_50.db"
    c = sqlite3.connect(str(bad))
    c.execute("create table x(a)")
    c.commit()
    c.close()
    assert len(store.list_projects()) == 1
    bad.unlink()  # WinError 32 here before the fix
    assert not bad.exists()


# 5 ────────────────────────────────────────────────────────────────
def test_deleted_project_id_is_not_reused_and_media_goes():
    store = ProjectStore(str(TMP / "ps_reuse"))
    a = store.create_project("A", "https://example.invalid/a")
    media = store.media_dir(a.id)
    (media / "video.mp4").write_bytes(b"A's video")
    assert store.delete_project(a.id)
    assert not (store.projects_dir / f"project_{a.id}").exists()
    assert not (store.projects_dir / f"project_{a.id}.db").exists()
    b = store.create_project("B", "https://example.invalid/b")
    assert b.id != a.id, (a.id, b.id)
    assert VideoProcessor.completed_download(
        str(store.media_dir(b.id))) == ""
    # Survives a fresh store (the counter is on disk, not in memory).
    store.delete_project(b.id)
    c = ProjectStore(str(TMP / "ps_reuse")).create_project("C", "x")
    assert c.id > b.id, (b.id, c.id)


def test_project_store_still_round_trips():
    store = ProjectStore(str(TMP / "ps_rt"))
    p = store.create_project("rt", "src")
    store.save_descriptions([D(start_time=1.0, end_time=2.0, text="one")])
    store.add_description(D(start_time=3.0, end_time=4.0, text="two"))
    store.set_video_duration(12.5)
    store.set_video_path("C:/v.mp4")
    first = store.current.descriptions[0].id
    store.delete_description(first)
    again = ProjectStore(str(TMP / "ps_rt")).open_project(p.id)
    assert [d.text for d in again.descriptions] == ["two"], again.descriptions
    assert again.video_duration == 12.5 and again.video_path == "C:/v.mp4"
    assert ProjectStore(str(TMP / "ps_rt")).open_project(999) is None


# 6 + 7 ────────────────────────────────────────────────────────────
class _FakeProc:
    def __init__(self, hang):
        self.hang = hang
        self.returncode = None
        self.killed = False
        self._done = asyncio.Event()

    async def communicate(self):
        if self.hang:
            await self._done.wait()
        self.returncode = 0 if self.returncode is None else self.returncode
        return b"{}", b""

    def kill(self):
        self.killed = True
        self.returncode = 1
        self._done.set()

    async def wait(self):
        await self._done.wait()
        return self.returncode


def _run_with_fake_exec(coro_factory, hang):
    calls = []
    real_exec = VPM.asyncio.create_subprocess_exec
    real_wait_for = VPM.asyncio.wait_for

    async def fake_exec(*args, **kw):
        proc = _FakeProc(hang)
        calls.append((args, proc))
        return proc

    async def short_wait_for(aw, timeout):
        return await real_wait_for(aw, timeout=min(timeout, 0.3))

    VPM.asyncio.create_subprocess_exec = fake_exec
    VPM.asyncio.wait_for = short_wait_for
    try:
        result = asyncio.run(coro_factory())
    finally:
        VPM.asyncio.create_subprocess_exec = real_exec
        VPM.asyncio.wait_for = real_wait_for
    return result, calls


def test_subtitle_timeout_kills_the_child():
    vp = _vp(ytdlp_path="yt-dlp.exe")
    t0 = time.time()
    result, calls = _run_with_fake_exec(
        lambda: vp._ytdlp_subtitles("https://example.invalid/v"), hang=True)
    assert result == [] and time.time() - t0 < 10
    assert calls and calls[0][1].killed, "timed-out yt-dlp was not killed"

    local = _write("dummy.mp4", b"not really a video")
    result, calls = _run_with_fake_exec(
        lambda: vp._embedded_subtitles(str(local)), hang=True)
    assert result == [] and calls[0][1].killed, "timed-out ffmpeg not killed"


def test_ytdlp_arguments_are_safe():
    vp = _vp(ytdlp_path="yt-dlp.exe")
    url = "https://www.youtube.com/watch?v=X&list=PL1"
    _, calls = _run_with_fake_exec(lambda: vp._ytdlp_subtitles(url),
                                   hang=False)
    args = list(calls[0][0])
    for flag in ("--no-playlist", "--write-subs", "--write-auto-sub"):
        assert flag in args, (flag, args)
    assert args[-2:] == ["--", url], args

    _, calls = _run_with_fake_exec(lambda: vp._probe_url(url), hang=False)
    args = list(calls[0][0])
    assert args[-2:] == ["--", url], args


# 8 ────────────────────────────────────────────────────────────────
def test_txt_with_an_arrow_is_still_simple_text():
    p = _write("arrow.txt", "0:05 Arrow --> points left\n0:10 Next\n")
    back = T.parse_any(p)
    assert [(d.start_time, d.text) for d in back] == [
        (5.0, "Arrow --> points left"), (10.0, "Next")], back


def test_prose_number_is_not_a_timestamp():
    p = _write("prose.txt", "0:05 Opening shot\n2024 was a good year\n"
                            "0:20 Next\n90s Ninety\n12.5 Decimal\n")
    back = T.parse_any(p)
    starts = [d.start_time for d in back]
    assert 2024.0 not in starts, starts
    assert starts == [5.0, 20.0, 90.0, 12.5], starts
    assert back[0].end_time < 20.0, back[0].end_time


def test_srt_content_in_txt_still_dispatches():
    p = _write("s.txt", "1\n00:00:01,000 --> 00:00:02,000\nHi\n")
    assert [d.text for d in T.parse_any(p)] == ["Hi"]


# minor ────────────────────────────────────────────────────────────
def test_end_before_start_is_exported_valid():
    srt = T.to_srt([D(start_time=10.0, end_time=0.0, text="zero end")])
    assert "00:00:10,000 --> 00:00:12,000" in srt, srt
    back = T.parse_srt(_write("end.srt", srt))
    assert back[0].end_time > back[0].start_time


def test_vtt_without_milliseconds_and_long_hours():
    p = _write("noms.vtt", "WEBVTT\n\n00:00:03 --> 00:00:04\nno ms\n\n"
                           "100:00:00,000 --> 100:00:02,000\nlong\n")
    back = T.parse_any(p)
    assert [(d.start_time, d.end_time, d.text) for d in back] == [
        (3.0, 4.0, "no ms"), (360000.0, 360002.0, "long")], back


def test_failed_conversion_does_not_leak_the_tts_clip():
    clip = _write("clip.wav", b"RIFF-not-really")

    class _TTS:
        async def speak(self, text, engine, voice, speed):
            return str(clip)

    real = T._to_wav

    def boom(src, dst):
        raise RuntimeError("conversion failed")

    T._to_wav = boom
    try:
        try:
            T.export_audio([D(start_time=0, end_time=1, text="x")],
                           TMP / "out.mp3", _TTS())
        except RuntimeError:
            pass
    finally:
        T._to_wav = real
    assert not clip.exists(), "TTS clip left behind after a failed convert"


# names ────────────────────────────────────────────────────────────
def test_project_names_are_safe_on_windows():
    s = VideoProcessor.sanitize_project_name
    assert s("CON") == "_CON"
    assert s("nul.txt") == "_nul.txt"
    assert s("com1") == "_com1" and s("LPT9.mp4") == "_LPT9.mp4"
    assert s("Console wars") == "Console wars"
    assert s("COM10") == "COM10"
    assert s("evil\u202Egnp.exe") == "evilgnp.exe"
    assert s("a\u200bb\u2066c") == "abc"
    assert s("\u202E") == "video"
    assert s('a/b:c*?"<>|d') == "a b c d"


if __name__ == "__main__":
    print("test_fixes37 — timeline, frame order, projects, paths")
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            check(name[5:].replace("_", " "), fn)
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
