"""AUTH-2 statistics: the arch pin, the frozen block-length rule, the paired bootstrap, Holm,
DSR/PBO wrappers and the exact intervals (research/auth2/FUNNEL_LAW_2.md §BOOTSTRAP_RULE,
§MULTIPLE_TESTING_LAW, §CALIBRATION_POWER_PROOF).

Fixed test vectors: a changed library, seed handling or formula changes a number here.

PAPER / RESEARCH ONLY. Synthetic numbers only.
"""

from __future__ import annotations

import hashlib
import math

import pytest

np = pytest.importorskip("numpy")
arch = pytest.importorskip("arch")

from auth2 import stats as ST  # noqa: E402


def vector():
    rng = np.random.default_rng(20261010)
    x = rng.standard_t(4, size=1500) * 0.02
    d = x[1:] + 0.3 * x[:-1]
    a = rng.standard_normal(1000) * 0.02 + 0.0006
    b = 0.7 * a + rng.standard_normal(1000) * 0.01
    return d, a, b


def test_arch_is_the_pinned_version():
    assert arch.__version__ == "8.0.0"


def test_optimal_block_length_test_vector():
    from arch.bootstrap import optimal_block_length

    d, _, _ = vector()
    got = optimal_block_length(d).to_dict()
    assert got["stationary"][0] == pytest.approx(6.089460604773656, rel=1e-9)
    assert got["circular"][0] == pytest.approx(6.97069228375183, rel=1e-9)


def test_block_length_rule_on_the_test_vector():
    d, _, _ = vector()
    res = ST.block_length(d)
    assert res["status"] == "OK"
    assert res["b_d"] == pytest.approx(6.089460604773656, rel=1e-9)
    assert res["b_d2"] == pytest.approx(3.213149095778505, rel=1e-9)
    assert res["b"] == 6  # round_half_up(max(6.09, 3.21)) = 6, inside [5, 60]


@pytest.mark.parametrize("x,expected", [(4.5, 5), (5.49, 5), (5.5, 6), (59.5, 60), (0.0, 0)])
def test_round_half_up(x, expected):
    assert ST.round_half_up(x) == expected


def test_block_length_clamps_and_never_falls_back():
    rng = np.random.default_rng(3)
    iid = rng.standard_normal(2000)
    assert ST.block_length(iid)["b"] == ST.BLOCK_MIN  # an IID series estimates ~1-2 days
    persistent = np.cumsum(rng.standard_normal(4000)) * 1e-3
    assert ST.block_length(persistent)["b"] == ST.BLOCK_MAX
    bad = iid.copy()
    bad[5] = np.nan
    assert ST.block_length(bad)["status"] == ST.NOT_EVALUABLE


def test_the_frozen_constants():
    assert (ST.RESAMPLES, ST.BLOCK_MIN, ST.BLOCK_MAX) == (10_000, 5, 60)
    assert ST.SENSITIVITY_BLOCKS == (5, 20, 60)
    assert ST.SPA_VOL_TARGET == 0.20
    assert ST.ANN == math.sqrt(365.0)


def test_stationary_indices_are_a_fixed_function_of_the_seed():
    idx = ST.stationary_indices(50, 5, 3, 11)
    assert idx.shape == (3, 50)
    assert hashlib.sha256(np.ascontiguousarray(idx).tobytes()).hexdigest() == \
        "3fe34ddb5803d60a11407c1d73a8df80fc8cd687d6f194605644bd091b04caa8"


def test_paired_bootstrap_test_vector_and_determinism():
    _, a, b = vector()
    blk = ST.block_length(a - b)["b"]
    r1 = ST.delta_sr_test(a, b, blk, "greater", 7)
    r2 = ST.delta_sr_test(a, b, blk, "greater", 7)
    assert r1 == r2
    assert r1["status"] == "OK" and r1["b"] == 5
    assert r1["delta_sr"] == pytest.approx(0.16840788174769208, rel=1e-9)
    assert r1["p_value"] == pytest.approx(0.3257674232576742, abs=0)


def test_paired_bootstrap_detects_a_large_difference_and_never_returns_zero():
    rng = np.random.default_rng(5)
    b = rng.standard_normal(2000) * 0.02
    a = b + 0.004 + rng.standard_normal(2000) * 0.002
    res = ST.delta_sr_test(a, b, 5, "greater", 1, reps=2000)
    assert res["status"] == "OK"
    assert res["p_value"] == pytest.approx(1 / 2001)  # (1 + 0) / (1 + B): never zero
    less = ST.delta_sr_test(a, b, 5, "less", 1, reps=2000)
    assert less["p_value"] > 0.9


def test_paired_bootstrap_is_not_evaluable_on_degenerate_input():
    a = np.full(500, 0.001)
    b = np.random.default_rng(1).standard_normal(500)
    assert ST.delta_sr_test(a, b, 5, "greater", 1)["status"] == ST.NOT_EVALUABLE
    assert ST.delta_sr_test(b[:8], b[:8] * 2, 5, "greater", 1)["status"] == ST.NOT_EVALUABLE
    with pytest.raises(ValueError):
        ST.delta_sr_test(b, b, 5, "two-sided", 1)


def test_spa_test_vector():
    _, a, b = vector()
    res = ST.spa_pvalue(b, np.column_stack([a, a * 0.5 + b * 0.5]), 10, 7, reps=2000)
    assert res["status"] == "OK"
    assert res["p_value"] == pytest.approx(0.3295, abs=0)


@pytest.mark.parametrize("p,expected", [
    ({"A1": 0.01, "A2": 0.02, "A3": 0.04}, {"A1": True, "A2": True, "A3": True}),
    ({"A1": 0.016, "A2": 0.03, "A3": 1.0}, {"A1": True, "A2": False, "A3": False}),
    ({"A1": 0.02, "A2": 0.001, "A3": 1.0}, {"A1": True, "A2": True, "A3": False}),
    ({"A1": 0.0167, "A2": 1.0, "A3": 1.0}, {"A1": False, "A2": False, "A3": False}),
])
def test_holm_step_down_m3_fwer_005(p, expected):
    assert ST.holm(p, 0.05) == expected


def test_clopper_pearson_at_the_law_thresholds():
    lo, hi = ST.clopper_pearson(10, 200)
    assert (round(lo, 3), round(hi, 3)) == (0.024, 0.090)
    lo, hi = ST.clopper_pearson(160, 200)
    assert (round(lo, 3), round(hi, 3)) == (0.738, 0.853)


def test_tail_statistics():
    r = np.array([0.1, -0.5, 0.2, -0.1])
    # equity 1, 1.1, 0.55, 0.66, 0.594: the worst loss from the 1.1 peak is to 0.55
    assert ST.max_drawdown(r) == pytest.approx(0.5)
    assert ST.total_return(r) == pytest.approx(0.594 - 1)
    worst = np.arange(-50, 50) / 1000.0
    assert ST.cvar(worst, 0.05) == pytest.approx(np.mean(worst[:5]))  # ceil(0.05 x 100) = 5 lowest days
    assert math.isnan(ST.sharpe(np.zeros(10)))
