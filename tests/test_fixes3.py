"""Regression tests round 3: voice cache, ask-more history, apply close."""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import sys, io, traceback

if "pytest" not in sys.modules: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
if "pytest" not in sys.modules: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
sys.path.insert(0, "src")

ok = 0
fail = 0

def check(name, fn):
    global ok, fail
    try:
        fn()
        print(f"PASS: {name}")
        ok += 1
    except Exception as e:
        print(f"FAIL: {name}: {e}")
        traceback.print_exc()
        fail += 1

# 1. Edge voices cache: fetch once, second call served from cache
def test_edge_voice_cache():
    import asyncio
    from omni_describer_custom.core.tts_engine import EdgeTTSEngine

    eng = EdgeTTSEngine()
    if not eng.available:
        print("  (edge-tts unavailable, skipping)")
        return

    call_count = {"n": 0}
    real_list_voices = None

    # A fixed list, not Microsoft's server: one dropped request made the
    # engine (rightly) not cache the failure and ask again, and the gate
    # failed on 6 Oct 2026 for a network blip, not a bug.
    async def counting_list_voices(*args, **kwargs):
        call_count["n"] += 1
        return [{"ShortName": "en-US-AriaNeural", "Locale": "en-US",
                 "Gender": "Female", "FriendlyName": "Aria"}]

    import edge_tts
    real_list_voices = edge_tts.list_voices
    edge_tts.list_voices = counting_list_voices
    try:
        loop = asyncio.new_event_loop()
        try:
            v1 = loop.run_until_complete(eng.get_voices())
            v2 = loop.run_until_complete(eng.get_voices())
        finally:
            loop.close()
        assert v1 == v2
        assert call_count["n"] == 1, f"list_voices called {call_count['n']} times, cache not used"
    finally:
        edge_tts.list_voices = real_list_voices
check("EdgeTTSEngine voices cached after first fetch", test_edge_voice_cache)

# 2. AskMoreDialog records assistant replies in history
def test_askmore_history():
    import wx
    from omni_describer_custom.ui.ask_more_dialog import AskMoreDialog
    from omni_describer_custom.core.ai_engine import AIEngine  # noqa: F401 (checks the name still exists)

    _app = wx.GetApp() or wx.App(False)

    class FakeEngine:
        async def ask(self, question, history=None, model=""):
            return f"echo:{question}"

    dlg = AskMoreDialog(None, FakeEngine())
    dlg.question_text.SetValue("hello?")
    dlg._on_submit(None)
    # Wait for background thread
    import time
    deadline = time.time() + 10
    while time.time() < deadline:
        if len(dlg._history) >= 2:
            break
        wx.Yield()
        time.sleep(0.05)
    assert dlg._history[0] == {"role": "user", "content": "hello?"}, dlg._history
    assert dlg._history[1]["role"] == "assistant", dlg._history
    assert dlg._history[1]["content"] == "echo:hello?", dlg._history
    dlg.Destroy()
check("AskMoreDialog stores assistant replies", test_askmore_history)

# 3. AskMoreDialog history includes prior context in follow-up calls
def test_askmore_context_passed():
    import wx, time
    from omni_describer_custom.ui.ask_more_dialog import AskMoreDialog

    _app = wx.GetApp() or wx.App(False)

    received = {}

    class FakeEngine:
        async def ask(self, question, history=None, model=""):
            received["history"] = list(history or [])
            return "ok"

    dlg = AskMoreDialog(None, FakeEngine())
    dlg._history.extend([
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ])
    dlg.question_text.SetValue("q2")
    dlg._on_submit(None)
    deadline = time.time() + 10
    while time.time() < deadline and "history" not in received:
        wx.Yield()
        time.sleep(0.05)
    h = received.get("history", [])
    assert {"role": "user", "content": "q1"} in h and {"role": "assistant", "content": "a1"} in h, h
    dlg.Destroy()
check("AskMoreDialog passes prior context to AI", test_askmore_context_passed)

print(f"\nRESULT: {ok} passed, {fail} failed")
if "pytest" not in sys.modules: sys.exit(1 if fail else 0)
