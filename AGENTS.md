# AGENTS.md — Omni Describer Custom

Arahan untuk coding agent (Hermes, jcode/evergreen, Claude, dll.) yang bekerja dalam projek ini.
Baca fail ni dulu SEBELUM buat apa-apa perubahan.

## Apa Projek Ini

Aplikasi desktop **penerangan video berasaskan AI untuk pengguna buta (NVDA screen reader)**.
wxPython GUI, Windows sahaja. Python 3.13.

Pipeline: download video (YouTube/URL/fail) → extract frame ATAU hantar video penuh
→ AI describe bertimestamp → TTS narrasi + SRT + Player Window.

Pengguna utama = pemilik repo sendiri (buta, BM Malaysia). **Aksesibiliti bukan optional —
ia keperluan utama.** Label screen reader, status announce, dan dialog berstruktur WAJIB
dikekalkan dalam setiap perubahan UI.

## Peraturan Wajib (hard rules)

1. **GATE SEBELUM COMMIT.** Jalankan `run_gate.bat` selepas setiap perubahan kod.
   Commit hanya bila `GATE_ALL_PASS`. Gate = compileall + 53 test suite
   (unit, E2E real-GUI, acceptance, pipeline, packaging).
   **Gate FAIL yang "kadang-kadang" BUKAN flake sampai dibuktikan.** v1.5.5:
   test_fixes12 gagal ~1 daripada 3 run; puncanya bug sebenar dalam app
   (ghost dialog), bukan test. Jalan suite yang gagal 10 kali sebelum
   melabelnya flaky.
2. **JANGAN pecahkan aksesibiliti.** Setiap widget baharu perlu `name=`/label NVDA.
   Status changes mesti di-announce (lihat corak `SetStatusText` + focus move dalam main_frame.py).
3. **JANGAN guna Opus Proxy** — provider tu dah dibuang sepenuhnya (v1.5.3, kuota habis).
   Provider aktif: **GLM via OpenRouter** (z-ai/glm-5.3-flash), Gemini, MiniMax, custom OpenAI-compatible.
   Model mesti support video kalau mod video dipilih — semak katalog, jangan agak nama model.
4. **API key TIDAK ditulis dalam kod/chat.** Key dibaca dari settings.json (terenkripsi)
   atau env var. Agent TIDAK PERNAH taip password/token ke mana-mana.
5. **Bahasa UI dwi (EN + BM).** Semua string user-facing melalui i18n (`src/omni_describer_custom/i18n/strings.py`).
   Tambah kedua-dua versi. Bahasa penerangan mesti konsisten merentas semua AI paths (v1.5.2).
6. **Commit konvensyen:** mesej ringkas, jenis dulu (`feat:`, `fix:`, `test:`, `docs:`, `release:`).
   Version bump + README changelog bila release (`__version__` dalam `src/omni_describer_custom/__init__.py`
   = sumber tunggal versi).
   **Penomboran (arahan pemilik, 23 Sep 2026):** digit terakhir berhenti pada 9.
   Selepas 1.6.9 ialah **1.7.0**, bukan 1.6.10; selepas 1.7.9 ialah 1.8.0.
   (1.7.0 dan 1.7.1 asalnya ditag 1.6.10 dan 1.6.11, kemudian dinamakan semula.)
7. **Fail untracked `VEDIO DESCRIBER.PY.txt` JANGAN disentuh** — sketch pemilik, asal package `video_describer`.
8. **Kerja latar (background) boleh terorphan** kalau server agent restart — build PyInstaller
   JALAN FOREGROUND (8-10 minit) supaya tak terputus.

## Arkitektur Minimum

```
main.py                          — entry point
src/omni_describer_custom/
├── __init__.py                  — __version__ (sumber tunggal)
├── core/
│   ├── ai_engine.py             — semua AI provider (GLM/OpenRouter, Gemini, MiniMax,
│   │                              custom); frame mode + fast one-shot + full-video mode;
│   │                              auto-compression; chunked processing
│   ├── video_processor.py       — ffmpeg frame extraction, burn-in timestamp, download
│   ├── tts_engine.py            — TTS (SAPI5 win32com, fallback chain)
│   ├── settings_store.py        — settings.json (API key terenkripsi)
│   ├── prompt_manager.py        — preset prompts per-bahasa
│   ├── project_store.py         — named projects, persist video/media
│   ├── timeline_io.py           — import/export SRT/VTT/TXT/audio segerak
│   └── tools.py                 — SATU tempat cari ffmpeg/ffprobe/ffplay/
│                                  yt-dlp (bundle dulu, PATH kemudian)
├── ui/
│   ├── main_frame.py            — window utama, pipeline _process_video, semua handler
│   ├── settings_dialog.py       — tabbed settings (General/AI/Audio)
│   ├── player_window.py         — player + subtitle overlay + TTS narrasi
│   ├── editor_window.py         — edit penerangan per-cue
│   └── scene_explorer.py        — browse frame + penerangan
└── i18n/
    ├── strings.py            — pemuat + API t()
    └── locales/<kod>.json    — satu fail satu bahasa (lihat doc/menambah-bahasa.md)
tests/                           — 53 suite; run_gate.bat = semua
bin/                             — ffmpeg/ffprobe/ffplay/yt-dlp terbungkus
                                   (TIDAK dalam git; tools/fetch_binaries.py)
doc/                             — panduan-pengguna.md (BM), README
build.bat                        — compile → PyInstaller → smoke test → zip (FOREGROUND)
```

**Aliran data:** MainFrame._process_video → download/extract (video_processor) →
AI describe per frame ATAU chunked full-video (ai_engine) → Description dataclass
(id, start_time, end_time, text, edited, created_at, frame_path) → Player/SRT/TTS/export.

## Pitfall (perangkap yang selalu tersandung)

1. **Mod video penuh ≠ timestamp tepat.** Frame mode = timestamp kita tentukan (tepat);
   full-video = AI agak sendiri. Jangan campur EXPECTATION antara dua mod ni dalam test.
2. **Chunked processing perlukan konteks antara bahagian** — part X of Y + ringkasan
   bahagian sebelumnya + larangan "video starts with" + nama watak konsisten.
   Kalau tambah mode baharu, salin corak ni (v1.5.3).
3. **DirectUI progress bar tiada msctls_progress32** — E2E baca percent via
   GetWindowTextW (tajuk dialog) + PrintWindow pixel scan, BUKAN PBM_GETPOS.
4. **TTS SAPI5:** guna win32com SpFileStream terus, BUKAN runAndWait (masa lalu menyebabkan
   bunyi tak keluar).
5. **wx GUI test** perlu pytest-style wx app init — lihat test_fixes15 sebagai contoh betul.
   GUI test dalam gate instantiasi dialog sebenar.
6. **Monaco/CodeMirror tidak ada** dalam GUI ni (wxPython) — browser automation tools
   tak releven; untuk GUI automation guna pywinauto UIA + raw Win32 (lihat tools/ dan
   test E2E).
7. **Model reasoning besar (GLM)** perlukan max_tokens ~6000 — timeout dah dibump;
   jangan kurangkan tanpa test real.
8. **`wx.ProgressDialog` PUMP event loop dalam constructor-nya.** Handler
   `wx.CallAfter` yang beratur boleh jalan DALAM constructor itu, sebelum
   `self._dl_dialog` di-assign. Sebab tu `_ensure_download_progress` guna
   kaunter `_dl_close_gen`: kalau cleanup berlaku semasa dialog sedang dibina,
   dialog baharu itu dibuang (v1.5.5). Corak sama perlu untuk mana-mana dialog
   modal baharu yang dicipta dari CallAfter.
9. **Output test MESTI line-buffered.** `io.TextIOWrapper(...)` yang dibina
   sendiri mengabaikan `python -u`; bila proses crash, buffer hilang dan gate
   cetak log KOSONG (v1.5.5: crash tersembunyi berbulan). Semua fail dalam
   `tests/` guna `line_buffering=True`.
10. **Frame wx perlu di-drain sebelum Destroy** dalam test: worker thread
   masih ada `wx.CallAfter` beratur; Destroy dulu = access violation.
   Lihat `_drain_events`/`_destroy_frame` dalam `tests/test_fixes12.py`.
11. **wxPython Phoenix: TIADA `SetYesLabel`/`SetNoLabel`/`SetCancelLabel`.**
   Guna `SetYesNoCancelLabels(yes, no, cancel)`. Bug v1.5.5: butang Open
   TIDAK BUAT APA-APA untuk video yang sudah ada projek (AttributeError
   dalam `_start_processing`). Sama keluarga dengan `MenuBar.SetLabelTop`.
   **Semak `hasattr` dulu sebelum guna API wx yang jarang dipakai.**
12. **`SetLabel()` MEMAKAN state kawalan pada MSW.** `wx.Choice` hilang
   SELECTION; `wx.TextCtrl` teksnya DIGANTI dengan label itu. v1.5.4 guna
   SetLabel untuk nama NVDA pada 3 kawalan → setiap lancaran baharu tiada
   preset dipilih (Open jawab "Please select a prompt preset") dan kotak
   prompt mengandungi labelnya sendiri, yang dihantar ke AI sebagai
   "User notes". Guna `MainFrame._set_accessible_name()` (v1.5.6/1.5.7).
   **Untuk TextCtrl guna `SetName`, jangan `SetLabel`.**
13. **Prompt MESTI ikut piawaian audio description, bukan "huraikan semua".**
   Sumber: DCMP Description Key, Netflix AD Style Guide v2.1, W3C/WAI,
   ADLAB. Teras: huraikan hanya yang perlu untuk memahami; JANGAN huraikan
   apa yang sudah kedengaran (dialog/muzik/bunyi); kala kini, orang ketiga;
   lapor yang boleh dilihat, bukan tafsiran; jangan teka bangsa/jantina;
   cukup pendek untuk dituturkan. Preset ikut STRATEGI, bukan genre —
   piawaian guna peraturan sama untuk semua genre (Netflix namakan dua
   sahaja: kanak-kanak, horror/suspense). `prompt_manager.DEFAULT_PROMPTS`
   = SATU sumber prompt; `tests/test_fixes22.py` mengunci peraturan ini.
   Preset lama dibuang hanya kalau teksnya masih teks asal kita (edit
   pengguna tidak pernah disentuh).
14. **Model TIDAK mematuhi permintaan penempatan cue — guna mekanisme.**
   Prompt v1.6.3 minta ia letak penerangan dalam celah antara pertuturan
   (transkrip ada timestamp). Diukur: diberi transkrip dengan lubang 55
   saat sengaja, ia letak 9 cue dalam separuh bercakap dan 7 dalam
   separuh senyap — 56% masih dalam yang bising. Ia memilih tempat
   sesuatu BERLAKU secara visual, bukan tempat audio lapang.
   **Jawapan yang boleh diharap = togel jeda pemain**
   (`player.pause_for_narration`), bukan ayat dalam prompt. Peraturan
   prompt dikekalkan kerana ia betul dan percuma, bukan kerana ia
   berkesan. Untuk kandungan padat dialog + aksi laju (contoh: video
   Ocong, 91% pertuturan), jeda automatik memang cara yang betul —
   itu kes *extended description* W3C.
15. **GLM TIDAK BOLEH MENDENGAR audio video.** Diprob 20 Sep 2026: diminta
   transkripkan ayat pertama, ia jawab "NO AUDIO ACCESS". Ia lihat frame
   sahaja. Sebab itu preset `foreign` mustahil tanpa transkrip, dan arahan
   lama "describe visuals AND sounds/speech" memang tidak pernah tercapai.
   Penyelesaian: `VideoProcessor.get_transcript()` (sari kata → sari kata
   terbenam → Grok STT/Whisper) + `build_transcript_block()`.
   `provider_hears_audio()` menyimpan keupayaan ini per-provider.
16. **Suffix enjin DITAMBAH SELEPAS prompt, jadi apa yang ia kata MENANG.**
   Ia tidak boleh ada pendapat tentang APA yang dihurai — dua kali ia
   membatalkan preset secara senyap (v1.6.0: "AND sounds/speech", kemudian
   "important VISUALS" yang membunuh `foreign`). Format sahaja di situ.
17. **`OmniDescriber.spec` DIJANA SEMULA oleh PyInstaller** daripada bendera
   dalam `build.bat` setiap kali. Mengeditnya sia-sia — tukar `build.bat`.
18. **Handler = permukaan yang paling kerap terlepas.** Sebelum
   `tests/test_fixes21.py` (17 Sep 2026) TIADA satu pun handler menu/butang
   tetingkap utama dipanggil oleh mana-mana test — tetingkap diuji, handler
   yang membukanya tidak. Di situlah bug butang Open mati bersembunyi.
   **Tambah handler baharu = tambah check dalam test_fixes21.**
19. **Test MESTI guna settings terasing.** `run_gate.bat` set
   `ODC_CONFIG_DIR=%TEMP%\odc_gate_config`; `SettingsStore` hormat env var
   itu. Sebelum v1.5.5 gate menulis ke `settings.json` SEBENAR pengguna
   (Gemini provider jadi `http://127.0.0.1:.../v1beta` + key `test-key`).
   Jangan buang env var ni, dan jangan set dalam tool E2E — E2E memang
   perlu settings sebenar (key GLM).
20. **Cari program luar HANYA melalui `core/tools.py:find_tool()`.**
   Sebelum v1.6.5 ada LIMA tempat berasingan (`video_processor`,
   `player_window`, `tts_engine`, `timeline_io`, `ai_engine`) dan hanya
   satu tahu tentang folder `bin/`. Itulah sebab pemain terbungkus senyam
   walaupun app lain berfungsi. `tests/test_fixes25.py` gagalkan gate
   kalau ada call site buat carian sendiri — disahkan menangkap
   kesemua 11 baris versi lama.
21. **Binari luar TIDAK dalam git (217 MB).** `tools/fetch_binaries.py`
   muat turun ke `bin/`; `build.bat` langkah [1/5] jalankannya. Clone
   baharu TANPA langkah ini menghasilkan app yang nampak siap tapi gagal
   pada muat turun pertama.
22. **ffmpeg terbungkus ialah binaan GPL, bukan LGPL** — `ai_engine`
   encode dengan `libx264` yang hanya wujud dalam binaan GPL. Kalau
   seseorang tukar ke LGPL untuk jimat obligasi, mampatan muat naik
   akan pecah. Obligasi dicatat dalam `NOTICE.md`; jangan buang
   `bin/FFMPEG-LICENSE.txt` atau `bin/FFMPEG-VERSION.txt`.
23. **PyInstaller DUPLIKASI setiap .dll dalam `--add-data`.** Ia kenal
   fail itu sebagai pustaka lalu tulis salinan kedua ke `_internal\`
   selain dalam `bin\` — 189 MB terbuang dalam binaan 1.6.5 pertama
   (avcodec sahaja 118 MB). `tools/dedupe_build.py` buang salinan yang
   BYTE-IDENTICAL sahaja dan gagalkan binaan kalau berbeza.
   `test_packaging_content.py` jaga supaya ia tak kembali.
24. **Jeda naratif hanya untuk enjin yang tahu bila ayat habis.**
   `HOLD_CAPABLE_ENGINES` = jawapan SANDARAN (edge, sapi5, openai)
   bila tiada objek enjin untuk ditanya. Sejak v1.6.6
   `supports_narration_hold` tanya instance dulu (`supports_hold`),
   jadi Prism-atas-SAPI dapat jeda dan Prism-atas-NVDA tidak.
25. **Prism = suara pada mesin TANPA pembaca skrin.** `core/speech.py`.
   `_announce` guna fokus MSAA/UIA (berfungsi dengan SEMUA pembaca
   skrin, bukan NVDA sahaja) — tetapi SENYAP kalau tiada pembaca skrin
   langsung. `speech.announce()` bercakap HANYA dalam kes itu; kalau
   pembaca skrin ada ia diam supaya tidak bercakap dua kali.
26. **Keupayaan backend Prism BERBEZA jauh — jangan andai.** Diukur
   22 Sep 2026: NVDA `supports_is_speaking=False`, `set_rate=False`,
   `set_voice=False`, `speak_to_memory=False`. SAPI/OneCore semuanya
   True. Sebab itu Voice dan Speed dilumpuhkan bila `screen_reader`
   dipilih. Baca dari backend HIDUP (`features`), bukan dari nama enjin.
   **DIBETULKAN v1.7.1:** entri ini dahulu berkata jeda naratif juga
   TIDAK BOLEH untuk pembaca skrin. Itu terlalu mutlak — lihat pitfall
   46. NVDA sendiri memang tidak melaporkan, tetapi bunyinya boleh
   didengar berhenti.
27. **`ODC_PRISM_BACKEND` paksa satu backend ikut nama** ("SAPI",
   "NVDA", "OneCore"). Tanpa ini cabang "tiada pembaca skrin" TIDAK
   BOLEH diuji pada mesin pemilik (NVDA sentiasa berjalan).
   `test_fixes26.py` guna subprocess kerana `PrismSpeech` singleton
   mengikat backend pada penggunaan pertama.
28. **Enjin yang `speaks_directly` TIDAK hasilkan fail.**
   `speak_and_play` mesti bercabang SEBELUM `speak()`, kerana `speak()`
   anggap laluan kosong sebagai gagal lalu jatuh ke enjin lain — suara
   yang user pilih akan diganti senyap. Eksport audio tetap guna enjin
   berasaskan fail.
29. **AKSESIBILITI DISAHKAN DENGAN MENDENGAR, bukan membaca kod.**
   `tools/nvda_accessibility_check.py` tab keliling tetingkap sebenar
   lalu tanya NVDA apa yang diumumkan, melalui NVDA HTTP Bridge
   (`http://127.0.0.1:19281`, plugin dalam scratchpad NVDA; repo di
   `C:\Users\USER\nvda-http-bridge`). Pitfall 12 lolos dulu KERANA
   kod nampak betul. Jalankan selepas apa-apa perubahan UI:
   ```
   python tools/nvda_accessibility_check.py --steps 12
   ```
   Perlu NVDA berjalan; tanpa bridge ia keluar kod 2 (BUKAN 0) supaya
   "tak disahkan" tidak disalah baca sebagai "lulus". Logik penilaian
   ialah fungsi tulen dan diuji dalam `test_fixes27.py` — pengesan yang
   tak pernah dilihat gagal bukan pengesan.
   Disahkan 22 Sep 2026: combo sebut "combo box default collapsed"
   (preset memang terpilih), kotak prompt sebut teks AD sebenar bukan
   labelnya sendiri.

30. **Muat turun MESTI masuk folder media projek.** yt-dlp sambung
   `.part` secara lalai; sebelum v1.6.7 setiap percubaan guna
   `mkdtemp` baharu jadi fail separa jadi yatim. Sebab itu projek kini
   dicipta SEBELUM muat turun (`_ensure_project_for`), bukan selepas AI
   siap. Jangan pulangkan ordering itu.
   **ADA TIGA PINTU MASUK muat turun, bukan satu.** Dua panggil
   `vp.resolve_source(...)` terus (mod video penuh); yang KETIGA ialah
   mod bingkai — laluan LALAI — yang panggil `vp.extract_frames(source)`
   dan resolve URL di dalamnya. Menampal dua yang pertama sahaja nampak
   betul dalam diff dan tetap salah: mod bingkai masih guna temp dir.
   `test_fixes28` kira pintu masuk lawan yang berwayar supaya pintu
   keempat tak boleh ditambah senyap.
31. **JANGAN pilih fail muat turun dengan `sorted(glob("video.*"))[0]`.**
   `video.f616.mp4` (aliran video sahaja, belum bercantum) datang
   SEBELUM `video.mp4` ikut abjad — app akan huraikan video SENYAP.
   Guna `VideoProcessor.completed_download()`: fail bercantum ada
   TEPAT satu suffix, yang perantaraan ada dua.
32. **`_compress_to` out_dir kini boleh jadi folder media projek.**
   JANGAN `rmtree(out_dir)` bila gagal — itu akan padam video pengguna.
   Padam fail output sahaja (`out.unlink`).
33. **Fail pementasan ffmpeg MESTI kekal sambungan sebenar.** ffmpeg
   pilih muxer ikut extension; `.part` gagal terus dengan "Error
   initializing the muxer ... Invalid argument". Guna
   `nama.partial.mp4`, bukan `nama.part`.
34. **Susunan Tab wx ikut urutan PENCIPTAAN, bukan urutan sizer.**
   Butang baharu yang ditambah ke sizer di tengah tetap jadi TERAKHIR
   bawah Tab. Guna `MoveAfterInTabOrder(kawalan_sebelumnya)` lalu
   sahkan dengan `tools/nvda_accessibility_check.py`.
35. **Petunjuk prestasi JANGAN bunuh kerja.** `upload_cache_dir`
   ditetapkan dari dalam saluran pemprosesan; setter asal guna
   `self._providers` terus dan meletup pada `AIEngine.__new__()` —
   seluruh kerja mati dengan "no descriptions saved". Guna `getattr`
   + try/except untuk apa-apa yang sekadar mengoptimumkan.
36. **Bendera build ≠ hasil build. SEMAK `dist/` SEBENAR.** v1.6.6
   hantar Prism dengan `--collect-all prism` dan ujian semak bendera
   itu dalam `build.bat` — lulus. App yang dihantar log "No module
   named 'prism._prism_cffi'" dan ciri suara pembaca skrin MATI
   sepenuhnya. Sebabnya `prism/_native.py` tambah folder ke `__path__`
   ketika RUNTIME, jadi PyInstaller tak nampak extension itu.
   `hooks/hook-prism.py` membetulkannya. **Ujian pembungkusan MESTI
   baca fail dalam `dist/`, bukan bendera dalam `build.bat`.**
37. **ADA DUA tempat pembersihan bahagian video, bukan satu.**
   `_describe_video_part` (satu bahagian) DAN blok `finally` dalam
   laluan chunked yang `unlink` setiap `part != path`. Yang kedua
   memadam salinan cache muat naik, jadi cache v1.6.7 tak pernah
   bertahan satu kerja pun dalam mod video penuh. Kedua-duanya kini
   semak `is_cached_upload()`.
38. **Log MESTI cetak LALUAN PENUH, bukan nama fail.** "Compressed
   upload copy kept for retries: upload_xxx.mp4" nampak betul
   sedangkan fail itu ditulis lalu dipadam — nama sahaja tak dapat
   bezakan "disimpan" daripada "disimpan lalu dibuang".
39. **Folder temp yang ditinggalkan TIDAK pernah dibersihkan** sebelum
   v1.6.7: 115 folder muat turun = 806 MB pada mesin pemilik.
   `core/housekeeping.py` sapu prefix `odc_*` yang berumur >24 jam
   ketika app dibuka. **Tambah prefix `mkdtemp` baharu ke
   `_OUR_PREFIXES`** — `test_fixes29` gagalkan gate kalau terlupa.
40. **Automasi GUI: TIGA cara "berjaya" tanpa berbuat apa-apa.**
   (a) UIA `invoke()` — butang wx tak melaksanakannya; (b)
   `click_input()` dengan app di latar — klik mendarat pada tetingkap
   lain; (c) `click_input()` walaupun di hadapan — butang Open hanya
   **15 piksel lebar** (combo preset ambil baris itu). Guna navigasi
   Tab + sahkan fokus melalui NVDA bridge, kemudian Enter. Lihat
   `tools/e2e_full_verify.py:focus_and_activate`.
41. **Endpoint mentah NVDA bridge TIADA pembalut `data`** — hanya CLI
   yang menambahnya. `r.get("data", r)`, bukan `r["data"]`.
42. **Transkrip Whisper tempatan DAHULUNYA tidak menentu** (dibaiki v1.6.9).
   Fail sama, model sama (`base`), tiga larian melalui
   `get_transcript`: dialog pertama dilaporkan pada 30.0s, 30.0s, lalu
   0.0s; liputan 40%, 32%, 93%. Puncanya fallback suhu
   faster-whisper yang MENSAMPEL secara rawak bila ambang logprob
   gagal. **Bajet jurang (v1.6.8) hanya sebaik transkrip ini** —
   jangan anggap jurang yang dilaporkan itu pasti.
   **CUBAAN YANG GAGAL, jangan ulang:** `beam_size=5 + vad_filter=True`
   menjadikannya LEBIH TERUK — liputan jatuh ke 20% dan VAD membuang
   pertuturan sebenar (dialog pertama dilaporkan 40.0s, bukan 30.0s).
   Diukur 22 Sep 2026. Kalau hendak baiki, ukur dahulu; jangan tukar
   tetapan kerana ia "sepatutnya lebih baik".
43. **Model TAHU tempat dialog, tetapi TIDAK tahu berapa ruang.**
   Diperiksa: transkrip memang dihantar (921 aksara, baris bertimestamp
   + arahan guna jurang), dan penempatan cue sebenarnya baik. Yang
   hilang ialah aritmetik — klip 50s ada ~77 patah ruang, model tulis
   97 lalu 99. `_gap_budget_block()` kini senaraikan setiap jurang dan
   bilangan patah yang muat, berskala dengan kelajuan TTS pengguna.
   Ini corak pitfall 14: beri nombor, bukan permintaan.
44. **UJI PADA VIDEO YANG BENAR-BENAR BERBEZA, bukan potongan dari
   satu video.** Penanda aras pertama saya ambil tiga keping dari SATU
   video dan menyimpulkan model `small` ialah jawapannya (0 halusinasi
   lwn 32). Pada tujuh video berasingan ia TERBALIK — `small` beri 12
   halusinasi, `base` beri 2. Mengukur satu video tiga kali ialah
   mengukur satu video. `tools/whisper_bench.py` ada set yang betul:
   berita Melayu, ceramah Inggeris, vlog bermuzik, dua kartun
   Indonesia, rakaman amatur, dua klip TTS berkebenaran diketahui.
45. **DUA jenis halusinasi Whisper, hanya satu boleh ditapis.**
   (a) Gelung berulang — "Mememe..." 27 saat, compression_ratio 29.7;
   baris tulen 1.7-2.8. `_looks_hallucinated()` tangkap ini.
   (b) Fantasi muzik — 17 baris teks KOREA pada vlog memasak Inggeris,
   compression_ratio 1.8-1.9, **tidak dapat dibezakan** dengan nisbah.
   Hanya VAD menghalangnya, dengan tidak menghantar muzik kepada model
   langsung. JANGAN matikan `vad_filter` menyangka ia hanya
   pengoptimuman.
46. **Masa tamat pertuturan pembaca skrin = DENGAR bunyinya, bukan
   tanya API.** `core/audio_meter.py` baca meter puncak Windows pada
   sesi audio proses pembaca skrin. Senyap ≥0.6s = ayat habis. Diukur
   dalam pemain sebenar dengan NVDA 2025.3: 5 patah → video dijeda
   1.43s, 26 patah → 4.64s. Berfungsi pada SEMUA versi NVDA kerana ia
   tidak meminta apa-apa daripada NVDA.
   **Laluan API DITOLAK, jangan cuba lagi tanpa ukur:** `speakSsml`
   segerak (controller client v2, NVDA 2024.1+) TERSEKAT pada panggilan
   pertama di NVDA 2025.3 — perlumbaan yang dibaiki hanya NVDA 2026.2
   (nvaccess/nvda#20220), dicetus oleh tekanan kekunci biasa.
   `isSpeaking` hanya NVDA 2026.3 (belum stabil). DLL controller client
   TIDAK diperlukan untuk ciri ini.
47. **Tiga kesilapan meter, semuanya dijumpai dengan mengukur:**
   (a) cari peranti LALAI sahaja → tiada sesi NVDA langsung; NVDA di
   sini dihalakan ke peranti 0, lalai Windows peranti 1. Cari SEMUA.
   (b) `tasklist` untuk cari proses → 0.83s, lebih lama daripada ayat
   3 patah pada kadar NVDA pengguna (~6 patah/saat). Guna
   `QueryFullProcessImageNameW` (~0.03s keseluruhan).
   (c) cari meter SELEPAS bercakap → terlepas ayat pendek. Sediakan
   SEBELUM `speak()`; `ReaderMeter.speak_and_wait(speak_fn, ...)`.
48. **Salinan `nvdaControllerClient64.dll` di akar projek TIDAK
   ditandatangani** (API v1.0, 4 fungsi sahaja). Versi rasmi 2026.2
   ditandatangani NV Access Limited melalui GlobalSign. Ia tidak
   digunakan oleh mana-mana kod; pemilik meletakkannya 23 Sep 2026.

49. **Tetingkap konsol HANYA muncul dalam build beku.** Exe `--windowed`
   tiada konsol, jadi Windows beri SETIAP anak (ffmpeg, ffprobe, yt-dlp)
   tetingkap konsol baharu yang merampas fokus — NVDA sebut "terminal"
   dan baca laluan ffmpeg di tengah kerja (larian sebenar, 28 Sep 2026,
   video 15 minit). Dari source anak berkongsi konsol python.exe, jadi
   TIADA test pernah nampak. `core/no_console.install()` (dipanggil awal
   dalam `main.py`) jadikan `CREATE_NO_WINDOW` lalai; `test_no_console`
   buktikan dengan induk `pythonw`. **Uji exe dalam `dist/`, bukan src.**
50. **SEMUA `SettingsStore` dalam satu proses KONGSI satu keadaan**
   (ikut laluan fail) sejak v1.7.4. Sebelum itu player cipta store
   sendiri lalu tulis snapshot lama — kunci yang baru disimpan dalam
   Settings hilang. Simpanan kini atomik (tmp + `os.replace`); fail
   rosak diasingkan jadi `settings.json.corrupt-<masa>`, BUKAN ditimpa;
   blob kunci yang DPAPI tak dapat buka DISIMPAN, bukan dibuang.
   Jangan kembalikan fallback XOR di Windows.
51. **Kunci API TIDAK BOLEH dalam URL.** Gemini dahulu guna `?key=`;
   halaman ralat HTML 503 buat `resp.json()` lempar ralat yang memuatkan
   URL penuh — kunci masuk log DAN disimpan sebagai "penerangan".
   Guna pengepala `x-goog-api-key`; `_http_json` semak status sebelum
   decode dan ulang cuba 429/5xx.
52. **Susun bingkai ikut NOMBOR, bukan teks.** `frame_%04d.jpg` melepasi
   9999 jadi `frame_10000.jpg`, yang tersusun antara 1000 dan 1001 —
   setiap bingkai selepasnya dapat masa salah (10 fps, video >16:40).
53. **`SetLabel()` pada `wx.Slider` TIDAK sampai ke NVDA** — didengar
   "slider 0". Windows namakan trackbar ikut StaticText yang DICIPTA
   SEJURUS sebelumnya. `tools/nvda_window_check.py --window
   player|editor|ask` semak tetingkap selain tetingkap utama; dialog wx
   berada DI BAWAH pemiliknya dalam pepohon UIA, jadi ia dicari ikut
   handle Win32.

54. **Folder projek BERNAMA sejak v1.7.6: `Nama (id)/project.db`.**
   Susun atur lama (`project_48.db` + `project_48/`) dipindah oleh
   `ProjectStore.migrate_layout()` semasa MainFrame dibuka. DB
   menyimpan laluan MUTLAK video dan bingkai — setiap penukaran nama
   folder MESTI melalui `_move_folder`, yang menulis semula laluan itu.
   **Jangan bina laluan `project_{id}` sendiri** — guna
   `store.project_dir(id)` / `media_dir(id)` / `_db_path(id)`.
   Folder yang videonya sedang dibuka tidak boleh ditukar nama di
   Windows; nama DB tetap berubah dan folder mengikut pada pembukaan
   seterusnya. `ODC_PROJECTS_DIR` mengasingkan projek dalam test (gate
   dahulu meninggalkan 14 projek ujian dalam Documents pemilik).
55. **Ujian yang MENDENGAR NVDA terganggu bila NVDA membaca app lain.**
   Meter mendengar SEMUA ucapan NVDA. Dibuktikan 28 Sep 2026 melalui
   bridge: setiap kegagalan `test_fixes26` berlaku semasa NVDA membaca
   permainan pemilik (sehingga 100 ucapan lain); setiap larian senyap
   lulus. Ujian itu kini mengukur semula sehingga senyap. JANGAN
   longgarkan ambangnya untuk "membaiki" kegagalan sebegini.

56. **yt-dlp boleh dikemas kini PENGGUNA (v1.7.7), di luar bundle.**
   `core/updater.py` pasang ke `%LOCALAPPDATA%\OmniDescriber\tools`
   hanya bila SHA-256 sepadan dengan `SHA2-256SUMS` keluaran itu DAN
   `--version` sama dengan tag. `find_tool()` utamakan salinan itu
   HANYA selagi hash-nya masih sama dengan `updates.json`; fail yang
   diubah diabaikan. Salinan bundle tidak pernah ditimpa (pin build
   dalam `fetch_binaries.py` kekal). Semakan mingguan HANYA mengumumkan.
   Test guna `ODC_TOOLS_DIR`; jangan biar test menulis ke LOCALAPPDATA.
   `updater.status()` menjalankan yt-dlp (1-3 s) — jangan panggil
   pada benang UI.

57. **`wx.Menu.SetTitle` pada menu dalam menubar ROSAKKAN menu itu di
   Windows** — ia menulis tajuk KE DALAM dropdown, menimpa item
   pertama. Sejak `_retranslate_menu` menggunakannya, File dibuka pada
   "File" (Settings tidak boleh dicapai dengan papan kekunci) dan Help
   pada "Help". Senarai item wx TETAP nampak betul, jadi hanya NVDA /
   menu Win32 sebenar yang menunjukkannya (ditemui 28 Sep 2026, v1.7.7).
   Guna `menubar.SetMenuLabel(i, label)`. `test_fixes40` baca menu
   NATIVE (GetMenuItemCount / GetMenuStringW), bukan senarai wx.

57. **JANGAN cipta semula kawalan untuk menukar gayanya.** Show/Hide kunci
   API dahulu membina TextCtrl baharu untuk membalik `TE_PASSWORD`:
   kotak baharu jatuh ke sudut kiri atas panel (hanya dialog di-layout,
   bukan halaman notebook), jadi TERAKHIR dalam susunan Tab, dan hilang
   label NVDA — pemilik melaporkan "input api key terus hilang"
   (28 Sep 2026). Test lama semak NILAI sahaja, jadi lulus. Di Windows
   tukar gaya pada kawalan yang SAMA (`EM_SETPASSWORDCHAR`). **Test UI
   mesti semak kedudukan, susunan Tab dan objek yang sama, bukan nilai
   sahaja** (`test_fixes42`). Nota automasi: `send_keys(" ")` pywinauto
   MEMBUANG ruang — guna `{SPACE}`.

58. **Bahasa pengguna tinggal di `%APPDATA%\OmniDescriber\locales`**
   (v1.8.0), kerana folder `locales/` dalam app diganti setiap kali
   dikemas kini. Fail kod baharu = bahasa baharu; fail kod sedia ada =
   pembetulan baris demi baris (baris kosong diabaikan). `*.missing.json`
   ialah laporan, BUKAN bahasa. `ODC_LOCALES_DIR` mengasingkan test.
   **Setiap teks yang dilihat/didengar pengguna melalui `t()`** —
   `test_fixes43` gagal pada teks Inggeris dalam UI atau kunci yang tak
   digunakan (46 kunci mati dibuang v1.8.0). Tambah kunci = tambah ke
   `en.json` DAN `ms.json`.

## Prosedur Biasa

### Run app (dev)
```bash
run.bat
# atau: C:/Users/USER/AppData/Local/Programs/Python/Python313/python.exe main.py
```

### Gate penuh
```bash
run_gate.bat   # GATE_ALL_PASS diperlukan sebelum commit
```

### Backup (repo tiada remote)
Hook `.git/hooks/post-commit` (v1.5.5) bundle SELURUH sejarah ke
`~/OneDrive/backups/omni-describer-custom.bundle` selepas setiap commit.
Hook TIDAK tersimpan dalam git — kalau repo di-clone semula, cipta balik.
Pulih: `git clone <bundle> <dir>`.

### Build release
```bash
build.bat      # 4 fasa: compile check → PyInstaller → exe smoke test → zip
# Hasil: dist/OmniDescriber-<versi>-win64.zip
# Buang zip lama selepas yang baharu disahkan (kekalkan versi terkini sahaja)
```

### Test satu suite
```bash
C:/Users/USER/AppData/Local/Programs/Python/Python313/python.exe -u tests/test_fixes18.py
```

## Disiplin Kerja (corak dari sesi sebenar)

- **JANGAN ulang kerja yang dah verified** tanpa input baharu (arahan baru, bug sebenar,
  atau git tree berubah). Corak dari evergreen: auto-validation loop ditolak berkali-kali
  dengan jawapan konsisten — repeat validation tanpa fakta baharu bukan kerja, ia buang masa.
- **Verify fakta dengan kod, bukan ingatan** — sebelum menulis dakwaan (fields, fail,
  behaviour), semak source sebenar dahulu. Corak: skrip pemeriksaan kecil, bukan agakan.
- **State keputusan dengan bukti** — "PASS" tanpa bukti = tak pass. Rantaian
  speculative → plausible → validated → verified yang digunakan evergreen adalah standard.
- **Bina di atas tag, bukan HEAD** — bila menyemak release, ukur commit tag;
  HEAD boleh ada commit selepas rilis (doc bukti, dsb.).

## Status Semasa (kemas kini bila release)

- **Versi:** 1.8.0 (tag `v1.8.0`; rumusan v1.5.4:
  `doc/rumusan-v1.5.4.md`). Gate: 53 suite dalam `run_gate.bat`.
- Provider aktif dalam GUI: GLM (OpenRouter), Gemini (lalai
  `gemini-3.8-flash` sejak v1.7.3; 2.5 ditutup untuk pengguna baharu),
  MiniMax, custom. Hanya Gemini MENDENGAR audio video.
- Gate 53 suite, GATE_ALL_PASS (28 Sep 2026, dua kali berturut).
- E2E build beku dengan video 15 minit (Sintel) PASS pada 1.7.4:
  Gemini 15/15 (73 cue); GLM 2 bahagian 121 cue (5 cue >20 patah —
  perangai model, pitfall 14).
- NVDA disemak dengan mendengar: tetingkap utama, player, editor,
  Ask More (`tools/nvda_window_check.py`).
- Senarai kerja terbuka: `doc/senarai-semak-v1.7.5.md` (JANGAN tulis
  "tiada bug terbuka" di sini — senarai itu sumbernya).
- wxPython Phoenix: `MenuBar.SetLabelTop` TIDAK wujud — guna
  `menubar.SetMenuLabel(i, ...)`. JANGAN `GetMenu(i).SetTitle` (pitfall 57).
