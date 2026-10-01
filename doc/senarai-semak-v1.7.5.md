# Senarai semak selepas v1.7.4

Dibuat 28 Sep 2026. Tanda `[x]` hanya bila ada bukti (output test/run).

Fasa yang sudah siap dipindah ke `senarai-semak-arkib.md` (30 Sep 2026). Di sini: semua yang MASIH terbuka, dan fasa semasa.

## Masih terbuka (dari fasa lama)

- [ ] Tukar kunci Gemini, OpenRouter, custom, Opus jika masih hidup (PEMILIK — di papan pemuka provider)
  _(dari: Fasa 1 — pemilik (bukan agent))_
- [ ] 5.1 Profil suara — DITANGGUHKAN oleh pemilik (28 Sep 2026)
  _(dari: Fasa 5 — ciri baharu (tanya pemilik dahulu))_
- [ ] 8.6 (tidak dibuat — pilihan pemilik) ffmpeg dalam menu Semak Kemas Kini
  _(dari: Fasa 8 — penambahbaikan kecil (diminta pemilik 28 Sep 2026))_
- [ ] 15.7 (PEMILIK) Kunci Gemini ditolak Google — ganti dalam Settings
  _(dari: Fasa 15 — perbandingan model (diminta pemilik 29 Sep 2026, v1.8.5))_
- [x] 18.1e suhu tetap, snap perubahan adegan — dibuat dalam 19.B1/19.B2
  _(dari: Fasa 18 — seterusnya (susunan pemilik 30 Sep 2026))_

## Fasa 19 — B + C + E (dipilih pemilik 30 Sep 2026; susunan E → B → C)
- [x] 19.E1 AGENTS.md: kedua jadi 57b; nota "jangan nombor semula" (nombor dirujuk dalam kod)
- [x] 19.E2 README 1232 → 143 baris (fakta semasa; bahagian lapuk dibuang); 37 keluaran dalam
      CHANGELOG.md, 0 baris sejarah hilang
- [x] 19.E3 18 fasa siap → senarai-semak-arkib.md; 5 item terbuka di atas; 0 baris hilang
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
- [ ] 23.7b Build 1.9.5, exe NVDA, tag
- [ ] 23.8 (cadangan) Ejen: jawapan akhir kosong selepas had giliran, dan pembetulan yang disebut tanpa propose_change

