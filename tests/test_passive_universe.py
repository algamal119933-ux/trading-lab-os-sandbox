"""Single-asset passive controls (sprint fair-controls requirement).

A BTC-specialist candidate must be compared against BTC's own buy-and-hold and
BTC's own exposure-matched passive line. The frozen sprint is explicit that a
combined BTC+ETH control is not a fair sole opponent for one.

The load-bearing test here is the *negative* one: the two-asset default must
still produce exactly what it produced before, because BASELINE-1's recorded
Development and Validation numbers came out of this function and must not move.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "freqtrade" / "user_data"))

PERIODS = {"development": ("2021-01-01T00:00:00Z", "2021-01-03T00:00:00Z")}


@pytest.fixture(scope="module")
def module():
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    import baseline_benchmarks

    return baseline_benchmarks


def frame(pd, prices: list[float]):
    return pd.DataFrame(
        {
            "date": pd.date_range("2021-01-01", periods=len(prices), freq="1h", tz="UTC"),
            "open": prices,
            "high": [p * 1.001 for p in prices],
            "low": [p * 0.999 for p in prices],
            "close": prices,
            "volume": [1.0] * len(prices),
        }
    )


def test_two_asset_default_is_unchanged(module):
    """BASELINE-1's control line must be reproduced by the same arithmetic."""
    pd = pytest.importorskip("pandas")
    btc = frame(pd, [100.0] * 24 + [110.0] * 25)   # +10%
    eth = frame(pd, [100.0] * 24 + [90.0] * 25)    # -10%

    result = module.compute_period("development", btc, eth, 0.0, PERIODS,
                                   wallet=100.0, stake=10.0, max_open_trades=2)

    # 50/50 of +10% and -10% is flat; exposure-matched invests 20 of 100.
    assert result["full_50_50_return"] == pytest.approx(0.0, abs=1e-12)
    assert result["max_exposure_invested_fraction"] == pytest.approx(0.20)
    assert result["exposure_matched_return"] == pytest.approx(0.0, abs=1e-12)
    assert result["ETH"] is not None
    assert result["universe"] == ["BTC/USDT", "ETH/USDT"]


def test_btc_only_universe_uses_btc_alone(module):
    pd = pytest.importorskip("pandas")
    btc = frame(pd, [100.0] * 24 + [110.0] * 25)

    result = module.compute_period("development", btc, None, 0.0, PERIODS,
                                   wallet=100.0, stake=10.0, max_open_trades=2)

    assert result["ETH"] is None
    assert result["universe"] == ["BTC/USDT"]
    # Whole wallet in BTC: +10%. Exposure-matched: 20 invested, so +2%.
    assert result["full_50_50_return"] == pytest.approx(0.10, abs=1e-12)
    assert result["exposure_matched_return"] == pytest.approx(0.02, abs=1e-12)


def test_a_btc_specialist_is_not_flattered_by_the_two_asset_control(module):
    """The reason the flag exists, stated as a test.

    When ETH falls and BTC rises, the combined control understates what BTC
    alone returned. Scoring a BTC specialist against it would credit the
    candidate with ETH's loss.
    """
    pd = pytest.importorskip("pandas")
    btc = frame(pd, [100.0] * 24 + [110.0] * 25)
    eth = frame(pd, [100.0] * 24 + [70.0] * 25)

    combined = module.compute_period("development", btc, eth, 0.0, PERIODS)
    btc_only = module.compute_period("development", btc, None, 0.0, PERIODS)

    assert btc_only["exposure_matched_return"] > combined["exposure_matched_return"]


def test_fees_are_applied_on_both_sides(module):
    pd = pytest.importorskip("pandas")
    flat = frame(pd, [100.0] * 49)
    result = module.compute_period("development", flat, None, 0.001, PERIODS)
    # Flat price, one entry and one exit fee: (1-0.001)^2 - 1
    assert result["BTC"]["net_return_after_entry_and_exit_fee"] == pytest.approx(0.999 * 0.999 - 1.0)
