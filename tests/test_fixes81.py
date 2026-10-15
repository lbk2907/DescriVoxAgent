"""Headless regressions for project switching and complete agent rename undo."""

import isolate  # noqa: F401
import ast
import copy
import logging
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from omni_describer_custom.core import characters as ch  # noqa: E402
from omni_describer_custom.core.project_store import Description  # noqa: E402


def method(file, cls, name, **extra):
    tree = ast.parse((ROOT / "src/omni_describer_custom" / file).read_text(encoding="utf-8"))
    owner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    node = next(n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = {"__package__": "omni_describer_custom.ui", "logger": logging.getLogger(__name__)}
    namespace.update(extra)
    exec(compile(ast.Module(body=[node], type_ignores=[]), file, "exec"), namespace)
    return namespace[name]


class PlayerSafetyTests(unittest.TestCase):
    def test_explicit_new_project_overrides_matching_original_source(self):
        source = "https://example.invalid/video"
        old = SimpleNamespace(id=1, video_path="media/video.mp4", source_path=source)
        created = []
        store = SimpleNamespace(current=old, media_dir=lambda project_id: Path(str(project_id)))

        def create(name, value):
            created.append((name, value))
            store.current = SimpleNamespace(id=2, video_path=value, source_path=value)

        store.create_project = create
        frame = SimpleNamespace(
            project_store=store,
            _project_source="",
            _force_new_project_source=source,
            _pending_project_name=(source, "Second analysis"),
            _project_display_name=lambda _: "Video",
        )
        ensure = method("ui/main_frame.py", "MainFrame", "_ensure_project_for", Path=Path)
        self.assertEqual(ensure(frame, source), "2")
        self.assertEqual(created, [("Second analysis", source)])
        self.assertIsNot(store.current, old)
        self.assertIsNone(frame._pending_project_name)
        self.assertEqual(ensure(frame, source), "2")
        self.assertEqual(len(created), 1)

    def player(self):
        project = SimpleNamespace(
            id=1, descriptions=[Description(start_time=1, end_time=4, text="Rahim nods.")]
        )
        player = SimpleNamespace(
            project=project,
            store=SimpleNamespace(current=project, project_dir=lambda _: Path("unused")),
            _agent_undo=[],
            _agent_backup_done=False,
            _project_srt_path=lambda: SimpleNamespace(exists=lambda: False),
            _save_agent_descriptions=lambda: None,
        )
        return player

    def test_rename_undo_restores_cast_and_descriptions(self):
        player = self.player()
        original = [{"name": "Rahim", "look": "grey coat", "by_user": True}]
        cast = copy.deepcopy(original)

        def save(_folder, value):
            cast[:] = copy.deepcopy(value)
            return True

        apply = method("ui/player_window.py", "PlayerWindow", "apply_agent_changes")
        undo = method("ui/player_window.py", "PlayerWindow", "undo_agent_changes")
        with (
            patch.object(ch, "load_cast", lambda _: copy.deepcopy(cast)),
            patch.object(ch, "save_cast", save),
        ):
            proposal = SimpleNamespace(action="rename", index=None, old="Rahim", text="Ali")
            self.assertEqual(apply(player, [proposal]), 1)
            self.assertEqual(cast[0]["name"], "Ali")
            self.assertTrue(undo(player))
            self.assertEqual(player.project.descriptions[0].text, "Rahim nods.")
            self.assertEqual(cast, original)

    def test_failed_cast_restore_keeps_undo_and_descriptions(self):
        player = self.player()
        before = copy.deepcopy(player.project.descriptions)
        player.project.descriptions[0].text = "Ali nods."
        player._agent_undo = [(before, [{"name": "Rahim", "look": "grey coat"}])]
        undo = method("ui/player_window.py", "PlayerWindow", "undo_agent_changes")
        with patch.object(ch, "save_cast", return_value=False):
            self.assertFalse(undo(player))
        self.assertEqual(player.project.descriptions[0].text, "Ali nods.")
        self.assertEqual(len(player._agent_undo), 1)

    def test_stale_player_cannot_undo(self):
        player = self.player()
        player._agent_undo = [(copy.deepcopy(player.project.descriptions), None)]
        player.store.current = SimpleNamespace(id=2, descriptions=[])
        undo = method("ui/player_window.py", "PlayerWindow", "undo_agent_changes")
        self.assertFalse(undo(player))
        self.assertEqual(len(player._agent_undo), 1)

    def test_text_edit_undo_does_not_overwrite_cast(self):
        player = self.player()
        apply = method("ui/player_window.py", "PlayerWindow", "apply_agent_changes")
        undo = method("ui/player_window.py", "PlayerWindow", "undo_agent_changes")
        with patch.object(ch, "save_cast") as save:
            proposal = SimpleNamespace(action="edit", index=0, text="Rahim waves.")
            self.assertEqual(apply(player, [proposal]), 1)
            self.assertTrue(undo(player))
            self.assertEqual(player.project.descriptions[0].text, "Rahim nods.")
            save.assert_not_called()

    def test_stale_player_cannot_apply_to_another_project(self):
        player = self.player()
        player.store.current = SimpleNamespace(id=2, descriptions=[])
        apply = method("ui/player_window.py", "PlayerWindow", "apply_agent_changes")
        proposal = SimpleNamespace(action="edit", index=0, text="Wrong project.")
        self.assertEqual(apply(player, [proposal]), 0)
        self.assertEqual(player.project.descriptions[0].text, "Rahim nods.")

    def test_stale_player_save_is_rejected_before_store_write(self):
        player = self.player()
        player.store.current = SimpleNamespace(id=2, descriptions=[])
        writes = []
        player.store.save_descriptions = lambda value: writes.append(value)
        player._agent = None
        player._narrated = set()
        player._update_desc_display = lambda: None
        save = method("ui/player_window.py", "PlayerWindow", "_save_agent_descriptions")
        save(player)
        self.assertEqual(writes, [])

    def test_project_open_closes_players_before_store_switch(self):
        # Inspect the actual call order without creating a native dialog.
        source = (ROOT / "src/omni_describer_custom/ui/main_frame.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        owner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MainFrame")
        handler = next(
            n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name == "_on_open_project"
        )
        switches = [
            n
            for n in ast.walk(handler)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "open_project"
        ]
        closes = [
            n.lineno
            for n in ast.walk(handler)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "_close_players"
        ]
        self.assertTrue(closes and max(closes) < switches[0].lineno)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    unittest.main(verbosity=2)
