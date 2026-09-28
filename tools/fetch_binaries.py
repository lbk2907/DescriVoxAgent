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
import hashlib
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "bin"

# v1.7.5: PINNED. These used to be "latest", so every build could ship
# a different ffmpeg and yt-dlp, unverified. Each download is now
# checked against the hash the publisher itself lists (the GitHub
# release digest for BtbN, SHA2-256SUMS for yt-dlp), and every file in
# bin/ against the hashes below — also when it is "already present".
#
# To move to a newer release: change the URL, run with --print-hashes,
# check the archive hash against the release page, paste the new values,
# then run the gate and a real E2E before shipping.
FFMPEG_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/"
              "autobuild-2026-09-21-13-55/"
              "ffmpeg-N-126734-ga9cbcc2bbb-win64-gpl-shared.zip")
FFMPEG_ZIP_SHA256 = (
    "0886420de730e186a747d29192ec176148a7c24f8ec89d8515023e7e18ad504b")
YTDLP_URL = ("https://github.com/yt-dlp/yt-dlp/releases/download/"
             "2026.08.19/yt-dlp.exe")

BINARY_SHA256 = {
    "ffmpeg.exe": "24770f008456164ec0bf0d23c93f26347580378e8b977ff92bc624a316a423b6",
    "ffprobe.exe": "50a91a439b577a5d133da1e01df6a4e9332fa604f14c9c6a839da48b359aa945",
    "ffplay.exe": "79706a9505d023bceeb11f4197e2507175dada7d8f88d5dd6baa05d79f9e1eb3",
    "avcodec-63.dll": "dcdb276a3b3803f64aa8a3e217b9efe363e9f9886a4e23407dbd79030a48354a",
    "avdevice-63.dll": "e19c4ee259a891f05c45eb4da711ff70a994e1dc7e7634ab8199d1319b762b8b",
    "avfilter-12.dll": "6a1571d5649fa405cb018dfd1cc47c22d4eb8401a6279fbe44e07d730b1d6228",
    "avformat-63.dll": "c250c51148a313c57ec724c63afa8c7ea9f27ebde019bbff96d66c58238127b7",
    "avutil-61.dll": "810664c6586f60f0a49f95f819949183dbe1beb1feed578007aaa09757e25171",
    "swresample-7.dll": "c6b4195f2cde55ced84f327166f879fdd732fe844119806ca3690d3f4e82bbf1",
    "swscale-10.dll": "f5f4b2907d4465c3475e69e2f52e05de08563bb11d3b33ee74e2254aae1b179b",
    "yt-dlp.exe": "66674953fe251b89f4d08c5f0e35e0728679bd67ab3d7d05c0562af101dd3e7a",
}

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


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_hash(label: str, data: bytes, expected: str) -> None:
    actual = _sha256(data)
    if actual != expected:
        raise SystemExit(
            f"{label}: SHA-256 {actual} does not match the pinned "
            f"{expected}. Refusing to ship an unverified binary.")


def fetch_ffmpeg(force: bool) -> None:
    if not force and (BIN / "ffmpeg.exe").exists():
        print("ffmpeg: already present, skipping (--force to replace)")
        return
    print("ffmpeg: downloading GPL shared build (~86 MB)")
    data = _download(FFMPEG_URL)
    _require_hash("ffmpeg archive", data, FFMPEG_ZIP_SHA256)
    archive = zipfile.ZipFile(io.BytesIO(data))

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
        payload = archive.read(member)
        _require_hash(name, payload, BINARY_SHA256[name])
        (BIN / name).write_bytes(payload)
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
    data = _download(YTDLP_URL)
    _require_hash("yt-dlp.exe", data, BINARY_SHA256["yt-dlp.exe"])
    target.write_bytes(data)
    print("  yt-dlp.exe")


def verify_hashes() -> int:
    """Check every pinned binary in bin/ — present ones included, since
    "already present" was never proof of WHAT is present."""
    wrong = []
    for name, expected in BINARY_SHA256.items():
        path = BIN / name
        if path.exists() and _sha256(path.read_bytes()) != expected:
            wrong.append(name)
    if wrong:
        print("\nHASH MISMATCH (bin/ does not hold the pinned release): "
              + ", ".join(wrong))
        print("Run with --force to fetch the pinned versions.")
        return 1
    print("All pinned binaries match their SHA-256.")
    return 0


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
    parser.add_argument("--print-hashes", action="store_true",
                        help="print SHA-256 of the files in bin/ (for "
                             "updating BINARY_SHA256) and exit")
    args = parser.parse_args()

    if args.print_hashes:
        for name in BINARY_SHA256:
            path = BIN / name
            if path.exists():
                print(f'    "{name}": "{_sha256(path.read_bytes())}",')
        return 0
    fetch_ffmpeg(args.force)
    fetch_ytdlp(args.force)
    return verify() or verify_hashes()


if __name__ == "__main__":
    raise SystemExit(main())
