# TRIALGATE-AUDIT-1 — trialgate==0.5.0 (CYCLE-2 UNIT 7.1)

**Authority:** research/OFFLINE_RESEARCH_CYCLE_2_OPENING_1.md §6.3 and §7.1 (merged PR #42, main
`4bbb1df6e866d657b9e486ca683c30fef4133035`), under research/OFFLINE_RESEARCH_AUTHORITY_1.md.
**Classification:** software audit. Calibration budget, but no trial ID was opened: 0 engine backtests,
0 ledger appends, 0 market data. **Budget consumed: NONE.**
**Date:** 2026-10-01.

## Verdict

**TRIALGATE_VERDICT = ADOPT_VALIDATION_ONLY.** Only `trialgate.validation` is used:
`deflated_sharpe_ratio`, `observations_required_for_dsr` and `probability_of_backtest_overfitting`.
`registry`, `holdout`, `gates` (and `risk`, `demo`, `__main__`) are FORBIDDEN. The canonical, and only,
trial-count authority stays `research/trial_ledger.py`. `arch` stays DEFER.

Pinned in research/requirements.txt as one line, both hashes:

```
trialgate==0.5.0 --hash=sha256:30c4ac41342b0477a4ed7954ef7de1a4ab53af435c5498f5ce3d59b8d7b8db1d --hash=sha256:22e2933ce685cc75e093a9df75beb9b8b54728d1013b2e81d2af8b0379f1f710
```

## A1 — Pin

| artifact | expected sha256 | observed sha256 | result |
|---|---|---|---|
| trialgate-0.5.0.tar.gz | 30c4ac41342b0477a4ed7954ef7de1a4ab53af435c5498f5ce3d59b8d7b8db1d | 30c4ac41342b0477a4ed7954ef7de1a4ab53af435c5498f5ce3d59b8d7b8db1d | PASS |
| trialgate-0.5.0-py3-none-any.whl | 22e2933ce685cc75e093a9df75beb9b8b54728d1013b2e81d2af8b0379f1f710 | 22e2933ce685cc75e093a9df75beb9b8b54728d1013b2e81d2af8b0379f1f710 | PASS |

Both were downloaded from files.pythonhosted.org (the URLs PyPI's JSON API lists for 0.5.0) and hashed
before any import. The source was read from the sdist first, then installed with
`--require-hashes` from a requirements line carrying both hashes. The PyPI JSON digests matched too.

- License: **MIT** (`LICENSE`, `pyproject.toml` `license = { text = "MIT" }`; copyright Tsai Chih-Chun).
- Runtime dependencies: **none**. `dependencies = []`; `requires_dist` has only `extra == "dev"` entries
  (pytest, ruff, mypy). `trialgate/validation.py` imports only the standard library: `math`,
  `statistics`, `collections.abc`, `dataclasses`, `itertools`. `requires-python >= 3.11`.
- Import side effects: importing `trialgate.validation` runs `trialgate/__init__.py`, which **loads**
  `registry`, `holdout`, `gates` and `risk` (definitions and four `DEFAULT_*` constants only). It does no
  I/O, opens no network connection and writes no file at import. Loading is not use: §A6 proves
  research/cycle2 never imports or calls them.

## A2 — Reference values

**Tolerances, stated before the run:**

| comparison | tolerance | why |
|---|---|---|
| vs the DSR paper's printed example | abs 5e-5 | the paper prints 4 decimals |
| trialgate DSR / SR0 vs the in-test reference | abs 1e-12 | same formula; only float summation order differs |
| trialgate PBO vs the in-test reference | exact (0) | PBO is a ratio of integer counts |

**(a) Papers.**

1. Bailey, D. H. & López de Prado, M. (2014), "The Deflated Sharpe Ratio: Correcting for Selection
   Bias, Backtest Overfitting and Non-Normality", *Journal of Portfolio Management* 40(5), numerical
   example. The inputs are N = 100 trials, a variance of the trials' annualized Sharpe of 1/2,
   T = 1250 daily observations (250 per year), annualized SR 2.5, skewness −3 and kurtosis 10.
   The paper reports SR0 ≈ 0.1132 and DSR ≈ 0.9004.
   - In-test reference: SR0 = 0.113172, DSR = 0.900397. **PASS** (both within 5e-5).
   - trialgate's `expected_max_sharpe` on the same N, variance and periods: 0.113172. It matches the
     paper within 5e-5 and the reference within 1e-12. **PASS.**
   - trialgate takes raw returns and computes skew and kurtosis itself, so the paper's full DSR cannot be
     fed in as moments. It is closed by the chain trialgate = reference (b) on raw returns, and
     reference = paper (a).
2. Bailey, D. H., Borwein, J. M., López de Prado, M. & Zhu, Q. J. (2015), "The Probability of Backtest
   Overfitting", *Journal of Computational Finance* (SSRN 2326253). That paper's results are Monte
   Carlo, so there is **no reproducible closed-form worked example**. This is recorded, not
   approximated. The definition is used instead: λ = ln(ω / (1 − ω)) with ω = OOS rank / (N + 1), and
   PBO = Pr[λ ≤ 0]. Two of its limiting cases were tested:
   - one configuration dominates every block: PBO = 0. **PASS.**
   - perfect anti-persistence, where the IS winner is the OOS loser in every split: PBO = 1. **PASS.**

**(b) Independent from-formula reference** (tests/test_cycle2_multiple_testing.py only, standard
library only, no second library), on fixed seeded synthetic inputs:

- DSR on 4 cases (Gaussian and left-skewed returns; N = 1, 5, 24, 120; including N = 1 / SR0 = 0):
  |Δ| ≤ 1e-12. **PASS.**
- PBO on 5 matrices (T = 33–160, N = 3–10, S = 2–10; noise and persistent-edge; T mod S ≠ 0 included):
  exact. **PASS.** Rows dropped = T mod S, the most recent ones, as the package documents.

**TRIALGATE_REFERENCE_VALUES = PASS** at the tolerances above.

**Findings that bind the wrapper's use** (none is a mismatch; each is handled in the wrapper):

- **A2.1** If `effective_trials > 1` but fewer than 2 trial Sharpes are supplied, or they are all equal,
  trialgate silently sets SR0 = 0. That deflates nothing while it reports N trials. The wrapper
  returns NOT_EVALUABLE.
- **A2.2** `probability_of_backtest_overfitting` drops the most recent `T mod S` rows. The wrapper
  discloses the count in `reason` and never pads.
- **A2.3** On ties, the IS argmax takes the first column and the OOS rank counts `<=`, which is
  favourable to the selection. With fewer than 2 varying columns the wrapper returns NOT_EVALUABLE.
- **A2.4** trialgate refuses when the Mertens term 1 − γ3·SR + (γ4 − 1)/4·SR² ≤ 0. With population
  moments, Pearson's inequality (γ4 ≥ γ3² + 1) keeps that term ≥ 0, so real data cannot reach the
  refusal. The wrapper still maps any trialgate input error to NOT_EVALUABLE; the test forces it.
- **A2.5** `observed_sharpe` uses the sample stdev (ddof = 1) while skew and kurtosis use population
  moments (ddof = 0). The reference reproduces exactly this estimator choice.

## A3 — Determinism

- Identical inputs gave bit-identical outputs (`float.hex`) over repeated in-process calls. **PASS.**
- Two fresh interpreter processes also gave bit-identical output (DSR, SR0, `DataRequirement`, PBO,
  combination count). **PASS.**
- PBO has no internal randomness, and this is proven rather than seeded. `trialgate.validation` imports
  no RNG, clock or entropy source (`random`, `secrets`, `time`, `os`, `uuid`, `numpy`), and CSCV
  enumerates all C(S, S/2) partitions instead of sampling them.

**TRIALGATE_DETERMINISM = PASS.**

## A4 — Thresholds are caller-supplied

- `multiple_testing.dsr(..., threshold=...)` and `multiple_testing.pbo(..., block_count=..., threshold=...)`
  have keyword-only arguments with **no defaults**. Calling without them raises `TypeError`.
- Passing `None`, a bool, a string, NaN, ±inf, or a value ≤ 0 or ≥ 1 raises `ThresholdRequiredError`.
  There is no fallback.
- The wrapper's source never names `DEFAULT_MAX_PBO`, `DEFAULT_MIN_DSR`, `DEFAULT_MIN_OBSERVATIONS` or
  `DEFAULT_MAX_STOP_BREACH`, and never imports `trialgate.gates`.
- `observations_required_for_dsr` is called with `target_dsr=threshold`, never with its own 0.95
  default.
- The test shows that the threshold decides the status: on the same data, a fixture threshold above or
  below the measured value flips PASS and FAIL.
- research/cycle2/prereg.schema.json requires `dsr_threshold`, `pbo_threshold`, `pbo_block_count`,
  `periods_per_year` and `effective_trials`, with no defaults. **No threshold value is chosen in this
  unit.** Every number in the tests is a labelled fixture.

**TRIALGATE_THRESHOLDS_CONFIGURABLE = PASS.**

## The NOT_EVALUABLE law (wrapper, research/cycle2/multiple_testing.py)

The result shape is `{status: PASS|FAIL|NOT_EVALUABLE, value, threshold, effective_trials, observations,
reason}`. The result is NOT_EVALUABLE, never PASS, in each case below. Every case is tested.

| statistic | NOT_EVALUABLE when |
|---|---|
| DSR | `effective_trials` not an int ≥ 1 · `periods_per_year` not an int ≥ 1 · non-finite or non-list returns or trial Sharpes · < 3 observations · constant returns · cross-trial Sharpe variance not estimable while N > 1 (A2.1) · any trialgate `ValidationInputError` · non-finite DSR · **too few observations by `observations_required_for_dsr` at the preregistered threshold** |
| PBO | `block_count` not an even int ≥ 2 · empty or ragged matrix · non-finite cell · < 2 configurations · fewer rows than blocks · fewer than 2 varying columns · any trialgate `ValidationInputError` |

When the observed Sharpe does not exceed the expected maximum of N noise trials, no sample size
reaches the threshold. That case is **FAIL**: it has been evaluated, and chance beat it. Nothing is
imputed, padded or relaxed.

**N and the upstream debt.** `effective_trials` is required. It must be the **cumulative family N**,
at least `ledger_family_trial_count(family_id)`, which is read-only from research/trial_ledger.py and
refuses a ledger that does not verify. Every DSR or PBO figure reported must state that N together with
the upstream selection debt it cannot observe
(research/external/candidate_registry.json → `multiple_testing_accounting`: "Do NOT claim DSR or PBO
certification from LOCAL_TRIAL_COUNT alone"). The driver's preregistration schema requires a
`selection_debt_statement` for that reason. The wrapper never stores trials.

## A5 — Verdict

A1–A4 PASS, with no mismatch beyond tolerance, so the verdict is **ADOPT_VALIDATION_ONLY**. Exactly one line
was added to research/requirements.txt.

Disclosures for the Owner (no action taken; each is outside 7.1's file scope):

1. **CI does not install trialgate.** .github/workflows/ci.yml installs requirements-dev.txt only, and
   no workflow installs research/requirements.txt. The tests that need trialgate itself skip in CI:
   the paper and reference comparison, determinism, the version check and the post-call NOT_EVALUABLE
   branches. The precondition branches, threshold-raising, the A6 static scan, the ledger count and
   the requirements pin run everywhere. All 64 tests ran and passed locally on Python 3.12.14 with the
   hash-verified install. Before §7.2's first CI run depends on this wrapper, the Owner must approve
   adding the pinned line to the install of the workflow that runs it. This unit may not change
   workflows.
2. **Hash-checking mode.** Because the trialgate line carries `--hash`, `pip install -r
   research/requirements.txt` now runs in hash-checking mode and would also demand a hash for the
   existing `mlflow==3.15.2` line. Nothing installs that file today, so nothing breaks. Whoever first
   installs it must hash-pin mlflow or install trialgate's line on its own.

## A6 — Forbidden surface

tests/test_cycle2_multiple_testing.py statically scans every research/cycle2/*.py (AST). It asserts:

- no import of `trialgate.registry`, `trialgate.holdout`, `trialgate.gates`, `trialgate.risk`,
  `trialgate.demo` or `trialgate.__main__`, in any `import` or `from` form;
- `trialgate.validation` is the only trialgate module named;
- no `importlib` or `__import__` side door, and no call to `append_trial`, `initialize_holdout`,
  `spend_holdout`, `evaluate_gates` or `evaluate_registry`.

A companion test proves the scan catches a forbidden import. **REGISTRY_HOLDOUT_UNUSED = YES.**

## Scope of 7.1 (what this record does not do)

- No null recalibration (§7.2, which needs a separate Owner go).
- No candidate preregistration, and no Trend or MR work.
- No trial ID and no ledger append.
- No engine backtest, docker, freqtrade or market data, locally or in CI.
- The driver's engine-propagation proof from a real run log belongs to §7.2's first CI run.
