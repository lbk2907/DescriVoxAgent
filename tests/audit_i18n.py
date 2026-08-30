"""Audit i18n: every t("...") key used in code must exist in EN and MS strings.

Also audits: every button/control created with an empty or placeholder label.
Standalone script, exits 1 on missing keys.
"""
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1] / "src" / "omni_describer_custom"
sys.path.insert(0, str(ROOT.parent))

from omni_describer_custom.i18n.strings import EN_STRINGS, MS_STRINGS  # noqa: E402

used: set[str] = set()
for py in ROOT.rglob("*.py"):
    if py.name == "strings.py":
        continue
    text = py.read_text(encoding="utf-8")
    for m in re.finditer(r'\bt\(\s*"([a-z0-9_.]+)"', text):
        used.add(m.group(1))

missing = [k for k in sorted(used) if k not in EN_STRINGS or k not in MS_STRINGS]
print(f"i18n keys used: {len(used)}")
print(f"i18n keys missing (EN or MS): {len(missing)}")
for k in missing:
    which = []
    if k not in EN_STRINGS:
        which.append("EN")
    if k not in MS_STRINGS:
        which.append("MS")
    print(f"  ! {k}  (missing in {','.join(which)})")

# Label audit: controls built with label="" (placeholder that stays blank)
bad_labels = []
for py in sorted(ROOT.rglob("*.py")):
    if py.name == "strings.py":
        continue
    for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
        if re.search(r'wx\.(Button|ToggleButton|BitmapButton)\([^)]*label=""', line):
            bad_labels.append(f"{py.name}:{i}: {line.strip()}")
print(f"buttons with empty label: {len(bad_labels)}")
for b in bad_labels:
    print("  !", b)

sys.exit(1 if (missing or bad_labels) else 0)
