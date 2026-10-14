"""Custom prompt persistence and main-window dispatch without GUI or AI calls."""

import isolate  # noqa: F401
import ast
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from omni_describer_custom.core.prompt_manager import PromptManager  # noqa: E402
from omni_describer_custom.core.settings_store import SettingsStore  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class PromptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ["ODC_CONFIG_DIR"])
        self.addCleanup(self.tmp.cleanup)
        self.manager = PromptManager(SettingsStore(self.tmp.name))
        self.manager.language = "id"
        tree = ast.parse(
            (ROOT / "src/omni_describer_custom/ui/main_frame.py").read_text(encoding="utf-8")
        )
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MainFrame")
        names = {
            "_on_preset_open",
            "_prompt_editor_text",
            "_preset_is_builtin",
            "_on_preset_save_as",
            "_on_preset_update",
            "_on_preset_delete",
        }
        nodes = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
        self.wx = SimpleNamespace(
            OK=1, ICON_WARNING=2, ID_OK=3, MessageBox=Mock(), TextEntryDialog=Mock()
        )
        self.dialog = Mock()
        self.dialog.ShowModal.return_value = self.wx.ID_OK
        self.dialog.GetValue.return_value = "My prompt"
        self.wx.TextEntryDialog.return_value = self.dialog
        ns = {"__package__": "omni_describer_custom.ui", "wx": self.wx, "t": lambda k, **kw: k}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "main_frame.py", "exec"), ns)
        cls = type("Frame", (), {name: ns[name] for name in names if name in ns})
        self.f = cls()
        self.f.prompt_mgr = self.manager
        self.f.prompt_choice = Mock()
        self.f.prompt_choice.GetStringSelection.return_value = "default"
        self.f.custom_prompt = Mock()
        self.f.custom_prompt.GetValue.return_value = "Describe only the visible text."
        for name in (
            "_start_processing",
            "_log",
            "_refresh_prompt_list",
            "_preview_preset",
            "_preset_notice",
        ):
            setattr(self.f, name, Mock())
        self.confirm = self.enterContext(
            patch("omni_describer_custom.ui.dialogs.ask_yes_no", return_value=True)
        )

    def test_edited_prompt_replaces_original(self):
        self.f._on_preset_open(None)
        self.f._start_processing.assert_called_once_with("Describe only the visible text.")

    def test_empty_editor_does_not_start_processing(self):
        self.f.custom_prompt.GetValue.return_value = "  "
        self.f._on_preset_open(None)
        self.f._start_processing.assert_not_called()
        self.wx.MessageBox.assert_called_once()

    def test_save_as_survives_new_manager(self):
        self.f._on_preset_save_as(None)
        stored = json.loads((Path(self.tmp.name) / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["prompts"]["id_My prompt"], "Describe only the visible text.")
        reopened = PromptManager(SettingsStore(self.tmp.name))
        reopened.language = "id"
        self.assertEqual(reopened.get_preset("My prompt"), "Describe only the visible text.")
        reopened.language = "en"
        self.assertNotIn("My prompt", reopened.get_preset_names())
        self.dialog.Destroy.assert_called_once()

    def test_cancel_save_as_does_not_write(self):
        self.dialog.ShowModal.return_value = 0
        self.f._on_preset_save_as(None)
        self.assertNotIn("My prompt", self.manager.get_preset_names())
        self.dialog.Destroy.assert_called_once()

    def test_duplicate_and_builtin_names_are_rejected(self):
        for name in ("default", "My prompt"):
            if name == "My prompt":
                self.manager.set_preset(name, "Original")
            before = self.manager.get_preset(name)
            self.dialog.GetValue.return_value = name
            self.f._on_preset_save_as(None)
            self.assertEqual(self.manager.get_preset(name), before)

    def test_update_and_delete_custom_preset(self):
        self.manager.set_preset("My prompt", "Old")
        self.f.prompt_choice.GetStringSelection.return_value = "My prompt"
        self.f._on_preset_update(None)
        self.assertEqual(self.manager.get_preset("My prompt"), "Describe only the visible text.")
        self.f._on_preset_delete(None)
        self.assertNotIn("My prompt", self.manager.get_preset_names())

    def test_reject_update_and_delete_preserves_content(self):
        self.manager.set_preset("My prompt", "Old")
        self.f.prompt_choice.GetStringSelection.return_value = "My prompt"
        self.confirm.return_value = False
        self.f._on_preset_update(None)
        self.f._on_preset_delete(None)
        self.assertEqual(self.manager.get_preset("My prompt"), "Old")

    def test_builtin_cannot_be_updated_or_deleted(self):
        original = self.manager.get_preset("default")
        self.f._on_preset_update(None)
        self.f._on_preset_delete(None)
        self.assertEqual(self.manager.get_preset("default"), original)
        self.confirm.assert_not_called()

    def test_invalid_text_and_name_are_not_saved(self):
        for text, name in ((" ", "Empty"), ("x" * 5001, "Long"), ("Text", " ")):
            self.f.custom_prompt.GetValue.return_value = text
            self.dialog.GetValue.return_value = name
            before = self.manager.export_prompts()
            self.f._on_preset_save_as(None)
            self.assertEqual(self.manager.export_prompts(), before)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    unittest.main(verbosity=2)
