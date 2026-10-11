# FUNNEL-LAW-2 — AUTH-2-DISCOVERY-QUALIFICATION-1

Status: binding for AUTH-2 only, from the Owner merge of the PR that adds this file. Never retroactive: it
changes no verdict, result or ledger record of Cycles 1–2 or any earlier program.

Source: the Owner-approved "AUTH-2 final frozen package" (2026-10-10; 10/10 Owner decisions closed), file sha256
`eda2d62b6b631bd4b3ddfaa67ea4f7e528ec1cb42a863d1af2cb69c03d099361`. Every section below is copied from it verbatim, in order:

  FINAL_AUTH2_SPEC: lines 11–52
  PRIMARY_CONFIGS: lines 102–110
  ROBUSTNESS_PERTURBATIONS: lines 112–128
  Matched benchmarks (Owner item 4): lines 132–140
  COMMON_GATES (C1–C12): lines 144–163
  A1_SPECIFIC_GATES: lines 165–171
  A2_SPECIFIC_GATES: lines 173–181
  A3_SPECIFIC_GATES (risk-overlay experiment): lines 183–193
  POINT_IN_TIME_UNIVERSE_LAW: lines 197–235
  A3_VALID_WINDOW: lines 239–253
  CALIBRATION_DAG: lines 257–309
  MULTIPLE_TESTING_LAW: lines 313–335
  BOOTSTRAP_RULE [OD-3]: lines 339–352
  REPLAY_EVALUATOR_CONTRACT [OD-6]: lines 356–377
  CALIBRATION_POWER_PROOF: lines 381–384
  COMPUTE_CAP_PROOF: lines 399–449
  MONTHLY_BILLING_PACING_RULE [OD-8]: lines 451–470

Omitted on purpose, because they are not AUTH-2 gate law: the change map (history), the planning pre-check of
§CALIBRATION_POWER_PROOF (the package itself says it "decides nothing"), PAPER_R1_RULE (AUTH-3 content, not
authorised here), the real-money ladder (AUTH-4), the errata draft (committed separately as
`research/RESEARCH_CYCLE2_CLOSURE_1_ERRATA_1.md`) and the platform-decision list.

The final section, §DAG_OPERATIONS, is not from the package. It states how the frozen DAG above is executed and
recorded; it adds no gate, threshold, family, node or authority. Where a rule needs an operational definition the
package does not spell out, the definition is in `research/auth2/IMPLEMENTATION_NOTES.md` and is fixed, with every
threshold, in the node preregistrations under `research/auth2/prereg/` before any node runs.

PAPER / RESEARCH ONLY. dry_run stays true; no exchange key, order, leverage, margin, future or short exists anywhere
in AUTH-2.

---

## FINAL_AUTH2_SPEC

```text
PROGRAM_ID        = AUTH-2-DISCOVERY-QUALIFICATION-1
SCOPE             = research only · spot only · long/cash only · no leverage/margin/futures/shorts · no keys ·
                    funding data read-only as a feature
FAMILIES          = A1 TSMOM-VT · A2 XSMOM-LO · A3 CROWD-OVERLAY (risk-overlay experiment). No other family.
SELECTION LAW     = one PRIMARY configuration per family, fixed before any result. Every other grid member is a
                    PRECOMMITTED ROBUSTNESS PERTURBATION that can only reject. No TRAIN ranking, no promotion,
                    no substitution, hyperopt = 0.
FUNNEL            = FUNNEL-LAW-2 = COMMON CORE (C1–C12) + family-specific mechanism gates (A1-x, A2-x, A3-x).
                    PBO mandatory and always reported; diagnostic only.
CALIBRATION       = per family: statistical calibration (size and power) + planted-edge positive control PC-Ax +
                    real-data null N-Ax, each traversing that family's actual procedure.
DATA              = Dataset V3: Binance public archive, spot 1h klines 2018-01-01 → 2026-08-31 for every USDT spot
                    symbol in the archive (live and delisted); USDT-M funding archive BTCUSDT/ETHUSDT read-only;
                    point-in-time U6/U12 membership tables frozen in the lock.
ENGINE            = Freqtrade, research image freqtradeorg/freqtrade:2026.7 for the whole of AUTH-2 [OD-5]; no re-pin
                    inside the program; any later upgrade needs a separate frozen parity check after AUTH-2 closure.
                    Base timeframe 4h derived deterministically from 1h (reconciliation gate).
STATISTICS LIB    = bashtage/arch, one exact version hash-pinned at package freeze (latest tag today: v8.0.0), used only
                    for optimal_block_length, StationaryBootstrap and SPA; never re-pinned inside the program.
WINDOWS           = A1/A2 scored 2019-01-01 → 2024-12-31 · A3 scored from its own A3_START (rule in A3_VALID_WINDOW)
                    → 2024-12-31 · secondary confirmation 2025-01-01 → 2026-08-31 (non-pristine; reject-only)
HOLDOUT           = Option B unchanged: the first strict holdout is prospective live-market paper.
CAPS              = ENGINE_INVOCATIONS ≤ 240 · AUTH2_ATTRIBUTED_GITHUB_LINUX_MINUTES ≤ 4000 (program lifetime) ·
                    PAID_ACTIONS_OVERAGE = USD 0 · monthly pacing inside included minutes with a CI/merge-law reserve
                    [OD-8] · HYPEROPT = 0 · LLM_AGENT_TOKENS = 0 · configurations 16 · scientific trial IDs 5 ·
                    calibration trial IDs 12
NEVER             = retroactive application to Cycles 1–2 · a node outside the DAG · post-result hypothesis invention ·
                    widening universe, budget, thresholds, risk or paper admission · historical allocation evidence
```

Records the package needs (each a protected-path, Owner-merged change; listed so nothing is hidden):
1. `research/auth2/FUNNEL_LAW_2.md` (this document's gate sections, verbatim).
2. `charters/research_program.schema.json` v2 [OD-7]: extended only to represent node kinds `DATA_LOCK`, `CALIBRATION_STAT`, `POSITIVE_CONTROL`, `NULL_CALIBRATION`, `SCIENTIFIC`, `HOLM`, `SECONDARY_CONFIRM`, the attributed-minutes cap and the frozen terminal DAG. No generic workflow abstraction, no new authority model, no orchestration framework; schema and validator stay protected, Owner-merged paths.
3. `research/auth2/prereg.schema.json` (`auth2-prereg-1.0.0`).
4. `research/datasets/dataset_v3.lock.json` + membership tables + coverage report.
5. Fixtures: A1/A2/A3 strategies, three matched benchmarks, three null fixtures, three synthetic generators.
6. A parity-checked **replay evaluator** [OD-6] under the contract in §REPLAY_EVALUATOR_CONTRACT.
7. `charters/programs/AUTH-2-DISCOVERY-QUALIFICATION-1.json` with every prereg sha256.
8. Append-only Cycle-2 errata record (text in §ERRATA_DRAFT).

---

## PRIMARY_CONFIGS

Chosen before any AUTH-2 result, from the literature in the replan §F, not from TLOS data. Their choice is still a human selection and is disclosed as such in each prereg.

| Family | Primary configuration | Rationale |
|---|---|---|
| **A1 TSMOM-VT** | Per U6 sleeve: signal = sign of the equal-weight mean of trailing returns over {20, 60, 120} days (lookback set M); long when > 0, else cash. Sleeve size = min(1, 25% ÷ realised vol over the last 30 days) × 1/6 of equity. Total exposure ≤ 100%. Decision at 00:00 UTC on daily closes; execution at the next 4h bar open. Each sleeve is sized independently, so per-asset decomposition is exact. | 1–4+ month TSMOM horizons (Liu & Tsyvinski 2021); 25% per-position vol target as in Zarattini et al. 2025 |
| **A2 XSMOM-LO** | Weekly, Monday 00:00 UTC. Rank point-in-time U12 by the 28-day return ending 1 day before the decision (skip 1 day). Cash gate: a coin is eligible only if that return > 0. Hold the top k = 3 eligible coins, each 1/3 of equity; unfilled slots stay in cash. | 2–4 week crypto momentum; skip-day guards against the short-term reversal documented for daily returns |
| **A3 CROWD-OVERLAY** | Base = BTC and ETH sleeves, always long, each min(1, 25% ÷ 30-day realised vol) × 1/2 of equity. Overlay per asset: m7 = 7-day mean funding rate; z = (m7 − mean(m7, trailing 365 days)) ÷ sd(m7, trailing 365 days); when z > 2.0 the sleeve is cut to 50% of base size until z ≤ 2.0. | High carry predicts crashes (BIS WP 1087); partial de-risking is the conservative primary |

---

## ROBUSTNESS_PERTURBATIONS

One dimension changed at a time around the primary. Each perturbation counts toward N (N LAW unchanged). It can reject the family; it can never replace the primary.

| Family | Perturbations (precommitted) | Count |
|---|---|---|
| A1 | P1 lookback set S = {10, 20, 40} · P2 lookback set L = {40, 120, 250} · P3 target vol 15% · P4 target vol 40% · P5 vol window 60 days | 5 → N family = 15 inherited + 6 = **21** |
| A2 | P1 lookback 14 days · P2 lookback 56 days · P3 k = 2 · P4 k = 5 · P5 no skip day | 5 → N = **6** |
| A3 | P1 z threshold 1.5 · P2 z threshold 2.5 · P3 action cut to 0% | 3 → N = **4** |

Fixed stress variants (cost ×2, cost ×3, +1 bar latency) and fixed spec checks (A2 U8 universe, A2 weekday offsets, leave-one-out checks) are **not** configurations: they can only reject and are never selectable.

Perturbation instability rule **[OD-2]**: the family FAILS instability (⇒ REJECTED) if either
- **positive count**: fewer than 4 of 5 perturbations (A1, A2), or fewer than 2 of 3 (A3, paired), have ΔSR > 0 versus the matched benchmark; or
- **significant negative**: for each perturbation j, test H0: ΔSR_j ≥ 0 against H1: ΔSR_j < 0 with the paired studentized stationary bootstrap (block length from §BOOTSTRAP_RULE, computed on that perturbation's paired series); apply Holm across the family's 5 (A3: 3) negative-direction p-values at family-wise α = 0.10; any Holm rejection fails the family.

No single unadjusted p-value rejects. Perturbations remain reject-only and never replace the primary.

---

## Matched benchmarks (Owner item 4)

| Family | Matched benchmark | What the difference isolates |
|---|---|---|
| A1 | `A1-BENCH`: same point-in-time U6, same per-sleeve VT law (25%, 30-day vol), same 1/6 sleeves, same daily rebalance and execution timing, **always long**, no timing signal | value of trend timing |
| A2 | `A2-BENCH`: same point-in-time U12, same weekly schedule, same skip-day lookback and cash gate. Gross exposure each week is matched exactly to the primary's: min(k, n_eligible)/k of equity, spread equally across **all** eligible coins. No ranking, no top-k. | value of relative-strength selection, separated from the cash gate |
| A3 | `A3-BASE`: exactly the base exposure with no overlay | value of the crowding overlay (paired ablation) |

Benchmarks run under the identical cost, stress and latency variants as the strategy they are compared with.

---

## COMMON_GATES (C1–C12)

All thresholds below are preregistered in each prereg; no code defaults.

| Gate | Rule |
|---|---|
| **C1 INTEGRITY** | DATA_TRUTH against the V3 lock (klines, funding, membership, delisting and coverage files; 1h→4h reconciliation) · LOOKAHEAD · RECURSIVE · LEDGER_CHAIN · ENGINE_FEE_PROPAGATION · REPLAY_PARITY (replay evaluator reproduces each engine equity curve: daily-return correlation ≥ 0.999 and total-return difference ≤ 0.25 pp). Any failure ⇒ INVALID_RUN. |
| **C2 ABSOLUTE NET ECONOMICS** | Primary configuration at base cost: total net return > 0 and annualised net Sharpe > 0 over the scored window |
| **C3 MATCHED-BENCHMARK INFERENCE** | ΔSR = SR(primary) − SR(matched benchmark) on the scored window; one-sided p-value from the studentized stationary bootstrap of Ledoit & Wolf (2008), resampling strategy and benchmark days jointly (paired); 10,000 resamples, fixed seed; expected block length from the frozen §BOOTSTRAP_RULE **[OD-3]**, with sensitivity at 5, 20 and 60 always reported (sensitivity never changes the verdict). This p-value enters Holm (C9). |
| **C4 FAMILY-MATCHED NULL** | ΔSR(primary) > 95th percentile of the family null distribution (1,000 draws, fixed seed): A1 random-timing nulls; A2 random-selection nulls; A3 random-overlay nulls (definitions in CALIBRATION_DAG). Empirical p ≤ 0.05. |
| **C5 COST STRESS** | At 2× total cost: ΔSR > 0 and net return > 0. 3× is reported only. |
| **C6 LATENCY STRESS** | Execution one extra 4h bar late (strategy and benchmark): ΔSR > 0 |
| **C7 ROBUSTNESS PERTURBATIONS** | Perturbation instability rule above |
| **C8 COVERAGE** | Minimum operational coverage (not independence): A1 ≥ 100 sleeve position changes; A2 ≥ 250 weekly decisions with at least one holding; A3 ≥ 6 independent crowding episodes (episode rules in A3 gates). Dependence is handled only by C3/C4/C9 inference. Short coverage ⇒ INCONCLUSIVE. |
| **C9 MULTIPLE TESTING** | DSR ≥ 0.95 · Hansen SPA p ≤ 0.05 · Holm across the three family hypotheses (details in MULTIPLE_TESTING_LAW) |
| **C10 SECONDARY CONFIRMATION** | Run only after C1–C9 and family gates pass and Holm passes: on 2025-01-01 → 2026-08-31 with point-in-time membership, ΔSR point estimate > 0. Reject-only; it can never rescue. |
| **C11 PBO (diagnostic)** | CSCV over the family grid (primary + perturbations), 16 contiguous blocks of daily returns; value always reported in the result; **never a gate**. |
| **C12 LAW** | Prereg bound in the ledger before the run; N LAW; caps; ledger chain; no post-result changes |

Costs (unchanged from the replan): fee 0.10%/side + slippage 0.05%/side ⇒ engine fee 0.0015; stress ×2 = 0.0030; ×3 = 0.0045 reported. A2 members ranked 7–12 by volume carry +0.05%/side extra slippage.

---

## A1_SPECIFIC_GATES

| Gate | Rule |
|---|---|
| A1-1 TREND EPISODES | Episodes are defined ex ante on the U6 equal-weight always-long index: a maximal run in which the sign of its 120-day trailing return stays constant for ≥ 60 days. The scored window must contain ≥ 2 down-trend and ≥ 2 up-trend episodes (coverage). **Leave-one-episode-out**: ΔSR > 0 with any single episode removed. |
| A1-2 CROSS-ASSET BREADTH | Per-sleeve ΔSR > 0 in ≥ 4 of the U6 sleeves with ≥ 2 years of scored membership; **leave-one-asset-out** ΔSR > 0 for every asset that ever entered U6 |
| A1-3 MECHANISM SIGNATURE (report-only) **[OD-4]** | Primary max drawdown versus A1-BENCH max drawdown over the scored window is reported in every result. It is **not** a rejection gate; A1 is judged on matched risk-adjusted edge, robustness, breadth, costs, latency and the other frozen gates. |

---

## A2_SPECIFIC_GATES

| Gate | Rule |
|---|---|
| A2-1 COIN BREADTH | **Leave-one-coin-out**: rebuild U12 point-in-time without coin c, rerun primary and A2-BENCH in the replay evaluator; ΔSR > 0 for every coin that was ever held |
| A2-2 FOLD BREADTH | ΔSR > 0 in ≥ 4 of the 6 calendar years 2019–2024 |
| A2-3 UNIVERSE BREADTH | U8 (top 8, same rules) primary vs U8 benchmark in the engine: ΔSR > 0 |
| A2-4 SCHEDULE BREADTH | Rebalance weekday offsets Mon…Sun in the replay evaluator: median ΔSR over the 7 offsets > 0 |
| A2-5 DATA_LIMITED | If the lock's coverage report shows point-in-time member-days without price data > 1.0% of all U12 member-days, A2 terminates **DATA_LIMITED / INCONCLUSIVE** before any market-data trial. No threshold adjustment compensates. |

---

## A3_SPECIFIC_GATES (risk-overlay experiment)

| Gate | Rule |
|---|---|
| A3-1 PAIRED IMPROVEMENT | C3 applied as a paired ablation (overlay vs A3-BASE on the same days) |
| A3-2 CRASH-AVOIDANCE SIGNATURE (hard gate) **[OD-4]** | Overlay max drawdown < base max drawdown **and** overlay CVaR(5%) of daily returns better than base (point estimates) |
| A3-3 EPISODE REPETITION | Episode = maximal run with z > primary threshold for an asset; episodes of the same asset separated by < 30 days merge. Coverage ≥ 6 episodes across BTC and ETH. **Leave-one-episode-out**: paired ΔSR > 0 with any single episode removed. |
| A3-4 ASSET BREADTH | Paired ΔSR > 0 for BTC and for ETH separately |
| A3-5 COST OF INSURANCE | Forgone return versus base is reported (not gating) |

C2 for A3 means the overlay strategy itself has positive net economics; it is not required to beat the base on raw return.

---

## POINT_IN_TIME_UNIVERSE_LAW

```text
CANDIDATE POOL     every USDT-quoted Binance spot symbol present in the public archive at any time 2017-08 → 2026-08,
                   including delisted symbols. Listing date = first archived kline; delisting date = last archived
                   kline followed by no data (both recorded in the lock).
EXCLUSIONS         stablecoins, fiat-pegged and commodity-pegged tokens, leveraged tokens (UP/DOWN/BULL/BEAR) and
                   wrapped/bridged duplicates, classified from each symbol's stated design at listing time (a frozen
                   classification table in the lock, built without reference to later outcomes; e.g. an
                   algorithmic stablecoin is excluded as a stablecoin even if it later collapsed).
RANKING STATISTIC  trailing 90-day sum of USDT quote volume from archived klines, ending at the selection timestamp.
ELIGIBILITY        listed ≥ 365 days (U6) / ≥ 90 days (U12) before the selection timestamp; ≥ 90 days of volume.
                   Nothing about the future (later survival, later listing status, later volume) is used.

U6  (A1, A3 excluded)   selection on 1 January each year 2019 … 2026: top 6 eligible by the ranking statistic.
                        Membership is fixed for the year. A delisted member is handled by the DELISTING CONVENTION
                        and its sleeve stays in cash until the next selection date.
U12 (A2)                selection at each month end from 2018-12-31: top 12 eligible. Membership is fixed for the month.
                        A delisted holding is handled by the DELISTING CONVENTION; its slot stays in cash until the
                        next universe-selection date.

DELISTING CONVENTION [OD-10]
  PRIMARY       forced exit at 0.80 × last archived 1h close, then the normal frozen fee and slippage
  DIAGNOSTICS   no-haircut (1.00 × last archived close) and severe stress (0.60 ×) — reported only; they can
                never rescue a primary failure
  TRUSTWORTHY TERMINAL PRICE  the 24 archived 1h klines before the last one are all present with non-zero volume;
                otherwise the terminal price is untrustworthy and is never invented: the affected member-days
                count as missing coverage under the DATA_LIMITED law below
  APPLIES TO    engine runs (fixtures implement the haircut as a forced exit) and replay statistics identically
U8  (A2-3 check)        identical rule, top 8.
A3 ASSETS               BTC and ETH, fixed ex ante as the two assets with the longest USDT-M funding history.

LOCK MUST PRESERVE      per-selection-date candidate lists with ranking statistics, membership tables, delisting
                        dates, per-file sha256, and a coverage report (member-days with and without price data).
INSUFFICIENT DELISTED HISTORY ⇒ the affected family terminates DATA_LIMITED / INCONCLUSIVE (A2-5; for A1 the same
                        1.0% rule on U6 member-days). No t-stat or threshold change compensates.
```

Unverified fact, to be measured at acquisition: whether `data.binance.vision` retains kline history for all delisted USDT spot symbols. The coverage report answers it; the plan does not assume it.

---

## A3_VALID_WINDOW

```text
f0(asset)       = timestamp of the first archived funding record for the asset's USDT-M perpetual
READY(asset)    = f0 + 365 days + 7 days   (complete trailing-365-day window for the 7-day mean)
A3_START        = first 00:00 UTC month start ≥ max(READY(BTC), READY(ETH))
A3_END          = 2024-12-31 (secondary confirmation 2025-01-01 → 2026-08-31 as for all families)
FOLD LAW        = calendar-year folds from A3_START; a first partial segment shorter than 183 days merges into the
                  next calendar year
MINIMUM         = ≥ 3 complete folds, else A3 terminates DATA_LIMITED / INCONCLUSIVE
FROZEN          = the 365-day history length, the 7-day mean and this rule are fixed now; A3_START is computed once
                  from the lock and written into the A3 prereg before the prereg is hashed
```

Expectation, not verified: BTCUSDT perpetual funding begins in September 2019 and ETHUSDT in late 2019, which would give A3_START around December 2020 and 4 folds (2021 with the merged stub, 2022, 2023, 2024). The rule decides; if ETH's history starts later, A3 starts later.

---

## CALIBRATION_DAG

### Per-family calibration (identical structure for A1, A2, A3)
```text
CAL-Ax-STAT  (replay evaluator, 0 engine invocations)
   PARITY   replay reproduces the engine equity curves of the PC-Ax and N-Ax engine runs (C1 thresholds)
   SIZE     200 synthetic NO-EDGE worlds (frozen generator: GARCH(1,1) Student-t returns, cross-asset correlation and
            volume/funding dynamics fitted to nothing in AUTH-2 results; parameters frozen in the prereg) → run the
            family's full statistical gate stack (C2–C9 + family gates, Holm treated as m=3 with the other two p=1)
            → PASS iff accepted ≤ 10 of 200
   POWER    200 synthetic PLANTED-EDGE worlds at effect size δ_x [OD-1] → PASS iff accepted ≥ 160 of 200 (power ≥ 0.80)
   REPORT   exact Clopper–Pearson 95% intervals for size and power (diagnostic only; no additional gate)
PC-Ax        engine run of the family's actual fixtures (strategy, perturbations, matched benchmark, stresses,
             secondary segment) on ONE planted-edge synthetic world (fixed seed) → must SURVIVE every gate
N-Ax         engine run on REAL Dataset V3 data of the family null fixture (seed 0), with 5 further null seeds as its
             "perturbations" (A3: 3), through every gate → must be REJECTED
```

Planted edges and nulls:
| Family | Planted edge (PC) | Null (N and C4 distribution) | δ **[OD-1]** |
|---|---|---|---|
| A1 | daily drift proportional to the sign of the asset's own trailing 60-day return | random timing: each sleeve's primary position series circularly shifted by an independent uniform offset in [90 days, T − 90 days]; preserves exposure time, holding lengths and turnover, destroys timing | true ΔSR vs always-long VT = **0.40** |
| A2 | next-week drift increasing in the cross-sectional rank of trailing 28-day return | random selection: each week choose k coins uniformly from the eligible set; same exposure | true ΔSR vs matched benchmark = **0.40** |
| A3 | synthetic funding AR process; when z > 2, the next 30 days carry an elevated crash-jump probability | random overlay: the same number and durations of overlay episodes placed at random non-overlapping times | true paired ΔSR = **0.30** **plus** a planted max-drawdown and CVaR(5%) improvement, so PC-A3 and the POWER worlds must also pass hard gate A3-2 |

"True" δ is computed by the frozen generator on a 200-year simulation of the same design (not estimated from any market data) and is recorded in the prereg with the generator seed.

### Outcomes
```text
CAL-Ax-STAT FAIL (size)          ⇒ family Ax terminal LAW_INVALID (no market trial; its trial ID ABORTED NOT_RUN)
CAL-Ax-STAT FAIL (power) or PC-Ax not SURVIVED ⇒ family Ax terminal INCONCLUSIVE_UNDERPOWERED (no market trial)
N-Ax not REJECTED                ⇒ family Ax terminal LAW_INVALID (no market trial)
any C1 integrity failure         ⇒ INVALID_RUN; one technical retry allowed within caps, otherwise STOP_PROGRAM
```
Calibration failure of one family never stops the other families.

### Full DAG
```text
D0  DATA_LOCK (Dataset V3 + coverage report)
     ├─ coverage fails for A1 ⇒ A1 DATA_LIMITED   ├─ for A2 ⇒ A2 DATA_LIMITED   ├─ A3 window < 3 folds ⇒ A3 DATA_LIMITED
     ▼
for each family x ∈ {A1, A2, A3} independently:
     CAL-Ax-STAT ─PASS─► PC-Ax ─SURVIVED─► N-Ax ─REJECTED─► Ax (market data, primary + perturbations + family gates)
                                                              └─► PRE_HOLM_PASS | REJECTED | INCONCLUSIVE
     ▼ (all three families terminal or PRE_HOLM_PASS)
HOLM (m = 3 fixed; a family not tested contributes p = 1)
     ▼
SC-Ax for every family passing Holm ─► SURVIVED | REJECTED
     ▼
CLOSURE RECORD (including the DIAGNOSTIC-ONLY combination of ≥2 survivors, if any) ─► STOP

nodes = 1 + 3×4 + 1 + 3 + 1 = 18 · max depth 7 · edges conditioned only on terminal states
```

---

## MULTIPLE_TESTING_LAW

```text
PRIMARY HYPOTHESIS per family   H0: SR(primary) ≤ SR(matched benchmark) on the scored window
PRIMARY P-VALUE                 C3 studentized stationary bootstrap (paired), one-sided
HOLM                            m = 3 (A1, A2, A3), fixed in advance; untested families enter with p = 1;
                                FWER α = 0.05; step-down: p(1) ≤ 0.05/3, p(2) ≤ 0.05/2, p(3) ≤ 0.05
DSR                             on the primary's net daily-return Sharpe, N = cumulative family configuration N
                                (A1 = 21 with the H1 upstream 42-strategy debt disclosed verbatim; A2 = 6; A3 = 4);
                                skew and kurtosis from the scored window; PASS iff DSR ≥ 0.95
HANSEN SPA                      bashtage/arch, pinned version; benchmark model = matched benchmark; alternatives =
                                primary + perturbations; performance = daily returns ex-post levelled to 20% annualised
                                volatility (a monotone transform so the test compares Sharpe-type means; the levelling
                                is used only inside the test statistic); stationary bootstrap 10,000 resamples, block
                                length from §BOOTSTRAP_RULE computed on the primary-vs-benchmark paired series, fixed
                                seed; PASS iff consistent p ≤ 0.05
PERTURBATION NEGATIVES          Holm across the family's perturbation negative-direction tests, FWER 0.10 (C7)
NULL (C4)                       empirical p ≤ 0.05, per family, not Holm-adjusted (it is a separate conjunctive gate)
PBO                             CSCV, 16 blocks, reported; diagnostic only
LIFETIME DISCLOSURE             TLOS strategy configurations tested: 19 before AUTH-2 + 16 = 35, stated in every result
NEVER                           re-run a configuration to obtain a new p-value; change m, α, the block-length rule or N
                                after a result
```

---

## BOOTSTRAP_RULE [OD-3]

```text
INPUT        for each paired series required by the law (primary vs matched benchmark; each perturbation vs benchmark;
             overlay vs base): d_t = r_strategy,t − r_benchmark,t over the scored days (calendar days, 24/7)
ESTIMATES    b1 = arch.bootstrap.optimal_block_length(d)["stationary"]
             b2 = arch.bootstrap.optimal_block_length(d ** 2)["stationary"]     (d squared elementwise, not demeaned)
RULE         b = clamp(round_half_up(max(b1, b2)), 5, 60)     in days; round_half_up(x) = floor(x + 0.5)
USE          b is the expected block length of every paired StationaryBootstrap and of SPA for that comparison
SENSITIVITY  the same statistic at b = 5, 20 and 60 is always reported; it never changes a verdict
FROZEN       arch version hash-pinned; computed from the series alone before any p-value exists; the code path that
             computes b receives no p-value, statistic or gate outcome; a non-finite estimate ⇒ NOT_EVALUABLE
             (never a fallback length)
```

---

## REPLAY_EVALUATOR_CONTRACT [OD-6]

```text
PURPOSE      the smallest protected deterministic component needed for: null distributions · statistical calibration
             (size/power worlds) · leave-one-out checks · schedule perturbations (A2 weekday offsets) · PBO and other
             diagnostics · the DIAGNOSTIC-ONLY survivor combination
INPUTS       only: frozen position schedules (exported by the engine run, or generated by a frozen null/synthetic
             generator with a recorded seed) · Dataset V3 prices (sha256-checked) or frozen synthetic prices · the
             frozen cost model (fee, slippage, A2 surcharge, delisting convention)
OUTPUTS      daily return series and derived statistics, each written with the input hashes and code sha256
NEVER        replaces Freqtrade as the judged engine (every primary, perturbation, stress, benchmark and secondary
             number in a verdict comes from an engine run) · optimises or searches parameters · generates or edits a
             schedule except by a frozen generator listed in the prereg · opens a hypothesis · reads the ledger for
             anything but binding checks · writes the ledger
PARITY       before any replay-derived statistic is admissible for a family, the replay of that family's engine
             schedules must match the engine: daily-return correlation ≥ 0.999 AND total-return difference
             ≤ 0.25 pp, for every engine run in that family's PC and N nodes and for the primary run.
             Parity FAIL ⇒ every replay-derived statistic for that family is NOT_EVALUABLE ⇒ the family cannot SURVIVE.
             Tolerances are frozen now and may not be loosened after any market result.
DETERMINISM  pure functions; fixed seeds recorded; identical inputs ⇒ byte-identical outputs (tested)
STATUS       protected path (Owner merge); covered by the CEA-1 base-policy merge law
```

---

## CALIBRATION_POWER_PROOF

### The law (binding)
Power and size are proven only by each family's CAL-Ax-STAT node: 200 no-edge and 200 planted-edge synthetic worlds through the family's full gate stack (C2–C9, family gates, Holm with m = 3 and the other two families at p = 1). PASS iff size ≤ 10/200 and power ≥ 160/200 [OD-1]. Clopper–Pearson 95% intervals at those exact thresholds: 10/200 → [0.024, 0.090]; 160/200 → [0.738, 0.853]. A family that fails power terminates **INCONCLUSIVE_UNDERPOWERED before any real market-data trial**.

---

## COMPUTE_CAP_PROOF

### Measured basis [main, GitHub Actions API, this session]
| Run | Content | Duration |
|---|---|---|
| 37155789386 (Donchian) | 22 engine invocations, BTC+ETH 1h, timeranges 1–4 years (≈ 5 pair-years mean), plus lookahead/recursive gates | job 10 m 41 s; driver step 9 m 17 s ⇒ ≈ 25 s per invocation ⇒ ≈ 5 s per pair-year incl. container start |
| 37032878568 / 37038822799 (nulls) | 6 invocations each | 2 m 54 s / 2 m 48 s jobs |
| 34064374896 (Dataset V2 acquisition) | BTC+ETH 1h+5m archive | 1 m 37 s |
| Fixed per-job overhead | setup, pinned deps, image pull, data gates | ≈ 1.5 min |

### Estimate (base timeframe 4h; ×3 allowance for position adjustment and multi-pair overhead)
| Family | Pair-years per run (assumption) | Est. min per invocation |
|---|---|---|
| A1 | ≤ 15 symbols ever in U6 × 7 years ≈ 105 at 1h-equivalent ÷ 4 (4h) ≈ 26 | ≈ 6 |
| A2 | ≤ 60 symbols ever in U12 × ≈ 4 years ≈ 240 ÷ 4 ≈ 60 | ≈ 15 |
| A3 | 2 × 6 years ≈ 12 ÷ 4 = 3 (+ funding join) | ≈ 1.5 |

### Planned engine invocations (benchmark runs are executed once, in the N node, and reused by hash in the Ax node; identical configuration ≠ new configuration)
| Node | A1 | A2 | A3 | Total |
|---|---|---|---|---|
| PC-x (synthetic): primary base/×2/latency 3 + perturbations + benchmark base/×2/latency 3 + secondary 2 (+ A2 U8 pair 2) | 13 | 15 | 11 | 39 |
| N-x (real data): null base/×2/latency 3 + null seeds + benchmark 3 + secondary 2 (+ A2 U8 2) | 13 | 15 | 11 | 39 |
| Ax (real data): primary base/×2/×3/latency 4 + perturbations + A2 U8 primary 1 | 9 | 10 | 7 | 26 |
| SC-x (only if Holm passes): primary 1 (benchmark reused) | 1 | 1 | 1 | 3 |
| **Planned** | 36 | 41 | 30 | **107** |

Replay-evaluator work (nulls ×1,000, SIZE/POWER worlds ×200, leave-one-out, weekday offsets, PBO, SPA) uses **0** engine invocations.

**Invocation proof:** each job may be retried once after a technical abort, and only the failed invocations re-run. Worst case = 2 × 107 = **214 ≤ 240**. The driver refuses any invocation that would take the program ledger past 240.

### Job plan with hard timeouts (GitHub-hosted Linux, 2-core; every job ≤ the 360-minute GitHub job limit)
| Job | Est. min | timeout-minutes |
|---|---|---|
| D0 Dataset V3 acquisition + lock + coverage | 45 | 150 |
| CAL-A1/A2/A3-STAT (replay, 400 worlds each + parity) | 3 × 25 | 3 × 60 = 180 |
| PC-A1 (13 × 6 + gates) | 95 | 150 |
| PC-A2 (15 × 15 + gates), split in 2 jobs | 250 | 2 × 180 = 360 |
| PC-A3 | 25 | 60 |
| N-A1 | 95 | 150 |
| N-A2, split in 2 jobs | 250 | 2 × 180 = 360 |
| N-A3 | 25 | 60 |
| A1 | 65 | 120 |
| A2 | 160 | 240 |
| A3 | 15 | 45 |
| HOLM | 2 | 15 |
| SC-A1 + SC-A2 + SC-A3 | 25 | 30 + 45 + 15 = 90 |
| **Total** | **≈ 1,130** | **Σ timeouts = 1,980** |

**Minutes proof:** billed minutes for a job can never exceed its timeout (rounded up per job). With at most one retry per job, the worst case is 2 × 1,980 = **3,960 ≤ 4,000**. A program minutes ledger records each job's billed minutes from the Actions API after it ends; the driver refuses to dispatch a job unless *ledger total + 2 × that job's timeout* ≤ 4,000 (so a retry can never be the job that breaches the cap). The caps are never raised; scope growth is impossible because the DAG is fixed.

The decisions [OD-1…OD-10] change no invocation or timeout: the δ change, Holm on perturbations, the block-length rule, the delisting diagnostics and the report-only A1-3 are all computed in the replay evaluator or from existing engine outputs. A family that ends DATA_LIMITED or INCONCLUSIVE_UNDERPOWERED never runs its N, A or SC engine nodes, so real usage can only be lower than the table.

---

## MONTHLY_BILLING_PACING_RULE [OD-8]

```text
OVERAGE           PAID_ACTIONS_OVERAGE = USD 0 (the account's Actions budget/spending limit is an Owner setting)
RUNNERS           GitHub-hosted standard Linux only (1× minute multiplier); no larger runners, no macOS/Windows
SERIAL            at most one AUTH-2 job in flight at any time
MONTHLY RESERVE   at the first AUTH-2 dispatch of billing month m, read A_m = the account's remaining included
                  Linux minutes; R_m = max(500, ceil(0.20 × A_m)); R_m is fixed for that month
DISPATCH job j    only if ALL hold at dispatch time:
                    remaining_included_now − 2 × timeout_j ≥ R_m                  (CI / merge-law reserve untouched)
                    program_minutes_ledger + 2 × timeout_j ≤ 4,000               (program lifetime ceiling)
                    program_invocation_ledger + 2 × planned_invocations_j ≤ 240
                  otherwise PARK (blocker class EXTERNAL) until the next billing month, then re-read
FAIL-CLOSED       remaining allowance not readable, ledger not reconcilable with the Actions API, or the Owner's
                  USD 0 setting not confirmed ⇒ no dispatch
LEDGER            after each job, billed minutes (per job, rounded up) are appended to the program minutes ledger
MEANING           4,000 is a lifetime ceiling, never permission to exceed a month's included allowance
```

Worked example (assumed plan sizes; verify on the account): with 2,000 included minutes and nothing else used, R = 500 and AUTH-2 may use at most 1,500 that month. The largest single reservation is 2 × 240 = 480 minutes (job A2), so the expected ≈ 1,130 minutes could fit in one month, and the worst case of 3,960 would need at least three months.

---

## DAG_OPERATIONS

```text
NODES         17 executable nodes: D0 · CAL-A1..A3 · PC-A1..A3 · N-A1..A3 · A1..A3 · HOLM · SC-A1..A3, plus the
              non-executing CLOSURE RECORD terminal (the package's "18 nodes"). The program charter
              charters/programs/AUTH-2-DISCOVERY-QUALIFICATION-1.json lists each node with its preregistration sha256.
ONE NODE      research/auth2/run_node.py runs exactly one node (or one half of PC-A2 / N-A2) per GitHub Actions job,
              dispatched by hand through .github/workflows/auth2.yml; it refuses unless the charter, the node's
              preregistration (code and threshold hashes), the trial ledger (a PREREGISTERED record binding that
              preregistration's sha256) and the predecessors' result files allow it.
EDGES         D0 ─PASS─► CAL-Ax ─PASS─► PC-Ax ─SURVIVED─► N-Ax ─REJECTED─► Ax ─ANY TERMINAL─► HOLM ─HOLM_PASS(x)─► SC-Ax
              D0 decides DATA_LIMITED per family; a DATA_LIMITED family has no further node.
HOLM JOIN     HOLM runs once, after every family is terminal or PRE_HOLM_PASS. A family that never reached Ax, or ended
              Ax other than PRE_HOLM_PASS, enters with p = 1. HOLM_PASS(x) requires Ax = PRE_HOLM_PASS and x rejected
              by the m = 3 step-down at FWER 0.05.
SC            SC-Ax runs only for x with HOLM_PASS(x). It is part of family x's scientific trial and can only reject.
RETRY         a job that ends without a result (runner loss, timeout, INVALID_RUN from a technical cause) may be
              dispatched once more; a node that produced a result is never re-run (dispatch_guard NEVER_RERUN).
CLOSURE       when no node is eligible, the closure record (research/auth2/closure.py) is written from the result
              files: every node's terminal state, every family's terminal, the Holm table, PBO, the lifetime
              disclosure, compute used, and — only if ≥ 2 families SURVIVED — the DIAGNOSTIC-ONLY inverse-volatility
              combination from the replay evaluator (0 engine invocations; never evidence of allocation edge).
LEDGER        terminal records are appended (never edited) at closure, one per trial ID:
                scientific Ax   SURVIVED (SC-Ax SURVIVED) · REJECTED (Ax REJECTED, Holm not passed, or SC-Ax REJECTED)
                                · COMPLETED with outcome INCONCLUSIVE · FAILED (INVALID_RUN after the retry)
                                · ABORTED with outcome NOT_RUN (DATA_LIMITED, LAW_INVALID, INCONCLUSIVE_UNDERPOWERED)
                D0, CAL-Ax, PC-Ax, N-Ax, HOLM   COMPLETED with the node's terminal state as the outcome
                                (a calibration node never records SURVIVED or REJECTED: those states belong to
                                strategies) · FAILED on INVALID_RUN · ABORTED NOT_RUN if never reached
TERMINALS     every terminal above is accepted as it falls, including zero survivors. Nothing is re-run, re-scoped
              or re-thresholded because of a result.
```
