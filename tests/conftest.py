"""Pytest bridge for the standalone gate (see AGENTS.md "Test style").

The repo's real test gate is run_gate.bat: every tests/*.py script is a
STANDALONE program that runs its whole suite at import time and exits with
sys.exit()/os._exit(). Import-based pytest collection can never work here
(a script would run its suite during collection and kill the runner).

This conftest makes `pytest tests` equivalent to the gate: each script is
collected as ONE pytest item and executed in a fresh subprocess, exactly
like run_gate.bat does. A script passes when its process exits 0.
Fast iteration works the same way: `pytest tests/test_fixes65.py`.

Two guards keep pytest from importing a script in-process:
- pyproject `python_files = "gate_*.py"` stops directory discovery from
  handing test_*.py to the default Module collector;
- `pytest_pycollect_makemodule` below blocks the Module collector for
  files named on the command line (those bypass `python_files`).
Verified on pytest 8.4 and 9.1.

test_build_smoke.py is excluded: it needs the PyInstaller bundle, so the
bat gate does not run it either. probe_*.py and audit_i18n.py are manual
diagnostics, not gate members.
"""

import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import subprocess
import sys

import pytest


class GateScriptFailed(Exception):
    def __init__(self, returncode, output):
        super().__init__(f"gate script exited {returncode}")
        self.returncode = returncode
        self.output = output


class GateItem(pytest.Item):
    """One standalone gate script = one pytest item."""

    def runtest(self):
        proc = subprocess.run(
            [sys.executable, "-u", str(self.path)],
            cwd=self.path.parent.parent,
            capture_output=True,
            text=True,
            timeout=900,
        )
        if proc.returncode != 0:
            raise GateScriptFailed(proc.returncode, (proc.stdout or "") + (proc.stderr or ""))

    def repr_failure(self, excinfo):
        if isinstance(excinfo.value, GateScriptFailed):
            tail = excinfo.value.output[-4000:]
            return f"{self.path.name} exited {excinfo.value.returncode}:\n{tail}"
        return super().repr_failure(excinfo)

    def reportinfo(self):
        return self.path, 0, f"gate: {self.path.name}"


class GateFile(pytest.File):
    def collect(self):
        yield GateItem.from_parent(self, name=self.path.name)


def _is_gate_script(file_path) -> bool:
    name = file_path.name
    return name == "run_checks.py" or (
        name.startswith("test_") and name.endswith(".py") and name != "test_build_smoke.py"
    )


class _NoImport(pytest.File):
    """Stand-in for the default Module collector: collects nothing, so a
    gate script is never imported in-process (it would run its suite and
    exit the runner)."""

    def collect(self):
        return []


@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makemodule(module_path, parent):
    # Files named on the command line bypass `python_files`, so the default
    # Module collector would import them too (double collection). Block it.
    if _is_gate_script(module_path):
        return _NoImport.from_parent(parent, path=module_path)
    return None


def pytest_collect_file(file_path, parent):
    if _is_gate_script(file_path):
        return GateFile.from_parent(parent, path=file_path)
    return None
