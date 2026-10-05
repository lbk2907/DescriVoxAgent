## What and why

<!-- What does this change, and why? Link the issue if there is one (Fixes #123). -->

## How it was tested

<!-- Paste the end of the gate output. A pull request without a passing gate is not merged. -->

```
GATE_ALL_PASS
```

- [ ] `run_gate.bat` (or `py -3.13 -m pytest tests`) ends with `GATE_ALL_PASS`
- [ ] A new or changed behaviour has a regression test in `tests/` that imports `isolate` first
- [ ] The test fails on the old code and passes on the new code

## Accessibility

- [ ] Every new or changed control has a name the screen reader reads
- [ ] Every status change is announced; no failure is silent
- [ ] Checked by listening with NVDA (say which tool or what you heard), or explain why not needed

## Housekeeping

- [ ] User-visible text goes through `t()` with keys in `en.json` and `ms.json`
- [ ] `CHANGELOG.md`, `docs/user-guide.md` and `docs/checklist.md` updated if users will notice the change
- [ ] A lesson learned from a bug is added at the end of `docs/pitfalls.md` (never renumber)
- [ ] No API keys, `settings.json`, logs or personal files in the diff
