# POST-BASELINE-EXTBENCH-1 — execution log

Written during §3.2 execution under the owner's execution directive. This is an
**execution log, not a closure record**. The sprint is not lawfully closed; §6
allows closure only as SURVIVOR, NO_SURVIVOR or TRUE_STOP, and none of those is
yet established.

```text
SPRINT_STATE = EXECUTING — Wave 1 partially complete
CLOSURE      = NOT REACHED
MERGED       = NO
DATASET_V2_VALIDATION_STATUS = SPENT / RETROSPECTIVE (untouched by this work)
PROSPECTIVE_OOS_PROVEN = NO
REAL_MONEY_AUTHORIZED = NO
```

## Preflight (§2)

All ten steps pass. The merge of authoritative `main` into this branch was a
normal merge commit; every preregistration artifact survived byte-identical by
git blob object ID, and the only file that changed was
`dataset_v2.lock.json`, which moved from the pre-acquisition stub to the frozen
lock by merge rather than by reacquisition — exactly what §2 of the governing
TL-FP-BOOT directive requires. The activation gate, recorded as NOT MET when
this registry was frozen, is now satisfied: `1dfb696` is an ancestor of
`origin/main`.

## How the sprint had to be executed

The research sandbox cannot execute a candidate — no Freqtrade, no Docker, no
pandas, no market data, `api.binance.com` blocked and `github.com` answering 403
so there is no clone. Only `raw.githubusercontent.com` is reachable.

A second obstacle was not in the preflight findings: **GitHub only registers a
workflow for manual dispatch once it is on the default branch.** `dataset-v2.yml`
was dispatchable only because it had landed on `main` in PR #2, and
`funding-probe.yml` has never been runnable from this branch for exactly this
reason — Track B was never actually startable. Merging benchmark infrastructure
to `main` ahead of its own closure is not authorised, so `extbench.yml` runs on a
push trigger instead: pushing `extbench/run/<LANE>` executes a lane and
`extbench/gates/<LANE>` runs the validity gates and stops. The lane is validated
against the frozen registry, so an unregistered lane fails the run.

## H1_DATASET_V2_DEVELOPMENT — executed

`EmaCross` at `b68a5518`, strategy sha256 `387cf39f…`, params sha256
`9209a90e…`, engine `freqtradeorg/freqtrade:2026.7`, Dataset V2 Development
(2021-01-01 → 2024-12-31), BTC/USDT only, fee 0.001 per side.
Run 34126570635, job 101756531915.

### Validity gates

| Gate | Result | Evidence |
| --- | --- | --- |
| V1 reproduction identity | PASS | all five components pinned; strategy SHA matched the registry |
| V2 load and config | PASS | backtest completed; paper guard passed on the config used |
| V3 safety compatibility | PASS | source read before running; long-only, no shorts/futures/margin/leverage |
| V3B execution rights | PASS | GPL-3.0 at the pinned commit; not vendored |
| V4 data integrity | PASS | `DATASET_LOCK_GATE = PASS (content matches the frozen lock)` |
| V5 lookahead | PASS | no lookahead on indicators; recursive drift 0.074 % at 1300 startup candles, −0.004 % at 1999 |
| V7a window parity | PASS | overlay joined, 2203 valid warm-up candles against a 1300 requirement, canonical identity preserved |

`MEASUREMENT_VALIDITY = PASS`.

### Result

| Metric | Value |
| --- | --- |
| Net return | **+20.02 %** |
| Trades | 76 (19 win / 57 loss), win rate 25.0 % |
| Max drawdown | 5.18 % |
| Profit factor | 2.169 |
| Sharpe / Sortino | 0.188 / 2.693 |
| Time in market | 56.38 % |
| Avg / peak capital exposure | ~5.54 % / 9.997 % |
| Return per unit of exposure | 361.3 |
| Max consecutive losses | 8 |
| Fees | 1.4907 stake units |

### Fair controls, and why the comparison is not one number

| Control | Return | Excess |
| --- | --- | --- |
| BTC buy-and-hold | +222.08 % | −202.06 pp |
| BTC max-exposure-matched (20 % invested) | +44.42 % | −24.40 pp |
| **BTC realised exposure-matched** | **+12.31 %** | **+7.72 pp** |

The lane's preregistered `fair_controls` name the **realised** exposure-matched
passive, so **+7.72 pp** is the excess this lane is judged on. The candidate
holds about 5.5 % average capital exposure and returns more per unit of capital
at risk than that capital would have earned sitting in BTC over the same window.

Three things must be said alongside that, or the number misleads:

* It loses heavily to plain buy-and-hold. On this window BTC rose 222 %, and a
  strategy in the market 56 % of the time captured 20 %.
* The realised-exposure line is an approximation that, in the tool's own words,
  "ignores when that exposure occurred". A strategy exposed during calm periods
  and flat during rallies is flattered by it.
* A 25 % win rate with profit factor 2.17 is a small number of large winners.
  Concentration is not yet quantified, and the frozen scorecard has a column for
  it that is still empty.

`CANDIDATE_QUALITY` is therefore **not** decided here. It is a survivor-selection
decision on the Pareto axes, and that decision needs the rest of Wave 1.

## H2_DATASET_V2_DEVELOPMENT — blocked on its preregistered dependency

All validity gates pass; the backtest does not run. `EmaCrossFunding.py` at the
pinned commit reads a perpetual funding series from
`research/webdata/funding.feather`, which does not exist in this repository.

That is the Track B dependency the sprint preregistered, not a defect in the
candidate or the runner. The sprint's own ordering puts Track B concurrent with
Track A and never blocking it, and makes H2 alone depend on it.

```text
H2_MEASUREMENT_VALIDITY = NOT ESTABLISHED — candidate did not execute
H2_BLOCKED_ON = funding archive acquisition (Track B)
```

The funding probe workflow exists but has never been runnable, for the
default-branch dispatch reason above. Giving it the same push trigger is the
next step for H2.

## What remains before this sprint can close

Closure is not a matter of writing it up. Still outstanding:

1. Track B: acquire and verify the funding archive, then execute H2 and the
   H1-vs-H2 ablation.
2. The licensed Freqtrade negative control.
3. NFI native Spot qualification.
4. Deep validation for whichever two or three candidates survive.
5. Component mining and the one-component ablations.
6. The survivor decision itself, on the Pareto axes, against the frozen gates.

Until those are done there is no lawful SURVIVOR or NO_SURVIVOR, and §10 forbids
merging a closure that its own evidence does not support.

## Defects found and fixed during execution

Recorded because the sprint's discipline is to keep its own errors visible.

* **The warm-up join outlived its run.** `join_warmup_overlay.py` writes the
  joined series into the data directory, that directory was the cache path, and
  a run therefore cached 51,845 candles where the frozen lock describes 50,382.
  The next run restored it and V4 correctly reported that Dataset V2 no longer
  matched its canonical digests. The canonical-identity gate caught a real
  defect, on its first opportunity. The cache now holds only the pristine
  acquisition and every run rebuilds a working copy from it.
* **V4 was asserting a slice of the lock.** The first run acquired BTC only,
  because the lane is BTC-only, and V4 failed on the missing ETH files. V4 asks
  whether the underlying data is *the frozen dataset*; asserting part of it
  would be a weaker gate wearing the same name. The universe is narrowed in the
  config now, not in the acquisition.
* **A shallow config merge silently removed the exchange.** The data-mirror
  overlay's `exchange` block carries no `name`, so a `dict.update` replaced
  binance with a block that names no exchange, and Freqtrade reported only "This
  command requires a configured exchange".
* **The passive report crashed on a single-asset universe**, after printing its
  header, because it formatted `result['ETH']` unconditionally.

## Evidence that Dataset V2 reproduces

Not a sprint deliverable, but worth recording: the runner re-acquired Dataset V2
independently from the public archive and reproduced the frozen canonical
digests exactly, for all four files. The raw Feather hashes differ and were
correctly classified as a serialization note rather than drift — the distinction
`CANONICAL_CANDLE_V1` exists to make.

---

`PAPER / RESEARCH ONLY`
`REAL_MONEY_AUTHORIZED = NO`
