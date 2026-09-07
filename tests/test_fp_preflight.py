"""FP-BOOT-1 preflight gate (specification section 12).

"No candidate T0 before preflight PASS." The tests below check both directions:
that the gate blocks while the environment cannot prove the checks, and that it
is capable of passing — a gate hard-wired to BLOCKED would satisfy every
"blocked" assertion while proving nothing.
"""

from __future__ import annotations

import pytest

from fp import preflight
from fp.ledger import Ledger
from fp.replay import EMA_PARITY_STATUS, derive_decisions, strategy_constants


@pytest.fixture(scope="module")
def report() -> dict:
    return preflight.run()


# -- the synthetic sample -------------------------------------------------


def test_synthetic_sample_is_deterministic():
    assert preflight.synthetic_candles() == preflight.synthetic_candles()


def test_synthetic_sample_is_long_enough_to_converge_ema200():
    candles = preflight.synthetic_candles()
    assert len(candles) > 3 * strategy_constants()["EMA_SLOW_PERIOD"]


def test_synthetic_sample_actually_produces_a_cross():
    """A sample with no cross would let the replay negative control pass vacuously."""
    actions = {d.intended_action for d in derive_decisions(preflight.synthetic_candles(), "BTC/USDT")}
    assert "enter_long" in actions


def test_synthetic_candles_are_ordered_and_ohlc_valid():
    candles = preflight.synthetic_candles()
    assert [c["ts"] for c in candles] == sorted(c["ts"] for c in candles)
    for candle in candles:
        assert candle["low"] <= min(candle["open"], candle["close"])
        assert candle["high"] >= max(candle["open"], candle["close"])


# -- the report -----------------------------------------------------------


def test_all_twelve_checks_are_reported(report):
    assert [c["id"] for c in report["checks"]] == list(range(1, 13))
    assert [c["check"] for c in report["checks"]] == list(preflight.CHECKS)


def test_every_check_carries_evidence(report):
    for check in report["checks"]:
        assert check["evidence"].strip(), f"check {check['id']} has no evidence"
        assert check["result"] in {"PASS", "FAIL", "UNPROVEN"}


def test_preflight_is_blocked_and_forbids_a_t0(report):
    assert report["preflight"] == "BLOCKED"
    assert report["t0_permitted"] is False
    assert report["blocking_checks"]


def test_the_executable_checks_actually_pass(report):
    """Checks 7, 8 and 11 are executed here, so they must not be UNPROVEN."""
    executed = {7: "paper_input_ledger", 8: "paper_decision_ledger", 11: "event-time replay"}
    for check_id, label in executed.items():
        check = report["checks"][check_id - 1]
        assert check["result"] == "PASS", f"{label} did not pass: {check['evidence']}"


def test_the_runtime_checks_are_honestly_unproven(report):
    """Market-data ingestion, monitoring liveness and duplicate-instance risk
    cannot be observed without a running instance, and must not be waved through."""
    for check_id in (5, 10, 12):
        assert report["checks"][check_id - 1]["result"] == "UNPROVEN"


def test_replay_evidence_states_the_ema_parity_status(report):
    assert EMA_PARITY_STATUS in report["checks"][10]["evidence"]


def test_replay_check_records_its_negative_control(report):
    assert report["details"]["negative_control"] == "detected"
    assert report["details"]["decisions_compared"] == len(preflight.synthetic_candles())


def test_real_money_is_never_authorized(report):
    assert report["real_money_authorized"] is False


def test_require_pass_exits_non_zero_while_blocked(capsys):
    assert preflight.main(["--require-pass", "--json"]) == 2
    assert "PREFLIGHT_BLOCKED" in capsys.readouterr().err


def test_report_without_require_pass_exits_zero():
    assert preflight.main([]) == 0


# -- the gate can pass ----------------------------------------------------


def test_preflight_passes_when_every_check_passes(monkeypatch):
    """Otherwise a permanently-BLOCKED gate would satisfy every test above."""
    for name in (
        "_check_guard",
        "_check_spot_dry_run",
        "_check_no_secret",
        "_check_hashes_match_registry",
        "_check_market_data_ingestion",
        "_check_external_features",
        "_check_db_isolation",
        "_check_monitoring",
        "_check_duplicate_instance",
    ):
        monkeypatch.setattr(preflight, name, lambda: ("PASS", "stub"))
    result = preflight.run()
    assert result["preflight"] == "PASS"
    assert result["t0_permitted"] is True
    assert result["blocking_checks"] == []


# -- the executed checks detect real faults -------------------------------


def test_input_ledger_check_fails_on_a_broken_chain(tmp_path, monkeypatch):
    """The check must be sensitive to the fault it claims to detect."""
    monkeypatch.setattr(Ledger, "verify", lambda self: ["injected chain break"])
    result, evidence, _ = preflight._check_input_ledger(tmp_path)
    assert result == "FAIL"
    assert "injected chain break" in evidence


def test_db_isolation_check_fails_on_colliding_paths(tmp_path, monkeypatch):
    import json

    registry = {
        "paper_alpha_cohort": "test",
        "instances": [
            {"role": "FP-CANDIDATE-A", "runtime_identity": {"db_path": "same.sqlite", "bot_name": "a"}},
            {"role": "FP-CANDIDATE-B", "runtime_identity": {"db_path": "same.sqlite", "bot_name": "b"}},
        ],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    monkeypatch.setattr(preflight, "COHORT_REGISTRY", path)
    result, evidence = preflight._check_db_isolation()
    assert result == "FAIL"
    assert "db_path" in evidence


def test_duplicate_instance_check_fails_on_two_running_instances(tmp_path, monkeypatch):
    import json

    registry = {
        "instances": [
            {"role": "FP-CANDIDATE-A", "status": "RUNNING", "runtime_identity": {}},
            {"role": "FP-CANDIDATE-A", "status": "RUNNING", "runtime_identity": {}},
        ]
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    monkeypatch.setattr(preflight, "COHORT_REGISTRY", path)
    result, evidence = preflight._check_duplicate_instance()
    assert result == "FAIL"
    assert "share a role" in evidence


def test_guard_check_fails_on_an_unsafe_config(tmp_path, monkeypatch):
    import json

    config = json.loads(preflight.EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    config["dry_run"] = False
    config["trading_mode"] = "futures"
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(preflight, "EXAMPLE_CONFIG", path)

    assert preflight._check_guard()[0] == "FAIL"
    assert preflight._check_spot_dry_run()[0] == "FAIL"
