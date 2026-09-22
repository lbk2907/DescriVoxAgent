"""Regression round 26: speaking through the user's own reader (v1.6.6).

The complaint that started this: give the app to someone whose
computer has no NVDA and they cannot use it. Two separate gaps hid
behind that sentence.

The narration voice was always one of ours — Edge, SAPI5, OpenAI —
never the reader the user already knows. And the status announcements
work by moving keyboard focus, which a screen reader reads aloud and a
computer without one passes over in silence, so the app says nothing
at all to someone who has no reader installed.

Prism closes both. It reaches NVDA, JAWS, ZDSR and the rest, and falls
back to SAPI or OneCore when no reader is running.

The capability difference is the load-bearing part. Measured here:

    NVDA      speak yes, is_speaking NO,  rate no,  voice no
    SAPI      speak yes, is_speaking yes, rate yes, voice yes

A screen reader returns the moment text is queued. It will not say
when it finished. So the player's narration hold cannot use it, the
voice and speed settings cannot drive it, and announcements must not
be duplicated through it. Each of those is checked below, and the
no-screen-reader half is forced with ODC_PRISM_BACKEND because this
machine runs NVDA and would otherwise only ever test one branch.
"""
import io
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "omni_describer_custom"
PY = sys.executable

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


def _in_subprocess(code: str, backend: str = "") -> dict:
    """Run a probe in a fresh interpreter.

    PrismSpeech is a process-wide singleton that binds a backend on
    first use, so switching backends means a new process — not a
    monkeypatch that would prove nothing about the real binding.
    """
    env = dict(os.environ)
    if backend:
        env["ODC_PRISM_BACKEND"] = backend
    else:
        env.pop("ODC_PRISM_BACKEND", None)
    out = subprocess.run(
        [PY, "-c", "import sys; sys.path.insert(0, 'src')\n" + code],
        capture_output=True, text=True, timeout=180, env=env, cwd=str(ROOT))
    if out.returncode != 0:
        raise AssertionError(f"probe failed: {out.stderr[-800:]}")
    line = [ln for ln in out.stdout.splitlines() if ln.startswith("{")]
    if not line:
        raise AssertionError(f"probe printed no result: {out.stdout[-500:]}")
    return json.loads(line[-1])


# ── Prism is wired in at all ─────────────────────────────────────

def test_prism_is_importable_and_binds_a_backend():
    from omni_describer_custom.core.speech import get_speech
    speech = get_speech()
    assert speech.available, (
        f"no Prism backend bound: {speech.unavailable_reason}")
    assert speech.backend_name, "backend bound but has no name"


def test_screen_reader_is_offered_as_a_narration_engine():
    from omni_describer_custom.core.tts_engine import TTSEngine
    engine = TTSEngine({})
    assert "screen_reader" in engine.get_available_engines(), (
        "the user's own screen reader is not offered as a voice")


def test_it_is_not_chosen_for_anyone_automatically():
    """Defaulting to it would override a narration voice already set."""
    from omni_describer_custom.core.tts_engine import TTSEngine
    engine = TTSEngine({})
    assert engine._current_engine != "screen_reader", (
        "the screen reader was selected without the user asking")


# ── The capability difference, which everything else rests on ────

def test_a_screen_reader_cannot_drive_the_narration_hold():
    """NVDA reports supports_is_speaking False — so no hold."""
    result = _in_subprocess("""
import json
from omni_describer_custom.core.speech import get_speech
s = get_speech()
print(json.dumps({"backend": s.backend_name,
                  "reader": s.is_screen_reader,
                  "can_report": s.can_report_speaking}))
""", backend="NVDA")
    assert result["reader"] is True, f"NVDA not seen as a reader: {result}"
    assert result["can_report"] is False, (
        "NVDA claims it can report speaking state; if that is ever true "
        "the hold logic needs revisiting, not this test relaxing")


def test_a_synthesiser_can_drive_it():
    """The same engine on SAPI does support the hold.

    Proves the decision is read from the live backend rather than
    hardcoded against the engine's name.
    """
    result = _in_subprocess("""
import json
from omni_describer_custom.core.tts_engine import TTSEngine
e = TTSEngine({})
print(json.dumps({"hold": e.supports_narration_hold("screen_reader")}))
""", backend="SAPI")
    assert result["hold"] is True, (
        "Prism on SAPI can report speaking state but the hold was still "
        "refused — the capability is being ignored")


def test_the_hold_is_refused_on_a_screen_reader():
    result = _in_subprocess("""
import json
from omni_describer_custom.core.tts_engine import TTSEngine
e = TTSEngine({})
print(json.dumps({"hold": e.supports_narration_hold("screen_reader")}))
""", backend="NVDA")
    assert result["hold"] is False, (
        "the player would hold the video for a voice that never reports "
        "finishing, so playback would resume over its own narration")


def test_waiting_actually_waits_where_waiting_is_possible():
    """speak_and_wait must block on SAPI, not just claim success.

    Measured at 3.8s for an eight-word sentence when written; the
    threshold is deliberately far below that so a faster voice does
    not fail the gate.
    """
    result = _in_subprocess("""
import json, time
from omni_describer_custom.core.speech import get_speech
s = get_speech()
t0 = time.monotonic()
ok = s.speak_and_wait("satu dua tiga empat lima enam tujuh lapan")
print(json.dumps({"ok": ok, "elapsed": time.monotonic() - t0}))
""", backend="SAPI")
    assert result["ok"] is True, "SAPI speech failed outright"
    assert result["elapsed"] > 0.8, (
        f"speak_and_wait returned after {result['elapsed']:.2f}s — it did "
        f"not wait for the sentence")


# ── Announcements: silent where a reader already speaks ──────────

def test_announcements_stay_quiet_when_a_reader_is_running():
    """Otherwise every status message is said twice."""
    result = _in_subprocess("""
import json
from omni_describer_custom.core.speech import announce, get_speech
s = get_speech()
print(json.dumps({"reader": s.is_screen_reader, "spoke": announce("x")}))
""", backend="NVDA")
    assert result["reader"] is True
    assert result["spoke"] is False, (
        "the app spoke a status message that NVDA was already reading "
        "from the focus change")


def test_announcements_speak_when_nothing_else_will():
    """The whole point: a computer with no screen reader."""
    result = _in_subprocess("""
import json
from omni_describer_custom.core.speech import announce, get_speech
s = get_speech()
print(json.dumps({"reader": s.is_screen_reader, "spoke": announce("x")}))
""", backend="SAPI")
    assert result["reader"] is False
    assert result["spoke"] is True, (
        "with no screen reader running the app stayed silent, which is "
        "the original complaint")


def test_every_status_surface_uses_the_fallback():
    """All four windows, not just the one that got tested by hand."""
    missing = []
    for name in ("player_window", "editor_window", "scene_explorer",
                 "ask_more_dialog"):
        text = (SRC / "ui" / f"{name}.py").read_text(encoding="utf-8")
        after = text.split("def _announce")[1][:900] if "def _announce" in text else ""
        if "speech import announce" not in after:
            missing.append(name)
    assert not missing, (
        f"these windows still announce by focus alone: {missing}")


def test_an_announcement_never_breaks_the_action():
    """A speech failure must not take the button press down with it."""
    text = (SRC / "ui" / "player_window.py").read_text(encoding="utf-8")
    after = text.split("def _announce")[1][:900]
    assert "except Exception" in after, (
        "_announce calls into Prism without catching failure")


# ── Settings that would silently do nothing ──────────────────────

def test_voice_and_speed_are_disabled_for_the_screen_reader():
    text = (SRC / "ui" / "settings_dialog.py").read_text(encoding="utf-8")
    assert "_sync_voice_controls" in text, (
        "nothing disables voice/speed for an engine that ignores them")
    body = text.split("def _sync_voice_controls")[1][:800]
    assert "voice_choice" in body and "speed_slider" in body, (
        "the disable does not cover both controls")
    assert "Enable(" in body, "the controls are never actually disabled"
    # Applied on load as well as on change, or reopening the dialog
    # shows live controls for an engine that ignores them.
    assert text.count("_sync_voice_controls(") >= 3, (
        "_sync_voice_controls is not called on both load and change")


def test_the_screen_reader_offers_no_voice_list():
    """Claiming voices we cannot set would be a lie in the UI."""
    from omni_describer_custom.core.tts_engine import PrismEngine
    assert PrismEngine().get_voices() == []


def test_labels_exist_in_both_languages():
    for code in ("en", "ms"):
        data = json.loads((SRC / "i18n" / "locales" / f"{code}.json").read_text(
            encoding="utf-8"))
        for key in ("settings.engine_screen_reader",
                    "settings.engine_screen_reader_named",
                    "settings.engine_owns_voice"):
            assert data.get(key), f"{code}.json has no {key}"
        assert "{backend}" in data["settings.engine_screen_reader_named"], (
            f"{code}: the named label cannot show which reader was found")


# ── Packaging ────────────────────────────────────────────────────

def test_the_build_ships_prism():
    """Check the BUILD, not the build flags.

    The first version of this test read build.bat for "--collect-all
    prism" and passed — while the shipped app logged "No module named
    'prism._prism_cffi'" and had no screen-reader voice at all.
    prism/_native.py appends its directory to __path__ at runtime, so
    PyInstaller never saw the extension and dropped it; hooks/hook-prism.py
    puts it back. A flag is an intention, not a result.
    """
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "prismatoid" in pyproject, "prismatoid is not a declared dependency"
    hook = ROOT / "hooks" / "hook-prism.py"
    assert hook.exists(), (
        "no PyInstaller hook for prism, so the native extension would be "
        "dropped from the build again")
    assert "--additional-hooks-dir hooks" in (
        ROOT / "build.bat").read_text(encoding="utf-8"), (
        "the hooks directory is not passed to PyInstaller")

    internal = ROOT / "dist" / "OmniDescriber" / "_internal"
    if not internal.is_dir():
        print("       (no build present — skipping the on-disk check)")
        return
    found = list(internal.rglob("_prism_cffi*.pyd"))
    assert found, (
        "the build has no _prism_cffi extension anywhere: prism will "
        "import and die, exactly as it did in v1.6.6")
    native = internal / "prism" / "_native"
    assert (native / "prism.dll").exists(), (
        "prism.dll is missing; the extension loads it by directory")


def test_a_missing_prism_does_not_stop_the_app():
    """Someone running from source without it must still get a window."""
    text = (SRC / "core" / "speech.py").read_text(encoding="utf-8")
    head = text.split("def _acquire")[1][:600]
    assert "except Exception" in head, (
        "a failed prism import would propagate out of startup")
    from omni_describer_custom.core.tts_engine import PrismEngine
    engine = PrismEngine()
    assert isinstance(engine.available, bool)


if __name__ == "__main__":
    print("Round 26: speaking through the user's own screen reader\n")
    check("prism binds a backend", test_prism_is_importable_and_binds_a_backend)
    check("screen reader offered as a voice",
          test_screen_reader_is_offered_as_a_narration_engine)
    check("not chosen automatically", test_it_is_not_chosen_for_anyone_automatically)
    check("a screen reader cannot drive the hold",
          test_a_screen_reader_cannot_drive_the_narration_hold)
    check("a synthesiser can drive it", test_a_synthesiser_can_drive_it)
    check("hold refused on a screen reader",
          test_the_hold_is_refused_on_a_screen_reader)
    check("waiting actually waits", test_waiting_actually_waits_where_waiting_is_possible)
    check("quiet when a reader is running",
          test_announcements_stay_quiet_when_a_reader_is_running)
    check("speaks when nothing else will",
          test_announcements_speak_when_nothing_else_will)
    check("every status surface uses the fallback",
          test_every_status_surface_uses_the_fallback)
    check("an announcement never breaks the action",
          test_an_announcement_never_breaks_the_action)
    check("voice and speed disabled for the reader",
          test_voice_and_speed_are_disabled_for_the_screen_reader)
    check("screen reader offers no voice list",
          test_the_screen_reader_offers_no_voice_list)
    check("labels exist in both languages", test_labels_exist_in_both_languages)
    check("the build ships prism", test_the_build_ships_prism)
    check("a missing prism does not stop the app",
          test_a_missing_prism_does_not_stop_the_app)
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
