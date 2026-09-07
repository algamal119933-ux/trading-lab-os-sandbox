# POST-BASELINE-EXTBENCH-1 — Owner termination record

**Authority:** `TRADING_LAB_OS_OWNER_COMPRESSION_AND_FP_NEXT_STAGE_20260907.md`, §0
**Machine-readable twin:** `research/external/sprint_closure.json`

```text
§3.2_STATUS            = OWNER_TERMINATED_INCONCLUSIVE
SURVIVOR_STATE         = NOT_DETERMINED
NO_SURVIVOR            = NOT_ESTABLISHED
PROSPECTIVE_OOS_PROVEN = NO
DATASET_V2_VALIDATION_STATUS = SPENT / RETROSPECTIVE
DATASET_V2_REACQUIRED  = NO
REAL_MONEY_AUTHORIZED  = NO
```

The Owner deliberately terminated the remaining retrospective expansion of this
sprint before every preregistered arm had run, because *marginal retrospective
evidence no longer justifies delaying prospective forward-paper evidence*.

This is an amendment, not a relabelling. The sprint is **not** closed as
`SURVIVOR`, **not** closed as `NO_SURVIVOR`, and **not** a full preregistered
closure. No survivor is declared and no no-survivor claim is declared. Anyone
reading this repository later should take the terminal status at face value:
the question the sprint asked was not answered, and was not going to be answered
by continuing.

## What was executed, and what it means

`H1_DATASET_V2_DEVELOPMENT` ran end to end. `EmaCross` at `b68a5518`, strategy
sha256 `387cf39f…`, params sha256 `9209a90e…`, engine
`freqtradeorg/freqtrade:2026.7`, Dataset V2 Development 2021-01-01 → 2024-12-31,
BTC/USDT only, fee 0.001 per side. Run 34126570635, job 101756531915.

Every validity gate passed — reproduction identity across all five components,
load and config, safety compatibility, execution rights, data integrity against
the frozen lock, lookahead and recursive analysis, and window parity through the
warm-up overlay.

`H1_MEASUREMENT_VALIDITY = PASS`

| Metric | Value |
| --- | --- |
| Net return | +20.02 % |
| Trades | 76 (19 / 57), win rate 25 % |
| Profit factor | 2.17 |
| Max drawdown | 5.18 % |
| Sharpe / Sortino | 0.188 / 2.693 |
| Time in market | 56.38 % |

| Control | Return | Excess |
| --- | --- | --- |
| BTC buy-and-hold | +222.08 % | −202.06 pp |
| BTC max-exposure-matched | +44.42 % | −24.40 pp |
| **BTC realised exposure-matched** (the lane's preregistered control) | **+12.31 %** | **+7.72 pp** |

The governing interpretation, which must travel with these numbers wherever they
are quoted:

```text
H1 = VALID HISTORICAL MEASUREMENT
H1 != SURVIVOR
H1 != PROSPECTIVE EDGE PROOF
```

It is `C_DEVELOPMENT` evidence on a historical window. It beats its own realised
exposure line by 7.72 pp and loses to simply holding BTC by 202 pp. It was never
put to the survivor-selection decision, because that decision needed arms that
are now cancelled.

## What was cancelled

Every item below is recorded as
`NOT_EXECUTED — CANCELLED_BY_OWNER_COMPRESSION_AMENDMENT`:

* Track B — funding archive acquisition and verification
* `H2_DATASET_V2_DEVELOPMENT` (EmaCrossFunding)
* the H1-vs-H2 ablation
* the licensed Freqtrade negative control
* NFI native Spot qualification
* deep validation for survivors
* component mining and the one-component ablations
* TradingLabCandidateV1
* `ETH_GENERALIZATION_CHALLENGE`
* `CLAIM_SNAPSHOT_RECONSTRUCTION` and `CURRENT_NATIVE_REPLAY`

H2 deserves one sentence of its own, so its state is not misremembered as a
failure: **all of its validity gates passed**, and its backtest never ran
because `EmaCrossFunding.py` reads a perpetual funding series from
`research/webdata/funding.feather` that Track B was to supply. It was blocked on
a preregistered dependency, not found wanting.

## Preregistration is preserved, not rewritten

`candidate_registry.json`, `ablation_registry.json`, `qualification_gates.json`,
`upstream_pins.json` and `claims_snapshot.json` are untouched. They record what
was preregistered before any result existed, and a terminated sprint is not a
reason to edit them. The terminal status lives in a separate additive artifact
so that Repo Truth carries both facts without either overwriting the other.

The scorecard keeps its single executed row. An empty scorecard would have
misrepresented the sprint as never started; a scorecard with invented rows would
have misrepresented it as finished.

## Why the sprint stopped where it did

Two obstacles are worth recording, because they cost the sprint its momentum and
the next person should not rediscover them.

**GitHub registers a workflow for manual dispatch only once it is on the default
branch.** `dataset-v2.yml` was dispatchable only because PR #2 had put it on
`main`. `funding-probe.yml` never was, so Track B — H2's only supplier — was
never actually startable from this branch. The benchmark runner works around
this with a push trigger; the funding probe was never given the same treatment
before the amendment landed.

**Four defects were found and fixed during execution**, all recorded in
`EXTBENCH_EXECUTION_LOG.md`. The one worth repeating is that the warm-up join
wrote into the cached data directory, so a run cached 51,845 candles where the
frozen lock describes 50,382 — and the canonical-identity gate refused the next
run. The gate caught a real defect on its first real opportunity.

## Not a claim about the strategy

Nothing here says EmaCross is good or bad. It says one configuration of it was
measured validly, once, on a historical window, against controls chosen before
the result existed — and that the sprint designed to judge it was stopped, by
the Owner, for reasons of research priority rather than anything the measurement
showed.

---

`PAPER / RESEARCH ONLY`
`REAL_MONEY_AUTHORIZED = NO`
