"""The Player agent's window (F2): ask, hear each step, approve changes.

Owner's choices (29-30 Sep 2026): the video pauses while this is open and
resumes on close; every step is spoken; several proposals are summarised,
then Accept all / Review one by one / Reject all; the conversation is
remembered until the Player closes. The agent itself changes nothing:
the Player applies what is accepted (PlayerWindow.apply_agent_changes),
with a backup and Undo.
"""

from __future__ import annotations

import asyncio
import logging
import threading

import wx

from ..i18n.strings import t

logger = logging.getLogger(__name__)


def _clock(seconds) -> str:
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return "?"
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def speak(text: str) -> None:
    """Say it through the user's screen reader (or SAPI), without cutting
    off what is being read — the same route as progress phases."""
    try:
        from ..core.speech import get_speech
        get_speech().speak(text, interrupt=False)
    except Exception:
        pass


def describe_proposal(p, descriptions) -> str:
    """One proposal as a sentence a person can decide on."""
    old = ""
    if p.index is not None and 0 <= p.index < len(descriptions):
        old = descriptions[p.index][1]
    when = _clock(p.time if p.time is not None else
                  (descriptions[p.index][0] if old else 0))
    return t(f"agent.proposal_{p.action}", old=old, new=p.text, when=when,
             reason=p.reason)


class AgentDialog(wx.Dialog):
    def __init__(self, player, agent):
        super().__init__(player, title=t("agent.title"), size=(620, 480),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.player, self.agent = player, agent
        self._busy = False
        self._last_step = ""
        self.agent.on_step = self._on_step

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(panel, label=t("agent.conversation")),
                  0, wx.ALL, 5)
        self.log = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY,
                               size=(-1, 220), name=t("agent.conversation"))
        sizer.Add(self.log, 1, wx.ALL | wx.EXPAND, 5)
        sizer.Add(wx.StaticText(panel, label=t("agent.question")), 0, wx.ALL, 5)
        self.question = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER,
                                    name=t("agent.question"))
        sizer.Add(self.question, 0, wx.ALL | wx.EXPAND, 5)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.ask_btn = wx.Button(panel, label=t("agent.ask_btn"))
        self.undo_btn = wx.Button(panel, label=t("agent.undo_btn"))
        self.close_btn = wx.Button(panel, wx.ID_CLOSE, t("close"))
        row.Add(self.ask_btn, 0, wx.ALL, 5)
        row.Add(self.undo_btn, 0, wx.ALL, 5)
        row.AddStretchSpacer()
        row.Add(self.close_btn, 0, wx.ALL, 5)
        sizer.Add(row, 0, wx.ALL | wx.EXPAND, 5)
        panel.SetSizer(sizer)

        self.undo_btn.Enable(player.can_undo_agent())
        self.question.Bind(wx.EVT_TEXT_ENTER, lambda e: self.submit())
        self.ask_btn.Bind(wx.EVT_BUTTON, lambda e: self.submit())
        self.undo_btn.Bind(wx.EVT_BUTTON, lambda e: self.undo())
        self.close_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        self.SetEscapeId(wx.ID_CLOSE)
        for line in getattr(player, "_agent_transcript", []):
            self.log.AppendText(line)
        self.question.SetFocus()

    # ── speaking ─────────────────────────────────────────────────
    def _on_step(self, code: str, args: dict) -> None:
        """Called on the worker thread for each tool the agent uses."""
        text = t(f"agent.step_{code}", at=_clock(args.get("at", 0)),
                 end=_clock(args.get("end", 0)))
        if text == self._last_step:
            return       # six looks in a row are said once
        self._last_step = text
        wx.CallAfter(self._status, text, True)

    def _status(self, text: str, say: bool) -> None:
        if not self:
            return
        self.SetTitle(f"{t('agent.title')} — {text}")
        if say:
            speak(text)

    def _append(self, line: str) -> None:
        self.log.AppendText(line + "\n")
        self.player._agent_transcript.append(line + "\n")

    # ── asking ───────────────────────────────────────────────────
    def submit(self, question: str | None = None) -> None:
        question = (question if question is not None
                    else self.question.GetValue()).strip()
        if self._busy:
            return
        if not question:
            speak(t("agent.empty"))
            return
        self._busy = True
        self.ask_btn.Disable()
        self.question.SetValue("")
        self._append(t("agent.you", text=question))
        self._last_step = ""
        speak(t("agent.thinking"))
        self._run(lambda: self.agent.ask(question))

    def _run(self, make_coro) -> None:
        def work():
            loop = asyncio.new_event_loop()
            try:
                reply = loop.run_until_complete(make_coro())
            except Exception as e:
                logger.error("Agent failed: %s", e)
                from ..core.agent import Reply
                reply = Reply(error=str(e)[:300])
            finally:
                loop.close()
            wx.CallAfter(self._done, reply)
        threading.Thread(target=work, daemon=True).start()

    def _done(self, reply) -> None:
        if not self:
            return
        if reply.needs_confirmation:
            from .dialogs import ask_yes_no
            if ask_yes_no(self, t("agent.over_budget", cost=f"{reply.cost:.3f}"),
                          t("agent.title")):
                speak(t("agent.thinking"))
                self._run(lambda: self.agent.resume())
                return
            reply.answer = reply.answer or t("agent.stopped")
        self._busy = False
        self.ask_btn.Enable()
        self.SetTitle(t("agent.title"))
        if reply.error:
            text = t("agent.error", error=reply.error)
        else:
            text = reply.answer or t("agent.no_answer")
        self._append(t("agent.said", text=text))
        speak(text)
        if reply.proposals:
            self.decide(reply.proposals)
        self.question.SetFocus()

    # ── approving ────────────────────────────────────────────────
    def decide(self, proposals) -> int:
        """Summary, then Accept all / Review one by one / Reject all.
        Returns how many changes were applied."""
        descs = self.agent.ctx.descriptions
        counts = {}
        for p in proposals:
            counts[p.action] = counts.get(p.action, 0) + 1
        summary = t("agent.summary", count=len(proposals), detail=", ".join(
            t(f"agent.kind_{k}", n=n) for k, n in counts.items()))
        lines = "\n".join(f"- {describe_proposal(p, descs)}" for p in proposals)
        speak(summary)
        dlg = wx.MessageDialog(self, f"{summary}\n\n{lines}", t("agent.title"),
                               wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION)
        dlg.SetYesNoCancelLabels(t("agent.accept_all"), t("agent.review_each"),
                                 t("agent.reject_all"))
        choice = dlg.ShowModal()
        dlg.Destroy()
        if choice == wx.ID_YES:
            chosen = list(proposals)
        elif choice == wx.ID_NO:
            chosen = []
            for i, p in enumerate(proposals, 1):
                one = wx.MessageDialog(
                    self, t("agent.review_one", n=i, total=len(proposals),
                            text=describe_proposal(p, descs)),
                    t("agent.title"), wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION)
                one.SetYesNoCancelLabels(t("agent.accept_one"),
                                         t("agent.skip_one"),
                                         t("agent.stop_review"))
                answer = one.ShowModal()
                one.Destroy()
                if answer == wx.ID_YES:
                    chosen.append(p)
                elif answer == wx.ID_CANCEL:
                    break
        else:
            chosen = []   # Reject all, Esc
        applied = self.player.apply_agent_changes(chosen) if chosen else 0
        text = (t("agent.applied", count=applied) if applied
                else t("agent.nothing_applied"))
        self._append(text)
        speak(text)
        self.undo_btn.Enable(self.player.can_undo_agent())
        return applied

    def undo(self) -> None:
        if self.player.undo_agent_changes():
            text = t("agent.undone")
        else:
            text = t("agent.nothing_to_undo")
        self._append(text)
        speak(text)
        self.undo_btn.Enable(self.player.can_undo_agent())
