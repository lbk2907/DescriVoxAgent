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
