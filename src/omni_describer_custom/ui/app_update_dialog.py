"""Help > Check for Updates: a newer DescriVox Agent (core/app_update.py).

Says whether a newer version is published, shows what is new, and on
request downloads it, checks it against the published checksum and
unpacks it next to the app. It never restarts by itself: the user is
asked first, and the main window does the restart only when no video is
being processed (MainFrame._install_app_update).

Like update_dialog.py, every step goes to a read-only status box that
takes focus, so NVDA reads it, and through speech.announce() when no
screen reader is running. Download progress moves the gauge and the
status text without stealing focus, and is spoken every 25%.
"""

from __future__ import annotations

import logging
import threading
import webbrowser

import wx

from ..core import app_update
from ..core.ai_engine import short_error
from ..i18n.strings import t

logger = logging.getLogger(__name__)


class AppUpdateDialog(wx.Dialog):
    def __init__(self, parent, settings=None, release=None,
                 check_on_open: bool = True):
        super().__init__(parent, title=t("app_update.title"), size=(600, 460),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.settings = settings
        self.release: app_update.Release | None = release
        self.staged = None      # set when a verified update is unpacked
        self._busy = False
        self._spoken_quarter = -1

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(panel, label=t("app_update.status_label")),
                  0, wx.ALL, 5)
        self.status_box = wx.TextCtrl(
            panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 90),
            name=t("app_update.status_label"))
        sizer.Add(self.status_box, 0, wx.ALL | wx.EXPAND, 5)
        self.gauge = wx.Gauge(panel, range=100,
                              name=t("app_update.progress_label"))
        sizer.Add(self.gauge, 0, wx.ALL | wx.EXPAND, 5)
        sizer.Add(wx.StaticText(panel, label=t("app_update.notes_label")),
                  0, wx.ALL, 5)
        self.notes_box = wx.TextCtrl(
            panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 160),
            name=t("app_update.notes_label"))
        sizer.Add(self.notes_box, 1, wx.ALL | wx.EXPAND, 5)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.install_btn = wx.Button(panel, label=t("app_update.install_btn"))
        self.page_btn = wx.Button(panel, label=t("app_update.page_btn"))
        self.skip_btn = wx.Button(panel, label=t("app_update.skip_btn"))
        self.check_btn = wx.Button(panel, label=t("app_update.check_btn"))
        self.close_btn = wx.Button(panel, wx.ID_CLOSE, t("close"))
        for btn in (self.install_btn, self.page_btn, self.skip_btn,
                    self.check_btn):
            row.Add(btn, 0, wx.ALL, 5)
        row.AddStretchSpacer()
        row.Add(self.close_btn, 0, wx.ALL, 5)
        sizer.Add(row, 0, wx.ALL | wx.EXPAND, 5)
        panel.SetSizer(sizer)

        self.install_btn.Bind(wx.EVT_BUTTON, lambda e: self.start_install())
        self.page_btn.Bind(wx.EVT_BUTTON, lambda e: self.open_page())
        self.skip_btn.Bind(wx.EVT_BUTTON, lambda e: self.skip_version())
        self.check_btn.Bind(wx.EVT_BUTTON, lambda e: self.start_check())
        self.close_btn.Bind(wx.EVT_BUTTON,
                            lambda e: self.EndModal(wx.ID_CLOSE))
        self.SetEscapeId(wx.ID_CLOSE)
        self._refresh_buttons()

        if release is not None:
            wx.CallAfter(self.show_release, release)
        elif check_on_open:
            wx.CallAfter(self.start_check)
        else:
            self.status_box.SetValue(t("app_update.checking"))

    # ── Reporting ────────────────────────────────────────────────

    def _announce(self, text: str, focus: bool = True) -> None:
        if not self:
            return  # closed while a worker was still running
        self.status_box.SetValue(text)
        if focus:
            self.status_box.SetFocus()
        try:
            from ..core.speech import announce
            announce(text)
        except Exception:
            pass  # an announcement must never break the action itself

    def _refresh_buttons(self) -> None:
        has = self.release is not None
        self.install_btn.Enable(has and not self._busy)
        self.skip_btn.Enable(has and not self._busy)
        self.check_btn.Enable(not self._busy)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._refresh_buttons()

    # ── Check ────────────────────────────────────────────────────

    def start_check(self) -> None:
        # Posted with CallAfter from __init__: the dialog may be closing.
        if not self or self.IsBeingDeleted() or self._busy:
            return
        self._set_busy(True)
        self._announce(t("app_update.checking"))

        def work():
            try:
                release = app_update.newer_release()
                wx.CallAfter(self._check_done, release, "")
            except Exception as e:
                logger.warning("App update check failed: %s", e)
                wx.CallAfter(self._check_done, None, short_error(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _check_done(self, release, error: str) -> None:
        if not self:
            return
        self._busy = False
        if error:
            self.release = None
            self._refresh_buttons()
            self._announce(t("app_update.check_failed", error=error))
        elif release is None:
            self.release = None
            self._refresh_buttons()
            self.notes_box.SetValue("")
            from .. import __version__
            self._announce(t("app_update.up_to_date", version=__version__))
        else:
            self.show_release(release)

    def show_release(self, release) -> None:
        if not self:
            return
        from .. import __version__
        self.release = release
        self._refresh_buttons()
        self.notes_box.SetValue(release.notes or t("app_update.no_notes"))
        self._announce(t("app_update.available", latest=release.version,
                         current=__version__))

    # ── Other buttons ────────────────────────────────────────────

    def open_page(self) -> None:
        url = self.release.page_url if self.release else app_update.RELEASES_PAGE
        try:
            webbrowser.open(url)
        except Exception as e:
            logger.warning("Could not open %s: %s", url, e)

    def skip_version(self) -> None:
        if self.release is None or self.settings is None:
            return
        self.settings.set("updates.skipped_version", self.release.version)
        self._announce(t("app_update.skipped", version=self.release.version))

    # ── Download and unpack ──────────────────────────────────────

    def start_install(self) -> None:
        if self._busy or self.release is None:
            return
        folder = app_update.app_dir()
        ok, why = app_update.can_self_install(folder)
        if not ok or folder is None:
            self._announce(t(f"app_update.cannot_{why}"))
            self.page_btn.SetFocus()
            return
        release = self.release
        self._set_busy(True)
        self._spoken_quarter = -1
        self.gauge.SetValue(0)
        self._announce(t("app_update.downloading", version=release.version,
                         percent=0))

        def progress(done: int, total: int) -> None:
            total = total or release.zip_size
            if total:
                wx.CallAfter(self._progress, release.version,
                             min(100, int(done * 100 / total)))

        def work():
            try:
                zip_path = app_update.download(release, on_progress=progress)
                wx.CallAfter(self._announce, t("app_update.unpacking"), False)
                staged = app_update.stage(zip_path, folder)
                wx.CallAfter(self._ready, release, staged)
            except Exception as e:
                logger.error("App update failed: %s", e)
                wx.CallAfter(self._failed, short_error(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _progress(self, version: str, percent: int) -> None:
        if not self:
            return
        self.gauge.SetValue(percent)
        text = t("app_update.downloading", version=version, percent=percent)
        quarter = percent // 25
        if quarter != self._spoken_quarter:
            self._spoken_quarter = quarter
            self._announce(text, focus=False)
        else:
            self.status_box.SetValue(text)

    def _failed(self, error: str) -> None:
        if not self:
            return
        self._set_busy(False)
        self.gauge.SetValue(0)
        self._announce(t("app_update.failed", error=error))

    def _ready(self, release, staged) -> None:
        if not self:
            return
        self._set_busy(False)
        self.gauge.SetValue(100)
        self.staged = staged
        self._announce(t("app_update.verified", version=release.version))
        from .dialogs import ask_yes_no
        if ask_yes_no(self, t("app_update.ready_question",
                              version=release.version),
                      t("app_update.title")):
            # The main window restarts the app once this dialog is gone.
            self.EndModal(wx.ID_OK)
        else:
            self._announce(t("app_update.later"))
