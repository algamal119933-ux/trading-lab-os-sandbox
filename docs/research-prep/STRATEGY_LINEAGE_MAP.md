# Strategy lineage map — selection-bias accounting

**Machine-readable:** `research/research-prep/strategy_lineage.json`

Strategy names are not experiments. Counting A1, A2 and A3 as three discoveries would
inflate the independent trial count and deflate every later Deflated Sharpe and PBO
correction — which is precisely the error the source repository itself warns about.

---

## The decisive finding

`btc-strategy-lab`'s own `NOTICE` file states it, so this is primary evidence and not inference:

> `user_data/strategies/EmaCross.py` and `EmaCrossFunding.py` are derived from
> this strategy. The trading logic is his; the parameterisation, funding-rate
> filter and validation harness are additions.

And A1's own docstring, translated from the Polish: *"parameterised version of
EMAPriceCrossoverWithThreshold … logic identical, the difference is only that three
hardcoded numbers (EMA period, exit threshold, stoploss) are parameters here."*

```
A3  EMAPriceCrossoverWithThreshold   ORIGINAL          (MIT, hardcoded 800 / 1%)
 │
 └── A1  EmaCross                    PARAMETER_VARIANT (GPL, swept to 600 / 2.0)
      │
      └── A2  EmaCrossFunding        FILTER_ADDITION   (GPL, + funding percentile gate)
```

**A1, A2 and A3 are one family, `F1_PRICE_VS_SINGLE_EMA`, containing one discovery and two variants.**

---

## Families

| Family | Description | Members | Original |
|---|---|---|---|
| `F0_DUAL_EMA_REGIME_CROSS` | EMA50 × EMA200, no gate | **BaselineEmaRegimeV1** (our control) | — |
| `F1_PRICE_VS_SINGLE_EMA` | Price crosses one long EMA; exit a fixed % below it | A3, A1, A2 | A3 |
| `F2_FAST_DUAL_EMA_WITH_TREND_GATE` | Fast EMA × slow EMA, gated by a long trend EMA | A5 | A5 |
| `F3_RSI_DIRECTIONAL_WITH_TREND_GATE` | RSI threshold cross, gated by a long trend EMA | A6 | A6 |
| `F4_MA_CROSS_WITH_RESAMPLED_SMA_GATE` | EMA cross gated by a higher-timeframe resampled SMA | A4 | A4 |
| `F5_MULTI_PAIR_COMPOSITE` | Multi-signal, multi-timeframe, multi-pair, DCA | A7 | A7 |

`INDEPENDENT_CANDIDATE_COUNT = 5` — A3, A4, A5, A6, A7. A1 and A2 sit inside A3's family.

---

## Relationship to the current baseline

The planning hypothesis asked whether EmaCross duplicates `BaselineEmaRegimeV1`. **It does not.**

| | Baseline | A1 / A2 / A3 |
|---|---|---|
| Signal | EMA50 crosses **EMA200** | **Price** crosses one EMA(600–800) |
| Construction | EMA-vs-EMA | price-vs-EMA |
| Exit | EMA50 crosses below EMA200 | price closes a fixed % below the EMA |
| Trailing | none | enabled |

Same broad trend-following intent, different signal construction and different exit geometry.
So `SEMANTIC_DUPLICATE_OF_BASELINE = NO` for A1, A2 and A3, and **none of them becomes
`CONTROL_LINEAGE_REFERENCE`**.

**But the nearest neighbour is not where the plan assumed.** A5 `DoubleEMACrossoverWithTrend`
is the closest relative to our baseline in the entire pool — both are fast-EMA-crosses-slow-EMA,
1h, spot, long-only. It differs by much faster periods (9/21 vs 50/200) and by adding a
`low > EMA200` trend gate that also serves as an OR-exit. `SEMANTIC_DUPLICATE_OF_BASELINE = PARTIAL`.

That makes A5 the highest-information probe of our own control's family, and it is the reason
A5 is promoted to P1.

A4 is also `PARTIAL` — its entry is an EMA8 × EMA21 crossover — but it runs at 4h behind a
resampled SMA gate, so both the regime logic and the bar clock differ.

---

## Full trial count preparation

`FULL_TRIAL_COUNT_PREPARATION = PREPARED_NOT_FINAL`

For family `F1`, the visible runs are the smallest part of the count:

| Selection step | Trials | Source |
|---|---|---|
| 42-way public benchmark that selected A3 as winner | **42** | README: "42 public strategies … 3 beat buy & hold, 33 lost money" |
| A1 parameter sweep | **25** | README: DSR "deflates for the 25 variants in the EmaCross sweep" |
| A2 funding-filter sweep | UNKNOWN | thresholds 50/55/60 discussed; full sweep size not stated |
| **Minimum family trials** | **≥ 67** | |

Every configuration Trading Lab OS itself evaluates must be added on top, including discarded runs.

**The source says the gate fails, and says so itself:**

> It deflates for the 25 variants in the EmaCross sweep, but the strategy was also picked as
> the winner of a 42-way benchmark and then had a fourth rule added, and neither of those
> selection steps is in the trial count. … At twice that spread the p-value drops to 0.88, at
> three times to 0.51. **The shipped strategy does not clear this gate.**

This is the single most important line in the whole source pool, and it comes from the author.
Any future work on A1 or A2 inherits it.
