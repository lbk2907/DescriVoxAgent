# CLAUDE.md

Read `AGENTS.md` first — it is the single source of rules for every agent in
this repo. Pitfalls (full text) are in `docs/pitfalls.md`; open work is in
`docs/checklist.md`.

The five most critical hard rules (details in AGENTS.md section 3):

1. Run `run_gate.bat` after every code change; commit only on `GATE_ALL_PASS` (twice in a row before a release).
2. Never break accessibility: every widget named for NVDA, status changes announced, verified by listening with the NVDA tools.
3. API keys never in code, chat, logs or URLs; never type passwords or tokens anywhere.
4. Ask the owner to leave the PC untouched and wait for OK before any GUI/keyboard/NVDA automation; keys only via `tools/safe_keys.py`.
5. Confirm with the owner before deleting anything or any outward-facing action; tests use isolated `ODC_*` dirs, never the owner's real data.

Reply to the owner in Malay first, then English detail.
