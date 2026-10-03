"""Regression round 66: owner, 3 Oct 2026.

"Zip the source code only for my backup - no exe, no release files -
and do it automatically on every release." build.bat now runs
tools/make_source_zip.py, which zips the committed files (git archive)
and refuses a zip holding anything that is not source.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import subprocess
import sys
import tempfile
import traceback
import zipfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "tools")

import make_source_zip as msz  # noqa: E402

results: list[tuple[str, bool]] = []
TMP = Path(tempfile.mkdtemp(prefix="odc_t66_"))


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def _zip(name, files):
    path = TMP / name
    with zipfile.ZipFile(path, "w") as z:
        for arc, data in files.items():
            z.writestr(arc, data)
    return path


def test_clean_source_passes():
    path = _zip("ok.zip", {"p/main.py": "print('hi')\n", "p/README.md": "# Hi\n"})
    assert msz.problems(path) == [], msz.problems(path)


def test_exe_and_build_output_are_refused():
    path = _zip("bad.zip", {"p/DescriVox.exe": b"MZ\x00\x00",
                            "p/dist/DescriVox/readme.txt": "x",
                            "p/settings.json": "{}"})
    found = msz.problems(path)
    assert len(found) == 3, found


def test_binary_and_keys_are_refused():
    key = "sk-or-v1-" + "a" * 40
    path = _zip("bad2.zip", {"p/blob.txt": b"abc\x00def",
                             "p/conf.py": f"KEY = '{key}'\n"})
    found = msz.problems(path)
    assert any("binary" in f for f in found) and any("API key" in f for f in found), found


def test_the_real_tool_makes_a_clean_zip():
    out = TMP / "real"
    run = subprocess.run([sys.executable, "tools/make_source_zip.py", "--out", str(out)],
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0 and "SOURCE_ZIP_OK" in run.stdout, run.stdout + run.stderr
    made = list(out.glob("DescriVox-Agent-source-v*.zip"))
    assert len(made) == 1 and msz.problems(made[0]) == []


def test_build_runs_it():
    bat = Path("build.bat").read_text(encoding="utf-8")
    assert r"%PY% tools\make_source_zip.py" in bat
    assert bat.index("make_source_zip") < bat.index("echo BUILD_ALL_OK")


def main() -> int:
    check("clean source passes", test_clean_source_passes)
    check("exe, build output and settings are refused", test_exe_and_build_output_are_refused)
    check("binary files and API keys are refused", test_binary_and_keys_are_refused)
    check("the real tool makes a clean zip", test_the_real_tool_makes_a_clean_zip)
    check("build.bat runs it before BUILD_ALL_OK", test_build_runs_it)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
