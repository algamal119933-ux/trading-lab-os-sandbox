"""Monte Carlo resampling of a closed-trade list: outcome range and risk of ruin.

Each path draws ``len(returns)`` trades with replacement (iid bootstrap) and
compounds them at a fixed fraction of equity. Seeded, so a report reproduces.

Limits, stated in every result: iid resampling ignores serial dependence
(regimes, streaks), and the paths can only recombine trades that happened; they
never produce a loss larger than the worst one observed.
"""

from __future__ import annotations

import random

LIMITATIONS = (
    "iid bootstrap: ignores serial dependence between trades (regimes, streaks)",
    "resamples observed trades only: no loss worse than the worst observed trade",
)


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        raise ValueError("no values")
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def simulate(returns: list[float], *, fraction: float = 1.0, paths: int = 5000,
             seed: int = 0, ruin_drawdown: float = 0.5) -> dict:
    if not returns:
        raise ValueError("no trades to resample")
    if not 0 < fraction <= 1:
        raise ValueError("fraction must be in (0, 1]")
    if not 0 < ruin_drawdown < 1:
        raise ValueError("ruin_drawdown must be in (0, 1)")
    if paths < 100:
        raise ValueError("at least 100 paths")
    rng = random.Random(seed)
    n = len(returns)
    finals, drawdowns, ruined = [], [], 0
    for _ in range(paths):
        equity = peak = 1.0
        worst = 0.0
        for _ in range(n):
            equity *= 1.0 + fraction * returns[rng.randrange(n)]
            peak = max(peak, equity)
            worst = max(worst, 1.0 - equity / peak)
        finals.append(equity - 1.0)
        drawdowns.append(worst)
        ruined += worst >= ruin_drawdown
    finals.sort()
    drawdowns.sort()
    return {
        "paths": paths,
        "trades_per_path": n,
        "seed": seed,
        "fraction": fraction,
        "return_p5": _percentile(finals, 0.05),
        "return_p50": _percentile(finals, 0.50),
        "return_p95": _percentile(finals, 0.95),
        "probability_of_loss": sum(1 for f in finals if f < 0) / paths,
        "max_drawdown_p50": _percentile(drawdowns, 0.50),
        "max_drawdown_p95": _percentile(drawdowns, 0.95),
        "ruin_drawdown": ruin_drawdown,
        "risk_of_ruin": ruined / paths,
        "limitations": list(LIMITATIONS),
    }
