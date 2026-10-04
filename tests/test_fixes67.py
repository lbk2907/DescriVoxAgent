"""Regression round 67: _speak_queued must never interrupt.

PlayerWindow._speak_queued(msg) promises to say msg AFTER what the
screen reader is saying now. When Prism speech failed (speak returned
False or raised) it fell back to _announce, which either spoke with
interrupt=True (_say_in_video_area) or moved the focus to the status
line - both cut the current speech off. It also ran after the window
was gone. Now the fallback only sets the status label (no focus move,
no interrupting speech) and a closed window is left alone.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import sys
import traceback

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

from omni_describer_custom.core import speech as speech_mod  # noqa: E402
from omni_describer_custom.ui.player_window import PlayerWindow  # noqa: E402

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


class FakeSpeech:
    """Records every speak call; answers with `result` or raises."""

    def __init__(self, result=True, raises=False):
        self.result = result
        self.raises = raises
        self.calls: list[tuple[str, bool]] = []
        self.available = True
        self.is_screen_reader = True

    def speak(self, text, interrupt=False):
        self.calls.append((text, interrupt))
        if self.raises:
            raise RuntimeError("prism broke")
        return self.result


class FakeLabel:
    def __init__(self, log):
        self.log = log
        self.label = ""

    def SetLabel(self, text):
        self.label = text

    def SetFocus(self):
        self.log.append("status.SetFocus")


class FakePanel:
    def __init__(self, log):
        self.log = log

    def SetFocus(self):
        self.log.append("video.SetFocus")


class FakeWindow:
    """Just enough of PlayerWindow to run the real methods on."""

    _speak_queued = PlayerWindow._speak_queued
    _announce = PlayerWindow._announce
    _say_in_video_area = PlayerWindow._say_in_video_area

    def __init__(self, alive=True, video_focus=False):
        self.alive = alive
        self.video_focus = video_focus
        self.log: list[str] = []
        self.status_text = FakeLabel(self.log)
        self.video_panel = FakePanel(self.log)

    def __bool__(self):
        return self.alive

    def _video_has_focus(self):
        return self.video_focus


def _run(fake_speech, **win_kw):
    """Call _speak_queued with get_speech() patched to fake_speech."""
    old = speech_mod.get_speech
    speech_mod.get_speech = lambda: fake_speech
    try:
        win = FakeWindow(**win_kw)
        win._speak_queued("Hello")
        return win
    finally:
        speech_mod.get_speech = old


def _assert_quiet_fallback(sp, win):
    assert not any(i for _, i in sp.calls), f"interrupting speech: {sp.calls}"
    assert not win.log, f"focus moved: {win.log}"
    assert win.status_text.label == "Hello", repr(win.status_text.label)


def test_speech_ok_no_fallback():
    for video_focus in (False, True):
        sp = FakeSpeech(result=True)
        win = _run(sp, video_focus=video_focus)
        assert sp.calls == [("Hello", False)], sp.calls
        assert not win.log, win.log


def test_speech_false_never_interrupts():
    for video_focus in (False, True):
        sp = FakeSpeech(result=False)
        _assert_quiet_fallback(sp, _run(sp, video_focus=video_focus))


def test_speech_raises_never_interrupts():
    for video_focus in (False, True):
        sp = FakeSpeech(raises=True)
        _assert_quiet_fallback(sp, _run(sp, video_focus=video_focus))


def test_window_gone_does_nothing():
    sp = FakeSpeech(result=True)
    win = _run(sp, alive=False)
    assert sp.calls == [], sp.calls
    assert not win.log and win.status_text.label == "", (win.log, win.status_text.label)


def main() -> int:
    check("speech OK: queued, no fallback", test_speech_ok_no_fallback)
    check("speech returns False: label only, no focus, no interrupt",
          test_speech_false_never_interrupts)
    check("speech raises: label only, no focus, no interrupt",
          test_speech_raises_never_interrupts)
    check("window gone: nothing happens", test_window_gone_does_nothing)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
