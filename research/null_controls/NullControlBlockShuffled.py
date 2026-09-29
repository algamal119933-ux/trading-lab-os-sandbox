"""Deterministic block-shuffled null control (Research Foundation Unit B).

Enters long at a fixed, pre-generated set of candle timestamps: 76 entries,
evenly spaced across the Dataset V2 Development window as a baseline
schedule, split into 19 blocks of 4, with block ORDER permuted by a seeded
Fisher-Yates shuffle (seed 20260930) and remapped onto the original block
time-slots — preserving the local clustering/spacing structure a block
shuffle is meant to preserve while destroying any link to calendar time or
market condition. Exits exactly HOLD_HOURS after entry. No market data
informs entry or exit timing; the schedule was generated and frozen before
this strategy ever ran, from
research/records/null_block_shuffled_schedule.json, whose sha256 is pinned
in the trial's preregistration.

Purpose: calibrate whether the measurement/accounting pipeline obviously
promotes noise. This is not a claim that a shuffled schedule is ever a
candidate strategy, and it establishes nothing about EmaCross's or any other
candidate's profitability. It is also not a shuffle of EmaCross's own signal
— EmaCross's source is licensed, hash-pinned and not vendored, and this
strategy has no dependency on it.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pandas as pd
from freqtrade.strategy import IStrategy


class NullControlBlockShuffled(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    # No indicators are computed; entry/exit are a precomputed schedule and a
    # fixed hold duration, so no warm-up window is actually needed. 30 is a
    # nominal, non-zero value only to satisfy Freqtrade's recursive-analysis
    # tooling, which refuses startup_candle_count == 0 regardless of whether
    # any indicator exists.
    startup_candle_count = 30
    process_only_new_candles = True

    minimal_roi = {"0": 100.0}
    stoploss = -0.99
    trailing_stop = False
    use_exit_signal = False
    can_short = False

    hold_hours = 260

    _schedule_path = Path(__file__).resolve().parent / "null_block_shuffled_schedule.json"
    _entries: set[str] | None = None

    @classmethod
    def _load_entries(cls) -> set[str]:
        if cls._entries is None:
            data = json.loads(cls._schedule_path.read_text(encoding="utf-8"))
            assert data["method"] == "block_shuffled"
            cls.hold_hours = data["hold_hours"]
            cls._entries = set(data["entries_utc"])
        return cls._entries

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        entries = self._load_entries()
        stamps = dataframe["date"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        dataframe.loc[stamps.isin(entries), ["enter_long", "enter_tag"]] = (1, "null_block_shuffled")
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe["exit_long"] = 0
        return dataframe

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        self._load_entries()
        if (current_time - trade.open_date_utc) >= timedelta(hours=self.hold_hours):
            return "null_control_time_exit"
        return None
