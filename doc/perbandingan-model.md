# Perbandingan model video (29 Sep 2026)

Soalan pemilik: model yang MENDENGAR audio sepatutnya menghurai lebih
tepat — betulkah? Diuji dengan enjin app sendiri (`tools/model_bench.py`),
bukan dengan membaca katalog. Kos keseluruhan: **$0.26** OpenRouter.

## Kaedah

Lima klip yang benar-benar berbeza (pitfall 44), 50–60 s setiap satu:

| Klip | Isi |
|---|---|
| truth | Dibina sendiri: 8 peristiwa visual + ketukan (0:20), suara "The password is pineapple" (0:31), loceng (0:45) pada masa DIKETAHUI |
| sintel_dialogue | Sintel 1:50–2:50, dialog Inggeris + aksi |
| ocong | Kartun Indonesia, dialog padat |
| bm_news | AWANI Ringkas (Astro AWANI), berita BM |
| bbb_music | Big Buck Bunny 2:00–3:00, muzik, tiada pertuturan |

Setiap model: 2 larian × 5 klip dengan preset `default` dan transkrip
(seperti app), ditambah **ujian pendengaran** pada klip truth TANPA
transkrip. Ketepatan pada klip sebenar disemak dengan MATA: bingkai pada
masa setiap penerangan dibandingkan dengan teksnya (larian 1).

## Keputusan

| Model | Mendengar? (ketukan / loceng / ayat) | Peristiwa truth | Ketepatan visual (semakan mata) | Masalah |
|---|---|---|---|---|
| **GLM 5.3 Flash** (lalai) | ✗ pekak; **mereka** 3 bunyi "titisan" | 8/8, ralat masa 0.6 s | **Terbaik bersama** — Sintel 6/6, BM 3/3, Ocong 7/7 | 17% penerangan >12 patah; salah kenal watak BBB ("red rabbit") |
| **Gemini 3.1 Flash-Lite** | loceng ✓ ayat ✓ | 8/8, 1.5 s | **Sangat baik** — Sintel 4/5, BM 3/3, Ocong 6/6 | Paling murah & cepat antara yang mendengar; 0% penerangan panjang |
| Gemini 3.8 Flash | loceng ✓ (dipanggil "hon kereta") ayat ✓ | 7.5/8, **0.1 s** | Tepat tetapi **terlalu sedikit** (Sintel 3, Ocong 2 penerangan/min) | Mahal (5× GLM) |
| Qwen3.8-Omni-Flash | loceng ✓ ayat ✓ | 8/8, 1.4 s | Baik, tetapi menulis **perenggan** (35 patah dalam satu penerangan) | "He stands" (sebenarnya duduk) |
| MiMo v2.6 Flash | ketukan ✓ loceng ✓ ayat ✗ ("The pet project have a bomb") | 7.5/8 | Masa **tersasar** (gari pada 0:22, sebenar 0:45; bandar 14 s awal) | Gagal baca AV1; paling perlahan (134 s) |
| Gemini 2.5 Flash-Lite | **✗ tiada bunyi langsung** walaupun katalog kata ya | 7/8 | **Mereka** — "bermain seruling", "tangan besar menangkap lengannya" | 37 penerangan dalam 60 s (tidak boleh dituturkan) |
| Nemotron Omni (percuma) | tidak dapat diuji (had pelayan) | 8/8, **10.4 s** | Sederhana | 3/8 larian gagal; format masa rosak ("-00:01]") |

## Jawapan kepada soalan

**Mendengar TIDAK menjadikan penerangan lebih tepat dalam app ini.**
GLM yang pekak sama tepat atau lebih tepat daripada semua model yang
mendengar. Tiga sebab:

1. App sudah memberi SETIAP model transkrip pertuturan — model pekak
   tahu apa yang dikatakan.
2. Piawaian AD melarang menghurai apa yang pendengar sudah dengar
   (dialog, muzik, bunyi). Kelebihan mendengar jarang digunakan.
3. Ketepatan visual dan masa bergantung pada PENGLIHATAN model.

Di mana mendengar MEMANG membantu: bila transkrip gagal (lihat bug 1
di bawah) atau bila bunyi dari luar skrin mengubah makna adegan.

**Calon terbaik:** GLM 5.3 Flash (kekal lalai: tepat, murah) dan
**Gemini 3.1 Flash-Lite** (mendengar, tepat, pantas, murah, penerangan
pendek). Jangan guna Gemini 2.5 Flash-Lite (mereka, pekak walaupun
didakwa mendengar) atau Nemotron percuma (tidak stabil).

## Bug app yang ditemui oleh ujian ini (dibaiki v1.8.5)

1. **Transkrip Ocong KOSONG.** faster-whisper memberi nisbah mampatan
   per tetingkap 30 s; "Bra, bra, bra, bra" menjadikan seluruh
   tetingkap 2.79 dan 8 ayat sebenar dibuang. Kini dinilai per ayat.
2. **YouTube memilih AV1 + Opus**; MiMo dan Nemotron tidak dapat
   membukanya. Muat turun kini mengutamakan H.264 + AAC (resolusi sama).
   Disahkan: MiMo gagal pada AV1, 16 penerangan pada H.264.
3. Kunci Gemini (terus) pemilik ditolak Google ("API key not valid") —
   bukan bug app; kunci perlu diganti dalam Settings.

## Jalankan semula

```
python tools/model_bench.py make-clips
python tools/model_bench.py run --runs 2
python tools/model_bench.py score
python tools/model_bench.py frames --run 1
```

## Pembaris ketepatan (Fasa 16.1, 29 Sep 2026)

`python tools/model_bench.py measure` — model LAIN menilai setiap
penerangan lawan 4 bingkai pada masanya (-0.5 s hingga +4 s): betul /
separa / salah.

**Dikalibrasi dahulu, dua kali:**

| Set label | GLM sebagai penilai | Gemini 3.8 sebagai penilai |
|---|---|---|
| 99 label tangan (`tools/bench_labels.json`, disemak semula selepas penilai menunjukkan 10 label saya silap) | 12/13 salah dikesan, 0/63 tuduhan palsu | 13/13, 1/63 |
| 30 label **buta** (`tools/bench_labels_blind.json`, dilabel SEBELUM penilai melihatnya) | 1/1, 0/20 tuduhan palsu | 0/1, 1/20 |

Gemini 3.1 Flash-Lite ditolak sebagai penilai (12/67 tuduhan palsu).
"Betul" lwn "separa" kabur walaupun antara manusia (~70% setuju) —
**ukuran yang dipercayai ialah kadar SALAH.**

**Keputusan pada semua 488 penerangan (2 larian × 5 klip), penilai GLM, kos $0.025:**

| Model | Salah | Salah (penilai Gemini 3.8) |
|---|---|---|
| Qwen3.8-Omni | 7.2% | 24.6% |
| **GLM 5.3 Flash** | 8.0% | **13.8%** |
| Gemini 2.5 Flash-Lite | 11.0% | – |
| Gemini 3.8 Flash | 11.7% | – |
| Gemini 3.1 Flash-Lite | 14.5% | – |
| Nemotron | 20.7% | – |
| MiMo | 22.2% | – |

Penilai berbeza ketegasan (Gemini lebih keras), jadi bandingkan model
dengan penilai YANG SAMA. GLM tidak memihak dirinya: Gemini menilai GLM
lebih baik daripada Qwen. **Asas untuk Fasa 3: kira-kira 1 dalam 10
penerangan GLM salah atau tersasar masa.** Kos penilai GLM ~$0.00005
setiap penerangan — cukup murah untuk pas semakan dalam app.

## Fasa 16.2 — asas lebih luas (29–30 Sep 2026)

Klip genre baharu (60 s): **Tears of Steel** (drama aksi langsung,
Blender CC-BY), **NASA Our Planet, Our Home** (dokumentari, domain awam),
**Tutorial Asas Microsoft Excel** (PiTutorial, rakaman skrin BM).
Video panjang: Sintel 14:48 penuh. Penilai: GLM (pembaris 16.1).

### Genre pada klip pendek — ketepatan bukan masalah
| Model | Drama | Dokumentari | Tutorial | 
|---|---|---|---|
| GLM 5.3 Flash | 0/10 salah | 0/16 | 0/16 |
| Gemini 3.1 Flash-Lite | 1/12 | 0/11 | 1/13 |

### Empat bug ditemui (dibaiki v1.8.6)
1. **Jurang pertuturan yang hilang.** Whisper memanjangkan setiap segmen
   hingga segmen seterusnya: Tears diklaim 58.5 s pertuturan dalam 60 s
   (29.0 s ikut perkataan). Kedua-dua model menulis SATU penerangan untuk
   seminit robot dan manusia. `word_timestamps=True`: GLM 12 → **30**
   penerangan (4 larian), **0 salah** sebelum dan selepas.
2. **Had saiz pembekal di sebalik OpenRouter.** Google AI Studio menolak
   badan >20 MB; Gemini 3.1 Flash-Lite GAGAL pada Sintel penuh (413).
   Satu pelayan hulu GLM pula berhad **8 MiB** walaupun bahagian 29 MB
   diterima pelayan lain — kerja boleh gagal secara RAWAK. Kini had
   diketahui untuk `google/*`, dan had lain DIPELAJARI daripada ralat 413
   lalu bahagian itu dimampat dan dihantar semula.
3. **504 di dalam jawapan 200** membunuh seluruh kerja selepas 15 minit
   (semua bahagian siap dibuang). Kini dicuba semula seperti 5xx lain.
4. Selepas pembetulan 2: Gemini 3.1 Flash-Lite berjaya pada Sintel penuh
   (77 penerangan).

### Video panjang: panjang bahagian menentukan ketepatan
| GLM, Sintel 14:48 | Salah | Masa | Nota |
|---|---|---|---|
| Bahagian 10 min (lalai) | **24.5%** | 978 s | bahagian 1 ~30% salah, bahagian 2 (4.8 min) 14% |
| Bahagian 5 min | **12.9%** | **605 s** | jurang 141 s = kredit penutup |
| Bahagian 3 min | **12.1%** | 696 s | jurang 87 s = kredit penutup |

Kesilapan bahagian panjang ialah peristiwa BETUL pada masa SALAH
(bahagian 10 minit dimampat ke 360p; model tidak dapat menentukan saat).
Klip 60 s: 0–8% salah. **Disahkan pada video panjang kedua sebelum
menukar lalai** (Tears of Steel penuh, sedang berjalan).

**Disahkan pada filem panjang KEDUA (Tears of Steel penuh, 12:14):**
bahagian 10 min **27.5%** salah (+ lubang 85 s tanpa penerangan di hujung
bahagian 1), bahagian 5 min **11.8%**. Lalai app kini 300 s (v1.8.6).

### Mod bingkai (lalai pengguna baharu) — tidak sesuai untuk filem
| Model | Klip 60 s | Penerangan | Patah/penerangan | Sampah markdown | Salah | Masa |
|---|---|---|---|---|---|---|
| Gemini 3.1 FL | Tears | **204** | 12 | 0% | 3% | 783 s |
| Gemini 3.1 FL | Berita BM | **176** | 16 | 0% | 11% | 501 s |
| Gemini 3.1 FL | Sintel | **147** | 10 | 0% | 10% | 417 s |
| Gemini 3.1 FL | Big Buck Bunny | 98 | 28 | 1% | 15% | 294 s |
| Gemini 3.1 FL | Ocong | 24 | 17 | 4% | 17% | 75 s |
| GLM 5.3 Flash | Excel | 31 | **41** | **51%** | 6% | **856 s** |

Setiap bingkai yang lolos dedup menjadi penerangan 1 saat — 2–3 sesaat,
mustahil dituturkan. Tidak lebih tepat daripada mod video penuh. GLM
~20 s setiap bingkai; larian GLM filem dihentikan (anggaran 4 jam).

## Fasa 16.3 — pas semakan (30 Sep 2026)

Penyemak (GLM) melihat 12 bingkai dari 20 s sebelum hingga 20 s selepas
setiap penerangan, lalu menjawab di mana ia PALING jelas kelihatan, atau
"tiada". Diuji pada hasil sedia ada (Sintel 14:48 + Tears 12:14, bahagian
5 min, 209 penerangan) — `model_bench.py review` — dan diukur oleh
penilai BEBAS (Gemini 3.8) serta GLM. Kos semakan ~$0.014 setiap filem.

| Pilihan | Penerangan | Salah (Gemini) | Betul (Gemini) | Salah (GLM) |
|---|---|---|---|---|
| Tiada semakan | 209 | 39 (18.7%) | 106 | 26 (12.4%) |
| A: v1 — alih ke bingkai paling jelas, buang "tiada" | 198 | 27 (13.6%) | **113** | 18 (9.1%) |
| B: v2 — kekal jika sudah kelihatan di tempatnya, buang "tiada" | 187 | **23 (12.3%)** | 107 | **15 (8.0%)** |
| C: v2 tanpa buang | 209 | 32 (15.3%) | 112 | – |

Dapatan:
- Kebanyakan kesilapan ialah peristiwa BETUL pada masa SALAH, jadi
  mengalih masa membantu. v1 memperbaiki 17 penerangan salah di Sintel
  tetapi merosakkan 9 yang betul/separa (mengalih yang sudah betul ke
  bingkai "lebih jelas"); di Tears ia rugi bersih (5 dibaiki, 7 rosak).
- v2 bertanya dahulu "adakah ia kelihatan di tempatnya?" — hanya 22
  dialih (bukan 98).
- "Tiada" (buang) v2: 9 salah, 8 separa, 5 betul — membuang juga
  kehilangan penerangan baik.
- Sampel kecil: beza A lwn B (27 lwn 23 salah) dalam lingkungan hingar.
  Yang pasti: SEMUA pilihan menurunkan salah ~20–40% berbanding tiada
  semakan, dengan kos kecil.
- Kredit OpenRouter hampir habis ($0.80) — ujian suhu tetap dan snap
  perubahan adegan belum dibuat.

## Mod agentic — Fasa A: bolehkah model memandu ejen? (30 Sep 2026)

`tools/agent_bench.py`: tugas sebenar ejen Player pada Tears of Steel,
melalui tool call gaya OpenAI (current_position, read_descriptions,
look_at, look_between, propose_change). Dua tugas: penerangan yang dinilai
SALAH (mesti dibaiki) dan yang dinilai BETUL (mesti dibiarkan). 2 larian
setiap satu. Kos keseluruhan $0.063.

**Protokol:** kesemua 4 model — 32/32 larian guna tool call sebenar, lihat
bingkai SEBELUM mencadang, argumen sah. Katalog betul kali ini.

**Tingkah laku (arahan v2: "hanya jika JELAS salah; lihat beberapa saat"):**

| Model | Baiki yang salah | Biar yang betul | Nota |
|---|---|---|---|
| Gemini 3.1 Flash-Lite | 2/2 | 2/2 | pantas (~7 s) |
| Qwen3.8-Omni | 2/2 | 2/2 | ~13 s |
| GLM 5.3 Flash | 2/2 | 0/2 | "betul" diubah secara munasabah (alih 2.6 s ke nyalaan sebenar / buang "blinding") — terlalu teliti, bukan salah |
| Gemini 3.8 Flash | 0/2 | 2/2 | pada tugas "salah" TIDAK menjawab langsung (had 8 giliran) |

Arahan v1 (tanpa syarat ketat): GLM, Gemini 3.1 FL dan Qwen menyunting
penerangan betul 6/6 kali — syarat "jelas salah" itu penting.

Untuk Fasa B: (1) bila had giliran dicapai, ejen MESTI dipaksa memberi
jawapan akhir; (2) "Uji mod agentic" lulus jika protokol + lihat dahulu +
argumen sah + ada jawapan akhir — bukan pada pendapat model.

## Fasa 19.B — suhu tetap dan snap perubahan adegan (30 Sep 2026)

**Suhu 0 — DIGUNAKAN (v1.9.1).** GLM 5.3 Flash, mod video penuh, 4 klip
berbeza (Tears, NASA, berita BM, Sintel dialog) x 3 larian setiap tetapan,
dijalankan serentak dengan kod yang sama (`@tdef` lwn `@temp0`):

| | Suhu lalai pelayan | Suhu 0 |
|---|---|---|
| Penerangan (12 larian) | 95 | 119 |
| Salah — penilai Gemini | 23 (24.2%) | **20 (16.8%)** |
| Betul — penilai Gemini | 51 | **83** |
| Salah — penilai GLM | 20 (21.1%) | **11 (9.2%)** |
| Beza bilangan antara larian (jumlah) | 21 | **11** |

Contoh ketidakstabilan suhu lalai: berita BM memberi 3, 15, 14 penerangan
pada tiga larian (suhu 0: 18, 16, 16). Kini `GLMProvider.TEMPERATURE = 0`
untuk semua model OpenRouter; Gemini terus tidak diubah (belum diukur).
Kos $0.08 + penilaian $0.29.

**Snap ke perubahan adegan — TIDAK digunakan.** Setiap penerangan dialih
ke potongan adegan terdekat dalam ±2 s (ffmpeg scene > 0.3), pada Sintel
dan Tears penuh: penilai Gemini — betul 106 → 113 tetapi salah 39 → 44;
penilai GLM — salah 26 → 24, betul 125 → 126. Tiada kemajuan yang jelas,
jadi tidak dimasukkan (peraturan: simpan hanya yang menaikkan angka).
`model_bench.py snap` kekal untuk ujian lain kemudian. Kos $0.13.
