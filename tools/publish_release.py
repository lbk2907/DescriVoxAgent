"""Publish a VERIFIED release on GitHub, so the in-app updater finds it.

Owner, 6 Oct 2026: "lepas ni awak je yang publish" - the agent publishes,
after ONE yes from the owner for that version (never without it).

    python tools/publish_release.py            # dry run: checks, prints the plan
    python tools/publish_release.py --yes      # publishes (only after the owner's yes)

Refuses unless:
  - tools/release_check.py says VERIFIED for HEAD (contracts/release.json),
  - tag v<version> exists and points at HEAD (tools/tag_release.py made it),
  - dist/ holds the zip, SHA256SUMS.txt and release-notes-<version>.md, and
    the zip matches its checksum line,
  - the GitHub CLI is logged in (the owner logs it in; no token passes here).

Then: push main and the tag, create the Release on lbk2907/DescriVoxAgent
with the zip and SHA256SUMS.txt attached and the notes as its text, and
read releases/latest back the way the app does (core/app_update.py).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Callable

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(REPO / "src"))

from omni_describer_custom.core import app_update  # noqa: E402

Runner = Callable[[list[str]], subprocess.CompletedProcess]


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def files(dist: Path, version: str) -> dict[str, Path]:
    return {"zip": dist / app_update.zip_name(version),
            "sums": dist / app_update.SUMS_NAME,
            "sig": dist / app_update.SIG_NAME,
            "notes": dist / f"release-notes-{version}.md"}


def check_files(dist: Path, version: str) -> list[str]:
    """Problems with the files to upload (empty list = fine)."""
    f = files(dist, version)
    missing = [str(p) for p in f.values() if not p.exists()]
    if missing:
        return [f"missing {m} (run build.bat)" for m in missing]
    try:
        # The app refuses an unsigned or wrongly signed release: so do we.
        app_update.verify_signature(f["sums"].read_bytes(), f["sig"].read_bytes())
        expected = app_update.expected_sha256(
            f["sums"].read_text(encoding="utf-8"), f["zip"].name)
    except app_update.UpdateError as e:
        return [str(e)]
    if app_update.sha256_of(f["zip"]) != expected:
        return [f"{f['zip'].name} does not match {app_update.SUMS_NAME}"]
    if not f["notes"].read_text(encoding="utf-8").strip():
        return [f"{f['notes'].name} is empty"]
    return []


def check_tag(version: str, run: Runner = _run) -> list[str]:
    tag = f"v{version}"
    head = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    tagged = run(["git", "rev-list", "-n", "1", tag]).stdout.strip()
    if not tagged:
        return [f"tag {tag} does not exist (python tools/tag_release.py)"]
    if tagged != head:
        return [f"tag {tag} is not HEAD"]
    return []


def check_gh(run: Runner = _run) -> list[str]:
    try:
        out = run(["gh", "auth", "status"])
    except OSError:
        return ["the GitHub CLI (gh) is not installed"]
    if out.returncode != 0:
        return ["gh is not logged in: the owner runs "
                "gh auth login --hostname github.com --git-protocol https --web"]
    return []


def plan(version: str, dist: Path) -> list[list[str]]:
    f = files(dist, version)
    tag = f"v{version}"
    return [
        ["git", "push", "origin", "main"],
        ["git", "push", "origin", tag],
        ["gh", "release", "create", tag, str(f["zip"]), str(f["sums"]), str(f["sig"]),
         "--repo", app_update.REPO, "--title", f"DescriVox Agent {version}",
         "--notes-file", str(f["notes"]), "--verify-tag", "--latest"],
    ]


def main() -> int:
    import evidence as E
    import release_check
    import contracts as C

    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true",
                    help="publish (only after the owner said yes for this version)")
    ap.add_argument("--dist", default=str(REPO / "dist"))
    args = ap.parse_args()
    version = E.version()
    dist = Path(args.dist)

    verdict = release_check.run()
    problems = [] if verdict.verdict == C.VERIFIED else \
        [f"release_check: {verdict.verdict} (must be VERIFIED)"]
    problems += check_tag(version) + check_files(dist, version) + check_gh()
    print(f"Release v{version}")
    if problems:
        print("NOT PUBLISHED:")
        print("\n".join(f"  - {p}" for p in problems))
        return 1
    steps = plan(version, dist)
    if not args.yes:
        print("DRY RUN - would run:")
        print("\n".join("  " + " ".join(s) for s in steps))
        return 0
    for step in steps:
        out = _run(step)
        print(f"$ {' '.join(step[:4])} ... -> {out.returncode}")
        if out.returncode != 0:
            print(out.stderr.strip()[-800:])
            print("PUBLISH_FAIL")
            return 1
    found = app_update.latest_release()
    if found.version != version:
        print(f"PUBLISH_FAIL: releases/latest says {found.version}, not {version}")
        return 1
    print(f"PUBLISHED v{version}: {found.page_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
