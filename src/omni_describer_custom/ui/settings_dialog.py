"""
Omni Describer Custom — Settings Dialog.

Tabbed dialog: AI, TTS, General settings.
Supports custom AI providers (user-supplied base_url + model).
"""

from __future__ import annotations

import logging
import wx
from typing import Any

from ..i18n.strings import I18n, t

logger = logging.getLogger(__name__)

# Provider model presets
PROVIDER_MODELS: dict[str, list[str]] = {
    "opus": [
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
    ],
    "gemini": [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4.1",
        "gpt-4.1-mini",
        "o4-mini",
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
        super().__init__(parent, title=t("settings.title"), size=(650, 560),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.settings = settings
        self.tts_engine = tts_engine
        self._custom_visible = False
        self._build_ui()
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

        # Tab 1: AI Settings
        ai_panel = self._build_ai_tab()
        self.notebook.AddPage(ai_panel, t("settings.ai_tab"))

        # Tab 2: TTS Settings
        tts_panel = self._build_tts_tab()
        self.notebook.AddPage(tts_panel, t("settings.tts_tab"))

        # Tab 3: General Settings
        general_panel = self._build_general_tab()
        self.notebook.AddPage(general_panel, t("settings.general_tab"))

        sizer.Add(self.notebook, 1, wx.ALL | wx.EXPAND, 10)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.test_btn = wx.Button(panel, label=t("settings.test_connection"),
                                  name="test_connection")
        self.apply_btn = wx.Button(panel, label=t("settings.apply"),
                                   name="apply_settings")
        self.cancel_btn = wx.Button(panel, label=t("settings.cancel"),
                                    name="cancel_settings")

        btn_sizer.Add(self.test_btn, 0, wx.ALL, 5)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self.apply_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.cancel_btn, 0, wx.ALL, 5)

        sizer.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, 10)

        # Bindings
        self.test_btn.Bind(wx.EVT_BUTTON, self._on_test)
        self.apply_btn.Bind(wx.EVT_BUTTON, self._on_apply)
        self.cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel)
        panel.Layout()

    def _build_ai_tab(self) -> wx.Panel:
        """Build AI settings tab with provider, model, and custom fields."""
        panel = wx.ScrolledWindow(self.notebook)
        panel.SetScrollRate(5, 5)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Provider
        sizer.Add(wx.StaticText(panel, label=t("settings.provider"), name="provider_label"), 0, wx.ALL, 5)
        self.provider_choice = wx.Choice(
            panel,
            choices=["opus", "gemini", "openai", "custom"],
            name="ai_provider",
        )
        self.provider_choice.SetLabel(t("settings.provider"))
        sizer.Add(self.provider_choice, 0, wx.ALL | wx.EXPAND, 5)
        self.provider_choice.Bind(wx.EVT_CHOICE, self._on_provider_changed)

        # Model (dropdown for built-in, text field for custom)
        model_sizer = wx.BoxSizer(wx.VERTICAL)
        model_sizer.Add(wx.StaticText(panel, label=t("settings.model"), name="model_label"), 0, wx.ALL, 5)

        self.model_choice = wx.Choice(panel, name="ai_model")
        self.model_choice.SetLabel(t("settings.model"))
        model_sizer.Add(self.model_choice, 0, wx.ALL | wx.EXPAND, 5)

        # Custom model text input (hidden by default)
        self.custom_model_text = wx.TextCtrl(panel, name="custom_model_input")
        self.custom_model_text.SetHint("e.g. my-model-v1")
        self.custom_model_text.Hide()
        model_sizer.Add(self.custom_model_text, 0, wx.ALL | wx.EXPAND, 5)

        sizer.Add(model_sizer, 0, wx.EXPAND)

        # ── Custom provider fields (hidden by default) ──────────
        self.custom_sizer = wx.BoxSizer(wx.VERTICAL)

        # Base URL
        self.custom_sizer.Add(
            wx.StaticText(panel, label=t("settings.base_url"), name="base_url_label"),
            0, wx.ALL, 5,
        )
        self.base_url_text = wx.TextCtrl(panel, name="custom_base_url")
        self.base_url_text.SetHint(t("settings.base_url_placeholder"))
        self.base_url_text.SetLabel(t("settings.base_url"))
        self.custom_sizer.Add(self.base_url_text, 0, wx.ALL | wx.EXPAND, 5)

        # API Format
        self.custom_sizer.Add(
            wx.StaticText(panel, label=t("settings.api_format"), name="api_format_label"),
            0, wx.ALL, 5,
        )
        fmt_labels = [t(label_key) for _, label_key in API_FORMATS]
        self.format_choice = wx.Choice(panel, choices=fmt_labels, name="api_format")
        self.custom_sizer.Add(self.format_choice, 0, wx.ALL | wx.EXPAND, 5)

        sizer.Add(self.custom_sizer, 0, wx.EXPAND)
        self._custom_sizer_items = list(self.custom_sizer.GetChildren())
        self._hide_custom_fields()

        # API Key
        sizer.Add(wx.StaticText(panel, label=t("settings.api_key"), name="api_key_label"), 0, wx.ALL, 5)
        self.api_key_text = wx.TextCtrl(panel, style=wx.TE_PASSWORD,
                                        name="api_key_input")
        self.api_key_text.SetHint(t("settings.api_key_placeholder"))
        self.api_key_text.SetLabel(t("settings.api_key"))
        sizer.Add(self.api_key_text, 0, wx.ALL | wx.EXPAND, 5)

        # Show/hide key button
        self.show_key_btn = wx.ToggleButton(panel, label="Show", name="toggle_key")
        sizer.Add(self.show_key_btn, 0, wx.ALL, 5)
        self.show_key_btn.Bind(wx.EVT_TOGGLEBUTTON, self._on_toggle_key)

        # Test result
        self.test_result = wx.StaticText(panel, label="", name="test_result")
        sizer.Add(self.test_result, 0, wx.ALL, 5)

        sizer.AddStretchSpacer()
        panel.SetSizer(sizer)
        return panel

    def _build_tts_tab(self) -> wx.Panel:
        """Build TTS settings tab."""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Engine
        sizer.Add(wx.StaticText(panel, label=t("settings.tts_engine"), name="tts_engine_label"), 0, wx.ALL, 5)
        self.tts_engine_choice = wx.Choice(panel, choices=["edge", "sapi5", "openai"], name="tts_engine")
        self.tts_engine_choice.SetLabel(t("settings.tts_engine"))
        sizer.Add(self.tts_engine_choice, 0, wx.ALL | wx.EXPAND, 5)

        # Voice
        sizer.Add(wx.StaticText(panel, label=t("settings.voice"), name="voice_label"), 0, wx.ALL, 5)
        self.voice_choice = wx.Choice(panel, name="tts_voice")
        self.tts_engine_choice.Bind(wx.EVT_CHOICE, self._on_tts_engine_changed)
        sizer.Add(self.voice_choice, 0, wx.ALL | wx.EXPAND, 5)

        # Speed
        sizer.Add(wx.StaticText(panel, label=t("settings.speed"), name="speed_label"), 0, wx.ALL, 5)
        self.speed_slider = wx.Slider(panel, value=10, minValue=5, maxValue=20,
                                      style=wx.SL_HORIZONTAL | wx.SL_LABELS,
                                      name="tts_speed")
        sizer.Add(self.speed_slider, 0, wx.ALL | wx.EXPAND, 5)

        sizer.AddStretchSpacer()
        panel.SetSizer(sizer)
        return panel

    def _build_general_tab(self) -> wx.Panel:
        """Build general settings tab."""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Language
        sizer.Add(wx.StaticText(panel, label=t("settings.language"), name="general_lang_label"), 0, wx.ALL, 5)
        self.lang_choice = wx.Choice(panel, choices=["en", "ms"], name="language")
        self.lang_choice.SetLabel(t("settings.language"))
        sizer.Add(self.lang_choice, 0, wx.ALL | wx.EXPAND, 5)

        # Frame rate
        sizer.Add(wx.StaticText(panel, label=t("settings.frame_rate"), name="frame_rate_label"), 0, wx.ALL, 5)
        self.fps_choice = wx.Choice(panel, choices=["1", "2", "5", "10"], name="frame_rate")
        self.fps_choice.SetLabel(t("settings.frame_rate"))
        sizer.Add(self.fps_choice, 0, wx.ALL | wx.EXPAND, 5)

        # Output directory
        sizer.Add(wx.StaticText(panel, label=t("settings.output_dir"), name="output_dir_label"), 0, wx.ALL, 5)
        out_row = wx.BoxSizer(wx.HORIZONTAL)
        self.output_text = wx.TextCtrl(panel, name="output_dir")
        browse_out = wx.Button(panel, label="...", name="browse_output")
        out_row.Add(self.output_text, 1, wx.ALL | wx.EXPAND, 5)
        out_row.Add(browse_out, 0, wx.ALL, 5)
        browse_out.Bind(wx.EVT_BUTTON, self._on_browse_output)
        sizer.Add(out_row, 0, wx.EXPAND)

        sizer.AddStretchSpacer()
        panel.SetSizer(sizer)
        return panel

    # ── Custom Provider UI Helpers ────────────────────────────

    def _hide_custom_fields(self):
        """Hide custom provider fields."""
        for child_info in self._custom_sizer_items:
            win = child_info.GetWindow()
            if win:
                win.Hide()
        self._custom_visible = False
        self.custom_model_text.Hide()

    def _show_custom_fields(self):
        """Show custom provider fields."""
        for child_info in self._custom_sizer_items:
            win = child_info.GetWindow()
            if win:
                win.Show()
        self.custom_model_text.Show()
        self._custom_visible = True
        self.Layout()

    # ── Event Handlers ─────────────────────────────────────────

    def _on_toggle_key(self, event):
        """Toggle API key visibility.

        wx.TE_PASSWORD cannot be removed at runtime on MSW, so we recreate
        the TextCtrl with the opposite style, preserving the value.
        """
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
        new_ctrl = wx.TextCtrl(parent, value=value, style=new_style,
                               name="api_key_input")
        # SetHint clears the value on some platforms, so re-apply afterwards
        new_ctrl.SetHint(t("settings.api_key_placeholder"))
        new_ctrl.SetLabel(t("settings.api_key"))
        new_ctrl.ChangeValue(value)
        sizer.Insert(index, new_ctrl, proportion, flags, border)
        sizer.Detach(self.api_key_text)
        self.api_key_text.Destroy()
        self.api_key_text = new_ctrl
        self.show_key_btn.SetLabel("Hide" if is_hidden else "Show")
        self.Layout()

    def _on_provider_changed(self, event):
        """Update model list and show/hide custom fields when provider changes."""
        provider = self.provider_choice.GetStringSelection()

        if provider == "custom":
            self._show_custom_fields()
            self.model_choice.Hide()
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
            # Populate model list from presets
            models = PROVIDER_MODELS.get(provider, [])
            self.model_choice.SetItems(models)
            # Load existing config
            prov_config = self.settings.get_ai_provider(provider)
            if prov_config.get("model"):
                self.model_choice.SetStringSelection(prov_config["model"])
            elif models:
                self.model_choice.SetSelection(0)
            if prov_config.get("api_key"):
                self.api_key_text.SetValue(prov_config["api_key"])
            else:
                self.api_key_text.SetValue("")

        self.Layout()

    def _on_tts_engine_changed(self, event):
        """Update voice list when TTS engine changes."""
        self._refresh_voice_list(self.tts_engine_choice.GetStringSelection())

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
                self.voice_choice.SetItems(names)
                if current in names:
                    self.voice_choice.SetStringSelection(current)
        except Exception as e:
            logger.warning("Voice list fetch failed for %s: %s", engine, e)

    def _on_browse_output(self, event):
        """Browse output directory."""
        dlg = wx.DirDialog(self, "Select Output Directory")
        if dlg.ShowModal() == wx.ID_OK:
            self.output_text.SetValue(dlg.GetPath())
        dlg.Destroy()

    def _on_test(self, event):
        """Test AI provider connection."""
        provider = self.provider_choice.GetStringSelection()
        api_key = self.api_key_text.GetValue().strip()

        if provider == "custom" and not self.base_url_text.GetValue().strip():
            self.test_result.SetLabel(t("settings.test_no_url"))
            return

        if not api_key:
            self.test_result.SetLabel(t("settings.test_no_key"))
            return

        self.test_result.SetLabel(t("settings.testing"))
        wx.Yield()

        def test():
            try:
                from ..core.ai_engine import AIEngine
                engine = AIEngine()

                if provider == "custom":
                    engine.set_provider(
                        "custom",
                        api_key=api_key,
                        base_url=self.base_url_text.GetValue().strip(),
                        model=self.custom_model_text.GetValue().strip(),
                        api_format=API_FORMATS[self.format_choice.GetSelection()][0],
                    )
                else:
                    engine.set_provider(provider, api_key=api_key)

                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # Text-only call — describe_frame requires a real image file
                    result = loop.run_until_complete(engine.ask("Say 'OK' in one word"))
                finally:
                    loop.close()
                wx.CallAfter(self.test_result.SetLabel, t("settings.test_ok", result=result[:60]))
            except Exception as e:
                wx.CallAfter(self.test_result.SetLabel, t("settings.test_error", error=str(e)[:100]))

        import threading
        threading.Thread(target=test, daemon=True).start()

    def _on_apply(self, event):
        """Apply settings."""
        provider = self.provider_choice.GetStringSelection()

        if provider == "custom":
            model = self.custom_model_text.GetValue().strip()
            base_url = self.base_url_text.GetValue().strip()
            api_format = API_FORMATS[self.format_choice.GetSelection()][0]
            api_key = self.api_key_text.GetValue().strip()
            if not model:
                wx.MessageBox(t("settings.enter_model_name"), t("settings.title"),
                              wx.OK | wx.ICON_WARNING)
                return
            config = self.settings.get_ai_provider("custom")
            config["api_key"] = api_key
            config["model"] = model
            config["base_url"] = base_url
            config["api_format"] = api_format
            self.settings.set_ai_provider("custom", config)
            self.settings.set("ai.default_provider", "custom")
        else:
            model = self.model_choice.GetStringSelection()
            api_key = self.api_key_text.GetValue().strip()
            config = self.settings.get_ai_provider(provider)
            config["api_key"] = api_key
            config["model"] = model
            self.settings.set_ai_provider(provider, config)
            self.settings.set("ai.default_provider", provider)

        # Update TTS
        tts_engine = self.tts_engine_choice.GetStringSelection()
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
        lang = self.lang_choice.GetStringSelection()
        self.settings.set("general.language", lang)
        I18n.set_language(lang)

        fps = self.fps_choice.GetStringSelection()
        self.settings.set("general.frame_rate", int(fps))

        output_dir = self.output_text.GetValue().strip()
        if output_dir:
            self.settings.set("general.output_dir", output_dir)

        self._load_values()
        wx.MessageBox("Settings saved.", t("settings.title"), wx.OK | wx.ICON_INFORMATION)

    def _on_cancel(self, event):
        """Close dialog without saving."""
        self.EndModal(wx.ID_CANCEL)

    # ── Load Values ────────────────────────────────────────────

    def _load_values(self):
        """Load current settings into UI."""
        default_provider = self.settings.get("ai.default_provider", "opus")
        self.provider_choice.SetStringSelection(default_provider)
        self._on_provider_changed(None)  # Refresh model list + fields

        # TTS
        default_tts = self.settings.get("tts.default_engine", "edge")
        self.tts_engine_choice.SetStringSelection(default_tts)
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

        # General
        lang = self.settings.get("general.language", "en")
        self.lang_choice.SetStringSelection(lang)

        fps = str(self.settings.get("general.frame_rate", 5))
        fps_items = [self.fps_choice.GetString(i) for i in range(self.fps_choice.GetCount())]
        if fps in fps_items:
            self.fps_choice.SetStringSelection(fps)

        output_dir = self.settings.get("general.output_dir", "")
        if output_dir:
            self.output_text.SetValue(output_dir)

        I18n.set_language(lang)


import threading as _threading
