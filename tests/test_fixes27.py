"""Regression round 27: verifying accessibility by listening (v1.6.6).

Every accessibility check in this repo used to read the source and
conclude. That is exactly how v1.5.4 shipped three controls whose NVDA
name was set with SetLabel(): the code looked correct, the control
quietly lost its state, and a real user met the result — the preset
combo had nothing selected, so Open refused to run, and the prompt box
held its own label, which was sent to the AI as if the user had typed
it (pitfall 12).

tools/nvda_accessibility_check.py tabs through the real window and
asks NVDA what it announced, through the local NVDA HTTP Bridge. That
part needs NVDA running, so it is not in the gate. The judgement it
applies to the answers is a pure function, and that IS checked here —
a detector nobody has seen fail is not a detector.

Heard on 22 Sep 2026 with the fix in place:
    combo:  "... combo box default collapsed"
    prompt: "... edit multi line You are writing audio description ..."
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import sys
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")
sys.path.insert(0, "tools")

ROOT = Path(__file__).resolve().parent.parent

from nvda_accessibility_check import (  # noqa: E402
    _check_pitfall_12, _USELESS_NAMES, report)

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


def _combo(spoken):
    return {"step": 1, "role": "combo box",
            "name": "Prompt preset (pick one):", "spoken": [spoken]}


def _prompt(spoken):
    return {"step": 2, "role": "edit",
            "name": "Prompt to send (from preset, editable):",
            "spoken": [spoken]}


HEALTHY = [
    _combo("Prompt preset (pick one): combo box default collapsed"),
    _prompt("Prompt to send (from preset, editable): edit multi line "
            "You are writing audio description for a blind viewer."),
]


def test_healthy_announcements_raise_nothing():
    """A detector that fires on correct output is worse than none."""
    assert _check_pitfall_12(HEALTHY) == []


def test_a_combo_with_no_selection_is_caught():
    """The exact v1.5.4 symptom: no value between name and 'collapsed'."""
    broken = [_combo("Prompt preset (pick one): combo box collapsed"),
              HEALTHY[1]]
    found = _check_pitfall_12(broken)
    assert len(found) == 1, found
    assert "NO selected value" in found[0]


def test_a_prompt_box_echoing_its_label_is_caught():
    """SetLabel on a TextCtrl replaces the CONTENTS with the label."""
    broken = [HEALTHY[0],
              _prompt("Prompt to send (from preset, editable): edit "
                      "multi line Prompt to send (from preset, editable)")]
    found = _check_pitfall_12(broken)
    assert len(found) == 1, found
    assert "its own label" in found[0]


def test_an_empty_prompt_box_is_caught():
    """No preset text loaded means Open would send nothing."""
    broken = [HEALTHY[0],
              _prompt("Prompt to send (from preset, editable): edit "
                      "multi line")]
    found = _check_pitfall_12(broken)
    assert len(found) == 1, found
    assert "empty" in found[0]


def test_a_control_that_was_never_reached_is_reported():
    """Silence from a missing control must not read as success."""
    found = _check_pitfall_12([HEALTHY[0]])
    assert any("never reached" in f for f in found), found


def test_an_unnamed_control_fails_the_report():
    """A control NVDA cannot name is unusable, however it looks."""
    seen = [{"step": 1, "role": "button", "name": "",
             "spoken": ["button"]}]
    assert report(seen) == 1, "an unnamed button passed the report"


def test_a_silent_control_fails_the_report():
    seen = [{"step": 1, "role": "button", "name": "Open", "spoken": []}]
    assert report(seen) == 1, "a control NVDA never announced passed"


def test_a_good_walk_passes_the_report():
    """A pass needs the two pitfall-12 controls to have been reached.

    Found while writing this: report() refuses a walk that never met
    the preset combo and the prompt box, even if every control it DID
    meet was fine. That is the intended strictness — a partial walk
    cannot certify the app — so the realistic walk is the one to
    assert on.
    """
    seen = [{"step": 1, "role": "button", "name": "Open",
             "spoken": ["Open button"]}] + HEALTHY
    assert report(seen) == 0


def test_a_partial_walk_cannot_certify():
    """Reaching only some controls must not read as verified."""
    seen = [{"step": 1, "role": "button", "name": "Open",
             "spoken": ["Open button"]}]
    assert report(seen) == 1, (
        "a walk that never reached the preset combo or the prompt box "
        "reported success")


def test_useless_names_include_the_bare_roles():
    for bare in ("", "pane", "panel", "window"):
        assert bare in _USELESS_NAMES


def test_the_tool_refuses_to_pass_without_nvda():
    """Exiting 0 with no bridge would certify an unverified app."""
    text = (ROOT / "tools" / "nvda_accessibility_check.py").read_text(
        encoding="utf-8")
    assert "return 2" in text, "no distinct exit code for 'not verified'"
    assert "Refusing to report a pass" in text, (
        "the tool does not say that a missing bridge means unverified")


if __name__ == "__main__":
    print("Round 27: accessibility verified by listening\n")
    check("healthy announcements raise nothing",
          test_healthy_announcements_raise_nothing)
    check("a combo with no selection is caught",
          test_a_combo_with_no_selection_is_caught)
    check("a prompt box echoing its label is caught",
          test_a_prompt_box_echoing_its_label_is_caught)
    check("an empty prompt box is caught", test_an_empty_prompt_box_is_caught)
    check("a control never reached is reported",
          test_a_control_that_was_never_reached_is_reported)
    check("an unnamed control fails the report",
          test_an_unnamed_control_fails_the_report)
    check("a silent control fails the report",
          test_a_silent_control_fails_the_report)
    check("a good walk passes the report", test_a_good_walk_passes_the_report)
    check("a partial walk cannot certify", test_a_partial_walk_cannot_certify)
    check("useless names include bare roles",
          test_useless_names_include_the_bare_roles)
    check("the tool refuses to pass without NVDA",
          test_the_tool_refuses_to_pass_without_nvda)
    print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)
