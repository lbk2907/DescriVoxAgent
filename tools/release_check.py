"""Judge a release against contracts/release.json, from recorded evidence.

    python tools/release_check.py          # prints the verdict, exit 0 only on VERIFIED
    python tools/release_check.py --json   # the same, as JSON

VERIFIED      every required check passed - tag it (tools/tag_release.py)
FAILED        something required is wrong
INCONCLUSIVE  something required could not be checked (no evidence yet,
              NVDA not reachable, ...) - never treated as a pass

The evidence comes from the tools themselves (tools/evidence.py): every
gate run, build and NVDA check of the exe appends a record with the git
tree it ran on. A record counts only if the released commit differs from
that tree in nothing but the paths the contract allows (documents).
"""

from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_docs  # noqa: E402
import contracts as C  # noqa: E402
import evidence as E  # noqa: E402

REPO = E.REPO


def _same_code(entry: dict, allowed: list[str]) -> tuple[bool, list[str]]:
    """Was this record made on the code being released?"""
    head_tree = E.git("rev-parse", "HEAD^{tree}")
    tree = entry.get("tree", "")
    if not tree:
        return False, ["no tree recorded"]
    changed = E.changed_between(tree, head_tree)
    other = [p for p in changed if not any(fnmatch.fnmatch(p, a) for a in allowed)]
    return not other, other


def _check(check: dict, contract: dict, records: list[dict], ver: str) -> C.Result:
    kind, cid = check["type"], check["id"]
    req = bool(check.get("required", True))
    allowed = contract.get("allowed_after_test", [])

    def res(outcome, detail):
        return C.Result(cid, outcome, detail, req)

    if kind == "contracts_ok":
        found = C.problems()
        return res(C.PASS, "all frozen") if not found else res(C.FAIL, "; ".join(found))

    if kind == "docs_ok":
        found = check_docs.problems()
        return res(C.PASS, f"DOCS_OK v{ver}") if not found else res(C.FAIL, "; ".join(found[:5]))

    if kind == "gate_runs":
        need = int(check.get("params", {}).get("min_passes", 2))
        gates = [r for r in records if r.get("kind") == "gate"]
        # newest first: count the consecutive passes on this code
        streak = 0
        for r in reversed(gates):
            same, _ = _same_code(r, allowed)
            if not same:
                continue
            if not r.get("ok"):
                break
            streak += 1
        if streak >= need:
            return res(C.PASS, f"{streak} passes in a row on this code")
        if not gates:
            return res(C.UNKNOWN, "no gate run recorded")
        same_code = [r for r in gates if _same_code(r, allowed)[0]]
        if same_code and not same_code[-1].get("ok"):
            return res(C.FAIL, "the latest gate run on this code FAILED")
        return res(C.UNKNOWN, f"{streak} pass(es) in a row on this code, {need} needed")

    if kind == "build":
        builds = [r for r in records if r.get("kind") == "build" and r.get("version") == ver]
        for r in reversed(builds):
            same, other = _same_code(r, allowed)
            if not same:
                continue
            z = Path(r.get("zip", ""))
            if not r.get("ok") or not z.exists():
                return res(C.FAIL, f"the build of {ver} left no zip at {z}")
            if E.sha256_file(z) != r.get("zip_sha256"):
                return res(C.FAIL, f"{z.name} changed after it was built")
            return res(C.PASS, f"{z.name} sha256 {r['zip_sha256'][:12]}")
        return res(C.UNKNOWN, f"no build of {ver} recorded on this code")

    if kind == "nvda_frozen":
        want = check.get("params", {}).get("contract", "a11y-main")
        exe = REPO / "dist/DescriVox/DescriVox.exe"
        if not exe.exists():
            return res(C.UNKNOWN, "no built exe")
        exe_sha = E.sha256_file(exe)
        runs = [
            r
            for r in records
            if r.get("kind") == "nvda"
            and r.get("frozen")
            and r.get("exe_sha256") == exe_sha
            and r.get("contract") == want
        ]
        if not runs:
            return res(C.UNKNOWN, f"NVDA has not checked this exe against {want}")
        last = runs[-1]
        if last.get("contract_digest") != C.load(want)[1]:
            return res(C.UNKNOWN, f"the exe was checked against an older {want}")
        v = last.get("verdict")
        outcome = {C.VERIFIED: C.PASS, C.FAILED: C.FAIL}.get(v, C.UNKNOWN)
        return res(outcome, f"{want}: {v} at {last.get('time')}")

    if kind == "source_backup":
        import make_source_zip as msz

        z = (
            Path.home()
            / "Documents"
            / "DescriVox-source-backups"
            / f"DescriVox-Agent-source-v{ver}.zip"
        )
        if not z.exists():
            return res(C.UNKNOWN, f"{z.name} not found")
        found = msz.problems(z)
        return res(C.PASS, z.name) if not found else res(C.FAIL, "; ".join(found[:3]))

    if kind == "tag_free":
        tag = f"v{ver}"
        at = E.git("rev-list", "-n", "1", tag) if E.git("tag", "-l", tag) else ""
        if not at:
            return res(C.PASS, f"{tag} not tagged yet")
        if at == E.head():
            return res(C.PASS, f"{tag} already on this commit")
        return res(C.FAIL, f"{tag} already exists on another commit ({at[:8]})")

    return res(C.UNKNOWN, f"unknown check type {kind}")


def run() -> C.Verdict:
    contract, d = C.load("release")
    ver = E.version()
    records = E.read()
    v = C.Verdict("release", d)
    for check in contract["checks"]:
        try:
            v.results.append(_check(check, contract, records, ver))
        except Exception as e:  # a checker that breaks is not a pass
            v.results.append(
                C.Result(
                    check["id"], C.UNKNOWN, f"could not run: {e}", bool(check.get("required", True))
                )
            )
    return v


def main() -> int:
    v = run()
    if "--json" in sys.argv:
        print(json.dumps(v.as_dict(), indent=2))
    else:
        print(f"Release v{E.version()}")
        print("\n".join(v.lines()))
    return 0 if v.verdict == C.VERIFIED else 1


if __name__ == "__main__":
    sys.exit(main())
