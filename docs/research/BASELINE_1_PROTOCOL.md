# BASELINE-1 — evaluation protocol (pre-registered)

Written and committed **before** any BASELINE-1 result was observed. The point
of fixing the thresholds first is that they cannot then be chosen to flatter
whatever came out.

## What BASELINE-1 is

`freqtrade/user_data/strategies/BaselineEmaRegimeV1.py` — 1h Binance spot,
long-only, `BTC/USDT` + `ETH/USDT`, EMA50/EMA200 regime crosses, nothing else.
It is a **scientific reference**, not a candidate that has to be profitable. A
negative return is a legitimate result and does not make the protocol fail.

**Its logic is frozen.** If a result suggests a change, that change becomes a
new, explicitly versioned candidate — it is not folded back into BASELINE-1.
`tests/test_baseline_strategy.py` asserts each exclusion individually, so
"just one more filter" fails the suite rather than landing quietly.

## Two separate verdicts

These are reported separately and must never be conflated.

### `BASELINE_PROTOCOL_RESULT` — is the evidence technically valid?

**PASS** requires all of:

1. Dataset V2 integrity `PASS` on real market data (coverage, cadence,
   duplicates, gaps, NaN, OHLC validity, monotonic timestamps, completed-candle
   boundaries, 5m → 1h reconciliation).
2. Code and config hashes frozen and recorded **before** the evaluation run.
3. The backtest completes over the whole Development window with 5m detail
   simulation, with no configuration error in the engine output.
4. Lookahead analysis reports no bias.
5. Recursive analysis is acceptable: no indicator whose values keep moving
   materially as more startup history is added, given
   `startup_candle_count = 600`.
6. Exposure, attribution and cost figures are actually computed, not assumed.
7. No rule changed between the specification freeze and the evaluation.

Any of these failing makes the protocol result **FAIL**, whatever the returns
look like.

### `BASELINE_PERFORMANCE_CLASSIFICATION` — how did it do, on this window?

Measured against the **realised-exposure-matched passive** line, not
buy-and-hold. A long-only regime strategy sits in cash much of the time; judging
it against a fully invested benchmark rewards or punishes it for exposure it
never took.

Let `E = total_return_pct − passive_realised_exposure_matched_return_pct`,
both over the same window.

| Classification | Pre-registered rule |
| --- | --- |
| **STRONG** | `E > +10` percentage points **and** Sharpe > 0.5 **and** max drawdown < 35 % **and** at least 30 closed trades |
| **WEAK** | `E < −10` percentage points **or** profit factor < 0.8 |
| **NEUTRAL** | anything else |

Fewer than 30 closed trades means the sample cannot support STRONG or WEAK; the
result is reported NEUTRAL and explicitly labelled statistically inconclusive.

## Measurements required on Development

Standard backtest; lookahead analysis; recursive analysis; 5m detailed-timeframe
simulation; per-pair attribution; turnover; fees; trade count; average and peak
capital exposure; time in market; return per unit of exposure; max drawdown;
profit factor; Sharpe; Sortino; Calmar; maximum consecutive losses; and the
passive comparisons (BTC buy-and-hold, ETH buy-and-hold, 50/50, max-exposure
matched, realised-exposure matched).

Freqtrade reports none of the exposure figures, so
`research/summarize_backtest.py` derives them from the trade list: time in
market is the union of trade intervals over the window, and average capital
exposure is the time-weighted mean of open stake divided by the wallet.

## Validation discipline

Validation is **not** run until the baseline implementation and this Development
protocol are frozen. It is then run **once**, unchanged.

* No tuning against Validation, silent or otherwise.
* A Validation outcome may not be used to retune BASELINE-1. Any tuning creates
  a new versioned candidate with its own record.
* Validation is **not** a Locked OOS and is never reported as one — see
  `docs/research/DATASET_V2_SPEC.md` for why no part of this dataset qualifies.
* The first strict prospective holdout is forward paper over data that did not
  exist at freeze time.

## Evidence

Every run is recorded as a schema-valid experiment record under
`research/records/`, carrying the code commit, config hash, dataset
fingerprints, strategy hash, engine version, window, costs, gate decision and
reason.
