"""
Omni Describer Custom — Prompt Manager.

Manages prompt presets: CRUD, per-language, validation.
"""

from __future__ import annotations

import logging
from typing import Any

from .settings_store import SettingsStore

logger = logging.getLogger(__name__)

# ── Prompt presets (v1.6.0) ──────────────────────────────────────
#
# Rewritten against the published audio-description standards, because
# the old presets contradicted them: "describe everything you see in
# detail" is the opposite of what audio description is, and "include
# emotional tone" asks the AI to interpret instead of report.
#
# Sources, all agreeing on the core:
#   DCMP Description Key (educational media standard)
#     "Describe objectively, without interpretation, censorship, or
#     comment"; present tense, active voice, third person; describe what
#     is ESSENTIAL to follow the programme; never describe after the
#     visual has passed; do not try to fill every silence.
#   Netflix Audio Description Style Guide v2.1
#     Skip description when the information is already given by dialogue;
#     never describe over main dialogue; do not guess race, ethnicity or
#     gender identity; read on-screen text verbatim.
#   W3C/WAI Audio Description
#     Convey the visual information needed to understand the content;
#     no need to describe what is apparent from the audio; EXTENDED
#     description is for when the natural gaps are too short.
#   ADLAB Guidelines (EU)
#     Prioritise focal characters, their actions and the space; decide
#     what other channels already convey before spending a gap on it.
#
# The presets differ by DESCRIPTION STRATEGY, not by film genre: the
# standards prescribe the same rules for every genre and vary only pace
# and tone. Netflix names exactly two genres (children's content and
# horror/suspense), which is why those two exist here and "action" or
# "thriller" do not.
#
# Every preset is written to be spoken by TTS into the gaps between
# events, so brevity is part of the instruction, not an afterthought.

_AD_CORE_EN = (
    "You are writing audio description for a blind viewer who HEARS the "
    "video's own soundtrack. Describe only what a sighted viewer sees and "
    "a listener cannot hear.\n"
    "- Never describe dialogue, music or sound effects; they are already "
    "audible.\n"
    "- Present tense, third person, active voice.\n"
    "- Report what is observable, not what it means: \"she lowers her eyes "
    "and turns away\", not \"she is ashamed\".\n"
    "- Prioritise who is present, what they do, where they are, and any "
    "change the story depends on. Leave out decorative detail.\n"
    "- Read on-screen text when it carries information.\n"
    "- Use one consistent name for each person. Describe appearance only "
    "when it matters, and do not state race, ethnicity or gender identity "
    "unless the video establishes it.\n"
    "- PLACE DESCRIPTIONS WHERE NO ONE IS SPEAKING. When a transcript "
    "is given below, it carries the times people talk: aim for the gaps "
    "between those lines, not on top of them. Narration over dialogue "
    "costs the listener both. If the talking is continuous and there is "
    "no gap, describe only what they cannot do without, and let the rest "
    "go.\n"
    "- PACE FOR SPEECH. Every line you write is read aloud at about two "
    "words per second, so a 12-word line takes six seconds to say. Before "
    "you add a description, make sure the NEXT one is far enough away for "
    "this one to finish. When events crowd together, describe the most "
    "important one and let the others pass — a gap of silence costs the "
    "listener nothing, but two descriptions colliding costs them both.\n"
    "- HARD LIMIT: 12 words per description. Not a target, a ceiling. "
    "Measured with a real voice, a 21-word line needs 11 seconds to speak "
    "and arrives on top of the next one.\n"
    "- Do not narrate film technique: no camera moves, cuts, zooms, angles "
    "or \"the video shows\". Saying someone speaks or looks to camera is "
    "fine when they address the viewer directly."
)

_AD_CORE_MS = (
    "Anda menulis penerangan audio untuk penonton buta yang MENDENGAR bunyi "
    "asal video. Huraikan hanya apa yang dilihat oleh mata dan tidak boleh "
    "didengar.\n"
    "- Jangan huraikan dialog, muzik atau kesan bunyi — semua itu sudah "
    "kedengaran.\n"
    "- Kala kini, orang ketiga, ayat aktif.\n"
    "- Nyatakan apa yang kelihatan, bukan tafsirannya: \"dia menundukkan "
    "pandangan dan berpaling\", bukan \"dia berasa malu\".\n"
    "- Utamakan siapa yang ada, apa yang mereka buat, di mana, dan "
    "perubahan penting kepada cerita. Tinggalkan butiran hiasan.\n"
    "- Baca teks pada skrin bila ia membawa maklumat.\n"
    "- Guna satu nama yang konsisten bagi setiap orang. Huraikan rupa hanya "
    "bila ia penting, dan jangan nyatakan bangsa, etnik atau identiti "
    "jantina melainkan video itu sendiri menetapkannya.\n"
    "- LETAKKAN PENERANGAN DI TEMPAT TIADA ORANG BERCAKAP. Bila "
    "transkrip diberi di bawah, ia membawa masa orang bercakap: sasarkan "
    "celah antara baris itu, bukan di atasnya. Narasi atas dialog "
    "merugikan pendengar kedua-duanya. Kalau percakapan berterusan tanpa "
    "celah, huraikan hanya apa yang mereka benar-benar perlukan, dan "
    "biarkan yang lain berlalu.\n"
    "- SESUAIKAN DENGAN PERTUTURAN. Setiap baris dibaca kuat pada kadar "
    "kira-kira dua patah perkataan sesaat, jadi baris 12 patah perkataan "
    "mengambil enam saat. Sebelum menambah satu penerangan, pastikan "
    "penerangan BERIKUTNYA cukup jauh untuk yang ini habis dituturkan. "
    "Bila peristiwa berhimpit, pilih yang paling penting sahaja — "
    "kesenyapan tidak merugikan pendengar, tetapi dua penerangan yang "
    "berlanggar merugikan kedua-duanya.\n"
    "- HAD KERAS: 12 patah perkataan bagi setiap penerangan. Bukan "
    "sasaran, tetapi siling. Diukur dengan suara sebenar, baris 21 patah "
    "perkataan perlu 11 saat dan bertindih dengan penerangan seterusnya.\n"
    "- Jangan menceritakan teknik filem: tiada pergerakan kamera, potongan, "
    "zum, sudut atau \"video ini menunjukkan\". Menyebut seseorang bercakap "
    "atau memandang ke kamera dibenarkan bila dia menyapa penonton terus."
)

DEFAULT_PROMPTS = {
    # 1. The standard. Use this unless something specific says otherwise.
    "default": _AD_CORE_EN,

    # 2. Dense dialogue: the gaps are tiny, so spend them carefully.
    "tight": _AD_CORE_EN + (
        "\n\nThis video talks almost continuously. Gaps are very short, so "
        "describe ONLY what makes the dialogue make sense: who is speaking "
        "to whom, who enters or leaves, and anything the words refer to but "
        "do not name. Skip everything else. Keep each description to a "
        "short phrase."
    ),

    # 3. W3C extended description: slow or information-dense material.
    "extended": _AD_CORE_EN + (
        "\n\nThis video has long stretches without speech, so there is room "
        "for fuller description. Use it for information the viewer needs "
        "and cannot hear: the layout of a space, what a diagram or chart "
        "shows and what it means numerically, steps in a demonstration, and "
        "on-screen text read as written. Stay factual — more room is not "
        "permission to interpret. Here the ceiling rises to 25 words, "
        "but only where the silence genuinely allows it."
    ),

    # 4. Audio subtitling: the recognised service for foreign speech.
    "foreign": _AD_CORE_EN + (
        "\n\nThe people in this video speak a language the listener may not "
        "understand. In addition to the visual description, convey what is "
        "said: give the meaning briefly in the language you are writing in, "
        "attributing it to the speaker (\"the woman says she is leaving "
        "tonight\"). Summarise rather than translating word for word, and "
        "read any subtitles on screen. CONVEYING SPEECH IS THE MAIN JOB of "
        "this preset: whenever someone says something that matters, say "
        "what they said — that outranks describing what you can see. The "
        "ceiling here is 25 words, not 12. ONE LIST ONLY: weave what is "
        "said into the same chronological list as what is seen, in time "
        "order. Do not write the speech first and the visuals afterwards, "
        "and do not produce two passes."
    ),

    # 5. Netflix names this genre explicitly: silence carries the tension.
    "suspense": _AD_CORE_EN + (
        "\n\nThis video builds tension through silence and music. Do not "
        "fill dramatic pauses — a held silence is information too. Never "
        "reveal what is about to happen before the video shows it: describe "
        "the shadow, not the killer waiting behind the door. Short, plain "
        "sentences; let the soundtrack do its work."
    ),

    # 6. The other genre the standard names: tone follows the audience.
    "children": _AD_CORE_EN + (
        "\n\nThis video is for children. Use simple everyday words and short "
        "sentences, and name colours, animals and actions plainly. Keep a "
        "warm, friendly tone without becoming excited or silly, and never "
        "explain the joke or the lesson — describe what happens and let the "
        "child work it out."
    ),

    # 7. Tutorials, slides, anything where the screen IS the content.
    "onscreen_text": _AD_CORE_EN + (
        "\n\nThe screen in this video carries text and graphics that matter: "
        "slides, menus, code, forms, charts. Read the text as written, in "
        "reading order, and say where it sits when position matters (which "
        "menu, which column, which button). For a chart, give what it "
        "measures and the values that matter, not its colours. Describe "
        "what the user is doing: what they click, type or select. Text "
        "read verbatim may exceed 12 words; your own wording may not."
    ),

    # ── Malay versions (same strategies, same rules) ──────────────
    "ms_default": _AD_CORE_MS,

    "ms_tight": _AD_CORE_MS + (
        "\n\nVideo ini bercakap hampir tanpa henti. Celah amat pendek, jadi "
        "huraikan HANYA apa yang menjadikan dialog itu difahami: siapa "
        "bercakap dengan siapa, siapa masuk atau keluar, dan apa yang "
        "dirujuk oleh percakapan tetapi tidak dinamakan. Tinggalkan yang "
        "lain. Pendekkan setiap penerangan kepada satu frasa."
    ),

    "ms_extended": _AD_CORE_MS + (
        "\n\nVideo ini ada tempoh panjang tanpa percakapan, jadi ada ruang "
        "untuk penerangan lebih penuh. Gunakannya untuk maklumat yang "
        "diperlukan tetapi tidak boleh didengar: susun atur ruang, apa yang "
        "ditunjukkan oleh rajah atau carta berserta nilainya, langkah dalam "
        "demonstrasi, dan teks pada skrin dibaca seperti tertulis. Kekal "
        "berasaskan fakta — ruang lebih bukan kebenaran untuk mentafsir. "
        "Di sini siling naik kepada 25 patah perkataan, tetapi hanya bila "
        "kesenyapan benar-benar mengizinkannya."
    ),

    "ms_foreign": _AD_CORE_MS + (
        "\n\nOrang dalam video ini bercakap dalam bahasa yang mungkin tidak "
        "difahami pendengar. Selain penerangan visual, sampaikan apa yang "
        "dikatakan: beri maksudnya secara ringkas dalam bahasa penulisan "
        "anda, dengan menyebut siapa yang berkata (\"wanita itu berkata dia "
        "akan pergi malam ini\"). Ringkaskan, jangan terjemah perkataan "
        "demi perkataan, dan baca sari kata yang ada pada skrin. "
        "MENYAMPAIKAN PERTUTURAN ADALAH KERJA UTAMA preset ini: setiap "
        "kali seseorang berkata sesuatu yang penting, nyatakan apa yang "
        "dikatakannya — itu lebih penting daripada menghuraikan visual. "
        "Untuk itu siling di sini ialah 25 patah perkataan, bukan 12. "
        "SATU SENARAI SAHAJA: gabungkan apa yang dikatakan ke dalam "
        "senarai kronologi yang sama dengan apa yang dilihat, mengikut "
        "urutan masa. Jangan tulis pertuturan dahulu kemudian visual "
        "kemudian, dan jangan hasilkan dua pusingan."
    ),

    "ms_suspense": _AD_CORE_MS + (
        "\n\nVideo ini membina ketegangan melalui kesenyapan dan muzik. "
        "Jangan penuhi jeda dramatik — senyap itu sendiri maklumat. Jangan "
        "dedahkan apa yang bakal berlaku sebelum video menunjukkannya: "
        "huraikan bayang itu, bukan pembunuh yang menunggu di balik pintu. "
        "Ayat pendek dan mudah; biar bunyi melakukan kerjanya."
    ),

    "ms_children": _AD_CORE_MS + (
        "\n\nVideo ini untuk kanak-kanak. Guna perkataan harian yang mudah "
        "dan ayat pendek, dan namakan warna, haiwan serta perbuatan secara "
        "jelas. Kekalkan nada mesra tanpa menjadi terlalu teruja, dan "
        "jangan terangkan jenaka atau pengajarannya — huraikan apa yang "
        "berlaku dan biar kanak-kanak itu memahaminya sendiri."
    ),

    "ms_onscreen_text": _AD_CORE_MS + (
        "\n\nSkrin dalam video ini membawa teks dan grafik yang penting: "
        "slaid, menu, kod, borang, carta. Baca teks seperti tertulis "
        "mengikut urutan bacaan, dan nyatakan kedudukannya bila itu penting "
        "(menu mana, lajur mana, butang mana). Bagi carta, beri apa yang "
        "diukur dan nilai yang penting, bukan warnanya. Huraikan apa yang "
        "dilakukan pengguna: apa yang diklik, ditaip atau dipilih. Teks yang "
        "dibaca seperti tertulis boleh melebihi 12 patah perkataan; ayat "
        "anda sendiri tidak boleh."
    ),
}

# Presets shipped before v1.6.0. They are removed on first run — but ONLY
# when the stored text still matches what we shipped, so a preset the
# user edited or wrote themselves is never touched.
LEGACY_PROMPTS = {
    "default": "Describe everything you see in this video frame in detail. Focus on visual elements, actions, context, and any text visible.",
    "detailed": "Provide a comprehensive description of this frame. Include all visual details, colors, lighting, emotional tone, and spatial relationships.",
    "minimal": "Brief description of this frame in one sentence.",
    "accessibility": "Describe this frame for a blind or visually impaired user. Be specific about spatial relationships, text content, and important visual information. Use clear, concise language.",
    "characters": "Identify and describe all people or characters in this frame. Include their appearance, actions, expressions, and positions.",
    "text_ocr": "Transcribe and describe any text visible in this frame. Include signs, subtitles, on-screen graphics, and written content.",
    "ms_default": "Huraikan semua yang anda lihat dalam kerangka video ini dengan terperinci. Fokus pada elemen visual, aksi, konteks, dan sebarang teks yang kelihatan.",
    "ms_accessibility": "Huraikan kerangka ini untuk pengguna buta atau kurang upaya penglihatan. Tekankan hubungan ruang, kandungan teks, dan maklumat visual penting.",
    # Also shipped from settings_store.DEFAULTS before v1.6.0, which kept
    # its own slightly different copy of the same presets. Both wordings
    # are in the wild, so BOTH must be recognised — a live install was
    # found still offering the "emotional tone" preset because only the
    # prompt_manager wording was listed here.
    "ms_default_alt": "Huraikan semua yang anda lihat dalam kerangka video ini dengan terperinci. Fokus pada elemen visual, aksi, dan konteks.",
    "default_alt": "Describe everything you see in this video frame in detail. Focus on visual elements, actions, and context.",
    "accessibility_alt": "Describe this frame for a blind or visually impaired user. Be specific about spatial relationships, text content, and important visual information.",
    "ms_accessibility_alt": "Huraikan kerangka ini untuk pengguna buta atau kurang upaya penglihatan. Nyatakan hubungan ruang, kandungan teks, dan maklumat visual penting dengan jelas dan ringkas.",
    "detailed_alt": "Provide a comprehensive description of this frame. Include all visual details, text visible, colors, lighting, and emotional tone.",
}

DEFAULT_LANGUAGE = "en"


class PromptManager:
    """
    Manages prompt presets with per-language support.
    Prompts are stored in SettingsStore but managed through this class.
    """

    def __init__(self, settings: SettingsStore | None = None):
        self.settings = settings or SettingsStore()
        self._language = DEFAULT_LANGUAGE
        self._ensure_defaults()

    def _ensure_defaults(self):
        """Ensure default prompts exist, retiring the pre-v1.6.0 set.

        The old presets told the AI to describe everything in detail and
        to report "emotional tone" — both contrary to every published
        audio-description standard. They are dropped so they cannot be
        picked by accident, but ONLY when the stored text is still
        exactly what we shipped: anything the user edited, renamed or
        wrote themselves survives untouched.
        """
        existing = self.settings.get_prompts()
        shipped = set(LEGACY_PROMPTS.values())
        for name, text in existing.items():
            if name in DEFAULT_PROMPTS:
                continue  # still part of the current set
            if text in shipped:
                self.settings.delete_prompt(name)
                logger.info("Retired obsolete prompt preset: %s", name)

        existing = self.settings.get_prompts()
        for name, text in DEFAULT_PROMPTS.items():
            stored = existing.get(name)
            if stored is None:
                self.settings.set_prompt(name, text)
            elif stored in shipped:
                # Same NAME as a current preset but still holding the old
                # wording (e.g. "default"): upgrade it in place.
                self.settings.set_prompt(name, text)
                logger.info("Upgraded prompt preset to v1.6.0 wording: %s",
                            name)

    @property
    def language(self) -> str:
        return self._language

    @language.setter
    def language(self, lang: str):
        self._language = lang or DEFAULT_LANGUAGE

    def get_presets(self) -> dict[str, str]:
        """Get all prompt presets for current language."""
        all_prompts = self.settings.get_prompts()
        # Filter prompts relevant to current language
        lang_prefix = f"{self._language}_"
        filtered = {}
        # Only a known language prefix marks a language-specific prompt.
        # Any other underscore (e.g. "text_ocr") belongs to a universal
        # preset name and must stay visible (v1.5.4 fix: text_ocr was
        # unreachable because "_" in the name filtered it out).
        lang_prefixes = ("en_", "ms_")
        for name, text in all_prompts.items():
            # Include language-specific or universal prompts
            if name.startswith(lang_prefix) or not name.startswith(lang_prefixes):
                # Strip language prefix for display
                display_name = name[len(lang_prefix):] if name.startswith(lang_prefix) else name
                filtered[display_name] = text
        return filtered

    def get_preset(self, name: str) -> str:
        """Get a specific prompt preset."""
        # Try language-specific first
        lang_key = f"{self._language}_{name}"
        all_prompts = self.settings.get_prompts()
        if lang_key in all_prompts:
            return all_prompts[lang_key]
        return all_prompts.get(name, "")

    def get_preset_names(self) -> list[str]:
        """Get list of available preset names for current language."""
        return list(self.get_presets().keys())

    def set_preset(self, name: str, text: str) -> None:
        """Create or update a prompt preset."""
        lang_key = f"{self._language}_{name}"
        self.settings.set_prompt(lang_key, text)
        logger.info("Prompt preset saved: %s", lang_key)

    def delete_preset(self, name: str) -> bool:
        """Delete a prompt preset. Returns True if existed."""
        lang_key = f"{self._language}_{name}"
        # A universal preset (no language prefix) is listed under its
        # bare name, so deleting by that name must reach it too.
        return (self.settings.delete_prompt(lang_key)
                or self.settings.delete_prompt(name))

    def get_default_prompt(self) -> str:
        """Get the default prompt for current language."""
        return self.get_preset("default")

    def validate(self, text: str) -> tuple[bool, str]:
        """Validate prompt text. Returns (is_valid, error_message)."""
        if not text or not text.strip():
            return False, "Prompt cannot be empty"
        if len(text) > 5000:
            return False, "Prompt too long (max 5000 characters)"
        return True, ""

    def export_prompts(self) -> dict[str, str]:
        """Export all prompts as a dict."""
        return self.settings.get_prompts()

    def import_prompts(self, prompts: dict[str, str]) -> int:
        """Import prompts dict. Returns count of imported prompts."""
        count = 0
        for name, text in prompts.items():
            # A hand-edited import file can hold null or a number here.
            if isinstance(name, str) and isinstance(text, str) and text.strip():
                self.settings.set_prompt(name, text)
                count += 1
        return count
