"""AUTH-2 schedule generators (FUNNEL_LAW_2.md §PRIMARY_CONFIGS, §ROBUSTNESS_PERTURBATIONS,
§Matched benchmarks, §CALIBRATION_DAG nulls).

Every AUTH-2 position comes from a function here. Each one reads only daily
closes known at its decision time, membership fixed at the selection date,
and (A3) funding records strictly before the decision time; the causality
gates (``lookahead_check``, ``recursive_check``) prove that on the data each
run uses. Execution is at the 4h bar opening at the decision time plus
``exec_offset_bars`` x 4h (0 = the next bar open; 1 = the +1 bar latency
stress).

Conventions (frozen; IMPLEMENTATION_NOTES.md):
  daily close C(D)      close of the 4h bar opening at D - 4h (D = a 00:00 UTC day boundary)
  return over L days    C(D) / C(D - L days) - 1
  realised vol (n days) sample sd (ddof 1) of the last n daily simple returns x sqrt(365)
  funding m7(D)         mean of the funding rates with calc time in [D - 7 days, D)
  funding z(D)          (m7(D) - mean) / sd (ddof 1) over the 365 daily m7 values D - 364 days ... D
  tradable at X         a real (not gap-filled) bar opens at X and X is not the pair's delisting bar
A weight that cannot be computed (missing history, non-tradable pair) is 0: cash.

PAPER / RESEARCH ONLY: long or cash, weights in [0, 1], total <= 1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

DAY_MS = 86_400_000
FOUR_H_MS = 14_400_000
ANN = math.sqrt(365.0)


@dataclass
class Market:
    """What a generator may read. ``real`` marks bars that exist in the data (not gap-fills)."""
    times: np.ndarray            # 4h grid, int64 ms
    pairs: list[str]
    close: np.ndarray            # (N, P), Freqtrade-filled, NaN outside each pair's rows
    real: np.ndarray             # (N, P) bool
    terminal: dict[int, set[int]]  # pair index -> delisting bar times
    periods: list[tuple[int, int, list[int], list[int]]]  # (start, end, member pair idx, ranks)
    funding: dict[int, tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)  # pair idx -> (ms, rate)
    # per period: the ranked eligible candidates (pair idx, best first), for the
    # point-in-time rebuilds of A2-1 and A2-3; defaults to the members
    candidates: list[list[int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.candidates:
            self.candidates = [list(p[2]) for p in self.periods]

    def bar(self, t: int) -> int:
        i = (t - int(self.times[0])) // FOUR_H_MS
        return int(i) if 0 <= i < len(self.times) and int(self.times[i]) == t else -1

    def daily_close(self, days: np.ndarray) -> np.ndarray:
        """C(D) for each day boundary D (rows) and pair (columns)."""
        out = np.full((len(days), len(self.pairs)), np.nan)
        for r, d in enumerate(days):
            i = self.bar(int(d) - FOUR_H_MS)
            if i >= 0:
                out[r] = self.close[i]
        return out

    def tradable(self, x: int) -> np.ndarray:
        i = self.bar(x)
        ok = np.zeros(len(self.pairs), dtype=bool)
        if i < 0:
            return ok
        ok[:] = self.real[i]
        for j, ts in self.terminal.items():
            if x in ts:
                ok[j] = False
        return ok

    def members_at(self, t: int) -> tuple[list[int], list[int], int, int]:
        for a, b, m, rk in self.periods:
            if a <= t < b:
                return m, rk, a, b
        return [], [], t, t


@dataclass
class Plan:
    """Dense schedule for one or more draws."""
    exec_times: np.ndarray        # (R,)
    weights: np.ndarray           # (R, D, P)
    forced_exits: dict[int, list[int]]
    extra_slippage: float
    slippage_exempt: list[tuple[int, int, set[int]]]
    meta: dict = field(default_factory=dict)


def _decision_days(start_ms: int, end_ms: int, weekday: int | None = None) -> np.ndarray:
    days = np.arange(start_ms, end_ms, DAY_MS, dtype=np.int64)
    if weekday is None:
        return days
    # 1970-01-01 was a Thursday (weekday 3, Monday = 0)
    wd = ((days // DAY_MS) + 3) % 7
    return days[wd == weekday]


def _history_days(days: np.ndarray, back: int) -> np.ndarray:
    """All day boundaries from the first decision minus ``back`` days to the last decision."""
    return np.arange(int(days[0]) - back * DAY_MS, int(days[-1]) + DAY_MS, DAY_MS, dtype=np.int64)


def _forced(m: Market, start: int, end: int) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for j, ts in m.terminal.items():
        for t in ts:
            if start <= t <= end:
                out.setdefault(int(t), []).append(j)
    return {t: sorted(v) for t, v in sorted(out.items())}


def _vol(C: np.ndarray, k: int, n: int) -> np.ndarray:
    """Realised vol at history index k from the n daily returns ending at C[k]."""
    seg = C[k - n:k + 1]
    r = seg[1:] / seg[:-1] - 1.0
    with np.errstate(invalid="ignore"):
        sd = np.std(r, axis=0, ddof=1)
    sd[np.isnan(r).any(axis=0)] = np.nan
    return sd * ANN


# -- A1 TSMOM-VT ----------------------------------------------------------------

A1_PRIMARY = {"lookbacks": [20, 60, 120], "target_vol": 0.25, "vol_window": 30, "sleeves": 6}


def a1_weights(m: Market, start: int, end: int, params: dict, timing: bool = True,
               exec_offset_bars: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(exec_times, weights (R, P), signal (R, P) in {0, 1}) for A1 (timing=False: A1-BENCH)."""
    days = _decision_days(start, end)
    back = max(params["lookbacks"]) + params["vol_window"] + 2
    hist = _history_days(days, back)
    C = m.daily_close(hist)
    W = np.zeros((len(days), len(m.pairs)))
    S = np.zeros((len(days), len(m.pairs)))
    for r, d in enumerate(days):
        k = back + r
        x = int(d) + exec_offset_bars * FOUR_H_MS
        members, _ranks, _a, _b = m.members_at(int(d))
        if not members:
            continue
        ok = m.tradable(x)
        vol = _vol(C, k, params["vol_window"])
        rets = np.stack([C[k] / C[k - L] - 1.0 for L in params["lookbacks"]])
        sig = rets.mean(axis=0)
        for j in members:
            if not ok[j] or not np.isfinite(vol[j]) or vol[j] <= 0 or not np.isfinite(sig[j]):
                continue
            size = min(1.0, params["target_vol"] / vol[j]) / params["sleeves"]
            on = 1.0 if sig[j] > 0 else 0.0
            S[r, j] = on
            W[r, j] = size * (on if timing else 1.0)
    return days + exec_offset_bars * FOUR_H_MS, W, S


def a1_null_weights(m: Market, start: int, end: int, params: dict, seeds: list[int],
                    exec_offset_bars: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """A1 random-timing null: each sleeve's primary on/off series circularly shifted by an
    independent uniform offset in [90, T - 90] days (sleeve = U6 rank slot), times the
    benchmark size of the asset in that slot. Returns (exec_times, weights (R, D, P))."""
    t_exec, Wb, _ = a1_weights(m, start, end, params, timing=False, exec_offset_bars=exec_offset_bars)
    _, _, S = a1_weights(m, start, end, params, timing=True, exec_offset_bars=exec_offset_bars)
    days = t_exec - exec_offset_bars * FOUR_H_MS
    R = len(days)
    slots = params["sleeves"]
    slot_pair = np.full((R, slots), -1)
    for r, d in enumerate(days):
        members, ranks, _a, _b = m.members_at(int(d))
        for j, rk in zip(members, ranks):
            if 1 <= rk <= slots:
                slot_pair[r, rk - 1] = j
    slot_sig = np.zeros((R, slots))
    for s in range(slots):
        js = slot_pair[:, s]
        valid = js >= 0
        slot_sig[valid, s] = S[np.arange(R)[valid], js[valid]]
    out = np.zeros((R, len(seeds), len(m.pairs)))
    for di, seed in enumerate(seeds):
        rng = np.random.default_rng(seed)
        offsets = rng.integers(90, R - 90 + 1, size=slots)
        for s in range(slots):
            shifted = np.roll(slot_sig[:, s], int(offsets[s]))
            js = slot_pair[:, s]
            valid = js >= 0
            rows = np.arange(R)[valid]
            out[rows, di, js[valid]] = shifted[valid] * Wb[rows, js[valid]]
    return t_exec, out


# -- A2 XSMOM-LO ----------------------------------------------------------------

A2_PRIMARY = {"lookback": 28, "skip": 1, "k": 3, "weekday": 0}


def a2_weights(m: Market, start: int, end: int, params: dict, mode: str = "primary", seeds: list[int] | None = None,
               k_eff_from: np.ndarray | None = None, exec_offset_bars: int = 0) -> dict:
    """A2 primary / benchmark / random-selection null.

    mode "primary": top k_eff eligible by trailing return, 1/k each.
    mode "bench":   gross min(k_eff, n)/k spread equally over all n eligible coins,
                    k_eff taken from the primary (``k_eff_from``) so exposure is matched.
    mode "null":    k_eff coins drawn uniformly from the eligible set per seed, 1/k each.
    A holding delisted inside a membership period reduces k_eff by one until the
    next universe-selection date (its slot stays cash).
    """
    days = _decision_days(start, end, params["weekday"])
    back = params["lookback"] + params["skip"] + 2
    hist = _history_days(days, back)
    C = m.daily_close(hist)
    hist_index = {int(d): i for i, d in enumerate(hist)}
    draws = len(seeds) if mode == "null" else 1
    rngs = [np.random.default_rng(s) for s in (seeds or [0])]
    R, P, k = len(days), len(m.pairs), params["k"]
    W = np.zeros((R, draws, P))
    k_eff_out = np.zeros(R, dtype=np.int64)
    held = [set() for _ in range(draws)]
    lost = [0] * draws
    period_of_prev = None
    for r, d in enumerate(days):
        d = int(d)
        x = d + exec_offset_bars * FOUR_H_MS
        members, _ranks, pa, pb = m.members_at(d)
        if (pa, pb) != period_of_prev:
            lost = [0] * draws
            period_of_prev = (pa, pb)
        prev_x = int(days[r - 1]) + exec_offset_bars * FOUR_H_MS if r else None
        for di in range(draws):
            if prev_x is not None:
                for j in list(held[di]):
                    if any(prev_x < t <= x for t in m.terminal.get(j, ())):
                        held[di].discard(j)
                        lost[di] += 1
        ok = m.tradable(x)
        i = hist_index[d]
        end_i, start_i = i - params["skip"], i - params["skip"] - params["lookback"]
        ret = C[end_i] / C[start_i] - 1.0
        elig = [j for j in members if ok[j] and np.isfinite(ret[j]) and ret[j] > 0]
        for di in range(draws):
            k_eff = max(0, k - lost[di]) if k_eff_from is None else int(k_eff_from[r])
            if di == 0:
                k_eff_out[r] = k_eff
            if mode == "primary":
                pick = sorted(elig, key=lambda j: (-ret[j], m.pairs[j]))[:k_eff]
                W[r, di, pick] = 1.0 / k
            elif mode == "null":
                n_pick = min(k_eff, len(elig))
                pick = list(rngs[di].choice(np.array(elig, dtype=np.int64), size=n_pick, replace=False)) if n_pick else []
                W[r, di, pick] = 1.0 / k
            elif mode == "bench":
                if elig:
                    gross = min(k_eff, len(elig)) / k
                    W[r, di, elig] = gross / len(elig)
                pick = elig
            else:
                raise ValueError(mode)
            held[di] = {j for j in pick} if mode != "bench" else set(elig)
    return {"exec_times": days + exec_offset_bars * FOUR_H_MS, "weights": W, "k_eff": k_eff_out}


def a2_slippage_exempt(m: Market, start: int, end: int, exempt_ranks: int = 6) -> list[tuple[int, int, set[int]]]:
    out = []
    for a, b, members, ranks in m.periods:
        if b <= start or a >= end:
            continue
        out.append((a, b, {j for j, rk in zip(members, ranks) if rk <= exempt_ranks}))
    return out


# -- A3 CROWD-OVERLAY -------------------------------------------------------------

A3_PRIMARY = {"z_threshold": 2.0, "cut_to": 0.5, "target_vol": 0.25, "vol_window": 30, "m7_days": 7,
              "z_window": 365, "assets": 2}


def funding_z(m: Market, j: int, days: np.ndarray, params: dict) -> np.ndarray:
    """z(D) per decision day for asset j (NaN without a complete trailing window)."""
    ts, rates = m.funding[j]
    span = params["z_window"]
    all_days = np.arange(int(days[0]) - (span - 1) * DAY_MS, int(days[-1]) + DAY_MS, DAY_MS, dtype=np.int64)
    lo = np.searchsorted(ts, all_days - params["m7_days"] * DAY_MS, side="left")
    hi = np.searchsorted(ts, all_days, side="left")
    csum = np.concatenate([[0.0], np.cumsum(rates)])
    cnt = hi - lo
    with np.errstate(invalid="ignore", divide="ignore"):
        m7 = np.where(cnt > 0, (csum[hi] - csum[lo]) / np.where(cnt > 0, cnt, 1), np.nan)
    # a day whose 7-day window starts before the first funding record is incomplete
    m7[all_days - params["m7_days"] * DAY_MS < ts[0]] = np.nan
    z = np.full(len(days), np.nan)
    for r in range(len(days)):
        w = m7[r:r + span]
        if np.isnan(w).any():
            continue
        sd = np.std(w, ddof=1)
        if sd > 0:
            z[r] = (w[-1] - w.mean()) / sd
    return z


def a3_weights(m: Market, start: int, end: int, params: dict, overlay: bool = True,
               exec_offset_bars: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(exec_times, weights (R, P), cut (R, P) bool) for A3 (overlay=False: A3-BASE)."""
    days = _decision_days(start, end)
    back = params["vol_window"] + 2
    hist = _history_days(days, back)
    C = m.daily_close(hist)
    assets = sorted(m.funding)
    Z = {j: funding_z(m, j, days, params) for j in assets}
    W = np.zeros((len(days), len(m.pairs)))
    CUT = np.zeros((len(days), len(m.pairs)), dtype=bool)
    for r, d in enumerate(days):
        k = back + r
        x = int(d) + exec_offset_bars * FOUR_H_MS
        ok = m.tradable(x)
        vol = _vol(C, k, params["vol_window"])
        for j in assets:
            if not ok[j] or not np.isfinite(vol[j]) or vol[j] <= 0:
                continue
            size = min(1.0, params["target_vol"] / vol[j]) / params["assets"]
            cut = bool(np.isfinite(Z[j][r]) and Z[j][r] > params["z_threshold"])
            CUT[r, j] = cut
            W[r, j] = size * (params["cut_to"] if (overlay and cut) else 1.0)
    return days + exec_offset_bars * FOUR_H_MS, W, CUT


def episodes(flags: np.ndarray) -> list[tuple[int, int]]:
    """Maximal runs of True as (first index, last index)."""
    out, start = [], None
    for i, f in enumerate(flags):
        if f and start is None:
            start = i
        if not f and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(flags) - 1))
    return out


def a3_null_weights(m: Market, start: int, end: int, params: dict, seeds: list[int],
                    exec_offset_bars: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """A3 random-overlay null: per asset, the primary's overlay episodes (same number and
    durations) placed at uniformly random non-overlapping times in the window."""
    t_exec, Wb, CUT = a3_weights(m, start, end, params, overlay=False, exec_offset_bars=exec_offset_bars)
    R = len(t_exec)
    out = np.zeros((R, len(seeds), len(m.pairs)))
    for di, seed in enumerate(seeds):
        rng = np.random.default_rng(seed)
        for j in sorted(m.funding):
            eps = episodes(CUT[:, j])
            durations = [b - a + 1 for a, b in eps]
            rng.shuffle(durations)
            free = R - sum(durations)
            flags = np.zeros(R, dtype=bool)
            if durations and free >= 0:
                # random composition: choose positions of the n episodes among free + n slots
                slots = np.sort(rng.choice(free + len(durations), size=len(durations), replace=False))
                pos = 0
                prev_slot = -1
                for n_ep, (slot, dur) in enumerate(zip(slots, durations)):
                    pos += slot - prev_slot - 1
                    flags[pos:pos + dur] = True
                    pos += dur
                    prev_slot = slot
            out[:, di, j] = Wb[:, j] * np.where(flags, params["cut_to"], 1.0)
    return t_exec, out


# -- plans and the engine schedule document ------------------------------------------


def plan(m: Market, exec_times: np.ndarray, W: np.ndarray, start: int, end: int,
         extra_slippage: float = 0.0, exempt: list | None = None, meta: dict | None = None) -> Plan:
    if W.ndim == 2:
        W = W[:, None, :]
    keep = (exec_times >= start) & (exec_times < end)
    return Plan(exec_times[keep], W[keep], _forced(m, start, end), extra_slippage, exempt or [], meta or {})


def schedule_document(m: Market, p: Plan, draw: int = 0) -> dict:
    """The engine's input file for one draw. Rows list every pair with a non-zero weight."""
    rows = []
    for t, w in zip(p.exec_times, p.weights[:, draw, :]):
        nz = {m.pairs[j]: float(w[j]) for j in np.nonzero(w > 0)[0]}
        rows.append({"t": int(t), "w": nz})
    return {
        "format": "auth2-schedule-1",
        "meta": p.meta,
        "pairs": list(m.pairs),
        "rows": rows,
        "forced_exits": [{"t": int(t), "pair": m.pairs[j]} for t, js in p.forced_exits.items() for j in js],
        "extra_slippage": p.extra_slippage,
        "slippage_exempt": [[int(a), int(b), sorted(m.pairs[j] for j in ex)] for a, b, ex in p.slippage_exempt],
    }


# -- causality gates (C1 LOOKAHEAD, RECURSIVE) -----------------------------------------


def truncate(m: Market, cut_ms: int) -> Market:
    """The market as known at the execution bar opening at ``cut_ms - 4h``.

    Bars opening at or after ``cut_ms`` are removed, the execution bar keeps only
    its existence (its close is unknown), funding keeps records before the
    execution time and delisting bars up to the execution bar."""
    n = int(np.searchsorted(m.times, cut_ms, side="left"))
    fund = {j: (ts[ts < cut_ms - FOUR_H_MS], r[ts < cut_ms - FOUR_H_MS]) for j, (ts, r) in m.funding.items()}
    close = m.close[:n].copy()
    close[m.times[:n] >= cut_ms - FOUR_H_MS] = np.nan  # the execution bar exists; its close is the future
    return Market(m.times[:n], m.pairs, close, m.real[:n],
                  {j: {t for t in ts if t < cut_ms} for j, ts in m.terminal.items()}, m.periods, fund, m.candidates)


def lookahead_check(gen, m: Market, start: int, end: int, cuts: int = 20) -> dict:
    """Every row decided at or before a cut is identical when the data stop at the cut.

    ``gen(market, start, end) -> (exec_times, weights)``. For K cut points evenly
    spaced over the window, rows with decision time <= cut must match exactly.
    """
    t_full, w_full = gen(m, start, end)
    bad = []
    span = end - start
    for c in range(1, cuts + 1):
        cut = start + (span * c // (cuts + 1)) // DAY_MS * DAY_MS
        mt = truncate(m, cut + FOUR_H_MS)  # the bar opening at the cut is the execution bar
        t_c, w_c = gen(mt, start, cut + DAY_MS)
        n = int(np.searchsorted(t_full, cut, side="right"))
        n_c = int(np.searchsorted(t_c, cut, side="right"))
        if n != n_c or not np.array_equal(t_full[:n], t_c[:n_c]) or not np.array_equal(w_full[:n], w_c[:n_c]):
            bad.append(cut)
    return {"status": "PASS" if not bad else "FAIL", "cuts": cuts, "failing_cuts": bad}


def recursive_check(gen, m: Market, start: int, end: int, warmup_days: int, shifts=(30, 90)) -> dict:
    """Rows after the warm-up are identical when the data begin later by ``shifts`` days."""
    t_full, w_full = gen(m, start, end)
    bad = []
    for s in shifts:
        first = int(m.times[0]) + s * DAY_MS
        n = int(np.searchsorted(m.times, first, side="left"))
        ms_ = Market(m.times[n:], m.pairs, m.close[n:], m.real[n:], m.terminal, m.periods,
                     {j: (ts[ts >= first], r[ts >= first]) for j, (ts, r) in m.funding.items()}, m.candidates)
        valid_from = first + warmup_days * DAY_MS
        s0 = max(start, valid_from)
        if s0 >= end:
            continue
        t_s, w_s = gen(ms_, s0, end)
        keep = t_full >= s0 - 0
        if not (np.array_equal(t_full[keep], t_s) and np.array_equal(w_full[keep], w_s)):
            bad.append(s)
    return {"status": "PASS" if not bad else "FAIL", "shifts": list(shifts), "failing_shifts": bad,
            "warmup_days": warmup_days}
