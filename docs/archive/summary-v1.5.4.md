# v1.5.4 summary — audit fix pass

> This document summarises ALL fixes from the v1.5.4 full-project audit (5 audit agents +
> 3 fix agents, manually reviewed, full gate PASS). Translated to English only on
> 5 Oct 2026; the content is unchanged.

## A. Critical fixes

- Description-ID bug — `save_descriptions()` never wrote `lastrowid` back, so every cue
  kept `id=0` after a fresh pipeline run. Effects: the player narrated only the FIRST cue,
  and deleting one cue in the editor removed ALL cues and wiped the project from SQLite
  (data loss). Now: real ids are written back; regression tests cover the full path.

## B. Accessibility (NVDA)

- The Player, Scene Explorer, Editor and Ask More windows now ANNOUNCE status to NVDA
  (Playing/Paused/Stopped/Ended, TTS results, errors, AI replies) using the
  SetLabel+SetFocus pattern. The 500 ms timer no longer rewrites unchanged labels.
- The main window retranslates immediately on a language switch (previously it stayed
  English); ~65 hard-coded strings → i18n (74 new EN+MS keys; full 302-key parity checked
  by `tests/audit_i18n.py`).
- Scene Explorer — the keyboard works while focus is inside text boxes (EVT_CHAR_HOOK),
  a D-key double-fire guard, the AI prompt follows the chosen language (not hard-coded
  English).
- Editor — delete confirmation + announcements. Settings — friendly choices ("Bahasa
  Melayu", "Edge TTS" instead of "ms", "edge"), Enter = Apply, the Test button cannot
  double-fire, the slider is labelled.

## C. Security

- API keys are now protected with Windows DPAPI (`dpapi:` prefix) — no longer XOR with a
  key in the source. Legacy XOR keys still decrypt. `settings.json` is written atomically
  (a crash can no longer wipe keys).
- Gemini — the API key was removed from URLs (moved to the `x-goog-api-key` header) on 5
  sites; HTTP errors are now clear. `download_video()` rejects non-http(s) URLs and guards
  yt-dlp with `--`. `.gitignore` gained defensive settings.json/.env/*.key entries.

## D. Reliability

- GLM `max_tokens` 1024 → 6000 (reasoning models need thinking room; fixes
  empty/truncated replies — pitfall #7).
- Cancel now works during video compression/duration probing (ffmpeg is polled every 1 s;
  previously Cancel could be ignored for up to 30 minutes).
- Temp-file leaks closed: TTS clips during audio export, compressed oversized parts,
  subtitle/project temp dirs. Dead code removed; `has_audio` is meaningful again; the
  `text_ocr` preset is reachable again; logging no longer silently disappears in the
  windowed exe.

## E. Tests

- New suite `tests/test_fixes19.py` (27 checks), registered in `run_gate.bat` → 28 suites.
  `test_fixes2.py` reads the raw id; `test_fixes12.py` waits for GUI clean-up event-driven
  (race fix).

## Evidence

- `run_gate.bat`: GATE_ALL_PASS — compileall + 28/28 suites PASS.
- `tests/audit_i18n.py`: 233 keys used, 0 missing, 0 buttons without a label.
- Files changed: 23 modified + 2 new (test_fixes19.py, this summary).

## Deliberately unchanged

- The "openai" provider stays in Settings (possibly = "custom OpenAI-compatible").
- The player buttons "<< 10s" / "10s >>" stay (a short display form).
- Settings: Escape still closes without checking for changes (deferred).
