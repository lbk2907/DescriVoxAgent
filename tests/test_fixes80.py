"""Regression round 80: durable source lookup and failed secret protection."""

import isolate  # noqa: F401 (first: never use the owner's data)
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
if "pytest" not in sys.modules:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

from omni_describer_custom.core.project_store import ProjectStore  # noqa: E402
from omni_describer_custom.core import settings_store as settings  # noqa: E402


class SourcePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="odc_t80_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = ProjectStore(str(self.root))
        self.source = "https://example.invalid/original-video"

    def legacy_project(self, source):
        project = self.store.create_project("Legacy", source)
        with closing(sqlite3.connect(self.store._db_path(project.id))) as conn:
            if "source_path" in {r[1] for r in conn.execute("PRAGMA table_info(projects)")}:
                conn.execute("ALTER TABLE projects DROP COLUMN source_path")
                conn.commit()
        return project

    def test_original_url_survives_download_and_fresh_store(self):
        project = self.store.create_project("Video", self.source)
        video = self.root / "download.mp4"
        video.write_bytes(b"synthetic video fixture")
        stored_path = self.store.persist_video_file(str(video))
        reopened = ProjectStore(str(self.root))
        match = reopened.find_project_by_source(self.source)
        self.assertIsNotNone(match)
        self.assertEqual(match["id"], project.id)
        self.assertEqual(reopened.open_project(project.id).video_path, stored_path)
        self.assertEqual(reopened.current.source_path, self.source)
        self.assertEqual(reopened.find_project_by_source(stored_path)["id"], project.id)

    def test_legacy_url_is_migrated_before_playback_path_changes(self):
        project = self.legacy_project(self.source)
        reopened = ProjectStore(str(self.root))
        reopened.open_project(project.id)
        reopened.set_video_path(str(self.root / "media" / "video.mp4"))
        again = ProjectStore(str(self.root))
        self.assertIsNotNone(again.find_project_by_source(self.source))
        self.assertEqual(again.open_project(project.id).source_path, self.source)

    def test_legacy_path_set_without_reopen_preserves_source(self):
        self.legacy_project(self.source)
        self.store.set_video_path(str(self.root / "media" / "video.mp4"))
        self.assertIsNotNone(ProjectStore(str(self.root)).find_project_by_source(self.source))

    def test_legacy_local_path_does_not_invent_missing_url(self):
        local = str(self.root / "media" / "video.mp4")
        project = self.legacy_project(local)
        reopened = ProjectStore(str(self.root))
        self.assertIsNone(reopened.find_project_by_source(self.source))
        self.assertEqual(reopened.find_project_by_source(local)["id"], project.id)
        self.assertEqual(reopened.open_project(project.id).source_path, local)


class SecretSaveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="odc_t80_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "settings.json"
        self.path.write_text(
            json.dumps({"ai": {"providers": {"glm": {"api_key_enc": "fake-protected"}}}}),
            encoding="utf-8",
        )
        with patch.object(settings, "_unprotect_secret_strict", return_value="fake-secret"):
            self.store = settings.SettingsStore(str(self.root))

    def test_protection_failure_preserves_entire_last_good_file(self):
        before = self.path.read_bytes()
        with patch.object(
            settings, "_protect_secret_strict", side_effect=settings.SecretProtectError("fixture")
        ):
            self.store.set("general.language", "ms")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.store._shared.last_bytes, before)

    def test_successful_key_change_and_clear_still_persist(self):
        with patch.object(settings, "_protect_secret_strict", return_value="new-protected"):
            self.store.set_ai_provider("glm", {"api_key": "new-fake-secret", "model": "fixture"})
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["ai"]["providers"]["glm"]["api_key_enc"], "new-protected")
        self.assertNotIn("api_key", saved["ai"]["providers"]["glm"])
        self.store.set_ai_provider("glm", {"api_key": "", "model": "fixture"})
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertNotIn("api_key_enc", saved["ai"]["providers"]["glm"])

    def test_save_can_retry_after_protection_recovers(self):
        with patch.object(
            settings, "_protect_secret_strict", side_effect=settings.SecretProtectError("fixture")
        ):
            self.store.set("general.language", "ms")
        with patch.object(settings, "_protect_secret_strict", return_value="reprotected"):
            self.store.set("general.language", "ms")
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["general"]["language"], "ms")
        self.assertEqual(saved["ai"]["providers"]["glm"]["api_key_enc"], "reprotected")


if __name__ == "__main__":
    unittest.main(verbosity=2)
