"""Characters: one name per person, from the first minute to the last.

v2.1.0 (owner, 5 Oct 2026): "the same person is called different things"
and "the AI does not use the name even when everyone says it". A long
video went to the AI in 5-minute parts and each part only saw the last
six descriptions of the one before, so a person met in part 1 had a new
label by part 3, and nothing told the AI to use names heard in the
dialogue.

Now:
- CHARACTER_RULES go into every full-video prompt (any provider);
- a cast list - name or label, and how to recognise them - is carried
  from part to part (chunked providers) and saved with the project
  (characters.json in the project folder), where the Player agent and the Characters
  window use it;
- the user can name someone the AI could only describe ("the man in the
  grey coat" -> "Encik Rahim"), in every description at once.

The cast is updated by a separate, text-only request after each part, so
the description answer and its parser are untouched; when that request
fails the cast simply stays as it was.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

CAST_FILE = "characters.json"
MAX_CAST = 30

CHARACTER_RULES = """
CHARACTERS - keep every person easy to follow for a blind listener:
- Use a person's NAME when it is heard in the dialogue or shown on screen
  (caption, name tag, title card). Never invent a name.
- Until a name is known, give the person ONE short label a listener can
  follow (for example "the woman in the blue headscarf") and reuse EXACTLY
  that label every time; do not switch to other descriptions of them.
- When a name becomes known, introduce it once ("the woman in the blue
  headscarf, Aisyah,") and use only the name after that.
- Use the names and labels under KNOWN CHARACTERS exactly as written.
"""


def cast_block(cast: list[dict]) -> str:
    """The cast as prompt text; empty when nobody is known yet."""
    if not cast:
        return ""
    lines = []
    for c in cast[:MAX_CAST]:
        look = (c.get("look") or "").strip()
        lines.append(f"- {c['name']}" + (f" — {look}" if look else ""))
    return "KNOWN CHARACTERS (name or label — how to recognise them):\n" + "\n".join(lines) + "\n"


_LINE = re.compile(r"^\s*(?:[-*•]|\d+[.)])?\s*(.+?)\s*(?:—|–|:|\s-\s)\s*(.+?)\s*$")


def parse_cast(text: str) -> list[dict]:
    """Read "- name — how to recognise" lines. Anything else is ignored."""
    cast: list[dict] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.upper().startswith(("KNOWN CHARACTERS", "CHARACTERS", "CAST")):
            continue
        m = _LINE.match(line)
        if m:
            name, look = m.group(1).strip(" *\"'"), m.group(2).strip()
        elif line.startswith(("-", "*", "•")):
            name, look = line.lstrip("-*• ").strip(" *\"'"), ""
        else:
            continue
        if not name or len(name) > 80:
            continue
        if name.isupper() and len(name) > 1:
            # "THOM", "WOMAN SOLDIER" (seen 5 Oct): NVDA may spell
            # capitals out. A one-word name keeps its capital letter.
            name = name.title() if " " not in name else name.capitalize()
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        cast.append({"name": name, "look": look})
        if len(cast) >= MAX_CAST:
            break
    return cast


def merge_user_names(ai_cast: list[dict], old_cast: list[dict]) -> list[dict]:
    """Names the user gave are never dropped or changed by the AI."""
    pinned = [c for c in old_cast if c.get("by_user")]
    result = []
    names = set()
    for c in pinned:
        match = next((a for a in ai_cast if a["name"].casefold() == c["name"].casefold()), None)
        look = c.get("look") or (match or {}).get("look", "")
        result.append({"name": c["name"], "look": look, "by_user": True})
        names.add(c["name"].casefold())
    for a in ai_cast:
        if a["name"].casefold() not in names:
            result.append({"name": a["name"], "look": a.get("look", "")})
            names.add(a["name"].casefold())
    return result[:MAX_CAST]


def cast_update_prompt(cast: list[dict], descriptions: list[str], spoken: str = "") -> str:
    known = cast_block(cast) or "KNOWN CHARACTERS: none yet.\n"
    said = (
        f"\nWords spoken in this part of the video:\n{spoken.strip()}\n" if spoken.strip() else ""
    )
    descs = "\n".join(f"- {d}" for d in descriptions if d.strip())
    return (
        "You keep the list of people in a video for its audio description.\n\n"
        f"{known}\nNew descriptions:\n{descs}\n{said}\n"
        "Update the list:\n"
        "- add every person the new descriptions mention who is not listed;\n"
        "- if a listed label now has a NAME (heard in the words spoken, or shown on\n"
        "  screen), replace the label with the name and keep how to recognise them;\n"
        "- never invent a name; keep names and labels exactly as already written;\n"
        "- write in the same language as the descriptions.\n"
        "Answer with the whole list and nothing else, one person per line:\n"
        "- name or label — how to recognise them (clothes, age, role)\n"
    )


async def update_cast(
    ask, cast: list[dict], descriptions: list[str], spoken: str = ""
) -> list[dict]:
    """One text-only request; on any failure the cast is kept as it was."""
    if not descriptions:
        return cast
    try:
        answer = await ask(cast_update_prompt(cast, descriptions, spoken))
    except Exception as e:
        logger.info("cast update failed, keeping the cast: %s", e)
        return cast
    new = parse_cast(answer)
    if not new:
        return cast
    return merge_user_names(new, cast)


def load_cast(media_dir: Path | str | None) -> list[dict]:
    if not media_dir:
        return []
    path = Path(media_dir) / CAST_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        # The Player agent's file before v2.1.0: {name: description},
        # names a person told it - kept as the user's.
        return [
            {"name": str(k)[:80], "look": str(v), "by_user": True}
            for k, v in data.items()
            if str(k).strip()
        ][:MAX_CAST]
    if not isinstance(data, list):
        return []
    return [
        {k: v for k, v in c.items() if k in ("name", "look", "by_user")}
        for c in data
        if isinstance(c, dict) and str(c.get("name", "")).strip()
    ]


def save_cast(media_dir: Path | str | None, cast: list[dict]) -> bool:
    if not media_dir:
        return False
    try:
        path = Path(media_dir) / CAST_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cast, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except OSError as e:
        logger.warning("cast not saved: %s", e)
        return False


def rename_in_texts(texts: list[str], old: str, new: str) -> tuple[list[str], int]:
    """Replace a label or name in every text, whole words, any case.

    A leading "the "/"a " of the old label goes too when it stands before
    it in the text ("The man in the grey coat nods" -> "Rahim nods").
    Returns the new texts and how many texts changed.
    """
    old = old.strip()
    if not old or not new.strip() or old.casefold() == new.strip().casefold():
        return list(texts), 0
    core = re.sub(r"^(the|a|an)\s+", "", old, flags=re.IGNORECASE)
    pattern = re.compile(r"\b(?:(?:the|a|an)\s+)?" + re.escape(core) + r"\b", re.IGNORECASE)
    out, changed = [], 0
    for text in texts:
        result = pattern.sub(new.strip(), text)
        if result != text:
            changed += 1
        out.append(result)
    return out, changed
