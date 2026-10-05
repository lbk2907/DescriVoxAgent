"""Regression round 75: 34.1 honest floor (owner, 6 Oct 2026).

Idea from Watch Skill: a blind person cannot check an answer, so the agent
says "I cannot see that clearly" (and the times it looked at) instead of
guessing. Measured under two frozen contracts (measure-honest-floor and
measure-honest-floor-2): both VERIFIED; today's Gemini agent was already
honest, so the gain is one consistent phrase. The owner chose to keep it.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import sys
import traceback
from pathlib import Path

if "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools"))

from omni_describer_custom.core import agent as ag  # noqa: E402

results: list[tuple[str, bool]] = []


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def test_on_by_default_in_every_conversation():
    assert ag.HONEST_FLOOR is True
    text = ag.system_prompt("Malay")
    assert "I cannot see that clearly" in text and "times you looked at" in text
    assert text.startswith(ag.SYSTEM.format(language="Malay"))
    ctx = ag.Context(video="v.mp4", length=10.0, descriptions=[])
    agent = ag.Agent("k", "m", ctx, post=lambda p: None)
    assert "I cannot see that clearly" in agent.messages[0]["content"]


def test_the_switch_turns_it_off():
    try:
        ag.HONEST_FLOOR = False
        assert "I cannot see that clearly" not in ag.system_prompt("English")
    finally:
        ag.HONEST_FLOOR = True


def test_measured_under_frozen_contracts():
    import contracts as C
    for cid in ("measure-honest-floor", "measure-honest-floor-2"):
        C.load(cid)       # frozen, and as frozen


def test_scorer_counts_every_way_of_declining():
    import honest_bench as hb
    for said in ("I cannot see that clearly at 6:40.",
                 "It is not possible to determine the colour of her eyes.",
                 "There is no bicycle in this frame.",
                 "The plate is too blurry to read."):
        assert hb.abstained(said), said
    assert not hb.abstained("The girl's hair is a reddish-brown color.")
    hard = {q: kw for _c, _k, q, kw, _t in hb.HARD}
    assert hb.correct("The girl's hair is a reddish-brown color.",
                      hard["At this moment, what colour is the girl's hair?"])


def main() -> int:
    check("on by default, in every agent conversation", test_on_by_default_in_every_conversation)
    check("the switch turns it off (for measuring)", test_the_switch_turns_it_off)
    check("measured under frozen contracts", test_measured_under_frozen_contracts)
    check("the scorer counts every way of declining", test_scorer_counts_every_way_of_declining)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
