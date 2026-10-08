# Contributing to DescriVox Agent

Thank you for wanting to contribute! This is the short version; the full orientation is in
[docs/developer-guide.md](docs/developer-guide.md).

## 1. Read first (required)

- **[AGENTS.md](AGENTS.md)** — the rules for any person or coding agent changing this code,
  with the numbered pitfalls that caused real bugs.
- **[docs/pitfalls.md](docs/pitfalls.md)** — the lessons from real bugs, by number. Code
  comments refer to these numbers; never renumber them.
- **[docs/plan.md](docs/plan.md)** — the current state and direction of the project, and
  [docs/checklist.md](docs/checklist.md) for open work.

## 2. Set up

```bat
git clone https://github.com/lbk2907/DescriVoxAgent
cd DescriVoxAgent
py -3.13 -m venv .venv
.venv\Scripts\pip install -e .[dev]
python tools\fetch_binaries.py
```

Requirements: **Windows**, Python 3.11+ (the gate is tested on 3.13). The external binaries
(ffmpeg, ffprobe, ffplay, yt-dlp) are fetched into `bin\` by `tools\fetch_binaries.py` and
checked against pinned SHA-256 hashes. In code, find them with `find_tool("ffmpeg")`
(`src/omni_describer_custom/core/tools.py`) — never hard-code a path.

The app is wxPython and screen-reader first: every UI change must stay fully usable with
NVDA.

## 3. Running the tests (the GATE — must pass before every commit)

This repository does NOT use ordinary pytest-style tests. Each `tests/test_*.py` is a
**standalone program** that runs its own suite and exits with a code (0 = pass).

Three equivalent ways:

```bat
rem 1. The full gate, as for a release (authoritative):
run_gate.bat

rem 2. The full gate through pytest (conftest bridge, one item per script):
py -3.13 -m pytest tests

rem 3. One script, while developing:
py -3.13 -m pytest tests\test_fixes65.py
rem    or run the script directly:
py -3.13 tests\test_fixes65.py
```

- The full gate takes about 12 minutes (real GUI, real video, some network).
- GitHub CI runs only light checks (ruff, compile, tests without a GUI); it does NOT
  replace the full local gate.
- Adding a test: copy the pattern of an existing file. Import `isolate` FIRST (pitfall 19 —
  a test must never touch a real user's settings or projects), end with
  `RESULT: N passed, M failed` and the exit code, and add the script to `run_gate.bat`.
- Do not change `python_files` in `pyproject.toml` or remove `tests/conftest.py` — pytest
  would import the scripts and run them at import time.

## 4. Code conventions

- Comments and commit messages in English, short, explaining *why*.
- Every text a user sees or hears goes through `t()` (i18n) with keys in `en.json` and
  `ms.json` — never hard-code UI text (`test_fixes43` enforces it). See
  [docs/adding-a-language.md](docs/adding-a-language.md).
- Accessibility: every control has a name NVDA can read, every status change is announced,
  and no failure is ever silent. Check by listening with the NVDA tools in `tools/`
  (see AGENTS.md), not by reading the code.
- API keys never appear in code, logs, URLs or test fixtures.
- Formatting: the code uses the standard `ruff format` style (line length 100, set in
  `pyproject.toml`). Run `ruff format .` and `ruff check .` before you commit; CI fails if a
  file is not formatted. The whole repository was formatted once (phase 37.5); that commit
  is listed in `.git-blame-ignore-revs`, so GitHub's blame skips it. To do the same locally:
  `git config blame.ignoreRevsFile .git-blame-ignore-revs`.

## 5. Commits

- One commit = one purpose. Use the existing style, for example
  `fix: <what changed> (pitfall N)` or `feat: ...`, `docs: ...`, `release: ...`.
- Update [CHANGELOG.md](CHANGELOG.md) and [docs/checklist.md](docs/checklist.md) when you
  add a user-facing feature.
- The version lives in `src/omni_describer_custom/__init__.py`; the last digit stops at 9
  (1.6.9 → 1.7.0).

## 6. Submitting

Branch → commit → run the full gate → open a pull request with the gate output
(`GATE_ALL_PASS`) attached. The pull request template lists what to include. A pull request
without a passing gate will not be merged.

## 7. Reporting bugs and security issues

- Bugs and feature requests: open an issue using the templates.
- Security problems (for example anything that could expose an API key): follow
  [SECURITY.md](SECURITY.md) — please do not open a public issue.

## 8. Licence and conduct

By submitting a contribution you agree that it is published under GPL-3.0-only (see
[LICENSE](LICENSE)). Everyone taking part is expected to follow
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
