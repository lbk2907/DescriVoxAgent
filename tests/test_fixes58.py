"""Regression round 58: guards for two kinds of bug found on 2 Oct 2026.

1. Tests wrote the owner's REAL settings. Thirteen test scripts relied
   on run_gate.bat to set ODC_CONFIG_DIR; run on their own they wrote a
   loopback Gemini URL into settings.json and every Gemini job failed
   with "Cannot connect to host 127.0.0.1:12144". Every test now imports
   tests/isolate.py before anything else; this checks that it stays so.
2. File > Open Project crashed EVERY time since v1.7.6:
   `wx.EVT_DOUBLECLICK` does not exist (it is EVT_LISTBOX_DCLICK). The
   handler test replaced the dialog, so the line never ran. This checks
   every `wx.<Name>` in the source against the real wxPython.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import ast
import io
import re
import sys
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)

ROOT = Path(__file__).resolve().parent.parent
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


def test_every_test_isolates_first():
    bad = []
    for p in sorted((ROOT / "tests").glob("*.py")):
        if p.name in ("isolate.py", "test_build_smoke.py"):
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))
                   and getattr(n, "module", None) != "__future__"]
        if not imports or not (isinstance(imports[0], ast.Import)
                               and imports[0].names[0].name == "isolate"):
            bad.append(p.name)
    assert not bad, f"these tests can touch the owner's real data: {bad}"


def test_isolate_sets_every_variable():
    import os
    for name in ("ODC_CONFIG_DIR", "ODC_PROJECTS_DIR", "ODC_LOCALES_DIR",
                 "ODC_TOOLS_DIR"):
        assert os.environ.get(name), name
    sys.path.insert(0, str(ROOT / "src"))
    from omni_describer_custom.core.settings_store import _get_config_dir
    assert Path(os.environ["ODC_CONFIG_DIR"]) == Path(_get_config_dir())


def test_every_wx_name_exists():
    import importlib
    import wx
    for sub in ("adv", "html", "lib", "media", "richtext", "grid", "dataview"):
        try:
            importlib.import_module(f"wx.{sub}")
        except Exception:
            pass
    missing = set()
    for p in (ROOT / "src").rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        for m in re.finditer(r"\bwx\.([A-Za-z_]\w*)(?:\.([A-Za-z_]\w*))?", text):
            first, second = m.group(1), m.group(2)
            obj = getattr(wx, first, None)
            if obj is None:
                missing.add(f"{p.name}: wx.{first}")
            elif second and isinstance(obj, type(wx)) and not hasattr(obj, second):
                missing.add(f"{p.name}: wx.{first}.{second}")
    assert not missing, f"not in wxPython: {sorted(missing)}"


def main() -> int:
    check("every test isolates the owner's data first",
          test_every_test_isolates_first)
    check("isolate sets config, projects, locales and tools",
          test_isolate_sets_every_variable)
    check("every wx.<Name> in the source exists", test_every_wx_name_exists)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
