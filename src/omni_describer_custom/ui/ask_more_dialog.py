"""
Omni Describer Custom — Ask More Dialog.

Ask follow-up questions about a scene or time range.
"""

from __future__ import annotations

import logging
import threading
import wx

from ..core.ai_engine import AIEngine, _run_cancellable, user_error_text
from ..i18n.strings import t

logger = logging.getLogger(__name__)


class AskMoreDialog(wx.Dialog):
    """Dialog for asking follow-up questions about a scene."""

    def __init__(self, parent, ai_engine: AIEngine | None,
                 descriptions=None, position: float = 0.0,
                 video_path: str = ""):
        self.ai = ai_engine
        # v1.9.0: the question goes with the FRAME at the player's
        # position. Ask More only ever sent description text, so it
        # answered about a scene it had never seen.
        self._video = video_path or ""
        self._history: list[dict] = []
        # v1.7.4: the scene context the "seconds" field refers to. It was
        # shown but never read, so the AI got the bare question with no
        # idea which part of the video it was about.
        self._descriptions = list(descriptions or [])
        self._position = float(position or 0.0)
        # v1.9.6: Cancel/Esc stops the question in flight; its reply
        # used to land in a destroyed dialog (RuntimeError).
        self._closed = False

        super().__init__(parent, title=t("askmore.title"), size=(500, 400))

        self._build_ui()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Status line — announce target for empty-question and results.
        self.status_text = wx.StaticText(panel, label="", name="ask_status")
        sizer.Add(self.status_text, 0, wx.ALL, 5)

        # History
        sizer.Add(wx.StaticText(panel, label=t("askmore.history"), name="history_label"), 0, wx.ALL, 5)
        self.history_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY,
                                        size=(-1, 150), name="ask_history")
        sizer.Add(self.history_text, 0, wx.ALL | wx.EXPAND, 5)

        # Question
        sizer.Add(wx.StaticText(panel, label=t("askmore.question"), name="question_label"), 0, wx.ALL, 5)
        self.question_text = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER,
                                         name="question_input")
        self.question_text.Bind(wx.EVT_TEXT_ENTER, self._on_submit)
        sizer.Add(self.question_text, 0, wx.ALL | wx.EXPAND, 5)

        # Time range
        time_row = wx.BoxSizer(wx.HORIZONTAL)
        time_row.Add(wx.StaticText(panel, label=t("askmore.seconds"), name="seconds_label"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        self.seconds_ctrl = wx.TextCtrl(panel, value="10", size=(60, -1), name="seconds_range")
        time_row.Add(self.seconds_ctrl, 0, wx.ALL, 5)
        time_row.AddStretchSpacer()
        sizer.Add(time_row, 0, wx.EXPAND)

        # Buttons
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.submit_btn = wx.Button(panel, label=t("askmore.submit"), name="submit_question")
        self.cancel_btn = wx.Button(panel, label=t("askmore.cancel"), name="cancel_question")
        # v1.8.2: Esc did nothing here (the button is not wx.ID_CANCEL).
        self.SetEscapeId(self.cancel_btn.GetId())
        btn_row.Add(self.submit_btn, 0, wx.ALL, 5)
        btn_row.AddStretchSpacer()
        btn_row.Add(self.cancel_btn, 0, wx.ALL, 5)
        sizer.Add(btn_row, 0, wx.ALL | wx.EXPAND, 5)

        # Bindings
        self.submit_btn.Bind(wx.EVT_BUTTON, self._on_submit)
        self.cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel)
        self.Bind(wx.EVT_CLOSE, self._on_cancel)

        panel.SetSizer(sizer)
        panel.Layout()

    def _announce(self, msg: str) -> None:
        """Set status text and move focus so a screen reader reads it.

        v1.6.6: the focus move says nothing on a computer with no
        screen reader at all, which is how someone given this app ends
        up staring at a silent window. speech.announce() speaks the
        message through Prism in exactly that case, and stays quiet
        when a reader is running so nothing is said twice.
        """
        self.status_text.SetLabel(msg)
        self.status_text.SetFocus()
        try:
            from ..core.speech import announce as _speak_status
            _speak_status(msg)
        except Exception:
            pass  # an announcement must never break the action itself

    def _on_submit(self, event):
        """Submit question to AI."""
        question = self.question_text.GetValue().strip()
        if not question:
            self._announce(t("ask.empty_question"))
            self.question_text.SetFocus()
            return

        self.submit_btn.Disable()
        self.history_text.AppendText(t("ask.you", question=question) + "\n")

        if not self.ai:
            self.history_text.AppendText(t("ask.ai_none"))
            self.submit_btn.Enable()
            return

        # v1.7.4: capture history BEFORE recording this question; the
        # worker used to read it afterwards, so the question was sent
        # twice (once in history, once as the prompt).
        history = list(self._history[-5:]) or None
        context = self._scene_context()
        prompt = f"{context}\n\n{question}" if context else question

        def closed() -> bool:
            return self._closed

        def ask():
            import asyncio
            from ..core.ai_engine import apply_output_language
            q = apply_output_language(prompt, getattr(
                self.ai, "output_lang", ""))
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                frame = self._frame_at_position()
                if frame:
                    past = "\n".join(
                        f"{h['role']}: {h['content']}" for h in history or [])
                    seen = (f"{past}\n\n{q}" if past else q)
                    result = loop.run_until_complete(_run_cancellable(
                        self.ai.ask_about_scene(frame, seen), closed))
                else:
                    result = loop.run_until_complete(_run_cancellable(
                        self.ai.ask(q, history), closed))
                # Record assistant reply so follow-ups keep context
                self._history.append({"role": "assistant", "content": result})
                wx.CallAfter(self._reply, t("ask.ai_prefix", result=result))
            except Exception as e:
                if self._closed:
                    return
                logger.error("Ask More failed: %s", e)
                wx.CallAfter(self._reply, t(
                    "ask.error", error=user_error_text(str(e))) + "\n\n")
            finally:
                loop.close()

        self._history.append({"role": "user", "content": question})
        threading.Thread(target=ask, daemon=True).start()
        self.question_text.SetValue("")

    def _reply(self, text: str) -> None:
        """Show a worker's answer — only while the dialog is alive."""
        if not self or self._closed:
            return
        self.history_text.AppendText(text)
        # Move focus to the history so NVDA reads the new reply.
        self.history_text.SetFocus()
        self.submit_btn.Enable()

    def _frame_at_position(self) -> str:
        """A JPEG of the video at the player's position, or "" when
        there is no video to look at (the text-only question is used)."""
        import os
        import subprocess
        import tempfile
        if not self._video or not os.path.exists(self._video):
            return ""
        from ..core.tools import find_tool
        out = os.path.join(tempfile.gettempdir(),
                           f"odc_ask_{os.getpid()}.jpg")
        try:
            subprocess.run(
                [find_tool("ffmpeg"), "-hide_banner", "-nostdin", "-y",
                 "-v", "error", "-ss", f"{max(0.0, self._position):.2f}",
                 "-i", self._video, "-frames:v", "1", "-vf",
                 "scale=960:-2", out], timeout=60, check=True)
            return out if os.path.exists(out) else ""
        except Exception as e:
            logger.warning("Ask More: no frame at %.1fs: %s", self._position, e)
            return ""

    def _scene_context(self) -> str:
        """Descriptions within +/- N seconds of the playback position,
        N from the seconds field. Empty when there is nothing to add."""
        if not self._descriptions:
            return ""
        try:
            window = max(0.0, float(self.seconds_ctrl.GetValue().strip()))
        except ValueError:
            window = 10.0
        lo, hi = self._position - window, self._position + window
        lines = [
            f"[{d.start_time:.1f}s-{d.end_time:.1f}s] {d.text}"
            for d in self._descriptions
            if d.end_time >= lo and d.start_time <= hi and d.text.strip()
        ]
        if not lines:
            return ""
        return t("ask.context", position=f"{self._position:.1f}",
                 seconds=f"{window:g}") + "\n" + "\n".join(lines)

    def _on_cancel(self, event):
        self._closed = True
        if self.IsModal():
            self.EndModal(wx.ID_CANCEL)
        else:
            self.Destroy()
