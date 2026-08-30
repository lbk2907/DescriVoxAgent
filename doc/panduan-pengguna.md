# Panduan Pengguna Omni Describer Custom

Alat penerangan audio yang mudah diakses untuk pengguna buta dan
penglihatan terhad. Ia memuat turun atau membuka video, mengekstrak
frame, menghantarnya kepada pembekal AI visi, dan memainkan video dalam
pemain terbina dalam yang membacakan penerangan AI segerak dengan
main balik.

Versi Inggeris ringkas: `README.md`.

## Memulakan aplikasi

Klik dua kali `run.bat` dalam folder `omni-describer-custom`. Aplikasi
akan dibuka dengan tetingkap utama. Fail log ditulis ke:

`C:\Users\USER\AppData\Local\OmniDescriber\logs\omni_describer.log`

Jika sesuatu berlaku ganjil (contohnya penerangan gagal untuk sesetengah
frame), log itu merekod sebab sebenar setiap kegagalan.

## Langkah demi langkah: menerangkan satu video

1. Pada tetingkap utama, pilih sumber video dengan butang:
   - **Local Video File**: fail video dalam komputer anda.
   - **Direct Video URL**: pautan terus ke fail video.
   - **YouTube Video URL**: pautan halaman YouTube.
2. Pilih pra-tetap arahan (prompt) atau taip arahan anda sendiri, kemudian
   tekan butang **Open**.
3. Satu dialog kemajuan akan mengiringi keseluruhan proses dan sentiasa
   mengemas kini: muat turun (peratus sebenar, MB, kelajuan, ETA),
   penggabungan, ekstraksi frame ("Extracting frames: N"), analisis AI
   ("AI analysis: 7/120 frame"), dan penyimpanan.
4. Anda boleh menekan **Cancel** pada bila-bila masa. Semasa analisis AI,
   proses berhenti antara frame dan apa yang sudah siap akan disimpan.
5. Apabila siap, pemain video berpenerangan terbuka secara automatik
   dengan penerangan dimuatkan. Jika tiada penerangan, pemain akan
   menyatakan "No descriptions available."

## Tetapan (menu System > Settings..., atau butang Settings...)

- **Tab AI**: pembekal (Gemini, OpenAI, Opus Proxy, atau Custom), kunci
  API, model. Butang **Test** menguji sambungan sebenar.
- **Tab TTS**: enjin suara, suara, kelajuan pertuturan.
- **Tab General**:
  - **Language**: `en` (Inggeris) atau `ms` (Melayu).
  - **Frame Rate (FPS)**: berapa banyak frame per saat video yang
    diekstrak untuk dianalisis (1, 2, 5, atau 10). FPS lebih tinggi =
    lebih banyak penerangan tetapi lebih lambat dan lebih mahal.
  - **Had Maksimum Frame Setiap Video (0 = tiada had)**: had kos untuk
    video panjang. Lalai `0` bermakna tiada had: setiap frame yang
    diekstrak dianalisis (kelakuan asal). Jika anda menetapkan contohnya
    `100`, hanya 100 frame pertama dihantar kepada AI, dan log akan
    mencatat "Had frame dicapai". Masa (timestamp) kekal pada garis masa
    penuh video, jadi penerangan kekal segerak dengan main balik.
    Contoh: video 17 minit pada 5 FPS bermakna kira-kira 5000 panggilan
    AI tanpa had.
  - **Output Directory**: lokasi eksport ditulis.

## Projek

Projek disimpan dalam `Documents\OmniDescriber\projects` (satu folder
setiap projek dengan pangkalan data SQLite dan salinan kekal setiap
frame yang digunakan, jadi pemain kekal berfungsi selepas pembersihan).
Gunakan menu **File** untuk mencipta, membuka, atau menyimpan projek.

## Pemain video berpenerangan

- Pemain memaparkan tempoh sebenar video pada garis masa.
- Semasa main balik, penerangan frame semasa dibacakan (TTS) dan
  ditunjukkan sebagai teks.
- Gunakan kawalan pemain untuk jeda, carian, dan navigasi penerangan.

## Penjelajah scene

Dari pemain anda boleh membuka Scene Explorer untuk menyemak frame
satu demi satu: kunci anak panah kiri/kanan untuk bergerak antara frame,
`D` untuk penerangan penuh AI bagi frame semasa, `L` untuk senarai objek
dalam frame, dan `Escape` untuk menutup.

## Jika ada masalah

1. Baca log di
   `C:\Users\USER\AppData\Local\OmniDescriber\logs\omni_describer.log`;
   setiap ralat frame direkod dengan sebab sebenar.
2. Semak tetapan AI (kunci API, model, URL asas) dan tekan **Test**.
3. Untuk video panjang, pertimbangkan FPS lebih rendah (contohnya 1)
   atau tetapkan **Had Maksimum Frame Setiap Video**.
