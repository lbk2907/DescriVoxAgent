"""Back up the source code of the current commit as a zip (owner, 3 Oct 2026).

    python tools/make_source_zip.py            # into Documents\\DescriVox-source-backups
    python tools/make_source_zip.py --out DIR

Run by build.bat after every release build. The zip is made with
`git archive HEAD`, so it holds ONLY files committed to this repository:
no exe, no build output, no settings, no projects, no untracked files.
It is then checked file by file, and the step fails rather than leave a
backup that is not what it claims to be:

- every file must be text (source, tests, docs, scripts);
- no forbidden kind of file (.exe, .dll, .zip, video, database, ...);
- nothing that looks like an API key.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FORBIDDEN = (".exe", ".dll", ".pyd", ".zip", ".7z", ".msi", ".mp4", ".mkv",
             ".mp3", ".wav", ".db", ".sqlite", ".onnx", ".bin", ".pt")
KEY = re.compile(rb"(sk-or-v1-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|sk-[A-Za-z0-9]{30,})")


def problems(zip_path: Path) -> list[str]:
    """Why this zip is not a clean source backup (empty list = clean)."""
    found = []
    with zipfile.ZipFile(zip_path) as z:
        bad = z.testzip()
        if bad:
            found.append(f"damaged entry: {bad}")
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename
            low = name.lower()
            if low.endswith(FORBIDDEN) or "/dist/" in low or "/build/" in low \
                    or low.endswith("settings.json"):
                found.append(f"not source: {name}")
                continue
            data = z.read(info)
            if b"\x00" in data:
                found.append(f"binary file: {name}")
            if KEY.search(data):
                found.append(f"looks like an API key: {name}")
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path.home() / "Documents" / "DescriVox-source-backups"))
    args = ap.parse_args()
    sys.path.insert(0, str(REPO / "src"))
    from omni_describer_custom import __version__ as version
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"DescriVox-Agent-source-v{version}.zip"
    subprocess.run(["git", "archive", "--format=zip",
                    f"--prefix=DescriVox-Agent-v{version}/", "-o", str(out), "HEAD"],
                   cwd=str(REPO), check=True)
    found = problems(out)
    if found:
        out.unlink()
        print("SOURCE_ZIP_FAIL")
        for line in found:
            print("  -", line)
        return 1
    with zipfile.ZipFile(out) as z:
        count = sum(1 for i in z.infolist() if not i.is_dir())
    print(f"SOURCE_ZIP_OK {out} ({count} files, {out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
