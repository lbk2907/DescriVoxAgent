"""A progress dialog whose bar a screen reader can read (v1.9.6).

The owner's decision (2 Oct 2026): progress is ONE real progress bar for
the whole job, read by NVDA with its own "Progress bar output" setting
(the owner uses "Speak and beep"), and no periodic spoken reports.

wx.ProgressDialog cannot do that on Windows: it is the native task dialog,
whose bar is DirectUI-drawn with no msctls_progress32 behind it (pitfall
3), so NVDA has no progress bar to follow. This dialog is a drop-in for
the part of wx.ProgressDialog the app uses (Update, Pulse, WasCancelled,
SetTitle, Destroy), built from ordinary controls:

  message   a StaticText (the phase, and time left when known)
  label     a StaticText created RIGHT BEFORE the bar: Windows names a
            control after the static text created just before it (pitfall
            34/53), so NVDA says "Overall progress, progress bar, 40%"
  bar       a wx.Gauge, a real msctls_progress32
  Cancel    focused at start; Esc presses it

Behaviour that differs from wx.ProgressDialog, on purpose:
  - The bar never moves backwards: Update() with a lower value keeps the
    higher one, and Pulse() never animates or resets it (only the text).
  - The bar and the text are written only when they CHANGE (pitfall 65:
    NVDA re-read unchanged text every second when the dialog had focus).
  - Cancel only records the press (WasCancelled(), and the next Update()/
    Pulse() returns (False, False)); the owner of the dialog closes it.
  - It is shown modeless, so it never blocks the caller, but the rest of
    the application is disabled while it is up, like PD_APP_MODAL.
  - The constructor does not pump the event loop. The ghost-dialog guard
    in MainFrame._ensure_download_progress (pitfall 8) stays anyway.
"""

from __future__ import annotations

import logging

import wx

from ..i18n.strings import t

logger = logging.getLogger(__name__)

_WRAP = 420  # message width in pixels before it wraps
_MESSAGE_LINES = 3  # room kept for the message, so the dialog does not jump


class AccessibleProgressDialog(wx.Dialog):
    """Drop-in for the subset of wx.ProgressDialog this app uses."""

    def __init__(
        self,
        title: str,
        message: str,
        maximum: int = 100,
        parent: wx.Window | None = None,
        style: int = wx.PD_APP_MODAL | wx.PD_CAN_ABORT,
    ):
        # `style` is accepted for drop-in compatibility: this dialog is
        # always app-modal and always has Cancel.
        super().__init__(parent, title=title, style=wx.CAPTION)
        self._maximum = max(1, int(maximum or 1))
        self._percent = 0
        self._message = ""
        self._cancelled = False
        self._disabler = None

        # Creation order IS the tab order and the NVDA naming (pitfall 34).
        self._text = wx.StaticText(self, label="")
        line_h = self._text.GetCharHeight()
        self._text.SetMinSize((_WRAP, line_h * _MESSAGE_LINES))
        self._bar_label = wx.StaticText(self, label=t("progress.bar_label"))
        self._gauge = wx.Gauge(
            self, range=100, size=(_WRAP, -1), style=wx.GA_HORIZONTAL | wx.GA_SMOOTH
        )
        self._cancel = wx.Button(self, wx.ID_CANCEL, t("cancel"))

        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(self._text, 0, wx.EXPAND | wx.ALL, 10)
        box.Add(self._bar_label, 0, wx.LEFT | wx.RIGHT, 10)
        box.Add(self._gauge, 0, wx.EXPAND | wx.ALL, 10)
        box.Add(self._cancel, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)
        self.SetSizer(box)
        self._set_message(message)
        box.Fit(self)

        self.SetEscapeId(wx.ID_CANCEL)
        self.Bind(wx.EVT_BUTTON, self._on_cancel, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)

        if parent is not None:
            self.CentreOnParent()
        self.Show()
        # Like PD_APP_MODAL: every other window of the app is disabled
        # while this one is up; Destroy() gives them back.
        self._disabler = wx.WindowDisabler(self)
        self._cancel.SetFocus()

    # ── wx.ProgressDialog API ──────────────────────────────────────────

    def Update(self, value: int = -1, newmsg: str = "") -> tuple[bool, bool]:
        """Move the bar to `value` (in 0..maximum) and set the text.

        A value lower than the bar's keeps the bar where it is: the bar is
        the whole job, and it never goes backwards. Returns
        (continue, skipped) like wx; continue is False once Cancel was
        pressed.
        """
        if value is not None and value >= 0:
            pct = int(min(self._maximum, value) * 100 / self._maximum)
            if pct > self._percent:
                self._percent = pct
                self._gauge.SetValue(pct)
        if newmsg:
            self._set_message(newmsg)
        return (not self._cancelled, False)

    def Pulse(self, newmsg: str = "") -> tuple[bool, bool]:
        """Only the text may change: the bar keeps its last value (wx
        animates and so loses the percentage NVDA reads)."""
        if newmsg:
            self._set_message(newmsg)
        return (not self._cancelled, False)

    def WasCancelled(self) -> bool:
        return self._cancelled

    def WasSkipped(self) -> bool:
        return False

    def GetValue(self) -> int:
        """The bar, in percent."""
        return self._percent

    def GetRange(self) -> int:
        return self._maximum

    def GetMessage(self) -> str:
        return self._message

    def Destroy(self) -> bool:
        self._release()
        return super().Destroy()

    # ── internals ──────────────────────────────────────────────────────

    def _set_message(self, text: str) -> None:
        text = str(text)
        if text == self._message:
            return  # pitfall 65: never rewrite unchanged text
        self._message = text
        self._text.SetLabelText(text)
        self._text.Wrap(_WRAP)
        self.Layout()

    def _on_cancel(self, event) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        try:
            self._cancel.SetLabel(t("progress.cancelling"))
            self._cancel.Disable()
        except RuntimeError:
            pass

    def _on_close(self, event) -> None:
        # Alt+F4 means Cancel; the owner of the dialog closes it.
        if event.CanVeto():
            event.Veto()
            self._on_cancel(event)
        else:
            self.Destroy()

    def _on_destroy(self, event) -> None:
        if event.GetEventObject() is self:
            self._release()
        event.Skip()

    def _release(self) -> None:
        """Give the rest of the app back BEFORE the window dies, so focus
        returns to the main window and not to another program."""
        disabler, self._disabler = self._disabler, None
        if disabler is not None:
            del disabler
