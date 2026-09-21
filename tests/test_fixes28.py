"""Regression round 28: interrupted work survives (v1.6.7).

Three things the user asked for, and the faults found while building
them — each of which only appeared by running the thing, not reading it.

RESUMABLE DOWNLOADS. yt-dlp continues a .part file by default, so the
capability was always there; every attempt just landed in a fresh
mkdtemp, orphaning the partial where nothing would look for it again.
Downloads now go to the project's media folder. Measured on a real
interrupted run: stopped at 4,193,280 bytes, restarted, yt-dlp printed
"Resuming download at byte 4193280" and finished a valid file.

  Fault found by doing this: making downloads resumable EXPOSED a
  latent bug. download_video returned sorted(glob("video.*"))[0], and
  "video.f616.mp4" sorts before "video.mp4" — so with an intermediate
  stream left over from an interrupted run, the app would have taken
  the video-only stream and described a SILENT video. yt-dlp normally
  deletes its own intermediates, which is why a fresh temp dir hid it.

RESUMABLE UPLOADS. GLM sends video base64 inside one chat request;
there is no resume at the protocol level and pretending otherwise
would be a lie. What IS recoverable is the re-encode, which used to be
deleted in a finally block and redone from scratch on every retry.
Measured on a 60-second clip: 16.2s the first time, 0.00s the second.

  Fault found by doing this: the encode failure paths called
  rmtree(out_dir), which was a private mkdtemp before and is now the
  PROJECT'S media folder — it would have deleted the user's downloaded
  video to clean up after a failed compression.

  Second fault: staging the encode as ".part" broke ffmpeg, which
  picks its muxer from the extension ("Error initializing the muxer").

PLAY WHAT IS ALREADY DESCRIBED. The pieces existed but nothing joined
them: importing an SRT made a project with no video, so the player
opened with descriptions over silence.
"""
import io
import os
import sys
import tempfile
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

import wx  # noqa: E402

from omni_describer_custom.core.ai_engine import AIEngine, GLMProvider  # noqa: E402
from omni_describer_custom.core.video_processor import VideoProcessor  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "omni_describer_custom"

ok_count = 0
fail_count = 0
_app = None


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


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="odc_f28_"))


# ── Resumable downloads ──────────────────────────────────────────

def test_an_intermediate_stream_is_not_a_finished_video():
    """The silent-video bug, pinned.

    video.f616.mp4 is the video stream before it is merged with audio.
    Treating it as complete meant describing a video with no sound
    while skipping the rest of the download.
    """
    d = _tmp()
    for name in ("video.f616.mp4", "video.f251.webm",
                 "video.mp4.part", "video.mp4.ytdl"):
        (d / name).write_bytes(b"x" * 100)
    assert VideoProcessor.completed_download(str(d)) == "", (
        "an unmerged stream was reported as a finished download")


def test_the_merged_video_is_found():
    d = _tmp()
    (d / "video.f616.mp4").write_bytes(b"x" * 100)
    (d / "video.mp4").write_bytes(b"x" * 500)
    found = VideoProcessor.completed_download(str(d))
    assert Path(found).name == "video.mp4", found


def test_other_containers_still_count():
    """--merge-output-format is not always mp4."""
    d = _tmp()
    (d / "video.mkv").write_bytes(b"x" * 10)
    assert Path(VideoProcessor.completed_download(str(d))).name == "video.mkv"


def test_an_empty_or_missing_directory_is_not_a_video():
    assert VideoProcessor.completed_download(str(_tmp())) == ""
    assert VideoProcessor.completed_download(r"Z:\no\such\place") == ""


def test_a_zero_byte_file_is_not_a_video():
    d = _tmp()
    (d / "video.mp4").write_bytes(b"")
    assert VideoProcessor.completed_download(str(d)) == ""


def test_partial_bytes_counts_what_can_be_resumed():
    d = _tmp()
    assert VideoProcessor._partial_bytes(str(d)) == 0
    (d / "video.f616.mp4.part").write_bytes(b"x" * 1000)
    (d / "video.f251.webm.part").write_bytes(b"x" * 500)
    (d / "video.mp4").write_bytes(b"x" * 99)  # finished, not a partial
    assert VideoProcessor._partial_bytes(str(d)) == 1500


def test_resolve_source_takes_a_download_directory():
    """Without out_dir threaded through, nothing else here matters."""
    import inspect
    sig = inspect.signature(VideoProcessor.resolve_source)
    assert "out_dir" in sig.parameters, (
        "resolve_source cannot be told where to download, so the "
        "partial would be orphaned in a temp dir again")


def test_the_pipeline_creates_the_project_before_downloading():
    text = (SRC / "ui" / "main_frame.py").read_text(encoding="utf-8")
    assert "_ensure_project_for" in text
    # [-1]: the name appears at its definition too; the CALL is last.
    before = text.split("_ensure_project_for(source)")[-1]
    first_resolve = before.find("vp.resolve_source")
    assert first_resolve > 0, (
        "the download happens before the project exists, so there is "
        "nowhere stable to resume into")
    assert text.count("out_dir=download_dir") == 2, (
        "not every download path was given the project folder")


def test_a_project_holding_a_partial_download_is_kept():
    """Tidying up must not delete the thing being resumed."""
    text = (SRC / "ui" / "main_frame.py").read_text(encoding="utf-8")
    body = text.split("def _discard_project_if_empty")[1][:1200]
    assert "iterdir()" in body, (
        "the cleanup does not look at whether a partial download is "
        "there, so cancelling would delete it")


# ── The compressed upload copy ───────────────────────────────────

def test_the_cache_name_follows_the_encode_settings():
    """Changing the recipe must not serve a stale encode."""
    provider = GLMProvider(api_key="x")
    d = _tmp()
    source = d / "clip.mp4"
    source.write_bytes(b"x" * 1000)
    base = provider.upload_cache_name(source, 40_000_000)
    assert base == provider.upload_cache_name(source, 40_000_000), (
        "the same job produced two different cache names")
    assert base != provider.upload_cache_name(source, 20_000_000)
    original = provider._UPLOAD_FPS
    try:
        provider._UPLOAD_FPS = original + 1
        assert base != provider.upload_cache_name(source, 40_000_000), (
            "bumping the frame rate still hits the old cached file")
    finally:
        provider._UPLOAD_FPS = original


def test_a_changed_source_gets_a_new_cache_name():
    provider = GLMProvider(api_key="x")
    d = _tmp()
    source = d / "clip.mp4"
    source.write_bytes(b"x" * 1000)
    before = provider.upload_cache_name(source, 40_000_000)
    source.write_bytes(b"y" * 2000)
    assert before != provider.upload_cache_name(source, 40_000_000)


def test_a_cached_copy_is_not_deleted_after_use():
    provider = GLMProvider(api_key="x")
    assert provider.is_cached_upload(Path("upload_abc123.mp4")) is True
    assert provider.is_cached_upload(Path("clip.mp4")) is False
    # A half-written encode must never be kept or uploaded.
    assert provider.is_cached_upload(
        Path("upload_abc123.partial.mp4")) is False


def test_staging_keeps_an_extension_ffmpeg_understands():
    """ffmpeg picks its muxer from the extension.

    Staging as ".part" failed outright with "Error initializing the
    muxer ... Invalid argument", so nothing was ever compressed.
    """
    text = (SRC / "core" / "ai_engine.py").read_text(encoding="utf-8")
    body = text.split("def compress_video_for_upload")[1][:2000]
    assert 'with_suffix(".part")' not in body, (
        "the staging file has no real container extension")
    assert ".partial" in body, "no staging name is used at all"


def test_a_failed_encode_never_deletes_the_directory():
    """out_dir is the project's media folder now.

    rmtree there would take the user's downloaded video with it.
    """
    text = (SRC / "core" / "ai_engine.py").read_text(encoding="utf-8")
    body = text.split("def _compress_to")[1][:3000]
    assert "rmtree(out_dir" not in body, (
        "a failed compression would delete the project's media folder")
    assert "out.unlink" in body, "the half-written output is not cleaned up"


def test_the_cache_directory_reaches_every_provider():
    engine = AIEngine()
    engine.upload_cache_dir = r"C:\somewhere"
    engine.set_provider("glm", api_key="k")
    assert engine.get_provider("glm").upload_cache_dir == r"C:\somewhere", (
        "a provider created after the cache dir was set did not get it")
    engine.upload_cache_dir = r"C:\elsewhere"
    assert engine.get_provider("glm").upload_cache_dir == r"C:\elsewhere", (
        "changing the cache dir did not reach an existing provider")


def test_compression_falls_back_to_a_temp_dir():
    """No cache dir must behave exactly as it always did."""
    import inspect
    sig = inspect.signature(GLMProvider.compress_video_for_upload)
    assert sig.parameters["cache_dir"].default == "", (
        "callers without a project would be forced into a cache")


# ── Play a video that already has descriptions ───────────────────

def test_sibling_subtitles_are_matched_by_exact_stem():
    """A loose .srt in the folder is somebody else's film."""
    from omni_describer_custom.ui.main_frame import MainFrame
    d = _tmp()
    video = d / "holiday.mp4"
    video.write_bytes(b"x")
    (d / "something_else.srt").write_text("1\n", encoding="utf-8")
    assert MainFrame._find_sibling_subtitles(video) is None, (
        "an unrelated subtitle file was adopted")
    wanted = d / "holiday.srt"
    wanted.write_text("1\n", encoding="utf-8")
    assert MainFrame._find_sibling_subtitles(video) == wanted


def test_opening_an_existing_pair_gives_the_player_both_halves():
    """The gap this closes: import used to leave the video behind."""
    from omni_describer_custom.core.project_store import ProjectStore
    from omni_describer_custom.ui.main_frame import MainFrame

    d = _tmp()
    video = d / "clip.mp4"
    video.write_bytes(b"not really a video, but a real file")
    subs = d / "clip.srt"
    subs.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nA man walks in.\n\n"
        "2\n00:00:05,000 --> 00:00:07,000\nHe sits down.\n",
        encoding="utf-8")

    frame = MainFrame()
    opened = []
    try:
        frame.project_store = ProjectStore(projects_dir=str(_tmp()))
        frame._open_player = lambda: opened.append(True)
        frame._open_existing(video, subs)

        project = frame.project_store.current
        assert project is not None, "no project was created"
        assert len(project.descriptions) == 2, project.descriptions
        assert project.video_path, (
            "the project has descriptions but NO video — this is exactly "
            "the old Import Descriptions behaviour, descriptions over "
            "silence")
        assert Path(project.video_path).exists(), project.video_path
        assert opened, "the player was never opened"
    finally:
        app = wx.GetApp()
        for _ in range(6):
            app.ProcessPendingEvents()
            app.Yield()
        try:
            frame.Destroy()
        except Exception:
            pass
        for _ in range(4):
            app.ProcessPendingEvents()
            app.Yield()


def test_the_button_sits_next_to_local_video_file_under_tab():
    """On MSW the Tab order follows creation order, not sizer order.

    Verified by listening as well (tools/nvda_accessibility_check.py):
    Local Video File -> Play Video with Existing Descriptions ->
    Direct Video URL.
    """
    text = (SRC / "ui" / "main_frame.py").read_text(encoding="utf-8")
    assert "MoveAfterInTabOrder(self.btn_local)" in text, (
        "the new button would be last under Tab despite sitting second "
        "on screen")


def test_the_button_is_disabled_while_a_job_runs():
    text = (SRC / "ui" / "main_frame.py").read_text(encoding="utf-8")
    assert "self.btn_play_existing.Disable()" in text
    assert "self.btn_play_existing.Enable()" in text


def test_both_languages_describe_the_new_button():
    import json
    for code in ("en", "ms"):
        data = json.loads((SRC / "i18n" / "locales" / f"{code}.json").read_text(
            encoding="utf-8"))
        for key in ("main.play_existing", "main.play_existing_hint",
                    "main.play_existing_pick_video",
                    "main.play_existing_pick_subs",
                    "main.play_existing_found",
                    "main.play_existing_ready"):
            assert data.get(key), f"{code}.json has no {key}"
        assert "{name}" in data["main.play_existing_found"]
        assert "{count}" in data["main.play_existing_ready"]


if __name__ == "__main__":
    os.environ.setdefault("ODC_CONFIG_DIR", tempfile.mkdtemp(prefix="odc_f28_cfg_"))
    _app = wx.App(False)
    print("Round 28: interrupted work survives\n")
    check("an intermediate stream is not a finished video",
          test_an_intermediate_stream_is_not_a_finished_video)
    check("the merged video is found", test_the_merged_video_is_found)
    check("other containers still count", test_other_containers_still_count)
    check("empty or missing directory is not a video",
          test_an_empty_or_missing_directory_is_not_a_video)
    check("a zero-byte file is not a video", test_a_zero_byte_file_is_not_a_video)
    check("partial bytes counts what can be resumed",
          test_partial_bytes_counts_what_can_be_resumed)
    check("resolve_source takes a download directory",
          test_resolve_source_takes_a_download_directory)
    check("the project is created before downloading",
          test_the_pipeline_creates_the_project_before_downloading)
    check("a project holding a partial is kept",
          test_a_project_holding_a_partial_download_is_kept)
    check("the cache name follows the encode settings",
          test_the_cache_name_follows_the_encode_settings)
    check("a changed source gets a new cache name",
          test_a_changed_source_gets_a_new_cache_name)
    check("a cached copy is not deleted after use",
          test_a_cached_copy_is_not_deleted_after_use)
    check("staging keeps an extension ffmpeg understands",
          test_staging_keeps_an_extension_ffmpeg_understands)
    check("a failed encode never deletes the directory",
          test_a_failed_encode_never_deletes_the_directory)
    check("the cache directory reaches every provider",
          test_the_cache_directory_reaches_every_provider)
    check("compression falls back to a temp dir",
          test_compression_falls_back_to_a_temp_dir)
    check("sibling subtitles matched by exact stem",
          test_sibling_subtitles_are_matched_by_exact_stem)
    check("an existing pair gives the player both halves",
          test_opening_an_existing_pair_gives_the_player_both_halves)
    check("the button sits next to Local Video File",
          test_the_button_sits_next_to_local_video_file_under_tab)
    check("the button is disabled while a job runs",
          test_the_button_is_disabled_while_a_job_runs)
    check("both languages describe the new button",
          test_both_languages_describe_the_new_button)
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
