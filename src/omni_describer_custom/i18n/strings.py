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
    "menu.export_mp3": "Export Audio (MP3)...",
    "menu.save_project": "Save Project",
    "menu.open_project": "Open Project...",
    "menu.new_project": "New Project...",
    "menu.close_project": "Close Project",

    # Main Window
    "main.title": "Omni Describer Custom",
    "main.video_source": "Video Source:",
    "main.select_file": "Select File...",
    "main.url": "URL:",
    "main.provider": "AI Provider:",
    "main.prompt": "Prompt Preset:",
    "main.start": "Start Processing",
    "main.stop": "Stop",
    "main.status": "Status:",
    "main.progress": "Progress:",
    "main.ready": "Ready",
    "main.processing": "Processing...",
    "main.complete": "Complete",
    "main.failed": "Failed",

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
    "settings.language": "Language:",
    "settings.output_dir": "Output Directory:",
    "settings.apply": "Apply",
    "settings.cancel": "Cancel",
    "settings.ok": "OK",

    # Player Window
    "player.title": "Described Video Player",
    "player.current_desc": "Current Description:",
    "player.upcoming": "Upcoming:",
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
    "status.generating_descriptions": "Generating descriptions...",
    "status.ready": "Ready",
    "status.no_provider": "No AI provider configured. Go to Settings.",
    "status.no_api_key": "API key not set for {provider}. Go to Settings.",
    "status.error": "Error: {error}",
    "status.frame_of": "Frame {current}/{total}",
    "status.processing_complete": "Processing complete! {count} descriptions generated.",

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
    "menu.export_mp3": "Eksport Audio (MP3)...",
    "menu.save_project": "Simpan Projek",
    "menu.open_project": "Buka Projek...",
    "menu.new_project": "Projek Baharu...",
    "menu.close_project": "Tutup Projek",

    # Main Window
    "main.title": "Omni Describer Custom",
    "main.video_source": "Sumber Video:",
    "main.select_file": "Pilih Fail...",
    "main.url": "URL:",
    "main.provider": "Pembekal AI:",
    "main.prompt": "Preset Arahan:",
    "main.start": "Mula Pemprosesan",
    "main.stop": "Henti",
    "main.status": "Status:",
    "main.progress": "Kemajuan:",
    "main.ready": "Sedia",
    "main.processing": "Memproses...",
    "main.complete": "Selesai",
    "main.failed": "Gagal",

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
    "settings.language": "Bahasa:",
    "settings.output_dir": "Direktori Output:",
    "settings.apply": "Terapkan",
    "settings.cancel": "Batal",
    "settings.ok": "OK",

    # Player Window
    "player.title": "Pemain Video Berpenerangan",
    "player.current_desc": "Penerangan Semasa:",
    "player.upcoming": "Akan Datang:",
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
    "status.generating_descriptions": "Menerangkan penerangan...",
    "status.ready": "Sedia",
    "status.no_provider": "Tiada pembekal AI. Pergi ke Tetapan.",
    "status.no_api_key": "Kunci API tidak diset untuk {provider}. Pergi ke Tetapan.",
    "status.error": "Ralat: {error}",
    "status.frame_of": "Kerangka {current}/{total}",
    "status.processing_complete": "Pemprosesan selesai! {count} penerangan dijana.",

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
