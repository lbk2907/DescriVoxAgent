# Pelan projek / Project plan — DescriVox Agent

**BM:** Fail ini mengumpul SEMUA pelan yang pernah dibuat dalam projek ini, dari v1.5.1
(Ogos 2026) hingga v1.9.5 (1 Okt 2026), di satu tempat yang mudah dibaca. Ia ialah
gambaran keseluruhan: apa yang dirancang, bila ia dihantar, apa yang diputuskan, dan apa
yang ditolak selepas diukur. Bukti peringkat item (output ujian, angka, larian NVDA) kekal
dalam senarai semak hidup [senarai-semak.md](senarai-semak.md) dan arkibnya
[arkib/senarai-semak-fasa-1-18.md](arkib/senarai-semak-fasa-1-18.md). Angka ukuran penuh
ada dalam [perbandingan-model.md](perbandingan-model.md); apa yang setiap keluaran bawa ada
dalam [../CHANGELOG.md](../CHANGELOG.md).

**EN:** This file gathers EVERY plan made in this project, from v1.5.1 (August 2026) to
v1.9.5 (1 Oct 2026), in one readable place. It is the overview: what was planned, when it
shipped, what was decided, and what was rejected after measuring. Item-level evidence (test
output, numbers, NVDA runs) stays in the live checklist [senarai-semak.md](senarai-semak.md)
and its archive [arkib/senarai-semak-fasa-1-18.md](arkib/senarai-semak-fasa-1-18.md). Full
measurement tables are in [perbandingan-model.md](perbandingan-model.md); what each release
shipped is in [../CHANGELOG.md](../CHANGELOG.md).

---

## 1. Matlamat / Goals

**BM:**
1. **Aksesibiliti dahulu.** Pengguna utama ialah pemilik, buta, menggunakan NVDA. Setiap
   kawalan bernama, setiap perubahan status disebut, dan aksesibiliti disahkan dengan
   MENDENGAR melalui NVDA, bukan dengan membaca kod.
2. **Penerangan audio yang tepat ikut piawaian AD** (DCMP, Netflix AD Style Guide v2.1,
   W3C/WAI, ADLAB): huraikan hanya yang perlu, jangan ulang apa yang sudah kedengaran, cukup
   pendek untuk dituturkan, dan pada masa yang betul. Ketepatan visual lebih penting
   daripada dialog (pemilik, 29 Sep 2026).
3. **Kunci dan data selamat.** Kunci API disulitkan (DPAPI), tidak pernah dalam URL, log
   atau kod; ujian tidak menyentuh tetapan atau projek sebenar pemilik.
4. **Diukur, bukan diandaikan.** Tetapan baharu digunakan hanya bila angka menunjukkan ia
   lebih baik; katalog model ialah dakwaan, probe ialah bukti.

**EN:**
1. **Accessibility first.** The main user is the owner, blind, using NVDA. Every control is
   named, every status change is spoken, and accessibility is verified by LISTENING through
   NVDA, not by reading code.
2. **Accurate audio description per AD standards** (DCMP, Netflix AD Style Guide v2.1,
   W3C/WAI, ADLAB): describe only what is needed, never repeat what is already audible, short
   enough to speak, at the right moment. Visual accuracy matters more than dialogue (owner,
   29 Sep 2026).
3. **Safe keys and data.** API keys are encrypted (DPAPI), never in URLs, logs or code;
   tests never touch the owner's real settings or projects.
4. **Measured, not assumed.** A new setting is adopted only when the numbers show it is
   better; a model catalog is a claim, a probe is proof.

---

## 2. Kerja terbuka / Open work

**BM:** Semua item yang masih belum ditanda dalam senarai semak, ditambah had yang diketahui
yang direkodkan dalam sumber tetapi tiada item senarai semak.
**EN:** Every item still unticked in the checklist, plus known limits recorded in the
sources that have no checklist item.

### 2.1 Item senarai semak / Checklist items

| ID | BM | EN | Status | Sebab / Why |
|---|---|---|---|---|
| 23.8 | Ejen: jawapan akhir kosong selepas had giliran; pembetulan disebut dalam kata-kata tanpa `propose_change` | Agent: empty final answer after the turn limit; a fix described in words without `propose_change` | Terbuka (cadangan) / Open (proposal) | Dilihat dalam ukuran 22.5b (Gemini 3.8 Flash menyebut pembetulan tanpa memanggil tool) / Seen in measurement 22.5b (Gemini 3.8 Flash named fixes without calling the tool) |
| Fasa 1 | Tukar kunci Gemini, OpenRouter, custom, Opus jika masih hidup | Replace Gemini, OpenRouter, custom, Opus keys if still live | Menunggu pemilik / Waiting for owner | Dibuat di papan pemuka provider; agent tidak pernah menyentuh kunci. Kunci lama pernah ada dalam sandaran XOR `settings.json.v1.5.2.bak` (dipadam 28 Sep) / Done on provider dashboards; the agent never handles keys. Old keys sat in the XOR backup (deleted 28 Sep) |
| 5.1 | Profil suara | Speech profiles | Ditangguhkan oleh pemilik (28 Sep 2026) / Deferred by owner | Fasa 5 = ciri baharu, tanya pemilik dahulu / Phase 5 = new features, ask owner first |
| 8.6 | ffmpeg dalam menu Semak Kemas Kini | ffmpeg in the Check for Updates menu | Tidak dibuat — pilihan pemilik / Not done — owner's choice | Semak Kemas Kini (v1.7.7) meliputi yt-dlp sahaja; ffmpeg kekal dipin dalam build / Check for Updates (v1.7.7) covers yt-dlp only; ffmpeg stays pinned in the build |

### 2.2 Had yang diketahui tanpa item / Known limits without an item

| BM | EN | Sumber / Source |
|---|---|---|
| Ejen GLM masih mengubah 5 daripada 8 penerangan yang betul (tahap `low`) | The GLM agent still changes 5 of 8 correct descriptions (level `low`) | perbandingan-model.md, 22.5 |
| Pelan 16.3 menyenaraikan "semak jurang panjang untuk peristiwa tertinggal"; tiada ukuran untuknya ditemui dalam sumber | Plan 16.3 listed "check long gaps for missed events"; no measurement of it was found in the sources | arkib 16.3, perbandingan-model.md |
| Whisper: audio kartun yang sukar masih memberi beberapa segmen rekaan; VAD yang salah menolak pertuturan sebenar akan tinggalkan video tanpa transkrip secara senyap | Whisper: hard cartoon audio still yields a few invented segments; VAD wrongly rejecting real speech would leave a video silently untranscribed | CHANGELOG v1.6.9 |
| Mod bingkai tidak disemak oleh "Semak penerangan" | Frame mode is not checked by "Check descriptions" | [pitfalls.md](pitfalls.md), pitfall 78 |
| Gemini 3.8 Flash tidak dapat diukur untuk suhu 0 (503, kemudian 429 kuota) | Gemini 3.8 Flash could not be measured for temperature 0 (503, then 429 quota) | perbandingan-model.md, 20.7 |
| Settings: Esc menutup tanpa semakan perubahan — "ditangguhkan" dalam v1.5.4; status kemudian tidak direkod | Settings: Esc closes without checking for changes — "deferred" in v1.5.4; later status not recorded | arkib/rumusan-v1.5.4.md |

---

## 3. Pelan mengikut fasa / Plans by phase

### 3.1 Sebelum fasa bernombor (v1.5.1 – v1.7.4) / Before numbered phases

**BM:** Sebelum 28 Sep 2026 tiada senarai semak bernombor; setiap keluaran ialah pelannya
sendiri. Ringkasan (butiran: CHANGELOG.md).
**EN:** Before 28 Sep 2026 there was no numbered checklist; each release was its own plan.
Summary (details: CHANGELOG.md).

| Keluaran / Release | Tarikh / Date | BM | EN |
|---|---|---|---|
| 1.5.1 | < 5 Sep | Cancel di mana-mana, projek bernama, bar seek penuh, TTS fallback | Cancel everywhere, named projects, full seek bar, TTS fallback |
| 1.5.2 | 5 Sep | Bahasa penerangan konsisten; preset BM dibaiki | Consistent description language; Malay presets fixed |
| 1.5.3 | 5 Sep | Konteks antara bahagian; bahagian 600 s; Opus dibuang | Context between parts; 600 s parts; Opus removed |
| 1.5.4 | 8 Sep | Audit penuh (5 agen): bug ID (hilang data), NVDA, DPAPI, kunci keluar dari URL; 28 suite | Full audit (5 agents): ID bug (data loss), NVDA, DPAPI, key out of URLs; 28 suites |
| 1.5.5–1.5.7 | 17 Sep | Dialog hantu, butang Open mati, gate menulis tetapan sebenar, `SetLabel` memakan state | Ghost dialog, dead Open button, gate writing real settings, `SetLabel` eating state |
| 1.6.0 | 19 Sep | Prompt ikut piawaian AD; 7 preset ikut strategi (22.7 → 14.0 patah/cue) | Prompts follow AD standards; 7 strategy presets (22.7 → 14.0 words/cue) |
| 1.6.1–1.6.4 | 21 Sep | Transkrip untuk GLM pekak; jeda naratif; had 12 patah; locale JSON; bunyi player dibaiki | Transcript for deaf GLM; narration pause; 12-word ceiling; JSON locales; player sound fixed |
| 1.6.5–1.6.7 | 22 Sep | Alat terbungkus (`core/tools.py`); Prism; muat turun boleh disambung; housekeeping temp | Bundled tools (`core/tools.py`); Prism; resumable downloads; temp housekeeping |
| 1.6.8–1.7.1 | 23 Sep | Bajet patah per jurang; Whisper deterministik (0/7); lantai liputan bingkai 30 s; jeda NVDA melalui meter audio | Word budget per gap; deterministic Whisper (0/7); 30 s frame coverage floor; NVDA pause via audio meter |
| 1.7.2–1.7.4 | 27–28 Sep | Muat naik Gemini dibaiki; lalai `gemini-3.8-flash`; audit + E2E Sintel 15 min (tiada konsol) | Gemini upload fixed; `gemini-3.8-flash` default; audit + 15-min Sintel E2E (no consoles) |

### 3.2 Fasa 1–27 / Phases 1–27

**BM:** Fasa 1–18 dalam [arkib/senarai-semak-fasa-1-18.md](arkib/senarai-semak-fasa-1-18.md);
fasa 19–27 dalam [senarai-semak.md](senarai-semak.md). "—" = tiada keluaran.
**EN:** Phases 1–18 are in [arkib/senarai-semak-fasa-1-18.md](arkib/senarai-semak-fasa-1-18.md);
phases 19–27 in [senarai-semak.md](senarai-semak.md). "—" = no release.

| Fasa | Nama / Name | Keluaran | Hasil (BM) | Outcome (EN) |
|---|---|---|---|---|
| 1 | Pemilik (bukan agent) / Owner (not agent) | — | `.bak` XOR dipadam; tukar kunci masih terbuka | XOR `.bak` deleted; key replacement still open |
| 2 | Sahkan 1.7.4 / Verify 1.7.4 | 1.7.5 | NVDA semua tetingkap 16/16; E2E GLM Sintel 121 cue | NVDA every window 16/16; GLM Sintel E2E 121 cues |
| 3 | Kemas / Tidy | — | AGENTS.md dikemas; zip lama dipadam | AGENTS.md updated; old zips deleted |
| 4 | Bug + build | 1.7.5 | Cancel GLM <1 s; torch dibuang (zip 446 → 319 MB); alat dipin + SHA-256 | GLM Cancel <1 s; torch removed (zip 446 → 319 MB); tools pinned + SHA-256 |
| 5 | Ciri baharu / New features | — | 5.1 profil suara ditangguhkan | 5.1 speech profiles deferred |
| 6 | Nama projek mesra / Friendly project names | 1.7.6 | `Nama (id)/project.db`; 27/27 projek dipindah; Rename Alt+N | `Name (id)/project.db`; 27/27 projects moved; Rename Alt+N |
| 7 | Semak Kemas Kini / Check for Updates | 1.7.7 | yt-dlp dikemas kini dengan SHA-256; pepijat menu `SetTitle` ditemui dengan mendengar | yt-dlp updates with SHA-256; menu `SetTitle` bug found by listening |
| 8 | Penambahbaikan kecil / Small improvements | 1.7.8 | Ujian tidak guna projek pemilik; preset ikut fail locale | Tests stop using owner projects; presets follow locale files |
| 9 | Bug pemilik / Owner bug | 1.7.9 | Kotak kunci API tidak lagi hilang selepas Show/Hide | API key box no longer vanishes after Show/Hide |
| 10 | Pelbagai bahasa / Multilingual | 1.8.0 | Bahasa pengguna dalam `%APPDATA%`; 46 kunci mati dibuang; Laporan Terjemahan | User languages in `%APPDATA%`; 46 dead keys removed; Translation Report |
| 11 | Model OpenRouter + audio per model | 1.8.1 | Fetch models 85 → 65; Uji model ini; audio per MODEL | Fetch models 85 → 65; Test this model; audio per MODEL |
| 12 | D/E/F/G | 1.8.2 (12.8: 1.8.7) | `safe_keys` selepas insiden TeamTalk; 7 masalah papan kekunci; lalai OpenRouter/GLM | `safe_keys` after TeamTalk incident; 7 keyboard issues; OpenRouter/GLM default |
| 13 | Video panjang pada exe / Long video on exe | 1.8.3 | YouTube 403 dicuba semula; E2E 15/15, 81 cue | YouTube 403 retried; E2E 15/15, 81 cues |
| 14 | Kemajuan muat naik + NVDA / Upload progress + NVDA | 1.8.4 | Bar bergerak semasa muat naik; fasa disebut sekali | Bar moves during upload; each phase spoken once |
| 15 | Perbandingan model / Model comparison | 1.8.5 (15.6: 1.8.7) | 7 model × 5 klip: mendengar tidak lebih tepat; GLM + Gemini 3.1 Flash-Lite disyorkan | 7 models × 5 clips: hearing is not more accurate; GLM + Gemini 3.1 Flash-Lite recommended |
| 16 | Ketepatan / Accuracy | 1.8.6, 1.8.8 | Pembaris (GLM 8% salah); bahagian 600 → 300 s (24.5% → 12.9%, 27.5% → 11.8%); lalai video penuh | Ruler (GLM 8% wrong); parts 600 → 300 s (24.5% → 12.9%, 27.5% → 11.8%); full-video default |
| 17 | Pelepasan 1.8.6 / Release 1.8.6 | 1.8.6, 1.8.7 | Mod bingkai 204 → 15 penerangan; Esc dalam Ya/Tidak | Frame mode 204 → 15 descriptions; Esc in Yes/No |
| 18 | Seterusnya / Next | 1.8.8, 1.9.0 | Semak penerangan (Tears salah 15 → 7); model pilihan kini digunakan; Ejen Player F2 | Check descriptions (Tears wrong 15 → 7); chosen model now used; Player agent F2 |
| 19 | B + C + E | 1.9.1 | Suhu 0 GLM (salah 24.2% → 16.8%); "Semak seluruh video"; README 1232 → 143 baris | GLM temperature 0 (wrong 24.2% → 16.8%); "Check the whole video"; README 1232 → 143 lines |
| 20 | Laporan pemilik / Owner report | 1.9.2 | Label Custom; Uji model ini untuk semua; ejen Gemini terus; suhu 0 Gemini | Custom labels; Test this model for all; direct Gemini agent; Gemini temperature 0 |
| 21 | Fetch models Gemini | 1.9.3 | 61 → 12 model video, 3.1 Flash-Lite dahulu | 61 → 12 video models, 3.1 Flash-Lite first |
| 22 | Tahap thinking / Thinking levels | 1.9.4 | Gemini 3.1 Flash-Lite `medium` 15.8% → 9.1%; ejen GLM `low` 8/16 → 11/16; GLM video penuh kekal had 2000 | Gemini 3.1 Flash-Lite `medium` 15.8% → 9.1%; GLM agent `low` 8/16 → 11/16; GLM full video keeps 2000 cap |
| 23 | 429 Gemini | 1.9.5 | 429 tunggu `retryDelay`; had harian gagal serta-merta; ejen Gemini 3.1 Flash-Lite 4/4; 15.7 selesai (kunci baharu 25/25) | 429 waits `retryDelay`; daily quota fails at once; Gemini 3.1 Flash-Lite agent 4/4; 15.7 done (new key 25/25) |
| 25 | Bug laporan pemilik / Owner's bug report | 1.9.6 | Cancel dikesan selepas muat turun (punca utama); transkrip boleh dibatal & disimpan; Buka Projek dibaiki; 413 tanpa had; ralat dalam kata-kata; tetapan sebenar tidak lagi disentuh ujian; slider "1:04"; ejen terima masa semasa | Cancel noticed after the download (the main cause); transcript cancellable & kept; Open Project fixed; 413 without a limit; errors in words; tests never touch real settings; slider "1:04"; agent gets the current time |
| 27 | Nama baharu / New name | 2.0.0 | DescriVox Agent: nama yang dilihat sahaja; folder tetapan kekal | DescriVox Agent: visible names only; settings folders kept |
| 26 | Ejen atau alat lama / Agent or older tools | 1.9.7 | Scene Explorer: mesej betul, ~600 bingkai; Player: Agent (F2) ATAU Tanya Lagi + Jelajah Adegan | Scene Explorer: right message, ~600 frames; Player: Agent (F2) OR Ask More + Explore Scene |
| 24 | Kemas dokumen / Tidy the docs | — | `plan.md` ini; AGENTS.md dalam English + `pitfalls.md` (88 entri, nombor sama); `CLAUDE.md`; fail lama ke `arkib/` | this `plan.md`; AGENTS.md in English + `pitfalls.md` (88 entries, same numbers); `CLAUDE.md`; old files to `arkib/` |

**BM:** Setiap fasa keluaran ditutup dengan gate ×2 GATE_ALL_PASS, build BUILD_ALL_OK, exe
didengar NVDA, tag, dan zip lama dibuang.
**EN:** Every release phase closed with gate ×2 GATE_ALL_PASS, build BUILD_ALL_OK, the exe
heard through NVDA, a tag, and the old zip deleted.

### 3.3 Dua pelan besar / Two large plans

**Pelan ketepatan (fasa 16) — BM:** Dicadangkan 29 Sep 2026 selepas pemilik berkata dialog
kurang penting daripada menghurai video dengan tepat. Empat fasa: (1) pembaris automatik
yang dikalibrasi pada label tangan; (2) asas lebih luas merentas drama, kartun,
berita/dokumentari, tutorial + mod bingkai lwn video penuh; (3) baiki — pas semakan, snap
adegan, suhu tetap, semak jurang; (4) tetapan dalam Settings. Disimpan dahulu atas
permintaan pemilik, kemudian dijalankan 29–30 Sep (16.1–16.4, 18.1, 19.B).

**Accuracy plan (phase 16) — EN:** Proposed 29 Sep 2026 after the owner said dialogue
matters less than describing the video accurately. Four phases: (1) an automatic ruler
calibrated on hand labels; (2) a wider baseline across drama, cartoon, news/documentary,
tutorial + frame vs full-video mode; (3) fixes — review pass, scene snapping, fixed
temperature, gap check; (4) a Settings toggle. Saved first at the owner's request, then run
29–30 Sep (16.1–16.4, 18.1, 19.B).

**Ejen Player (fasa 18.2) — BM:** Idea pemilik 29 Sep 2026; "GO" pada 30 Sep. Pelan A–E:
A ukur tool calling setiap model (`tools/agent_bench.py`, 4 model lulus, $0.063) →
B `core/agent.py` tanpa UI → C Tanya Lagi hantar bingkai → D UI F2 dalam Player →
E ujian/NVDA/gate/larian sebenar → 1.9.0. Lanjutan: semak seluruh video (1.9.1), ejen
Gemini terus (1.9.2), tahap thinking ejen (1.9.4).

**Player agent (phase 18.2) — EN:** Owner's idea 29 Sep 2026; "GO" on 30 Sep. Plan A–E:
A measure tool calling per model (`tools/agent_bench.py`, 4 models pass, $0.063) →
B `core/agent.py` with no UI → C Ask More sends the frame → D F2 UI in the Player →
E tests/NVDA/gate/real run → 1.9.0. Follow-ups: check the whole video (1.9.1), direct
Gemini agent (1.9.2), agent thinking levels (1.9.4).

---

## 4. Keputusan penting / Key decisions

**BM:** Keputusan yang dibuat oleh pemilik (atau diterima pemilik selepas ukuran), dengan
tarikh bila diketahui.
**EN:** Decisions made by the owner (or accepted by the owner after measuring), with dates
where known.

| Tarikh / Date | BM | EN |
|---|---|---|
| v1.5.3 (5 Sep) | Provider Opus dibuang (kuota habis); guna Custom | Opus provider removed (quota exhausted); use Custom |
| v1.6.0 (19 Sep) | Preset ikut STRATEGI AD, bukan genre | Presets by AD STRATEGY, not genre |
| 23 Sep | Penomboran versi berhenti pada 9: 1.6.9 → 1.7.0 | Version numbering stops at 9: 1.6.9 → 1.7.0 |
| v1.7.3 (28 Sep) | Lalai Gemini `gemini-3.8-flash` (2.5 ditutup untuk pengguna baharu) | Gemini default `gemini-3.8-flash` (2.5 closed to new users) |
| 28 Sep | Padam sandaran `.bak` XOR; padam `.audit_scan.sh`; padam projek ujian (6.0, 6.8, 6.10) | Delete the XOR `.bak`; delete `.audit_scan.sh`; delete test projects (6.0, 6.8, 6.10) |
| 28 Sep | 4.7: cue >20 patah — BIARKAN (jeda naratif menanganinya) | 4.7: cues >20 words — LEAVE (narration pause handles them) |
| 28 Sep | 5.1 profil suara ditangguhkan; 8.6 ffmpeg dalam menu kemas kini tidak dibuat | 5.1 speech profiles deferred; 8.6 ffmpeg in the updates menu not done |
| 28 Sep | Setuju: Semak Kemas Kini (fasa 7), pelbagai bahasa (fasa 10) | Agreed: Check for Updates (phase 7), multilingual (phase 10) |
| 29 Sep | Minta pemilik tidak menyentuh PC sebelum automasi GUI/NVDA | Ask the owner to leave the PC before GUI/NVDA automation |
| 29 Sep | 15.8: GLM kekal lalai; GLM + Gemini 3.1 Flash-Lite disusun dahulu sebagai "Disyorkan" | 15.8: GLM stays default; GLM + Gemini 3.1 Flash-Lite listed first as "Recommended" |
| 29 Sep | Ketepatan visual > dialog; pelan ketepatan disimpan, tunggu pemilik | Visual accuracy > dialogue; accuracy plan saved, waits for owner |
| 29 Sep | Reka bentuk ejen: F2; video dijeda; Terima semua / Semak satu-satu / Tolak semua; ingatan sesi Player; bahasa ikut app; had $0.02 lalu tanya "teruskan?"; dikawal Uji mod ejen; tiada muat turun, Settings, padam, atau tulis SRT luar | Agent design: F2; video pauses; Accept all / Review one by one / Reject all; Player-session memory; app language; $0.02 cap then ask "continue?"; gated by Test agent mode; no downloading, Settings, deleting or writing external SRT |
| 30 Sep | Lalai pengguna baharu = mod video penuh; mod bingkai dijarakkan 4 s (mod tersimpan tidak disentuh) | New-user default = full-video mode; frame mode spaced 4 s (saved mode untouched) |
| 30 Sep | "Semak penerangan" MATI secara lalai; pilihan Auto / Paling tepat / Paling banyak / Kekalkan semua | "Check descriptions" OFF by default; choices Auto / Most accurate / Most descriptions / Keep all |
| 30 Sep | Bahagian video penuh 300 s (migrasi sekali dari 600) | Full-video parts 300 s (one-time migration from 600) |
| 30 Sep | Susunan fasa 18; fasa 19 = B + C + E, susunan E → B → C | Phase 18 order; phase 19 = B + C + E, order E → B → C |
| 1 Okt | Suhu 0 untuk Gemini terus — kerana kestabilan (ketepatan sama) | Temperature 0 for direct Gemini — for stability (same accuracy) |
| 1 Okt | Fasa 22: tahap baharu hanya jika lebih tepat; jika sama, pilih yang paling murah/pantas | Phase 22: a new level only if more accurate; if equal, the cheapest/fastest |
| 1 Okt | Model Gemini pemilik → 3.1 Flash-Lite (23.6) | Owner's Gemini model → 3.1 Flash-Lite (23.6) |

**BM:** Ditolak oleh pemilik tanpa ukuran (pilihan reka bentuk ejen): alat `listen`
(pengenalan bunyi) dan pratonton "dengar sebelum terima".
**EN:** Declined by the owner without measuring (agent design choices): a `listen` tool
(sound identification) and a "hear before accept" preview.

---

## 5. Ditolak selepas diukur / Measured and rejected

**BM:** Perkara yang dicuba dan TIDAK digunakan, dengan angka. Jangan cuba semula tanpa
ukuran baharu.
**EN:** Things tried and NOT adopted, with the number. Do not retry without a new
measurement.

| Perkara / Item | BM | EN | Sumber / Source |
|---|---|---|---|
| Whisper `beam_size=5` + `vad_filter` (v1.6.8) | Liputan jatuh ke 20%; pertuturan sebenar dibuang | Coverage fell to 20%; real speech dropped | CHANGELOG v1.6.8, pitfall 42 |
| Whisper model `small` | 12 segmen halusinasi lwn 2 (`base`) pada 7 video berbeza | 12 hallucinated segments vs 2 (`base`) on 7 different videos | CHANGELOG v1.6.9, pitfall 44 |
| Minta model letak cue dalam jurang (prompt) | 56% masih dalam separuh bercakap; jeda naratif digunakan sebagai mekanisme | 56% still in the talky half; narration pause used as the mechanism | CHANGELOG v1.6.3, pitfall 14 |
| Naikkan had token untuk preset `foreign` | Model hanya berfikir lebih (15,995/16,000 token); bajet dibahagi | The model just thinks more (15,995/16,000 tokens); budget split instead | CHANGELOG v1.6.3 |
| API NVDA `speakSsml` segerak | Tersekat pada panggilan pertama di NVDA 2025.3; meter audio digunakan | Hung on the first call in NVDA 2025.3; audio meter used instead | CHANGELOG v1.7.1, pitfall 46 |
| `tasklist` untuk cari proses NVDA | 0.83 s (lebih lama daripada ayat 3 patah); kini ~0.03 s | 0.83 s (longer than a 3-word sentence); now ~0.03 s | pitfall 47 |
| Mod bingkai sebagai lalai | 147–204 penerangan seminit pada filem | 147–204 descriptions a minute on films | perbandingan-model.md 16.2 |
| Bahagian 10 min / 3 min | 10 min: 24.5% / 27.5% salah; 3 min: 12.1% tetapi lebih perlahan (696 s lwn 605 s) | 10 min: 24.5% / 27.5% wrong; 3 min: 12.1% but slower (696 s vs 605 s) | perbandingan-model.md 16.2 |
| Gemini 2.5 Flash-Lite, Nemotron percuma | Mereka-reka dan pekak walaupun didakwa mendengar; Nemotron 3/8 larian gagal | Invents and is deaf despite the catalog; Nemotron 3/8 runs failed | perbandingan-model.md |
| Gemini 3.1 Flash-Lite sebagai penilai | 12/67 tuduhan palsu | 12/67 false accusations | perbandingan-model.md 16.1 |
| Snap ke perubahan adegan (19.B2) | Penilai Gemini: salah 39 → 44; penilai GLM 26 → 24 — tiada kemajuan jelas | Gemini judge: wrong 39 → 44; GLM judge 26 → 24 — no clear gain | perbandingan-model.md 19.B |
| Thinking GLM video penuh `low` / `high` / `max` (22.3) | low 7.1% lwn had 8.3% (dalam hingar, lebih perlahan); high 12.0%; max ~15 min purata, satu kosong — had 2000 dikekalkan | low 7.1% vs cap 8.3% (noise, slower); high 12.0%; max ~15 min average, one empty — 2000 cap kept | perbandingan-model.md 22.3 |
| Gemini 3.1 Flash-Lite `low` / `high` (22.4) | 12.7% / 10.7% lwn `medium` 9.1% | 12.7% / 10.7% vs `medium` 9.1% | perbandingan-model.md 22.4 |
| Ejen GLM `high` (22.5) | Sama 11/16 seperti `low` tetapi $0.0122 lwn $0.0076 | Same 11/16 as `low` but $0.0122 vs $0.0076 | perbandingan-model.md 22.5 |
| Ejen Gemini 3.8 Flash (22.5b) | 0/4 pembetulan, ~10× kos 3.1 Flash-Lite | 0/4 fixes, ~10× the cost of 3.1 Flash-Lite | perbandingan-model.md 22.5b |
| Ejen 3.1 Flash-Lite `medium` / `high` | 5/8 dan 6/8 lwn `low` 6/8, lebih mahal — `low` dikekalkan | 5/8 and 6/8 vs `low` 6/8, costlier — `low` kept | perbandingan-model.md 22.5b |
| Arahan ejen v1 (tanpa "hanya jika JELAS salah") | 3 model menyunting penerangan betul 6/6 kali | 3 models edited correct descriptions 6/6 times | perbandingan-model.md, Fasa A |

---

## 6. Cara menambah pelan / How to add a plan

**BM:**
1. Fasa baharu meneruskan nombor: yang seterusnya ialah **Fasa 28**. Jangan nombor semula.
2. Tulis entri ringkas di sini (fasa, nama, sebab, tarikh, siapa yang meminta), dan
   item terperinci dalam [senarai-semak.md](senarai-semak.md) (`28.1`, `28.2`, ...).
3. Tanda `[x]` hanya dengan bukti: output ujian, angka, larian sebenar, atau NVDA didengar.
4. Ukur sebelum menggunakan: tetapan atau model baharu masuk hanya bila angka lebih baik
   (penilai bebas, beberapa klip berbeza, beberapa larian). Catat angka dalam
   [perbandingan-model.md](perbandingan-model.md); yang ditolak masuk bahagian 5 di atas.
5. Ciri baharu: tanya pemilik dahulu. Kerja GUI/NVDA: minta pemilik tidak menyentuh PC.
6. Bila keluaran siap: kemas kini jadual fasa di sini, CHANGELOG.md dan status AGENTS.md.

**EN:**
1. A new phase continues the numbering: the next one is **Phase 28**. Never renumber.
2. Write a short entry here (phase, name, reason, date, who asked) and the detailed items
   in [senarai-semak.md](senarai-semak.md) (`28.1`, `28.2`, ...).
3. Tick `[x]` only with evidence: test output, numbers, a real run, or NVDA heard.
4. Measure before adopting: a new setting or model goes in only when the numbers are better
   (independent judge, several different clips, several runs). Record the numbers in
   [perbandingan-model.md](perbandingan-model.md); rejected ones go in section 5 above.
5. New features: ask the owner first. GUI/NVDA work: ask the owner to leave the PC.
6. When a release ships: update the phase table here, CHANGELOG.md and the AGENTS.md status.
