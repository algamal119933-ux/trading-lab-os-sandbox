# CYCLE-2 UNIT 7.3 — Trend / Breakout lineage: preregistration

**Frozen before any performance result from this lineage exists.** No backtest of
`DonchianBreakoutV1` has been run anywhere, by anyone, before this record and its
ledger `PREREGISTERED` record were committed.

**Authority:** research/OFFLINE_RESEARCH_CYCLE_2_OPENING_1.md §2.1, §3, §4, §7.3
(Owner, PR #42); Owner CONTINUOUS EXECUTION AUTHORIZATION 2026-10-03T19:09Z (7.3 and
its lawful successors, within the frozen caps). Judged by research/cycle2/FUNNEL_LAW_1.md
(sha256 `5ad00f5a…468a`), unchanged. Unit 7.2 (null recalibration) closed PASS on main
`45c1e583`.

**Machine-readable preregistration:** research/cycle2/prereg/TRIAL-C2-TREND-DONCHIAN-1.json.
The ledger record binds that file and this one by sha256. Where they differ, the JSON
governs execution and this record governs interpretation; neither is edited after the
ledger record exists.

## Identity

```text
FAMILY_ID      = BTSL_EMA_REGIME        the Cycle-1 trend family (OPENING-1 §2.1 "family F1":
                                         the lineage inherits that family's Cycle-1 count and
                                         H1's upstream selection debt)
LINEAGE_ID     = BTSL_EMA_REGIME/L2     new; independent of BTSL_EMA_REGIME/L1 (H1)
CANDIDATE_ID   = TREND_DONCHIAN_BREAKOUT
EXPERIMENT_ID  = EXP-CYCLE2-SCI-TREND-DONCHIAN   (scientific trial ID 1 of 12)
TRIAL_ID       = TRIAL-C2-TREND-DONCHIAN-1
RUN_ID         = RUN-C2-TREND-DONCHIAN-1
STRATEGY       = research/trend_breakout/DonchianBreakoutV1.py (sha256 pinned in the JSON)
```

## Hypothesis

On BTC/USDT and ETH/USDT spot, a 1h close that breaks above the highest high of the
prior one to three weeks marks the start of a trend leg that continues often and far
enough, net of fees, to beat a passive position of the same maximum size held over
the same window.

## Mechanism (signal construction)

Computed from each pair's own 1h OHLCV with pandas rolling max/min only:

```text
upper = high.rolling(entry_period).max().shift(1)    highest high of the previous entry_period candles
lower = low.rolling(exit_period).min().shift(1)      lowest low of the previous exit_period candles
entry: close > upper (and volume > 0)                long only
exit:  close < lower
```

The one-candle shift means a candle never compares against a range that contains
itself. Frozen, not parameters: `stoploss = -0.10` (fixed, a risk backstop),
`minimal_roi = {"0": 100.0}` (disabled), no trailing stop, `startup_candle_count = 500`
(covers the 480-candle maximum lookback plus the shift; Dataset V2 holds 744 1h
candles before 2021-01-01 for ETH and more for BTC). Sizing is the research config's,
unchanged: wallet 100, stake 10, max_open_trades 2.

## Why this is not an EMA-cross or EMA-regime re-expression (OPENING-1 §2.1)

H1 (`EmaCross`, BTSL_EMA_REGIME/L1) compares the close with a 600-period EMA and exits
on an EMA-distance threshold: a smoothed, recursive average of all past closes decides
both the regime and the trade. This lineage uses no average of any kind, smoothed or
simple, and no recursive formula. Its signal is an order statistic (the extreme high or
low of a finite window), so it reacts to a new range extreme, not to price crossing a
lagging mean. Entry and exit use different windows and different series (highs for
entry, lows for exit), which an EMA cross cannot express. It also trades both Dataset
V2 pairs, where H1 was BTC-only.

## Selection context (considered, none executed)

1. **Donchian channel breakout** (selected): the canonical, parameter-sparse breakout
   rule (the "Turtle" channel rule), two natural parameters, no indicator library.
2. **Volatility (ATR/Keltner) breakout:** rejected as the first pick because Keltner
   channels centre on an EMA, which would put an EMA back into the signal.
3. **Time-series momentum (sign of the N-hour return):** rejected because a return-sign
   rule over a long window is close to a moving-average-slope rule, the very family H1
   belongs to.

This is selection context, not three trials. Only design 1 is preregistered.

## Grid (explicit enumeration, no sweep)

Window lengths follow the channel rule's own convention (exit window shorter than or
comparable to the entry window, in day multiples), not any data inspection.

| config_id | entry_period (h) | exit_period (h) |
|---|---|---|
| E168_X72  | 168 (7 d)  | 72 (3 d)  |
| E168_X168 | 168 (7 d)  | 168 (7 d) |
| E336_X72  | 336 (14 d) | 72 (3 d)  |
| E336_X168 | 336 (14 d) | 168 (7 d) |
| E480_X72  | 480 (20 d) | 72 (3 d)  |
| E480_X168 | 480 (20 d) | 168 (7 d) |

6 configurations, all counted (OPENING-1 §3: Trend ≤ 12). None is regime- or
session-gated. Params are nested by Freqtrade space (`buy.entry_period`,
`sell.exit_period`).

## Funnel (OPENING-1 §4, FUNNEL_LAW_1) as executed by this trial

```text
windows   Development only. Folds (anchored, Cycle-1 shape):
            F1 TRAIN 2021-01-01..2022-12-31  EVAL 2023-01-01..2023-12-31
            F2 TRAIN 2021-01-01..2023-12-31  EVAL 2024-01-01..2024-12-31
          Robustness window 2021-01-01..2024-12-31 (in-sample by design: a plateau check)
selection per fold on TRAIN by return_over_drawdown (Cycle-1 metric and tie-break)
fees      base 0.001/side, stress 0.002/side, engine-propagated (--fee); a symmetric fee
          proxy, slippage/latency/partial fills NOT_SUPPORTED
L1/L2     benchmark-relative against the exposure-matched passive line, as frozen
L3        DSR >= 0.95 with N = 15 (Cycle-1 H1's 9 + these 6; config_n.py, EVALUATED);
          PBO <= 0.05 over the 6 last-fold TRAIN series, 8 CSCV blocks
L4        PARAMETER_ROBUSTNESS, criterion GRID_EXCESS_OVER_EXPOSURE_MATCHED,
          min_positive_configs = 4: each configuration's robustness-window return minus
          the exposure-matched passive over the same window; a configuration is positive
          only with excess > 0 and >= 10 trades. PASS iff >= 4 of 6 are positive AND every
          TRAIN-selected configuration is positive; else FAIL
engine    2 folds x (6 TRAIN + 1 EVAL + 1 stress EVAL) + 6 robustness = 22 invocations
budget    after: engine 34/120, SCI IDs 1/12, CAL IDs 2/6, configurations 6/24 (Trend 6/12)
```

L4's criterion is set here because FUNNEL_LAW_1 L4 makes robustness "required, per the
trial's preregistration" and until this unit no preregistration could carry one (the
evaluator returned NOT_EVALUABLE for every non-null lineage). The law file is unchanged.

## Outcomes and what follows

```text
REJECTED      any gate FAIL. Terminal; the lineage is not modified, re-tuned or rerun. With
              MR not approved (OPENING-1 §2.2), Cycle 2 proceeds to its closure record (7.5).
INCONCLUSIVE  ledger COMPLETED with outcome.funnel_result = INCONCLUSIVE. Not a survivor.
              Closure (7.5).
SURVIVED      FREEZE. One unchanged run of the frozen TRAIN-selected configuration on the
              Validation window 2025-01-01..2026-08-31 (SHARED_NON_PRISTINE, reported, never
              selected on), as a separate scientific trial ID; the current tooling forbids
              Validation windows, so that run needs its own tooling unit first. Paper
              admission is a separate Owner decision either way.
INVALID_RUN   an integrity gate is not PASS: STOP and report.
```

## Disclosed before any result

- The exposure-matched passive line is held for the whole window at the strategy's
  maximum exposure (FUNNEL_LAW_1, disclosed bias). A breakout strategy is out of the
  market part of the time, so in rising windows it must out-earn a fully exposed passive
  position while exposed less. Both EVAL years (2023, 2024) are publicly known to have
  been rising years for BTC and ETH; that is general market knowledge, not a result of
  this lineage, and it was not used to choose the grid. A REJECTED result is likely and
  is a valid scientific outcome.
- The robustness window overlaps the EVAL years; L4 is a parameter-plateau check, not
  out-of-sample evidence.
- Validation is SHARED_NON_PRISTINE; no historical holdout exists (OPENING-1 §5, Option B).
