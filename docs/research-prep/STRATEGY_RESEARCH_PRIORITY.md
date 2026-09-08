# Research priority — pre-test

**This answers:** which candidate to investigate first *if* the governing plan later opens the
Alpha Research branch.
**It does not answer:** which strategy will make the most money. Historical return is one weak
factor among the eighteen scored.

`CANDIDATE_EXECUTION_AUTHORIZED = NO`

---

## Verdict

| Priority | Candidates |
|---|---|
| **P1** | **A3** EMAPriceCrossoverWithThreshold · **A5** DoubleEMACrossoverWithTrend |
| **P2** | A1 EmaCross · A2 EmaCrossFunding · A6 RSIDirectionalWithTrendSlow |
| **P3** | A4 ReinforcedAverageStrategy |
| **HOLD** | A7 NostalgiaForInfinityX8 |

**Top 3:** A3, A5, A1.

A3 first because it is the *unfitted original* of the winning family under a permissive licence.
A5 second because it is the nearest neighbour to our own baseline and therefore the best probe of
that family. A1 third, and only paired with A3, because on its own it measures a sweep rather
than a strategy.

---

## Changes to the planning hypothesis — reported, not silently applied

The approved pool is unchanged. Three orderings moved, each on evidence:

**A1 and A2 drop from P1 to P2.** The directive listed the EmaCross lineage first. Source evidence
shows A1 is a parameter variant of A3 with sweep-fitted values (600/2.0 versus A3's hardcoded 800/1.0),
that its family self-reports a Deflated Sharpe failure once the 42-way selection is counted, and that
it explicitly fails to generalise to other coins — while half our universe is ETH. Testing the fitted
GPL derivative before the unfitted MIT original would be backwards.

**A5 rises from P2 to P1.** Lineage analysis shows A5, not A1, is the closest relative to
`BaselineEmaRegimeV1`: both are fast-EMA-crosses-slow-EMA on 1h spot long-only. It therefore carries
the most information about our own control's family, which is the family we are actually running.

**A7 drops from P3 to HOLD.** No citable performance claim exists in the repository, its canonical
file mutates daily by design, and a native test needs a universe our dataset cannot supply.

---

## Why each, in one paragraph

**A3 — P1, information gain HIGH.** The family original, and the only F1 member whose parameters were
never fitted: 800 and 1% are hardcoded, so it carries no sweep-selection bias of its own. MIT, so no
copyleft question. It won a 42-way benchmark on 210 trades with a −30.3% drawdown. It answers the
sharpest question available: does the unfitted parent generalise, or is the family's headline an
artefact of A1's sweep? Cost is a mechanical legacy-interface adapter whose signal parity must be
proven. Residual risk: its own 42-way selection is a trial and must enter the count.

**A5 — P1, information gain HIGH.** The closest relative to our baseline in the pool, so it isolates
what a trend gate plus much faster periods does to the family we already run. MIT, no external data,
and 753 trades is the largest sample here. Residual risk: that same 753 trades is roughly seven times
A3's turnover, making it the most fee-exposed candidate — cost robustness must be tested early, not last.

**A1 — P2, information gain MEDIUM.** Not an independent discovery, so it can never be counted as a new
strategy. Its value is narrow but real: paired against A3 it measures exactly what the sweep bought.
Modern interface, so no adapter. Residual risk: GPL-3.0 copyleft, fitted parameters, and the source's
own admission that the family fails DSR under honest trial counting.

**A2 — P2, information gain MEDIUM-HIGH.** A clean single-variable ablation on A1, and the source frames
it correctly itself: the baseline for testing rule 4 is A1, not buy-and-hold. Its claim is specific and
falsifiable — the filter buys drawdown, not return, verified 6 out of 6 independent checks. Residual
risk: only interpretable after A1, needs external funding history, and the author reports the funding
signal reversed direction in 2023.

**A6 — P2, information gain MEDIUM.** The only momentum-family candidate, so it broadens family coverage
instead of re-testing the EMA idea a fourth time. MIT, simple, no external data. Residual risk: the
weakest source evidence in the pool — +117.7% against buy-and-hold's +781%, Sharpe 0.054, and its
faster sibling lost money outright.

**A4 — P3, information gain MEDIUM.** Second in the benchmark on 206 trades with the lowest drawdown of
the top three. Residual risk: its own author calls it a proof of concept that doesn't perform well, it
runs at 4h rather than our 1h, and it needs the `technical` package plus resampling validation. GPL-3.0.

**A7 — HOLD, information gain UNKNOWN.** It would answer whether a large multi-signal system beats simple
models, which is genuinely interesting. But it is not researchable under current constraints: no citable
claim, a file that changed the day we locked it and an updater that rewrites it daily, and a native test
requiring 40–80 pairs at 5m with four informative timeframes and DCA position adjustment — none of which
our dataset or our fixed-stake architecture supports. **A BTC/ETH-only run would not be native NFI
validation and must never be labelled as such.**

---

## Blockers

| Class | Status |
|---|---|
| `LICENSE_BLOCKERS` | **None.** All seven licences read and identified at HIGH confidence. But four are GPL-3.0 copyleft and this repository ships no LICENSE of its own — an Owner decision required *before* any GPL candidate enters an executable path. |
| `COMPATIBILITY_BLOCKERS` | A3, A5, A6 use the legacy Freqtrade interface and require adapters with proven signal parity. A4 needs the `technical` package. None is fatal. |
| `DATA_DEPENDENCY_BLOCKERS` | A2 needs funding-rate history (LOW cost). A4 needs 4h candles (derivable, LOW cost). **A7 needs a 40–160 pair multi-timeframe dataset — HIGH cost, and explicitly not to be built during the active FP run.** |
