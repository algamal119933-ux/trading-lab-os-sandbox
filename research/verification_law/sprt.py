"""Wald sequential probability ratio test on standardized returns (PROFITABILITY-VERIFICATION-LAW-1 §6).

Model. Each test unit (a day, or a closed trade for a trade-unit preregistration) gives a return r_t.
It is standardized by the sample standard deviation of the PREVIOUS units only (no look-ahead):
x_t = r_t / sd(r_1..r_{t-1}). The test compares

    H0: per-unit Sharpe = 0          (no edge)
    H1: per-unit Sharpe = s          (the preregistered alternative, s > 0)

under a unit-variance Gaussian working model. Each unit adds s * x_t - s^2 / 2 to the log
likelihood ratio LLR. Wald's bounds:

    A = ln((1 - beta) / alpha)   cross upward   -> ACCEPT_H1 (edge supported at the preregistered s)
    B = ln(beta / (1 - alpha))   cross downward -> ACCEPT_H0 (refuted: the kill boundary)

The first ``burn_in`` units only seed the standard deviation; they add nothing to the LLR. If
``max_n`` units are used without a crossing, the test is TRUNCATED (an underpowered, inconclusive
end; never rounded up to either side).

Caveats the law records and the test suite checks by simulation: the Gaussian working model is
wrong for fat-tailed, autocorrelated crypto returns; Wald's error bounds are approximations; and
SPRT for monitoring a live Sharpe ratio is an application of general sequential-testing theory,
not a peer-reviewed procedure for this use. Error rates must therefore be verified by simulation
on the declared return model before a candidate's preregistration is frozen.

Pure and deterministic. PAPER / RESEARCH ONLY. This module claims no profitability.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from typing import Callable, Iterable

CONTINUE = "CONTINUE"
ACCEPT_H1 = "ACCEPT_H1"
ACCEPT_H0 = "ACCEPT_H0"
TRUNCATED = "TRUNCATED"
TERMINAL = frozenset({ACCEPT_H1, ACCEPT_H0, TRUNCATED})


def sprt_bounds(alpha: float, beta: float) -> tuple[float, float]:
    """(A, B) = (ln((1 - beta) / alpha), ln(beta / (1 - alpha))). alpha=0.05, beta=0.20 -> (2.773, -1.558)."""
    for name, value in (("alpha", alpha), ("beta", beta)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 < value < 0.5:
            raise ValueError(f"{name} must lie strictly between 0 and 0.5, got {value!r}")
    return math.log((1.0 - beta) / alpha), math.log(beta / (1.0 - alpha))


@dataclass(frozen=True)
class SprtState:
    """Immutable test state. Create with :meth:`start`; advance with :func:`sprt_update`."""

    s: float
    upper: float
    lower: float
    burn_in: int
    max_n: int
    n_seen: int = 0
    n_used: int = 0
    llr: float = 0.0
    mean: float = 0.0
    m2: float = 0.0
    decision: str = CONTINUE

    @classmethod
    def start(cls, *, s: float, alpha: float, beta: float, burn_in: int, max_n: int) -> "SprtState":
        if isinstance(s, bool) or not isinstance(s, (int, float)) or not math.isfinite(s) or s <= 0.0:
            raise ValueError(f"s (per-unit Sharpe alternative) must be a finite number > 0, got {s!r}")
        if isinstance(burn_in, bool) or not isinstance(burn_in, int) or burn_in < 2:
            raise ValueError(f"burn_in must be an integer >= 2, got {burn_in!r}")
        if isinstance(max_n, bool) or not isinstance(max_n, int) or max_n < 1:
            raise ValueError(f"max_n must be an integer >= 1, got {max_n!r}")
        upper, lower = sprt_bounds(alpha, beta)
        return cls(s=float(s), upper=upper, lower=lower, burn_in=burn_in, max_n=max_n)


def sprt_update(state: SprtState, r: float) -> SprtState:
    """Advance by one unit return ``r``. A terminal state is returned unchanged."""
    if state.decision in TERMINAL:
        return state
    if isinstance(r, bool) or not isinstance(r, (int, float)) or not math.isfinite(r):
        raise ValueError(f"return must be a finite number, got {r!r}")
    llr, n_used, decision = state.llr, state.n_used, CONTINUE
    if state.n_seen >= state.burn_in:
        sd = math.sqrt(state.m2 / (state.n_seen - 1)) if state.n_seen > 1 else 0.0
        if sd > 0.0:
            x = r / sd
            llr += state.s * x - state.s * state.s / 2.0
            n_used += 1
            if llr >= state.upper:
                decision = ACCEPT_H1
            elif llr <= state.lower:
                decision = ACCEPT_H0
            elif n_used >= state.max_n:
                decision = TRUNCATED
    # Welford update AFTER use, so a unit is never standardized by its own value.
    n_seen = state.n_seen + 1
    delta = r - state.mean
    mean = state.mean + delta / n_seen
    m2 = state.m2 + delta * (r - mean)
    return replace(state, n_seen=n_seen, n_used=n_used, llr=llr, mean=mean, m2=m2, decision=decision)


def sprt_decision(state: SprtState) -> str:
    """CONTINUE, ACCEPT_H1, ACCEPT_H0 or TRUNCATED."""
    return state.decision


def sprt_run(returns: Iterable[float], *, s: float, alpha: float, beta: float, burn_in: int,
             max_n: int) -> SprtState:
    """Run the test over ``returns`` in order, stopping at the first terminal state."""
    state = SprtState.start(s=s, alpha=alpha, beta=beta, burn_in=burn_in, max_n=max_n)
    for r in returns:
        state = sprt_update(state, r)
        if state.decision in TERMINAL:
            break
    return state


def normal_sampler(rng) -> float:
    """Standard normal unit innovation."""
    return rng.gauss(0.0, 1.0)


def student_t_sampler(df: int) -> Callable:
    """Student-t innovation with ``df`` > 2 degrees of freedom, rescaled to unit variance."""
    if isinstance(df, bool) or not isinstance(df, int) or df <= 2:
        raise ValueError(f"df must be an integer > 2, got {df!r}")
    scale = math.sqrt((df - 2) / df)

    def sample(rng) -> float:
        chi2 = sum(rng.gauss(0.0, 1.0) ** 2 for _ in range(df))
        return rng.gauss(0.0, 1.0) / math.sqrt(chi2 / df) * scale

    return sample


def simulate_error_rates(*, true_sharpe: float, s: float, upper: float, lower: float, burn_in: int,
                         max_n: int, paths: int, seed: int, sampler: Callable = normal_sampler) -> dict:
    """Monte Carlo decision frequencies for a preregistration's calibration (law §6.4).

    Each path draws unit returns 0.01 * (true_sharpe + e_t), e_t from ``sampler`` (unit variance), so
    the per-unit Sharpe is ``true_sharpe``. Returns the fraction of paths ending in each decision and
    the mean number of units used. Deterministic for a given ``seed``.
    """
    if isinstance(paths, bool) or not isinstance(paths, int) or paths < 1:
        raise ValueError(f"paths must be an integer >= 1, got {paths!r}")
    if not upper > 0.0 > lower:
        raise ValueError("bounds must satisfy upper > 0 > lower")
    rng = random.Random(seed)
    counts = {ACCEPT_H1: 0, ACCEPT_H0: 0, TRUNCATED: 0}
    used = 0
    for _ in range(paths):
        state = SprtState(s=float(s), upper=float(upper), lower=float(lower), burn_in=burn_in, max_n=max_n)
        while state.decision not in TERMINAL:
            state = sprt_update(state, 0.01 * (true_sharpe + sampler(rng)))
        counts[state.decision] += 1
        used += state.n_used
    return {**{k: v / paths for k, v in counts.items()}, "mean_units": used / paths, "paths": paths,
            "seed": seed}


# --- §6.4 calibration under the declared return model (Owner decision OD-3) --------------------------
#
# A *path model* is a callable ``model(rng) -> iterator of unit innovations`` with long-run mean 0 and
# variance 1. Unlike a stateless ``sampler(rng) -> float``, a path model may carry state, which is what
# volatility clustering (GARCH) and temporal dependence (block bootstrap of an observed series) need.
# Every model is seeded through ``rng``; nothing reads a clock, a file or the network.


def iid_model(sampler: Callable = normal_sampler) -> Callable:
    """Wrap a stateless unit-variance ``sampler`` as a path model (i.i.d. innovations)."""

    def model(rng):
        while True:
            yield sampler(rng)

    return model


def garch_t_model(*, a: float = 0.12, b: float = 0.85, df: int = 3) -> Callable:
    """GARCH(1,1) with unit-variance Student-t(df) shocks, scaled to unconditional variance 1.

    sigma2_{t+1} = (1 - a - b) + a * e_t^2 + b * sigma2_t, e_t = sigma_t * z_t. Defaults (a 0.12, b 0.85,
    df 3) are the conservative crypto-like reference model of law §6.4: strong clustering, fat tails.
    """
    for name, value in (("a", a), ("b", b)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value < 1.0:
            raise ValueError(f"{name} must lie in [0, 1), got {value!r}")
    if a + b >= 1.0:
        raise ValueError(f"a + b must be < 1 for a finite unconditional variance, got {a + b!r}")
    z = student_t_sampler(df)
    omega = 1.0 - a - b

    def model(rng):
        sigma2 = 1.0
        while True:
            e = math.sqrt(sigma2) * z(rng)
            yield e
            sigma2 = omega + a * e * e + b * sigma2

    return model


def stationary_bootstrap_model(series: list[float], *, mean_block: float = 20.0) -> Callable:
    """Politis–Romano stationary bootstrap of an observed (or synthetic) unit-return ``series``.

    The series is demeaned and scaled to unit variance first, so the model is a zero-edge null that keeps
    the series' tails and its temporal dependence up to roughly ``mean_block`` units. Use the candidate's
    own historical unit returns (HISTORICAL_EXPLORATORY evidence is acceptable as a *shape* input; its mean
    is removed and never enters a verdict).
    """
    xs = [float(v) for v in series]
    if len(xs) < 30 or not all(math.isfinite(v) for v in xs):
        raise ValueError("series must hold at least 30 finite values")
    if isinstance(mean_block, bool) or not isinstance(mean_block, (int, float)) or mean_block < 1.0:
        raise ValueError(f"mean_block must be >= 1, got {mean_block!r}")
    mu = sum(xs) / len(xs)
    sd = math.sqrt(sum((v - mu) ** 2 for v in xs) / (len(xs) - 1))
    if not sd > 0.0:
        raise ValueError("series has zero variance")
    std = [(v - mu) / sd for v in xs]
    n, p = len(std), 1.0 / float(mean_block)

    def model(rng):
        i = rng.randrange(n)
        while True:
            yield std[i]
            i = rng.randrange(n) if rng.random() < p else (i + 1) % n

    return model


def _path_max_llr(innovations, *, true_sharpe: float, s: float, lower: float, burn_in: int, max_n: int) -> float:
    """Highest LLR a path reaches before it first touches ``lower`` or uses ``max_n`` units.

    Mirrors :func:`sprt_update` exactly (plug-in sd from previous units only, burn-in, increments
    s*x - s^2/2) but ignores the upper bound, so one simulation answers "would this path have crossed
    A?" for every A at once: it crosses A iff its running maximum reaches A first.
    """
    n_seen, n_used, llr, mean, m2, best = 0, 0, 0.0, 0.0, 0.0, 0.0
    half = s * s / 2.0
    for e in innovations:
        r = 0.01 * (true_sharpe + e)
        if n_seen >= burn_in and n_seen > 1:
            sd = math.sqrt(m2 / (n_seen - 1))
            if sd > 0.0:
                llr += s * (r / sd) - half
                n_used += 1
                if llr > best:
                    best = llr
                if llr <= lower or n_used >= max_n:
                    return best
        n_seen += 1
        delta = r - mean
        mean += delta / n_seen
        m2 += delta * (r - mean)
    return best


def calibrate_upper_bound(*, s: float, alpha: float, beta: float, burn_in: int, max_n: int, paths: int,
                          seed: int, model: Callable, step: float = 0.05, ceiling: float = 12.0) -> dict:
    """Smallest upper bound A* >= Wald's A whose simulated false-acceptance at zero edge is <= ``alpha``.

    One seeded simulation under H0 (true per-unit Sharpe 0) with the declared path ``model``. A* is searched
    on a ``step`` grid starting AT Wald's A, so calibration can only make the test stricter, never weaker.
    For m concurrent candidates pass ``alpha / m`` (law §8). If no A* <= ``ceiling`` achieves ``alpha``,
    ``status`` is ``NOT_CALIBRATABLE`` and the preregistration cannot be frozen with this design.

    Returns {"upper", "lower", "wald_upper", "false_accept", "false_accept_at_wald", "status", "paths",
    "seed"}. Verify power separately at A* with :func:`simulate_model_error_rates` under true_sharpe = s.
    """
    if isinstance(paths, bool) or not isinstance(paths, int) or paths < 100:
        raise ValueError(f"paths must be an integer >= 100, got {paths!r}")
    wald_upper, lower = sprt_bounds(alpha, beta)
    SprtState.start(s=s, alpha=alpha, beta=beta, burn_in=burn_in, max_n=max_n)  # validates s/burn_in/max_n
    rng = random.Random(seed)
    peaks = sorted((_path_max_llr(model(rng), true_sharpe=0.0, s=float(s), lower=lower, burn_in=burn_in,
                                  max_n=max_n) for _ in range(paths)), reverse=True)

    def rate(a: float) -> float:
        return sum(1 for p in peaks if p >= a) / paths

    upper, status = wald_upper, "CALIBRATED"
    while rate(upper) > alpha:
        upper = round(upper + step, 10)
        if upper > ceiling:
            status = "NOT_CALIBRATABLE"
            break
    return {"upper": upper, "lower": lower, "wald_upper": wald_upper, "false_accept": rate(upper),
            "false_accept_at_wald": rate(wald_upper), "status": status, "paths": paths, "seed": seed}


def simulate_model_error_rates(*, true_sharpe: float, s: float, upper: float, lower: float, burn_in: int,
                               max_n: int, paths: int, seed: int, model: Callable) -> dict:
    """Like :func:`simulate_error_rates`, for a stateful path ``model`` (GARCH-t, block bootstrap, i.i.d.)."""
    if isinstance(paths, bool) or not isinstance(paths, int) or paths < 1:
        raise ValueError(f"paths must be an integer >= 1, got {paths!r}")
    if not upper > 0.0 > lower:
        raise ValueError("bounds must satisfy upper > 0 > lower")
    rng = random.Random(seed)
    counts = {ACCEPT_H1: 0, ACCEPT_H0: 0, TRUNCATED: 0}
    used = 0
    for _ in range(paths):
        state = SprtState(s=float(s), upper=float(upper), lower=float(lower), burn_in=burn_in, max_n=max_n)
        for e in model(rng):
            state = sprt_update(state, 0.01 * (true_sharpe + e))
            if state.decision in TERMINAL:
                break
        counts[state.decision] += 1
        used += state.n_used
    return {**{k: v / paths for k, v in counts.items()}, "mean_units": used / paths, "paths": paths,
            "seed": seed}
