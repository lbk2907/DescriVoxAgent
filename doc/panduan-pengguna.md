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
   `OmniDescriber-1.2.4-win64.zip`; nombor versi meningkat setiap
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

## Tetapan (menu File > Settings..., atau butang Settings...)

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
- **Tab AI**: pembekal (Gemini, MiniMax, OpenAI, GLM, Opus Proxy, atau
  Custom), kunci API, model. **GLM** berjalan melalui OpenRouter secara
  lalai: pilih pembekal `glm`, model `z-ai/glm-5.3-flash`, dan tampal
  kunci OpenRouter anda (bermula dengan `sk-or-v1-`); kunci terus
  Zhipu juga boleh digunakan melalui pembekal Custom dengan URL asas
  `https://open.bigmodel.cn/api/paas/v4`. Butang **Uji Sambungan** (Test Connection) menyemak sama
  ada tetapan yang anda taip benar-benar berfungsi: ia menghantar satu
  soalan kecil kepada servis AI guna kunci itu (tanpa perlu memproses
  satu video). Keputusan muncul sebagai teks di bawah borang dan fokus
  papan kekunci berpindah ke situ supaya pembaca skrin terus
  membacanya. "OK: ..." bermakna kunci sah; "Error: ..." bermakna kunci
  salah, tiada internet, atau URL asas salah. Butang ini menguji nilai
  dalam borang semasa, jadi anda boleh menguji sebelum menekan Apply.
  - **Mod video penuh (Full-video mode)**: kotak semak ini hanya aktif
    apabila pembekal **Gemini atau MiniMax** dipilih. Bila didayakan,
    AI menerima **keseluruhan fail video** (audio + visual) dan AI
    menontonnya sendiri, kemudian memulangkan senarai penerangan
    ber-timestamp buatannya. Tiada frame diekstrak dan tiada satu
    panggilan AI bagi setiap frame — satu muat naik dan satu panggilan
    sahaja, jadi biasanya lebih pantas dan lebih murah untuk video
    panjang, dan penerangan meliputi bunyi/perkataan juga, bukan
    sekadar imej. Status diumumkan sepanjang proses: "Memuat naik
    video ke penyedia AI...", "AI sedang menonton video
    (pemprosesan)...", dan "AI sedang menulis penerangan...".
  Pembekal **GLM** dipaparkan sebagai **OpenRouter** dalam senarai.
  Untuk OpenRouter, senarai model hanya menunjukkan model yang
  menyokong video, dan butang **Dapatkan model (Fetch models)**
  memuat semula senarai itu dari katalog awam OpenRouter (percuma,
  tanpa kunci atau kredit).
  - **Mod pantas satu-request (Fast one-shot mode)**: kotak semak ini
    hanya aktif apabila pembekal **OpenRouter (GLM)** dipilih. Frame diekstrak
    secara lokal dengan **cap masa H:MM:SS tertera terbakar** pada
    setiap frame (kotak gelap, penjuru kiri atas), kemudian **semua
    frame dihantar kepada AI dalam SATU panggilan** (untuk video
    panjang, pecahan automatik kepada pukal 150 imej setiap satu).
    AI membaca cap masa yang tertera itu sendiri, dan aplikasi
    melekatkan semula masa pada grid frame yang tepat — jadi walaupun
    AI tersalah baca sesuatu cap, timestamp penerangan kekal segerak
    dengan main balik. Satu muat turun, satu (atau sedikit) panggilan
    AI, dan frame dianalisis secara lokal. Ini adalah cara paling
    pantas dan paling jimat untuk GLM.
  - **Mod video penuh turut tersedia untuk OpenRouter**: model yang
    katalognya menyenaraikan input video (contoh `z-ai/glm-5.3-flash`)
    boleh menerima **satu fail video penuh** dalam satu permintaan
    (disahkan secara empirikal: video 60 saat guna kira-kira 9 ribu
    token). AI menonton sendiri, termasuk bunyi dan pertuturan, dan
    memberi timestamp sendiri. Video besar melebihi kira-kira 24 MB
    ditolak — guna mod pantas satu-request untuk video panjang. Kedua-
    dua kotak semak ini saling menolak.
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
Dalam mod video penuh, fasa ekstraksi/analisis frame diganti dengan
"Memuat naik video ke penyedia AI: peratus", "AI sedang menonton
video (pemprosesan)...", dan "AI sedang menulis penerangan..." —
tiada frasa frame diumumkan kerana tiada frame terlibat.

## Bagaimana pemprosesan berfungsi (dan kenapa)

- **Video dimuat turun sekali sahaja.** Aplikasi tidak pernah "muat
  turun per frame". Satu muat turun penuh (strim video + audio
  digabungkan oleh ffmpeg) cukup untuk keseluruhan penerangan.
- **Mod frame (lalai):** frame diekstrak secara lokal dari video itu
  mengikut tetapan FPS anda. Setiap frame membawa masa (timestamp)
  sendiri, contohnya 0.0s, 0.2s, 0.4s pada 5 FPS. Hanya frame (imej),
  bukan fail video penuh, dihantar kepada AI; aplikasi melekatkan
  timestamp frame pada teks yang AI pulangkan.
- **Mod video penuh (Gemini atau MiniMax, kotak semak dalam Tab AI):**
  satu fail video penuh dimuat naik (ke Gemini Files API atau MiniMax
  Files API), AI menonton video (termasuk audio) sendiri, dan
  timestamp datang daripada AI itu juga. Ini sesuai untuk penerangan
  yang meliputi bunyi dan pertuturan, atau bila anda mahukan proses
  satu langkah sahaja. Pembekal lain (OpenAI, Claude/Opus Proxy,
  Custom) tidak menerima fail video tempatan, jadi mod ini tidak
  tersedia untuk mereka.
- **Mod pantas satu-request (GLM, kotak semak dalam Tab AI):** frame
  diekstrak secara lokal seperti mod frame, tetapi setiap frame
  dibekalkan dengan cap masa `H:MM:SS` yang tertera di atas imej.
  Semua frame pergi dalam satu panggilan AI (pukal maksimum 150 imej),
  AI membaca cap itu, dan aplikasi betulkan masa ke grid frame yang
  tepat sebelum disimpan. Sesuai bila anda mahukan kelajuan mod frame
  dengan kos panggilan AI yang hampir dengan mod video penuh.
- Ketiga-tiga mod menghasilkan penerangan ber-timestamp yang sama
  segeraknya dengan main balik; bezanya hanya siapa yang menentukan
  masa (proses ekstraksi berbanding AI) dan apa yang dihantar (imej
  berbanding satu fail video).

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

## Penerang video berdikari (baris perintah + API HTTP)

Selain aplikasi GUI, repositori ini memuat pakej berdikari
`video_describer` (tiada hubungan kod dengan GUI). Ia membakar cap masa
`H:MM:SS` (kotak gelap, penjuru kiri atas) pada setiap frame yang
diekstrak ffmpeg, menghantar SEMUA frame base64 dalam SATU permintaan
`glm-5.3-flash`, membiarkan model MEMBACA cap masa yang tertera, kemudian
mengekstrak baris `H:MM:SS - penerangan` menjadi `description.srt` dan
`description.json` (batch automatik melebihi 150 frame; had 5 MB dan
6000 px setiap frame).

```bat
:: Terangkan satu video tempatan (SRT + JSON ditulis di sebelahnya)
set GLM_API_KEY=kunci-anda
python -m video_describer describe video.mp4 --fps 1 --tts

:: Parse teks model sahaja (baris H:MM:SS - penerangan)
python -m video_describer parse output_model.txt

:: API HTTP di 127.0.0.1:8765
python -m video_describer serve --port 8765
```

Titik akhir API: `GET /health`, `POST /describe` (badan JSON
`{"video_path": "...", "fps": 1, "tts": false}`),
`POST /describe/upload?name=v.mp4` (bait video mentah), dan
`POST /parse` (parse sahaja). Kunci API diambil daripada badan
permintaan, pengepala `X-API-Key`, atau pemboleh ubah persekitaran
`GLM_API_KEY`. Narasi TTS (`--tts`) menggunakan edge-tts (lalai
`ms-MY-OsmanNeural`) atau SAPI5 Windows (`--tts-engine sapi`); fail
pemangkin audio dan audio gabungan diletakkan dalam folder `audio/`
di sebelah output.

## Jika ada masalah

1. Baca log di
   `C:\Users\USER\AppData\Local\OmniDescriber\logs\omni_describer.log`;
   setiap ralat frame direkod dengan sebab sebenar.
2. Semak tetapan AI (kunci API, model, URL asas) dan tekan **Test**.
3. Untuk video panjang, pertimbangkan FPS lebih rendah (contohnya 1)
   atau tetapkan **Had Maksimum Frame Setiap Video**.
