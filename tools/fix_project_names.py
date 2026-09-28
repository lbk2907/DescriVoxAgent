"""Give projects that are named after a URL their real video title.

Projects made before v1.5.1 were named with the raw link
("https://www.youtube.com/watch?v=..."), which reads as noise in the
Open Project list and in File Explorer. This asks yt-dlp for each
link's title once and renames the project (name and folder) with it.

    python tools/fix_project_names.py            # the real projects
    python tools/fix_project_names.py --dry-run  # show, change nothing

Needs the network for yt-dlp. A link that no longer resolves is left
as it is and reported.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from omni_describer_custom.core.project_store import ProjectStore  # noqa: E402
from omni_describer_custom.core.tools import find_tool  # noqa: E402


def fetch_title(url: str) -> str:
    out = subprocess.run(
        [find_tool("yt-dlp"), "--no-playlist", "--skip-download",
         "--print", "title", "--", url],
        capture_output=True, text=True, encoding="utf-8", timeout=120)
    lines = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    return lines[-1] if out.returncode == 0 and lines else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--projects", default="",
                        help="projects folder (default: the real one)")
    args = parser.parse_args()

    store = ProjectStore(args.projects)
    store.migrate_layout()
    titles: dict[str, str] = {}
    failed = 0
    for row in store.list_projects():
        name = (row.get("name") or "").strip()
        if not name.startswith(("http://", "https://")):
            continue
        if name not in titles:
            titles[name] = fetch_title(name)
        title = titles[name]
        if not title:
            print(f"  ({row['id']}) no title found for {name}")
            failed += 1
            continue
        print(f"  ({row['id']}) {name}  ->  {title}")
        if not args.dry_run:
            store.rename_project(row["id"], title)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
