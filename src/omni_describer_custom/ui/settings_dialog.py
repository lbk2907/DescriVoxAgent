"""
Omni Describer Custom — Settings Dialog.

Tabbed dialog: AI, TTS, General settings.
Supports custom AI providers (user-supplied base_url + model).
"""

from __future__ import annotations

import logging
import sys

import wx

from ..core.ai_engine import user_error_text
from ..i18n.strings import I18n, t

logger = logging.getLogger(__name__)

# Provider model presets
PROVIDER_MODELS: dict[str, list[str]] = {
    "minimax": [
        "MiniMax-M3",
    ],
    "gemini": [
        "gemini-3.5-flash-lite",  # Recommended (phase 36, 8 Oct 2026)
        "gemini-3.1-flash-lite",
        "gemini-3.8-flash",
        # Google limits 2.5 to accounts that used it before; kept
        # last so an existing saved choice stays selectable.
        "gemini-2.5-flash",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4.1",
        "gpt-4.1-mini",
        "o4-mini",
    ],
    "glm": [
        "z-ai/glm-5.3-flash",
        # v1.8.5: the best of those that hear (docs/model-comparison.md).
        "google/gemini-3.1-flash-lite",
        # v1.8.1: these also HEAR the video (probed 28 Sep 2026).
        "qwen/qwen3.8-omni-flash",
        "xiaomi/mimo-v2.6-flash",
    ],
    "custom": [],  # user provides their own
}

API_FORMATS = [
    ("auto", "settings.format_auto"),
    ("openai", "settings.format_openai"),
    ("anthropic", "settings.format_anthropic"),
]


class SettingsDialog(wx.Dialog):
    """Settings dialog with tabbed interface."""

    def __init__(self, parent, settings, tts_engine=None):
        super().__init__(
            parent,
            title=t("settings.title"),
            size=(650, 560),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.settings = settings
        self.tts_engine = tts_engine
        self._custom_visible = False
        # raw id -> shown label per labelled wx.Choice (see
        # _set_choice_labels). NVDA must read friendly names, not ids.
        self._choice_labels: dict[int, dict[str, str]] = {}
        self._build_ui()
        # Default button: Enter runs Apply; Escape keeps closing the
        # dialog without saving (default wx behaviour unchanged).
        self.apply_btn.SetDefault()
        self._load_values()
        logger.info("SettingsDialog opened")

    def _build_ui(self):
        """Build settings UI."""
        panel = wx.Panel(self)
        panel.SetName("settings_panel")
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        # Notebook (tabs)
        self.notebook = wx.Notebook(panel, name="settings_notebook")

        # Tab 1: General Settings (standard apps put General first)
        general_panel = self._build_general_tab()
        self.notebook.AddPage(general_panel, t("settings.general_tab"))

        # Tab 2: AI Settings
        ai_panel = self._build_ai_tab()
        self.notebook.AddPage(ai_panel, t("settings.ai_tab"))

        # Tab 3: TTS Settings
        tts_panel = self._build_tts_tab()
        self.notebook.AddPage(tts_panel, t("settings.tts_tab"))

        sizer.Add(self.notebook, 1, wx.ALL | wx.EXPAND, 10)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.apply_btn = wx.Button(panel, label=t("settings.apply"), name="apply_settings")
        self.cancel_btn = wx.Button(panel, label=t("settings.cancel"), name="cancel_settings")

        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self.apply_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.cancel_btn, 0, wx.ALL, 5)

        sizer.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, 10)

        # Bindings
        self.apply_btn.Bind(wx.EVT_BUTTON, self._on_apply)
        self.cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel)
        panel.Layout()

    def _build_ai_tab(self) -> wx.Panel:
        """Build AI settings tab with provider, model, and custom fields."""
        panel = wx.ScrolledWindow(self.notebook)
        panel.SetScrollRate(5, 5)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Provider
        sizer.Add(
            wx.StaticText(panel, label=t("settings.provider"), name="provider_label"), 0, wx.ALL, 5
        )
        self.provider_choice = wx.Choice(
            panel,
            choices=["gemini", "minimax", "openai", "glm", "custom"],
            name="ai_provider",
        )
        self.provider_choice.SetLabel(t("settings.provider"))
        sizer.Add(self.provider_choice, 0, wx.ALL | wx.EXPAND, 5)
        # Show friendly provider names on screen while the stored value
        # stays the machine id. Accessibility: "glm" means nothing to a
        # screen-reader user; "OpenRouter" does.
        self._provider_labels = {
            pid: t(f"settings.provider_{pid}") for pid in self.provider_choice.GetItems()
        }
        self.provider_choice.SetItems(
            [self._provider_labels.get(pid, pid) for pid in self.provider_choice.GetItems()]
        )
        self.provider_choice.Bind(wx.EVT_CHOICE, self._on_provider_changed)

        # Model (dropdown for built-in, text field for custom)
        model_sizer = wx.BoxSizer(wx.VERTICAL)
        model_sizer.Add(
            wx.StaticText(panel, label=t("settings.model"), name="model_label"), 0, wx.ALL, 5
        )

        self.model_choice = wx.Choice(panel, name="ai_model")
        self.model_choice.SetLabel(t("settings.model"))
        model_sizer.Add(self.model_choice, 0, wx.ALL | wx.EXPAND, 5)

        # Video-only filter notice (OpenRouter): the model list shows
        # only catalog-verified video-capable models.
        self.video_only_hint = wx.StaticText(
            panel, label=t("settings.video_only_hint"), name="video_only_hint"
        )
        self.video_only_hint.Wrap(560)
        model_sizer.Add(self.video_only_hint, 0, wx.ALL, 5)

        # Fetch models: pull the live catalog of video-capable models
        # from OpenRouter (public endpoint, no key/credit needed).
        self.fetch_models_btn = wx.Button(
            panel, label=t("settings.fetch_models"), name="fetch_models"
        )
        self.fetch_models_btn.Bind(wx.EVT_BUTTON, self._on_fetch_models)
        model_sizer.Add(self.fetch_models_btn, 0, wx.ALL, 5)

        # v1.8.1: send the chosen model a 6-second clip and hear whether
        # it really watches the video and hears its sound.
        self.probe_model_btn = wx.Button(panel, label=t("settings.probe_model"), name="probe_model")
        self.probe_model_btn.Bind(wx.EVT_BUTTON, self._on_probe_model)
        model_sizer.Add(self.probe_model_btn, 0, wx.ALL, 5)

        # v1.9.0: can this model drive the Player agent (F2)? Judged on
        # what it does (tools used, looked first, valid proposal, an
        # answer), measured in tools/agent_bench.py.
        self.test_agent_btn = wx.Button(panel, label=t("settings.test_agent"), name="test_agent")
        self.test_agent_btn.Bind(wx.EVT_BUTTON, self._on_test_agent)
        model_sizer.Add(self.test_agent_btn, 0, wx.ALL, 5)

        # Custom model text input (hidden by default). NVDA names the box
        # from the static text created just before it; without this one it
        # followed a button and was read as an unlabelled edit (v1.9.2).
        self.custom_model_label = wx.StaticText(
            panel, label=t("settings.custom_model"), name="custom_model_label"
        )
        self.custom_model_label.Hide()
        model_sizer.Add(self.custom_model_label, 0, wx.ALL, 5)
        self.custom_model_text = wx.TextCtrl(panel, name="custom_model_input")
        self.custom_model_text.SetHint(t("settings.model_hint"))
        self.custom_model_text.Hide()
        model_sizer.Add(self.custom_model_text, 0, wx.ALL | wx.EXPAND, 5)

        sizer.Add(model_sizer, 0, wx.EXPAND)

        # ── Custom provider fields (hidden by default) ──────────
        self.custom_sizer = wx.BoxSizer(wx.VERTICAL)

        # Base URL
        self.custom_sizer.Add(
            wx.StaticText(panel, label=t("settings.base_url"), name="base_url_label"),
            0,
            wx.ALL,
            5,
        )
        self.base_url_text = wx.TextCtrl(panel, name="custom_base_url")
        self.base_url_text.SetHint(t("settings.base_url_placeholder"))
        self.custom_sizer.Add(self.base_url_text, 0, wx.ALL | wx.EXPAND, 5)

        # API Format
        self.custom_sizer.Add(
            wx.StaticText(panel, label=t("settings.api_format"), name="api_format_label"),
            0,
            wx.ALL,
            5,
        )
        fmt_labels = [t(label_key) for _, label_key in API_FORMATS]
        self.format_choice = wx.Choice(panel, choices=fmt_labels, name="api_format")
        self.custom_sizer.Add(self.format_choice, 0, wx.ALL | wx.EXPAND, 5)

        sizer.Add(self.custom_sizer, 0, wx.EXPAND)
        self._custom_sizer_items = list(self.custom_sizer.GetChildren())
        self._hide_custom_fields()

        # API Key
        self._api_key_label = wx.StaticText(
            panel, label=t("settings.api_key"), name="api_key_label"
        )
        sizer.Add(self._api_key_label, 0, wx.ALL, 5)
        # No SetLabel on a TextCtrl (pitfall 12): NVDA names it from the
        # static text created just before it.
        self.api_key_text = wx.TextCtrl(panel, style=wx.TE_PASSWORD, name="api_key_input")
        self.api_key_text.SetHint(t("settings.api_key_placeholder"))
        self._key_hidden = True
        sizer.Add(self.api_key_text, 0, wx.ALL | wx.EXPAND, 5)

        # Show/hide key button
        self.show_key_btn = wx.ToggleButton(panel, label=t("settings.show"), name="toggle_key")
        sizer.Add(self.show_key_btn, 0, wx.ALL, 5)
        self.show_key_btn.Bind(wx.EVT_TOGGLEBUTTON, self._on_toggle_key)

        # Result of Fetch models / Test this model / Test agent mode
        self.test_result = wx.StaticText(panel, label="", name="test_result")
        sizer.Add(self.test_result, 0, wx.ALL, 5)

        # Full-video mode: the provider watches the whole video (Gemini,
        # MiniMax, OpenRouter). Unticked = still frames one at a time.
        self.video_mode_cb = wx.CheckBox(panel, label=t("settings.video_mode"), name="video_mode")
        self.video_mode_cb.SetValue(self.settings.get("ai.video_mode", "full") == "full")
        sizer.Add(self.video_mode_cb, 0, wx.ALL, 5)
        sizer.Add(
            wx.StaticText(panel, label=t("settings.video_mode_hint"), name="video_mode_hint"),
            0,
            wx.ALL,
            5,
        )
        self.video_mode_cb.Bind(wx.EVT_CHECKBOX, self._on_video_mode_toggle)

        # Fast one-shot mode: burn-in timestamps + ALL frames in ONE AI
        # request (GLM via OpenRouter). Mutually exclusive with
        # full-video mode; frame-per-frame stays the fallback.
        self.fast_mode_cb = wx.CheckBox(panel, label=t("settings.fast_mode"), name="fast_mode")
        self.fast_mode_cb.SetValue(bool(self.settings.get("ai.fast_mode", False)))
        sizer.Add(self.fast_mode_cb, 0, wx.ALL, 5)
        sizer.Add(
            wx.StaticText(panel, label=t("settings.fast_mode_hint"), name="fast_mode_hint"),
            0,
            wx.ALL,
            5,
        )
        self.fast_mode_cb.Bind(wx.EVT_CHECKBOX, self._on_fast_mode_toggle)

        # v2.1.0 (owner, 5 Oct 2026): names for the people, one each
        # (core/characters.py). On by default after measuring; this is
        # the way back if accuracy is heard to drop.
        self.characters_cb = wx.CheckBox(panel, label=t("settings.characters"), name="characters")
        self.characters_cb.SetValue(bool(self.settings.get("ai.characters", True)))
        sizer.Add(self.characters_cb, 0, wx.ALL, 5)
        sizer.Add(
            wx.StaticText(panel, label=t("settings.characters_hint"), name="characters_hint"),
            0,
            wx.ALL,
            5,
        )

        sizer.AddStretchSpacer()
        panel.SetSizer(sizer)
        return panel

    def _build_tts_tab(self) -> wx.Panel:
        """Build TTS settings tab."""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Engine
        sizer.Add(
            wx.StaticText(panel, label=t("settings.tts_engine"), name="tts_engine_label"),
            0,
            wx.ALL,
            5,
        )
        self.tts_engine_choice = wx.Choice(panel, name="tts_engine")
        self.tts_engine_choice.SetLabel(t("settings.tts_engine"))
        # Friendly engine names on screen; raw ids stay for the
        # "tts.engines.<id>" settings keys.
        self._set_choice_labels(
            self.tts_engine_choice,
            [
                ("edge", t("settings.engine_edge")),
                ("sapi5", t("settings.engine_sapi5")),
                ("openai", t("settings.engine_openai")),
                ("screen_reader", self._screen_reader_label()),
            ],
        )
        sizer.Add(self.tts_engine_choice, 0, wx.ALL | wx.EXPAND, 5)

        # Voice
        sizer.Add(wx.StaticText(panel, label=t("settings.voice"), name="voice_label"), 0, wx.ALL, 5)
        self.voice_choice = wx.Choice(panel, name="tts_voice")
        self.tts_engine_choice.Bind(wx.EVT_CHOICE, self._on_tts_engine_changed)
        sizer.Add(self.voice_choice, 0, wx.ALL | wx.EXPAND, 5)

        # Speed
        sizer.Add(wx.StaticText(panel, label=t("settings.speed"), name="speed_label"), 0, wx.ALL, 5)
        # v1.8.2: no wx.SL_LABELS. Its little "5", "20", "10" labels are
        # static texts created right before the trackbar, so NVDA named
        # the slider "10" (heard: "10 slider 33"). The value is shown
        # after it instead, where it cannot take the name.
        self.speed_slider = wx.Slider(
            panel, value=10, minValue=5, maxValue=20, style=wx.SL_HORIZONTAL, name="tts_speed"
        )
        sizer.Add(self.speed_slider, 0, wx.ALL | wx.EXPAND, 5)
        self.speed_value = wx.StaticText(panel, label="1.0x", name="speed_value")
        sizer.Add(self.speed_value, 0, wx.LEFT, 10)
        self.speed_slider.Bind(
            wx.EVT_SLIDER,
            lambda e: self.speed_value.SetLabel(f"{self.speed_slider.GetValue() / 10:.1f}x"),
        )

        sizer.AddStretchSpacer()
        panel.SetSizer(sizer)
        return panel

    def _build_general_tab(self) -> wx.Panel:
        """Build general settings tab."""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Language
        sizer.Add(
            wx.StaticText(panel, label=t("settings.language"), name="general_lang_label"),
            0,
            wx.ALL,
            5,
        )
        self.lang_choice = wx.Choice(panel, name="language")
        self.lang_choice.SetLabel(t("settings.language"))
        sizer.Add(self.lang_choice, 0, wx.ALL | wx.EXPAND, 5)
        # Friendly labels on screen, raw ids stored (NVDA reads
        # "English", not "en").
        # v1.6.2: built from the locale files present, so a new
        # language appears here by dropping locales/<code>.json — no
        # code change. Each file names itself in its own language.
        self._set_choice_labels(
            self.lang_choice,
            [(code, I18n.language_name(code)) for code in I18n.available_languages()],
        )
        # v1.5.2: description output language (AI answers)
        sizer.Add(
            wx.StaticText(panel, label=t("settings.desc_language"), name="desc_lang_label"),
            0,
            wx.ALL,
            5,
        )
        self.desc_lang_choice = wx.Choice(panel, name="desc_language")
        self.desc_lang_choice.SetLabel(t("settings.desc_language"))
        # Friendly labels; "system" follows the UI language. Raw ids
        # ("system"/"ms"/"en") stay for settings storage.
        # "system" follows the UI language; every installed locale is
        # also offered, because the language you read the app in is not
        # always the language you want the descriptions in (sharing an
        # SRT with someone else, for instance).
        self._set_choice_labels(
            self.desc_lang_choice,
            [
                ("system", t("settings.lang_system")),
            ]
            + [(code, I18n.language_name(code)) for code in I18n.available_languages()],
        )
        # v1.9.6: on screen in CREATION order (= Tab order, pitfall 34),
        # each box under its own label. The boxes were added in the
        # opposite order, so "Language" sat below "Description language".
        sizer.Add(self.desc_lang_choice, 0, wx.ALL | wx.EXPAND, 5)

        # Frame rate
        sizer.Add(
            wx.StaticText(panel, label=t("settings.frame_rate"), name="frame_rate_label"),
            0,
            wx.ALL,
            5,
        )
        self.fps_choice = wx.Choice(panel, choices=["1", "2", "5", "10"], name="frame_rate")
        self.fps_choice.SetLabel(t("settings.frame_rate"))
        sizer.Add(self.fps_choice, 0, wx.ALL | wx.EXPAND, 5)

        # Frame cap (0 = no limit; default keeps current behaviour)
        sizer.Add(
            wx.StaticText(panel, label=t("settings.frame_cap"), name="frame_cap_label"),
            0,
            wx.ALL,
            5,
        )
        self.frame_cap_spin = wx.SpinCtrl(panel, min=0, max=100000, initial=0, name="frame_cap")
        sizer.Add(self.frame_cap_spin, 0, wx.ALL | wx.EXPAND, 5)

        # v1.7.0: the floor to the cap above. Deduplication keeps one
        # frame for any stretch that does not change, so a 100-second
        # held shot left the AI with nothing to look at and nothing to
        # describe. 0 turns it off.
        sizer.Add(
            wx.StaticText(panel, label=t("settings.max_frame_gap"), name="max_frame_gap_label"),
            0,
            wx.ALL,
            5,
        )
        self.max_gap_spin = wx.SpinCtrl(panel, min=0, max=600, initial=30, name="max_frame_gap")
        self.max_gap_spin.SetToolTip(t("settings.max_frame_gap_hint"))
        sizer.Add(self.max_gap_spin, 0, wx.ALL | wx.EXPAND, 5)

        # v1.4.1: chunk length for full-video mode (seconds per part).
        sizer.Add(
            wx.StaticText(panel, label=t("settings.chunk_seconds"), name="chunk_seconds_label"),
            0,
            wx.ALL,
            5,
        )
        self.chunk_spin = wx.SpinCtrl(panel, min=60, max=3600, initial=300, name="chunk_seconds")
        sizer.Add(self.chunk_spin, 0, wx.ALL | wx.EXPAND, 5)

        # v1.8.8: check descriptions against the picture. The label is
        # created right before the Choice so NVDA names it (pitfall 53).
        sizer.Add(
            wx.StaticText(panel, label=t("settings.review_mode"), name="review_mode_label"),
            0,
            wx.ALL,
            5,
        )
        self.review_choice = wx.Choice(
            panel,
            choices=[
                t(f"settings.review_{m}") for m in ["off", "auto", "accurate", "most", "keep"]
            ],
            name="review_mode",
        )
        sizer.Add(self.review_choice, 0, wx.ALL | wx.EXPAND, 5)
        sizer.Add(
            wx.StaticText(panel, label=t("settings.review_hint"), name="review_mode_hint"),
            0,
            wx.ALL,
            5,
        )

        self.preserve_res_check = wx.CheckBox(
            panel, label=t("settings.preserve_resolution"), name="preserve_resolution"
        )
        sizer.Add(self.preserve_res_check, 0, wx.ALL, 5)
        sizer.Add(
            wx.StaticText(
                panel, label=t("settings.preserve_resolution_hint"), name="preserve_resolution_hint"
            ),
            0,
            wx.ALL,
            5,
        )

        # 2.1.3: offer a newer DescriVox Agent at every start (owner's
        # choice); Help > Check for Updates works either way.
        self.app_update_check_cb = wx.CheckBox(
            panel, label=t("settings.check_app_updates"), name="check_app_updates"
        )
        sizer.Add(self.app_update_check_cb, 0, wx.ALL, 5)

        # v1.6.1: speech-to-text. The default AI provider cannot hear the
        # video, so this is what lets it know what was said when there
        # are no published or embedded subtitles.
        sizer.Add(
            wx.StaticText(panel, label=t("settings.transcription"), name="transcription_label"),
            0,
            wx.ALL,
            5,
        )
        self.transcribe_choice = wx.Choice(
            panel,
            choices=[
                t("settings.transcribe_auto"),
                t("settings.transcribe_whisper"),
                t("settings.transcribe_grok"),
                t("settings.transcribe_off"),
            ],
            name="transcription_backend",
        )
        self.transcribe_choice.SetLabel(t("settings.transcription"))
        sizer.Add(self.transcribe_choice, 0, wx.ALL | wx.EXPAND, 5)
        sizer.Add(
            wx.StaticText(panel, label=t("settings.transcription_hint"), name="transcription_hint"),
            0,
            wx.ALL,
            5,
        )

        sizer.Add(
            wx.StaticText(panel, label=t("settings.xai_key"), name="xai_key_label"), 0, wx.ALL, 5
        )
        self.xai_key_text = wx.TextCtrl(panel, style=wx.TE_PASSWORD, name="xai_api_key")
        self.xai_key_text.SetName(t("settings.xai_key"))
        sizer.Add(self.xai_key_text, 0, wx.ALL | wx.EXPAND, 5)

        # Output directory
        sizer.Add(
            wx.StaticText(panel, label=t("settings.output_dir"), name="output_dir_label"),
            0,
            wx.ALL,
            5,
        )
        out_row = wx.BoxSizer(wx.HORIZONTAL)
        self.output_text = wx.TextCtrl(panel, name="output_dir")
        # Accessible label (was "..."): screen readers announce a real name,
        # so a blind user knows this opens the folder picker.
        browse_out = wx.Button(panel, label=t("settings.browse"), name="browse_output")
        out_row.Add(self.output_text, 1, wx.ALL | wx.EXPAND, 5)
        out_row.Add(browse_out, 0, wx.ALL, 5)
        browse_out.Bind(wx.EVT_BUTTON, self._on_browse_output)
        sizer.Add(out_row, 0, wx.EXPAND)

        sizer.AddStretchSpacer()
        panel.SetSizer(sizer)
        return panel

    # ── Choice label helpers ──────────────────────────────────
    #
    # wx.Choice items must be readable by NVDA, so friendly labels are
    # shown while raw ids ("en", "edge", ...) are kept for settings
    # storage. _choice_label maps raw -> label for loads; _choice_value
    # maps the shown selection back to the raw id for saves.

    def _set_choice_labels(self, choice, pairs):
        """Fill a wx.Choice with friendly labels and remember raw ids."""
        self._choice_labels[id(choice)] = dict(pairs)
        choice.SetItems([label for _, label in pairs])

    def _choice_label(self, choice, raw):
        """Shown label for a raw id (falls back to the raw id)."""
        return self._choice_labels.get(id(choice), {}).get(raw, raw)

    def _choice_value(self, choice):
        """Raw id for the current selection (label -> raw id)."""
        labels = self._choice_labels.get(id(choice), {})
        shown = choice.GetStringSelection()
        for raw, label in labels.items():
            if label == shown:
                return raw
        return shown

    # ── Custom Provider UI Helpers ────────────────────────────

    def _hide_custom_fields(self):
        """Hide custom provider fields."""
        for child_info in self._custom_sizer_items:
            win = child_info.GetWindow()
            if win:
                win.Hide()
        self._custom_visible = False
        self.custom_model_label.Hide()
        self.custom_model_text.Hide()

    def _show_custom_fields(self):
        """Show custom provider fields."""
        for child_info in self._custom_sizer_items:
            win = child_info.GetWindow()
            if win:
                win.Show()
        self.custom_model_label.Show()
        self.custom_model_text.Show()
        self._custom_visible = True
        self.Layout()

    # ── Event Handlers ─────────────────────────────────────────

    def _on_toggle_key(self, event):
        """Toggle API key visibility.

        v1.7.9: on Windows the SAME control is switched with
        EM_SETPASSWORDCHAR. Recreating it (the old way, kept below for
        other platforms) put the new box at the panel's top-left corner
        with a default size, LAST in the Tab order, and without the
        label NVDA takes from the static text created just before it —
        to the owner, the key field simply vanished after Show/Hide.
        """
        is_hidden = getattr(self, "_key_hidden", True)
        if sys.platform == "win32":
            import ctypes

            EM_SETPASSWORDCHAR = 0x00CC
            # 0 removes ES_PASSWORD; U+25CF is the bullet Windows uses.
            ctypes.windll.user32.SendMessageW(
                self.api_key_text.GetHandle(), EM_SETPASSWORDCHAR, 0 if is_hidden else 0x25CF, 0
            )
            self.api_key_text.Refresh()
            self._key_hidden = not is_hidden
            self.show_key_btn.SetLabel(t("settings.hide") if is_hidden else t("settings.show"))
            return
        is_hidden = (self.api_key_text.GetWindowStyleFlag() & wx.TE_PASSWORD) != 0
        value = self.api_key_text.GetValue()
        # Preserve sizer placement
        parent = self.api_key_text.GetParent()
        sizer = self.api_key_text.GetContainingSizer()
        if sizer is None:
            return
        index = 0
        for i, child in enumerate(sizer.GetChildren()):
            if child.GetWindow() is self.api_key_text:
                index = i
                break
        flags = sizer.GetItem(self.api_key_text).GetFlag()
        border = sizer.GetItem(self.api_key_text).GetBorder()
        proportion = sizer.GetItem(self.api_key_text).GetProportion()

        new_style = 0 if is_hidden else wx.TE_PASSWORD
        new_ctrl = wx.TextCtrl(parent, value=value, style=new_style, name="api_key_input")
        # SetHint clears the value on some platforms, so re-apply afterwards
        new_ctrl.SetHint(t("settings.api_key_placeholder"))
        new_ctrl.ChangeValue(value)
        sizer.Insert(index, new_ctrl, proportion, flags, border)
        sizer.Detach(self.api_key_text)
        self.api_key_text.Destroy()
        self.api_key_text = new_ctrl
        # Back to its place in the Tab order (pitfall 34) and in the
        # layout: the PANEL's sizer, not only the dialog's.
        new_ctrl.MoveAfterInTabOrder(self._api_key_label)
        self._key_hidden = not is_hidden
        self.show_key_btn.SetLabel(t("settings.hide") if is_hidden else t("settings.show"))
        parent.Layout()
        self.Layout()

    def _on_provider_changed(self, event):
        """Update model list and show/hide custom fields when provider changes."""
        provider = self._selected_provider()

        if provider == "custom":
            self._show_custom_fields()
            self.model_choice.Hide()
            # Buttons Custom cannot use (Fetch models, Test agent mode): heard
            # by NVDA as live buttons that
            # did nothing for Custom (v1.9.2).
            self.fetch_models_btn.Disable()
            self.probe_model_btn.Enable()
            self.test_agent_btn.Disable()
            self.video_only_hint.Hide()
            self.custom_model_text.Show()
            self.custom_model_text.SetFocus()
            # Load custom config
            config = self.settings.get_ai_provider("custom")
            if config.get("model"):
                self.custom_model_text.SetValue(config["model"])
            if config.get("base_url"):
                self.base_url_text.SetValue(config["base_url"])
            fmt_val = config.get("api_format", "auto")
            fmt_idx = next((i for i, (v, _) in enumerate(API_FORMATS) if v == fmt_val), 0)
            self.format_choice.SetSelection(fmt_idx)
            if config.get("api_key"):
                self.api_key_text.SetValue(config["api_key"])
        else:
            self._hide_custom_fields()
            self.custom_model_text.Hide()
            self.model_choice.Show()
            self.fetch_models_btn.Show()
            self.probe_model_btn.Show()
            self.test_agent_btn.Show()
            self.video_only_hint.Show()
            # Populate model list from presets (glm later swaps in the
            # video-capable catalog list when the user fetches).
            rows = []
            if provider == "glm":
                # v1.8.1: the list fetched last time, kept between visits.
                from ..core.model_catalog import load_cache

                rows = load_cache()[0]
            elif provider == "gemini":
                from ..core.model_catalog import GEMINI_CACHE_NAME, load_cache

                rows = load_cache(GEMINI_CACHE_NAME)[0]
            prov_config = self.settings.get_ai_provider(provider)
            self._fill_models(
                rows or [{"id": m} for m in PROVIDER_MODELS.get(provider, [])],
                prov_config.get("model", ""),
            )
            # Video-only list + Fetch models: OpenRouter and Gemini (v1.9.3);
            # Test agent mode: the agent's providers (OpenRouter, Gemini).
            self.fetch_models_btn.Enable(provider in ("glm", "gemini"))
            self.probe_model_btn.Enable()
            self.test_agent_btn.Enable(provider in ("glm", "gemini"))
            self.video_only_hint.Show(provider in ("glm", "gemini"))
            if prov_config.get("api_key"):
                self.api_key_text.SetValue(prov_config["api_key"])
            else:
                self.api_key_text.SetValue("")

        # Full-video mode checkbox is enabled for providers that accept
        # a whole video: native upload (Gemini, MiniMax) or base64
        # video_url (GLM via OpenRouter, empirically verified).
        self.video_mode_cb.Enable(provider in ("gemini", "minimax", "glm"))
        if provider not in ("gemini", "minimax", "glm"):
            self.video_mode_cb.SetValue(False)
        # Fast one-shot mode is only offered for GLM (OpenRouter,
        # OpenAI-compatible vision with a huge context window).
        self.fast_mode_cb.Enable(provider == "glm")
        if provider != "glm":
            self.fast_mode_cb.SetValue(False)

        self.Layout()

    def _on_video_mode_toggle(self, event):
        """Send-video and send-frames-fast are mutually exclusive."""
        if self.video_mode_cb.GetValue() and self.fast_mode_cb.GetValue():
            self.fast_mode_cb.SetValue(False)
        if event is not None:
            event.Skip()

    def _on_fast_mode_toggle(self, event):
        if self.fast_mode_cb.GetValue() and self.video_mode_cb.GetValue():
            self.video_mode_cb.SetValue(False)
        if event is not None:
            event.Skip()

    def _selected_provider(self) -> str:
        """Map the displayed provider label back to its machine id."""
        shown = self.provider_choice.GetStringSelection()
        for pid, label in getattr(self, "_provider_labels", {}).items():
            if label == shown:
                return pid
        return shown

    def select_provider(self, provider_id: str) -> None:
        """Select a provider by machine id and refresh dependent fields.

        Public helper for tests and accessibility automation: the combo
        shows friendly labels, but callers reason in plain ids
        ("glm", "gemini", ...).
        """
        self.provider_choice.SetStringSelection(self._provider_labels.get(provider_id, provider_id))
        self._on_provider_changed(None)

    def _on_fetch_models(self, event):
        """Fetch video-capable model ids from the provider catalog."""
        provider = self._selected_provider()
        if provider not in ("glm", "gemini"):
            return
        if provider == "gemini":
            self._fetch_gemini_models()
            return
        self.fetch_models_btn.Disable()
        self._show_test_result(t("settings.fetching_models"))

        def fetch():
            try:
                from ..core.model_catalog import fetch_catalog, save_cache

                models = fetch_catalog()
                if models:
                    save_cache(models)
                    wx.CallAfter(self._apply_fetched_models, models)
                    wx.CallAfter(
                        self._show_test_result,
                        t(
                            "settings.fetch_models_ok",
                            count=len(models),
                            audio=sum(1 for m in models if m["audio"]),
                        ),
                    )
                else:
                    wx.CallAfter(self._show_test_result, t("settings.fetch_models_none"))
            except Exception as e:
                logger.warning("Fetch models failed: %s", e)
                wx.CallAfter(
                    self._show_test_result,
                    t("settings.fetch_models_error", error=user_error_text(str(e))),
                )
            finally:
                wx.CallAfter(self._fetch_done)

        import threading

        threading.Thread(target=fetch, daemon=True).start()

    def _fetch_gemini_models(self):
        """v1.9.3: the models this Gemini key can use, from Google."""
        api_key = self.api_key_text.GetValue().strip()
        if not api_key:
            self._show_test_result(t("settings.probe_needs_key"))
            return
        self.fetch_models_btn.Disable()
        self._show_test_result(t("settings.fetching_models"))

        def fetch():
            try:
                from ..core.model_catalog import GEMINI_CACHE_NAME, fetch_gemini_models, save_cache

                models = fetch_gemini_models(api_key)
                if models:
                    save_cache(models, GEMINI_CACHE_NAME)
                    wx.CallAfter(self._apply_fetched_models, models)
                    wx.CallAfter(
                        self._show_test_result, t("settings.fetch_gemini_ok", count=len(models))
                    )
                else:
                    wx.CallAfter(self._show_test_result, t("settings.fetch_models_none"))
            except Exception as e:
                logger.warning("Fetch Gemini models failed: %s", e)
                wx.CallAfter(
                    self._show_test_result,
                    t("settings.fetch_models_error", error=user_error_text(str(e))),
                )
            finally:
                wx.CallAfter(self._fetch_done)

        import threading

        threading.Thread(target=fetch, daemon=True).start()

    def _apply_fetched_models(self, models):
        """Replace the dropdown with fetched video models (rows from
        core.model_catalog), keeping the current selection reachable."""
        if not self:
            return  # v1.9.6: Settings closed while the list was fetched
        current = self._choice_value(self.model_choice)
        self._fill_models(models, current)

    def _fetch_done(self) -> None:
        if self:
            self.fetch_models_btn.Enable()

    def _model_label(self, row: dict) -> str:
        """What NVDA reads for a model: name, whether it hears the
        soundtrack, and its input price — not a bare id."""
        from ..core.model_catalog import RECOMMENDED

        if "name" not in row:
            label = row["id"]
        elif row.get("gemini"):
            # Every model Google lists here takes video; whether one
            # HEARS is for Test this model to say, not the list.
            label = (
                t("settings.gemini_model_label", name=row["name"], price=f"{row['price_in']:.2f}")
                if row.get("price_in")
                else row["name"]
            )
        else:
            if row.get("tested"):
                hears = row.get("hears")
            else:
                hears = row.get("audio")
            label = t(
                "settings.model_label",
                name=row["name"],
                audio=t("settings.model_hears") if hears else t("settings.model_video_only"),
                price=f"{row.get('price_in', 0):.2f}",
            )
        # v1.8.5: said FIRST, so it is heard before the details.
        if row["id"] in RECOMMENDED or f"google/{row['id']}" in RECOMMENDED:
            label = t("settings.model_recommended", label=label)
        return label

    def _fill_models(self, rows, selected: str) -> None:
        from ..core.model_catalog import recommended_rank

        # A list cached by an older version is in the old order.
        rows = sorted(rows, key=lambda r: recommended_rank(r["id"]))
        ids = [r["id"] for r in rows]
        if selected and selected not in ids:
            # Keep a saved model reachable even if the list lacks it.
            rows = list(rows) + [{"id": selected}]
            ids.append(selected)
        self._model_catalog = ids
        self._set_choice_labels(self.model_choice, [(r["id"], self._model_label(r)) for r in rows])
        if selected:
            self.model_choice.SetSelection(ids.index(selected))
        elif ids:
            self.model_choice.SetSelection(0)

    def _on_probe_model(self, event):
        """Send the chosen model a 6-second clip: does it see and hear?

        v1.9.2: every provider, through the app's own engine and the form
        values (the old Test Connection only asked for "OK")."""
        provider = self._selected_provider()
        custom = provider == "custom"
        model = (
            self.custom_model_text.GetValue().strip()
            if custom
            else self._choice_value(self.model_choice)
        )
        api_key = self.api_key_text.GetValue().strip()
        if not model:
            self._show_test_result(t("settings.probe_needs_model"))
            return
        if custom and not self.base_url_text.GetValue().strip():
            self._show_test_result(t("settings.probe_needs_url"))
            return
        if not api_key:
            self._show_test_result(t("settings.probe_needs_key"))
            return
        self.probe_model_btn.Disable()
        self._show_test_result(t("settings.probing_model", model=model))

        if provider == "glm":

            def work():
                from ..core.model_catalog import probe_model, record_probe

                result = probe_model(api_key, model)
                record_probe(model, result)
                wx.CallAfter(self._probe_done, model, result)
        else:
            from ..core.ai_engine import AIEngine

            engine = AIEngine()
            if custom:
                engine.set_provider(
                    "custom",
                    api_key=api_key,
                    base_url=self.base_url_text.GetValue().strip(),
                    model=model,
                    api_format=API_FORMATS[self.format_choice.GetSelection()][0],
                )
            else:
                engine.set_provider(provider, api_key=api_key, model=model)

            def work():
                from ..core.model_catalog import probe_engine

                result = probe_engine(engine, provider, model)
                wx.CallAfter(self._probe_done, model, result)

        import threading

        threading.Thread(target=work, daemon=True).start()

    def _on_test_agent(self, event):
        """Settings > Test agent mode: a 12-second test clip, one question."""
        provider = self._selected_provider()
        model = self._choice_value(self.model_choice)
        api_key = self.api_key_text.GetValue().strip()
        from ..core.agent import AGENT_PROVIDERS

        if provider not in AGENT_PROVIDERS or not model:
            self._show_test_result(t("settings.agent_openrouter_only"))
            return
        if not api_key:
            self._show_test_result(t("settings.probe_needs_key"))
            return
        self.test_agent_btn.Disable()
        self._show_test_result(t("settings.testing_agent", model=model))

        def work():
            import asyncio
            from ..core.agent import probe

            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(probe(api_key, model, provider=provider))
            except Exception as e:
                logger.warning("Agent test failed: %s", e)
                result = {"ok": False, "error": str(e)}
            finally:
                loop.close()
            wx.CallAfter(self._test_agent_done, model, result)

        import threading

        threading.Thread(target=work, daemon=True).start()

    def _test_agent_done(self, model, result) -> None:
        if not self:
            return
        self.test_agent_btn.Enable()
        passed = list(self.settings.get("ai.agent_models", []) or [])
        if result.get("ok"):
            if model not in passed:
                passed.append(model)
            text = t("settings.agent_pass", model=model)
        else:
            passed = [m for m in passed if m != model]
            text = (
                t("settings.agent_error", model=model, error=user_error_text(result["error"]))
                if result.get("error")
                else t("settings.agent_fail", model=model)
            )
        self.settings.set("ai.agent_models", passed)
        self._show_test_result(text)

    def _probe_done(self, model, result) -> None:
        if not self:
            return
        self.probe_model_btn.Enable()
        if result["error"]:
            logger.warning("Probe of %s failed: %s", model, result["error"])
            text = t("settings.probe_error", model=model, error=user_error_text(result["error"]))
        elif result.get("picture"):
            text = (
                t("settings.probe_sees_picture", model=model)
                if result["sees"]
                else t("settings.probe_blind", model=model, answer=result["answer"][:80])
            )
        elif not result["sees"]:
            text = t("settings.probe_blind", model=model, answer=result["answer"][:80])
        elif result["hears"]:
            text = t("settings.probe_sees_hears", model=model)
        elif result["hears"] is None:
            text = t("settings.probe_sees_untested", model=model)
        else:
            text = t("settings.probe_sees_only", model=model)
        self._show_test_result(text)
        if self._selected_provider() != "glm":
            return
        # The label now reflects what was measured, not the catalog.
        from ..core.model_catalog import load_cache

        rows = load_cache()[0]
        if rows:
            self._fill_models(rows, model)

    def _screen_reader_label(self) -> str:
        """Name the reader we actually found, not a generic label.

        "Screen reader (NVDA)" tells the user it was detected;
        "Screen reader" alone leaves them guessing whether it works.
        """
        try:
            from ..core.speech import get_speech

            speech = get_speech()
            if speech.available:
                return t("settings.engine_screen_reader_named").format(backend=speech.backend_name)
        except Exception as e:
            logger.debug("Could not name the screen reader: %s", e)
        return t("settings.engine_screen_reader")

    def _on_tts_engine_changed(self, event):
        """Update voice list when TTS engine changes."""
        engine = self._choice_value(self.tts_engine_choice)
        self._refresh_voice_list(engine)
        self._sync_voice_controls(engine)

    def _sync_voice_controls(self, engine: str) -> None:
        """Voice and speed belong to the screen reader, not to us.

        NVDA reports supports_set_rate and supports_set_voice as False,
        so leaving these enabled would offer settings that silently do
        nothing. Disabled with a reason instead.
        """
        owns_its_voice = engine == "screen_reader"
        for widget in (self.voice_choice, self.speed_slider):
            widget.Enable(not owns_its_voice)
            if owns_its_voice:
                widget.SetToolTip(t("settings.engine_owns_voice"))
            else:
                widget.SetToolTip(None)

    def _refresh_voice_list(self, engine: str):
        """Populate voice dropdown with real voices for the given engine."""
        current = self.voice_choice.GetStringSelection()
        self.voice_choice.SetItems(["Default"])
        self.voice_choice.SetSelection(0)
        if not self.tts_engine:
            return
        try:
            engine = engine or self.tts_engine.get_available_engines()[0]
            voices = self.tts_engine.get_voices(engine)
            names = [v["name"] for v in voices]
            if names:
                # v1.7.4: keep "Default" as the first entry. Replacing the
                # list outright meant that once a voice was picked there
                # was no way back to the engine's default voice.
                self.voice_choice.SetItems(["Default"] + names)
                if current in names:
                    self.voice_choice.SetStringSelection(current)
                else:
                    self.voice_choice.SetSelection(0)
        except Exception as e:
            logger.warning("Voice list fetch failed for %s: %s", engine, e)

    def _on_browse_output(self, event):
        """Browse output directory."""
        dlg = wx.DirDialog(self, t("settings.select_dir"))
        if dlg.ShowModal() == wx.ID_OK:
            self.output_text.SetValue(dlg.GetPath())
        dlg.Destroy()

    def _show_test_result(self, text):
        """Show the connection test result and move keyboard focus to it
        so screen readers announce it immediately."""
        if not self:
            return  # v1.9.6: a worker's result after Settings closed
        self.test_result.SetLabel(text)
        self.test_result.SetFocus()

    def _on_apply(self, event):
        """Apply settings."""
        provider = self._selected_provider()

        if provider == "custom":
            model = self.custom_model_text.GetValue().strip()
            base_url = self.base_url_text.GetValue().strip()
            api_format = API_FORMATS[self.format_choice.GetSelection()][0]
            api_key = self.api_key_text.GetValue().strip()
            if not model:
                wx.MessageBox(
                    t("settings.enter_model_name"), t("settings.title"), wx.OK | wx.ICON_WARNING
                )
                return
            config = self.settings.get_ai_provider("custom")
            config["api_key"] = api_key
            config["model"] = model
            config["base_url"] = base_url
            config["api_format"] = api_format
            self.settings.set_ai_provider("custom", config)
            self.settings.set("ai.default_provider", "custom")
        else:
            model = self._choice_value(self.model_choice)
            api_key = self.api_key_text.GetValue().strip()
            config = self.settings.get_ai_provider(provider)
            config["api_key"] = api_key
            config["model"] = model
            self.settings.set_ai_provider(provider, config)
            self.settings.set("ai.default_provider", provider)

        # Full-video mode (persisted for the processing pipeline; the
        # pipeline itself double-checks provider supports full-video).
        self.settings.set("ai.video_mode", "full" if self.video_mode_cb.GetValue() else "frames")
        self.settings.set("ai.fast_mode", bool(self.fast_mode_cb.GetValue()))
        self.settings.set("ai.characters", bool(self.characters_cb.GetValue()))

        # Update TTS
        tts_engine = self._choice_value(self.tts_engine_choice)
        self.settings.set("tts.default_engine", tts_engine)

        # Voice + speed (map display name back to voice id)
        voice_name = self.voice_choice.GetStringSelection()
        voice_id = ""
        if voice_name and voice_name != "Default" and self.tts_engine:
            try:
                for v in self.tts_engine.get_voices(tts_engine):
                    if v["name"] == voice_name:
                        voice_id = v["id"]
                        break
            except Exception:
                voice_id = ""
        self.settings.set(f"tts.engines.{tts_engine}.voice", voice_id)
        speed = self.speed_slider.GetValue() / 10.0
        self.settings.set(f"tts.engines.{tts_engine}.speed", speed)

        # Update general
        lang = self._choice_value(self.lang_choice)
        self.settings.set("general.language", lang)
        # v1.5.2: description language (empty = follow UI)
        desc_lang = self._choice_value(self.desc_lang_choice)
        if desc_lang == "system":
            desc_lang = ""
        self.settings.set("general.description_language", desc_lang)
        I18n.set_language(lang)

        fps = self.fps_choice.GetStringSelection()
        self.settings.set("general.frame_rate", int(fps))

        self.settings.set("general.frame_cap", int(self.frame_cap_spin.GetValue()))
        self.settings.set("general.max_frame_gap", int(self.max_gap_spin.GetValue()))

        self.settings.set("general.chunk_seconds", int(self.chunk_spin.GetValue()))

        self.settings.set("general.preserve_resolution", bool(self.preserve_res_check.GetValue()))
        self.settings.set("updates.check_app_at_start", bool(self.app_update_check_cb.GetValue()))

        review_modes = ["off", "auto", "accurate", "most", "keep"]
        idx = self.review_choice.GetSelection()
        if idx != wx.NOT_FOUND:
            self.settings.set("general.review_mode", review_modes[idx])

        backends = ["auto", "whisper", "grok", "off"]
        idx = self.transcribe_choice.GetSelection()
        if idx != wx.NOT_FOUND:
            self.settings.set("general.transcription_backend", backends[idx])
        xai_key = self.xai_key_text.GetValue().strip()
        if xai_key and not xai_key.startswith("*"):
            # Stored through set_ai_provider so it lands encrypted, the
            # same path every other API key takes.
            self.settings.set_ai_provider("xai", {"api_key": xai_key})

        output_dir = self.output_text.GetValue().strip()
        if output_dir:
            self.settings.set("general.output_dir", output_dir)

        self._load_values()
        wx.MessageBox(t("settings.saved"), t("settings.title"), wx.OK | wx.ICON_INFORMATION)
        if self.IsModal():
            self.EndModal(wx.ID_OK)
        else:
            self.Close()

    def _on_cancel(self, event):
        """Close dialog without saving."""
        if self.IsModal():
            self.EndModal(wx.ID_CANCEL)
        else:
            self.Close()

    # ── Load Values ────────────────────────────────────────────

    def _load_values(self):
        """Load current settings into UI."""
        # v1.8.2: "or": a new user's file holds "" — the key exists, so
        # the default never applied and Provider was read as empty.
        # Phase E (29 Sep 2026): OpenRouter/GLM, not Gemini, for a new
        # user -- cheapest, did not fail under load, and the only model
        # that conveyed foreign dialogue (via the transcript).
        default_provider = self.settings.get("ai.default_provider", "") or "glm"
        # The dropdown shows friendly labels; map the stored machine id.
        self.provider_choice.SetStringSelection(
            self._provider_labels.get(default_provider, default_provider)
        )
        self._on_provider_changed(None)  # Refresh model list + fields
        self.fast_mode_cb.SetValue(bool(self.settings.get("ai.fast_mode", False)))
        self.characters_cb.SetValue(bool(self.settings.get("ai.characters", True)))

        # TTS
        default_tts = self.settings.get("tts.default_engine", "edge")
        self.tts_engine_choice.SetStringSelection(
            self._choice_label(self.tts_engine_choice, default_tts)
        )
        self._refresh_voice_list(default_tts)
        # Select saved voice by id (match display name)
        saved_voice = self.settings.get(f"tts.engines.{default_tts}.voice", "")
        if saved_voice and self.tts_engine:
            try:
                for v in self.tts_engine.get_voices(default_tts):
                    if v["id"] == saved_voice:
                        self.voice_choice.SetStringSelection(v["name"])
                        break
            except Exception:
                pass
        saved_speed = self.settings.get(f"tts.engines.{default_tts}.speed", 1.0)
        self.speed_slider.SetValue(int(float(saved_speed) * 10))
        self.speed_value.SetLabel(f"{self.speed_slider.GetValue() / 10:.1f}x")
        # Applied on load too, not only on change: opening the dialog
        # with the screen reader already saved must show the voice and
        # speed controls as the dead ends they are.
        self._sync_voice_controls(default_tts)

        # General
        lang = self.settings.get("general.language", "en")
        self.lang_choice.SetStringSelection(self._choice_label(self.lang_choice, lang))
        # v1.5.2: description language selection
        _dl = str(self.settings.get("general.description_language", "") or "")
        self.desc_lang_choice.SetStringSelection(
            self._choice_label(self.desc_lang_choice, _dl if _dl in ("ms", "en") else "system")
        )

        fps = str(self.settings.get("general.frame_rate", 5))
        fps_items = [self.fps_choice.GetString(i) for i in range(self.fps_choice.GetCount())]
        if fps in fps_items:
            self.fps_choice.SetStringSelection(fps)

        self.frame_cap_spin.SetValue(int(self.settings.get("general.frame_cap", 0) or 0))
        self.max_gap_spin.SetValue(int(self.settings.get("general.max_frame_gap", 30) or 0))

        chunk_val = int(self.settings.get("general.chunk_seconds", 300) or 300)
        self.chunk_spin.SetValue(max(60, chunk_val))

        review_modes = ["off", "auto", "accurate", "most", "keep"]
        saved = str(self.settings.get("general.review_mode", "off") or "off")
        self.review_choice.SetSelection(review_modes.index(saved) if saved in review_modes else 0)

        self.preserve_res_check.SetValue(
            bool(self.settings.get("general.preserve_resolution", False))
        )
        self.app_update_check_cb.SetValue(
            bool(self.settings.get("updates.check_app_at_start", True))
        )

        backends = ["auto", "whisper", "grok", "off"]
        current = str(self.settings.get("general.transcription_backend", "auto") or "auto")
        self.transcribe_choice.SetSelection(backends.index(current) if current in backends else 0)
        if (self.settings.get_ai_provider("xai") or {}).get("api_key"):
            self.xai_key_text.SetValue("*" * 12)

        output_dir = self.settings.get("general.output_dir", "")
        if output_dir:
            self.output_text.SetValue(output_dir)

        I18n.set_language(lang)
