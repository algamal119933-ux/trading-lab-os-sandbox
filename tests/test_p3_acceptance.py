"""P3-PLN-10 acceptance program validators (research/p3/acceptance.py).

Synthetic evidence only. Every validator is fail-closed: missing, malformed, foreign-run, UNPROVEN or
contradictory evidence never yields PASS, and the run verdict is at best a CANDIDATE for the Owner's
acceptance. PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

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
    out = acc.reconcile_pnl(FILLS, fees, [{"trade_id": "T1", "net_quote": "0.0879"}], base_asset="BTC")
    assert out[0].status == acc.PASS and out[0].computed_net_quote == Decimal("0.0879")


def test_a_bnb_fee_is_converted_and_deducted_and_needs_a_price():
    fees = [{"trade_id": "T1", "fill_id": "f1", "asset": "BNB", "amount": "0.00001"}]
    ok = acc.reconcile_pnl(FILLS, fees, [{"trade_id": "T1", "net_quote": "0.094"}], base_asset="BTC",
                           fee_prices={"f1": {"BNB": "600"}})
    assert ok[0].status == acc.PASS  # 0.1 - 0.006
    missing = acc.reconcile_pnl(FILLS, fees, [{"trade_id": "T1", "net_quote": "0.094"}], base_asset="BTC")
    assert missing[0].status == acc.FAIL and "conversion price" in missing[0].detail


def test_a_base_fee_leaves_dust_and_is_not_double_counted():
    fills = [{"trade_id": "T1", "fill_id": "f1", "side": "buy", "qty": "0.0001", "price": "60000"},
             {"trade_id": "T1", "fill_id": "f2", "side": "sell", "qty": "0.0000999", "price": "61000"}]
    fees = [{"trade_id": "T1", "fill_id": "f1", "asset": "BTC", "amount": "0.0000001"}]
    net = Decimal("0.0000999") * 61000 - Decimal("0.0001") * 60000
    out = acc.reconcile_pnl(fills, fees, [{"trade_id": "T1", "net_quote": str(net)}], base_asset="BTC")
    assert out[0].status == acc.PASS
    assert out[0].dust_base == Decimal("0")
    assert out[0].fees_quote == Decimal("0.0000001") * 60000


def test_a_misreported_pnl_fails():
    out = acc.reconcile_pnl(FILLS, [], [{"trade_id": "T1", "net_quote": "0.2"}], base_asset="BTC")
    assert out[0].status == acc.FAIL and "differs" in out[0].detail


@pytest.mark.parametrize("fills,reported,needle", [
    (FILLS + [{"trade_id": "T1", "fill_id": "f2", "side": "sell", "qty": "0.0001", "price": "61000"}],
     [{"trade_id": "T1", "net_quote": "0.1"}], "duplicate fill"),
    ([], [{"trade_id": "T1", "net_quote": "0.1"}], "no fills"),
    (FILLS, [], "without a reported"),
    ([FILLS[0], {**FILLS[1], "qty": "0.0002"}], [{"trade_id": "T1", "net_quote": "0"}], "sold more"),
])
def test_inconsistent_trades_fail_closed(fills, reported, needle):
    out = acc.reconcile_pnl(fills, [], reported, base_asset="BTC")
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
    v = acc.run_verdict(records, run_id="RUN-1")
    assert v["verdict"] == "CANDIDATE_FOR_OWNER_ACCEPTANCE" and v["unmet"] == {}


def test_no_evidence_is_not_accepted():
    v = acc.run_verdict([], run_id="RUN-1")
    assert v["verdict"] == "NOT_ACCEPTED" and len(v["unmet"]) == len(acc.ACCEPTANCE_MATRIX)


def test_evidence_from_another_run_never_counts():
    records = [_rec(cid, run="RUN-0") for cid in acc.ACCEPTANCE_MATRIX]
    assert acc.run_verdict(records, run_id="RUN-1")["verdict"] == "NOT_ACCEPTED"


def test_a_fail_is_never_overwritten_by_a_later_pass_and_unproven_is_not_pass():
    records = [_rec(cid) for cid in acc.ACCEPTANCE_MATRIX]
    records += [_rec("PLN-08.kill_bounded", "FAIL"), _rec("PLN-08.kill_bounded", "PASS")]
    v = acc.run_verdict(records, run_id="RUN-1")
    assert v["unmet"] == {"PLN-08.kill_bounded": "FAIL"}
    records2 = [_rec(cid) for cid in acc.ACCEPTANCE_MATRIX if cid != "PLN-05.host_loss_redundancy"]
    records2.append(_rec("PLN-05.host_loss_redundancy", "UNPROVEN"))
    assert acc.run_verdict(records2, run_id="RUN-1")["unmet"] == {"PLN-05.host_loss_redundancy": "UNPROVEN"}


def test_a_malformed_record_blocks_the_verdict():
    records = [_rec(cid) for cid in acc.ACCEPTANCE_MATRIX] + [_rec("PLN-02.inventory_complete",
                                                                     real_money_authorized=True)]
    v = acc.run_verdict(records, run_id="RUN-1")
    assert v["verdict"] == "NOT_ACCEPTED" and v["problems"]
