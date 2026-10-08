"""Regression round 77: Gemini 3.5 Flash-Lite recommended (phase 36, 8 Oct 2026).

Measured under frozen contracts (contracts/measure-gemini-*): on four
re-downloaded clips x 3 runs, GLM ruler, against 3.1 Flash-Lite on the
app's own path, only 3.5 Flash-Lite passed - wrong 19.9% -> 11.7% with
the same coverage and speed. 3.7/3.8 Flash gave far fewer descriptions;
agentic video (Interactions API) was no better and slower. Owner: use
3.5 Flash-Lite for 2.1.4.

Only the DIRECT Gemini provider was measured, so only its default and
recommendation change; OpenRouter's recommendation and the agent's model
stay as they were. 3.5 Flash-Lite ran with its own default thinking, so
it gets no THINKING_BY_MODEL entry.
"""

import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import sys
import traceback
from pathlib import Path

if "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

results: list[tuple[str, bool]] = []
NEW = "gemini-3.5-flash-lite"


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def test_direct_gemini_defaults():
    from omni_describer_custom.core.ai_engine import GeminiProvider
    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.ui.settings_dialog import PROVIDER_MODELS

    assert GeminiProvider.models[0] == NEW, GeminiProvider.models
    assert PROVIDER_MODELS["gemini"][0] == NEW, PROVIDER_MODELS["gemini"]
    assert "gemini-3.1-flash-lite" in GeminiProvider.models, "old choice must stay selectable"
    default = SettingsStore.DEFAULTS["ai"]["providers"]["gemini"]["model"]
    assert default == NEW, default


def test_measured_thinking_kept():
    from omni_describer_custom.core.ai_engine import GeminiProvider

    assert NEW not in GeminiProvider.THINKING_BY_MODEL, (
        "3.5 Flash-Lite was measured with its own default thinking"
    )


def test_fetched_list_puts_it_first():
    from omni_describer_custom.core.model_catalog import parse_gemini_models

    def model(name):
        return {
            "name": f"models/{name}",
            "displayName": name,
            "inputTokenLimit": 1048576,
            "supportedGenerationMethods": ["generateContent"],
        }

    rows = parse_gemini_models(
        {
            "models": [
                model(m)
                for m in ("gemini-3.8-flash", "gemini-3.1-flash-lite", NEW, "gemini-3.7-flash")
            ]
        }
    )
    assert rows[0]["id"] == NEW, [r["id"] for r in rows]


def test_openrouter_recommendation_unchanged():
    from omni_describer_custom.core.model_catalog import RECOMMENDED

    assert RECOMMENDED == ("z-ai/glm-5.3-flash", "google/gemini-3.1-flash-lite"), (
        "only the direct Gemini path was measured"
    )


def test_measured_under_frozen_contracts():
    sys.path.insert(0, str(REPO / "tools"))
    import contracts as C

    C.load("measure-gemini-35-flash-lite-new")


def main() -> int:
    check("direct Gemini default is 3.5 Flash-Lite", test_direct_gemini_defaults)
    check("its measured thinking (model default) is kept", test_measured_thinking_kept)
    check("Fetch models lists it first", test_fetched_list_puts_it_first)
    check("OpenRouter recommendation unchanged", test_openrouter_recommendation_unchanged)
    check("measured under a frozen contract", test_measured_under_frozen_contracts)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
