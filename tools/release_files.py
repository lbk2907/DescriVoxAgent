"""The two extra files a GitHub Release needs for the in-app updater.

core/app_update.py (2.1.3) installs a release only when the zip matches
its line in SHA256SUMS.txt, and shows the release text as "What's new".
build.bat runs this after making the zip:

    dist/SHA256SUMS.txt             <sha256>  DescriVox-Agent-<v>-win64.zip
    dist/release-notes-<v>.md       the "What's new in v<v>" of CHANGELOG.md

The owner then publishes a GitHub Release tagged v<v> with the zip and
SHA256SUMS.txt attached and the notes as its text (docs/developer-guide.md,
"Releasing"). Publishing is outward-facing, so no tool here does it.

    python tools/release_files.py [--dist dist] [--version X.Y.Z]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools"))

from omni_describer_custom import __version__  # noqa: E402
from omni_describer_custom.core.app_update import (  # noqa: E402
    SUMS_NAME,
    sha256_of,
    zip_name,
)


def notes_for(changelog: str, version: str) -> str:
    """The body of "## What's new in v<version>", without its heading."""
    m = re.search(
        rf"^## What's new in v{re.escape(version)}\s*\n(.*?)(?=^## |\Z)", changelog, re.M | re.S
    )
    if not m:
        raise SystemExit(f'CHANGELOG.md has no "## What\'s new in v{version}"')
    return m.group(1).strip() + "\n"


def write(dist: Path, version: str, changelog: str) -> tuple[Path, Path]:
    archive = dist / zip_name(version)
    if not archive.exists():
        raise SystemExit(f"{archive} does not exist; build it first")
    sums = dist / SUMS_NAME
    sums.write_text(f"{sha256_of(archive)}  {archive.name}\n", encoding="utf-8", newline="\n")
    # Signed with the owner's release key (tools/release_key.py): the app
    # installs nothing whose SHA256SUMS.txt does not verify.
    import release_key

    release_key.sign(sums)
    notes = dist / f"release-notes-{version}.md"
    notes.write_text(notes_for(changelog, version), encoding="utf-8", newline="\n")
    return sums, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", default=str(REPO / "dist"))
    ap.add_argument("--version", default=__version__)
    args = ap.parse_args()
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    sums, notes = write(Path(args.dist), args.version, changelog)
    print(f"RELEASE_FILES_OK {sums.name} {notes.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
