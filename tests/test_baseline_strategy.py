"""BASELINE-1 invariants.

The baseline's value comes from being minimal and frozen. These tests exist so
that "add one more filter" cannot happen quietly: any of them failing means the
strategy is no longer BASELINE-1 and needs a new version number instead.
"""

from __future__ import annotations

import ast
import re

import pytest

STRATEGY_PATH = "freqtrade/user_data/strategies/BaselineEmaRegimeV1.py"


@pytest.fixture(scope="module")
def source(request) -> str:
    return (request.config.rootpath / STRATEGY_PATH).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code_body(source: str) -> str:
    """The strategy source with its module docstring removed.

    The docstring deliberately names every excluded indicator, so scanning the
    whole file for those names would always match.
    """
    tree = ast.parse(source)
    doc = ast.get_docstring(tree, clean=False)
    return source.replace(f'"""{doc}"""', "", 1) if doc else source


@pytest.fixture(scope="module")
def class_body(source: str) -> dict:
    """Class-level constants, resolved without importing talib.

    Values may reference module-level constants (``3 * EMA_SLOW_PERIOD``), so
    those are collected first and used as the only names available.
    """
    tree = ast.parse(source)
    module_consts: dict[str, object] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target = stmt.targets[0]
            if isinstance(target, ast.Name):
                try:
                    module_consts[target.id] = ast.literal_eval(stmt.value)
                except ValueError:
                    pass

    values: dict[str, object] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "BaselineEmaRegimeV1":
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                    target = stmt.targets[0]
                    if not isinstance(target, ast.Name):
                        continue
                    try:
                        values[target.id] = eval(  # noqa: S307 - literal AST, no builtins
                            compile(ast.Expression(stmt.value), "<strategy>", "eval"),
                            {"__builtins__": {}},
                            dict(module_consts),
                        )
                    except Exception:  # noqa: BLE001
                        values[target.id] = "<unresolved>"
    return values


def test_is_spot_long_only(class_body):
    assert class_body["can_short"] is False


def test_runs_on_the_primary_timeframe(class_body):
    assert class_body["timeframe"] == "1h"


def test_no_trailing_stop(class_body):
    assert class_body["trailing_stop"] is False
    assert class_body["use_custom_stoploss"] is False


def test_single_conservative_emergency_stoploss(class_body):
    stoploss = class_body["stoploss"]
    assert isinstance(stoploss, float) and stoploss < 0
    # Wide enough to be a backstop rather than a tuned exit.
    assert stoploss <= -0.15


def test_roi_schedule_is_a_single_non_binding_entry(class_body):
    roi = class_body["minimal_roi"]
    assert list(roi) == ["0"], "a multi-step ROI schedule is not BASELINE-1"
    assert roi["0"] >= 1.0, "ROI must be unreachable so exits come from the signal"


def test_startup_covers_the_slow_ema(class_body):
    assert class_body["startup_candle_count"] >= 3 * 200


@pytest.mark.parametrize(
    ("pattern", "what"),
    [
        (r"\bRSI\b|\brsi\b", "RSI"),
        (r"\bATR\b|\batr\b", "ATR"),
        (r"\bvolume\b", "a volume filter"),
        (r"\bBBANDS\b|bollinger", "Bollinger bands"),
        (r"\bMACD\b|\bmacd\b", "MACD"),
        (r"IntParameter|DecimalParameter|CategoricalParameter|RealParameter", "hyperopt parameters"),
        (r"\bfreqai\b|\bFreqAI\b", "FreqAI"),
        (r"trailing_stop_positive", "trailing-stop tuning"),
    ],
)
def test_baseline_carries_no_extra_machinery(code_body, pattern, what):
    assert not re.search(pattern, code_body), f"BASELINE-1 must not use {what}"


def test_uses_exactly_ema50_and_ema200(source):
    assert "EMA_FAST_PERIOD = 50" in source
    assert "EMA_SLOW_PERIOD = 200" in source
    assert source.count("ta.EMA(") == 2, "exactly two EMAs, nothing else"


def test_entry_and_exit_are_plain_regime_crosses(source, code_body):
    assert 'enter_tag"' in source and "ema_regime_up" in source
    assert 'exit_tag"' in source and "ema_regime_down" in source
    assert "shift(1)" in source, "a cross must compare against the previous closed bar"
    assert "shift(-" not in code_body, "a negative shift would read the future"


def test_no_future_reference_anywhere(code_body):
    for forbidden in ("shift(-", ".iloc[-1]", "look_ahead", "future"):
        assert forbidden not in code_body, f"suspicious future reference: {forbidden}"


def test_strategy_passes_the_paper_guard():
    import paper_guard

    violations = paper_guard.Violations()
    paper_guard.check_strategies(violations)
    assert violations == []


def test_signals_match_a_hand_computed_cross():
    """Runs only where talib is installed (the Freqtrade image and CI's engine job)."""
    pytest.importorskip("talib")
    pandas = pytest.importorskip("pandas")
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("baseline", root / STRATEGY_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # A slow decline followed by a sustained rally forces one down-cross and one
    # up-cross of EMA50 through EMA200.
    closes = [100.0 - i * 0.2 for i in range(600)] + [i * 1.5 for i in range(600)]
    frame = pandas.DataFrame(
        {
            "date": pandas.date_range("2021-01-01", periods=len(closes), freq="1h", tz="UTC"),
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [1.0] * len(closes),
        }
    )
    strategy = module.BaselineEmaRegimeV1({})
    frame = strategy.populate_indicators(frame, {"pair": "BTC/USDT"})
    frame = strategy.populate_entry_trend(frame, {"pair": "BTC/USDT"})
    frame = strategy.populate_exit_trend(frame, {"pair": "BTC/USDT"})

    fast, slow = frame["ema_fast"], frame["ema_slow"]
    expected_entries = ((fast > slow) & (fast.shift(1) <= slow.shift(1))).sum()
    assert frame["enter_long"].fillna(0).sum() == expected_entries
    assert expected_entries >= 1, "the fixture must actually produce a cross"
