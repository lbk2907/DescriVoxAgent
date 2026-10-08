"""Shared by the real-GUI E2E tools: find their project, then remove it.

The E2E tools drive the real app, which saves into the owner's real
projects folder (they need the real settings and keys, so they are not
isolated like the gate). Until v1.7.7 every run left its project
behind: 17 "Me at the zoo" and 4 "sintel" projects had piled up in the
owner's Open Project list. Now a run removes ONLY the projects it
created itself — the ids that were not there when it started — so the
owner's own projects are never touched.

Set ODC_E2E_KEEP=1 to keep a run's project for inspection.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from omni_describer_custom.core.project_store import ProjectStore  # noqa: E402

REAL_PROJECTS = Path.home() / "Documents" / "OmniDescriber" / "projects"


def all_dbs(projects_dir: Path = REAL_PROJECTS) -> list[Path]:
    """Every project database in either layout, oldest first.

    v1.7.6 moved them from "project_48.db" into "<name> (48)/project.db";
    a bare glob("*.db") finds nothing in the new layout.
    """
    found = list(projects_dir.glob("project_*.db")) + list(projects_dir.glob("*/project.db"))
    return sorted(found, key=lambda p: p.stat().st_mtime)


def newest_db(projects_dir: Path = REAL_PROJECTS) -> Path | None:
    dbs = all_dbs(projects_dir)
    return dbs[-1] if dbs else None


def media_dir_of(db: Path) -> Path:
    """The media folder that belongs to a project database."""
    if db.name == "project.db":
        return db.parent / "media"
    return db.with_suffix("") / "media"


class ProjectsGuard:
    """Remember which projects existed; remove the ones a run added."""

    def __init__(self, projects_dir: Path = REAL_PROJECTS):
        self.store = ProjectStore(str(projects_dir))
        self.before = {p["id"] for p in self.store.list_projects()}

    def cleanup(self) -> list[int]:
        if os.environ.get("ODC_E2E_KEEP", "").strip() == "1":
            print("ODC_E2E_KEEP=1: leaving this run's project in place")
            return []
        removed = []
        for row in self.store.list_projects():
            if row["id"] not in self.before:
                if self.store.delete_project(row["id"]):
                    removed.append(row["id"])
                else:
                    print(
                        f"could not remove test project {row['id']} "
                        f"({row['name']}) — a file in it is still open"
                    )
        if removed:
            print(f"removed this run's test project(s): {removed}")
        return removed
