"""Regression round 74: owner, 6 Oct 2026 - frozen contracts.

After reviewing Watch Skill's verification design the owner chose three
contracts for this repo: the release (judged on recorded evidence), the
main window's accessibility (what NVDA must hear), and measurements (the
rule frozen before the numbers). An agent may change a contract only
through tools/contracts.py freeze, which records why.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import io
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

if "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import contracts as C  # noqa: E402
import evidence as E  # noqa: E402

results: list[tuple[str, bool]] = []


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def test_every_contract_is_frozen_with_a_reason():
    assert C.problems() == [], C.problems()
    assert {"release", "a11y-main", "measure-template"} <= set(C.contract_ids())


def test_a_change_is_caught_and_freeze_records_why():
    tmp = Path(tempfile.mkdtemp(prefix="odc_t74_"))
    for f in ("release.json", "LOCK.json", "CHANGES.md"):
        shutil.copy2(C.CONTRACTS / f, tmp / f)
    data = json.loads((tmp / "release.json").read_text(encoding="utf-8"))
    data["checks"] = [c for c in data["checks"] if c["id"] != "gate_twice"]   # weaken it
    (tmp / "release.json").write_text(json.dumps(data), encoding="utf-8")
    lock = json.loads((tmp / "LOCK.json").read_text(encoding="utf-8"))
    (tmp / "LOCK.json").write_text(json.dumps({"release": lock["release"]}), encoding="utf-8")
    assert any("changed since it was frozen" in p for p in C.problems(tmp)), C.problems(tmp)
    try:
        C.load("release", tmp)
        raise AssertionError("a changed contract was loaded")
    except ValueError:
        pass
    try:
        C.freeze("release", "   ", folder=tmp)
        raise AssertionError("frozen without a reason")
    except ValueError:
        pass
    v = C.freeze("release", "test: dropped gate_twice", folder=tmp)
    assert v == 2 and C.problems(tmp) == [], C.problems(tmp)
    assert "`release` v2" in (tmp / "CHANGES.md").read_text(encoding="utf-8")


def test_verdicts():
    v = C.Verdict("x", "d")
    assert v.verdict == C.INCONCLUSIVE                         # no checks = not a pass
    v.results = [C.Result("a", C.PASS), C.Result("b", C.UNKNOWN)]
    assert v.verdict == C.INCONCLUSIVE
    v.results.append(C.Result("c", C.FAIL))
    assert v.verdict == C.FAILED
    v.results = [C.Result("a", C.PASS), C.Result("b", C.FAIL, required=False)]
    assert v.verdict == C.VERIFIED                             # advisory never decides


def test_release_needs_evidence_on_this_code():
    import release_check as R
    os.environ["ODC_EVIDENCE_DIR"] = tempfile.mkdtemp(prefix="odc_t74ev_")
    contract, _d = C.load("release")
    gate = next(c for c in contract["checks"] if c["id"] == "gate_twice")
    ver = E.version()
    head_tree = E.git("rev-parse", "HEAD^{tree}")
    r = R._check(gate, contract, [], ver)
    assert r.outcome == C.UNKNOWN, r                           # nothing recorded
    same = {"kind": "gate", "ok": True, "tree": head_tree}
    r = R._check(gate, contract, [same], ver)
    assert r.outcome == C.UNKNOWN and "1 pass" in r.detail, r  # one is not two
    r = R._check(gate, contract, [same, same], ver)
    assert r.outcome == C.PASS, r
    # a gate run on code with an uncommitted CODE change is not this release
    import fnmatch
    work = E.working_tree()
    changed = E.changed_between(work, head_tree)
    if any(not any(fnmatch.fnmatch(p, a) for a in contract["allowed_after_test"])
           for p in changed):
        wt = {"kind": "gate", "ok": True, "tree": work}
        assert R._check(gate, contract, [wt, wt], ver).outcome != C.PASS
    old = {"kind": "gate", "ok": True, "tree": E.git("rev-parse", "HEAD~30^{tree}")}
    if old["tree"]:
        r = R._check(gate, contract, [old, old], ver)
        assert r.outcome != C.PASS, "a gate run on other code counted"
    failed = {"kind": "gate", "ok": False, "tree": head_tree}
    r = R._check(gate, contract, [failed], ver)
    assert r.outcome == C.FAIL, r


def test_release_tag_check_and_unknown_type():
    import release_check as R
    contract, _d = C.load("release")
    tag = next(c for c in contract["checks"] if c["id"] == "tag_free")
    assert R._check(tag, contract, [], "0.0.0-never").outcome == C.PASS
    assert R._check(tag, contract, [], "1.9.7").outcome == C.FAIL     # an old tag elsewhere
    odd = {"id": "x", "type": "nonsense", "required": True}
    assert R._check(odd, contract, [], "1.9.7").outcome == C.UNKNOWN


def test_a11y_contract_judges_what_nvda_said():
    import nvda_accessibility_check as N
    contract, d = C.load("a11y-main")
    good = [{"step": i + 1, "role": w["role"], "name": w["name"] + " x",
             "spoken": [w["name"] + " " + w["role"]]}
            for i, w in enumerate(contract["required"])]
    assert N.evaluate_contract(good, contract, d).verdict == C.VERIFIED
    missing = good[1:]
    assert N.evaluate_contract(missing, contract, d).verdict == C.FAILED
    silent = [dict(e, spoken=[]) if e["step"] == 3 else e for e in good]
    assert N.evaluate_contract(silent, contract, d).verdict == C.FAILED
    nothing = [dict(e, spoken=[]) for e in good]
    assert N.evaluate_contract(nothing, contract, d).verdict == C.INCONCLUSIVE


def test_measure_rule_must_come_first():
    import measure_check as M
    contract, d = C.load("measure-template")
    frozen = "2026-10-06T00:00:00"
    good = {"created": "2026-10-07T00:00:00", "runs": 2,
            "metrics": {"wrong_rate": {"on": 13.0, "off": 12.0},
                        "name_rate": {"on": 50.0, "off": 10.0},
                        "lines": {"on": 90, "off": 100}}}
    assert M.judge(contract, d, good, frozen).verdict == C.VERIFIED
    worse = json.loads(json.dumps(good))
    worse["metrics"]["wrong_rate"]["on"] = 16.0
    assert M.judge(contract, d, worse, frozen).verdict == C.FAILED
    early = dict(good, created="2026-10-05T00:00:00")
    assert M.judge(contract, d, early, frozen).verdict == C.INCONCLUSIVE
    one_run = dict(good, runs=1)
    assert M.judge(contract, d, one_run, frozen).verdict == C.INCONCLUSIVE


def test_tools_record_their_own_evidence():
    gate = (REPO / "run_gate.bat").read_text(encoding="utf-8")
    build = (REPO / "build.bat").read_text(encoding="utf-8")
    nvda = (REPO / "tools/nvda_accessibility_check.py").read_text(encoding="utf-8")
    assert "tools\\evidence.py gate %FAIL%" in gate
    assert "tools\\evidence.py build" in build
    assert '_record(args.frozen, args.contract, digest' in nvda
    tmp = tempfile.mkdtemp(prefix="odc_t74rec_")
    os.environ["ODC_EVIDENCE_DIR"] = tmp
    E.record("gate", ok=True)
    got = E.read()
    assert got and got[-1]["kind"] == "gate" and got[-1]["tree"], got
    assert Path(tmp, "evidence.jsonl").exists()


def main() -> int:
    check("every contract is frozen, with a reason", test_every_contract_is_frozen_with_a_reason)
    check("a weakened contract is caught; freeze records why",
          test_a_change_is_caught_and_freeze_records_why)
    check("verdicts: inconclusive is never a pass", test_verdicts)
    check("release: evidence must be on this code", test_release_needs_evidence_on_this_code)
    check("release: tag check, unknown check type", test_release_tag_check_and_unknown_type)
    check("a11y contract judges what NVDA said", test_a11y_contract_judges_what_nvda_said)
    check("measure: the rule must come first", test_measure_rule_must_come_first)
    check("gate, build and NVDA record their own evidence", test_tools_record_their_own_evidence)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
