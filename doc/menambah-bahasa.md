# Menambah bahasa baharu

Panduan ini untuk sesiapa yang mahu menambah bahasa kepada Omni
Describer — anda sendiri, kawan, atau coding agent.

Sejak v1.6.2, menambah bahasa bermakna **meletakkan satu fail**. Tiada
perubahan kod, tiada langkah kompil, dan tiada prompt baharu untuk
ditulis.

## Ringkasnya (pengguna app .exe — sejak v1.8.0)

Fail bahasa anda sendiri disimpan dalam folder ini, yang **tidak
disentuh semasa app dikemas kini**:

```
%APPDATA%\OmniDescriber\locales\
```

Cara paling mudah ke sana: **Bantuan > Laporan Terjemahan...** (Help > Translation Report...), kemudian
jawab **Ya** untuk membuka folder itu.

1. Salin `en.json` ke folder itu dan tukar namanya kepada kod bahasa
   anda, contohnya `id.json` untuk Bahasa Indonesia. (`en.json` ada
   dalam app di `_internal\omni_describer_custom\i18n\locales\`.)
2. Tukar blok `_meta` di bahagian atas
3. Terjemah nilai (bahagian kanan), **jangan sentuh kunci**
4. Buka semula app, kemudian pilih bahasa itu dalam Tetapan

Fail dengan kod bahasa yang SUDAH ada (contohnya `ms.json`) dalam folder
ini **membetulkan** bahasa itu baris demi baris — anda hanya perlu
menulis baris yang mahu diubah. Baris kosong diabaikan.

## Selepas app dikemas kini: apa yang baharu untuk diterjemah?

Versi baharu kadang-kadang menambah teks (contohnya menu baharu). Anda
tidak perlu membandingkan fail sendiri:

1. Pilih bahasa anda dalam Tetapan
2. **Bantuan > Laporan Terjemahan...** (Help > Translation Report...) — app memberitahu berapa baris
   yang belum diterjemah, dan menyimpannya dalam
   `<kod>.missing.json` dalam folder yang sama, **setiap baris bersama
   teks Inggerisnya**
3. Terjemah baris-baris itu, salin ke dalam `<kod>.json` anda, dan buka
   semula app

Laporan itu juga menyenaraikan kunci lama yang app tidak guna lagi
(`_obsolete_keys_you_can_delete`) — boleh dipadam dari fail anda.
Sehingga anda menterjemah, baris yang tiada dibaca dalam Bahasa
Inggeris, bukan sebagai nama kunci.

## Untuk pembangun (kod sumber)

Bahasa yang dibekalkan bersama app tinggal dalam
`src/omni_describer_custom/i18n/locales/`. Setiap teks yang pengguna
lihat atau dengar MESTI melalui `t("kunci")` dengan kunci dalam
`en.json` DAN `ms.json` — `test_fixes43` gagal jika ada teks Inggeris
ditulis terus dalam UI, atau kunci yang tiada kod menggunakannya.

## Kod bahasa

Guna kod ISO 639-1 dua huruf: `id` Indonesia, `ar` Arab, `zh` Cina,
`th` Thai, `ta` Tamil, `hi` Hindi. Nama fail mesti sama dengan kod.

## Blok `_meta`

Ini yang menjadikan bahasa itu "tahu tentang dirinya sendiri":

```json
"_meta": {
  "code": "id",
  "name": "Bahasa Indonesia",
  "english_name": "Indonesian",
  "ai_language": "Indonesian",
  "tts_voice_edge": "id-ID-GadisNeural"
}
```

| Medan | Maksud |
|---|---|
| `code` | Mesti sama dengan nama fail |
| `name` | Nama dalam bahasa itu sendiri — inilah yang dibaca NVDA dalam pemilih |
| `english_name` | Untuk rujukan pembangun |
| `ai_language` | Nama yang diberitahu kepada AI: *"Write EVERY description in Indonesian"* |
| `tts_voice_edge` | Suara Edge TTS lalai untuk bahasa itu |

Untuk mencari nama suara Edge TTS yang sah:

```bash
python -c "import asyncio, edge_tts; print([v['ShortName'] for v in asyncio.run(edge_tts.list_voices()) if v['Locale'].startswith('id')])"
```

## Menterjemah

Kunci di sebelah kiri, terjemahan di sebelah kanan:

```json
"player.load_srt": "Muat SRT...",
```

Tiga peraturan:

1. **Jangan ubah kunci.** `"player.load_srt"` kekal sama dalam semua
   bahasa.
2. **Kekalkan pemegang tempat.** Kalau Inggeris ada `{count}` atau
   `{provider}`, terjemahan mesti ada yang sama. Ujian akan gagal jika
   tertinggal — pemegang tempat yang hilang bermakna nombor atau nama
   tidak akan muncul.
3. **Terjemahan separa tidak apa.** Kunci yang belum diterjemah akan
   jatuh balik ke Bahasa Inggeris satu demi satu. App tidak akan
   membaca nama kunci mentah seperti "menu.file" kepada pengguna.

## Anda TIDAK perlu terjemah prompt AI

Tujuh preset penerangan audio (`default`, `tight`, `extended`,
`foreign`, `suspense`, `children`, `onscreen_text`) kekal dalam Bahasa
Inggeris. Enjin menambah satu arahan — *"Write EVERY description in
Indonesian"* — dan model menulis dalam bahasa itu.

Ini sengaja: menterjemah tujuh prompt panjang untuk setiap bahasa akan
menjadikan setiap bahasa baharu kerja berjam-jam, dan terjemahan prompt
yang lemah menghasilkan penerangan yang lemah.

(Bahasa Melayu ada versi prompt tersendiri kerana ia ditulis oleh
penutur asli. Kalau anda mahu buat begitu untuk bahasa lain, tambah
preset `<kod>_default` dan rakan-rakannya dalam `prompt_manager.py`.)

## Menyemak kerja anda

```bash
run_gate.bat
```

`test_fixes24` akan memberitahu:

- kunci yang tertinggal (dan berapa banyak)
- kunci yang tidak wujud dalam Bahasa Inggeris (biasanya salah taip)
- pemegang tempat yang hilang
- `_meta` yang tidak lengkap
- fail JSON yang rosak

## Satu nasihat tentang kualiti

Pengguna utama aplikasi ini buta. Label ini **dibaca kuat-kuat** oleh
pembaca skrin. Terjemahan mesin yang janggal lebih teruk daripada
Bahasa Inggeris yang betul — pengguna yang mendengar ayat pelik tidak
dapat "mengimbas" skrin untuk meneka maksudnya seperti pengguna celik.

Jadi: terjemah dengan mesin kalau perlu, tetapi **minta penutur asli
dengar dan semak** sebelum ia dianggap siap.

## Contoh lengkap (pembangun)

```bash
cd src/omni_describer_custom/i18n/locales
cp en.json id.json
# edit id.json: tukar _meta, terjemah nilai
cd ../../../..
run_gate.bat
```

Selesai. Buka app, pergi ke Tetapan, dan "Bahasa Indonesia" sudah ada
dalam senarai. (Pengguna .exe: letak `id.json` dalam
`%APPDATA%\OmniDescriber\locales\` — lihat bahagian atas.)
