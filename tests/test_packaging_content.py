"""Packaging content test: verify the PyInstaller bundle really contains the
new features by reading the PYZ archive inside the built exe.

Checks (when dist/OmniDescriber/OmniDescriber.exe exists):
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
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "OmniDescriber" / "OmniDescriber.exe"


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

    print("PACKAGING_ALL_OK", flush=True)


if __name__ == "__main__":
    main()
