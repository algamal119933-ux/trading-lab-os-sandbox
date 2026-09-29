"""Deterministic matched-frequency null control (Research Foundation Unit B,
exit mechanism corrected under RESEARCH-FOUNDATION-CLOSURE-1 Gate 3).

Enters and exits long at fixed, pre-generated candle timestamps — 76 entries,
uniformly random over the Dataset V2 Development window, non-overlapping,
seed 20260929, each exit precomputed as entry + HOLD_HOURS — from
research/null_controls/null_matched_frequency_schedule.json, whose sha256 is
pinned in the trial's preregistration.

Attempt 1/2 (COMPRESSED RESEARCH FOUNDATION, TRIAL-NULL-MATCHFREQ-1/2) used a
`custom_exit` callback comparing `current_time - trade.open_date_utc` against
HOLD_HOURS at runtime. That callback never returned an exit signal in
backtesting: the one position it did open rode to the end of the backtest
window and was closed only by the engine's own end-of-run force_exit,
consuming the pair's single-position slot and silently blocking the other 75
scheduled entries. The exact internal cause inside the callback was not
confirmed (Freqtrade did not log an exception), so rather than debug a
runtime datetime comparison further, this attempt removes it entirely: the
exit candle for every entry is precomputed at schedule-generation time —
exactly the same way the entry candles already were, which is the one
mechanism already proven to work (the historical attempts' single trade was
correctly tagged and opened) — and both signals are applied with the
identical `.isin()` pattern in populate_entry_trend / populate_exit_trend.
No runtime datetime arithmetic remains.

Purpose: calibrate whether the measurement/accounting pipeline obviously
promotes noise. This is not a claim that random entries are ever a candidate
strategy, and it establishes nothing about EmaCross's or any other
candidate's profitability.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from freqtrade.strategy import IStrategy


class NullControlMatchedFrequency(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    # No indicators are computed; entry/exit are both precomputed schedules,
    # so no warm-up window is actually needed. 30 is a nominal, non-zero
    # value only to satisfy Freqtrade's recursive-analysis tooling, which
    # refuses startup_candle_count == 0 regardless of whether any indicator
    # exists.
    startup_candle_count = 30
    process_only_new_candles = True

    minimal_roi = {"0": 100.0}
    stoploss = -0.99
    trailing_stop = False
    use_exit_signal = True
    can_short = False

    _schedule_path = Path(__file__).resolve().parent / "null_matched_frequency_schedule.json"
    _entries: set[str] | None = None
    _exits: set[str] | None = None

    @classmethod
    def _load_schedule(cls) -> tuple[set[str], set[str]]:
        if cls._entries is None or cls._exits is None:
            data = json.loads(cls._schedule_path.read_text(encoding="utf-8"))
            assert data["method"] == "matched_frequency_random"
            cls._entries = set(data["entries_utc"])
            cls._exits = set(data["exits_utc"])
        return cls._entries, cls._exits

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        entries, _ = self._load_schedule()
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = ""
        stamps = dataframe["date"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        mask = stamps.isin(entries)
        dataframe.loc[mask, "enter_long"] = 1
        dataframe.loc[mask, "enter_tag"] = "null_matched_freq"
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        _, exits = self._load_schedule()
        dataframe["exit_long"] = 0
        dataframe["exit_tag"] = ""
        stamps = dataframe["date"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        mask = stamps.isin(exits)
        dataframe.loc[mask, "exit_long"] = 1
        dataframe.loc[mask, "exit_tag"] = "null_control_scheduled_exit"
        return dataframe
