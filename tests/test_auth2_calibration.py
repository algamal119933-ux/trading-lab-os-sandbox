"""AUTH-2 calibration (FUNNEL_LAW_2.md §CALIBRATION_DAG, §CALIBRATION_POWER_PROOF): the Owner's δ,
world counts and thresholds, disjoint seeds, deterministic synthetic worlds, and a calibration
record that the preregistrations and the current generator code agree with.

The 200-year true-δ recomputation takes minutes per family, so it is not repeated here; the
record pins the sha256 of every file it depends on and this suite requires them unchanged.

PAPER / RESEARCH ONLY. Synthetic data only; the seeds used here are used by no AUTH-2 node.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

from auth2 import calibration as CA  # noqa: E402
from auth2 import synthetic as SY  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RECORD = json.loads((REPO / "research/auth2/calibration_edges.json").read_text())
A3_START = 1612137600000  # 2021-02-01, the lock's A3_START
TEST_SEED = 4242


def test_owner_decision_1():
    assert CA.DELTA == {"A1": 0.40, "A2": 0.40, "A3": 0.30}
    assert (CA.WORLDS, CA.SIZE_MAX_ACCEPTED, CA.POWER_MIN_ACCEPTED) == (200, 10, 160)
    assert CA.TRUE_DELTA_YEARS == 200 and CA.EDGE_TOLERANCE == 0.005


def test_seeds_are_disjoint():
    size, power = set(CA.SIZE_SEEDS), set(CA.POWER_SEEDS)
    assert len(size) == len(power) == 200 and not size & power
    assert CA.PC_SEED not in size | power
    assert CA.TRUE_DELTA_SEED > max(size | power | {CA.PC_SEED})
    assert TEST_SEED not in size | power | {CA.PC_SEED}


@pytest.mark.parametrize("fam", ["A1", "A2", "A3"])
def test_the_calibration_record(fam):
    rec = RECORD["families"][fam]
    assert rec["status"] == "OK" and rec["delta"] == CA.DELTA[fam]
    assert abs(rec["true_delta"] - rec["delta"]) <= CA.EDGE_TOLERANCE
    assert (rec["first_seed"], rec["years"]) == (CA.TRUE_DELTA_SEED, CA.TRUE_DELTA_YEARS)
    trace = sorted(rec["trace"])
    assert trace[-1][0] >= rec["edge"] >= trace[0][0]
    assert [rec["edge"], rec["true_delta"]] in rec["trace"]
    # the bisection steps are monotone in the edge strength (the premise of a bisection)
    deltas = [d for _, d in trace]
    assert all(b >= a - 1e-3 for a, b in zip(deltas, deltas[1:]))


def test_the_record_was_made_with_the_current_generator_code():
    for name, sha in RECORD["code_sha256"].items():
        assert hashlib.sha256((REPO / "research/auth2" / name).read_bytes()).hexdigest() == sha, name


@pytest.mark.parametrize("node", ["CAL-A1", "CAL-A2", "CAL-A3", "PC-A1", "PC-A2", "PC-A3"])
def test_preregistrations_carry_the_recorded_edge(node):
    pre = json.loads((REPO / f"research/auth2/prereg/{node}.json").read_text())
    rec = RECORD["families"][pre["family"]]
    cal = pre["calibration"]
    assert (cal["delta"], cal["edge"], cal["true_delta"]) == (rec["delta"], rec["edge"], rec["true_delta"])
    assert cal["record"]["sha256"] == hashlib.sha256(
        (REPO / "research/auth2/calibration_edges.json").read_bytes()).hexdigest()


@pytest.mark.parametrize("fam", ["A1", "A2", "A3"])
def test_worlds_are_a_pure_function_of_family_seed_and_edge(fam):
    end = SY._ms(SY.WORLD_START.replace(year=2019))
    a = SY.generate(fam, TEST_SEED, 0.0, end_ms=end)
    b = SY.generate(fam, TEST_SEED, 0.0, end_ms=end)
    assert all(a.bars[p].tobytes() == b.bars[p].tobytes() for p in a.market.pairs)
    c = SY.generate(fam, TEST_SEED + 1, 0.0, end_ms=end)
    assert any(a.bars[p].tobytes() != c.bars[p].tobytes() for p in a.market.pairs)
    assert len(a.market.pairs) == SY.N_ASSETS[fam]


def test_a3_no_edge_worlds_have_the_base_crash_probability_every_day():
    z = np.full((100, 2), 5.0)  # crowded every day
    p = SY.crash_schedule(z, 100, 2, 0.0)
    assert (p == SY.CRASH_P_BASE).all()
    hot = SY.crash_schedule(z, 100, 2, 0.1)
    assert (hot == SY.CRASH_P_BASE + 0.1).all()


def test_one_world_evaluation_is_deterministic():
    a = CA._one(("A3", TEST_SEED, 0.0, A3_START))
    b = CA._one(("A3", TEST_SEED, 0.0, A3_START))
    assert a == b and a["seed"] == TEST_SEED and isinstance(a["accepted"], bool)
