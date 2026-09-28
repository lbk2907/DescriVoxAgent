# Panduan Pengguna Omni Describer Custom

Alat penerangan audio yang mudah diakses untuk pengguna buta dan
penglihatan terhad. Ia memuat turun atau membuka video, mengekstrak
frame, menghantarnya kepada pembekal AI visi, dan memainkan video dalam
pemain terbina dalam yang membacakan penerangan AI segerak dengan
main balik.

Versi Inggeris penuh: `doc/user-guide.md` (ringkas: `README.md`).

## Memasang versi exe (tanpa Python)

Untuk komputer baharu tanpa Python, guna bungkusan siap bina:

1. Dapatkan `OmniDescriber-<versi>-win64.zip` (contoh
   `OmniDescriber-1.5.3-win64.zip`; nombor versi meningkat setiap
   rilis baharu supaya mudah bezakan) dan nyahzip ke mana-mana
   folder, contohnya `C:\OmniDescriber`.
2. Klik dua kali `OmniDescriber.exe` di dalamnya. Tiada pemasangan
   diperlukan; dokumen panduan ini turut dibundel dalam folder `doc`.
3. Mulai v1.6.5, tiada pemasangan lain diperlukan langsung. ffmpeg,
   ffprobe, ffplay dan yt-dlp dibundel di dalam folder `_internal\bin`
   aplikasi. Jangan padam folder itu — tanpanya muat turun YouTube,
   pengekstrakan bingkai dan bunyi video semuanya berhenti berfungsi.
   Kalau salah satunya hilang (contohnya dibuang antivirus), aplikasi
   akan memberitahu anda semasa ia dibuka, bukan gagal senyap kemudian.

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
   Kemudian tekan butang **Open** untuk mula memproses dengan arahan
   tersebut. Menukar teks dalam kotak itu tidak mengubah preset asal.

   Mulai v1.6.0, preset ditulis mengikut piawaian penerangan audio
   antarabangsa (DCMP Description Key, panduan gaya Netflix, W3C/WAI,
   ADLAB). Maknanya penerangan sengaja **lebih sedikit dan lebih
   pendek** daripada versi lama: ia tidak lagi menghuraikan semula latar
   belakang yang tidak berubah, dan tidak menceritakan dialog atau bunyi
   yang anda memang dengar sendiri. Senyap itu bukan kepincangan — ia
   bermakna tiada apa yang baharu untuk dilihat.

   Pilih preset ikut jenis video, bukan ikut genre:

   | Preset | Bila guna |
   |---|---|
   | `default` | Kebanyakan video. Mula dengan yang ini. |
   | `tight` | Video yang bercakap hampir tanpa henti; celah sangat pendek. |
   | `extended` | Dokumentari, tutorial, video perlahan — ada ruang untuk penerangan lebih penuh. |
   | `foreign` | Video bahasa yang anda tidak faham. Selain visual, ia menyampaikan maksud pertuturan. |
   | `suspense` | Cerita seram atau menegangkan. Ia mengekalkan kesenyapan dramatik dan tidak membocorkan apa yang bakal berlaku. |
   | `children` | Kandungan kanak-kanak: perkataan mudah, ayat pendek. |
   | `onscreen_text` | Slaid, menu, kod, carta — teks pada skrin dibaca mengikut urutan. |

   Setiap preset ada versi Bahasa Melayu; app pilih versi yang betul
   mengikut bahasa penerangan dalam Tetapan.
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
  Menggunakan ffmpeg yang dibundel. Kemajuan ditunjukkan semasa jana;
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
- **Tab AI**: pembekal (Gemini, MiniMax, OpenAI, GLM, atau Custom),
  kunci API, model. **GLM** berjalan melalui OpenRouter secara
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
    apabila pembekal **GLM (OpenRouter), Gemini atau MiniMax** dipilih.
    Bila didayakan,
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
    memberi timestamp sendiri. Video panjang dipecahkan kepada
    beberapa bahagian (kira-kira 10 minit setiap satu) dan dihantar
    bahagian demi bahagian; timestamp dicantum semula ke satu garis
    masa. Bahagian besar (melebihi kira-kira 50 MB) dimampatkan
    terlebih dahulu — disahkan terhadap OpenRouter: video 50.7 MB
    berjaya dimuat naik, kira-kira 98 MB ditolak. Kedua-dua kotak
    semak ini saling menolak.
### Main video yang sudah ada penerangan

Butang **"Main Video dengan Penerangan Sedia Ada"** (kedua dalam
susunan Tab, selepas "Fail Video Tempatan") untuk video yang sudah ada
fail penerangannya — sama ada dijana di sini sebelum ini, atau ditulis
sendiri.

1. Pilih video.
2. Kalau ada fail `.srt`, `.vtt` atau `.txt` bernama SAMA di sebelah
   video itu, aplikasi akan tanya sama ada mahu guna fail itu. Kalau
   tiada, anda pilih sendiri.
3. Pemain terus dibuka.

Tiada pemprosesan AI, tiada kos, tiada menunggu. Video itu disalin ke
dalam folder projek, jadi ia masih boleh dimain walaupun fail asal
dipindahkan atau pemacu USB dicabut.

### Muat turun yang terputus

Mulai v1.6.7 muat turun yang terputus **disambung dari tempat ia
berhenti**, bukan dimulakan semula. Tekan Cancel, tutup aplikasi, atau
putus internet — bila anda buka video yang sama sekali lagi, ia
menyambung. Video yang sudah siap tidak disentuh langsung, dan projek
yang sudah ada videonya tidak akan memuat turun semula.

Untuk muat naik: dengan Gemini ia memang boleh disambung. Dengan GLM
tidak boleh — video dihantar dalam satu permintaan tunggal dan tiada
cara untuk menyambungnya. Tetapi kerja mampatan sebelum muat naik kini
disimpan, jadi percubaan semula tidak perlu mengekod semula video
(kira-kira 2.7 minit dijimatkan untuk video 10 minit).

- **Tab TTS**: enjin suara, suara, kelajuan pertuturan.
  Mulai v1.6.6 ada pilihan **"Pembaca skrin saya"**, dilabel dengan
  pembaca yang dijumpai (contoh "Pembaca skrin saya (NVDA)"). Ia
  bercakap melalui NVDA, JAWS, ZDSR atau apa sahaja yang sedang
  berjalan. Bila pilihan ini dipilih, kotak Suara dan Kelajuan
  dilumpuhkan — pembaca skrin anda yang menentukannya, bukan aplikasi
  ini; ubah dalam tetapan pembaca skrin itu sendiri. Jeda automatik
  semasa penerangan juga tidak tersedia, kerana pembaca skrin tidak
  memberitahu bila ayat sudah habis dibaca.

  Pada komputer yang **tiada** pembaca skrin langsung, aplikasi akan
  bercakap sendiri (SAPI/OneCore Windows) untuk mesej status. Kalau
  ada pembaca skrin, aplikasi diam supaya tiada yang dibaca dua kali.

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
- **Mod video penuh (GLM, Gemini atau MiniMax, kotak semak dalam Tab
  AI):** satu fail video penuh dihantar (dimuat naik ke Gemini atau
  MiniMax Files API, atau dimasukkan sebagai base64 untuk GLM melalui
  OpenRouter), AI menonton video (termasuk audio) sendiri, dan
  timestamp datang daripada AI itu juga. Ini sesuai untuk penerangan
  yang meliputi bunyi dan pertuturan, atau bila anda mahukan proses
  satu langkah sahaja. Pembekal lain (OpenAI, Custom) tidak menerima
  fail video tempatan, jadi mod ini tidak tersedia untuk mereka.
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

Setiap video yang diproses disimpan sebagai **projek**: video itu,
penerangan AI, dan fail SRT. Membuka projek semula TIDAK memanggil AI
lagi — jimat masa dan kos.

Projek disimpan dalam `Documents\OmniDescriber\projects`, satu folder
setiap projek yang dinamakan ikut projek itu, contohnya
`Sintel (48)`. Nombor dalam kurungan membezakan dua video yang sama
tajuk. Di dalamnya: `project.db` (penerangan) dan folder `media`
(video, `descriptions.srt`).

**File > Open Project...** membuka senarai semua projek, terbaru
dahulu. Setiap baris menyebut nama, bilangan penerangan dan tarikh,
contohnya "Sintel — 79 penerangan — 28/09/2026 11:30". Butang:

- **Buka** (Alt+B) — muatkan projek itu untuk dimain, disunting atau
  dieksport.
- **Namakan semula** (Alt+N) — beri nama baharu; foldernya juga
  ditukar. Kalau video projek itu sedang dimain, folder ditukar pada
  kali seterusnya app dibuka.
- **Buang** (Alt+A) — padam projek sepenuhnya, selepas pengesahan.

## Bahasa anda sendiri (Help > Laporan Terjemahan)

Fail bahasa yang anda buat atau betulkan disimpan dalam
`%APPDATA%\OmniDescriber\locales\` dan tidak hilang semasa app
dikemas kini. Selepas kemas kini, **Help > Laporan Terjemahan**
memberitahu berapa baris bahasa anda yang belum diterjemah dan
menyimpan baris-baris itu sahaja, bersama teks Inggerisnya, sebagai
`<kod>.missing.json` dalam folder itu. Panduan penuh:
`doc/menambah-bahasa.md`.

## Semak Kemas Kini (menu Help)

YouTube kerap berubah, dan yt-dlp (program yang memuat turun video)
versi lama boleh berhenti berfungsi. **Help > Semak Kemas Kini...**
memberitahu versi yt-dlp yang digunakan dan sama ada versi lebih
baharu tersedia; hasilnya dibacakan terus.

- **Kemas kini** (Alt+K) — muat turun versi baharu terus dari GitHub
  rasmi yt-dlp. Ia dipasang HANYA jika cap jari (SHA-256) sepadan
  dengan senarai rasmi penerbit dan program itu melaporkan versi yang
  betul; jika tidak, tiada apa yang berubah.
- **Guna versi asal** (Alt+A) — kembali ke yt-dlp yang dibekalkan
  bersama app.

Versi baharu disimpan dalam `%LOCALAPPDATA%\OmniDescriber\tools`;
salinan asal app tidak pernah ditimpa. Sekali seminggu, semasa app
dibuka, app menyemak secara senyap dan hanya **mengumumkan** jika ada
kemas kini — tiada apa dimuat turun tanpa pilihan anda. Jika muat
turun YouTube gagal, log akan mencadangkan menu ini.

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
