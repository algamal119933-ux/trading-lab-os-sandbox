# Future benchmark protocol — design only

**`STATUS = DESIGN_ONLY_NOT_EXECUTED`. `CANDIDATE_EXECUTION_AUTHORIZED = NO`.**
Research preparation is not execution authorization.
**Machine-readable:** `research/research-prep/future_benchmark_contract.json`

## Phases

**Phase 1 — Source / static admission.** Licence identified and compatible (ambiguous ⇒
`BLOCKED_LICENSE`); provenance recorded; source lock pinned; compiles and imports; interface
compatibility determined; side-effect scan (no writes, no shared-state mutation at import);
network scan (no runtime fetch of code, pairlists or blacklists — this one is not hypothetical,
A7 ships exactly such an updater); future-indexing scan (no negative shifts, no `.iloc[-1]` on a
full frame, no reindex to future timestamps); warm-up validation — `startup_candle_count` must
cover the longest lookback, which **four of seven candidates fail to declare at all**; effective-config lock.

**Phase 2 — Adapter parity.** Applies to A3, A5, A6. The original signal stream and the
modernized signal stream must match exactly under a deterministic fixture: entry and exit boolean
series compared index-for-index, zero mismatches. **Any semantic difference means a NEW CANDIDATE,
not an adapter** — and a new candidate is a new trial in the count.

**Phase 3 — Bias analysis.** Freqtrade lookahead analysis, recursive analysis, sufficient signal coverage.

**Phase 4 — Native test.** The candidate's intended market, universe, timeframe and slot
configuration, where scientifically feasible.

**Phase 5 — Normalized test.** Shared Trading Lab OS controls, only where scientifically valid.
`NATIVE_RESULT` and `NORMALIZED_RESULT` are always reported separately. BTC/ETH-only testing is
never labelled native NFI validation.

**Phase 6 — Cheap qualification.** Net return after costs, CAGR, max drawdown, drawdown duration,
trades, win rate, profit factor, expectancy, Sharpe, Sortino, Calmar, exposure, turnover, fees,
slippage, control excess, signal count.

**Phase 7 — Robustness, qualifiers only, pre-registered.** Fees 5/10/20 bps per side; slippage
0/2/5/10 bps per fill; one-candle execution delay; parameter neighbourhoods; subperiods; regimes;
bootstrap; top-1/top-3/top-5 trade contribution; remove-best-trade; remove-best-regime; PBO;
Deflated Sharpe. **The full trial count must include lineage, source-selection and
parameter-selection steps — not only the final visible runs.** For family F1 that floor is already
≥ 67 before we run anything.

## Controls — defined, not executed

| ID | Control | Note |
|---|---|---|
| C1 | TrendRiderStrategy | Source benchmark: −99.48%. A genuine negative control. |
| C2 | Strategy001 | −98.62% on an **88.6% win rate** — the win-rate trap in one row. |
| C3 | Matched-count random signal | Random entries matched to trade count and holding-time distribution. |
| C4 | Time-shifted signal | The candidate's own signals shifted k bars: destroys timing, preserves statistics. |
| C5 | BTC buy-and-hold | Passive. |
| C6 | Exposure-matched passive | Matched to time-in-market, so reduced exposure is never mistaken for alpha. |

C1 and C2 are especially valuable because their failure modes are already measured in a public
benchmark, so a harness that scores them as anything but disastrous is itself broken.

## Execution order — eliminate weak candidates cheaply

| Step | Candidates | Cost | Why |
|---|---|---|---|
| 1 | A3, A5 | CHEAP | Phases 1–3 only; no new data. |
| 2 | A1 | CHEAP | No adapter; only meaningful paired with A3. |
| 3 | A6 | CHEAP | Broadens family coverage; weakest evidence, so cheap elimination fits. |
| 4 | A2 | MODERATE | Needs funding acquisition and QA; interpretable only after A1. |
| 5 | A4 | MODERATE | Needs 4h data, `technical`, resampling validation. |
| 6 | A7 | EXPENSIVE | HOLD. Not to be built during an active FP run. |

Not scheduled in parallel, by design.

## Allowed outcomes

`SURVIVOR` · `NO_SURVIVOR` · `TRUE_STOP`

Never `BEST_OF_BAD_SET`. The highest historical return is never selected automatically — the
source pool itself demonstrates why, with a strategy that won 88.6% of its trades and lost 98.6%
of its capital.
