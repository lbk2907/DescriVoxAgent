"""Download the external binaries the packaged app ships with.

The app calls out to ffmpeg, ffprobe, ffplay and yt-dlp. Before v1.6.5
it expected the user to have installed them; on a machine without
ffmpeg the app failed phase by phase, and without ffplay the player
ran descriptions over a silent video. They are bundled now.

The binaries are ~217 MB, so they are not kept in git — this script
fetches them into bin/ instead, and build.bat runs it before
PyInstaller. Run it by hand after a fresh clone:

    python tools/fetch_binaries.py

Add --force to re-download when a binary is already present.

LICENCE NOTE: the ffmpeg build fetched here is configured with
--enable-gpl --enable-version3, because ai_engine encodes upload
copies with libx264, which exists only in GPL builds. Distributing
this app therefore carries GPL obligations; see NOTICE.md.
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "bin"

FFMPEG_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/"
              "latest/ffmpeg-master-latest-win64-gpl-shared.zip")
YTDLP_URL = ("https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
             "yt-dlp.exe")

# The shared ffmpeg build splits the work across DLLs; the .exe files
# are small stubs and will not start without every one of them, so all
# are required rather than nice to have.
FFMPEG_MEMBERS = (
    "ffmpeg.exe", "ffprobe.exe", "ffplay.exe",
    "avcodec-63.dll", "avdevice-63.dll", "avfilter-12.dll",
    "avformat-63.dll", "avutil-61.dll",
    "swresample-7.dll", "swscale-10.dll",
)


def _download(url: str) -> bytes:
    print(f"  fetching {url}")
    with urllib.request.urlopen(url, timeout=300) as response:
        return response.read()


def fetch_ffmpeg(force: bool) -> None:
    if not force and (BIN / "ffmpeg.exe").exists():
        print("ffmpeg: already present, skipping (--force to replace)")
        return
    print("ffmpeg: downloading GPL shared build (~86 MB)")
    archive = zipfile.ZipFile(io.BytesIO(_download(FFMPEG_URL)))

    # Member names are prefixed with the build's own directory, whose
    # name carries the date, so they are matched by basename.
    wanted = {name: None for name in FFMPEG_MEMBERS}
    licence_member = None
    for info in archive.infolist():
        base = Path(info.filename).name
        if base in wanted and wanted[base] is None:
            wanted[base] = info.filename
        elif base == "LICENSE.txt":
            licence_member = info.filename

    absent = [name for name, found in wanted.items() if found is None]
    if absent:
        raise SystemExit(
            f"ffmpeg archive is missing {', '.join(absent)} — the upstream "
            "build layout or its library versions changed; update "
            "FFMPEG_MEMBERS in this script")

    BIN.mkdir(exist_ok=True)
    for name, member in wanted.items():
        with archive.open(member) as src, open(BIN / name, "wb") as dst:
            shutil.copyfileobj(src, dst)
        print(f"  {name}")

    if licence_member:
        with archive.open(licence_member) as src, \
                open(BIN / "FFMPEG-LICENSE.txt", "wb") as dst:
            shutil.copyfileobj(src, dst)
        print("  FFMPEG-LICENSE.txt")

    # Record which build shipped: a GPL distribution has to be able to
    # say which source the binaries correspond to.
    version = _run_version(BIN / "ffmpeg.exe")
    (BIN / "FFMPEG-VERSION.txt").write_text(version + "\n", encoding="utf-8")
    print(f"  version {version}")


def _run_version(exe: Path) -> str:
    import subprocess
    try:
        out = subprocess.run([str(exe), "-hide_banner", "-version"],
                             capture_output=True, text=True, timeout=60)
        first = out.stdout.splitlines()[0]
        return first.split()[2]  # "ffmpeg version N-126734-g... Copyright"
    except Exception:
        return "unknown"


def fetch_ytdlp(force: bool) -> None:
    target = BIN / "yt-dlp.exe"
    if not force and target.exists():
        print("yt-dlp: already present, skipping (--force to replace)")
        return
    print("yt-dlp: downloading (~18 MB)")
    BIN.mkdir(exist_ok=True)
    target.write_bytes(_download(YTDLP_URL))
    print("  yt-dlp.exe")


def verify() -> int:
    """Report anything still absent. Returns a process exit code."""
    sys.path.insert(0, str(BIN.parent / "src"))
    from omni_describer_custom.core.tools import missing_tools
    absent = missing_tools()
    if absent:
        print("\nSTILL MISSING:")
        for name, why in absent:
            print(f"  {name} — needed for {why}")
        return 1
    print("\nAll external tools present.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="re-download binaries that already exist")
    args = parser.parse_args()

    fetch_ffmpeg(args.force)
    fetch_ytdlp(args.force)
    return verify()


if __name__ == "__main__":
    raise SystemExit(main())
