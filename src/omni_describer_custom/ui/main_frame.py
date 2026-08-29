"""
Omni Describer Custom — Main Application Frame.

Main window: video source, provider, prompt, processing controls.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any

import wx
import wx.adv

from ..core.ai_engine import AIEngine
from ..core.tts_engine import TTSEngine
from ..core.project_store import ProjectStore
from ..core.settings_store import SettingsStore
from ..core.prompt_manager import PromptManager
from ..i18n.strings import I18n, t

logger = logging.getLogger(__name__)


class MainFrame(wx.Frame):
    """
    Main application window.
    Accessible for screen readers: labels, keyboard nav.
    """

    def __init__(self):
        self.settings = SettingsStore()
        self.ai_engine = AIEngine()
        self.tts_engine = TTSEngine()
        self.prompt_mgr = PromptManager(self.settings)
        self.project_store = ProjectStore()
        self._processing = False
        self._worker: threading.Thread | None = None
        self._current_frames: list[str] = []

        # Set language from settings
        lang = self.settings.get("general.language", "en")
        I18n.set_language(lang)

        title = t("main.title")
        super().__init__(None, title=title, size=(900, 600),
                         style=wx.DEFAULT_FRAME_STYLE | wx.MAXIMIZE)

        self._build_ui()
        self._bind_events()
        self._load_provider_settings()

        # Menu bar
        self._build_menu()

        self.SetStatusBar(self._create_statusbar())
        self.SetStatusText(t("main.ready"))

        logger.info("MainFrame initialized")

    # ── UI Builders ─────────────────────────────────────────────

    def _build_ui(self):
        """Build main UI layout."""
        panel = wx.Panel(self)
        panel.SetName("main_panel")
        panel.SetLabel(t("main.title"))
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        # ── Video Source Section ────────────────────────────────
        video_box = wx.StaticBox(panel, label=t("main.video_source"))
        video_sizer = wx.StaticBoxSizer(video_box, wx.VERTICAL)

        # File path + browse
        file_row = wx.BoxSizer(wx.HORIZONTAL)
        self.file_text = wx.TextCtrl(panel, value="", size=(500, -1),
                                     name="video_file_path")
        self.file_text.SetLabel(t("main.video_source"))
        self.browse_btn = wx.Button(panel, label=t("main.select_file"),
                                    name="browse_video")
        file_row.Add(self.file_text, 1, wx.ALL | wx.EXPAND, 5)
        file_row.Add(self.browse_btn, 0, wx.ALL, 5)

        # URL
        url_row = wx.BoxSizer(wx.HORIZONTAL)
        url_label = wx.StaticText(panel, label=t("main.url"), name="url_label")
        self.url_text = wx.TextCtrl(panel, value="", size=(500, -1),
                                    name="video_url")
        url_row.Add(url_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        url_row.Add(self.url_text, 1, wx.ALL | wx.EXPAND, 5)

        video_sizer.Add(file_row, 0, wx.EXPAND)
        video_sizer.Add(url_row, 0, wx.EXPAND)
        sizer.Add(video_sizer, 0, wx.ALL | wx.EXPAND, 10)

        # ── AI Settings Section ─────────────────────────────────
        ai_box = wx.StaticBox(panel, label=t("settings.ai_tab"))
        ai_sizer = wx.StaticBoxSizer(ai_box, wx.VERTICAL)

        # Provider + Model
        prov_row = wx.BoxSizer(wx.HORIZONTAL)
        prov_label = wx.StaticText(panel, label=t("main.provider"),
                                   name="provider_label")
        self.provider_choice = wx.Choice(panel, choices=["opus", "gemini", "openai"],
                                         name="provider_choice")
        self.provider_choice.SetLabel(t("main.provider"))
        prov_row.Add(prov_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        prov_row.Add(self.provider_choice, 1, wx.ALL | wx.EXPAND, 5)

        # Prompt preset
        prompt_row = wx.BoxSizer(wx.HORIZONTAL)
        prompt_label = wx.StaticText(panel, label=t("main.prompt"),
                                     name="prompt_label")
        self.prompt_choice = wx.Choice(panel, name="prompt_choice")
        self.prompt_choice.SetLabel(t("main.prompt"))
        self._refresh_prompt_list()
        prompt_row.Add(prompt_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        prompt_row.Add(self.prompt_choice, 1, wx.ALL | wx.EXPAND, 5)

        ai_sizer.Add(prov_row, 0, wx.EXPAND)
        ai_sizer.Add(prompt_row, 0, wx.EXPAND)
        sizer.Add(ai_sizer, 0, wx.ALL | wx.EXPAND, 10)

        # ── Action Buttons ──────────────────────────────────────
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.start_btn = wx.Button(panel, label=t("main.start"),
                                   name="start_processing")
        self.start_btn.SetLabel(t("main.start"))
        self.stop_btn = wx.Button(panel, label=t("main.stop"),
                                  name="stop_processing")
        self.stop_btn.SetLabel(t("main.stop"))
        self.stop_btn.Disable()

        self.player_btn = wx.Button(panel, label=t("player.title"),
                                    name="open_player")
        self.player_btn.SetLabel(t("player.title"))
        self.player_btn.Disable()

        btn_row.Add(self.start_btn, 0, wx.ALL, 5)
        btn_row.Add(self.stop_btn, 0, wx.ALL, 5)
        btn_row.Add(self.player_btn, 0, wx.ALL, 5)
        sizer.Add(btn_row, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        # ── Progress + Log ──────────────────────────────────────
        prog_row = wx.BoxSizer(wx.HORIZONTAL)
        prog_label = wx.StaticText(panel, label=t("main.progress"),
                                   name="progress_label")
        self.progress_bar = wx.Gauge(panel, range=100, size=(400, 20),
                                     name="progress_bar")
        prog_row.Add(prog_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        prog_row.Add(self.progress_bar, 1, wx.ALL | wx.EXPAND, 5)
        sizer.Add(prog_row, 0, wx.ALL | wx.EXPAND, 10)

        self.log_text = wx.TextCtrl(panel, value="", style=wx.TE_MULTILINE | wx.TE_READONLY,
                                    size=(-1, 200), name="log_output")
        sizer.Add(self.log_text, 1, wx.ALL | wx.EXPAND, 10)

        panel.Layout()

    def _create_statusbar(self) -> wx.StatusBar:
        """Create accessible status bar."""
        sb = wx.StatusBar(self)
        sb.SetFieldsCount(2)
        sb.SetStatusWidths([-3, -1])
        return sb

    def _build_menu(self):
        """Build menu bar."""
        menubar = wx.MenuBar()

        # File menu
        file_menu = wx.Menu()
        file_menu.Append(wx.ID_NEW, t("menu.new_project"))
        file_menu.Append(wx.ID_OPEN, t("menu.open_project"))
        file_menu.Append(wx.ID_SAVE, t("menu.save_project"))
        file_menu.Append(wx.ID_CLOSE, t("menu.close_project"))
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_PREFERENCES, t("menu.settings"))
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT, t("menu.exit"))
        menubar.Append(file_menu, t("menu.file"))

        # Edit menu
        edit_menu = wx.Menu()
        edit_menu.Append(wx.ID_UNDO, _("&Undo\tCtrl+Z"))
        menubar.Append(edit_menu, t("menu.edit"))

        # Help menu
        help_menu = wx.Menu()
        help_menu.Append(wx.ID_ABOUT, "About")
        menubar.Append(help_menu, t("menu.help"))

        self.SetMenuBar(menubar)

    # ── Events ──────────────────────────────────────────────────

    def _bind_events(self):
        """Bind UI events."""
        self.browse_btn.Bind(wx.EVT_BUTTON, self._on_browse)
        self.start_btn.Bind(wx.EVT_BUTTON, self._on_start)
        self.stop_btn.Bind(wx.EVT_BUTTON, self._on_stop)
        self.player_btn.Bind(wx.EVT_BUTTON, self._on_player)
        self.Bind(wx.EVT_MENU, self._on_settings, id=wx.ID_PREFERENCES)
        self.Bind(wx.EVT_MENU, self._on_exit, id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self._on_new_project, id=wx.ID_NEW)
        self.Bind(wx.EVT_MENU, self._on_open_project, id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self._on_save_project, id=wx.ID_SAVE)
        self.Bind(wx.EVT_MENU, self._on_close, id=wx.ID_CLOSE)
        self.Bind(wx.EVT_CLOSE, self._on_close_window)

    def _on_browse(self, event):
        """Browse for video file."""
        wildcard = "Video files|*.mp4;*.avi;*.mkv;*.mov;*.wmv;*.flv;*.webm|All files|*.*"
        dlg = wx.FileDialog(self, t("main.select_file"), wildcard=wildcard,
                            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            self.file_text.SetValue(path)
            self.url_text.SetValue("")
            self._log(f"Selected: {path}")
        dlg.Destroy()

    def _on_start(self, event):
        """Start processing the video."""
        if self._processing:
            return

        # Validate input
        file_path = self.file_text.GetValue().strip()
        url = self.url_text.GetValue().strip()

        if not file_path and not url:
            wx.MessageBox(t("error.no_video"), t("settings.title"),
                          wx.OK | wx.ICON_ERROR)
            return

        # Validate provider
        provider = self.provider_choice.GetStringSelection()
        prov_config = self.settings.get_ai_provider(provider)
        if not prov_config.get("api_key"):
            wx.MessageBox(
                t("status.no_api_key", provider=provider),
                t("settings.title"),
                wx.OK | wx.ICON_WARNING
            )
            self._show_settings()
            return

        # Set provider
        self.ai_engine.set_provider(provider, api_key=prov_config["api_key"])

        # Get prompt
        prompt_name = self.prompt_choice.GetStringSelection()
        prompt = self.prompt_mgr.get_preset(prompt_name)

        # Disable buttons
        self._processing = True
        self.start_btn.Disable()
        self.stop_btn.Enable()
        self.progress_bar.SetValue(0)

        # Run in background thread
        self._worker = threading.Thread(
            target=self._process_video,
            args=(file_path or url, prompt),
            daemon=True
        )
        self._worker.start()

    def _on_stop(self, event):
        """Stop processing."""
        self._processing = False
        self.stop_btn.Disable()
        self.SetStatusText(t("main.status"))

    def _on_player(self, event):
        """Open described video player."""
        if not self.project_store.current:
            wx.MessageBox(t("editor.no_descriptions"), t("main.title"),
                          wx.OK | wx.ICON_INFORMATION)
            return
        player = PlayerWindow(self, self.project_store, self.tts_engine)
        player.Show()

    def _on_settings(self, event):
        """Open settings dialog."""
        self._show_settings()

    def _on_new_project(self, event):
        """Create new project."""
        name_dlg = wx.TextEntryDialog(self, "Project name:", "New Project")
        if name_dlg.ShowModal() == wx.ID_OK:
            name = name_dlg.GetValue().strip()
            if name:
                proj = self.project_store.create_project(name, "")
                self._log(f"Project created: {name}")
                self.SetStatusText(f"Project: {name}")
        name_dlg.Destroy()

    def _on_open_project(self, event):
        """Open existing project."""
        projects = self.project_store.list_projects()
        if not projects:
            wx.MessageBox("No saved projects found.", "Open Project",
                          wx.OK | wx.ICON_INFORMATION)
            return

        choices = [f"{p['name']} (updated: {p['updated_at']})" for p in projects]
        dlg = wx.SingleChoiceDialog(self, "Select project:", "Open Project", choices)
        if dlg.ShowModal() == wx.ID_OK:
            idx = dlg.GetSelection()
            proj = self.project_store.open_project(projects[idx]["id"])
            if proj:
                self._log(f"Opened: {proj.name} ({len(proj.descriptions)} descriptions)")
                self.player_btn.Enable()
        dlg.Destroy()

    def _on_save_project(self, event):
        """Save current project."""
        if not self.project_store.current:
            wx.MessageBox("No project open.", t("settings.title"),
                          wx.OK | wx.ICON_INFORMATION)
            return
        self.project_store.save_descriptions(self.project_store.current.descriptions)
        self._log("Project saved")

    def _on_close(self, event):
        """Close current project."""
        self.project_store._current = None
        self.player_btn.Disable()
        self._log("Project closed")

    def _on_exit(self, event):
        """Exit application."""
        self.Close()

    def _on_close_window(self, event):
        """Handle window close."""
        self._processing = False
        self.Destroy()

    # ── Processing ──────────────────────────────────────────────

    def _process_video(self, source: str, prompt: str):
        """
        Background video processing pipeline.
        1. Get video info
        2. Extract frames
        3. Describe frames with AI
        4. Save descriptions
        """
        try:
            from ..core.video_processor import VideoProcessor
            import asyncio

            vp = VideoProcessor()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Step 1: Video info
            wx.CallAfter(self.SetStatusText, t("status.loading_video"))
            info = loop.run_until_complete(vp.get_video_info(source))
            wx.CallAfter(self._log, f"Video: {info.width}x{info.height}, {info.duration:.1f}s")
            wx.CallAfter(self.progress_bar.SetValue, 10)

            # Step 2: Extract frames
            wx.CallAfter(self.SetStatusText, t("status.extracting_frames"))
            import tempfile
            frame_dir = tempfile.mkdtemp(prefix="odc_frames_")
            frames = loop.run_until_complete(
                vp.extract_frames(source, fps=5, output_dir=frame_dir)
            )
            self._current_frames = [f.path for f in frames]
            wx.CallAfter(self._log, f"Extracted {len(frames)} frames")
            wx.CallAfter(self.progress_bar.SetValue, 30)

            if not frames:
                wx.CallAfter(self._log, "ERROR: No frames extracted")
                wx.CallAfter(self._processing_done)
                return

            # Step 3: Describe frames
            wx.CallAfter(self.SetStatusText, t("status.analyzing"))
            frame_paths = [f.path for f in frames]
            descriptions = loop.run_until_complete(
                self.ai_engine.describe_frames(frame_paths, prompt)
            )

            wx.CallAfter(self.progress_bar.SetValue, 80)

            # Step 4: Save
            wx.CallAfter(self.SetStatusText, t("status.generating_descriptions"))

            # Create project if needed
            if not self.project_store.current:
                video_name = Path(source).name if Path(source).exists() else source
                proj = self.project_store.create_project(video_name, source)
            else:
                proj = self.project_store.current

            # Save descriptions
            desc_objects = []
            for i, (frame, text) in enumerate(zip(frames, descriptions)):
                if text and not text.startswith("(error:"):
                    desc_objects.append(type('Obj', (), {
                        'id': 0,
                        'start_time': frame.timestamp,
                        'end_time': frame.timestamp + 1.0,
                        'text': text,
                        'edited': False,
                        'created_at': '',
                        'frame_path': frame.path,
                    })())

            self.project_store.save_descriptions(desc_objects)

            wx.CallAfter(self._log, f"Generated {len(desc_objects)} descriptions")
            wx.CallAfter(self.progress_bar.SetValue, 100)
            wx.CallAfter(self.SetStatusText, t("status.complete"))
            wx.CallAfter(self.player_btn.Enable)

            loop.close()

        except Exception as e:
            logger.error("Processing error: %s", e)
            wx.CallAfter(self._log, f"ERROR: {e}")
            wx.CallAfter(self.SetStatusText, t("status.error", error=str(e)))

        wx.CallAfter(self._processing_done)

    def _processing_done(self):
        """Reset UI after processing."""
        self._processing = False
        self.start_btn.Enable()
        self.stop_btn.Disable()

    # ── Helpers ─────────────────────────────────────────────────

    def _show_settings(self):
        """Open settings dialog."""
        dlg = SettingsDialog(self, self.settings)
        dlg.ShowModal()
        dlg.Destroy()
        self._load_provider_settings()

    def _load_provider_settings(self):
        """Load current provider into UI."""
        default = self.settings.get("ai.default_provider", "opus")
        self.provider_choice.SetStringSelection(default)

    def _refresh_prompt_list(self):
        """Refresh prompt preset dropdown."""
        names = self.prompt_mgr.get_preset_names()
        self.prompt_choice.SetItems(names)
        if names:
            self.prompt_choice.SetSelection(0)

    def _log(self, message: str):
        """Append a line to the log."""
        self.log_text.AppendText(message + "\n")
        # Scroll to bottom
        self.log_text.ShowPosition(self.log_text.GetLastPosition())


# Fix import issue with underscore
import gettext as _gettext
_ = _gettext.gettext
