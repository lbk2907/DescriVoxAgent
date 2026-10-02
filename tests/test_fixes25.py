"""Regression round 25: the app carries its own tools (v1.6.5).

Until now the app assumed ffmpeg, ffprobe, ffplay and yt-dlp were
already installed. On the author's machine they were, so nothing ever
complained. On a machine without them the app failed a phase at a time
with errors that named no cause, and the player ran descriptions over a
silent video — the exact report that started this work.

Three things are pinned here. The binaries ship inside the bundle. Every
place that shells out asks ONE function where they are, so a frozen
build cannot have some call sites finding them and others not. And when
one is genuinely absent the app says which and why, instead of failing
quietly later.

The ffmpeg build is the GPL one because ai_engine encodes with libx264,
which LGPL builds do not carry; that obligation is recorded in
NOTICE.md, and a check here keeps that file honest.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import os
import re
import subprocess
import sys
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

from omni_describer_custom.core import tools  # noqa: E402
from omni_describer_custom.core.tools import (  # noqa: E402
    REQUIRED_TOOLS, find_tool, missing_tools, tool_available)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "omni_describer_custom"

ok_count = 0
fail_count = 0


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


# ── The binaries are here and they work ──────────────────────────

def test_every_required_tool_is_present():
    absent = missing_tools()
    assert not absent, (
        f"missing {[n for n, _ in absent]} — run "
        f"python tools/fetch_binaries.py")


def test_tools_come_from_the_bundle_not_the_system():
    """The point is not "ffmpeg works here", it is "ffmpeg ships"."""
    for name in REQUIRED_TOOLS:
        path = Path(find_tool(name))
        assert path.is_absolute(), f"{name} resolved to a bare name: {path}"
        assert path.parent == ROOT / "bin", (
            f"{name} resolved to {path}, not the repo's bin/ — a machine "
            f"without a system install would not find it")


def test_the_bundled_binaries_actually_run():
    """Present on disk is not the same as executable.

    A shared ffmpeg build is a stub plus DLLs; miss one DLL and the exe
    exists, is found, and dies on launch.
    """
    for name in ("ffmpeg", "ffprobe", "ffplay"):
        out = subprocess.run([find_tool(name), "-hide_banner", "-version"],
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, f"{name} exited {out.returncode}: {out.stderr[:300]}"
        assert "version" in out.stdout.lower(), f"{name} printed no version"
    out = subprocess.run([find_tool("yt-dlp"), "--version"],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, f"yt-dlp exited {out.returncode}"


def test_ffmpeg_has_the_encoder_the_app_uses():
    """ai_engine compresses uploads with libx264.

    This is why the GPL build is shipped; if a future fetch quietly
    switches to LGPL, compression breaks at upload time on a real video
    rather than here.
    """
    out = subprocess.run([find_tool("ffmpeg"), "-hide_banner", "-encoders"],
                         capture_output=True, text=True, timeout=60)
    assert "libx264" in out.stdout, (
        "the bundled ffmpeg has no libx264 — an LGPL build was fetched, "
        "but ai_engine encodes with it")


# ── One place decides, so a frozen build cannot disagree ─────────

def test_no_call_site_looks_for_the_tools_on_its_own():
    """Every shell-out must route through find_tool.

    Before v1.6.5 five separate places each did their own lookup and
    only one of them knew about bin/, which is how the packaged player
    ended up silent while the rest of the app worked.
    """
    offenders = []
    # Any quoted tool name at all, then subtract the harmless uses. A
    # narrower regex aimed at the known-bad shapes let
    # `for player in ("ffplay",)` through when it was tried against the
    # pre-fix source, which is precisely the line that made the packaged
    # player silent.
    named = re.compile(r"""["'](ffmpeg|ffprobe|ffplay|yt-dlp)["']""")
    excused = re.compile(
        r"find_tool|tool_available|REQUIRED_TOOLS"      # the sanctioned route
        r"|logger\.|^\s*#|^\s*[\"']{3}|\.endswith|with_name"   # talking about it
        r"|_backend")  # "ffplay" as a state label, not a program to run
    for path in SRC.rglob("*.py"):
        if path.name == "tools.py":
            continue  # the one place allowed to know
        for num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if named.search(line) and not excused.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{num}: {line.strip()}")
    assert not offenders, "call sites bypassing find_tool:\n" + "\n".join(offenders)


def test_ytdlp_is_told_where_ffmpeg_is():
    """yt-dlp merges video+audio with ffmpeg and finds it ITSELF.

    Bundling ffmpeg does not help a child process that searches PATH.
    Measured: with PATH emptied and yt-dlp.exe moved out of bin/, it
    reported "exe versions: none" and would have failed at the merge;
    with --ffmpeg-location it found the bundled build. Today it also
    works by accident because yt-dlp.exe sits beside ffmpeg.exe, and
    that accident is not something to depend on.
    """
    text = (SRC / "core" / "video_processor.py").read_text(encoding="utf-8")
    assert "--ffmpeg-location" in text, (
        "yt-dlp is never told where ffmpeg is; the merge step would use "
        "PATH only")
    download = text.split("--merge-output-format")[1][:1200]
    assert "--ffmpeg-location" in download, (
        "the flag is not on the call that actually merges")


def test_bundled_copy_wins_over_path():
    """A system ffmpeg must not shadow the one we shipped and tested."""
    path = find_tool("ffmpeg")
    import shutil as _sh
    system = _sh.which("ffmpeg")
    if system and Path(system).parent != ROOT / "bin":
        assert Path(path).parent == ROOT / "bin", (
            f"PATH copy {system} won over the bundled one")


def test_frozen_bundle_directory_is_searched_first():
    """PyInstaller extracts to _MEIPASS; bin/ lands inside it.

    Simulated rather than built: the build takes minutes, and what
    matters is that the lookup consults _MEIPASS at all, which nothing
    else in the gate would catch.
    """
    original = getattr(sys, "_MEIPASS", None)
    sys._MEIPASS = r"C:\fake\_internal"
    try:
        dirs = tools._bundle_dirs()
        assert dirs[0] == Path(r"C:\fake\_internal") / "bin", (
            f"_MEIPASS/bin is not searched first; got {dirs[0]}")
    finally:
        if original is None:
            del sys._MEIPASS
        else:
            sys._MEIPASS = original


def test_a_missing_tool_is_reported_with_a_reason():
    """The user must learn WHICH tool and WHAT it cost them."""
    original = tools._bundle_dirs
    tools._bundle_dirs = lambda: [Path(r"C:\nowhere\at\all")]
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = ""
    try:
        absent = dict(missing_tools())
        assert set(absent) == set(REQUIRED_TOOLS), (
            f"with nothing installed, only {sorted(absent)} were reported")
        for name, why in absent.items():
            assert len(why) > 10, f"{name} has no explanation: {why!r}"
        assert not tool_available("ffmpeg")
    finally:
        tools._bundle_dirs = original
        os.environ["PATH"] = original_path


def test_startup_warns_instead_of_failing_later():
    text = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "missing_tools" in text, "main.py never checks for the tools"
    assert "log_tool_status" in text, "main.py never records where they came from"
    # [-1]: the name appears on the import line too; the call is last.
    assert "MessageBox" in text.split("missing_tools()")[-1][:900], (
        "the missing-tool check does not tell the user anything")


# ── The build actually carries them ──────────────────────────────

def test_build_ships_the_binaries_and_the_notice():
    text = (ROOT / "build.bat").read_text(encoding="utf-8")
    assert '--add-data "bin;bin"' in text, "build.bat does not bundle bin/"
    assert "NOTICE.md" in text, "build.bat does not ship NOTICE.md"
    assert "fetch_binaries.py" in text, (
        "build.bat does not fetch the binaries, so a clean clone would "
        "silently build an app with none")


def test_binaries_are_not_committed_to_git():
    """217 MB does not belong in git; the fetch script replaces them."""
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "bin/*.exe" in ignore and "bin/*.dll" in ignore, (
        "the bundled binaries are not gitignored")


def test_fetch_script_asks_for_every_dll_the_build_needs():
    """A shared build's exe is useless without all of its DLLs.

    Compared against what is actually in bin/ rather than a hardcoded
    list, so bumping ffmpeg's major versions fails here instead of
    producing a build that cannot start.
    """
    script = (ROOT / "tools" / "fetch_binaries.py").read_text(encoding="utf-8")
    on_disk = {p.name for p in (ROOT / "bin").glob("*.dll")}
    missing = [dll for dll in on_disk if dll not in script]
    assert not missing, (
        f"fetch_binaries.py would not download {missing}, so a fresh "
        f"clone's ffmpeg would fail to start")


# ── The licence obligation we took on ────────────────────────────

def test_notice_records_the_gpl_obligation():
    notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
    for needed in ("GPL", "libx264", "github.com/FFmpeg/FFmpeg", "yt-dlp"):
        assert needed in notice, f"NOTICE.md does not mention {needed}"


def test_the_licence_text_and_version_ship_beside_the_binaries():
    licence = ROOT / "bin" / "FFMPEG-LICENSE.txt"
    version = ROOT / "bin" / "FFMPEG-VERSION.txt"
    assert licence.exists(), "the GPL text is not in bin/"
    assert "GENERAL PUBLIC LICENSE" in licence.read_text(
        encoding="utf-8", errors="replace")[:2000]
    assert version.exists(), (
        "bin/FFMPEG-VERSION.txt is missing — GPL distribution has to be "
        "able to say which source the binaries correspond to")
    assert version.read_text(encoding="utf-8").strip(), "version file is empty"


# ── The narration hold only where it can work ────────────────────

def test_hold_is_offered_only_by_engines_that_know_when_speech_ends():
    from omni_describer_custom.core.tts_engine import (
        HOLD_CAPABLE_ENGINES, TTSEngine)
    assert "edge" in HOLD_CAPABLE_ENGINES
    assert "sapi5" in HOLD_CAPABLE_ENGINES
    # Built without engine instances on purpose: this exercises the
    # HOLD_CAPABLE_ENGINES fallback, the answer used when no live
    # engine object is there to ask. v1.6.6 added the instance-first
    # path, which test_fixes26 covers against real backends.
    engine = TTSEngine.__new__(TTSEngine)
    engine._current_engine = "edge"
    engine._engines = {}
    assert engine.supports_narration_hold() is True
    assert engine.supports_narration_hold("sapi5") is True
    # A screen-reader engine returns as soon as text is queued, so the
    # video would resume over its own narration.
    assert engine.supports_narration_hold("screen_reader") is False


def test_player_asks_before_holding_the_video():
    text = (SRC / "ui" / "player_window.py").read_text(encoding="utf-8")
    assert "_hold_supported" in text, "the player never asks the engine"
    narrate = text.split("pause_for_narration = bool(widget.GetValue())")[1][:700]
    assert "_hold_supported" in narrate, (
        "the hold is applied without checking the engine can support it")


def test_the_unavailable_case_is_explained_in_both_languages():
    import json
    for code in ("en", "ms"):
        data = json.loads((SRC / "i18n" / "locales" / f"{code}.json").read_text(
            encoding="utf-8"))
        message = data.get("player.pause_unavailable", "")
        assert message, f"{code}.json has no player.pause_unavailable"
        assert len(message) > 40, (
            f"{code} message is too short to explain why: {message!r}")


if __name__ == "__main__":
    print("Round 25: bundled external tools\n")
    check("every required tool is present", test_every_required_tool_is_present)
    check("tools come from the bundle, not the system",
          test_tools_come_from_the_bundle_not_the_system)
    check("the bundled binaries actually run",
          test_the_bundled_binaries_actually_run)
    check("ffmpeg has the encoder the app uses",
          test_ffmpeg_has_the_encoder_the_app_uses)
    check("no call site does its own lookup",
          test_no_call_site_looks_for_the_tools_on_its_own)
    check("yt-dlp is told where ffmpeg is", test_ytdlp_is_told_where_ffmpeg_is)
    check("bundled copy wins over PATH", test_bundled_copy_wins_over_path)
    check("frozen bundle dir is searched first",
          test_frozen_bundle_directory_is_searched_first)
    check("a missing tool is reported with a reason",
          test_a_missing_tool_is_reported_with_a_reason)
    check("startup warns instead of failing later",
          test_startup_warns_instead_of_failing_later)
    check("build ships the binaries and the notice",
          test_build_ships_the_binaries_and_the_notice)
    check("binaries are not committed to git",
          test_binaries_are_not_committed_to_git)
    check("fetch script asks for every DLL",
          test_fetch_script_asks_for_every_dll_the_build_needs)
    check("NOTICE records the GPL obligation",
          test_notice_records_the_gpl_obligation)
    check("licence and version ship beside the binaries",
          test_the_licence_text_and_version_ship_beside_the_binaries)
    check("hold offered only where speech end is known",
          test_hold_is_offered_only_by_engines_that_know_when_speech_ends)
    check("player asks before holding the video",
          test_player_asks_before_holding_the_video)
    check("unavailable case explained in both languages",
          test_the_unavailable_case_is_explained_in_both_languages)
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
