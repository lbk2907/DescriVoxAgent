"""Check what NVDA actually says about this app's controls.

Every accessibility check in this repo until now read the source and
concluded. That is how v1.5.4 shipped three controls whose NVDA name
was set with SetLabel(): the code looked right, the control lost its
state, and the fault reached a real user (AGENTS.md pitfall 12).

This tabs through the real window and asks NVDA what it announced,
through the local NVDA HTTP Bridge at 127.0.0.1:19281. It reads; it
changes nothing about NVDA.

    python tools/nvda_accessibility_check.py            # run from source
    python tools/nvda_accessibility_check.py --frozen   # the built exe

Requires NVDA running with the Bridge plugin loaded. Without it the
script says so and exits 2, rather than passing quietly and pretending
the app was verified.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable
BRIDGE = "http://127.0.0.1:19281"
APP_TITLE_HINT = "Omni Describer"

# Controls whose announcement carries no information: a name that is
# empty, or that is just the role over again, leaves a blind user
# tabbing into something unidentifiable.
_USELESS_NAMES = {"", "pane", "panel", "window", "form", "document"}


def _get(path: str, timeout: float = 10.0) -> dict:
    with urllib.request.urlopen(f"{BRIDGE}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def bridge_alive() -> tuple[bool, str]:
    try:
        _get("/health", timeout=5)
        version = _get("/v1/version", timeout=5)
        return True, json.dumps(version.get("version", version))[:120]
    except urllib.error.URLError as e:
        return False, str(e)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def speech_since(marker_time: str) -> list[str]:
    """What NVDA has said since a timestamp, oldest first."""
    data = _get("/v1/speech")
    items = data.get("items", data.get("data", {}).get("items", []))
    return [i["text"] for i in items if i.get("time", "") > marker_time]


def speech_now() -> str:
    """Timestamp of the newest utterance, used as a marker."""
    data = _get("/v1/speech")
    items = data.get("items", data.get("data", {}).get("items", []))
    return items[-1]["time"] if items else ""


def focus_object() -> dict:
    data = _get("/v1/objects/focus")
    return data.get("data", data)


def launch(frozen: bool):
    from pywinauto import Desktop
    if frozen:
        exe = REPO / "dist" / "OmniDescriber" / "OmniDescriber.exe"
        if not exe.exists():
            raise SystemExit(f"no build at {exe}; run build.bat first")
        proc = subprocess.Popen([str(exe)], cwd=str(exe.parent))
    else:
        log_file = open(REPO / "_a11y_app_log.txt", "w", encoding="utf-8")
        proc = subprocess.Popen([PY, "main.py"], cwd=str(REPO),
                                stdout=log_file, stderr=log_file)
    desktop = Desktop(backend="uia")
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            win = desktop.window(title_re=f".*{APP_TITLE_HINT}.*",
                                 visible_only=False)
            if win.exists() and win.is_visible():
                return proc, win
        except Exception:
            pass
        time.sleep(1.0)
    proc.terminate()
    raise SystemExit("the app window never appeared")


def walk_controls(win, steps: int) -> list[dict]:
    """Tab through the window, recording focus and what NVDA said."""
    from pywinauto.keyboard import send_keys
    win.set_focus()
    time.sleep(1.5)
    seen: list[dict] = []
    for index in range(steps):
        marker = speech_now()
        send_keys("{TAB}")
        # NVDA speaks asynchronously; without this the history is read
        # before the announcement lands and every control looks silent.
        time.sleep(0.9)
        try:
            obj = focus_object()
        except Exception as e:
            obj = {"error": str(e)}
        spoken = speech_since(marker)
        seen.append({
            "step": index + 1,
            "name": obj.get("name") or "",
            "role": (obj.get("role") or {}).get("display", ""),
            "spoken": spoken,
        })
    return seen


def _check_pitfall_12(seen: list[dict]) -> list[str]:
    """Guard the two controls SetLabel() broke in v1.5.4.

    That bug shipped: the preset combo lost its selection, so Open
    answered "Please select a prompt preset", and the prompt box held
    its own label, which went to the AI as if the user had typed it.
    Reading the source could not tell the difference. NVDA can.

    Heard on 22 Sep 2026 with the fix in place:
      combo:  "... combo box default collapsed"   <- a preset IS chosen
      prompt: "... edit multi line You are writing audio description"
    """
    found: list[str] = []
    combo = next((e for e in seen if e["role"] == "combo box"
                  and "preset" in e["name"].lower()), None)
    if combo is None:
        found.append("the prompt preset combo box was never reached — "
                     "raise --steps, or it has lost its accessible name")
    else:
        said = " ".join(combo["spoken"]).lower()
        # NVDA reads a combo box as "<name> combo box <value> collapsed".
        # With nothing selected there is no value between the two.
        if "combo box collapsed" in said or "combo box  collapsed" in said:
            found.append(
                "the preset combo announces NO selected value — this is "
                "the v1.5.4 SetLabel regression; Open will refuse to run")

    prompt = next((e for e in seen if e["role"] == "edit"
                   and "prompt to send" in e["name"].lower()), None)
    if prompt is None:
        found.append("the prompt edit box was never reached — raise "
                     "--steps, or it has lost its accessible name")
    else:
        said = " ".join(prompt["spoken"])
        label = prompt["name"].rstrip(":").strip()
        body = said.split("multi line", 1)[-1].strip()
        if not body:
            found.append("the prompt box is empty — no preset text was "
                         "loaded, so Open would send nothing")
        elif label and body.startswith(label):
            found.append(
                f"the prompt box contains its own label ({label!r}) — "
                f"SetLabel on a TextCtrl again; this text is sent to the "
                f"AI as user notes")
    return found


def report(seen: list[dict]) -> int:
    problems: list[str] = []
    print(f"\n{'#':>3}  {'role':<14} {'name':<34} spoken by NVDA")
    print("-" * 100)
    for entry in seen:
        spoken = " | ".join(entry["spoken"]) or "(silence)"
        print(f"{entry['step']:>3}  {entry['role']:<14} "
              f"{entry['name'][:33]:<34} {spoken[:44]}")

        name = (entry["name"] or "").strip().lower()
        if name in _USELESS_NAMES:
            problems.append(
                f"step {entry['step']}: a {entry['role'] or 'control'} with "
                f"no usable name — NVDA cannot say what it is")
        if not entry["spoken"]:
            problems.append(
                f"step {entry['step']}: NVDA said nothing when "
                f"'{entry['name']}' took focus")
        # Pitfall 12: SetLabel() on a TextCtrl replaces its CONTENTS
        # with the label, so the control announces its own label as if
        # it were the user's text.
        for said in entry["spoken"]:
            if entry["name"] and said.strip() == entry["name"].strip() and \
                    entry["role"] == "edit":
                problems.append(
                    f"step {entry['step']}: the edit box reads back its own "
                    f"label ('{entry['name']}') as content — SetLabel on a "
                    f"TextCtrl again?")

    problems += _check_pitfall_12(seen)

    print("-" * 100)
    if problems:
        print(f"\n{len(problems)} PROBLEM(S):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"\nOK: {len(seen)} controls, every one named and announced.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen", action="store_true",
                        help="drive dist/OmniDescriber/OmniDescriber.exe")
    parser.add_argument("--steps", type=int, default=14,
                        help="how many Tab presses to record")
    args = parser.parse_args()

    alive, detail = bridge_alive()
    if not alive:
        print(f"NVDA HTTP Bridge is not answering on {BRIDGE}: {detail}")
        print("Start NVDA with the nvdaHttpBridge plugin loaded, then "
              "run this again. Refusing to report a pass without it.")
        return 2
    print(f"Bridge up: {detail}")

    proc, win = launch(args.frozen)
    try:
        seen = walk_controls(win, args.steps)
        return report(seen)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
