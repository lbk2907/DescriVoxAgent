# AGENTS.md — Omni Describer Custom

Arahan untuk coding agent (Hermes, jcode/evergreen, Claude, dll.) yang bekerja dalam projek ini.
Baca fail ni dulu SEBELUM buat apa-apa perubahan.

## Apa Projek Ini

Aplikasi desktop **penerangan video berasaskan AI untuk pengguna buta (NVDA screen reader)**.
wxPython GUI, Windows sahaja. Python 3.13.

Pipeline: download video (YouTube/URL/fail) → extract frame ATAU hantar video penuh
→ AI describe bertimestamp → TTS narrasi + SRT + Player Window.

Pengguna utama = pemilik repo sendiri (buta, BM Malaysia). **Aksesibiliti bukan optional —
ia keperluan utama.** Label screen reader, status announce, dan dialog berstruktur WAJIB
dikekalkan dalam setiap perubahan UI.

## Peraturan Wajib (hard rules)

1. **GATE SEBELUM COMMIT.** Jalankan `run_gate.bat` selepas setiap perubahan kod.
   Commit hanya bila `GATE_ALL_PASS`. Gate = compileall + 27 test suite
   (unit, E2E real-GUI, acceptance, pipeline, packaging).
2. **JANGAN pecahkan aksesibiliti.** Setiap widget baharu perlu `name=`/label NVDA.
   Status changes mesti di-announce (lihat corak `SetStatusText` + focus move dalam main_frame.py).
3. **JANGAN guna Opus Proxy** — provider tu dah dibuang sepenuhnya (v1.5.3, kuota habis).
   Provider aktif: **GLM via OpenRouter** (z-ai/glm-5.3-flash), Gemini, MiniMax, custom OpenAI-compatible.
   Model mesti support video kalau mod video dipilih — semak katalog, jangan agak nama model.
4. **API key TIDAK ditulis dalam kod/chat.** Key dibaca dari settings.json (terenkripsi)
   atau env var. Agent TIDAK PERNAH taip password/token ke mana-mana.
5. **Bahasa UI dwi (EN + BM).** Semua string user-facing melalui i18n (`src/omni_describer_custom/i18n/strings.py`).
   Tambah kedua-dua versi. Bahasa penerangan mesti konsisten merentas semua AI paths (v1.5.2).
6. **Commit konvensyen:** mesej ringkas, jenis dulu (`feat:`, `fix:`, `test:`, `docs:`, `release:`).
   Version bump + README changelog bila release (`__version__` dalam `src/omni_describer_custom/__init__.py`
   = sumber tunggal versi).
7. **Fail untracked `VEDIO DESCRIBER.PY.txt` JANGAN disentuh** — sketch pemilik, asal package `video_describer`.
8. **Kerja latar (background) boleh terorphan** kalau server agent restart — build PyInstaller
   JALAN FOREGROUND (8-10 minit) supaya tak terputus.

## Arkitektur Minimum

```
main.py                          — entry point
src/omni_describer_custom/
├── __init__.py                  — __version__ (sumber tunggal)
├── core/
│   ├── ai_engine.py             — semua AI provider (GLM/OpenRouter, Gemini, MiniMax,
│   │                              custom); frame mode + fast one-shot + full-video mode;
│   │                              auto-compression; chunked processing
│   ├── video_processor.py       — ffmpeg frame extraction, burn-in timestamp, download
│   ├── tts_engine.py            — TTS (SAPI5 win32com, fallback chain)
│   ├── settings_store.py        — settings.json (API key terenkripsi)
│   ├── prompt_manager.py        — preset prompts per-bahasa
│   ├── project_store.py         — named projects, persist video/media
│   └── timeline_io.py           — import/export SRT/VTT/TXT/audio segerak
├── ui/
│   ├── main_frame.py            — window utama, pipeline _process_video, semua handler
│   ├── settings_dialog.py       — tabbed settings (General/AI/Audio)
│   ├── player_window.py         — player + subtitle overlay + TTS narrasi
│   ├── editor_window.py         — edit penerangan per-cue
│   └── scene_explorer.py        — browse frame + penerangan
└── i18n/strings.py              — EN + BM strings
tests/                           — 27 suite; run_gate.bat = semua
doc/                             — panduan-pengguna.md (BM), README
build.bat                        — compile → PyInstaller → smoke test → zip (FOREGROUND)
```

**Aliran data:** MainFrame._process_video → download/extract (video_processor) →
AI describe per frame ATAU chunked full-video (ai_engine) → Description dataclass
(id, start_time, end_time, text, edited, created_at, frame_path) → Player/SRT/TTS/export.

## Pitfall (perangkap yang selalu tersandung)

1. **Mod video penuh ≠ timestamp tepat.** Frame mode = timestamp kita tentukan (tepat);
   full-video = AI agak sendiri. Jangan campur EXPECTATION antara dua mod ni dalam test.
2. **Chunked processing perlukan konteks antara bahagian** — part X of Y + ringkasan
   bahagian sebelumnya + larangan "video starts with" + nama watak konsisten.
   Kalau tambah mode baharu, salin corak ni (v1.5.3).
3. **DirectUI progress bar tiada msctls_progress32** — E2E baca percent via
   GetWindowTextW (tajuk dialog) + PrintWindow pixel scan, BUKAN PBM_GETPOS.
4. **TTS SAPI5:** guna win32com SpFileStream terus, BUKAN runAndWait (masa lalu menyebabkan
   bunyi tak keluar).
5. **wx GUI test** perlu pytest-style wx app init — lihat test_fixes15 sebagai contoh betul.
   GUI test dalam gate instantiasi dialog sebenar.
6. **Monaco/CodeMirror tidak ada** dalam GUI ni (wxPython) — browser automation tools
   tak releven; untuk GUI automation guna pywinauto UIA + raw Win32 (lihat tools/ dan
   test E2E).
7. **Model reasoning besar (GLM)** perlukan max_tokens ~6000 — timeout dah dibump;
   jangan kurangkan tanpa test real.

## Prosedur Biasa

### Run app (dev)
```bash
run.bat
# atau: C:/Users/USER/AppData/Local/Programs/Python/Python313/python.exe main.py
```

### Gate penuh
```bash
run_gate.bat   # GATE_ALL_PASS diperlukan sebelum commit
```

### Build release
```bash
build.bat      # 4 fasa: compile check → PyInstaller → exe smoke test → zip
# Hasil: dist/OmniDescriber-<versi>-win64.zip
# Buang zip lama selepas yang baharu disahkan (kekalkan versi terkini sahaja)
```

### Test satu suite
```bash
C:/Users/USER/AppData/Local/Programs/Python/Python313/python.exe -u tests/test_fixes18.py
```

## Disiplin Kerja (corak dari sesi sebenar)

- **JANGAN ulang kerja yang dah verified** tanpa input baharu (arahan baru, bug sebenar,
  atau git tree berubah). Corak dari evergreen: auto-validation loop ditolak berkali-kali
  dengan jawapan konsisten — repeat validation tanpa fakta baharu bukan kerja, ia buang masa.
- **Verify fakta dengan kod, bukan ingatan** — sebelum menulis dakwaan (fields, fail,
  behaviour), semak source sebenar dahulu. Corak: skrip pemeriksaan kecil, bukan agakan.
- **State keputusan dengan bukti** — "PASS" tanpa bukti = tak pass. Rantaian
  speculative → plausible → validated → verified yang digunakan evergreen adalah standard.
- **Bina di atas tag, bukan HEAD** — bila menyemak release, ukur commit tag;
  HEAD boleh ada commit selepas rilis (doc bukti, dsb.).

## Status Semasa (kemas kini bila release)

- **Versi:** 1.5.3 (tag `v1.5.3`, commit `2d8437f`)
- Provider aktif: GLM/OpenRouter sahaja untuk GUI; Gemini + MiniMax full-video mode tersedia
- 27 test suite, semua PASS
- dist zip terkini: `OmniDescriber-1.5.3-win64.zip`
- Tiada bug terbuka
