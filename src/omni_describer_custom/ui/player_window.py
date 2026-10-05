"""
Omni Describer Custom — Described Video Player.

VLC-based player with audio descriptions overlay.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

import wx

from ..core.project_store import ProjectStore
from ..core.tts_engine import TTSEngine
from ..core.timeline_io import Description, parse_any
from ..i18n.strings import I18n, t

logger = logging.getLogger(__name__)


class _TimeSliderAccessible(wx.Accessible):
    """What a screen reader hears for the timeline: "1:04 of 24:30", not
    the slider's raw number. Only the value is ours; name, role, state
    and position stay Windows' own (NOT_IMPLEMENTED falls back to them)."""

    def __init__(self, slider, fmt):
        super().__init__(slider)
        self._slider = slider
        self._fmt = fmt

    def GetValue(self, childId):
        try:
            return (wx.ACC_OK, t("player.slider_value",
                                 position=self._fmt(self._slider.GetValue()),
                                 total=self._fmt(self._slider.GetMax())))
        except RuntimeError:            # the slider is gone
            return (wx.ACC_NOT_IMPLEMENTED, "")


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
        settings=None,
    ):
        self.project = project_store.current
        self.store = project_store
        self.tts = tts_engine
        self.ai_engine = ai_engine
        self._current_desc_idx = 0
        self._playing = False
        self._timer: wx.Timer | None = None
        self._position = 0.0  # Current playback position in seconds
        self._tick_at: float | None = None  # clock of the last position update
        self._volume = 100                  # video sound, 0..100 (v1.9.7)
        self._vlc = None
        self._vlc_instance = None
        self._vlc_media = None
        self._vlc_available = False
        self._paused_by_user = False
        # v1.6.1: held by the app while a description is spoken, which is
        # a different thing from the user pressing Pause — see
        # _pause_for_narration.
        self._auto_paused = False
        # What was playing when the app held the video for a cue.
        self._paused_backend = "none"
        # v1.7.4: share the app's SettingsStore. A second store held a
        # stale snapshot and each one's save overwrote the other's keys
        # (a pause toggle here wiped a new API key saved in Settings).
        self._settings = settings
        if self._settings is None:
            self._settings = getattr(parent, "settings", None)
        if self._settings is None:
            try:
                from ..core.settings_store import SettingsStore
                self._settings = SettingsStore()
            except Exception:  # settings are a nicety here, not a need
                self._settings = None
        # v1.9.0: the agent (F2) lives for this Player session.
        self._agent = None
        self._agent_transcript: list[str] = []
        self._agent_undo: list[list] = []
        self._agent_backup_done = False
        self._narrated: set[int] = set()  # description ids spoken during playback
        self._tts_thread: threading.Thread | None = None
        self._sub_cues: list[Description] = []  # v1.3.0: SRT subtitle cues
        self._audio_proc = None  # v1.4.0: ffplay process for real audio in simulated mode
        self._audio_backend = "none"  # "vlc" | "ffplay" | "none"
        # v1.5.4: change-guards so the 500 ms timer only touches widgets
        # when a value actually changed (keeps the NVDA review buffer stable).
        self._last_time_txt = ""
        self._last_desc_text = ""
        self._last_upcoming_text = ""
        self._last_slider_val = -1
        self._init_vlc()

        super().__init__(parent, title=f"{t('player.title')} — {self.project.name if self.project else ''}",
                         size=(1000, 700))

        self._ensure_duration()
        try:
            self._volume = max(0, min(100, int(
                self._settings.get("player.volume", 100) if self._settings else 100)))
        except (TypeError, ValueError):
            self._volume = 100
        self._build_ui()
        self._refresh_mode_buttons()
        self._load_descriptions()
        self._attach_vlc_video()
        # v1.5.1: VLC attach may learn the real duration (media probe);
        # refresh the slider scale AFTER that so seeks cover the whole
        # video, not just the duration known at UI-build time.
        if self.project and self.project.video_duration:
            self._slider_dur = max(
                0.1, float(self.project.video_duration))
            self.position_slider.SetMax(max(1, int(round(self._slider_dur))))
        # v1.3.0: in simulated mode _attach_vlc_video returns early, so
        # auto-load the project SRT here as well (VLC path loads its own).
        if not self._vlc_available and self.project:
            srt = self._project_srt_path()
            if srt.exists():
                self._load_srt_file(str(srt), silent=True)
        logger.info("PlayerWindow opened (VLC: %s)", self._vlc_available)

    def _init_vlc(self):
        """Try to create a VLC instance. Falls back to simulated playback
        (description walkthrough with timeline) when VLC is unavailable."""
        try:
            import vlc
            self._vlc_instance = vlc.Instance("--no-video-title-show")
            self._vlc = self._vlc_instance.media_player_new()
            self._vlc_available = True
            self._audio_backend = "vlc"
        except Exception as e:
            logger.info("VLC unavailable, using simulated playback: %s", e)
            self._vlc_available = False

    # ── v1.4.0: real audio in simulated mode (no libvlc installed) ──

    def _audio_path(self) -> str:
        """Local media file for the current project, if any."""
        if not self.project or not self.project.video_path:
            return ""
        p = self.project.video_path
        return p if __import__("os").path.exists(p) else ""

    def _ffplay_available(self) -> bool:
        """True if ffplay can be found — bundled copy or PATH.

        v1.6.5: this used to ask shutil.which alone, so the packaged app
        was silent on any machine without a system ffmpeg even though
        ffplay now ships beside it.
        """
        from ..core.tools import tool_available
        return tool_available("ffplay")

    def _start_ffplay(self, seek_seconds: float) -> bool:
        """Start ffplay on the project's local media file (audio with video
        window disabled, ffmpeg's own controls hidden). Returns success."""
        self._tick_at = time.monotonic()   # the sound restarts from here
        self._stop_ffplay()
        media = self._audio_path()
        if not media:
            logger.info("No local media file for this project; the player "
                        "has descriptions but no video audio")
            return False
        if not self._ffplay_available():
            logger.warning(
                "ffplay not found (neither bundled nor on PATH): the "
                "video will be silent.")
            return False
        try:
            import subprocess
            from ..core.tools import find_tool
            cmd = [
                find_tool("ffplay"), "-vn", "-nodisp", "-loglevel", "quiet",
                "-window_title", "omni_audio",
                "-autoexit", "-nostats", "-hide_banner",
                "-volume", str(self._volume),
            ]
            if seek_seconds > 0.5:
                cmd += ["-ss", f"{seek_seconds:.3f}"]
            cmd.append(media)
            self._audio_proc = subprocess.Popen(
                cmd,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self._audio_backend = "ffplay"
            logger.info("Audio via ffplay from %.1fs: %s", seek_seconds, media)
            return True
        except Exception as e:
            logger.warning("ffplay start failed: %s", e)
            self._audio_proc = None
            return False

    def _stop_ffplay(self) -> None:
        """Terminate the ffplay audio process, if running.

        Pause in ffplay mode simply kills the process (instant, verifiable
        silence); resume restarts it at the simulated clock position."""
        if self._audio_proc is not None:
            try:
                self._audio_proc.terminate()
            except Exception:
                pass
            self._audio_proc = None
        if self._audio_backend == "ffplay":
            self._audio_backend = "none"

    def _audio_available(self) -> bool:
        """Real audio (VLC or ffplay) available for the current project?"""
        if self._vlc_available:
            return True
        return bool(self._audio_path()) and self._ffplay_available()

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
            # v1.3.0: auto-load the project's own SRT sidecar (if any) so
            # subtitles appear without any extra steps for the user.
            srt = self._project_srt_path()
            if srt.exists():
                self._load_srt_file(str(srt), add_to_vlc=True, silent=True)
        except Exception as e:
            logger.warning("VLC attach failed: %s", e)
            self._vlc_available = False

    def _project_srt_path(self) -> Path:
        """Path of this project's auto-generated descriptions.srt."""
        vid = self.project.id if self.project else 0
        return self.store.project_dir(vid) / "media" / "descriptions.srt"

    def _load_srt_file(self, path: str, add_to_vlc: bool = False,
                       silent: bool = False):
        """v1.3.0: load an SRT/VTT subtitle file.

        VLC mode: attaches the file to the media so subtitles render on
        the video. Simulated mode: cues are shown over the video panel,
        synced to the simulated playback clock, so the feature works and
        is verifiable without VLC installed.
        """
        try:
            cues = parse_any(path)
        except Exception as e:
            logger.error("SRT parse failed (%s): %s", path, e)
            self._announce(t("player.subtitle_failed"))
            if not silent:
                from ..core.ai_engine import short_error
                wx.MessageBox(t("player.subtitle_error",
                                error=short_error(str(e))),
                              t("player.load_srt"), wx.OK | wx.ICON_ERROR)
            return
        if not cues:
            self._announce(t("player.subtitle_empty"))
            if not silent:
                wx.MessageBox(t("player.subtitle_no_entries"),
                              t("player.load_srt"), wx.OK | wx.ICON_WARNING)
            return
        self._sub_cues = cues
        if add_to_vlc and self._vlc_available and self._vlc_media is not None:
            try:
                import vlc
                self._vlc_media.slaves_add(
                    vlc.SlaveType.subtitle,
                    Path(path).resolve().as_uri(),
                )
            except Exception as e:
                # Non-fatal: simulated overlay still shows the cues.
                logger.warning("VLC slave attach failed: %s", e)
        self._announce(t("player.subtitles_loaded", count=len(cues)))
        logger.info("SRT loaded: %s (%d cues)", path, len(cues))

    def _on_load_srt(self, event):
        """v1.3.0: pick an external SRT/VTT file and load it."""
        dlg = wx.FileDialog(
            self,
            message=t("player.load_srt"),
            wildcard=(f"{t('filter.subtitles')}|*.srt;*.vtt"
                      f"|{t('filter.all_files')}|*.*"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        if dlg.ShowModal() == wx.ID_OK:
            self._load_srt_file(dlg.GetPath())
        dlg.Destroy()

    def _build_ui(self):
        """Build player UI."""
        panel = wx.Panel(self)
        panel.SetName("player_panel")
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        # ── Video Area ─────────────────────────────────────────
        # v1.9.7 (owner): keys in the video area - Space play/pause, Left/
        # Right 5 s, Ctrl 10 s, Ctrl+Shift 1 min, Up/Down volume. WANTS_CHARS so
        # the arrows reach the panel instead of moving the focus.
        self.video_panel = wx.Panel(panel, size=(854, 480),
                                    style=wx.WANTS_CHARS,
                                    name=t("player.video_area"))
        self.video_panel.SetBackgroundColour(wx.Colour(0, 0, 0))
        # v1.3.0: subtitle overlay for simulated playback (no VLC).
        self._sub_overlay = wx.StaticText(
            self.video_panel, label="", name="sub_overlay",
            style=wx.ALIGN_CENTER_HORIZONTAL)
        self._sub_overlay.SetForegroundColour(wx.Colour(255, 255, 255))
        self._sub_overlay.SetFont(self._sub_overlay.GetFont().Bold())
        self._active_sub_text = ""  # unwrapped text currently shown
        vsizer = wx.BoxSizer(wx.VERTICAL)
        vsizer.AddStretchSpacer(1)
        vsizer.Add(self._sub_overlay, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, 25)
        self.video_panel.SetSizer(vsizer)
        sizer.Add(self.video_panel, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        # ── Transport Controls ─────────────────────────────────
        controls = wx.BoxSizer(wx.HORIZONTAL)

        self.play_btn = wx.Button(panel, label=t("player.play"), name="play")
        self.stop_btn = wx.Button(panel, label=t("player.stop"), name="stop_player")

        self.rewind_btn = wx.Button(panel, label="<< 10s", name="rewind")
        self.forward_btn = wx.Button(panel, label="10s >>", name="forward")
        # v1.3.0: manual subtitle loading (SRT/VTT).
        self.load_srt_btn = wx.Button(panel, label=t("player.load_srt"),
                                      name="load_srt")

        # v1.6.1: hold-while-speaking is a preference, not a policy. It
        # lives HERE as well as in Settings because whether it helps
        # depends on the video in front of you — a slide deck needs it,
        # a talking head does not — and changing it should not mean
        # leaving the player. Takes effect on the next cue.
        self.pause_narration_check = wx.CheckBox(
            panel, label=t("player.pause_for_narration"),
            name="pause_for_narration")
        self.pause_narration_check.SetValue(bool(
            self._settings.get("player.pause_for_narration", True)
            if self._settings else True))
        self.pause_narration_check.SetToolTip(
            t("player.pause_for_narration_hint"))
        # v1.6.5: an engine that cannot report when a sentence finished
        # cannot hold the video for it. Disable rather than hide — a
        # checkbox that vanishes leaves the user wondering where the
        # setting went; a disabled one with a reason does not.
        if not self._hold_supported():
            self.pause_narration_check.Enable(False)
            self.pause_narration_check.SetToolTip(
                t("player.pause_unavailable"))

        controls.Add(self.play_btn, 0, wx.ALL, 5)
        controls.Add(self.stop_btn, 0, wx.ALL, 5)
        controls.AddStretchSpacer()
        controls.Add(self.pause_narration_check, 0,
                     wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        controls.Add(self.load_srt_btn, 0, wx.ALL, 5)
        controls.Add(self.rewind_btn, 0, wx.ALL, 5)
        controls.Add(self.forward_btn, 0, wx.ALL, 5)

        sizer.Add(controls, 0, wx.ALL | wx.EXPAND, 5)

        # ── Timeline Slider ────────────────────────────────────
        timeline_row = wx.BoxSizer(wx.HORIZONTAL)
        # v1.5.1: fixed 0..1000 slider range mapped onto the REAL video
        # duration. The old position*10 scale only covered the first 100
        # seconds, so a 9-minute video could not be seeked beyond 1:40.
        self._slider_dur = max(0.1, float(self.project.video_duration or 0.0))
        # v1.7.5: SetLabel below never reached NVDA — heard as "slider 0"
        # (tools/nvda_window_check.py). Windows names a trackbar after the
        # static text created just before it, so that label must exist
        # and must be created first.
        timeline_label = wx.StaticText(panel, label=t("player.timeline") + ":")
        self._timeline_label = timeline_label
        timeline_row.Add(timeline_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        # v1.9.6: one step = one second (was 0..1000 per mille, which NVDA
        # read as a bare number); arrows move 5 s, Page Up/Down 30 s, and
        # the value is spoken as a time ("1:04 of 24:30", owner's request).
        self.position_slider = wx.Slider(
            panel, value=0, minValue=0,
            maxValue=max(1, int(round(self._slider_dur))),
            style=wx.SL_HORIZONTAL, name="timeline")
        self.position_slider.SetLineSize(5)
        self.position_slider.SetPageSize(30)
        self.position_slider.SetAccessible(_TimeSliderAccessible(
            self.position_slider, self._format_time))
        # Accessible name for screen readers: without it NVDA/JAWS announce
        # nothing meaningful for this control.
        self.position_slider.SetLabel(t("player.timeline"))
        self.time_label = wx.StaticText(panel, label="0:00 / 0:00", name="time_display")
        timeline_row.Add(self.position_slider, 1, wx.ALL | wx.EXPAND, 5)
        timeline_row.Add(self.time_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        sizer.Add(timeline_row, 0, wx.ALL | wx.EXPAND, 5)

        # ── Description Display ────────────────────────────────
        desc_box = wx.StaticBox(panel, label=t("player.current_desc"))
        self._desc_box = desc_box
        desc_sizer = wx.StaticBoxSizer(desc_box, wx.VERTICAL)

        self.current_desc_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY,
                                             size=(-1, 80), name="current_description")
        self.current_desc_text.SetValue("")
        desc_sizer.Add(self.current_desc_text, 1, wx.ALL | wx.EXPAND, 5)

        # Upcoming
        upcoming_row = wx.BoxSizer(wx.HORIZONTAL)
        upcoming_label = wx.StaticText(panel, label=t("player.upcoming"), name="upcoming_label")
        self._upcoming_label = upcoming_label
        self.upcoming_text = wx.TextCtrl(panel, style=wx.TE_READONLY, size=(-1, -1),
                                         name="upcoming_description")
        upcoming_row.Add(upcoming_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        upcoming_row.Add(self.upcoming_text, 1, wx.ALL | wx.EXPAND, 5)
        desc_sizer.Add(upcoming_row, 0, wx.EXPAND)

        sizer.Add(desc_sizer, 0, wx.ALL | wx.EXPAND, 10)

        # ── Action Buttons ─────────────────────────────────────
        action_row = wx.BoxSizer(wx.HORIZONTAL)

        self.edit_btn = wx.Button(panel, label=t("editor.title"), name="edit_descriptions")
        # v2.1.0 (owner): the people in the video, one name each.
        self.cast_btn = wx.Button(panel, label=t("player.characters"), name="characters")
        self.ask_btn = wx.Button(panel, label=t("player.ask_more"), name="ask_more")
        self.explore_btn = wx.Button(panel, label=t("player.explore"), name="explore")
        self.agent_btn = wx.Button(panel, label=t("player.agent"), name="agent")
        speaker = chr(0x1F50A)
        self.speak_btn = wx.Button(
            panel, label=speaker + " " + t("player.read_description"),
            name="speak_desc")

        action_row.Add(self.edit_btn, 0, wx.ALL, 5)
        action_row.Add(self.cast_btn, 0, wx.ALL, 5)
        action_row.Add(self.ask_btn, 0, wx.ALL, 5)
        action_row.Add(self.agent_btn, 0, wx.ALL, 5)
        action_row.Add(self.explore_btn, 0, wx.ALL, 5)
        action_row.Add(self.speak_btn, 0, wx.ALL, 5)

        sizer.Add(action_row, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        # ── Status ─────────────────────────────────────────────
        self.status_text = wx.StaticText(panel, label="", name="player_status")
        sizer.Add(self.status_text, 0, wx.ALL, 5)

        # ── Bindings ───────────────────────────────────────────
        self.play_btn.Bind(wx.EVT_BUTTON, self._on_play_toggle)
        self.stop_btn.Bind(wx.EVT_BUTTON, self._on_stop)
        self.rewind_btn.Bind(wx.EVT_BUTTON, self._on_rewind)
        self.forward_btn.Bind(wx.EVT_BUTTON, self._on_forward)
        self.position_slider.Bind(wx.EVT_SLIDER, self._on_seek)
        self.edit_btn.Bind(wx.EVT_BUTTON, self._on_edit)
        self.cast_btn.Bind(wx.EVT_BUTTON, self._on_characters)
        self.ask_btn.Bind(wx.EVT_BUTTON, self._on_ask)
        self.explore_btn.Bind(wx.EVT_BUTTON, self._on_explore)
        self.agent_btn.Bind(wx.EVT_BUTTON, lambda e: self.open_agent())
        # Settings may change the provider or model while the Player is
        # open: the buttons are brought up to date whenever it is active.
        self.Bind(wx.EVT_ACTIVATE, self._on_activate)
        # F2 anywhere in the Player (owner's choice; it had no shortcuts).
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        # F2 as a window accelerator too: Windows translates it before any
        # control sees the key. In the test Player (3 Oct 2026) CHAR_HOOK
        # never ran, so F2 was silent everywhere but the video picture.
        self._agent_key_id = wx.NewIdRef()
        self.Bind(wx.EVT_MENU, lambda e: self.open_agent(), id=self._agent_key_id)
        self.SetAcceleratorTable(wx.AcceleratorTable(
            [(wx.ACCEL_NORMAL, wx.WXK_F2, self._agent_key_id)]))
        # Keys that reach the panel without the window's CHAR_HOOK (a key
        # posted straight to it) are taken here too; a key handled in
        # CHAR_HOOK never arrives, so nothing is done twice.
        self.video_panel.Bind(wx.EVT_KEY_DOWN, self._on_video_key_down)
        self.speak_btn.Bind(wx.EVT_BUTTON, self._on_speak)
        self.pause_narration_check.Bind(wx.EVT_CHECKBOX,
                                        self._on_pause_narration_toggle)
        self.load_srt_btn.Bind(wx.EVT_BUTTON, self._on_load_srt)
        self.Bind(wx.EVT_CLOSE, self._on_close)

        # Start timer (created here so EVT_TIMER binding is already in place)
        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer, self._timer)
        self._start_timer()  # 500ms interval

        panel.Layout()

    def _announce(self, msg: str) -> None:
        """Set status text and move focus so a screen reader reads it.

        v1.6.6: the focus move says nothing on a computer with no
        screen reader at all, which is how someone given this app ends
        up staring at a silent window. speech.announce() speaks the
        message through Prism in exactly that case, and stays quiet
        when a reader is running so nothing is said twice.
        """
        if not self:
            return  # v1.9.6: a worker's CallAfter after the window closed
        if self._video_has_focus():
            self._say_in_video_area(msg)   # v1.9.7: keep the focus there
            return
        self.status_text.SetLabel(msg)
        self.status_text.SetFocus()
        try:
            from ..core.speech import announce as _speak_status
            _speak_status(msg)
        except Exception:
            pass  # an announcement must never break the action itself

    def _say_in_video_area(self, msg: str) -> None:
        """v1.9.7: say msg WITHOUT moving the focus off the video picture.

        _announce moves the focus to the status line so the screen reader
        reads it; after a video key the focus stayed there and the next
        arrow went somewhere else (owner, 2 Oct 2026; real test 3 Oct:
        focus on player_status after the first key). Here the words go
        straight to the screen reader through Prism. Without a voice the
        old way is used and the focus is given back to the picture.
        """
        if not self:
            return
        self.status_text.SetLabel(msg)
        try:
            from ..core.speech import get_speech
            if get_speech().speak(msg, interrupt=True):
                return
        except Exception:
            logger.debug("Prism speak failed", exc_info=True)
        self.status_text.SetFocus()
        wx.CallLater(700, lambda: self and self.video_panel.SetFocus())

    def _speak_queued(self, msg: str) -> None:
        """Say msg after what the screen reader is saying now."""
        if not self:
            return  # a CallLater after the window closed
        try:
            from ..core.speech import get_speech
            if get_speech().speak(msg, interrupt=False):
                return
        except Exception:
            logger.debug("Prism speak failed", exc_info=True)
        # Speech unavailable or refused: only show it on the status line.
        # _announce would move the focus or speak with interrupt=True and
        # cut off what the reader is saying, breaking the queued promise.
        self.status_text.SetLabel(msg)

    def _load_descriptions(self):
        """Load descriptions from current project."""
        if not self.project or not self.project.descriptions:
            self.current_desc_text.SetValue(t("player.no_descriptions"))
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
        else:
            # v1.7.4: past every cue -> the LAST one is current, not the
            # first (the loop used to fall through leaving index 0).
            self._current_desc_idx = len(descs) - 1

        current = descs[self._current_desc_idx]
        # v1.5.4: only touch the widget when the text changed, so the
        # 500 ms timer does not churn the NVDA review buffer.
        if current.text != self._last_desc_text:
            self._last_desc_text = current.text
            self.current_desc_text.SetValue(current.text)

        if self._current_desc_idx + 1 < len(descs):
            upcoming = descs[self._current_desc_idx + 1]
            up_txt = f"[{upcoming.start_time:.1f}s] {upcoming.text[:80]}..."
        else:
            up_txt = t("player.upcoming_end")
        if up_txt != self._last_upcoming_text:
            self._last_upcoming_text = up_txt
            self.upcoming_text.SetValue(up_txt)

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
        txt = f"{pos_str} / {dur_str}"
        if txt != self._last_time_txt:
            self._last_time_txt = txt
            self.time_label.SetLabel(txt)

    @staticmethod
    def _format_time(seconds: float) -> str:
        """1:04 for one minute four seconds; 1:02:05 past an hour
        (v1.9.6, owner: "slider 1:04 untuk 1 minit 4 saat")."""
        total = max(0, int(seconds))
        h, rest = divmod(total, 3600)
        m, sec = divmod(rest, 60)
        return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

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
                self._announce(t("player.ended"))
                self._set_play_label(False)
        elif self._playing:
            # v1.9.6: the time that really passed, not "+0.5 per tick". A
            # wx timer fires late whenever the UI is busy (NVDA speaking,
            # a dialog), so counting ticks fell behind the sound ffplay
            # was playing, and F2 sent the agent an old position.
            now = time.monotonic()
            last = self._tick_at if self._tick_at is not None else now - 0.5
            self._position += max(0.0, now - last)
            self._tick_at = now
        dur = self.project.video_duration if self.project else 0.0
        if dur > 0 and self._position >= dur:
            self._position = dur
            if self._playing:
                self._playing = False
                self._announce(t("player.ended"))
                self._stop_ffplay()
                self._set_play_label(False)
        self._update_desc_display()
        self._update_sub_overlay()
        slider_val = int(self._position)
        if slider_val != self._last_slider_val:
            self._last_slider_val = slider_val
            self.position_slider.SetValue(slider_val)
        self._maybe_narrate()

    def _update_sub_overlay(self):
        """v1.3.0: show the active subtitle cue over the video panel
        during simulated playback (VLC renders its own subtitles)."""
        if self._vlc_available:
            return  # real VLC draws subtitles on the video itself
        if not self._playing or not self._sub_cues:
            if self._active_sub_text:
                self._active_sub_text = ""
                self._sub_overlay.SetLabel("")
                self.video_panel.Refresh()
            return
        pos = self._position
        active = ""
        for cue in self._sub_cues:
            if cue.start_time <= pos < cue.end_time:
                active = cue.text.replace("\n", " ")
                break
        if active != self._active_sub_text:
            self._active_sub_text = active
            self._sub_overlay.SetLabel(active)
            if active:
                # Wrap takes PIXELS: keep a margin inside the video panel.
                self._sub_overlay.Wrap(
                    max(200, self.video_panel.GetSize().GetWidth() - 60))
            self.video_panel.Layout()
            self.video_panel.Refresh()

    def _maybe_narrate(self):
        """Speak the current description aloud when playback reaches it.

        This is the core accessibility path: during video playback the
        description for the current scene must be heard, not only shown.

        v1.5.1: on TTS FAILURE the id is removed from _narrated so the
        cue is RETRIED on the next tick instead of being skipped forever
        (previously a failed Edge TTS call silently dropped the cue);
        speak_and_play itself now falls back to offline SAPI5 instantly.
        """
        if not self._playing or not self.project or not self.project.descriptions:
            return
        desc = self.project.descriptions[self._current_desc_idx]
        if desc.id in self._narrated:
            return
        # v1.7.4: never speak a cue before its start time. Before the
        # first cue the display falls back to cue 0, which used to be
        # narrated at 0:00 for a scene not yet on screen.
        if desc.start_time > self._position:
            return
        if not desc.text.strip():
            return
        self._narrated.add(desc.id)

        desc_text = desc.text
        desc_id = desc.id

        # v1.6.1 extended description (W3C/WAI): hold the video while the
        # cue is spoken. Measured need — reading a slide's bullets took
        # 9.9s into a 5s gap, so three of four cues collided and the
        # listener lost them. Pausing costs a longer runtime; not pausing
        # costs the content itself.
        widget = getattr(self, "pause_narration_check", None)
        if widget is not None:
            pause_for_narration = bool(widget.GetValue())
        else:
            pause_for_narration = bool(self._settings.get(
                "player.pause_for_narration", True)) if self._settings else True
        # v1.6.5: the hold only works for engines that can say when the
        # sentence ended. Asked of the engine every cue, not once at
        # startup, because the user can switch engines while the player
        # is open.
        if pause_for_narration and not self._hold_supported():
            pause_for_narration = False
        auto_paused = False
        if pause_for_narration and self._playing:
            self._pause_for_narration()
            auto_paused = True

        def _narrate_bg():
            try:
                if not self.tts.speak_and_play(desc_text):
                    logger.error("Narration failed for cue %s", desc_id)
                    # v1.5.1: allow a RETRY on the next timer tick.
                    wx.CallAfter(self._narrated.discard, desc_id)
            except Exception as e:
                logger.error("Narration failed: %s", e)
                wx.CallAfter(self._narrated.discard, desc_id)
                wx.CallAfter(lambda: self._announce(t("player.tts_failed")))
            finally:
                if auto_paused:
                    wx.CallAfter(self._resume_after_narration)

        self._tts_thread = threading.Thread(target=_narrate_bg, daemon=True)
        self._tts_thread.start()

    def _hold_supported(self) -> bool:
        """Does the current narration engine support the automatic pause?

        Tolerant of a TTS object that predates the capability so the
        player still runs against an older engine: absent the method,
        assume the hold works, which is how it behaved before v1.6.5.
        """
        check = getattr(self.tts, "supports_narration_hold", None)
        if check is None:
            return True
        try:
            return bool(check())
        except Exception as e:
            logger.warning("Could not ask the TTS engine about the "
                           "narration hold: %s", e)
            return True

    def _on_pause_narration_toggle(self, event):
        """Persist the choice and say what it now does.

        Announced, not just checked: a screen-reader user hears the
        control's new state but not what it means for playback.
        """
        on = bool(self.pause_narration_check.GetValue())
        if self._settings:
            self._settings.set("player.pause_for_narration", on)
        # If they switch it off mid-cue, let the current hold finish
        # rather than resuming into the middle of a sentence.
        self._announce(t("player.pause_on") if on else t("player.pause_off"))

    def _pause_for_narration(self) -> None:
        """Hold playback while a description is spoken.

        Deliberately NOT _do_pause(): that sets _paused_by_user, which
        would make the app treat an automatic hold as the user's own
        choice — the Play button label would flip and the video would
        never resume.
        """
        self._auto_paused = True
        # v1.7.1: timed so the log can say how long the video waited.
        # Without it, "the video did not pause for the description" could
        # not be told apart from "it paused, but too briefly".
        self._hold_started = time.monotonic()
        # v1.6.4: remember what was playing BEFORE stopping it.
        # _stop_ffplay() sets _audio_backend to "none", so the resume
        # path used to test a flag its own pause had just cleared — the
        # video audio died at the first description and never came back
        # for the rest of the session. Narration kept working, which is
        # why it looked like "the player has no sound but descriptions
        # are read".
        self._paused_backend = self._audio_backend
        if self._vlc_available and self._vlc_media is not None:
            try:
                self._vlc.set_pause(1)
            except Exception as e:
                logger.debug("VLC pause for narration failed: %s", e)
        elif self._audio_backend == "ffplay":
            self._stop_ffplay()
        self._timer.Stop()

    def _resume_after_narration(self) -> None:
        """Carry on where the hold started — unless the user intervened.

        If they pressed Pause or Stop while the cue was being read, that
        decision wins: resuming would override a deliberate action.
        """
        if not self:
            return  # v1.9.6: the hold ended after the window closed
        started = getattr(self, "_hold_started", None)
        if started is not None:
            logger.info("Narration hold released after %.2fs (voice: %s)",
                        time.monotonic() - started,
                        getattr(self.tts, "_current_engine", "?"))
            self._hold_started = None
        if not self._auto_paused:
            return
        self._auto_paused = False
        if self._paused_by_user or not self._playing:
            return
        if self._vlc_available and self._vlc_media is not None:
            try:
                self._vlc.set_pause(0)
            except Exception as e:
                logger.debug("VLC resume after narration failed: %s", e)
        elif self._paused_backend == "ffplay":
            # What was playing before the hold, not what is playing now:
            # nothing is, because the hold stopped it.
            if not self._start_ffplay(self._position):
                logger.warning(
                    "Could not restart audio after narration; the video "
                    "will be silent from here")
        self._paused_backend = "none"
        self._start_timer()

    def _on_play_toggle(self, event):
        """v1.4.0: single Play/Pause toggle button."""
        if self._playing:
            self._do_pause()
        else:
            self._do_play()

    def _set_play_label(self, playing: bool) -> None:
        """Toggle button shows the action that WILL happen next."""
        self.play_btn.SetLabel(t("player.pause") if playing else t("player.play"))

    def _ensure_duration(self) -> None:
        """Know the video's length before the timeline is built (v1.9.6).

        "Play Video with Existing Descriptions" created its project
        without a length, so the slider covered 0.1 s and playback never
        ended; found while listening to the new "1:04 of 24:30" slider.
        Measured once with ffprobe and kept in the project."""
        proj = self.project
        if proj is None or proj.video_duration or not proj.video_path:
            return
        try:
            from ..core.timeline_io import _ffprobe_duration
            seconds = float(_ffprobe_duration(proj.video_path) or 0.0)
        except Exception as e:
            logger.info("Could not measure the video length: %s", e)
            return
        if seconds > 0:
            proj.video_duration = seconds
            try:
                if self.store.current is proj:
                    self.store.set_video_duration(seconds)
            except Exception:
                logger.debug("video length not saved", exc_info=True)

    def _start_timer(self) -> None:
        """Start (or restart) the 500 ms timer and the position clock: the
        time spent stopped or held must not be counted as played."""
        self._tick_at = time.monotonic()
        self._timer.Start(500)

    def _do_play(self):
        self._paused_by_user = False
        if self._vlc_available and self._vlc_media is not None:
            self._auto_paused = False
            self._vlc.play()
            self._playing = True
            self._announce(t("player.playing"))
            self._set_play_label(True)
            # v1.7.4: a narration hold stops the timer; if the user
            # paused or stopped during it, nothing else restarts it.
            self._start_timer()
            return
        if not self._playing:
            # v1.4.0: real audio via ffplay when VLC is unavailable but a
            # local media file exists (works without libvlc installed).
            if self._start_ffplay(self._position):
                self._announce(t("player.playing_audio"))
            else:
                self._announce(t("player.playing_sim"))
        self._playing = True
        self._set_play_label(True)
        self._start_timer()

    def _do_pause(self):
        self._paused_by_user = True
        if self._vlc_available and self._vlc_media is not None:
            # v1.7.4: set_pause(1), not pause(): pause() TOGGLES, so
            # pressing Pause during a narration hold (already paused)
            # started the video again.
            self._vlc.set_pause(1)
            self._playing = False
            self._announce(t("player.paused"))
            self._set_play_label(False)
            return
        if self._audio_backend == "ffplay":
            self._stop_ffplay()  # instant, verifiable silence on pause
        self._playing = False
        self._announce(t("player.paused"))
        self._timer.Stop()
        self._set_play_label(False)

    def _on_stop(self, event):
        self._paused_by_user = True
        self._playing = False
        self._narrated.clear()
        if self._vlc_available and self._vlc_media is not None:
            self._vlc.stop()
        self._stop_ffplay()
        self._position = 0.0
        self.position_slider.SetValue(0)
        self._update_desc_display()
        self._update_sub_overlay()
        self._announce(t("player.stopped"))
        self._set_play_label(False)

    def _on_rewind(self, event):
        self._position = max(0, self._position - 10)
        if self._vlc_available and self._vlc_media is not None:
            self._vlc.set_time(int(self._position * 1000))
        elif self._audio_backend == "ffplay":
            self._start_ffplay(self._position)  # restart ffplay at new pos
        self._update_desc_display()
        self._announce_jump(self.rewind_btn)

    def _on_forward(self, event):
        self._position += 10
        if self._vlc_available and self._vlc_media is not None:
            self._vlc.set_time(int(self._position * 1000))
        elif self._audio_backend == "ffplay":
            self._start_ffplay(self._position)  # restart ffplay at new pos
        self._update_desc_display()
        self._announce_jump(self.forward_btn)

    def retranslate(self) -> None:
        """Re-apply every label after a language switch (v1.8.2)."""
        name = self.project.name if self.project else ""
        self.SetTitle(f"{t('player.title')} — {name}")
        self._set_play_label(self._playing if hasattr(self, "_playing") else False)
        self.stop_btn.SetLabel(t("player.stop"))
        self.load_srt_btn.SetLabel(t("player.load_srt"))
        self.pause_narration_check.SetLabel(t("player.pause_for_narration"))
        self.pause_narration_check.SetToolTip(
            t("player.pause_for_narration_hint") if self._hold_supported()
            else t("player.pause_unavailable"))
        self._timeline_label.SetLabel(t("player.timeline") + ":")
        self._desc_box.SetLabel(t("player.current_desc"))
        self._upcoming_label.SetLabel(t("player.upcoming"))
        self.edit_btn.SetLabel(t("editor.title"))
        self.cast_btn.SetLabel(t("player.characters"))
        self.ask_btn.SetLabel(t("player.ask_more"))
        self.explore_btn.SetLabel(t("player.explore"))
        self.agent_btn.SetLabel(t("player.agent"))
        self.speak_btn.SetLabel(chr(0x1F50A) + " " + t("player.read_description"))
        self.video_panel.SetName(t("player.video_area"))
        self.Layout()

    def _announce_jump(self, button) -> None:
        """v1.8.2: the 10-second buttons were silent — heard in a
        keyboard sweep. Say where the jump landed, then give focus back
        to the button so pressing it again jumps again."""
        total = float(getattr(self, "_slider_dur", 0) or 0)
        position = self._format_time(self._position)
        # "of 00:00" when the length is unknown would only confuse.
        self._announce(t("player.position", position=position,
                         total=self._format_time(total)) if total >= 1
                       else position)
        wx.CallLater(700, lambda: button and button.SetFocus())

    def _on_seek(self, event):
        # v1.9.6: the slider value IS the position in seconds.
        self._position = float(self.position_slider.GetValue())
        if self._vlc_available and self._vlc_media is not None:
            self._vlc.set_time(int(self._position * 1000))
        elif self._audio_backend == "ffplay":
            self._start_ffplay(self._position)
        self._update_desc_display()

    def _on_characters(self, event):
        """v2.1.0: Characters window; a rename there reaches the display."""
        from .characters_dialog import CharactersDialog
        if not self.project or self.store.current is None:
            return
        dlg = CharactersDialog(self, self.store,
                               on_descriptions_changed=self._load_descriptions)
        dlg.ShowModal()
        dlg.Destroy()
        self.cast_btn.SetFocus()

    def _on_edit(self, event):
        """Open description editor."""
        from .editor_window import EditorWindow
        editor = EditorWindow(self, self.store, self.tts)
        editor.Show()

    def _on_ask(self, event):
        """Open 'ask more' dialog."""
        from .ask_more_dialog import AskMoreDialog
        dlg = AskMoreDialog(
            self, self.ai_engine,
            descriptions=self.project.descriptions if self.project else None,
            position=self._position,
            video_path=self.project.video_path if self.project else "")
        dlg.ShowModal()
        dlg.Destroy()

    # ── The agent (v1.9.0) ─────────────────────────────────────
    def _on_activate(self, event):
        if event.GetActive():
            wx.CallAfter(self._refresh_mode_buttons)
        event.Skip()

    def _refresh_mode_buttons(self) -> None:
        """Agent OR Ask More + Explore Scene (owner, 2 Oct 2026).

        Agent ready  -> only "Agent (F2)": it can look at frames and answer
                        questions, so the two older tools are hidden.
        Not tested   -> all three; once Test agent mode passes, the two
                        older tools go away.
        No agent     -> Ask More and Explore Scene; no Agent button.
        """
        if not self:
            return
        ok, why = self.agent_available()
        show_agent = ok or why == "untested"
        show_old = not ok
        changed = False
        for btn, show in ((self.agent_btn, show_agent),
                          (self.ask_btn, show_old),
                          (self.explore_btn, show_old)):
            if btn.IsShown() != show:
                if not show and btn.HasFocus():
                    self.play_btn.SetFocus()
                btn.Show(show)
                changed = True
        if changed:
            self.agent_btn.GetParent().Layout()

    # ── v1.9.7: keys in the video area (owner's request) ──────────

    def _video_has_focus(self) -> bool:
        focus = wx.Window.FindFocus()
        while focus is not None:
            if focus is self.video_panel:
                return True
            focus = focus.GetParent()
        return False

    def _on_video_key(self, event) -> bool:
        """True when the key was one of the video-area keys (handled)."""
        code = event.GetKeyCode()
        ctrl = event.ControlDown()
        if code == wx.WXK_SPACE and not event.HasAnyModifiers():
            self._on_play_toggle(None)
        elif code in (wx.WXK_LEFT, wx.WXK_RIGHT):
            # 5 s; Ctrl 10 s; Ctrl+Shift one minute (owner, 2 Oct 2026)
            step = 60 if (ctrl and event.ShiftDown()) else 10 if ctrl else 5
            self._seek_by(-step if code == wx.WXK_LEFT else step)
        elif code in (wx.WXK_UP, wx.WXK_DOWN) and not event.HasAnyModifiers():
            self._change_volume(10 if code == wx.WXK_UP else -10)
        else:
            return False
        return True

    def _seek_by(self, delta: float) -> None:
        """Jump by delta seconds and say where the video is now."""
        total = float(self._slider_dur or 0)
        pos = self._position + delta
        pos = max(0.0, min(pos, total)) if total > 0 else max(0.0, pos)
        self._position = pos
        if self._vlc_available and self._vlc_media is not None:
            self._vlc.set_time(int(pos * 1000))
        elif self._audio_backend == "ffplay" and self._playing:
            self._restart_sound_soon()
        self.position_slider.SetValue(int(pos))
        self._update_desc_display()
        self._announce(t("player.slider_value",
                         position=self._format_time(pos),
                         total=self._format_time(total)))

    def _change_volume(self, delta: int) -> None:
        """Video sound only; the screen reader's voice is not touched."""
        self._volume = max(0, min(100, self._volume + delta))
        if self._settings is not None:
            try:
                self._settings.set("player.volume", self._volume)
            except Exception:
                logger.debug("volume not saved", exc_info=True)
        if self._vlc_available and self._vlc is not None:
            try:
                self._vlc.audio_set_volume(self._volume)
            except Exception:
                logger.debug("VLC volume failed", exc_info=True)
        elif self._audio_backend == "ffplay" and self._playing:
            self._restart_sound_soon()           # ffplay takes it at start
        self._announce(t("player.volume", pct=self._volume))

    def _restart_sound_soon(self) -> None:
        """ffplay only takes the volume and the start point when it starts.
        Restarting it on every key made quick presses stutter and miss
        (owner, 2 Oct 2026): restart once, 0.35 s after the last key."""
        timer = getattr(self, "_sound_timer", None)
        if timer is not None and timer.IsRunning():
            timer.Stop()
        self._sound_timer = wx.CallLater(350, self._restart_sound_now)

    def _restart_sound_now(self) -> None:
        if self and self._playing and self._audio_backend == "ffplay":
            self._start_ffplay(self._position)

    def _on_video_key_down(self, event):
        if self._on_video_key(event):
            return
        if event.GetKeyCode() == wx.WXK_F2 and not event.HasAnyModifiers():
            # F2 was silent on the video picture (owner, 3 Oct 2026): the
            # panel takes every key, so it never reached the window's
            # CHAR_HOOK. Taken here too; a key CHAR_HOOK handled never
            # arrives, so the agent is not opened twice.
            self.open_agent()
            return
        if event.GetKeyCode() == wx.WXK_TAB and not event.ControlDown():
            # WANTS_CHARS gives the panel Tab too, so Windows no longer
            # moves on by itself: Tab seemed dead (owner, 3 Oct 2026).
            flags = wx.NavigationKeyEvent.FromTab | (
                wx.NavigationKeyEvent.IsBackward if event.ShiftDown()
                else wx.NavigationKeyEvent.IsForward)
            self.video_panel.Navigate(flags)
            return
        event.Skip()

    def _on_char_hook(self, event):
        if event.GetKeyCode() == wx.WXK_F2 and not event.HasAnyModifiers():
            self.open_agent()
            return
        # v1.9.7: the video-area keys are taken HERE, before Windows uses
        # the arrows to move between controls. As EVT_KEY_DOWN on the panel
        # (first try) the arrows mostly moved the focus to a button and the
        # volume changed only now and then (owner, 2 Oct 2026).
        if self._video_has_focus() and self._on_video_key(event):
            return
        event.Skip()

    def agent_available(self) -> tuple[bool, str]:
        """(ok, why not): OpenRouter or Gemini (v1.9.2), a key, a model
        that passed Settings > Test agent mode, and a video to look at."""
        import os
        st = self._settings
        if st is None:
            return False, "settings"
        from ..core.agent import AGENT_PROVIDERS
        provider = st.get("ai.default_provider", "") or ""
        if provider not in AGENT_PROVIDERS:
            return False, "provider"
        cfg = st.get_ai_provider(provider) or {}
        if not cfg.get("api_key"):
            return False, "key"
        passed = st.get("ai.agent_models", []) or []
        if (cfg.get("model") or "") not in passed:
            return False, "untested"
        if not (self.project and self.project.video_path
                and os.path.exists(self.project.video_path)):
            return False, "video"
        return True, ""

    def _make_agent(self):
        from ..core.agent import Agent, Context
        from ..i18n.strings import I18n
        provider = self._settings.get("ai.default_provider", "") or "glm"
        cfg = self._settings.get_ai_provider(provider)
        proj = self.project
        folder = self.store.project_dir(proj.id)
        # Answers follow the app language (owner's choice).
        language = I18n.ai_language_name(I18n.current_language()) or "English"
        ctx = Context(
            video=proj.video_path,
            length=float(proj.video_duration or self._slider_dur or 0),
            descriptions=[(d.start_time, d.text) for d in proj.descriptions],
            get_position=lambda: float(self._position),
            seek=lambda at: wx.CallAfter(self.seek_to, at),
            get_transcript=lambda: self._transcript_for_agent(folder),
            characters_file=str(folder / "characters.json"),
            language=language)
        return Agent(cfg["api_key"], cfg.get("model", ""), ctx,
                     provider=provider)

    def _transcript_for_agent(self, folder):
        """Worker thread: the project's transcript, made once and kept in
        the project folder (it is not stored anywhere else)."""
        import asyncio
        import json
        from types import SimpleNamespace
        cache = folder / "media" / "transcript.json"
        if cache.exists():
            try:
                return [SimpleNamespace(**seg) for seg in
                        json.loads(cache.read_text(encoding="utf-8"))]
            except (ValueError, TypeError):
                pass
        from ..core.video_processor import VideoProcessor
        video = self.project.video_path
        # The agent calls this from INSIDE its own running event loop, so
        # the transcript gets a loop of its own on a helper thread ("Cannot
        # run the event loop while another loop is running" — heard in the
        # first NVDA listening run, v1.9.0).
        got: dict = {}

        def work():
            loop = asyncio.new_event_loop()
            try:
                got["segs"] = loop.run_until_complete(
                    VideoProcessor().get_transcript(video, local_path=video,
                                                    cache_path=cache))
            except Exception as e:
                got["error"] = e
            finally:
                loop.close()
        import threading
        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        worker.join()
        if "error" in got:
            raise got["error"]
        segs = got.get("segs") or []
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(
                [{"start": s.start, "end": s.end, "text": s.text} for s in segs],
                ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return segs

    def seek_to(self, seconds: float) -> None:
        if not self:
            return  # the agent's CallAfter after the window closed
        dur = float(self._slider_dur or 0)
        self._position = max(0.0, min(float(seconds), dur or float(seconds)))
        if self._vlc_available and self._vlc_media is not None:
            self._vlc.set_time(int(self._position * 1000))
        elif self._audio_backend == "ffplay" and self._playing:
            self._start_ffplay(self._position)
        if dur > 0:
            self.position_slider.SetValue(int(self._position))
        self._update_desc_display()

    def open_agent(self) -> None:
        """F2: the agent, or Ask More (with the frame) when this model has
        not passed Test agent mode (owner's rule)."""
        ok, why = self.agent_available()
        if not ok:
            logger.info("Agent not available: %s", why)
            if why == "untested" and self._offer_agent_test():
                return          # the test runs; the agent opens if it passes
            msg = t(f"agent.unavailable_{why}")
            if why in ("untested", "provider"):
                # Ask More takes the focus at once, so a focus-move
                # announcement was never heard (real test 3 Oct 2026):
                # the reason is spoken once the dialog is up.
                self.status_text.SetLabel(msg)
                wx.CallLater(900, self._speak_queued, msg)
                self._on_ask(None)
            else:
                self._announce(msg)
            return
        self._open_agent_dialog()

    def _offer_agent_test(self) -> bool:
        """v1.9.6: the owner changed model and F2 only said "not
        available" — the test lived in Settings. Offer it right here.
        True when the test was started (its result opens the agent)."""
        from .dialogs import ask_yes_no
        provider = self._settings.get("ai.default_provider", "") or ""
        cfg = self._settings.get_ai_provider(provider) or {}
        model = cfg.get("model", "") or ""
        if not model or not cfg.get("api_key"):
            return False
        if not ask_yes_no(self, t("agent.offer_test", model=model),
                          t("agent.title")):
            return False
        self._announce(t("settings.testing_agent", model=model))
        key = cfg["api_key"]

        def work():
            import asyncio
            from ..core.agent import probe
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    probe(key, model, provider=provider))
            except Exception as e:
                logger.warning("Agent test failed: %s", e)
                result = {"ok": False, "error": str(e)}
            finally:
                loop.close()
            wx.CallAfter(self._agent_test_done, model, result)
        import threading
        threading.Thread(target=work, daemon=True).start()
        return True

    def _agent_test_done(self, model: str, result: dict) -> None:
        if not self:
            return
        passed = list(self._settings.get("ai.agent_models", []) or [])
        if result.get("ok"):
            if model not in passed:
                passed.append(model)
                self._settings.set("ai.agent_models", passed)
            self._announce(t("settings.agent_pass", model=model))
            self._refresh_mode_buttons()
            self._open_agent_dialog()
            return
        from ..core.ai_engine import user_error_text
        self._announce(
            t("settings.agent_error", model=model,
              error=user_error_text(result["error"]))
            if result.get("error") else t("settings.agent_fail", model=model))
        self._on_ask(None)

    def _open_agent_dialog(self) -> None:
        was_playing = bool(self._playing)
        if was_playing:
            self._do_pause()
        try:
            if self._agent is None:
                self._agent = self._make_agent()
            from .agent_dialog import AgentDialog
            dlg = AgentDialog(self, self._agent)
            dlg.ShowModal()
            dlg.Destroy()
        except Exception as e:
            logger.error("Agent failed to open: %s", e)
            from ..core.ai_engine import user_error_text
            self._announce(t("agent.error", error=user_error_text(str(e))))
        finally:
            if was_playing:
                self._do_play()

    def can_undo_agent(self) -> bool:
        return bool(self._agent_undo)

    def apply_agent_changes(self, proposals) -> int:
        """Apply ACCEPTED proposals to this project's own descriptions.

        Before the first change of the session the project's SRT is copied
        aside; each batch can be undone. A subtitle file loaded from
        elsewhere (Load SRT) is never written to.
        """
        import copy
        import shutil
        import time as _time
        from ..core.project_store import Description
        proj = self.project
        if not proj or not proposals:
            return 0
        descs = proj.descriptions
        self._agent_undo.append(copy.deepcopy(descs))
        srt = self._project_srt_path()
        if not self._agent_backup_done and srt.exists():
            backup = srt.with_name(
                f"descriptions.before-agent-{_time.strftime('%Y%m%d-%H%M%S')}.srt")
            try:
                shutil.copy2(srt, backup)
                self._agent_backup_done = True
            except OSError as e:
                logger.warning("SRT backup failed: %s", e)
        by_index = list(descs)
        remove, applied = set(), 0
        for p in proposals:
            target = (by_index[p.index] if p.index is not None
                      and 0 <= p.index < len(by_index) else None)
            if p.action == "edit" and target is not None and p.text:
                target.text, target.edited = p.text, True
            elif p.action == "move" and target is not None and p.time is not None:
                length = max(0.5, target.end_time - target.start_time)
                target.start_time = float(p.time)
                target.end_time = float(p.time) + length
                target.edited = True
            elif p.action == "remove" and target is not None:
                remove.add(id(target))
            elif p.action == "rename" and p.old and p.text:
                # v2.1.0: one proposal, every description; the name goes
                # into the cast too, as the person's (never changed by AI).
                from ..core import characters as ch
                texts, changed = ch.rename_in_texts([d.text for d in descs],
                                                    p.old, p.text)
                if not changed:
                    continue
                for d, new_text in zip(descs, texts):
                    if d.text != new_text:
                        d.text, d.edited = new_text, True
                folder = self.store.project_dir(proj.id)
                cast = [c for c in ch.load_cast(folder)
                        if c["name"].casefold() not in (p.old.casefold(), p.text.casefold())]
                look = next((c.get("look", "") for c in ch.load_cast(folder)
                             if c["name"].casefold() == p.old.casefold()), "")
                ch.save_cast(folder, [{"name": p.text, "look": look, "by_user": True}] + cast)
            elif p.action == "add" and p.time is not None and p.text:
                from ..core.timeline_io import WORDS_PER_SECOND_AT_1X
                words = len(p.text.split())
                descs.append(Description(
                    start_time=float(p.time),
                    end_time=float(p.time) + max(2.0, words / WORDS_PER_SECOND_AT_1X),
                    text=p.text, edited=True))
            else:
                continue
            applied += 1
        proj.descriptions = sorted((d for d in descs if id(d) not in remove),
                                   key=lambda d: d.start_time)
        self._save_agent_descriptions()
        return applied

    def undo_agent_changes(self) -> bool:
        if not self._agent_undo or not self.project:
            return False
        self.project.descriptions = self._agent_undo.pop()
        self._save_agent_descriptions()
        return True

    def _save_agent_descriptions(self) -> None:
        proj = self.project
        self.store.save_descriptions(proj.descriptions)
        try:
            from ..core.timeline_io import to_srt
            srt = self._project_srt_path()
            srt.parent.mkdir(parents=True, exist_ok=True)
            srt.write_text(to_srt(proj.descriptions), encoding="utf-8")
        except Exception as e:
            logger.warning("Project SRT rewrite failed: %s", e)
        if self._agent is not None:
            self._agent.ctx.descriptions = [(d.start_time, d.text)
                                            for d in proj.descriptions]
        self._narrated.clear()
        self._update_desc_display()

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
        self._announce(t("player.speaking"))
        self.tts.stop()

        def _speak_bg():
            try:
                if self.tts.speak_and_play(desc_text):
                    wx.CallAfter(lambda: self._announce(t("player.spoken")))
                else:
                    wx.CallAfter(lambda: self._announce(t("player.tts_failed")))
            except Exception as e:
                # Capture the text eagerly: the except variable is deleted
                # when the block exits, before the lambda runs. v1.9.6:
                # through user_error_text — an edge-tts error can carry
                # its wss:// URL with the TrustedClientToken.
                logger.error("Speak failed: %s", e)
                from ..core.ai_engine import user_error_text
                err = user_error_text(str(e))
                wx.CallAfter(lambda: self._announce(t("player.tts_error", error=err)))

        __import__("threading").Thread(target=_speak_bg, daemon=True).start()

    def _on_close(self, event):
        self._playing = False
        # v1.7.4: an open editor is a child frame; Destroy() below would
        # take it down without its EVT_CLOSE, losing unsaved edits.
        from .editor_window import EditorWindow
        for child in list(self.GetChildren()):
            if isinstance(child, EditorWindow):
                try:
                    child.save_edits()
                except Exception as e:
                    logger.error("Saving editor on player close failed: %s", e)
        if self._agent is not None:
            try:
                self._agent.close()      # its frames; memory ends here
            except Exception:
                pass
            self._agent = None
        self.tts.stop()
        self._stop_ffplay()
        if self._vlc_available and self._vlc is not None:
            try:
                self._vlc.stop()
            except Exception:
                pass
        if self._timer:
            self._timer.Stop()
        self.Destroy()
