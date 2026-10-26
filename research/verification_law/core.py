"""Closed-form verification statistics for PROFITABILITY-VERIFICATION-LAW-1.

Units. Unless a name says ``_annual``, a Sharpe ratio here is PER PERIOD (per day, or per
trade for a trade-unit test) and is NOT annualized. ``kurtosis`` is the raw (non-excess)
fourth standardized moment, 3 for a normal distribution, matching trialgate and the DSR
paper's (gamma_4 - 1) / 4 term.

Sources:
- Bailey & López de Prado (2012), "The Sharpe Ratio Efficient Frontier", J. of Risk:
  Probabilistic Sharpe Ratio (PSR) and Minimum Track Record Length (MinTRL).
- Bailey & López de Prado (2014), "The Deflated Sharpe Ratio", JPM: expected maximum
  Sharpe of N trials (SR0) and DSR = PSR(SR0).
- Benjamini & Yekutieli (2001): BHY step-up procedure under arbitrary dependence.
- Holm (1979): step-down FWER control (forwarded to research/auth2/stats.py).

Every function is pure. Invalid input raises ValueError; nothing is clamped, padded or
imputed to produce a number.
"""

from __future__ import annotations

import math
from statistics import NormalDist

_N = NormalDist()
EULER_GAMMA = 0.5772156649015329


def _finite(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, got {value!r}")
    return float(value)


def _prob(name: str, value: float) -> float:
    value = _finite(name, value)
    if not 0.0 < value < 1.0:
        raise ValueError(f"{name} must lie strictly between 0 and 1, got {value!r}")
    return value


def _variance_term(sr: float, skew: float, kurtosis: float) -> float:
    """1 - g3*SR + (g4 - 1)/4 * SR^2, the non-normal Sharpe variance factor."""
    term = 1.0 - skew * sr + (kurtosis - 1.0) / 4.0 * sr * sr
    if term <= 0.0:
        raise ValueError(
            f"moments too extreme for the Sharpe variance approximation (term {term:.6f} <= 0)")
    return term


def psr(sr: float, *, n: int, skew: float = 0.0, kurtosis: float = 3.0, benchmark: float = 0.0) -> float:
    """Probabilistic Sharpe Ratio: P(true per-period SR > ``benchmark``) given ``n`` observations.

    PSR = Phi( (SR - SR*) * sqrt(n - 1) / sqrt(1 - g3 SR + (g4 - 1)/4 SR^2) ).
    With ``benchmark`` = :func:`expected_max_sharpe` this is the Deflated Sharpe Ratio.
    """
    sr = _finite("sr", sr)
    benchmark = _finite("benchmark", benchmark)
    if isinstance(n, bool) or not isinstance(n, int) or n < 2:
        raise ValueError(f"n must be an integer >= 2, got {n!r}")
    term = _variance_term(sr, _finite("skew", skew), _finite("kurtosis", kurtosis))
    return _N.cdf((sr - benchmark) * math.sqrt(n - 1.0) / math.sqrt(term))


def expected_max_sharpe(trial_sharpe_variance: float, n_trials: int) -> float:
    """SR0: expected maximum per-period Sharpe of ``n_trials`` independent zero-edge trials.

    SR0 = sqrt(V) * ((1 - gamma) * Phi^-1(1 - 1/N) + gamma * Phi^-1(1 - 1/(N e))), with V the
    cross-trial variance of PER-PERIOD Sharpe ratios (annualized variance / periods_per_year).
    N = 1 gives 0: one trial carries no selection.
    """
    v = _finite("trial_sharpe_variance", trial_sharpe_variance)
    if v < 0.0:
        raise ValueError("trial_sharpe_variance must be >= 0")
    if isinstance(n_trials, bool) or not isinstance(n_trials, int) or n_trials < 1:
        raise ValueError(f"n_trials must be an integer >= 1, got {n_trials!r}")
    if n_trials == 1 or v == 0.0:
        return 0.0
    return math.sqrt(v) * ((1.0 - EULER_GAMMA) * _N.inv_cdf(1.0 - 1.0 / n_trials)
                           + EULER_GAMMA * _N.inv_cdf(1.0 - 1.0 / (n_trials * math.e)))


def min_trl(sr: float, *, benchmark: float = 0.0, skew: float = 0.0, kurtosis: float = 3.0,
            confidence: float = 0.95) -> float:
    """Minimum Track Record Length, in observations of the same unit as ``sr``.

    MinTRL = 1 + (1 - g3 SR + (g4 - 1)/4 SR^2) * (Phi^-1(confidence) / (SR - SR*))^2.
    Infinite when SR <= SR*: no length of record makes a non-positive edge significant.
    """
    sr = _finite("sr", sr)
    benchmark = _finite("benchmark", benchmark)
    confidence = _prob("confidence", confidence)
    if sr <= benchmark:
        return math.inf
    term = _variance_term(sr, _finite("skew", skew), _finite("kurtosis", kurtosis))
    return 1.0 + term * (_N.inv_cdf(confidence) / (sr - benchmark)) ** 2


def min_trl_years(sr_annual: float, *, periods_per_year: int, skew: float = 0.0, kurtosis: float = 3.0,
                  confidence: float = 0.95) -> float:
    """:func:`min_trl` against a zero benchmark, converted to years."""
    if isinstance(periods_per_year, bool) or not isinstance(periods_per_year, int) or periods_per_year < 1:
        raise ValueError(f"periods_per_year must be an integer >= 1, got {periods_per_year!r}")
    sr = _finite("sr_annual", sr_annual) / math.sqrt(periods_per_year)
    return min_trl(sr, skew=skew, kurtosis=kurtosis, confidence=confidence) / periods_per_year


def years_for_power(sr_annual: float, *, alpha: float = 0.05, power: float = 0.80) -> float:
    """Years of i.i.d.-normal returns for a one-sided fixed-horizon test of SR <= 0 to reach ``power``.

    L = ((Phi^-1(1 - alpha) + Phi^-1(power)) / SR_annual)^2. Independent of the sampling frequency.
    """
    sr = _finite("sr_annual", sr_annual)
    if sr <= 0.0:
        return math.inf
    z = _N.inv_cdf(1.0 - _prob("alpha", alpha)) + _N.inv_cdf(_prob("power", power))
    return (z / sr) ** 2


def power_after_years(sr_annual: float, years: float, *, alpha: float = 0.05) -> float:
    """Power of the one-sided fixed-horizon test after ``years``: Phi(SR sqrt(L) - Phi^-1(1 - alpha))."""
    sr = _finite("sr_annual", sr_annual)
    years = _finite("years", years)
    if years < 0.0:
        raise ValueError("years must be >= 0")
    return _N.cdf(sr * math.sqrt(years) - _N.inv_cdf(1.0 - _prob("alpha", alpha)))


def trades_for_power(sr_annual: float, *, trades_per_year: float, alpha: float = 0.05,
                     power: float = 0.80) -> float:
    """Trades needed when the test unit is one trade: years_for_power(...) * trades_per_year.

    Per-trade Sharpe = SR_annual / sqrt(trades_per_year), so the count is
    ((z_a + z_b) / SR_trade)^2 — the same information, counted in independent bets.
    """
    tpy = _finite("trades_per_year", trades_per_year)
    if tpy <= 0.0:
        raise ValueError("trades_per_year must be > 0")
    return years_for_power(sr_annual, alpha=alpha, power=power) * tpy


def max_drawdown_bound(mu: float, sigma: float, *, confidence: float = 0.95) -> tuple[float, float]:
    """(MaxDD, t*) at ``confidence`` for i.i.d. normal unit returns with mean ``mu`` > 0 and sd ``sigma``.

    Bailey & López de Prado (2015), "Stop-outs under serial correlation and the triple penance rule":
    MaxDD_c = (z_c sigma)^2 / (4 mu), reached at t* = (z_c sigma / (2 mu))^2 units. Drawdown is in
    the same additive return units as ``mu`` and ``sigma``.
    """
    mu, sigma = _finite("mu", mu), _finite("sigma", sigma)
    if mu <= 0.0 or sigma <= 0.0:
        raise ValueError("mu and sigma must be > 0 (a kill rule needs a declared positive alternative)")
    z = _N.inv_cdf(_prob("confidence", confidence))
    return (z * sigma) ** 2 / (4.0 * mu), (z * sigma / (2.0 * mu)) ** 2


def max_time_under_water(mu: float, sigma: float, *, confidence: float = 0.95) -> float:
    """MaxTuW_c = (z_c sigma / mu)^2 = 4 t*: the triple penance rule (recovery takes ~3 t*)."""
    _, t_star = max_drawdown_bound(mu, sigma, confidence=confidence)
    return 4.0 * t_star


def bhy(pvalues: dict[str, float], q: float) -> dict[str, bool]:
    """Benjamini-Hochberg-Yekutieli step-up at FDR ``q`` (valid under arbitrary dependence).

    Reject the k smallest p-values, k = max{i : p(i) <= i q / (m c(m))}, c(m) = sum_{j<=m} 1/j.
    For SCREENING only; a "proven" claim uses Holm (FWER).
    """
    q = _prob("q", q)
    if not pvalues:
        return {}
    for name, p in pvalues.items():
        p = _finite(f"p[{name}]", p)
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"p[{name}] must lie in [0, 1], got {p!r}")
    m = len(pvalues)
    c_m = sum(1.0 / j for j in range(1, m + 1))
    order = sorted(pvalues, key=lambda k: pvalues[k])
    k_max = 0
    for i, name in enumerate(order, start=1):
        if pvalues[name] <= i * q / (m * c_m):
            k_max = i
    rejected = set(order[:k_max])
    return {name: name in rejected for name in pvalues}


def holm(pvalues: dict[str, float], alpha: float) -> dict[str, bool]:
    """Holm step-down FWER control. Forwards to research/auth2/stats.py (reuse, not a second copy)."""
    from auth2.stats import holm as _holm

    return _holm(pvalues, _prob("alpha", alpha))


def dsr(returns, *, trial_sharpes, periods_per_year: int, effective_trials: int, threshold: float) -> dict:
    """Deflated Sharpe Ratio gate. Forwards to the audited research/cycle2/multiple_testing.py."""
    from cycle2 import multiple_testing

    return multiple_testing.dsr(returns, trial_sharpes=trial_sharpes, periods_per_year=periods_per_year,
                                effective_trials=effective_trials, threshold=threshold)


def pbo(performance_matrix, *, block_count: int, threshold: float) -> dict:
    """CSCV PBO. Forwards to the audited research/cycle2/multiple_testing.py."""
    from cycle2 import multiple_testing

    return multiple_testing.pbo(performance_matrix, block_count=block_count, threshold=threshold)
