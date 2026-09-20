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
   Commit hanya bila `GATE_ALL_PASS`. Gate = compileall + 32 test suite
   (unit, E2E real-GUI, acceptance, pipeline, packaging).
   **Gate FAIL yang "kadang-kadang" BUKAN flake sampai dibuktikan.** v1.5.5:
   test_fixes12 gagal ~1 daripada 3 run; puncanya bug sebenar dalam app
   (ghost dialog), bukan test. Jalan suite yang gagal 10 kali sebelum
   melabelnya flaky.
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
8. **`wx.ProgressDialog` PUMP event loop dalam constructor-nya.** Handler
   `wx.CallAfter` yang beratur boleh jalan DALAM constructor itu, sebelum
   `self._dl_dialog` di-assign. Sebab tu `_ensure_download_progress` guna
   kaunter `_dl_close_gen`: kalau cleanup berlaku semasa dialog sedang dibina,
   dialog baharu itu dibuang (v1.5.5). Corak sama perlu untuk mana-mana dialog
   modal baharu yang dicipta dari CallAfter.
9. **Output test MESTI line-buffered.** `io.TextIOWrapper(...)` yang dibina
   sendiri mengabaikan `python -u`; bila proses crash, buffer hilang dan gate
   cetak log KOSONG (v1.5.5: crash tersembunyi berbulan). Semua fail dalam
   `tests/` guna `line_buffering=True`.
10. **Frame wx perlu di-drain sebelum Destroy** dalam test: worker thread
   masih ada `wx.CallAfter` beratur; Destroy dulu = access violation.
   Lihat `_drain_events`/`_destroy_frame` dalam `tests/test_fixes12.py`.
11. **wxPython Phoenix: TIADA `SetYesLabel`/`SetNoLabel`/`SetCancelLabel`.**
   Guna `SetYesNoCancelLabels(yes, no, cancel)`. Bug v1.5.5: butang Open
   TIDAK BUAT APA-APA untuk video yang sudah ada projek (AttributeError
   dalam `_start_processing`). Sama keluarga dengan `MenuBar.SetLabelTop`.
   **Semak `hasattr` dulu sebelum guna API wx yang jarang dipakai.**
12. **`SetLabel()` MEMAKAN state kawalan pada MSW.** `wx.Choice` hilang
   SELECTION; `wx.TextCtrl` teksnya DIGANTI dengan label itu. v1.5.4 guna
   SetLabel untuk nama NVDA pada 3 kawalan → setiap lancaran baharu tiada
   preset dipilih (Open jawab "Please select a prompt preset") dan kotak
   prompt mengandungi labelnya sendiri, yang dihantar ke AI sebagai
   "User notes". Guna `MainFrame._set_accessible_name()` (v1.5.6/1.5.7).
   **Untuk TextCtrl guna `SetName`, jangan `SetLabel`.**
13. **Prompt MESTI ikut piawaian audio description, bukan "huraikan semua".**
   Sumber: DCMP Description Key, Netflix AD Style Guide v2.1, W3C/WAI,
   ADLAB. Teras: huraikan hanya yang perlu untuk memahami; JANGAN huraikan
   apa yang sudah kedengaran (dialog/muzik/bunyi); kala kini, orang ketiga;
   lapor yang boleh dilihat, bukan tafsiran; jangan teka bangsa/jantina;
   cukup pendek untuk dituturkan. Preset ikut STRATEGI, bukan genre —
   piawaian guna peraturan sama untuk semua genre (Netflix namakan dua
   sahaja: kanak-kanak, horror/suspense). `prompt_manager.DEFAULT_PROMPTS`
   = SATU sumber prompt; `tests/test_fixes22.py` mengunci peraturan ini.
   Preset lama dibuang hanya kalau teksnya masih teks asal kita (edit
   pengguna tidak pernah disentuh).
14. **Handler = permukaan yang paling kerap terlepas.** Sebelum
   `tests/test_fixes21.py` (17 Sep 2026) TIADA satu pun handler menu/butang
   tetingkap utama dipanggil oleh mana-mana test — tetingkap diuji, handler
   yang membukanya tidak. Di situlah bug butang Open mati bersembunyi.
   **Tambah handler baharu = tambah check dalam test_fixes21.**
15. **Test MESTI guna settings terasing.** `run_gate.bat` set
   `ODC_CONFIG_DIR=%TEMP%\odc_gate_config`; `SettingsStore` hormat env var
   itu. Sebelum v1.5.5 gate menulis ke `settings.json` SEBENAR pengguna
   (Gemini provider jadi `http://127.0.0.1:.../v1beta` + key `test-key`).
   Jangan buang env var ni, dan jangan set dalam tool E2E — E2E memang
   perlu settings sebenar (key GLM).

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

### Backup (repo tiada remote)
Hook `.git/hooks/post-commit` (v1.5.5) bundle SELURUH sejarah ke
`~/OneDrive/backups/omni-describer-custom.bundle` selepas setiap commit.
Hook TIDAK tersimpan dalam git — kalau repo di-clone semula, cipta balik.
Pulih: `git clone <bundle> <dir>`.

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

- **Versi:** 1.6.1 (tag terakhir `v1.5.6`; rumusan v1.5.4:
  `doc/rumusan-v1.5.4.md`)
- Provider aktif: GLM/OpenRouter sahaja untuk GUI; GLM + Gemini + MiniMax
  full-video mode tersedia
- 32 test suite, semua PASS (test_fixes19 = audit fix regression suite;
  test_fixes20 = ghost progress dialog, dedupe label API, isolasi settings;
  test_fixes21 = SETIAP handler tetingkap utama + editor ditekan sungguh)
- E2E GUI sebenar (`tools/e2e_gui_phase.py`) PASS dengan GLM sebenar:
  12 cue, progress live, export SRT, exit bersih
- Tiada bug terbuka
- wxPython Phoenix: `MenuBar.SetLabelTop` TIDAK wujud — guna
  `menubar.GetMenu(i).SetTitle(...)`
