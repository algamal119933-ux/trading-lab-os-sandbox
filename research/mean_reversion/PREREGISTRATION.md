# MEAN-REVERSION-CYCLE1-DISCOVERY-1 — Preregistration

**Frozen before any performance result from this lineage was inspected.**
Authority: Owner directive `MEAN-REVERSION-CYCLE1-DISCOVERY-1` (2026-09-29),
under `OFFLINE-RESEARCH-AUTHORITY-1`. Recorded verbatim (not summarized) in
the canonical Research Selection Ledger as the `PREREGISTERED` record for
`TRIAL-MR-ZSCORE-WF-1` before execution began.

## Identity

```text
LINEAGE_ID    = MEAN_REVERSION_ZSCORE
FAMILY_ID     = MEAN_REVERSION
CANDIDATE_ID  = MR_ZSCORE
EXPERIMENT_ID = EXP-MEAN-REVERSION-CYCLE1-1
```

## Hypothesis

BTC/USDT spot price, after an unusually large short-term deviation below its
own recent rolling mean, tends to revert toward that mean with enough
regularity and magnitude to be captured net of realistic trading costs.

## Economic / market micro-logic

Short-horizon mean reversion in a liquid spot market is a standard,
textbook effect attributed to short-term liquidity provision / overreaction
correction: a sharp move away from recent fair value attracts opportunistic
buyers (or profit-taking sellers on the other side), pulling price back
toward its recent average faster than a pure random walk would predict. This
is a distinct mechanism from H1's trend-following EMA-cross hypothesis by
construction — it bets on reversal, not continuation, and reacts to the
pair's own recent price distribution rather than to a moving-average
crossover.

## Selection debt (Owner directive §4 — considered before selecting one)

Three canonical mean-reversion implementations were considered before this
one was selected, in this order, none executed or performance-inspected:

1. **RSI-based** (enter when RSI < 30, exit when RSI > 50) — the most
   common retail implementation; rejected as the first pick only because
   RSI is a bounded oscillator whose "extremeness" is relative to a fixed
   0–100 scale rather than to the pair's own recent volatility, making its
   economic interpretation ("how many standard deviations from typical") less
   direct than a z-score.
2. **Bollinger-Band based** (enter when price crosses below the lower band,
   exit at the middle band) — mechanically near-identical to the z-score
   design below (a Bollinger band *is* a rolling-mean ± k·rolling-std
   envelope); not selected only because it is usually paired with a specific
   band-touch/close-below convention that adds an extra design choice
   (touch vs. close, band width vs. raw z-score) without changing the
   underlying mechanism being tested.
3. **Rolling z-score of price vs. its own rolling mean/std** (selected) —
   the most direct, parsimonious expression of "how far below its own
   recent typical range is price right now," with exactly two natural
   parameters (lookback, threshold) and a natural, symmetric exit condition
   (reversion to zero) that does not require a second band parameter.

This is recorded as selection context, not as three executed trials.

## Entry mechanism

```text
roll_mean = close.rolling(LOOKBACK_HOURS).mean()
roll_std  = close.rolling(LOOKBACK_HOURS).std()
zscore    = (close - roll_mean) / roll_std
ENTER LONG when zscore <= -Z_THRESHOLD
```

## Exit mechanism

```text
Primary (expected):  EXIT when zscore >= 0 (reverted to/above the rolling mean)
Backstop (defensive): forced close MAX_HOLD_HOURS = 168h (1 week) after entry,
  via Freqtrade's minimal_roi table (a proven, non-callback mechanism —
  Research Foundation Unit B found the custom_exit callback unreliable in
  this environment for an unconfirmed reason, and this design has no
  dependency on it)
Risk control: fixed stoploss = -8%, independent of the mean-reversion signal
```

## Pair universe

`BTC/USDT` only (spot). Not broadened to a multi-asset universe — Stage 0
and the Research Foundation both established no point-in-time multi-asset
universe mechanism exists yet, and broadening one for this lineage alone
would be exactly the scope-widening the governing directive forbids.

## Timeframe

`1h`, matching every existing dataset-lock and provenance convention already
proven (Dataset V2, `research/datasets/dataset_v2.lock.json`).

## Allowed indicators

Rolling mean and rolling standard deviation of `close` only (pandas
built-ins). No other indicator, no external indicator library, no
cross-asset input.

## Allowed parameter dimensions and ranges

```text
LOOKBACK_HOURS ∈ {24, 72}     (short vs. long rolling window)
Z_THRESHOLD    ∈ {1.5, 2.5}   (moderate vs. strict deviation requirement)
```
2×2 grid = 4 configurations. No other dimension (exit threshold, stoploss,
hold cap) varies in Cycle 1 — those are fixed, mechanism-level design
choices stated above, not search dimensions.

## Maximum configuration attempts / maximum total trials

```text
MAXIMUM_CONFIGURATION_ATTEMPTS = 4 (the full grid; no early stopping, no
  narrowing after partial results)
WALK_FORWARD_FOLDS = 2
TOTAL_PREREGISTERED_TRIAL_LIMIT = 4 configs x 2 folds (development/selection
  runs) + 2 fold-evaluation runs (winning config only) + 2 cost-stress
  reruns (evaluation folds, adverse cost case) = 12 backtest invocations,
  all accounted for under one preregistered lineage trial (TRIAL-MR-ZSCORE-WF-1)
  in the canonical ledger; no attempt outside this ceiling is authorized
  without a fresh preregistration.
```

## Development windows / walk-forward design

Anchored (expanding-window) walk-forward over Dataset V2's Development
period, preserving temporal order — no evaluation-window information may
inform which configuration is selected for that same fold:

```text
Fold 1: TRAIN = 2021-01-01 -> 2022-12-31 (2y)   EVAL = 2023-01-01 -> 2023-12-31 (1y)
Fold 2: TRAIN = 2021-01-01 -> 2023-12-31 (3y)   EVAL = 2024-01-01 -> 2024-12-31 (1y)
```
For each fold: all 4 configurations are backtested on that fold's TRAIN
window only; the configuration with the best TRAIN-window selection metric
(below) is chosen; that single configuration is then backtested, unmodified,
on that fold's EVAL window. The EVAL result is never used to pick a
different configuration for that fold after the fact.

**Selection metric (frozen before any result is seen):**
`total_return_pct / max_drawdown_pct` on the TRAIN window (a Calmar-like,
risk-adjusted metric — chosen to avoid rewarding raw return alone, per the
Owner directive's explicit instruction not to optimize for highest PnL
alone). Ties broken by higher TRAIN trade_count (more evidence), then by
lower LOOKBACK_HOURS (simpler/faster-reacting config), in that order.

## Cost assumptions

```text
Base:    fee_per_side = 0.001 (0.1%), matching every existing lane's convention
Adverse: fee_per_side = 0.002 (0.2%, double), applied to both fold-evaluation
  windows using each fold's selected configuration, as the cost-stress case
Slippage: Freqtrade backtesting default (no explicit slippage model beyond
  fee), matching the project's existing convention for every prior lane —
  noted as a real limitation in the final report, not silently assumed away
```

## Robustness tests

Parameter-neighborhood stability is read directly from the 2x2 grid's own
TRAIN-window results already produced for configuration selection (no
additional runs): whether the selected configuration's neighbors in the
grid (same lookback, other threshold; same threshold, other lookback) show
directionally consistent, non-spiking behavior, or whether the selected
point is an isolated spike surrounded by clearly worse neighbors.

## Regime / session diagnostics

Not planned in advance beyond the two-fold split itself (2023 vs. 2024
already differ materially in realised BTC volatility and trend regime,
which is itself a form of regime diagnostic). No further regime/session
splitting is authorized without a fresh preregistration, per the Owner
directive's explicit prohibition on splitting regimes until one looks
profitable.

## Falsification conditions (frozen)

```text
- If the selected configuration's EVAL-window return is negative in 2 of 2
  folds -> REJECTED.
- If either EVAL fold's trade_count < 10 -> that fold's evidence is
  DOWNGRADED to insufficient for that fold; if this affects both folds ->
  INCONCLUSIVE.
- If cost-stress reverses the sign of aggregate EVAL performance (summed
  or averaged across folds) -> COST_STRESS = FAIL, weighed under the
  Survivor Law (Owner directive §17) rather than auto-REJECTED.
```

## Survivor conditions

Exactly the Owner directive's §17 minimum, no weaker and no additional
post-hoc criteria: `DATA_TRUTH=PASS`, `LOOKAHEAD=PASS`,
`RECURSIVE_ANALYSIS=PASS` where applicable, `SELECTION_LEDGER_CHAIN=PASS`,
`WALK_FORWARD=PASS`, `PARAMETER_ROBUSTNESS=PASS`, `COST_STRESS=PASS`,
`SAMPLE_EVIDENCE=SUFFICIENT`. Any one materially unresolved ->
`INCONCLUSIVE`, never rounded up to `SURVIVOR`.
