"""
Omni Describer Custom — Ask More Dialog.

Ask follow-up questions about a scene or time range.
"""

from __future__ import annotations

import logging
import threading
import wx

from ..core.ai_engine import AIEngine
from ..i18n.strings import I18n, t

logger = logging.getLogger(__name__)


class AskMoreDialog(wx.Dialog):
    """Dialog for asking follow-up questions about a scene."""

    def __init__(self, parent, ai_engine: AIEngine | None):
        self.ai = ai_engine
        self._history: list[dict] = []

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
        """Set status text and move focus so NVDA announces it."""
        self.status_text.SetLabel(msg)
        self.status_text.SetFocus()

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

        def ask():
            import asyncio
            from ..core.ai_engine import apply_output_language
            q = apply_output_language(question, getattr(
                self.ai, "output_lang", ""))
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.ai.ask(q, self._history[-5:] if self._history else None)
                )
                # Record assistant reply so follow-ups keep context
                self._history.append({"role": "assistant", "content": result})
                wx.CallAfter(self.history_text.AppendText,
                             t("ask.ai_prefix", result=result))
                # Move focus to the history so NVDA reads the new reply.
                wx.CallAfter(self.history_text.SetFocus)
                wx.CallAfter(self.submit_btn.Enable)
            except Exception as e:
                wx.CallAfter(self.history_text.AppendText,
                             t("ask.error", error=str(e)) + "\n\n")
                wx.CallAfter(self.history_text.SetFocus)
                wx.CallAfter(self.submit_btn.Enable)
            finally:
                loop.close()

        self._history.append({"role": "user", "content": question})
        threading.Thread(target=ask, daemon=True).start()
        self.question_text.SetValue("")

    def _on_cancel(self, event):
        if self.IsModal():
            self.EndModal(wx.ID_CANCEL)
        else:
            self.Destroy()
