"""One real run of the shipped build, watched through NVDA.

Everything else in tools/ tests a layer. This drives the FROZEN app —
the exe a user actually receives — through a complete job with a real
AI call, and checks each stage two ways: what the files on disk say,
and what NVDA announced while it happened. A pipeline can finish
correctly and still be unusable to a blind user if it says nothing.

Needs NVDA running with the nvdaHttpBridge plugin (127.0.0.1:19281)
and a real provider key. It runs against an ISOLATED config directory
so the user's own settings.json is never written to.

    python tools/e2e_full_verify.py --clip <path-to-video>

Exits 0 only when every stage passed. Exit 2 means "could not verify"
— a missing bridge or missing build — which is deliberately distinct
from a failure.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# NVDA can speak anything (emoji included); a log redirected to a file
# is cp1252 on Windows and the first emoji killed a 15-minute run.
sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import safe_keys  # noqa: E402  (guards every keystroke; import first)

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e_projects import ProjectsGuard, all_dbs  # noqa: E402
BRIDGE = "http://127.0.0.1:19281"
APP_TITLE = "DescriVox Agent"

results: list[tuple[str, bool, str]] = []


def record(stage: str, ok: bool, detail: str = "") -> bool:
    mark = "OK  " if ok else "FAIL"
    print(f"  [{mark}] {stage}" + (f" — {detail}" if detail else ""),
          flush=True)
    results.append((stage, ok, detail))
    return ok


# ── NVDA bridge ──────────────────────────────────────────────────

def _bridge(path: str, timeout: float = 10.0) -> dict:
    with urllib.request.urlopen(f"{BRIDGE}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def bridge_ready() -> tuple[bool, str]:
    try:
        version = _bridge("/v1/version", timeout=5)
        data = version.get("data", version)
        nvda = (data.get("nvda") or {}).get("version", "?")
        return True, f"NVDA {nvda}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _completion_prefixes() -> list[str]:
    """The fixed start of the app's "processing complete" line, per language."""
    prefixes = []
    for f in (REPO / "src" / "omni_describer_custom" / "i18n" / "locales").glob("*.json"):
        text = json.loads(f.read_text(encoding="utf-8")).get(
            "status.processing_complete", "")
        head = text.split("{")[0].strip()
        if head:
            prefixes.append(head)
    return prefixes


def _locale_texts(key: str) -> list[str]:
    """One app text in every shipped language, without trailing dots."""
    out = []
    for f in (REPO / "src" / "omni_describer_custom" / "i18n" / "locales").glob("*.json"):
        text = json.loads(f.read_text(encoding="utf-8")).get(key, "")
        if text:
            out.append(text.rstrip(". "))
    return out


def _clip_seconds(clip: Path) -> float:
    ffprobe = REPO / "bin" / "ffprobe.exe"
    try:
        out = subprocess.run(
            [str(ffprobe), "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(clip)],
            capture_output=True, text=True, timeout=60).stdout
        return float(out.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def speech_items() -> list[dict]:
    data = _bridge("/v1/speech")
    return data.get("data", data).get("items", [])


def speech_mark() -> str:
    items = speech_items()
    return items[-1]["time"] if items else ""


def spoken_since(mark: str) -> list[str]:
    return [i["text"] for i in speech_items() if i.get("time", "") > mark]


def focus_now() -> dict:
    """The object NVDA currently reports as focused.

    The raw HTTP endpoint returns the object itself; only the bundled
    CLI wraps it in {"data": ...}. Asking for ["data"] unconditionally
    yielded {} every time, so every focus check compared against an
    empty name and the whole run tabbed past its target sixteen times
    reporting nothing found.
    """
    try:
        payload = _bridge("/v1/objects/focus")
        return payload.get("data", payload)
    except Exception:
        return {}


# ── Driving the app ──────────────────────────────────────────────

def launch(config_dir: Path):
    from pywinauto import Desktop
    exe = REPO / "dist" / "DescriVox" / "DescriVox.exe"
    if not exe.exists():
        print(f"No build at {exe}; run build.bat first")
        raise SystemExit(2)
    env = dict(os.environ)
    env["ODC_CONFIG_DIR"] = str(config_dir)
    # v1.9.6: projects in a sandbox too; ProjectsGuard deletes the
    # projects a run creates, which must never be the owner's folder.
    env["ODC_PROJECTS_DIR"] = str(config_dir / "projects")
    proc = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env)
    safe_keys.allow(proc.pid)
    desktop = Desktop(backend="uia")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            win = desktop.window(title_re=f".*{APP_TITLE}.*",
                                 visible_only=False)
            if win.exists() and win.is_visible():
                time.sleep(2.0)  # let the first paint settle
                return proc, win
        except Exception:
            pass
        time.sleep(1.0)
    proc.terminate()
    print("The app window never appeared")
    raise SystemExit(2)


def status_log(win) -> str:
    """The app's own Status Log pane — the ground truth for progress.

    More reliable than watching NVDA: speech includes whatever else is
    talking on the machine, and the app writes every phase here.
    """
    for edit in win.descendants(control_type="Edit"):
        try:
            if "status" not in (edit.element_info.name or "").lower():
                continue
            # get_value(), not window_text(): on a UIA Edit the latter
            # returns the control's NAME ("Status Log"), so every check
            # against it compared the label with itself and passed or
            # failed for the wrong reason.
            if hasattr(edit, "get_value"):
                return edit.get_value() or ""
            return edit.window_text()
        except Exception:
            continue
    return ""


def focus_and_activate(win, label: str,
                       max_tabs: int = 16) -> tuple[bool, str]:
    """Tab to a control, confirm it through NVDA, then press Enter.

    This is the journey the actual user takes, and it is the only one
    that proved reliable. Four alternatives were tried against the real
    app and three reported success while doing nothing:

      - the UIA wrapper's invoke(): wx buttons do not implement it;
      - click_input() with the app in the background: the click landed
        on whatever was on top;
      - click_input() with the app in front: the Open button measures
        FIFTEEN pixels wide here (L1275..R1290) because the preset
        combo box next to it takes the row, so the click reached the
        combo instead and NVDA kept announcing "Prompt preset ...".

    Tabbing depends on no geometry, and NVDA is asked what actually has
    focus at every step, so a miss fails loudly instead of silently.
    """
    from pywinauto.keyboard import send_keys
    try:
        win.set_focus()
        time.sleep(0.8)
    except Exception:
        pass
    send_keys("{ESC}")
    time.sleep(0.4)

    seen: list[str] = []
    for _ in range(max_tabs):
        send_keys("{TAB}")
        time.sleep(0.7)
        name = (focus_now().get("name") or "").strip()
        seen.append(name)
        if name.lower().startswith(label.lower()):
            send_keys("{ENTER}")
            return True, f"{name} (NVDA confirmed focus)"
    return False, f"never reached '{label}'; tabbed through {seen}"


def answer_file_dialog(path: Path, app_pid: int,
                       timeout: float = 30.0) -> tuple[bool, str]:
    """Put a path into the file dialog the app just opened.

    Type it. Focus already sits in the File name box when the dialog
    opens, which is how a person does it and the only approach of
    three that worked here:

      - guessing dialog titles missed the real one ("Select File...");
      - Alt+N did not reach the field;
      - WM_SETTEXT hit the wrong control, because the modern shell
        dialog carries 68 Edit windows (address bar, search, ...).

    Each of those reported success while choosing no file at all.
    """
    import win32gui
    import win32process
    from pywinauto.keyboard import send_keys

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found: list[tuple[int, str]] = []

        def visit(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            try:
                if win32gui.GetClassName(hwnd) != "#32770":
                    return
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid == app_pid:
                    found.append((hwnd, win32gui.GetWindowText(hwnd)))  # noqa: B023 (used in this iteration only)
            except Exception:
                pass

        win32gui.EnumWindows(visit, None)
        if not found:
            time.sleep(0.5)
            continue

        hwnd, title = found[0]
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.6)
        send_keys(str(path), with_spaces=True, pause=0.01)
        time.sleep(0.8)
        send_keys("{ENTER}")
        time.sleep(2.0)
        still_open = win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd)
        if still_open:
            return False, f"'{title}' did not close"
        return True, title
    return False, "no dialog appeared"


# ── Checking the result ──────────────────────────────────────────

def read_project(projects_dir: Path) -> dict:
    """Newest project: its row plus its descriptions."""
    # Both layouts: "project_N.db" (before v1.7.6) and "<name> (N)/project.db".
    dbs = all_dbs(projects_dir)   # either project layout
    if not dbs:
        return {}
    conn = sqlite3.connect(str(dbs[-1]))
    conn.row_factory = sqlite3.Row
    try:
        project = dict(conn.execute("SELECT * FROM projects").fetchone())
        rows = conn.execute(
            "SELECT start_time, end_time, text FROM descriptions "
            "ORDER BY start_time").fetchall()
        project["descriptions"] = [dict(r) for r in rows]
        project["_db"] = str(dbs[-1])
        return project
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", required=True, help="video to describe")
    parser.add_argument("--config", default="",
                        help="isolated config dir (must hold settings.json)")
    parser.add_argument("--timeout", type=float, default=900.0,
                        help="seconds to wait for the job")
    args = parser.parse_args()

    clip = Path(args.clip).resolve()
    if not clip.is_file():
        print(f"No clip at {clip}")
        return 2
    config_dir = Path(args.config or (Path(os.environ["TEMP"]) / "odc_realrun"))
    if not (config_dir / "settings.json").exists():
        print(f"No settings.json in {config_dir}; the run needs a real key")
        return 2
    # v1.9.6: projects go to a sandbox folder (ODC_PROJECTS_DIR, set in
    # launch()); this watches the same folder.
    projects_dir = config_dir / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    ready, detail = bridge_ready()
    if not ready:
        print(f"NVDA HTTP Bridge not answering: {detail}")
        print("Refusing to report a pass without it.")
        return 2
    print(f"Bridge up: {detail}\n")

    print("== LAUNCH ==", flush=True)
    mark = speech_mark()
    guard = ProjectsGuard(projects_dir)
    proc, win = launch(config_dir)
    record("frozen app started", True, win.window_text()[:50])
    startup_speech = spoken_since(mark)
    record("NVDA spoke at startup", bool(startup_speech),
           (startup_speech[0][:60] if startup_speech else "silence"))

    try:
        print("\n== PICK THE VIDEO ==", flush=True)
        mark = speech_mark()
        ok, detail = focus_and_activate(win, "Local Video")
        record("Local Video File clicked", ok, detail)
        ok, detail = answer_file_dialog(clip, proc.pid)
        record("file dialog answered", ok, detail)
        time.sleep(2.0)
        # The click and the dialog can both "succeed" without a file
        # being chosen. The app's own Status Log is the only proof.
        log_text = status_log(win)
        record("the app recorded the file as selected",
               clip.name in log_text,
               log_text.strip().splitlines()[-1][:70] if log_text else "empty")
        picked = spoken_since(mark)
        record("NVDA followed the file choice", bool(picked),
               " | ".join(picked)[:70])

        print("\n== START THE JOB ==", flush=True)
        mark = speech_mark()
        before = status_log(win)
        ok, detail = focus_and_activate(win, "Open")
        record("Open clicked", ok, detail)
        time.sleep(6.0)
        after = status_log(win)
        record("the job actually started", after != before,
               after.strip().splitlines()[-1][:70] if after else "no change")

        print("\n== WATCH IT WORK ==", flush=True)
        deadline = time.monotonic() + args.timeout
        phases: list[str] = []
        last_report = 0.0
        while time.monotonic() < deadline:
            fresh = spoken_since(mark)
            if fresh:
                mark = speech_mark()
                for line in fresh:
                    phases.append(line)
            project = read_project(projects_dir) if projects_dir.exists() else {}
            if project.get("descriptions"):
                break
            if time.monotonic() - last_report > 25:
                last_report = time.monotonic()
                latest = phases[-1][:50] if phases else "(nothing)"
                app_says = status_log(win).strip().splitlines()
                print(f"    ... {int(deadline - time.monotonic())}s left | "
                      f"app: {app_says[-1][:56] if app_says else '-'} | "
                      f"NVDA: {latest}", flush=True)
            time.sleep(2.0)

        project = read_project(projects_dir) if projects_dir.exists() else {}
        descriptions = project.get("descriptions", [])
        record("the job produced descriptions", bool(descriptions),
               f"{len(descriptions)} cues")
        if descriptions:
            first = descriptions[0]
            record("descriptions carry timestamps and text",
                   first["text"].strip() != "" and first["end_time"] > 0,
                   f'{first["start_time"]:.1f}s: {first["text"][:50]}')
            words = [len(d["text"].split()) for d in descriptions]
            longest = max(words)
            # The whole video must be described, not its first part.
            # v1.8.2 changed how a part's length is measured; a wrong
            # length silently drops every cue past it (pitfall 61).
            length = _clip_seconds(clip)
            starts = sorted(float(d["start_time"]) for d in descriptions)
            edges = [0.0] + starts + [length]
            gap = max(b - a for a, b in zip(edges, edges[1:], strict=False))
            record("descriptions cover the whole video",
                   length > 0 and starts[-1] >= length - 90 and gap <= 120,
                   f"last cue {starts[-1]:.0f}s of {length:.0f}s, "
                   f"widest gap {gap:.0f}s")
            # Owner's decision (28 Sep 2026): long cues are left as the
            # model writes them; the narration hold covers them. Reported,
            # not failed — models do not obey length requests (pitfall 14).
            over = sum(1 for w in words if w > 20)
            print(f"  [NOTE] cue length: longest {longest} words, "
                  f"{over} of {len(words)} over 20 (AD guideline is 12)",
                  flush=True)
        record("the project stored the video", bool(project.get("video_path")),
               Path(project.get("video_path", "")).name)

        print("\n== WHAT NVDA ANNOUNCED ==", flush=True)
        unique: list[str] = []
        for line in phases:
            if line not in unique:
                unique.append(line)
        for line in unique[-14:]:
            print(f"    {line[:88]}", flush=True)
        record("NVDA narrated the work", len(unique) >= 3,
               f"{len(unique)} distinct announcements")
        # v1.8.4: a change of phase must be SAID, not only shown in a
        # dialog whose focus stays on Cancel (pitfall 65). The app's own
        # "watching" line, in whichever language it runs.
        watching = [line for line in unique
                    if any(w in line for w in _locale_texts("video.phase_waiting"))]
        record("NVDA announced the AI's wait by itself", bool(watching),
               watching[0][:70] if watching else "never said")

        # A blind user must hear that it finished, not discover it.
        # Matched against the app's OWN completion text, in every
        # language it ships. Keywords matched other programs: on 29 Sep
        # 2026 "Indonesian" (TeamTalk, read by NVDA meanwhile) contains
        # "done", and the check passed on speech that was not the app's.
        finished = [line for line in unique
                    if any(p in line for p in _completion_prefixes())]
        record("completion was announced, not silent", bool(finished),
               finished[-1][:60] if finished else "nothing said about the end")

        print("\n== ARTEFACTS ON DISK ==", flush=True)
        if project.get("_db"):
            db_file = Path(project["_db"])
            media = (db_file.parent if db_file.name == "project.db"
                     else db_file.with_suffix("")) / "media"
            if media.is_dir():
                for item in sorted(media.iterdir()):
                    print(f"    {item.name}: {item.stat().st_size} bytes",
                          flush=True)
                srt = media / "descriptions.srt"
                record("SRT written beside the video", srt.exists(),
                       f"{srt.stat().st_size} bytes" if srt.exists() else "")
                # v1.6.7's retry saving: the compressed upload copy must
                # still be here. A second cleanup used to delete it at
                # the end of every job in full-video mode.
                cached = list(media.glob("upload_*.mp4"))
                # Only GLM compresses before upload, and only a file over
                # its 50 MB limit (smaller ones are sent or split as they
                # are); Gemini sends the original. Otherwise there is no
                # copy to survive.
                settings = json.loads((config_dir / "settings.json")
                                      .read_text(encoding="utf-8"))
                provider = settings.get("ai", {}).get("default_provider")
                # A video longer than one part is SPLIT, not compressed;
                # split parts are temporary and there is no copy to keep.
                chunk = float(settings.get("general", {}).get(
                    "chunk_seconds", 600) or 600)
                if provider == "glm" and clip.stat().st_size > 50 * 1024 * 1024                         and _clip_seconds(clip) <= chunk + 1.0:
                    record("the compressed upload copy survived the job",
                           bool(cached),
                           f"{cached[0].name} "
                           f"({cached[0].stat().st_size/1e6:.1f} MB)"
                           if cached else "deleted by the parts cleanup")
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=15)   # its files must be closed first
        except Exception:
            pass
        guard.cleanup()

    print("\n" + "=" * 60)
    failed = [s for s, ok, _ in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} stages passed")
    if failed:
        print("FAILED: " + "; ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
