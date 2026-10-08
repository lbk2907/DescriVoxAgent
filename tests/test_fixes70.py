"""Regression round 70: checklist 23.8 - the agent's two loose ends.

1. It sometimes said a fix in words ("it should say a red car") without
   calling propose_change, so there was nothing to accept and the person
   had to edit by hand. Such an answer is now sent back once.
2. It sometimes ended with an EMPTY answer at the turn limit. The forced
   answer is asked for once more; still empty with proposals, the window
   says how many changes are waiting instead of "no answer".
"""

import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
import io
import json
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

if "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
sys.path.insert(0, "src")

from omni_describer_custom.core import agent as ag  # noqa: E402
from omni_describer_custom.core.tools import find_tool  # noqa: E402

results: list[tuple[str, bool]] = []
TMP = Path(tempfile.mkdtemp(prefix="odc_t70_"))


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
        subprocess.run(
            [
                find_tool("ffmpeg"),
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=160x120:rate=5:duration=20",
                "-c:v",
                "libx264",
                str(out),
            ],
            check=True,
            timeout=120,
        )
    return out


def call(name, **args):
    return {
        "id": f"c_{name}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def turn(*calls, content=""):
    msg = {"role": "assistant", "content": content}
    if calls:
        msg["tool_calls"] = list(calls)
    return {"choices": [{"message": msg}], "usage": {"cost": 0.001}}


class Script:
    def __init__(self, turns):
        self.turns, self.payloads = list(turns), []

    async def __call__(self, payload):
        self.payloads.append(json.loads(json.dumps(payload)))
        return self.turns.pop(0) if self.turns else turn(content="Done.")


def make(turns):
    context = ag.Context(
        video=str(video()),
        length=20.0,
        descriptions=[(2.0, "A test pattern."), (10.0, "A blue car.")],
        characters_file=str(TMP / "characters.json"),
    )
    script = Script(turns)
    return ag.Agent("k", "m", context, post=script), script


def test_words_only_fix_is_sent_back_once():
    agent, script = make(
        [
            turn(call("look_at", seconds=10)),
            turn(content="Description 1 should say a red car, not a blue car."),
            turn(
                call(
                    "propose_change",
                    action="edit",
                    index=1,
                    text="A red car.",
                    reason="the car is red",
                )
            ),
            turn(content="Proposed: the car is red."),
        ]
    )
    reply = asyncio.run(agent.ask("Is [1] right?"))
    nudges = [
        m
        for m in agent.messages
        if m.get("role") == "user" and m.get("content") == ag.NUDGE_PROPOSE
    ]
    assert len(nudges) == 1, len(nudges)
    assert len(reply.proposals) == 1 and reply.answer == "Proposed: the car is red."


def test_a_plain_answer_is_not_sent_back():
    agent, script = make([turn(content="Description 1 is correct.")])
    reply = asyncio.run(agent.ask("Is [1] right?"))
    assert reply.answer == "Description 1 is correct." and len(script.payloads) == 1


def test_never_sent_back_twice():
    agent, script = make(
        [
            turn(content="It should say a red car."),
            turn(content="It should say a red car, I think."),
        ]
    )
    reply = asyncio.run(agent.ask("Is [1] right?"))
    assert reply.answer == "It should say a red car, I think." and len(script.payloads) == 2


def test_empty_final_answer_is_asked_again():
    looks = [turn(call("look_at", seconds=2)) for _ in range(ag.MAX_TURNS)]
    agent, script = make(looks + [turn(content=""), turn(content="I could not decide.")])
    reply = asyncio.run(agent.ask("Look around."))
    assert reply.answer == "I could not decide.", reply.answer
    assert "tools" not in script.payloads[-1] or not script.payloads[-1].get("tools")


def test_window_says_changes_are_waiting():
    from omni_describer_custom.i18n.strings import I18n, t

    I18n.set_language("en")
    assert t("agent.no_answer_proposals", count=2).endswith("proposed 2 changes: review them now.")
    assert t("agent.no_answer_proposals", count=1).endswith("proposed 1 change: review it now.")
    src = Path("src/omni_describer_custom/ui/agent_dialog.py").read_text(encoding="utf-8")
    assert 't("agent.no_answer_proposals", count=len(reply.proposals))' in src


def main() -> int:
    check("a fix in words only is sent back once", test_words_only_fix_is_sent_back_once)
    check("a plain answer is not sent back", test_a_plain_answer_is_not_sent_back)
    check("never sent back twice", test_never_sent_back_twice)
    check("an empty final answer is asked for again", test_empty_final_answer_is_asked_again)
    check("the window says changes are waiting", test_window_says_changes_are_waiting)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
