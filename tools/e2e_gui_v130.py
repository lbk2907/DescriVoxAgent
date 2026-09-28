"""E2E GUI test for v1.3.0/v1.4.0 player features (hybrid pywinauto + win32).

Extends tools/e2e_gui_phase.py (launch/settings/url/process flow) with
the player + persistence features.

CRITICAL lesson from the v1.2.9 run, re-learned here: the app's UIA
provider goes NUMB intermittently (UIA Text/Button enumeration returns
few or stale elements while raw Win32 sees everything). The player
window is therefore driven ENTIRELY with raw Win32:
  - clicks:  BM_CLICK on child Button hwnds (same message a real mouse
    click produces; proven on wx dialogs in the 1.2.9 run)
  - reads:   GetWindowTextW over EnumChildWindows (wx StaticText texts
    like the subtitle overlay, time label, and status line)

v1.3.0 checks:
  - the physical video file was copied into the project media folder
    and the DB video_path points at it (survives temp cleanup)
  - a descriptions.srt sidecar was written next to it
  - the player auto-opened and AUTO-LOADED the project SRT: the status
    static reads "Subtitles loaded: N" immediately after auto-open
    (before any test interaction), and pressing Play renders a sidecar
    cue in the subtitle overlay static.
  - clicking "Load SRT..." opens the native file dialog, an external
    SRT loads ("Subtitles loaded: 3") and its cue renders in the
    overlay during playback.

v1.4.0 checks:
  - ONE Play/Pause toggle button (no separate Pause button): clicking
    Play starts playback, the same button then reads "Pause", clicking
    it pauses, clicking again resumes.
  - REAL audio in simulated mode (no VLC installed): an ffplay.exe
    process (parent = app PID) is alive while playing, gone while
    paused, alive again after resume.

Run:  python tools/e2e_gui_v130.py
"""
from __future__ import annotations

import json
import subprocess
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
PLAY_LABELS = {"Play", "Pause", "Main", "Jeda"}  # en + ms toggle labels


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
    from e2e_projects import media_dir_of, newest_db
    db = newest_db(PROJECTS_DIR)   # either project layout
    assert db, "no project db found"
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
    assert p.parent == media_dir_of(db), \
        f"not in this project's media folder: {vp}"
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


def _toggle_button_hwnd(hwnd: int) -> int:
    """Find the single Play/Pause toggle button (label is state-dependent,
    language-dependent: en Play/Pause, ms Main/Jeda)."""
    for child in phase.enum_children(hwnd):
        if phase._window_class(child) == "Button":
            txt = _norm(phase._window_title(child))
            if txt in PLAY_LABELS:
                return child
    raise RuntimeError("Play/Pause toggle button not found")


def press_play_toggle(hwnd: int) -> str:
    """BM_CLICK the toggle; returns the label it had before the click."""
    h = _toggle_button_hwnd(hwnd)
    label = _norm(phase._window_title(h))
    user32.SendMessageW(h, 0x00F5, 0, 0)  # BM_CLICK
    phase.log(f"clicked toggle (was '{label}')")
    return label


def ffplay_parent_pids() -> set[int]:
    """Parent PIDs of running ffplay.exe processes (PowerShell CIM)."""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='ffplay.exe'\" | "
         "ForEach-Object { $_.ParentProcessId }"],
        capture_output=True, text=True, timeout=25)
    pids: set[int] = set()
    for line in out.stdout.split():
        line = line.strip()
        if line.isdigit():
            pids.add(int(line))
    return pids


def wait_ffplay(alive: bool, timeout: float, what: str) -> None:
    deadline = time.time() + timeout
    last = False
    while time.time() < deadline:
        last = phase.APP_PID in ffplay_parent_pids()
        if last == alive:
            phase.log(f"{what} (ffplay running={last})")
            return
        time.sleep(0.6)
    raise RuntimeError(f"{what} FAILED: ffplay running={last}, "
                       f"expected {'alive' if alive else 'gone'}")


def step_player_t5(sidecar_texts: list[str]) -> None:
    """Auto-open + auto-load status + sidecar cue in overlay + REAL audio
    via ffplay + single Play/Pause toggle. All interaction raw Win32."""
    phase.log("== PLAYER t5: AUTO-OPEN + AUTO-LOAD + AUDIO + TOGGLE ==")
    hwnd = _player_hwnd()
    phase.log(f"player window: '{phase._window_title(hwnd)[:70]}'")

    # 1) DIRECT evidence of auto-load: status static right after the
    # player opened, before we touch anything.
    wait_win32_text(hwnd, lambda t: t.startswith("Subtitles loaded:"),
                    10.0, "auto-load status")
    phase.log("AUTOLOAD_STATUS_OK (direct evidence)")

    # 2) Single toggle button exists and NO separate pause button.
    btns = [_norm(phase._window_title(c))
            for c in phase.enum_children(hwnd)
            if phase._window_class(c) == "Button"]
    assert not any(b == "Pause" for b in btns), f"separate Pause button: {btns}"
    press_play_toggle(hwnd)  # Play -> starts (was 'Play' or 'Main')
    phase.log("TOGGLE_SINGLE_OK (no separate Pause button)")

    # 3) BEHAVIORAL evidence of auto-load: the overlay static must show
    # a sidecar cue (nothing else populated the cue list).
    def _is_sidecar_cue(t: str) -> bool:
        return any(t.startswith(txt[:30]) for txt in sidecar_texts)

    wait_win32_text(hwnd, _is_sidecar_cue, 30.0,
                    "sidecar cue in subtitle overlay")
    phase.log("AUTOLOAD_BEHAVIORAL_OK (sidecar cue rendered on Play)")

    # 4) v1.4.0: REAL audio while playing (ffplay child of the app).
    wait_ffplay(True, 10.0, "AUDIO_PLAY_OK")
    # 5) Same button now pauses -> sound stops (process gone).
    press_play_toggle(hwnd)
    wait_ffplay(False, 10.0, "AUDIO_PAUSE_OK")
    # 6) Same button again resumes -> sound returns.
    press_play_toggle(hwnd)
    wait_ffplay(True, 10.0, "AUDIO_RESUME_OK")
    # 7) Pause again before moving on.
    press_play_toggle(hwnd)
    wait_ffplay(False, 10.0, "AUDIO_STOPPED_FOR_T6_OK")
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

    phase.press_button(hwnd, "Stop")  # reset to 0; toggle label -> Play
    time.sleep(0.8)
    press_play_toggle(hwnd)
    wait_win32_text(hwnd, lambda t: "E2E EXT SUB" in t, 30.0,
                    "external cue in subtitle overlay")
    wait_ffplay(True, 10.0, "AUDIO_PLAYING_T6_OK")
    press_play_toggle(hwnd)
    wait_ffplay(False, 10.0, "AUDIO_PAUSED_T6_OK")
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
    wait_ffplay(False, 5.0, "AUDIO_CLEANUP_ON_CLOSE_OK")
    phase.log("player closed cleanly")


def main() -> int:
    from e2e_projects import ProjectsGuard
    guard = ProjectsGuard(PROJECTS_DIR)
    try:
        return _run()
    finally:
        guard.cleanup()   # only the project this run created


def _run() -> int:
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
