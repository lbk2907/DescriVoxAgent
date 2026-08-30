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
        self._worker: threading.Thread | None = None
        self._current_frames: list[str] = []
        self._current_source: str = ""

        # Language
        lang = self.settings.get("general.language", "en")
        I18n.set_language(lang)

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

        self.btn_local = wx.Button(panel, label="Local Video File",
                                   name="source_local")
        self.btn_url = wx.Button(panel, label="Direct Video URL",
                                 name="source_url")
        self.btn_youtube = wx.Button(panel, label="YouTube Video URL",
                                     name="source_youtube")

        for btn in (self.btn_local, self.btn_url, self.btn_youtube):
            btn.SetMinSize((-1, _BTN_H))
            outer.Add(btn, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, _BORDER)

        outer.AddSpacer(8)

        # ── 2. Prompt preset row (ComboBox + Open button) ────────
        preset_row = wx.BoxSizer(wx.HORIZONTAL)

        preset_label = wx.StaticText(
            panel,
            label="Optional: Select a prompt preset to enhance generation:",
            name="preset_label",
        )
        outer.Add(preset_label, 0, wx.LEFT | wx.RIGHT, _BORDER)

        combo_row = wx.BoxSizer(wx.HORIZONTAL)
        self.prompt_choice = wx.Choice(panel, name="prompt_choice")
        self.prompt_choice.SetMinSize((-1, _COMBO_H))
        self._refresh_prompt_list()

        self.btn_preset_open = wx.Button(panel, label="Open",
                                         name="preset_open")
        self.btn_preset_open.SetMinSize((50, _COMBO_H))

        combo_row.Add(self.prompt_choice, 1, wx.RIGHT | wx.EXPAND, 5)
        combo_row.Add(self.btn_preset_open, 0, wx.RIGHT, _BORDER)
        outer.Add(combo_row, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, _BORDER)

        outer.AddSpacer(5)

        # ── 3. Custom prompt text area ───────────────────────────
        outer.Add(wx.StaticText(panel, label="Custom Prompt:",
                                name="custom_prompt_label"),
                  0, wx.LEFT | wx.RIGHT, _BORDER)
        self.custom_prompt = wx.TextCtrl(
            panel,
            value="",
            style=wx.TE_MULTILINE,
            name="custom_prompt",
        )
        self.custom_prompt.SetMinSize((-1, _EDIT_H))
        outer.Add(self.custom_prompt, 0,
                  wx.LEFT | wx.RIGHT | wx.EXPAND, _BORDER)

        outer.AddSpacer(8)

        # ── 4. Status Log ────────────────────────────────────────
        outer.Add(wx.StaticText(panel, label="Status Log",
                                name="log_label"),
                  0, wx.LEFT | wx.RIGHT, _BORDER)
        self.log_text = wx.TextCtrl(
            panel,
            value="",
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            name="log_output",
        )
        self.log_text.SetMinSize((-1, _LOG_H))
        outer.Add(self.log_text, 1,
                  wx.LEFT | wx.RIGHT | wx.EXPAND, _BORDER)

        outer.AddSpacer(8)

        # ── 5. Bottom buttons: Settings ... Exit ─────────────────
        bottom_row = wx.BoxSizer(wx.HORIZONTAL)

        self.btn_settings = wx.Button(panel, label="Settings...",
                                      name="open_settings")
        self.btn_settings.SetMinSize((90, _BTN_H))

        self.btn_exit = wx.Button(panel, label="Exit",
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
        """Mirror original: System, Help."""
        menubar = wx.MenuBar()

        # System — dropdown
        system_menu = wx.Menu()
        system_menu.Append(wx.ID_PREFERENCES, "Settings...")
        system_menu.Append(wx.ID_EXIT, "Exit")
        menubar.Append(system_menu, "System")

        # File — dropdown
        file_menu = wx.Menu()
        file_menu.Append(wx.ID_NEW, "New Project...")
        file_menu.Append(wx.ID_OPEN, "Open Project...")
        file_menu.Append(wx.ID_SAVE, "Save Project")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT, "Exit")
        menubar.Append(file_menu, "File")

        # Help — dropdown
        help_menu = wx.Menu()
        help_menu.Append(wx.ID_ABOUT, "About")
        menubar.Append(help_menu, "Help")

        self.SetMenuBar(menubar)

    # ── Events ────────────────────────────────────────────────────

    def _bind_events(self):
        """Bind all UI events."""
        # Source buttons
        self.btn_local.Bind(wx.EVT_BUTTON, self._on_local_file)
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
        self.Bind(wx.EVT_MENU, self._on_about, id=wx.ID_ABOUT)
        self.Bind(wx.EVT_CLOSE, self._on_close_window)

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
            self._log(f"Selected: {path}")
            self.SetStatusText(f"File: {Path(path).name}")
        dlg.Destroy()

    def _on_direct_url(self, event):
        """Open dialog to enter a direct video URL."""
        dlg = wx.TextEntryDialog(
            self, "Enter video URL:", "Direct Video URL",
        )
        if dlg.ShowModal() == wx.ID_OK:
            url = dlg.GetValue().strip()
            if url:
                self._current_source = url
                self._log(f"URL: {url}")
                self.SetStatusText(f"URL: {url[:60]}")
        dlg.Destroy()

    def _on_youtube_url(self, event):
        """Open dialog to enter a YouTube URL."""
        dlg = wx.TextEntryDialog(
            self, "Enter YouTube video URL:", "YouTube Video URL",
        )
        if dlg.ShowModal() == wx.ID_OK:
            url = dlg.GetValue().strip()
            if url:
                self._current_source = url
                self._log(f"YouTube: {url}")
                self.SetStatusText(f"YouTube: {url[:60]}")
        dlg.Destroy()

    # ── Preset Handler ─────────────────────────────────���──────────

    def _on_preset_open(self, event):
        """Apply the selected prompt preset and start processing."""
        preset_name = self.prompt_choice.GetStringSelection()
        if not preset_name:
            wx.MessageBox("Please select a prompt preset.", "Prompt",
                          wx.OK | wx.ICON_WARNING)
            return

        # Get preset text
        prompt = self.prompt_mgr.get_preset(preset_name)

        # Check if user added custom prompt text
        custom = self.custom_prompt.GetValue().strip()
        if custom:
            prompt = f"{prompt}\n\nUser notes: {custom}"

        self._log(f"Preset: {preset_name}")
        self._start_processing(prompt)

    # ── Settings / Exit ───────────────────────────────────────────

    def _on_settings(self, event):
        """Open settings dialog."""
        from .settings_dialog import SettingsDialog
        dlg = SettingsDialog(self, self.settings, self.tts_engine)
        dlg.ShowModal()
        dlg.Destroy()
        self._load_settings()
        # Re-apply TTS engine/voice/speed from settings
        self.tts_engine.settings = self.settings.get("tts", {})
        self.tts_engine._init_engines()

    def _on_exit(self, event):
        """Exit the application."""
        self._processing = False
        self.Close()

    def _on_new_project(self, event):
        name_dlg = wx.TextEntryDialog(self, "Project name:", "New Project")
        if name_dlg.ShowModal() == wx.ID_OK:
            name = name_dlg.GetValue().strip()
            if name:
                self.project_store.create_project(name, "")
                self._log(f"Project created: {name}")
                self.SetStatusText(f"Project: {name}")
        name_dlg.Destroy()

    def _on_open_project(self, event):
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
        dlg.Destroy()

    def _on_save_project(self, event):
        if not self.project_store.current:
            wx.MessageBox("No project open.", "Save",
                          wx.OK | wx.ICON_INFORMATION)
            return
        self.project_store.save_descriptions(self.project_store.current.descriptions)
        self._log("Project saved")

    def _on_about(self, event):
        info = wx.adv.AboutDialogInfo()
        info.SetName("Omni Describer Custom")
        info.SetVersion("1.0.0")
        info.SetDescription(
            "Accessible audio description tool for blind and visually "
            "impaired users. Describes video frames using AI and narrates "
            "them via text-to-speech."
        )
        info.SetCopyright("(C) 2026 Omni Describer Custom")
        wx.adv.AboutBox(info)

    def _on_close_window(self, event):
        """Handle window close."""
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
        provider = self.settings.get("ai.default_provider", "opus")
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

        self._processing = True
        self._dl_cancelled = False
        self.btn_preset_open.Disable()
        self.btn_local.Disable()
        self.btn_url.Disable()
        self.btn_youtube.Disable()

        self._worker = threading.Thread(
            target=self._process_video,
            args=(source, prompt),
            daemon=True,
        )
        self._worker.start()

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
            info = loop.run_until_complete(vp.get_video_info(source))
            wx.CallAfter(self._log, f"Video: {info.width}x{info.height}, {info.duration:.1f}s")

            # Step 2: Extract frames (FPS from settings). For URLs this first
            # downloads via yt-dlp with a REAL progress dialog: percentage,
            # MB downloaded of MB total, speed and ETA (user request 30 Aug).
            # The dialog is created lazily on the first download event so
            # local files never see an empty dialog.
            # FIX (30 Aug): during the silent ffmpeg extraction a background
            # counter keeps the dialog moving ("Extracting frames: N").
            wx.CallAfter(self.SetStatusText, t("status.extracting_frames"))
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
            cancelled = False
            try:
                fps = int(self.settings.get("general.frame_rate", 5) or 5)
                frames = loop.run_until_complete(
                    vp.extract_frames(source, fps=fps, output_dir=frame_dir,
                                      on_progress=download_progress,
                                      is_cancelled=lambda: bool(getattr(self, "_dl_cancelled", False)))
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
            wx.CallAfter(self._log, f"Extracted {len(frames)} frames at {fps} FPS")

            if not frames:
                wx.CallAfter(self._log, "ERROR: No frames extracted")
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
                video_name = Path(source).name if Path(source).exists() else source
                self.project_store.create_project(video_name, source)

            # Persist video duration for the player timeline
            self.project_store.set_video_duration(info.duration)

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

            wx.CallAfter(self._ensure_download_progress)
            wx.CallAfter(self._download_progress_tick_text, t("download.saving"), -1)
            self.project_store.save_descriptions(desc_objects)
            wx.CallAfter(self._log, f"Generated {len(desc_objects)} descriptions")
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
            return
        except Exception as e:
            logger.error("Processing error: %s", e)
            wx.CallAfter(self._log, f"ERROR: {e}")
            wx.CallAfter(self.SetStatusText, t("status.error", error=str(e)))
            wx.CallAfter(self._close_download_progress)
            if frame_dir:
                self._cleanup_dir(frame_dir)

        wx.CallAfter(self._processing_done)

    def _ensure_download_progress(self):
        """Create the download progress dialog on first progress event.

        Runs on the UI thread (via wx.CallAfter). Lazily created so local
        files never flash an empty dialog.
        """
        if self._dl_dialog is not None or self.IsBeingDeleted():
            return
        try:
            dlg = wx.ProgressDialog(
                t("download.dialog_title"),
                t("download.preparing"),
                maximum=100,
                parent=self,
                style=wx.PD_CAN_ABORT | wx.PD_SMOOTH | wx.PD_AUTO_HIDE,
            )
            dlg.SetSize((460, 150))
            self._dl_dialog = dlg
        except Exception:
            logger.debug("ProgressDialog creation failed", exc_info=True)
            self._dl_dialog = None

    def _download_progress_tick(self, p):
        """Update the progress dialog from a DownloadProgress (UI thread)."""
        dlg = self._dl_dialog
        if dlg is None:
            return
        line = self._format_progress(p)
        if p.percent < 0:
            # Unknown percentage: pulse the bar, show the text
            ok = dlg.Pulse(line)[0]
        else:
            ok = dlg.Update(int(p.percent), line)[0]
        if not ok:
            # User pressed Cancel
            self._dl_cancelled = True
            dlg.Update(0, t("download.cancelling"))
            self._close_download_progress()

    def _frame_count_tick(self, count: int):
        """Show extraction progress in the dialog (UI thread)."""
        dlg = self._dl_dialog
        if dlg is None:
            return
        line = t("download.extract_progress", count=count)
        ok = dlg.Pulse(line)[0]
        if not ok:
            self._dl_cancelled = True
            dlg.Update(0, t("download.cancelling"))
            self._close_download_progress()

    def _ai_progress_tick(self, done: int, total: int):
        """Show real per-frame AI progress in the dialog (UI thread)."""
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
        dlg, self._dl_dialog = self._dl_dialog, None
        if dlg is not None:
            try:
                dlg.Destroy()
            except Exception:
                pass
            self.Refresh()

    def _processing_done(self):
        """Reset UI after processing and open PlayerWindow."""
        self._processing = False
        self.btn_preset_open.Enable()
        self.btn_local.Enable()
        self.btn_url.Enable()
        self.btn_youtube.Enable()

        # Auto-open PlayerWindow if descriptions were generated
        if self.project_store.current and self.project_store.current.descriptions:
            self._log("Opening Player Window...")
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
        self.prompt_choice.SetItems(names)
        if names:
            self.prompt_choice.SetSelection(0)

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
        """Append a line to the status log."""
        self.log_text.AppendText(message + "\n")
        self.log_text.ShowPosition(self.log_text.GetLastPosition())
