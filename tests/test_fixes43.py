"""Regression round 43: translations people can actually keep up (v1.8.0).

Asked by the owner: does the app really work in several languages, and
are new strings always added so users can keep their language current?
The check found:

  1. ~15 user-facing texts written straight into the code, in English
     only (start-up warnings, log errors, file-type filters NVDA reads,
     the About box). A Malay user heard English there.
  2. 46 keys no code used any more: 13% of the work of anyone
     translating into a new language, for text never shown.
  3. The locales folder sits inside the app, which every update
     replaces — a language someone added was lost on the next version.
  4. Nothing told a translator which lines a new version had added.

These checks keep all four from coming back.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import ast
import io
import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "omni_describer_custom"
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("ODC_CONFIG_DIR", tempfile.mkdtemp(prefix="odc_t43_cfg_"))
os.environ.setdefault("ODC_PROJECTS_DIR", tempfile.mkdtemp(prefix="odc_t43_prj_"))
os.environ["ODC_LOCALES_DIR"] = tempfile.mkdtemp(prefix="odc_t43_loc_")

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


# Calls whose string arguments are not shown to the user.
_NOT_SHOWN = {
    "t", "getLogger", "debug", "info", "warning", "error", "exception",
    "critical", "startswith", "endswith", "join", "split", "replace",
    "strip", "format", "get", "set", "setdefault", "Path", "open", "run",
    "Popen", "glob", "rglob", "FindWindow", "SendMessageW", "strftime",
    "strptime", "encode", "decode", "isinstance", "hasattr", "getattr",
    "setattr", "Bind", "sub", "search", "match", "compile", "fullmatch",
    "findall", "SetName", "SetCopyright",
}
# Deliberate exceptions, each with its reason.
_ALLOWED = {
    "Say 'OK' in one word",   # the connection test's prompt to the AI
    "Error starting application:\n",   # last resort if i18n itself failed
    "DescriVox Agent",  # the product name (formerly Omni Describer Custom)
}


def _shown_english():
    found = []
    files = list((SRC / "ui").glob("*.py")) + [ROOT / "main.py"]
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name in _NOT_SHOWN:
                continue
            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) \
                    and fn.value.id in ("logger", "logging", "os", "re", "json",
                                        "subprocess"):
                continue
            args = list(node.args) + [k.value for k in node.keywords if k.arg
                                      not in ("name", "style", "encoding",
                                              "errors", "mode", "prefix",
                                              "suffix", "dir")]
            for a in args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    parts = [a.value]
                elif isinstance(a, ast.JoinedStr):
                    parts = [v.value for v in a.values
                             if isinstance(v, ast.Constant)]
                elif isinstance(a, ast.BinOp):
                    parts = [x.value for x in ast.walk(a)
                             if isinstance(x, ast.Constant) and isinstance(x.value, str)]
                else:
                    continue
                for text in parts:
                    if text in _ALLOWED or text.strip() in _ALLOWED:
                        continue
                    if re.search(r"[A-Za-z]{3,} [A-Za-z]{2,}|\b[A-Z]{4,}:", text):
                        found.append(f"{path.name}:{node.lineno}: {text[:60]!r}")
    return found


def test_no_english_written_into_the_ui():
    found = _shown_english()
    assert not found, ("user-facing text outside the language files — add a "
                       "key to en.json and ms.json and use t():\n  "
                       + "\n  ".join(found))


def _locale(code):
    data = json.loads((SRC / "i18n" / "locales" / f"{code}.json")
                      .read_text(encoding="utf-8"))
    data.pop("_meta", None)
    return data


def test_every_key_is_used():
    code = " ".join(p.read_text(encoding="utf-8")
                    for p in list(SRC.rglob("*.py")) + [ROOT / "main.py"])
    dynamic = set(re.findall(r't\(\s*f["\']([a-z_]+\.[a-z0-9_-]*)\{', code))
    unused = [k for k in _locale("en")
              if f'"{k}"' not in code and f"'{k}'" not in code
              and not any(k.startswith(d) for d in dynamic)]
    assert not unused, (f"{len(unused)} keys nothing uses — a translator "
                        f"would translate them for nothing: {unused[:10]}")


def test_english_and_malay_match():
    en, ms = _locale("en"), _locale("ms")
    assert set(en) == set(ms), (sorted(set(en) ^ set(ms)))[:10]
    for k in en:
        want = set(re.findall(r"\{(\w+)\}", en[k]))
        got = set(re.findall(r"\{(\w+)\}", ms[k]))
        assert want == got, f"{k}: placeholders {want} vs {got}"


def test_user_folder_adds_and_corrects_languages():
    from omni_describer_custom.i18n import strings
    folder = Path(os.environ["ODC_LOCALES_DIR"])
    (folder / "id.json").write_text(json.dumps({
        "_meta": {"code": "id", "name": "Bahasa Indonesia"},
        "main.ready": "Siap",
    }), encoding="utf-8")
    (folder / "ms.json").write_text(json.dumps({
        "main.ready": "Sedia sekarang", "main.title": "",
    }), encoding="utf-8")
    (folder / "zz.json").write_text("{ not json", encoding="utf-8")
    (folder / "id.missing.json").write_text("{}", encoding="utf-8")
    tables, metas = strings._load_locales()
    assert tables["id"]["main.ready"] == "Siap"
    assert metas["id"]["name"] == "Bahasa Indonesia"
    assert tables["ms"]["main.ready"] == "Sedia sekarang", "no correction"
    assert tables["ms"]["main.title"], "an empty line blanked the bundled one"
    assert "zz" not in tables, "a broken file was loaded"
    assert "id.missing" not in tables, "a report was loaded as a language"
    assert len(tables["ms"]) > 300, "the user file replaced ms instead of correcting it"
    for f in folder.iterdir():
        f.unlink()


def test_report_lists_what_is_left_to_translate():
    from omni_describer_custom.i18n import strings
    en = strings.EN_STRINGS
    strings.I18n.add_translation("id", {"main.ready": "Siap",
                                        "old.gone_key": "x"})
    try:
        report = strings.missing_report("id")
        assert "main.ready" not in report["missing"]
        assert report["missing"]["menu.file"] == en["menu.file"], \
            "a missing line must carry its English text"
        assert len(report["missing"]) == len(en) - 1
        assert report["obsolete"] == ["old.gone_key"]
        path, count = strings.write_missing_report("id")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert count == len(en) - 1 and data["menu.file"] == en["menu.file"]
        assert "_obsolete_keys_you_can_delete" in data and "_about" in data
        assert path.parent == strings.user_locales_dir()
    finally:
        strings.I18n._translations.pop("id", None)
    assert strings.missing_report("ms")["missing"] == {}, \
        "Malay should be complete"


def test_menu_handler_and_filters():
    import wx
    app = wx.GetApp() or wx.App(False)
    from omni_describer_custom.i18n.strings import I18n, t, user_locales_dir
    from omni_describer_custom.ui.main_frame import MainFrame
    I18n.set_language("ms")
    assert "Semua fail" in t("filter.all_files")
    frame = MainFrame()
    shown = []
    from omni_describer_custom.ui import dialogs
    real = dialogs.ask_yes_no
    dialogs.ask_yes_no = lambda parent, msg, *a, **k: shown.append(msg) or False
    try:
        assert frame.GetMenuBar().FindItemById(frame._id_language_report)
        I18n.set_language("ms")
        frame._on_language_report(None)
        assert shown and "semua baris sudah diterjemah" in shown[-1], shown
        assert not (user_locales_dir() / "ms.missing.json").exists(), \
            "an empty report file was left behind"
        I18n.add_translation("id", {"main.ready": "Siap"})
        I18n.set_language("id")
        frame._on_language_report(None)
        assert (user_locales_dir() / "id.missing.json").exists()
    finally:
        dialogs.ask_yes_no = real
        I18n._translations.pop("id", None)
        I18n.set_language("en")
        for _ in range(20):
            wx.Yield()
        frame.Destroy()
        del app


def test_gate_isolates_the_user_locales():
    gate = (ROOT / "run_gate.bat").read_text()
    assert "set ODC_LOCALES_DIR=" in gate, \
        "the gate would load the owner's own language files"


def main() -> int:
    check("no English written into the UI", test_no_english_written_into_the_ui)
    check("every key is used", test_every_key_is_used)
    check("English and Malay match, placeholders too", test_english_and_malay_match)
    check("the user folder adds and corrects languages",
          test_user_folder_adds_and_corrects_languages)
    check("the report lists what is left to translate",
          test_report_lists_what_is_left_to_translate)
    check("Translation Report menu and translated file filters",
          test_menu_handler_and_filters)
    check("the gate isolates the user locales", test_gate_isolates_the_user_locales)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
