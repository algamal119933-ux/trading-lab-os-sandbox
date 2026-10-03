"""Donchian channel breakout (OFFLINE-RESEARCH-CYCLE-2, Unit 7.3, Trend/Breakout lineage).

Hypothesis, grid and validation design are frozen in
research/trend_breakout/PREREGISTRATION.md and
research/cycle2/prereg/TRIAL-C2-TREND-DONCHIAN-1.json before any performance
result from this file exists. This docstring restates only the mechanism.

Mechanism: a long-only price-channel breakout on each pair's own 1h OHLCV. No
moving average of any kind, no EMA, no regime filter, no other pair, no external
data and no indicator library: only pandas rolling max/min of the pair's own
highs and lows, shifted one candle so a candle never sees itself.

  upper = high.rolling(entry_period).max().shift(1)   # highest high of the previous entry_period candles
  lower = low.rolling(exit_period).min().shift(1)     # lowest low of the previous exit_period candles

Entry: close > upper   (the close breaks above the prior entry_period-hour range)
Exit:  close < lower   (the close breaks below the prior exit_period-hour range)
Risk control: a fixed stoploss, frozen, not a grid parameter. minimal_roi is
disabled; the channel exit is the expected exit path.

entry_period and exit_period are read from this strategy's auto-loaded
parameter file (DonchianBreakoutV1.json in the same directory), one file per
preregistered configuration, written by research/cycle2/driver.py.
"""

from __future__ import annotations

import pandas as pd
from freqtrade.strategy import IntParameter, IStrategy


class DonchianBreakoutV1(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    # Covers the largest preregistered lookback (480 h) plus the one-candle shift.
    startup_candle_count = 500
    process_only_new_candles = True

    minimal_roi = {"0": 100.0}
    stoploss = -0.10
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    can_short = False

    entry_period = IntParameter(24, 480, default=336, space="buy")
    exit_period = IntParameter(24, 480, default=168, space="sell")

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        entry = int(self.entry_period.value)
        exit_ = int(self.exit_period.value)
        dataframe["donchian_upper"] = dataframe["high"].rolling(entry).max().shift(1)
        dataframe["donchian_lower"] = dataframe["low"].rolling(exit_).min().shift(1)
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = ""
        mask = (dataframe["close"] > dataframe["donchian_upper"]) & (dataframe["volume"] > 0)
        dataframe.loc[mask, "enter_long"] = 1
        dataframe.loc[mask, "enter_tag"] = "donchian_breakout"
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_tag"] = ""
        mask = dataframe["close"] < dataframe["donchian_lower"]
        dataframe.loc[mask, "exit_long"] = 1
        dataframe.loc[mask, "exit_tag"] = "donchian_breakdown"
        return dataframe
