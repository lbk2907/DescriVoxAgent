"""
Unit tests for v1.3.0 features (no GUI needed).

Covers:
- parse_srt / parse_any round-trip with to_srt
- ProjectStore.persist_video_file (copy into project media dir, DB update)
- ProjectStore.set_video_path (DB + memory update)
- ProjectStore.media_dir creation
"""
from __future__ import annotations

import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from omni_describer_custom.core.project_store import ProjectStore
from omni_describer_custom.core.timeline_io import (
    Description, parse_any, parse_srt, to_srt,
)

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name} {detail}")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="odc_v130_test_"))
    print(f"Temp dir: {tmp}")

    # ── 1. SRT round trip ────────────────────────────────────────
    print("[1] SRT parse / to_srt round-trip")
    descs = [
        Description(start_time=1.0, end_time=4.5, text="A red-black jacket"),
        Description(start_time=10.25, end_time=13.0, text="Elephant behind fence\nsecond line"),
    ]
    srt_text = to_srt(descs)
    p = tmp / "round.srt"
    p.write_text(srt_text, encoding="utf-8")
    parsed = parse_srt(p)
    check("two cues parsed", len(parsed) == 2, str(len(parsed)))
    check("start 1.0", abs(parsed[0].start_time - 1.0) < 0.01, str(parsed[0].start_time))
    check("end 4.5", abs(parsed[0].end_time - 4.5) < 0.01, str(parsed[0].end_time))
    check("ms 10.250", abs(parsed[1].start_time - 10.25) < 0.001, str(parsed[1].start_time))
    check("multiline kept", "second line" in parsed[1].text, parsed[1].text)
    check("text round trip", parsed[0].text == "A red-black jacket", parsed[0].text)

    # parse_any dispatch on .srt
    parsed2 = parse_any(p)
    check("parse_any dispatch", len(parsed2) == 2, str(len(parsed2)))

    # BOM + CRLF tolerance
    p2 = tmp / "bom.srt"
    p2.write_bytes(b"\xef\xbb\xbf1\r\n00:00:02,000 --> 00:00:05,000\r\nBOM cue\r\n\r\n")
    parsed3 = parse_srt(p2)
    check("BOM+CRLF parse", len(parsed3) == 1 and parsed3[0].text == "BOM cue",
          str([d.text for d in parsed3]))

    # ── 2. ProjectStore video persistence ────────────────────────
    print("[2] ProjectStore.persist_video_file / set_video_path")
    store = ProjectStore(str(tmp / "projects"))
    fake_video = tmp / "video.mp4"
    fake_video.write_bytes(b"FAKEVIDEO" * 1000)
    proj = store.create_project("Test Project", "https://youtu.be/abc")
    out = store.persist_video_file(str(fake_video))
    expect = store.project_dir(1) / "media" / "video.mp4"
    check("copied into media dir", Path(out) == expect, out)
    check("file exists", expect.exists())
    check("same content", expect.stat().st_size == fake_video.stat().st_size)
    check("video_path updated in memory", proj.video_path == str(expect), proj.video_path)

    # DB row really updated
    conn = sqlite3.connect(str(store._db_path(1)))
    row = conn.execute("SELECT video_path FROM projects WHERE id=1").fetchone()
    conn.close()
    check("video_path updated in DB", row and row[0] == str(expect), str(row))

    # Persisting twice does not duplicate/corrupt
    out2 = store.persist_video_file(str(fake_video))
    check("idempotent re-persist", Path(out2) == expect and expect.exists(), out2)

    # Nonexistent source returns unchanged, no raise
    out3 = store.persist_video_file(str(tmp / "missing.mp4"))
    check("missing source no-crash", out3 == str(tmp / "missing.mp4"), out3)

    # set_video_path direct
    store.set_video_path("C:/some/other.mp4")
    conn = sqlite3.connect(str(store._db_path(1)))
    row = conn.execute("SELECT video_path FROM projects WHERE id=1").fetchone()
    conn.close()
    check("set_video_path DB", row and row[0] == "C:/some/other.mp4", str(row))

    # media_dir creates
    md = store.media_dir(2)
    check("media_dir creates", md.is_dir() and md.name == "media", str(md))

    # ── 3. open_project returns persisted video_path ─────────────
    print("[3] open_project round-trip")
    store.create_project("Second", "https://x")
    store.set_video_path(str(expect))
    reopened = store.open_project(2)
    check("open_project video_path", reopened and reopened.video_path == str(expect),
          reopened.video_path if reopened else "none")

    print()
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
