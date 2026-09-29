# H1-PAPER-READINESS-QUALIFICATION-1 — Preregistration

**Frozen before any qualification-diagnostic result was inspected.**
Authority: Owner directive `H1-PAPER-READINESS-QUALIFICATION-1` (2026-09-29),
under `OFFLINE-RESEARCH-AUTHORITY-1` §2.1 ("H1 robustness work, later, only
if a specific, named need is identified" — this is that need). Recorded
verbatim in the canonical Research Selection Ledger as the `PREREGISTERED`
record for `TRIAL-H1-QUAL-1` before execution began.

## Identity

```text
QUALIFICATION_ID = H1-PAPER-READINESS-QUALIFICATION-1
LINEAGE_ID        = BTSL_EMA_REGIME (reused, unchanged — Stage 0 / Unit B)
CANDIDATE_ID      = H1_EMACROSS (reused, unchanged)
```

## Frozen H1 identity (unchanged — no search, no redesign)

```text
Strategy file    = freqtrade/user_data/strategies/EmaCross.py
Strategy sha256  = 387cf39f58d266bb63d06865a0784bc2e08676edf54f4610c7d7709bb2a95f24
Upstream         = wiktorj137/btc-strategy-lab@b68a5518b4a3eba2fde1733160d7d7de356023b5
                    (GPL-3.0, not vendored, fetched hash-verified via
                    research/external/pin_upstream.py — the same mechanism
                    extbench.yml and TRIAL-H1-CD1 already used)
Params (center)  = EmaCross.json: ema_period=600, exit_threshold=2.0
                    sha256 = 9209a90e5092216af166fd10b9e7415690ab16af0fb3010c7e94e162c027e3ee
Engine           = freqtradeorg/freqtrade:2026.7
Pair / timeframe = BTC/USDT, 1h
```
No EMA period, exit threshold, timeframe, pair, entry, exit, stoploss, ROI
rule or filter search is authorized. No Hyperopt. The candidate that may
reach `ADVANCE_TO_PAPER_ADMISSION_REVIEW` is this exact frozen identity —
never a neighboring configuration.

## Reuse of an already-canonical result

`TRIAL-H1-CD1` (Research Foundation Unit B, `research/records/trial_ledger.jsonl`
seq 7, COMPLETED, `measurement_validity=PASS`) already executed this exact
frozen identity on the 2021-01-01→2024-12-31 window at `fee_per_side=0.001`,
with lookahead and recursive analysis both PASS. That result is reused here
as:
- the parameter-sensitivity grid's center point (config `EMA600_TH2.0`);
- the cost-stress `BASE_CASE`;
- the lookahead/recursive evidence for this qualification's Data/Provenance
  gate — the indicator computation does not change with parameter *values*
  or with which historical *window* is scored, so one bias check already
  covers every temporal slice and every neighbor in this qualification, and
  is not re-run per diagnostic trial.

It is cited, not re-executed, and this document does not alter its record.

## Temporal-stability design

Four non-overlapping, calendar-year historical slices, the frozen config,
unchanged, on each — no selection, no retuning between slices, no
segmentation change after seeing any result:

```text
2021-01-01T00:00:00Z -> 2021-12-31T23:00:00Z
2022-01-01T00:00:00Z -> 2022-12-31T23:00:00Z
2023-01-01T00:00:00Z -> 2023-12-31T23:00:00Z
2024-01-01T00:00:00Z -> 2024-12-31T23:00:00Z
```
Together these exactly cover H1's own historically-scored window
(2021-01-01 -> 2024-12-31); no data outside it is introduced.

**TEMPORAL_STABILITY_PASS_LAW**: PASS if `net_return_pct >= 0` in at least 3
of the 4 slices, AND `max_drawdown_pct < 25%` in every slice, AND no single
slice's `net_return_pct` exceeds 70% of the sum of all 4 slices' returns
(guards against one outlier year manufacturing an illusion of stability).

**TEMPORAL_STABILITY_FAIL_LAW**: FAIL if `net_return_pct < 0` in 3 or more of
the 4 slices, OR any slice's `max_drawdown_pct >= 25%`.

**TEMPORAL_STABILITY_INSUFFICIENT_LAW**: INSUFFICIENT if fewer than 3 of the
4 slices produce a measurement-valid result.

## Parameter-sensitivity neighborhood (diagnostic only)

Small, symmetric, fixed before execution — the candidate never changes:

```text
ema_period      in {500, 600, 700}   (600 = frozen center)
exit_threshold  in {1.5, 2.0, 2.5}   (2.0 = frozen center)
```
3x3 = 9 points; the center (`EMA600_TH2.0`) is `TRIAL-H1-CD1`, reused, not
re-run. The other 8 are new diagnostic trials, each on the same
2021-01-01->2024-12-31 window as the center, at `fee_per_side=0.001`. No
neighbor may be promoted, selected, or substituted for H1 under any
circumstance.

**PARAMETER_SENSITIVITY_STABLE_LAW**: STABLE if at least 6 of the 8
neighbors share the center's return sign, AND no neighbor's
`net_return_pct` is more than 3x worse (in the adverse direction) than the
center's.

**PARAMETER_SENSITIVITY_BRITTLE_LAW**: BRITTLE if fewer than 5 of the 8
neighbors share the center's sign, OR any neighbor shows a return more than
3x worse than the center in the adverse direction.

**PARAMETER_SENSITIVITY_INSUFFICIENT_LAW**: INSUFFICIENT if fewer than 6 of
the 8 neighbor runs produce a measurement-valid result.

## Cost-stress design

```text
BASE_CASE     fee_per_side = 0.001  (= TRIAL-H1-CD1, reused)
ADVERSE_CASE  fee_per_side = 0.002  (2x base, matching the convention
              Mean-Reversion Cycle 1 preregistered), NEW diagnostic trial,
              same 2021-01-01->2024-12-31 window, frozen identity unchanged
```

**Execution-fix requirement** (Owner directive section 6): the fee must
reach the actual `freqtrade backtesting` invocation, not only
`summarize_backtest.py`'s reporting. Implementation: the ADVERSE_CASE writes
its own `config.research.stress.json`, identical to the base research
config except `"fee": 0.002`, and passes that file via `--config` to the
docker invocation. Freqtrade's own backtest log prints
`Using fee 0.2000% from config.` when this takes effect, which is checked
directly from the log, not assumed.

**COST_STRESS_PASS_LAW**: PASS if `net_return_pct` remains positive under
ADVERSE_CASE.

**COST_STRESS_FAIL_LAW**: FAIL if `net_return_pct` becomes negative (sign
flips) under ADVERSE_CASE.

**COST_STRESS_INSUFFICIENT_LAW**: INSUFFICIENT if the ADVERSE_CASE run
cannot be validly executed and measured, or if engine-level fee propagation
cannot be proven from its own log.

## Friction / slippage

No directly-supported Freqtrade backtesting mechanism for slippage was
found, and no already-validated, documented conservative calculation method
exists in this project (Stage 0 confirmed: no lane has ever modeled
slippage). Per Owner directive section 7, none is invented here.
`FRICTION_STRESS = NOT_SUPPORTED` is the expected, honest classification,
not a defect to work around.

## Sample-sufficiency law

`SAMPLE_EVIDENCE = SUFFICIENT` if: every temporal slice individually carries
enough trades for its own return figure to be more than a 1-2 trade
artifact (>= 5 trades), AND the full 4-year footprint's own trade count
(76, already established) remains the primary evidence base, treated as 76
dependent observations of one mechanism across ~4 independent yearly
episodes — never as 76 independent draws, and never inflated by counting
underlying candles.

## Terminal qualification law

Exactly as the Owner directive's section 17-18 states, restated here for
completeness: `ADVANCE_TO_PAPER_ADMISSION_REVIEW` only if every material
gate (`AUTHORITY_COVERAGE`, `H1_FROZEN_IDENTITY`, `DATA_TRUTH`, `LOOKAHEAD`,
`RECURSIVE_ANALYSIS`, `SELECTION_LEDGER_CHAIN`,
`ALL_DIAGNOSTIC_TRIALS_RECORDED`, `TEMPORAL_STABILITY=PASS`,
`PARAMETER_SENSITIVITY=STABLE`, `COST_STRESS=PASS`,
`SAMPLE_EVIDENCE=SUFFICIENT`) passes. `REJECTED` if a material gate clearly
fails. `INCONCLUSIVE` if a material gate cannot be established honestly.
`FRICTION_STRESS` is not material (not in the Owner directive's required-gate
list) and cannot by itself block or grant `ADVANCE_TO_PAPER_ADMISSION_REVIEW`.
