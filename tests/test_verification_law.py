"""PROFITABILITY-VERIFICATION-LAW-1 statistics (research/verification_law), synthetic only.

Known values: the DSR paper's worked example (Bailey & López de Prado 2014: SR0 = 0.1132,
DSR = 0.9004), the MinTRL / power closed forms and the law's own worked table. Simulations are
seeded and short. The SPRT simulations check, rather than assume, the error rates the law relies
on — including that fat tails INFLATE the false-accept rate at Wald's bound, which is why the law
requires a calibrated upper bound (§6.4). Nothing here reads data, a ledger or the network.

Thresholds below are TEST FIXTURES, not research thresholds; those come only from a preregistration.
"""

from __future__ import annotations

import functools
import math
import os
import random
import statistics

import pytest

import verification_law as vl
from verification_law import sprt as sp

try:
    import trialgate  # noqa: F401
    from trialgate import validation as tg_validation

    HAVE_TRIALGATE = True
except ImportError:  # pragma: no cover - CI installs it and requires it
    HAVE_TRIALGATE = False

REQUIRE_TRIALGATE = os.environ.get("TLOS_REQUIRE_TRIALGATE") == "1"


def needs_trialgate(test):
    """Skip without trialgate locally; fail without it where it is required (CI)."""
    if HAVE_TRIALGATE:
        return test
    if not REQUIRE_TRIALGATE:
        return pytest.mark.skip(reason="trialgate==0.5.0 not installed here")(test)

    @functools.wraps(test)
    def refuse(*_args, **_kwargs):
        pytest.fail("TLOS_REQUIRE_TRIALGATE=1 but trialgate==0.5.0 is not importable")

    return refuse


PAPER_TOL = 5e-5  # the DSR paper prints 4 decimals


# -- PSR / DSR -------------------------------------------------------------------------------

def test_dsr_paper_worked_example_via_psr_and_expected_max():
    # N = 100 trials, annualized trial-Sharpe variance 0.5, 250 periods/yr, T = 1250,
    # annualized SR 2.5, skew -3, kurtosis 10 -> SR0 = 0.1132, DSR = 0.9004.
    sr0 = vl.expected_max_sharpe(0.5 / 250, 100)
    assert abs(sr0 - 0.1132) <= PAPER_TOL
    dsr = vl.psr(2.5 / math.sqrt(250), n=1250, skew=-3.0, kurtosis=10.0, benchmark=sr0)
    assert abs(dsr - 0.9004) <= PAPER_TOL


def test_psr_basic_properties():
    assert vl.psr(0.0, n=500) == pytest.approx(0.5)
    assert vl.psr(0.05, n=200) < vl.psr(0.05, n=2000)              # more data, more confidence
    assert vl.psr(0.05, n=500, benchmark=0.06) < 0.5                # below the benchmark
    assert vl.psr(0.05, n=500, skew=-1.0) < vl.psr(0.05, n=500)    # negative skew widens the SE


def test_expected_max_sharpe_grows_with_trials_and_is_zero_for_one():
    assert vl.expected_max_sharpe(1e-3, 1) == 0.0
    values = [vl.expected_max_sharpe(1e-3, n) for n in (2, 10, 100, 1000)]
    assert values == sorted(values) and values[0] > 0.0


@needs_trialgate
def test_psr_at_expected_max_equals_the_audited_trialgate_dsr():
    rng = random.Random(7)
    returns = [rng.gauss(0.001, 0.02) for _ in range(800)]
    trial_sharpes = [0.2, 0.9, 1.4, -0.3, 0.6]
    ref = tg_validation.deflated_sharpe_ratio(returns, trial_sharpes=trial_sharpes, periods_per_year=365,
                                              effective_trials=40)
    n = len(returns)
    mean, sd = statistics.fmean(returns), statistics.stdev(returns)
    skew = sum(((r - mean) / statistics.pstdev(returns)) ** 3 for r in returns) / n
    kurt = sum(((r - mean) / statistics.pstdev(returns)) ** 4 for r in returns) / n
    sr0 = vl.expected_max_sharpe(statistics.pvariance(trial_sharpes) / 365, 40)
    assert sr0 == pytest.approx(ref.expected_max_sharpe, rel=1e-12)
    ours = vl.psr(mean / sd, n=n, skew=skew, kurtosis=kurt, benchmark=sr0)
    assert ours == pytest.approx(ref.deflated_sharpe_ratio, abs=1e-6)


@needs_trialgate
def test_dsr_and_pbo_forward_to_the_audited_cycle2_wrapper():
    from cycle2 import multiple_testing as mt

    rng = random.Random(3)
    returns = [rng.gauss(0.002, 0.02) for _ in range(400)]
    kw = dict(trial_sharpes=[0.5, 1.0, 1.5], periods_per_year=365, effective_trials=3, threshold=0.95)
    assert vl.dsr(returns, **kw) == mt.dsr(returns, **kw)
    matrix = [[rng.gauss(0, 0.01) for _ in range(6)] for _ in range(160)]
    assert vl.pbo(matrix, block_count=16, threshold=0.05) == mt.pbo(matrix, block_count=16, threshold=0.05)


@needs_trialgate
def test_pbo_is_high_on_pure_noise_and_low_with_a_planted_edge():
    rng = random.Random(2026)
    noise = [[rng.gauss(0.0, 0.01) for _ in range(20)] for _ in range(320)]
    noisy = vl.pbo(noise, block_count=16, threshold=0.05)
    assert noisy["status"] == "FAIL" and noisy["value"] > 0.2
    planted = [row[:-1] + [row[-1] + 0.01] for row in noise]  # one configuration with a large real edge
    clean = vl.pbo(planted, block_count=16, threshold=0.05)
    assert clean["status"] == "PASS" and clean["value"] <= 0.05


# -- MinTRL and power: the law's worked table ------------------------------------------------

@pytest.mark.parametrize(("sr", "years_normal", "years_crypto"), [
    (0.5, 10.83, 10.98), (1.0, 2.71, 2.80), (1.5, 1.21, 1.27), (2.0, 0.68, 0.73)])
def test_min_trl_years_table(sr, years_normal, years_crypto):
    assert vl.min_trl_years(sr, periods_per_year=365) == pytest.approx(years_normal, abs=0.005)
    assert vl.min_trl_years(sr, periods_per_year=365, skew=-0.5, kurtosis=10.0) == pytest.approx(
        years_crypto, abs=0.005)


def test_min_trl_inverts_psr():
    sr = 1.2 / math.sqrt(365)
    n = vl.min_trl(sr, skew=-0.5, kurtosis=10.0, confidence=0.95)
    assert vl.psr(sr, n=math.ceil(n), skew=-0.5, kurtosis=10.0) >= 0.95
    assert vl.psr(sr, n=math.floor(n) - 1, skew=-0.5, kurtosis=10.0) < 0.95
    assert vl.min_trl(0.0) == math.inf and vl.min_trl(-0.01) == math.inf


@pytest.mark.parametrize(("sr", "years", "power_1y", "trades_19"), [
    (0.5, 24.73, 0.13, 470), (1.0, 6.18, 0.26, 117), (1.5, 2.75, 0.44, 52), (2.0, 1.55, 0.64, 29)])
def test_power_table(sr, years, power_1y, trades_19):
    assert vl.years_for_power(sr) == pytest.approx(years, abs=0.005)
    assert vl.power_after_years(sr, 1.0) == pytest.approx(power_1y, abs=0.005)
    assert round(vl.trades_for_power(sr, trades_per_year=19)) == trades_19
    assert vl.power_after_years(sr, vl.years_for_power(sr)) == pytest.approx(0.80, abs=1e-9)


def test_invalid_inputs_raise_instead_of_guessing():
    for bad in (float("nan"), float("inf"), True, "1"):
        with pytest.raises(ValueError):
            vl.psr(bad, n=10)
    with pytest.raises(ValueError):
        vl.psr(0.1, n=1)
    with pytest.raises(ValueError):
        vl.min_trl(0.1, confidence=1.0)
    with pytest.raises(ValueError):
        vl.psr(3.0, n=10, skew=5.0, kurtosis=1.0)   # variance term <= 0: refused, not clamped
    assert vl.years_for_power(0.0) == math.inf


def test_triple_penance_kill_bounds():
    mu, sigma = 0.001, 0.02
    dd, t_star = vl.max_drawdown_bound(mu, sigma, confidence=0.95)
    z = 1.6448536269514722
    assert dd == pytest.approx((z * sigma) ** 2 / (4 * mu))
    assert t_star == pytest.approx((z * sigma / (2 * mu)) ** 2)
    assert vl.max_time_under_water(mu, sigma) == pytest.approx(4 * t_star)  # recovery = 3 t*
    with pytest.raises(ValueError):
        vl.max_drawdown_bound(0.0, sigma)


# -- multiple testing ------------------------------------------------------------------------

def test_bhy_is_stricter_than_bh_and_handles_order():
    p = {"a": 0.001, "b": 0.008, "c": 0.039, "d": 0.041, "e": 0.27}
    rejected = vl.bhy(p, 0.05)
    # c(5) = 2.2833; thresholds i * 0.05 / (5 * 2.2833) = 0.00438, 0.00876, 0.01314, ...
    assert rejected == {"a": True, "b": True, "c": False, "d": False, "e": False}
    assert vl.bhy({}, 0.05) == {}
    with pytest.raises(ValueError):
        vl.bhy({"a": 1.5}, 0.05)


def test_holm_forwards_to_auth2():
    pytest.importorskip("numpy")
    assert vl.holm({"a": 0.01, "b": 0.02, "c": 0.5}, 0.05) == {"a": True, "b": True, "c": False}


# -- SPRT ------------------------------------------------------------------------------------

def test_sprt_bounds_match_the_law():
    upper, lower = vl.sprt_bounds(0.05, 0.20)
    assert upper == pytest.approx(2.7726, abs=1e-4) and lower == pytest.approx(-1.5581, abs=1e-4)


def test_sprt_burn_in_uses_no_look_ahead_and_terminal_states_freeze():
    state = vl.SprtState.start(s=0.5, alpha=0.05, beta=0.2, burn_in=5, max_n=100)
    for r in (0.01, -0.01, 0.02, -0.02, 0.0):
        state = vl.sprt_update(state, r)
    assert state.n_seen == 5 and state.n_used == 0 and state.llr == 0.0
    state = vl.sprt_update(state, 0.0)
    assert state.n_used == 1 and state.llr == pytest.approx(-0.125)   # s*x - s^2/2 with x = 0
    big = vl.sprt_run([0.01, -0.01] * 3 + [1.0] * 50, s=0.5, alpha=0.05, beta=0.2, burn_in=6, max_n=100)
    assert big.decision == "ACCEPT_H1"
    assert vl.sprt_update(big, -100.0) == big


def test_sprt_truncates_without_rounding_up():
    st = vl.sprt_run([0.01, -0.01] * 50, s=0.01, alpha=0.05, beta=0.2, burn_in=4, max_n=20)
    assert st.decision == "TRUNCATED" and st.n_used == 20


def test_sprt_error_rates_under_the_gaussian_model():
    upper, lower = vl.sprt_bounds(0.05, 0.20)
    common = dict(s=0.2, upper=upper, lower=lower, burn_in=20, max_n=2000, paths=1500)
    null = vl.simulate_error_rates(true_sharpe=0.0, seed=1, **common)
    alt = vl.simulate_error_rates(true_sharpe=0.2, seed=2, **common)
    assert null["ACCEPT_H1"] <= 0.065          # alpha 0.05 (+ Monte Carlo tolerance)
    assert alt["ACCEPT_H1"] >= 0.77            # power 0.80 (- Monte Carlo tolerance)
    assert null["TRUNCATED"] == 0.0 and alt["TRUNCATED"] == 0.0


def test_fat_tails_inflate_alpha_at_wald_bound_and_calibration_restores_it():
    t3 = vl.student_t_sampler(3)
    lower = vl.sprt_bounds(0.05, 0.20)[1]
    common = dict(s=0.2, lower=lower, burn_in=20, max_n=2000, paths=2000, sampler=t3)
    wald = vl.simulate_error_rates(true_sharpe=0.0, upper=vl.sprt_bounds(0.05, 0.20)[0], seed=11, **common)
    assert wald["ACCEPT_H1"] > 0.06            # the caveat is real: Wald's bound is not enough
    calibrated = vl.simulate_error_rates(true_sharpe=0.0, upper=3.5, seed=11, **common)
    assert calibrated["ACCEPT_H1"] <= 0.055
    power = vl.simulate_error_rates(true_sharpe=0.2, upper=3.5, seed=12, **{**common, "paths": 1000})
    assert power["ACCEPT_H1"] >= 0.77


def test_simulation_is_deterministic():
    kw = dict(true_sharpe=0.0, s=0.3, upper=2.77, lower=-1.56, burn_in=10, max_n=500, paths=50, seed=5)
    assert vl.simulate_error_rates(**kw) == vl.simulate_error_rates(**kw)


# -- §6.4 calibration under the declared return model (Owner decision OD-3) ----------------------------

_CAL = dict(s=0.2, alpha=0.05, beta=0.20, burn_in=20, max_n=400)
_SIM = dict(s=0.2, burn_in=20, max_n=400)


def test_path_peak_matches_the_sprt_decision_unit_for_unit():
    from verification_law.sprt import _path_max_llr
    rng = random.Random(7)
    upper, lower = vl.sprt_bounds(0.05, 0.20)
    for _ in range(300):
        xs = [rng.gauss(0.0, 1.0) * (3.0 if rng.random() < 0.05 else 1.0) for _ in range(rng.randrange(25, 200))]
        peak = _path_max_llr(iter(xs), true_sharpe=0.15, s=0.2, lower=lower, burn_in=20, max_n=150)
        state = vl.sprt_run([0.01 * (0.15 + e) for e in xs], s=0.2, alpha=0.05, beta=0.20, burn_in=20, max_n=150)
        assert (peak >= upper) == (state.decision == sp.ACCEPT_H1)


def test_calibration_keeps_wald_under_the_gaussian_model():
    out = vl.calibrate_upper_bound(seed=101, paths=2000, model=vl.iid_model(), **_CAL)
    assert out["status"] == "CALIBRATED"
    assert out["upper"] == pytest.approx(out["wald_upper"]) and out["false_accept"] <= 0.05


@pytest.mark.parametrize("name, model", [
    ("student_t3", vl.iid_model(vl.student_t_sampler(3))),
    ("garch_t3", vl.garch_t_model()),
])
def test_naive_wald_bound_over_accepts_and_calibration_restores_alpha(name, model):
    out = vl.calibrate_upper_bound(seed=101, paths=3000, model=model, **_CAL)
    assert out["false_accept_at_wald"] > 0.05, f"{name}: the naive Wald bound should over-accept at zero edge"
    assert out["status"] == "CALIBRATED" and out["upper"] > out["wald_upper"] and out["false_accept"] <= 0.05
    fresh = vl.simulate_model_error_rates(true_sharpe=0.0, upper=out["upper"], lower=out["lower"], seed=202,
                                          paths=2000, model=model, **_SIM)
    assert fresh["ACCEPT_H1"] <= 0.05 + 0.015, f"{name}: calibrated bound must hold out of sample"
    power = vl.simulate_model_error_rates(true_sharpe=0.2, upper=out["upper"], lower=out["lower"], seed=303,
                                          paths=800, model=model, **_SIM)
    assert power["ACCEPT_H1"] >= 1 - 0.20 - 0.03


def test_block_bootstrap_of_a_clustered_series_calibrates_without_weakening():
    rng = random.Random(5)
    gen = vl.garch_t_model()(rng)
    series = [next(gen) for _ in range(3000)]
    model = vl.stationary_bootstrap_model(series, mean_block=20)
    out = vl.calibrate_upper_bound(seed=404, paths=2000, model=model, **_CAL)
    assert out["status"] == "CALIBRATED" and out["upper"] >= out["wald_upper"] and out["false_accept"] <= 0.05
    fresh = vl.simulate_model_error_rates(true_sharpe=0.0, upper=out["upper"], lower=out["lower"], seed=505,
                                          paths=1500, model=model, **_SIM)
    assert fresh["ACCEPT_H1"] <= 0.05 + 0.015


def test_calibration_never_weakens_and_reports_failure_honestly():
    model = vl.garch_t_model()
    out = vl.calibrate_upper_bound(seed=101, paths=1000, model=model, ceiling=2.8, **_CAL)
    assert out["status"] == "NOT_CALIBRATABLE"
    for seed in (1, 2, 3):
        assert vl.calibrate_upper_bound(seed=seed, paths=500, model=vl.iid_model(), **_CAL)["upper"] >= \
            vl.sprt_bounds(0.05, 0.20)[0]


def test_calibration_and_models_are_deterministic_and_validated():
    kw = dict(seed=9, paths=300, model=vl.garch_t_model(), **_CAL)
    assert vl.calibrate_upper_bound(**kw) == vl.calibrate_upper_bound(**kw)
    with pytest.raises(ValueError):
        vl.garch_t_model(a=0.2, b=0.85)
    with pytest.raises(ValueError):
        vl.stationary_bootstrap_model([1.0] * 10)
    with pytest.raises(ValueError):
        vl.calibrate_upper_bound(seed=1, paths=10, model=vl.iid_model(), **_CAL)
