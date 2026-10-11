# pragma: no cover - loaded by Freqtrade, exercised by the engine parity tests
"""AUTH-2 engine fixture: trade a frozen target-weight schedule in Freqtrade.

Every AUTH-2 engine run (primary, perturbation, matched benchmark, null,
stress and secondary segment) uses this one strategy class. It makes no
decision: the decisions are the schedule, generated before the run by the
frozen family generator (research/auth2/signals.py) and pinned by sha256 in
the run config. This class only turns the schedule into Freqtrade orders, so
fills, fees, wallet and position accounting are Freqtrade 2026.7's own.

Schedule semantics (research/auth2/FUNNEL_LAW_2.md, IMPLEMENTATION_NOTES.md):
  · a row at execution time T holds the target weight of every pair as a
    fraction of equity E(T) = free stake + sum(amount x open price at T),
    computed once per row before any order at T;
  · a pair absent from a row has target 0 (exit at T's open);
  · a forced exit (delisting terminal bar) closes the pair at that bar's open;
  · there is no stop-loss and no ROI exit;
  · an order carries the schedule's extra slippage as a price adjustment unless
    the pair is exempt at that time (A2: ranks 1-6 of the U12 period).

Signals are placed on the candle BEFORE T because Freqtrade backtesting fills a
signal at the next candle's open.

PAPER / RESEARCH ONLY. Backtesting only; dry_run stays true; no key.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy
from pandas import DataFrame, read_feather

FOUR_H_MS = 4 * 3_600_000
REBALANCE_TOLERANCE = 1e-9  # |target - holding| at or below this fraction of equity is no order


def _ms(dt) -> int:
    return int(dt.timestamp() * 1000)


class AUTH2ScheduleFollower(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "4h"
    can_short = False
    # No stop and no ROI exit: every exit is the schedule's. A stop at -100% sits at a price of
    # zero, which no candle low reaches (archived data holds flash-crash wicks to 0.0001 that a
    # -99% stop would sell into).
    stoploss = -1.0
    minimal_roi: dict = {}
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    position_adjustment_enable = True
    max_entry_position_adjustment = -1
    process_only_new_candles = True
    startup_candle_count = 0
    order_types = {"entry": "limit", "exit": "limit", "stoploss": "market", "stoploss_on_exchange": False}

    def bot_start(self, **kwargs) -> None:
        cfg = self.config["auth2"]
        raw = open(cfg["schedule_file"], "rb").read()
        if hashlib.sha256(raw).hexdigest() != cfg["schedule_sha256"]:
            raise RuntimeError("AUTH2: schedule sha256 does not match the run config")
        sched = json.loads(raw)
        self._rows: dict[int, dict[str, float]] = {int(r["t"]): r["w"] for r in sched["rows"]}
        self._forced: dict[int, set[str]] = {}
        for f in sched["forced_exits"]:
            self._forced.setdefault(int(f["t"]), set()).add(f["pair"])
        self._slip = float(sched["extra_slippage"])
        self._exempt = [(int(a), int(b), set(p)) for a, b, p in sched["slippage_exempt"]]
        self._opens: dict[str, dict[int, float]] = {}
        self._equity: dict[int, float] = {}

    # -- prices and equity -------------------------------------------------

    def _open_at(self, pair: str, t: int) -> float | None:
        # The open of the candle starting at T is the price every order at T fills
        # near, but Freqtrade's DataProvider (rightly) withholds that candle while T
        # is being processed. It is read from the run's own frozen feather input,
        # used only to value holdings at T, never to decide anything.
        if pair not in self._opens:
            path = Path(self.config["datadir"]) / f"{pair.replace('/', '_')}-{self.timeframe}.feather"
            df = read_feather(path)
            self._opens[pair] = dict(zip((_ms(d) for d in df["date"]), df["open"].astype(float)))
        return self._opens[pair].get(t)

    def bot_loop_start(self, current_time: datetime, **kwargs) -> None:
        t = _ms(current_time)
        if t in self._rows and t not in self._equity:
            stake = self.config["stake_currency"]
            equity = self.wallets.get_free(stake)
            for trade in Trade.get_trades_proxy(is_open=True):
                price = self._open_at(trade.pair, t)
                if price is None:
                    raise RuntimeError(f"AUTH2: no {trade.pair} candle at {t}; holdings cannot be valued")
                equity += trade.amount * price
            self._equity[t] = equity

    def _target_value(self, pair: str, t: int) -> float | None:
        row = self._rows.get(t)
        if row is None:
            return None
        return float(row.get(pair, 0.0)) * self._equity[t]

    def _slippage(self, pair: str, t: int) -> float:
        if not self._slip:
            return 0.0
        for a, b, pairs in self._exempt:
            if a <= t < b and pair in pairs:
                return 0.0
        return self._slip

    # -- signals -----------------------------------------------------------

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata["pair"]
        nxt = [_ms(d) + FOUR_H_MS for d in dataframe["date"]]
        dataframe["enter_long"] = [1 if float(self._rows.get(t, {}).get(pair, 0.0)) > 0 else 0 for t in nxt]
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata["pair"]
        nxt = [_ms(d) + FOUR_H_MS for d in dataframe["date"]]
        dataframe["exit_long"] = [
            1 if (t in self._rows and float(self._rows[t].get(pair, 0.0)) <= 0) or pair in self._forced.get(t, ())
            else 0 for t in nxt]
        return dataframe

    # -- sizing ------------------------------------------------------------

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: float | None, max_stake: float,
                            leverage: float, entry_tag: str | None, side: str, **kwargs) -> float:
        value = self._target_value(pair, _ms(current_time))
        if value is None or value <= 0:
            return 0.0
        return min(value, max_stake)

    def adjust_trade_position(self, trade: Trade, current_time: datetime, current_rate: float,
                              current_profit: float, min_stake: float | None, max_stake: float,
                              current_entry_rate: float, current_exit_rate: float,
                              current_entry_profit: float, current_exit_profit: float, **kwargs):
        t = _ms(current_time)
        value = self._target_value(trade.pair, t)
        if value is None or value <= 0 or trade.pair in self._forced.get(t, ()):
            return None  # no row, or a full exit handled by the exit signal
        if trade.open_date_utc == current_time:
            return None  # entered at this open: the entry order already sized the position
        delta = value - trade.amount * current_rate
        if abs(delta) <= REBALANCE_TOLERANCE * self._equity[t]:
            return None
        if delta > 0:
            return min(delta, max_stake) if max_stake > 0 else None
        if delta < 0 and trade.amount > 0:
            sell_amount = min(-delta / current_rate, trade.amount)
            # Freqtrade converts a negative stake to an amount via amount / stake_amount.
            return -sell_amount * trade.stake_amount / trade.amount
        return None

    def custom_entry_price(self, pair: str, trade: Trade | None, current_time: datetime,
                           proposed_rate: float, entry_tag: str | None, side: str, **kwargs) -> float:
        return proposed_rate * (1.0 + self._slippage(pair, _ms(current_time)))

    def custom_exit_price(self, pair: str, trade: Trade, current_time: datetime, proposed_rate: float,
                          current_profit: float, exit_tag: str | None, **kwargs) -> float:
        return proposed_rate * (1.0 - self._slippage(pair, _ms(current_time)))
