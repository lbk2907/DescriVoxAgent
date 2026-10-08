"""Yes/No questions whose buttons speak the app's language (v1.8.2).

wx.MessageBox takes its Yes/No button text from WINDOWS, so on an
English Windows a Malay user heard a Malay question followed by "Yes
button" / "No button". The buttons are now labelled from the language
files, with their own Alt keys.
"""

from __future__ import annotations

import wx

from ..i18n.strings import t


def ask_yes_no(
    parent, message: str, title: str, style: int = wx.ICON_QUESTION, default_no: bool = False
) -> bool:
    """Ask a Yes/No question; True for Yes. No, Cancel and Esc give False.

    v1.8.6: a Cancel button too. Windows disables Esc in a message box
    that has no Cancel, so Esc did nothing and the user had to find No.
    The box stays the native one, which NVDA reads in full.
    """
    flags = wx.YES_NO | wx.CANCEL | style | (wx.NO_DEFAULT if default_no else 0)
    dlg = wx.MessageDialog(parent, message, title, flags)
    try:
        if hasattr(dlg, "SetYesNoCancelLabels"):  # pitfall 11: check first
            dlg.SetYesNoCancelLabels(t("common.yes"), t("common.no"), t("cancel"))
        return dlg.ShowModal() == wx.ID_YES
    finally:
        dlg.Destroy()
