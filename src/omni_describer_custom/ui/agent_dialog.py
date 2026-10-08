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
    if p.action == "rename":
        from ..core.characters import rename_in_texts

        _texts, count = rename_in_texts([d for _, d in descriptions], p.old, p.text)
        return t("agent.proposal_rename", old=p.old, new=p.text, count=count, reason=p.reason)
    when = _clock(p.time if p.time is not None else (descriptions[p.index][0] if old else 0))
    return t(f"agent.proposal_{p.action}", old=old, new=p.text, when=when, reason=p.reason)


class AgentDialog(wx.Dialog):
    def __init__(self, player, agent):
        super().__init__(
            player,
            title=t("agent.title"),
            size=(620, 480),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.player, self.agent = player, agent
        self._busy = False
        self._last_step = ""
        self.agent.on_step = self._on_step

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(panel, label=t("agent.conversation")), 0, wx.ALL, 5)
        self.log = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            size=(-1, 220),
            name=t("agent.conversation"),
        )
        sizer.Add(self.log, 1, wx.ALL | wx.EXPAND, 5)
        sizer.Add(wx.StaticText(panel, label=t("agent.question")), 0, wx.ALL, 5)
        self.question = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER, name=t("agent.question"))
        sizer.Add(self.question, 0, wx.ALL | wx.EXPAND, 5)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.ask_btn = wx.Button(panel, label=t("agent.ask_btn"))
        self.check_all_btn = wx.Button(panel, label=t("agent.check_all_btn"))
        self.undo_btn = wx.Button(panel, label=t("agent.undo_btn"))
        self.close_btn = wx.Button(panel, wx.ID_CLOSE, t("close"))
        row.Add(self.ask_btn, 0, wx.ALL, 5)
        row.Add(self.check_all_btn, 0, wx.ALL, 5)
        row.Add(self.undo_btn, 0, wx.ALL, 5)
        row.AddStretchSpacer()
        row.Add(self.close_btn, 0, wx.ALL, 5)
        sizer.Add(row, 0, wx.ALL | wx.EXPAND, 5)
        panel.SetSizer(sizer)

        self.undo_btn.Enable(player.can_undo_agent())
        self.question.Bind(wx.EVT_TEXT_ENTER, lambda e: self.submit())
        self.ask_btn.Bind(wx.EVT_BUTTON, lambda e: self.ask_or_stop())
        self.undo_btn.Bind(wx.EVT_BUTTON, lambda e: self.undo())
        self.check_all_btn.Bind(wx.EVT_BUTTON, lambda e: self.check_all())
        self._checking = False
        self._asking = False
        # One stop flag per run (v1.9.6). A threading.Event, not an
        # attribute read through `self`: the worker still reads it after
        # the window is destroyed. Close, Esc, Stop and Stop checking all
        # set it; the engine gives up within about half a second.
        self._stop = threading.Event()
        self.close_btn.Bind(wx.EVT_BUTTON, lambda e: self.close())
        self.SetEscapeId(wx.ID_CLOSE)
        self.Bind(wx.EVT_CLOSE, lambda e: self.close())
        for line in getattr(player, "_agent_transcript", []):
            self.log.AppendText(line)
        self.question.SetFocus()

    # ── speaking ─────────────────────────────────────────────────
    def _on_step(self, code: str, args: dict) -> None:
        """Called on the worker thread for each tool the agent uses."""
        text = t(f"agent.step_{code}", at=_clock(args.get("at", 0)), end=_clock(args.get("end", 0)))
        if text == self._last_step:
            return  # six looks in a row are said once
        self._last_step = text
        wx.CallAfter(self._status, text, True)

    def _status(self, text: str, say: bool) -> None:
        # Spoken only. It used to go into the window title too, and when
        # focus came back to the dialog NVDA read the step a second time
        # ("Checking part 1 of 1 dialog"), heard in the v1.9.1 check.
        if not self:
            return
        if say:
            speak(text)

    def _append(self, line: str) -> None:
        self.log.AppendText(line + "\n")
        self.player._agent_transcript.append(line + "\n")

    # ── asking ───────────────────────────────────────────────────
    def submit(self, question: str | None = None) -> None:
        question = (question if question is not None else self.question.GetValue()).strip()
        if self._busy:
            return
        if not question:
            speak(t("agent.empty"))
            return
        if self.agent.busy:
            # An earlier window's run is still stopping (it shares this
            # Agent): never start a second one next to it.
            speak(t("agent.still_working"))
            return
        self._busy = self._asking = True
        self._stop = stop = threading.Event()
        self.ask_btn.SetLabel(t("agent.ask_stop_btn"))
        self.check_all_btn.Disable()
        self.question.SetValue("")
        self._append(t("agent.you", text=question))
        self._last_step = ""
        speak(t("agent.thinking"))
        self._run(lambda: self.agent.ask(question, is_cancelled=stop.is_set))

    def ask_or_stop(self) -> None:
        """The Ask button; while an ask runs it is "Stop asking" (v1.9.6).
        Enter in the question box only ever asks, so typing the next
        question cannot stop the current one by accident."""
        if self._asking:
            self.stop()
        else:
            self.submit()

    def stop(self) -> None:
        """Stop asking / Stop checking: the engine gives up within about
        half a second, keeping the proposals found so far."""
        if not self._busy or self._stop.is_set():
            return
        self._stop.set()
        speak(t("agent.check_all_stopping") if self._checking else t("agent.stopping"))

    def close(self) -> None:
        """Close, Esc, Alt+F4: stop whatever is running first (v1.9.6) —
        a run left going kept paying for requests nobody would hear."""
        self._stop.set()
        if self.IsModal():
            self.EndModal(wx.ID_CLOSE)
        else:
            self.Hide()

    def _run(self, make_coro) -> None:
        def work():
            loop = asyncio.new_event_loop()
            try:
                reply = loop.run_until_complete(make_coro())
            except Exception as e:
                logger.error("Agent failed: %s", e)
                from ..core.agent import Reply

                reply = Reply(error=str(e))
            finally:
                loop.close()
            wx.CallAfter(self._done, reply)

        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _error_text(error: str) -> str:
        """Any failure in words (v1.9.6): the one translator, so no JSON,
        URL or account id is read out."""
        from ..core.agent import BUSY

        if error == BUSY:
            return t("agent.still_working")
        from ..core.ai_engine import user_error_text

        return user_error_text(error)

    def _done(self, reply) -> None:
        if not self:
            return
        self._asking = False
        self.ask_btn.SetLabel(t("agent.ask_btn"))
        self.check_all_btn.Enable()
        if self._checking:
            self._checking = False
            self.check_all_btn.SetLabel(t("agent.check_all_btn"))
            self._busy = False
            self.ask_btn.Enable()
            self.SetTitle(t("agent.title"))
            stopped = reply.error == "cancelled"
            text = (
                t("agent.check_all_stopped", count=len(reply.proposals))
                if stopped
                else t("agent.check_all_done", count=len(reply.proposals), cost=f"{reply.cost:.3f}")
            )
            if reply.error and not stopped:
                text += " " + self._error_text(reply.error)
            self._append(text)
            speak(text)
            if reply.proposals:
                self.decide(reply.proposals)
            self.question.SetFocus()
            return
        if reply.needs_confirmation and not self._stop.is_set():
            from .dialogs import ask_yes_no

            if ask_yes_no(self, t("agent.over_budget", cost=f"{reply.cost:.3f}"), t("agent.title")):
                speak(t("agent.thinking"))
                self._asking = True
                self._stop = stop = threading.Event()
                self.ask_btn.SetLabel(t("agent.ask_stop_btn"))
                self.check_all_btn.Disable()
                self._run(lambda: self.agent.resume(is_cancelled=stop.is_set))
                return
        if reply.needs_confirmation:
            reply.answer = reply.answer or t("agent.stopped")
        self._busy = False
        self.ask_btn.Enable()
        self.SetTitle(t("agent.title"))
        if reply.error == "cancelled":
            text = t("agent.stopped")  # asked for, not a failure
        elif reply.error:
            text = self._error_text(reply.error)
        elif reply.answer:
            text = reply.answer
        elif reply.proposals:
            # 23.8: no words, but changes to review - say so.
            text = t("agent.no_answer_proposals", count=len(reply.proposals))
        else:
            text = t("agent.no_answer")
        self._append(t("agent.said", text=text))
        speak(text)
        if reply.proposals:
            self.decide(reply.proposals)
        self.question.SetFocus()

    # ── the whole video (v1.9.1) ─────────────────────────────────
    def check_all(self) -> None:
        """Ask first (time and cost), then go through every description;
        pressing the same button again stops it."""
        if self._checking:
            self.stop()
            return
        if self._busy:
            return
        count = len(self.agent.ctx.descriptions)
        if not count:
            speak(t("agent.check_all_nothing"))
            return
        if self.agent.busy:
            speak(t("agent.still_working"))
            return
        stretches = max(1, int(self.agent.ctx.length // 60) + 1)
        from .dialogs import ask_yes_no

        if not ask_yes_no(
            self,
            t(
                "agent.check_all_confirm",
                count=count,
                minutes=max(1, round(stretches * 20 / 60)),
                cost=f"{stretches * 0.004:.2f}",
            ),
            t("agent.title"),
        ):
            return
        self._busy = self._checking = True
        self._stop = stop = threading.Event()
        self.ask_btn.Disable()
        self.check_all_btn.SetLabel(t("agent.check_all_stop"))
        self._append(t("agent.check_all_started", count=count))

        def progress(n, total):
            wx.CallAfter(self._status, t("agent.check_all_progress", n=n, total=total), True)

        self._run(lambda: self.agent.check_all(on_progress=progress, is_cancelled=stop.is_set))

    # ── approving ────────────────────────────────────────────────
    def decide(self, proposals) -> int:
        """Summary, then Accept all / Review one by one / Reject all.
        Returns how many changes were applied."""
        descs = self.agent.ctx.descriptions
        counts = {}
        for p in proposals:
            counts[p.action] = counts.get(p.action, 0) + 1
        summary = t(
            "agent.summary",
            count=len(proposals),
            detail=", ".join(t(f"agent.kind_{k}", n=n) for k, n in counts.items()),
        )
        lines = "\n".join(f"- {describe_proposal(p, descs)}" for p in proposals)
        speak(summary)
        dlg = wx.MessageDialog(
            self,
            f"{summary}\n\n{lines}",
            t("agent.title"),
            wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION,
        )
        dlg.SetYesNoCancelLabels(
            t("agent.accept_all"), t("agent.review_each"), t("agent.reject_all")
        )
        choice = dlg.ShowModal()
        dlg.Destroy()
        if choice == wx.ID_YES:
            chosen = list(proposals)
        elif choice == wx.ID_NO:
            chosen = []
            for i, p in enumerate(proposals, 1):
                one = wx.MessageDialog(
                    self,
                    t(
                        "agent.review_one",
                        n=i,
                        total=len(proposals),
                        text=describe_proposal(p, descs),
                    ),
                    t("agent.title"),
                    wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION,
                )
                one.SetYesNoCancelLabels(
                    t("agent.accept_one"), t("agent.skip_one"), t("agent.stop_review")
                )
                answer = one.ShowModal()
                one.Destroy()
                if answer == wx.ID_YES:
                    chosen.append(p)
                elif answer == wx.ID_CANCEL:
                    break
        else:
            chosen = []  # Reject all, Esc
        applied = self.player.apply_agent_changes(chosen) if chosen else 0
        text = t("agent.applied", count=applied) if applied else t("agent.nothing_applied")
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
