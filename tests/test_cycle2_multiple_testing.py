"""CYCLE-2 UNIT 7.1 — trialgate==0.5.0 audit (A2–A4, A6) and the §6.3 wrapper.

Reference values come from two places, with the tolerance for each stated in
research/cycle2/TRIALGATE_AUDIT_1.md before these tests were run:

(a) the worked numeric example in Bailey & López de Prado (2014), "The Deflated
    Sharpe Ratio", and the definitional limiting cases of CSCV/PBO in Bailey,
    Borwein, López de Prado & Zhu (2015) — that paper's own results are Monte
    Carlo, so no closed-form worked example exists to reproduce;
(b) an independent from-formula reference implementation written only in this
    file (standard library only — not a second library), on fixed synthetic
    inputs.

Every threshold below is a TEST FIXTURE that exercises a branch. None of them is
a research threshold; those come only from a preregistration.

Tests that need trialgate itself skip where it is not installed (the CI image
installs requirements-dev.txt only); the wrapper's own precondition branches
and the static scans run everywhere.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import math
import random
import statistics
import subprocess
import sys
from itertools import combinations
from pathlib import Path

import pytest

from cycle2 import multiple_testing as mt

REPO_ROOT = Path(__file__).resolve().parents[1]
CYCLE2_DIR = REPO_ROOT / "research" / "cycle2"
LEDGER = REPO_ROOT / "research" / "records" / "trial_ledger.jsonl"

try:
    import trialgate  # noqa: F401
    from trialgate import validation as tg_validation

    HAVE_TRIALGATE = True
except ImportError:  # pragma: no cover - exercised in the CI image
    HAVE_TRIALGATE = False

needs_trialgate = pytest.mark.skipif(not HAVE_TRIALGATE, reason="trialgate==0.5.0 not installed here")

# Tolerances, as recorded in TRIALGATE_AUDIT_1.md §A2 before running.
PAPER_TOL = 5e-5        # the paper prints 4 decimals
REFERENCE_TOL = 1e-12   # same formula, different float summation order
PBO_TOL = 0.0           # PBO is a ratio of integer counts: exact

EULER_GAMMA = 0.5772156649015329


# -- (b) independent reference implementations -------------------------------


def _mean(xs):
    return sum(xs) / len(xs)


def ref_expected_max_sharpe(trial_sharpes_annual, periods_per_year, n_trials):
    """E[max SR] of N noise trials (DSR paper, eq. for SR0), per-period units."""
    m = _mean(trial_sharpes_annual)
    var = sum((s - m) ** 2 for s in trial_sharpes_annual) / len(trial_sharpes_annual) / periods_per_year
    if n_trials == 1 or var == 0.0:
        return 0.0
    z = statistics.NormalDist().inv_cdf
    return math.sqrt(var) * ((1 - EULER_GAMMA) * z(1 - 1 / n_trials)
                             + EULER_GAMMA * z(1 - 1 / (n_trials * math.e)))


def ref_dsr_from_moments(sr, sr0, t, skew, kurt):
    """DSR = Phi[(SR - SR0) sqrt(T-1) / sqrt(1 - g3 SR + (g4-1)/4 SR^2)]."""
    stat = (sr - sr0) * math.sqrt(t - 1) / math.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr * sr)
    return statistics.NormalDist().cdf(stat)


def ref_dsr(returns, trial_sharpes_annual, periods_per_year, n_trials):
    t = len(returns)
    m = _mean(returns)
    dev = [x - m for x in returns]
    sample_sd = math.sqrt(sum(d * d for d in dev) / (t - 1))
    pop_sd = math.sqrt(sum(d * d for d in dev) / t)
    skew = sum((d / pop_sd) ** 3 for d in dev) / t
    kurt = sum((d / pop_sd) ** 4 for d in dev) / t
    sr = m / sample_sd
    sr0 = ref_expected_max_sharpe(trial_sharpes_annual, periods_per_year, n_trials)
    return ref_dsr_from_moments(sr, sr0, t, skew, kurt), sr0


def ref_pbo(matrix, s):
    """CSCV straight from the definition, on raw rows, no block statistics.

    Rows split into S contiguous equal blocks (trailing T mod S dropped, as the
    package documents); for every C(S, S/2) train set: n* = in-sample argmax of
    Sharpe (mean / sample stdev), omega = OOS rank of n* / (N + 1),
    lambda = ln(omega / (1 - omega)); PBO = share of lambda <= 0.
    """
    t = len(matrix) - len(matrix) % s
    size = t // s
    n = len(matrix[0])
    blocks = [matrix[b * size:(b + 1) * size] for b in range(s)]

    def sharpe(rows, col):
        xs = [r[col] for r in rows]
        if len(xs) < 2:
            return 0.0
        m = _mean(xs)
        var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
        return m / math.sqrt(var) if var > 0 else 0.0

    overfit = total = 0
    for train in combinations(range(s), s // 2):
        test = [b for b in range(s) if b not in train]
        train_rows = [r for b in train for r in blocks[b]]
        test_rows = [r for b in test for r in blocks[b]]
        is_sr = [sharpe(train_rows, c) for c in range(n)]
        oos_sr = [sharpe(test_rows, c) for c in range(n)]
        best = is_sr.index(max(is_sr))
        rank = sum(1 for v in oos_sr if v <= oos_sr[best])
        omega = rank / (n + 1)
        lam = math.log(omega / (1 - omega))
        overfit += lam <= 0
        total += 1
    return overfit / total


def synthetic_returns(seed, n=750, mu=0.0006, sigma=0.012, skewed=False):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        x = rng.gauss(mu, sigma)
        if skewed and rng.random() < 0.03:
            x -= 4 * sigma
        out.append(x)
    return out


def synthetic_matrix(seed, t, n, persistence=0.0):
    rng = random.Random(seed)
    edge = [rng.gauss(0, 0.0005) for _ in range(n)]
    return [[persistence * edge[c] + rng.gauss(0.0, 0.01) for c in range(n)] for _ in range(t)]


# -- A2(a): the DSR paper's worked example ------------------------------------
# Bailey & López de Prado (2014), numerical example: N = 100 trials, variance of
# the trials' annualized Sharpe = 1/2, T = 1250 daily observations (250/yr),
# annualized SR = 2.5, skewness = -3, kurtosis = 10 → SR0 ≈ 0.1132, DSR ≈ 0.9004.

PAPER_N, PAPER_V, PAPER_PPY, PAPER_T = 100, 0.5, 250, 1250
PAPER_SR_ANNUAL, PAPER_SKEW, PAPER_KURT = 2.5, -3.0, 10.0
PAPER_TRIAL_SHARPES = [PAPER_SR_ANNUAL - math.sqrt(PAPER_V), PAPER_SR_ANNUAL + math.sqrt(PAPER_V)]


def test_reference_reproduces_the_dsr_paper_example():
    sr0 = ref_expected_max_sharpe(PAPER_TRIAL_SHARPES, PAPER_PPY, PAPER_N)
    sr = PAPER_SR_ANNUAL / math.sqrt(PAPER_PPY)
    assert abs(sr0 - 0.1132) <= PAPER_TOL
    assert abs(ref_dsr_from_moments(sr, sr0, PAPER_T, PAPER_SKEW, PAPER_KURT) - 0.9004) <= PAPER_TOL


@needs_trialgate
def test_trialgate_expected_max_sharpe_matches_the_dsr_paper_example():
    # SR0 depends only on N and the trials' Sharpe variance, so the paper's
    # value is checkable against trialgate directly, not only via the reference.
    returns = synthetic_returns(1, n=50)
    got = tg_validation.deflated_sharpe_ratio(
        returns, trial_sharpes=PAPER_TRIAL_SHARPES, periods_per_year=PAPER_PPY,
        effective_trials=PAPER_N).expected_max_sharpe
    assert abs(got - 0.1132) <= PAPER_TOL
    assert abs(got - ref_expected_max_sharpe(PAPER_TRIAL_SHARPES, PAPER_PPY, PAPER_N)) <= REFERENCE_TOL


# -- A2(b): trialgate against the independent reference -----------------------

DSR_CASES = [
    (11, False, [0.4, 1.1, -0.3, 0.8, 1.6], 5),
    (12, True, [0.2, 0.9, 1.3], 24),
    (13, False, [1.0, 1.0001], 1),
    (14, True, [-0.5, 0.0, 0.5, 1.0, 1.5, 2.0], 120),
]


@needs_trialgate
@pytest.mark.parametrize("seed,skewed,trial_sharpes,n_trials", DSR_CASES)
def test_trialgate_dsr_matches_the_reference(seed, skewed, trial_sharpes, n_trials):
    returns = synthetic_returns(seed, skewed=skewed)
    got = tg_validation.deflated_sharpe_ratio(returns, trial_sharpes=trial_sharpes,
                                              periods_per_year=365, effective_trials=n_trials)
    want, want_sr0 = ref_dsr(returns, trial_sharpes, 365, n_trials)
    assert abs(got.deflated_sharpe_ratio - want) <= REFERENCE_TOL
    assert abs(got.expected_max_sharpe - want_sr0) <= REFERENCE_TOL
    assert got.observations == len(returns)


PBO_CASES = [(21, 64, 4, 4, 0.0), (22, 96, 6, 8, 0.0), (23, 130, 10, 8, 1.0),
             (24, 160, 5, 10, 3.0), (25, 33, 3, 2, 0.0)]


@needs_trialgate
@pytest.mark.parametrize("seed,t,n,s,persistence", PBO_CASES)
def test_trialgate_pbo_matches_the_reference(seed, t, n, s, persistence):
    matrix = synthetic_matrix(seed, t, n, persistence)
    got = tg_validation.probability_of_backtest_overfitting(matrix, block_count=s)
    assert abs(got.pbo - ref_pbo(matrix, s)) <= PBO_TOL
    assert got.observations == t - t % s
    assert got.combinations_evaluated == math.comb(s, s // 2)


@needs_trialgate
def test_pbo_definitional_limits_from_the_cscv_paper():
    # One configuration dominates in every block: the IS winner is the OOS
    # winner in every split, so lambda > 0 always and PBO = 0.
    rng = random.Random(31)
    dominant = [[0.02 + rng.gauss(0, 0.001)] + [rng.gauss(0, 0.001) for _ in range(3)] for _ in range(40)]
    assert tg_validation.probability_of_backtest_overfitting(dominant, block_count=4).pbo == 0.0
    assert ref_pbo(dominant, 4) == 0.0
    # Perfect anti-persistence: whatever wins in-sample loses out-of-sample in
    # every split, so lambda <= 0 always and PBO = 1.
    anti = ([[0.01 + 0.001 * (i % 2), -0.01 - 0.001 * (i % 2)] for i in range(10)]
            + [[-0.01 - 0.001 * (i % 2), 0.01 + 0.001 * (i % 2)] for i in range(10)])
    assert tg_validation.probability_of_backtest_overfitting(anti, block_count=2).pbo == 1.0
    assert ref_pbo(anti, 2) == 1.0


# -- A3: determinism ----------------------------------------------------------

_DETERMINISM_SNIPPET = r"""
import random, sys
from trialgate import validation as v
rng = random.Random(7)
r = [rng.gauss(0.0005, 0.01) for _ in range(500)]
m = [[rng.gauss(0, 0.01) for _ in range(6)] for _ in range(96)]
d = v.deflated_sharpe_ratio(r, trial_sharpes=[0.3, 0.9, 1.4], periods_per_year=365, effective_trials=12)
q = v.observations_required_for_dsr(r, trial_sharpes=[0.3, 0.9, 1.4], periods_per_year=365,
                                    effective_trials=12, target_dsr=0.9)
p = v.probability_of_backtest_overfitting(m, block_count=8)
print(d.deflated_sharpe_ratio.hex(), d.expected_max_sharpe.hex(), q, p.pbo.hex(), p.combinations_evaluated)
"""


@needs_trialgate
def test_identical_inputs_give_bit_identical_outputs_in_process():
    returns = synthetic_returns(41)
    matrix = synthetic_matrix(42, 96, 6)
    first = [tg_validation.deflated_sharpe_ratio(returns, trial_sharpes=[0.3, 0.9], periods_per_year=365,
                                                 effective_trials=7).deflated_sharpe_ratio.hex(),
             tg_validation.probability_of_backtest_overfitting(matrix, block_count=8).pbo.hex()]
    for _ in range(5):
        again = [tg_validation.deflated_sharpe_ratio(returns, trial_sharpes=[0.3, 0.9], periods_per_year=365,
                                                     effective_trials=7).deflated_sharpe_ratio.hex(),
                 tg_validation.probability_of_backtest_overfitting(matrix, block_count=8).pbo.hex()]
        assert again == first


@needs_trialgate
def test_identical_inputs_give_bit_identical_outputs_across_two_fresh_processes():
    outs = [subprocess.run([sys.executable, "-c", _DETERMINISM_SNIPPET], capture_output=True,
                           text=True, check=True).stdout for _ in range(2)]
    assert outs[0] and outs[0] == outs[1]


@needs_trialgate
def test_pbo_has_no_internal_randomness():
    # Proven, not seeded: the module neither imports a RNG nor reads time or
    # entropy, and CSCV enumerates every combination rather than sampling.
    tree = ast.parse(inspect.getsource(tg_validation))
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert imported.isdisjoint({"random", "secrets", "time", "os", "uuid", "numpy"}), imported


# -- A1 echo + A4: pin and caller-supplied thresholds ---------------------------


@needs_trialgate
def test_installed_trialgate_is_the_pinned_version_with_no_runtime_dependencies():
    from importlib import metadata

    assert metadata.version("trialgate") == "0.5.0"
    requires = metadata.requires("trialgate") or []
    assert all("extra ==" in r for r in requires), requires


def test_research_requirements_pin_trialgate_with_both_audited_hashes():
    lines = [ln for ln in (REPO_ROOT / "research" / "requirements.txt").read_text().splitlines()
             if ln.startswith("trialgate")]
    assert lines == [
        "trialgate==0.5.0"
        " --hash=sha256:30c4ac41342b0477a4ed7954ef7de1a4ab53af435c5498f5ce3d59b8d7b8db1d"
        " --hash=sha256:22e2933ce685cc75e093a9df75beb9b8b54728d1013b2e81d2af8b0379f1f710"
    ]


def test_calling_without_thresholds_raises():
    with pytest.raises(TypeError):
        mt.dsr([0.1, 0.2, 0.3], trial_sharpes=[0.1, 0.2], periods_per_year=365, effective_trials=2)
    with pytest.raises(TypeError):
        mt.pbo([[0.1, 0.2]] * 4, block_count=2)


@pytest.mark.parametrize("bad", [None, True, "0.95", float("nan"), float("inf"), 0.0, 1.0, -0.1, 1.5])
def test_a_missing_or_unusable_threshold_raises_rather_than_defaulting(bad):
    with pytest.raises(mt.ThresholdRequiredError):
        mt.dsr([0.1, 0.2, 0.3], trial_sharpes=[0.1, 0.2], periods_per_year=365,
               effective_trials=2, threshold=bad)
    with pytest.raises(mt.ThresholdRequiredError):
        mt.pbo([[0.1, 0.2]] * 4, block_count=2, threshold=bad)


def test_the_wrapper_never_reads_package_default_thresholds():
    source = (CYCLE2_DIR / "multiple_testing.py").read_text(encoding="utf-8")
    for name in ("DEFAULT_MAX_PBO", "DEFAULT_MIN_DSR", "DEFAULT_MIN_OBSERVATIONS", "DEFAULT_MAX_STOP_BREACH"):
        assert name not in source
    signature = inspect.signature(mt.dsr)
    assert signature.parameters["threshold"].default is inspect.Parameter.empty
    assert signature.parameters["effective_trials"].default is inspect.Parameter.empty
    assert inspect.signature(mt.pbo).parameters["threshold"].default is inspect.Parameter.empty
    assert inspect.signature(mt.pbo).parameters["block_count"].default is inspect.Parameter.empty


@needs_trialgate
def test_the_threshold_actually_decides_the_status():
    # Same data, two fixture thresholds either side of the measured value.
    returns = synthetic_returns(51, n=2000, mu=0.002)
    low = mt.dsr(returns, trial_sharpes=[0.2, 0.6], periods_per_year=365, effective_trials=3, threshold=0.6)
    assert low["status"] == mt.PASS
    matrix = synthetic_matrix(52, 96, 6)
    value = mt.pbo(matrix, block_count=8, threshold=0.99)["value"]
    assert 0.0 < value < 0.99
    assert mt.pbo(matrix, block_count=8, threshold=0.99)["status"] == mt.PASS
    assert mt.pbo(matrix, block_count=8, threshold=value / 2)["status"] == mt.FAIL


# -- the NOT_EVALUABLE law: every branch, never PASS ----------------------------

GOOD = synthetic_returns(61, n=400)
TS = [0.3, 0.9, 1.4]


@pytest.mark.parametrize("kwargs,why", [
    ({"returns": [0.01, 0.02]}, "too few observations"),
    ({"returns": [0.01] * 50}, "constant"),
    ({"returns": GOOD[:-1] + [float("nan")]}, "finite"),
    ({"returns": GOOD[:-1] + [float("inf")]}, "finite"),
    ({"returns": "not-a-list"}, "finite"),
    ({"trial_sharpes": [0.3, float("nan")]}, "finite"),
    ({"trial_sharpes": [0.9]}, "not estimable"),
    ({"trial_sharpes": [0.9, 0.9, 0.9]}, "not estimable"),
    ({"effective_trials": 0}, "effective_trials"),
    ({"effective_trials": 2.5}, "effective_trials"),
    ({"periods_per_year": 0}, "periods_per_year"),
])
def test_dsr_precondition_branches_are_not_evaluable(kwargs, why):
    args = {"returns": GOOD, "trial_sharpes": TS, "periods_per_year": 365, "effective_trials": 12}
    args.update(kwargs)
    out = mt.dsr(args.pop("returns"), threshold=0.9, **args)
    assert out["status"] == mt.NOT_EVALUABLE
    assert why in out["reason"]
    assert set(out) == {"status", "value", "threshold", "effective_trials", "observations", "reason"}


@needs_trialgate
def test_dsr_too_few_observations_by_the_inversion_is_not_evaluable():
    rng = random.Random(71)
    short = [rng.gauss(0.002, 0.01) for _ in range(40)]
    out = mt.dsr(short, trial_sharpes=[0.1, 0.3], periods_per_year=365, effective_trials=2, threshold=0.99)
    assert out["status"] == mt.NOT_EVALUABLE
    assert "required" in out["reason"]
    assert out["value"] is not None and out["value"] < 0.99


@needs_trialgate
def test_dsr_trialgate_input_error_is_not_evaluable(monkeypatch):
    # trialgate refuses when the Mertens variance term 1 - g3*SR + (g4-1)/4*SR^2
    # is <= 0. With population moments Pearson's inequality (g4 >= g3^2 + 1)
    # keeps that term >= 0, so real data cannot reach the refusal (audit
    # finding A2.4); the catch-all branch is proven by forcing the error.
    def refuse(*_a, **_k):
        raise tg_validation.ValidationInputError("Mertens variance term <= 0 (forced)")

    monkeypatch.setattr(tg_validation, "deflated_sharpe_ratio", refuse)
    out = mt.dsr(GOOD, trial_sharpes=TS, periods_per_year=365, effective_trials=3, threshold=0.9)
    assert out["status"] == mt.NOT_EVALUABLE
    assert "trialgate input error" in out["reason"]


@needs_trialgate
@pytest.mark.parametrize("seed", range(5))
def test_the_mertens_term_is_non_negative_on_any_sample(seed):
    rng = random.Random(seed)
    sample = [rng.choice([-1.0, 0.0, 3.0, 25.0]) * rng.random() for _ in range(60)]
    m = _mean(sample)
    psd = math.sqrt(sum((x - m) ** 2 for x in sample) / len(sample))
    skew = sum(((x - m) / psd) ** 3 for x in sample) / len(sample)
    kurt = sum(((x - m) / psd) ** 4 for x in sample) / len(sample)
    assert kurt >= skew * skew + 1 - 1e-9


@needs_trialgate
def test_dsr_beaten_by_chance_is_fail_not_not_evaluable():
    losing = synthetic_returns(72, n=400, mu=-0.002)
    out = mt.dsr(losing, trial_sharpes=TS, periods_per_year=365, effective_trials=12, threshold=0.9)
    assert out["status"] == mt.FAIL


@pytest.mark.parametrize("matrix,block_count,why", [
    ([[0.1, 0.2]] * 8, 3, "even integer"),
    ([[0.1, 0.2]] * 8, 0, "even integer"),
    ([[0.1, 0.2]] * 8, 2.0, "integer"),
    ([], 2, "rectangular"),
    ([[0.1, 0.2], [0.1]], 2, "rectangular"),
    ([[0.1, float("nan")], [0.2, 0.3]], 2, "non-finite"),
    ([[0.1], [0.2], [0.3], [0.4]], 2, "too few configurations"),
    ([[0.1, 0.2], [0.3, 0.1], [0.2, 0.2]], 4, "too few observations"),
    ([[0.0, float(i)] for i in range(8)], 2, "degenerate"),
    ([[1.0, 1.0]] * 8, 2, "degenerate"),
])
def test_pbo_precondition_branches_are_not_evaluable(matrix, block_count, why):
    out = mt.pbo(matrix, block_count=block_count, threshold=0.5)
    assert out["status"] == mt.NOT_EVALUABLE
    assert why in out["reason"]
    assert out["value"] is None


@needs_trialgate
def test_pbo_trialgate_input_error_is_not_evaluable(monkeypatch):
    # Every input error trialgate itself can raise is pre-empted above; the
    # catch-all branch is still proven by forcing one.
    def refuse(*_a, **_k):
        raise tg_validation.ValidationInputError("forced")

    monkeypatch.setattr(tg_validation, "probability_of_backtest_overfitting", refuse)
    out = mt.pbo(synthetic_matrix(81, 32, 3), block_count=4, threshold=0.5)
    assert out["status"] == mt.NOT_EVALUABLE and "trialgate input error" in out["reason"]


@needs_trialgate
def test_pbo_dropped_rows_are_disclosed_not_padded():
    out = mt.pbo(synthetic_matrix(82, 35, 3), block_count=4, threshold=0.99)
    assert out["observations"] == 32
    assert "3 most-recent row(s) excluded" in out["reason"]


# -- trial counts come from the canonical ledger only, read-only ------------------


def test_family_trial_count_reads_the_canonical_ledger_without_writing_it():
    before = hashlib.sha256(LEDGER.read_bytes()).hexdigest()
    assert mt.ledger_family_trial_count("BTSL_EMA_REGIME") == 3
    assert mt.ledger_family_trial_count("PIPELINE_NULL_CALIBRATION") == 6
    assert mt.ledger_family_trial_count("NO_SUCH_FAMILY") == 0
    assert hashlib.sha256(LEDGER.read_bytes()).hexdigest() == before


def test_family_trial_count_refuses_a_ledger_that_does_not_verify(tmp_path):
    bad = tmp_path / "ledger.jsonl"
    lines = LEDGER.read_text(encoding="utf-8").splitlines()
    bad.write_text("\n".join([lines[1], lines[0]]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not verify"):
        mt.ledger_family_trial_count("BTSL_EMA_REGIME", bad)


# -- A6: forbidden trialgate surfaces are never imported ---------------------------

FORBIDDEN_TRIALGATE = {"trialgate.registry", "trialgate.holdout", "trialgate.gates",
                       "trialgate.risk", "trialgate.demo", "trialgate.__main__"}


def _trialgate_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names if a.name.split(".")[0] == "trialgate"}
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "trialgate":
            if node.module == "trialgate":
                found |= {f"trialgate.{a.name}" for a in node.names}
            else:
                found |= {f"{node.module}:{a.name}" for a in node.names}
                found.add(node.module)
    return found


def test_research_cycle2_never_imports_trialgate_registry_holdout_or_gates():
    files = sorted(CYCLE2_DIR.glob("*.py"))
    assert files
    for path in files:
        imports = _trialgate_imports(path)
        assert imports.isdisjoint(FORBIDDEN_TRIALGATE), (path.name, imports)
        modules = {i.split(":")[0] for i in imports}
        assert modules <= {"trialgate.validation"}, (path.name, imports)
        source = path.read_text(encoding="utf-8")
        for token in ("importlib", "__import__", "append_trial", "spend_holdout", "evaluate_gates",
                      "evaluate_registry", "initialize_holdout"):
            assert token not in source, (path.name, token)


def test_the_scan_itself_catches_a_forbidden_import(tmp_path):
    probe = tmp_path / "probe.py"
    probe.write_text("from trialgate import registry\nimport trialgate.holdout\n"
                     "from trialgate.gates import evaluate_gates\n", encoding="utf-8")
    assert {"trialgate.registry", "trialgate.holdout", "trialgate.gates"} <= _trialgate_imports(probe)
