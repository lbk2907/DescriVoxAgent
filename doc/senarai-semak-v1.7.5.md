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

## Fasa 8 — penambahbaikan kecil (diminta pemilik 28 Sep 2026)
- [x] 8.1 test_fixes16: semakan video panjang guna video ujian 10 minit yang dijana sendiri,
      bukan projek pemilik — 4 semakan yang dilangkau kini lulus (20/20)
- [x] 8.2 Alat E2E buang HANYA projek yang dicipta oleh larian itu (`tools/e2e_projects.py`);
      larian sebenar exe 1.7.7 + Gemini: 14/14, projek 50 dibuang, folder pemilik tidak berubah
- [x] 8.3 DITEMUI: `e2e_gui_phase` dan `e2e_gui_v130` masih cari `*.db` (rosak sejak susun
      atur 1.7.6) — dibaiki; `e2e_gui_v130` juga menyemak "project_" dalam laluan
- [x] 8.4 Nama preset: awalan bahasa diambil daripada fail locale, bukan ("en_", "ms_");
      test_fixes41 gagal pada kod lama (preset `id_` dalam senarai English), lulus sekarang
- [x] 8.5 Gate 51 suite x2 GATE_ALL_PASS
- [x] 8.7 Build 1.7.8 BUILD_ALL_OK; exe didengar NVDA 10/10; E2E sebenar 14/14, projek
      ujian 51 dibuang sendiri; tag v1.7.8
- [ ] 8.6 (tidak dibuat — pilihan pemilik) ffmpeg dalam menu Semak Kemas Kini

## Fasa 9 — bug dilaporkan pemilik (v1.7.9)
- [x] 9.1 Kotak API key hilang selepas Show/Hide: dibina semula di (0,0), terakhir dalam Tab,
      tanpa label NVDA. Dibaiki dengan EM_SETPASSWORDCHAR pada kawalan yang sama.
      Didengar NVDA: Show → "API Key: edit selected TESTKEY 123", Hide → "edit protected".
      test_fixes42 gagal pada kod lama; gate 52 suite x2 GATE_ALL_PASS
- [x] 9.2 Build 1.7.9 BUILD_ALL_OK; aliran sama didengar dalam exe beku — sama seperti
      dari source; tag v1.7.9

## Fasa 10 — pelbagai bahasa (v1.8.0, dipersetujui pemilik 28 Sep 2026)
- [x] 10.0 Semakan: EN=MS 366 kunci; tukar bahasa semasa berjalan 33/33 kawalan betul
- [x] 10.1 ~15 teks Inggeris tetap kini melalui t() (amaran permulaan, log ralat, About,
      penapis jenis fail yang dibaca NVDA)
- [x] 10.2 46 kunci mati dibuang (388 → 342); ujian gagal jika kunci tidak digunakan
- [x] 10.3 Folder bahasa pengguna `%APPDATA%\OmniDescriber\locales` (kekal selepas kemas kini;
      pembetulan baris demi baris)
- [x] 10.4 Help > Laporan Terjemahan: `<kod>.missing.json` dengan teks Inggeris; didengar NVDA
      dalam BM: "Bahasa Melayu: semua baris sudah diterjemah"
- [x] 10.5 Panduan `menambah-bahasa.md` untuk pengguna exe; user-guide + panduan-pengguna
- [x] 10.6 test_fixes43 7/7; pada kod lama 5/7 gagal
- [x] 10.7 Gate 53 suite x2 GATE_ALL_PASS (NVDA senyap); build 1.8.0 BUILD_ALL_OK; Laporan
      Terjemahan didengar dalam exe dalam BM; tag v1.8.0
- [x] 10.8 (nota) Butang Yes/No dalam kotak mesej ikut bahasa Windows, bukan bahasa app — selesai v1.8.2 (12.6)

## Fasa 11 — model OpenRouter yang boleh dipercayai + audio per model (v1.8.1)
- [x] 11.1 Kajian: 4 model OpenRouter mendengar audio video (Qwen3.8-Omni-Flash, MiMo-v2.6-Flash,
      MiMo-v2.5, Nemotron free) — probe "pineapple"
- [x] 11.2 Fetch models: 85 → 65 (buang 13 :batch, 3 penghala, 4 alias); audio dahulu, harga;
      label NVDA; disimpan
- [x] 11.3 Uji model ini: klip 6 s warna + perkataan; didengar NVDA "watches the video and hears
      its sound"; menangkap Nova ("black, black"); keputusan mengatasi katalog (Seed-2.0-mini)
- [x] 11.4 Audio per model: salinan termampat kekal audio untuk model yang mendengar (ffprobe);
      amaran preset foreign ikut model; Qwen + MiMo dalam senarai lalai
- [x] 11.5 test_fixes44 7/7; kod lama gagal 3 (termasuk "sent a silent video")
- [x] 11.6 Gate 54 x2; build 1.8.1 BUILD_ALL_OK; E2E exe + Qwen via OpenRouter 14/14 (klip dialog
      Sintel 30 s: 1 cue — Qwen dan GLM sama-sama tulis 1 baris; parser ambil semua; preset
      tidak bercakap atas dialog); Uji model didengar NVDA; tag v1.8.1

## Fasa 12 — D/E/F/G (dipersetujui pemilik 29 Sep 2026)
- [x] 12.0 INSIDEN: ujian Scene Explorer gagal ambil fokus; kekunci (anak panah, d, l, Enter)
      pergi ke TeamTalk pemilik ("borak bersama") — mungkin terhantar mesej pendek. Dibaiki:
      `tools/safe_keys.py` enggan menaip kecuali tetingkap hadapan milik proses ujian (disahkan:
      menolak bila TeamTalk di hadapan). Semua alat automasi guna pengawal ini.
- [x] 12.1 Tambah mod `explorer` dan `settings` pada tools/nvda_window_check.py
- [x] 12.2 Settings tab General: 13/13 kawalan dibaca NVDA
- [x] 12.3 Sapuan papan kekunci + NVDA: 7 masalah (Esc editor/Ask More, 10s senyap, Scene Explorer
      senyap/tiada label, slider kelajuan dibaca '10', provider kosong pengguna baharu), semua dibaiki;
      test_fixes45 lulus 0/4 pada kod lama
- [x] 12.4 E: Sintel + Ocong melalui enjin app: GLM+transkrip satu-satunya yang sampaikan dialog
      (foreign); Gemini 3.8 paling terperinci tetapi 503; Qwen terlalu sedikit. Lalai: OpenRouter/GLM.
      DITEMUI: panjang video ikut audio pendek (22/23 cue hilang) + bin/ salah aras, dibaiki
      (test_fixes46); 503 kini tunggu 5 s/15 s dengan mesej jelas
- [x] 12.5 F: custom provider sebenar: format OpenAI, auto, Anthropic (Claude Haiku), ask_text lulus
- [x] 12.6 G: Yes/No ikut bahasa app (ui/dialogs.ask_yes_no); pemain retranslate()
- [x] 12.7 Didengar semula (EN + BM): anak panah/L/D/Tab Scene Explorer, 10s, Esc, slider 'Kelajuan',
      'Tidak button Alt+T'; gate 56 x2; build 1.8.2; exe: provider OpenRouter, slider Kelajuan; tag.
      DITEMUI semasa mendengar: Tab terperangkap dalam kotak Description (dibaiki); huruf dari
      pywinauto dihantar sebagai VK_PACKET (artifak ujian; guna vk_packet=False untuk huruf)
- [x] 12.8 Esc dalam kotak Ya/Tidak: butang Batal ditambah (Esc/Batal = Tidak), v1.8.7 — standard Windows
      tanpa butang Batal; Alt+T memilih Tidak

## Fasa 13 — ujian video panjang pada exe (dipersetujui pemilik 29 Sep 2026)
- [x] 13.1 Sintel 888 s pada exe 1.8.2: 169 cue, 2 bahagian. Alat E2E: crash emoji (log cp1252),
      "siap diumumkan" LULUS PALSU ("Indonesian" TeamTalk mengandungi "done"), tiada semakan liputan,
      jangkaan salinan mampat salah untuk video yang dipecah — semua dibaiki (pitfall 64)
- [x] 13.2 YouTube 403 tidak dicuba semula, ralat mentah Inggeris — dibaiki v1.8.3 (test_fixes47, pitfall 63)
- [x] 13.3 Gate 57 x2 GATE_ALL_PASS; build 1.8.3 BUILD_ALL_OK; E2E exe 1.8.3 15/15: 81 cue, cue terakhir
      846 s / 888 s, jurang terluas 82 s, NVDA sebut "Processing complete! 81 descriptions generated."

## Fasa 14 — kemajuan muat naik + NVDA (dilaporkan pemilik 29 Sep 2026, v1.8.4)
- [x] 14.1 Bar 0% semasa muat naik GLM: badan distrim dengan kiraan bait; menunggu model dianggar
      (core/timing_store: 60 s + nisbah dipelajari); masa tinggal dipaparkan
- [x] 14.2 Peralihan fasa tidak dibaca NVDA: disebut melalui Prism, tidak memotong
- [x] 14.3 "bahagian 1 daripada 2, 55%" sebelum apa-apa dihantar — kini 10%
- [x] 14.4 Gate 58 x2; build 1.8.4; E2E exe 16/16: NVDA sebut "About 8 min left" pada 15:29,
      kerja siap 15:37 (anggaran tepat); 98 cue, liputan 882/888 s
- [x] 14.5 DITEMUI semasa mendengar: fokus pada dialog -> NVDA ulang teks sama setiap saat 20 s.
      Dibaiki (teks hanya bila berubah); test_fixes48 menangkapnya
- [x] 14.6 Gate 58 x2; build 1.8.4; E2E klip 50 s 17/17: setiap fasa disebut SEKALI (transkrip, mampat, muat naik, "About 1 min left", membaca jawapan, siap)

## Fasa 15 — perbandingan model (diminta pemilik 29 Sep 2026, v1.8.5)
- [x] 15.1 tools/model_bench.py: 5 klip berbeza + klip kebenaran; 7 model x 2 larian; $0.26
- [x] 15.2 Keputusan: doc/perbandingan-model.md — mendengar tidak lebih tepat; GLM & Gemini 3.1 Flash-Lite terbaik
- [x] 15.3 Transkrip Ocong kosong (nisbah per tetingkap) — dibaiki, test_fixes31
- [x] 15.4 YouTube AV1 tidak boleh dibuka MiMo/Nemotron — utamakan H.264, test_fixes47
- [x] 15.5 Gate 58 x2 GATE_ALL_PASS; build 1.8.5 (test_fixes14 dikemas kini untuk label "Recommended:")
- [x] 15.6 Fail tempatan AV1/HEVC/VP9 dikod semula ke H.264 (v1.8.7, test_fixes51 klip sebenar)
- [ ] 15.7 (PEMILIK) Kunci Gemini ditolak Google — ganti dalam Settings
- [x] 15.8 Pemilik: GLM kekal lalai; GLM + Gemini 3.1 Flash-Lite disusun dahulu, dibaca "Disyorkan: ..." (test_fixes44)


## Fasa 16 — ketepatan & kebolehpercayaan penerangan (DISIMPAN, tunggu pemilik — 29 Sep 2026)
Pemilik: dialog kurang penting; yang penting video dihurai TEPAT dan boleh dipercayai.
Genre yang pemilik huraikan: drama/filem, kartun/animasi, berita/dokumentari, tutorial/ceramah (semua empat).
Ukuran: betul (padan bingkai), masa, rekaan, tertinggal, konsisten antara larian (169 lwn 81).
- [x] 16.1 Fasa 1 — pembaris siap (`model_bench.py judge|measure`): penilai GLM dikalibrasi pada 99 label
      tangan + 30 label buta (0/83 tuduhan palsu, 13/14 salah dikesan); GLM 8% salah (Gemini-judge 13.8%).
      Keputusan dalam doc/perbandingan-model.md. Kos keseluruhan fasa ~$0.40
- [x] 16.2 Fasa 2 — asas lebih luas (doc/perbandingan-model.md): genre pendek GLM 0 salah; video
      panjang 24.5%/27.5% salah dengan bahagian 10 min → 12.9%/11.8% dengan 5 min (lalai kini 300 s,
      v1.8.6). DITEMUI & DIBAIKI: jurang Whisper lesap (word_timestamps), had badan hulu OpenRouter
      (Google 20 MB, GLM 8 MiB), 504 dalam jawapan 200. Mod bingkai: 147-204 penerangan/min
- [x] 16.2b Pemilik (30 Sep): lalai video penuh; mod bingkai dijarakkan 4 s + dibersihkan.
      Larian sebenar GLM, Tears 60 s: 204 → 15 penerangan, 0 markdown (test_fixes50)
- [ ] 16.3 Fasa 3 — baiki, simpan hanya yang menaikkan angka: pas semakan kedua (betulkan/buang/
      alih masa), snap ke perubahan adegan (ffmpeg scene), suhu tetap untuk konsistensi,
      semak jurang panjang untuk peristiwa tertinggal
- [ ] 16.4 Fasa 4 — tetapan "Semak penerangan", NVDA, dokumen, gate
Anggaran: fasa 1-2 ~$0.50-1; pas semakan +20-40% kos/masa setiap video (akan diukur).

## Fasa 17 — pelepasan 1.8.6 (diteruskan 30 Sep 2026)
- [x] 17.1 Gate pertama GAGAL 4 suite (kerja 1.8.6 + mod bingkai bercampur, belum siap): ujian saluran
      bingkai set jarak 0; test_fixes23 potong kod pada `class` peringkat atas; test_fixes34 uji
      tingkah laku. DITEMUI: tajuk markdown dicantum ke ayat ("Scene A girl...") — dibaiki
- [x] 17.2 test_fixes50 (mod bingkai) 5/5; larian sebenar GLM Tears 60 s: 204 → 15 penerangan
- [x] 17.3 Gate 60 suite x2 GATE_ALL_PASS; build bersih 1.8.6 (kerja 1.8.7 di-stash semasa build);
      exe didengar NVDA 12/12; tag v1.8.6
- [x] 17.4 Gate 61 suite x2 GATE_ALL_PASS; build 1.8.7; exe NVDA 10/10; kotak Ya/Tidak (BM) didengar:
      "Sahkan dialog Padam penerangan ini?" → "Tidak button Alt+T", Batal, Ya; Esc → Tidak; tag v1.8.7

## Fasa 18 — seterusnya (susunan pemilik 30 Sep 2026)
- [ ] 18.1 Pelan ketepatan fasa 3 & 4 (16.3–16.4)
- [ ] 18.2 Mod agentic dalam Player (reka bentuk: memori agent-coeditor-design)
