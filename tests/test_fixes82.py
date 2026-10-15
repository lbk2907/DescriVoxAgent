"""Headless Windows launcher regressions; fixture scripts never open the real app."""

import isolate  # noqa: F401
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POWERSHELL = str(
    Path(os.environ.get("SystemRoot", r"C:\Windows"))
    / "System32/WindowsPowerShell/v1.0/powershell.exe"
)
CMD = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")


@unittest.skipUnless(sys.platform == "win32", "Windows batch launchers")
class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ["ODC_CONFIG_DIR"])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "checkout with spaces"
        self.root.mkdir()
        (self.root / "tools").mkdir()
        for name in ("run.bat", "build.bat", "run_gate.bat"):
            shutil.copy2(ROOT / name, self.root / name)
        resolver = ROOT / "tools/find_python.ps1"
        if resolver.exists():
            shutil.copy2(resolver, self.root / "tools/find_python.ps1")
        self.env = dict(os.environ)
        for key in ("VIRTUAL_ENV", "ODC_PYTHON", "PYTHONHOME"):
            self.env.pop(key, None)
        self.env["ODC_PYTHON"] = sys.executable
        self.env["PYTHONPATH"] = str(self.root)
        self.env["LOCALAPPDATA"] = str(self.root / "empty local appdata")
        self.env["PATH"] = str(Path(POWERSHELL).parent)

    def batch(self, name):
        return subprocess.run(
            [CMD, "/d", "/c", str(self.root / name)],
            cwd=self.temp.name,
            env=self.env,
            input="",
            capture_output=True,
            text=True,
            timeout=40,
        )

    def resolve(self):
        return subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.root / "tools/find_python.ps1"),
            ],
            cwd=self.temp.name,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_run_uses_checkout_and_preserves_failure(self):
        (self.root / "main.py").write_text(
            "from pathlib import Path\nassert Path.cwd() == Path(__file__).parent\n"
            "print('FIXTURE_APP_RAN')\nraise SystemExit(13)\n",
            encoding="utf-8",
        )
        result = self.batch("run.bat")
        self.assertIn("FIXTURE_APP_RAN", result.stdout, result.stdout + result.stderr)
        self.assertEqual(result.returncode, 13, result.stdout + result.stderr)

    def test_build_stops_at_failed_document_check(self):
        (self.root / "tools/check_docs.py").write_text(
            "from pathlib import Path\nassert Path.cwd() == Path(__file__).parents[1]\n"
            "print('FIXTURE_DOC_CHECK')\nraise SystemExit(17)\n",
            encoding="utf-8",
        )
        result = self.batch("build.bat")
        self.assertIn("FIXTURE_DOC_CHECK", result.stdout, result.stdout + result.stderr)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("external binaries", result.stdout)

    def test_full_build_dispatch_without_downloads_or_gui(self):
        interpreter_dir = self.root / "build python with spaces"
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(interpreter_dir)],
            check=True,
            capture_output=True,
            timeout=30,
        )
        self.env["ODC_PYTHON"] = str(interpreter_dir / "Scripts/python.exe")
        (self.root / "main.py").write_text("# fixture only\n", encoding="utf-8")
        (self.root / "NOTICE.md").write_text("Fixture notice\n", encoding="utf-8")
        package = self.root / "src/omni_describer_custom"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("__version__ = '0.0.0'\n", encoding="utf-8")
        (self.root / "PyInstaller.py").write_text(
            "from pathlib import Path\np = Path('dist/DescriVox')\np.mkdir(parents=True)\n"
            "(p / 'DescriVox.exe').write_text('fixture')\n",
            encoding="utf-8",
        )
        for name in (
            "check_docs",
            "fetch_binaries",
            "dedupe_build",
            "release_files",
            "make_source_zip",
        ):
            (self.root / f"tools/{name}.py").write_text("# fixture only\n", encoding="utf-8")
        (self.root / "tools/evidence.py").write_text(
            "import json, sys\nfrom pathlib import Path\n"
            "Path('evidence.json').write_text(json.dumps(sys.argv[1:]))\n",
            encoding="utf-8",
        )
        (self.root / "tests").mkdir()
        (self.root / "tests/test_build_smoke.py").write_text("# no GUI\n", encoding="utf-8")
        result = self.batch("build.bat")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("BUILD_ALL_OK", result.stdout)
        self.assertTrue((self.root / "dist/DescriVox-Agent-0.0.0-win64.zip").is_file())
        self.assertEqual(
            json.loads((self.root / "evidence.json").read_text()),
            ["build", "dist/DescriVox-Agent-0.0.0-win64.zip"],
        )

    def test_override_is_validated_and_has_priority(self):
        self.env["VIRTUAL_ENV"] = str(self.root / "nonexistent env")
        result = self.resolve()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()).resolve(), Path(sys.executable).resolve())

    def test_bad_override_fails_without_falling_back(self):
        self.env["ODC_PYTHON"] = str(self.root / "missing python.exe")
        result = self.resolve()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ODC_PYTHON", result.stderr)
        self.assertFalse(result.stdout.strip())

    def test_missing_python_reports_actionable_error(self):
        self.env.pop("ODC_PYTHON")
        result = self.resolve()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Python 3.13", result.stderr)
        self.assertIn("ODC_PYTHON", result.stderr)
        self.assertFalse(result.stdout.strip())

    def test_project_venv_with_spaces(self):
        self.env.pop("ODC_PYTHON")
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(self.root / ".venv")],
            check=True,
            capture_output=True,
            timeout=30,
        )
        result = self.resolve()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            Path(result.stdout.strip()).resolve(),
            (self.root / ".venv/Scripts/python.exe").resolve(),
        )

    def test_gate_fails_before_running_tests_when_override_is_bad(self):
        self.env["ODC_PYTHON"] = str(self.root / "missing python.exe")
        result = self.batch("run_gate.bat")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ODC_PYTHON", result.stdout + result.stderr)
        self.assertNotIn("test_fixes:", result.stdout)

    def test_active_environment_has_priority(self):
        self.env.pop("ODC_PYTHON")
        active = self.root / "active env"
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(active)],
            check=True,
            capture_output=True,
            timeout=30,
        )
        self.env["VIRTUAL_ENV"] = str(active)
        result = self.resolve()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            Path(result.stdout.strip()).resolve(), (active / "Scripts/python.exe").resolve()
        )

    def test_path_fallback(self):
        self.env.pop("ODC_PYTHON")
        self.env["PATH"] = str(Path(sys.executable).parent)
        result = self.resolve()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()).resolve(), Path(sys.executable).resolve())

    def test_launcher_selects_313(self):
        self.env.pop("ODC_PYTHON")
        commands = self.root / "commands"
        commands.mkdir()
        (commands / "py.cmd").write_text(
            '@echo off\nif not "%~1"=="-3.13" exit /b 1\n'
            f'"{sys.executable}" -I -c "import sys; print(sys.executable)"\n',
            encoding="utf-8",
        )
        self.env["PATH"] = str(commands)
        result = self.resolve()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()).resolve(), Path(sys.executable).resolve())


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    unittest.main(verbosity=2)
