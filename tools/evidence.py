"""Evidence for the release contract, recorded by the tools themselves.

Before (6 Oct 2026) "the gate passed twice" and "NVDA heard 14/14" were
things the agent read on screen and reported. Now run_gate.bat, build.bat
and the NVDA check append one line each to an evidence log that
tools/release_check.py reads, with the commit they ran on - so a release is
judged on records, not on a summary.

    python tools/evidence.py gate <0|1>         # from run_gate.bat
    python tools/evidence.py build <zip path>   # from build.bat

The log lives outside the repository: %LOCALAPPDATA%\\OmniDescriber\\release\\
evidence.jsonl (ODC_EVIDENCE_DIR overrides it; tests always override it).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Files a build rewrites by itself (PyInstaller regenerates the spec).
NOISE = {"DescriVox.spec"}


def evidence_dir() -> Path:
    base = os.environ.get("ODC_EVIDENCE_DIR") or str(
        Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "OmniDescriber" / "release"
    )
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8"
    ).stdout.strip()


def head() -> str:
    return git("rev-parse", "HEAD")


def dirty() -> list[str]:
    """Tracked files changed but not committed (build noise ignored)."""
    out = []
    for line in git("status", "--porcelain", "--untracked-files=no").splitlines():
        path = line[3:].strip().split(" -> ")[-1]
        if path not in NOISE:
            out.append(path)
    return out


def working_tree() -> str:
    """The git tree of the tracked files AS THEY ARE NOW (uncommitted
    changes included): the gate usually runs before the commit, and what
    matters is whether the released code is the code that was tested."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="odc_evidx_") as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"))
        run = lambda *a: subprocess.run(
            ["git", *a],
            cwd=REPO,
            env=env,  # noqa: E731
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
        run("read-tree", "HEAD")
        run("add", "-A")  # new files too (.gitignore respected)
        return run("write-tree")


def changed_between(tree_a: str, tree_b: str) -> list[str]:
    out = git("diff", "--name-only", tree_a, tree_b)
    return [line for line in out.splitlines() if line.strip()]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def version() -> str:
    import re

    text = (REPO / "src/omni_describer_custom/__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def record(kind: str, **data) -> dict:
    entry = {
        "time": datetime.datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        "commit": head(),
        "tree": working_tree(),
        "dirty": dirty(),
        "version": version(),
        **data,
    }
    with (evidence_dir() / "evidence.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read() -> list[dict]:
    path = evidence_dir() / "evidence.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def main() -> int:
    kind = sys.argv[1] if len(sys.argv) > 1 else ""
    if kind == "gate":
        e = record("gate", ok=sys.argv[2:3] == ["0"])
    elif kind == "build":
        zip_path = Path(sys.argv[2])
        e = record(
            "build",
            ok=zip_path.exists(),
            zip=str(zip_path),
            zip_sha256=sha256_file(zip_path) if zip_path.exists() else "",
            exe_sha256=sha256_file(REPO / "dist/DescriVox/DescriVox.exe")
            if (REPO / "dist/DescriVox/DescriVox.exe").exists()
            else "",
        )
    else:
        print("usage: evidence.py gate <0|1> | build <zip>")
        return 2
    print(
        f"EVIDENCE {e['kind']} ok={e['ok']} commit={e['commit'][:8]}"
        + (f" dirty={len(e['dirty'])}" if e["dirty"] else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
