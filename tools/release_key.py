"""The release signing key (Ed25519): make it once, sign each release.

Review of the self-updater, 6 Oct 2026 (HIGH): SHA256SUMS.txt from the
same GitHub release only proves the zip was not damaged; whoever can
publish a release can publish matching checksums. So SHA256SUMS.txt is
signed with a key that never leaves the owner's PC, and the app
(core/app_update.py, RELEASE_PUBLIC_KEY) installs only what verifies.

    python tools/release_key.py generate   # once; refuses to overwrite
    python tools/release_key.py public     # the public key, for app_update.py
    python tools/release_key.py sign FILE  # writes FILE.sig (build.bat does this)

The secret key is KEY_FILE (or ODC_RELEASE_KEY). Back it up somewhere
safe and offline: without it no copy of the app accepts another update.
It is never committed, printed or sent anywhere.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

KEY_FILE = Path(os.environ.get("ODC_RELEASE_KEY") or
                Path.home() / ".descrivox" / "release-signing.key")


def _signing_key():
    from nacl.signing import SigningKey
    if not KEY_FILE.exists():
        raise SystemExit(f"no signing key at {KEY_FILE} "
                         f"(python tools/release_key.py generate)")
    try:
        return SigningKey(bytes.fromhex(KEY_FILE.read_text(encoding="ascii").strip()))
    except (ValueError, UnicodeDecodeError) as e:
        raise SystemExit(f"the signing key at {KEY_FILE} is damaged ({type(e).__name__}); "
                         f"restore it from the backup") from None


def generate() -> str:
    from nacl.signing import SigningKey
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    key = SigningKey.generate()
    try:
        # "x": created only if absent, atomically (review): an existing key
        # is never truncated, even by two runs at once.
        with open(KEY_FILE, "x", encoding="ascii") as f:
            f.write(bytes(key).hex() + "\n")
    except FileExistsError:
        raise SystemExit(f"{KEY_FILE} already exists; not overwriting it") from None
    return bytes(key.verify_key).hex()


def public() -> str:
    return bytes(_signing_key().verify_key).hex()


def sign(path: Path) -> Path:
    signature = _signing_key().sign(path.read_bytes()).signature
    out = path.with_name(path.name + ".sig")
    out.write_text(signature.hex() + "\n", encoding="ascii", newline="\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate")
    sub.add_parser("public")
    s = sub.add_parser("sign")
    s.add_argument("file")
    args = ap.parse_args()
    if args.cmd == "generate":
        print(f"KEY_CREATED {KEY_FILE}\npublic key: {generate()}")
    elif args.cmd == "public":
        print(public())
    else:
        print(f"SIGNED {sign(Path(args.file))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
