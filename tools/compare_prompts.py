"""Run ONE video through TWO prompts and print both results side by side.

Built to answer "is the new prompt actually better?" with evidence
instead of opinion. It calls the real provider twice on the same video,
then reports the cues plus the measurements that audio-description
standards actually care about:

  cues            how many description events came back
  words/cue       a cue must be speakable in the gap before the next one
  meta phrases    "the camera", "we see", "in this frame" — unusable in
                  narration, and a sign the model is describing a picture
                  rather than telling the story
  speech echo     "he says", "she asks" — narrating what the listener can
                  already hear, which every standard warns against
  interpretation  "seems", "appears to be", "obviously" — AD reports what
                  is observable and lets the listener conclude

Usage:
  python tools/compare_prompts.py                 # newest project video
  python tools/compare_prompts.py <video> [name]  # explicit file/preset
  python tools/compare_prompts.py --dry-run [name]  # no API call, no cost

--dry-run prints the COMPLETE text each request would carry (preset plus
the instructions the engine appends), which is worth reading on its own:
it is the only place the two halves of the prompt appear together.
"""
import asyncio
import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, "src")

from omni_describer_custom.core.ai_engine import AIEngine  # noqa: E402
from omni_describer_custom.core.prompt_manager import (  # noqa: E402
    DEFAULT_PROMPTS, LEGACY_PROMPTS)
from omni_describer_custom.core.settings_store import SettingsStore  # noqa: E402

PROJECTS = Path.home() / "Documents" / "OmniDescriber" / "projects"

# "to camera" is NOT flagged: the Netflix guide allows it for direct
# address ("She turns to the camera and winks at us"). What makes
# narration unusable is film technique and caption voice.
META = (r"\bthe camera (?:pans|zooms|cuts|moves|follows|tilts)\b",
        r"\bwe see\b", r"\bin this (?:frame|image|picture)\b",
        r"\bthe (?:scene|shot|video) (?:shows|opens|begins|ends)\b",
        r"\bclose[- ]up shot\b", r"\bcuts? to\b",
        # Malay: these patterns were English-only, so a BM run scored a
        # clean 0 while its last cue read "sehingga video tamat".
        r"\bvideo (?:ini|itu) (?:menunjukkan|bermula|tamat|berakhir)\b",
        r"\b(?:sehingga|hingga) video (?:tamat|berakhir)\b",
        r"\bkita (?:lihat|nampak)\b", r"\bdalam (?:babak|kerangka) ini\b",
        r"\bkamera (?:bergerak|mengezum|beralih)\b")
SPEECH = (r"\b(?:he|she|they|the man|the woman|the narrator)\s+"
          r"(?:says|said|asks|asked|explains|tells|shouts)\b",
          r"\bvoice[- ]?over\b", r"\bwe hear\b", r"\bthe music\b",
          r"\b(?:dia|lelaki itu|wanita itu)\s+"
          r"(?:berkata|bertanya|menjelaskan|memberitahu)\b",
          r"\bkita dengar\b", r"\bmuzik (?:dimainkan|berkumandang)\b")
INTERPRET = (r"\bseems? to\b", r"\bappears? to\b", r"\bobviously\b",
             r"\bclearly (?:happy|sad|angry|nervous)\b",
             r"\bis (?:happy|sad|angry|nervous|excited)\b",
             r"\bnampak(?:nya)? (?:gembira|sedih|marah|gelisah)\b",
             r"\bkelihatan (?:gembira|sedih|marah|gelisah|teruja)\b",
             r"\bjelas sekali\b")


def _hits(cues: list[str], patterns) -> list[str]:
    found = []
    for text in cues:
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                found.append(f"{m.group(0)} — {text[:70]}")
                break
    return found


def _report(label: str, cues: list[tuple[float, str]]) -> None:
    texts = [t for _, t in cues]
    words = [len(t.split()) for t in texts]
    avg = sum(words) / len(words) if words else 0
    print(f"\n{'=' * 68}\n{label}\n{'=' * 68}")
    for seconds, text in cues:
        print(f"  [{int(seconds)//60:02d}:{int(seconds)%60:02d}] {text}")
    print(f"\n  cues={len(cues)}  words/cue avg={avg:.1f}  "
          f"longest={max(words) if words else 0}")
    for name, pats in (("meta phrases", META), ("speech echo", SPEECH),
                       ("interpretation", INTERPRET)):
        hits = _hits(texts, pats)
        print(f"  {name}: {len(hits)}")
        for h in hits[:3]:
            print(f"      {h}")


def _newest_video() -> Path | None:
    vids = sorted(PROJECTS.glob("*/media/video.mp4"),  # either layout
                  key=lambda p: p.stat().st_mtime, reverse=True)
    return vids[0] if vids else None


async def _describe(engine: AIEngine, video: Path, prompt: str):
    return await engine.describe_video_full(str(video), prompt)


def _dry_run(preset: str) -> int:
    """Show what would be sent, without spending a cent."""
    from omni_describer_custom.core.ai_engine import FULL_VIDEO_TS_PROMPT_SUFFIX

    for label, prompt in (
        ("BEFORE — pre-v1.6.0 default", LEGACY_PROMPTS["default"]),
        (f"AFTER — v1.6.0 {preset!r}", DEFAULT_PROMPTS[preset]),
    ):
        print(f"\n{'=' * 68}\n{label}\n{'=' * 68}")
        print(prompt + FULL_VIDEO_TS_PROMPT_SUFFIX)
    return 0


def main() -> int:
    argv = sys.argv[1:]
    only_new = "--only-new" in argv          # validating a preset, not comparing
    lang = ""
    if "--lang" in argv:
        i = argv.index("--lang")
        lang = argv[i + 1]
        del argv[i:i + 2]
    args = [a for a in argv if a not in ("--dry-run", "--only-new")]
    if "--dry-run" in argv:
        return _dry_run(args[0] if args else "default")
    video = Path(args[0]) if args else _newest_video()
    preset = args[1] if len(args) > 1 else "default"
    if not video or not video.exists():
        print("no video found; pass one as the first argument")
        return 1
    cfg = SettingsStore().get_ai_provider("glm")
    if not cfg.get("api_key"):
        print("no GLM key in settings")
        return 1

    engine = AIEngine()
    engine.set_provider("glm", api_key=cfg["api_key"],
                        base_url=cfg.get("base_url") or "",
                        model=cfg.get("model") or "")
    print(f"video: {video}  ({video.stat().st_size / 1e6:.1f} MB)")
    print(f"preset under test: {preset}")

    old = LEGACY_PROMPTS["default"]
    new = DEFAULT_PROMPTS.get(preset, DEFAULT_PROMPTS["default"])
    if lang:
        engine.output_lang = lang
        print(f"description language: {lang}")

    if not only_new:
        before = asyncio.run(_describe(engine, video, old))
        _report("BEFORE — pre-v1.6.0 prompt "
                "(\"describe everything you see in detail\")", before)
    after = asyncio.run(_describe(engine, video, new))
    _report(f"AFTER — v1.6.0 {preset!r} preset (AD standards)", after)
    print("\nRead both lists aloud in your head: the second should sound "
          "like narration, the first like a caption.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
