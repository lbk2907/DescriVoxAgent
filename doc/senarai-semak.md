# Senarai semak selepas v1.7.4

Dibuat 28 Sep 2026. Tanda `[x]` hanya bila ada bukti (output test/run).

Fasa yang sudah siap dipindah ke `arkib/senarai-semak-fasa-1-18.md` (30 Sep 2026). Di sini: semua yang MASIH terbuka, dan fasa semasa.

## Masih terbuka (dari fasa lama)

- [ ] Tukar kunci Gemini, OpenRouter, custom, Opus jika masih hidup (PEMILIK — di papan pemuka provider)
  _(dari: Fasa 1 — pemilik (bukan agent))_
- [ ] 5.1 Profil suara — DITANGGUHKAN oleh pemilik (28 Sep 2026)
  _(dari: Fasa 5 — ciri baharu (tanya pemilik dahulu))_
- [ ] 8.6 (tidak dibuat — pilihan pemilik) ffmpeg dalam menu Semak Kemas Kini
  _(dari: Fasa 8 — penambahbaikan kecil (diminta pemilik 28 Sep 2026))_
- [x] 15.7 (PEMILIK) Kunci Gemini ditolak Google — ganti dalam Settings — SELESAI 1 Okt 2026: kunci baharu, 25/25 permintaan berturut (23.5)
  _(dari: Fasa 15 — perbandingan model (diminta pemilik 29 Sep 2026, v1.8.5))_
- [x] 18.1e suhu tetap, snap perubahan adegan — dibuat dalam 19.B1/19.B2
  _(dari: Fasa 18 — seterusnya (susunan pemilik 30 Sep 2026))_

## Fasa 19 — B + C + E (dipilih pemilik 30 Sep 2026; susunan E → B → C)
- [x] 19.E1 AGENTS.md: kedua jadi 57b; nota "jangan nombor semula" (nombor dirujuk dalam kod)
- [x] 19.E2 README 1232 → 143 baris (fakta semasa; bahagian lapuk dibuang); 37 keluaran dalam
      CHANGELOG.md, 0 baris sejarah hilang
- [x] 19.E3 18 fasa siap → arkib/senarai-semak-fasa-1-18.md; 5 item terbuka di atas; 0 baris hilang
- [x] 19.E4 doc/developer-guide.md
- [x] 19.B1 Suhu 0: betul 51 → 83, salah 24.2% → 16.8% (Gemini), beza larian 21 → 11 — DIGUNAKAN
- [x] 19.B2 Snap ke perubahan adegan: tiada kemajuan jelas (salah 39 → 44 Gemini) — TIDAK digunakan
- [x] 19.C1 "Semak seluruh video": sebenar pada 3 min Tears — 22 penerangan, 6 cadangan, $0.005;
      DITEMUI: edit dengan teks sama — kini ditolak
- [x] 19.C2 Ejen untuk Gemini terus — dibuat dalam 20.6
- [x] 19.R Didengar NVDA: pengesahan masa/kos dibaca penuh, "Checking part 1 of 1", langkah,
      "Whole video checked: 2 changes proposed", Esc → "No changes made". DITEMUI & DIBAIKI:
      kemajuan disebut dua kali (tajuk dialog), "About 1 minutes". Gate 65 suite x2 GATE_ALL_PASS
- [x] 19.S Build 1.9.1 (BUILD_ALL_OK), exe didengar NVDA 10/10, tag v1.9.1, zip 1.9.0 dibuang

## Fasa 20 — 1.9.2 (laporan pemilik 1 Okt 2026)

- [x] 20.1 Custom: kotak model tanpa label → label "Model name:" (didengar NVDA); base URL tanpa SetLabel
- [x] 20.2 Butang Test Connection dibuang (Uji model ini / Uji mod ejen buat semakan sebenar)
- [x] 20.3 "Full-video mode (GLM, Gemini or MiniMax)" → "Send the whole video to the AI (recommended)",
      petunjuk terangkan maksud tidak ditanda (didengar NVDA)
- [x] 20.4 DITEMUI semasa mendengar: Fetch/Test this model/Test agent aktif tetapi mati untuk Custom → dilumpuhkan
- [x] 20.5 "Uji model ini" untuk semua pembekal: sebenar Gemini 3.8/3.1 (lihat + dengar), Custom→OpenRouter
      (gambar "Red"), kunci salah → HTTP 401 jelas. MiniMax/OpenAI: tiada kunci, diuji dengan enjin palsu.
      DITEMUI: Gemini 3.1 Flash-Lite (disyorkan) tiada dalam senarai Gemini terus → ditambah
- [x] 20.6 Ejen Gemini terus: probe 3.1 Flash-Lite lulus (3 tool, betulkan BLUE→RED, $0.002);
      semak seluruh video 3 min Tears: 19 penerangan, 5 cadangan, ~$0.013. 3.8 Flash: 503 lalu 429 kuota
- [x] 20.7 Suhu 0 Gemini: salah 14.7% → 14.2% (sama), beza larian 23 → 12 — DIGUNAKAN (pilihan pemilik)
- [x] 20.8a Gate 66 suite x2 GATE_ALL_PASS; NVDA Tab AI: Custom 9/9, OpenRouter 12/12, Gemini 10/10
- [x] 20.8b Build 1.9.2 (BUILD_ALL_OK), exe didengar NVDA 10/10, tag v1.9.2, zip 1.9.1 dibuang

## Fasa 21 — 1.9.3 (pemilik 1 Okt 2026: "model hard coded atau boleh fetch?")

- [x] 21.1 Fetch models untuk Gemini: sebenar dengan kunci pemilik 61 → 12 model video, 3.1 Flash-Lite
      dahulu, harga daripada katalog OpenRouter; kunci salah → "HTTP 400: API key not valid"
- [x] 21.2 test_fixes57 (gagal pada kod lama 0/4, lulus 4/4); MiniMax/OpenAI kekal senarai terbina (tiada kunci)
- [x] 21.3a Gate 67 suite x2 GATE_ALL_PASS; NVDA Tab AI Gemini 11/11 ("Fetch models button")
- [x] 21.3b Build 1.9.3 (BUILD_ALL_OK), exe didengar NVDA 10/10, tag v1.9.3, zip 1.9.2 dibuang

- [x] 21.4 Ejen Gemini disediakan untuk pemilik: Test agent mode gemini-3.8-flash LULUS (4 tool, betulkan BLUE→RED, $0.0076), direkod dalam ai.agent_models

## Fasa 22 — tahap thinking (pemilik 1 Okt 2026: "adakah awak cuba high, medium, max?")

Peraturan: guna tahap baharu HANYA jika lebih tepat (penilai bebas); jika sama, pilih yang
paling murah/pantas. Catat masa dan kos setiap tahap.

- [x] 22.1 Semak tahap yang DITERIMA setiap API — GLM: none ditolak; Gemini 3.1 Lite tiada thinking
      secara lalai, max tiada; 3.8 Flash menolak minimal; laluan compat tidak lapor token:
      OpenRouter `reasoning.effort` (GLM), Gemini `thinkingConfig` (video penuh),
      Gemini OpenAI-compatible `reasoning_effort` (ejen)
- [x] 22.2 model_bench: varian `@think<tahap>` untuk GLM dan Gemini
- [x] 22.3 (cap 8.3%/4.6%, low 7.1%/2.7%, high 12.0%; max 19 min + kosong → DIKEKALKAN had 2000) Video penuh GLM 5.3 Flash: tahap semasa (2000 token) lwn tahap yang diterima,
      4 klip x 3 larian, penilai Gemini (+ GLM sebagai semakan kedua)
- [x] 22.4 (lalai 15.8%, low 12.7%, MEDIUM 9.1%, high 10.7% → medium DIGUNAKAN) Video penuh Gemini 3.1 Flash-Lite: lalai Google lwn tahap yang diterima,
      4 klip x 3 larian, penilai GLM
- [x] 22.5 (GLM: cap 8/16, LOW 11/16 2x pantas → DIGUNAKAN; Gemini 3.8: 429 kuota, tidak diukur) Ejen (tools/agent_levels.py): tahap semasa lwn tahap lain, GLM + Gemini — cadangan betul?
      langkah? kos?
- [x] 22.6 Keputusan + angka ke doc/perbandingan-model.md (keputusan jelas; kos $0.68)
- [x] 22.7 THINKING_BY_MODEL + AGENT_REASONING + cuba semula tanpa thinking bila ditolak (sebenar: 3.8 + minimal → berjaya);
      test_fixes53/55
- [x] 22.8a Gate 67 suite x2 berturut GATE_ALL_PASS (kegagalan pertama: folder odc_probe_ ditinggalkan SKRIP MANUAL saya, bukan app)
- [x] 22.8b Build 1.9.4 (BUILD_ALL_OK), exe didengar NVDA 10/10, tag v1.9.4, zip 1.9.3 dibuang

## Fasa 23 — 1.9.5 (pemilik: "saya topup Gemini, sepatutnya tiada masalah")

- [x] 23.1 Dokumentasi Google dibaca (rate-limits, billing, thinking, openai): tier per PROJEK
- [x] 23.2 Punca 429: kunci lama FreeTier 20/hari untuk 3.8 Flash (quotaId daripada badan ralat penuh)
- [x] 23.3 DIBAIKI: 429 tunggu `retryDelay`/`Retry-After` (maks 65 s); had harian gagal serta-merta + mesej jelas (test_fixes34)
- [x] 23.4 DIBAIKI (alat): salinan tetapan bench basi memakai kunci lama; kiraan bench "berhenti pada had kos" ≠ "dikekalkan"
- [x] 23.5 Ujian keras kunci baharu: 25/25; ejen 3.8 Flash 0/4 pembetulan, 3.1 Flash-Lite 4/4 (low dikekalkan)
- [x] 23.6 Tetapan pemilik: model Gemini → 3.1 Flash-Lite, Test agent mode lulus (pilihan pemilik)
- [x] 23.7a Gate 67 suite x2 berturut GATE_ALL_PASS
- [x] 23.7b Build 1.9.5 (BUILD_ALL_OK), exe didengar NVDA 10/10, tag v1.9.5, zip 1.9.4 dibuang
- [ ] 23.8 (cadangan) Ejen: jawapan akhir kosong selepas had giliran, dan pembetulan yang disebut tanpa propose_change

## Fasa 24 — kemas dokumen (pemilik 1 Okt 2026)

- [x] 24.1 doc/plan.md dwibahasa: semua pelan dari v1.5.1 hingga fasa 24, kerja terbuka di atas
- [x] 24.2 AGENTS.md dalam English (270 baris, aliran kerja + peraturan untuk semua agent); CLAUDE.md menunjuk ke AGENTS.md
- [x] 24.3 doc/pitfalls.md: 88 entri (1–87 + 57b), nombor sama, diterjemah; komen kod "AGENTS.md pitfall N" → "pitfall N"
- [x] 24.4 Fail lama ke doc/arkib/; senarai-semak-v1.7.5.md → senarai-semak.md; semua pautan dikemas kini
- [ ] 24.5 Panduan pengguna, developer-guide, README disemak terhadap kod; gate x1


## Fasa 25 — bug laporan pemilik 2 Okt 2026 ("jangan ada yang tertinggal lagi")

Sumber: log pemilik (omni_describer.log, 1–2 Okt) + semakan bebas dokumen lwn kod.

- [x] 25.1 Tetapan SEBENAR pemilik tercemar: Gemini base_url = http://127.0.0.1:12144/v1beta (pelayan ujian) →
      semua kerja Gemini "Cannot connect to host". DIPULIHKAN (izin pemilik). Punca: 13 fail ujian tanpa ODC_CONFIG_DIR sendiri
- [x] 25.2 (tests/isolate.py diimport PERTAMA oleh 71 ujian; test_fixes58 menggagalkan gate jika tidak; 4 alat E2E dikotak-pasir) Setiap fail ujian mengasingkan tetapan/projek/locales SENDIRI + ujian pengawal (gagal jika ada fail tanpa)
- [x] 25.3 (test_fixes58 menangkap EVT_DOUBLECLICK pada kod lama) Buka Projek RANAP setiap kali sejak 1.7.6: wx.EVT_DOUBLECLICK tidak wujud → EVT_LISTBOX_DCLICK;
      ujian statik: setiap nama wx.* dalam src wujud
- [x] 25.4 (test_fixes49) OpenRouter 413 "Payload Too Large" tanpa nombor (hulu Alibaba) tidak dipelajari → turunkan had & cuba semula
- [x] 25.5 (test_fixes59: berhenti dalam 1 segmen; sari kata yt-dlp/ffmpeg juga) Cancel diabaikan semasa transkrip Whisper (1.5–6 min menunggu) → transkripsi boleh dibatalkan
- [x] 25.6 (media/transcript.json, dikongsi dengan ejen) Transkrip dibuat SEMULA setiap larian (Jantan Miskin 4x, 3–6 min setiap kali) → simpan dalam projek
- [x] 25.7 (perlumbaan pembaca stderr; kod keluar disertakan) "video split failed:" tanpa sebab → sebab sebenar + mesej jelas
- [x] 25.8 (test_fixes60: _ui() + pengawal; Player/Editor ditutup dengan betul) Tutup tetingkap semasa memproses → ranap "MainFrame has been deleted"
- [x] 25.9 (user_error_text pusat; muat naik Gemini cuba semula 3x) Ralat sambungan/Gemini mentah ("Cannot connect to host ...") → mesej jelas dwibahasa
- [x] 25.10 (test_fixes54) Ejen F2 "tidak tersedia" bila model belum diuji → tawar uji sekarang; log sebab
- [x] 25.11 (audit: Cancel dialog tidak dikesan SELEPAS muat turun dalam semua mod = punca utama; eksport audio, ejen, Tanya Lagi, Scene Explorer, semakan, mod bingkai/pantas — test_fixes60/61/62/59) Audit SEMUA butang Cancel (muat turun, proses, mampat, pecah, semak, ejen, kemas kini, eksport audio, uji model)
- [x] 25.12 (30+ tempat; kegagalan kerja kini dalam kotak mesej yang dibaca NVDA) Audit semua ralat mentah yang sampai kepada pengguna
- [x] 25.13 (output_dir = folder dialog eksport; lalai glm; ms.json; susunan kotak bahasa; 16 kesilapan dokumen) Semakan bebas (fasa 24): output_dir tidak digunakan; provider lalai "gemini" vs "glm"; OpenRouter 429/kuota
      harian; perkataan English dalam ms.json; susunan kotak bahasa; 16 kesilapan panduan/README
- [x] 25.15 Pemilik: ejen mesti terima masa SEMASA; slider "1:04" — kedudukan ikut jam sebenar (tanpa VLC
      ia ketinggalan bila pemasa lewat), slider dalam saat (anak panah 5 s, Page 30 s) dibaca "1:04 daripada 24:30",
      setiap soalan ejen membawa kedudukan (test_fixes63; kod lama 0/4)
- [x] 25.16 Pemilik: "ada progress yang hanya dibaca saat sahaja" — fasa panjang disebut sekali, lalu teks
      dialog berubah SETIAP SAAT dan NVDA membaca "46s" sahaja. Kini laporan ayat penuh setiap 30 s untuk semua
      pembekal (fasa + % / masa lagi / masa berlalu), teks dialog berubah setiap 15 s — DIGANTI oleh 25.17
- [x] 25.17 Pemilik memilih BAR % SAHAJA, tanpa suara berkala: AccessibleProgressDialog (wx.Gauge sebenar yang NVDA
      kenal; dialog Windows lama DirectUI) dengan SATU peratus untuk seluruh kerja: muat turun 0-15, transkrip 15-30
      (peratus Whisper sebenar), AI 30-95 (Gemini/MiniMax dianggar ikut masa), semakan 95-99; tidak pernah undur.
      Pengumuman pertukaran fasa dikekalkan (test_fixes64 6/6; lama 0/6)
- [x] 25.18 DITEMUI semasa mendengar: 'Play Video with Existing Descriptions' mencipta projek TANPA panjang video ->
      slider 0.1 s, main balik tidak tamat (bug lama). Player kini mengukur dengan ffprobe (test_fixes63)
- [x] 25.14a Gate 74 suite x2 GATE_ALL_PASS (sebelum 25.18); NVDA didengar: bar kemajuan "10 percent".."90 percent"
      (tools/nvda_progress_check.py), slider "0:00 of 0:30", Settings (Language di atas), Tanya Lagi, tetingkap
      utama 10/10, ejen sebenar (alat, cadangan, kotak keputusan, Esc)
- [x] 25.14b Gate 74 suite x2 GATE_ALL_PASS selepas 25.18; build BUILD_ALL_OK; exe didengar NVDA 10/10;
      tag v1.9.6; zip 1.9.5 dibuang

## Fasa 26 — 1.9.7 (pemilik 2 Okt 2026)

- [x] 26.1 Scene Explorer berkata "No AI configured" — puncanya: tiada bingkai LAGI (video panjang dimuat 2 fps,
      >2,800 bingkai); mesej itu untuk dua keadaan. Kini: "masih memuatkan" / "tiada bingkai" / "tiada AI";
      video panjang dimuat ~600 bingkai (test_fixes65)
- [x] 26.2 Ejen ATAU dua alat lama (pilihan pemilik): ejen sedia -> hanya Agent (F2); belum diuji -> ketiga-tiganya,
      lulus -> dua alat lama hilang; tiada ejen -> Ask More + Explore Scene. Ikut perubahan Settings (EVT_ACTIVATE)
      (test_fixes65; kod lama 0/6)
- [x] 26.4 Pemilik: pintasan di kawasan video — Space main/jeda, Kiri/Kanan 5 s (Ctrl 10 s, Ctrl+Shift 1 minit) + kedudukan disebut,
      Atas/Bawah kelantangan video 10% (disimpan; ffplay -volume, VLC audio_set_volume); nama kawasan video
      menyenaraikan kekunci (test_fixes65)
- [x] 26.5 Kekunci Video picture diuji SEBENAR (tools/nvda_video_keys_check.py, PostMessage ke tetingkap Player sahaja):
      fokus kekal, kelantangan ikut setiap kekunci, NVDA baca setiap satu (3 Okt 2026). Punca bug pemilik: _announce
      mengalih fokus ke baris status; ffplay dimulakan semula setiap kekunci (pitfall 95-97; test_fixes65 11/11)
- [x] 26.6 Tab dan F2 di Player (ujian pemilik 3 Okt): Tab/Shift+Tab keluar dari Video picture; F2 kini accelerator
      tetingkap (berfungsi di mana-mana); sebab ejen tiada disebut selepas Ask More dibuka (ujian sebenar NVDA; test_fixes65 14/14)
- [x] 26.3 Gate x2 (GATE_ALL_PASS dua kali berturut), kekunci Video picture diuji sebenar + oleh pemilik, build BUILD_ALL_OK,
      exe NVDA 14/14, tag v1.9.7 (3 Okt 2026); zip 1.9.6 dipadam dengan izin pemilik

## Fasa 27 — 2.0.0: nama baharu DescriVox Agent (pemilik 3 Okt 2026)

- [x] 27.1 Nama dipilih pemilik selepas semakan web >80 nama: **DescriVox Agent** (tiada produk lain bernama sama;
      paling hampir Scriptivox). Ejaan V besar, exe `DescriVox.exe`, zip `DescriVox-Agent-<versi>-win64.zip`, versi 2.0.0
- [x] 27.2 Hanya nama yang dilihat ditukar (pilihan pemilik): tajuk, About (+ "dahulu Omni Describer Custom"), exe/zip,
      build.bat + DescriVox.spec, dokumen. KEKAL: pakej `omni_describer_custom`, `%APPDATA%\OmniDescriber`,
      `Documents\OmniDescriber`, log — tetapan, kunci API dan projek selamat
- [x] 27.3 Gate x2 (GATE_ALL_PASS berturut), build BUILD_ALL_OK (DescriVox-Agent-2.0.0-win64.zip), exe NVDA 14/14 dan
      tetingkap ditemui dengan tajuk "DescriVox Agent", tag v2.0.0 (3 Okt 2026); build 1.9.7 dipadam dengan izin pemilik
- [x] 27.4 Zip sumber sahaja untuk sandaran (pemilik): `Documents\DescriVox-source-backups\DescriVox-Agent-source-v2.0.0.zip`
      (git archive, 182 fail teks, tiada exe/kunci). AUTOMATIK setiap keluaran: build.bat langkah [6/6]
      `tools/make_source_zip.py` menyemak setiap fail dan gagal jika ada binari/kunci (test_fixes66)

## Fasa 28 — 2.0.2: Open Project (pemilik 5 Okt 2026)

- [x] 28.1 "Selepas buka projek, tiada apa berlaku" — hanya satu baris log. Kini (pilihan pemilik: terus buka Player):
      projek dengan penerangan -> Player dibuka; Player projek lain ditutup dulu (tiada dua video serentak); projek
      kosong -> mesej apa perlu dibuat. Kedua-dua laluan (File > Open Project, dan pilih projek sedia ada untuk video
      yang sama) guna `_after_project_opened` (test_fixes68 3/3, MainFrame + Player sebenar)
- [x] 28.2 Semakan NVDA sebenar (5 Okt): "Open Project dialog" -> Enter -> "Described Video Player – Projek Ujian",
      fokus pada Video picture; tajuk utama dibaca "Descri Vox Agent" (sahkan 27.3)
- [x] 28.4 "1 descriptions" -> "1 description" (11 ayat EN; BM sudah betul): `I18n.t()` guna `<kunci>:one` bila count = 1
      (pitfall 98; test_fixes68 4/4, test_fixes43 7/7); panduan penterjemah dikemas kini
- [x] 28.3 Keluaran 2.0.2 (5 Okt): gate x2 GATE_ALL_PASS, build BUILD_ALL_OK + sandaran sumber automatik pertama
      (DescriVox-Agent-source-v2.0.2.zip, 195 fail), exe NVDA 14/14; tag v2.0.1 (1baa764) dan v2.0.2.
      Alat NVDA dibetulkan: NVDA tidak lagi sebut "multi line", semakan kotak prompt beri amaran palsu

