# Contracts

What "done" means, written down and frozen **before** the work it judges (owner, 6 Oct
2026, after reviewing the verification design of Watch Skill).

| Contract | Judges | Run by |
|---|---|---|
| `release.json` | Whether a version may be tagged: contracts frozen, documents current, the gate passed twice on this code, this version's zip built from it, NVDA heard this exact exe, the source backup is clean, the tag is free | `tools/release_check.py`; `tools/tag_release.py` tags only on VERIFIED |
| `a11y-main.json` | What NVDA must hear in the main window: every listed control reached by Tab, with its role, named and spoken | `tools/nvda_accessibility_check.py [--frozen]` |
| `measure-template.json` | The template for a measurement: copy it to `measure-<feature>.json`, set the thresholds and **freeze it before running the bench** | `tools/measure_check.py measure-<feature> <results.json>` |

## Verdicts

- **VERIFIED** — every required check passed.
- **FAILED** — a required check failed.
- **INCONCLUSIVE** — a required check could not run (no evidence, NVDA not reachable, results
  older than the rule). Never treated as a pass. Advisory checks never decide.

## Freezing and changing a contract

`LOCK.json` holds each contract's SHA-256 (canonical JSON) and version; `CHANGES.md` records
every version with who changed it and why. The gate (`tests/test_fixes74.py`) fails if a
contract differs from its lock or a version has no recorded reason.

An agent may change a contract (owner's choice, 6 Oct 2026) — only with

```bash
python tools/contracts.py freeze <id> --why "what changed and why"
```

and must tell the owner about the change in the same reply.

## Evidence

`run_gate.bat`, `build.bat` and the NVDA check record their own results, with the git tree
they ran on, in `%LOCALAPPDATA%\OmniDescriber\release\evidence.jsonl` (outside the
repository). A record counts for a release only if the released commit differs from that tree
in nothing but the documents listed in `release.json` (`allowed_after_test`).
