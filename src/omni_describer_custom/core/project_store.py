"""
Omni Describer Custom — Project Store (SQLite).

Stores video descriptions, metadata, and project state.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    Each project = one .db file in the projects/ directory.
    """

    def __init__(self, projects_dir: str = ""):
        self.projects_dir = Path(projects_dir) if projects_dir else self._default_dir()
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self._current: Project | None = None

    @staticmethod
    def _default_dir() -> Path:
        base = Path.home() / "Documents" / "OmniDescriber" / "projects"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _db_path(self, project_id: int) -> Path:
        return self.projects_dir / f"project_{project_id}.db"

    def create_project(self, name: str, video_path: str, provider: str = "", model: str = "") -> Project:
        """Create a new project with a unique auto-incremented ID."""
        now = time.strftime("%Y-%m-%d %H:%M:%S")

        # Determine next ID from existing project files
        existing = self.projects_dir.glob("project_*.db")
        max_id = 0
        for p in existing:
            try:
                max_id = max(max_id, int(p.stem.split("_")[1]))
            except (ValueError, IndexError):
                pass
        next_id = max_id + 1

        project = Project(
            id=next_id,
            name=name,
            video_path=video_path,
            provider=provider,
            model=model,
            created_at=now,
            updated_at=now,
        )

        db_path = self._db_path(next_id)
        conn = sqlite3.connect(str(db_path))
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
        cursor = conn.execute(
            "INSERT INTO projects (id, name, video_path, provider, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (next_id, name, video_path, provider, model, now, now),
        )
        conn.commit()
        conn.close()

        self._current = project
        logger.info("Project created: id=%d name=%s", project.id, name)
        return project

    def open_project(self, project_id: int) -> Project | None:
        """Open an existing project by ID."""
        db_path = self._db_path(project_id)
        if not db_path.exists():
            logger.error("Project not found: %d", project_id)
            return None

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            conn.close()
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

        # Load descriptions
        desc_rows = conn.execute(
            "SELECT * FROM descriptions WHERE project_id = ? ORDER BY start_time",
            (project_id,),
        ).fetchall()
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

        conn.close()
        logger.info("Project opened: id=%d name=%s (%d descriptions)", project.id, project.name, len(project.descriptions))
        return project

    def set_video_duration(self, duration: float) -> None:
        """Persist video duration for the current project (player timeline)."""
        if not self._current:
            return
        self._current.video_duration = duration
        try:
            conn = sqlite3.connect(str(self._db_path(self._current.id)))
            conn.execute(
                "UPDATE projects SET video_duration = ?, updated_at = ? WHERE id = ?",
                (duration, time.strftime("%Y-%m-%d %H:%M:%S"), self._current.id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Failed to persist video duration: %s", e)

    def media_dir(self, project_id: int) -> Path:
        """Permanent media folder for a project (video, subtitles)."""
        d = self.projects_dir / f"project_{project_id}" / "media"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def set_video_path(self, video_path: str) -> None:
        """Update the stored video path for the current project (DB + memory)."""
        if not self._current:
            return
        self._current.video_path = video_path
        try:
            conn = sqlite3.connect(str(self._db_path(self._current.id)))
            conn.execute(
                "UPDATE projects SET video_path = ?, updated_at = ? WHERE id = ?",
                (video_path, time.strftime("%Y-%m-%d %H:%M:%S"), self._current.id),
            )
            conn.commit()
            conn.close()
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

        conn = sqlite3.connect(str(self._db_path(self._current.id)))
        conn.execute("DELETE FROM descriptions WHERE project_id = ?", (self._current.id,))
        for desc in descriptions:
            conn.execute(
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
        conn.commit()
        conn.close()

        self._current.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self._current.descriptions = descriptions
        logger.info("Saved %d descriptions", len(descriptions))

    def add_description(self, desc: Description) -> Description:
        """Add a single description to current project."""
        if not self._current:
            logger.error("No project open")
            return desc

        conn = sqlite3.connect(str(self._db_path(self._current.id)))
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
        conn.close()
        self._current.descriptions.append(desc)
        return desc

    def delete_description(self, desc_id: int) -> bool:
        """Delete a description by ID."""
        if not self._current:
            return False
        conn = sqlite3.connect(str(self._db_path(self._current.id)))
        conn.execute("DELETE FROM descriptions WHERE id = ?", (desc_id,))
        conn.commit()
        conn.close()
        self._current.descriptions = [d for d in self._current.descriptions if d.id != desc_id]
        return True

    def list_projects(self) -> list[dict]:
        """List all projects."""
        projects = []
        for db_path in sorted(self.projects_dir.glob("project_*.db")):
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT id, name, video_path, provider, updated_at FROM projects ORDER BY updated_at DESC").fetchone()
                if row:
                    projects.append(dict(row))
                conn.close()
            except Exception as e:
                logger.warning("Error reading project %s: %s", db_path, e)
        return projects

    def delete_project(self, project_id: int) -> bool:
        """Delete a project entirely."""
        db_path = self._db_path(project_id)
        if db_path.exists():
            db_path.unlink()
            if self._current and self._current.id == project_id:
                self._current = None
            logger.info("Project deleted: %d", project_id)
            return True
        return False

    @property
    def current(self) -> Project | None:
        return self._current
