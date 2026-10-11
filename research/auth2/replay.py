"""AUTH-2 replay evaluator (FUNNEL_LAW_2.md §REPLAY_EVALUATOR_CONTRACT).

The smallest deterministic component that turns a frozen target-weight
schedule into a daily return series, for: null distributions, statistical
calibration worlds, leave-one-out checks, A2 weekday offsets, PBO and the
diagnostic-only survivor combination. It never replaces the engine: every
primary, perturbation, stress, benchmark and secondary number in a verdict
comes from a Freqtrade run. It never searches parameters, never writes a
schedule (schedules come only from research/auth2/signals.py generators) and
never touches the ledger.

To be admissible for a family it must reproduce that family's engine runs
(``parity``: daily-return correlation >= 0.999 and total-return difference
<= 0.25 pp). It therefore mirrors Freqtrade 2026.7's backtest accounting, as
read from its source:

  · fills at the bar open, entry price min(open x (1 + s), high), exit price
    max(open x (1 - s), low), s = the schedule's extra slippage for the pair;
  · average-cost basis; the entry fee of the units still held is recognised
    when they are sold (Freqtrade realises fees with profit), the exit fee at
    the sale; free cash = start + realised profit - stake held at cost;
  · sizing equity E(T) = free cash + sum(amount x open(T)), fixed once per row;
  · order of processing at T: open positions in the order they were opened,
    then new entries in whitelist order; a buy is capped by free cash;
  · the equity mark at each day boundary is taken at the bar open before any
    order at that bar (Freqtrade's wallet capture).

Everything is vectorised over D independent schedules (draws) so a null
distribution of 1,000 draws is one call. Pure functions, float64,
deterministic: identical inputs give byte-identical outputs.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DAY_MS = 86_400_000
FOUR_H_MS = 14_400_000
PARITY_MIN_CORRELATION = 0.999
PARITY_MAX_TOTAL_RETURN_DIFF = 0.0025  # 0.25 percentage points
REBALANCE_TOLERANCE = 1e-9  # the follower's no-order band, as a fraction of equity


@dataclass
class Prices:
    """4h bars on one grid; NaN where Freqtrade would hold no row for the pair."""
    times: np.ndarray  # int64 ms, ascending, 4h spacing
    pairs: list[str]
    open: np.ndarray   # (N, P)
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray

    def index(self, t: int) -> int:
        i = int((t - int(self.times[0])) // FOUR_H_MS)
        if i < 0 or i >= len(self.times) or int(self.times[i]) != t:
            raise KeyError(t)
        return i


@dataclass
class Schedule:
    """Targets at execution times for D draws: weights (R, D, P) over ``pairs``."""
    exec_times: np.ndarray            # (R,) int64 ms
    weights: np.ndarray               # (R, D, P)
    forced_exits: dict[int, list[int]]  # time -> pair indices
    extra_slippage: float
    slippage_exempt: list[tuple[int, int, set[int]]]


def fill_like_freqtrade(times: np.ndarray, bars: dict[str, np.ndarray], pairs: list[str]) -> Prices:
    """Grid the bars of each pair the way Freqtrade's backtest loader fills gaps.

    Inside a pair's own first..last bar, a missing 4h bar becomes
    open = high = low = close = previous close (ohlcv_fill_up_missing_data).
    Outside that range the pair has no row (NaN).
    """
    n, p = len(times), len(pairs)
    arr = {k: np.full((n, p), np.nan) for k in ("open", "high", "low", "close")}
    t0 = int(times[0])
    for j, pair in enumerate(pairs):
        b = bars[pair]  # (M, 5): t, o, h, l, c
        if len(b) == 0:
            continue
        idx = ((b[:, 0].astype(np.int64) - t0) // FOUR_H_MS).astype(np.int64)
        keep = (idx >= 0) & (idx < n)
        first, last = int(b[0, 0]), int(b[-1, 0])
        lo = max(0, (first - t0) // FOUR_H_MS)
        hi = min(n - 1, (last - t0) // FOUR_H_MS)
        col_c = np.full(n, np.nan)
        col_c[idx[keep]] = b[keep, 4]
        has = np.zeros(n, dtype=bool)
        has[idx[keep]] = True
        # forward-fill close inside [lo, hi]
        filled = col_c.copy()
        last_val = np.nan
        for i in range(lo, hi + 1):
            if has[i]:
                last_val = filled[i]
            else:
                filled[i] = last_val
        for k, c in (("open", 1), ("high", 2), ("low", 3)):
            col = np.full(n, np.nan)
            col[idx[keep]] = b[keep, c]
            gap = (~has) & (np.arange(n) >= lo) & (np.arange(n) <= hi)
            prev_close = np.concatenate([[np.nan], filled[:-1]])
            col[gap] = prev_close[gap]
            arr[k][:, j] = col
        c_col = filled.copy()
        c_col[np.arange(n) < lo] = np.nan
        c_col[np.arange(n) > hi] = np.nan
        gap = (~has) & (np.arange(n) >= lo) & (np.arange(n) <= hi)
        prev_close = np.concatenate([[np.nan], filled[:-1]])
        c_col[gap] = prev_close[gap]
        arr["close"][:, j] = c_col
    return Prices(times, pairs, arr["open"], arr["high"], arr["low"], arr["close"])


def run(prices: Prices, sched: Schedule, fee: float, start_ms: int, end_ms: int,
        whitelist_order: list[int] | None = None, trace: list | None = None) -> np.ndarray:
    """Daily equity marks (D, days + 1) at every 00:00 UTC from start_ms to end_ms inclusive.

    A mark is valued at the open of the bar opening at the mark. When the data ends
    exactly at end_ms (its last bar closes there and no bar opens there, as at the end
    of the secondary window on Dataset V3), the end_ms mark is valued at that last
    bar's close instead (``END_AT_CLOSE``; engine_daily_marks does the same).

    ``trace``, when given, receives (t, pair index, side, units of draw 0, price)
    for every fill of draw 0 (a debugging and test aid; no effect on the marks).
    """
    R, D, P = sched.weights.shape
    order = np.array(whitelist_order if whitelist_order is not None else range(P), dtype=np.int64)
    rank_of_pair = np.empty(P, dtype=np.int64)
    rank_of_pair[order] = np.arange(P)
    cash = np.ones(D)               # economic cash (fees paid)
    amt = np.zeros((D, P))
    avg = np.zeros((D, P))          # average cost per unit
    seq = np.full((D, P), np.inf)   # opening order of open positions
    counter = 0.0
    marks_t = np.arange(start_ms, end_ms + 1, DAY_MS, dtype=np.int64)
    marks = np.full((D, len(marks_t)), np.nan)
    row_at = {int(t): r for r, t in enumerate(sched.exec_times)}
    events = sorted(set(int(t) for t in marks_t) | set(row_at) | set(sched.forced_exits))
    mark_index = {int(t): i for i, t in enumerate(marks_t)}
    ar = np.arange(D)
    end_at_close = int(prices.times[-1]) + FOUR_H_MS == end_ms

    def slip_vec(t: int) -> np.ndarray:
        """Extra slippage of every pair at time t (0 for exempt pairs)."""
        out = np.full(P, float(sched.extra_slippage))
        if sched.extra_slippage:
            for a, b, ex in sched.slippage_exempt:
                if a <= t < b and ex:
                    out[list(ex)] = 0.0
        return out

    def free_cash() -> np.ndarray:
        return cash + (amt * avg).sum(axis=1) * fee

    def sell(d_idx: np.ndarray, js: np.ndarray, units: np.ndarray, px: np.ndarray) -> None:
        nonlocal cash
        if trace is not None and d_idx.size and d_idx[0] == 0:
            trace.append((now, int(js[0]), "sell", float(units[0]), float(px[0])))
        cash[d_idx] += units * px * (1.0 - fee)
        amt[d_idx, js] -= units
        closed = amt[d_idx, js] <= 1e-15 * np.maximum(1.0, units)
        if closed.any():
            dc, jc = d_idx[closed], js[closed]
            amt[dc, jc] = 0.0
            avg[dc, jc] = 0.0
            seq[dc, jc] = np.inf

    def buy(d_idx: np.ndarray, js: np.ndarray, stake: np.ndarray, px: np.ndarray) -> None:
        nonlocal cash, counter
        units = stake / px
        if trace is not None and d_idx.size and d_idx[0] == 0:
            trace.append((now, int(js[0]), "buy", float(units[0]), float(px[0])))
        a0 = amt[d_idx, js]
        new = a0 <= 0
        tot = a0 + units
        avg[d_idx, js] = np.where(tot > 0, (a0 * avg[d_idx, js] + units * px) / np.where(tot > 0, tot, 1), 0.0)
        amt[d_idx, js] = tot
        cash[d_idx] -= units * px * (1.0 + fee)
        if new.any():
            seq[d_idx[new], js[new]] = counter
            counter += 1.0

    now = 0
    for t in events:
        if t < start_ms or t > end_ms:
            continue
        now = t
        if t == end_ms and end_at_close:  # nothing executes here: rows are < end_ms, no bar opens here
            c = prices.close[-1]
            marks[:, mark_index[t]] = free_cash() + (amt * np.where(np.isnan(c), 0.0, c)).sum(axis=1)
            continue
        i = prices.index(t)
        o, h, lo = prices.open[i], prices.high[i], prices.low[i]
        if t in mark_index:
            px = np.where(np.isnan(o), 0.0, o)
            marks[:, mark_index[t]] = free_cash() + (amt * px).sum(axis=1)
        forced = sched.forced_exits.get(t, ())
        sv = slip_vec(t) if (forced or t in row_at) else None
        for j in forced:
            held = amt[:, j] > 0
            if held.any() and not np.isnan(o[j]):
                d_idx = ar[held]
                js = np.full(d_idx.size, j)
                sell(d_idx, js, amt[held, j].copy(), np.full(d_idx.size, max(o[j] * (1.0 - sv[j]), lo[j])))
        r = row_at.get(t)
        if r is None:
            continue
        w = sched.weights[r]  # (D, P)
        px_mark = np.where(np.isnan(o), 0.0, o)
        equity = free_cash() + (amt * px_mark).sum(axis=1)
        target = w * equity[:, None]
        tol = REBALANCE_TOLERANCE * equity
        active = np.where((amt > 0).any(axis=0) | (w > 0).any(axis=0))[0]
        if len(active) == 0:
            continue
        key = np.where(np.isfinite(seq[:, active]), seq[:, active], 1e18 + rank_of_pair[active][None, :])
        perm = active[np.argsort(key, axis=1, kind="stable")]  # (D, A): each draw's processing order
        sell_px_all = np.maximum(o * (1.0 - sv), lo)
        buy_px_all = np.minimum(o * (1.0 + sv), h)
        for k in range(perm.shape[1]):
            js = perm[:, k]  # the k-th pair of every draw
            oj = o[js]
            valid = ~np.isnan(oj)
            if not valid.any():
                continue
            a_cur = amt[ar, js]
            held = a_cur > 0
            tv = target[ar, js]
            with np.errstate(invalid="ignore"):
                cur = a_cur * oj
                ex = valid & held & (tv <= 0)                      # exit
                red = valid & held & (tv > 0) & (cur - tv > tol)   # reduce
                inc = valid & (tv > 0) & (~held | (tv - cur > tol))  # enter or increase
            sm = ex | red
            if sm.any():
                units = np.where(ex, a_cur, np.minimum((cur - tv) / np.where(valid, oj, 1.0), a_cur))
                sell(ar[sm], js[sm], units[sm], sell_px_all[js[sm]])
            if inc.any():
                dd = ar[inc]
                stake = np.minimum(tv[inc] - np.where(held[inc], cur[inc], 0.0), free_cash()[dd])
                ok = stake > 0
                if ok.any():
                    buy(dd[ok], js[inc][ok], stake[ok], buy_px_all[js[inc][ok]])
    return marks


def daily_returns(marks: np.ndarray) -> np.ndarray:
    return marks[:, 1:] / marks[:, :-1] - 1.0


# -- engine output --------------------------------------------------------------


def engine_daily_marks(wallet_df, start_ms: int, end_ms: int, final_close: dict[str, float] | None = None,
                       stake: str = "USDT") -> np.ndarray:
    """Daily equity marks from Freqtrade's exported wallet capture (date, currency, rate, balance).

    Equity at a timestamp is sum(balance x rate) over currencies captured at
    that timestamp (Freqtrade's own wallet statistic). Marks are taken at every
    00:00 UTC from start_ms to end_ms inclusive.

    ``final_close`` (currency -> close of the last bar) is given only when the
    data ends exactly at end_ms (END_AT_CLOSE, as in ``run``): the engine then
    captures nothing at end_ms, and the end_ms mark is the balances captured at
    the last bar (end_ms - 4h) valued at that bar's close. The caller proves
    that nothing executes in that last bar.
    """
    import pandas as pd

    df = wallet_df.copy()
    df["date_ms"] = pd.to_datetime(df["date"], utc=True).dt.as_unit("ms").astype("int64")
    df["value"] = df["rate"].astype(float) * df["balance"].astype(float)
    eq = df.groupby("date_ms")["value"].sum()
    want = np.arange(start_ms, end_ms + 1, DAY_MS, dtype=np.int64)
    at_close = final_close is not None and int(want[-1]) == end_ms and end_ms not in eq.index
    head = want[:-1] if at_close else want
    missing = [int(t) for t in head if int(t) not in eq.index]
    if missing:
        raise ValueError(f"engine wallet capture lacks {len(missing)} day marks, first {missing[0]}")
    out = eq.loc[head].to_numpy(dtype=float)
    if not at_close:
        return out
    last = df[df["date_ms"] == end_ms - FOUR_H_MS]
    if last.empty:
        raise ValueError(f"engine wallet capture lacks the last bar {end_ms - FOUR_H_MS}")
    unpriced = sorted(set(last["currency"]) - set(final_close) - {stake})
    if unpriced:
        raise ValueError(f"no last-bar close for held currencies {unpriced}")
    value = sum(float(b) * (1.0 if c == stake else float(final_close[c]))
                for c, b in zip(last["currency"], last["balance"]))
    return np.append(out, value)


def parity(engine_marks: np.ndarray, replay_marks: np.ndarray) -> dict:
    re = engine_marks[1:] / engine_marks[:-1] - 1.0
    rr = replay_marks[1:] / replay_marks[:-1] - 1.0
    if len(re) < 3 or np.std(re) == 0 or np.std(rr) == 0:
        corr = float("nan")
    else:
        corr = float(np.corrcoef(re, rr)[0, 1])
    tre = float(engine_marks[-1] / engine_marks[0] - 1.0)
    trr = float(replay_marks[-1] / replay_marks[0] - 1.0)
    diff = abs(tre - trr)
    ok = bool(np.isfinite(corr) and corr >= PARITY_MIN_CORRELATION and diff <= PARITY_MAX_TOTAL_RETURN_DIFF)
    return {"status": "PASS" if ok else "FAIL", "daily_return_correlation": corr,
            "engine_total_return": tre, "replay_total_return": trr, "total_return_difference": diff,
            "thresholds": {"min_correlation": PARITY_MIN_CORRELATION,
                           "max_total_return_difference": PARITY_MAX_TOTAL_RETURN_DIFF}}


def output_record(name: str, series: np.ndarray, inputs: dict[str, str]) -> dict:
    """A replay output with its input hashes and this module's code sha256 (contract OUTPUTS)."""
    return {"name": name, "values_sha256": hashlib.sha256(np.ascontiguousarray(series).tobytes()).hexdigest(),
            "inputs_sha256": dict(sorted(inputs.items())),
            "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def schedule_from_json(doc: dict, pairs: list[str]) -> Schedule:
    """One-draw Schedule from a schedule document (the engine's input file)."""
    pos = {p: j for j, p in enumerate(pairs)}
    rows = doc["rows"]
    w = np.zeros((len(rows), 1, len(pairs)))
    for r, row in enumerate(rows):
        for p, x in row["w"].items():
            w[r, 0, pos[p]] = float(x)
    forced: dict[int, list[int]] = {}
    for f in doc["forced_exits"]:
        forced.setdefault(int(f["t"]), []).append(pos[f["pair"]])
    exempt = [(int(a), int(b), {pos[p] for p in ps if p in pos}) for a, b, ps in doc["slippage_exempt"]]
    return Schedule(np.array([int(r["t"]) for r in rows], dtype=np.int64), w, forced,
                    float(doc["extra_slippage"]), exempt)


def load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
