"""Regression round 69: owner, 5 Oct 2026 - characters.

"The same person is called different things" and "the AI does not use
the name even when everyone says it". A long video went to the AI in
5-minute parts and each part saw only the last six descriptions of the
one before. Now the name rules go into every full-video prompt, a cast
list travels through every part and is saved with the project, the
agent uses the same file, and the Characters window can give a person a
name in every description at once.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
import io
import json
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

from omni_describer_custom.core import characters as ch  # noqa: E402
from omni_describer_custom.core.project_store import Description, ProjectStore  # noqa: E402

results: list[tuple[str, bool]] = []
TMP = Path(tempfile.mkdtemp(prefix="odc_t69_"))


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def test_cast_lines_are_read():
    cast = ch.parse_cast("KNOWN CHARACTERS:\n- Aisyah — woman in a blue headscarf\n"
                         "* Ali: a boy\nnot a list line\n- Aisyah — again")
    assert [c["name"] for c in cast] == ["Aisyah", "Ali"], cast
    block = ch.cast_block(cast)
    assert "Aisyah — woman in a blue headscarf" in block and block.startswith("KNOWN CHARACTERS")
    assert ch.cast_block([]) == ""


def test_user_names_survive_the_ai():
    async def ask(prompt):
        assert "Rahim" in prompt          # the known cast goes in
        return "- Aisyah — blue headscarf"
    old = [{"name": "Rahim", "look": "grey coat", "by_user": True}]
    new = asyncio.run(ch.update_cast(ask, old, ["Rahim and a woman talk."]))
    assert [c["name"] for c in new] == ["Rahim", "Aisyah"], new

    async def broken(prompt):
        raise RuntimeError("HTTP 500")
    assert asyncio.run(ch.update_cast(broken, old, ["x"])) == old


def test_rename_everywhere():
    texts, n = ch.rename_in_texts(
        ["The man in the grey coat nods.", "Aisyah looks at the man in the grey coat.",
         "A dog runs."], "the man in the grey coat", "Rahim")
    assert texts[:2] == ["Rahim nods.", "Aisyah looks at Rahim."] and n == 2, texts


def test_capitals_are_not_kept():
    cast = ch.parse_cast("- THOM — man\n- WOMAN SOLDIER — rifle\n- Dr. Ali — doctor")
    assert [c["name"] for c in cast] == ["Thom", "Woman soldier", "Dr. Ali"], cast


def test_cast_request_caps_thinking():
    from omni_describer_custom.core.ai_engine import GLMProvider
    prov = GLMProvider(api_key="k")
    sent = []

    async def chat(payload, timeout=0, **k):
        sent.append(payload)
        return "- Aisyah — scarf"
    prov._chat = chat
    asyncio.run(prov._ask_capped("q", "m"))
    assert sent[0]["reasoning"] == {"max_tokens": prov._REASONING_BUDGET}, sent[0]


def test_old_agent_file_is_read():
    folder = TMP / "agentfile"
    folder.mkdir()
    (folder / "characters.json").write_text(json.dumps({"Sintel": "girl with a spear"}),
                                            encoding="utf-8")
    cast = ch.load_cast(folder)
    assert cast == [{"name": "Sintel", "look": "girl with a spear", "by_user": True}], cast


def test_cast_travels_through_every_part():
    """Three 5-minute parts: part 2 and 3 are told who part 1 met."""
    from omni_describer_custom.core.ai_engine import GLMProvider
    prov = GLMProvider(api_key="k")
    video = TMP / "v.mp4"
    video.write_bytes(b"x")
    prov._probe_duration = lambda p, is_cancelled=None: 900.0
    prov.split_video_for_upload = lambda *a, **k: ([0.0, 300.0, 600.0], [video, video, video])
    prompts, asked, seen = [], [], []

    async def one_part(part, prompt, model, **kw):
        prompts.append(prompt)
        return [(kw["offset"] + 5, f"Part {kw['part_index']}: the woman in red waves.")]

    async def ask_capped(q, model=""):
        asked.append(q)
        return "- the woman in red — long red dress"

    prov._describe_one_part = one_part
    prov._ask_capped = ask_capped
    pairs = asyncio.run(prov.describe_video_full(
        str(video), "Describe.", cast=[], on_cast=lambda c: seen.append(c)))
    assert len(pairs) == 3
    assert "KNOWN CHARACTERS" not in prompts[0]
    assert all("the woman in red — long red dress" in p for p in prompts[1:]), prompts[1]
    assert len(asked) == 3 and seen[-1][0]["name"] == "the woman in red"


def test_engine_rules_and_cast_for_a_whole_video_provider():
    from omni_describer_custom.core.ai_engine import AIEngine
    got = {}

    class Whole:
        name = "whole"

        async def describe_video_full(self, video_path, prompt, model, **kw):
            got["prompt"], got["kw"] = prompt, kw
            return []

    engine = AIEngine()
    engine._provider_or_raise = lambda name: Whole()
    engine._model_for = lambda p, m: "m"
    asyncio.run(engine.describe_video_full(
        "v.mp4", "Describe.", cast=[{"name": "Aisyah", "look": "blue headscarf"}]))
    assert "Use a person's NAME when it is heard" in got["prompt"]
    assert "Aisyah — blue headscarf" in got["prompt"]
    assert "cast" not in got["kw"]


def _store_with(texts):
    store = ProjectStore(projects_dir=str(TMP / f"projects{time.monotonic_ns()}"))
    store.create_project("Cast", "")
    store.save_descriptions([Description(start_time=i * 5.0, end_time=i * 5.0 + 2, text=x)
                             for i, x in enumerate(texts)])
    return store


def test_characters_window_names_someone_everywhere():
    from omni_describer_custom.ui import characters_dialog as cd
    store = _store_with(["The man in the grey coat sits.", "A car passes."])
    ch.save_cast(store.project_dir(store.current.id),
                 [{"name": "the man in the grey coat", "look": "grey coat"}])
    changed = []
    real = cd.ask_yes_no
    cd.ask_yes_no = lambda *a, **k: True
    dlg = cd.CharactersDialog(None, store, on_descriptions_changed=lambda: changed.append(1))
    try:
        dlg._say = lambda text: None
        assert dlg.list.GetString(0) == "the man in the grey coat — grey coat"
        dlg.cast[0] = {"name": "Rahim", "look": "grey coat", "by_user": True}
        dlg._save()
        dlg._rename_everywhere("the man in the grey coat", "Rahim")
        texts = [d.text for d in store.current.descriptions]
        assert texts == ["Rahim sits.", "A car passes."], texts
        reread = ProjectStore(projects_dir=store.projects_dir).open_project(store.current.id)
        assert reread.descriptions[0].text == "Rahim sits."
        assert changed and ch.load_cast(store.project_dir(store.current.id))[0]["name"] == "Rahim"
    finally:
        cd.ask_yes_no = real
        dlg.Destroy()


def test_the_run_saves_the_cast_for_a_whole_video_provider():
    from omni_describer_custom.ui.main_frame import MainFrame
    frame = MainFrame()
    try:
        frame.project_store = _store_with(["x"])
        logged = []
        frame._ui = (lambda fn, *a: logged.append(a)
                     if getattr(fn, "__name__", "") == "_log" else fn(*a))

        async def ask(q, *a, **k):
            return "- Aisyah — blue headscarf"
        frame.ai_engine.ask = ask
        loop = asyncio.new_event_loop()
        try:
            frame._finish_cast(loop, [(1.0, "Aisyah waves.")], None, None)
        finally:
            loop.close()
        saved = ch.load_cast(frame.project_store.project_dir(frame.project_store.current.id))
        assert saved == [{"name": "Aisyah", "look": "blue headscarf"}], saved
        assert logged, "the log does not say the characters were kept"
    finally:
        frame.Destroy()


def test_settings_switch():
    from omni_describer_custom.core.settings_store import SettingsStore
    assert SettingsStore().get("ai.characters", None) is True
    src = Path("src/omni_describer_custom/ui/main_frame.py").read_text(encoding="utf-8")
    assert 'self.settings.get("ai.characters", True))' in src
    assert "self.ai_engine.CHARACTERS = bool(" in src
    sd = Path("src/omni_describer_custom/ui/settings_dialog.py").read_text(encoding="utf-8")
    assert 'self.settings.set("ai.characters", bool(self.characters_cb.GetValue()))' in sd


def test_player_has_a_characters_button():
    src = Path("src/omni_describer_custom/ui/player_window.py").read_text(encoding="utf-8")
    assert 'name="characters"' in src and "self._on_characters" in src


def main() -> int:
    app = wx.App(False)
    check("cast lines are read", test_cast_lines_are_read)
    check("names the user gave survive the AI", test_user_names_survive_the_ai)
    check("a label is renamed in every text", test_rename_everywhere)
    check("the agent's old characters file is read", test_old_agent_file_is_read)
    check("names in capitals are not kept", test_capitals_are_not_kept)
    check("the cast request caps the thinking", test_cast_request_caps_thinking)
    check("the cast travels through every part", test_cast_travels_through_every_part)
    check("a whole-video provider gets the rules and the cast",
          test_engine_rules_and_cast_for_a_whole_video_provider)
    check("the Characters window names someone everywhere",
          test_characters_window_names_someone_everywhere)
    check("the run saves the cast (whole-video provider)",
          test_the_run_saves_the_cast_for_a_whole_video_provider)
    check("the Player has a Characters button", test_player_has_a_characters_button)
    check("Settings > AI switch, on by default", test_settings_switch)
    del app
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
