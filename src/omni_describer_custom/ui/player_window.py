"""
Omni Describer Custom — Described Video Player.

VLC-based player with audio descriptions overlay.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import wx

from ..core.project_store import ProjectStore
from ..core.tts_engine import TTSEngine
from ..i18n.strings import I18n, t

logger = logging.getLogger(__name__)


class PlayerWindow(wx.Frame):
    """
    Described Video Player with TTS audio descriptions.
    """

    def __init__(
        self,
        parent,
        project_store: ProjectStore,
        tts_engine: TTSEngine,
        ai_engine=None,
    ):
        self.project = project_store.current
        self.store = project_store
        self.tts = tts_engine
        self.ai_engine = ai_engine
        self._current_desc_idx = 0
        self._playing = False
        self._timer: wx.Timer | None = None
        self._position = 0.0  # Current playback position in seconds
        self._vlc = None
        self._vlc_instance = None
        self._vlc_media = None
        self._vlc_available = False
        self._paused_by_user = False
        self._init_vlc()

        super().__init__(parent, title=f"{t('player.title')} — {self.project.name if self.project else ''}",
                         size=(1000, 700))

        self._build_ui()
        self._load_descriptions()
        self._attach_vlc_video()
        logger.info("PlayerWindow opened (VLC: %s)", self._vlc_available)

    def _init_vlc(self):
        """Try to create a VLC instance. Falls back to simulated playback
        (description walkthrough with timeline) when VLC is unavailable."""
        try:
            import vlc
            self._vlc_instance = vlc.Instance("--no-video-title-show")
            self._vlc = self._vlc_instance.media_player_new()
            self._vlc_available = True
        except Exception as e:
            logger.info("VLC unavailable, using simulated playback: %s", e)
            self._vlc_available = False

    def _attach_vlc_video(self):
        """Attach VLC output to the video panel and load media if present."""
        if not self._vlc_available or not self.project:
            return
        video_path = self.project.video_path or ""
        if not video_path or not __import__("os").path.exists(video_path):
            logger.info("No local video file for VLC: %s", video_path)
            return
        try:
            if hasattr(self._vlc, "set_hwnd"):
                self._vlc.set_hwnd(self.video_panel.GetHandle())
            self._vlc_media = self._vlc_instance.media_new(video_path)
            self._vlc.set_media(self._vlc_media)
            self.project.video_duration = self._vlc_media.get_duration() / 1000.0
        except Exception as e:
            logger.warning("VLC attach failed: %s", e)
            self._vlc_available = False

    def _build_ui(self):
        """Build player UI."""
        panel = wx.Panel(self)
        panel.SetName("player_panel")
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        # ── Video Area ─────────────────────────────────────────
        self.video_panel = wx.Panel(panel, size=(854, 480), name="video_area")
        self.video_panel.SetBackgroundColour(wx.Colour(0, 0, 0))
        sizer.Add(self.video_panel, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        # ── Transport Controls ─────────────────────────────────
        controls = wx.BoxSizer(wx.HORIZONTAL)

        self.play_btn = wx.Button(panel, label=t("player.play"), name="play")
        self.pause_btn = wx.Button(panel, label=t("player.pause"), name="pause")
        self.stop_btn = wx.Button(panel, label=t("player.stop"), name="stop_player")

        self.rewind_btn = wx.Button(panel, label="<< 10s", name="rewind")
        self.forward_btn = wx.Button(panel, label="10s >>", name="forward")

        controls.Add(self.play_btn, 0, wx.ALL, 5)
        controls.Add(self.pause_btn, 0, wx.ALL, 5)
        controls.Add(self.stop_btn, 0, wx.ALL, 5)
        controls.AddStretchSpacer()
        controls.Add(self.rewind_btn, 0, wx.ALL, 5)
        controls.Add(self.forward_btn, 0, wx.ALL, 5)

        sizer.Add(controls, 0, wx.ALL | wx.EXPAND, 5)

        # ── Timeline Slider ────────────────────────────────────
        timeline_row = wx.BoxSizer(wx.HORIZONTAL)
        self.position_slider = wx.Slider(panel, value=0, minValue=0, maxValue=1000,
                                         style=wx.SL_HORIZONTAL, name="timeline")
        self.time_label = wx.StaticText(panel, label="00:00 / 00:00", name="time_display")
        timeline_row.Add(self.position_slider, 1, wx.ALL | wx.EXPAND, 5)
        timeline_row.Add(self.time_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        sizer.Add(timeline_row, 0, wx.ALL | wx.EXPAND, 5)

        # ── Description Display ────────────────────────────────
        desc_box = wx.StaticBox(panel, label=t("player.current_desc"))
        desc_sizer = wx.StaticBoxSizer(desc_box, wx.VERTICAL)

        self.current_desc_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY,
                                             size=(-1, 80), name="current_description")
        self.current_desc_text.SetValue("")
        desc_sizer.Add(self.current_desc_text, 1, wx.ALL | wx.EXPAND, 5)

        # Upcoming
        upcoming_row = wx.BoxSizer(wx.HORIZONTAL)
        upcoming_label = wx.StaticText(panel, label=t("player.upcoming"), name="upcoming_label")
        self.upcoming_text = wx.TextCtrl(panel, style=wx.TE_READONLY, size=(-1, -1),
                                         name="upcoming_description")
        upcoming_row.Add(upcoming_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        upcoming_row.Add(self.upcoming_text, 1, wx.ALL | wx.EXPAND, 5)
        desc_sizer.Add(upcoming_row, 0, wx.EXPAND)

        sizer.Add(desc_sizer, 0, wx.ALL | wx.EXPAND, 10)

        # ── Action Buttons ─────────────────────────────────────
        action_row = wx.BoxSizer(wx.HORIZONTAL)

        self.edit_btn = wx.Button(panel, label=t("editor.title"), name="edit_descriptions")
        self.ask_btn = wx.Button(panel, label=t("player.ask_more"), name="ask_more")
        self.explore_btn = wx.Button(panel, label=t("player.explore"), name="explore")
        speaker = chr(0x1F50A)
        self.speak_btn = wx.Button(panel, label=speaker + " Read Description", name="speak_desc")

        action_row.Add(self.edit_btn, 0, wx.ALL, 5)
        action_row.Add(self.ask_btn, 0, wx.ALL, 5)
        action_row.Add(self.explore_btn, 0, wx.ALL, 5)
        action_row.Add(self.speak_btn, 0, wx.ALL, 5)

        sizer.Add(action_row, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        # ── Status ─────────────────────────────────────────────
        self.status_text = wx.StaticText(panel, label="", name="player_status")
        sizer.Add(self.status_text, 0, wx.ALL, 5)

        # ── Bindings ───────────────────────────────────────────
        self.play_btn.Bind(wx.EVT_BUTTON, self._on_play)
        self.pause_btn.Bind(wx.EVT_BUTTON, self._on_pause)
        self.stop_btn.Bind(wx.EVT_BUTTON, self._on_stop)
        self.rewind_btn.Bind(wx.EVT_BUTTON, self._on_rewind)
        self.forward_btn.Bind(wx.EVT_BUTTON, self._on_forward)
        self.position_slider.Bind(wx.EVT_SLIDER, self._on_seek)
        self.edit_btn.Bind(wx.EVT_BUTTON, self._on_edit)
        self.ask_btn.Bind(wx.EVT_BUTTON, self._on_ask)
        self.explore_btn.Bind(wx.EVT_BUTTON, self._on_explore)
        self.speak_btn.Bind(wx.EVT_BUTTON, self._on_speak)
        self.Bind(wx.EVT_CLOSE, self._on_close)

        # Start timer (created here so EVT_TIMER binding is already in place)
        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer, self._timer)
        self._timer.Start(500)  # 500ms interval

        panel.Layout()

    def _load_descriptions(self):
        """Load descriptions from current project."""
        if not self.project or not self.project.descriptions:
            self.current_desc_text.SetValue("No descriptions available.")
            return
        self._update_desc_display()

    def _update_desc_display(self):
        """Update current + upcoming description display."""
        if not self.project or not self.project.descriptions:
            return

        descs = self.project.descriptions
        self._current_desc_idx = 0

        # Find description matching current position
        for i, desc in enumerate(descs):
            if desc.start_time <= self._position < desc.end_time:
                self._current_desc_idx = i
                break
            elif desc.start_time > self._position:
                self._current_desc_idx = max(0, i - 1)
                break

        current = descs[self._current_desc_idx]
        self.current_desc_text.SetValue(current.text)

        if self._current_desc_idx + 1 < len(descs):
            upcoming = descs[self._current_desc_idx + 1]
            self.upcoming_text.SetValue(f"[{upcoming.start_time:.1f}s] {upcoming.text[:80]}...")
        else:
            self.upcoming_text.SetValue("(end)")

        # Update time label
        self._update_time_label()

    def _update_time_label(self):
        """Update time display."""
        if self.project:
            dur = self.project.video_duration
        else:
            dur = 0
        pos_str = self._format_time(self._position)
        dur_str = self._format_time(dur)
        self.time_label.SetLabel(f"{pos_str} / {dur_str}")

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds to MM:SS."""
        m = int(seconds) // 60
        s = int(seconds) % 60
        return f"{m:02d}:{s:02d}"

    def _on_timer(self, event):
        """Periodic update from playback."""
        if self._vlc_available and self._vlc is not None:
            # Sync position from real VLC playback
            if self._vlc.is_playing():
                self._playing = True
                self._position = self._vlc.get_time() / 1000.0
            elif self._playing and not self._paused_by_user:
                # VLC stopped without user pause — end of media
                self._playing = False
                self.status_text.SetLabel("Ended")
        elif self._playing:
            self._position += 0.5  # 500ms tick (simulated playback)
        dur = self.project.video_duration if self.project else 0.0
        if dur > 0 and self._position >= dur:
            self._position = dur
            if self._playing:
                self._playing = False
                self.status_text.SetLabel("Ended")
        self._update_desc_display()
        self.position_slider.SetValue(int(self._position * 10))

    def _on_play(self, event):
        self._paused_by_user = False
        if self._vlc_available and self._vlc_media is not None:
            self._vlc.play()
            self._playing = True
            self.status_text.SetLabel("Playing (VLC)...")
            return
        self._playing = True
        self.status_text.SetLabel("Playing (simulated)...")
        self._timer.Start(500)

    def _on_pause(self, event):
        self._paused_by_user = True
        if self._vlc_available and self._vlc_media is not None:
            self._vlc.pause()
            self._playing = self._vlc.is_playing()
            self.status_text.SetLabel("Paused" if not self._playing else "Playing (VLC)...")
            return
        self._playing = False
        self.status_text.SetLabel("Paused")
        self._timer.Stop()

    def _on_stop(self, event):
        self._paused_by_user = True
        self._playing = False
        if self._vlc_available and self._vlc_media is not None:
            self._vlc.stop()
        self._position = 0.0
        self.position_slider.SetValue(0)
        self._update_desc_display()
        self.status_text.SetLabel("Stopped")

    def _on_rewind(self, event):
        self._position = max(0, self._position - 10)
        if self._vlc_available and self._vlc_media is not None:
            self._vlc.set_time(int(self._position * 1000))
        self._update_desc_display()

    def _on_forward(self, event):
        self._position += 10
        if self._vlc_available and self._vlc_media is not None:
            self._vlc.set_time(int(self._position * 1000))
        self._update_desc_display()

    def _on_seek(self, event):
        self._position = self.position_slider.GetValue() / 10.0
        if self._vlc_available and self._vlc_media is not None:
            self._vlc.set_time(int(self._position * 1000))
        self._update_desc_display()

    def _on_edit(self, event):
        """Open description editor."""
        from .editor_window import EditorWindow
        editor = EditorWindow(self, self.store, self.tts)
        editor.Show()

    def _on_ask(self, event):
        """Open 'ask more' dialog."""
        from .ask_more_dialog import AskMoreDialog
        dlg = AskMoreDialog(self, self.ai_engine)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_explore(self, event):
        """Open scene explorer."""
        from .scene_explorer import SceneExplorer
        video_path = ""
        if self.store.current:
            video_path = self.store.current.video_path
        explorer = SceneExplorer(self, self.ai_engine, video_path)
        explorer.Show()

    def _on_speak(self, event):
        """Read current description aloud via TTS."""
        desc_text = self.current_desc_text.GetValue().strip()
        if not desc_text:
            return
        self.status_text.SetLabel("Speaking...")
        self.tts.stop()

        def _speak_bg():
            loop = __import__("asyncio").new_event_loop()
            __import__("asyncio").set_event_loop(loop)
            try:
                result = loop.run_until_complete(self.tts.speak(desc_text, engine="edge"))
                if result:
                    wx.CallAfter(self.status_text.SetLabel, "Spoken")
                else:
                    wx.CallAfter(self.status_text.SetLabel, "TTS failed")
            except Exception as e:
                wx.CallAfter(self.status_text.SetLabel, "TTS error: " + str(e))
            finally:
                loop.close()

        __import__("threading").Thread(target=_speak_bg, daemon=True).start()

    def _on_close(self, event):
        self._playing = False
        self.tts.stop()
        if self._vlc_available and self._vlc is not None:
            try:
                self._vlc.stop()
            except Exception:
                pass
        if self._timer:
            self._timer.Stop()
        self.Destroy()
