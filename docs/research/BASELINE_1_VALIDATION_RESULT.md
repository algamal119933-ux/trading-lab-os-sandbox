# BASELINE-1 — Validation result on Dataset V2

**Run once, unchanged.** Evidence: GitHub Actions run
[34077370180](https://github.com/algamal119933-ux/trading-lab-os-sandbox/actions/runs/34077370180),
code commit `e98943c`, strategy sha256 `8c0bc6c5…` — byte-identical to the file
evaluated on Development — config `fc00865b…`, also unchanged.

Machine-readable record: `research/records/baseline1_validation_datasetv2.json`.

## What was frozen before this ran

* The strategy: not one line changed between Development and Validation.
* The Development protocol: closed as `BASELINE_PROTOCOL_RESULT = PASS`
  ([`BASELINE_1_DEVELOPMENT_RESULT.md`](BASELINE_1_DEVELOPMENT_RESULT.md))
  before this window was touched.
* The classification thresholds: pre-registered in
  [`BASELINE_1_PROTOCOL.md`](BASELINE_1_PROTOCOL.md).
* The dataset: the run asserted all eight fingerprints against the frozen lock
  before the backtest was allowed to start.

## `VALIDATION_PERFORMANCE_CLASSIFICATION = NEUTRAL`

## Validation backtest — 2025-01-01 → 2026-08-31 (607 days)

| Metric | Value |
| --- | --- |
| Trades | 96 (25 win / 71 loss, **26.0 %** win rate) |
| Total return | **−0.07 %** (−0.068 USDT on a 100 USDT wallet) |
| Average profit per trade | −0.02 % |
| Average trade duration | 6 days 2:04 |
| Profit factor | **1.00** (0.997) |
| Max drawdown (wallet basis) | **9.41 %** (9.848 USDT) |
| Max drawdown (closed-trade basis) | 8.02 % (8.016 USDT) |
| Min / max wallet balance | 92.288 / 104.619 USDT |
| Max consecutive losses / wins | **14** / 4 |
| Sharpe — daily wallet balance / closed trades | 0.03 / −0.00 |
| Sortino — daily wallet balance / closed trades | 0.05 / −0.01 |
| Calmar — daily wallet balance / closed trades | −0.01 / −0.03 |
| Market change over the window | **−21.70 %** |
| Per-pair attribution | ETH/USDT **+1.70 %**, BTC/USDT **−1.77 %** |
| Time in market | 55.72 % |
| Average capital exposure | 9.30 % |
| Peak capital exposure | 19.77 % (2 concurrent trades) |
| Return per unit of exposure | −0.73 % |
| Turnover / fees | 1,862 USDT / ≈ 1.86 USDT |

## Passive comparison

| Benchmark | Return |
| --- | --- |
| 50/50 fully invested | −21.85 % |
| Max-exposure-matched (20 % invested throughout) | −4.37 % |
| **Realised-exposure-matched (9.30 % average exposure)** | **−2.03 %** |
| **BASELINE-1** | **−0.07 %** |
| **Excess over realised-exposure-matched** | **+1.97 pp → NEUTRAL** |

Profit factor 0.997 is above the 0.8 WEAK threshold and 96 closed trades is
above the 30-trade minimum, so NEUTRAL here is a result on the merits, not a
verdict withheld for lack of data.

## Reading it honestly

The window fell 21.7 %. The baseline finished flat — down 0.07 %, which after
1.86 USDT of fees is a wash — and did it while holding positions 56 % of the
time. Against passive at the same average exposure it is ahead by 1.97
percentage points.

That is consistent with Development, which is the useful part. On a four-year
bull-dominated sample it came in 1.38 pp *behind* exposure-matched passive; on a
twenty-month falling sample it came in 1.97 pp *ahead*. Both are inside the
NEUTRAL band, and together they describe a rule that mostly reproduces the
return of the exposure it takes, shifting a little with regime and not much:
it clips some of the downside a passive holder would have eaten, and gives back
a similar amount of upside. There is no evidence here of edge, and none of
serious harm either.

Two things are worth noting for any successor candidate, without acting on them
now:

* **14 consecutive losses**, against 12 on Development. An EMA-cross rule
  whipsaws in a range, and the Validation window had more range than trend.
* **Per-pair attribution flipped sign**: ETH carried Development (+18.70 % vs
  BTC's +9.10 %) and stayed marginally positive here (+1.70 %) while BTC turned
  negative (−1.77 %). Two pairs is far too small a cross-section to call that
  anything but noise.

## What this is not

* **Not a Locked OOS result.** Dataset V1 work already inspected parts of
  2025-2026, so no span of this dataset qualifies as pristine holdout. This
  window is Validation, and is labelled that everywhere.
* **Not a tuning signal.** This result has not been used to change BASELINE-1
  in any way. Under the protocol, any tuning prompted by it must become a new,
  explicitly versioned candidate — it cannot be folded back into the reference.
* **Not forward evidence.** The first strict prospective holdout must be
  forward paper over data that did not exist when the strategy was frozen. None
  exists yet.
