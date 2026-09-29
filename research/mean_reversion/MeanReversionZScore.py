"""Z-score mean reversion (MEAN-REVERSION-CYCLE1-DISCOVERY-1).

Hypothesis, entry/exit mechanism, parameter grid, and validation design are
frozen in research/mean_reversion/PREREGISTRATION.md before any performance
result from this file was inspected. This file and the preregistration must
be read together; this docstring restates only the mechanism, not the
research design around it.

Mechanism: BTC/USDT spot price is expected to revert toward its own recent
rolling mean after an unusually large short-term deviation below it (a
classic, textbook mean-reversion signal, computed only from the pair's own
OHLCV — no external data, no other pair, no indicator library beyond
pandas' own rolling functions).

  roll_mean = close.rolling(LOOKBACK_HOURS).mean()
  roll_std  = close.rolling(LOOKBACK_HOURS).std()
  zscore    = (close - roll_mean) / roll_std

Entry:  zscore <= -Z_THRESHOLD   (price unusually far below its own recent mean)
Exit:   zscore >= 0              (price has reverted to at least its recent mean)
Backstop exit: minimal_roi forces a close after MAX_HOLD_HOURS regardless of
  price, via Freqtrade's standard ROI-table mechanism — not a custom_exit
  callback (Research Foundation Unit B found that callback silently fails to
  fire in this project's backtesting environment for an unconfirmed reason;
  this strategy does not depend on it at all).
Risk control: a fixed stoploss, not a mean-reversion-specific mechanism.

lookback_hours and z_threshold are read from this strategy's own
auto-loaded parameter file (MeanReversionZScore.json, in the same directory,
matching the convention Freqtrade and this project already use for
EmaCross.json), one file per configuration under test.
"""

from __future__ import annotations

import pandas as pd
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy

MAX_HOLD_HOURS = 168  # one week backstop


class MeanReversionZScore(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    # Covers the largest lookback in the preregistered grid (72h) plus margin.
    startup_candle_count = 100
    process_only_new_candles = True

    # ROI table forces a close MAX_HOLD_HOURS after entry regardless of
    # price, as a defensive backstop only — the primary, expected exit path
    # is the zscore>=0 signal in populate_exit_trend.
    minimal_roi = {"0": 100.0, str(MAX_HOLD_HOURS * 60): -100.0}
    stoploss = -0.08
    trailing_stop = False
    use_exit_signal = True
    can_short = False

    lookback_hours = IntParameter(12, 96, default=48, space="buy")
    z_threshold = DecimalParameter(1.0, 3.0, default=2.0, decimals=1, space="buy")

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        lb = int(self.lookback_hours.value)
        dataframe["roll_mean"] = dataframe["close"].rolling(lb).mean()
        dataframe["roll_std"] = dataframe["close"].rolling(lb).std()
        dataframe["zscore"] = (dataframe["close"] - dataframe["roll_mean"]) / dataframe["roll_std"]
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = ""
        threshold = float(self.z_threshold.value)
        mask = dataframe["zscore"] <= -threshold
        dataframe.loc[mask, "enter_long"] = 1
        dataframe.loc[mask, "enter_tag"] = "mr_zscore_entry"
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_tag"] = ""
        mask = dataframe["zscore"] >= 0
        dataframe.loc[mask, "exit_long"] = 1
        dataframe.loc[mask, "exit_tag"] = "mr_zscore_reverted"
        return dataframe
