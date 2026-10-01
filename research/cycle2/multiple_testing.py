"""Thin multiple-testing wrapper over ``trialgate.validation`` (OPENING-1 §6.3).

Only the two validation statistics are used: ``deflated_sharpe_ratio`` (with
``observations_required_for_dsr``) and ``probability_of_backtest_overfitting``.
trialgate's registry, holdout and gates are FORBIDDEN here: the canonical and
only trial-count authority is ``research/trial_ledger.py``, read-only, and the
package's default thresholds (PBO 0.05 / DSR 0.95 in ``trialgate.gates``) are
never used — every threshold is a required, caller-supplied argument that comes
from a preregistration. Calling without one raises.

The NOT_EVALUABLE law: when an input cannot be meaningfully evaluated — too few
observations, constant or degenerate returns, too few configurations or splits
for CSCV, non-finite values, or any trialgate input error — the result is
NOT_EVALUABLE, never PASS. Nothing is imputed, padded or relaxed to reach a
number.

``effective_trials`` is required on purpose: it must be the cumulative family N
(see :func:`ledger_family_trial_count`), and any figure reported from it must
also carry the upstream selection-debt statement it cannot observe
(``research/external/candidate_registry.json`` → ``multiple_testing_accounting``).
"""

from __future__ import annotations

import math
import statistics
import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]

PASS = "PASS"
FAIL = "FAIL"
NOT_EVALUABLE = "NOT_EVALUABLE"


class ThresholdRequiredError(ValueError):
    """A statistic was requested without an explicit, preregistered threshold."""


def _validation():
    # Imported here, not at module import, so the precondition branches below
    # are checkable in an environment that has not installed the pinned
    # package. Only the validation module is ever named.
    from trialgate import validation

    return validation


def _result(status: str, value, threshold: float, effective_trials, observations, reason: str) -> dict:
    return {
        "status": status,
        "value": value,
        "threshold": threshold,
        "effective_trials": effective_trials,
        "observations": observations,
        "reason": reason,
    }


def _require_threshold(threshold, name: str) -> float:
    if threshold is None or isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ThresholdRequiredError(f"{name} must be an explicit preregistered number, got {threshold!r}")
    value = float(threshold)
    if not math.isfinite(value) or not 0.0 < value < 1.0:
        raise ThresholdRequiredError(f"{name} must lie strictly between 0 and 1, got {threshold!r}")
    return value


def _all_finite(values) -> bool:
    try:
        return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                   for v in values)
    except TypeError:
        return False


def dsr(
    returns: list[float],
    *,
    trial_sharpes: list[float],
    periods_per_year: int,
    effective_trials: int,
    threshold: float,
) -> dict:
    """Deflated Sharpe Ratio of ``returns`` against ``effective_trials`` trials.

    ``trial_sharpes`` are the ANNUALIZED Sharpe ratios of every counted trial
    (trialgate de-annualizes them). PASS only when the DSR is at least
    ``threshold`` and the sample is long enough by
    ``observations_required_for_dsr`` at that same target.
    """
    threshold = _require_threshold(threshold, "DSR threshold")
    observations = len(returns) if isinstance(returns, (list, tuple)) else None

    def not_evaluable(reason: str, value=None) -> dict:
        return _result(NOT_EVALUABLE, value, threshold, effective_trials, observations, reason)

    if isinstance(effective_trials, bool) or not isinstance(effective_trials, int) or effective_trials < 1:
        return not_evaluable(f"effective_trials must be an integer >= 1, got {effective_trials!r}")
    if isinstance(periods_per_year, bool) or not isinstance(periods_per_year, int) or periods_per_year < 1:
        return not_evaluable(f"periods_per_year must be an integer >= 1, got {periods_per_year!r}")
    if observations is None or not _all_finite(returns):
        return not_evaluable("returns must be a list of finite numbers")
    if not isinstance(trial_sharpes, (list, tuple)) or not _all_finite(trial_sharpes):
        return not_evaluable("trial_sharpes must be a list of finite numbers")
    if observations < 3:
        return not_evaluable(f"too few observations: {observations} < 3")
    if statistics.pstdev(returns) == 0.0:
        return not_evaluable("returns are constant")
    if effective_trials > 1 and (len(trial_sharpes) < 2 or statistics.pvariance(trial_sharpes) == 0.0):
        # trialgate silently sets the expected maximum Sharpe to 0 here, which
        # would deflate nothing while claiming N trials. That is not an answer.
        return not_evaluable(
            "cross-trial Sharpe variance is not estimable (fewer than 2 trial Sharpes, or all equal) "
            f"while effective_trials={effective_trials}"
        )

    validation = _validation()
    try:
        measured = validation.deflated_sharpe_ratio(
            list(returns), trial_sharpes=list(trial_sharpes),
            periods_per_year=periods_per_year, effective_trials=effective_trials,
        )
        requirement = validation.observations_required_for_dsr(
            list(returns), trial_sharpes=list(trial_sharpes),
            periods_per_year=periods_per_year, effective_trials=effective_trials,
            target_dsr=threshold,
        )
    except validation.ValidationInputError as exc:
        return not_evaluable(f"trialgate input error: {exc}")

    value = measured.deflated_sharpe_ratio
    if not math.isfinite(value):
        return not_evaluable("trialgate returned a non-finite DSR")
    if not requirement.reachable:
        return _result(FAIL, value, threshold, effective_trials, observations,
                       "observed Sharpe does not exceed the expected maximum of N noise trials; "
                       "no sample size reaches the threshold")
    if requirement.shortfall:
        return not_evaluable(
            f"too few observations: {observations} present, {requirement.observations_required} "
            f"required for DSR >= {threshold}", value)
    if value >= threshold:
        return _result(PASS, value, threshold, effective_trials, observations, "DSR >= threshold")
    return _result(FAIL, value, threshold, effective_trials, observations, "DSR < threshold")


def pbo(performance_matrix: list[list[float]], *, block_count: int, threshold: float) -> dict:
    """CSCV probability of backtest overfitting over a T x N matrix.

    ``block_count`` is required (no package default): it is a preregistered
    choice. PASS only when PBO <= ``threshold``. ``effective_trials`` in the
    result is the number of configuration columns evaluated.
    """
    threshold = _require_threshold(threshold, "PBO threshold")
    rows = performance_matrix if isinstance(performance_matrix, (list, tuple)) else None
    observations = len(rows) if rows is not None else None
    strategies = len(rows[0]) if rows and isinstance(rows[0], (list, tuple)) else 0

    def not_evaluable(reason: str) -> dict:
        return _result(NOT_EVALUABLE, None, threshold, strategies, observations, reason)

    if isinstance(block_count, bool) or not isinstance(block_count, int):
        return not_evaluable(f"block_count must be an integer, got {block_count!r}")
    if block_count < 2 or block_count % 2:
        return not_evaluable(f"block_count must be an even integer >= 2, got {block_count}")
    if not rows or any(not isinstance(r, (list, tuple)) or len(r) != strategies for r in rows):
        return not_evaluable("performance_matrix must be a non-empty rectangular list of rows")
    if not all(_all_finite(r) for r in rows):
        return not_evaluable("performance_matrix contains non-finite values")
    if strategies < 2:
        return not_evaluable(f"too few configurations for CSCV: {strategies} < 2")
    if observations < block_count:
        return not_evaluable(f"too few observations for {block_count} CSCV blocks: {observations}")
    varying = sum(1 for c in range(strategies) if len({r[c] for r in rows}) > 1)
    if varying < 2:
        return not_evaluable(f"degenerate matrix: only {varying} configuration column(s) vary")

    validation = _validation()
    try:
        result = validation.probability_of_backtest_overfitting(
            [list(r) for r in rows], block_count=block_count)
    except validation.ValidationInputError as exc:
        return not_evaluable(f"trialgate input error: {exc}")

    value = result.pbo
    dropped = observations - result.observations
    note = f"; {dropped} most-recent row(s) excluded to keep blocks equal" if dropped else ""
    if value <= threshold:
        return _result(PASS, value, threshold, strategies, result.observations, f"PBO <= threshold{note}")
    return _result(FAIL, value, threshold, strategies, result.observations, f"PBO > threshold{note}")


def ledger_family_trial_count(family_id: str, ledger_path: str | Path | None = None) -> int:
    """Distinct trial IDs the canonical ledger records for ``family_id`` (read-only).

    This is the ledger's own count; the cumulative family N used for DSR must
    be at least this, and is never derived from anything trialgate stores.
    Refuses an unverifiable ledger rather than counting it.
    """
    if str(_RESEARCH_DIR) not in sys.path:
        sys.path.insert(0, str(_RESEARCH_DIR))
    from trial_ledger import TrialLedger

    ledger = TrialLedger(ledger_path or _RESEARCH_DIR / "records" / "trial_ledger.jsonl")
    problems = ledger.verify()
    if problems:
        raise ValueError(f"trial ledger does not verify: {problems}")
    return len({r.payload["trial_id"] for r in ledger if r.payload.get("family_id") == family_id})
