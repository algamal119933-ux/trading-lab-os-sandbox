"""Event-time replay reference (FP-BOOT-1 sections 9, 10).

Replay is the primary parity gate, so the tests that matter are the ones that
prove it can *fail*: a gate that only ever agrees with the runtime proves
nothing about the runtime.
"""

from __future__ import annotations

import pytest

from fp.ledger import Ledger
from fp.replay import (
    ACTION_ENTER_LONG,
    ACTION_EXIT_LONG,
    ACTION_HOLD,
    SIGNAL_FLAT,
    SIGNAL_LONG,
    SOURCE_REVISION_DRIFT,
    ReplayError,
    canonical_later_diagnostic,
    derive_decisions,
    ema,
    ema_parity_vectors,
    event_time_replay,
    strategy_constants,
)
from fp.preflight import synthetic_candles

PAIR = "BTC/USDT"


# -- EMA ------------------------------------------------------------------


def test_ema_follows_talib_seeding_convention():
    """Undefined before period-1, SMA seed at period-1, recursive after."""
    values = [float(v) for v in range(1, 11)]
    out = ema(values, 5)
    assert out[:4] == [None] * 4
    assert out[4] == pytest.approx(3.0)  # mean(1..5)
    assert out[5] == pytest.approx(3.0 + (2 / 6) * (6.0 - 3.0))


def test_ema_is_undefined_when_the_series_is_shorter_than_the_period():
    assert ema([1.0, 2.0], 5) == [None, None]


def test_ema_rejects_a_nonsensical_period():
    with pytest.raises(ReplayError):
        ema([1.0], 0)


def test_ema_parity_vectors_are_deterministic_and_long_enough():
    """CI feeds these to TA-Lib; they must be reproducible and exercise EMA200."""
    first = ema_parity_vectors()["close"]
    assert first == ema_parity_vectors()["close"]
    assert len(first) >= 3 * strategy_constants()["EMA_SLOW_PERIOD"]


# -- parameters are bound to the frozen strategy --------------------------


def test_constants_are_read_from_the_strategy_not_copied():
    constants = strategy_constants()
    assert constants["EMA_FAST_PERIOD"] == 50
    assert constants["EMA_SLOW_PERIOD"] == 200


def test_constants_track_an_edited_strategy(tmp_path):
    """If the strategy's periods move, the replay reference must move with them."""
    source = tmp_path / "Edited.py"
    source.write_text("EMA_FAST_PERIOD = 9\nEMA_SLOW_PERIOD = 21\n", encoding="utf-8")
    assert strategy_constants(source) == {"EMA_FAST_PERIOD": 9, "EMA_SLOW_PERIOD": 21}


def test_missing_constant_is_an_error(tmp_path):
    source = tmp_path / "Broken.py"
    source.write_text("EMA_FAST_PERIOD = 9\n", encoding="utf-8")
    with pytest.raises(ReplayError):
        strategy_constants(source)


# -- decision derivation --------------------------------------------------


def test_derived_decisions_mirror_the_baseline_cross_rules():
    decisions = derive_decisions(synthetic_candles(), PAIR)
    actions = [d.intended_action for d in decisions if d.intended_action != ACTION_HOLD]
    assert ACTION_ENTER_LONG in actions
    # An entry is never immediately followed by another entry: state is tracked.
    assert all(a != b for a, b in zip(actions, actions[1:]))
    for decision in decisions:
        if decision.intended_action == ACTION_ENTER_LONG:
            assert decision.signal_state == SIGNAL_LONG
        if decision.intended_action == ACTION_EXIT_LONG:
            assert decision.signal_state == SIGNAL_FLAT


def test_early_bars_report_unconverged_indicators():
    decisions = derive_decisions(synthetic_candles(), PAIR)
    slow = strategy_constants()["EMA_SLOW_PERIOD"]
    assert decisions[0].no_action_reason == "indicators_not_converged"
    assert decisions[slow - 2].no_action_reason == "indicators_not_converged"
    assert all(d.intended_action == ACTION_HOLD for d in decisions[: slow - 1])


def test_derivation_uses_only_the_current_and_previous_bar():
    """Truncating the future must not change any past decision (no lookahead)."""
    candles = synthetic_candles()
    full = derive_decisions(candles, PAIR)
    truncated = derive_decisions(candles[:450], PAIR)
    assert [d.intended_action for d in truncated] == [d.intended_action for d in full[:450]]


def test_out_of_order_candles_are_refused():
    candles = synthetic_candles(300)
    candles[100], candles[101] = candles[101], candles[100]
    with pytest.raises(ReplayError):
        derive_decisions(candles, PAIR)


def test_duplicate_candles_are_refused():
    candles = synthetic_candles(300)
    candles[100] = dict(candles[99])
    with pytest.raises(ReplayError):
        derive_decisions(candles, PAIR)


# -- replay comparison ----------------------------------------------------


@pytest.fixture
def captured(tmp_path):
    """A faithful runtime: inputs captured, decisions recorded from them."""
    inputs = Ledger(tmp_path / "paper_input_ledger.jsonl", "input")
    decisions = Ledger(tmp_path / "paper_decision_ledger.jsonl", "decision")
    candles = synthetic_candles()
    inputs.extend(
        [{"pair": PAIR, "timeframe": "1h", "candle": candle, "source_id": "test"} for candle in candles]
    )
    decisions.extend(
        [
            {
                "pair": PAIR,
                "candle_ts": decision.candle_ts,
                "signal_state": decision.signal_state,
                "intended_action": decision.intended_action,
            }
            for decision in derive_decisions(candles, PAIR)
        ]
    )
    return inputs, decisions, candles


def test_faithful_runtime_replays_clean(captured):
    inputs, decisions, candles = captured
    report = event_time_replay(inputs.records(), decisions.records(), PAIR)
    assert report["status"] == "PASS"
    assert report["mismatch_count"] == 0
    assert report["decisions_compared"] == len(candles)


def test_a_single_flipped_action_is_caught(captured):
    inputs, decisions, _ = captured
    records = decisions.records()
    for index, record in enumerate(records):
        if record.payload["intended_action"] == ACTION_ENTER_LONG:
            record.payload["intended_action"] = ACTION_HOLD
            break
    else:  # pragma: no cover - the fixture always produces an entry
        pytest.fail("fixture produced no entry signal")

    report = event_time_replay(inputs.records(), records, PAIR)
    assert report["status"] == "FAIL"
    assert report["mismatch_count"] == 1
    assert report["classification"] == "DECISION_MISMATCH"


def test_a_decision_without_a_captured_input_is_caught(captured):
    """A decision the runtime cannot show an input for is not evidence."""
    inputs, decisions, _ = captured
    records = decisions.records()
    records[-1].payload["candle_ts"] = 1
    report = event_time_replay(inputs.records(), records, PAIR)
    assert report["status"] == "FAIL"
    assert report["decisions_without_captured_input"] == [1]


def test_other_pairs_are_ignored(captured):
    inputs, decisions, _ = captured
    inputs.append({"pair": "ETH/USDT", "candle": {"ts": 1, "close": 1.0}})
    report = event_time_replay(inputs.records(), decisions.records(), PAIR)
    assert report["status"] == "PASS"


def test_errata_do_not_enter_the_replay(captured):
    inputs, decisions, _ = captured
    decisions.append_erratum(0, "note", {"anything": True})
    report = event_time_replay(inputs.records(), decisions.records(), PAIR)
    assert report["status"] == "PASS"


# -- canonical-later diagnostic (section 9.2) -----------------------------


def test_upstream_revision_is_classified_as_source_revision_drift(captured):
    """Event-time replay passed, so a later disagreement is the source's doing."""
    inputs, _, candles = captured
    later = [dict(c) for c in candles]
    later[300]["close"] = later[300]["close"] + 1.0
    report = canonical_later_diagnostic(inputs.records(), later, PAIR, event_time_status="PASS")
    assert report["classification"] == SOURCE_REVISION_DRIFT
    assert report["revision_count"] == 1
    assert report["revised_candles"][0]["fields"]["close"]["canonical_later"] == later[300]["close"]


def test_no_revision_is_reported_when_the_archive_agrees(captured):
    inputs, _, candles = captured
    report = canonical_later_diagnostic(inputs.records(), candles, PAIR, event_time_status="PASS")
    assert report["classification"] == "NO_REVISION"
    assert report["revision_count"] == 0


def test_revision_is_not_used_to_excuse_a_failed_parity_gate(captured):
    """A revision must never launder a real decision mismatch into a data excuse."""
    inputs, _, candles = captured
    later = [dict(c) for c in candles]
    later[300]["close"] += 1.0
    report = canonical_later_diagnostic(inputs.records(), later, PAIR, event_time_status="FAIL")
    assert report["classification"] == "DECISION_MISMATCH"
