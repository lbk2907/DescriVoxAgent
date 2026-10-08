"""Remove PyInstaller's duplicate copies of the bundled ffmpeg DLLs.

`--add-data "bin;bin"` puts the binaries where the app looks for them,
but PyInstaller also recognises the .dll files as libraries and writes
a second copy into `_internal\\` alongside the Python extensions. The
first 1.6.5 build carried all seven twice: 189 MB of duplicate, and
avcodec alone is 118 MB.

Nothing loads them from there. The app never links FFmpeg; it runs
ffmpeg.exe, which loads its DLLs from its own directory — `bin\\`. PyAV
has its own separate copies under `av.libs` and is untouched here.

Only files that are byte-identical to the copy in `bin\\` are removed,
and a mismatch stops the build rather than guessing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTERNAL = ROOT / "dist" / "DescriVox" / "_internal"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    bin_dir = INTERNAL / "bin"
    if not bin_dir.is_dir():
        print(f"DEDUPE_FAIL no bundled bin/ at {bin_dir}")
        return 1

    freed = 0
    removed = 0
    for bundled in sorted(bin_dir.glob("*.dll")):
        duplicate = INTERNAL / bundled.name
        if not duplicate.exists():
            continue
        if _digest(duplicate) != _digest(bundled):
            # Same name, different content: something else shipped a
            # library by this name and deleting it could break it.
            print(f"DEDUPE_FAIL {duplicate.name} differs from bin/ copy; not touching it")
            return 1
        size = duplicate.stat().st_size
        duplicate.unlink()
        freed += size
        removed += 1
        print(f"  removed duplicate {duplicate.name} ({size / 1e6:.1f} MB)")

    print(f"DEDUPE_OK {removed} duplicates removed, {freed / 1e6:.0f} MB freed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
