# H1-PAPER-COHORT-1 — Prospective Paper Preregistration

**Frozen before any T0.** Part of `H1-PAPER-COHORT-PACKAGE-1` v1.0.0; its bytes
are bound by `PACKAGE_MANIFEST.sha256`. Authority: Owner directive
`H1-PAPER-ADMISSION-AND-LAUNCH-PACKAGE-1` (2026-09-29), which authorizes building
this package and **does not** authorize starting it. Admission record:
`research/paper/h1/H1_PAPER_ADMISSION_AND_LAUNCH_PACKAGE_1.md`.

PAPER / DRY-RUN ONLY · `REAL_MONEY_AUTHORIZED = NO` · no path to P3 or live.

---

## 1. Identity

The frozen identity is `cohort.json`. In brief: `H1_EMACROSS` =
upstream `wiktorj137/btc-strategy-lab@b68a5518`, `EmaCross.py` sha256
`387cf39f…a95f24`, `EmaCross.json` sha256 `9209a90e…27e3ee`
(`ema_period = 600`, `exit_threshold = 2.0`), BTC/USDT, 1h, Binance spot,
long-only. The strategy fixes `stoploss -0.15` and `trailing_stop = true`.
Engine: `freqtradeorg/freqtrade:2026.7` pinned by digest `sha256:da3428fd…a643`.
Wallet 100, stake 10, fee 0.1%/side. Cohort `H1-PAPER-COHORT-1`.

A changed strategy, parameter, pair, timeframe, engine or config is a **new
candidate**, not this cohort.

## 2. The prospective question

> Does the frozen H1 identity, running forward on data that did not exist at its
> freeze time, behave as its specification and historical profile say it
> should, and can this project operate it continuously and verifiably, all
> without any intervention?

This is deliberately **not** "will H1 make money?". The answer is split into two
classifications that are never merged (§5):

- **PROSPECTIVE_BEHAVIOR**: signal fidelity to the frozen code, completed trade
  lifecycles, drawdown envelope and cost treatment. Realised trade frequency and
  realised exposure are measured against the historical profile.
- **OPERATIONAL_CAPABILITY**: continuity of hourly processing, restart and
  recovery continuity, evidence-chain integrity and isolation from P2.

Profit and loss are reported as **EDGE_EVIDENCE**, which is descriptive only
(§5.3). This cohort cannot produce an edge verdict, and nothing in it may be
cited as proof of edge.

## 3. Historical profile (context only, cited not re-run)

From `TRIAL-H1-CD1` (seq 7) and `TRIAL-H1-QUAL-2` (seq 19), Development window
2021-01-01 → 2024-12-31:

| | 2021 | 2022 | 2023 | 2024 | 4-year |
|---|---|---|---|---|---|
| completed trades | 20 | 23 | 13 | 21 | 76 |
| net return % | +8.25 | −5.30 | +9.80 | +7.12 | +20.02 |
| max drawdown % | 1.75 | 5.61 | 1.17 | 2.12 | 5.18 |
| time in position % | 52.5 | 32.2 | 74.1 | 65.6 | 56.4 |
| win rate % | 25.0 | 17.4 | 30.8 | 28.6 | 25.0 |
| max consecutive losses | 6 | 8 | 5 | 4 | 8 |
| BTC market change % | +62.4 | −64.5 | +156.3 | +117.7 | +225.6 |

Cadence: 13–23 completed trades a year (mean ≈ 19); average holding time
≈ 10.8 days; at most one position at a time. This is a selected,
heavily examined, in-sample profile. It sets expectations for how much
evidence a window can hold. It is **not** a target.

## 4. Benchmark contract (frozen before T0)

Every benchmark uses Binance spot BTC/USDT public 1h candles for the exact
observation window `[ACTIVATION_UTC, END_UTC)`, fetched after the terminal
event, and charges a fee of 0.1% per side.

| Benchmark | Definition | Label |
|---|---|---|
| `CASH` | 0% | exact |
| `BTC_PASSIVE_FULL` | buy the whole 100 USDT wallet at the open of the first candle ≥ `ACTIVATION_UTC`, value it at the close of the last candle < `END_UTC`, and apply the fee on both sides | exact |
| `BTC_PASSIVE_REALISED_EXPOSURE_MATCHED` | `BTC_PASSIVE_FULL` return × H1's realised average capital exposure (`research/summarize_backtest.py` method: Σ(stake × hours held) / (wallet × window hours)) | **APPROXIMATE**, because it ignores *when* exposure occurred |
| `BTC_PASSIVE_TIMING_MATCHED` | BTC return over exactly the hours H1 held a position, at H1's stake, with the fee applied on each entry and exit | exact for timing; it isolates entry/exit selection from market beta |

The candidate's realised exposure is reported both as time in position (% of
window hours) and as average capital exposure (formula above). Fees are the
dry-run fills' recorded fee at 0.1% per side. Slippage and latency are
**not modelled** by Freqtrade dry-run. The dry-run fills from the order book
top (`price_side = other`), whereas backtests fill at the candle open, and this
difference is reported rather than corrected.

No benchmark may be added, removed or redefined after T0.

## 5. Terminal law

### 5.1 Window

```text
OBSERVATION_START    = ACTIVATION_UTC
MAX_CALENDAR_DURATION = 180 days
END_UTC              = ACTIVATION_UTC + 180 days  (fixed; no automatic extension)
```

**Rationale (recorded before T0).** Under a Poisson approximation at the
historical cadence, 180 days yields an expected 6.4 / 9.4 / 11.3 completed
lifecycles at the lowest / mean / highest historical yearly rate. The
probability of fewer than 4 lifecycles is 0.12 at the lowest rate and 0.02 at
the mean. A 90-day window would leave fewer than 4 lifecycles with probability
0.60 at the lowest rate and 0.31 at the mean, which would usually be
uninterpretable. A 365-day window doubles the opportunity cost for evidence that
still could not settle edge (§5.3). The window is **fixed-horizon**: no early
stop for good or bad performance, so no optional stopping.

Allowed early terminations, each recorded as a `COHORT_TERMINAL` incident:
- a `SAFETY_BREACH` (§7), which stops the cohort immediately;
- an Owner stop order;
- **P2 protection**: if the H1 runtime is shown to degrade a running P2 cohort,
  the H1 runtime stops and P2 is never touched.

At `END_UTC` the worker is stopped. **No position is force-closed**, because a
forced exit is forbidden (§6). An open position is recorded as open and valued
at the last close for mark-to-market reporting only. It never counts as a
completed lifecycle.

### 5.2 PROSPECTIVE_BEHAVIOR

The criteria are evaluated once, after `END_UTC`, over the whole window:

- **B1 Signal fidelity.** A post-terminal Freqtrade backtest of the frozen
  identity over the window's public candles (with its 1300-candle warm-up)
  defines the replay decisions. Every paper **entry** must match a replay entry
  on the same 1h candle, and every replay entry must appear in paper, unless it
  falls inside an `ACTIVATION_GAP` recorded before the terminal event. Paper
  **signal exits** (`ema_cross_down`) must match replay on the same candle,
  within ±1 candle. Stoploss and trailing exits depend on the intra-candle
  price path; they are reported by reason and time and are not gated.
- **B2 Lifecycles.** At least **4** completed lifecycles, each with the entry
  filled and the exit filled.
- **B3 Drawdown envelope.** The paper wallet's maximum drawdown stays
  **< 15%**. The historical worst was 5.61% in a year and 5.18% over the full
  window; each trade risks at most 15% of a 10% stake.
- **B4 Cost treatment.** Every fill carries fee = 0.1% per side.
- **B5 Coverage.** At least 80% of the window's 1h candles were processed; hours
  inside recorded `ACTIVATION_GAP`s count as not processed.

The measured quantities, reported descriptively and never gated, are: realised
trade frequency against the 13–23 a year range, realised time in position and
capital exposure against 32–74%, consecutive losses, and holding times.

```text
PROSPECTIVE_BEHAVIOR_NOT_SUPPORTED    B1 fails, or B3 fails, or B4 fails
INCONCLUSIVE_INSUFFICIENT_EVIDENCE    none of the above fails, but B2 or B5 does
PROSPECTIVE_BEHAVIOR_SUPPORTED        B1–B5 all pass
```

A truthful `INCONCLUSIVE_INSUFFICIENT_EVIDENCE` is a lawful outcome. It is not
extended and not "rescued".

### 5.3 EDGE_EVIDENCE (descriptive only)

The report gives: net return; each §4 benchmark and the difference from it; win
rate; profit factor; fees paid. This cohort **cannot** yield an edge verdict.
About 9 expected trades at a historical 25% win rate is far too few: the
chance of zero winners in 9 trades is 7.5% even if the historical profile is
exactly true. `H1_PROSPECTIVE_EDGE_PROVEN` stays `NO` whatever the result. Any
edge claim needs its own preregistered design, and this cohort's evidence would
be a single input to that design, not its conclusion.

```text
PAPER_EXPECTED_INFORMATION_RATE   EDGE = LOW · BEHAVIOR = MODERATE · OPERATIONAL = MODERATE
```

### 5.4 OPERATIONAL_CAPABILITY

```text
PROVEN        coverage ≥ 95% of 1h candles, ≥ 1 completed lifecycle, incident
              ledger verify() == [], restart_counter never reset, every restart
              reconciled, zero SAFETY_BREACH, zero P2 contamination finding
NOT_PROVEN    any SAFETY_BREACH, any P2 contamination, an incident-ledger chain
              break, or coverage < 80%
INCONCLUSIVE  otherwise (for example, coverage 80–95%, or zero completed lifecycles)
```

## 6. Freeze law (from T0 until the terminal record)

The following are forbidden: strategy modification; parameter, pair, timeframe,
entry, exit or threshold changes; config or package changes; forced trades;
artificial entries or exits (`force_entry_enable = false`; no `/forceenter` or
`/forceexit`); resetting, deleting or rewriting evidence; discarding adverse
periods; changing the benchmark or success criteria after results appear.

A technically recovered process continues **the same cohort** under §7. A
container recreated for recovery must come from the identical package: preflight
is re-run and its manifest digest must equal the one in `COHORT_START`.

## 7. Incident and recovery law

Incidents are appended by `h1_paper.py incident` to
`<lane>/evidence/paper_incident_ledger.jsonl`. It is hash-chained under
`research/fp/ledger.py` `CANONICAL_LEDGER_V1`, and payloads validate against
`incident.schema.json`. The rules are:
- The first record is `COHORT_START`. Its `recorded_utc` **is PAPER_T0**, and it
  carries the host bindings and the materialized strategy hashes.
- `restart_counter` is derived by the tool (`+1` per `PROCESS_RESTART`) and is
  never reset.
- Nothing may follow `COHORT_TERMINAL`.

| Event | Handling |
|---|---|
| Process/container restart | `PROCESS_RESTART` with the open-trade state read from the cohort DB before and after. Freqtrade reloads open trades from the same sqlite DB, so the lifecycle continues. |
| Missed hourly candle(s) | `ACTIVATION_GAP` with `missed_candles_1h`. Missed signals are **never** executed after the fact. |
| Market-data fetch failure | `MARKET_DATA_FAILURE`. Freqtrade retries, and no manual data is injected. |
| DNS / network failure | `DNS_NETWORK_FAILURE`. Record whether FP-CONTROL-3 logged a simultaneous incident; the correlation is noted and the ledgers are never merged. |
| Exchange API unreachable | `EXCHANGE_API_UNREACHABLE`. No manual trade, no config change. |
| Resource pressure | `RESOURCE_PRESSURE`. P2 takes priority: H1 may be stopped, and P2 is never throttled. |
| Reconciliation | `RECONCILIATION` at every restart, weekly, and at the terminal event: open trades in the DB are compared with the API `/status` and the log. |
| dry_run ≠ true, a credential present, or a P2 path written | `SAFETY_BREACH` → immediate stop → `COHORT_TERMINAL` |

**Digest continuity.** At the terminal event, the sha256 of the DB, the logs and
the incident ledger go into `COHORT_TERMINAL`. The lane is then copied to the
primary evidence store and to a second durable copy (a launch precondition,
§9).

## 8. Placement, resources, network

**Placement.** Prefer a separate persistent host; none exists (2026-09-29).
While FP-CONTROL-3 is active, the recommendation is
`WAIT_FOR_P2_CLOSURE`: its hard cap is **2026-10-24T12:01:14Z** at the
latest. The same-host reasons are that Binance request weight is counted per
egress IP and both runtimes would share it, that both would share one DNS
resolver (given the prior DNS incidents), and that they would share one Docker
daemon and one disk. Incident attribution between the two cohorts would also be
ambiguous. A wait of at most about 25 days costs little against a 180-day
window. `ISOLATED_SAME_HOST_AFTER_OWNER_APPROVAL` is technically supported by
this package and requires an explicit Owner decision.

**Resource law** (enforced in `docker-compose.h1-paper.yml`, checked by
`verify`):

```text
cpus 1.0 · cpu_shares 256 (P2 default 1024) · mem_limit 1g · memswap_limit 1g · pids_limit 256
oom_score_adj 500 (killed before P2) · no-new-privileges · docker log 10m × 5
own compose project / container / bridge network · API on 127.0.0.1:8181 only
no mount of any P2 path · config and strategy read-only · the lane is the only writable mount
lane disk budget 2 GB · preflight requires ≥ 20 GB free on the lane filesystem
```

**Network.** One pair on 1h makes Freqtrade's steady state one OHLCV refresh
per candle, a periodic market reload, and order-book/ticker calls around
open trades. This is orders of magnitude below Binance's per-IP weight limit,
but it is not zero, and it shares FP-CONTROL-3's IP and resolver. That is the
reason for §8's placement recommendation.

## 9. T0 and launch binding

- The launch authorization must name `PACKAGE_MANIFEST.sha256`'s digest. If any
  package byte changes after that authorization, the authorization is void and
  must be re-issued.
- Launch preconditions (none are satisfied by this package unit):
  1. an Owner launch authorization;
  2. a verified second durable evidence copy location;
  3. the placement decision (§8);
  4. `h1_paper.py verify` = PASS;
  5. materialization in a credential-free environment: `pin_upstream.py --verify
     --materialize <W>`, then copy exactly `EmaCross.py`, `EmaCross.json` and
     `LICENSE` into the strategy dir;
  6. `h1_paper.py preflight --lane-dir … --strategy-dir …` = PASS;
  7. start;
  8. `COHORT_START` incident, which sets PAPER_T0.
- Nothing observed before PAPER_T0 is prospective evidence.

## 10. No P3 / live path

This package contains no exchange credential, no withdrawal capability, no live
order route, and no automatic transition to P3, controlled live or real money.
A `PROSPECTIVE_BEHAVIOR_SUPPORTED` result requires a new, explicit Owner
decision for anything further.
