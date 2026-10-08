"""Frozen contracts: what "done" means, written down before the work.

Owner, 6 Oct 2026, after reviewing Watch Skill's verification design:
use the same idea here. A contract in `contracts/<id>.json` lists the checks
that decide a result. It is frozen: `contracts/LOCK.json` holds the SHA-256
of its canonical form, and `contracts/CHANGES.md` records every version -
when, and why. The gate (test_fixes74) fails if a contract differs from its
lock or a version has no recorded reason. An agent may change a contract
(owner's choice), but only through `freeze`, which records it - and the
change is reported to the owner.

    python tools/contracts.py status
    python tools/contracts.py freeze <id> --why "what changed and why"

Verdicts (shared by every contract kind):
    VERIFIED      every required check passed
    FAILED        a required check failed
    INCONCLUSIVE  a required check could not run, or there was none -
                  "we could not check" is never reported as a pass
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONTRACTS = Path(os.environ.get("ODC_CONTRACTS_DIR") or REPO / "contracts")

PASS, FAIL, UNKNOWN = "pass", "fail", "inconclusive"
VERIFIED, FAILED, INCONCLUSIVE = "VERIFIED", "FAILED", "INCONCLUSIVE"


@dataclass
class Result:
    check_id: str
    outcome: str  # PASS / FAIL / UNKNOWN
    detail: str = ""
    required: bool = True


@dataclass
class Verdict:
    contract_id: str
    digest: str
    results: list[Result] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        required = [r for r in self.results if r.required]
        if any(r.outcome == FAIL for r in required):
            return FAILED
        if not required or any(r.outcome != PASS for r in required):
            return INCONCLUSIVE
        return VERIFIED

    def lines(self) -> list[str]:
        mark = {PASS: "PASS", FAIL: "FAIL", UNKNOWN: "????"}
        out = [f"{self.contract_id} ({self.digest[:12]}): {self.verdict}"]
        for r in self.results:
            tag = "" if r.required else " (advisory)"
            out.append(f"  [{mark[r.outcome]}] {r.check_id}{tag}: {r.detail}")
        return out

    def as_dict(self) -> dict:
        return {
            "contract_id": self.contract_id,
            "digest": self.digest,
            "verdict": self.verdict,
            "results": [r.__dict__ for r in self.results],
        }


def canonical(data) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def digest(data) -> str:
    return hashlib.sha256(canonical(data)).hexdigest()


def _lock_path(folder: Path) -> Path:
    return folder / "LOCK.json"


def _changes_path(folder: Path) -> Path:
    return folder / "CHANGES.md"


def contract_ids(folder: Path = CONTRACTS) -> list[str]:
    return sorted(p.stem for p in folder.glob("*.json") if p.name != "LOCK.json")


def load(contract_id: str, folder: Path = CONTRACTS) -> tuple[dict, str]:
    """The contract and its digest; refuses one that is not as frozen."""
    data = json.loads((folder / f"{contract_id}.json").read_text(encoding="utf-8"))
    d = digest(data)
    lock = json.loads(_lock_path(folder).read_text(encoding="utf-8"))
    frozen = lock.get(contract_id, {}).get("sha256")
    if frozen != d:
        raise ValueError(
            f"contract {contract_id} is not as frozen "
            f"(lock {str(frozen)[:12]}, file {d[:12]}): "
            f"run tools/contracts.py freeze {contract_id} --why ..."
        )
    return data, d


def problems(folder: Path = CONTRACTS) -> list[str]:
    """Every contract matches its lock, and every version has a reason."""
    found = []
    lock_file = _lock_path(folder)
    lock = json.loads(lock_file.read_text(encoding="utf-8")) if lock_file.exists() else {}
    changes = (
        _changes_path(folder).read_text(encoding="utf-8") if _changes_path(folder).exists() else ""
    )
    for cid in contract_ids(folder):
        data = json.loads((folder / f"{cid}.json").read_text(encoding="utf-8"))
        entry = lock.get(cid)
        if not entry:
            found.append(f"{cid}: not frozen (no entry in LOCK.json)")
            continue
        if entry.get("sha256") != digest(data):
            found.append(f"{cid}: changed since it was frozen - freeze it with a reason")
        for v in range(1, int(entry.get("version", 0)) + 1):
            if f"`{cid}` v{v}" not in changes:
                found.append(f"{cid}: version {v} has no reason in CHANGES.md")
    for cid in lock:
        if not (folder / f"{cid}.json").exists():
            found.append(f"{cid}: in LOCK.json but the contract file is gone")
    return found


def freeze(contract_id: str, why: str, who: str = "agent", folder: Path = CONTRACTS) -> int:
    if not why.strip():
        raise ValueError("a reason is required")
    data = json.loads((folder / f"{contract_id}.json").read_text(encoding="utf-8"))
    lock_file = _lock_path(folder)
    lock = json.loads(lock_file.read_text(encoding="utf-8")) if lock_file.exists() else {}
    entry = lock.get(contract_id, {})
    d = digest(data)
    if entry.get("sha256") == d:
        raise ValueError(f"{contract_id} is unchanged; nothing to freeze")
    version = int(entry.get("version", 0)) + 1
    now = datetime.datetime.now().isoformat(timespec="seconds")
    lock[contract_id] = {"sha256": d, "version": version, "frozen_at": now}
    lock_file.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    changes = _changes_path(folder)
    head = (
        ""
        if changes.exists()
        else (
            "# Contract changes\n\nEvery version of every contract, with who changed it and why.\n"
            "The owner allowed agents to change contracts on condition that every change is\n"
            "recorded here and reported (6 Oct 2026).\n\n"
        )
    )
    with changes.open("a", encoding="utf-8") as f:
        f.write(
            head + f"- {now[:10]} `{contract_id}` v{version} ({who}, sha256 {d[:12]}): "
            f"{why.strip()}\n"
        )
    return version


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    fr = sub.add_parser("freeze")
    fr.add_argument("contract_id")
    fr.add_argument("--why", required=True)
    fr.add_argument("--who", default="agent")
    args = ap.parse_args()
    if args.cmd == "freeze":
        v = freeze(args.contract_id, args.why, args.who)
        print(f"FROZEN {args.contract_id} v{v} - report this change to the owner")
        return 0
    found = problems()
    for cid in contract_ids():
        print(f"{cid}: {'ok' if not any(f.startswith(cid + ':') for f in found) else 'NOT OK'}")
    for f in found:
        print("  -", f)
    print("CONTRACTS_OK" if not found else "CONTRACTS_FAIL")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
