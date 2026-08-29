"""
Omni Describer Custom — Settings Dialog.

Tabbed dialog: AI, TTS, General settings.
"""

from __future__ import annotations

import logging
import wx
from ..i18n.strings import I18n, t

logger = logging.getLogger(__name__)


class SettingsDialog(wx.Dialog):
    """Settings dialog with tabbed interface."""

    def __init__(self, parent, settings):
        super().__init__(parent, title=t("settings.title"), size=(600, 500),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.settings = settings
        self._temp_changes: dict[str, Any] = {}
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
        self.notebook.SetLabel(t("settings.title"))

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
        """Build AI settings tab."""
        panel = wx.ScrolledWindow(self.notebook)
        panel.SetScrollRate(5, 5)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Provider
        sizer.Add(wx.StaticText(panel, label=t("settings.provider"), name="provider_label"), 0, wx.ALL, 5)
        self.provider_choice = wx.Choice(panel, choices=["opus", "gemini", "openai"], name="ai_provider")
        self.provider_choice.SetLabel(t("settings.provider"))
        sizer.Add(self.provider_choice, 0, wx.ALL | wx.EXPAND, 5)

        # Provider changes -> update model list
        self.provider_choice.Bind(wx.EVT_CHOICE, self._on_provider_changed)

        # Model
        sizer.Add(wx.StaticText(panel, label=t("settings.model"), name="model_label"), 0, wx.ALL, 5)
        self.model_choice = wx.Choice(panel, name="ai_model")
        self.model_choice.SetLabel(t("settings.model"))
        sizer.Add(self.model_choice, 0, wx.ALL | wx.EXPAND, 5)

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

    # ── Event Handlers ─────────────────────────────────────────

    def _on_toggle_key(self, event):
        """Toggle API key visibility."""
        if event.IsChecked():
            self.api_key_text.SetWindowStyleFlag(wx.TE_PASSWORD ^ wx.TE_PASSWORD)
            self.show_key_btn.SetLabel("Hide")
        else:
            self.api_key_text.SetWindowStyleFlag(wx.TE_PASSWORD)
            self.show_key_btn.SetLabel("Show")
        self.api_key_text.SetFocus()

    def _on_provider_changed(self, event):
        """Update model list when provider changes."""
        provider = self.provider_choice.GetStringSelection()
        providers = self.settings.get("ai.providers", {})
        if provider in providers:
            model = providers[provider].get("model", "")
            self.model_choice.SetStringSelection(model)
            # Load existing key
            config = self.settings.get_ai_provider(provider)
            if config.get("api_key"):
                self.api_key_text.SetValue(config["api_key"])

    def _on_tts_engine_changed(self, event):
        """Update voice list when TTS engine changes."""
        engine = self.tts_engine_choice.GetStringSelection()
        # TODO: populate voice list from engine
        self.voice_choice.SetItems(["Default"])
        self.voice_choice.SetSelection(0)

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

        if not api_key:
            self.test_result.SetLabel("No API key entered")
            return

        self.test_result.SetLabel("Testing...")
        wx.Yield()

        # Test in background thread
        def test():
            try:
                from ..core.ai_engine import AIEngine
                engine = AIEngine()
                engine.set_provider(provider, api_key=api_key)
                # Simple test: list models or describe a test image
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(
                    engine.describe_frame(
                        "",  # No image = text-only test
                        "Say 'OK' in one word"
                    )
                )
                loop.close()
                wx.CallAfter(self.test_result.SetLabel, f"OK: {result[:50]}")
            except Exception as e:
                wx.CallAfter(self.test_result.SetLabel, f"Error: {str(e)[:100]}")

        threading.Thread(target=test, daemon=True).start()

    def _on_apply(self, event):
        """Apply settings."""
        provider = self.provider_choice.GetStringSelection()
        model = self.model_choice.GetStringSelection()
        api_key = self.api_key_text.GetValue().strip()

        # Update provider config
        config = self.settings.get_ai_provider(provider)
        config["api_key"] = api_key
        config["model"] = model
        self.settings.set_ai_provider(provider, config)
        self.settings.set("ai.default_provider", provider)

        # Update TTS
        tts_engine = self.tts_engine_choice.GetStringSelection()
        self.settings.set("tts.default_engine", tts_engine)

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
        # AI
        default_provider = self.settings.get("ai.default_provider", "opus")
        self.provider_choice.SetStringSelection(default_provider)

        prov_config = self.settings.get_ai_provider(default_provider)
        if prov_config:
            self.model_choice.SetStringSelection(prov_config.get("model", ""))
            if prov_config.get("api_key"):
                self.api_key_text.SetValue(prov_config["api_key"])

        # TTS
        default_tts = self.settings.get("tts.default_engine", "edge")
        self.tts_engine_choice.SetStringSelection(default_tts)

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
