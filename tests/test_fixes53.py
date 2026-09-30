"""Regression round 53: the Player agent's engine (v1.9.0, phase B).

core/agent.py drives OpenRouter tool calls. Pinned here with a scripted
fake model, so every rule is checked on every gate run for free:

  - a proposal before looking at the frames is REFUSED (phase A: all
    models looked first when told to; the engine now enforces it);
  - at the turn limit the agent is made to answer without tools
    (phase A: Gemini 3.8 once looked until the limit and said nothing);
  - the cost cap stops and waits for "continue?", then resumes;
  - a proposal is validated (action, index, time, text length);
  - the agent can change NOTHING itself — it only returns proposals;
  - session memory keeps words, drops old pictures;
  - read/search/transcript/gaps/check_rules/characters/seek work;
  - "Test agent mode" judges behaviour, not the model's opinion.
"""
import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from types import SimpleNamespace

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")
os.environ.setdefault("ODC_CONFIG_DIR", tempfile.mkdtemp(prefix="odc_t53_cfg_"))

from omni_describer_custom.core import agent as ag  # noqa: E402
from omni_describer_custom.core.tools import find_tool  # noqa: E402

results: list[tuple[str, bool]] = []
TMP = Path(tempfile.mkdtemp(prefix="odc_t53_"))


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
    out = TMP / "clip.mp4"
    if not out.exists():
        subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi",
                        "-i", "testsrc=size=320x240:rate=10:duration=30",
                        "-c:v", "libx264", str(out)], check=True, timeout=120)
    return out


def call(name, **args):
    return {"id": f"c_{name}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


def turn(*calls, content="", cost=0.001):
    msg = {"role": "assistant", "content": content}
    if calls:
        msg["tool_calls"] = list(calls)
    return {"choices": [{"message": msg}], "usage": {"cost": cost}}


class Script:
    """A fake model: returns the scripted turns in order, records payloads."""

    def __init__(self, turns):
        self.turns, self.payloads = list(turns), []

    async def __call__(self, payload):
        self.payloads.append(json.loads(json.dumps(payload)))
        return self.turns.pop(0) if self.turns else turn(content="Done.")


def make(turns, **ctx):
    seeks = []
    context = ag.Context(
        video=str(video()), length=30.0,
        descriptions=[(2.0, "A test pattern."), (10.0, "A red dragon flies.")],
        get_position=lambda: 10.0, seek=seeks.append,
        get_transcript=lambda: [SimpleNamespace(start=4.0, end=8.0, text="Hello there."),
                                SimpleNamespace(start=15.0, end=18.0, text="Go.")],
        characters_file=str(TMP / "characters.json"), **ctx)
    script = Script(turns)
    steps = []
    agent = ag.Agent("k", "m", context, post=script,
                     on_step=lambda code, args: steps.append(code))
    return agent, script, seeks, steps


def test_no_proposal_before_looking():
    agent, script, _s, _st = make([
        turn(call("propose_change", action="remove", index=1, reason="x")),
        turn(call("look_at", seconds=10)),
        turn(call("propose_change", action="remove", index=1, reason="no dragon")),
        turn(content="Removed the dragon line."),
    ])
    reply = asyncio.run(agent.ask("Is [1] right?"))
    tool_msgs = [m["content"] for m in agent.messages if m.get("role") == "tool"]
    assert tool_msgs[0].startswith("Refused: look at the frames first"), tool_msgs
    assert [p.action for p in reply.proposals] == ["remove"], reply.proposals
    assert reply.answer == "Removed the dragon line."
    # the look sent a real picture back as a user message
    images = [m for m in agent.messages if m.get("role") == "user"
              and isinstance(m.get("content"), list)]
    assert images and images[0]["content"][1]["image_url"]["url"].startswith(
        "data:image/jpeg;base64,")
    agent.close()


def test_turn_limit_forces_an_answer():
    looks = [turn(call("look_at", seconds=i)) for i in range(ag.MAX_TURNS)]
    agent, script, _s, _st = make(looks + [turn(content="I could not decide.")])
    reply = asyncio.run(agent.ask("Check everything."))
    assert reply.answer == "I could not decide."
    last = script.payloads[-1]
    assert "tools" not in last, "the final request still offered tools"
    assert "Stop using tools" in last["messages"][-1]["content"]
    agent.close()


def test_cost_cap_asks_then_resumes():
    agent, script, _s, _st = make([
        turn(call("look_at", seconds=3), cost=0.015),
        turn(call("look_at", seconds=4), cost=0.015),
        turn(call("propose_change", action="edit", index=0,
                  text="Colour bars fill the screen.", reason="pattern"), cost=0.001),
        turn(content="Edited it.", cost=0.001),
    ])
    reply = asyncio.run(agent.ask("Fix [0]."))
    assert reply.needs_confirmation and not reply.answer, reply
    reply = asyncio.run(agent.resume())
    assert not reply.needs_confirmation and reply.answer == "Edited it."
    assert [p.text for p in reply.proposals] == ["Colour bars fill the screen."]
    assert abs(reply.cost - 0.032) < 1e-9, reply.cost
    agent.close()


def test_proposals_are_validated():
    agent, _sc, _s, _st = make([])
    agent._looked = True
    reply = ag.Reply()
    bad = [dict(action="delete", reason="x"),
           dict(action="edit", index=9, text="x", reason="x"),
           dict(action="move", index=0, time=99, reason="x"),
           dict(action="add", time=5, reason="x"),
           dict(action="edit", index=0, reason="x",
                text=" ".join(["word"] * 25))]
    for args in bad:
        assert agent._propose(args, reply).startswith("Refused"), args
    assert agent._propose(dict(action="keep", index=0, reason="fine"), reply) \
        .startswith("Proposal recorded")
    assert reply.proposals == [], "keep is not a change"
    assert agent._propose(dict(action="add", time=12.5, text="A door opens.",
                               reason="missing"), reply).startswith("Proposal")
    assert reply.proposals[0].time == 12.5
    agent.close()


def test_the_agent_cannot_write():
    agent, _sc, _s, _st = make([])
    names = {t["name"] for t in ag.TOOLS}
    for forbidden in ("download", "delete", "save", "write", "settings",
                      "export", "remove_file"):
        assert not any(forbidden in n for n in names), names
    before = list(agent.ctx.descriptions)
    agent._looked = True
    agent._propose(dict(action="remove", index=0, reason="x"), ag.Reply())
    assert agent.ctx.descriptions == before, "a proposal changed the descriptions"
    agent.close()


def test_memory_keeps_words_not_old_pictures():
    agent, script, _s, _st = make([
        turn(call("look_at", seconds=3)), turn(content="It shows bars."),
        turn(content="Yes, the same bars."),
    ])
    asyncio.run(agent.ask("What is at 3 s?"))
    asyncio.run(agent.ask("And again?"))
    second = script.payloads[-1]["messages"]
    assert any("What is at 3 s?" == m.get("content") for m in second), \
        "the first question was forgotten"
    assert not any(isinstance(m.get("content"), list) for m in second), \
        "an old picture was sent again"
    agent.close()


def test_tools_answer_from_the_project():
    agent, _sc, seeks, steps = make([])
    d = agent._dispatch
    r = ag.Reply()
    assert "[1] 10.0s: A red dragon flies." in d("read_descriptions",
                                                  {"start": 5, "end": 12}, r)[0]
    assert "[1]" in d("search_descriptions", {"query": "red dragon"}, r)[0]
    assert "Hello there." in d("transcript", {"start": 0, "end": 10}, r)[0]
    gaps = d("find_gap", {"start": 0, "end": 20}, r)[0]
    assert "0.0-4.0s" in gaps and "8.0-15.0s" in gaps, gaps
    rules = d("check_rules", {"text": "A dragon lands on a rock.", "time": 9}, r)[0]
    assert "6 words" in rules and "OK" in rules and "fits" in rules, rules
    long = d("check_rules", {"text": " ".join(["w"] * 14), "time": 4}, r)[0]
    assert "TOO LONG" in long and "does NOT fit" in long, long
    assert "mentions sound" in d("check_rules", {"text": "She says hello.",
                                                 "time": 9}, r)[0]
    assert d("seek", {"seconds": 12}, r)[0].startswith("The player is now at")
    assert seeks == [12.0]
    d("characters", {"action": "remember", "name": "Sintel",
                     "description": "girl with a spear"}, r)
    assert "Sintel: girl with a spear" in d("characters", {"action": "list"}, r)[0]
    sheet = d("search_video", {"start": 0, "end": 30}, r)[1]
    assert sheet and "12 frames" in sheet["content"][0]["text"]
    zoom = d("zoom", {"seconds": 5, "area": "top-left"}, r)[1]
    assert zoom and "top-left" in zoom["content"][0]["text"]
    assert "looking" in steps and "seek" in steps
    agent.close()
    assert not agent.frames.dir.exists(), "frames folder left behind"


def test_probe_judges_behaviour():
    good = Script([turn(call("look_at", seconds=1)),
                   turn(call("propose_change", action="edit", index=0,
                             text="A red screen shows RED.", reason="red")),
                   turn(content="Fixed it.")])
    r = asyncio.run(ag.probe("k", "m", post=good))
    assert r["ok"] and r["looked"] and r["proposals"], r
    lazy = Script([turn(content="It is probably fine.")])
    r = asyncio.run(ag.probe("k", "m", post=lazy))
    assert not r["ok"], "a model that never used a tool passed"
    blind = Script([turn(call("propose_change", action="edit", index=0,
                              text="Red.", reason="guess")),
                    turn(content="Done.")])
    r = asyncio.run(ag.probe("k", "m", post=blind))
    assert not r["ok"], "a model that never looked passed"


def test_temp_folders_are_swept():
    from omni_describer_custom.core import housekeeping
    assert "odc_agent_" in housekeeping._OUR_PREFIXES


def test_check_all_gathers_one_list():
    turns = [
        # stretch 0-60: looks, proposes an edit, answers
        turn(call("look_between", start=0, end=20)),
        turn(call("propose_change", action="edit", index=0,
                  text="Colour bars and a clock.", reason="bars")),
        turn(content="One fix."),
        # stretch 60-120: an edit with the SAME text is refused
        turn(call("look_at", seconds=70)),
        turn(call("propose_change", action="edit", index=2,
                  text="A late line!", reason="same")),
        turn(content="Nothing to change."),
    ]
    agent, script, _s, _st = make(turns)
    agent.ctx.descriptions = [(2.0, "A test pattern."), (10.0, "A dragon."),
                              (70.0, "A late line.")]
    agent.ctx.length = 120.0
    agent.messages.append({"role": "user", "content": "earlier question"})
    progress = []
    reply = asyncio.run(agent.check_all(on_progress=lambda n, t: progress.append((n, t))))
    assert progress == [(1, 2), (2, 2)], progress
    assert [(p.action, p.index) for p in reply.proposals] == [("edit", 0)], reply.proposals
    assert agent.messages[-1]["content"] == "earlier question",         "the person's own conversation was replaced"
    # every stretch started fresh: system prompt + one question
    firsts = [p["messages"] for p in script.payloads]
    assert all(m[0]["role"] == "system" for m in firsts)
    assert "earlier question" not in json.dumps(firsts)
    agent.close()


def test_check_all_can_be_stopped():
    agent, _sc, _s, _st = make([])
    agent.ctx.length = 300.0
    agent.ctx.descriptions = [(t, f"line {t}") for t in (10.0, 70.0, 130.0)]
    reply = asyncio.run(agent.check_all(is_cancelled=lambda: True))
    assert reply.error == "cancelled" and not reply.proposals
    agent.close()


def test_gemini_direct():
    """v1.9.2: Gemini with the user's own key. Google's OpenAI-compatible
    endpoint, no OpenRouter-only fields, and a cost worked out from tokens
    (Google returns none) so the cost cap still works."""
    context = ag.Context(video=str(video()), length=30.0,
                         descriptions=[(2.0, "A test pattern.")],
                         get_position=lambda: 2.0)
    usage = {"prompt_tokens": 10_000, "completion_tokens": 1_000}
    script = Script([{"choices": [{"message": {"role": "assistant",
                                               "content": "Fine."}}],
                      "usage": usage}])
    agent = ag.Agent("k", "gemini-no-such-model", context, post=script,
                     provider="gemini")
    reply = asyncio.run(agent.ask("Is it right?"))
    agent.close()
    body = script.payloads[0]
    assert "usage" not in body and "reasoning" not in body, body.keys()
    assert body["tools"] and body["model"] == "gemini-no-such-model"
    price_in, price_out = ag.FALLBACK_PRICE
    want = (10_000 * price_in + 1_000 * price_out) / 1e6
    assert abs(reply.cost - want) < 1e-9, (reply.cost, want)

    # The real transport goes to Google, not OpenRouter.
    from omni_describer_custom.core import ai_engine
    seen = {}

    async def fake_http(method, url, **kw):
        seen["url"], seen["auth"] = url, kw["headers"]["Authorization"]
        return {"choices": [{"message": {"role": "assistant", "content": "x"}}]}
    real = ai_engine._http_json
    ai_engine._http_json = fake_http
    try:
        gem = ag.Agent("key-g", "m", context, provider="gemini")
        asyncio.run(gem.ask("q"))
        gem.close()
        assert seen["url"] == ag.GEMINI_URL and seen["auth"] == "Bearer key-g"
        orr = ag.Agent("key-o", "m", context)
        asyncio.run(orr.ask("q"))
        orr.close()
        assert seen["url"] == ag.URL, seen
    finally:
        ai_engine._http_json = real


def test_gemini_price_from_catalog():
    from omni_describer_custom.core import model_catalog
    real = model_catalog.load_cache
    model_catalog.load_cache = lambda: ([{"id": "google/gemini-z",
                                          "price_in": 0.25,
                                          "price_out": 1.5}], 0)
    try:
        assert ag.gemini_price("gemini-z") == (0.25, 1.5)
        assert ag.gemini_price("gemini-unknown") == ag.FALLBACK_PRICE
    finally:
        model_catalog.load_cache = real


def main() -> int:
    check("no proposal before looking", test_no_proposal_before_looking)
    check("the turn limit forces an answer", test_turn_limit_forces_an_answer)
    check("the cost cap asks, then resumes", test_cost_cap_asks_then_resumes)
    check("proposals are validated", test_proposals_are_validated)
    check("the agent cannot write", test_the_agent_cannot_write)
    check("memory keeps words, not old pictures",
          test_memory_keeps_words_not_old_pictures)
    check("tools answer from the project", test_tools_answer_from_the_project)
    check("Test agent mode judges behaviour", test_probe_judges_behaviour)
    check("check the whole video gathers one list", test_check_all_gathers_one_list)
    check("check the whole video can be stopped", test_check_all_can_be_stopped)
    check("temp folders are swept", test_temp_folders_are_swept)
    check("Gemini direct: Google endpoint, cost from tokens", test_gemini_direct)
    check("Gemini price comes from the catalog", test_gemini_price_from_catalog)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
