"""AUTH-2 DAG law (FUNNEL_LAW_2.md §CALIBRATION_DAG, §DAG_OPERATIONS): which node may run next,
every terminal state and its ledger mapping, the HOLM join, the closure, and the refusals of
the node runner (program, preregistration, ledger binding, predecessors).

PAPER / RESEARCH ONLY. No node runs here; results are hand-written records.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from auth2 import calibration as CA  # noqa: E402
from auth2 import closure as CL  # noqa: E402
from auth2 import families as F  # noqa: E402
from auth2 import gates as GT  # noqa: E402
from auth2 import run_node as RN  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SHA = "p" * 64
LIMITS = {"A1": False, "A2": False, "A3": False}


def rec(state, **kw):
    return {"terminal_state": state, "program_sha256": SHA, **kw}


def d0(limited=None, state="PASS"):
    return {"D0": rec(state, data_limited=limited or dict(LIMITS))}


def chain(fam, *states):
    names = [f"CAL-{fam}", f"PC-{fam}", f"N-{fam}", fam]
    return {n: rec(s) for n, s in zip(names, states)}


def nodes(e):
    return [n for n, _ in e["next"]]


# -- eligibility ---------------------------------------------------------------------------

def test_the_first_node_is_d0_and_an_invalid_d0_is_a_retry():
    assert nodes(RN.eligible({})) == ["D0"]
    e = RN.eligible(d0(state="INVALID_RUN"))
    assert e["next"] == [] and e["retry"] == ["D0"] and not e["closure"]


def test_after_d0_every_family_calibrates_independently():
    assert nodes(RN.eligible(d0())) == ["CAL-A1", "CAL-A2", "CAL-A3"]


def test_a_data_limited_family_has_no_further_node():
    e = RN.eligible(d0({"A1": False, "A2": True, "A3": False}))
    assert nodes(e) == ["CAL-A1", "CAL-A3"]
    assert e["families"]["A2"] == "DATA_LIMITED"


@pytest.mark.parametrize("states,terminal", [
    (("LAW_INVALID",), "LAW_INVALID"),                       # size FAIL
    (("INCONCLUSIVE_UNDERPOWERED",), "INCONCLUSIVE_UNDERPOWERED"),  # power FAIL
    (("PASS", "NOT_SURVIVED"), "NOT_SURVIVED"),              # PC-Ax not SURVIVED
    (("PASS", "SURVIVED", "NOT_REJECTED"), "NOT_REJECTED"),  # N-Ax not REJECTED
    (("PASS", "SURVIVED", "REJECTED", "REJECTED"), "REJECTED"),
    (("PASS", "SURVIVED", "REJECTED", "INCONCLUSIVE"), "INCONCLUSIVE"),
])
def test_a_family_stops_at_its_first_failed_edge(states, terminal):
    r = {**d0(), **chain("A1", *states), **chain("A2", "INCONCLUSIVE_UNDERPOWERED"),
         **chain("A3", "INCONCLUSIVE_UNDERPOWERED")}
    e = RN.eligible(r)
    assert e["families"]["A1"] == terminal
    assert nodes(e) == ["HOLM"]  # every family terminal: the join runs


def test_holm_waits_for_every_family():
    r = {**d0(), **chain("A1", "PASS", "SURVIVED", "REJECTED", "PRE_HOLM_PASS"), **chain("A2", "PASS"),
         **chain("A3", "LAW_INVALID")}
    assert nodes(RN.eligible(r)) == ["PC-A2"]


def test_a_split_node_runs_its_parts_in_order():
    r = {**d0(), **chain("A2", "PASS"), **chain("A1", "LAW_INVALID"), **chain("A3", "LAW_INVALID")}
    assert RN.eligible(r)["next"] == [("PC-A2", 1)]
    r["PC-A2.part1"] = rec("PART_COMPLETE", partial=True)
    assert RN.eligible(r)["next"] == [("PC-A2", 2)]


def test_sc_runs_only_for_families_that_passed_holm():
    r = {**d0(), **chain("A1", "PASS", "SURVIVED", "REJECTED", "PRE_HOLM_PASS"),
         **chain("A2", "PASS", "SURVIVED", "REJECTED", "PRE_HOLM_PASS"), **chain("A3", "LAW_INVALID"),
         "HOLM": rec("COMPLETE", holm_pass={"A1": True, "A2": False, "A3": False})}
    assert nodes(RN.eligible(r)) == ["SC-A1"]
    r["SC-A1"] = rec("REJECTED")
    e = RN.eligible(r)
    assert e["next"] == [] and e["closure"]


# -- closure and the ledger mapping -----------------------------------------------------------

def all_underpowered():
    return {**d0(), **chain("A1", "INCONCLUSIVE_UNDERPOWERED"), **chain("A2", "INCONCLUSIVE_UNDERPOWERED"),
            **chain("A3", "INCONCLUSIVE_UNDERPOWERED"),
            "HOLM": rec("COMPLETE", holm_pass={f: False for f in F.FAMILIES},
                        holm=GT.holm_node({f: None for f in F.FAMILIES}))}


def test_zero_survivors_is_a_lawful_closure():
    c = CL.closure(all_underpowered(), REPO)
    assert c["zero_survivors"] and c["survivors"] == [] and c["diagnostic_combination"] is None
    assert c["holm"]["p_values"] == {"A1": 1.0, "A2": 1.0, "A3": 1.0}
    t = c["trials"]
    assert t["TRIAL-AUTH2-A1"] == {"node": "A1", "state": "ABORTED", "terminal": "NOT_RUN: INCONCLUSIVE_UNDERPOWERED"}
    assert t["TRIAL-AUTH2-CAL-A1"]["state"] == "COMPLETED"
    assert t["TRIAL-AUTH2-PC-A1"] == {"node": "PC-A1", "state": "ABORTED", "terminal": "NOT_RUN"}
    assert t["TRIAL-AUTH2-HOLM"]["state"] == "COMPLETED"
    assert len(t) == 14 and c["real_money_authorized"] is False


def survivor_world():
    rng = np.random.default_rng(0)
    run = lambda n: {"primary": {"returns": (rng.standard_normal(n) * 0.01).tolist()}}  # noqa: E731
    r = {**d0(), **chain("A1", "PASS", "SURVIVED", "REJECTED", "PRE_HOLM_PASS"),
         **chain("A2", "PASS", "SURVIVED", "REJECTED", "PRE_HOLM_PASS"),
         **chain("A3", "PASS", "SURVIVED", "REJECTED", "REJECTED"),
         "HOLM": rec("COMPLETE", holm_pass={"A1": True, "A2": True, "A3": False}),
         "SC-A1": rec("SURVIVED"), "SC-A2": rec("SURVIVED")}
    r["A1"]["engine_runs"] = run(2192)
    r["A2"]["engine_runs"] = run(2192)
    return r


def test_two_survivors_get_only_a_diagnostic_combination():
    c = CL.closure(survivor_world(), REPO)
    assert c["survivors"] == ["A1", "A2"]
    combo = c["diagnostic_combination"]
    assert combo["status"] == "DIAGNOSTIC_ONLY" and combo["engine_invocations"] == 0
    assert sum(combo["weights"].values()) == pytest.approx(1.0)
    t = c["trials"]
    assert t["TRIAL-AUTH2-A1"]["state"] == "SURVIVED" and t["TRIAL-AUTH2-A3"]["state"] == "REJECTED"
    assert t["TRIAL-AUTH2-PC-A1"]["state"] == "COMPLETED"  # a control never records SURVIVED


def test_holm_failure_and_sc_rejection_are_rejections():
    r = survivor_world()
    r["HOLM"]["holm_pass"]["A2"] = False
    del r["SC-A2"]
    r["SC-A1"] = rec("REJECTED")
    c = CL.closure(r, REPO)
    assert c["families"]["A2"] == {"terminal": "REJECTED", "at": "HOLM"}
    assert c["families"]["A1"] == {"terminal": "REJECTED", "at": "SC-A1"}
    assert c["zero_survivors"]


def test_closure_refuses_while_a_node_can_run():
    r = all_underpowered()
    del r["HOLM"]
    with pytest.raises(SystemExit, match="not exhausted"):
        CL.closure(r, REPO)


def test_closure_refuses_mixed_program_hashes():
    r = all_underpowered()
    r["CAL-A2"]["program_sha256"] = "q" * 64
    with pytest.raises(SystemExit, match="more than one program"):
        CL.closure(r, REPO)


def test_stop_program_after_a_spent_retry():
    r = {**d0(), **chain("A1", "PASS", "INVALID_RUN"), **chain("A2", "PASS"), **chain("A3", "LAW_INVALID")}
    with pytest.raises(SystemExit, match="not exhausted"):
        CL.closure(r, REPO)
    c = CL.closure(r, REPO, stop_program=True)
    assert c["families"]["A1"] == {"terminal": "INVALID_RUN", "at": "PC-A1"}
    assert c["families"]["A2"] == {"terminal": "STOP_PROGRAM", "at": "PC-A2"}
    assert c["trials"]["TRIAL-AUTH2-PC-A1"]["state"] == "FAILED"
    assert c["trials"]["TRIAL-AUTH2-PC-A2"] == {"node": "PC-A2", "state": "ABORTED", "terminal": "NOT_RUN: STOP_PROGRAM"}
    assert c["trials"]["TRIAL-AUTH2-A1"]["state"] == "ABORTED"
    with pytest.raises(SystemExit, match="INVALID_RUN"):
        CL.closure(all_underpowered(), REPO, stop_program=True)


def test_calibration_outcome_mapping():
    assert CA.outcome({"status": "FAIL_SIZE"}) == "LAW_INVALID"
    assert CA.outcome({"status": "FAIL_POWER"}) == "INCONCLUSIVE_UNDERPOWERED"
    assert CA.outcome({"status": "PASS"}) == "PASS"


def test_holm_node_untested_family_enters_with_p_one():
    res = GT.holm_node({"A1": 0.001, "A2": None, "A3": None})
    assert res["p_values"] == {"A1": 0.001, "A2": 1.0, "A3": 1.0}
    assert res["rejected"] == {"A1": True, "A2": False, "A3": False}
    assert res["m"] == 3 and res["alpha"] == 0.05


def test_verdict_precedence():
    fail = GT._verdict("A1", {"C2": {"status": "FAIL"}, "C8": {"status": "INCONCLUSIVE"}}, False)
    assert fail["verdict"] == "REJECTED"
    inc = GT._verdict("A1", {"C2": {"status": "PASS"}, "C8": {"status": "INCONCLUSIVE"}}, False)
    assert inc["verdict"] == "INCONCLUSIVE"
    ok = GT._verdict("A1", {"C2": {"status": "PASS"}, "C3": {"status": "PASS", "p_value": 0.02},
                            "C11": {"status": "REPORTED"}}, False)
    assert ok["verdict"] == "PRE_HOLM_PASS" and not ok["accepted_with_holm_m3"]  # 0.02 > 0.05 / 3


# -- the node runner's refusals on the committed program ---------------------------------------

def test_every_node_matches_its_preregistration():
    program, sha = RN.load_program(REPO)
    for node in RN.NODES:
        entry, prereg = RN.node_prereg(REPO, program, node)
        assert prereg["node_id"] == node and prereg["dry_run"] is True


def test_every_node_is_bound_in_the_ledger_and_not_yet_terminal():
    program, _ = RN.load_program(REPO)
    from trial_ledger import TrialLedger

    if TrialLedger(REPO / RN.LEDGER_REL).preregistration_for("TRIAL-AUTH2-D0") is None:
        pytest.skip("AUTH-2 PREREGISTERED records are not appended yet (tests/test_auth2_records.py: all or none)")
    for entry in program["dag"]["nodes"]:
        led = RN.check_ledger(REPO, entry["trial_id"], entry["id"], entry["prereg_sha256"])
        assert led["status"] == "PASS", led
        assert led["terminal_records"] == []
        bad = RN.check_ledger(REPO, entry["trial_id"], entry["id"], "0" * 64)
        assert bad["status"] == "FAIL"


@pytest.mark.parametrize("node,part,match", [("A4", 1, "unknown node"), ("A1", 2, "part"),
                                              ("PC-A2", 3, "part")])
def test_the_runner_refuses_unknown_nodes_and_parts(tmp_path, node, part, match):
    with pytest.raises(SystemExit, match=match):
        RN.run(node, part, REPO, tmp_path / "out", tmp_path, tmp_path, "docker")


def test_the_runner_refuses_a_missing_or_wrong_predecessor(tmp_path):
    from trial_ledger import TrialLedger

    if TrialLedger(REPO / RN.LEDGER_REL).preregistration_for("TRIAL-AUTH2-CAL-A1") is None:
        with pytest.raises(SystemExit, match="not preregistered"):
            RN.run("CAL-A1", 1, REPO, tmp_path / "out", tmp_path, tmp_path, "docker")
        return
    with pytest.raises(SystemExit, match="predecessor D0"):
        RN.run("CAL-A1", 1, REPO, tmp_path / "out", tmp_path, tmp_path, "docker")
    program, sha = RN.load_program(REPO)
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "D0.result.json").write_text(json.dumps({"terminal_state": "PASS", "program_sha256": "0" * 64}))
    with pytest.raises(SystemExit, match="different program"):
        RN.run("CAL-A1", 1, REPO, tmp_path / "out", tmp_path, tmp_path, "docker")
    (tmp_path / "x" / "D0.result.json").write_text(json.dumps({"terminal_state": "INVALID_RUN", "program_sha256": sha}))
    with pytest.raises(SystemExit, match="edge requires"):
        RN.run("CAL-A1", 1, REPO, tmp_path / "out", tmp_path, tmp_path, "docker")


def test_scan_refuses_duplicate_results(tmp_path):
    for d in ("a", "b"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "D0.result.json").write_text("{}")
    with pytest.raises(SystemExit, match="two result records"):
        RN.scan_results(tmp_path)


def test_run_plans_equal_the_compute_plan():
    for node, spec in RN.NODES.items():
        if spec["invocations"]:
            plan = RN.run_plan(node, spec["family"])
            assert len(plan) == spec["invocations"]
            assert len({r["name"] for r in plan}) == len(plan)
    assert [r["name"] for r in RN.run_plan("SC-A2", "A2")] == ["primary@sec"]
    assert RN.NODES["PC-A2"]["parts"] == 2 and RN.NODES["N-A2"]["parts"] == 2


@pytest.mark.parametrize("fam", ["A1", "A3"])
def test_null_nodes_check_causality_on_the_family_generators(fam):
    # N-Ax: C1 LOOKAHEAD / RECURSIVE judge the family's own generators on the node's data; the
    # law defines the A1 and A3 nulls over the whole window, so a truncated window changes them
    # by construction (that is no price lookahead) and they are reported as not checked
    from auth2 import signals as S
    from auth2 import synthetic as SY
    from auth2.engine_selftest import _ms

    w = SY.generate(fam, seed=4242, edge=0.0, start_ms=_ms(2018), end_ms=_ms(2021))
    win = (_ms(2019, 6), _ms(2021))
    r = RN.causality(fam, w.market, win, ("null", F.N_FIXTURE_SEED))
    assert r["status"] == "PASS" and "null_fixtures" in r
    assert sorted(r["by_generator"]) == sorted(["primary", "bench", *F.PERTURBATIONS[fam]])

    if fam == "A3":  # (an A1 null cannot even be drawn on a cut shorter than its 2 x 90-day margins)
        def null_gen(mm, s, e):
            b = F.bundle(fam, mm, s, e, ["primary"], 0, ("null", F.N_FIXTURE_SEED))
            return b.exec_times, b.weights[:, 0, :]
        assert S.lookahead_check(null_gen, w.market, win[0], win[1])["status"] == "FAIL"
    assert "null_fixtures" not in RN.causality(fam, w.market, win, None)
