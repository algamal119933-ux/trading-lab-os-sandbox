"""AUTH-2 statistics (FUNNEL_LAW_2.md §C3, §C4, §C7, §C9, §BOOTSTRAP_RULE, §MULTIPLE_TESTING_LAW).

Every function is pure: inputs are daily return arrays (calendar days, 24/7),
seeds are explicit, and nothing reads a ledger, a file or a clock.

    sharpe                annualised Sharpe ratio, sqrt(365)
    block_length          the frozen §BOOTSTRAP_RULE (arch optimal_block_length)
    delta_sr_test         Ledoit-Wolf (2008) studentized stationary bootstrap of
                          SR(a) - SR(b), paired, one-sided either direction
    spa_pvalue            Hansen SPA (arch), consistent p-value
    holm                  Holm step-down
    dsr                   deflated Sharpe ratio (research/cycle2/multiple_testing, trialgate)
    pbo                   CSCV probability of backtest overfitting (diagnostic only)
    clopper_pearson       exact binomial interval
    max_drawdown, cvar    tail statistics of A3-2 and A1-3

Operationalisations (IMPLEMENTATION_NOTES.md §Statistics):
  * The covariance of the four moments (mean and second moment of both series)
    is the batch-means estimator with batch length b, the same expected block
    length as the bootstrap, both in the sample and inside every resample, so
    each resample is studentized exactly like the sample.
  * p-values are (1 + #{t* at least as extreme as t}) / (1 + B): never zero.
  * A non-finite or degenerate input is NOT_EVALUABLE, never a number.

PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

ANN = math.sqrt(365.0)
RESAMPLES = 10_000
BLOCK_MIN = 5
BLOCK_MAX = 60
SENSITIVITY_BLOCKS = (5, 20, 60)
SPA_VOL_TARGET = 0.20
CHUNK = 250

NOT_EVALUABLE = "NOT_EVALUABLE"


def sharpe(r: np.ndarray) -> float:
    r = np.asarray(r, dtype=float)
    if r.size < 3 or not np.isfinite(r).all():
        return float("nan")
    sd = r.std(ddof=1)
    return float(r.mean() / sd * ANN) if sd > 0 else float("nan")


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def block_length(d: np.ndarray) -> dict:
    """§BOOTSTRAP_RULE: b = clamp(round_half_up(max(b(d), b(d^2))), 5, 60), or NOT_EVALUABLE."""
    from arch.bootstrap import optimal_block_length

    d = np.asarray(d, dtype=float)
    if d.size < 10 or not np.isfinite(d).all() or np.all(d == d[0]):
        return {"status": NOT_EVALUABLE, "b": None, "reason": "series too short, non-finite or constant"}
    with np.errstate(all="ignore"):
        b1 = float(optimal_block_length(d)["stationary"].iloc[0])
        b2 = float(optimal_block_length(d ** 2)["stationary"].iloc[0])
    if not (math.isfinite(b1) and math.isfinite(b2)):
        return {"status": NOT_EVALUABLE, "b": None, "b_d": b1, "b_d2": b2, "reason": "non-finite estimate"}
    b = min(BLOCK_MAX, max(BLOCK_MIN, round_half_up(max(b1, b2))))
    return {"status": "OK", "b": b, "b_d": b1, "b_d2": b2}


_INDEX_CACHE: dict[tuple[int, int, int, int], np.ndarray] = {}
_INDEX_CACHE_MAX = 3


def stationary_indices(n: int, b: int, reps: int, seed: int) -> np.ndarray:
    """(reps, n) resample indices from arch's StationaryBootstrap (expected block length b).

    A pure function of (n, b, reps, seed); the last few are kept in memory because
    a calibration world asks for the same ones many times."""
    from arch.bootstrap import StationaryBootstrap

    key = (n, b, reps, seed)
    if key in _INDEX_CACHE:
        return _INDEX_CACHE[key]
    bs = StationaryBootstrap(b, np.arange(n, dtype=np.int32), seed=np.random.default_rng(seed))
    out = np.empty((reps, n), dtype=np.int32)
    for i, (data, _kw) in enumerate(bs.bootstrap(reps)):
        out[i] = data[0]
    if len(_INDEX_CACHE) >= _INDEX_CACHE_MAX:
        _INDEX_CACHE.pop(next(iter(_INDEX_CACHE)))
    _INDEX_CACHE[key] = out
    return out


def _moments(u: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Sharpe difference (daily units) and its gradient from moment means u (..., 4) =
    (mean a, mean b, mean a^2, mean b^2)."""
    m1, m2, s1, s2 = u[..., 0], u[..., 1], u[..., 2], u[..., 3]
    v1, v2 = s1 - m1 ** 2, s2 - m2 ** 2
    with np.errstate(invalid="ignore", divide="ignore"):
        f = m1 / np.sqrt(v1) - m2 / np.sqrt(v2)
        g = np.stack([s1 / v1 ** 1.5, -s2 / v2 ** 1.5, -m1 / (2 * v1 ** 1.5), m2 / (2 * v2 ** 1.5)], axis=-1)
    return f, g


def _se(w: np.ndarray, centre: np.ndarray, b: int) -> np.ndarray:
    """Delta-method standard error with the batch-means long-run covariance (batch length b).

    ``w`` (..., T) is g . y_t in time order and ``centre`` (...) is g . mean(y). With
    Psi = (1/K) sum_k z_k z_k', z_k = b^-1/2 sum over batch k of (y_t - mean y),
    se^2 = g' Psi g / T = mean_k (g . z_k)^2 / T, computed without forming Psi.
    """
    T = w.shape[-1]
    K = T // b
    q = (w[..., :K * b].reshape(*w.shape[:-1], K, b).sum(axis=-1) - b * centre[..., None]) / math.sqrt(b)
    with np.errstate(invalid="ignore"):
        return np.sqrt((q ** 2).mean(axis=-1) / T)


def delta_sr_test(ra: np.ndarray, rb: np.ndarray, b: int, alternative: str, seed: int,
                  reps: int = RESAMPLES) -> dict:
    """Paired studentized stationary-bootstrap test of SR(a) - SR(b) (Ledoit & Wolf 2008).

    alternative "greater": H0 SR(a) <= SR(b) vs H1 >; "less": H0 SR(a) >= SR(b) vs H1 <.
    Each resample y* = y[idx] (days resampled jointly) is studentized like the sample:
    t* = (f(y*) - f(y)) / se(y*).
    """
    ra, rb = np.asarray(ra, dtype=float), np.asarray(rb, dtype=float)
    if alternative not in ("greater", "less"):
        raise ValueError(alternative)
    out = {"alternative": alternative, "b": b, "resamples": reps, "seed": seed, "days": int(ra.size)}
    if ra.shape != rb.shape or ra.size < 2 * b or not (np.isfinite(ra).all() and np.isfinite(rb).all()):
        return {**out, "status": NOT_EVALUABLE, "reason": "unequal, short or non-finite series"}
    if ra.std() == 0 or rb.std() == 0:
        return {**out, "status": NOT_EVALUABLE, "reason": "constant return series"}
    T = ra.size
    y = np.stack([ra, rb, ra ** 2, rb ** 2], axis=-1)
    u = y.mean(axis=0)
    f, g = _moments(u)
    se = _se(y @ g, np.dot(u, g), b)
    if not (np.isfinite(f) and np.isfinite(se) and se > 0):
        return {**out, "status": NOT_EVALUABLE, "reason": "non-finite statistic or standard error"}
    t = float(f / se)
    idx = stationary_indices(T, b, reps, seed)
    exceed = 0
    valid = 0
    for c in range(0, reps, CHUNK):
        I = idx[c:c + CHUNK]
        C = I.shape[0]
        rows = np.arange(C)[:, None]
        counts = np.bincount((I + T * rows).ravel(), minlength=C * T).reshape(C, T)
        us = counts @ y / T                       # resample moment means (C, 4)
        fs, gs = _moments(us)
        w = (y @ gs.T)[I, rows]                   # g* . y*_t in resample order (C, T)
        ses = _se(w, np.einsum("ci,ci->c", us, gs), b)
        with np.errstate(invalid="ignore", divide="ignore"):
            ts = (fs - f) / ses
        ok = np.isfinite(ts)
        valid += int(ok.sum())
        exceed += int((ts[ok] >= t).sum() if alternative == "greater" else (ts[ok] <= t).sum())
    if valid < reps:
        return {**out, "status": NOT_EVALUABLE, "reason": f"{reps - valid} degenerate resamples"}
    return {**out, "status": "OK", "delta_sr": float(f * ANN), "sr_a": sharpe(ra), "sr_b": sharpe(rb),
            "t": t, "p_value": (1 + exceed) / (1 + reps)}


def spa_pvalue(bench: np.ndarray, models: np.ndarray, b: int, seed: int, reps: int = RESAMPLES) -> dict:
    """Hansen SPA consistent p-value: does any model beat the benchmark?

    Performance = daily returns levelled to 20% annualised volatility (each series
    scaled by 0.20 / its own annualised sd; used only inside the statistic). arch's
    SPA takes losses, so loss = -levelled return. ``models`` is (T, M).
    """
    from arch.bootstrap import SPA

    bench = np.asarray(bench, dtype=float)
    models = np.asarray(models, dtype=float).reshape(len(bench), -1)
    allr = np.column_stack([bench, models])
    if not np.isfinite(allr).all() or (allr.std(axis=0, ddof=1) == 0).any():
        return {"status": NOT_EVALUABLE, "reason": "non-finite or constant series", "b": b}
    lev = allr * (SPA_VOL_TARGET / ANN) / allr.std(axis=0, ddof=1)
    spa = SPA(-lev[:, 0], -lev[:, 1:], block_size=b, reps=reps, bootstrap="stationary", studentize=True,
              nested=False, seed=np.random.default_rng(seed))
    spa.compute()
    p = float(spa.pvalues["consistent"])
    return {"status": "OK", "p_value": p, "lower": float(spa.pvalues["lower"]), "upper": float(spa.pvalues["upper"]),
            "b": b, "resamples": reps, "seed": seed, "models": int(models.shape[1])}


def holm(pvalues: dict[str, float], alpha: float) -> dict[str, bool]:
    """Holm step-down: name -> rejected. Ties keep the input order (stable)."""
    names = sorted(pvalues, key=lambda k: pvalues[k])
    m = len(names)
    rejected = {k: False for k in pvalues}
    for i, k in enumerate(names):
        if pvalues[k] <= alpha / (m - i):
            rejected[k] = True
        else:
            break
    return rejected


def _cycle2():
    research = Path(__file__).resolve().parents[1]
    if str(research) not in sys.path:
        sys.path.insert(0, str(research))
    from cycle2 import multiple_testing

    return multiple_testing


def dsr(r: np.ndarray, trial_sharpes: list[float], effective_trials: int, threshold: float) -> dict:
    """Deflated Sharpe ratio through the audited Cycle-2 wrapper (trialgate)."""
    return _cycle2().dsr([float(x) for x in r], trial_sharpes=[float(s) for s in trial_sharpes],
                         periods_per_year=365, effective_trials=int(effective_trials), threshold=threshold)


def pbo(matrix: np.ndarray, block_count: int) -> dict:
    """CSCV PBO, DIAGNOSTIC ONLY: the wrapper demands a threshold, which is passed as 0.5 and
    whose PASS/FAIL is discarded here; only the value (or NOT_EVALUABLE) is reported."""
    res = _cycle2().pbo([[float(x) for x in row] for row in np.asarray(matrix)], block_count=block_count,
                        threshold=0.5)
    return {"status": NOT_EVALUABLE if res["status"] == NOT_EVALUABLE else "REPORTED", "value": res["value"],
            "block_count": block_count, "configurations": res["effective_trials"],
            "observations": res["observations"], "reason": res["reason"] if res["status"] == NOT_EVALUABLE else ""}


def clopper_pearson(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    from scipy.stats import beta

    a = (1 - level) / 2
    lo = 0.0 if k == 0 else float(beta.ppf(a, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - a, k + 1, n - k))
    return lo, hi


def equity(r: np.ndarray) -> np.ndarray:
    return np.concatenate([[1.0], np.cumprod(1.0 + np.asarray(r, dtype=float))])


def max_drawdown(r: np.ndarray) -> float:
    """Largest peak-to-trough loss of the compounded equity curve, as a positive fraction."""
    e = equity(r)
    return float(np.max(1.0 - e / np.maximum.accumulate(e)))


def cvar(r: np.ndarray, level: float = 0.05) -> float:
    """Mean of the worst ``level`` fraction of daily returns: the ceil(level x T) lowest days."""
    r = np.sort(np.asarray(r, dtype=float))
    n = max(1, math.ceil(level * r.size))
    return float(r[:n].mean())


def total_return(r: np.ndarray) -> float:
    return float(np.prod(1.0 + np.asarray(r, dtype=float)) - 1.0)
