"""COMMERCIAL-VERIFICATION-LANE-1 — trade-history statistics, Monte Carlo and the CLI.

Every input is synthetic and built inside tmp_path; no client file exists here.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from verification import monte_carlo, trade_check, trade_stats

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _write_csv(path: Path, rows: list[tuple[str, float]], header=("close_date", "profit_ratio")) -> Path:
    path.write_text(",".join(header) + "\n" + "".join(f"{t},{r}\n" for t, r in rows), encoding="utf-8")
    return path


def _trades(returns: list[float], step_days: float = 3.0) -> list[trade_stats.Trade]:
    return [trade_stats.Trade(T0 + timedelta(days=i * step_days), r) for i, r in enumerate(returns)]


def test_freqtrade_ratio_and_percent_columns_parse_to_the_same_trades(tmp_path):
    rows = [((T0 + timedelta(days=i)).isoformat(), r) for i, r in enumerate([0.02, -0.01, 0.03])]
    ratio = trade_stats.load_trades(_write_csv(tmp_path / "a.csv", rows))
    pct = trade_stats.load_trades(_write_csv(tmp_path / "b.csv", [(t, r * 100) for t, r in rows],
                                             header=("Exit_Time", "Return_Pct")))
    assert [t.ret for t in ratio] == pytest.approx([t.ret for t in pct])


def test_trades_are_sorted_by_close_time_and_epoch_ms_is_accepted(tmp_path):
    ms = int((T0 + timedelta(days=5)).timestamp() * 1000)
    path = _write_csv(tmp_path / "t.csv", [(str(ms), 0.05), (T0.isoformat(), -0.02)])
    trades = trade_stats.load_trades(path)
    assert [t.ret for t in trades] == [-0.02, 0.05]


@pytest.mark.parametrize("body, message", [
    ("", "no header row"),
    ("pair,profit_ratio\nBTC,0.1\n", "close-time"),
    ("close_date,pair\n2024-01-01,BTC\n", "return column"),
    ("close_date,profit_ratio\n", "no trades"),
    ("close_date,profit_ratio\n2024-01-01,-1.5\n", "not a possible trade return"),
    ("close_date,profit_ratio\nyesterday,0.1\n", "line 2"),
])
def test_input_contract_violations_are_rejected(tmp_path, body, message):
    path = tmp_path / "bad.csv"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(trade_stats.TradeFileError, match=message):
        trade_stats.load_trades(path)


def test_summary_numbers_on_a_hand_checked_series():
    s = trade_stats.summarize(_trades([0.10, -0.05, 0.10, -0.05, -0.05]))
    assert s["trades"] == 5
    assert s["win_rate"] == pytest.approx(0.4)
    assert s["profit_factor"] == pytest.approx(0.20 / 0.15)
    assert s["expectancy_per_trade"] == pytest.approx(0.01)
    assert s["total_return"] == pytest.approx(1.1 * 0.95 * 1.1 * 0.95 * 0.95 - 1)
    # peak 1.1*0.95*1.1 = 1.1495, then two -5% trades
    assert s["max_drawdown"] == pytest.approx(1 - 0.95 ** 2)
    assert (s["longest_win_streak"], s["longest_loss_streak"]) == (1, 2)


def test_fraction_scales_the_equity_curve_not_the_trade_statistics():
    full = trade_stats.summarize(_trades([0.10, -0.05] * 20), fraction=1.0)
    tenth = trade_stats.summarize(_trades([0.10, -0.05] * 20), fraction=0.1)
    assert tenth["profit_factor"] == full["profit_factor"]
    assert tenth["max_drawdown"] < full["max_drawdown"]
    with pytest.raises(ValueError):
        trade_stats.summarize(_trades([0.1]), fraction=0)


def test_a_clean_record_has_no_red_flags():
    returns = ([0.03, -0.015, 0.02, -0.01, 0.025, -0.02] * 10)
    s = trade_stats.summarize(_trades(returns, step_days=7))
    assert s["red_flags"] == [] and s["verdict"] == "NO_RED_FLAGS_FOUND"


@pytest.mark.parametrize("returns, step, flag", [
    ([0.01, -0.005] * 5, 3, "FEW_TRADES"),
    ([0.01, -0.02] * 20, 3, "NON_POSITIVE_EXPECTANCY"),
    ([2.0] + [0.001, -0.001] * 20, 3, "CONCENTRATION"),
    ([0.05, 0.05, 0.05, -0.01] * 10, 3, "TOO_GOOD"),
    ([0.01] * 40, 3, "NO_LOSING_TRADES"),
    ([0.01] * 38 + [-0.05, -0.05], 3, "MARTINGALE_SHAPE"),
    ([0.02, 0.02, 0.02, -0.01] * 13, 8, "FLAWLESS_MONTHS"),
])
def test_each_red_flag_fires_on_its_shape(returns, step, flag):
    s = trade_stats.summarize(_trades(returns, step_days=step))
    assert any(f.startswith(flag) for f in s["red_flags"]), s["red_flags"]
    assert s["verdict"] == "RED_FLAGS"


def test_monte_carlo_is_deterministic_for_a_seed():
    returns = [0.03, -0.02, 0.01, -0.01, 0.04, -0.03] * 5
    a = monte_carlo.simulate(returns, paths=500, seed=7)
    b = monte_carlo.simulate(returns, paths=500, seed=7)
    c = monte_carlo.simulate(returns, paths=500, seed=8)
    assert a == b and a != c
    assert a["return_p5"] <= a["return_p50"] <= a["return_p95"]
    assert a["max_drawdown_p50"] <= a["max_drawdown_p95"]


def test_monte_carlo_extremes():
    assert monte_carlo.simulate([-0.2] * 10, paths=100)["risk_of_ruin"] == 1.0
    winners = monte_carlo.simulate([0.01] * 10, paths=100)
    assert winners["risk_of_ruin"] == 0.0 and winners["probability_of_loss"] == 0.0
    assert monte_carlo.simulate([-0.2] * 10, paths=100, fraction=0.1)["risk_of_ruin"] == 0.0


@pytest.mark.parametrize("kwargs", [{"fraction": 0}, {"paths": 10}, {"ruin_drawdown": 1.0}])
def test_monte_carlo_refuses_bad_parameters(kwargs):
    with pytest.raises(ValueError):
        monte_carlo.simulate([0.01, -0.01], **kwargs)


def test_cli_writes_report_outside_a_checkout_and_refuses_inside(tmp_path, monkeypatch):
    rows = [((T0 + timedelta(days=7 * i)).isoformat(), r)
            for i, r in enumerate([0.03, -0.015, 0.02, -0.01, 0.025, -0.02] * 10)]
    csv_path = _write_csv(tmp_path / "trades.csv", rows)
    out = tmp_path / "out"
    monkeypatch.setattr(trade_check, "_inside_git_checkout", lambda p: False)
    assert trade_check.main([str(csv_path), "--out-dir", str(out), "--paths", "200"]) == 0
    report = json.loads((out / "trade_check.json").read_text(encoding="utf-8"))
    assert report["stats"]["verdict"] == "NO_RED_FLAGS_FOUND"
    assert report["stats"]["verdict"] != "PASS"
    assert "not a pass" in (out / "trade_check.md").read_text(encoding="utf-8")

    monkeypatch.setattr(trade_check, "_inside_git_checkout", lambda p: True)
    assert trade_check.main([str(csv_path), "--out-dir", str(tmp_path / "x"), "--paths", "200"]) == 2
    assert not (tmp_path / "x").exists()


def test_cli_inside_this_repository_is_refused_for_real():
    repo = Path(__file__).resolve().parents[1]
    assert trade_check._inside_git_checkout(repo / "nonexistent-output-dir") is True
