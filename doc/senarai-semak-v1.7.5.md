# Senarai semak selepas v1.7.4

Dibuat 28 Sep 2026. Tanda `[x]` hanya bila ada bukti (output test/run).

## Fasa 1 — pemilik (bukan agent)
- [ ] Padam `%APPDATA%\OmniDescriber\settings.json.v1.5.2.bak` (4 kunci XOR)
- [ ] Tukar kunci Gemini, OpenRouter, custom, Opus jika masih hidup

## Fasa 2 — sahkan 1.7.4
- [x] 2.1 `tools/nvda_accessibility_check.py` — tetingkap utama (build 1.7.4: 20/20 OK)
- [x] 2.2 Semakan NVDA — editor, player, Ask More (alat baharu `tools/nvda_window_check.py`;
  DIBAIKI: slider player disebut "slider 0" tanpa nama, panel video disebut "video_area";
  kini 16/16 OK setiap tetingkap; gate GATE_ALL_PASS)
- [ ] 2.3 E2E sebenar video panjang dengan GLM (mampatan + pecahan)
- [ ] 2.4 Editor/player: sunting → pindah → tutup player → buka semula → suntingan kekal

## Fasa 3 — kemas
- [ ] 3.1 AGENTS.md: kiraan suite, Status Semasa, pitfall baharu
- [ ] 3.2 Padam zip 1.7.2 dan 1.7.3
- [ ] 3.3 `.audit_scan.sh` — commit atau padam

## Fasa 4 — bug + build → 1.7.5
- [ ] 4.1 GLM Cancel semasa permintaan panjang
- [ ] 4.2 Mod batch: satu gagal, yang lain dibatalkan
- [ ] 4.3 Bitrate bahagian ikut panjang bahagian
- [ ] 4.4 Buang `torch` daripada build (Whisper masih berfungsi)
- [ ] 4.5 Pin versi + SHA-256 ffmpeg/yt-dlp
- [ ] 4.6 Gate x2, build, E2E, tag v1.7.5

## Fasa 5 — ciri baharu (tanya pemilik dahulu)
- [ ] 5.1 Profil suara (enjin + suara + kelajuan)
