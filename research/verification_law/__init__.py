"""PROFITABILITY-VERIFICATION-LAW-1 statistics (research/PROFITABILITY_VERIFICATION_LAW_1.md).

Pure, deterministic, standard library only. Nothing here reads a ledger, a file, the
network or a clock, and nothing here decides a verdict on its own: the law maps these
numbers to verdicts, and every threshold comes from a preregistration.

Reuse before build: the Deflated Sharpe Ratio and CSCV/PBO are NOT re-implemented here.
They stay with the audited Cycle-2 wrapper over trialgate==0.5.0
(research/cycle2/multiple_testing.py, research/cycle2/TRIALGATE_AUDIT_1.md); ``dsr`` and
``pbo`` below only forward to it. Holm forwards to research/auth2/stats.py.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO. This module claims no profitability.
"""

from verification_law.core import (
    bhy,
    dsr,
    expected_max_sharpe,
    holm,
    max_drawdown_bound,
    max_time_under_water,
    min_trl,
    min_trl_years,
    pbo,
    power_after_years,
    psr,
    trades_for_power,
    years_for_power,
)
from verification_law.sprt import (
    SprtState,
    calibrate_upper_bound,
    garch_t_model,
    iid_model,
    normal_sampler,
    simulate_error_rates,
    simulate_model_error_rates,
    stationary_bootstrap_model,
    sprt_bounds,
    sprt_decision,
    sprt_run,
    sprt_update,
    student_t_sampler,
)

__all__ = [
    "SprtState",
    "bhy",
    "calibrate_upper_bound",
    "dsr",
    "expected_max_sharpe",
    "garch_t_model",
    "holm",
    "iid_model",
    "max_drawdown_bound",
    "max_time_under_water",
    "min_trl",
    "min_trl_years",
    "normal_sampler",
    "pbo",
    "power_after_years",
    "psr",
    "simulate_error_rates",
    "simulate_model_error_rates",
    "sprt_bounds",
    "sprt_decision",
    "sprt_run",
    "sprt_update",
    "stationary_bootstrap_model",
    "student_t_sampler",
    "trades_for_power",
    "years_for_power",
]
