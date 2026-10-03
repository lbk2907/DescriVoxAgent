"""Packaging content test: verify the PyInstaller bundle really contains the
new features by reading the PYZ archive inside the built exe.

Checks (when dist/DescriVox/DescriVox.exe exists):
1. PYZ archive is extractable from the CArchive
2. omni_describer_custom.core.timeline_io / ui.main_frame / core.tts_engine
   are bundled
3. main_frame code object carries the import/export handler keys
   (impexp.dlg_import, impexp.invalid_file, impexp.imported)
4. tts_engine code object carries the win32com SAPI.SpFileStream fix marker
5. timeline_io code object carries the WEBVTT parser marker

Skips cleanly (exit 0, marker PACKAGING_SKIPPED) when no build exists, so the
gate stays usable from a fresh checkout. Prints PACKAGING_<CHECK> markers.
Exits 0 on pass, 1 on failure.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "DescriVox" / "DescriVox.exe"


def fail(msg: str) -> None:
    print(f"PACKAGING_FAIL {msg}", flush=True)
    sys.exit(1)


def walk_strings(co):
    out = []
    stack = [co]
    while stack:
        cur = stack.pop()
        for k in cur.co_consts:
            if hasattr(k, "co_consts"):
                stack.append(k)
            elif isinstance(k, str):
                out.append(k)
    return out


def main() -> None:
    if not EXE.exists():
        print("PACKAGING_SKIPPED_NO_BUILD", flush=True)
        return

    from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

    c = CArchiveReader(str(EXE))
    pyz_names = [n for n in c.toc if n.lower().endswith(".pyz")]
    if not pyz_names:
        fail("no .pyz entry in CArchive TOC")
    raw = c.extract(pyz_names[0])
    print("PACKAGING_PYZ_EXTRACTED", flush=True)

    fd, tmp = tempfile.mkstemp(suffix=".pyz")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        z = ZlibArchiveReader(tmp)

        required = [
            "omni_describer_custom.core.timeline_io",
            "omni_describer_custom.ui.main_frame",
            "omni_describer_custom.core.tts_engine",
        ]
        for m in required:
            if m not in z.toc:
                fail(f"module missing from PYZ: {m}")
        print("PACKAGING_MODULES_OK", flush=True)

        mf_strings = set(walk_strings(z.extract("omni_describer_custom.ui.main_frame")))
        for marker in ("impexp.dlg_import", "impexp.invalid_file", "impexp.imported"):
            if marker not in mf_strings:
                fail(f"main_frame marker missing in bundle: {marker}")
        print("PACKAGING_IMPEXP_MARKERS_OK", flush=True)

        tts_strings = set(walk_strings(z.extract("omni_describer_custom.core.tts_engine")))
        if not any("SpFileStream" in s for s in tts_strings):
            fail("tts_engine SAPI.SpFileStream fix marker missing in bundle")
        print("PACKAGING_TTS_FIX_MARKER_OK", flush=True)

        tio_strings = set(walk_strings(z.extract("omni_describer_custom.core.timeline_io")))
        if not any("WEBVTT" in s for s in tio_strings):
            fail("timeline_io WEBVTT parser marker missing in bundle")
        print("PACKAGING_TIMELINE_MARKER_OK", flush=True)
    finally:
        os.unlink(tmp)

    # v1.6.5: the external binaries ride along as data, not as PYZ
    # modules, so they are checked on disk. A bundle that omits them
    # starts fine and then fails at the first download, which is the
    # failure this whole change exists to remove.
    bundled_bin = EXE.parent / "_internal" / "bin"
    if not bundled_bin.is_dir():
        fail(f"the build has no bundled bin/ at {bundled_bin}")
    for name in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe", "yt-dlp.exe",
                 "FFMPEG-LICENSE.txt"):
        if not (bundled_bin / name).exists():
            fail(f"the build does not ship bin/{name}")
    dll_count = len(list(bundled_bin.glob("*.dll")))
    if dll_count < 7:
        fail(f"only {dll_count} ffmpeg DLLs shipped; the shared build "
             f"needs all of them or the exes will not start")
    print("PACKAGING_BINARIES_OK", flush=True)

    # PyInstaller writes a second copy of each ffmpeg DLL next to the
    # Python extensions because it recognises them as libraries; that
    # was 189 MB of duplicate in the first 1.6.5 build, avcodec alone
    # being 118 MB. tools/dedupe_build.py removes them.
    duplicates = [p.name for p in bundled_bin.glob("*.dll")
                  if (EXE.parent / "_internal" / p.name).exists()]
    if duplicates:
        fail(f"ffmpeg DLLs duplicated at _internal top level: "
             f"{duplicates} — run tools/dedupe_build.py")
    print("PACKAGING_NO_DUPLICATE_DLLS_OK", flush=True)

    if not (EXE.parent / "NOTICE.md").exists():
        fail("NOTICE.md is not next to the exe; the GPL notice would be "
             "buried in _internal where nobody opens it")
    print("PACKAGING_NOTICE_OK", flush=True)

    # v1.7.5: --collect-all ctranslate2 dragged in its model CONVERTERS,
    # which import torch: 365 MB the app never loads (Whisper runs
    # without it — transcribed Sintel with torch blocked). coverage came
    # along the same way.
    for unwanted in ("torch", "coverage"):
        if (EXE.parent / "_internal" / unwanted).exists():
            fail(f"the build ships {unwanted}, which the app never uses "
                 f"— check the --exclude-module flags in build.bat")
    print("PACKAGING_NO_TORCH_OK", flush=True)

    print("PACKAGING_ALL_OK", flush=True)


if __name__ == "__main__":
    main()
