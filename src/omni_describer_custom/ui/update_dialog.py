"""Help > Check for Updates.

Says which yt-dlp is in use and whether a newer one exists, installs it
only when asked, and can always go back to the copy shipped with the
app. Every step is written to a read-only status box that takes focus,
so NVDA reads it, and is spoken through speech.announce() when no screen
reader is running (the same pattern as the editor's _announce).
"""

from __future__ import annotations

import logging
import threading

import wx

from ..core import tools, updater
from ..i18n.strings import t

logger = logging.getLogger(__name__)


class UpdateDialog(wx.Dialog):
    def __init__(self, parent, settings=None, check_on_open: bool = True):
        super().__init__(parent, title=t("update.title"), size=(520, 320),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.settings = settings
        self._latest = ""
        self._busy = False

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(panel, label=t("update.status_label")),
                  0, wx.ALL, 5)
        self.status_box = wx.TextCtrl(
            panel, style=wx.TE_MULTILINE | wx.TE_READONLY,
            size=(-1, 150), name=t("update.status_label"))
        sizer.Add(self.status_box, 1, wx.ALL | wx.EXPAND, 5)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.check_btn = wx.Button(panel, label=t("update.check_btn"))
        self.update_btn = wx.Button(panel, label=t("update.install_btn"))
        self.revert_btn = wx.Button(panel, label=t("update.revert_btn"))
        self.close_btn = wx.Button(panel, wx.ID_CLOSE, t("close"))
        for btn in (self.check_btn, self.update_btn, self.revert_btn):
            row.Add(btn, 0, wx.ALL, 5)
        row.AddStretchSpacer()
        row.Add(self.close_btn, 0, wx.ALL, 5)
        sizer.Add(row, 0, wx.ALL | wx.EXPAND, 5)
        panel.SetSizer(sizer)

        self.update_btn.Disable()
        self.check_btn.Bind(wx.EVT_BUTTON, lambda e: self.start_check())
        self.update_btn.Bind(wx.EVT_BUTTON, lambda e: self.start_install())
        self.revert_btn.Bind(wx.EVT_BUTTON, lambda e: self.do_revert())
        self.close_btn.Bind(wx.EVT_BUTTON,
                            lambda e: self.EndModal(wx.ID_CLOSE))
        self.SetEscapeId(wx.ID_CLOSE)

        # Running yt-dlp to ask its version takes 1-3 s, so nothing here
        # does it on the UI thread; the check worker reports it.
        self.status_box.SetValue(t("update.checking"))
        self.revert_btn.Enable(self._using_update())
        if check_on_open:
            wx.CallAfter(self.start_check)

    # ── Reporting ────────────────────────────────────────────────

    def _announce(self, text: str) -> None:
        if not self:
            return  # closed while a worker was still running
        self.status_box.SetValue(text)
        self.status_box.SetFocus()
        try:
            from ..core.speech import announce
            announce(text)
        except Exception:
            pass  # an announcement must never break the action itself

    @staticmethod
    def _using_update() -> bool:
        return bool(tools._user_copy(updater.TOOL))

    @staticmethod
    def _describe(st: dict) -> str:
        source = (t("update.source_updated") if st["using_update"]
                  else t("update.source_bundled"))
        return t("update.current", version=st["in_use_version"] or "?",
                 source=source, bundled=st["bundled_version"] or "?")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.check_btn.Enable(not busy)
        self.revert_btn.Enable(not busy and self._using_update())
        self.update_btn.Enable(not busy and bool(self._latest))

    # ── Actions ──────────────────────────────────────────────────

    def start_check(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self._announce(t("update.checking"))

        def work():
            st = updater.status()
            try:
                latest = updater.latest_version()
                current = st["in_use_version"]
                newer = latest if updater.is_newer(latest, current) else ""
                if self.settings is not None:
                    updater.record_check(self.settings)
                wx.CallAfter(self._check_done, st, latest, newer, "")
            except Exception as e:
                logger.warning("Update check failed: %s", e)
                wx.CallAfter(self._check_done, st, "", "", str(e))

        threading.Thread(target=work, daemon=True).start()

    def _check_done(self, st, latest, newer, error) -> None:
        if not self:
            return
        self._latest = newer
        self._set_busy(False)
        current = st["in_use_version"]
        if error:
            result = t("update.check_failed", error=error)
        elif newer:
            result = t("update.available", current=current or "?",
                       latest=newer)
        else:
            result = t("update.up_to_date", version=current or latest)
        # The result first: it is what the user is waiting to hear.
        self._announce(result + "\n\n" + self._describe(st))

    def start_install(self) -> None:
        if self._busy or not self._latest:
            return
        tag = self._latest
        self._set_busy(True)
        self.update_btn.Disable()

        def status(key: str) -> None:
            wx.CallAfter(self._announce, t(f"update.step_{key}", version=tag))

        def work():
            try:
                version = updater.install(tag, on_status=status)
                wx.CallAfter(self._install_done, version, "")
            except Exception as e:
                logger.error("yt-dlp update failed: %s", e)
                wx.CallAfter(self._install_done, "", str(e))

        threading.Thread(target=work, daemon=True).start()

    def _install_done(self, version, error) -> None:
        if not self:
            return
        self._latest = "" if version else self._latest
        self._set_busy(False)
        if error:
            self._announce(t("update.install_failed", error=error))
        else:
            self._announce(t("update.installed", version=version))

    def do_revert(self) -> None:
        if self._busy:
            return
        updater.revert()
        self._latest = ""
        self._set_busy(True)

        def work():
            version = updater.status()["in_use_version"]
            wx.CallAfter(self._revert_done, version)

        threading.Thread(target=work, daemon=True).start()

    def _revert_done(self, version) -> None:
        if not self:
            return
        self._set_busy(False)
        self._announce(t("update.reverted", version=version or "?"))
