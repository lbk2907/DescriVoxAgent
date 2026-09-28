"""Yes/No questions whose buttons speak the app's language (v1.8.2).

wx.MessageBox takes its Yes/No button text from WINDOWS, so on an
English Windows a Malay user heard a Malay question followed by "Yes
button" / "No button". The buttons are now labelled from the language
files, with their own Alt keys.
"""

from __future__ import annotations

import wx

from ..i18n.strings import t


def ask_yes_no(parent, message: str, title: str,
               style: int = wx.ICON_QUESTION, default_no: bool = False) -> bool:
    """Ask a Yes/No question; True for Yes. Esc and No give False."""
    flags = wx.YES_NO | style | (wx.NO_DEFAULT if default_no else 0)
    dlg = wx.MessageDialog(parent, message, title, flags)
    try:
        if hasattr(dlg, "SetYesNoLabels"):  # pitfall 11: check first
            dlg.SetYesNoLabels(t("common.yes"), t("common.no"))
        return dlg.ShowModal() == wx.ID_YES
    finally:
        dlg.Destroy()
