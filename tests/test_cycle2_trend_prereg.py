"""CYCLE-2 UNIT 7.3 — the Trend/Breakout preregistration, read only.

Nothing here runs a backtest or reads market data: the preregistration, the
strategy source, the ledger record that binds them and the driver's dry-run plan
are checked against what OPENING-1 §2.1/§3 and FUNNEL_LAW_1 require.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from cycle2 import config_n, driver
from trial_ledger import TrialLedger

REPO_ROOT = Path(__file__).resolve().parents[1]
PREREG = REPO_ROOT / "research" / "cycle2" / "prereg" / "TRIAL-C2-TREND-DONCHIAN-1.json"
RECORD = REPO_ROOT / "research" / "trend_breakout" / "PREREGISTRATION.md"
STRATEGY = REPO_ROOT / "research" / "trend_breakout" / "DonchianBreakoutV1.py"
LEDGER = REPO_ROOT / "research" / "records" / "trial_ledger.jsonl"
TRIAL = "TRIAL-C2-TREND-DONCHIAN-1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def prereg() -> dict:
    return driver.load_prereg(PREREG)


def _records(trial_id: str) -> list[dict]:
    return [r.payload for r in TrialLedger(LEDGER) if r.payload.get("trial_id") == trial_id]


def test_the_preregistration_is_a_scientific_trend_trial_in_the_trend_family(prereg):
    assert prereg["trial_class"] == "scientific" and prereg["experiment_id"].startswith("EXP-CYCLE2-SCI-")
    assert prereg["lineage_kind"] == "TREND"
    # OPENING-1 §2.1: inherits the trend family's Cycle-1 count, as a lineage other than H1's
    assert prereg["family_id"] == "BTSL_EMA_REGIME" and prereg["lineage_id"] != "BTSL_EMA_REGIME/L1"
    assert prereg["pair_universe"] == ["BTC/USDT", "ETH/USDT"]
    assert prereg["funnel_law"] == {"record": "research/cycle2/FUNNEL_LAW_1.md",
                                    "sha256": _sha(REPO_ROOT / "research" / "cycle2" / "FUNNEL_LAW_1.md")}


def test_the_grid_is_an_explicit_six_point_enumeration_without_gating(prereg):
    grid = prereg["grid"]
    assert [c["config_id"] for c in grid] == ["E168_X72", "E168_X168", "E336_X72", "E336_X168",
                                             "E480_X72", "E480_X168"]
    for c in grid:
        e, x = (int(v) for v in c["config_id"][1:].split("_X"))
        assert c["params"] == {"buy": {"entry_period": e}, "sell": {"exit_period": x}}
        assert c["regime_gated"] is False


def test_n_is_the_family_configuration_count_not_a_trial_count(prereg):
    n = config_n.family_configuration_n("BTSL_EMA_REGIME", extra_preregs=[prereg])
    assert n["status"] == "EVALUATED" and n["family_configuration_N"] == 15
    assert prereg["multiple_testing"]["effective_trials"] == 15
    assert prereg["multiple_testing"]["dsr_threshold"] == 0.95 and prereg["multiple_testing"]["pbo_threshold"] == 0.05


def test_l4_criterion_is_preregistered_and_reachable(prereg):
    assert prereg["parameter_robustness"] == {"criterion": "GRID_EXCESS_OVER_EXPOSURE_MATCHED",
                                              "min_positive_configs": 4}
    assert "robustness" in prereg["lanes"]
    assert prereg["robustness_window"] == {"start": "20210101", "end": "20241231"}


def test_the_strategy_is_pinned_and_materialised_as_its_only_fixture(prereg):
    assert prereg["strategy"] == {"name": "DonchianBreakoutV1", "file": "research/trend_breakout/DonchianBreakoutV1.py",
                                  "sha256": _sha(STRATEGY)}
    assert prereg["fixture_files"] == [{"path": prereg["strategy"]["file"], "sha256": _sha(STRATEGY)}]


def test_the_strategy_uses_no_moving_average_and_shifts_its_channel():
    tree = ast.parse(STRATEGY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):  # docstrings and comments are not code
        body_nodes = getattr(node, "body", None)
        if isinstance(body_nodes, list) and body_nodes and isinstance(body_nodes[0], ast.Expr) \
                and isinstance(body_nodes[0].value, ast.Constant) and isinstance(body_nodes[0].value.value, str):
            body_nodes.pop(0)
    body = ast.unparse(tree)
    for forbidden in ("ewm", "ema", "EMA", ".mean(", "talib", "ta.", "qtpylib", "shift(-"):
        assert forbidden not in body, forbidden
    assert "rolling(entry).max().shift(1)" in body and "rolling(exit_).min().shift(1)" in body
    assert "can_short = False" in body


def test_the_strategy_parameters_and_warmup_cover_the_grid(prereg):
    tree = ast.parse(STRATEGY.read_text(encoding="utf-8"))
    (cls,) = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    assigns = {t.id: n.value for n in cls.body if isinstance(n, ast.Assign) for t in n.targets
               if isinstance(t, ast.Name)}
    spaces = {}
    for name in ("entry_period", "exit_period"):
        call = assigns[name]
        assert isinstance(call, ast.Call) and call.func.id == "IntParameter"
        low, high = (a.value for a in call.args[:2])
        spaces[name] = ({k.arg: k.value.value for k in call.keywords}["space"], low, high)
    for c in prereg["grid"]:
        for space, values in c["params"].items():
            for name, value in values.items():
                assert spaces[name][0] == space
                assert spaces[name][1] <= value <= spaces[name][2]
    longest = max(v for c in prereg["grid"] for vals in c["params"].values() for v in vals.values())
    assert assigns["startup_candle_count"].value >= longest + 1


def test_the_ledger_binds_this_preregistration_before_any_outcome():
    records = _records(TRIAL)
    assert records, "the trial is not preregistered"
    first = records[0]
    assert first["state"] == "PREREGISTERED" and "outcome" not in first
    ident = first["dataset_identity"]
    assert ident["prereg_file"] == "research/cycle2/prereg/TRIAL-C2-TREND-DONCHIAN-1.json"
    assert ident["prereg_sha256"] == _sha(PREREG)
    assert ident["preregistration_record"] == {"file": "research/trend_breakout/PREREGISTRATION.md",
                                               "sha256": _sha(RECORD)}
    assert first["code_identity"]["sha256"] == _sha(STRATEGY)
    assert ident["family_configuration_N"] == 15 and ident["planned_engine_invocations"] == 22


def test_the_dry_run_plan_fits_the_frozen_caps_or_the_trial_is_closed():
    assert len(driver.build_plan(driver.load_prereg(PREREG))) == 22
    if any(p["state"] != "PREREGISTERED" for p in _records(TRIAL)):
        # once the terminal record exists the trial is never re-run
        with pytest.raises(driver.DriverRefusal, match="never re-run"):
            driver.prepare(PREREG, LEDGER)
        return
    _, _, _, ledger_state, budget = driver.prepare(PREREG, LEDGER)
    assert ledger_state["binding"] == "BOUND" and budget["refusals"] == []
    assert budget["consumed_after"] == {"engine_invocations": 34, "scientific_configurations": 6,
                                        "scientific_trial_ids": 1, "calibration_trial_ids": 2}
