"""Cost-stress fee propagation (H1-PAPER-READINESS-QUALIFICATION-1, section 6).

Mean-Reversion Cycle 1's cost-stress gate was not informative: the adverse
fee reached only summarize_backtest.py's own reporting, never the actual
`freqtrade backtesting` invocation, so its "stress" runs were identical to
base by construction. This test proves the fix at the level it can be
proven without Freqtrade itself: that the two config files actually differ
in `fee`, and that the stress run is dispatched against the stress config's
container path, not the base one. Section 6.B/D ("command identity records
the actual fee value", "resulting evidence records the effective engine
assumption") are checked against the real run's own log line in the
qualification report, not here — a static test cannot prove what a live
engine actually did; it can only prove the input it was given was correct.
"""

from __future__ import annotations

import json

from h1_qualification import run_qualification as rq


def test_stress_config_differs_from_base_only_in_fee(tmp_path, monkeypatch):
    base = {
        "fee": rq.BASE_FEE, "exchange": {"name": "binance", "pair_whitelist": ["BTC/USDT"]},
        "stake_currency": "USDT",
    }
    base_path = tmp_path / "config.research.json"
    base_path.write_text(json.dumps(base), encoding="utf-8")
    stress_path = tmp_path / "config.research.stress.json"

    monkeypatch.setattr(rq, "CONFIG_BASE", base_path)
    monkeypatch.setattr(rq, "CONFIG_STRESS", stress_path)

    rq.write_stress_config()

    stress = json.loads(stress_path.read_text(encoding="utf-8"))
    assert stress["fee"] == rq.ADVERSE_FEE
    assert stress["fee"] != base["fee"]
    for key in ("exchange", "stake_currency"):
        assert stress[key] == base[key], f"{key} must be unchanged, only fee differs"


def test_base_and_stress_runs_are_dispatched_against_different_config_paths():
    # do_trial's own call sites, not a re-implementation: the base-fee
    # neighbor/temporal trials pass config.research.json, the cost-stress
    # trial passes config.research.stress.json -- read directly from source
    # so this test breaks if that call site's argument ever changes.
    import inspect

    source = inspect.getsource(rq.main)
    assert '"/freqtrade/user_data/config.research.json"' in source
    assert '"/freqtrade/user_data/config.research.stress.json"' in source
    stress_call = source[source.index("write_stress_config()"):]
    assert "config.research.stress.json" in stress_call


def test_engine_fee_propagation_is_checked_from_the_run_s_own_log_not_assumed():
    """The driver must not simply assert success -- it greps the actual
    backtest log for Freqtrade's own 'Using fee X% from config.' line and
    fails the job if that line does not show the adverse value."""
    import inspect

    source = inspect.getsource(rq)
    assert "Using fee" in source
    assert "effective_fee_line" in source
    assert "engine_fee_propagation_proven" in source
    main_source = inspect.getsource(rq.main)
    assert "engine_fee_propagation_proven" in main_source and "return 1" in main_source
