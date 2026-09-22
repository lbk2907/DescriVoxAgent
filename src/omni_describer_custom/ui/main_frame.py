"""
Omni Describer Custom — Main Application Frame.

Replicates the original Omni Describer v2.1.2 UI layout:
  - Menu bar: System, Help
  - 4 source buttons (Local File / Direct URL / YouTube / Web Platform)
  - Prompt preset ComboBox + Open button
  - Multi-line custom prompt text area
  - Status Log (read-only)
  - Settings + Exit buttons

Accessible for screen readers: labels, keyboard nav.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import wx
import wx.adv

from ..core.ai_engine import AIEngine
from ..core.tts_engine import TTSEngine
from ..core.project_store import ProjectStore
from ..core.settings_store import SettingsStore
from ..core.prompt_manager import PromptManager
from ..core.video_processor import VideoProcessor, SourceError, DownloadProgress
from ..i18n.strings import I18n, t
from .settings_dialog import PROVIDER_MODELS

logger = logging.getLogger(__name__)

# Spacing constants (match original compact feel)
_BORDER = 10
_BTN_H = 28
_COMBO_H = 23
_EDIT_H = 80
_LOG_H = 110


class MainFrame(wx.Frame):
    """Main application window — mirrors Omni Describer v2.1.2 layout."""

    def __init__(self):
        self.settings = SettingsStore()
        self.ai_engine = AIEngine()
        self.tts_engine = TTSEngine(self.settings.get("tts", {}))
        self.prompt_mgr = PromptManager(self.settings)
        self.project_store = ProjectStore()
        self._processing = False
        self._dl_dialog = None
        self._dl_cancelled = False
        # v1.5.1: once the user cancels, every later UI touch from the
        # worker must be a no-op. _dl_done guards dialog re-creation,
        # player auto-open and status changes after cancellation.
        self._dl_done = False
        self._worker: threading.Thread | None = None
        self._current_frames: list[str] = []
        self._current_source: str = ""
        # Temp video file from resolve_source (YouTube download); copied
        # into the project media folder at save time (v1.5.1: also stored
        # for the "video saved at" completion message).
        self._pending_local_video: str = ""
        # v1.5.1: TRUE download title from yt-dlp metadata (used as the
        # project name instead of the raw URL) and the resolved local file.
        self._download_title: str = ""
        # v1.5.1: heartbeat timer keeps the progress dialog responsive and
        # shows elapsed time so long silent phases never look stuck.
        self._hb_timer = None
        self._hb_start = 0.0
        self._hb_phase = ""
        self._hb_dialog_was_destroyed = False
        # v1.5.5: bumped by every _close_download_progress. The
        # ProgressDialog constructor pumps the event loop, so a cleanup
        # can land WHILE a dialog is being built; the counter lets the
        # builder notice and throw the newborn dialog away.
        self._dl_close_gen = 0

        # Language
        lang = self.settings.get("general.language", "en")
        I18n.set_language(lang)

        # Keep the prompt preset manager in the same language as the UI
        # so the dropdown lists the right language-specific presets.
        self.prompt_mgr.language = lang

        title = t("main.title")
        super().__init__(
            None,
            title=title,
            size=(784, 591),
            style=wx.DEFAULT_FRAME_STYLE,
        )

        self._build_ui()
        self._build_menu()
        self._bind_events()
        self._load_settings()

        self.SetStatusBar(self._create_statusbar())
        self.SetStatusText(t("main.ready"))
        # v1.5.4: one place re-applies every translated label; runs
        # again after the Settings dialog changes general.language.
        self._retranslate_ui()

        logger.info("MainFrame initialized (v2.1.2 layout)")

    # ── UI ────────────────────────────────────────────────────────

    def _build_ui(self):
        """Build UI mirroring original layout: source buttons → preset → text → log → bottom buttons."""
        panel = wx.Panel(self)
        panel.SetName("main_panel")
        outer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(outer)

        # ── 1. Source Buttons (stacked vertically, full width) ───
        outer.AddSpacer(_BORDER)

        self.btn_local = wx.Button(panel, label=t("main.source_local"),
                                   name="source_local")
        self.btn_url = wx.Button(panel, label=t("main.source_url"),
                                 name="source_url")
        self.btn_youtube = wx.Button(panel, label=t("main.source_youtube"),
                                     name="source_youtube")
        # v1.6.7: play a video that already HAS its descriptions, with
        # no AI pass and no cost. Placed directly after "Local Video
        # File" because it is the same act — opening a file you already
        # have — and a screen-reader user meets the two together.
        self.btn_play_existing = wx.Button(
            panel, label=t("main.play_existing"), name="play_existing")
        self.btn_play_existing.SetToolTip(t("main.play_existing_hint"))

        for btn in (self.btn_local, self.btn_play_existing,
                    self.btn_url, self.btn_youtube):
            btn.SetMinSize((-1, _BTN_H))
            outer.Add(btn, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, _BORDER)
        # On MSW the Tab order follows CREATION order, not the order
        # things were added to the sizer. Without this the new button
        # would sit second on screen but last under Tab — and a
        # screen-reader user navigates by Tab, so the two orders
        # disagreeing is a real fault, not a cosmetic one.
        self.btn_play_existing.MoveAfterInTabOrder(self.btn_local)

        outer.AddSpacer(8)

        # ── 2. Prompt preset row (ComboBox + Open button) ────────
        preset_row = wx.BoxSizer(wx.HORIZONTAL)

        self.preset_label = wx.StaticText(
            panel,
            label=t("main.preset_hint"),
            name="preset_label",
        )
        outer.Add(self.preset_label, 0, wx.LEFT | wx.RIGHT, _BORDER)

        combo_row = wx.BoxSizer(wx.HORIZONTAL)
        self.prompt_choice = wx.Choice(panel, name="prompt_choice")
        self.prompt_choice.SetMinSize((-1, _COMBO_H))
        # Accessible name for screen readers (pattern: player_window).
        self.prompt_choice.SetLabel(t("main.prompt"))
        self._refresh_prompt_list()
        self.prompt_choice.Bind(wx.EVT_CHOICE, self._on_preset_selected)
        self.prompt_choice.Bind(wx.EVT_SET_FOCUS, self._on_preset_focus)

        self.btn_preset_open = wx.Button(panel, label=t("main.btn_open"),
                                         name="preset_open")
        self.btn_preset_open.SetMinSize((50, _COMBO_H))

        combo_row.Add(self.prompt_choice, 1, wx.RIGHT | wx.EXPAND, 5)
        combo_row.Add(self.btn_preset_open, 0, wx.RIGHT, _BORDER)
        outer.Add(combo_row, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, _BORDER)

        outer.AddSpacer(5)

        # ── 3. Custom prompt text area ───────────────────────────
        self.custom_prompt_label = wx.StaticText(
            panel, label=t("main.custom_prompt"),
            name="custom_prompt_label")
        outer.Add(self.custom_prompt_label, 0, wx.LEFT | wx.RIGHT, _BORDER)
        self.custom_prompt = wx.TextCtrl(
            panel,
            value="",
            style=wx.TE_MULTILINE,
            name="custom_prompt",
        )
        self.custom_prompt.SetMinSize((-1, _EDIT_H))
        # Accessible name for screen readers (pattern: player_window).
        # NOT SetLabel: on MSW that REPLACES a text control's contents
        # (v1.5.6 fix — the box used to start life holding this label).
        self._set_accessible_name(self.custom_prompt, t("main.custom_prompt"))
        outer.Add(self.custom_prompt, 0,
                  wx.LEFT | wx.RIGHT | wx.EXPAND, _BORDER)

        outer.AddSpacer(8)

        # ── 4. Status Log ────────────────────────────────────────
        self.log_label = wx.StaticText(panel, label=t("main.status_log"),
                                       name="log_label")
        outer.Add(self.log_label, 0, wx.LEFT | wx.RIGHT, _BORDER)
        self.log_text = wx.TextCtrl(
            panel,
            value="",
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name="log_output",
        )
        self.log_text.SetMinSize((-1, _LOG_H))
        # Accessible name for screen readers (pattern: player_window).
        # SetLabel would write "Status Log" INTO the log as if it were a
        # logged line (v1.5.6 fix).
        self._set_accessible_name(self.log_text, t("main.status_log"))
        outer.Add(self.log_text, 1,
                  wx.LEFT | wx.RIGHT | wx.EXPAND, _BORDER)

        outer.AddSpacer(8)

        # ── 5. Bottom buttons: Settings ... Exit ─────────────────
        bottom_row = wx.BoxSizer(wx.HORIZONTAL)

        self.btn_settings = wx.Button(panel, label=t("menu.settings"),
                                      name="open_settings")
        self.btn_settings.SetMinSize((90, _BTN_H))

        self.btn_exit = wx.Button(panel, label=t("menu.exit"),
                                  name="exit_app")
        self.btn_exit.SetMinSize((90, _BTN_H))

        bottom_row.Add(self.btn_settings, 0, wx.LEFT, _BORDER)
        bottom_row.AddStretchSpacer(1)
        bottom_row.Add(self.btn_exit, 0, wx.RIGHT, _BORDER)

        outer.Add(bottom_row, 0, wx.EXPAND)
        outer.AddSpacer(_BORDER)

        panel.Layout()

    def _create_statusbar(self) -> wx.StatusBar:
        sb = wx.StatusBar(self)
        sb.SetFieldsCount(2)
        sb.SetStatusWidths([-3, -1])
        return sb

    # ── Menu Bar ──────────────────────────────────────────────────

    def _build_menu(self):
        """File, Help. Settings lives in File; Exit appears once."""
        menubar = wx.MenuBar()

        # File — dropdown
        file_menu = wx.Menu()
        file_menu.Append(wx.ID_PREFERENCES, t("menu.settings"))
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_NEW, t("menu.new_project"))
        file_menu.Append(wx.ID_OPEN, t("menu.open_project"))
        file_menu.Append(wx.ID_SAVE, t("menu.save_project"))
        file_menu.AppendSeparator()
        self._id_import = wx.NewIdRef()
        self._id_export_srt = wx.NewIdRef()
        self._id_export_vtt = wx.NewIdRef()
        self._id_export_audio = wx.NewIdRef()
        file_menu.Append(self._id_import, t("menu.import_desc"))
        file_menu.AppendSeparator()
        file_menu.Append(self._id_export_srt, t("menu.export_srt"))
        file_menu.Append(self._id_export_vtt, t("menu.export_vtt"))
        file_menu.Append(self._id_export_audio, t("menu.export_audio"))
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT, t("menu.exit"))
        menubar.Append(file_menu, t("menu.file"))

        # Help — dropdown
        help_menu = wx.Menu()
        help_menu.Append(wx.ID_ABOUT, t("menu.about"))
        menubar.Append(help_menu, t("menu.help"))

        self.SetMenuBar(menubar)

    def _retranslate_ui(self):
        """Re-apply translated labels after a language change.

        v1.5.4: runs once at startup and again after the Settings
        dialog returns (Apply may switch general.language), so a
        language switch takes effect without restarting the app.
        """
        self.SetTitle(t("main.title"))
        self.btn_local.SetLabel(t("main.source_local"))
        self.btn_play_existing.SetLabel(t("main.play_existing"))
        self.btn_url.SetLabel(t("main.source_url"))
        self.btn_youtube.SetLabel(t("main.source_youtube"))
        self.btn_preset_open.SetLabel(t("main.btn_open"))
        self.btn_settings.SetLabel(t("menu.settings"))
        self.btn_exit.SetLabel(t("menu.exit"))
        self.preset_label.SetLabel(t("main.preset_hint"))
        self.custom_prompt_label.SetLabel(t("main.custom_prompt"))
        self.log_label.SetLabel(t("main.status_log"))
        # Accessible names for screen readers follow the language too.
        # v1.5.6: NOT via SetLabel on these three. On MSW SetLabel eats
        # the control's STATE — it clears a wx.Choice selection and
        # replaces a wx.TextCtrl's text with the label. Because
        # __init__ runs _load_settings() (which picks preset 0 and
        # previews it) BEFORE this pass, a freshly launched app ended up
        # with no preset selected — pressing Open answered "Please
        # select a prompt preset" — and with the prompt box containing
        # the label string, which _on_preset_open would have shipped to
        # the AI as "User notes". Both since v1.5.4.
        self._set_accessible_name(self.prompt_choice, t("main.prompt"))
        self._set_accessible_name(self.custom_prompt, t("main.custom_prompt"))
        self._set_accessible_name(self.log_text, t("main.status_log"))
        self._retranslate_menu()
        self.SetStatusText(t("main.ready"), 0)

    @staticmethod
    def _set_accessible_name(ctrl, label: str) -> None:
        """Give a control a screen-reader name without eating its state.

        wx.Choice keeps its selection (restored around SetLabel, which
        NVDA does read for this control); wx.TextCtrl gets SetName only,
        because for a text control the "label" IS its contents — the
        visible StaticText beside it is what NVDA announces.
        """
        if isinstance(ctrl, wx.TextCtrl):
            ctrl.SetName(label)
            return
        if isinstance(ctrl, wx.Choice):
            selection = ctrl.GetSelection()
            ctrl.SetLabel(label)
            if selection != wx.NOT_FOUND and ctrl.GetSelection() != selection:
                ctrl.SetSelection(selection)
            return
        ctrl.SetLabel(label)

    def _retranslate_menu(self):
        """Update menu item labels IN PLACE (no rebuild: ids/bindings
        stay valid, so re-binding can never go stale)."""
        menubar = self.GetMenuBar()
        if menubar is None:
            return
        for item_id, key in (
            (wx.ID_PREFERENCES, "menu.settings"),
            (wx.ID_NEW, "menu.new_project"),
            (wx.ID_OPEN, "menu.open_project"),
            (wx.ID_SAVE, "menu.save_project"),
            (self._id_import, "menu.import_desc"),
            (self._id_export_srt, "menu.export_srt"),
            (self._id_export_vtt, "menu.export_vtt"),
            (self._id_export_audio, "menu.export_audio"),
            (wx.ID_EXIT, "menu.exit"),
            (wx.ID_ABOUT, "menu.about"),
        ):
            item = menubar.FindItemById(item_id)
            if item is not None:
                item.SetItemLabel(t(key))
        # wxPython Phoenix has no MenuBar.SetLabelTop; a top-level
        # title is the wx.Menu's title.
        for idx, key in ((0, "menu.file"), (1, "menu.help")):
            menu = menubar.GetMenu(idx)
            if menu is not None:
                menu.SetTitle(t(key))

    # ── Events ────────────────────────────────────────────────────

    def _bind_events(self):
        """Bind all UI events."""
        # Source buttons
        self.btn_local.Bind(wx.EVT_BUTTON, self._on_local_file)
        self.btn_play_existing.Bind(wx.EVT_BUTTON, self._on_play_existing)
        self.btn_url.Bind(wx.EVT_BUTTON, self._on_direct_url)
        self.btn_youtube.Bind(wx.EVT_BUTTON, self._on_youtube_url)

        # Preset Open button
        self.btn_preset_open.Bind(wx.EVT_BUTTON, self._on_preset_open)

        # Bottom buttons
        self.btn_settings.Bind(wx.EVT_BUTTON, self._on_settings)
        self.btn_exit.Bind(wx.EVT_BUTTON, self._on_exit)

        # Menu
        self.Bind(wx.EVT_MENU, self._on_settings, id=wx.ID_PREFERENCES)
        self.Bind(wx.EVT_MENU, self._on_exit, id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self._on_new_project, id=wx.ID_NEW)
        self.Bind(wx.EVT_MENU, self._on_open_project, id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self._on_save_project, id=wx.ID_SAVE)
        self.Bind(wx.EVT_MENU, self._on_import_descriptions, id=self._id_import)
        self.Bind(wx.EVT_MENU, self._on_export_srt, id=self._id_export_srt)
        self.Bind(wx.EVT_MENU, self._on_export_vtt, id=self._id_export_vtt)
        self.Bind(wx.EVT_MENU, self._on_export_audio, id=self._id_export_audio)
        self.Bind(wx.EVT_MENU, self._on_about, id=wx.ID_ABOUT)
        self.Bind(wx.EVT_CLOSE, self._on_close_window)

    # ── Import / export descriptions ────────────────────────────

    def _on_import_descriptions(self, event):
        """Import SRT/VTT/simple timed text into a new project."""
        from ..core import timeline_io
        dlg = wx.FileDialog(
            self, t("impexp.dlg_import"),
            wildcard="Timed text (*.srt;*.vtt;*.txt)|*.srt;*.vtt;*.txt|All files (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()
        try:
            descs = timeline_io.parse_any(path)
        except Exception as e:
            logger.error("Import failed: %s", e)
            wx.MessageBox(t("impexp.import_failed", error=str(e)[:150]),
                          t("impexp.dlg_import"), wx.OK | wx.ICON_ERROR)
            return
        if not descs:
            wx.MessageBox(t("impexp.invalid_file"),
                          t("impexp.dlg_import"), wx.OK | wx.ICON_WARNING)
            return
        # Default policy: each import creates its own project so an
        # open project is never modified by accident.
        name = Path(path).stem or "Imported"
        self.project_store.create_project(name, "")
        self.project_store.save_descriptions(descs)
        msg = t("impexp.imported", count=len(descs), name=name)
        self._log(msg)
        self.SetStatusText(msg, 0)
        wx.MessageBox(msg, t("impexp.dlg_import"), wx.OK | wx.ICON_INFORMATION)

    def _require_project_descriptions(self):
        """Return current descriptions or None after warning the user."""
        cur = self.project_store.current
        if not cur:
            wx.MessageBox(t("impexp.no_project"), t("impexp.dlg_export"),
                          wx.OK | wx.ICON_WARNING)
            return None
        if not cur.descriptions:
            wx.MessageBox(t("impexp.nothing_to_export"), t("impexp.dlg_export"),
                          wx.OK | wx.ICON_WARNING)
            return None
        return cur

    def _on_export_srt(self, event):
        """Export current project descriptions as an SRT file."""
        from ..core import timeline_io
        cur = self._require_project_descriptions()
        if not cur:
            return
        dlg = wx.FileDialog(
            self, t("menu.export_srt"),
            defaultFile=f"{cur.name or 'descriptions'}.srt",
            wildcard="SubRip (*.srt)|*.srt",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()
        try:
            Path(path).write_text(timeline_io.to_srt(cur.descriptions),
                                  encoding="utf-8")
        except Exception as e:
            logger.error("SRT export failed: %s", e)
            wx.MessageBox(t("impexp.export_failed", error=str(e)[:150]),
                          t("impexp.dlg_export"), wx.OK | wx.ICON_ERROR)
            return
        msg = t("impexp.exported", count=len(cur.descriptions), path=path)
        self._log(msg)
        self.SetStatusText(msg, 0)

    def _on_export_vtt(self, event):
        """Export current project descriptions as a WebVTT file."""
        from ..core import timeline_io
        cur = self._require_project_descriptions()
        if not cur:
            return
        dlg = wx.FileDialog(
            self, t("menu.export_vtt"),
            defaultFile=f"{cur.name or 'descriptions'}.vtt",
            wildcard="WebVTT (*.vtt)|*.vtt",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()
        try:
            Path(path).write_text(timeline_io.to_vtt(cur.descriptions),
                                  encoding="utf-8")
        except Exception as e:
            logger.error("VTT export failed: %s", e)
            wx.MessageBox(t("impexp.export_failed", error=str(e)[:150]),
                          t("impexp.dlg_export"), wx.OK | wx.ICON_ERROR)
            return
        msg = t("impexp.exported", count=len(cur.descriptions), path=path)
        self._log(msg)
        self.SetStatusText(msg, 0)

    def _on_export_audio(self, event):
        """Render current descriptions to one synchronized audio file."""
        from ..core import timeline_io
        cur = self._require_project_descriptions()
        if not cur:
            return
        if getattr(self, "_exporting", False):
            return
        dlg = wx.FileDialog(
            self, t("menu.export_audio"),
            defaultFile=f"{cur.name or 'descriptions'}.mp3",
            wildcard="MP3 audio (*.mp3)|*.mp3|WAV audio (*.wav)|*.wav",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()

        self._exporting = True
        progress = wx.ProgressDialog(
            t("impexp.exporting_title"), t("impexp.rendering", done=0,
                                           total=len(cur.descriptions)),
            maximum=len(cur.descriptions), parent=self,
            style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE,
        )

        def done_cb(result: dict | None, error: str | None):
            def ui():
                progress.Destroy()
                self._exporting = False
                if error:
                    logger.error("Audio export failed: %s", error)
                    wx.MessageBox(t("impexp.export_failed", error=error[:150]),
                                  t("impexp.dlg_export"), wx.OK | wx.ICON_ERROR)
                    return
                msg = t("impexp.audio_done", path=result["path"],
                        rendered=result["rendered"], skipped=result["skipped"])
                self._log(msg)
                self.SetStatusText(msg, 0)
                wx.MessageBox(msg, t("impexp.dlg_export"),
                              wx.OK | wx.ICON_INFORMATION)
            wx.CallAfter(ui)

        def progress_cb(done, total, skipped):
            wx.CallAfter(progress.Update,
                         done, t("impexp.rendering", done=done, total=total))

        def worker():
            try:
                result = timeline_io.export_audio(
                    cur.descriptions, path, self.tts_engine,
                    progress_cb=progress_cb,
                )
                done_cb(result, None)
            except Exception as e:
                done_cb(None, str(e))

        threading.Thread(target=worker, daemon=True).start()

    # ── Source Handlers ───────────────────────────────────────────

    def _on_local_file(self, event):
        """Browse for local video file."""
        wildcard = ("Video files|*.mp4;*.avi;*.mkv;*.mov;*.wmv;*.flv;*.webm"
                    "|All files|*.*")
        dlg = wx.FileDialog(
            self, t("main.select_file"), wildcard=wildcard,
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            self._current_source = path
            self._log(t("main.log_selected", path=path))
            self.SetStatusText(t("main.log_file", name=Path(path).name))
        dlg.Destroy()

    # ── Play a video that already has its descriptions ───────────

    _SUBTITLE_SUFFIXES = (".srt", ".vtt", ".txt")

    @staticmethod
    def _find_sibling_subtitles(video: Path) -> Path | None:
        """A subtitle file that clearly belongs to this video.

        Only exact stem matches — movie.mp4 finds movie.srt, never some
        other .srt that happens to share the folder. Guessing wrong
        would play one film's descriptions over another's.

        Static because it is a pure question about a path: it needs no
        window, so it can be tested without building one.
        """
        for suffix in MainFrame._SUBTITLE_SUFFIXES:
            candidate = video.with_suffix(suffix)
            if candidate.is_file():
                return candidate
        return None

    def _on_play_existing(self, event):
        """Open a video plus its existing descriptions and just play it.

        No AI pass, no cost, no waiting: this is for the case where the
        descriptions already exist — made here earlier, or written by
        hand — and the user wants to listen to them again. Before
        v1.6.7 the pieces existed but nothing joined them: importing an
        SRT created a project with no video, so the player opened with
        descriptions over silence.
        """
        wildcard = ("Video files|*.mp4;*.avi;*.mkv;*.mov;*.wmv;*.flv;*.webm"
                    "|All files|*.*")
        dlg = wx.FileDialog(
            self, t("main.play_existing_pick_video"), wildcard=wildcard,
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        video = Path(dlg.GetPath())
        dlg.Destroy()

        subtitles = self._find_sibling_subtitles(video)
        if subtitles is not None:
            ask = wx.MessageDialog(
                self, t("main.play_existing_found", name=subtitles.name),
                t("main.play_existing"), wx.YES_NO | wx.ICON_QUESTION)
            ask.SetYesNoLabels(t("main.play_existing_use_found"),
                               t("main.play_existing_pick_other"))
            use_it = ask.ShowModal() == wx.ID_YES
            ask.Destroy()
            if not use_it:
                subtitles = None
        if subtitles is None:
            sub_dlg = wx.FileDialog(
                self, t("main.play_existing_pick_subs"),
                defaultDir=str(video.parent),
                wildcard=("Timed text (*.srt;*.vtt;*.txt)|*.srt;*.vtt;*.txt"
                          "|All files|*.*"),
                style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
            if sub_dlg.ShowModal() != wx.ID_OK:
                sub_dlg.Destroy()
                return
            subtitles = Path(sub_dlg.GetPath())
            sub_dlg.Destroy()

        self._open_existing(video, subtitles)

    def _open_existing(self, video: Path, subtitles: Path) -> None:
        """Build a project from a video + subtitle pair and play it."""
        from ..core import timeline_io
        try:
            descriptions = timeline_io.parse_any(str(subtitles))
        except Exception as e:
            logger.error("Could not read %s: %s", subtitles, e)
            wx.MessageBox(t("impexp.import_failed", error=str(e)[:150]),
                          t("main.play_existing"), wx.OK | wx.ICON_ERROR)
            return
        if not descriptions:
            wx.MessageBox(t("impexp.invalid_file"), t("main.play_existing"),
                          wx.OK | wx.ICON_WARNING)
            return
        try:
            self.project_store.create_project(video.stem, str(video))
            # Copy the video in, so the project still plays if the
            # original is moved or a USB stick is unplugged.
            self.project_store.persist_video_file(str(video))
            self.project_store.save_descriptions(descriptions)
        except Exception as e:
            logger.error("Could not build a project for %s: %s", video, e)
            wx.MessageBox(t("main.play_existing_failed", error=str(e)[:150]),
                          t("main.play_existing"), wx.OK | wx.ICON_ERROR)
            return
        message = t("main.play_existing_ready",
                    count=len(descriptions), name=video.name)
        self._log(message)
        self.SetStatusText(message, 0)
        self._open_player()

    def _on_direct_url(self, event):
        """Open dialog to enter a direct video URL."""
        dlg = wx.TextEntryDialog(
            self, t("main.enter_url"), t("main.source_url"),
        )
        if dlg.ShowModal() == wx.ID_OK:
            url = dlg.GetValue().strip()
            if url:
                self._current_source = url
                self._log(t("main.log_url", url=url))
                self.SetStatusText(t("main.log_url", url=url[:60]))
        dlg.Destroy()

    def _on_youtube_url(self, event):
        """Open dialog to enter a YouTube URL."""
        dlg = wx.TextEntryDialog(
            self, t("main.enter_youtube"), t("main.source_youtube"),
        )
        if dlg.ShowModal() == wx.ID_OK:
            url = dlg.GetValue().strip()
            if url:
                self._current_source = url
                self._log(t("main.log_youtube", url=url))
                self.SetStatusText(t("main.log_youtube", url=url[:60]))
        dlg.Destroy()

    # ── Preset Handler ─────────────────────────────────���──────────

    def _on_preset_open(self, event):
        """Apply the selected prompt preset and start processing."""
        preset_name = self.prompt_choice.GetStringSelection()
        if not preset_name:
            wx.MessageBox(t("main.no_preset"), t("settings.title"),
                          wx.OK | wx.ICON_WARNING)
            return

        # Get preset text
        prompt = self.prompt_mgr.get_preset(preset_name)
        if not prompt:
            wx.MessageBox(t("main.no_preset"), t("settings.title"),
                          wx.OK | wx.ICON_WARNING)
            return

        # v1.6.0: the `foreign` preset exists to convey SPEECH the
        # listener cannot understand. A provider that only sees frames
        # cannot do that, and fails silently — it returns an ordinary
        # visual description, which a blind user has no way to spot.
        # Probed 20 Sep 2026: GLM answers "NO AUDIO ACCESS".
        if "foreign" in preset_name.lower():
            from ..core.ai_engine import provider_hears_audio

            provider = self.settings.get("ai.default_provider", "gemini")
            if not provider_hears_audio(provider):
                answer = wx.MessageBox(
                    t("preset.needs_audio", provider=provider),
                    t("settings.title"),
                    wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
                if answer != wx.YES:
                    self.SetStatusText(t("status.ready"))
                    return

        # Anything typed on top of the previewed preset counts as
        # extra notes; ignore text identical to the preset itself.
        custom = self.custom_prompt.GetValue().strip()
        if custom and custom != prompt.strip():
            prompt = f"{prompt}\n\nUser notes: {custom}"

        self._log(t("main.log_preset", name=preset_name))
        self._start_processing(prompt)

    def _on_preset_selected(self, event):
        """A preset was picked: show its text and announce it."""
        self._preview_preset(event.GetString())
        event.Skip()

    def _on_preset_focus(self, event):
        """Announce the current preset when the picker gets focus."""
        name = self.prompt_choice.GetStringSelection()
        if name and self.GetStatusBar():
            self.SetStatusText(t("status.preset_selected", name=name), 0)
        event.Skip()

    def _preview_preset(self, name: str):
        """Put the preset text into the custom prompt box and announce
        the selection, so screen reader users can read and edit it."""
        if not name:
            return
        text = self.prompt_mgr.get_preset(name)
        box = getattr(self, "custom_prompt", None)
        if text and box is not None:
            box.ChangeValue(text)
        if self.GetStatusBar():
            self.SetStatusText(t("status.preset_selected", name=name), 0)
        if name == "default" and getattr(self, "log_text", None) is not None:
            self._log(t("prompts.default_hint"))
        logger.info("Preset selected: %s", name)

    # ── Settings / Exit ───────────────────────────────────────────

    def _on_settings(self, event):
        """Open settings dialog."""
        from .settings_dialog import SettingsDialog
        dlg = SettingsDialog(self, self.settings, self.tts_engine)
        result = dlg.ShowModal()
        dlg.Destroy()
        if result != wx.ID_OK:
            # User cancelled: keep their current preset selection and
            # prompt text untouched.
            return
        # v1.5.4: Settings Apply may have switched general.language.
        # Re-sync I18n + the preset language, then re-translate every
        # label (widgets + menus) so the switch needs no restart.
        lang = str(self.settings.get("general.language", "en") or "en")
        I18n.set_language(lang)
        self.prompt_mgr.language = lang
        self._retranslate_ui()
        self._load_settings()
        # Re-apply TTS engine/voice/speed from settings
        self.tts_engine.settings = self.settings.get("tts", {})
        self.tts_engine._init_engines()

    def _on_exit(self, event):
        """Exit the application."""
        self._processing = False
        self.Close()

    def _on_new_project(self, event):
        name_dlg = wx.TextEntryDialog(self, t("main.project_name"),
                                      t("main.new_project"))
        if name_dlg.ShowModal() == wx.ID_OK:
            name = name_dlg.GetValue().strip()
            if name:
                self.project_store.create_project(name, "")
                self._log(t("main.log_project_created", name=name))
                self.SetStatusText(t("main.log_project", name=name))
        name_dlg.Destroy()

    def _on_open_project(self, event):
        """v1.5.1: custom dialog with Open AND Remove buttons.

        The old SingleChoiceDialog could only open a project; removing a
        wrong/finished project required manual file deletion. Now the
        user selects a project and can open it or remove it (DB + media
        folder) with explicit confirmation.
        """
        projects = self.project_store.list_projects()
        if not projects:
            wx.MessageBox(t("main.no_saved_projects"),
                          t("main.open_project_title"),
                          wx.OK | wx.ICON_INFORMATION)
            return

        dlg = wx.Dialog(self, title=t("project.dialog_title"),
                        size=(460, 300))
        pad = 5
        top = wx.BoxSizer(wx.VERTICAL)
        top.Add(wx.StaticText(dlg, label=t("project.select_hint")),
                0, wx.ALL, pad)
        lb = wx.ListBox(dlg, choices=[
            f"{p['name']} (updated: {p['updated_at']})" for p in projects],
            style=wx.LB_SINGLE)
        top.Add(lb, 1, wx.ALL | wx.EXPAND, pad)
        btns = wx.BoxSizer(wx.HORIZONTAL)
        open_btn = wx.Button(dlg, wx.ID_OK, t("project.open_btn"))
        open_btn.SetDefault()
        remove_btn = wx.Button(dlg, wx.ID_ANY, t("project.remove_btn"))
        cancel_btn = wx.Button(dlg, wx.ID_CANCEL, t("close"))
        btns.Add(open_btn, 0, wx.ALL, pad)
        btns.Add(remove_btn, 0, wx.ALL, pad)
        btns.AddStretchSpacer()
        btns.Add(cancel_btn, 0, wx.ALL, pad)
        top.Add(btns, 0, wx.ALL | wx.EXPAND, pad)
        dlg.SetSizer(top)

        def _selected():
            idx = lb.GetSelection()
            return projects[idx] if idx != wx.NOT_FOUND else None

        def _on_remove(evt):
            proj = _selected()
            if not proj:
                wx.MessageBox(t("project.select_hint"),
                              t("project.dialog_title"),
                              wx.OK | wx.ICON_INFORMATION)
                return
            name = proj.get("name", "")
            confirm = wx.MessageDialog(
                dlg, t("project.remove_confirm", name=name),
                t("project.remove_title"),
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
            confirmed = confirm.ShowModal() == wx.ID_YES
            confirm.Destroy()
            if not confirmed:
                return
            ok, err = self._remove_project_files(proj["id"])
            if ok:
                self._log(t("project.removed_log", name=name))
            else:
                self._log(t("project.remove_failed", name=name, error=err))
                wx.MessageBox(t("project.remove_failed", name=name, error=err),
                              t("project.remove_title"),
                              wx.OK | wx.ICON_WARNING)
            # Refresh the list in place
            projects[:] = self.project_store.list_projects()
            if projects:
                lb.Set([
                    f"{p['name']} (updated: {p['updated_at']})"
                    for p in projects])
                lb.SetSelection(0)
            else:
                dlg.EndModal(wx.ID_CANCEL)

        remove_btn.Bind(wx.EVT_BUTTON, _on_remove)
        lb.Bind(wx.EVT_DOUBLECLICK, lambda evt: dlg.EndModal(wx.ID_OK))

        # Preselect the newest project
        lb.SetSelection(0)
        dlg.CenterOnScreen()
        result = dlg.ShowModal()
        dlg.Destroy()

        if result == wx.ID_OK:
            proj_row = _selected()
            if proj_row:
                proj = self.project_store.open_project(proj_row["id"])
                if proj:
                    self._log(t("main.log_opened", name=proj.name,
                                count=len(proj.descriptions)))
                    if not proj.descriptions:
                        wx.MessageBox(t("project.opened_empty", name=proj.name),
                                      t("project.dialog_title"),
                                      wx.OK | wx.ICON_WARNING)

    def _remove_project_files(self, project_id: int):
        """Delete a project's DB file + media folder. Returns (ok, error)."""
        import shutil as _shutil
        base = Path(self.project_store.projects_dir)
        errors = []
        db_path = base / f"project_{project_id}.db"
        media_root = base / f"project_{project_id}"
        try:
            if media_root.exists():
                _shutil.rmtree(media_root, ignore_errors=False)
        except Exception as e:
            errors.append(str(e))
        try:
            if db_path.exists():
                db_path.unlink()
        except Exception as e:
            errors.append(str(e))
        if self.project_store.current and self.project_store.current.id == project_id:
            self.project_store._current = None
        return (not errors, "; ".join(errors))

    def _on_save_project(self, event):
        if not self.project_store.current:
            wx.MessageBox(t("main.no_project"), t("save"),
                          wx.OK | wx.ICON_INFORMATION)
            return
        self.project_store.save_descriptions(self.project_store.current.descriptions)
        self._log(t("main.log_project_saved"))

    def _on_about(self, event):
        info = wx.adv.AboutDialogInfo()
        info.SetName("Omni Describer Custom")
        from omni_describer_custom import __version__
        info.SetVersion(__version__)
        info.SetDescription(
            "Accessible audio description tool for blind and visually "
            "impaired users. Describes video frames using AI and narrates "
            "them via text-to-speech."
        )
        info.SetCopyright("(C) 2026 Omni Describer Custom")
        wx.adv.AboutBox(info)

    def _on_close_window(self, event):
        """Handle window close.

        v1.5.1: closing during processing used to leave the worker
        thread posting wx.CallAfter callbacks into a destroyed frame
        (crash). Now we first signal cancel so the worker unwinds, and
        the callbacks all check _dl_done/IsBeingDeleted before touching
        widgets.
        """
        if self._processing:
            self._dl_cancelled = True
            self._dl_done = True
            self._hb_stop()
            self._close_download_progress()
            # Give the worker a moment to observe the flag; it is a
            # daemon thread, so even a slow subprocess teardown will not
            # block process exit.
            self._worker.join(timeout=3.0) if self._worker and self._worker.is_alive() else None
        self._processing = False
        self.Destroy()

    # ── Processing ────────────────────────────────────────────────

    def _start_processing(self, prompt: str):
        """Start video processing in background thread."""
        if self._processing:
            return

        source = self._current_source
        if not source:
            wx.MessageBox(t("error.no_video"), t("settings.title"),
                          wx.OK | wx.ICON_ERROR)
            return

        # Validate provider
        provider = self.settings.get("ai.default_provider", "gemini")
        prov_config = self.settings.get_ai_provider(provider)
        if not prov_config.get("api_key"):
            wx.MessageBox(
                t("status.no_api_key", provider=provider),
                t("settings.title"), wx.OK | wx.ICON_WARNING,
            )
            self._on_settings(None)
            return

        self.ai_engine.set_provider(
            provider,
            api_key=prov_config["api_key"],
            base_url=prov_config.get("base_url", ""),
            model=prov_config.get("model", ""),
            api_format=prov_config.get("api_format", ""),
        )
        # v1.5.2: description language - pilihan khas
        # ("ms"/"en"); kosong = ikut bahasa UI.
        desc_lang = str(self.settings.get(
            "general.description_language", "") or "").strip().lower()
        # v1.6.2: was hardcoded to ("ms", "en"), which silently threw
        # away any other choice and fell back to the UI language. Now
        # anything with a locale file counts; "system" (or blank) still
        # means "follow the UI".
        from ..i18n.strings import I18n
        if desc_lang not in I18n.available_languages():
            desc_lang = str(self.settings.get(
                "general.language", "en") or "en").strip().lower()
        self.ai_engine.output_lang = desc_lang

        # v1.5.1 dedupe: the SAME source may already have a project (it
        # stores the original URL/path). Offer to open it instead of
        # paying for a second download + AI pass.
        existing = self.project_store.find_project_by_source(source)
        if existing:
            msg = (t("project.dedupe_found") + "\n\n"
                   f"{existing.get('name', '')} "
                   f"(updated: {existing.get('updated_at', '')})")
            dlg = wx.MessageDialog(
                self, msg, t("project.dedupe_title"),
                wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION)
            # v1.5.5: wxPython Phoenix has NO SetYesLabel/SetNoLabel/
            # SetCancelLabel (same family as the missing
            # MenuBar.SetLabelTop). Calling them raised AttributeError
            # here, so opening a video that already had a project did
            # nothing at all — no dialog, no processing, a dead button.
            # SetYesNoCancelLabels is the real Phoenix API.
            dlg.SetYesNoCancelLabels(t("project.dedupe_open"),
                                     t("project.dedupe_new"),
                                     t("cancel"))
            choice = dlg.ShowModal()
            dlg.Destroy()
            if choice == wx.ID_YES:
                proj = self.project_store.open_project(existing["id"])
                if proj:
                    self._log(t("main.log_opened", name=proj.name,
                                count=len(proj.descriptions)))
                    self.SetStatusText(t("main.log_project", name=proj.name))
                    if not proj.descriptions:
                        wx.MessageBox(t("project.opened_empty", name=proj.name),
                                      t("project.dialog_title"),
                                      wx.OK | wx.ICON_WARNING)
                return
            if choice == wx.ID_CANCEL:
                return
            # ID_NO: fall through and process again as a new project.
            # Forget which source the open project belongs to, so
            # _ensure_project_for cannot decide to reuse it — the user
            # just said they wanted a separate one.
            self._project_source = ""

        self._processing = True
        self._dl_cancelled = False
        self._dl_done = False
        self.btn_preset_open.Disable()
        self.btn_local.Disable()
        self.btn_play_existing.Disable()
        self.btn_url.Disable()
        self.btn_youtube.Disable()

        self._worker = threading.Thread(
            target=self._process_video,
            args=(source, prompt),
            daemon=True,
        )
        self._worker.start()

    # ── v1.5.1 heartbeat: silent phases stay visibly alive ────────

    def _hb_start_timer(self, phase: str) -> None:
        """Start the 1s heartbeat timer (UI thread) for a phase."""
        import time as _time
        self._hb_phase = phase
        self._hb_start = _time.monotonic()
        self._hb_dialog_was_destroyed = False
        if self._hb_timer is None:
            self._hb_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._hb_tick, self._hb_timer)
        self._hb_timer.Start(1000)

    def _hb_set_phase(self, phase: str) -> None:
        """Tell the heartbeat which phase we are actually in now.

        v1.6.4: this was the missing half. _hb_phase was written once, at
        the start, with "Loading video info..." — and never again. The
        dialog then repeated that line for the whole job while the
        counter climbed: a user waiting 808 seconds was told the app was
        still loading video info, and the title still read "Downloading
        video - 100%" from a download that had finished long before.

        Resetting _hb_start too means the seconds shown are the seconds
        THIS phase has taken, which is the number a waiting user wants —
        not the age of the whole job.
        """
        import time as _time
        if not phase or phase == self._hb_phase:
            return
        self._hb_phase = phase
        self._hb_start = _time.monotonic()

    def _hb_stop(self) -> None:
        if self._hb_timer is not None:
            self._hb_timer.Stop()

    def _hb_tick(self, event):
        """1s tick: keep the dialog responsive and show elapsed time.

        Fixes the "stuck" feel (and stuck REALITY) during silent phases:
        - metadata probe / ffmpeg merge: Pulse keeps the dialog painting
          and the Cancel button live.
        - only pulses when NO real progress arrived recently (>1.5s), so
          it never fights with real percentage updates.
        - if the dialog was destroyed by a Cancel press, nothing is
          re-created (guarded by _dl_done).
        """
        if self._dl_done or self._dl_cancelled:
            self._hb_stop()
            return
        import time as _time
        dlg = self._dl_dialog
        if dlg is None:
            return
        now = _time.monotonic()
        if now - getattr(self, "_last_progress_at", 0.0) < 1.5:
            return  # real progress is flowing; stay out of the way
        secs = int(now - self._hb_start)
        line = t("download.heartbeat", phase=self._hb_phase, secs=secs)
        try:
            dlg.Pulse(line)
        except Exception:
            # Dialog already destroyed (e.g. user closed it): stop.
            self._hb_stop()

    def _project_display_name(self, source: str) -> str:
        """v1.5.1: human project name for remote sources.

        Remote URL -> the REAL video title from yt-dlp metadata
        (sanitized); local file -> the filename stem. Never the raw URL.
        """
        if source.startswith(("http://", "https://")) and not Path(source).exists():
            from ..core.video_processor import VideoProcessor
            return VideoProcessor.sanitize_project_name(
                self._download_title, fallback="video")
        return Path(source).stem or "video"

    def _tts_speed(self) -> float:
        """The speed the user's chosen narration voice actually runs at."""
        try:
            engine = self.settings.get("tts.default_engine", "edge") or "edge"
            return float(self.settings.get(
                f"tts.engines.{engine}.speed", 1.0) or 1.0)
        except (TypeError, ValueError):
            return 1.0

    def _tts_words_per_second(self) -> float:
        from ..core.timeline_io import WORDS_PER_SECOND_AT_1X
        return WORDS_PER_SECOND_AT_1X * max(0.5, self._tts_speed())

    def _time_cues_by_length(self, pairs, transcript=None):
        """Give each cue the time its text actually needs, and report
        the ones that still land on top of speech.

        Every cue used to get a flat three seconds. A 36-word
        description takes about ten seconds to say at 1.5x, so it ran
        into the next cue AND into the dialogue — measured on a real
        run, where cue 1 (0-3s) and cue 2 (2-5s) overlapped outright.

        The text is never altered here. Only the timing is corrected,
        and anything still colliding is named so the user can decide.
        """
        from ..core.timeline_io import speaking_seconds
        speed = self._tts_speed()
        speaking = [(secs, text, speaking_seconds(text, speed))
                    for secs, text in pairs]

        objects = []
        collisions = []
        for index, (secs, text, needed) in enumerate(speaking):
            end = secs + needed
            # Never run into the next description: shorten rather than
            # overlap, because two voices at once is no description.
            if index + 1 < len(speaking):
                end = min(end, speaking[index + 1][0])
            objects.append(type("Obj", (), {
                "id": 0,
                "start_time": secs,
                "end_time": max(secs + 0.5, end),
                "text": text,
                "edited": False,
                "created_at": "",
                "frame_path": "",  # no frame: AI watched the video
            })())
            for seg in transcript or []:
                s = float(getattr(seg, "start", 0.0))
                e = float(getattr(seg, "end", s))
                if secs < e and secs + needed > s:
                    collisions.append((secs, len(text.split())))
                    break
        return objects, collisions

    def _report_cue_collisions(self, collisions, total: int) -> None:
        """Say plainly which descriptions will talk over the dialogue."""
        if not collisions:
            return
        where = ", ".join(f"{secs:.0f}s ({words} words)"
                          for secs, words in collisions[:6])
        message = t("process.cues_overrun", count=len(collisions),
                    total=total, where=where)
        logger.info("Cue/speech collisions: %s", where)
        wx.CallAfter(self._log, message)

    def _ensure_project_for(self, source: str) -> str:
        """Make sure a project exists before anything is downloaded.

        Returns its media folder, which becomes the download directory
        so an interrupted download resumes there next time (v1.6.7).

        Returns "" on failure rather than raising: a project that
        cannot be created should cost the user resumability, not the
        whole job — the pipeline then falls back to a temp directory
        exactly as it behaved before.
        """
        try:
            current = self.project_store.current
            # Reuse ONLY a project this frame opened for THIS source.
            # "current" alone is not enough: it survives from the last
            # job, so describing video B straight after video A would
            # have downloaded B into A's folder and overwritten A's
            # descriptions. Verified before fixing — asking for B while
            # A was current returned A's media directory.
            # Two ways a project is known to belong to this source:
            # this frame opened it for that source, or the project
            # still records the source as its video_path (true until
            # persist_video_file replaces it with the local copy).
            owns_it = current is not None and (
                getattr(self, "_project_source", "") == source
                or (current.video_path or "") == source)
            if not owns_it:
                name = (self._project_display_name(source)
                        if not Path(source).exists() else Path(source).stem)
                self.project_store.create_project(name, source)
                current = self.project_store.current
                self._project_created_by_run = True
            if current is None:
                return ""
            self._project_source = source
            return str(self.project_store.media_dir(current.id))
        except Exception as e:
            logger.warning("Could not prepare a project for %s (%s); the "
                           "download will not be resumable", source, e)
            return ""

    def _discard_project_if_empty(self) -> None:
        """Drop a project this run created that holds nothing at all.

        Cancelling used to leave no trace; creating the project up front
        would leave an empty one behind on every abandoned attempt. But
        a project holding a PARTIAL download is kept deliberately —
        that partial is the thing being resumed, and deleting it would
        undo the feature.
        """
        if not getattr(self, "_project_created_by_run", False):
            return
        self._project_created_by_run = False
        current = self.project_store.current
        if current is None or current.descriptions:
            return
        try:
            media = self.project_store.media_dir(current.id)
            if any(media.iterdir()):
                logger.info("Keeping project %s: it holds a partial "
                            "download to resume", current.id)
                return
            self.project_store.delete_project(current.id)
            logger.info("Discarded empty project %s after an abandoned run",
                        current.id)
        except Exception as e:
            logger.warning("Could not tidy up empty project: %s", e)

    def _process_video(self, source: str, prompt: str):
        """Background video processing pipeline.

        Frame lifecycle (fix for the "frames deleted before AI" bug): the
        temp frame dir stays alive until the AI describe step has finished
        and the project is saved, and every used frame is copied into the
        project folder so the player keeps a permanent copy. The progress
        dialog now covers the whole pipeline (download -> merge ->
        extraction -> AI analysis -> save) so it never looks stuck on one
        phase, and Cancel aborts the AI loop between frames.
        """
        frame_dir: str | None = None
        loop = None  # proactor loop: closed on EVERY exit path (leak fix)
        # v1.5.5: each mode stops the frame counter thread itself (full
        # video at its branch head, frame mode in the extraction finally),
        # but nothing covered a failure BETWEEN the thread starting and
        # those points — that window leaked a daemon thread polling a
        # deleted temp dir every 0.7s. Held here so the outer finally can
        # stop it on every exit path, like the event loop above.
        stop_counter = None
        try:
            vp = VideoProcessor()
            loop = __import__("asyncio").new_event_loop()
            __import__("asyncio").set_event_loop(loop)
            import shutil
            import tempfile
            import threading
            import time as _time

            # Step 1: Video info
            wx.CallAfter(self.SetStatusText, t("status.loading_video"))
            # FIX (1 Sep): for URLs the yt-dlp metadata probe can take up
            # to 120s with NO visible feedback (the download dialog only
            # appears at the first download event). Show the phase
            # immediately; screen readers read the status line.
            wx.CallAfter(self._ensure_download_progress)
            wx.CallAfter(self._download_progress_tick_text,
                         t("download.loading_info"), -1)
            wx.CallAfter(self._hb_start_timer, t("download.loading_info"))
            info = loop.run_until_complete(vp.get_video_info(
                source,
                is_cancelled=lambda: bool(
                    getattr(self, "_dl_cancelled", False))))
            # v1.5.1: keep the REAL title (yt-dlp metadata) for the
            # project name; local files keep their filename stem.
            self._download_title = getattr(info, "title", "") or ""
            wx.CallAfter(self._log, f"Video: {info.width}x{info.height}, {info.duration:.1f}s")

            # v1.4.1: chunk length is user-configurable (General tab).
            # Announce it once with an estimated part count so blind users
            # know upfront how many parts the video will be split into.
            chunk_seconds = int(self.settings.get(
                "general.chunk_seconds", 600) or 600)
            est_parts = (max(1, int(float(info.duration) / chunk_seconds + 0.999))
                         if info.duration > 0 else 1)
            if est_parts > 1:
                wx.CallAfter(self._log, t("video.chunk_multi",
                                          chunk=chunk_seconds, parts=est_parts))
            else:
                wx.CallAfter(self._log, t("video.chunk_single",
                                          chunk=chunk_seconds))

            # Full-video mode decided ONCE here so every announcement in
            # this pipeline stays accurate for this mode (no frame wording)
            video_mode = (
                self.settings.get("ai.video_mode", "frames") == "full"
                and self.settings.get("ai.default_provider", "")
                in ("gemini", "minimax", "glm")
            )

            # Step 2: Extract frames (FPS from settings). For URLs this first
            # downloads via yt-dlp with a REAL progress dialog: percentage,
            # MB downloaded of MB total, speed and ETA (user request 30 Aug).
            # The dialog is created lazily on the first download event so
            # local files never see an empty dialog.
            # FIX (30 Aug): during the silent ffmpeg extraction a background
            # counter keeps the dialog moving ("Extracting frames: N").
            # FIX (1 Sep, full-video mode): announcing "Extracting
            # frames" misleads screen-reader users when no frames are
            # involved; frame_dir/counter stay as harmless machinery.
            if not video_mode:
                wx.CallAfter(self.SetStatusText, t("status.extracting_frames"))
            # v1.6.7: the project is created HERE, before the download,
            # not after the AI finishes. A download that dies halfway
            # then has a permanent home to resume into; previously each
            # attempt used a fresh temp dir, so the partial file was
            # orphaned and the next attempt started from zero. The three
            # later create_project calls are guarded by "if not current"
            # and become no-ops.
            # Declared for the WHOLE pipeline, not inside one branch.
            # It was assigned only under "if video_mode", while fast
            # mode reads it too — a NameError that would have killed
            # every fast-mode job with an unexplained "Processing
            # error". Caught by walking the branches, not by reading.
            transcript: list = []
            download_dir = self._ensure_project_for(source)
            # The same folder keeps the compressed upload copy, so a
            # retry after a failed upload skips the re-encode. Guarded
            # because it is only a speed hint: an engine that will not
            # take it must cost the user a re-encode, not the job.
            try:
                self.ai_engine.upload_cache_dir = download_dir
            except Exception as e:
                logger.warning("Upload cache dir not accepted (%s); a "
                               "retry will re-compress the video", e)
            # v1.6.8: the model is told how many words fit in each
            # silent gap, and that depends on how fast THIS user's
            # voice speaks. A listener at 1.5x gets a bigger budget
            # than one at 1.0x, instead of a figure that suits neither.
            try:
                self.ai_engine.words_per_second = self._tts_words_per_second()
            except Exception as e:
                logger.warning("Speaking rate not accepted (%s); the "
                               "default pace will be used", e)
            frame_dir = tempfile.mkdtemp(prefix="odc_frames_")
            last_ui_update = [0.0]
            stop_counter = threading.Event()

            def _ui_throttled(fn, *args) -> None:
                """Run fn on the UI thread, throttled to >=0.5s apart."""
                now = _time.monotonic()
                if now - last_ui_update[0] < 0.5:
                    return
                last_ui_update[0] = now
                wx.CallAfter(fn, *args)

            def _ui_now(fn, *args) -> None:
                wx.CallAfter(fn, *args)

            def count_frames() -> None:
                """Keep the dialog alive while ffmpeg extracts silently."""
                while not stop_counter.wait(0.7):
                    try:
                        n = sum(1 for _ in Path(frame_dir).glob("frame_*.jpg")) if frame_dir else 0
                    except Exception:
                        continue
                    if n:
                        wx.CallAfter(self._ensure_download_progress)
                        _ui_throttled(self._frame_count_tick, n)

            counter_thread = threading.Thread(target=count_frames, daemon=True)
            counter_thread.start()

            def download_progress(p) -> None:
                _ui_now(self._ensure_download_progress)
                _ui_now(self._download_progress_tick, p)

            # ── Full-video mode (Gemini native video understanding) ──
            # ai.video_mode == "full" AND provider == gemini: upload the
            # WHOLE video and let Gemini watch it (audio + visual) and
            # return its own timestamped description list. No frame
            # extraction, one AI call instead of one per frame.
            if video_mode:
                stop_counter.set()  # no frames to count in this mode
                wx.CallAfter(self._log, t("video.mode_enabled_log"))
                wx.CallAfter(self.SetStatusText, t("status.analyzing_video"))
                try:
                    resolved = loop.run_until_complete(vp.resolve_source(
                        source, on_progress=download_progress,
                        is_cancelled=lambda: bool(
                            getattr(self, "_dl_cancelled", False)),
                        out_dir=download_dir)
                    )
                    self._pending_local_video = resolved
                except SourceError as e:
                    if "cancelled" in str(e).lower():
                        wx.CallAfter(self._log, t("download.cancelled_log"))
                        wx.CallAfter(self._close_download_progress)
                        wx.CallAfter(self._processing_done)
                        loop.close()
                        return
                    raise

                def vstatus(phase: str) -> None:
                    wx.CallAfter(self._video_status_tick, phase)

                def vprogress(pct: float) -> None:
                    wx.CallAfter(self._video_upload_tick, pct)

                def vpart(part: int, total: int) -> None:
                    wx.CallAfter(self._video_part_tick, part, total)

                def vsplit(pct: float) -> None:
                    wx.CallAfter(self._video_split_tick, pct)

                # v1.6.1: say what this will cost BEFORE spending it. A
                # run died mid-way with "HTTP 402: requires at least
                # $1.00 in balance for video" — and the price was never
                # the problem (a 2-hour film is about $0.10); the
                # balance floor was. Best effort: a failed check must
                # not stop a job the user could well afford.
                try:
                    from ..core.ai_engine import estimate_video_cost

                    prov_name = self.settings.get("ai.default_provider", "")
                    prov_cfg = self.settings.get_ai_provider(prov_name) or {}
                    est = loop.run_until_complete(estimate_video_cost(
                        getattr(info, "duration", 0.0) if info else 0.0,
                        prov_cfg.get("model", ""),
                        int(self.settings.get("general.chunk_seconds", 600) or 600),
                        prov_cfg.get("api_key", "")))
                    if est.get("priced"):
                        wx.CallAfter(self._log, t(
                            "cost.estimate", usd=f"{est['usd']:.3f}",
                            parts=est["parts"]))
                    if "remaining" in est:
                        wx.CallAfter(self._log, t(
                            "cost.balance", usd=f"{est['remaining']:.2f}"))
                    if est.get("min_balance_ok") is False:
                        wx.CallAfter(self._log, t("cost.too_low"))
                except Exception as e:
                    logger.debug("Cost estimate skipped: %s", e)

                # v1.6.1: fetch what is SAID before describing. The
                # default provider cannot hear the video at all (GLM,
                # probed: "NO AUDIO ACCESS"), so without this the model
                # is guessing at anything the soundtrack carries. Best
                # effort only — no transcript simply means no extra
                # context, never a failed run.
                transcript = []
                try:
                    wx.CallAfter(self._video_status_tick, "transcript")
                    # local_path lets a URL with no published captions
                    # fall back to transcribing the file just downloaded.
                    transcript = loop.run_until_complete(
                        vp.get_transcript(source, local_path=resolved))
                    if transcript:
                        wx.CallAfter(
                            self._log,
                            t("process.transcript_ok", count=len(transcript)))
                    else:
                        wx.CallAfter(self._log, t("process.transcript_none"))
                except Exception as e:
                    logger.warning("Transcript step failed: %s", e)

                try:
                    pairs = loop.run_until_complete(
                        self.ai_engine.describe_video_full(
                            resolved, prompt,
                            transcript=transcript,
                            preserve_resolution=bool(self.settings.get(
                                "general.preserve_resolution", False)),
                            on_status=vstatus, on_upload_progress=vprogress,
                            on_part=vpart, on_split_progress=vsplit,
                            chunk_seconds=int(self.settings.get(
                                "general.chunk_seconds", 600) or 600),
                            is_cancelled=lambda: bool(
                                getattr(self, "_dl_cancelled", False)),
                        )
                    )
                except Exception as e:
                    if "cancel" in str(e).lower():
                        wx.CallAfter(self._log, t("download.cancelled_log"))
                        wx.CallAfter(self._close_download_progress)
                        if loop is not None and not loop.is_closed():
                            loop.close()
                        wx.CallAfter(self._processing_done)
                        return
                    if "mm_file" in str(e):
                        wx.CallAfter(
                            self._log, t("video.mm_file_error",
                                         msg=str(e)[:300]))
                        raise
                    raise
                wx.CallAfter(self._log, t("video.parsed_count", count=len(pairs)))
                # v1.6.8: a cue lasts as long as its text takes to
                # say, not a flat 3 seconds. Anything still landing
                # on the dialogue is named in the log.
                desc_objects, _clashes = self._time_cues_by_length(
                    pairs, transcript)
                self._report_cue_collisions(_clashes, len(pairs))
                if not self.project_store.current:
                    name = self._project_display_name(source)
                    self.project_store.create_project(name, source)
                self.project_store.set_video_duration(info.duration)
                # v1.3.0: keep the actual video file so the player can
                # replay it after the temp dir is gone (YouTube).
                if self._pending_local_video:
                    self.project_store.persist_video_file(
                        self._pending_local_video)
                    self._pending_local_video = ""
                self._save_descriptions_and_finish(
                    desc_objects, loop, None)
                return

            # ── Fast one-shot mode (GLM burn-in + ALL frames in ONE
            # request): ai.fast_mode AND provider == glm. Frames carry a
            # burned-in H:MM:SS stamp so ONE AI request covers them all
            # (auto-batched at 150 images/request when needed); returned
            # event lines are snapped onto the known extraction grid, so
            # timestamps stay exact even if the model misreads a stamp.
            fast_mode = (
                bool(self.settings.get("ai.fast_mode", False))
                and self.settings.get("ai.default_provider", "") == "glm"
            )
            if fast_mode:
                stop_counter.set()  # this branch runs its own counter
                wx.CallAfter(self.SetStatusText, t("video.fast_extracting"))
                from ..core.ai_engine import build_fast_batch_filter
                import re as _re
                import subprocess as _subprocess
                try:
                    resolved = loop.run_until_complete(vp.resolve_source(
                        source, on_progress=download_progress,
                        is_cancelled=lambda: bool(
                            getattr(self, "_dl_cancelled", False)),
                        out_dir=download_dir)
                    )
                    self._pending_local_video = resolved
                except SourceError as e:
                    if "cancelled" in str(e).lower():
                        wx.CallAfter(self._log, t("download.cancelled_log"))
                        wx.CallAfter(self._close_download_progress)
                        wx.CallAfter(self._processing_done)
                        loop.close()
                        return
                    raise

                fast_fps = int(self.settings.get("general.frame_rate", 1) or 1)
                pattern = str(Path(frame_dir) / "frame_%05d.jpg")
                cmd = [
                    vp.ffmpeg, "-hide_banner", "-nostdin",
                    "-i", resolved,
                    "-vf", build_fast_batch_filter(fast_fps),
                    "-q:v", "3", "-y", pattern,
                ]
                # Blocking run on the worker thread; cancellation is
                # checked after (extraction of a normal video takes
                # seconds; the dialog stays alive via Pulse text).
                wx.CallAfter(self._download_progress_tick_text,
                             t("video.fast_extracting"), -1)
                try:
                    ff = _subprocess.run(cmd, capture_output=True,
                                         timeout=900)
                except Exception as e:
                    wx.CallAfter(self._log, f"ERROR: ffmpeg failed: {e}")
                    wx.CallAfter(self._close_download_progress)
                    wx.CallAfter(self._processing_done)
                    self._cleanup_dir(frame_dir)
                    frame_dir = None
                    loop.close()
                    return
                if ff.returncode != 0:
                    tail = ff.stderr.decode("utf-8", "replace")[-500:]
                    wx.CallAfter(self._log,
                                 f"ERROR: ffmpeg failed: {tail}")
                    wx.CallAfter(self._close_download_progress)
                    wx.CallAfter(self._processing_done)
                    self._cleanup_dir(frame_dir)
                    frame_dir = None
                    loop.close()
                    return
                if bool(getattr(self, "_dl_cancelled", False)):
                    wx.CallAfter(self._log, t("download.cancelled_log"))
                    wx.CallAfter(self._close_download_progress)
                    wx.CallAfter(self._processing_done)
                    self._cleanup_dir(frame_dir)
                    frame_dir = None
                    loop.close()
                    return

                fast_frames = sorted(
                    Path(frame_dir).glob("frame_*.jpg"),
                    key=lambda p: int(_re.search(
                        r"(\d+)\.jpg$", p.name).group(1))
                    if _re.search(r"(\d+)\.jpg$", p.name) else 0)
                if not fast_frames:
                    wx.CallAfter(self._log, "ERROR: " + t("error.no_frames"))
                    wx.CallAfter(self._close_download_progress)
                    wx.CallAfter(self._processing_done)
                    self._cleanup_dir(frame_dir)
                    frame_dir = None
                    loop.close()
                    return

                # expected_times[i] = i / fast_fps (fps filter emits its
                # i-th output frame at exactly i/fps seconds)
                expected_times = [i / fast_fps
                                  for i in range(len(fast_frames))]
                n_batches = max(
                    1, -(-len(fast_frames) // 150))  # ceil division
                wx.CallAfter(self._log, t(
                    "video.fast_mode_enabled_log",
                    count=len(fast_frames), batches=n_batches))
                wx.CallAfter(self._download_progress_tick_text,
                             t("video.fast_encoding",
                               count=len(fast_frames)), -1)
                frame_paths_fast = [str(p) for p in fast_frames]

                def fast_status(phase: str) -> None:
                    if phase == "describing":
                        wx.CallAfter(self._download_progress_tick_text,
                                     t("video.fast_batches",
                                       count=len(frame_paths_fast),
                                       batches=n_batches), -1)
                        wx.CallAfter(self.SetStatusText,
                                     t("status.analyzing"))

                try:
                    pairs = loop.run_until_complete(
                        self.ai_engine.describe_video_frames_batch(
                            frame_paths_fast, prompt,
                            expected_times=expected_times,
                            on_status=fast_status,
                            is_cancelled=lambda: bool(
                                getattr(self, "_dl_cancelled", False)),
                        )
                    )
                except Exception as e:
                    if "cancel" in str(e).lower():
                        wx.CallAfter(self._log, t("download.cancelled_log"))
                        wx.CallAfter(self._close_download_progress)
                        if loop is not None and not loop.is_closed():
                            loop.close()
                        wx.CallAfter(self._processing_done)
                        return
                    raise
                wx.CallAfter(self._log, t("video.parsed_count",
                                          count=len(pairs)))
                # v1.6.8: a cue lasts as long as its text takes to
                # say, not a flat 3 seconds. Anything still landing
                # on the dialogue is named in the log.
                desc_objects, _clashes = self._time_cues_by_length(
                    pairs, transcript)
                self._report_cue_collisions(_clashes, len(pairs))
                if not self.project_store.current:
                    video_name = (self._project_display_name(source)
                                  if not Path(source).exists()
                                  else Path(source).stem)
                    self.project_store.create_project(video_name, source)
                self.project_store.set_video_duration(info.duration)
                # v1.3.0: keep the actual video file so the player can
                # replay it after the temp dir is gone (YouTube).
                if self._pending_local_video:
                    self.project_store.persist_video_file(
                        self._pending_local_video)
                    self._pending_local_video = ""
                self._save_descriptions_and_finish(
                    desc_objects, loop, frame_dir)
                return

            cancelled = False
            try:
                fps = int(self.settings.get("general.frame_rate", 5) or 5)
                frames = loop.run_until_complete(
                    vp.extract_frames(source, fps=fps, output_dir=frame_dir,
                                      on_progress=download_progress,
                                      is_cancelled=lambda: bool(getattr(self, "_dl_cancelled", False)),
                                      download_dir=download_dir)
                )
            except SourceError as e:
                if "cancelled" in str(e).lower():
                    cancelled = True
                    frames = []
                else:
                    raise
            finally:
                stop_counter.set()
            if cancelled:
                wx.CallAfter(self._log, t("download.cancelled_log"))
                wx.CallAfter(self._close_download_progress)
                wx.CallAfter(self.SetStatusText, t("status.ready"))
                wx.CallAfter(self._processing_done)
                self._cleanup_dir(frame_dir)
                frame_dir = None
                loop.close()
                return
            wx.CallAfter(self._log, t("main.log_frames",
                                      count=len(frames), fps=fps))
            # Announce the completed download phase explicitly so screen
            # reader users know the fetch finished and what comes next.
            wx.CallAfter(self._ensure_download_progress)
            wx.CallAfter(self._download_progress_tick_text,
                         t("download.download_done"), -1)

            # OPT-IN FRAME CAP (30 Aug): an optional user setting limits how
            # many extracted frames are sent for AI analysis, keeping long
            # videos affordable (17 min at 5 fps would otherwise mean ~5000
            # API calls). Default 0 = NO limit (behaviour unchanged). The
            # analysis still covers the WHOLE video: AI requests and the
            # player timeline keep full-video timestamps, so descriptions
            # stay synced with playback.
            cap = int(self.settings.get("general.frame_cap", 0) or 0)
            total_extracted = len(frames)
            if cap > 0 and total_extracted > cap:
                # v1.6.3: sample EVENLY across the video. This used to be
                # frames[:cap], which kept the first N and dropped the
                # rest — so a cap of 30 on a ten-minute video described
                # the opening two minutes and left the other eight
                # silent. A listener has no way to tell that from a film
                # that simply stopped having anything to describe.
                step = total_extracted / float(cap)
                frames = [frames[min(total_extracted - 1, int(i * step))]
                          for i in range(cap)]
                wx.CallAfter(self._log, t("process.frame_capped", cap=cap, total=total_extracted))

            if not frames:
                wx.CallAfter(self._log, t("main.log_no_frames"))
                wx.CallAfter(self._close_download_progress)
                wx.CallAfter(self._processing_done)
                self._cleanup_dir(frame_dir)
                frame_dir = None
                loop.close()
                return

            # Step 3: Describe frames. The same dialog now shows real
            # per-frame AI progress (done/total); Cancel aborts the AI loop
            # between frames and keeps whatever is already done.
            wx.CallAfter(self.SetStatusText, t("status.analyzing"))
            self._ai_cancelled = False
            frame_paths = [f.path for f in frames]

            def ai_progress(done: int, tot: int) -> None:
                _ui_now(self._ai_progress_tick, done, tot)

            descriptions = loop.run_until_complete(
                self.ai_engine.describe_frames(
                    frame_paths, prompt,
                    on_progress=ai_progress,
                    is_cancelled=lambda: bool(
                        getattr(self, "_ai_cancelled", False)
                        or getattr(self, "_dl_cancelled", False)
                    ),
                )
            )

            # Step 4: Save
            wx.CallAfter(self.SetStatusText, t("status.generating_descriptions"))

            if not self.project_store.current:
                video_name = (self._project_display_name(source)
                              if not Path(source).exists()
                              else Path(source).stem)
                self.project_store.create_project(video_name, source)

            # Persist video duration for the player timeline
            self.project_store.set_video_duration(info.duration)
            # v1.3.0: keep the actual video file so the player can
            # replay it after the temp dir is gone (YouTube).
            if self._pending_local_video:
                self.project_store.persist_video_file(
                    self._pending_local_video)
                self._pending_local_video = ""

            # FIX (30 Aug): copy each used frame from the temp dir into the
            # project folder BEFORE saving, so the player survives the temp
            # cleanup below and frames are never deleted before use.
            frames_dir = Path(self.project_store.projects_dir) / f"project_{self.project_store.current.id}" / "frames"
            frames_dir.mkdir(parents=True, exist_ok=True)
            desc_objects = []
            for i, (frame, text) in enumerate(zip(frames, descriptions)):
                if not text or text.startswith("(error:") or text == "(cancelled)":
                    continue
                perm = frames_dir / Path(frame.path).name
                try:
                    if not perm.exists():
                        shutil.copy2(frame.path, perm)
                except Exception as e:
                    logger.warning("Frame copy failed (%s): %s", frame.path, e)
                    continue
                desc_objects.append(type("Obj", (), {
                    "id": 0,
                    "start_time": frame.timestamp,
                    "end_time": frame.timestamp + 1.0,
                    "text": text,
                    "edited": False,
                    "created_at": "",
                    "frame_path": str(perm),
                })())

            # FIX (1 Sep): zero usable descriptions used to be saved
            # silently, producing "Opened: <url> (0 descriptions)" with no
            # explanation. Now surface a clear failure notice instead of
            # an empty project, and clean up like the error paths do.
            if not desc_objects:
                wx.CallAfter(self._log, "ERROR: " + t("error.ai_empty"))
                wx.CallAfter(self.SetStatusText,
                             t("status.error", error=t("error.ai_empty")))
                wx.CallAfter(self._close_download_progress)

                def _notify_empty() -> None:
                    # A modal MessageBox blocks until dismissed, which hung
                    # an automated run that pumps the wx event loop (16 min
                    # stuck in test_fixes9). Show the modal only when the
                    # frame is actually on screen; headless runs get the
                    # same information via the log + status bar lines.
                    if self.IsShown():
                        wx.MessageBox(t("process.no_descriptions"),
                                      t("process.failed_title"),
                                      wx.OK | wx.ICON_ERROR)

                wx.CallAfter(_notify_empty)
                self._cleanup_dir(frame_dir)
                frame_dir = None
                if loop is not None and not loop.is_closed():
                    loop.close()
                wx.CallAfter(self._processing_done)
                return

            wx.CallAfter(self._ensure_download_progress)
            wx.CallAfter(self._download_progress_tick_text, t("download.saving"), -1)
            self.project_store.save_descriptions(desc_objects)
            self._write_project_srt()
            video_path = self._video_saved_path()
            wx.CallAfter(self._log, t("main.log_generated",
                                      count=len(desc_objects)))
            wx.CallAfter(self._log, t("status.processing_complete",
                                      count=len(desc_objects)))
            if video_path:
                wx.CallAfter(self._log, t("log.video_saved_at", path=video_path))

            def _notify_done(count: int, vpath: str) -> None:
                # Same guard as _notify_empty: modal only for visible
                # frames (real users), log/status only for headless runs.
                if self.IsShown():
                    key = ("process.complete_with_video" if vpath
                           else "status.processing_complete")
                    wx.MessageBox(t(key, count=count, path=vpath),
                                  t("process.complete_title"),
                                  wx.OK | wx.ICON_INFORMATION)

            wx.CallAfter(_notify_done, len(desc_objects), video_path)
            if getattr(self, "_ai_cancelled", False):
                wx.CallAfter(self._log, "AI analysis cancelled; partial descriptions saved")
            wx.CallAfter(self._close_download_progress)
            wx.CallAfter(self.SetStatusText, t("status.complete"))

            # Temp frames are no longer needed: used frames were copied.
            self._cleanup_dir(frame_dir)
            frame_dir = None
            loop.close()

        except SourceError as e:
            logger.error("Source resolution failed: %s", e)
            msg = str(e)
            wx.CallAfter(self._log, f"ERROR: {msg}")
            wx.CallAfter(self.SetStatusText, t("status.error", error=msg))
            wx.CallAfter(self._close_download_progress)
            wx.CallAfter(self._processing_done)
            if frame_dir:
                self._cleanup_dir(frame_dir)
            # LEAK FIX (30 Aug): close the proactor loop on the error path
            # too. Measured: without this, 40 failing runs retained ~3x more
            # OS handles (21 vs 7) than the control path that closes the
            # loop (IOCP + self-dial socket released only via GC).
            if loop is not None and not loop.is_closed():
                loop.close()
            return
        except Exception as e:
            logger.error("Processing error: %s", e)
            wx.CallAfter(self._log, f"ERROR: {e}")
            wx.CallAfter(self.SetStatusText, t("status.error", error=str(e)))
            wx.CallAfter(self._close_download_progress)
            if frame_dir:
                self._cleanup_dir(frame_dir)
            if loop is not None and not loop.is_closed():
                loop.close()
        finally:
            # Every return above (cancel, empty result, error, success)
            # passes through here, so the counter thread always dies with
            # the pipeline instead of outliving it.
            if stop_counter is not None:
                stop_counter.set()

        wx.CallAfter(self._processing_done)

    def _ensure_download_progress(self):
        """Create the download progress dialog on first progress event.

        Runs on the UI thread (via wx.CallAfter). Lazily created so local
        files never flash an empty dialog.

        v1.5.1: once cancelled/done (_dl_done), this is a NO-OP so late
        worker callbacks can never re-create a ghost dialog after the
        user pressed Cancel.
        """
        if getattr(self, "_dl_done", False):
            return
        if self._dl_dialog is not None or self.IsBeingDeleted():
            return
        try:
            # v1.5.5 GHOST DIALOG FIX: wx.ProgressDialog pumps the event
            # loop while it shows the window, so queued CallAfter
            # handlers run INSIDE this constructor. When the pipeline
            # finished meanwhile, _close_download_progress ran here, saw
            # _dl_dialog still None (it is only assigned below) and
            # closed nothing — leaving a progress dialog nobody owns,
            # which keeps the main window disabled and makes the app look
            # frozen. Comparing the close counter across the constructor
            # detects exactly that and discards the newborn dialog.
            gen = getattr(self, "_dl_close_gen", 0)
            dlg = wx.ProgressDialog(
                t("download.dialog_title"),
                t("download.preparing"),
                maximum=100,
                parent=self,
                style=wx.PD_CAN_ABORT | wx.PD_SMOOTH | wx.PD_AUTO_HIDE,
            )
            if (getattr(self, "_dl_close_gen", 0) != gen
                    or getattr(self, "_dl_done", False)):
                dlg.Destroy()
                self._dl_dialog = None
                return
            dlg.SetSize((460, 150))
            self._dl_dialog = dlg
        except Exception:
            logger.debug("ProgressDialog creation failed", exc_info=True)
            self._dl_dialog = None

    def _download_progress_tick(self, p):
        """Update the progress dialog from a DownloadProgress (UI thread)."""
        if getattr(self, "_dl_done", False):
            return
        dlg = self._dl_dialog
        if dlg is None:
            return
        # Real progress is flowing: record the time so the 1s heartbeat
        # tick stands down (it resumes pulsing only in silent phases).
        try:
            self._last_progress_at = time.monotonic()
        except Exception:
            pass
        line = self._format_progress(p)
        if p.percent < 0:
            # Unknown percentage: pulse the bar, show the text
            ok = dlg.Pulse(line)[0]
        else:
            # Cap at 99: Update(100) auto-hides a PD_AUTO_HIDE dialog while
            # later phases (frame extraction, AI pass) still need it.
            ok = dlg.Update(min(int(p.percent), 99), line)[0]
            # Live percentage in the title: screen readers announce it
            # and cross-process tools can read a window title.
            try:
                dlg.SetTitle(f"{t('download.dialog_title')} - "
                             f"{min(int(p.percent), 100)}%")
            except Exception:
                pass
        if not ok:
            # User pressed Cancel
            self._dl_cancelled = True
            self._dl_done = True
            self._hb_stop()
            dlg.Update(0, t("download.cancelling"))
            self._close_download_progress()

    def _frame_count_tick(self, count: int):
        """Show extraction progress in the dialog (UI thread)."""
        if getattr(self, "_dl_done", False):
            return
        dlg = self._dl_dialog
        if dlg is None:
            return
        line = t("download.extract_progress", count=count)
        ok = dlg.Pulse(line)[0]
        if not ok:
            self._dl_cancelled = True
            self._dl_done = True
            self._hb_stop()
            dlg.Update(0, t("download.cancelling"))
            self._close_download_progress()

    def _ai_progress_tick(self, done: int, total: int):
        """Show real per-frame AI progress in the dialog (UI thread)."""
        if getattr(self, "_dl_done", False):
            return
        dlg = self._dl_dialog
        if dlg is None:
            return
        line = t("download.analyzing", done=done, total=total)
        pct = int(done * 100 / total) if total else 0
        ok = dlg.Update(pct, line)[0]
        if not ok:
            self._ai_cancelled = True
            dlg.Update(pct, t("download.cancel_analysis"))
            self._close_download_progress()

    def _set_dialog_phase_title(self, phase_line: str, pct: int | None = None) -> None:
        """Put the CURRENT phase in the dialog title.

        The title is what a screen reader announces when the dialog
        takes focus, and what Win32 tools can read. It used to be
        "Downloading video - N%" for every phase of the run, frozen at
        the download's last percentage — so a user ten minutes into an
        AI upload was told the download was finished at 100%.
        """
        dlg = self._dl_dialog
        if dlg is None:
            return
        text = phase_line.rstrip(". ")
        if pct is not None:
            text = f"{text} - {pct}%"
        try:
            dlg.SetTitle(text)
        except Exception:
            logger.debug("dialog title update failed", exc_info=True)

    def _video_status_tick(self, phase: str):
        """Full-video mode: announce the current phase (UI thread).

        The dialog text and status bar change together so screen readers
        pick the new phase up as it happens.
        """
        dlg = self._dl_dialog
        phase_keys = {
            "transcript": "video.phase_transcript",
            "uploading": "video.phase_uploading",
            "compressing": "video.phase_compressing",
            "splitting": "video.phase_splitting",
            "processing": "video.phase_processing",
            "describing": "video.phase_describing",
        }
        line = t(phase_keys.get(phase, "video.phase_processing"))
        # v1.6.4: three things had to change together here.
        #
        # The heartbeat now learns the new phase, so its once-a-second
        # pulse repeats THIS phase instead of "Loading video info..."
        # forever. Without that, the line below was overwritten 1.5
        # seconds later and the truth was visible only in that window.
        self._hb_set_phase(line)
        # The title carried the word "Downloading" and the download's
        # final percentage for the whole job. Phases that are not a
        # download now say so, and drop the stale percentage.
        self._set_dialog_phase_title(line)
        if dlg is not None:
            dlg.Pulse(line)
        self.SetStatusText(line)

    def _video_upload_tick(self, pct: float):
        """Full-video mode: upload progress percentage (UI thread).

        Clamped to 99: Update(100) would auto-hide the dialog
        (PD_AUTO_HIDE) while the AI is still describing the video.
        """
        dlg = self._dl_dialog
        line = t("video.uploading_progress", pct=int(pct))
        # v1.6.4: real progress is arriving, so the heartbeat must stand
        # down — otherwise it overwrites this line a second and a half
        # later with whatever phase it last knew about. Only the
        # download tick used to record this, which is why every AI phase
        # was eventually covered over.
        self._last_progress_at = time.monotonic()
        self._set_dialog_phase_title(t("video.phase_uploading"), int(pct))
        if dlg is not None:
            dlg.Update(min(99, int(pct)), line)
        self.SetStatusText(line)

    def _video_split_tick(self, pct: float):
        """v1.4.1: real split/describe progress for chunked videos (UI)."""
        dlg = self._dl_dialog
        line = t("video.split_progress", pct=int(pct))
        if dlg is not None:
            try:
                dlg.Update(min(99, max(1, int(pct))), line)
                # Live percentage in the title (screen readers + Win32).
                dlg.SetTitle(f"{t('download.dialog_title')} - "
                             f"{int(pct)}%")
            except Exception:
                logger.debug("split tick dialog update failed", exc_info=True)
        self.SetStatusText(line)

    def _video_part_tick(self, part: int, total: int):
        """v1.4.1: part counter + OVERALL percentage for chunked videos.

        part_progress callback (ai_engine) already computed the overall
        percent; the dialog bar MOVES here instead of pulsing, and the
        same line is written to the status log for E2E verification.
        """
        pct = 10.0 + 90.0 * part / max(1, total)
        dlg = self._dl_dialog
        line = t("video.part_progress", part=part, total=total, pct=int(pct))
        if dlg is not None:
            try:
                # 99 cap: Update(100) auto-hides the dialog while the
                # "Saving project" phase is still running; the dialog
                # is closed properly by _close_download_progress.
                dlg.Update(min(99, max(1, int(pct))), line)
                # Live percentage in the title (screen readers + Win32).
                dlg.SetTitle(f"{t('download.dialog_title')} - "
                             f"{int(pct)}%")
            except Exception:
                logger.debug("part tick dialog update failed", exc_info=True)
        self.SetStatusText(line)
        self._log(line)

    def _write_project_srt(self) -> None:
        """v1.3.0: write descriptions.srt into the project media folder
        so the player auto-loads subtitles. Best-effort, never raises.
        """
        try:
            cur = self.project_store.current
            if not cur or not cur.descriptions:
                return
            from ..core.timeline_io import to_srt
            srt_path = self.project_store.media_dir(cur.id) / "descriptions.srt"
            srt_path.write_text(to_srt(cur.descriptions), encoding="utf-8")
            logger.info("Project SRT written: %s", srt_path)
        except Exception as e:
            logger.warning("Project SRT write failed: %s", e)

    def _video_saved_path(self) -> str:
        """v1.5.1: permanent video path for the completion message.

        The persisted media video if present, else the local source.
        Empty for remote sources whose download was not persisted.
        """
        cur = self.project_store.current
        if cur and cur.video_path and Path(cur.video_path).exists() \
                and cur.video_path.startswith(str(self.project_store.projects_dir)):
            return cur.video_path
        source = self._current_source
        if source and not source.startswith(("http://", "https://")) \
                and Path(source).exists():
            return str(Path(source).resolve())
        return ""

    def _save_descriptions_and_finish(self, desc_objects, loop, frame_dir):
        """Shared save + notify path for both processing modes.

        Runs on the worker thread; every UI touch goes through wx.CallAfter.
        Mirrors the main path: modal guarded by IsShown() so headless runs
        never hang.
        """
        if not desc_objects:
            wx.CallAfter(self._log, "ERROR: " + t("error.ai_empty"))
            wx.CallAfter(self.SetStatusText,
                         t("status.error", error=t("error.ai_empty")))
            wx.CallAfter(self._close_download_progress)

            def _notify_empty() -> None:
                if self.IsShown():
                    wx.MessageBox(t("process.no_descriptions"),
                                  t("process.failed_title"),
                                  wx.OK | wx.ICON_ERROR)

            wx.CallAfter(_notify_empty)
            if frame_dir:
                self._cleanup_dir(frame_dir)
            if loop is not None and not loop.is_closed():
                loop.close()
            wx.CallAfter(self._processing_done)
            return

        wx.CallAfter(self._ensure_download_progress)
        wx.CallAfter(self._download_progress_tick_text, t("download.saving"), -1)
        self.project_store.save_descriptions(desc_objects)
        self._write_project_srt()
        video_path = self._video_saved_path()
        wx.CallAfter(self._log, t("main.log_generated",
                                  count=len(desc_objects)))
        wx.CallAfter(self._log, t("status.processing_complete",
                                  count=len(desc_objects)))
        if video_path:
            wx.CallAfter(self._log, t("log.video_saved_at", path=video_path))

        def _notify_done(count: int, vpath: str) -> None:
            if self.IsShown():
                key = ("process.complete_with_video" if vpath
                       else "status.processing_complete")
                wx.MessageBox(t(key, count=count, path=vpath),
                              t("process.complete_title"),
                              wx.OK | wx.ICON_INFORMATION)

        wx.CallAfter(_notify_done, len(desc_objects), video_path)
        wx.CallAfter(self._close_download_progress)
        wx.CallAfter(self.SetStatusText, t("status.complete"))
        if frame_dir:
            self._cleanup_dir(frame_dir)
        if loop is not None and not loop.is_closed():
            loop.close()
        wx.CallAfter(self._processing_done)

    def _download_progress_tick_text(self, text: str, percent: int):
        """Show an arbitrary phase text in the dialog (UI thread)."""
        dlg = self._dl_dialog
        if dlg is None:
            return
        if percent < 0:
            dlg.Pulse(text)
        else:
            dlg.Update(percent, text)

    def _format_progress(self, p) -> str:
        """Format one progress line: percent, MB of MB, speed, ETA."""
        if p.phase == "merge":
            return t("download.merging")
        if p.phase == "audio":
            label = t("download.audio")
        elif p.phase == "video":
            label = t("download.video")
        else:
            label = t("download.preparing")
        if p.percent < 0:
            return label
        if p.total_mb >= 0 and p.downloaded_mb >= 0:
            body = f"{p.percent:.1f}% ({p.downloaded_mb:.1f}/{p.total_mb:.1f} MB"
        else:
            body = f"{p.percent:.1f}%"
        if p.speed:
            body += f", {p.speed}"
        if p.eta:
            body += f", ETA {p.eta}"
        return f"{label}: {body})" if "MB" in body else f"{label}: {body}"

    def _close_download_progress(self):
        """Close and destroy the progress dialog if it exists (UI thread)."""
        self._hb_stop()
        # Bumped even when there is nothing to close: a dialog may be
        # mid-construction right now (see _ensure_download_progress).
        self._dl_close_gen = getattr(self, "_dl_close_gen", 0) + 1
        dlg, self._dl_dialog = self._dl_dialog, None
        if dlg is not None:
            try:
                dlg.Destroy()
            except Exception:
                pass
            self.Refresh()

    def _processing_done(self):
        """Reset UI after processing and open PlayerWindow.

        v1.5.1: after a user CANCEL this must NOT re-open the player or
        flip the status bar (the old code auto-opened the player on the
        partial/empty state left behind by cancellation).
        """
        self._hb_stop()
        self._processing = False
        # v1.6.7: the project is created before the download now, so an
        # abandoned run would otherwise leave an empty one behind. One
        # that holds a partial download is kept — that is the resume.
        self._discard_project_if_empty()
        self.btn_preset_open.Enable()
        self.btn_local.Enable()
        self.btn_play_existing.Enable()
        self.btn_url.Enable()
        self.btn_youtube.Enable()
        if self._dl_cancelled or self._dl_done:
            # v1.5.1: after cancel, never auto-open the player on the
            # partial/empty state left behind by cancellation.
            self.SetStatusText(t("status.ready"))
            return

        # Auto-open PlayerWindow if descriptions were generated
        if self.project_store.current and self.project_store.current.descriptions:
            self._log(t("main.log_opening_player"))
            wx.CallAfter(self._open_player)

    @staticmethod
    def _cleanup_dir(path: str):
        """Best-effort removal of a temporary directory tree."""
        import shutil
        try:
            shutil.rmtree(path, ignore_errors=True)
        except Exception as e:
            logger.debug("Cleanup failed for %s: %s", path, e)

    # ── Helpers ───────────────────────────────────────────────────

    def _load_settings(self):
        """Load current settings into UI."""
        self._refresh_prompt_list()

    def _refresh_prompt_list(self):
        """Refresh prompt preset dropdown."""
        names = self.prompt_mgr.get_preset_names()
        current = self.prompt_choice.GetStringSelection()
        self.prompt_choice.SetItems(names)
        if not names:
            return
        if current and current in names:
            # Keep the user's current selection (and prompt text) when
            # the preset still exists after the refresh.
            self.prompt_choice.SetStringSelection(current)
            # v1.5.6: the FIRST call happens inside _build_ui, before
            # custom_prompt exists, so _preview_preset silently skipped
            # the box; the second call (from _load_settings) took this
            # branch and never retried. The prompt box therefore stayed
            # empty of the preset the combo claimed was selected.
            box = getattr(self, "custom_prompt", None)
            if box is not None and not box.GetValue().strip():
                self._preview_preset(current)
            return
        if names:
            self.prompt_choice.SetSelection(0)
            self._preview_preset(names[0])

    def _open_player(self):
        """Open the described video player window."""
        from .player_window import PlayerWindow
        try:
            win = PlayerWindow(self, self.project_store, self.tts_engine, self.ai_engine)
            win.Show()
        except Exception as e:
            logger.error("Failed to open PlayerWindow: %s", e)
            self._log("ERROR opening player: " + str(e))

    def _log(self, message: str):
        """Append a line to the status log.

        v1.5.1: late wx.CallAfter(self._log, ...) from the worker after
        the frame is destroyed must not crash the app.
        """
        try:
            if self.IsBeingDeleted() or not self.log_text:
                return
        except Exception:
            return
        self.log_text.AppendText(message + "\n")
        self.log_text.ShowPosition(self.log_text.GetLastPosition())
