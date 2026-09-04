"""E2E GUI test for v1.3.0 features (hybrid pywinauto + win32).

Extends tools/e2e_gui_phase.py (launch/settings/url/process flow) with
the v1.3.0 player + persistence features.

CRITICAL lesson from the v1.2.9 run, re-learned here: the app's UIA
provider goes NUMB intermittently (UIA Text/Button enumeration returns
few or stale elements while raw Win32 sees everything). The player
window is therefore driven ENTIRELY with raw Win32:
  - clicks:  BM_CLICK on child Button hwnds (same message a real mouse
    click produces; proven on wx dialogs in the 1.2.9 run)
  - reads:   GetWindowTextW over EnumChildWindows (wx StaticText texts
    like the subtitle overlay, time label, and status line)

t5: process a YouTube video through the REAL GUI, then verify:
  - the physical video file was copied into the project media folder
    and the DB video_path points at it (survives temp cleanup)
  - a descriptions.srt sidecar was written next to it
  - the player auto-opened and AUTO-LOADED the project SRT: the status
    static reads "Subtitles loaded: N" immediately after auto-open
    (before any test interaction), and pressing Play renders a sidecar
    cue in the subtitle overlay static.

t6: through the REAL GUI, click "Load SRT...", pick an external SRT in
  the native file dialog, verify "Subtitles loaded: 3", then Stop+Play
  and verify the overlay shows the external cue.

Run:  python tools/e2e_gui_v130.py
"""
from __future__ import annotations

import ctypes
import json
import sys
import time
from pathlib import Path

# NOTE: do NOT re-wrap sys.stdout here; e2e_gui_phase wraps it at import
# and a second wrapper would close the first one on GC (I/O on closed file).

REPO = Path(r"C:\Users\USER\Documents\omni-describer-custom")
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "src"))

import e2e_gui_phase as phase  # reuse the proven helpers

BASE = Path.home() / "Documents" / "OmniDescriber"
PROJECTS_DIR = BASE / "projects"
EXT_SRT = BASE / "e2e_ext_srt.srt"
EXT_CUES = [
    (0.5, 4.0, "E2E EXT SUB ONE"),
    (4.5, 8.0, "E2E EXT SUB TWO"),
    (8.5, 12.0, "E2E EXT SUB THREE"),
]

user32 = phase.user32


def _norm(s: str) -> str:
    return " ".join((s or "").split())


def win32_child_texts(frame_hwnd: int, cls: str | None = None) -> list[str]:
    """Visible texts of child windows (default: Static), via GetWindowTextW."""
    out = []
    for child in phase.enum_children(frame_hwnd):
        if not user32.IsWindowVisible(child):
            continue
        if cls and phase._window_class(child) != cls:
            continue
        t = _norm(phase._window_title(child))
        if t:
            out.append(t)
    return out


def wait_win32_text(frame_hwnd: int, predicate, timeout: float,
                    what: str) -> str:
    deadline = time.time() + timeout
    seen_last: list[str] = []
    while time.time() < deadline:
        texts = win32_child_texts(frame_hwnd)
        seen_last = texts
        for t in texts:
            if predicate(t):
                phase.log(f"found {what}: {t[:80]!r}")
                return t
        time.sleep(0.6)
    phase.log(f"{what} not seen; statics at timeout: {seen_last!r}")
    raise RuntimeError(f"{what} not seen within {timeout}s")


def list_app_dialogs() -> list[str]:
    out = []
    for hwnd in phase.enum_top_windows():
        if (user32.IsWindowVisible(hwnd)
                and phase._pid_of(hwnd) == phase.APP_PID
                and phase._window_class(hwnd) == "#32770"):
            out.append(phase._window_title(hwnd))
    return out


def click_until_dialog(button_label: str, dialog_title: str,
                       attempts: int = 3, wait: float = 8.0):
    """Click a main-window button (UIA-proven path) and wait for the
    dialog it should open; retries with escalating waits."""
    last_err = None
    for i in range(1, attempts + 1):
        top = phase.find_main_uia()
        top.set_focus()
        time.sleep(1.0 + i)
        phase.button_by_label(top, button_label).click_input()
        phase.log(f"clicked '{button_label}' (attempt {i})")
        try:
            return phase.find_dialog_win32(dialog_title, timeout=wait)
        except RuntimeError as e:
            last_err = e
            phase.log(f"dialog '{dialog_title}' not seen; "
                      f"other dialogs: {list_app_dialogs() or 'none'}")
    raise RuntimeError(
        f"dialog '{dialog_title}' never appeared: {last_err}")


def step_youtube() -> None:
    phase.log("== YOUTUBE URL (via real GUI) ==")
    ted = click_until_dialog("YouTube Video URL", "YouTube Video URL")
    time.sleep(0.5)
    phase.set_edit_text(ted, phase.URL)
    time.sleep(0.4)
    phase.press_button(ted, "OK")
    time.sleep(0.5)
    phase.log("URL entered via TextEntryDialog")


def _ts(seconds: float) -> str:
    """Format seconds as SRT timestamp HH:MM:SS,mmm."""
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def step_verify_persistence() -> tuple[Path, list[str]]:
    """DB video_path must now be a REAL file inside the project folder.
    Also returns the sidecar cue texts (used as the t5 overlay oracle)."""
    phase.log("== VERIFY v1.3.0 PERSISTENCE ==")
    dbs = sorted(PROJECTS_DIR.glob("*.db"), key=lambda p: p.stat().st_mtime)
    assert dbs, "no project db found"
    db = dbs[-1]
    import sqlite3
    conn = sqlite3.connect(str(db))
    name, vp = conn.execute(
        "SELECT name, video_path FROM projects ORDER BY id DESC LIMIT 1"
    ).fetchone()
    n = conn.execute("SELECT COUNT(*) FROM descriptions").fetchone()[0]
    conn.close()
    phase.log(f"db={db.name} project={name[:40]!r} descs={n} video_path={vp}")
    assert n >= 1, "no descriptions"
    assert vp, "video_path empty"
    p = Path(vp)
    assert p.exists(), f"persisted video missing: {vp}"
    assert any(s.startswith("project_") for s in p.parts), \
        f"not in project dir: {vp}"
    assert "media" in {seg.lower() for seg in p.parts}, \
        f"not in media dir: {vp}"
    assert p.stat().st_size > 0, "persisted video is empty"
    media = p.parent
    srt = media / "descriptions.srt"
    assert srt.exists(), f"SRT sidecar missing: {srt}"
    srt_text = srt.read_text(encoding="utf-8")
    assert "-->" in srt_text, "SRT sidecar has no timestamps"
    from omni_describer_custom.core.timeline_io import parse_srt
    cues = parse_srt(srt)
    texts = [_norm(c.text) for c in cues if _norm(c.text)]
    assert texts, "sidecar has no cue texts"
    phase.log(f"persisted video: {p.name} ({p.stat().st_size} bytes), "
              f"srt sidecar: {srt.name} ({len(srt_text)} bytes, "
              f"{len(texts)} cues)")
    phase.log("PERSIST_OK")
    return p, texts


def _player_hwnd() -> int:
    return phase.find_window_win32("Described Video Player", timeout=25)


def step_player_t5(sidecar_texts: list[str]) -> None:
    """Auto-open + auto-load status + sidecar cue in overlay on Play.
    All interaction raw Win32 (UIA numb on this app)."""
    phase.log("== PLAYER t5: AUTO-OPEN + AUTO-LOAD + PLAY ==")
    hwnd = _player_hwnd()
    phase.log(f"player window: '{phase._window_title(hwnd)[:70]}'")

    # 1) DIRECT evidence of auto-load: status static right after the
    # player opened, before we touch anything.
    wait_win32_text(hwnd, lambda t: t.startswith("Subtitles loaded:"),
                    10.0, "auto-load status")
    phase.log("AUTOLOAD_STATUS_OK (direct evidence)")

    # 2) BEHAVIORAL evidence: Stop+Play from 0; the overlay static must
    # show a sidecar cue (nothing else populated the cue list).
    phase.press_button(hwnd, "Stop")
    time.sleep(0.8)
    phase.press_button(hwnd, "Play")
    phase.log("Stop+Play clicked (win32 BM_CLICK)")

    def _is_sidecar_cue(t: str) -> bool:
        return any(t.startswith(txt[:30]) for txt in sidecar_texts)

    wait_win32_text(hwnd, _is_sidecar_cue, 30.0,
                    "sidecar cue in subtitle overlay")
    phase.log("AUTOLOAD_BEHAVIORAL_OK (sidecar cue rendered on Play)")
    phase.press_button(hwnd, "Pause")
    phase.log("PLAYER_T5_OK")


def step_player_t6() -> None:
    """Load SRT via the REAL file dialog; overlay shows external cue."""
    phase.log("== PLAYER t6: LOAD SRT VIA FILE DIALOG ==")
    lines = []
    for i, (a, b, txt) in enumerate(EXT_CUES, 1):
        lines += [str(i), f"{_ts(a)} --> {_ts(b)}", txt, ""]
    EXT_SRT.write_text("\n".join(lines), encoding="utf-8")
    phase.log(f"external srt written: {EXT_SRT} ({len(EXT_CUES)} cues)")

    hwnd = _player_hwnd()
    phase.press_button(hwnd, "Load SRT...")
    fd = phase.find_dialog_win32("Load SRT...", timeout=20)
    time.sleep(0.6)
    phase.set_edit_text(fd, str(EXT_SRT))
    time.sleep(0.4)
    phase.press_button(fd, "Open")
    time.sleep(1.0)
    wait_win32_text(hwnd, lambda t: t.startswith("Subtitles loaded: 3"),
                    10.0, "external load status")
    phase.log("LOAD_SRT_DIALOG_OK (3 cues)")

    phase.press_button(hwnd, "Stop")
    time.sleep(0.8)
    phase.press_button(hwnd, "Play")
    phase.log("Stop+Play clicked for external cues")
    wait_win32_text(hwnd, lambda t: "E2E EXT SUB" in t, 30.0,
                    "external cue in subtitle overlay")
    phase.press_button(hwnd, "Pause")
    phase.log("PLAYER_T6_OK")


def step_close_player() -> None:
    phase.log("== CLOSE PLAYER ==")
    hwnd = _player_hwnd()
    user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
    time.sleep(2.0)
    for h in phase.enum_top_windows():
        if (phase._pid_of(h) == phase.APP_PID
                and "Described Video Player" in phase._window_title(h)):
            raise RuntimeError("player window still open")
    phase.log("player closed cleanly")


def main() -> int:
    top = phase.step_launch()
    time.sleep(3.0)  # let startup TTS init / list refresh settle

    # Settings already persisted from the previous full E2E run; only
    # drive the settings GUI when they are missing/wrong.
    data = json.loads(phase.SETTINGS_JSON.read_text(encoding="utf-8"))
    prov = data.get("ai", {}).get("default_provider")
    mode = data.get("ai", {}).get("video_mode")
    if prov == "glm" and mode == "full":
        phase.log("settings already glm/full — skip settings GUI")
    else:
        phase.step_settings(top)

    step_youtube()
    phase.step_process()
    _, sidecar_texts = step_verify_persistence()
    step_player_t5(sidecar_texts)
    step_player_t6()
    step_close_player()
    phase.step_exit()
    phase.log("E2E_V130_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
