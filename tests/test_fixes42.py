"""Regression round 42: the API key box vanished after Show/Hide (v1.7.9).

Reported by the owner: Settings > AI > Gemini, go to the API key box,
press Show (or Hide) — the key box is gone.

The toggle recreated the TextCtrl to flip TE_PASSWORD. The new box
kept its value, which is all the old test (test_fixes2) checked, but:
  - it sat at the panel's top-left corner with a default size, because
    only the dialog was re-laid out, not the notebook page;
  - it was LAST in the Tab order (pitfall 34), so Tab from the Show
    button never reached it again;
  - NVDA names a text box after the static text created just before
    it, which after recreation was no longer its label.

Now the same control is switched natively (EM_SETPASSWORDCHAR). These
checks fail on the old code: position, size, Tab order, same object.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import os
import sys
import tempfile
import traceback

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")
os.environ.setdefault("ODC_CONFIG_DIR", tempfile.mkdtemp(prefix="odc_t42_"))

import wx  # noqa: E402

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


def _dialog():
    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(None, SettingsStore())
    dlg.Show()
    for _ in range(10):
        wx.Yield()
    return dlg


def _press(dlg):
    ev = wx.CommandEvent(wx.EVT_TOGGLEBUTTON.typeId, dlg.show_key_btn.GetId())
    dlg.show_key_btn.SetValue(not dlg.show_key_btn.GetValue())
    dlg._on_toggle_key(ev)
    for _ in range(10):
        wx.Yield()


def _tab_index(ctrl):
    return list(ctrl.GetParent().GetChildren()).index(ctrl)


def test_box_stays_where_it_was():
    dlg = _dialog()
    try:
        before = dlg.api_key_text.GetRect()
        tab_before = _tab_index(dlg.api_key_text)
        original = dlg.api_key_text
        dlg.api_key_text.ChangeValue("MY-SECRET-KEY")
        for step in ("Show", "Hide", "Show"):
            _press(dlg)
            box = dlg.api_key_text
            assert box.GetRect() == before, (
                f"after {step} the box moved from {before} to {box.GetRect()}")
            assert _tab_index(box) == tab_before, (
                f"after {step} the box went from Tab position {tab_before} "
                f"to {_tab_index(box)}")
            assert box.IsShown() and box.GetValue() == "MY-SECRET-KEY"
        if sys.platform == "win32":
            assert dlg.api_key_text is original, \
                "the box was recreated; NVDA loses its label that way"
    finally:
        dlg.Destroy()


def test_box_follows_its_label_and_precedes_show():
    dlg = _dialog()
    try:
        _press(dlg)
        kids = list(dlg.api_key_text.GetParent().GetChildren())
        i = kids.index(dlg.api_key_text)
        assert kids[i - 1] is dlg._api_key_label, \
            "the box no longer follows its label; NVDA reads it unnamed"
        assert kids[i + 1] is dlg.show_key_btn, \
            "Tab from the box no longer reaches the Show button next"
    finally:
        dlg.Destroy()


def test_label_is_not_written_into_the_box():
    """Pitfall 12: SetLabel on a TextCtrl replaces its CONTENTS."""
    src = (os.path.join("src", "omni_describer_custom", "ui",
                        "settings_dialog.py"))
    text = open(src, encoding="utf-8").read()
    assert "api_key_text.SetLabel" not in text
    assert "new_ctrl.SetLabel" not in text


def main() -> int:
    app = wx.App(False)
    check("the key box stays in place through Show/Hide",
          test_box_stays_where_it_was)
    check("the key box follows its label and precedes Show",
          test_box_follows_its_label_and_precedes_show)
    check("no label is written into the key box",
          test_label_is_not_written_into_the_box)
    del app
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
