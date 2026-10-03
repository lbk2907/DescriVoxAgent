# Panduan Pengguna DescriVox Agent

*Dahulu dikenali sebagai **Omni Describer Custom** (nama ditukar dalam v2.0.0).
Tetapan, kunci dan projek kekal dalam folder lama (`%APPDATA%\OmniDescriber`,
`Documents\OmniDescriber`), jadi tiada apa yang hilang atau perlu dipindahkan.*

Alat penerangan audio yang mudah diakses untuk pengguna buta dan
penglihatan terhad. Ia memuat turun atau membuka video, meminta AI
menghuraikan apa yang DILIHAT pada setiap saat, dan memainkan video
dalam pemain terbina dalam yang membacakan penerangan segerak dengan
main balik. Semuanya boleh digunakan dengan papan kekunci dan
diumumkan kepada pembaca skrin anda.

Versi Inggeris penuh: `doc/user-guide.md` (ringkas: `README.md`).

Label dalam panduan ini ialah label antara muka Bahasa Melayu. Jika
app dalam Bahasa Inggeris, label Inggerisnya ada dalam
`doc/user-guide.md`.

## Memasang versi exe (tanpa Python)

Untuk komputer baharu tanpa Python, guna bungkusan siap bina:

1. Dapatkan `DescriVox-Agent-<versi>-win64.zip` (contoh
   `DescriVox-Agent-2.0.0-win64.zip`; nombor versi meningkat setiap
   rilis baharu supaya mudah bezakan) dan nyahzip ke mana-mana
   folder, contohnya `C:\DescriVox`.
2. Klik dua kali `DescriVox.exe` di dalamnya. Tiada pemasangan
   diperlukan; dokumen panduan ini turut dibundel dalam folder
   `_internal\doc`.
3. Tiada pemasangan lain diperlukan langsung. ffmpeg, ffprobe, ffplay
   dan yt-dlp dibundel di dalam folder `_internal\bin` aplikasi.
   Jangan padam folder itu — tanpanya muat turun YouTube,
   pengekstrakan bingkai dan bunyi video semuanya berhenti berfungsi.
   Kalau salah satunya hilang (contohnya dibuang antivirus), aplikasi
   akan memberitahu anda semasa ia dibuka, bukan gagal senyap kemudian.
4. Buka **Fail > Tetapan...**, pergi ke tab **Tetapan AI**, tampal
   kunci API anda dan tekan **Uji model ini** (lihat Tetapan di bawah).

Versi pembangun (skrip Python) pula dimulakan dengan `run.bat` dalam
folder `omni-describer-custom`.

## Fail log

Fail log ditulis ke:

`%LOCALAPPDATA%\OmniDescriber\logs\omni_describer.log`

Jika sesuatu berlaku ganjil (contohnya kerja gagal), log itu merekod
sebab sebenar setiap kegagalan.

## Langkah demi langkah: menerangkan satu video

1. Pada tetingkap utama, pilih sumber video dengan butang:
   - **Fail Video Tempatan**: fail video dalam komputer anda.
   - **URL Video Terus**: pautan terus ke fail video.
   - **URL Video YouTube**: pautan halaman YouTube.
2. Pilih preset arahan dari senarai **Preset Arahan**. Apabila anda
   memilih satu, teks penuh preset itu serta-merta muncul dalam kotak
   "Arahan untuk dihantar" di bawah, dan pembaca skrin mengumumkan
   "Preset dipilih: <nama>". Anda boleh membaca, menyunting, atau
   menambah nota pada teks itu sebelum memproses. Kemudian tekan butang
   **Buka** untuk mula memproses dengan arahan tersebut. Menukar teks
   dalam kotak itu tidak mengubah preset asal.

   Preset ditulis mengikut piawaian penerangan audio antarabangsa (DCMP
   Description Key, panduan gaya Netflix, W3C/WAI, ADLAB). Maknanya
   penerangan sengaja **sedikit dan pendek**: ia tidak menghuraikan
   semula latar belakang yang tidak berubah, dan tidak menceritakan
   dialog atau bunyi yang anda memang dengar sendiri. Senyap itu bukan
   kepincangan — ia bermakna tiada apa yang baharu untuk dilihat.

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

   Setiap preset ada versi Bahasa Melayu. Versi yang disenaraikan
   mengikut bahasa app itu sendiri (**Tetapan > Am > Bahasa**); tetapan
   **Bahasa huraian** hanya menentukan bahasa yang AI gunakan untuk
   menulis.
3. Satu dialog kemajuan mengiringi keseluruhan proses: muat turun
   (peratus sebenar, MB, kelajuan, ETA), penggabungan, kemudian sama ada
   muat naik dan AI menonton video, atau pengekstrakan dan analisis
   gambar pegun, dan akhirnya penyimpanan.
4. Anda boleh menekan butang **Batal** (atau Esc) dalam dialog itu pada
   bila-bila masa, termasuk selepas muat turun selesai. Kerja itu
   berhenti dalam beberapa saat, walau di langkah mana pun. Apa yang
   disimpan:
   - muat turun yang belum habis disimpan dan disambung kali seterusnya;
   - dengan gambar pegun, penerangan yang sudah siap disimpan;
   - dengan seluruh video, kerja yang dibatalkan tidak menyimpan
     sebarang penerangan, tetapi transkrip pertuturan disimpan, jadi
     percubaan seterusnya melangkaunya.
5. Apabila siap, pemain video berpenerangan terbuka secara automatik
   dengan penerangan dimuatkan. Jika tiada penerangan, pemain akan
   menyatakan "Tiada penerangan tersedia."

## Import dan eksport penerangan (menu Fail)

Menu Fail ada empat fungsi garis masa:

- **Import Penerangan dari fail SRT / VTT / teks...**: pilih satu fail
  `.srt`, `.vtt`, atau `.txt`. Setiap baris masa menjadi satu
  penerangan dalam **projek baharu** (nama projek = nama fail), jadi
  projek sedia ada tidak terjejas. Format fail teks mudah: satu
  penerangan satu baris, bermula dengan masa, contohnya
  `0:05 Seorang lelaki masuk ke bilik` atau `00:10 - 00:14 Dia duduk`.
  Baris bermula dengan `#` diabaikan. Masa boleh ditulis sebagai
  `M:SS`, `H:MM:SS`, atau saat dengan titik perpuluhan atau `s`
  (contohnya `90.5` atau `90s`). Nombor bulat sahaja seperti `90`
  TIDAK dibaca sebagai masa, jadi baris yang bermula dengan tahun atau
  bilangan diabaikan.
- **Eksport sebagai SRT...** dan **Eksport sebagai WebVTT...**: simpan
  semua penerangan projek terbuka sebagai fail sari kata bertambah
  waktu, boleh dibuka semula di sini atau dipakai dengan
  pemain/penyunting video lain.
- **Eksport sebagai Audio (lisan, disegerak)...**: jana satu fail MP3
  (atau WAV) yang menyebut setiap penerangan dengan suara TTS anda
  pada masa yang betul. Fail ini boleh didengar bersebelahan video
  menggunakan mana-mana pemain media, tanpa perlu aplikasi ini.
  Menggunakan ffmpeg yang dibundel. Kemajuan ditunjukkan semasa jana,
  dengan butang **Batal** (eksport yang dibatalkan tidak meninggalkan
  fail separuh siap); suara, kelajuan, dan enjin mengikut tetapan
  Output Audio anda.

Kegunaan biasa "huraikan ikut masa": terima fail SRT penerangan yang
disediakan oleh orang lain (atau taip sendiri dalam format teks
mudah), import ia, pilih video sumber yang sama, dan pemain akan
membacakan penerangan itu segerak semasa main balik.

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

## Tetapan (Fail > Tetapan..., atau butang Tetapan...)

Dialog ini ada tiga tab: **Am**, **Tetapan AI** dan **Output Audio**.

### Tab Am

- **Bahasa**: bahasa app itu sendiri (Inggeris, Melayu, atau fail
  bahasa yang anda tambah).
- **Bahasa huraian (jawapan AI)**: bahasa yang AI gunakan untuk menulis.
- **Kadar Kerangka (FPS)** dan **Had Maksimum Frame Setiap Video (0 =
  tiada had)**: hanya untuk gambar pegun (kotak seluruh video tidak
  ditanda). FPS lebih tinggi = lebih banyak gambar, lebih lambat dan
  lebih mahal; had itu mengehadkan kos video panjang tanpa mengalih
  penerangan dari garis masa video.
- **Jangan biarkan AI buta lebih lama daripada (saat, 0 = mati)**:
  gambar pegun sahaja; memastikan syot panjang yang tidak berubah masih
  diberi gambar sekali-sekala.
- **Panjang bahagian video untuk analisis AI (saat setiap bahagian)**:
  bila seluruh video dihantar, video panjang dihantar dalam bahagian
  sepanjang ini. Lalai 300 saat (5 minit); bahagian lebih pendek diukur
  meletakkan penerangan dengan lebih tepat.
- **Semak penerangan dengan video (bila menghantar seluruh video)**:
  lihat "Semak penerangan dengan video" di bawah. **Mati** secara lalai.
- **Kekalkan resolusi penuh untuk video besar (pecah, bukan
  kecilkan)**: untuk slaid dan tutorial, di mana video yang dikecilkan
  menjadikan teks pada skrin tidak terbaca.
- **Tukar pertuturan ke teks (bila video tiada sari kata)**: cara app
  mendapatkan transkrip apa yang diperkatakan, supaya AI tahu dialognya
  dan di mana ada senyap. **Automatik** guna Grok jika ada kunci xAI,
  jika tidak **Whisper tempatan** (percuma, luar talian, lebih
  perlahan). **Tutup** hanya menghuraikan gambar.
- **Direktori Output**: folder tempat dialog Simpan untuk eksport (SRT,
  WebVTT, audio) dibuka. Setiap eksport masih bertanya di mana mahu
  disimpan.

Kotak **Bahasa** berada di atas kotak **Bahasa huraian** (sebelum 1.9.6
susunannya terbalik).

### Tab Tetapan AI

- **Pembekal**: **OpenRouter** (lalai untuk pengguna baharu, model
  `z-ai/glm-5.3-flash`, kunci bermula dengan `sk-or-v1-`), **Gemini**
  (kunci Google anda sendiri), **MiniMax**, **OpenAI**, atau
  **Tersuai** (mana-mana titik akhir serasi OpenAI atau format
  Anthropic: **URL Asas**, **Format API**, dan kotak **Nama model** di
  bawah senarai Model).
- **Model**: untuk OpenRouter dan Gemini, senarai hanya menunjukkan
  model yang boleh menonton video. **Dapatkan model** memuat semula
  senarai itu: dari katalog awam OpenRouter (percuma, tanpa kunci atau
  kredit), atau untuk Gemini dengan bertanya kepada Google model mana
  yang boleh digunakan oleh kunci anda (percuma, tidak guna kuota).
  Senarai itu disimpan untuk kali seterusnya. Model yang disyorkan
  disenarai dahulu dan dibaca "Disyorkan: ...". Setiap baris menyebut
  nama model, kemudian (OpenRouter) "menonton dan mendengar video" atau
  "menonton sahaja, guna transkrip", kemudian harga sejuta token.
- **Uji model ini** (Alt+U): menyemak kunci dan model dengan klip
  sebenar, untuk SEMUA pembekal. OpenRouter, Gemini dan MiniMax
  menerima video ujian 6 saat (adakah ia melihat dan mendengarnya);
  OpenAI dan Tersuai menerima satu gambar. Keputusan dibaca terus oleh
  pembaca skrin, dan kosnya hanya sebahagian kecil satu sen. (Butang Uji
  Sambungan lama dibuang dalam 1.9.2; Uji model ini menggantikannya.)
- **Uji mod ejen** (Alt+E): OpenRouter dan Gemini sahaja. Menyemak sama
  ada model itu boleh menjalankan ejen Player (F2); model mesti lulus
  sebelum F2 menggunakannya.
- **Hantar seluruh video kepada AI (disyorkan)** — dahulu "Mod video
  penuh", ditanda secara lalai untuk pengguna baharu. Aktif untuk
  OpenRouter, Gemini dan MiniMax. Ditanda: AI menonton seluruh video
  dan meletakkan setiap penerangan sendiri. Tidak ditanda: app
  menghantar gambar pegun satu demi satu (OpenAI dan Tersuai sentiasa
  begini).
- **Mod gambar pantas (OpenRouter): semua gambar dalam satu
  permintaan**: hanya bila kotak di atas tidak ditanda. Masa `H:MM:SS`
  dibakar pada setiap gambar (kotak gelap, penjuru kiri atas) dan semua
  gambar dihantar kepada AI dalam satu permintaan (pukal maksimum 150);
  app melekatkan semula masa pada grid gambar yang tepat. Kedua-dua
  kotak ini saling menolak.

### Tab Output Audio

Enjin suara (**Enjin TTS**: Edge TTS, SAPI5 (Windows), OpenAI TTS atau
**Pembaca skrin saya**), **Suara** dan **Kelajuan**.

**"Pembaca skrin saya"** dilabel dengan pembaca yang dijumpai (contoh
"Pembaca skrin saya (NVDA)") dan bercakap melalui NVDA, JAWS, ZDSR atau
apa sahaja yang sedang berjalan. Bila pilihan ini dipilih, Suara dan
Kelajuan dilumpuhkan — pembaca skrin anda yang menentukannya; ubah
dalam tetapan pembaca skrin itu sendiri. Jeda automatik dalam Player
masih berfungsi: sejak 1.7.1 app mendengar bunyi pembaca skrin itu
sendiri untuk tahu bila penerangan sudah habis. Jika tidak dapat,
Player memberitahu begitu dan tidak menawarkan kotak yang tidak
berbuat apa-apa.

Pada komputer yang **tiada** pembaca skrin langsung, aplikasi akan
bercakap sendiri (SAPI/OneCore Windows) untuk mesej status. Kalau
ada pembaca skrin, aplikasi diam supaya tiada yang dibaca dua kali.

## Semasa video diproses

Dialog kemajuan menunjukkan setiap fasa: "Memuatkan maklumat
video...", muat turun (peratus, MB, kelajuan, ETA, strim video dan
audio berasingan), "Menggabungkan video dan audio dengan ffmpeg...",
kemudian:

- seluruh video, mula-mula: "Mencari transkrip pertuturan..."; bila
  perlu "Memecahkan video panjang kepada beberapa bahagian..." dan
  "Menyediakan video untuk dimuat naik (memampat)...". Selepas itu
  bergantung pada pembekal:
  - **OpenRouter**: "Menyediakan video untuk dihantar...", "Memuat naik
    video ke penyedia AI..." dengan peratus, "AI sedang menonton video
    dan menulis penerangan..." dengan anggaran masa ("Lebih kurang 4
    minit lagi.") yang dipelajari daripada kerja anda sebelum ini untuk
    model yang sama, dan "Membaca jawapan AI...". Jika AI mengambil
    masa lebih lama daripada jangkaan, app berkata "Lebih lama daripada
    biasa; masih berjalan."
  - **Gemini** dan **MiniMax**: "Memuat naik video ke penyedia AI: N%",
    kemudian (Gemini) "AI sedang menonton video (pemprosesan)..." dan
    "AI sedang menulis penerangan...". Tiada anggaran masa di sini.
  - Jika semakan penerangan dihidupkan: "Menyemak penerangan dengan
    video...".
- gambar pegun: "Mengekstrak frame: N frame", "Analisis AI: N/M frame".

dan akhirnya "Menyimpan projek...". **Setiap peralihan fasa dan bahagian
dibaca secara automatik oleh pembaca skrin** (contoh: "Bahagian 2
daripada 2. Memuat naik video ke penyedia AI..."), tanpa memotong apa
yang sedang dibaca — anda tidak perlu menyemak dialog sendiri.

Bila pemprosesan selesai, dialog memaparkan "Pemprosesan selesai! N
penerangan dijana." Jika kerja gagal, kotak mesej bertajuk
"Pemprosesan gagal" dibuka, supaya pembaca skrin terus membaca
sebabnya. Sebab itu ditulis dalam perkataan biasa dalam bahasa app
(lihat "Jika ada masalah" di bawah); projek kosong **tidak** disimpan
senyap-senyap.

Jika anda menutup tetingkap utama semasa kerja sedang berjalan, kerja
itu dihentikan dengan selamat dan tetingkap Player serta Penyunting
ditutup dengan betul, dengan suntingan anda disimpan.

### Batal berhenti cepat, di mana-mana

Sejak 1.9.6 tetingkap kemajuan mempunyai SATU bar kemajuan untuk seluruh
kerja (muat turun, transkrip pertuturan, langkah AI, semakan). NVDA
melaporkannya semasa ia bergerak - bunyi bip, peratus disebut, atau
kedua-duanya, mengikut Tetapan NVDA > Object presentation > Progress bar
output. Bar itu tidak pernah undur; untuk langkah tanpa peratus sendiri
(Gemini menonton video) ia bergerak mengikut anggaran yang dipelajari
daripada kerja terdahulu. Nama langkah disebut sekali bila ia bertukar,
dan "Kira-kira N minit lagi" dipaparkan bila diketahui.

Sejak 1.9.6, Batal berfungsi dalam setiap langkah dan tidak membuat
anda menunggu:

- butang **Batal** (atau Esc) dialog kemajuan, termasuk selepas muat
  turun selesai;
- transkrip pertuturan berhenti dalam beberapa saat;
- muat naik atau permintaan kepada AI berhenti dalam kira-kira setengah
  saat;
- semakan penerangan dan analisis gambar pegun juga berhenti;
- **Eksport sebagai Audio** ada butang **Batal** sendiri;
- menutup **Penjelajah Adegan** menghentikan pemuatannya, dan **Batal**
  dalam **Tanya Lagi** meninggalkan soalan itu;
- dalam ejen Player, **Henti tanya**, **Henti semakan**, **Tutup** dan
  Esc menghentikan kerjanya (lihat "Ejen dalam Player (F2)").

### Muat turun yang terputus

Muat turun yang terputus **disambung dari tempat ia berhenti**, bukan
dimulakan semula. Tekan Cancel, tutup aplikasi, atau putus internet —
bila anda buka video yang sama sekali lagi, ia menyambung. Video yang
sudah siap tidak disentuh langsung, dan projek yang sudah ada videonya
tidak akan memuat turun semula.

**Muat naik** kepada AI yang terputus tidak disambung, dengan mana-mana
pembekal. Muat naik Gemini yang gagal dicuba semula secara automatik,
sehingga tiga kali kesemuanya, setiap kali dari mula. Jika app perlu
memampatkan video sebelum menghantarnya (OpenRouter), salinan yang
dimampatkan itu disimpan, jadi percubaan semula tidak perlu mengekod
semula video.

### Transkrip pertuturan dibuat sekali sahaja

Transkrip pertuturan dibuat sekali bagi setiap projek dan disimpan
dalam folder projek (`media\transcript.json`). Percubaan kedua pada
video yang sama, selepas Batal atau kegagalan, menggunakannya semula
dan tidak mentranskrip video sekali lagi.

## Bagaimana pemprosesan berfungsi (dan kenapa)

- **Video dimuat turun sekali sahaja.** Satu muat turun penuh (strim
  video + audio digabungkan oleh ffmpeg) cukup untuk keseluruhan
  penerangan.
- **Seluruh video (lalai):** fail video dihantar (dimuat naik ke Files
  API Gemini atau MiniMax, atau dihantar terus kepada OpenRouter) dan AI
  menontonnya serta memberi timestamp sendiri. Video panjang dipecahkan
  kepada bahagian (5 minit secara lalai) dan setiap bahagian membawa
  konteks ke bahagian seterusnya (bahagian X daripada Y, masa mulanya,
  dan ringkasan pendek apa yang berlaku sebelumnya), supaya nama watak
  kekal konsisten. Bahagian yang besar dimampatkan dahulu. Kebanyakan
  model tidak boleh mendengar video, jadi app memberi AI transkrip
  pertuturan (daripada sari kata video, atau tukar pertuturan ke teks)
  dan bilangan patah perkataan yang muat dalam setiap senyap.
- **Gambar pegun:** frame diekstrak secara lokal mengikut tetapan FPS
  anda, dan setiap satu dihuraikan dengan timestamp tepatnya sendiri,
  paling banyak satu penerangan setiap 4 saat. Terbaik untuk slaid dan
  rakaman skrin; untuk filem ia memberi lebih banyak penerangan yang
  terputus-putus.
- Semua mod menghasilkan penerangan ber-timestamp yang sama jenisnya;
  bezanya hanya siapa yang menentukan masa (proses ekstraksi berbanding
  AI) dan apa yang dihantar (gambar berbanding satu fail video).

## Projek

Setiap video yang diproses disimpan sebagai **projek**: video itu,
penerangan AI, dan fail SRT. Membuka projek semula TIDAK memanggil AI
lagi — jimat masa dan kos.

Projek disimpan dalam `Documents\OmniDescriber\projects`, satu folder
setiap projek yang dinamakan ikut projek itu, contohnya
`Sintel (48)`. Nombor dalam kurungan membezakan dua video yang sama
tajuk. Di dalamnya: `project.db` (penerangan) dan folder `media`
(video, `descriptions.srt` dan, selepas kerja seluruh video,
`transcript.json`, iaitu transkrip pertuturan).

**Fail > Buka Projek...** membuka senarai semua projek, terbaru
dahulu. Setiap baris menyebut nama, bilangan penerangan dan tarikh,
contohnya "Sintel — 79 penerangan — 28/09/2026 11:30". Butang:

- **Buka** (Alt+B) — muatkan projek itu untuk dimain, disunting atau
  dieksport. (Dalam 1.7.6 hingga 1.9.5 ini ranap; sejak 1.9.6 ia
  berfungsi semula.)
- **Namakan semula** (Alt+N) — beri nama baharu; foldernya juga
  ditukar. Kalau video projek itu sedang dimain, folder ditukar pada
  kali seterusnya app dibuka.
- **Buang** (Alt+A) — padam projek sepenuhnya, selepas pengesahan.

## Semak penerangan dengan video (Tetapan > Am)

Bila seluruh video dihantar, AI kadang-kadang menghurai peristiwa yang
betul pada saat yang salah. **Semak penerangan dengan video** (**Mati**
secara lalai) memeriksa setiap penerangan dengan bingkai di
sekelilingnya, lalu mengalihnya ke saat sebenar atau membuangnya jika
tiada langsung. Diukur pada dua filem: penerangan salah kira-kira
separuh. Menambah beberapa minit dan kos kecil. Jika semakan gagal,
penerangan asal disimpan.

- **Auto (app memilih)** — Paling tepat untuk video panjang, Kekalkan
  semua untuk yang pendek.
- **Paling tepat (mungkin buang sedikit)** — paling sedikit salah.
- **Paling banyak penerangan** — paling banyak yang betul.
- **Kekalkan semua, betulkan masa sahaja** — tiada yang dibuang.

## Bahasa anda sendiri (Bantuan > Laporan Terjemahan)

Fail bahasa yang anda buat atau betulkan disimpan dalam
`%APPDATA%\OmniDescriber\locales\` dan tidak hilang semasa app
dikemas kini. Selepas kemas kini, **Bantuan > Laporan Terjemahan...**
memberitahu berapa baris bahasa anda yang belum diterjemah dan
menyimpan baris-baris itu sahaja, bersama teks Inggerisnya, sebagai
`<kod>.missing.json` dalam folder itu. Panduan penuh:
`doc/menambah-bahasa.md`.

## Semak Kemas Kini (menu Bantuan)

YouTube kerap berubah, dan yt-dlp (program yang memuat turun video)
versi lama boleh berhenti berfungsi. **Bantuan > Semak Kemas Kini...**
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
- Semasa main balik, penerangan semasa dibacakan dan ditunjukkan
  sebagai teks, dengan penerangan seterusnya di bawahnya.
- **Main**, **Henti**, **<< 10s** dan **10s >>** mengawal main balik;
  **Baca Penerangan** membaca penerangan semasa sekali lagi.
- **Jeda video semasa penerangan dibaca**: menahan video sehingga
  penerangan habis, kemudian sambung semula — berguna untuk slaid,
  tutorial dan video yang padat dialog.
- **Gambar video** (Tab ke sana; NVDA membaca kekuncinya): **Space**
  main atau jeda; **Kiri/Kanan** melompat 5 saat, dengan **Ctrl** 10
  saat, dengan **Ctrl+Shift** 1 minit, dan kedudukan baharu disebut ("1:09 daripada 24:30");
  **Atas/Bawah** menukar kelantangan video 10% setiap kali (suara pembaca
  skrin tidak berubah). Kelantangan diingati.
- **Penyunting Penerangan**, **Tanya Lagi...**, **Jelajah Adegan...**
  dan **Ejen (F2)** membuka tetingkap yang diterangkan di bawah. Sejak
  1.9.7 Player memaparkan SAMA ADA ejen ATAU dua alat lama: bila ejen
  sedia (OpenRouter atau Gemini, ada kunci, dan model sudah lulus Uji mod
  ejen) hanya **Ejen (F2)** dipaparkan, kerana ia sendiri boleh melihat
  video dan menjawab soalan; tanpa ejen, **Tanya Lagi...** dan **Jelajah
  Adegan...** dipaparkan. Untuk model yang belum diuji, ketiga-tiganya
  dipaparkan; bila ujian lulus, dua alat lama itu hilang.

## Ejen dalam Player (F2)

Dalam Player, tekan **F2** (atau butang **Ejen (F2)**) dan tanya
apa-apa tentang video dalam bahasa anda sendiri: "adakah penerangan di
sini betul?", "apa berlaku di jambatan?", "lelaki tua itu bernama
Hans". Ejen melihat bingkai video, membaca penerangan dan dialog,
mencari jurang senyap, dan boleh mengalih Player. Video dijeda semasa
ejen dibuka.

Ejen **tidak mengubah apa-apa sendiri**. Ia mencadangkan; anda mendengar
ringkasan, kemudian pilih **Terima semua**, **Semak satu per satu** atau
**Tolak semua** (Esc = tolak). Fail sari kata projek disalin dahulu
sebelum perubahan pertama, dan **Buat asal perubahan terakhir**
sentiasa ada. Setiap langkah disebut. Perbualan diingat sehingga Player
ditutup; nama watak diingat untuk projek itu. Jika satu soalan menelan
lebih daripada beberapa sen, ejen bertanya dahulu sebelum meneruskan.

**Semak seluruh video** (butang dalam tetingkap ejen) menyemak setiap
penerangan, seminit video pada satu masa, lalu memberi SATU senarai
cadangan untuk anda terima, semak atau tolak. Masa dan kos disebut
dahulu.

Anda boleh menghentikan ejen pada bila-bila masa:

- Semasa ejen menjawab soalan, butang **Tanya** menjadi **Henti tanya**
  (Alt+T). Tekan untuk berhenti.
- Semasa ejen menyemak seluruh video, butang itu menjadi **Henti
  semakan**.
- **Tutup** atau Esc juga menghentikan apa sahaja yang ejen sedang
  buat, supaya tiada permintaan terus dibayar selepas tetingkap
  ditutup.

Ejen berfungsi dengan model **OpenRouter** dan model **Gemini** (kunci
Gemini anda sendiri, sejak 1.9.2) yang sudah lulus **Tetapan > Uji mod
ejen**. Jika anda menekan F2 dengan model yang belum lulus, Player
menawarkan untuk menjalankan ujian itu terus di situ ("Ejen belum diuji
dengan <model>. Uji sekarang? Ia mengambil kira-kira setengah minit dan
kosnya sebahagian kecil satu sen."). Jika ujian lulus, ejen dibuka.
Jika anda menjawab Tidak, ujian gagal, atau pembekal tiada ejen, F2
membuka **Tanya Lagi** sebagai ganti, yang menghantar bingkai pada
kedudukan Player bersama soalan anda. Dalam Tanya Lagi, **Batal** (atau
Esc) meninggalkan soalan yang masih menunggu jawapan.

## Penjelajah Adegan

(Sejak 1.9.7 video panjang memuatkan kira-kira 600 bingkai, jadi
penjelajah lebih cepat sedia; semasa masih memuat, D dan L
memberitahunya dan bukan lagi "No AI configured".)

Dari pemain, **Jelajah Adegan...** membuka Penjelajah Adegan untuk
menyemak frame satu demi satu: kunci anak panah kiri/kanan untuk
bergerak antara frame, `D` untuk penerangan penuh AI bagi frame semasa,
`L` untuk senarai objek dalam frame, Enter untuk menghuraikan objek
terdekat, dan `Escape` untuk menutup. Menutup Penjelajah Adegan semasa
ia masih memuatkan frame menghentikan pemuatan itu.

## Penerang video berdikari (baris perintah + API HTTP)

Selain aplikasi GUI, repositori ini memuat pakej berdikari
`video_describer` (tiada hubungan kod dengan GUI). Ia membakar cap masa
`H:MM:SS` (kotak gelap, penjuru kiri atas) pada setiap frame yang
diekstrak ffmpeg, menghantar SEMUA frame base64 dalam SATU permintaan
`glm-5.3-flash`, membiarkan model MEMBACA cap masa yang tertera, kemudian
mengekstrak baris `H:MM:SS - penerangan` menjadi satu fail SRT dan satu
fail JSON (batch automatik melebihi 150 frame; had 5 MB dan 6000 px
setiap frame).

Untuk `describe`, output diletakkan dalam folder yang dinamakan ikut
video, di dalam folder video itu (`<folder video>\<nama video>\`), dan
fail-failnya dinamakan ikut video: `<nama video>.srt` dan
`<nama video>.json` (`--out` memilih folder lain).

Secara lalai ia berhubung **terus dengan Zhipu**
(`https://open.bigmodel.cn/api/paas/v4`, model `glm-5.3-flash`), jadi
`GLM_API_KEY` mesti kunci Zhipu, bukan kunci OpenRouter `sk-or-v1-`.
`--base-url` dan `--model` mengubahnya.

```bat
:: Terangkan satu video tempatan (SRT + JSON dalam <folder video>\<nama video>\)
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
`ms-MY-OsmanNeural`) atau SAPI5 Windows (`--tts-engine sapi`); satu
fail audio bagi setiap penerangan diletakkan dalam folder `audio\` di
dalam folder output (tiada fail audio gabungan dibuat).

Alat berdikari ini lebih lama daripada enjin app sekarang; app itu
sendiri tidak menggunakannya.

## Jika ada masalah

1. Baca log di
   `%LOCALAPPDATA%\OmniDescriber\logs\omni_describer.log`; setiap
   kegagalan direkod dengan sebab sebenar.
2. Semak tetapan AI (kunci API, model, URL asas) dan tekan **Uji model
   ini**.
3. Sejak 1.9.6 mesej ralat ditulis dalam perkataan biasa dalam bahasa
   app, tanpa teks teknikal (butiran penuh ada dalam log). Maksudnya
   dan apa yang perlu dibuat:
   - **"Perkhidmatan AI sedang sibuk (terlalu banyak permintaan).
     Tunggu beberapa minit dan cuba lagi, atau pilih model lain dalam
     Tetapan > AI."** Pembekal sedang mengehadkan anda (HTTP 429).
     Dengan setiap pembekal, termasuk OpenRouter, app sudah menunggu
     selama yang diminta pembekal (sehingga kira-kira seminit) sebelum
     mencuba semula. Jika mesej ini masih keluar, buat seperti yang
     disebut.
   - **"Kuota harian penyedia AI untuk model ini sudah habis. Ia
     dipulihkan pada tengah malam waktu Pasifik (jam 3 hingga 4 petang
     waktu Malaysia). ..."** Kunci anda sudah menghabiskan kuota
     permintaan harian (contohnya peringkat percuma Gemini). Menunggu
     beberapa minit tidak membantu: tunggu sehingga kuota dipulihkan,
     pilih model atau pembekal lain, atau naikkan projek kunci itu ke
     peringkat berbayar yang menaikkan hadnya.
   - **"Penyedia AI menolak video kerana terlalu besar, walaupun
     selepas app mengecilkannya. ..."** Dengan OpenRouter, app sudah
     menghantar bahagian itu semula, lebih kecil setiap kali, sehingga
     tiga kali. Pilih model lain, atau tetapkan **Panjang bahagian
     video** yang lebih pendek dalam Tetapan > Am.
   - **"Penyedia AI menolak kunci API ..."**: kunci tidak sah, atau
     tidak dibenarkan untuk model ini. Semak dalam Tetapan > Tetapan AI
     dan tekan **Uji model ini**.
   - **"Penyedia AI mengatakan kredit akaun ini tidak mencukupi.
     ..."**: tambah nilai di laman web penyedia, atau pilih pembekal
     lain.
   - **"Tidak dapat menghubungi penyedia AI (tiada sambungan, atau ia
     tidak menjawab dalam masa). ..."**: semak sambungan internet dan
     cuba lagi.
   - **"Penyediaan video untuk AI gagal (...)"**: cuba lagi; jika
     berulang, fail video mungkin rosak.
   - **"Laman video menolak muat turun (HTTP 403), walaupun selepas
     mencuba semula. ..."**: tunggu seminit dan cuba lagi; jika
     berulang, kemas kini yt-dlp dengan **Bantuan > Semak Kemas
     Kini**.
4. Untuk video panjang yang dihantar sebagai gambar pegun, pertimbangkan
   FPS lebih rendah (contohnya 1) atau tetapkan **Had Maksimum Frame
   Setiap Video**.
