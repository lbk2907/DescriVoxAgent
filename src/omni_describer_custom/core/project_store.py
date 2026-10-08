"""
Omni Describer Custom — Project Store (SQLite).

Stores video descriptions, metadata, and project state.
"""

from __future__ import annotations

import logging
import sqlite3
import shutil
import time
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Description:
    """A single audio description entry."""

    id: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    text: str = ""
    edited: bool = False
    created_at: str = ""
    frame_path: str = ""


@dataclass
class Project:
    """Project metadata."""

    id: int = 0
    name: str = ""
    video_path: str = ""
    video_duration: float = 0.0
    provider: str = ""
    model: str = ""
    created_at: str = ""
    updated_at: str = ""
    descriptions: list[Description] = field(default_factory=list)


class ProjectStore:
    """
    SQLite-backed project storage.

    v1.7.6 layout -- one readable folder per project:

        projects/
          Sintel (48)/
            project.db
            media/      video, subtitles, upload cache
            frames/

    The owner browses this in File Explorer, where the old layout showed
    only "project_48" and "project_48.db". The id stays in the folder
    name: two videos may share a title, and every lookup is by id.
    Projects in the old layout are moved on start (migrate_layout).
    """

    def __init__(self, projects_dir: str = ""):
        self.projects_dir = Path(projects_dir) if projects_dir else self._default_dir()
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self._current: Project | None = None

    @staticmethod
    def _default_dir() -> Path:
        # ODC_PROJECTS_DIR isolates tests, as ODC_CONFIG_DIR does for
        # settings (pitfall 19). Without it every gate run created and
        # deleted projects in the user's real Documents folder — 14 test
        # projects ("V1", "hold_test", ...) were found there in v1.7.5.
        import os

        override = os.environ.get("ODC_PROJECTS_DIR", "").strip()
        base = (
            Path(override) if override else Path.home() / "Documents" / "OmniDescriber" / "projects"
        )
        base.mkdir(parents=True, exist_ok=True)
        return base

    DB_NAME = "project.db"

    @staticmethod
    def folder_label(name: str, project_id: int) -> str:
        """Folder name for a project: "<name> (<id>)", Windows-safe.

        The " (id)" suffix also defuses reserved device names: "CON" is
        refused by Windows, "CON (5)" is not.
        """
        import re
        import unicodedata

        clean = "".join(ch for ch in (name or "") if unicodedata.category(ch) not in ("Cc", "Cf"))
        clean = re.sub(r'[<>:"/\\|?*]+', " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip(" .")
        if len(clean) > 60:
            clean = clean[:60].rstrip(" .")
        return f"{clean or 'Video'} ({project_id})"

    def _legacy_db(self, project_id: int) -> Path:
        return self.projects_dir / f"project_{project_id}.db"

    def project_dir(self, project_id: int) -> Path:
        """The folder that holds this project, in either layout.

        For an id not on disk in the new layout this is where the OLD
        layout keeps it; create_project makes the named folder itself.
        """
        suffix = f" ({project_id})"
        if self.projects_dir.exists():
            for d in self.projects_dir.iterdir():
                if d.is_dir() and d.name.endswith(suffix) and (d / self.DB_NAME).exists():
                    return d
        return self.projects_dir / f"project_{project_id}"

    def _db_path(self, project_id: int) -> Path:
        folder_db = self.project_dir(project_id) / self.DB_NAME
        if folder_db.exists():
            return folder_db
        return self._legacy_db(project_id)

    def _connect(self, db_path) -> "closing[sqlite3.Connection]":
        """A connection that is CLOSED when the with-block ends, error
        or not. A connection left open on an error path keeps the .db
        locked on Windows (WinError 32), so the project could not be
        deleted while the app ran."""
        return closing(sqlite3.connect(str(db_path)))

    # Highest id ever handed out. Ids are never reused: a new project
    # that inherited a deleted one's id also inherited whatever was
    # left in project_<id>/media, and a finished video.mp4 there was
    # taken as ITS download -- the wrong video got described.
    _LAST_ID_FILE = "last_project_id.txt"
    _ID_SUFFIX = __import__("re").compile(r" \((\d+)\)$")

    def _next_project_id(self) -> int:
        highest = 0
        for d in self.projects_dir.iterdir():
            m = self._ID_SUFFIX.search(d.name)
            if d.is_dir() and m and (d / self.DB_NAME).exists():
                highest = max(highest, int(m.group(1)))
        for p in self.projects_dir.glob("project_*"):
            tail = p.name.split(".", 1)[0].split("_", 1)[-1]
            if not tail.isdigit():
                continue
            # A folder counts only when something is in it: an orphan
            # left by an older version may still hold a video, while an
            # empty media/ folder carries nothing a new project could
            # mistake for its own.
            if p.is_dir() and not any(f.is_file() for f in p.rglob("*")):
                continue
            highest = max(highest, int(tail))
        marker = self.projects_dir / self._LAST_ID_FILE
        try:
            highest = max(highest, int(marker.read_text(encoding="utf-8").strip()))
        except (OSError, ValueError):
            pass
        next_id = highest + 1
        try:
            marker.write_text(str(next_id), encoding="utf-8")
        except OSError as e:
            logger.warning("Could not record last project id: %s", e)
        return next_id

    def create_project(
        self, name: str, video_path: str, provider: str = "", model: str = ""
    ) -> Project:
        """Create a new project with a unique auto-incremented ID."""
        now = time.strftime("%Y-%m-%d %H:%M:%S")

        next_id = self._next_project_id()

        project = Project(
            id=next_id,
            name=name,
            video_path=video_path,
            provider=provider,
            model=model,
            created_at=now,
            updated_at=now,
        )

        folder = self.projects_dir / self.folder_label(name, next_id)
        folder.mkdir(parents=True, exist_ok=True)
        db_path = folder / self.DB_NAME
        with self._connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    video_path TEXT,
                    video_duration REAL DEFAULT 0,
                    provider TEXT DEFAULT '',
                    model TEXT DEFAULT '',
                    created_at TEXT,
                    updated_at TEXT,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS descriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL NOT NULL,
                    text TEXT NOT NULL,
                    edited INTEGER DEFAULT 0,
                    created_at TEXT,
                    frame_path TEXT DEFAULT '',
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                )
            """)
            conn.execute(
                "INSERT INTO projects (id, name, video_path, provider, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (next_id, name, video_path, provider, model, now, now),
            )
            conn.commit()

        self._current = project
        logger.info("Project created: id=%d name=%s", project.id, name)
        return project

    def open_project(self, project_id: int) -> Project | None:
        """Open an existing project by ID."""
        db_path = self._db_path(project_id)
        if not db_path.exists():
            logger.error("Project not found: %d", project_id)
            return None

        with self._connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            desc_rows = (
                conn.execute(
                    "SELECT * FROM descriptions WHERE project_id = ? ORDER BY start_time",
                    (project_id,),
                ).fetchall()
                if row
                else []
            )
        if not row:
            return None

        project = Project(
            id=row["id"],
            name=row["name"],
            video_path=row["video_path"],
            video_duration=row["video_duration"],
            provider=row["provider"],
            model=row["model"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        project._db_path = str(db_path)
        self._current = project

        project.descriptions = [
            Description(
                id=r["id"],
                start_time=r["start_time"],
                end_time=r["end_time"],
                text=r["text"],
                edited=bool(r["edited"]),
                created_at=r["created_at"],
                frame_path=r["frame_path"],
            )
            for r in desc_rows
        ]

        logger.info(
            "Project opened: id=%d name=%s (%d descriptions)",
            project.id,
            project.name,
            len(project.descriptions),
        )
        return project

    def set_video_duration(self, duration: float) -> None:
        """Persist video duration for the current project (player timeline)."""
        if not self._current:
            return
        self._current.video_duration = duration
        try:
            with self._connect(self._db_path(self._current.id)) as conn:
                conn.execute(
                    "UPDATE projects SET video_duration = ?, updated_at = ? WHERE id = ?",
                    (duration, time.strftime("%Y-%m-%d %H:%M:%S"), self._current.id),
                )
                conn.commit()
        except Exception as e:
            logger.error("Failed to persist video duration: %s", e)

    def media_dir(self, project_id: int) -> Path:
        """Permanent media folder for a project (video, subtitles)."""
        d = self.project_dir(project_id) / "media"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def set_video_path(self, video_path: str) -> None:
        """Update the stored video path for the current project (DB + memory)."""
        if not self._current:
            return
        self._current.video_path = video_path
        try:
            with self._connect(self._db_path(self._current.id)) as conn:
                conn.execute(
                    "UPDATE projects SET video_path = ?, updated_at = ? WHERE id = ?",
                    (video_path, time.strftime("%Y-%m-%d %H:%M:%S"), self._current.id),
                )
                conn.commit()
        except Exception as e:
            logger.error("Failed to persist video path: %s", e)

    def persist_video_file(self, source_path: str) -> str:
        """Copy a temp/remote video file into the project's media folder so
        playback survives temp-dir cleanup (mirrors the frames copy fix).

        Returns the permanent path, or the original path on any failure
        (never raises: playback must not break the save pipeline).
        """
        if not self._current:
            return source_path
        src = Path(source_path)
        if not src.exists() or not src.is_file():
            return source_path
        try:
            dest = self.media_dir(self._current.id) / src.name
            if not dest.exists() or dest.stat().st_size != src.stat().st_size:
                shutil.copy2(src, dest)
            self.set_video_path(str(dest))
            logger.info("Video persisted into project: %s", dest)
            return str(dest)
        except Exception as e:
            logger.error("Video persist failed (%s): %s", source_path, e)
            return source_path

    def save_descriptions(self, descriptions: list[Description]) -> None:
        """Save/update descriptions for current project."""
        if not self._current:
            logger.error("No project open")
            return

        with self._connect(self._db_path(self._current.id)) as conn:
            conn.execute("DELETE FROM descriptions WHERE project_id = ?", (self._current.id,))
            for desc in descriptions:
                cursor = conn.execute(
                    """INSERT INTO descriptions
                       (project_id, start_time, end_time, text, edited, created_at, frame_path)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        self._current.id,
                        desc.start_time,
                        desc.end_time,
                        desc.text,
                        int(desc.edited),
                        desc.created_at or time.strftime("%Y-%m-%d %H:%M:%S"),
                        desc.frame_path,
                    ),
                )
                # Write the real DB id back into the in-memory object.
                # v1.5.4 fix: without this every desc kept id=0 after a fresh
                # pipeline run, so the player narrated only the first cue and
                # a single editor delete wiped all cues from the project.
                desc.id = cursor.lastrowid
            conn.commit()

        self._current.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self._current.descriptions = descriptions
        logger.info("Saved %d descriptions", len(descriptions))

    def add_description(self, desc: Description) -> Description:
        """Add a single description to current project."""
        if not self._current:
            logger.error("No project open")
            return desc

        with self._connect(self._db_path(self._current.id)) as conn:
            cursor = conn.execute(
                """INSERT INTO descriptions
                   (project_id, start_time, end_time, text, edited, created_at, frame_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    self._current.id,
                    desc.start_time,
                    desc.end_time,
                    desc.text,
                    int(desc.edited),
                    desc.created_at or time.strftime("%Y-%m-%d %H:%M:%S"),
                    desc.frame_path,
                ),
            )
            desc.id = cursor.lastrowid
            conn.commit()
        self._current.descriptions.append(desc)
        return desc

    def delete_description(self, desc_id: int) -> bool:
        """Delete a description by ID."""
        if not self._current:
            return False
        with self._connect(self._db_path(self._current.id)) as conn:
            conn.execute("DELETE FROM descriptions WHERE id = ?", (desc_id,))
            conn.commit()
        self._current.descriptions = [d for d in self._current.descriptions if d.id != desc_id]
        return True

    def find_project_by_source(self, source: str) -> dict | None:
        """v1.5.1: find an existing project created from this source.

        Matches when the stored video_path (the original source saved at
        creation time) equals the given source string. Used so pasting
        the SAME YouTube link again offers to open the existing project
        instead of downloading and describing it a second time.
        Returns the list_projects() row (id, name, video_path, ...) or None.
        """
        if not source:
            return None
        for row in self.list_projects():
            if (row.get("video_path") or "") == source:
                return row
            # Also match by the persisted media video file name for
            # projects whose source was a URL (video saved as video.mp4).
        return None

    def _all_db_paths(self) -> list[Path]:
        paths = [
            d / self.DB_NAME
            for d in self.projects_dir.iterdir()
            if d.is_dir() and self._ID_SUFFIX.search(d.name) and (d / self.DB_NAME).exists()
        ]
        paths += sorted(self.projects_dir.glob("project_*.db"))
        return paths

    def list_projects(self) -> list[dict]:
        """All projects, most recently updated first.

        Each row also carries `count` (descriptions) and `created_at`, so
        the Open Project list can say more than a bare name.
        """
        projects = []
        for db_path in self._all_db_paths():
            try:
                with self._connect(db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute(
                        "SELECT id, name, video_path, provider, created_at, "
                        "updated_at FROM projects "
                        "ORDER BY updated_at DESC"
                    ).fetchone()
                    count = conn.execute("SELECT COUNT(*) FROM descriptions").fetchone()[0]
                if row:
                    item = dict(row)
                    item["count"] = count
                    projects.append(item)
            except Exception as e:
                logger.warning("Error reading project %s: %s", db_path, e)
        projects.sort(key=lambda p: p.get("updated_at") or "", reverse=True)
        return projects

    # -- Readable folders (v1.7.6) --------------------------------

    def _move_folder(self, project_id: int, old: Path, new: Path) -> bool:
        """Rename a project folder and rewrite the paths stored inside.

        The DB keeps ABSOLUTE paths to the video and to each frame; a
        renamed folder without this rewrite leaves the player unable to
        find the video. Returns False (nothing changed) if Windows
        refuses the rename -- a file inside is open, e.g. in the player.
        """
        if old == new:
            return True
        if new.exists():
            logger.warning("Cannot rename %s: %s already exists", old, new)
            return False
        try:
            old.rename(new)
        except OSError as e:
            logger.warning("Project folder %s kept its name (%s)", old, e)
            return False
        db = new / self.DB_NAME
        if db.exists():
            self._rewrite_paths(db, str(old), str(new))
        if self._current and self._current.id == project_id:
            self._current.video_path = self._swap_prefix(
                self._current.video_path, str(old), str(new)
            )
            for desc in self._current.descriptions:
                desc.frame_path = self._swap_prefix(desc.frame_path, str(old), str(new))
        logger.info("Project folder renamed: %s -> %s", old.name, new.name)
        return True

    @staticmethod
    def _swap_prefix(path: str, old: str, new: str) -> str:
        if path and path.lower().startswith(old.lower()):
            return new + path[len(old) :]
        return path

    def _rewrite_paths(self, db_path: Path, old: str, new: str) -> None:
        with self._connect(db_path) as conn:
            for pid, video in conn.execute("SELECT id, video_path FROM projects").fetchall():
                fixed = self._swap_prefix(video or "", old, new)
                if fixed != (video or ""):
                    conn.execute("UPDATE projects SET video_path = ? WHERE id = ?", (fixed, pid))
            for did, frame in conn.execute("SELECT id, frame_path FROM descriptions").fetchall():
                fixed = self._swap_prefix(frame or "", old, new)
                if fixed != (frame or ""):
                    conn.execute(
                        "UPDATE descriptions SET frame_path = ? WHERE id = ?", (fixed, did)
                    )
            conn.commit()

    def migrate_layout(self) -> int:
        """Move old-layout projects into readable folders, and bring any
        folder whose name no longer matches its project up to date (a
        rename made while the video was open). Returns how many moved.

        Never raises: a project that cannot move now keeps its old place
        and is tried again on the next start.
        """
        moved = 0
        for legacy in sorted(self.projects_dir.glob("project_*.db")):
            tail = legacy.stem.split("_", 1)[-1]
            if not tail.isdigit():
                continue
            pid = int(tail)
            try:
                with self._connect(legacy) as conn:
                    row = conn.execute("SELECT name FROM projects WHERE id = ?", (pid,)).fetchone()
                target = self.projects_dir / self.folder_label(row[0] if row else "", pid)
                old_folder = self.projects_dir / f"project_{pid}"
                if old_folder.is_dir():
                    if not self._move_folder(pid, old_folder, target):
                        continue
                else:
                    target.mkdir(parents=True, exist_ok=True)
                legacy.rename(target / self.DB_NAME)
                self._rewrite_paths(target / self.DB_NAME, str(old_folder), str(target))
                moved += 1
            except Exception as e:
                logger.warning("Could not migrate project %s: %s", legacy, e)
        for db_path in self._all_db_paths():
            folder = db_path.parent
            m = self._ID_SUFFIX.search(folder.name)
            if folder == self.projects_dir or not m:
                continue
            try:
                with self._connect(db_path) as conn:
                    row = conn.execute("SELECT name FROM projects").fetchone()
                want = self.projects_dir / self.folder_label(row[0] if row else "", int(m.group(1)))
                if want != folder and self._move_folder(int(m.group(1)), folder, want):
                    moved += 1
            except Exception as e:
                logger.warning("Could not tidy project %s: %s", folder, e)
        if moved:
            logger.info("Project layout: %d project(s) moved", moved)
        return moved

    def rename_project(self, project_id: int, new_name: str) -> bool:
        """Rename a project: its stored name AND its folder.

        The name always changes. The folder follows when Windows allows
        it; if a file inside is open it follows on the next start.
        """
        new_name = (new_name or "").strip()
        db_path = self._db_path(project_id)
        if not new_name or not db_path.exists():
            return False
        # updated_at is left alone: it orders the Open Project list by
        # when the WORK changed, and a rename (or the bulk fix of old
        # URL names) must not reshuffle that list.
        with self._connect(db_path) as conn:
            conn.execute("UPDATE projects SET name = ? WHERE id = ?", (new_name, project_id))
            conn.commit()
        if self._current and self._current.id == project_id:
            self._current.name = new_name
        folder = db_path.parent
        if folder != self.projects_dir:
            self._move_folder(
                project_id, folder, self.projects_dir / self.folder_label(new_name, project_id)
            )
        logger.info("Project %d renamed to %s", project_id, new_name)
        return True

    def delete_project(self, project_id: int) -> bool:
        """Delete a project entirely: its .db AND its project_<id>/ folder.

        The folder holds the downloaded video. Leaving it behind let a
        later project that got the same id pick up that video as its
        own finished download. The id is also never handed out again
        (see _next_project_id). The folder goes first: if a file in it
        is locked (the player has the video open) the .db is kept, so
        nothing is left half-deleted and invisible.
        """
        db_path = self._db_path(project_id)
        folder = self.project_dir(project_id)
        if not db_path.exists() and not folder.exists():
            return False
        if folder.exists():
            try:
                shutil.rmtree(folder)
            except OSError as e:
                logger.error("Could not delete project folder %s: %s", folder, e)
                return False
        if db_path.exists():
            db_path.unlink()
        if self._current and self._current.id == project_id:
            self._current = None
        logger.info("Project deleted: %d", project_id)
        return True

    @property
    def current(self) -> Project | None:
        return self._current
