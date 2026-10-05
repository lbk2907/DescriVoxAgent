"""Regression round 71: owner, 5 Oct 2026 - "can the agent change characters?"

The agent could remember a name but only propose edits one description at
a time. propose_rename makes ONE proposal - "Name Encik Rahim: replace
'the man in the grey coat' in 3 descriptions" - that the person accepts
or rejects like any other; accepted, every description changes and the
name joins the cast as the person's.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
import io
import json
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

if "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
sys.path.insert(0, "src")

import wx  # noqa: E402

from omni_describer_custom.core import agent as ag  # noqa: E402
from omni_describer_custom.core import characters as ch  # noqa: E402
from omni_describer_custom.core.project_store import Description, ProjectStore  # noqa: E402
from omni_describer_custom.core.tools import find_tool  # noqa: E402

results: list[tuple[str, bool]] = []
TMP = Path(tempfile.mkdtemp(prefix="odc_t71_"))
TEXTS = ["The man in the grey coat sits.", "Aisyah waves at the man in the grey coat.",
         "A car passes.", "The man in the grey coat stands."]


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def video() -> Path:
    out = TMP / "v.mp4"
    if not out.exists():
        subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi",
                        "-i", "testsrc=size=160x120:rate=5:duration=20",
                        "-c:v", "libx264", str(out)], check=True, timeout=120)
    return out


def call(name, **args):
    return {"id": f"c_{name}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


def turn(*calls, content=""):
    msg = {"role": "assistant", "content": content}
    if calls:
        msg["tool_calls"] = list(calls)
    return {"choices": [{"message": msg}], "usage": {"cost": 0.001}}


def agent_with(turns):
    turns = list(turns)

    async def post(payload):
        return turns.pop(0) if turns else turn(content="Done.")
    ctx = ag.Context(video=str(video()), length=20.0,
                     descriptions=[(i * 4.0, x) for i, x in enumerate(TEXTS)],
                     characters_file=str(TMP / "characters.json"))
    return ag.Agent("k", "m", ctx, post=post)


def test_one_proposal_for_every_description():
    agent = agent_with([
        turn(call("propose_rename", old="the man in the grey coat", new="Encik Rahim",
                  reason="the person named him")),
        turn(content="Proposed the name."),
    ])
    reply = asyncio.run(agent.ask("The man in the grey coat is Encik Rahim."))
    assert len(reply.proposals) == 1, reply.proposals
    p = reply.proposals[0]
    assert (p.action, p.old, p.text) == ("rename", "the man in the grey coat", "Encik Rahim")
    from omni_describer_custom.i18n.strings import I18n
    from omni_describer_custom.ui.agent_dialog import describe_proposal
    I18n.set_language("en")
    said = describe_proposal(p, agent.ctx.descriptions)
    assert said.startswith('Name Encik Rahim: replace "the man in the grey coat" in 3 descriptions.'), said


def test_a_label_nobody_uses_is_refused():
    agent = agent_with([
        turn(call("propose_rename", old="the tall stranger", new="Hans", reason="x")),
        turn(content="Could not find him."),
    ])
    reply = asyncio.run(agent.ask("Name the tall stranger Hans."))
    tool = [m["content"] for m in agent.messages if m.get("role") == "tool"]
    assert not reply.proposals and tool and tool[0].startswith("Refused"), tool


def test_accepted_rename_changes_every_description_and_the_cast():
    from omni_describer_custom.core.tts_engine import TTSEngine
    from omni_describer_custom.ui.player_window import PlayerWindow
    store = ProjectStore(projects_dir=str(TMP / f"p{time.monotonic_ns()}"))
    store.create_project("Rename", str(video()))
    store.set_video_duration(20.0)
    store.save_descriptions([Description(start_time=i * 4.0, end_time=i * 4.0 + 2, text=x)
                             for i, x in enumerate(TEXTS)])
    folder = store.project_dir(store.current.id)
    ch.save_cast(folder, [{"name": "the man in the grey coat", "look": "briefcase"},
                          {"name": "Aisyah", "look": "blue headscarf"}])
    w = PlayerWindow(None, store, TTSEngine({}))
    try:
        applied = w.apply_agent_changes([ag.Proposal(action="rename", reason="named",
                                                     old="the man in the grey coat",
                                                     text="Encik Rahim")])
        assert applied == 1, applied
        texts = [d.text for d in store.current.descriptions]
        assert texts == ["Encik Rahim sits.", "Aisyah waves at Encik Rahim.",
                         "A car passes.", "Encik Rahim stands."], texts
        cast = ch.load_cast(folder)
        assert cast[0] == {"name": "Encik Rahim", "look": "briefcase", "by_user": True}, cast
        assert [c["name"] for c in cast] == ["Encik Rahim", "Aisyah"], cast
        assert w.undo_agent_changes() and store.current.descriptions[0].text == TEXTS[0]
    finally:
        w.Destroy()


def main() -> int:
    app = wx.App(False)
    check("one proposal for every description", test_one_proposal_for_every_description)
    check("a label nobody uses is refused", test_a_label_nobody_uses_is_refused)
    check("an accepted rename changes every description and the cast",
          test_accepted_rename_changes_every_description_and_the_cast)
    del app
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
