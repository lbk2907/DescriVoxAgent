"""Regression round 41: loose ends from the v1.7.7 review.

  1. The E2E tools save into the owner's REAL projects folder (they need
     the real keys). Every run left its project behind — 17 "Me at the
     zoo" and 4 "sintel" had piled up. tools/e2e_projects.ProjectsGuard
     removes only the projects a run created, never one that was there.
  2. The same tools looked for "*.db" in the projects folder, which
     finds nothing since v1.7.6 moved each .db into "<name> (id)/".
  3. Preset names: only "en_"/"ms_" counted as language prefixes, so a
     third locale's presets ("id_default") showed in the English list.

(The long-video checks in test_fixes16 now make their own 10-minute
video instead of borrowing the owner's project; that is tested there.)
"""

import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import os
import sqlite3
import sys
import tempfile
import traceback
from contextlib import closing
from pathlib import Path

if "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
if "pytest" not in sys.modules:
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("ODC_CONFIG_DIR", tempfile.mkdtemp(prefix="odc_t41_cfg_"))

from omni_describer_custom.core.project_store import ProjectStore  # noqa: E402

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


def test_guard_removes_only_what_a_run_created():
    from e2e_projects import ProjectsGuard

    d = Path(tempfile.mkdtemp(prefix="odc_t41_"))
    owner = ProjectStore(str(d)).create_project("Owner's own video", "x")
    guard = ProjectsGuard(d)
    run = ProjectStore(str(d)).create_project("Me at the zoo", "y")
    assert guard.cleanup() == [run.id]
    left = [p["id"] for p in ProjectStore(str(d)).list_projects()]
    assert left == [owner.id], f"the owner's project was touched: {left}"


def test_guard_can_be_told_to_keep():
    from e2e_projects import ProjectsGuard

    d = Path(tempfile.mkdtemp(prefix="odc_t41_"))
    guard = ProjectsGuard(d)
    ProjectStore(str(d)).create_project("Inspect me", "y")
    os.environ["ODC_E2E_KEEP"] = "1"
    try:
        assert guard.cleanup() == []
    finally:
        os.environ.pop("ODC_E2E_KEEP", None)
    assert len(ProjectStore(str(d)).list_projects()) == 1


def test_tools_find_the_newest_project_in_both_layouts():
    from e2e_projects import media_dir_of, newest_db

    d = Path(tempfile.mkdtemp(prefix="odc_t41_"))
    legacy = d / "project_3.db"
    with closing(sqlite3.connect(str(legacy))) as conn:
        conn.execute("CREATE TABLE t (x)")
        conn.commit()
    os.utime(legacy, (1, 1))  # older than what follows
    p = ProjectStore(str(d)).create_project("Sintel", "z")
    newest = newest_db(d)
    assert newest == d / f"Sintel ({p.id})" / "project.db", newest
    assert media_dir_of(newest) == d / f"Sintel ({p.id})" / "media"
    assert media_dir_of(legacy) == d / "project_3" / "media"
    for tool in ("e2e_gui_phase.py", "e2e_gui_v130.py", "e2e_full_verify.py"):
        text = (ROOT / "tools" / tool).read_text(encoding="utf-8")
        assert 'glob("*.db")' not in text, f"{tool} still uses the old layout"


def test_third_language_presets_stay_in_their_language():
    from omni_describer_custom.core.prompt_manager import PromptManager
    from omni_describer_custom.i18n.strings import I18n

    class Store:
        def __init__(self):
            self.prompts = {
                "default": "EN",
                "ms_default": "MS",
                "id_default": "ID",
                "text_ocr": "universal",
            }

        def get_prompts(self):
            return dict(self.prompts)

        def set_prompt(self, name, text):
            self.prompts[name] = text

        def delete_prompt(self, name):
            return self.prompts.pop(name, None) is not None

    I18n.add_translation("id", {"_probe": "x"})
    try:
        pm = PromptManager(Store())
        pm.language = "en"
        en = pm.get_presets()
        assert "id_default" not in en, f"Indonesian preset in English list: {en}"
        assert en.get("default") == "EN" and "text_ocr" in en
        pm.language = "id"
        idl = pm.get_presets()
        assert idl.get("default") == "ID", idl
        assert "ms_default" not in idl
    finally:
        I18n._translations.pop("id", None)


def main() -> int:
    check(
        "the E2E guard removes only what a run created", test_guard_removes_only_what_a_run_created
    )
    check("ODC_E2E_KEEP keeps a run's project", test_guard_can_be_told_to_keep)
    check(
        "the E2E tools find the newest project in both layouts",
        test_tools_find_the_newest_project_in_both_layouts,
    )
    check(
        "a third language's presets stay in their language",
        test_third_language_presets_stay_in_their_language,
    )
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
