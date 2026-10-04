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
from .progress_dialog import AccessibleProgressDialog

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
        # v1.9.0: ready before any project is opened (Ask More, agent).
        self.configure_ai()
        # v1.7.6: old "project_48" folders become "Sintel (48)". Never
        # blocks start-up; a project that cannot move is tried next time.
        try:
            self.project_store.migrate_layout()
        except Exception:
            logger.warning("Project layout migration failed", exc_info=True)
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
        # v1.5.1: heartbeat timer; it notices Cancel every second and
        # moves the bar by time while a provider gives no percentage.
        self._hb_timer = None
        self._hb_start = 0.0
        self._hb_phase = ""
        self._hb_dialog_was_destroyed = False
        # v1.5.5: bumped by every _close_download_progress. The
        # ProgressDialog constructor pumps the event loop, so a cleanup
        # can land WHILE a dialog is being built; the counter lets the
        # builder notice and throw the newborn dialog away.
        self._dl_close_gen = 0
        # v1.9.6: ONE overall percentage for the whole job (_advance).
        self._progress_reset()

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
        self._id_check_updates = wx.NewIdRef()
        help_menu.Append(self._id_check_updates, t("menu.check_updates"))
        self._id_language_report = wx.NewIdRef()
        help_menu.Append(self._id_language_report, t("menu.language_report"))
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
            (self._id_check_updates, "menu.check_updates"),
            (self._id_language_report, "menu.language_report"),
            (wx.ID_ABOUT, "menu.about"),
        ):
            item = menubar.FindItemById(item_id)
            if item is not None:
                item.SetItemLabel(t(key))
        # Top-level labels: MenuBar.SetMenuLabel. NOT wx.Menu.SetTitle —
        # on Windows that writes a title INTO the dropdown over its first
        # item. Heard through NVDA in v1.7.7: File opened on "File"
        # instead of "Settings...", and Help on "Help" instead of "Check
        # for Updates...", so neither could be reached from the keyboard.
        # (Phoenix has no SetLabelTop; SetMenuLabel is its name.)
        for idx, key in ((0, "menu.file"), (1, "menu.help")):
            if idx < menubar.GetMenuCount():
                menubar.SetMenuLabel(idx, t(key))

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
        self.Bind(wx.EVT_MENU, self._on_check_updates,
                  id=self._id_check_updates)
        self.Bind(wx.EVT_MENU, self._on_language_report,
                  id=self._id_language_report)
        self.Bind(wx.EVT_CLOSE, self._on_close_window)

    # ── Import / export descriptions ────────────────────────────

    def _on_import_descriptions(self, event):
        """Import SRT/VTT/simple timed text into a new project."""
        from ..core import timeline_io
        dlg = wx.FileDialog(
            self, t("impexp.dlg_import"),
            wildcard=(f"{t('filter.timed_text')}|*.srt;*.vtt;*.txt"
                      f"|{t('filter.all_files')}|*.*"),
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
            wx.MessageBox(t("impexp.import_failed", error=self._local_error_text(e)),
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
            defaultDir=self._export_dir(),
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
            wx.MessageBox(t("impexp.export_failed", error=self._local_error_text(e)),
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
            defaultDir=self._export_dir(),
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
            wx.MessageBox(t("impexp.export_failed", error=self._local_error_text(e)),
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
            defaultDir=self._export_dir(),
            wildcard=(f"{t('filter.mp3')}|*.mp3"
                      f"|{t('filter.wav')}|*.wav"),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()

        self._exporting = True
        maximum = max(1, len(cur.descriptions))
        # v1.9.6: Cancel. Rendering a long film is minutes of TTS and
        # there was no way out but waiting (or killing the app). A real
        # progress bar NVDA reads; app-modal, closed by done_cb below.
        progress = AccessibleProgressDialog(
            t("impexp.exporting_title"), t("impexp.rendering", done=0,
                                           total=len(cur.descriptions)),
            maximum=maximum, parent=self,
        )
        cancel_event = threading.Event()
        # A cancelled export must not leave a half-written file — but the
        # user may have chosen to overwrite an existing one, which is
        # theirs until the export really replaces it.
        out = Path(path)
        try:
            before = out.stat().st_mtime_ns if out.exists() else None
        except OSError:
            before = None

        def remove_partial() -> None:
            try:
                if out.exists() and (before is None
                                     or out.stat().st_mtime_ns != before):
                    out.unlink()
            except OSError as e:
                logger.warning("Could not remove partial export %s: %s",
                               out, e)

        def done_cb(result: dict | None, error: str | None):
            def ui():
                try:
                    progress.Destroy()
                except RuntimeError:
                    pass
                self._exporting = False
                # A Cancel pressed too late to stop a finished export is
                # not a failure: the file is complete, so keep it.
                if error and (cancel_event.is_set() or error == "cancelled"):
                    remove_partial()
                    msg = t("error.cancelled")
                    self._log(msg)
                    self.SetStatusText(msg, 0)
                    return
                if error:
                    logger.error("Audio export failed: %s", error)
                    # export_audio's own messages are already in the app
                    # language; anything else (a file error) is shortened.
                    own = {t("impexp.nothing_to_export"),
                           t("impexp.all_clips_failed")}
                    shown = error if error in own else self._local_error_text(error)
                    wx.MessageBox(t("impexp.export_failed", error=shown),
                                  t("impexp.dlg_export"),
                                  wx.OK | wx.ICON_ERROR, self)
                    return
                msg = t("impexp.audio_done", path=result["path"],
                        rendered=result["rendered"], skipped=result["skipped"])
                self._log(msg)
                self.SetStatusText(msg, 0)
                wx.MessageBox(msg, t("impexp.dlg_export"),
                              wx.OK | wx.ICON_INFORMATION, self)
            self._ui(ui)

        def progress_tick(done: int, total: int) -> None:
            if cancel_event.is_set():
                return
            try:
                res = progress.Update(min(done, maximum),
                                      t("impexp.rendering", done=done,
                                        total=total))
            except RuntimeError:
                return  # dialog already gone
            if not res[0]:
                cancel_event.set()

        def progress_cb(done, total, skipped):
            if cancel_event.is_set():
                # Stops export_audio between cues when it does not take
                # is_cancelled itself (the exception ends its loop).
                raise RuntimeError("cancelled")
            self._ui(progress_tick, done, total)

        import inspect as _inspect
        try:
            takes_cancel = "is_cancelled" in _inspect.signature(
                timeline_io.export_audio).parameters
        except (TypeError, ValueError):
            takes_cancel = False

        def worker():
            try:
                kwargs = {"progress_cb": progress_cb}
                if takes_cancel:
                    kwargs["is_cancelled"] = cancel_event.is_set
                result = timeline_io.export_audio(
                    cur.descriptions, path, self.tts_engine, **kwargs)
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
                t("main.play_existing"),
                wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION)
            # v1.8.6: Cancel (and so Esc, which Windows disables without
            # it) stops here instead of forcing a choice.
            ask.SetYesNoCancelLabels(t("main.play_existing_use_found"),
                                     t("main.play_existing_pick_other"),
                                     t("cancel"))
            answer = ask.ShowModal()
            ask.Destroy()
            if answer == wx.ID_CANCEL:
                return
            use_it = answer == wx.ID_YES
            if not use_it:
                subtitles = None
        if subtitles is None:
            sub_dlg = wx.FileDialog(
                self, t("main.play_existing_pick_subs"),
                defaultDir=str(video.parent),
                wildcard=(f"{t('filter.timed_text')}|*.srt;*.vtt;*.txt"
                          f"|{t('filter.all_files')}|*.*"),
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
            wx.MessageBox(t("impexp.import_failed", error=self._local_error_text(e)),
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
            wx.MessageBox(t("main.play_existing_failed",
                            error=self._local_error_text(e)),
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

            provider = self._provider_name()
            model = (self.settings.get_ai_provider(provider) or {}).get(
                "model", "")
            if not provider_hears_audio(provider, model):
                from .dialogs import ask_yes_no
                if not ask_yes_no(self, t("preset.needs_audio", provider=provider),
                                  t("settings.title"), wx.ICON_WARNING,
                                  default_no=True):
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

    def _provider_name(self) -> str:
        """The provider in use. Empty means the default, which is "glm"
        (OpenRouter) as in the Settings dialog -- not "gemini" (v1.9.6:
        the main window and Settings disagreed, and an empty value
        produced "API key not set for ." when Open was pressed)."""
        return str(self.settings.get("ai.default_provider", "glm")
                   or "glm").strip() or "glm"

    def configure_ai(self) -> bool:
        """Point the AI engine at the provider, key and model in Settings.

        v1.9.0: this happened only when a video was processed, so Ask More,
        Explore Scene (and the Player agent) on a project opened later
        failed with "No AI provider configured". Now it also runs at start
        and after Settings. False when there is no key yet (silent: the
        processing path still warns when it needs one).
        """
        provider = self._provider_name()
        cfg = self.settings.get_ai_provider(provider) or {}
        if not cfg.get("api_key"):
            return False
        try:
            self.ai_engine.set_provider(
                provider, api_key=cfg["api_key"],
                base_url=cfg.get("base_url", ""),
                model=cfg.get("model", ""),
                api_format=cfg.get("api_format", ""))
        except Exception as e:
            logger.warning("AI provider not configured: %s", e)
            return False
        return True

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
        # v1.8.2: an open player follows too (it used to keep the old
        # language until reopened).
        from .player_window import PlayerWindow
        for child in self.GetChildren():
            if isinstance(child, PlayerWindow):
                child.retranslate()
        self._load_settings()
        self.configure_ai()
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

    @staticmethod
    def _project_list_label(p: dict) -> str:
        """One Open Project entry: name, how many descriptions, when.

        v1.7.6: was "<name> (updated: 2026-09-28 11:30:05)". Fourteen
        projects were called "Me at the zoo"; the count and a readable
        date are what tell them apart when NVDA reads the list.
        """
        stamp = (p.get("updated_at") or p.get("created_at") or "").strip()
        when = stamp
        try:
            import datetime as _dt
            when = _dt.datetime.strptime(
                stamp, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
        except ValueError:
            pass
        return t("project.list_item", name=p.get("name") or "",
                 count=p.get("count", 0), date=when)

    def _rename_project_row(self, proj: dict, parent=None) -> bool:
        """Ask for a new name and apply it (name AND folder).

        A method rather than a closure inside the dialog so the handler
        is reachable from tests (pitfall 18).
        """
        old = proj.get("name") or ""
        dlg = wx.TextEntryDialog(parent or self, t("project.rename_prompt"),
                                 t("project.rename_title"), old)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return False
            new = dlg.GetValue().strip()
        finally:
            dlg.Destroy()
        if not new or new == old:
            return False
        if not self.project_store.rename_project(proj["id"], new):
            return False
        self._log(t("project.renamed_log", old=old, name=new))
        return True

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
            self._project_list_label(p) for p in projects],
            style=wx.LB_SINGLE)
        top.Add(lb, 1, wx.ALL | wx.EXPAND, pad)
        btns = wx.BoxSizer(wx.HORIZONTAL)
        open_btn = wx.Button(dlg, wx.ID_OK, t("project.open_btn"))
        open_btn.SetDefault()
        rename_btn = wx.Button(dlg, wx.ID_ANY, t("project.rename_btn"))
        remove_btn = wx.Button(dlg, wx.ID_ANY, t("project.remove_btn"))
        cancel_btn = wx.Button(dlg, wx.ID_CANCEL, t("close"))
        btns.Add(open_btn, 0, wx.ALL, pad)
        btns.Add(rename_btn, 0, wx.ALL, pad)
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
            from .dialogs import ask_yes_no
            confirmed = ask_yes_no(dlg, t("project.remove_confirm", name=name),
                                   t("project.remove_title"), wx.ICON_WARNING,
                                   default_no=True)
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
                lb.Set([self._project_list_label(p) for p in projects])
                lb.SetSelection(0)
            else:
                dlg.EndModal(wx.ID_CANCEL)

        def _on_rename(evt):
            proj = _selected()
            if not proj or not self._rename_project_row(proj, dlg):
                return
            projects[:] = self.project_store.list_projects()
            lb.Set([self._project_list_label(p) for p in projects])
            # Keep the renamed project selected, so NVDA reads its new
            # name straight away instead of jumping to the top.
            for i, p in enumerate(projects):
                if p["id"] == proj["id"]:
                    lb.SetSelection(i)
                    break
            lb.SetFocus()

        remove_btn.Bind(wx.EVT_BUTTON, _on_remove)
        rename_btn.Bind(wx.EVT_BUTTON, _on_rename)
        lb.Bind(wx.EVT_LISTBOX_DCLICK, lambda evt: dlg.EndModal(wx.ID_OK))

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
                    self._after_project_opened(proj)

    def _after_project_opened(self, proj) -> None:
        """v2.0.2 (owner, 5 Oct 2026): "after opening, nothing happens" -
        only a log line. With descriptions the Player opens, as it does
        after describing; a Player still showing another project is
        closed first so two videos never play at once. Without
        descriptions the user is told what to do instead."""
        self._log(t("main.log_opened", name=proj.name,
                    count=len(proj.descriptions)))
        if not proj.descriptions:
            wx.MessageBox(t("project.opened_empty", name=proj.name),
                          t("project.dialog_title"),
                          wx.OK | wx.ICON_WARNING)
            return
        self._close_players()
        self._log(t("main.log_opening_player"))
        wx.CallAfter(self._open_player)

    def _close_players(self) -> None:
        """Close every open Player (each stops its own sound on close)."""
        from .player_window import PlayerWindow
        for child in list(self.GetChildren()):
            if isinstance(child, PlayerWindow):
                try:
                    child.Close(force=True)
                except Exception:
                    logger.debug("Player close failed", exc_info=True)

    def _remove_project_files(self, project_id: int):
        """Delete a project's DB file + media folder. Returns (ok, error)."""
        import shutil as _shutil
        errors = []
        # Either layout: the old one keeps the .db beside the folder, the
        # v1.7.6 one inside it (removed with the folder).
        db_path = self.project_store._db_path(project_id)
        media_root = self.project_store.project_dir(project_id)
        try:
            if media_root.exists():
                _shutil.rmtree(media_root, ignore_errors=False)
        except Exception as e:
            errors.append(self._local_error_text(e))
        try:
            # Keep the .db while its media survives (a file locked by the
            # player): the project stays listed and can be deleted later,
            # instead of leaving an orphan folder behind.
            if db_path.exists() and not errors:
                db_path.unlink()
        except Exception as e:
            errors.append(self._local_error_text(e))
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

    def _on_check_updates(self, event):
        """Help > Check for Updates (v1.7.7): a newer yt-dlp, verified."""
        from .update_dialog import UpdateDialog
        dlg = UpdateDialog(self, self.settings)
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()

    def _on_language_report(self, event):
        """Help > Translation Report (v1.8.0).

        For the language in use, writes <code>.missing.json into the
        user's own locales folder with every line still to translate and
        its English text, says how many, and offers to open the folder.
        A translator never has to diff files by hand after an update.
        """
        import os as _os
        from ..i18n.strings import (I18n, user_locales_dir,
                                    write_missing_report)
        lang = I18n.current_language()
        language = I18n.language_name(lang)
        folder = user_locales_dir()
        folder.mkdir(parents=True, exist_ok=True)
        if lang == "en":
            message = t("i18n.report_english", folder=folder)
        else:
            path, count = write_missing_report(lang)
            self._log(t("i18n.report_log", language=language, count=count,
                        path=path))
            if count:
                message = t("i18n.report_todo", language=language,
                            count=count, path=path, code=lang)
            else:
                try:
                    path.unlink()  # nothing to translate: no empty file
                except OSError:
                    pass
                message = t("i18n.report_complete", language=language,
                            folder=folder)
        from .dialogs import ask_yes_no
        if ask_yes_no(self, message, t("i18n.report_title"),
                      wx.ICON_INFORMATION):
            try:
                _os.startfile(str(folder))
            except OSError as e:
                logger.warning("Could not open %s: %s", folder, e)

    def check_updates_in_background(self) -> None:
        """Once a week, at start-up: say if a newer yt-dlp exists.

        Only announces. Nothing is downloaded without the user choosing
        Update in Help > Check for Updates. Silent on any failure — an
        offline start must not greet the user with an error.
        """
        from ..core import updater
        if not updater.weekly_check_due(self.settings):
            return

        def work():
            try:
                newer = updater.available_update()
                updater.record_check(self.settings)
            except Exception as e:
                logger.info("Weekly update check skipped: %s", e)
                return
            if newer:
                self._ui(self._announce_update, newer)

        import threading as _threading
        _threading.Thread(target=work, daemon=True).start()

    def _announce_update(self, version: str) -> None:
        if not self:
            return
        msg = t("update.weekly_notice", version=version)
        self._log(msg)
        self.SetStatusText(msg)
        try:
            from ..core.speech import announce
            announce(msg)
        except Exception:
            pass

    def _on_about(self, event):
        info = wx.adv.AboutDialogInfo()
        info.SetName("DescriVox Agent")
        from omni_describer_custom import __version__
        info.SetVersion(__version__)
        info.SetDescription(t("about.description") + "\n\n" + t("about.formerly"))
        info.SetCopyright("(C) 2026 DescriVox Agent")
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
            # block process exit. Whatever it posts after Destroy goes
            # through _ui(), which drops calls into a dead frame (v1.9.6:
            # "wrapped C/C++ object of type MainFrame has been deleted").
            self._worker.join(timeout=3.0) if self._worker and self._worker.is_alive() else None
        self._processing = False
        timer = getattr(self, "_announce_timer", None)
        try:
            if timer is not None and timer.IsRunning():
                timer.Stop()
        except Exception:
            pass
        self._close_child_frames()
        self.Destroy()

    def _close_child_frames(self) -> None:
        """Close Player/Editor windows through their own EVT_CLOSE.

        Destroy() on this frame takes its children down WITHOUT their
        close handlers: an open editor lost its unsaved edits and the
        player's ffplay/TTS kept running. Deepest first, so an editor
        (child of the player) saves before its player goes.
        """
        def frames_under(win):
            for child in list(win.GetChildren()):
                if isinstance(child, wx.Frame):
                    yield from frames_under(child)
                    yield child

        for frame in list(frames_under(self)):
            try:
                if frame and not frame.IsBeingDeleted():
                    frame.Close()
            except Exception:
                logger.warning("Closing a child window failed",
                               exc_info=True)

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
        provider = self._provider_name()
        prov_config = self.settings.get_ai_provider(provider)
        if not prov_config.get("api_key"):
            wx.MessageBox(
                t("status.no_api_key", provider=provider),
                t("settings.title"), wx.OK | wx.ICON_WARNING,
            )
            self._on_settings(None)
            return

        self.configure_ai()
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
                    self.SetStatusText(t("main.log_project", name=proj.name))
                    self._after_project_opened(proj)
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
        self._progress_reset()
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

    # ── v1.5.1 heartbeat: Cancel is noticed in silent phases too ──────

    def _hb_start_timer(self, phase: str) -> None:
        """Start the 1s heartbeat timer (UI thread) for a phase."""
        self._hb_phase = phase
        self._hb_start = time.monotonic()
        self._hb_dialog_was_destroyed = False
        if self._hb_timer is None:
            self._hb_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._hb_tick, self._hb_timer)
        self._hb_timer.Start(1000)

    def _hb_set_phase(self, phase: str) -> None:
        """Tell the heartbeat which phase we are actually in now.

        v1.6.4: this was the missing half. _hb_phase was written once, at
        the start, with "Loading video info..." — and never again, so the
        dialog repeated that line for the whole job. _hb_start is reset
        too: it is when THIS phase began.
        """
        if not phase or phase == self._hb_phase:
            return
        self._hb_phase = phase
        self._hb_start = time.monotonic()

    def _hb_stop(self) -> None:
        if self._hb_timer is not None:
            self._hb_timer.Stop()

    def _hb_tick(self, event):
        """1s tick: notice Cancel, and move the bar by time while the
        provider gives no percentage (_begin_timed_wait).

        v1.9.6 (owner, 2 Oct 2026): nothing is spoken and no text is
        written here any more. The bar is the progress (NVDA reads it
        with its own progress bar setting); a changing seconds counter
        was read as just "46s", "47s" (pitfall 93), and a spoken report
        every 30 s was not wanted.
        """
        if not self:
            return
        if self._dl_done or self._dl_cancelled:
            self._hb_stop()
            return
        dlg = self._dl_dialog
        if dlg is None:
            return
        # v1.9.6: Cancel is checked FIRST, every second, for the whole
        # job. Before, a press was noticed only by the few ticks that
        # read Update()'s result, so after the download (or for a local
        # file) Cancel did nothing at all.
        try:
            pressed = (dlg.WasCancelled()
                       if hasattr(dlg, "WasCancelled") else False)
        except Exception:
            pressed = False
        if pressed:
            self._on_dialog_cancel()
            return
        self._timed_wait_tick(time.monotonic())

    # ── v1.9.6: ONE overall percentage for the whole job ──────────────
    #
    # Owner's decision, 2 Oct 2026: a real progress bar with ONE
    # percentage for the WHOLE job, never going backwards. Each stage
    # owns a slice of the bar; every tick reports a fraction (0..1) of its
    # own stage through _advance(), which maps it into the slice.
    #
    #   download     0-15   only when something is downloaded; a local or
    #                       already downloaded file starts at 15
    #   transcript  15-30   full video (Whisper per segment; subtitles or
    #   extract     15-30   the project cache jump to the end); frame
    #                       mode extracts frames here instead
    #   ai          30-95   OpenRouter: its own 0..100 (split, parts,
    #                       upload, estimated wait); Gemini/MiniMax:
    #                       upload = first half, then the silent wait
    #                       moves by time (_begin_timed_wait); frame mode:
    #                       frames done/total; fast mode: by time
    #   review      95-99   the description check, done/total
    #
    # 100 is never shown: _close_download_progress closes the dialog when
    # the job is really done. A stage that is already behind is ignored,
    # so a late tick (a retry, a second stream) can never pull the bar
    # back.
    STAGES = {
        "download": (0, 0.0, 15.0),
        "transcript": (1, 15.0, 30.0),
        "extract": (1, 15.0, 30.0),
        "ai": (2, 30.0, 95.0),
        "review": (3, 95.0, 99.0),
    }
    # A wait with no real percentage stops short of its stage's end
    # (share of the stage); only the real answer moves past it.
    TIMED_WAIT_CEILING = 0.95

    def _progress_reset(self) -> None:
        """A new job: the bar starts again from 0 (UI thread)."""
        self._overall = 0.0
        self._stage_order = -1
        self._stage_name = ""
        self._timed_wait = None
        self._part_text = ""
        self._dlg_text = None
        self._dlg_title = None
        self._title_phase = ""
        self._expected_frames = 0
        self._wait_basis = None

    def _overall_pct(self) -> int:
        return max(0, min(99, int(getattr(self, "_overall", 0.0))))

    def _advance(self, stage: str, fraction: float = 0.0) -> int:
        """Report `fraction` (0..1) of `stage`; returns the overall %.

        Moving to a later stage starts the bar at that stage's beginning;
        an earlier stage, or a lower value, changes nothing.
        """
        order, lo, hi = self.STAGES[stage]
        current = getattr(self, "_stage_order", -1)
        if order < current:
            return self._overall_pct()
        if order > current:
            self._stage_order = order
            self._stage_name = stage
            self._timed_wait = None
        try:
            fraction = max(0.0, min(1.0, float(fraction)))
        except (TypeError, ValueError):
            fraction = 0.0
        value = lo + (hi - lo) * fraction
        if value > getattr(self, "_overall", 0.0):
            self._overall = value
        return self._overall_pct()

    def _stage_fraction(self) -> float:
        """How far the current stage is, 0..1 (for a timed wait's start)."""
        stage = getattr(self, "_stage_name", "")
        if stage not in self.STAGES:
            return 0.0
        _, lo, hi = self.STAGES[stage]
        return max(0.0, min(1.0, (self._overall - lo) / (hi - lo)))

    def _push_dialog(self, text: str | None = None):
        """Show the overall % (bar and title) and, if it CHANGED, the
        text. Returns Update()'s raw (continue, skip), or None when there
        is no dialog or it is gone."""
        dlg = self._dl_dialog
        if dlg is None:
            return None
        pct = self._overall_pct()
        self._set_dialog_phase_title(
            getattr(self, "_title_phase", "") or t("download.dialog_title"))
        try:
            # Pitfall 65: text only when it changes, else the bar alone.
            if text and text != getattr(self, "_dlg_text", None):
                self._dlg_text = text
                return dlg.Update(pct, text)
            return dlg.Update(pct)
        except Exception:
            logger.debug("progress dialog update failed", exc_info=True)
            return None

    def _show_progress(self, text: str | None = None) -> bool:
        """_push_dialog, then react to Cancel. False = cancelled."""
        result = self._push_dialog(text)
        if result is None:
            return True
        return self._dialog_ok(result)

    def _phase_text(self, phase: str, left: str = "") -> str:
        """The dialog text: "Part 2 of 3." + the phase, time left below."""
        line = " ".join(x for x in (getattr(self, "_part_text", ""), phase)
                        if x)
        return f"{line}\n{left}" if left else line

    def _estimate_wait(self, key: str, media_seconds: float) -> float:
        """Seconds a silent AI wait should take (an estimate, never
        shown as finished). Learned per model in core/timing_store when
        this model was measured before; otherwise 60 s plus half a second
        per second of video."""
        from ..core import timing_store
        media = max(0.0, float(media_seconds or 0.0))
        try:
            known = bool(key) and key in timing_store._load()
        except Exception:
            known = False
        if known and media > 0:
            return timing_store.expected_seconds(key, media)
        return 60.0 + 0.5 * media

    def _begin_timed_wait(self, key: str = "", media_seconds: float = 0.0,
                          record: bool = False) -> None:
        """A provider is working and says nothing (Gemini "processing",
        "describing"; MiniMax "describing"; fast mode). From now on the
        heartbeat moves the AI stage by time, easing out toward
        TIMED_WAIT_CEILING (UI thread). Started once per wait."""
        if getattr(self, "_timed_wait", None) is not None:
            return
        self._advance("ai")
        self._timed_wait = {
            "start": time.monotonic(),
            "expected": max(1.0, self._estimate_wait(key, media_seconds)),
            "from": self._stage_fraction(),
            "key": key if record else "",
            "media": media_seconds,
        }

    def _timed_wait_tick(self, now: float) -> None:
        """Heartbeat: one step of a timed wait. 80% of the way at the
        estimate, 96% at twice it, never the stage's end."""
        import math
        wait = getattr(self, "_timed_wait", None)
        if not wait or getattr(self, "_stage_name", "") != "ai":
            return
        waited = max(0.0, now - wait["start"])
        eased = 1.0 - math.exp(-1.6 * waited / wait["expected"])
        frm = min(wait["from"], self.TIMED_WAIT_CEILING)
        self._advance("ai", frm + (self.TIMED_WAIT_CEILING - frm) * eased)
        left = wait["expected"] - waited
        self._show_progress(self._phase_text(
            getattr(self, "_hb_phase", ""),
            self._eta_text(left if left > 0 else None)))

    def _record_timed_wait(self) -> None:
        """Worker thread, after the real answer: learn how long this
        model took (core/timing_store), so the next estimate is better.
        OpenRouter records its own waits per part."""
        wait = getattr(self, "_timed_wait", None)
        if not wait or not wait.get("key"):
            return
        from ..core import timing_store
        timing_store.record(wait["key"], float(wait.get("media") or 0.0),
                            time.monotonic() - wait["start"])

    # ── v1.9.6: one way to react to Cancel, one way to reach the UI ──

    def _ui(self, fn, *args) -> None:
        """wx.CallAfter that does nothing once this frame is gone.

        The worker thread keeps posting updates after the user closes
        the main window; each landed on a deleted C++ object and raised
        "wrapped C/C++ object of type MainFrame has been deleted". The
        frame is checked when the call is posted AND when it runs.
        """
        def alive() -> bool:
            try:
                return bool(self) and not self.IsBeingDeleted()
            except RuntimeError:
                return False

        def run() -> None:
            if alive():
                fn(*args)

        if alive():
            wx.CallAfter(run)

    def _user_cancel(self) -> None:
        """The user pressed Cancel in the progress dialog (UI thread)."""
        if not self:
            return
        self._dl_cancelled = True
        self._dl_done = True
        self._hb_stop()
        dlg = self._dl_dialog
        if dlg is not None:
            try:
                dlg.Update(0, t("download.cancelling"))
            except Exception:
                pass
        try:
            self.SetStatusText(t("download.cancelling"))
        except Exception:
            pass
        self._close_download_progress()

    def _ai_cancel(self, pct: int = 0) -> None:
        """Frame mode, AI phase: Cancel keeps the frames already described
        (they are saved) instead of throwing the whole job away."""
        self._ai_cancelled = True
        dlg = self._dl_dialog
        if dlg is not None:
            try:
                dlg.Update(pct, t("download.cancel_analysis"))
            except Exception:
                pass
        self._close_download_progress()

    def _on_dialog_cancel(self, pct: int = 0) -> None:
        if getattr(self, "_frame_ai_phase", False):
            self._ai_cancel(pct)
        else:
            self._user_cancel()

    def _dialog_ok(self, result) -> bool:
        """Read the (continue, skip) pair from Update()/Pulse(). False
        means Cancel was pressed: the job is cancelled here, so EVERY
        dialog update notices it, not only some of them."""
        try:
            ok = bool(result[0])
        except Exception:
            ok = True
        if not ok:
            self._on_dialog_cancel()
        return ok

    def _export_dir(self) -> str:
        """Settings > General > Output Directory, where Save dialogs for
        exports open (v1.9.6: the setting was stored and used nowhere)."""
        try:
            folder = str(self.settings.get("general.output_dir", "") or "")
        except Exception:
            return ""
        return folder if folder and Path(folder).is_dir() else ""

    @staticmethod
    def _local_error_text(error) -> str:
        """A file/OS error in words: no JSON, URL or account id."""
        from ..core.ai_engine import short_error
        if isinstance(error, OSError) and error.strerror:
            name = Path(error.filename).name if error.filename else ""
            return f"{error.strerror}: {name}" if name else error.strerror
        return short_error(str(error), 150)

    @staticmethod
    def _error_text(error, source_error: bool = False) -> str:
        """What the user is told for a failed job (status log, status
        bar, message box). Never the raw provider text: an HTTP 413 used
        to be read out as a JSON body with an OpenRouter user id."""
        from ..core.ai_engine import short_error, user_error_text
        from ..core.video_processor import is_forbidden_error
        text = str(error)
        if is_forbidden_error(text):
            # v1.8.3: YouTube still refused after the retries. Download
            # 403s arrive as SourceError, which used to skip this test.
            return t("error.download_forbidden")
        shown = user_error_text(text)
        if source_error and shown == t("error.ai_generic",
                                       detail=short_error(text)):
            # Not an AI step: say what failed without the "AI" wording.
            return short_error(text, 300)
        return shown

    def _report_failure(self, shown: str) -> None:
        """Worker thread: a job failed. Log, status bar, close the
        progress dialog, THEN the message box NVDA reads."""
        line = t("status.error", error=shown)
        self._ui(self._log, line)
        self._ui(self.SetStatusText, line)
        self._ui(self._close_download_progress)
        self._ui(self._show_failure, shown)

    def _show_failure(self, shown: str) -> None:
        """v1.9.6: say a failed job in a message box. The status log and
        bar are not read by NVDA, and the progress dialog just closed,
        so a failure used to be silent. Never for a cancel."""
        try:
            if (not self or self.IsBeingDeleted()
                    or getattr(self, "_dl_cancelled", False)
                    or not self.IsShown()):
                return
        except RuntimeError:
            return
        wx.MessageBox(t("status.error", error=shown),
                      t("process.failed_title"), wx.OK | wx.ICON_ERROR, self)

    def _run_cancellable(self, cmd: list[str], timeout: float = 900.0):
        """Run a command, polling Cancel every 0.5 s (worker thread).

        Returns (returncode, stderr tail). Raises RuntimeError("cancelled")
        when the user cancels (the process is killed) and RuntimeError on
        timeout. Fast mode's frame extraction used subprocess.run, which
        ignored Cancel for up to 15 minutes.
        """
        import subprocess as _sp
        proc = _sp.Popen(cmd, stdout=_sp.DEVNULL, stderr=_sp.PIPE)
        tail = bytearray()

        def drain() -> None:
            try:
                for line in iter(proc.stderr.readline, b""):
                    tail.extend(line)
                    del tail[:-8192]
            except Exception:
                pass

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        deadline = time.monotonic() + timeout
        try:
            while True:
                if getattr(self, "_dl_cancelled", False):
                    proc.kill()
                    raise RuntimeError("cancelled")
                ret = proc.poll()
                if ret is not None:
                    break
                if time.monotonic() > deadline:
                    proc.kill()
                    raise TimeoutError(int(timeout))   # seconds; logged by the caller
                time.sleep(0.5)
        finally:
            if proc.poll() is None:
                proc.kill()
            reader.join(timeout=2.0)
            try:
                proc.stderr.close()
            except Exception:
                pass
        return ret, bytes(tail)

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
        self._ui(self._log, message)

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
            self._ui(self.SetStatusText, t("status.loading_video"))
            # FIX (1 Sep): for URLs the yt-dlp metadata probe can take up
            # to 120s with NO visible feedback (the download dialog only
            # appears at the first download event). Show the phase
            # immediately; screen readers read the status line.
            self._ui(self._ensure_download_progress)
            self._ui(self._download_progress_tick_text,
                         t("download.loading_info"), -1)
            self._ui(self._hb_start_timer, t("download.loading_info"))
            info = loop.run_until_complete(vp.get_video_info(
                source,
                is_cancelled=lambda: bool(
                    getattr(self, "_dl_cancelled", False))))
            # v1.5.1: keep the REAL title (yt-dlp metadata) for the
            # project name; local files keep their filename stem.
            self._download_title = getattr(info, "title", "") or ""
            self._ui(self._log, f"Video: {info.width}x{info.height}, {info.duration:.1f}s")

            # v1.4.1: chunk length is user-configurable (General tab).
            # Announce it once with an estimated part count so blind users
            # know upfront how many parts the video will be split into.
            chunk_seconds = int(self.settings.get(
                "general.chunk_seconds", 300) or 300)
            est_parts = (max(1, int(float(info.duration) / chunk_seconds + 0.999))
                         if info.duration > 0 else 1)
            if est_parts > 1:
                self._ui(self._log, t("video.chunk_multi",
                                          chunk=chunk_seconds, parts=est_parts))
            else:
                self._ui(self._log, t("video.chunk_single",
                                          chunk=chunk_seconds))

            # Full-video mode decided ONCE here so every announcement in
            # this pipeline stays accurate for this mode (no frame wording)
            video_mode = (
                self.settings.get("ai.video_mode", "full") == "full"
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
                self._ui(self.SetStatusText, t("status.extracting_frames"))
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
                self._ui(fn, *args)

            def _ui_now(fn, *args) -> None:
                self._ui(fn, *args)

            def count_frames() -> None:
                """Keep the dialog alive while ffmpeg extracts silently."""
                while not stop_counter.wait(0.7):
                    try:
                        n = sum(1 for _ in Path(frame_dir).glob("frame_*.jpg")) if frame_dir else 0
                    except Exception:
                        continue
                    if n:
                        self._ui(self._ensure_download_progress)
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
                self._ui(self._log, t("video.mode_enabled_log"))
                self._ui(self.SetStatusText, t("status.analyzing_video"))
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
                        self._ui(self._log, t("download.cancelled_log"))
                        self._ui(self._close_download_progress)
                        self._ui(self._processing_done)
                        loop.close()
                        return
                    raise

                def vstatus(phase: str) -> None:
                    self._ui(self._video_status_tick, phase)

                def vprogress(pct: float) -> None:
                    self._ui(self._video_upload_tick, pct)

                def vpart(part: int, total: int) -> None:
                    self._ui(self._video_part_tick, part, total)

                def vsplit(pct: float) -> None:
                    self._ui(self._video_split_tick, pct)

                def veta(pct: float, eta: float | None) -> None:
                    self._ui(self._video_eta_tick, pct, eta)

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
                        int(self.settings.get("general.chunk_seconds", 300) or 300),
                        prov_cfg.get("api_key", "")))
                    if est.get("priced"):
                        self._ui(self._log, t(
                            "cost.estimate", usd=f"{est['usd']:.3f}",
                            parts=est["parts"]))
                    if "remaining" in est:
                        self._ui(self._log, t(
                            "cost.balance", usd=f"{est['remaining']:.2f}"))
                    if est.get("min_balance_ok") is False:
                        self._ui(self._log, t("cost.too_low"))
                except Exception as e:
                    logger.debug("Cost estimate skipped: %s", e)

                # v1.6.1: fetch what is SAID before describing. The
                # default provider cannot hear the video at all (GLM,
                # probed: "NO AUDIO ACCESS"), so without this the model
                # is guessing at anything the soundtrack carries. Best
                # effort only — no transcript simply means no extra
                # context, never a failed run.
                transcript = []
                last_t = [-1]

                def tprogress(fraction: float) -> None:
                    # Whisper's thread, once per segment: post only when
                    # the whole percentage changes (a film has thousands
                    # of segments).
                    pct = int(max(0.0, min(1.0, fraction)) * 100)
                    if pct != last_t[0]:
                        last_t[0] = pct
                        self._ui(self._transcript_tick, fraction)

                try:
                    self._ui(self._video_status_tick, "transcript")
                    # local_path lets a URL with no published captions
                    # fall back to transcribing the file just downloaded.
                    transcript = loop.run_until_complete(
                        vp.get_transcript(
                            source, local_path=resolved,
                            is_cancelled=lambda: bool(
                                getattr(self, "_dl_cancelled", False)),
                            cache_path=self._transcript_cache_path(),
                            on_progress=tprogress))
                    if transcript:
                        self._ui(
                            self._log,
                            t("process.transcript_ok", count=len(transcript)))
                    else:
                        self._ui(self._log, t("process.transcript_none"))
                except Exception as e:
                    if str(e) == "cancelled":
                        # Same ending as a cancelled AI step below.
                        self._ui(self._log, t("download.cancelled_log"))
                        self._ui(self._close_download_progress)
                        if loop is not None and not loop.is_closed():
                            loop.close()
                        self._ui(self._processing_done)
                        return
                    logger.warning("Transcript step failed: %s", e)
                # Subtitles, the project cache or no transcript at all:
                # the stage is over either way.
                self._ui(self._transcript_tick, 1.0)

                # What a silent wait (Gemini/MiniMax) is estimated from;
                # OpenRouter reports its own progress and records its
                # own timings.
                try:
                    prov = self._provider_name()
                    model = (self.settings.get_ai_provider(prov) or {}).get(
                        "model", "")
                    self._wait_basis = (f"{prov}:{model}" if model else "",
                                        float(info.duration or 0.0),
                                        prov != "glm" and bool(model))
                except Exception:
                    self._wait_basis = None

                try:
                    pairs = loop.run_until_complete(
                        self.ai_engine.describe_video_full(
                            resolved, prompt,
                            transcript=transcript,
                            preserve_resolution=bool(self.settings.get(
                                "general.preserve_resolution", False)),
                            on_status=vstatus, on_upload_progress=vprogress,
                            on_part=vpart, on_split_progress=vsplit,
                            on_eta=veta,
                            chunk_seconds=int(self.settings.get(
                                "general.chunk_seconds", 300) or 300),
                            is_cancelled=lambda: bool(
                                getattr(self, "_dl_cancelled", False)),
                        )
                    )
                except Exception as e:
                    if "cancel" in str(e).lower():
                        self._ui(self._log, t("download.cancelled_log"))
                        self._ui(self._close_download_progress)
                        if loop is not None and not loop.is_closed():
                            loop.close()
                        self._ui(self._processing_done)
                        return
                    if "mm_file" in str(e):
                        self._ui(
                            self._log, t("video.mm_file_error",
                                         msg=self._error_text(e)))
                    raise
                try:
                    self._record_timed_wait()
                except Exception:
                    logger.debug("wait timing not recorded", exc_info=True)
                # The real answer is in: the AI stage is done.
                self._ui(self._stage_tick, "ai", 1.0)
                self._ui(self._log, t("video.parsed_count", count=len(pairs)))
                # v1.8.8: optional check of each description against the
                # picture (Settings; off unless the user turns it on).
                pairs = self._review_pairs(loop, resolved, pairs,
                                           float(info.duration or 0),
                                           est_parts)
                if pairs is None:
                    return  # cancelled; _review_pairs has cleaned up
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
                # No frame counter here: ffmpeg's frames are counted by
                # nobody. The 1 s heartbeat started at the top keeps
                # running for this branch, and it is what notices Cancel.
                stop_counter.set()
                self._ui(self.SetStatusText, t("video.fast_extracting"))
                from ..core.ai_engine import build_fast_batch_filter
                import re as _re
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
                        self._ui(self._log, t("download.cancelled_log"))
                        self._ui(self._close_download_progress)
                        self._ui(self._processing_done)
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
                # v1.9.6: polled every 0.5 s, so Cancel kills ffmpeg at
                # once. subprocess.run ignored Cancel for up to 900 s.
                self._ui(self._hb_set_phase, t("video.fast_extracting"))
                self._ui(self._stage_tick, "extract", 0.0)
                self._ui(self._download_progress_tick_text,
                         t("video.fast_extracting"), -1)
                failure = ""
                try:
                    returncode, stderr = self._run_cancellable(cmd, 900)
                    if returncode != 0:
                        tail = stderr.decode("utf-8", "replace")[-500:]
                        logger.error("Fast-mode ffmpeg failed (%s): %s",
                                     returncode, tail)
                        lines = [x for x in tail.splitlines() if x.strip()]
                        failure = f"ffmpeg: {lines[-1] if lines else returncode}"
                except RuntimeError as e:
                    if str(e) != "cancelled":
                        logger.error("Fast-mode ffmpeg failed: %s", e)
                        failure = f"ffmpeg: {e}"
                except Exception as e:
                    logger.error("Fast-mode ffmpeg failed: %s", e)
                    failure = f"ffmpeg: {e}"
                if failure and not getattr(self, "_dl_cancelled", False):
                    from ..core.ai_engine import short_error
                    # Named directly: user_error_text would call an
                    # ffmpeg timeout a network problem.
                    self._report_failure(t("error.video_prepare",
                                           detail=short_error(failure, 120)))
                    self._ui(self._processing_done)
                    self._cleanup_dir(frame_dir)
                    frame_dir = None
                    loop.close()
                    return
                if bool(getattr(self, "_dl_cancelled", False)):
                    self._ui(self._log, t("download.cancelled_log"))
                    self._ui(self._close_download_progress)
                    self._ui(self._processing_done)
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
                    self._report_failure(t("error.no_frames"))
                    self._ui(self._processing_done)
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
                self._ui(self._log, t(
                    "video.fast_mode_enabled_log",
                    count=len(fast_frames), batches=n_batches))
                self._ui(self._download_progress_tick_text,
                             t("video.fast_encoding",
                               count=len(fast_frames)), -1)
                frame_paths_fast = [str(p) for p in fast_frames]

                self._ui(self._stage_tick, "extract", 1.0)

                def fast_status(phase: str) -> None:
                    if phase == "describing":
                        # One request, no percentage: the bar moves by
                        # time (60 s + 0.5 s per second of video).
                        self._ui(self._hb_set_phase, t(
                            "video.fast_batches",
                            count=len(frame_paths_fast), batches=n_batches))
                        self._ui(self._begin_timed_wait, "",
                                 float(info.duration or 0.0))
                        self._ui(self._download_progress_tick_text,
                                     t("video.fast_batches",
                                       count=len(frame_paths_fast),
                                       batches=n_batches), -1)
                        self._ui(self.SetStatusText,
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
                        self._ui(self._log, t("download.cancelled_log"))
                        self._ui(self._close_download_progress)
                        if loop is not None and not loop.is_closed():
                            loop.close()
                        self._ui(self._processing_done)
                        return
                    raise
                self._ui(self._stage_tick, "ai", 1.0)
                self._ui(self._log, t("video.parsed_count",
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
                # The extract stage of the bar: frames written of these.
                self._expected_frames = int(float(info.duration or 0) * fps)
                frames = loop.run_until_complete(
                    vp.extract_frames(source, fps=fps, output_dir=frame_dir,
                                      min_spacing=float(self.settings.get(
                                          "general.min_description_gap", 4) or 0),
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
                self._ui(self._log, t("download.cancelled_log"))
                self._ui(self._close_download_progress)
                self._ui(self.SetStatusText, t("status.ready"))
                self._ui(self._processing_done)
                self._cleanup_dir(frame_dir)
                frame_dir = None
                loop.close()
                return
            self._ui(self._log, t("main.log_frames",
                                      count=len(frames), fps=fps))
            # Announce the completed download phase explicitly so screen
            # reader users know the fetch finished and what comes next.
            self._ui(self._ensure_download_progress)
            self._ui(self._download_progress_tick_text,
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
                self._ui(self._log, t("process.frame_capped", cap=cap, total=total_extracted))

            if not frames:
                self._ui(self._log, t("main.log_no_frames"))
                self._ui(self._close_download_progress)
                self._ui(self._processing_done)
                self._cleanup_dir(frame_dir)
                frame_dir = None
                loop.close()
                return

            # Step 3: Describe frames. The same dialog now shows real
            # per-frame AI progress (done/total); Cancel aborts the AI loop
            # between frames and keeps whatever is already done.
            self._ui(self.SetStatusText, t("status.analyzing"))
            self._ai_cancelled = False
            frame_paths = [f.path for f in frames]

            def ai_progress(done: int, tot: int) -> None:
                _ui_now(self._ai_progress_tick, done, tot)

            # While this flag is up, Cancel noticed anywhere (heartbeat
            # included) means "stop and keep what is described".
            self._frame_ai_phase = True
            try:
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
            finally:
                self._frame_ai_phase = False

            # Step 4: Save
            self._ui(self.SetStatusText, t("status.generating_descriptions"))

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
            frames_dir = self.project_store.project_dir(self.project_store.current.id) / "frames"
            frames_dir.mkdir(parents=True, exist_ok=True)
            desc_objects = []
            # v1.7.4: placeholders are not descriptions; v1.8.7: markdown,
            # headings and invented timestamps are cleaned out, and a line
            # identical to the one before is not said twice.
            from ..core.ai_engine import finalize_frame_descriptions
            for frame, text in finalize_frame_descriptions(frames, descriptions):
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
                # v1.9.6: when EVERY frame failed, say why -- the first
                # "(error: ...)" placeholder, in words (no JSON body).
                reason = ""
                for text in descriptions or []:
                    if str(text).startswith("(error:"):
                        reason = self._error_text(
                            str(text)[len("(error:"):].rstrip(") ").strip())
                        break
                empty = t("error.ai_empty")
                if reason:
                    empty = f"{empty} {reason}"
                self._ui(self._log, t("status.error", error=empty))
                self._ui(self.SetStatusText,
                         t("status.error", error=empty))
                self._ui(self._close_download_progress)

                def _notify_empty() -> None:
                    # A modal MessageBox blocks until dismissed, which hung
                    # an automated run that pumps the wx event loop (16 min
                    # stuck in test_fixes9). Show the modal only when the
                    # frame is actually on screen; headless runs get the
                    # same information via the log + status bar lines.
                    if not self or self.IsBeingDeleted():
                        return
                    if self.IsShown():
                        msg = t("process.no_descriptions")
                        if reason:
                            msg = f"{msg}\n\n{t('status.error', error=reason)}"
                        wx.MessageBox(msg, t("process.failed_title"),
                                      wx.OK | wx.ICON_ERROR, self)

                self._ui(_notify_empty)
                self._cleanup_dir(frame_dir)
                frame_dir = None
                if loop is not None and not loop.is_closed():
                    loop.close()
                self._ui(self._processing_done)
                return

            self._ui(self._ensure_download_progress)
            self._ui(self._download_progress_tick_text, t("download.saving"), -1)
            self.project_store.save_descriptions(desc_objects)
            self._write_project_srt()
            video_path = self._video_saved_path()
            self._ui(self._log, t("main.log_generated",
                                      count=len(desc_objects)))
            self._ui(self._log, t("status.processing_complete",
                                      count=len(desc_objects)))
            if video_path:
                self._ui(self._log, t("log.video_saved_at", path=video_path))

            def _notify_done(count: int, vpath: str) -> None:
                # Same guard as _notify_empty: modal only for visible
                # frames (real users), log/status only for headless runs.
                if not self or self.IsBeingDeleted():
                    return
                if self.IsShown():
                    key = ("process.complete_with_video" if vpath
                           else "status.processing_complete")
                    wx.MessageBox(t(key, count=count, path=vpath),
                                  t("process.complete_title"),
                                  wx.OK | wx.ICON_INFORMATION)

            self._ui(_notify_done, len(desc_objects), video_path)
            if getattr(self, "_ai_cancelled", False):
                self._ui(self._log, t("log.ai_cancelled_partial"))
            self._ui(self._close_download_progress)
            self._ui(self.SetStatusText, t("status.complete"))

            # Temp frames are no longer needed: used frames were copied.
            self._cleanup_dir(frame_dir)
            frame_dir = None
            loop.close()

        except SourceError as e:
            logger.error("Source resolution failed: %s", e)
            if getattr(self, "_dl_cancelled", False):
                self._ui(self._log, t("download.cancelled_log"))
                self._ui(self._close_download_progress)
            else:
                from ..core.video_processor import is_forbidden_error
                # v1.9.6: never the raw text (it carried the URL), and a
                # download 403 -- raised as SourceError -- now reaches
                # error.download_forbidden.
                shown = self._error_text(e, source_error=True)
                self._report_failure(shown)
                # v1.7.7: the usual cause of a YouTube download that used
                # to work is an outdated yt-dlp, so say where the fix is.
                if (not is_forbidden_error(str(e)) and "youtu" in str(
                        getattr(self, "_current_source", "") or e)):
                    self._ui(self._log, t("update.download_hint"))
            self._ui(self._processing_done)
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
            if getattr(self, "_dl_cancelled", False):
                # Cancel (or closing the window) made a step fail on its
                # way out: that is a cancellation, not "Processing error".
                self._ui(self._log, t("download.cancelled_log"))
                self._ui(self._close_download_progress)
            else:
                # v1.8.2/v1.9.6: busy, daily quota, 413, key, credit,
                # network... told in words with what to do -- never the
                # raw JSON body (it carried an OpenRouter user id).
                self._report_failure(self._error_text(e))
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

        self._ui(self._processing_done)

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
            # v1.9.6: AccessibleProgressDialog, a real progress bar NVDA
            # reads (wx.ProgressDialog's bar is DirectUI, pitfall 3). It
            # does not pump the event loop, but the guard below stays:
            # it is what keeps ANY dialog built here from becoming a
            # ghost.
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
            dlg = AccessibleProgressDialog(
                t("download.dialog_title"),
                t("download.preparing"),
                maximum=100,
                parent=self,
            )
            if (getattr(self, "_dl_close_gen", 0) != gen
                    or getattr(self, "_dl_done", False)):
                dlg.Destroy()
                self._dl_dialog = None
                return
            self._dl_dialog = dlg
            # A dialog re-created mid-job starts where the job is.
            self._dlg_text = self._dlg_title = None
            if self._overall_pct() > 0:
                dlg.Update(self._overall_pct())
            # The heartbeat is what notices Cancel in silent phases; a
            # dialog re-created mid-job (it is closed between phases)
            # must have it running again.
            timer = self._hb_timer
            if (self._processing and timer is not None
                    and not timer.IsRunning()):
                timer.Start(1000)
        except Exception:
            logger.debug("progress dialog creation failed", exc_info=True)
            self._dl_dialog = None

    def _download_progress_tick(self, p):
        """Download progress from a DownloadProgress (UI thread): the
        download stage, 0-15 of the overall bar."""
        if not self or getattr(self, "_dl_done", False):
            return
        if self._dl_dialog is None:
            return
        # Real progress is flowing (kept for tools that look at it).
        self._last_progress_at = time.monotonic()
        if p.phase == "merge":
            fraction, text = 1.0, t("download.merging")
        else:
            # Video first, then the (much smaller) audio stream: each
            # restarts at 0%, so they share the stage 90/10. A single
            # file ("preparing") has the whole stage.
            share = (max(0.0, min(100.0, p.percent)) / 100.0
                     if p.percent >= 0 else 0.0)
            fraction = {"video": 0.9 * share,
                        "audio": 0.9 + 0.1 * share}.get(p.phase, share)
            text = self._phase_text(t("download.dialog_title"),
                                    self._eta_text(self._clock_seconds(p.eta)))
        self._advance("download", fraction)
        self._title_phase = t("download.dialog_title")
        self._show_progress(text)
        # The detail (percent, MB, speed) stays in the status bar, which
        # is read on demand, not in the dialog.
        try:
            self.SetStatusText(self._format_progress(p))
        except Exception:
            logger.debug("status bar update failed", exc_info=True)

    @staticmethod
    def _clock_seconds(value: str) -> float:
        """yt-dlp's ETA ("01:05", "1:02:03") in seconds; -1 = unknown."""
        try:
            total = 0
            for part in str(value or "").strip().split(":"):
                total = total * 60 + int(part)
            return float(total) if value else -1.0
        except ValueError:
            return -1.0

    def _frame_count_tick(self, count: int):
        """Frame mode, extraction (UI thread): the extract stage, by the
        number of frames written of those expected."""
        if not self or getattr(self, "_dl_done", False):
            return
        if self._dl_dialog is None:
            return
        expected = getattr(self, "_expected_frames", 0) or 0
        self._advance("extract", count / expected if expected > 0 else 0.0)
        self._title_phase = t("status.extracting_frames")
        self._show_progress(t("status.extracting_frames"))
        self.SetStatusText(t("download.extract_progress", count=count))

    def _ai_progress_tick(self, done: int, total: int):
        """Frame mode, AI pass (UI thread): frames done of total."""
        if not self or getattr(self, "_dl_done", False):
            return
        if self._dl_dialog is None:
            return
        pct = self._advance("ai", done / total if total else 0.0)
        self._title_phase = t("status.analyzing")
        result = self._push_dialog(t("status.analyzing"))
        self.SetStatusText(t("download.analyzing", done=done, total=total))
        if result is not None and not result[0]:
            # Frame mode keeps its meaning: stop and save what is done.
            self._ai_cancel(pct)

    def _stage_tick(self, stage: str, fraction: float,
                    text: str | None = None) -> None:
        """A step with no tick of its own reached `fraction` of `stage`
        (UI thread)."""
        if not self or getattr(self, "_dl_done", False):
            return
        self._advance(stage, fraction)
        if fraction >= 1.0:
            # The real answer is in: a timed wait must not go on writing
            # "taking longer than usual" over the next phase.
            self._timed_wait = None
        self._show_progress(text)

    def _transcript_tick(self, fraction: float) -> None:
        """Transcript (UI thread): Whisper's position in the audio, or 1.0
        when subtitles or the project cache answered at once."""
        if not self or getattr(self, "_dl_done", False):
            return
        self._last_progress_at = time.monotonic()
        self._advance("transcript", fraction)
        self._show_progress()

    def _review_tick(self, done: int, total: int) -> None:
        """Description check (UI thread): checked of total."""
        if not self or getattr(self, "_dl_done", False):
            return
        self._advance("review", done / max(1, total))
        self._show_progress()
        self.SetStatusText(t("review.progress", done=done, total=total))

    def _set_dialog_phase_title(self, phase_line: str, pct: int | None = None) -> None:
        """Put the CURRENT phase and the OVERALL percentage in the title.

        The title is what a screen reader announces when the dialog
        takes focus, and what Win32 tools read (pitfall 3). It used to be
        "Downloading video - N%" for every phase of the run, frozen at
        the download's last percentage. `pct` is ignored: the title
        always shows the one overall percentage of the bar. Written only
        when it changes.
        """
        self._title_phase = phase_line
        dlg = self._dl_dialog
        if dlg is None:
            return
        text = f"{phase_line.rstrip('. ')} - {self._overall_pct()}%"
        if text == getattr(self, "_dlg_title", None):
            return
        try:
            dlg.SetTitle(text)
            self._dlg_title = text
        except Exception:
            logger.debug("dialog title update failed", exc_info=True)

    def _video_status_tick(self, phase: str):
        """Full-video mode: announce the current phase (UI thread).

        The dialog text, title and status bar change together; the phase
        is SPOKEN once (_announce_progress, pitfall 65), and the bar
        moves to the stage the phase belongs to.
        """
        if not self or getattr(self, "_dl_done", False):
            return
        phase_keys = {
            "transcript": "video.phase_transcript",
            "uploading": "video.phase_uploading",
            "compressing": "video.phase_compressing",
            "splitting": "video.phase_splitting",
            "processing": "video.phase_processing",
            "describing": "video.phase_describing",
            # v1.8.4: GLM's own steps. "encoding" and "parsing" used to
            # fall through to "The AI is watching the video" while the
            # app was still preparing the upload, or already done.
            "encoding": "video.phase_encoding",
            "waiting": "video.phase_waiting",
            "parsing": "video.phase_parsing",
            "reviewing": "video.phase_reviewing",
        }
        line = t(phase_keys.get(phase, "video.phase_processing"))
        # The heartbeat learns the phase (v1.6.4), the title stops
        # claiming "Downloading" for phases that are not a download.
        self._hb_set_phase(line)
        self._title_phase = line
        if phase == "transcript":
            self._advance("transcript")
        elif phase == "reviewing":
            self._advance("review")
        else:
            self._advance("ai")
            if phase in ("processing", "describing"):
                # Gemini/MiniMax say nothing until the answer: the bar
                # moves by time from here (_begin_timed_wait).
                basis = getattr(self, "_wait_basis", None) or ("", 0.0, False)
                self._begin_timed_wait(*basis)
        if not self._show_progress(self._phase_text(line)):
            return  # Cancel pressed: the job is being cancelled
        self.SetStatusText(line)
        if phase != "waiting":
            # A wait is announced by the first time-left tick, with
            # its estimate (see _video_eta_tick).
            self._announce_progress(line)

    def _review_pairs(self, loop, video: str, pairs, length: float,
                      parts: int):
        """Run the description check if Settings asks for it (worker
        thread). Returns the pairs to save, or None when cancelled.

        A failed check never costs the job: the unchecked descriptions
        are saved instead, and the log says why.
        """
        from ..core import review
        mode = review.resolve_mode(
            str(self.settings.get("general.review_mode", "off") or "off"),
            parts)
        if mode == "off" or not pairs:
            return pairs
        self._ui(self._video_status_tick, "reviewing")
        last = {"pct": -1}

        def progress(done: int, total: int) -> None:
            pct = int(done * 100 / max(1, total))
            # Only on whole 10% steps: the review owns 4 points of the
            # overall bar, and the status line need not change faster.
            if pct // 10 != last["pct"] // 10 or done == total:
                last["pct"] = pct
                self._ui(self._review_tick, done, total)
        try:
            kept, summary = loop.run_until_complete(review.review(
                self.ai_engine, video, pairs, mode, length,
                on_progress=progress,
                is_cancelled=lambda: bool(
                    getattr(self, "_dl_cancelled", False))))
        except RuntimeError as e:
            if "cancel" in str(e).lower():
                self._ui(self._log, t("download.cancelled_log"))
                self._ui(self._close_download_progress)
                if loop is not None and not loop.is_closed():
                    loop.close()
                self._ui(self._processing_done)
                return None
            logger.warning("Description check failed: %s", e)
            self._ui(self._log, t("review.failed", error=self._error_text(e)))
            return pairs
        except Exception as e:
            logger.warning("Description check failed: %s", e)
            self._ui(self._log, t("review.failed", error=self._error_text(e)))
            return pairs
        self._ui(self._log, t(
            "review.summary", checked=summary["checked"],
            moved=summary["moved"], removed=summary["removed"],
            mode=t(f"settings.review_{mode}")))
        return kept

    def _announce_progress(self, text: str, part: bool = False) -> None:
        """Say a change of phase through the user's screen reader.

        v1.8.4: the progress dialog keeps focus on Cancel, and a screen
        reader does not read text that changes away from the focus - the
        owner had to go and look to learn that "uploading" had become
        "the AI is watching". Prism speaks through NVDA (or SAPI when
        there is no screen reader) without interrupting what is being
        read. Phases that follow each other within 0.8 s collapse into
        the last one; a "Part 2 of 3" line is kept in front of it.
        """
        if not text:
            return
        if part:
            self._announce_part = text
        else:
            self._announce_pending = text
        timer = getattr(self, "_announce_timer", None)
        if timer is not None and timer.IsRunning():
            timer.Stop()
        self._announce_timer = wx.CallLater(800, self._announce_flush)

    def _announce_flush(self) -> None:
        text = " ".join(x for x in (getattr(self, "_announce_part", ""),
                                    getattr(self, "_announce_pending", ""))
                        if x)
        self._announce_part = self._announce_pending = ""
        if (not text or getattr(self, "_dl_done", False)
                or text == getattr(self, "_announced_text", "")):
            return
        self._announced_text = text
        self._speak_progress(text)

    @staticmethod
    def _speak_progress(text: str) -> None:
        def speak() -> None:
            try:
                from ..core.speech import get_speech
                get_speech().speak(text, interrupt=False)
            except Exception:
                logger.debug("progress announcement failed", exc_info=True)

        threading.Thread(target=speak, daemon=True).start()

    @staticmethod
    def _eta_text(eta: float | None) -> str:
        """Time left in words. None = past the estimate; <0 = unknown."""
        if eta is None:
            return t("video.eta_over")
        if eta < 0:
            return ""
        if eta < 60:
            return t("video.eta_under_minute")
        return t("video.eta_minutes", minutes=max(1, int(round(eta / 60.0))))

    def _video_eta_tick(self, pct: float, eta: float | None):
        """v1.8.4: OpenRouter's progress (0..100 of the AI step) and time
        left while a part uploads and waits. Mapped into the AI stage of
        the overall bar (v1.9.6)."""
        if not self or getattr(self, "_dl_done", False):
            return
        self._last_progress_at = time.monotonic()
        overall = self._advance("ai", pct / 100.0)
        phase = getattr(self, "_hb_phase", "") or t("video.phase_processing")
        left = ""
        if phase == t("video.phase_waiting"):
            left = self._eta_text(eta)
            # The wait is announced once, with its estimate, from here
            # rather than from the phase change a second earlier.
            if getattr(self, "_wait_said_for", None) != self._hb_start:
                self._wait_said_for = self._hb_start
                self._announce_progress(f"{phase} {left}".strip())
        self._title_phase = phase
        # The text is set only when it CHANGES. Heard in the 1.8.4 run:
        # with focus on the dialog itself, NVDA read the same two lines
        # again every second for 20 seconds.
        line = self._phase_text(phase, left)
        if not self._show_progress(line):
            return
        status = phase if not left else f"{phase} {left}"
        self.SetStatusText(f"{status} ({overall}%)")

    def _video_upload_tick(self, pct: float):
        """Gemini/MiniMax upload percentage (UI thread): the first half
        of the AI stage; the silent wait after it is the second half."""
        if not self or getattr(self, "_dl_done", False):
            return
        line = t("video.uploading_progress", pct=int(pct))
        # v1.6.4: real progress is arriving (tools and older tests read
        # this; the heartbeat no longer writes over anything).
        self._last_progress_at = time.monotonic()
        self._advance("ai", 0.5 * max(0.0, min(100.0, pct)) / 100.0)
        self._title_phase = t("video.phase_uploading")
        if not self._show_progress(self._phase_text(t("video.phase_uploading"))):
            return
        self.SetStatusText(line)

    def _video_split_tick(self, pct: float):
        """v1.4.1: OpenRouter split/describe progress for chunked videos,
        0..100 of the AI step (UI thread)."""
        if not self or getattr(self, "_dl_done", False):
            return
        overall = self._advance("ai", pct / 100.0)
        if not self._show_progress():
            return
        self.SetStatusText(t("video.split_progress", pct=overall))

    def _video_part_tick(self, part: int, total: int):
        """v1.4.1: part N of M starts (OpenRouter, UI thread).

        v1.8.4: part N STARTS here, so the parts already finished are
        N-1 ("part 1 of 2, overall 55%" was said before anything was
        sent). Splitting is the first 10% of the AI step.
        """
        if not self or getattr(self, "_dl_done", False):
            return
        overall = self._advance(
            "ai", (10.0 + 90.0 * (part - 1) / max(1, total)) / 100.0)
        line = t("video.part_progress", part=part, total=total, pct=overall)
        self._part_text = (t("video.part_start", part=part, total=total)
                           if total > 1 else "")
        if not self._show_progress(
                self._phase_text(getattr(self, "_hb_phase", ""))):
            return
        self.SetStatusText(line)
        self._log(line)
        if total > 1:
            self._announce_progress(t("video.part_start", part=part,
                                      total=total), part=True)

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
            self._ui(self._log, t("status.error", error=t("error.ai_empty")))
            self._ui(self.SetStatusText,
                         t("status.error", error=t("error.ai_empty")))
            self._ui(self._close_download_progress)

            def _notify_empty() -> None:
                if not self or self.IsBeingDeleted():
                    return
                if self.IsShown():
                    wx.MessageBox(t("process.no_descriptions"),
                                  t("process.failed_title"),
                                  wx.OK | wx.ICON_ERROR, self)

            self._ui(_notify_empty)
            if frame_dir:
                self._cleanup_dir(frame_dir)
            if loop is not None and not loop.is_closed():
                loop.close()
            self._ui(self._processing_done)
            return

        self._ui(self._ensure_download_progress)
        self._ui(self._download_progress_tick_text, t("download.saving"), -1)
        self.project_store.save_descriptions(desc_objects)
        self._write_project_srt()
        video_path = self._video_saved_path()
        self._ui(self._log, t("main.log_generated",
                                  count=len(desc_objects)))
        self._ui(self._log, t("status.processing_complete",
                                  count=len(desc_objects)))
        if video_path:
            self._ui(self._log, t("log.video_saved_at", path=video_path))

        def _notify_done(count: int, vpath: str) -> None:
            if not self or self.IsBeingDeleted():
                return
            if self.IsShown():
                key = ("process.complete_with_video" if vpath
                       else "status.processing_complete")
                wx.MessageBox(t(key, count=count, path=vpath),
                              t("process.complete_title"),
                              wx.OK | wx.ICON_INFORMATION)

        self._ui(_notify_done, len(desc_objects), video_path)
        self._ui(self._close_download_progress)
        self._ui(self.SetStatusText, t("status.complete"))
        if frame_dir:
            self._cleanup_dir(frame_dir)
        if loop is not None and not loop.is_closed():
            loop.close()
        self._ui(self._processing_done)

    def _download_progress_tick_text(self, text: str, percent: int):
        """Show a phase text in the dialog (UI thread). The bar keeps the
        overall percentage; `percent` is ignored (every caller passed -1,
        "no percentage", which used to animate the bar and lose it)."""
        if not self or getattr(self, "_dl_done", False):
            return
        if self._dl_dialog is None:
            return
        self._show_progress(text)

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
        if not self:
            return
        self._hb_stop()
        # Bumped even when there is nothing to close: a dialog may be
        # mid-construction right now (see _ensure_download_progress).
        self._dl_close_gen = getattr(self, "_dl_close_gen", 0) + 1
        dlg, self._dl_dialog = self._dl_dialog, None
        self._dlg_text = self._dlg_title = None
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
        if not self:
            return  # the window was closed while the job ran
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
            self._ui(self._open_player)

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

    def _transcript_cache_path(self):
        """media/transcript.json of the project being processed (shared
        with the Player agent), or None when there is no project."""
        cur = self.project_store.current
        if cur is None:
            return None
        try:
            return self.project_store.media_dir(cur.id) / "transcript.json"
        except Exception:
            return None

    def _open_player(self):
        """Open the described video player window."""
        from .player_window import PlayerWindow
        try:
            win = PlayerWindow(self, self.project_store, self.tts_engine,
                               self.ai_engine, settings=self.settings)
            win.Show()
        except Exception as e:
            logger.error("Failed to open PlayerWindow: %s", e)
            self._log(t("log.player_failed", error=self._local_error_text(e)))

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
