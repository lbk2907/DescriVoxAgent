"""Regression round 73: owner, 6 Oct 2026 - "next time do all of this
automatically".

After 2.1.2 the plan was found not updated (phase 30 still "no release",
phase 31 missing, "next phase" wrong). tools/check_docs.py now fails the
gate and the build whenever the documents fall behind the version or the
checklist.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

if "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
sys.path.insert(0, "tools")

import check_docs  # noqa: E402

results: list[tuple[str, bool]] = []
REPO = Path(__file__).resolve().parent.parent
FILES = ["CHANGELOG.md", "README.md", "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md",
         "SECURITY.md", "CODE_OF_CONDUCT.md", "LICENSE", "NOTICE.md",
         ".github/PULL_REQUEST_TEMPLATE.md"]


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def copy_repo() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="odc_t73_"))
    for rel in FILES:
        src = REPO / rel
        if src.exists():
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, tmp / rel)
    shutil.copytree(REPO / "docs", tmp / "docs")
    return tmp


def test_the_repository_is_up_to_date():
    found = check_docs.problems()
    assert not found, found


def test_the_plan_left_behind_is_caught():
    """The real miss: plan.md as it was in the 2.1.2 release commit."""
    old = subprocess.run(["git", "show", "9afd5ba:docs/plan.md"], cwd=REPO,
                         capture_output=True, text=True, encoding="utf-8")
    if old.returncode != 0:
        print("  (history not available here - simulated instead)")
        text = (REPO / "docs/plan.md").read_text(encoding="utf-8")
        text = text.replace("| 31 | File > New Project | 2.1.2 |", "| 99 | x | — |")
    else:
        text = old.stdout
    tmp = copy_repo()
    (tmp / "docs/plan.md").write_text(text, encoding="utf-8")
    found = check_docs.problems(tmp, "2.1.2")
    joined = "\n".join(found)
    assert "no phase row with release 2.1.2" in joined, found
    assert "phase 31 is missing" in joined, found


def test_readme_changelog_agents_behind_are_caught():
    tmp = copy_repo()
    found = check_docs.problems(tmp, "9.9.9")
    joined = "\n".join(found)
    for words in ("CHANGELOG.md has no", "README.md: the first", "AGENTS.md status",
                  "no phase row with release 9.9.9"):
        assert words in joined, (words, found)


def test_a_broken_link_is_caught():
    tmp = copy_repo()
    guide = tmp / "docs/user-guide.md"
    guide.write_text(guide.read_text(encoding="utf-8") + "\n[gone](nowhere.md)\n",
                     encoding="utf-8")
    assert any("broken link nowhere.md" in f for f in check_docs.problems(tmp)), "not caught"


def test_build_runs_it_first():
    bat = (REPO / "build.bat").read_text(encoding="utf-8")
    assert "tools\\check_docs.py" in bat
    assert bat.index("check_docs.py") < bat.index("PyInstaller --noconfirm")


def main() -> int:
    check("the repository's documents are up to date", test_the_repository_is_up_to_date)
    check("a plan left behind is caught (the 2.1.2 miss)", test_the_plan_left_behind_is_caught)
    check("README, CHANGELOG and AGENTS left behind are caught",
          test_readme_changelog_agents_behind_are_caught)
    check("a broken link is caught", test_a_broken_link_is_caught)
    check("build.bat checks the documents before building", test_build_runs_it_first)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
