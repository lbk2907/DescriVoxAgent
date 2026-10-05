"""Tag a release - only when contracts/release.json is VERIFIED.

    python tools/tag_release.py

Writes the evidence bundle (the verdict, every check, the zip and exe
digests) next to the evidence log, with a SHA-256 over its canonical form,
and creates an annotated tag v<version> whose message carries that digest.
Pushing stays a separate step that needs the owner's permission.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contracts as C  # noqa: E402
import evidence as E  # noqa: E402
import release_check  # noqa: E402


def main() -> int:
    v = release_check.run()
    print("\n".join(v.lines()))
    if v.verdict != C.VERIFIED:
        print(f"NOT TAGGED: the release is {v.verdict}")
        return 1
    ver = E.version()
    bundle = {"version": ver, "commit": E.head(), "tree": E.git("rev-parse", "HEAD^{tree}"),
              **v.as_dict()}
    bundle["attestation_sha256"] = C.digest(bundle)
    out = E.evidence_dir() / f"v{ver}.release.json"
    out.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    tag = f"v{ver}"
    if not E.git("tag", "-l", tag):
        msg = (f"DescriVox Agent {ver}\n\nrelease contract {v.digest[:12]}: VERIFIED\n"
               f"evidence bundle sha256 {bundle['attestation_sha256']}\n")
        subprocess.run(["git", "tag", "-a", tag, "-m", msg], cwd=E.REPO, check=True)
    print(f"TAGGED {tag} - evidence {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
