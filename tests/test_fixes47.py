"""Regression round 47: YouTube's passing 403 is retried (v1.8.3).

Setting up the long-video test (29 Sep 2026), yt-dlp stopped with
"HTTP Error 403: Forbidden"; the same command a second later downloaded
all 888 seconds. The app tried once and showed the raw English error.

  1. download_video now retries a 403 (only a 403) up to three times,
     resuming the partial file in the project's media folder;
  2. if the site keeps refusing, the user hears what to do, in the app's
     language, instead of "ERROR: unable to download video data".
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
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
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from omni_describer_custom.core import video_processor as vpm  # noqa: E402

results: list[tuple[str, bool]] = []


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


# A stand-in for yt-dlp: fails with the given stderr for the first
# `failures` calls, then writes the merged video.mp4 like the real one.
_FAKE = r'''
import sys
from pathlib import Path
out = Path(sys.argv[1]).parent
count = out / "calls.txt"
n = int(count.read_text()) + 1 if count.exists() else 1
count.write_text(str(n))
if n <= int(sys.argv[2]):
    sys.stderr.write(sys.argv[3] + "\n")
    sys.exit(1)
(out / "video.mp4").write_bytes(b"merged")
'''


def _download(failures: int, error: str):
    out_dir = tempfile.mkdtemp(prefix="odc_t47_")
    real_exec = asyncio.create_subprocess_exec

    async def fake_exec(*args, **kwargs):
        tmpl = args[args.index("-o") + 1]
        return await real_exec(sys.executable, "-c", _FAKE, tmpl,
                               str(failures), error, **kwargs)

    real_sleep = asyncio.sleep
    vpm.asyncio.create_subprocess_exec = fake_exec
    vpm.asyncio.sleep = lambda s, *a, **k: real_sleep(0)
    try:
        vp = vpm.VideoProcessor(ffmpeg_path="ffmpeg", ytdlp_path="yt-dlp")
        try:
            path = asyncio.run(vp.download_video("https://example.com/v", out_dir))
            error_text = ""
        except vpm.SourceError as e:
            path, error_text = "", str(e)
    finally:
        vpm.asyncio.create_subprocess_exec = real_exec
        vpm.asyncio.sleep = real_sleep
    calls = int((Path(out_dir) / "calls.txt").read_text())
    return path, error_text, calls


FORBIDDEN = "ERROR: unable to download video data: HTTP Error 403: Forbidden"


def test_a_passing_403_is_retried():
    path, error, calls = _download(1, FORBIDDEN)
    assert path.endswith("video.mp4") and not error, error
    assert calls == 2, f"{calls} calls"


def test_a_lasting_403_gives_up_and_is_named():
    path, error, calls = _download(99, FORBIDDEN)
    assert not path and calls == vpm.DOWNLOAD_ATTEMPTS == 3, calls
    assert vpm.is_forbidden_error(error), error


def test_other_errors_are_not_retried():
    path, error, calls = _download(99, "ERROR: [youtube] abc: Private video")
    assert not path and calls == 1, f"a private video was tried {calls} times"
    assert not vpm.is_forbidden_error(error)


def test_downloads_prefer_h264():
    """v1.8.5: yt-dlp's own ranking chose AV1 + Opus for Big Buck Bunny,
    and two of seven models could not open it. The fake yt-dlp records
    the arguments it was given."""
    seen = {}
    real_exec = asyncio.create_subprocess_exec

    async def spy(*args, **kwargs):
        seen["args"] = list(args)
        tmpl = args[args.index("-o") + 1]
        return await real_exec(sys.executable, "-c", _FAKE, tmpl, "0", "",
                               **kwargs)
    vpm.asyncio.create_subprocess_exec = spy
    try:
        vp = vpm.VideoProcessor(ffmpeg_path="ffmpeg", ytdlp_path="yt-dlp")
        asyncio.run(vp.download_video("https://example.com/v",
                                      tempfile.mkdtemp(prefix="odc_t47_")))
    finally:
        vpm.asyncio.create_subprocess_exec = real_exec
    args = seen["args"]
    assert "-S" in args, args
    order = args[args.index("-S") + 1]
    assert order.startswith("vcodec:h264"), order
    assert args.index("-S") < args.index("--"), "the sort must come before the URL"


def test_the_user_hears_what_to_do():
    from omni_describer_custom.i18n.strings import I18n, t
    source = (ROOT / "src" / "omni_describer_custom" / "ui" /
              "main_frame.py").read_text(encoding="utf-8")
    assert 'is_forbidden_error(str(e))' in source and \
        't("error.download_forbidden")' in source, \
        "the processing error handler does not translate a 403"
    I18n.set_language("ms")
    try:
        said = t("error.download_forbidden")
        assert "403" in said and "Semak Kemas Kini" in said, said
    finally:
        I18n.set_language("en")


def main() -> int:
    check("a passing 403 is retried", test_a_passing_403_is_retried)
    check("a lasting 403 gives up after 3 and is named",
          test_a_lasting_403_gives_up_and_is_named)
    check("other download errors are not retried",
          test_other_errors_are_not_retried)
    check("downloads prefer H.264 every model can open",
          test_downloads_prefer_h264)
    check("the user hears what to do, in the app language",
          test_the_user_hears_what_to_do)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
