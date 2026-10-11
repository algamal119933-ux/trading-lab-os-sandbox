"""Frozen synthetic world generators (FUNNEL_LAW_2.md §CALIBRATION_DAG).

One generator per family, used three ways: the 200 no-edge SIZE worlds, the
200 planted-edge POWER worlds and the single planted-edge world of the
engine positive control PC-Ax. Returns follow a GARCH(1,1) with Student-t
innovations and one common factor; nothing is fitted to AUTH-2 results or
to market data. Every parameter is a module constant recorded in the
preregistration, and a world is a pure function of (spec, seed).

Planted edges (strength ``edge`` is calibrated once, on a 200-year world, so
the true effect equals the Owner's delta; see ``calibrate``):
  A1  daily drift edge x sign(own trailing 60-day return)
  A2  weekly drift edge x (2 (rank - 1) / (n - 1) - 1) by the cross-sectional rank of
      the trailing 28-day return at each Monday, held for the following week
  A3  funding follows an AR(1) per asset; while z > 2 (the strategy's own z) the
      next 30 days carry crash probability CRASH_P_HIGH(edge) instead of the base
      CRASH_P_BASE; a crash is a one-day log return of CRASH_LOG_JUMP; each asset's
      constant log drift is raised by its expected extra crash loss, so the planted
      world differs from the no-edge world in crash timing, not in expected drift
Without an edge (SIZE worlds) the same generator runs with edge = 0 (A3: the
crash probability is CRASH_P_BASE every day, independent of funding).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from auth2 import signals as S

DAY_MS = 86_400_000
FOUR_H_MS = 14_400_000
BARS_PER_DAY = 6

# GARCH(1,1)-t, daily, one common factor. Unconditional annualised vol 70%.
ANNUAL_VOL = 0.70
GARCH_ALPHA = 0.08
GARCH_BETA = 0.90
T_DOF = 4.0
FACTOR_RHO = 0.6
DAILY_VAR = (ANNUAL_VOL / math.sqrt(365.0)) ** 2
GARCH_OMEGA = DAILY_VAR * (1.0 - GARCH_ALPHA - GARCH_BETA)
INTRADAY_RANGE = 0.5  # high/low excursion beyond open/close, in units of the bar sd

# A3 funding and crash process
FUNDING_PER_DAY = 3
FUNDING_MEAN = 1e-4
FUNDING_PHI = 0.985
FUNDING_SD = 4e-5
CRASH_P_BASE = 0.002
CRASH_LOG_JUMP = -0.15
CRASH_HORIZON_DAYS = 30

WORLD_START = datetime(2018, 1, 1, tzinfo=timezone.utc)
WORLD_END = datetime(2026, 9, 1, tzinfo=timezone.utc)

N_ASSETS = {"A1": 6, "A2": 12, "A3": 2}


def _ms(d: datetime) -> int:
    return int(d.timestamp() * 1000)


@dataclass(frozen=True)
class World:
    market: S.Market
    bars: dict[str, np.ndarray]  # pair -> (M, 6): t, o, h, l, c, v
    funding_rows: dict[str, list[tuple[int, float]]]


def _std_t(rng: np.random.Generator, size) -> np.ndarray:
    return rng.standard_t(T_DOF, size=size) / math.sqrt(T_DOF / (T_DOF - 2.0))


def generate(family: str, seed: int, edge: float, start_ms: int | None = None, end_ms: int | None = None) -> World:
    rng = np.random.default_rng(seed)
    n = N_ASSETS[family]
    t0 = start_ms if start_ms is not None else _ms(WORLD_START)
    t1 = end_ms if end_ms is not None else _ms(WORLD_END)
    days = (t1 - t0) // DAY_MS
    zf = _std_t(rng, days)
    zi = _std_t(rng, (days, n))
    e = math.sqrt(FACTOR_RHO) * zf[:, None] + math.sqrt(1 - FACTOR_RHO) * zi
    var = np.full(n, DAILY_VAR)
    logp = np.zeros((days + 1, n))
    logp[0] = math.log(100.0)
    drift = np.zeros(n)
    week_drift = np.zeros(n)
    fund = None
    if family == "A3":
        steps = days * FUNDING_PER_DAY
        f = np.zeros((steps, n))
        f[0] = FUNDING_MEAN
        eta = rng.standard_normal((steps, n))
        for s in range(1, steps):
            f[s] = FUNDING_MEAN + FUNDING_PHI * (f[s - 1] - FUNDING_MEAN) + FUNDING_SD * eta[s]
        fund = f
        zser = daily_z(f, days)
        crash_u = rng.random((days, n))
        p_crash = crash_schedule(zser, days, n, edge)
        # The planted edge is conditional timing only: each asset gets the constant log drift
        # that returns its expected crash loss to the no-edge world's, so a planted world is
        # not simply a worse market (without it a strong edge drives every strategy, overlay
        # included, to large absolute losses and C2 rejects a perfect overlay).
        compensation = (p_crash - CRASH_P_BASE).mean(axis=0) * (-CRASH_LOG_JUMP)
    for d in range(days):
        if family == "A1" and d >= 60:
            drift = edge * np.sign(logp[d] - logp[d - 60])
        elif family == "A2" and d >= 28:
            weekday = (((t0 + d * DAY_MS) // DAY_MS) + 3) % 7
            if weekday == 0:
                ret = logp[d] - logp[d - 28]
                order = np.argsort(np.argsort(ret, kind="stable"), kind="stable")  # 0 = lowest
                week_drift = edge * (2.0 * order / (n - 1) - 1.0)
            drift = week_drift
        eps = np.sqrt(var) * e[d]
        lr = drift + eps
        if family == "A3":
            lr = lr + compensation + np.where(crash_u[d] < p_crash[d], CRASH_LOG_JUMP, 0.0)
        var = GARCH_OMEGA + GARCH_ALPHA * eps ** 2 + GARCH_BETA * var
        logp[d + 1] = logp[d] + lr
    return _assemble(family, rng, logp, t0, fund)


def crash_schedule(zser: np.ndarray, days: int, n: int, edge: float) -> np.ndarray:
    """Daily crash probability (days, n): CRASH_P_HIGH(edge) within CRASH_HORIZON_DAYS after a
    day with z > 2, else CRASH_P_BASE. Funding is generated before prices, so this is exogenous."""
    p = np.full((days, n), CRASH_P_BASE)
    if edge <= 0:
        return p
    crash_until = np.full(n, -1)
    for d in range(days):
        hot = np.isfinite(zser[d]) & (zser[d] > 2.0)
        crash_until[hot] = d + CRASH_HORIZON_DAYS
        p[d] = np.where(crash_until >= d, crash_probability(edge), CRASH_P_BASE)
    return p


def crash_probability(edge: float) -> float:
    """Crash probability inside a crowding horizon for edge strength ``edge`` (edge = 0: base)."""
    return CRASH_P_BASE + edge


def daily_z(f: np.ndarray, days: int, span: int = 365, m7_days: int = 7) -> np.ndarray:
    """z(D) for every day index D (rows) and asset (columns): the strategy's own definition
    (signals.funding_z) applied to the synthetic funding, NaN without a full window."""
    n = f.shape[1]
    csum = np.vstack([np.zeros((1, n)), np.cumsum(f, axis=0)])
    d_idx = np.arange(days + 1)
    lo = (d_idx - m7_days) * FUNDING_PER_DAY
    hi = d_idx * FUNDING_PER_DAY
    m7 = np.full((days + 1, n), np.nan)
    ok = lo >= 0
    m7[ok] = (csum[hi[ok]] - csum[lo[ok]]) / (m7_days * FUNDING_PER_DAY)
    z = np.full((days + 1, n), np.nan)
    c1 = np.vstack([np.zeros((1, n)), np.nancumsum(m7, axis=0)])
    c2 = np.vstack([np.zeros((1, n)), np.nancumsum(m7 ** 2, axis=0)])
    for d in range(m7_days + span - 1, days + 1):
        s1 = c1[d + 1] - c1[d + 1 - span]
        s2 = c2[d + 1] - c2[d + 1 - span]
        mean = s1 / span
        var = (s2 - s1 * s1 / span) / (span - 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            z[d] = np.where(var > 0, (m7[d] - mean) / np.sqrt(np.maximum(var, 0)), np.nan)
    return z


def _assemble(family: str, rng: np.random.Generator, logp: np.ndarray, t0: int, fund) -> World:
    days, n = logp.shape[0] - 1, logp.shape[1]
    pairs = [f"S{family[-1]}{j + 1:02d}/USDT" for j in range(n)]
    nb = days * BARS_PER_DAY
    times = t0 + np.arange(nb, dtype=np.int64) * FOUR_H_MS
    close = np.zeros((nb, n))
    bars = {}
    noise = rng.standard_normal((days, BARS_PER_DAY, n))
    excursion = np.abs(rng.standard_normal((days, BARS_PER_DAY, 2, n)))
    for j in range(n):
        dr = logp[1:, j] - logp[:-1, j]
        sd_bar = np.maximum(np.abs(dr), 1e-4) / math.sqrt(BARS_PER_DAY)
        inc = dr[:, None] / BARS_PER_DAY + sd_bar[:, None] * (noise[:, :, j] - noise[:, :, j].mean(axis=1, keepdims=True))
        path = logp[:-1, j][:, None] + np.cumsum(inc, axis=1)
        c = np.exp(path).reshape(-1)
        o = np.concatenate([[math.exp(logp[0, j])], c[:-1]])
        ex = excursion[:, :, :, j].reshape(-1, 2) * np.repeat(sd_bar, BARS_PER_DAY)[:, None] * INTRADAY_RANGE
        h = np.maximum(o, c) * np.exp(ex[:, 0])
        lo = np.minimum(o, c) * np.exp(-ex[:, 1])
        close[:, j] = c
        bars[pairs[j]] = np.column_stack([times, o, h, lo, c, np.full(nb, 1000.0)])
    real = np.ones((nb, n), dtype=bool)
    members = list(range(n))
    periods = [(int(times[0]), int(times[-1]) + FOUR_H_MS, members, [j + 1 for j in members])]
    funding = {}
    funding_rows = {}
    if fund is not None:
        step = DAY_MS // FUNDING_PER_DAY
        ts = t0 + np.arange(fund.shape[0], dtype=np.int64) * step
        for j in range(n):
            funding[j] = (ts, fund[:, j].copy())
            funding_rows[pairs[j]] = [(int(t), float(r)) for t, r in zip(ts, fund[:, j])]
    market = S.Market(times, pairs, close, real, {}, periods, funding)
    return World(market, bars, funding_rows)
