"""
Omni Describer Custom — i18n strings.

Base English strings with Malay (ms) translations.
Usage: from src.i18n.strings import t; t("menu.file")
"""

from __future__ import annotations

import gettext
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Base English strings (fallback)
EN_STRINGS: dict[str, str] = {
    # Menu
    "menu.file": "File",
    "menu.about": "About",
    "menu.edit": "Edit",
    "menu.view": "View",
    "menu.help": "Help",
    "menu.open_video": "Open Video File...",
    "menu.open_url": "Open from URL...",
    "menu.open_youtube": "Open from YouTube...",
    "menu.settings": "Settings...",
    "menu.exit": "Exit",
    "menu.export_txt": "Export as TXT...",
    "menu.export_srt": "Export as SRT...",
    "menu.export_vtt": "Export as WebVTT...",
    "menu.export_audio": "Export as Audio (spoken, synchronized)...",
    "menu.import_desc": "Import Descriptions from SRT / VTT / text file...",
    "impexp.dlg_import": "Import Descriptions",
    "impexp.dlg_export": "Export",
    "impexp.imported": "Imported {count} descriptions into project: {name}",
    "impexp.import_failed": "Import failed: {error}",
    "impexp.invalid_file": "No timed descriptions found in that file.\n\nExpected SRT, WebVTT, or lines like: 0:05 text to speak",
    "impexp.no_project": "No project is open. Open or create a project first.",
    "impexp.nothing_to_export": "The current project has no descriptions to export.",
    "impexp.exported": "Exported {count} descriptions to:\n{path}",
    "impexp.export_failed": "Export failed: {error}",
    "impexp.exporting_title": "Exporting audio",
    "impexp.rendering": "Rendering speech: {done} / {total}",
    "impexp.audio_done": "Audio file ready:\n{path}\n\nSpoken: {rendered}, skipped: {skipped}",
    "menu.export_mp3": "Export Audio (MP3)...",
    "menu.save_project": "Save Project",
    "menu.open_project": "Open Project...",
    "menu.new_project": "New Project...",
    "menu.close_project": "Close Project",
    "settings.video_mode": "Full-video mode (Gemini or MiniMax)",
    "settings.video_mode_hint": "AI watches the whole video once and gives timestamps itself. Ignored for other providers.",
    "settings.fast_mode": "Fast one-shot mode (GLM): ALL frames in one AI request",
    "settings.fast_mode_hint": "Frames get the H:MM:SS time burned in, and the AI watches them all at once. Ignored for other providers.",
    "settings.provider_glm": "OpenRouter",
    "settings.provider_opus": "Opus Proxy",
    "settings.provider_gemini": "Gemini",
    "settings.provider_minimax": "MiniMax",
    "settings.provider_openai": "OpenAI",
    "settings.provider_custom": "Custom",
    "settings.fetch_models": "Fetch models",
    "settings.fetching_models": "Fetching models...",
    "settings.fetch_models_ok": "OK: {count} video models found.",
    "settings.fetch_models_none": "No video-capable models found.",
    "settings.fetch_models_error": "Error: {error}",
    "settings.video_only_hint": "Only models supporting video input are listed; press Fetch models to refresh from the provider catalog.",
    "video.fast_mode_enabled_log": "Fast one-shot mode: {count} frames with burned-in timestamps in {batches} AI request(s).",
    "video.fast_extracting": "Extracting frames with burned-in timestamps...",
    "video.fast_encoding": "Preparing {count} frames for the AI...",
    "video.fast_batches": "Sending {count} frame(s) to the AI in {batches} request(s)...",
    "video.mode_enabled_log": "Full-video mode: uploading the video to the AI provider (no frame extraction).",
    "video.uploading_progress": "Uploading video to the AI provider: {pct}%",
    "video.phase_uploading": "Uploading video to the AI provider...",
    "video.phase_compressing": "Preparing video for upload (compressing)...",
    "video.phase_splitting": "Splitting long video into parts...",
    "video.part_of": "Processing part {part} of {total}...",
    "video.part_progress": "Processing part {part} of {total}, overall {pct}%",
    "video.split_progress": "Splitting and describing video: {pct}%",
    "video.chunk_multi": "Long video: it will be split into parts of {chunk}s ({parts} parts).",
    "video.chunk_single": "Video fits in one part (chunk length {chunk}s).",
    "settings.chunk_seconds": "Video chunk length for AI analysis (seconds per part):",
    "video.phase_processing": "The AI is watching the video (processing)...",
    "video.phase_describing": "The AI is writing descriptions...",
    "video.parsed_count": "The AI returned {count} timestamped descriptions",
    "video.mm_file_error": "MiniMax reported an error for the uploaded video: {msg}",

    # Main Window
    "main.title": "Omni Describer Custom",
    "main.video_source": "Video Source:",
    "main.select_file": "Select File...",
    "main.url": "URL:",
    "main.provider": "AI Provider:",
    "main.prompt": "Prompt Preset:",
    "main.preset_hint": "Prompt preset (pick one, its text appears below for review):",
    "main.custom_prompt": "Prompt to send (from preset, editable):",
    "main.no_preset": "Please select a prompt preset.",
    "status.preset_selected": "Preset selected: {name}",
    "prompts.default_hint": "This is the default prompt: it describes everything visible in each video frame in detail.",
    "main.start": "Start Processing",
    "main.stop": "Stop",
    "main.status": "Status:",
    "main.progress": "Progress:",
    "main.ready": "Ready",
    "main.processing": "Processing...",
    "status.complete": "Complete",
    "status.failed": "Failed",
    "main.no_video": "No video loaded.",

    # Settings Dialog
    "settings.title": "Settings",
    "settings.ai_tab": "AI Settings",
    "settings.tts_tab": "Audio Output",
    "settings.general_tab": "General",
    "settings.provider": "Provider:",
    "settings.api_key": "API Key:",
    "settings.api_key_placeholder": "Enter your API key...",
    "settings.model": "Model:",
    "settings.custom_model": "Custom Model:",
    "settings.base_url": "Base URL:",
    "settings.base_url_placeholder": "https://your-api.example.com/v1",
    "settings.api_format": "API Format:",
    "settings.format_auto": "Auto-detect",
    "settings.format_openai": "OpenAI-compatible",
    "settings.format_anthropic": "Anthropic Messages",
    "settings.test_connection": "Test Connection",
    "settings.testing": "Testing...",
    "settings.test_ok": "OK: {result}",
    "settings.test_error": "Error: {error}",
    "settings.test_no_key": "No API key entered",
    "settings.test_no_url": "Custom provider needs a Base URL",
    "settings.enter_model_name": "Please enter a model name.",
    "settings.tts_engine": "TTS Engine:",
    "settings.voice": "Voice:",
    "settings.speed": "Speed:",
    "settings.frame_rate": "Frame Rate (FPS):",
    "settings.frame_cap": "Max frames per video (0 = no limit):",
    "settings.language": "Language:",
    "settings.output_dir": "Output Directory:",
    "settings.browse": "Browse...",
    "settings.apply": "Apply",
    "settings.cancel": "Cancel",
    "settings.ok": "OK",

    # Player Window
    "player.title": "Described Video Player",
    "player.load_srt": "Load SRT...",
    "player.current_desc": "Current Description:",
    "player.upcoming": "Upcoming:",
    "player.timeline": "Playback position",
    "player.edit_descriptions": "Edit Descriptions...",
    "player.ask_more": "Ask More...",
    "player.explore": "Explore Scene...",
    "player.export": "Export:",
    "player.tokens_used": "Tokens used:",
    "player.play": "Play",
    "player.pause": "Pause",
    "player.stop": "Stop",
    "player.rewind": "Rewind",
    "player.forward": "Forward",

    # Editor Window
    "editor.title": "Description Editor",
    "editor.select_desc": "Select Description:",
    "editor.start_time": "Start Time:",
    "editor.end_time": "End Time:",
    "editor.duration": "Duration:",
    "editor.text": "Description Text:",
    "editor.add_new": "Add New...",
    "editor.delete": "Delete",
    "editor.close": "Close",
    "editor.no_descriptions": "No descriptions yet. Process a video first.",
    "editor.time_validation": "Start time must be before end time.",

    # Scene Explorer
    "explorer.title": "Scene Explorer",
    "explorer.analyze": "Analyze Scene",
    "explorer.description": "Description:",
    "explorer.objects": "Objects:",
    "explorer.close": "Close",
    "explorer.arrow_keys": "Use arrow keys to navigate",
    "explorer.d_key": "D: Full description",
    "explorer.l_key": "L: List objects",
    "explorer.enter_key": "Enter: Describe nearest object",
    "explorer.esc_key": "Escape: Close",

    # Ask More Dialog
    "askmore.title": "Ask About This Scene",
    "askmore.question": "Your Question:",
    "askmore.seconds": "Seconds around current time:",
    "askmore.submit": "Submit",
    "askmore.cancel": "Cancel",
    "askmore.history": "Conversation History:",

    # Status / Log
    "status.loading_video": "Loading video...",
    "status.extracting_frames": "Extracting frames...",
    "status.analyzing": "Analyzing frames with AI...",
    "status.analyzing_video": "The AI is analyzing the video...",
    "status.generating_descriptions": "Generating descriptions...",
    "status.ready": "Ready",
    "status.no_provider": "No AI provider configured. Go to Settings.",
    "status.no_api_key": "API key not set for {provider}. Go to Settings.",
    "status.error": "Error: {error}",
    "status.frame_of": "Frame {current}/{total}",
    "status.processing_complete": "Processing complete! {count} descriptions generated.",
    "process.complete_with_video": "Processing complete! {count} descriptions generated.\n\nVideo saved at:\n{path}",
    "log.video_saved_at": "Video saved at: {path}",
    "download.heartbeat": "Working: {phase} ({secs}s)\nCancel is always available.",

    # Download progress dialog
    "download.dialog_title": "Downloading video",
    "download.loading_info": "Loading video info...",
    "download.download_done": "Download complete. Preparing frame extraction...",
    "download.preparing": "Preparing download...",
    "download.video": "Video stream",
    "download.audio": "Audio stream",
    "download.merging": "Merging video and audio with ffmpeg...",
    "download.cancelling": "Cancelling download...",
    "download.cancelled_log": "Download cancelled by user.",
    "download.extracting": "Extracting frames...",
    "download.extract_progress": "Extracting frames: {count} frames",
    "download.analyzing": "AI analysis: {done}/{total} frames",
    "process.frame_capped": "Frame cap reached: analyzing the first {cap} of {total} frames",
    "download.cancel_analysis": "Cancelling AI analysis...",
    "download.saving": "Saving project...",
    "process.complete_title": "Processing complete",
    "process.failed_title": "Processing failed",
    "error.ai_empty": "AI returned no usable descriptions.",
    "process.no_descriptions": "No descriptions were generated.\n\nThe AI provider returned no usable text. Check your API key and connection in Settings (Test Connection), then try again.\n\nDetails are in the log below.",
    "project.dialog_title": "Open Project",
    "project.opened_empty": "Project '{name}' has no descriptions.\n\nRun Start Processing on the video, or import descriptions from the File menu.",
    "project.remove_btn": "&Remove",
    "project.remove_confirm": "Delete project '{name}'?\n\nThis permanently removes its database, media folder (video + subtitles) and description list.\n\nThis cannot be undone.",
    "project.remove_title": "Remove Project",
    "project.removed_log": "Project removed: {name}",
    "project.remove_failed": "Could not fully remove project '{name}': {error}",
    "project.open_btn": "&Open",
    "project.select_hint": "Select a project:",
    "project.dedupe_found": "This video already has a project:",
    "project.dedupe_open": "&Open existing project",
    "project.dedupe_new": "&Process again as new project",
    "project.dedupe_title": "Existing project found",

    # Errors
    "error.no_video": "No video loaded.",
    "error.no_frames": "No frames extracted.",
    "error.ai_failed": "AI analysis failed: {error}",
    "error.tts_failed": "Text-to-speech failed: {error}",
    "error.save_failed": "Failed to save: {error}",
    "error.invalid_time": "Invalid time range.",

    # Misc
    "yes": "Yes",
    "no": "No",
    "ok": "OK",
    "cancel": "Cancel",
    "close": "Close",
    "save": "Save",
    "delete": "Delete",
    "add": "Add",
    "edit": "Edit",
    "name": "Name:",
    "path": "Path:",
    "duration": "Duration:",
    "language": "Language:",
}


# Malay translations
MS_STRINGS: dict[str, str] = {
    # Menu
    "menu.file": "Fail",
    "menu.about": "Perihal",
    "menu.edit": "Sunting",
    "menu.view": "Lihat",
    "menu.help": "Bantuan",
    "menu.open_video": "Buka Fail Video...",
    "menu.open_url": "Buka dari URL...",
    "menu.open_youtube": "Buka dari YouTube...",
    "menu.settings": "Tetapan...",
    "menu.exit": "Keluar",
    "menu.export_txt": "Eksport sebagai TXT...",
    "menu.export_srt": "Eksport sebagai SRT...",
    "menu.export_vtt": "Eksport sebagai WebVTT...",
    "menu.export_audio": "Eksport sebagai Audio (lisan, disegerak)...",
    "menu.import_desc": "Import Penerangan dari fail SRT / VTT / teks...",
    "impexp.dlg_import": "Import Penerangan",
    "impexp.dlg_export": "Eksport",
    "impexp.imported": "{count} penerangan diimport ke projek: {name}",
    "impexp.import_failed": "Import gagal: {error}",
    "impexp.invalid_file": "Tiada penerangan bertambah waktu dalam fail itu.\n\nJangkaan SRT, WebVTT, atau baris seperti: 0:05 teks untuk dilafal",
    "impexp.no_project": "Tiada projek terbuka. Buka atau cipta projek dahulu.",
    "impexp.nothing_to_export": "Projek semasa tiada penerangan untuk dieksport.",
    "impexp.exported": "{count} penerangan dieksport ke:\n{path}",
    "impexp.export_failed": "Eksport gagal: {error}",
    "impexp.exporting_title": "Mengeksport audio",
    "impexp.rendering": "Menjana suara: {done} / {total}",
    "impexp.audio_done": "Fail audio siap:\n{path}\n\nDilafal: {rendered}, dilangkau: {skipped}",
    "menu.export_mp3": "Eksport Audio (MP3)...",
    "menu.save_project": "Simpan Projek",
    "menu.open_project": "Buka Projek...",
    "menu.new_project": "Projek Baharu...",
    "menu.close_project": "Tutup Projek",
    "settings.video_mode": "Mod video penuh (Gemini atau MiniMax)",
    "settings.video_mode_hint": "AI menonton seluruh video sekali dan beri timestamp sendiri. Diabaikan untuk pembekal lain.",
    "settings.fast_mode": "Mod pantas satu-request (GLM): SEMUA frame dalam satu permintaan AI",
    "settings.fast_mode_hint": "Masa H:MM:SS dibakar pada setiap frame, dan AI menonton semuanya sekali gus. Diabaikan untuk pembekal lain.",
    "settings.provider_glm": "OpenRouter",
    "settings.provider_opus": "Opus Proxy",
    "settings.provider_gemini": "Gemini",
    "settings.provider_minimax": "MiniMax",
    "settings.provider_openai": "OpenAI",
    "settings.provider_custom": "Tersuai",
    "settings.fetch_models": "Dapatkan model",
    "settings.fetching_models": "Mendapatkan model...",
    "settings.fetch_models_ok": "OK: {count} model video dijumpai.",
    "settings.fetch_models_none": "Tiada model yang menyokong video.",
    "settings.fetch_models_error": "Ralat: {error}",
    "settings.video_only_hint": "Hanya model yang menyokong input video disenaraikan; tekan Dapatkan model untuk muat semula dari katalog pembekal.",
    "video.fast_mode_enabled_log": "Mod pantas satu-request: {count} frame ber-cap masa terbakar dalam {batches} permintaan AI.",
    "video.fast_extracting": "Mengekstrak frame dengan cap masa terbakar...",
    "video.fast_encoding": "Menyediakan {count} frame untuk AI...",
    "video.fast_batches": "Menghantar {count} frame kepada AI dalam {batches} permintaan...",
    "video.mode_enabled_log": "Mod video penuh: memuat naik video ke penyedia AI (tanpa ekstraksi frame).",
    "video.uploading_progress": "Memuat naik video ke penyedia AI: {pct}%",
    "video.phase_uploading": "Memuat naik video ke penyedia AI...",
    "video.phase_compressing": "Menyediakan video untuk dimuat naik (memampat)...",
    "video.phase_splitting": "Memecahkan video panjang kepada beberapa bahagian...",
    "video.part_of": "Memproses bahagian {part} daripada {total}...",
    "video.part_progress": "Memproses bahagian {part} daripada {total}, keseluruhan {pct}%",
    "video.split_progress": "Memecah dan menganalisis video: {pct}%",
    "video.chunk_multi": "Video panjang: ia akan dipecah kepada bahagian {chunk}s ({parts} bahagian).",
    "video.chunk_single": "Video muat dalam satu bahagian (panjang bahagian {chunk}s).",
    "settings.chunk_seconds": "Panjang bahagian video untuk analisis AI (saat setiap bahagian):",
    "video.phase_processing": "AI sedang menonton video (pemprosesan)...",
    "video.phase_describing": "AI sedang menulis penerangan...",
    "video.parsed_count": "AI pulangkan {count} penerangan ber-timestamp",
    "video.mm_file_error": "MiniMax melaporkan ralat bagi video yang dimuat naik: {msg}",

    # Main Window
    "main.title": "Omni Describer Custom",
    "main.video_source": "Sumber Video:",
    "main.select_file": "Pilih Fail...",
    "main.url": "URL:",
    "main.provider": "Pembekal AI:",
    "main.prompt": "Preset Arahan:",
    "main.preset_hint": "Preset arahan (pilih satu, teksnya muncul di bawah untuk semakan):",
    "main.custom_prompt": "Arahan untuk dihantar (dari preset, boleh disunting):",
    "main.no_preset": "Sila pilih preset arahan.",
    "status.preset_selected": "Preset dipilih: {name}",
    "prompts.default_hint": "Ini preset lalai: ia menghuraikan semua yang kelihatan dalam setiap frame video secara terperinci.",
    "main.start": "Mula Pemprosesan",
    "main.stop": "Henti",
    "main.status": "Status:",
    "main.progress": "Kemajuan:",
    "main.ready": "Sedia",
    "main.processing": "Memproses...",
    "status.complete": "Selesai",
    "status.failed": "Gagal",

    # Settings Dialog
    "settings.title": "Tetapan",
    "settings.ai_tab": "Tetapan AI",
    "settings.tts_tab": "Output Audio",
    "settings.general_tab": "Am",
    "settings.provider": "Pembekal:",
    "settings.api_key": "Kunci API:",
    "settings.api_key_placeholder": "Masukkan kunci API anda...",
    "settings.model": "Model:",
    "settings.custom_model": "Model Pilihan:",
    "settings.base_url": "URL Asas:",
    "settings.base_url_placeholder": "https://api-contoh-anda.example.com/v1",
    "settings.api_format": "Format API:",
    "settings.format_auto": "Auto-kesan",
    "settings.format_openai": "Serasi OpenAI",
    "settings.format_anthropic": "Pesanan Anthropic",
    "settings.test_connection": "Uji Sambungan",
    "settings.testing": "Menguji...",
    "settings.test_ok": "OK: {result}",
    "settings.test_error": "Ralat: {error}",
    "settings.test_no_key": "Tiada kunci API dimasukkan",
    "settings.test_no_url": "Pembekal custom perlau URL Asas",
    "settings.enter_model_name": "Sila masukkan nama model.",
    "settings.tts_engine": "Enjin TTS:",
    "settings.voice": "Suara:",
    "settings.speed": "Kelajuan:",
    "settings.frame_rate": "Kadar Kerangka (FPS):",
    "settings.frame_cap": "Had Maksimum Frame Setiap Video (0 = tiada had):",
    "settings.language": "Bahasa:",
    "settings.output_dir": "Direktori Output:",
    "settings.browse": "Layarari...",
    "settings.apply": "Terapkan",
    "settings.cancel": "Batal",
    "settings.ok": "OK",

    # Player Window
    "player.title": "Pemain Video Berpenerangan",
    "player.load_srt": "Muat SRT...",
    "player.current_desc": "Penerangan Semasa:",
    "player.upcoming": "Akan Datang:",
    "player.timeline": "Kedudukan main balik",
    "player.edit_descriptions": "Sunting Penerangan...",
    "player.ask_more": "Tanya Lagi...",
    "player.explore": "Jelajah Adegan...",
    "player.export": "Eksport:",
    "player.tokens_used": "Token digunakan:",
    "player.play": "Main",
    "player.pause": "Jeda",
    "player.stop": "Henti",
    "player.rewind": "Undur",
    "player.forward": "Maju",

    # Editor Window
    "editor.title": "Penyunting Penerangan",
    "editor.select_desc": "Pilih Penerangan:",
    "editor.start_time": "Masa Mula:",
    "editor.end_time": "Masa Tamat:",
    "editor.duration": "Tempoh:",
    "editor.text": "Teks Penerangan:",
    "editor.add_new": "Tambah Baharu...",
    "editor.delete": "Padam",
    "editor.close": "Tutup",
    "editor.no_descriptions": "Tiada penerangan lagi. Proses video dahulu.",
    "editor.time_validation": "Masa mula mesti sebelum masa tamat.",

    # Scene Explorer
    "explorer.title": "Penjelajah Adegan",
    "explorer.analyze": "Analisis Adegan",
    "explorer.description": "Penerangan:",
    "explorer.objects": "Objek:",
    "explorer.close": "Tutup",
    "explorer.arrow_keys": "Gunakan anak panah untuk bergerak",
    "explorer.d_key": "D: Penerangan penuh",
    "explorer.l_key": "L: Senarai objek",
    "explorer.enter_key": "Enter: Huraikan objek terdekat",
    "explorer.esc_key": "Escape: Tutup",

    # Ask More
    "askmore.title": "Tanya Tentang Adegan Ini",
    "askmore.question": "Soalan Anda:",
    "askmore.seconds": "Saiz sekitar masa semasa:",
    "askmore.submit": "Hantar",
    "askmore.cancel": "Batal",
    "askmore.history": "Sejarah Perbualan:",

    # Status
    "status.loading_video": "Memuatkan video...",
    "status.extracting_frames": "Mengekstrak kerangka...",
    "status.analyzing": "Menganalisis kerangka dengan AI...",
    "status.analyzing_video": "AI sedang menganalisis video...",
    "status.generating_descriptions": "Menerangkan penerangan...",
    "status.ready": "Sedia",
    "status.no_provider": "Tiada pembekal AI. Pergi ke Tetapan.",
    "status.no_api_key": "Kunci API tidak diset untuk {provider}. Pergi ke Tetapan.",
    "status.error": "Ralat: {error}",
    "status.frame_of": "Kerangka {current}/{total}",
    "status.processing_complete": "Pemprosesan selesai! {count} penerangan dijana.",
    "process.complete_with_video": "Pemprosesan selesai! {count} penerangan dijana.\n\nVideo disimpan di:\n{path}",
    "log.video_saved_at": "Video disimpan di: {path}",
    "download.heartbeat": "Sedang bekerja: {phase} ({secs}s)\nBatal sentiasa tersedia.",

    # Dialog kemajuan muat turun
    "download.dialog_title": "Memuat turun video",
    "download.loading_info": "Memuatkan maklumat video...",
    "download.download_done": "Muat turun selesai. Bersedia untuk ekstrak frame...",
    "download.preparing": "Menyediakan muat turun...",
    "download.video": "Strim video",
    "download.audio": "Strim audio",
    "download.merging": "Menggabungkan video dan audio dengan ffmpeg...",
    "download.cancelling": "Membatalkan muat turun...",
    "download.cancelled_log": "Muat turun dibatalkan oleh pengguna.",
    "download.extracting": "Mengekstrak frame...",
    "download.extract_progress": "Mengekstrak frame: {count} frame",
    "download.analyzing": "Analisis AI: {done}/{total} frame",
    "process.frame_capped": "Had frame dicapai: menganalisis {cap} frame pertama daripada {total}",
    "download.cancel_analysis": "Membatalkan analisis AI...",
    "download.saving": "Menyimpan projek...",
    "process.complete_title": "Pemprosesan selesai",
    "process.failed_title": "Pemprosesan gagal",
    "error.ai_empty": "AI tidak memulangkan sebarang penerangan yang boleh diguna.",
    "process.no_descriptions": "Tiada penerangan dijana.\n\nPenyedia AI tidak memulangkan teks yang boleh diguna. Semak kunci API dan sambungan dalam Tetapan (Uji Sambungan), kemudian cuba lagi.\n\nButiran ada dalam log di bawah.",
    "project.dialog_title": "Buka Projek",
    "project.opened_empty": "Projek '{name}' tiada penerangan.\n\nJalankan Mula Pemprosesan pada video, atau import penerangan dari menu File.",
    "project.remove_btn": "&Buang",
    "project.remove_confirm": "Padam projek '{name}'?\n\nIni memadam kekal pangkalan data, folder media (video + sari kata) dan senarai penerangan.\n\nTindakan ini tidak boleh dibatalkan.",
    "project.remove_title": "Buang Projek",
    "project.removed_log": "Projek dibuang: {name}",
    "project.remove_failed": "Tidak dapat memadam projek '{name}' sepenuhnya: {error}",
    "project.open_btn": "&Buka",
    "project.select_hint": "Pilih projek:",
    "project.dedupe_found": "Video ini sudah ada projek:",
    "project.dedupe_open": "&Buka projek sedia ada",
    "project.dedupe_new": "&Proses semula sebagai projek baharu",
    "project.dedupe_title": "Projek sedia ada dijumpai",

    # Errors
    "error.no_video": "Tiada video dimuatkan.",
    "error.no_frames": "Tiada kerangkan diekstrak.",
    "error.ai_failed": "Analisis AI gagal: {error}",
    "error.tts_failed": "Teks-ke-pertuturan gagal: {error}",
    "error.save_failed": "Gagal simpan: {error}",
    "error.invalid_time": "Julat masa tidak sah.",

    # Misc
    "yes": "Ya",
    "no": "Tidak",
    "ok": "OK",
    "cancel": "Batal",
    "close": "Tutup",
    "save": "Simpan",
    "delete": "Padam",
    "add": "Tambah",
    "edit": "Sunting",
    "name": "Nama:",
    "path": "Laluan:",
    "duration": "Tempoh:",
    "language": "Bahasa:",
}


class I18n:
    """Internationalization manager."""

    _translations: dict[str, dict[str, str]] = {
        "en": EN_STRINGS,
        "ms": MS_STRINGS,
    }
    _current_lang: str = "en"

    @classmethod
    def set_language(cls, lang: str) -> None:
        """Set current language."""
        if lang in cls._translations:
            cls._current_lang = lang
        else:
            cls._current_lang = "en"
        logger.info("Language set to: %s", cls._current_lang)

    @classmethod
    def t(cls, key: str, **kwargs: Any) -> str:
        """
        Translate a string key.
        Usage: t("menu.file") or t("status.error", error="connection failed")
        """
        strings = cls._translations.get(cls._current_lang, EN_STRINGS)
        text = strings.get(key, EN_STRINGS.get(key, key))
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, ValueError):
                pass
        return text

    @classmethod
    def add_translation(cls, lang: str, strings: dict[str, str]) -> None:
        """Add a new language translation."""
        cls._translations[lang] = strings

    @classmethod
    def available_languages(cls) -> list[str]:
        """Return list of available language codes."""
        return list(cls._translations.keys())


# Convenience function
def t(key: str, **kwargs: Any) -> str:
    """Translate a string key."""
    return I18n.t(key, **kwargs)
