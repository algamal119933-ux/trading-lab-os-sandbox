"""P3-PLN-10 acceptance program validators (research/p3/acceptance.py).

Synthetic evidence only. Every validator is fail-closed: missing, malformed, foreign-run, UNPROVEN or
contradictory evidence never yields PASS, and the run verdict is at best a CANDIDATE for the Owner's
acceptance. PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import copy
import math
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from p3 import acceptance as acc  # noqa: E402

SHA = "a" * 64
TOL = "0.00000001"


def _config(**over) -> dict:
    """A COMPLETE synthetic run configuration (every Owner decision set). Synthetic values only."""
    cfg = {
        "record_type": acc.RUN_CONFIG_TYPE, "run_id": "RUN-1", "frozen_commit": "c" * 40,
        "dry_run": True, "real_money_authorized": False,
        "paper_runtime": {"runtime_id": "tradinglab-fp-control-9", "authority_record": "docs/p3/SYNTHETIC_RUNTIME.md",
                          "authority_merge": "d" * 40},
        "trial_window": {"start_utc": "2026-11-01T00:00:00Z", "duration_hours": 72},
        "emergency_stop_bound_s": 30,
        "acceptance_criteria": {"matrix_sha256": acc.matrix_digest(), "criterion_ids": sorted(acc.ACCEPTANCE_MATRIX),
                                "pnl_tolerance_quote": TOL},
        "launch_authority": {"granted_by": "Owner", "record_path": "docs/p3/SYNTHETIC_LAUNCH_AUTHORITY.md",
                             "merge_commit": "e" * 40, "paper_launch_authorized": True},
    }
    for dotted, value in over.items():
        node, *path = dotted.split("__")
        if not path:
            cfg[node] = value
        else:
            cfg[node][path[0]] = value
    return cfg


def _rec(cid: str, status: str = "PASS", run: str = "RUN-1", **over) -> dict:
    rec = {"record_type": acc.RECORD_TYPE, "run_id": run, "criterion_id": cid, "scenario": "synthetic",
           "utc": "2026-11-01T00:00:00Z", "status": status,
           "artifacts": [{"path": "p3-evidence/x.json", "sha256": SHA}], "real_money_authorized": False}
    rec.update(over)
    return rec


# -- matrix -------------------------------------------------------------------------------------------------
def test_the_matrix_maps_every_required_workstream_with_complete_rows():
    assert acc.matrix_completeness() == []
    assert {row["ws"] for row in acc.ACCEPTANCE_MATRIX.values()} >= set(acc.REQUIRED_WORKSTREAMS)


def test_the_matrix_refuses_a_missing_workstream_or_an_unknown_validator():
    broken = {k: v for k, v in acc.ACCEPTANCE_MATRIX.items() if v["ws"] != "PLN-05"}
    broken["PLN-02.x"] = {**acc.ACCEPTANCE_MATRIX["PLN-02.inventory_complete"], "validator": "trust_me"}
    problems = acc.matrix_completeness(broken)
    assert any("PLN-05" in p for p in problems)
    assert any("unknown validator" in p for p in problems)


# -- schema ---------------------------------------------------------------------------------------------------
def test_a_well_formed_record_validates():
    assert acc.validate_evidence(_rec("PLN-08.kill_bounded")) == []


@pytest.mark.parametrize("mutation", [
    {"real_money_authorized": True},
    {"status": "OK"},
    {"criterion_id": "PLN-99.invented"},
    {"artifacts": []},
    {"artifacts": [{"path": "x", "sha256": "not-a-digest"}]},
    {"utc": "yesterday"},
    {"extra": 1},
])
def test_malformed_records_are_rejected(mutation):
    assert acc.validate_evidence(_rec("PLN-08.kill_bounded", **mutation))


# -- P&L reconciliation (measurement only) -----------------------------------------------------------------
FILLS = [
    {"trade_id": "T1", "fill_id": "f1", "side": "buy", "qty": "0.0001", "price": "60000"},
    {"trade_id": "T1", "fill_id": "f2", "side": "sell", "qty": "0.0001", "price": "61000"},
]


def test_net_of_quote_fees_reconciles():
    fees = [{"trade_id": "T1", "fill_id": "f1", "asset": "USDT", "amount": "0.006"},
            {"trade_id": "T1", "fill_id": "f2", "asset": "USDT", "amount": "0.0061"}]
    # gross 6.1 - 6.0 = 0.1; fees 0.0121 → net 0.0879
    out = acc.reconcile_pnl(FILLS, fees, [{"trade_id": "T1", "net_quote": "0.0879"}], base_asset="BTC",
                            tolerance_quote=TOL)
    assert out[0].status == acc.PASS and out[0].computed_net_quote == Decimal("0.0879")


def test_a_bnb_fee_is_converted_and_deducted_and_needs_a_price():
    fees = [{"trade_id": "T1", "fill_id": "f1", "asset": "BNB", "amount": "0.00001"}]
    ok = acc.reconcile_pnl(FILLS, fees, [{"trade_id": "T1", "net_quote": "0.094"}], base_asset="BTC",
                           tolerance_quote=TOL,
                           fee_prices={"f1": {"BNB": "600"}})
    assert ok[0].status == acc.PASS  # 0.1 - 0.006
    missing = acc.reconcile_pnl(FILLS, fees, [{"trade_id": "T1", "net_quote": "0.094"}], base_asset="BTC",
                                tolerance_quote=TOL)
    assert missing[0].status == acc.FAIL and "conversion price" in missing[0].detail


def test_a_base_fee_leaves_dust_and_is_not_double_counted():
    fills = [{"trade_id": "T1", "fill_id": "f1", "side": "buy", "qty": "0.0001", "price": "60000"},
             {"trade_id": "T1", "fill_id": "f2", "side": "sell", "qty": "0.0000999", "price": "61000"}]
    fees = [{"trade_id": "T1", "fill_id": "f1", "asset": "BTC", "amount": "0.0000001"}]
    net = Decimal("0.0000999") * 61000 - Decimal("0.0001") * 60000
    out = acc.reconcile_pnl(fills, fees, [{"trade_id": "T1", "net_quote": str(net)}], base_asset="BTC",
                            tolerance_quote=TOL)
    assert out[0].status == acc.PASS
    assert out[0].dust_base == Decimal("0")
    assert out[0].fees_quote == Decimal("0.0000001") * 60000


def test_a_misreported_pnl_fails():
    out = acc.reconcile_pnl(FILLS, [], [{"trade_id": "T1", "net_quote": "0.2"}], base_asset="BTC",
                            tolerance_quote=TOL)
    assert out[0].status == acc.FAIL and "differs" in out[0].detail


@pytest.mark.parametrize("fills,reported,needle", [
    (FILLS + [{"trade_id": "T1", "fill_id": "f2", "side": "sell", "qty": "0.0001", "price": "61000"}],
     [{"trade_id": "T1", "net_quote": "0.1"}], "duplicate fill"),
    ([], [{"trade_id": "T1", "net_quote": "0.1"}], "no fills"),
    (FILLS, [], "without a reported"),
    ([FILLS[0], {**FILLS[1], "qty": "0.0002"}], [{"trade_id": "T1", "net_quote": "0"}], "sold more"),
])
def test_inconsistent_trades_fail_closed(fills, reported, needle):
    out = acc.reconcile_pnl(fills, [], reported, base_asset="BTC", tolerance_quote=TOL)
    assert out and out[0].status == acc.FAIL and needle in out[0].detail


# -- kill switch ------------------------------------------------------------------------------------------------
KILL = {"record_type": "P3_KILL_SWITCH_V1", "dry_run": False, "reason": "acceptance S-KILL", "operator": "hamza",
        "targets": ["tlos-h1-paper-cohort-1"], "still_running": [], "outcome": "STOPPED", "elapsed_s": 0.4,
        "prev_digest": "0" * 64, "digest": "b" * 64}


def test_a_bounded_attributable_stop_passes():
    assert acc.kill_switch_bounded(KILL, bound_s=30)[0] == acc.PASS


@pytest.mark.parametrize("over,expected", [
    ({"elapsed_s": 31}, "FAIL"),
    ({"dry_run": True}, "FAIL"),
    ({"reason": " "}, "FAIL"),
    ({"outcome": "STOP_INCOMPLETE", "still_running": ["x"]}, "FAIL"),
    ({"digest": ""}, "FAIL"),
    ({"targets": [], "outcome": "NOTHING_RUNNING"}, "UNPROVEN"),
    ({"record_type": "OTHER"}, "FAIL"),
])
def test_unbounded_unattributed_or_unexercised_stops_do_not_pass(over, expected):
    assert acc.kill_switch_bounded({**KILL, **over}, bound_s=30)[0] == expected


# -- restart continuity -------------------------------------------------------------------------------------
BEFORE = {"cohort_id": "C1", "t0_utc": "2026-11-01T00:00:00Z", "source_commit": "abc", "ledger_last_digest": "d1",
          "fill_ids": ["f1"], "stopped_runtimes": ["tlos-h1-paper-cohort-1"]}
AFTER = {"cohort_id": "C1", "t0_utc": "2026-11-01T00:00:00Z", "source_commit": "abc",
         "ledger_first_prev_digest": "d1", "fill_ids": ["f2"], "running_runtimes": []}


def test_a_continuous_restart_passes():
    assert acc.restart_continuity(BEFORE, AFTER)[0] == acc.PASS


@pytest.mark.parametrize("over,needle", [
    ({"cohort_id": "C2"}, "cohort_id"),
    ({"source_commit": "def"}, "source_commit"),
    ({"ledger_first_prev_digest": "zz"}, "chain"),
    ({"fill_ids": ["f1"]}, "duplicate execution"),
    ({"running_runtimes": ["tlos-h1-paper-cohort-1"]}, "stopped runtime came back"),
])
def test_broken_continuity_fails(over, needle):
    status, detail = acc.restart_continuity(BEFORE, {**AFTER, **over})
    assert status == acc.FAIL and needle in detail


# -- run verdict --------------------------------------------------------------------------------------------
def test_all_criteria_passing_in_one_run_is_only_a_candidate():
    records = [_rec(cid) for cid in acc.ACCEPTANCE_MATRIX]
    v = acc.run_verdict(records, config=_config())
    assert v["verdict"] == "CANDIDATE_FOR_OWNER_ACCEPTANCE" and v["unmet"] == {}


def test_no_evidence_is_not_accepted():
    v = acc.run_verdict([], config=_config())
    assert v["verdict"] == "NOT_ACCEPTED" and len(v["unmet"]) == len(acc.ACCEPTANCE_MATRIX)


def test_evidence_from_another_run_never_counts():
    records = [_rec(cid, run="RUN-0") for cid in acc.ACCEPTANCE_MATRIX]
    assert acc.run_verdict(records, config=_config())["verdict"] == "NOT_ACCEPTED"


def test_a_fail_is_never_overwritten_by_a_later_pass_and_unproven_is_not_pass():
    records = [_rec(cid) for cid in acc.ACCEPTANCE_MATRIX]
    records += [_rec("PLN-08.kill_bounded", "FAIL"), _rec("PLN-08.kill_bounded", "PASS")]
    v = acc.run_verdict(records, config=_config())
    assert v["unmet"] == {"PLN-08.kill_bounded": "FAIL"}
    records2 = [_rec(cid) for cid in acc.ACCEPTANCE_MATRIX if cid != "PLN-05.host_loss_redundancy"]
    records2.append(_rec("PLN-05.host_loss_redundancy", "UNPROVEN"))
    assert acc.run_verdict(records2, config=_config())["unmet"] == {"PLN-05.host_loss_redundancy": "UNPROVEN"}


def test_a_malformed_record_blocks_the_verdict():
    records = [_rec(cid) for cid in acc.ACCEPTANCE_MATRIX] + [_rec("PLN-02.inventory_complete",
                                                                     real_money_authorized=True)]
    v = acc.run_verdict(records, config=_config())
    assert v["verdict"] == "NOT_ACCEPTED" and v["problems"]


def test_an_incomplete_run_config_blocks_the_verdict_even_when_every_record_passes():
    records = [_rec(cid) for cid in acc.ACCEPTANCE_MATRIX]
    v = acc.run_verdict(records, config=copy.deepcopy(acc.RUN_CONFIG_TEMPLATE))
    assert v["verdict"] == "NOT_ACCEPTED" and any(p.startswith("run config: D") for p in v["problems"])
    with pytest.raises(TypeError):
        acc.run_verdict(records, run_id="RUN-1")  # the old run_id-only call is gone: a config is mandatory


# -- matrix: reuse of merged procedures, evidence ids -------------------------------------------------------
def test_every_matrix_row_cites_a_merged_procedure_that_exists():
    refs = acc.referenced_documents()
    assert refs, "the matrix must cite its procedures"
    for path in refs:
        assert (REPO_ROOT / path).is_file(), f"{path} is cited by {sorted(refs[path])} but is not in the repository"
    for cid, row in acc.ACCEPTANCE_MATRIX.items():
        assert acc._DOC_RE.search(row["procedure"]), cid


def test_reuse_targets_the_accepted_pln04_07_records_and_the_pln09_checklist():
    m = acc.ACCEPTANCE_MATRIX
    assert m["PLN-04.reboot_correct"]["procedure"].startswith("docs/p3/PLN_04_REBOOT_ACCEPTANCE_RUNBOOK.md")
    assert "docs/p3/PLN_04_RECOVERY.md" in m["PLN-04.reboot_correct"]["standalone_record"]
    assert m["PLN-07.matrix_rows"]["procedure"].startswith("docs/p3/PLN_04_RECOVERY.md")
    assert m["PLN-09.projection"]["procedure"].startswith("docs/p3/PLN_09_OWNER_ACCEPTANCE_CHECKLIST.md")
    assert m["PLN-06.s19_alerts"]["procedure"].startswith("docs/p3/PLN_06_ALERTING.md")


def test_a_row_without_a_procedure_or_standalone_record_is_incomplete():
    broken = copy.deepcopy(acc.ACCEPTANCE_MATRIX)
    broken["PLN-02.inventory_complete"]["procedure"] = "see elsewhere"
    del broken["PLN-03.restore_drill"]["standalone_record"]
    problems = acc.matrix_completeness(broken)
    assert any("PLN-02.inventory_complete: procedure" in p for p in problems)
    assert any("PLN-03.restore_drill: missing standalone_record" in p for p in problems)


def test_the_matrix_digest_is_stable_and_sensitive():
    assert acc.matrix_digest() == acc.matrix_digest(copy.deepcopy(acc.ACCEPTANCE_MATRIX))
    changed = copy.deepcopy(acc.ACCEPTANCE_MATRIX)
    changed["PLN-08.kill_bounded"]["criterion"] += " (edited)"
    assert acc.matrix_digest(changed) != acc.matrix_digest()


# -- run configuration: no default may authorize a launch ---------------------------------------------------
def test_the_template_is_launch_blocked_on_all_five_owner_decisions():
    r = acc.launch_readiness(copy.deepcopy(acc.RUN_CONFIG_TEMPLATE))
    assert r["verdict"] == "LAUNCH_BLOCKED"
    assert r["open_owner_decisions"] == ["D1", "D2", "D3", "D4", "D5"]
    assert r["paper_launch_performed"] is False and r["real_money_authorized"] is False


def test_a_complete_synthetic_config_is_only_complete_never_a_launch():
    r = acc.launch_readiness(_config())
    assert r["verdict"] == "CONFIG_COMPLETE_FOR_OWNER_LAUNCH" and r["blockers"] == []
    assert r["paper_launch_performed"] is False


def test_every_owner_decision_maps_to_a_template_field():
    assert sorted(acc.OWNER_DECISIONS) == ["D1", "D2", "D3", "D4", "D5"]
    for d in acc.OWNER_DECISIONS.values():
        assert d["field"] in acc.RUN_CONFIG_TEMPLATE


@pytest.mark.parametrize("field", ["paper_runtime", "trial_window", "emergency_stop_bound_s", "acceptance_criteria",
                                   "launch_authority"])
def test_removing_any_decision_field_blocks_with_its_decision_id(field):
    cfg = _config()
    del cfg[field]
    did = next(k for k, v in acc.OWNER_DECISIONS.items() if v["field"] == field)
    r = acc.launch_readiness(cfg)
    assert r["verdict"] == "LAUNCH_BLOCKED" and did in r["open_owner_decisions"]


@pytest.mark.parametrize("over,decision", [
    ({"paper_runtime__runtime_id": None}, "D1"),
    ({"paper_runtime__runtime_id": "TBD"}, "D1"),
    ({"paper_runtime__runtime_id": "<runtime>"}, "D1"),
    ({"paper_runtime__runtime_id": "freqtrade-live"}, "D1"),
    ({"paper_runtime__runtime_id": "tradinglab-fp-control-3"}, "D1"),
    ({"paper_runtime__authority_record": "default"}, "D1"),
    ({"paper_runtime__authority_merge": "abc"}, "D1"),
    ({"trial_window__duration_hours": None}, "D2"),
    ({"trial_window__duration_hours": 0}, "D2"),
    ({"trial_window__duration_hours": -5}, "D2"),
    ({"trial_window__duration_hours": "72"}, "D2"),
    ({"trial_window__duration_hours": True}, "D2"),
    ({"trial_window__duration_hours": math.inf}, "D2"),
    ({"trial_window__start_utc": "next week"}, "D2"),
    ({"emergency_stop_bound_s": None}, "D3"),
    ({"emergency_stop_bound_s": 0}, "D3"),
    ({"emergency_stop_bound_s": math.nan}, "D3"),
    ({"emergency_stop_bound_s": "30"}, "D3"),
    ({"acceptance_criteria__matrix_sha256": None}, "D4"),
    ({"acceptance_criteria__matrix_sha256": "f" * 64}, "D4"),
    ({"acceptance_criteria__criterion_ids": ["PLN-08.kill_bounded"]}, "D4"),
    ({"acceptance_criteria__criterion_ids": sorted(acc.ACCEPTANCE_MATRIX) + ["PLN-99.extra"]}, "D4"),
    ({"acceptance_criteria__pnl_tolerance_quote": None}, "D4"),
    ({"acceptance_criteria__pnl_tolerance_quote": 1e-8}, "D4"),
    ({"acceptance_criteria__pnl_tolerance_quote": "-1"}, "D4"),
    ({"acceptance_criteria__pnl_tolerance_quote": "TBD"}, "D4"),
    ({"launch_authority__paper_launch_authorized": False}, "D5"),
    ({"launch_authority__paper_launch_authorized": "true"}, "D5"),
    ({"launch_authority__paper_launch_authorized": 1}, "D5"),
    ({"launch_authority__granted_by": "Claude"}, "D5"),
    ({"launch_authority__record_path": None}, "D5"),
    ({"launch_authority__record_path": "docs/p3/OWNER_P3_EXECUTION_AUTHORIZATION.md"}, "D5"),
    ({"launch_authority__merge_commit": None}, "D5"),
])
def test_unset_defaulted_or_placeholder_decisions_block_the_launch(over, decision):
    r = acc.launch_readiness(_config(**over))
    assert r["verdict"] == "LAUNCH_BLOCKED" and decision in r["open_owner_decisions"], r


@pytest.mark.parametrize("over", [{"dry_run": False}, {"dry_run": "true"}, {"real_money_authorized": True},
                                  {"real_money_authorized": None}, {"run_id": "TBD"}, {"frozen_commit": "HEAD"},
                                  {"record_type": "OTHER"}])
def test_safety_and_identity_fields_block_the_launch(over):
    assert acc.launch_readiness(_config(**over))["verdict"] == "LAUNCH_BLOCKED"


def test_an_h1_runtime_needs_its_own_h1_launch_authorization():
    cfg = _config(paper_runtime__runtime_id="tlos-h1-paper-cohort-1")
    assert any("H1_LAUNCH_AUTHORIZATION" in x for x in acc.validate_run_config(cfg))
    cfg["launch_authority"]["record_path"] = "research/paper/h1/launch/H1_LAUNCH_AUTHORIZATION_SYNTHETIC.md"
    assert acc.validate_run_config(cfg) == []


def test_no_committed_run_config_authorizes_a_launch_unless_it_validates():
    path = REPO_ROOT / acc.RUN_CONFIG_PATH
    if not path.exists():
        return  # PAPER_LAUNCH_AUTHORIZED = NO: no configuration is committed
    import json
    assert acc.validate_run_config(json.loads(path.read_text(encoding="utf-8"))) == []


# -- validators refuse a missing threshold ----------------------------------------------------------------------
@pytest.mark.parametrize("bound", [None, 0, -1, math.inf, math.nan, "30", True])
def test_the_kill_validator_refuses_a_missing_or_invalid_bound(bound):
    status, detail = acc.kill_switch_bounded(KILL, bound_s=bound)
    assert status == acc.FAIL and "bound" in detail


def test_the_pnl_tolerance_has_no_default():
    with pytest.raises(TypeError):
        acc.reconcile_pnl(FILLS, [], [{"trade_id": "T1", "net_quote": "0.1"}], base_asset="BTC")
    for bad in (None, 1e-8, "-0.1", "nan"):
        with pytest.raises(ValueError):
            acc.reconcile_pnl(FILLS, [], [{"trade_id": "T1", "net_quote": "0.1"}], base_asset="BTC",
                              tolerance_quote=bad)


# -- the program document renders the module ---------------------------------------------------------------------
def test_the_program_document_lists_every_criterion_and_every_owner_decision():
    doc = (REPO_ROOT / "docs/p3/PLN_10_PAPER_BETA_ACCEPTANCE_PROGRAM.md").read_text(encoding="utf-8")
    assert "DRAFT" in doc and "PAPER_LAUNCH_AUTHORIZED = NO" in doc
    for cid in acc.ACCEPTANCE_MATRIX:
        assert f"`{cid}`" in doc, cid
    for did, d in acc.OWNER_DECISIONS.items():
        assert f"| {did} |" in doc and f"`{d['field']}`" in doc, did
    for heading in ("Acceptance matrix", "Evidence requirements", "Safety boundaries", "Operator procedure",
                    "Stop conditions", "Failure handling", "Controlled rollback"):
        assert heading in doc, heading


def test_the_pln09_checklist_is_the_s_ui_procedure_and_carries_a_run_id():
    text = (REPO_ROOT / "docs/p3/PLN_09_OWNER_ACCEPTANCE_CHECKLIST.md").read_text(encoding="utf-8")
    assert "PLN09_OWNER_ACCEPTANCE   = PENDING" in text, "the checklist must not claim acceptance"
    assert "RUN_ID" in text and "`PLN-09.projection`" in text
    assert "no runtime and no trading authority" in text
    for item in [f"G{i}" for i in range(1, 10)] + [f"S{i}" for i in range(1, 13)] + [f"M{i}" for i in range(1, 10)]:
        assert f"| {item} |" in text, f"walkthrough item {item} missing"


# -- round 3: every matrix row is executable: evidence id, owner, source procedure, stop condition ----------------
def test_every_matrix_row_has_an_evidence_id_owner_source_procedure_and_stop_condition():
    for cid, row in acc.ACCEPTANCE_MATRIX.items():
        assert acc.EVIDENCE_ID_RE.match(cid) and cid.startswith(row["ws"] + "."), cid
        assert row["owner"] in acc.ROW_OWNERS, cid
        assert acc._DOC_RE.search(row["procedure"]), cid
        assert row["stop_condition"].strip() and ("§9" in row["stop_condition"] or "§10" in row["stop_condition"]), cid
    assert acc.matrix_completeness() == []


@pytest.mark.parametrize("key,value,needle", [
    ("owner", "", "missing owner"), ("owner", "Someone", "unknown owner"),
    ("stop_condition", " ", "missing stop_condition"), ("stop_condition", "stop when it feels wrong", "stop_condition must cite"),
])
def test_a_row_without_a_known_owner_or_a_cited_stop_condition_is_incomplete(key, value, needle):
    broken = copy.deepcopy(acc.ACCEPTANCE_MATRIX)
    broken["PLN-08.kill_bounded"][key] = value
    assert any(needle in p for p in acc.matrix_completeness(broken))


def test_a_malformed_evidence_id_is_refused():
    broken = copy.deepcopy(acc.ACCEPTANCE_MATRIX)
    broken["PLN-08 kill"] = broken.pop("PLN-08.kill_bounded")
    broken["PLN-03.x"] = {**broken["PLN-02.inventory_complete"]}  # id prefix does not match its workstream
    problems = acc.matrix_completeness(broken)
    assert any("PLN-08 kill: evidence id" in p for p in problems)
    assert any("PLN-03.x: evidence id" in p for p in problems)


def test_the_program_document_renders_each_rows_owner_and_stop_condition():
    doc = (REPO_ROOT / "docs/p3/PLN_10_PAPER_BETA_ACCEPTANCE_PROGRAM.md").read_text(encoding="utf-8")
    section = doc[doc.index("### 2a."):doc.index("## 3.")]
    for cid, row in acc.ACCEPTANCE_MATRIX.items():
        line = next(l for l in section.splitlines() if l.startswith(f"| `{cid}` |"))
        assert f"| {row['owner']} |" in line and row["stop_condition"] in line, cid


# -- round 3: the run configuration — each decision alone, unset or defaulted, blocks ----------------------------
@pytest.mark.parametrize("did", ["D1", "D2", "D3", "D4", "D5"])
def test_each_decision_left_at_its_template_default_blocks_exactly_that_decision(did):
    field = acc.OWNER_DECISIONS[did]["field"]
    cfg = _config()
    cfg[field] = copy.deepcopy(acc.RUN_CONFIG_TEMPLATE[field])
    r = acc.launch_readiness(cfg)
    assert r["verdict"] == "LAUNCH_BLOCKED" and r["open_owner_decisions"] == [did], r
    v = acc.run_verdict([_rec(c) for c in acc.ACCEPTANCE_MATRIX], config=cfg)
    assert v["verdict"] == "NOT_ACCEPTED" and any(p.startswith(f"run config: {did} ") for p in v["problems"])


@pytest.mark.parametrize("over,decision", [
    ({"paper_runtime": "tradinglab-fp-control-9"}, "D1"),
    ({"paper_runtime__runtime_id": 9}, "D1"),
    ({"paper_runtime__authority_record": None}, "D1"),
    ({"paper_runtime__authority_merge": None}, "D1"),
    ({"trial_window__start_utc": None}, "D2"),
    ({"trial_window": None}, "D2"),
    ({"emergency_stop_bound_s": -1}, "D3"),
    ({"emergency_stop_bound_s": math.inf}, "D3"),
    ({"emergency_stop_bound_s": True}, "D3"),
    ({"acceptance_criteria__criterion_ids": []}, "D4"),
    ({"acceptance_criteria__criterion_ids": "all"}, "D4"),
    ({"acceptance_criteria__pnl_tolerance_quote": "abc"}, "D4"),
    ({"acceptance_criteria__pnl_tolerance_quote": "NaN"}, "D4"),
    ({"acceptance_criteria__pnl_tolerance_quote": "<tolerance>"}, "D4"),
    ({"acceptance_criteria__pnl_tolerance_quote": ""}, "D4"),
    ({"acceptance_criteria__matrix_sha256": "TBD"}, "D4"),
    ({"launch_authority__granted_by": "owner"}, "D5"),
    ({"launch_authority__granted_by": None}, "D5"),
    ({"launch_authority__record_path": "docs/p3/AUTH.txt"}, "D5"),
    ({"launch_authority__record_path": "TBD.md"}, "D5"),
    ({"launch_authority__merge_commit": "HEAD"}, "D5"),
    ({"launch_authority": {}}, "D5"),
])
def test_further_unset_or_defaulted_decisions_block_the_launch_and_the_verdict(over, decision):
    cfg = _config(**over)
    r = acc.launch_readiness(cfg)
    assert r["verdict"] == "LAUNCH_BLOCKED" and decision in r["open_owner_decisions"], r
    assert acc.run_verdict([_rec(c) for c in acc.ACCEPTANCE_MATRIX], config=cfg)["verdict"] == "NOT_ACCEPTED"


@pytest.mark.parametrize("config", [None, [], "RUN-1", {}])
def test_a_config_that_is_not_a_complete_object_never_yields_a_candidate(config):
    v = acc.run_verdict([_rec(c) for c in acc.ACCEPTANCE_MATRIX], config=config)
    assert v["verdict"] == "NOT_ACCEPTED" and v["problems"] and v["met"] == 0


def test_the_template_itself_validates_to_blockers_on_every_decision_and_identity_field():
    blockers = acc.validate_run_config(copy.deepcopy(acc.RUN_CONFIG_TEMPLATE))
    for did in ("D1", "D2", "D3", "D4", "D5"):
        assert any(b.startswith(did + " ") for b in blockers), did
    assert any("run_id" in b for b in blockers) and any("frozen_commit" in b for b in blockers)


def test_no_run_config_with_real_values_is_committed():
    assert not (REPO_ROOT / acc.RUN_CONFIG_PATH).exists(), "the run configuration is the Owner's own PR"


# -- round 3: evidence outside the trial window never counts --------------------------------------------------
@pytest.mark.parametrize("utc", ["2026-10-31T23:59:59Z", "2026-11-04T00:00:01Z"])
def test_a_pass_record_outside_the_trial_window_does_not_count(utc):
    records = [_rec(c) for c in acc.ACCEPTANCE_MATRIX if c != "PLN-08.kill_bounded"]
    records.append(_rec("PLN-08.kill_bounded", utc=utc))  # window: 2026-11-01T00:00:00Z + 72 h
    v = acc.run_verdict(records, config=_config())
    assert v["verdict"] == "NOT_ACCEPTED" and v["unmet"] == {"PLN-08.kill_bounded": "MISSING"}
    assert any("outside the trial window" in p for p in v["problems"])


def test_records_at_the_window_edges_count():
    records = [_rec(c, utc="2026-11-01T00:00:00Z") for c in acc.ACCEPTANCE_MATRIX]
    records[0]["utc"] = "2026-11-04T00:00:00Z"
    assert acc.run_verdict(records, config=_config())["verdict"] == "CANDIDATE_FOR_OWNER_ACCEPTANCE"


# -- round 3: validators refuse non-finite or nonsensical measurements --------------------------------------------
@pytest.mark.parametrize("elapsed", [math.nan, "nan", -0.1, math.inf, None, "fast"])
def test_a_non_finite_or_negative_stop_time_never_passes(elapsed):
    status, detail = acc.kill_switch_bounded({**KILL, "elapsed_s": elapsed}, bound_s=30)
    assert status == acc.FAIL, (elapsed, detail)


@pytest.mark.parametrize("fills,fees,reported", [
    ([{**FILLS[0], "price": "NaN"}, FILLS[1]], [], [{"trade_id": "T1", "net_quote": "0.1"}]),
    ([{**FILLS[0], "side": "BUY"}, FILLS[1]], [], [{"trade_id": "T1", "net_quote": "-12.1"}]),
    ([{**FILLS[0], "qty": "-0.0001"}, {**FILLS[1], "qty": "-0.0001"}], [], [{"trade_id": "T1", "net_quote": "-0.1"}]),
    ([FILLS[0], {**FILLS[1], "price": "0"}], [], [{"trade_id": "T1", "net_quote": "-6"}]),
    (FILLS, [{"trade_id": "T1", "fill_id": "f1", "asset": "USDT", "amount": "-1"}], [{"trade_id": "T1", "net_quote": "1.1"}]),
    (FILLS, [], [{"trade_id": "T1", "net_quote": "NaN"}]),
    (FILLS, [], [{"trade_id": "T1", "net_quote": "Infinity"}]),
])
def test_nonsensical_fills_fees_or_reports_fail_and_never_raise(fills, fees, reported):
    out = acc.reconcile_pnl(fills, fees, reported, base_asset="BTC", tolerance_quote=TOL)
    assert out and all(c.status == acc.FAIL for c in out), out


def test_a_trial_window_that_outlives_the_p3_authorization_is_blocked():
    import re
    auth = (REPO_ROOT / acc.P3_EXECUTION_AUTHORIZATION).read_text(encoding="utf-8")
    assert re.findall(r"^EXPIRES_UTC = (\S+)", auth, re.M) == [acc.P3_AUTHORIZATION_EXPIRES_UTC]
    cfg = _config(trial_window__start_utc="2027-01-31T00:00:00Z", trial_window__duration_hours=24)
    r = acc.launch_readiness(cfg)
    assert r["open_owner_decisions"] == ["D2"] and any("expires" in b for b in r["blockers"])
    ok = _config(trial_window__start_utc="2027-01-30T23:59:59Z", trial_window__duration_hours=24)
    assert acc.validate_run_config(ok) == []


def test_the_decision_packet_covers_d1_to_d5_and_chooses_nothing():
    text = (REPO_ROOT / "docs/p3/PLN_10_OWNER_DECISION_PACKET.md").read_text(encoding="utf-8")
    assert "DECISIONS_OPEN = D1, D2, D3, D4, D5" in text and "No value is chosen here" in text
    for did, d in acc.OWNER_DECISIONS.items():
        assert f"## {did} — " in text and f"(`{d['field']}`)" in text and "Validator requires" in text, did
    assert "PAPER_LAUNCH_AUTHORIZED = NO" in text and "REAL_MONEY_AUTHORIZED = NO" in text
    assert acc.P3_AUTHORIZATION_EXPIRES_UTC in text and f"({len(acc.ACCEPTANCE_MATRIX)} today)" in text


def test_every_walkthrough_step_says_what_to_open_pass_fail_and_its_evidence_id():
    text = (REPO_ROOT / "docs/p3/PLN_09_OWNER_ACCEPTANCE_CHECKLIST.md").read_text(encoding="utf-8")
    items = [f"G{i}" for i in range(1, 10)] + [f"S{i}" for i in range(1, 13)] + [f"M{i}" for i in range(1, 10)]
    for item in items:
        row = next(l for l in text.splitlines() if l.startswith(f"| {item} |"))
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert len(cells) == 6 and all(cells[:5]), (item, cells)  # #, Open, PASS when, FAIL when, evidence id, ✓
        assert cells[4] == f"`PLN09-W-{item}`", item
    assert "PLN09-W-ID" in text and "PASS / FAIL per evidence id" in text
    assert "PLN09_OWNER_ACCEPTANCE   = PENDING" in text
