"""Exposure and metric normalisation.

Freqtrade does not report capital exposure, and for a long-only strategy that
sits in cash most of the time the exposure numbers decide whether a headline
return means anything. These tests pin the arithmetic down on trades whose
answer can be worked out by hand.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import summarize_backtest as sb

START = datetime(2021, 1, 1, tzinfo=timezone.utc)
END = datetime(2021, 1, 11, tzinfo=timezone.utc)  # exactly 10 days


def trade(open_day: int, close_day: int, stake: float = 10.0, profit: float = 1.0) -> dict:
    return {
        "open_date": f"2021-01-{1 + open_day:02d}T00:00:00+00:00",
        "close_date": f"2021-01-{1 + close_day:02d}T00:00:00+00:00",
        "stake_amount": stake,
        "profit_abs": profit,
        "pair": "BTC/USDT",
    }


def test_parse_time_handles_iso_seconds_and_milliseconds():
    assert sb.parse_time("2021-01-01T00:00:00Z") == START
    assert sb.parse_time("2021-01-01T00:00:00+00:00") == START
    assert sb.parse_time(START.timestamp()) == START
    assert sb.parse_time(START.timestamp() * 1000) == START
    assert sb.parse_time(None) is None


def test_first_not_none_keeps_a_legitimate_zero():
    assert sb.first_not_none(None, 0.0, 5.0) == 0.0
    assert sb.first_not_none(None, None) is None


def test_exposure_of_a_single_half_window_trade():
    """One 10 USDT trade open for 5 of 10 days on a 100 USDT wallet."""
    profile = sb.exposure_profile([trade(0, 5)], START, END, wallet=100.0)
    assert profile["time_exposure_pct"] == pytest.approx(50.0)
    assert profile["avg_capital_exposure_pct"] == pytest.approx(5.0)
    assert profile["peak_capital_exposure_pct"] == pytest.approx(10.0)
    assert profile["peak_concurrent_trades"] == 1


def test_overlapping_trades_raise_peak_but_time_in_market_is_a_union():
    trades = [trade(0, 6), trade(2, 8)]
    profile = sb.exposure_profile(trades, START, END, wallet=100.0)
    # Union of [0,6] and [2,8] is [0,8] = 8 of 10 days.
    assert profile["time_exposure_pct"] == pytest.approx(80.0)
    assert profile["peak_capital_exposure_pct"] == pytest.approx(20.0)
    assert profile["peak_concurrent_trades"] == 2
    # 10 USDT for 6 days + 10 USDT for 6 days = 120 stake-days over 10 days.
    assert profile["avg_capital_exposure_pct"] == pytest.approx(12.0)


def test_a_trade_still_open_at_the_window_end_is_clipped():
    profile = sb.exposure_profile(
        [{"open_date": "2021-01-06T00:00:00Z", "close_date": None, "stake_amount": 10.0}],
        START,
        END,
        wallet=100.0,
    )
    assert profile["time_exposure_pct"] == pytest.approx(50.0)


def test_no_trades_means_no_exposure():
    profile = sb.exposure_profile([], START, END, wallet=100.0)
    assert profile["time_exposure_pct"] == 0.0
    assert profile["avg_capital_exposure_pct"] == 0.0


def test_trade_derived_stats_counts_streaks_and_fees():
    trades = [
        trade(0, 1, profit=5.0),
        trade(1, 2, profit=-1.0),
        trade(2, 3, profit=-2.0),
        trade(3, 4, profit=-3.0),
        trade(4, 5, profit=4.0),
    ]
    stats = sb.trade_derived_stats(trades, fee=0.001)
    assert stats["trade_count"] == 5
    assert stats["winning_trades"] == 2
    assert stats["losing_trades"] == 3
    assert stats["max_consecutive_losses"] == 3
    assert stats["win_rate_pct"] == pytest.approx(40.0)
    assert stats["profit_factor"] == pytest.approx(9.0 / 6.0)
    # 5 trades x 10 stake = 50 entry notional, doubled for the round trip.
    assert stats["turnover_stake"] == pytest.approx(100.0)
    assert stats["total_fees_stake"] == pytest.approx(2 * 0.001 * 50.0)


def test_explicit_fee_fields_win_over_the_derived_estimate():
    trades = [{**trade(0, 1), "fee_open_cost": 0.02, "fee_close_cost": 0.03}]
    stats = sb.trade_derived_stats(trades, fee=0.001)
    assert stats["total_fees_stake"] == pytest.approx(0.05)
    assert "per-trade fee fields" in stats["fees_note"]


def write_result(tmp_path, block: dict, name: str = "result.json"):
    path = tmp_path / name
    path.write_text(json.dumps({"strategy": {"BaselineEmaRegimeV1": block}}), encoding="utf-8")
    return path


def test_build_normalises_engine_keys_and_derives_exposure(tmp_path):
    result = write_result(
        tmp_path,
        {
            "profit_total": -0.12,
            "max_drawdown_account": 0.2,
            "sharpe": -0.4,
            "sortino": -0.5,
            "calmar": -0.3,
            "winrate": 0.4,
            "total_trades": 1,
            "results_per_pair": [
                {"key": "BTC/USDT", "profit_total_pct": -8.0},
                {"key": "ETH/USDT", "profit_total_pct": -4.0},
                {"key": "TOTAL", "profit_total_pct": -12.0},
            ],
            "trades": [trade(0, 5)],
        },
    )
    passive = tmp_path / "passive.json"
    passive.write_text(
        json.dumps({"result": {"full_50_50_return": -0.4, "exposure_matched_return": -0.08}}),
        encoding="utf-8",
    )

    args = sb.argparse.Namespace(
        result=str(result), trades=None,
        window_start="2021-01-01T00:00:00Z", window_end="2021-01-11T00:00:00Z",
        wallet=100.0, fee=0.001, passive=str(passive),
    )
    metrics = sb.build(args)

    assert metrics["strategy"] == "BaselineEmaRegimeV1"
    assert metrics["total_return_pct"] == pytest.approx(-12.0)
    assert metrics["max_drawdown_pct"] == pytest.approx(20.0)
    assert metrics["win_rate_pct"] == pytest.approx(40.0)
    assert metrics["per_pair_return_pct"] == {"BTC/USDT": -8.0, "ETH/USDT": -4.0}
    assert metrics["avg_capital_exposure_pct"] == pytest.approx(5.0)
    # -12% earned on 5% average capital exposure.
    assert metrics["return_per_exposure_unit"] == pytest.approx(-240.0)
    # 50/50 passive lost 40%; scaled to 5% realised exposure that is -2%.
    assert metrics["passive_realised_exposure_matched_return_pct"] == pytest.approx(-2.0)
    assert metrics["passive_max_exposure_matched_return_pct"] == pytest.approx(-8.0)


def test_markdown_renders_every_metric(tmp_path):
    metrics = {"strategy": "S", "window_start_utc": "a", "window_end_utc": "b",
               "total_return_pct": 1.5, "per_pair_return_pct": {"BTC/USDT": 1.0}, "missing": None}
    markdown = sb.to_markdown(metrics)
    assert "total_return_pct" in markdown and "1.5" in markdown
    assert "BTC/USDT=1" in markdown
    assert "| missing | — |" in markdown
