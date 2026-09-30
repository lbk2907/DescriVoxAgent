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
