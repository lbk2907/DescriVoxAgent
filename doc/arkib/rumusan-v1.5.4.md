# Rumusan v1.5.4 — Audit Fix Pass / v1.5.4 Summary — Audit Fix Pass

> BM: Dokumen ini merumuskan SEMUA pembetulan audit penuh projek v1.5.4
> (5 agen audit + 3 agen pembetulan, disemak manual, gate penuh PASS).
> EN: This document summarises ALL fixes from the v1.5.4 full-project
> audit (5 audit agents + 3 fix agents, manually reviewed, full gate PASS).

## A. Pembetulan kritikal / Critical fixes

- BM: Bug ID penerangan — `save_descriptions()` tidak pernah menulis balik
  `lastrowid`, jadi semua cue kekal `id=0` selepas proses video baharu.
  Kesan: player hanya menarasikan cue PERTAMA, dan memadam SATU cue dalam
  editor memadam SEMUA cue + memadam projek dari SQLite (hilang data).
  Kini: ID sebenar ditulis balik; ujian regresi meliputi kes penuh.
- EN: Description-ID bug — `save_descriptions()` never wrote `lastrowid`
  back, so every cue kept `id=0` after a fresh pipeline run. Effects: the
  player narrated only the FIRST cue, and deleting one cue in the editor
  removed ALL cues and wiped the project from SQLite (data loss). Now:
  real ids are written back; regression tests cover the full path.

## B. Kebolehcapaian / Accessibility (NVDA)

- BM: Tetingkap Player, Scene Explorer, Editor dan Ask More kini
  MENGUMUMKAN status kepada NVDA (Playing/Paused/Stopped/Ended, keputusan
  TTS, ralat, jawapan AI) menggunakan corak SetLabel+SetFocus. Timer 500 ms
  tidak lagi menulis label yang tak berubah.
- EN: Player, Scene Explorer, Editor and Ask More windows now ANNOUNCE
  status to NVDA (Playing/Paused/Stopped/Ended, TTS results, errors, AI
  replies) using the SetLabel+SetFocus pattern. The 500 ms timer no longer
  rewrites unchanged labels.
- BM: Tetingkap utama menterjemah semula serta-merta bila bahasa ditukar
  (sebelum ini kekal Inggeris); ~65 string hardcoded → i18n (74 kunci EN+BM
  baharu; pariti penuh 302 kunci disemak oleh `tests/audit_i18n.py`).
- EN: The main window retranslates immediately on language switch
  (previously stayed English); ~65 hardcoded strings → i18n (74 new EN+BM
  keys; full 302-key parity checked by `tests/audit_i18n.py`).
- BM: Scene Explorer — papan kekunci berfungsi walaupun fokus dalam kotak
  teks (EVT_CHAR_HOOK), guard double-fire untuk kekunci D, prompt AI ikut
  bahasa pilihan (bukan hardcoded Inggeris).
- EN: Scene Explorer — keyboard works while focus is inside text boxes
  (EVT_CHAR_HOOK), D-key double-fire guard, AI prompt follows the chosen
  language (not hardcoded English).
- BM: Editor — pengesahan sebelum padam + umuman selepas padam/tambah.
  Settings — pilihan mesra ("Bahasa Melayu", "Edge TTS", bukan "ms",
  "edge"), Enter = Apply, butang Test tak boleh double-fire, label slider.
- EN: Editor — delete confirmation + announcements. Settings — friendly
  choices ("Bahasa Melayu", "Edge TTS" instead of "ms", "edge"), Enter =
  Apply, Test button cannot double-fire, slider labelled.

## C. Keselamatan / Security

- BM: Kunci API kini dilindungi Windows DPAPI (`dpapi:` prefix) — bukan
  lagi XOR dengan kunci dalam kod. Kunci lama (XOR) masih boleh dibaca.
  `settings.json` ditulis secara atomik (crash tidak lagi hilangkan kunci).
- EN: API keys are now protected with Windows DPAPI (`dpapi:` prefix) —
  no longer XOR with a key in the source. Legacy XOR keys still decrypt.
  `settings.json` is written atomically (a crash can no longer wipe keys).
- BM: Gemini — kunci API dikeluarkan dari URL (ke header `x-goog-api-key`)
  pada 5 laman; ralat HTTP kini jelas. `download_video()` menolak URL
  bukan-http(s) dan melindungi yt-dlp dengan `--`. `.gitignore` + entri
  defensif untuk settings.json/.env/*.key.
- EN: Gemini — API key removed from URLs (moved to the `x-goog-api-key`
  header) on 5 sites; HTTP errors are now clear. `download_video()` rejects
  non-http(s) URLs and guards yt-dlp with `--`. `.gitignore` gained
  defensive settings.json/.env/*.key entries.

## D. Kebolehpercayaan / Reliability

- BM: GLM `max_tokens` 1024 → 6000 (model reasoning memerlukan ruang berfikir;
  jawapan kosong/terpotong dibaiki — pitfall #7 AGENTS.md).
- EN: GLM `max_tokens` 1024 → 6000 (reasoning models need thinking room;
  fixes empty/truncated replies — AGENTS.md pitfall #7).
- BM: Cancel kini berkesan semasa mampatan video/imbangan tempoh (ffmpeg
  dipoll setiap 1 s; sebelum ini Cancel tak berkesan sampai 30 minit).
- EN: Cancel now works during video compression/duration probing (ffmpeg is
  polled every 1 s; previously Cancel could be ignored for up to 30 minutes).
- BM: Kebocoran fail sementara ditutup: klip TTS semasa eksport audio,
  video termampah bahagian besar, folder sementara sari kata/projek.
  Kod mati dibuang; `has_audio` kini bermakna; `text_ocr` preset boleh
  diakses semula; logging tidak hilang dalam exe windowed.
- EN: Temp-file leaks closed: TTS clips during audio export, compressed
  oversized parts, subtitle/project temp dirs. Dead code removed; `has_audio`
  is meaningful again; the `text_ocr` preset is reachable again; logging no
  longer silently disappears in the windowed exe.

## E. Ujian / Tests

- BM: Suite baharu `tests/test_fixes19.py` (27 semakan) + didaftarkan dalam
  `run_gate.bat` → 28 suite. `test_fixes2.py` membaca ID mentah; `test_fixes12.py`
  menunggu pembersihan GUI secara event-driven (penilaian/ujian race).
- EN: New suite `tests/test_fixes19.py` (27 checks) + registered in
  `run_gate.bat` → 28 suites. `test_fixes2.py` reads the raw id; `test_fixes12.py`
  waits for GUI cleanup event-driven (race fix).

## Bukti / Evidence

- `run_gate.bat`: GATE_ALL_PASS — compileall + 28/28 suite PASS.
- `tests/audit_i18n.py`: 233 kunci digunakan, 0 hilang, 0 butang tanpa label.
- Fail/fail berubah: 23 diubah + 2 baharu (test_fixes19.py, rumusan ini).

## Tidak diubah / Deliberately unchanged

- Provider "openai" kekal dalam Settings (mungkin = "custom OpenAI-compatible").
- Butang player "<< 10s" / "10s >>" kekal (bentuk paparan pendek).
- Settings: Escape masih tutup tanpa semakan perubahan (ditangguhkan).
