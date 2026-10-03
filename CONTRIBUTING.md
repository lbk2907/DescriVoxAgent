# Contributing to DescriVox Agent

Terima kasih kerana mahu menyumbang! Panduan ringkas — versi penuh
sistem ada dalam `doc/developer-guide.md`.

## 1. Baca dahulu (wajib)

- **`AGENTS.md`** — peraturan wajib untuk mana-mana agent/orang yang
  mengubah kod ini. Ia mengandungi perangkap bernombor yang telah
  menyebabkan bug sebenar.
- **`doc/pitfalls.md`** — pelajaran daripada bug sebenar, dengan
  nombor rujukan.
- **`doc/plan.md`** — status semasa dan arah projek.

## 2. Setup

```bat
git clone <repo>
cd omni-describer-custom
py -3.13 -m venv .venv
.venv\Scripts\pip install -e .[dev]
```

Keperluan: **Windows**, Python 3.11+, ffmpeg dalam PATH (guna
`tools/find ffmpeg` helper dalam kod — jangan hardcode path).
Aplikasi ini wxPython + NVDA-first: setiap perubahan UI mesti
kekal boleh diakses pembaca skrin.

## 3. Menjalankan ujian (GATE — wajib lulus sebelum commit)

Repo ini TIDAK guna test gaya pytest biasa. Setiap `tests/test_*.py`
ialah **program standalone** yang menjalankan suite sendiri dan
keluar dengan exit code (0 = lulus).

Tiga cara yang setara:

```bat
rem 1. Gate penuh seperti CI (autoritatif):
run_gate.bat

rem 2. Gate penuh melalui pytest (bridge conftest, satu item per skrip):
py -3.13 -m pytest tests

rem 3. Satu skrip pantas semasa membangun:
py -3.13 -m pytest tests\test_fixes65.py
py -3.13 -m tests\test_fixes65.py     :: atau terus jalan skrip
```

- Gate penuh mengambil ~15 minit (GUI sebenar, video sebenar).
- Menambah ujian baru: salin pola fail sedia ada (import `isolate`
  dahulu — pitfall 19, jangan sentuh data pemilik!), akhiri dengan
  `RESULT: N passed, M failed` + exit code.
- Jangan tukar `python_files` dalam `pyproject.toml` atau buang
  `tests/conftest.py` — pytest akan import skrip dan binakan runner.

## 4. Konvensyen kod

- Bahasa komen/commit: English, ringkas, jelaskan *sebab*.
- UI strings mesti melalui `t()` (i18n) — jangan hardcode teks.
- File dialog/folder mesti guna helper `tools/` (kekal accessible).
- Pembangunan NVDA: setiap laluan yang gagal mesti ada
  pengumuman (tidak pernah senyap).

## 5. Commit

- Satu commit = satu tujuan; format mesej ikut gaya sedia ada:
  `vX.Y.Z: ringkasan perubahan (rujuk pitfall N bila relevan)`.
- Kemaskini `CHANGELOG.md` dan `doc/senarai-semak.md` bila menambah
  fitur user-facing.
- Versi naik dalam `src/omni_describer_custom/__init__.py`.

## 6. Hantar

Branch → commit → lari gate penuh → PR dengan output gate
(`GATE_ALL_PASS`) dilekat. PR tanpa gate lulus tidak akan
diterima.
