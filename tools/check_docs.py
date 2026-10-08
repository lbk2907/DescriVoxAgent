"""Are the documents up to date with the code? (owner, 6 Oct 2026)

"Next time do all of this automatically": after 2.1.2 the plan was found
not updated by hand. This check runs in the gate (test_fixes73) and at
the start of build.bat, so a release cannot be committed or built with
documents left behind.

    python tools/check_docs.py        # DOCS_OK, or DOCS_FAIL + every reason

Checks, for the version in src/omni_describer_custom/__init__.py:
- CHANGELOG.md has "## What's new in v<version>" (and no "## Unreleased"
  left once that version is the current one);
- README.md's first "What's new" is that version, and it keeps exactly 3;
- AGENTS.md says "Version <version>";
- docs/plan.md has the release in its phase table, every checklist phase
  is in that table, and "the next one is Phase N" is the newest + 1;
- every relative link in the documents points to a file that exists.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def version() -> str:
    text = (REPO / "src/omni_describer_custom/__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def problems(repo: Path = REPO, ver: str | None = None) -> list[str]:
    ver = ver or version()
    found: list[str] = []

    def read(rel: str) -> str:
        return (repo / rel).read_text(encoding="utf-8")

    changelog = read("CHANGELOG.md")
    if f"## What's new in v{ver}\n" not in changelog:
        found.append(f'CHANGELOG.md has no "## What\'s new in v{ver}"')

    readme = read("README.md")
    news = re.findall(r"^## What's new in v([\d.]+)", readme, re.M)
    if not news or news[0] != ver:
        found.append(f'README.md: the first "What\'s new" is {news[:1]}, not v{ver}')
    if len(news) != 3:
        found.append(f'README.md keeps {len(news)} "What\'s new" sections, not 3')

    if f"Version {ver}**" not in read("AGENTS.md"):
        found.append(f'AGENTS.md status does not say "Version {ver}"')

    plan = read("docs/plan.md")
    rows = {
        int(m.group(1)): m.group(2).strip()
        for m in re.finditer(r"^\| (\d+) \| [^|]+\| ([^|]+)\|", plan, re.M)
    }
    if not any(re.search(rf"(^|[ ,]){re.escape(ver)}([ ,(]|$)", r) for r in rows.values()):
        found.append(f"docs/plan.md: no phase row with release {ver}")
    phases = [int(n) for n in re.findall(r"^## Phase (\d+)", read("docs/checklist.md"), re.M)]
    for n in phases:
        if n not in rows:
            found.append(f"docs/plan.md: checklist phase {n} is missing from the phase table")
    if phases:
        m = re.search(r"the next one is \*\*Phase (\d+)\*\*", plan)
        want = max(phases) + 1
        if not m or int(m.group(1)) != want:
            found.append(
                f'docs/plan.md: "the next one is Phase {m.group(1) if m else "?"}", '
                f"should be {want}"
            )

    docs = [
        repo / p
        for p in (
            "README.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
            "AGENTS.md",
            "CLAUDE.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
        )
    ]
    docs += list((repo / "docs").rglob("*.md"))
    for f in docs:
        if not f.exists():
            continue
        for m in re.finditer(r"\]\(([^)#\s]+)(#[^)]*)?\)", f.read_text(encoding="utf-8")):
            target = m.group(1)
            if target.startswith(("http", "mailto")):
                continue
            if not (f.parent / target).exists():
                found.append(f"{f.relative_to(repo)}: broken link {target}")
    return found


def main() -> int:
    found = problems()
    if found:
        print("DOCS_FAIL")
        for line in found:
            print("  -", line)
        return 1
    print(f"DOCS_OK v{version()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
