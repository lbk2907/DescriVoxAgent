"""v1.7.3 real run: the windowed build opened a console window for ffmpeg.

A windowed parent (pythonw, like the frozen exe) starts a console child.
The child reports whether it got a console WINDOW. With no_console
installed it must not; without it, it does — proving the test can fail.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYW = str(Path(sys.executable).with_name("pythonw.exe"))
CHILD = "import ctypes; print(ctypes.windll.kernel32.GetConsoleWindow())"
PARENT = (
    "import subprocess, sys\n"
    "sys.path.insert(0, {src!r})\n"
    "if {install}:\n"
    "    from omni_describer_custom.core.no_console import install; install()\n"
    "out = subprocess.run([{py!r}, '-c', {child!r}], capture_output=True,"
    " text=True).stdout.strip()\n"
    "open({out!r}, 'w').write(out)\n"
)


def child_window(install: bool) -> int:
    out = Path(os.environ.get("TEMP", ".")) / f"odc_noconsole_{int(install)}.txt"
    out.unlink(missing_ok=True)
    code = PARENT.format(src=str(REPO / "src"), install=install,
                         py=sys.executable, child=CHILD, out=str(out))
    subprocess.run([PYW, "-c", code], timeout=60)
    return int(out.read_text().strip() or "0")


def main() -> int:
    if sys.platform != "win32":
        print("SKIP: Windows only")
        return 0
    without = child_window(False)
    with_fix = child_window(True)
    print(f"console window without fix: {without}, with fix: {with_fix}")
    ok = without != 0 and with_fix == 0
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
