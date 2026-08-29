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

from ..core.ai_engine import AIEngine
from ..core.video_processor import VideoProcessor
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

        super().__init__(parent, title=t("explorer.title"), size=(900, 700))

        self._build_ui()
        if video_path and os.path.exists(video_path):
            self._load_frames()
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
        self.frame_info = wx.StaticText(panel, label="Frame 0 / 0", name="frame_info")
        sizer.Add(self.frame_info, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        # Description area
        desc_box = wx.StaticBox(panel, label=t("explorer.description"))
        desc_sizer = wx.StaticBoxSizer(desc_box, wx.VERTICAL)

        self.desc_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY,
                                     size=(-1, 100), name="scene_description")
        desc_sizer.Add(self.desc_text, 1, wx.ALL | wx.EXPAND, 5)
        sizer.Add(desc_sizer, 0, wx.ALL | wx.EXPAND, 10)

        # Objects list
        self.objects_text = wx.TextCtrl(panel, style=wx.TE_READONLY, size=(-1, 60),
                                        name="objects_list")
        sizer.Add(self.objects_text, 0, wx.ALL | wx.EXPAND, 10)

        # Status
        self.status_text = wx.StaticText(panel, label=t("status.ready"), name="explorer_status")
        sizer.Add(self.status_text, 0, wx.ALL, 5)

        # Key bindings
        self.Bind(wx.EVT_KEY_DOWN, self._on_key)
        panel.SetFocus()

        panel.Layout()

    def _load_frames(self):
        """Load frames from video."""
        import asyncio, tempfile
        vp = VideoProcessor()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        tmp = tempfile.mkdtemp(prefix="odc_explorer_")
        try:
            self.frames = [
                {"path": f.path, "time": f.timestamp}
                for f in loop.run_until_complete(vp.extract_frames(self.video_path, fps=2, output_dir=tmp))
            ]
        except Exception as e:
            logger.error("Frame loading error: %s", e)
            self._load_sample_frames()
        finally:
            loop.close()

        if self.frames:
            self._show_frame(0)

    def _load_sample_frames(self):
        """No video available — leave frame list empty and inform the user."""
        self.frames = []
        self.frame_info.SetLabel("Frame 0 / 0")
        self.status_text.SetLabel(
            "No video loaded. Open a project or process a video first."
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
            f"Frame {idx + 1} / {len(self.frames)} | {frame['time']:.1f}s"
        )
        self.desc_text.SetValue("")
        self.objects_text.SetValue("")
        self.status_text.SetLabel(t("status.ready"))

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
        else:
            event.Skip()

    def _describe_frame(self):
        """Get full AI description of current frame."""
        if not self.frames or not self.ai:
            self.status_text.SetLabel("No AI configured")
            return

        frame = self.frames[self._current_idx]
        self.status_text.SetLabel(t("status.analyzing"))
        self.desc_text.SetValue("Analyzing...")
        wx.Yield()

        def run():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.ai.describe_frame(frame["path"], t("explorer.description"))
                )
                wx.CallAfter(self.desc_text.SetValue, result)
                wx.CallAfter(self.status_text.SetLabel, t("status.ready"))
            except Exception as e:
                wx.CallAfter(self.desc_text.SetValue, f"Error: {e}")
                wx.CallAfter(self.status_text.SetLabel, t("status.error", error=str(e)))
            finally:
                loop.close()

        threading.Thread(target=run, daemon=True).start()

    def _list_objects(self):
        """List objects in current frame."""
        if not self.frames or not self.ai:
            return
        frame = self.frames[self._current_idx]
        self.status_text.SetLabel("Detecting objects...")

        def run():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.ai.describe_frame(frame["path"], "List all objects visible in this frame, one per line.")
                )
                wx.CallAfter(self.objects_text.SetValue, result)
            except Exception as e:
                wx.CallAfter(self.objects_text.SetValue, f"Error: {e}")
            finally:
                loop.close()

        threading.Thread(target=run, daemon=True).start()

    def _describe_nearest(self):
        """Describe the nearest detected object."""
        self._describe_frame()  # For now, same as full description


def _pil_to_wx(img) -> wx.Bitmap:
    """Convert PIL Image to wx.Bitmap."""
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    wx_image = wx.Image(buf.getvalue(), wx.BITMAP_TYPE_PNG)
    return wx.Bitmap(wx_image)
