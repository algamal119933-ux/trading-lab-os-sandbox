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
