"""BASELINE-1 — deterministic EMA50/EMA200 regime reference.

This is a *scientific reference*, not a candidate that must be made profitable.
Its purpose is to give every later candidate something interpretable to beat
under an identical frozen protocol. Its result may well be negative; that says
something about the market and the protocol, not about the code.

Deliberate constraints (BASELINE-1 scope — do not relax any of them here; a
change of rules is a new, explicitly versioned candidate):

* 1h timeframe, Binance spot, long-only, BTC/USDT + ETH/USDT
* EMA50 / EMA200 regime logic and nothing else
* no Hyperopt, no AI/FreqAI, no RSI, no ATR filter, no volume filter
* no trailing stop, no trailing-stop optimisation
* no ROI schedule (a single non-binding entry, so exits come from the signal)
* a single conservative emergency stoploss, not a tuned parameter

Entry:  EMA50 crosses above EMA200 (regime turns up)
Exit:   EMA50 crosses below EMA200 (regime turns down)

Both indicators are computed on closed candles only. There is no reference to
any future bar, and no value from the current bar is used to decide the current
bar's fill: Freqtrade fills a signal on the following candle.
"""

from pandas import DataFrame
import talib.abstract as ta
from freqtrade.strategy import IStrategy

# Longest lookback in the strategy. The EMA seeds converge well before this, and
# the Dataset V2 warm-up window (2020-12, ~744 hourly candles) covers it.
EMA_SLOW_PERIOD = 200
EMA_FAST_PERIOD = 50


class BaselineEmaRegimeV1(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Three times the longest lookback, so the recursive EMA has converged before
    # the first scored candle.
    startup_candle_count = 3 * EMA_SLOW_PERIOD

    # No ROI schedule. 1000% is unreachable in this universe, so every exit comes
    # from the regime signal or the emergency stoploss, and the exit behaviour
    # stays readable.
    minimal_roi = {"0": 10.0}

    # Conservative emergency backstop only. It is not tuned and is deliberately
    # wide enough that it almost never binds before the regime signal does.
    stoploss = -0.25

    trailing_stop = False
    use_custom_stoploss = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=EMA_FAST_PERIOD)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=EMA_SLOW_PERIOD)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "ema_regime_up")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["ema_fast"] < dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "ema_regime_down")
        return dataframe
