# Strategy comparison matrix

**`OUR_RESULT = NOT_RUN` for every candidate.** Every number below is a SOURCE CLAIM.
A source's result is never converted into our result. `UNKNOWN` stays `UNKNOWN` — it is never rendered as 0.

**Machine-readable:** `research/research-prep/source_claims.json`, `candidate_manifest.json`

---

## Identity, lineage, licence

| | Baseline | A1 | A2 | A3 | A4 | A5 | A6 | A7 |
|---|---|---|---|---|---|---|---|---|
| Strategy | BaselineEmaRegimeV1 | EmaCross | EmaCrossFunding | EMAPriceCrossover…| ReinforcedAverage | DoubleEMACross… | RSIDirectional…Slow | NFI X8 |
| Source | ours | S1 | S1 | S2 | S3 | S2 | S2 | S4 |
| Trial family | F0 | F1 | F1 | F1 | F4 | F2 | F3 | F5 |
| Parent / derivation | — | A3 / PARAMETER_VARIANT | A1 / FILTER_ADDITION | — / ORIGINAL | — / INDEPENDENT | — / INDEPENDENT | — / FAMILY_RELATIVE | X7 / FAMILY_RELATIVE |
| Independent trial? | control | **NO** | **NO** | YES | YES | YES | YES | YES |
| Semantic duplicate of baseline? | — | NO | NO | NO | PARTIAL | **PARTIAL** | NO | NO |
| Licence | — | GPL-3.0 | GPL-3.0 | **MIT** | GPL-3.0 | **MIT** | **MIT** | GPL-3.0 |
| Signal family | crossover | trend | trend | trend | crossover | crossover | momentum | multi-condition |
| Complexity | LOW | LOW | MEDIUM | LOW | MEDIUM | LOW | LOW | **HIGH** |

## Runtime shape

| | Baseline | A1 | A2 | A3 | A4 | A5 | A6 | A7 |
|---|---|---|---|---|---|---|---|---|
| Market | spot | spot | spot | spot | spot | spot | spot | spot |
| Timeframe | 1h | 1h | 1h | 1h | **4h** | 1h | 1h | **5m** + 15m/1h/4h/1d |
| Intended universe | BTC+ETH | BTC | BTC | BTC | multi-pair | any | any | **40–80 pairs** |
| Startup / warm-up | 600 (declared) | 1300 (declared) | 1300 (declared) | **not declared**, needs ≥800 | **not declared**, needs ~600×4h | **not declared**, needs ≥200 | **not declared**, needs ≥600 | 800 (declared) |
| Stoploss | −0.25 | −0.15 | −0.15 | −0.15 | −0.2 | −0.2 | −0.2 | **−0.99 (disabled)** |
| Trailing | no | yes | yes | yes | no | no | yes | no |
| External data | none | none | **funding rate** | none | none | none | none | none |
| Position sizing | fixed 10 USDT | engine | engine | engine | engine | engine | engine | **DCA enabled** |
| Native interface | v3 | v3 | v3 | **legacy** | v3 | **legacy** | **legacy** | v3 |
| Adapter required | — | no | no | **YES** | no¹ | **YES** | **YES** | no |

¹ A4 needs no interface adapter but does import the external `technical` package.

## Source claims — all from primary repository evidence

Benchmark conditions where marked ᵇ: Binance BTC/USDT spot, `max_open_trades 1`, unlimited stake,
10 000 USDT, 0.1% fee per side, ~8 years, from `btc-strategy-lab research/out/benchmark.csv`.

| | A1 | A2 | A3ᵇ | A4ᵇ | A5ᵇ | A6ᵇ | A7 |
|---|---|---|---|---|---|---|---|
| Source return | +1,353% | **+1,604%** | +1,312.2% | +1,170.9% | +287.5% | +117.7% | UNKNOWN |
| CAGR | UNKNOWN | 50.9% | 35.97% | 34.27% | 17.02% | 9.45% | UNKNOWN |
| Max drawdown | −49.4% | **−33.8%** | −30.26% | −26.24% | −42.76% | −23.27% | UNKNOWN |
| Sharpe | UNKNOWN | 1.31ᶜ | 0.116 | 0.130 | 0.195 | 0.054 | UNKNOWN |
| Sortino | UNKNOWN | 1.42ᶜ | 0.712 | 0.456 | 0.642 | 0.183 | UNKNOWN |
| Trades | UNKNOWN | 96 | 210 | 206 | **753** | 114 | UNKNOWN |
| Win rate | UNKNOWN | UNKNOWN | 19.52% | 33.50% | 25.63% | 25.44% | UNKNOWN |
| Profit factor | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| Exposure | UNKNOWN | 61% | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| Benchmark | BTC +781% | BTC +781% | 1st of 42 | 2nd of 42 | 6th of 42 | loses to hold | UNKNOWN |
| Walk-forward | UNKNOWN | 8/13, +1,125% | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| PBO | UNKNOWN | **0.21** | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| Deflated Sharpe | UNKNOWN | **fails under honest trial count** | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| Fee model | 0.1%/side | 0.1%/side | 0.1%/side | 0.1%/side | 0.1%/side | 0.1%/side | UNKNOWN |
| Slippage model | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| Claim confidence | HIGH | HIGH | HIGH | MEDIUM | HIGH | HIGH | **LOW** |
| **OUR_RESULT** | **NOT_RUN** | **NOT_RUN** | **NOT_RUN** | **NOT_RUN** | **NOT_RUN** | **NOT_RUN** | **NOT_RUN** |

ᶜ Sharpe/Sortino for A2 come from the README headline table, computed by the author's own
`research/metrics.py`, not from the benchmark CSV — different harness, so not directly comparable
to the A3–A6 column values.

## Risk assessment

| | A1 | A2 | A3 | A4 | A5 | A6 | A7 |
|---|---|---|---|---|---|---|---|
| Trade frequency | LOW | LOW | LOW | MEDIUM | **HIGH** | MEDIUM | HIGH |
| Cost sensitivity | LOW | LOW | LOW | MEDIUM | **HIGH** | MEDIUM | UNKNOWN |
| Regime dependence | **HIGH** | **HIGH** | **HIGH** | UNKNOWN | MEDIUM | MEDIUM | UNKNOWN |
| Overfit risk | MEDIUM | MEDIUM | **LOW** | LOW | LOW | LOW | UNKNOWN |
| Native test feasible | YES | needs funding data | YES | needs 4h | YES | YES | **NO** |
| Normalized test feasible | YES | after data | YES | YES | YES | YES | partial, never "native" |
| Information gain | MEDIUM | MEDIUM-HIGH | **HIGH** | MEDIUM | **HIGH** | MEDIUM | UNKNOWN |
| Research priority | P2 | P2 | **P1** | P3 | **P1** | P2 | **HOLD** |

---

## The two findings that matter most

**The family's headline result is BTC-specific, and our universe is BTC *and* ETH.** The source
publishes its own generalisation test with no re-tuning: ETH +84% against buy-and-hold +53%,
XRP −48%, AVAX −53%, LINK −9%; three lost money outright and four lost to simply holding. The
author's verdict is `Works on other assets: fails ❌`. Whatever A1/A2 do on BTC, the ETH half of
our universe should be expected to look nothing like the headline.

**A4's benchmark rank contradicts its own author.** The CSV puts it 2nd of 42 at +1,170.9%.
Its docstring says it "doesn't really perfom that well and its just a proof of concept". Per the
evidence-precedence rule, repository evidence outranks marketing — but here both *are* repository
evidence, from different repositories, and they disagree. Both are recorded; neither is discarded.
