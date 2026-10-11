"""AUTH-2 gate constants are the Owner-frozen package's values (FUNNEL_LAW_2.md §COMMON_GATES,
family gates, §PRIMARY_CONFIGS, §ROBUSTNESS_PERTURBATIONS, §MULTIPLE_TESTING_LAW,
§POINT_IN_TIME_UNIVERSE_LAW), and every preregistration carries exactly the code's thresholds.

A value here can only change together with FUNNEL_LAW_2.md and an Owner merge.

PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from auth2 import families as F  # noqa: E402
from auth2 import gates as GT  # noqa: E402
from auth2 import run_node as RN  # noqa: E402
from auth2 import signals as S  # noqa: E402
from auth2 import universe as U  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def test_costs():
    assert GT.BASE_FEE == pytest.approx(0.0015)  # 0.10% fee + 0.05% slippage per side
    assert GT.STRESS_FEES == {"x2": pytest.approx(0.0030), "x3": pytest.approx(0.0045)}
    assert F.A2_EXTRA_SLIPPAGE == 0.0005 and F.A2_EXEMPT_RANKS == 6


def test_multiple_testing_and_gate_levels():
    assert (GT.ALPHA_HOLM, GT.HOLM_M, GT.ALPHA_PERTURBATION) == (0.05, 3, 0.10)
    assert (GT.C4_ALPHA, F.NULL_DRAWS, GT.DSR_THRESHOLD, GT.SPA_ALPHA, GT.PBO_BLOCKS) == (0.05, 1000, 0.95, 0.05, 16)
    assert GT.COVERAGE_MIN == {"A1": 100, "A2": 250, "A3": 6}
    assert (GT.A1_MIN_SLEEVE_DAYS, GT.A1_SLEEVES_POSITIVE) == (730, 4)
    assert (GT.A2_YEARS, GT.A2_YEARS_POSITIVE) == (list(range(2019, 2025)), 4)
    assert GT.A3_CVAR_LEVEL == 0.05
    assert (F.A1_EPISODE_LOOKBACK, F.A1_EPISODE_MIN_DAYS, F.A3_EPISODE_MERGE_DAYS) == (120, 60, 30)


def test_n_law_and_the_positive_count_rule():
    assert F.FAMILY_N == {"A1": 21, "A2": 6, "A3": 4}
    assert F.MIN_POSITIVE == {"A1": 4, "A2": 4, "A3": 2}
    assert {f: len(p) for f, p in F.PERTURBATIONS.items()} == {"A1": 5, "A2": 5, "A3": 3}
    assert 3 + sum(len(p) for p in F.PERTURBATIONS.values()) == 16  # configurations cap


def test_primary_configurations():
    assert S.A1_PRIMARY == {"lookbacks": [20, 60, 120], "target_vol": 0.25, "vol_window": 30, "sleeves": 6}
    assert S.A2_PRIMARY == {"lookback": 28, "skip": 1, "k": 3, "weekday": 0}
    a3 = S.A3_PRIMARY
    assert (a3["z_threshold"], a3["cut_to"], a3["target_vol"], a3["vol_window"], a3["m7_days"]) == \
        (2.0, 0.5, 0.25, 30, 7)


def test_precommitted_perturbations():
    assert F.PERTURBATIONS == {
        "A1": {"P1": {"lookbacks": [10, 20, 40]}, "P2": {"lookbacks": [40, 120, 250]}, "P3": {"target_vol": 0.15},
               "P4": {"target_vol": 0.40}, "P5": {"vol_window": 60}},
        "A2": {"P1": {"lookback": 14}, "P2": {"lookback": 56}, "P3": {"k": 2}, "P4": {"k": 5}, "P5": {"skip": 0}},
        "A3": {"P1": {"z_threshold": 1.5}, "P2": {"z_threshold": 2.5}, "P3": {"cut_to": 0.0}},
    }


def test_null_seeds_are_disjoint():
    c4 = set(F.C4_SEEDS)
    assert c4 == set(range(1, 1001)) and F.N_FIXTURE_SEED == 0
    for fam, seeds in F.N_PERTURBATION_SEEDS.items():
        assert len(seeds) == len(F.PERTURBATIONS[fam]) and not (set(seeds) & c4) and 0 not in seeds


def test_delisting_convention_and_data_limited_law():
    assert U.DELISTING_HAIRCUT == 0.80 and U.DIAGNOSTIC_HAIRCUTS == (1.00, 0.60)
    assert U.TERMINAL_LOOKBACK == 24 and U.DATA_LIMITED_THRESHOLD == 0.01


def test_terminal_price_trust_rule():
    hour = U.HOUR_MS
    opens = [i * hour for i in range(30)]
    assert U.terminal_trustworthy(opens, [1.0] * 30, 29)
    assert not U.terminal_trustworthy(opens, [1.0] * 10 + [0.0] + [1.0] * 19, 29)  # a zero-volume kline
    gap = opens[:20] + opens[21:]
    assert not U.terminal_trustworthy(gap, [1.0] * 29, 28)  # a missing kline


def test_windows():
    assert RN.SCORED == {"A1": (RN._ms(2019), RN._ms(2025)), "A2": (RN._ms(2019), RN._ms(2025))}
    assert RN.SECONDARY == (RN._ms(2025), RN._ms(2026, 9))
    lock = json.loads((REPO / "research/datasets/dataset_v3.lock.json").read_text())
    assert RN.scored("A3", REPO) == (RN._ms(2021, 2), RN._ms(2025))
    assert lock["a3_start_utc"] == "2021-02-01T00:00:00Z"


def test_every_preregistration_carries_the_code_thresholds():
    want = json.loads(json.dumps(RN.thresholds()))
    for p in sorted((REPO / "research/auth2/prereg").glob("*.json")):
        assert json.loads(p.read_text())["thresholds"] == want, p.name
