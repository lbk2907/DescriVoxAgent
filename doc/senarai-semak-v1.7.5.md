# Senarai semak selepas v1.7.4

Dibuat 28 Sep 2026. Tanda `[x]` hanya bila ada bukti (output test/run).

## Fasa 1 — pemilik (bukan agent)
- [x] Padam `%APPDATA%\OmniDescriber\settings.json.v1.5.2.bak` (4 kunci XOR) — dipadam kekal atas
  arahan pemilik 28 Sep; kunci Gemini/GLM dalam settings.json (DPAPI) disahkan masih dibaca
- [ ] Tukar kunci Gemini, OpenRouter, custom, Opus jika masih hidup (PEMILIK — di papan pemuka provider)

## Fasa 2 — sahkan 1.7.4
- [x] 2.1 `tools/nvda_accessibility_check.py` — tetingkap utama (build 1.7.4: 20/20 OK)
- [x] 2.2 Semakan NVDA — editor, player, Ask More (alat baharu `tools/nvda_window_check.py`;
  DIBAIKI: slider player disebut "slider 0" tanpa nama, panel video disebut "video_area";
  kini 16/16 OK setiap tetingkap; gate GATE_ALL_PASS)
- [x] 2.3 E2E sebenar video panjang dengan GLM (Sintel 14:48, 2 bahagian): 121 cue,
  selesai diumumkan, SRT ditulis, log sahkan klamp cue lepas hujung bahagian.
  Semakan "upload copy" dalam alat E2E dibetulkan (hanya untuk fail >50 MB).
  DITEMUI: 5/121 cue >20 patah (model GLM, pitfall 14) — lihat 4.7.
- [x] 2.4 Editor/player dengan papan kekunci: sunting → pindah (Down) → tutup player →
  DB: `(5.0, 'EDITED ONE BY KEYBOARD')` — PASS. Nota kecil: senarai masih sebut teks
  lama sehingga pengguna berpindah (lihat 4.8).

## Fasa 3 — kemas
- [x] 3.1 AGENTS.md: 42→47 suite, Status Semasa ditulis semula, pitfall 49–53
- [x] 3.2 Padam zip 1.7.2 dan 1.7.3 (~890 MB; boleh dibina semula dari tag)
- [x] 3.3 `.audit_scan.sh` — dipadam (keputusan pemilik; audit 1.7.4 meliputinya)

## Fasa 4 — bug + build → 1.7.5
- [x] 4.1 GLM Cancel semasa permintaan panjang — `_run_cancellable`, <1 s (test_fixes38)
- [x] 4.2 Mod batch: satu gagal → yang lain dibatalkan (test_fixes38)
- [x] 4.3 Bitrate bahagian ikut panjang bahagian — Sintel 179 → ~350 kbps (test_fixes38)
- [x] 4.4 Buang `torch` + `coverage` — Whisper transkrip Sintel 12 segmen dengan torch disekat;
  test_packaging_content menolak build yang membawanya
- [x] 4.5 Pin ffmpeg autobuild-2026-09-21-13-55 + yt-dlp 2026.08.19; hash rasmi sepadan
  dengan bin/ (10/10 + 1); fail diubah → kod keluar 1, build berhenti
- [x] 4.6 Build 1.7.5 BUILD_ALL_OK (zip 446 → 319 MB, tiada torch); gate 48 suite x2
  GATE_ALL_PASS; E2E beku Sintel/Gemini 14/15 — satu-satunya 'gagal' ialah panjang cue
  (keputusan 4.7: biarkan), kini dilapor sebagai nota; Whisper dalam exe: 15 segmen
- [x] 4.8 Editor: label senarai dikemas kini semasa menaip — NVDA sebut teks baharu
  (`tools/e2e_editor_flow.py`)
- [x] 4.7 Cue >20 patah — keputusan pemilik: BIARKAN (jeda naratif menanganinya)

## Fasa 5 — ciri baharu (tanya pemilik dahulu)
- [ ] 5.1 Profil suara — DITANGGUHKAN oleh pemilik (28 Sep 2026)

## Fasa 6 — nama projek mesra (v1.7.6, diminta pemilik 28 Sep 2026)
- [x] 6.0 Padam 14 projek ujian (disahkan pemilik): 1–10, 32–35 — 27 projek tinggal
- [x] 6.1 Gate guna `ODC_PROJECTS_DIR` sementara; disahkan: folder sebenar tidak berubah semasa gate
- [x] 6.2 Folder bernama `Nama (id)/project.db`; diuji pada salinan dahulu, kemudian projek
      sebenar: 27/27 dipindah, 0 laluan video rosak (sandaran DB di %TEMP%)
- [x] 6.3 Senarai Open Project: "sintel — 79 descriptions — 28/09/2026 11:30" (didengar melalui NVDA)
- [x] 6.4 Butang Rename (Alt+N, BM/EN, NVDA sebut "Rename button Alt+ n"); handler diuji
      dalam test_fixes39; Alt+B bertembung Buka/Buang dalam BM dibaiki (Buang = Alt+A)
- [x] 6.5 17 projek bernama URL → tajuk sebenar (`tools/fix_project_names.py`)
- [x] 6.7 DITEMUI semasa gate: SAPI `speak_and_wait` kalah perlumbaan permulaan (~1/10)
      — video boleh sambung atas penerangan; dibaiki. Kegagalan NVDA test_fixes26 dibuktikan
      berpunca daripada NVDA membaca app lain; ujian kini ukur semula sehingga senyap
- [x] 6.6 Build 1.7.6 BUILD_ALL_OK; E2E beku 14/14 (folder `Sintel dialog clip (49)`);
      dialog Open Project didengar NVDA; gate 49 suite x2 GATE_ALL_PASS semasa NVDA senyap
- [x] 6.8 Pembersihan kedua (disahkan pemilik): 25 projek ujian dipadam (sintel ×4, zoo ×17,
      video ×2, percubaan gagal 11 & 26). Tinggal 27 dan 31 (Ocong). 1.1 GB → 361 MB
- [x] 6.9 Alat NVDA bridge disemak: sejarah ucapan (100 item: masa/teks/keutamaan) dan acara
      `speech`/`foreground` — TIADA acara "ucapan tamat", jadi meter audio kekal satu-satunya
      cara mengukur akhir ucapan; ujian menapis ucapan sendiri ikut teks
- [x] 6.10 Projek 27 dan 31 (Ocong) dihantar ke Recycle Bin atas arahan pemilik — folder projek kini
      kosong. test_fixes16 melangkau semakan video panjang (SKIP, bukan FAIL): 16/16 lulus

## Fasa 7 — Semak Kemas Kini dalam app (v1.7.7, dipersetujui pemilik 28 Sep 2026)
- [x] 7.1 `core/updater.py`: semak GitHub, muat turun, sahkan SHA-256 rasmi + versi, pasang di luar bundle
- [x] 7.2 `find_tool` guna kemas kini hanya selagi hash sepadan; "Guna versi asal" kembali
- [x] 7.3 Help > Semak Kemas Kini (BM/EN, NVDA: "Check again button Alt+c", hasil dibaca automatik)
- [x] 7.4 Semakan mingguan semasa app dibuka — hanya mengumumkan
- [x] 7.5 Petunjuk dalam log bila muat turun YouTube gagal
- [x] 7.6 test_fixes40 7/7 (fail yt-dlp sebenar, tanpa rangkaian); ujian sebenar GitHub: semak,
      muat turun, cap jari, uji, guna, kembali — semua berjaya (dalam folder sementara)
- [x] 7.8 DITEMUI dengan mendengar exe: menu File dibuka pada "File" (Settings tidak boleh dicapai
      dengan papan kekunci) dan Help pada "Help" — `Menu.SetTitle` menimpa item pertama di Windows.
      Dibaiki dengan `SetMenuLabel`; ujian menu native gagal tanpa pembaikan, lulus dengannya
- [x] 7.7 Gate 50 suite x2 GATE_ALL_PASS; build 1.7.7 BUILD_ALL_OK; exe didengar melalui NVDA:
      File → "Settings... s", Help → "Check for Updates... u" → dialog dibuka dan dibaca
