# Panduan Pengguna Omni Describer Custom

Alat penerangan audio yang mudah diakses untuk pengguna buta dan
penglihatan terhad. Ia memuat turun atau membuka video, mengekstrak
frame, menghantarnya kepada pembekal AI visi, dan memainkan video dalam
pemain terbina dalam yang membacakan penerangan AI segerak dengan
main balik.

Versi Inggeris ringkas: `README.md`.

## Memasang versi exe (tanpa Python)

Untuk komputer baharu tanpa Python, guna bungkusan siap bina:

1. Dapatkan `OmniDescriber-<versi>-win64.zip` (contoh
   `OmniDescriber-1.1.0-win64.zip`; nombor versi meningkat setiap
   rilis baharu supaya mudah bezakan) dan nyahzip ke mana-mana
   folder, contohnya `C:\OmniDescriber`.
2. Klik dua kali `OmniDescriber.exe` di dalamnya. Tiada pemasangan
   diperlukan; dokumen panduan ini turut dibundel dalam folder `doc`.
3. Untuk main balik video tempatan, tiada keperluan tambahan. Untuk
   pautan YouTube, pasang `yt-dlp` dan pastikan ia boleh dijumpai
   melalui PATH.

Versi pembangun (skrip Python) masih boleh dimulakan dengan `run.bat`
seperti di bawah.

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
2. Pilih preset arahan (prompt) dari senarai juntai bawah "Preset
   Arahan". Apabila anda memilih satu, teks penuh preset itu serta-merta
   muncul dalam kotak "Arahan untuk dihantar" di bawah, dan pembaca
   skrin mengumumkan "Preset dipilih: <nama>". Anda boleh membaca,
   menyunting, atau menambah nota pada teks itu sebelum memproses.
   Preset "default" menghuraikan semua yang kelihatan dalam setiap frame
   secara terperinci; preset lain lebih ringkas atau memberi tumpuan
   tertentu (aksara, teks pada skrin, dan sebagainya). Kemudian tekan
   butang **Open** untuk mula memproses dengan arahan tersebut.
   Menukar teks dalam kotak itu tidak mengubah preset asal.
3. Satu dialog kemajuan akan mengiringi keseluruhan proses dan sentiasa
   mengemas kini: muat turun (peratus sebenar, MB, kelajuan, ETA),
   penggabungan, ekstraksi frame ("Extracting frames: N"), analisis AI
   ("AI analysis: 7/120 frame"), dan penyimpanan.
4. Anda boleh menekan **Cancel** pada bila-bila masa. Semasa analisis AI,
   proses berhenti antara frame dan apa yang sudah siap akan disimpan.
5. Apabila siap, pemain video berpenerangan terbuka secara automatik
   dengan penerangan dimuatkan. Jika tiada penerangan, pemain akan
   menyatakan "No descriptions available."

## Import dan eksport penerangan (menu File)

Menu File kini ada empat fungsi timeline:

- **Import Penerangan dari fail SRT / VTT / teks**: pilih satu fail
  `.srt`, `.vtt`, atau `.txt`. Setiap baris masa menjadi satu
  penerangan dalam **projek baharu** (nama projek = nama fail), jadi
  projek sedia ada tidak terjejas. Format fail teks mudah: satu
  penerangan satu baris, bermula dengan masa, contohnya
  `0:05 Seorang lelaki masuk ke bilik` atau `00:10 - 00:14 Dia duduk`.
  Baris bermula dengan `#` diabaikan. Masa boleh ditulis sebagai
  `M:SS`, `H:MM:SS`, atau saat sahaja (contohnya `90.5`).
- **Eksport sebagai SRT** dan **Eksport sebagai WebVTT**: simpan semua
  penerangan projek terbuka sebagai fail sari kata bertambah waktu,
  boleh dibuka semula di sini atau dipakai dengan pemain/penyunting
  video lain.
- **Eksport sebagai Audio (lisan, disegerak)**: jana satu fail MP3
  (atau WAV) yang menyebut setiap penerangan dengan suara TTS anda
  pada masa yang betul. Fail ini boleh didengar bersebelahan video
  menggunakan mana-mana pemain media, tanpa perlu aplikasi ini.
  Memerlukan ffmpeg pada PATH. Kemajuan ditunjukkan semasa jana;
  suara, kelajuan, dan enjin mengikut tetapan TTS anda.

Kegunaan biasa "describe by time": terima fail SRT penerangan yang
disediakan oleh orang lain (atau taip sendiri dalam format teks
mudah), import ia, pilih video sumber yang sama, dan pemain akan
membacakan penerangan itu segerak semasa main balik.

## Tetapan (menu System > Settings..., atau butang Settings...)

- **Tab General** (kini tab pertama):
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
- **Tab AI**: pembekal (Gemini, OpenAI, Opus Proxy, atau Custom), kunci
  API, model. Butang **Uji Sambungan** (Test Connection) menyemak sama
  ada tetapan yang anda taip benar-benar berfungsi: ia menghantar satu
  soalan kecil kepada servis AI guna kunci itu (tanpa perlu memproses
  satu video). Keputusan muncul sebagai teks di bawah borang dan fokus
  papan kekunci berpindah ke situ supaya pembaca skrin terus
  membacanya. "OK: ..." bermakna kunci sah; "Error: ..." bermakna kunci
  salah, tiada internet, atau URL asas salah. Butang ini menguji nilai
  dalam borang semasa, jadi anda boleh menguji sebelum menekan Apply.
- **Tab TTS**: enjin suara, suara, kelajuan pertuturan.

Notis pemprosesan: bila pemprosesan selesai, dialog memaparkan
"Pemprosesan selesai! N penerangan dijana." Jika AI gagal atau tidak
memulangkan teks yang boleh diguna, dialog ralat menjelaskan langkah
susulan (semak kunci API melalui Uji Sambungan), projek kosong **tidak**
disimpan senyap-senyap, dan membuka projek yang tiada penerangan
memberi amaran dengan langkah susulan yang sama.

Dialog kemajuan menunjukkan fasa secara jelas dari mula hingga akhir:
"Memuatkan maklumat video..." (semak metadata, boleh ambil beberapa
saat untuk URL), "Muat turun: peratusan, MB, kelajuan, ETA" (strim
video dan audio berasingan), "Merging video and audio with ffmpeg...",
"Extracting frames: N frames", "AI analysis: N/M frames", "Saving
project...", dan "Muat turun selesai" selepas strim siap diambil.

## Bagaimana pemprosesan berfungsi (dan kenapa)

- **Video dimuat turun sekali sahaja.** Aplikasi tidak pernah "muat
  turun per frame". Satu muat turun penuh (strim video + audio
  digabungkan oleh ffmpeg) cukup untuk keseluruhan penerangan.
- **Frame diekstrak secara lokal** dari video itu mengikut tetapan FPS
  anda. Setiap frame membawa masa (timestamp) sendiri, contohnya
  0.0s, 0.2s, 0.4s pada 5 FPS. Timestamp datang daripada proses
  ekstraksi, bukan daripada AI.
- **Hanya frame (imej), bukan fail video penuh, dihantar kepada AI.**
  Model memulangkan teks penerangan untuk setiap imej; aplikasi
  melekatkan timestamp frame pada teks itu. Itulah sebabnya
  penerangan segerak dengan main balik video.
- Kenapa bukan hantar video penuh ke AI: API AI yang disokong menerima
  imej bagi setiap permintaan, bukan fail video; kaedah frame ini
  lebih pantas dan lebih murah, dan timestamp tetap tepat.

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
