"""Judge a measurement against a contract frozen BEFORE it was run.

Owner, 6 Oct 2026: the rule for adopting a change is written down and
frozen first, so it cannot be bent to fit the numbers afterwards.

    python tools/measure_check.py measure-<feature> <results.json>

<results.json> (written by the bench, e.g. `cast_bench.py score --json`):
    {"created": "<ISO time>", "runs": 2,
     "metrics": {"wrong_rate": {"on": 14.6, "off": 12.5}, ...}}

Each metric in the contract compares "on" with "off":
    on_minus_off   on - off, within [min, max]
    on_over_off    on / off, within [min, max]
Results created before the contract was frozen are INCONCLUSIVE: a rule
written after the numbers is not a rule.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contracts as C  # noqa: E402


def judge(contract: dict, digest: str, results: dict, frozen_at: str) -> C.Verdict:
    v = C.Verdict(contract["contract_id"], digest)
    created = str(results.get("created", ""))
    if not created or created < frozen_at:
        v.results.append(C.Result("frozen_first", C.UNKNOWN,
                                  f"results ({created or 'no time'}) are older than the "
                                  f"contract ({frozen_at}) - freeze the rule BEFORE measuring"))
        return v
    v.results.append(C.Result("frozen_first", C.PASS, f"contract {frozen_at}, results {created}"))
    runs = int(results.get("runs", 0))
    need = int(contract.get("min_runs", 1))
    v.results.append(C.Result("enough_runs", C.PASS if runs >= need else C.UNKNOWN,
                              f"{runs} run(s), {need} needed"))
    for m in contract.get("metrics", []):
        req = bool(m.get("required", True))
        got = results.get("metrics", {}).get(m["metric"])
        if not got or "on" not in got or "off" not in got:
            v.results.append(C.Result(m["id"], C.UNKNOWN, f"{m['metric']} not measured", req))
            continue
        on, off = float(got["on"]), float(got["off"])
        if m["compare"] == "on_minus_off":
            value = on - off
        elif m["compare"] == "on_over_off":
            if off == 0:
                v.results.append(C.Result(m["id"], C.UNKNOWN, "off is 0", req))
                continue
            value = on / off
        else:
            v.results.append(C.Result(m["id"], C.UNKNOWN, f"unknown compare {m['compare']}", req))
            continue
        ok = ("min" not in m or value >= m["min"]) and ("max" not in m or value <= m["max"])
        bound = " ".join(f"{k} {m[k]}" for k in ("min", "max") if k in m)
        v.results.append(C.Result(m["id"], C.PASS if ok else C.FAIL,
                                  f"{m['metric']} {m['compare']} = {value:.2f} ({bound})", req))
    return v


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    contract_id, results_path = sys.argv[1], Path(sys.argv[2])
    contract, digest = C.load(contract_id)
    lock = json.loads((C.CONTRACTS / "LOCK.json").read_text(encoding="utf-8"))
    results = json.loads(results_path.read_text(encoding="utf-8"))
    v = judge(contract, digest, results, lock[contract_id]["frozen_at"])
    print("\n".join(v.lines()))
    return 0 if v.verdict == C.VERIFIED else 1


if __name__ == "__main__":
    sys.exit(main())
