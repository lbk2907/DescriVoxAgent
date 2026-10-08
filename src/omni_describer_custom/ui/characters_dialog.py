"""Characters window (v2.1.0, owner 5 Oct 2026).

The people in this video, as the AI and the agent know them: a name or
a label, and how to recognise them. The user can give a real name to
someone the AI could only describe, and put that name into every
description at once. Names given here are kept by later runs: the AI
never drops or changes them (core/characters.py, by_user).
"""

from __future__ import annotations

import wx

from ..core import characters as ch
from ..i18n.strings import t
from .dialogs import ask_yes_no


class CharacterEditDialog(wx.Dialog):
    """Name and how to recognise one person."""

    def __init__(self, parent, name: str = "", look: str = ""):
        super().__init__(parent, title=t("cast.edit_title"))
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label=t("cast.name_label")), 0, wx.ALL, 5)
        self.name_box = wx.TextCtrl(self, value=name, name=t("cast.name_label"))
        sizer.Add(self.name_box, 0, wx.ALL | wx.EXPAND, 5)
        sizer.Add(wx.StaticText(self, label=t("cast.look_label")), 0, wx.ALL, 5)
        self.look_box = wx.TextCtrl(self, value=look, name=t("cast.look_label"))
        sizer.Add(self.look_box, 0, wx.ALL | wx.EXPAND, 5)
        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(buttons, 0, wx.ALL | wx.ALIGN_RIGHT, 5)
        self.SetSizerAndFit(sizer)
        self.SetSize((440, -1))
        self.name_box.SetFocus()

    def values(self) -> tuple[str, str]:
        return self.name_box.GetValue().strip(), self.look_box.GetValue().strip()


class CharactersDialog(wx.Dialog):
    """List, add, rename (everywhere) and remove the people in a video."""

    def __init__(self, parent, store, on_descriptions_changed=None):
        super().__init__(parent, title=t("cast.title"), size=(520, 360))
        self.store = store
        self.on_descriptions_changed = on_descriptions_changed or (lambda: None)
        self.folder = store.project_dir(store.current.id)
        self.cast = ch.load_cast(self.folder)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label=t("cast.list_label")), 0, wx.ALL, 5)
        self.list = wx.ListBox(self, style=wx.LB_SINGLE, name=t("cast.list_label"))
        sizer.Add(self.list, 1, wx.ALL | wx.EXPAND, 5)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.edit_btn = wx.Button(self, label=t("cast.edit_btn"), name="cast_edit")
        self.add_btn = wx.Button(self, label=t("cast.add_btn"), name="cast_add")
        self.remove_btn = wx.Button(self, label=t("cast.remove_btn"), name="cast_remove")
        close_btn = wx.Button(self, wx.ID_CANCEL, t("close"))
        for b in (self.edit_btn, self.add_btn, self.remove_btn):
            row.Add(b, 0, wx.ALL, 5)
        row.AddStretchSpacer()
        row.Add(close_btn, 0, wx.ALL, 5)
        sizer.Add(row, 0, wx.ALL | wx.EXPAND, 5)
        self.status = wx.StaticText(self, label="", name="cast_status")
        sizer.Add(self.status, 0, wx.ALL, 5)
        self.SetSizer(sizer)

        self.edit_btn.Bind(wx.EVT_BUTTON, lambda e: self.edit_selected())
        self.add_btn.Bind(wx.EVT_BUTTON, lambda e: self.add())
        self.remove_btn.Bind(wx.EVT_BUTTON, lambda e: self.remove_selected())
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.edit_selected())
        self._refresh(0)
        self.list.SetFocus()

    # ── list ──────────────────────────────────────────────────────

    def _label(self, c: dict) -> str:
        look = c.get("look", "")
        return f"{c['name']} — {look}" if look else c["name"]

    def _refresh(self, select: int = 0) -> None:
        if self.cast:
            self.list.Set([self._label(c) for c in self.cast])
            self.list.SetSelection(max(0, min(select, len(self.cast) - 1)))
        else:
            self.list.Set([t("cast.empty")])
            self.list.SetSelection(0)
        for b in (self.edit_btn, self.remove_btn):
            b.Enable(bool(self.cast))

    def _selected(self) -> int:
        i = self.list.GetSelection()
        return i if self.cast and i != wx.NOT_FOUND else -1

    def _say(self, text: str) -> None:
        self.status.SetLabel(text)
        try:
            from ..core.speech import get_speech

            get_speech().speak(text, interrupt=True)
        except Exception:
            pass

    def _save(self) -> None:
        ch.save_cast(self.folder, self.cast)

    # ── actions ───────────────────────────────────────────────────

    def add(self) -> None:
        dlg = CharacterEditDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            name, look = dlg.values()
            if name:
                self.cast = [c for c in self.cast if c["name"].casefold() != name.casefold()]
                self.cast.insert(0, {"name": name, "look": look, "by_user": True})
                self._save()
                self._refresh(0)
                self._say(t("cast.added", name=name))
        dlg.Destroy()
        self.list.SetFocus()

    def edit_selected(self) -> None:
        i = self._selected()
        if i < 0:
            return
        old = self.cast[i]
        dlg = CharacterEditDialog(self, old["name"], old.get("look", ""))
        ok = dlg.ShowModal() == wx.ID_OK
        name, look = dlg.values()
        dlg.Destroy()
        if not ok or not name:
            self.list.SetFocus()
            return
        self.cast[i] = {"name": name, "look": look, "by_user": True}
        self._save()
        if name.casefold() != old["name"].casefold():
            self._rename_everywhere(old["name"], name)
        self._refresh(i)
        self.list.SetFocus()

    def _rename_everywhere(self, old: str, new: str) -> None:
        descs = list(self.store.current.descriptions or [])
        texts, changed = ch.rename_in_texts([d.text for d in descs], old, new)
        if not changed:
            self._say(t("cast.renamed_none", name=new))
            return
        if not ask_yes_no(
            self, t("cast.rename_confirm", old=old, new=new, count=changed), t("cast.title")
        ):
            self._say(t("cast.renamed_list_only", name=new))
            return
        for d, text in zip(descs, texts, strict=False):
            if d.text != text:
                d.text = text
                d.edited = True
        self.store.save_descriptions(descs)
        self.on_descriptions_changed()
        self._say(t("cast.renamed", count=changed, name=new))

    def remove_selected(self) -> None:
        i = self._selected()
        if i < 0:
            return
        name = self.cast[i]["name"]
        if not ask_yes_no(
            self,
            t("cast.remove_confirm", name=name),
            t("cast.title"),
            wx.ICON_WARNING,
            default_no=True,
        ):
            return
        del self.cast[i]
        self._save()
        self._refresh(i)
        self._say(t("cast.removed", name=name))
        self.list.SetFocus()
