"""
Omni Describer Custom — Description Editor Window.

Edit, add, delete audio description entries.
"""

from __future__ import annotations

import logging
import threading
import wx

from ..core.project_store import ProjectStore
from ..core.tts_engine import TTSEngine
from ..i18n.strings import I18n, t

logger = logging.getLogger(__name__)


class EditorWindow(wx.Frame):
    """Description editor with timeline."""

    def __init__(self, parent, project_store: ProjectStore, tts_engine: TTSEngine):
        self.store = project_store
        self.tts = tts_engine
        self._current_idx = 0

        super().__init__(parent, title=t("editor.title"),
                         size=(800, 600))

        self._build_ui()
        self._load_descriptions()
        logger.info("EditorWindow opened")

    def _build_ui(self):
        """Build editor UI."""
        panel = wx.Panel(self)
        panel.SetName("editor_panel")
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        # Status line — announce target so NVDA reports add/delete/TTS
        # results (audit fix: this window had no status channel).
        self.status_text = wx.StaticText(panel, label="", name="editor_status")
        sizer.Add(self.status_text, 0, wx.ALL, 5)

        # Description list
        list_box = wx.StaticBox(panel, label=t("editor.select_desc"))
        list_sizer = wx.StaticBoxSizer(list_box, wx.VERTICAL)

        self.desc_list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL,
                                     name="description_list")
        self.desc_list.InsertColumn(0, t("editor.col_start"), width=70)
        self.desc_list.InsertColumn(1, t("editor.col_end"), width=70)
        self.desc_list.InsertColumn(2, t("editor.col_text"), width=500)
        list_sizer.Add(self.desc_list, 1, wx.ALL | wx.EXPAND, 5)
        sizer.Add(list_sizer, 1, wx.ALL | wx.EXPAND, 10)

        # Time controls
        time_box = wx.BoxSizer(wx.HORIZONTAL)
        time_box.Add(wx.StaticText(panel, label=t("editor.start_time"), name="start_label"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        self.start_time_ctrl = wx.TextCtrl(panel, value="0.0", size=(80, -1), name="start_time")
        time_box.Add(self.start_time_ctrl, 0, wx.ALL, 5)

        time_box.Add(wx.StaticText(panel, label=t("editor.end_time"), name="end_label"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        self.end_time_ctrl = wx.TextCtrl(panel, value="5.0", size=(80, -1), name="end_time")
        time_box.Add(self.end_time_ctrl, 0, wx.ALL, 5)

        time_box.AddStretchSpacer()
        sizer.Add(time_box, 0, wx.ALL | wx.EXPAND, 5)

        # Description text editor
        text_box = wx.StaticBox(panel, label=t("editor.text"))
        text_sizer = wx.StaticBoxSizer(text_box, wx.VERTICAL)
        self.text_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE, size=(-1, 150),
                                     name="description_text")
        text_sizer.Add(self.text_ctrl, 1, wx.ALL | wx.EXPAND, 5)
        sizer.Add(text_sizer, 0, wx.ALL | wx.EXPAND, 10)

        # Buttons
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.add_btn = wx.Button(panel, label=t("editor.add_new"), name="add_description")
        self.delete_btn = wx.Button(panel, label=t("editor.delete"), name="delete_description")
        self.close_btn = wx.Button(panel, label=t("editor.close"), name="close_editor")
        self.tts_btn = wx.Button(panel, label="🔊 " + t("editor.read"), name="tts_read")

        btn_row.Add(self.add_btn, 0, wx.ALL, 5)
        btn_row.Add(self.delete_btn, 0, wx.ALL, 5)
        btn_row.Add(self.tts_btn, 0, wx.ALL, 5)
        btn_row.AddStretchSpacer()
        btn_row.Add(self.close_btn, 0, wx.ALL, 5)

        sizer.Add(btn_row, 0, wx.ALL | wx.EXPAND, 10)

        # Bindings
        self.desc_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_select)
        self.add_btn.Bind(wx.EVT_BUTTON, self._on_add)
        self.delete_btn.Bind(wx.EVT_BUTTON, self._on_delete)
        self.close_btn.Bind(wx.EVT_BUTTON, self._on_close)
        self.tts_btn.Bind(wx.EVT_BUTTON, self._on_tts)
        self.Bind(wx.EVT_CLOSE, self._on_close)

        panel.Layout()

    def _announce(self, msg: str) -> None:
        """Set status text and move focus so NVDA announces it."""
        self.status_text.SetLabel(msg)
        self.status_text.SetFocus()

    def _load_descriptions(self):
        """Load descriptions into list."""
        self.desc_list.DeleteAllItems()
        if not self.store.current:
            return

        for desc in self.store.current.descriptions:
            idx = self.desc_list.GetItemCount()
            self.desc_list.InsertItem(idx, f"{desc.start_time:.1f}s")
            self.desc_list.SetItem(idx, 1, f"{desc.end_time:.1f}s")
            self.desc_list.SetItem(idx, 2, desc.text[:100])

        if self.store.current.descriptions:
            self.desc_list.Select(0)
            self._on_select(None)

    def _on_select(self, event):
        """Description selected."""
        idx = self.desc_list.GetFirstSelected()
        if idx == wx.NOT_FOUND or not self.store.current:
            return

        self._current_idx = idx
        desc = self.store.current.descriptions[idx]
        self.start_time_ctrl.SetValue(str(desc.start_time))
        self.end_time_ctrl.SetValue(str(desc.end_time))
        self.text_ctrl.SetValue(desc.text)

    def _on_add(self, event):
        """Add new description."""
        if not self.store.current:
            return
        new_desc = type('Desc', (), {
            'id': 0, 'start_time': 0.0, 'end_time': 5.0,
            'text': '', 'edited': False, 'created_at': '', 'frame_path': ''
        })()
        self.store.add_description(new_desc)
        self._load_descriptions()
        self._announce(t("editor.add_new"))

    def _on_delete(self, event):
        """Delete the selected description after a YES/NO confirmation."""
        idx = self.desc_list.GetFirstSelected()
        if idx == wx.NOT_FOUND:
            return
        if wx.MessageBox(
            t("editor.confirm_delete"),
            t("editor.confirm_title"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
        ) != wx.YES:
            return
        desc = self.store.current.descriptions[idx]
        self.store.delete_description(desc.id)
        self._load_descriptions()
        self._announce(t("editor.deleted"))

    def _on_tts(self, event):
        """Read current description via TTS."""
        text = self.text_ctrl.GetValue().strip()
        if not text:
            self._announce(t("editor.empty_text"))
            return
        # Generate AND play the audio in a background thread; a bare
        # speak() only writes a temp file and the user hears nothing.
        def speak():
            try:
                self.tts.speak_and_play(text)
            except Exception as e:
                logger.error("TTS speak error: %s", e)
        threading.Thread(target=speak, daemon=True).start()

    def _on_close(self, event):
        """Save and close."""
        # Save changes
        if self.store.current:
            for i, desc in enumerate(self.store.current.descriptions):
                if i == self._current_idx:
                    try:
                        desc.start_time = float(self.start_time_ctrl.GetValue())
                        desc.end_time = float(self.end_time_ctrl.GetValue())
                    except ValueError:
                        pass
                    desc.text = self.text_ctrl.GetValue()
            self.store.save_descriptions(self.store.current.descriptions)
        self.Destroy()


