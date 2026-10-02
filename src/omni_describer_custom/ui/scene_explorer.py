"""
Omni Describer Custom — Scene Explorer.

Navigate video frames with keyboard, get AI descriptions.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

import wx

from ..core.ai_engine import AIEngine, short_error, user_error_text
from ..core.prompt_manager import PromptManager
from ..core.video_processor import VideoProcessor, SourceError
from ..i18n.strings import I18n, t

logger = logging.getLogger(__name__)


class SceneExplorer(wx.Frame):
    """
    Scene explorer: browse frames with arrow keys,
    get AI descriptions with D/L/Enter/Escape shortcuts.
    """

    def __init__(self, parent, ai_engine: AIEngine | None, video_path: str):
        self.ai = ai_engine
        self.video_path = video_path
        self.frames: list[dict] = []
        self._current_idx = 0
        self._frames_dir = ""
        self._prompt_mgr: PromptManager | None = None
        self._describing = False  # reentrancy guard for the D key
        # v1.9.6: set by _on_close; stops the frame extraction (and a
        # URL's download) and tells the worker to delete its temp folder.
        self._closing = False
        self._loading = False

        super().__init__(parent, title=t("explorer.title"), size=(900, 700))

        self._build_ui()
        if video_path and os.path.exists(video_path):
            self._load_frames_async()
        else:
            self._load_sample_frames()

        self.SetFocus()
        logger.info("SceneExplorer opened")

    def _build_ui(self):
        """Build scene explorer UI."""
        panel = wx.Panel(self)
        panel.SetName("explorer_panel")
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        # Instructions
        help_text = (
            f"{t('explorer.arrow_keys')} | "
            f"{t('explorer.d_key')} | "
            f"{t('explorer.l_key')} | "
            f"{t('explorer.enter_key')} | "
            f"{t('explorer.esc_key')}"
        )
        help_bar = wx.StaticText(panel, label=help_text, name="help_bar")
        help_bar.SetBackgroundColour(wx.Colour(240, 240, 240))
        sizer.Add(help_bar, 0, wx.ALL | wx.EXPAND, 5)

        # Frame display
        self.frame_display = wx.StaticBitmap(panel, size=(854, 480), name="frame_display")
        self.frame_display.SetBackgroundColour(wx.Colour(0, 0, 0))
        sizer.Add(self.frame_display, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        # Frame info
        self.frame_info = wx.StaticText(
            panel, label=t("scene.frame_info", index=0, total=0),
            name="frame_info")
        sizer.Add(self.frame_info, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        # Description area
        desc_box = wx.StaticBox(panel, label=t("explorer.description"))
        desc_sizer = wx.StaticBoxSizer(desc_box, wx.VERTICAL)

        self.desc_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY,
                                     size=(-1, 100), name="scene_description")
        desc_sizer.Add(self.desc_text, 1, wx.ALL | wx.EXPAND, 5)
        sizer.Add(desc_sizer, 0, wx.ALL | wx.EXPAND, 10)

        # Objects list — v1.8.2: labelled; NVDA read nothing here.
        sizer.Add(wx.StaticText(panel, label=t("explorer.objects_label"),
                                name="objects_label"), 0, wx.LEFT, 10)
        self.objects_text = wx.TextCtrl(panel, style=wx.TE_READONLY, size=(-1, 60),
                                        name="objects_list")
        sizer.Add(self.objects_text, 0, wx.ALL | wx.EXPAND, 10)

        # Status — TWO labels taking turns (v1.8.2). NVDA speaks when
        # focus MOVES; arrowing through frames announced into the label
        # that already had focus, so after the first frame it said
        # nothing. Each announcement now focuses the other label.
        self.status_text = wx.StaticText(panel, label=t("status.ready"), name="explorer_status")
        sizer.Add(self.status_text, 0, wx.ALL, 5)
        self._status_alt = wx.StaticText(panel, label="", name="explorer_status_alt")
        sizer.Add(self._status_alt, 0, wx.ALL, 5)
        self._status_alt.Hide()

        # Key bindings (EVT_CHAR_HOOK so arrows/D/L/Enter/Esc still work
        # while focus sits inside the readonly text controls)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)
        self.Bind(wx.EVT_CLOSE, self._on_close)
        panel.SetFocus()

        panel.Layout()

    def _announce(self, msg: str) -> None:
        """Set status text and move focus so a screen reader reads it.

        v1.6.6: the focus move says nothing on a computer with no
        screen reader at all, which is how someone given this app ends
        up staring at a silent window. speech.announce() speaks the
        message through Prism in exactly that case, and stays quiet
        when a reader is running so nothing is said twice.
        """
        if not self or self._closing:
            return  # v1.9.6: a worker's CallAfter after the window closed
        shown, hidden = self.status_text, self._status_alt
        if wx.Window.FindFocus() is shown:
            shown, hidden = hidden, shown
        hidden.Hide()
        shown.SetLabel(msg)
        shown.Show()
        shown.GetParent().Layout()
        shown.SetFocus()
        try:
            from ..core.speech import announce as _speak_status
            _speak_status(msg)
        except Exception:
            pass  # an announcement must never break the action itself

    def _set_text(self, ctrl_name: str, text: str) -> None:
        """SetValue from a worker's CallAfter, only while the window is
        alive (v1.9.6: closing during a describe raised RuntimeError)."""
        if not self or self._closing:
            return
        ctrl = getattr(self, ctrl_name, None)
        if ctrl:
            ctrl.SetValue(text)

    def _default_prompt(self) -> str:
        """Per-language default AI prompt, consistent with MainFrame.

        SceneExplorer receives no settings store, so PromptManager uses
        the app default SettingsStore; its language follows the current
        I18n language so BM users get the BM prompt (I18n has no public
        language getter, hence the guarded read of the class attribute)."""
        if self._prompt_mgr is None:
            self._prompt_mgr = PromptManager()
            self._prompt_mgr.language = getattr(I18n, "_current_lang", "en")
        return self._prompt_mgr.get_default_prompt()

    def _load_frames_async(self):
        """Load frames from video WITHOUT blocking the UI thread.

        ffmpeg extraction can take seconds to minutes; running it on the
        UI thread made the window appear frozen (bad for screen reader
        users who cannot see a hung window).
        """
        self._announce(t("scene.loading"))
        self._loading = True
        import asyncio, tempfile
        fps = self._frames_per_second(self.video_path)

        def run():
            vp = VideoProcessor()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            tmp = tempfile.mkdtemp(prefix="odc_explorer_")
            error_msg = ""
            try:
                self.frames = [
                    {"path": f.path, "time": f.timestamp}
                    for f in loop.run_until_complete(vp.extract_frames(
                        self.video_path, fps=fps, output_dir=tmp,
                        is_cancelled=lambda: self._closing))
                ]
            except SourceError as e:
                # Real reason: bad URL, private video, network failure...
                logger.error("Source error: %s", e)
                # Not an AI error: shortened only (no URL, no JSON).
                error_msg = short_error(str(e))
                self.frames = []
            except Exception as e:
                logger.error("Frame loading error: %s", e)
                self.frames = []
            finally:
                loop.close()
                if self._closing:
                    # v1.9.6: the window closed while extracting; it
                    # never learned this folder, so it is deleted here.
                    import shutil
                    shutil.rmtree(tmp, ignore_errors=True)
            if self._closing:
                return
            # Always notify the UI thread, success or failure
            wx.CallAfter(self._frames_loaded, self.frames, tmp, error_msg)
        threading.Thread(target=run, daemon=True).start()

    # About this many frames at most: 2 a second for a short video, fewer
    # for a long one (a 24-minute film took minutes at 2 fps, and the owner
    # asked for a description before it had finished).
    MAX_FRAMES = 600

    @classmethod
    def _frames_per_second(cls, video_path: str) -> float:
        if not video_path or "://" in video_path:
            return 2.0
        try:
            from ..core.timeline_io import _ffprobe_duration
            seconds = float(_ffprobe_duration(video_path) or 0.0)
        except Exception:
            seconds = 0.0
        if seconds <= cls.MAX_FRAMES / 2:
            return 2.0
        return max(0.1, round(cls.MAX_FRAMES / seconds, 3))

    def _frames_loaded(self, frames: list[dict], frames_dir: str, error_msg: str = ""):
        """Called on the UI thread when background extraction finishes."""
        if not self or self._closing:
            import shutil
            shutil.rmtree(frames_dir, ignore_errors=True)
            return
        self._loading = False
        self.frames = frames
        self._frames_dir = frames_dir
        if self.frames:
            self._show_frame(0)
        elif error_msg:
            self._announce(t("scene.error", msg=error_msg))
        else:
            self._announce(t("scene.no_frames"))

    def _load_sample_frames(self):
        """No video available — leave frame list empty and inform the user."""
        self.frames = []
        self.frame_info.SetLabel(t("scene.frame_info", index=0, total=0))
        self.status_text.SetLabel(
            t("scene.no_video_loaded")
        )
        logger.info("SceneExplorer opened without a video source")

    def _show_frame(self, idx: int):
        """Display frame at index."""
        if not self.frames or idx < 0 or idx >= len(self.frames):
            return
        self._current_idx = idx
        frame = self.frames[idx]

        # Load image
        try:
            from PIL import Image
            img = Image.open(frame["path"])
            # Resize to fit
            img.thumbnail((854, 480))
            wx_image = _pil_to_wx(img)
            self.frame_display.SetBitmap(wx_image)
        except Exception as e:
            logger.error("Frame display error: %s", e)

        self.frame_info.SetLabel(
            f"{t('scene.frame_info', index=idx + 1, total=len(self.frames))}"
            f" | {frame['time']:.1f}s"
        )
        self.desc_text.SetValue("")
        self.objects_text.SetValue("")
        # v1.8.2: arrows were silent — say which frame this is.
        self._announce(self.frame_info.GetLabel())

    def _on_key(self, event):
        """Handle keyboard shortcuts."""
        key = event.GetKeyCode()

        if key == wx.WXK_LEFT:
            self._show_frame(max(0, self._current_idx - 1))
        elif key == wx.WXK_RIGHT:
            self._show_frame(min(len(self.frames) - 1, self._current_idx + 1))
        elif key == ord('D') or key == ord('d'):
            self._describe_frame()
        elif key == ord('L') or key == ord('l'):
            self._list_objects()
        elif key == wx.WXK_RETURN:
            self._describe_nearest()
        elif key == wx.WXK_ESCAPE:
            self.Close()
        elif key == wx.WXK_TAB:
            # v1.8.2: the read-only multi-line Description box kept Tab
            # to itself, so the objects box could never be reached by
            # keyboard; Navigate() from here moved nothing either. The
            # window has two boxes to read, so Tab cycles between them.
            boxes = [self.desc_text, self.objects_text]
            focused = wx.Window.FindFocus()
            step = -1 if event.ShiftDown() else 1
            index = boxes.index(focused) + step if focused in boxes else 0
            boxes[index % len(boxes)].SetFocus()
        else:
            event.Skip()

    def _ready_to_ask(self) -> bool:
        """v1.9.6 (owner): "No AI configured" was said whenever there were
        no frames yet - while a long video was still loading, the AI was
        fine. Each case now has its own words."""
        if not self.ai:
            self._announce(t("scene.no_ai"))
            return False
        if self._loading:
            self._announce(t("scene.still_loading"))
            return False
        if not self.frames:
            self._announce(t("scene.no_frames"))
            return False
        return True

    def _describe_frame(self):
        """Get full AI description of current frame."""
        if not self._ready_to_ask():
            return

        if self._describing:
            return  # a describe thread is already running (D key guard)
        self._describing = True
        frame = self.frames[self._current_idx]
        self._announce(t("scene.analyzing"))
        self.desc_text.SetValue(t("scene.analyzing"))
        wx.Yield()

        prompt = self._default_prompt()

        def run():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.ai.describe_frame(frame["path"], prompt)
                )
                wx.CallAfter(self._set_text, "desc_text", result)
                wx.CallAfter(self._announce, t("status.ready"))
            except Exception as e:
                logger.error("Describe frame failed: %s", e)
                said = user_error_text(str(e))
                wx.CallAfter(self._set_text, "desc_text",
                             t("scene.error", msg=said))
                wx.CallAfter(self._announce, t("status.error", error=said))
            finally:
                loop.close()
                wx.CallAfter(self._describe_done)

        threading.Thread(target=run, daemon=True).start()

    def _list_objects(self):
        """List objects in current frame."""
        if not self._ready_to_ask():
            return
        frame = self.frames[self._current_idx]
        self._announce(t("scene.detecting"))

        def run():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.ai.describe_frame(frame["path"], t("scene.objects_prompt"))
                )
                wx.CallAfter(self._set_text, "objects_text", result)
            except Exception as e:
                logger.error("List objects failed: %s", e)
                wx.CallAfter(self._set_text, "objects_text",
                             t("scene.error", msg=user_error_text(str(e))))
            finally:
                loop.close()

        threading.Thread(target=run, daemon=True).start()

    def _describe_done(self) -> None:
        if self:
            self._describing = False

    def _describe_nearest(self):
        """Describe the nearest detected object."""
        self._describe_frame()  # For now, same as full description

    def _on_close(self, event):
        """Clean up extracted frames temp dir and close."""
        # v1.9.6: stops a running extraction; its worker deletes the
        # folder this window has not been told about yet.
        self._closing = True
        if self._frames_dir:
            import shutil
            shutil.rmtree(self._frames_dir, ignore_errors=True)
            self._frames_dir = ""
        self.Destroy()


def _pil_to_wx(img) -> wx.Bitmap:
    """Convert PIL Image to wx.Bitmap via raw pixel data.

    The previous PNG-bytes round trip failed because wx.Image(bytes)
    interprets its first argument as a filename, raising a confusing
    utf-8 decode error and leaving the frame display permanently blank.
    """
    img_rgb = img.convert("RGB")
    wx_image = wx.Image(img_rgb.size[0], img_rgb.size[1])
    wx_image.SetData(img_rgb.tobytes())
    return wx.Bitmap(wx_image)
