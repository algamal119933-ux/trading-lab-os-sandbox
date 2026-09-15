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


def test_all_sixteen_checks_are_reported(report):
    assert [c["id"] for c in report["checks"]] == list(range(1, 17))
    assert [c["check"] for c in report["checks"]] == list(preflight.CHECKS)


def test_every_check_carries_evidence(report):
    for check in report["checks"]:
        assert check["evidence"].strip(), f"check {check['id']} has no evidence"
        assert check["result"] in {"PASS", "FAIL", "UNPROVEN"}


def test_preflight_is_blocked_and_forbids_a_t0(report):
    assert report["preflight"] == "BLOCKED"
    assert report["t0_permitted"] is False
    assert report["blocking_checks"]


def test_every_scaffold_mechanism_reports_its_own_verdict(report):
    """Section 1.3: the scaffold mechanisms are validated even where the check
    itself cannot pass, and each reports that verdict explicitly rather than
    having it inferred from its prose."""
    assert set(report["mechanism_verdicts"]) == set(preflight.MECHANISM_KEYS)
    assert all(v == "PASS" for v in report["mechanism_verdicts"].values())
    assert report["fp_infrastructure_scaffold_validation"] == "PASS"


def test_scaffold_validation_is_not_runtime_readiness(report):
    """The distinction section 1.3 exists to protect."""
    assert report["fp_infrastructure_scaffold_validation"] == "PASS"
    assert report["fp_runtime_readiness"] == "NOT_PROVEN"


def test_synthetic_samples_cannot_satisfy_the_real_data_checks(report):
    """Checks 8 and 12 say *real* data; every candle here is synthetic."""
    for check_id in (8, 12):
        check = report["checks"][check_id - 1]
        assert check["result"] == "UNPROVEN", check
        assert "synthetic" in check["evidence"]
    assert report["details"]["input_sample"] == "synthetic"
    assert report["details"]["replay_sample"] == "synthetic"


def test_the_checks_that_need_no_real_data_do_pass(report):
    """Decision ledger and evidence persistence are fully provable here."""
    for check_id in (9, 15):
        check = report["checks"][check_id - 1]
        assert check["result"] == "PASS", f"check {check_id} did not pass: {check['evidence']}"


def test_the_runtime_checks_are_honestly_unproven(report):
    """Real market-data ingestion, monitoring liveness, duplicate-instance risk,
    clock skew and the full restart drill cannot be observed without a running
    instance, and must not be waved through."""
    for check_id in (6, 11, 13, 14, 16):
        assert report["checks"][check_id - 1]["result"] == "UNPROVEN", check_id


def test_replay_evidence_states_the_bounded_meaning_of_ema_parity(report):
    """Section 14: EMA parity is EMA_IMPLEMENTATION_PARITY and nothing more."""
    evidence = report["checks"][11]["evidence"]
    assert EMA_PARITY_STATUS in evidence
    assert "EMA_IMPLEMENTATION_PARITY = PASS only" in evidence
    for overclaim in ("exchange-input", "strategy-level", "position-state", "execution"):
        assert overclaim in evidence


def test_replay_check_records_its_negative_control(report):
    assert report["details"]["negative_control"] == "detected"
    assert report["details"]["decisions_compared"] == len(preflight.synthetic_candles())


def test_restart_drill_continues_the_chain_without_duplicating(report):
    """Section 17: a restart must not duplicate a decision or lose the chain."""
    check = report["checks"][15]
    assert report["details"]["mechanism_restart"] == "PASS"
    assert "no duplicate decision" in check["evidence"]


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
    # Checks that answer from the repository alone keep their two-value shape.
    for name in (
        "_check_guard",
        "_check_dry_run",
        "_check_spot_mode",
        "_check_no_secret",
        "_check_external_features",
        "_check_db_isolation",
    ):
        # The config-reading checks now take the runtime, so that they read the
        # configuration the instance is actually running under.
        monkeypatch.setattr(preflight, name, lambda runtime=None: ("PASS", "stub"))
    # Checks that may interrogate a live runtime take the runtime and return
    # their own evidence detail alongside the verdict.
    for name in (
        "_check_hashes_match_registry",
        "_check_market_data_ingestion",
        "_check_monitoring",
        "_check_duplicate_instance",
        "_check_clock_tolerance",
    ):
        monkeypatch.setattr(preflight, name, lambda runtime=None: ("PASS", "stub", {}))
    monkeypatch.setattr(preflight, "_check_input_ledger", lambda d: ("PASS", "stub", {"mechanism_input_ledger": "PASS"}))
    monkeypatch.setattr(
        preflight, "_check_decision_ledger", lambda d: ("PASS", "stub", {"mechanism_decision_ledger": "PASS"})
    )
    monkeypatch.setattr(preflight, "_check_replay", lambda d: ("PASS", "stub", {"mechanism_event_time_replay": "PASS"}))
    monkeypatch.setattr(
        preflight, "_check_evidence_persistence", lambda d: ("PASS", "stub", {"mechanism_persistence": "PASS"})
    )
    monkeypatch.setattr(preflight, "_check_restart_drill", lambda d: ("PASS", "stub", {"mechanism_restart": "PASS"}))
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
    result, evidence, _ = preflight._check_duplicate_instance()
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
    assert preflight._check_dry_run()[0] == "FAIL"
    assert preflight._check_spot_mode()[0] == "FAIL"


# -- a live runtime can prove what the scaffold cannot ---------------------


def test_runtime_context_is_absent_by_default():
    """With no runtime the gate must behave exactly as it did before.

    This is the property that keeps the gate honest: running preflight
    somewhere with less evidence available must never make it easier to pass.
    """
    report = preflight.run()
    for check_id in (5, 6, 8, 11, 12, 13, 14, 16):
        assert report["checks"][check_id - 1]["result"] == "UNPROVEN", check_id


def test_empty_runtime_context_changes_nothing():
    runtime = preflight.RuntimeContext()
    assert runtime.has_evidence is False
    assert runtime.client() is None
    report = preflight.run(runtime=runtime)
    for check_id in (5, 6, 8, 11, 12, 13, 14, 16):
        assert report["checks"][check_id - 1]["result"] == "UNPROVEN", check_id


def test_real_input_check_fails_on_synthetic_provenance(tmp_path):
    """Evidence that did not come from the exchange must not satisfy check 8."""
    from fp import ledger as fp_ledger

    ledgers = fp_ledger.open_ledgers(tmp_path, create=True)
    ledgers["input"].append(
        {
            "pair": "BTC/USDT",
            "timeframe": "1h",
            "candle": {"ts": 1, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0},
            "market_event_id": "BTC/USDT|1h|1",
            "source_ts_ms": 1,
            "receive_ts_ms": 2,
            "source_id": "synthetic:not-an-exchange",
        }
    )
    runtime = preflight.RuntimeContext(evidence_dir=tmp_path)
    result, evidence, _ = preflight._check_input_ledger_real(runtime)
    assert result == "FAIL"
    assert "exchange-sourced" in evidence


def test_real_restart_drill_is_unproven_before_a_second_run(tmp_path):
    from fp import ledger as fp_ledger

    ledgers = fp_ledger.open_ledgers(tmp_path, create=True)
    ledgers["incident"].append(
        {"category": "run_started", "full_identity": {"run_id": "a", "restart_counter": 0}}
    )
    runtime = preflight.RuntimeContext(evidence_dir=tmp_path)
    result, evidence, _ = preflight._check_restart_drill_real(runtime)
    assert result == "UNPROVEN"
    assert "1 start" in evidence


def test_real_restart_drill_fails_when_counters_do_not_advance(tmp_path):
    from fp import ledger as fp_ledger

    ledgers = fp_ledger.open_ledgers(tmp_path, create=True)
    for run_id in ("a", "b"):
        ledgers["incident"].append(
            {"category": "run_started", "full_identity": {"run_id": run_id, "restart_counter": 0}}
        )
    runtime = preflight.RuntimeContext(evidence_dir=tmp_path)
    result, evidence, _ = preflight._check_restart_drill_real(runtime)
    assert result == "FAIL"
    assert "not strictly increasing" in evidence


def test_monitoring_check_fails_when_a_probe_is_dead(tmp_path):
    runtime = preflight.RuntimeContext(exporter_url="http://127.0.0.1:9/metrics")
    result, evidence, _ = preflight._check_monitoring(runtime)
    assert result == "FAIL"
    assert "not alive" in evidence
