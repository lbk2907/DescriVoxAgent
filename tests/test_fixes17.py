# -*- coding: utf-8 -*-
"""v1.5.2 language-consistency test suite (zero cost, no network).

Covers:
 1. apply_output_language / language_directive helpers (ms/en/none/no-double)
 2. AIEngine dispatch: output_lang param exists on all 4 describe methods
    and a mock provider RECEIVES the wrapped prompt
 3. Malay presets: ms_default / ms_accessibility exist; language=ms lists
    BM text; language=en lists EN text (malay_* legacy still loads)
 4. Settings dialog has description-language UI + save/load logic
 5. main_frame _start_processing sets ai_engine.output_lang from settings
 6. ask_more_dialog wraps question with directive
 7. CLI: --lang arg exists; apply_lang appends directive
 8. i18n: settings.desc_language present in EN and BM
Run: python tests\\test_fixes17.py
"""
from __future__ import annotations

import asyncio
import inspect
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

PASS = 0
FAIL = 0
FAIL_NAMES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        FAIL_NAMES.append(name)
        print(f"FAIL {name} {detail}")


# ── 1. helpers ──────────────────────────────────────────────────────
from omni_describer_custom.core.ai_engine import (
    apply_output_language, language_directive, FULL_VIDEO_TS_PROMPT_SUFFIX)

check("1a directive ms", "Bahasa Malaysia" in language_directive("ms"))
check("1b directive en", "in English" in language_directive("en"))
check("1c directive none", language_directive("fr") == "")
p = "Describe the scene."
check("1d apply ms", apply_output_language(p, "ms").startswith(p)
      and "Bahasa Malaysia" in apply_output_language(p, "ms"))
check("1e apply en", "in English" in apply_output_language(p, "en"))
check("1f apply empty lang = noop", apply_output_language(p, "") == p)
once = apply_output_language(p, "ms")
check("1g no double apply", apply_output_language(once, "ms") == once)
check("1h full-video suffix same-language clause",
      "SAME LANGUAGE" in FULL_VIDEO_TS_PROMPT_SUFFIX)

# ── 2. dispatch output_lang ─────────────────────────────────────────
from omni_describer_custom.core.ai_engine import AIEngine

eng = AIEngine()
check("2a engine default output_lang empty", eng.output_lang == "")
for m in ("describe_frame", "describe_frames", "describe_video_full",
          "describe_video_frames_batch"):
    check(f"2b sig {m}",
          "output_lang" in inspect.signature(getattr(eng, m)).parameters)

captured: dict[str, str] = {}


class _Prov:
    name = "mock"

    async def describe_image(self, image_path, prompt, model=""):
        captured["frame"] = prompt
        return "ok"

    async def describe_frames_batch(self, frames, prompt, model="",
                                    on_progress=None, is_cancelled=None):
        captured["frames"] = prompt
        return ["ok"] * len(frames)

    async def describe_video_full(self, video_path, prompt, model="",
                                  on_status=None, on_upload_progress=None,
                                  is_cancelled=None, chunk_seconds=600,
                                  on_part=None, on_split_progress=None):
        captured["full"] = prompt
        return [(0.0, "ok")]

    async def describe_video_frames_batch(self, frames, prompt, model="",
                                          on_status=None,
                                          is_cancelled=None,
                                          expected_times=None):
        captured["fast"] = prompt
        return [(0.0, "ok")]


eng._providers["mock"] = _Prov()  # type: ignore[assignment]
eng._default_provider = "mock"

async def _t2():
    await eng.describe_frame("x.jpg", "P1", output_lang="ms")
    captured["frame_ms"] = captured.pop("frame", "")
    await eng.describe_frames(["a.jpg"], "P2", output_lang="ms")
    await eng.describe_video_full("v.mp4", "P3", output_lang="ms")
    await eng.describe_video_frames_batch(["a.jpg"], "P4", output_lang="ms")
    # engine-level default (key berasingan)
    eng.output_lang = "en"
    await eng.describe_frame("x.jpg", "P5")
    captured["frame_default_en"] = captured.pop("frame", "")
    eng.output_lang = ""

asyncio.run(_t2())
check("2c frame prompt wrapped", "Bahasa Malaysia" in captured.get("frame_ms", ""))
check("2d frames prompt wrapped", "Bahasa Malaysia" in captured.get("frames", ""))
check("2e full prompt wrapped", "Bahasa Malaysia" in captured.get("full", ""))
check("2f fast prompt wrapped", "Bahasa Malaysia" in captured.get("fast", ""))
check("2g engine default en", "in English" in captured.get("frame_default_en", ""))

# ── 3. preset ms_* ──────────────────────────────────────────────────
from omni_describer_custom.core.settings_store import SettingsStore
from omni_describer_custom.core.prompt_manager import PromptManager

tmp = tempfile.mkdtemp(prefix="odc_t17_")
st = SettingsStore(config_dir=tmp)
pm = PromptManager(st)
prompts_all = st.get_prompts()
check("3a ms_default exists", "ms_default" in prompts_all)
check("3b ms_accessibility exists", "ms_accessibility" in prompts_all)
check("3c ms_default is BM", "Huraikan" in prompts_all.get("ms_default", ""))
pm.language = "ms"
ms_view = pm.get_presets()
check("3d language=ms shows BM default", "Huraikan" in ms_view.get("default", ""))
pm.language = "en"
en_view = pm.get_presets()
check("3e language=en shows EN default",
      "Describe everything" in en_view.get("default", ""))

# ── 4. settings dialog source contains desc_lang UI ─────────────────
sd = (ROOT / "src" / "omni_describer_custom" / "ui" / "settings_dialog.py").read_text(encoding="utf-8")
check("4a dialog desc_lang_choice UI", "desc_lang_choice" in sd)
check("4b dialog saves general.description_language",
      'general.description_language' in sd)
check("4c dialog loads saved value", "desc_lang_choice.SetStringSelection" in sd)

# ── 5. main_frame sets engine.output_lang ───────────────────────────
mf = (ROOT / "src" / "omni_describer_custom" / "ui" / "main_frame.py").read_text(encoding="utf-8")
check("5a main sets output_lang", "self.ai_engine.output_lang = desc_lang" in mf)
check("5b main falls back to UI language", 'general.language' in mf)

# ── 6. ask_more_dialog wraps ────────────────────────────────────────
am = (ROOT / "src" / "omni_describer_custom" / "ui" / "ask_more_dialog.py").read_text(encoding="utf-8")
check("6a ask uses apply_output_language", "apply_output_language" in am)
check("6b ask passes engine output_lang", "output_lang" in am)

# ── 7. CLI ──────────────────────────────────────────────────────────
sys.path.insert(0, str(ROOT))
from video_describer.glm_describe import apply_lang, DESCRIPTOR_PROMPT

check("7a cli apply_lang ms", "Bahasa Malaysia" in apply_lang(DESCRIPTOR_PROMPT, "ms"))
check("7b cli apply_lang noop", apply_lang("X", "") == "X")
r = subprocess.run(
    [sys.executable, "-m", "video_describer", "describe", "--help"],
    capture_output=True, text=True, cwd=str(ROOT), env={
        **__import__("os").environ, "PYTHONPATH": str(ROOT)})
check("7c cli --lang arg", "--lang" in (r.stdout + r.stderr))

# ── 8. i18n key ─────────────────────────────────────────────────────
from omni_describer_custom.i18n.strings import EN_STRINGS, MS_STRINGS

check("8a i18n EN desc_language", "settings.desc_language" in EN_STRINGS)
check("8b i18n BM desc_language", "settings.desc_language" in MS_STRINGS)

# ── summary ─────────────────────────────────────────────────────────
print(f"\nRESULT: PASS={PASS} FAIL={FAIL}")
if FAIL_NAMES:
    print("Failed:", ", ".join(FAIL_NAMES))
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if FAIL else 0)
