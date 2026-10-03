"""Pytest bridge for the standalone gate (see AGENTS.md "Test style").

The repo's real test gate is run_gate.bat: every tests/*.py script is a
STANDALONE program that runs its whole suite at import time and exits with
sys.exit()/os._exit(). Import-based pytest collection can never work here
(a script would run its suite during collection and kill the runner).

VERIFIED BEHAVIOUR (3 Oct 2026): per-file runs work, e.g.
`pytest tests/test_fixes65.py` = one item, runs the script standalone.
Whole-directory collection dies SILENTLY on this machine (exit 0, no
output, ~30 s) - cause not root-caused; run_gate.bat stays the
authoritative full gate. This conftest makes per-file pytest runs work: each script is
collected as ONE pytest item and executed in a fresh subprocess, exactly
like run_gate.bat does. A script passes when its process exits 0.

Fast iteration works the same way: `pytest tests/test_fixes65.py`.

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
            raise GateScriptFailed(
                proc.returncode, (proc.stdout or "") + (proc.stderr or "")
            )

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


@pytest.hookimpl(tryfirst=True)
def pytest_collect_file(file_path, path, parent):
    name = file_path.name
    if name == "run_checks.py" or (
        name.startswith("test_") and name.endswith(".py") and name != "test_build_smoke.py"
    ):
        return GateFile.from_parent(parent, path=file_path)
    return None
