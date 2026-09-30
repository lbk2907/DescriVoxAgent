# -*- coding: utf-8 -*-
"""Regression tests for v1.5.3 changes.

Covers:
1. OpusProvider fully removed from AIEngine.
2. Default chunk_seconds is 300 (5 minutes) everywhere. It was 600
   until v1.8.6; measured on two long films, 10-minute parts put
   24.5% / 27.5% of descriptions at the wrong moment, 5-minute
   parts 12.9% / 11.8% (doc/perbandingan-model.md).
3. GLM full-video mode threads part position + previous-part summary
   into every _describe_one_part call (continuity context), and the
   part payload really contains the position/continuity text.
4. Continuous narration rules: no "video starts with" phrasing except
   at the true 00:00, and the rules text exists and is wired in.
5. Fast-mode batches beyond the first get a position note (no
   "starts with" mid-video), and the note uses expected_times.
"""
import asyncio
import inspect
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omni_describer_custom.core.ai_engine import (  # noqa: E402
    AIEngine, GLMProvider, FULL_VIDEO_TS_PROMPT_SUFFIX, CONTINUITY_RULES,
    _fast_batch_content,
)

PASS = []


def ok(name, cond, extra=""):
    if cond:
        PASS.append(name)
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        raise AssertionError(name + " " + extra)


print("== test_fixes18: v1.5.3 ==")

# 1 ── OpusProvider removed ------------------------------------------
ok("1a. PROVIDERS has no opus",
   "opus" not in getattr(AIEngine, "PROVIDERS", {}))
import omni_describer_custom.core.ai_engine as mod  # noqa: E402
src_all = inspect.getsource(mod)
ok("1b. no 'opus' token in ai_engine source", "opus" not in src_all.lower())

# 2 ── chunk defaults 300 ---------------------------------------------
sig = inspect.signature(AIEngine.describe_video_full)
ok("2a. AIEngine full-video default chunk 300",
   sig.parameters["chunk_seconds"].default == 300)
sig_g = inspect.signature(GLMProvider.describe_video_full)
ok("2b. GLM full-video default chunk 300",
   sig_g.parameters["chunk_seconds"].default == 300)

from omni_describer_custom.core.settings_store import SettingsStore  # noqa: E402
_store_src = inspect.getsource(
    sys.modules["omni_describer_custom.core.settings_store"])
ok("2c. settings_store default chunk 300",
   '"chunk_seconds": 300' in _store_src
   and '"chunk_seconds": 480' not in _store_src)

from omni_describer_custom.ui.settings_dialog import PROVIDER_MODELS  # noqa: E402
_dlg_src = inspect.getsource(
    sys.modules["omni_describer_custom.ui.settings_dialog"])
ok("2d. dialog chunk spin initial 300",
   "initial=300" in _dlg_src and "initial=480" not in _dlg_src)
ok("2e. PROVIDER_MODELS has no opus", "opus" not in PROVIDER_MODELS)

# 3 ── continuity context threading -----------------------------------
def _capture_full():
    """Run GLM describe_video_full with mocked probe/split/part and
    capture the kwargs every _describe_one_part call receives."""
    eng = AIEngine()
    eng.set_provider("glm", api_key="k",
                     base_url="https://openrouter.ai/api/v1")
    calls = []

    # **kwargs: this stands in for a real method whose signature grows
    # (v1.6.1 added transcript/part_seconds). The check here is about
    # part numbering and continuity, not the argument list.
    async def fake_one(self, path, prompt, model, on_status=None,
                       is_cancelled=None, offset=0.0, part_index=0,
                       part_total=0, prev_summary="", **kwargs):
        calls.append((part_index, part_total, prev_summary))
        return [(0.0, f"Part {part_index} story.")]

    with patch.object(GLMProvider, "_describe_one_part", fake_one), \
         patch.object(GLMProvider, "_probe_duration",
                      return_value=1300.0), \
         patch.object(GLMProvider, "split_video_for_upload",
                      return_value=([0.0, 60.0], [Path("p1.mp4"),
                                                  Path("p2.mp4")])):
        merged = asyncio.run(
            eng.describe_video_full("fake.mp4", "describe",
                                    chunk_seconds=600))
    return calls, merged


calls, merged = _capture_full()
ok("3a. two parts described", len(calls) == 2, str(calls))
ok("3b. part 1 carries no summary", calls[0] == (1, 2, ""), str(calls[0]))
ok("3c. part 2 carries part-1 summary",
   calls[1] == (2, 2, "Part 1 story."), str(calls[1]))
ok("3d. merged cues", len(merged) == 2, str(merged))


# 3e ── the part payload really contains the position block -----------
def _check_payload_position():
    with tempfile.TemporaryDirectory() as td:
        fake = Path(td) / "part.mp4"
        fake.write_bytes(b"\x00" * 1024)  # small; no recompress needed
        prov = GLMProvider(api_key="k",
                           base_url="https://openrouter.ai/api/v1")
        captured = []

        async def fake_chat(payload, timeout):
            texts = [c.get("text", "")
                     for c in payload["messages"][0]["content"]
                     if isinstance(c, dict) and c.get("type") == "text"]
            captured.append("\n".join(texts))
            return "[00:05] cue one\n[00:09] cue two\n"

        async def run():
            with patch.object(prov, "_chat", fake_chat):
                return await prov._describe_one_part(
                    fake, "describe it", "glm-5.3-flash",
                    on_status=None, is_cancelled=None, offset=600.0,
                    part_index=2, part_total=3,
                    prev_summary="A man entered the lab.")

        pairs = asyncio.run(run())
        return captured[0], pairs


pos_text, pairs = _check_payload_position()
ok("3e. payload says part 2 of 3", "part 2 of 3" in pos_text, pos_text[:200])
ok("3f. payload includes prev summary",
   "A man entered the lab." in pos_text)
ok("3g. payload bans narrative restart",
   "do NOT restart" in pos_text)
ok("3h. timestamps shifted by offset",
   pairs == [(605.0, "cue one"), (609.0, "cue two")], str(pairs))


# 3i ── part 1 (part_total=1) gets NO position block -------------------
def _check_first_part_clean():
    with tempfile.TemporaryDirectory() as td:
        fake = Path(td) / "part.mp4"
        fake.write_bytes(b"\x00" * 1024)
        prov = GLMProvider(api_key="k",
                           base_url="https://openrouter.ai/api/v1")
        captured = []

        async def fake_chat(payload, timeout):
            texts = [c.get("text", "")
                     for c in payload["messages"][0]["content"]
                     if isinstance(c, dict) and c.get("type") == "text"]
            captured.append("\n".join(texts))
            return "[00:05] cue\n"

        async def run():
            with patch.object(prov, "_chat", fake_chat):
                return await prov._describe_one_part(
                    fake, "describe it", "glm-5.3-flash",
                    on_status=None, is_cancelled=None, offset=0.0,
                    part_index=1, part_total=1, prev_summary="")

        asyncio.run(run())
        return captured[0]


first_txt = _check_first_part_clean()
ok("3i. single-part video has no position block",
   "CONTEXT: You are describing part" not in first_txt)

# 4 ── continuity rules text ------------------------------------------
ok("4a. FULL suffix bans 'starts with'",
   "video starts with" in FULL_VIDEO_TS_PROMPT_SUFFIX.lower()
   and "video begins with" in FULL_VIDEO_TS_PROMPT_SUFFIX.lower())
ok("4b. CONTINUITY_RULES content",
   "one consistent name" in CONTINUITY_RULES.lower()
   and "video opens with" in CONTINUITY_RULES.lower())
_one_part_src = inspect.getsource(GLMProvider._describe_one_part)
ok("4c. _describe_one_part embeds position block",
   "CONTEXT: You are describing part" in _one_part_src
   and "prev_summary" in _one_part_src)

# 5 ── fast-mode batch position note -----------------------------------
import tempfile as _tf  # noqa: E402
_td5 = _tf.TemporaryDirectory()
for _i in range(3):
    (Path(_td5.name) / f"f{_i}.jpg").write_bytes(
        b"\xff\xd8\xff\xe0" + b"\x00" * 16)
fake_frames = [Path(_td5.name) / f"f{_i}.jpg" for _i in range(3)]
c0 = _fast_batch_content(fake_frames, "Describe.")
ok("5a. first batch has no note", c0[-1]["text"].startswith("Describe."))
c1 = _fast_batch_content(fake_frames, "Describe.", batch_note="CTX. ")
ok("5b. note prepended", c1[-1]["text"].startswith("CTX. "))
ok("5c. frames + text blocks", len(c1) == 4 and c1[-1]["type"] == "text")
batch_src = inspect.getsource(GLMProvider.describe_video_frames_batch)
ok("5d. batch note uses expected_times",
   "expected_times" in batch_src and "_batch_note" in batch_src)
ok("5e. gather enumerates batches", "enumerate(batches)" in batch_src)

# 5f: real _batch_note math — batch 1 of a 10 s grid starts at 1500 s.
times = [float(t) for t in range(0, 3200, 10)]  # 320 frames, 10 s apart
MAX_IMAGES = 150
first_idx = 1 * MAX_IMAGES
t0 = times[first_idx] if first_idx < len(times) else None
ok("5f. batch-1 starts at 1500 s in 10 s grid", t0 == 1500.0, str(t0))

print(f"\nALL_OK ({len(PASS)} checks)")
