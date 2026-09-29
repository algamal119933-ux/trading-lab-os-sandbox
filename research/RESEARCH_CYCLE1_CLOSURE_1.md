# RESEARCH-CYCLE1-CLOSURE-1 — Cycle-1 Closure Record

**Authority:** `research/CLAUDE_ACCOUNT_HANDOFF_2026-09-29.md` (PR #38, merge
`effa2e7645833743e43006b999ce08749dd708f2`), carrying forward the Owner's
closure-unit instructions from `CLAUDE-ACCOUNT-HANDOFF-1` §§23-29, under
`research/OFFLINE_RESEARCH_AUTHORITY_1.md`.

**This is a closure/reporting unit, not a research unit.** No backtest, no
trial, no preregistration and no ledger append was made. Nothing here reruns,
repairs, re-tunes or re-interprets Mean-Reversion or H1; every figure below is
cited from an already-merged, chain-verified ledger record. The only
non-document action taken was evidence *preservation* (§G): two already-existing
GitHub artifacts of an aborted attempt were copied into the evidence store
before their retention expiry.

Closure performed 2026-09-29 against canonical `main` =
`effa2e7645833743e43006b999ce08749dd708f2`.

---

## A — CANONICAL STATE

```text
CANONICAL_MAIN_SHA                  = effa2e7645833743e43006b999ce08749dd708f2 (PR #38 merge)
HANDOFF_SHA_MATCH                   = YES (direct continuation: handoff doc merged at this SHA)
CONTROL_WORKTREE                    = clean at start
RUNTIME_PINNED_SHA                  = 3191285a28823907f62c6eb915327599cd6ed90b (unchanged, clean)
RESEARCH_WORKFLOWS_RUNNING          = 0 (all recent runs completed)
TRIAL_LEDGER                        = research/records/trial_ledger.jsonl
TRIAL_LEDGER_RECORDS                = 20 (seq 0..19)
TRIAL_LEDGER_TIP_DIGEST             = ef5f319fba1262c074d89d35a182e6be5d97540d5c571821474a7b2d98520be4
TRIAL_LEDGER_VERIFY                 = [] (TrialLedger.verify(): no errors)
DATASET                             = dataset_v2 (research/datasets/dataset_v2.lock.json), frozen
```

Cycle-1 merged units, in order:

| PR | Unit | Merge commit | Terminal |
|----|------|--------------|----------|
| #35 | RESEARCH-FOUNDATION-CLOSURE-1 (H1 controlled derivation, null calibration) | `30064e86a4ec05d27d5e5187596452499503b39e` | foundation CLOSED |
| #36 | MEAN-REVERSION-CYCLE1-DISCOVERY-1 | `fb2c8fb6738bd40296bf705a82373fd8e86d2514` | `REJECTED` |
| #37 | H1-PAPER-READINESS-QUALIFICATION-1 | `0862ea3c7dd26265ccab6c45c264fda2d23d1198` | `ADVANCE_TO_PAPER_ADMISSION_REVIEW` |
| #38 | CLAUDE-ACCOUNT-HANDOFF-1 (continuity doc, not research) | `effa2e7645833743e43006b999ce08749dd708f2` | — |

---

## B — H1 FINAL STATUS

```text
CANDIDATE                 = H1_EMACROSS (family BTSL_EMA_REGIME, lineage BTSL_EMA_REGIME/L1)
CODE_IDENTITY             = freqtrade/user_data/strategies/EmaCross.py
                            sha256 387cf39f58d266bb63d06865a0784bc2e08676edf54f4610c7d7709bb2a95f24
                            upstream wiktorj137/btc-strategy-lab@b68a5518 (GPL-3.0, not vendored)
CONFIG_HASH               = 9209a90e5092216af166fd10b9e7415690ab16af0fb3010c7e94e162c027e3ee
SCOPE                     = BTC/USDT, 1h, Binance spot, long-only, wallet 100, fee 0.1%/side
H1_AGGREGATE_REPRODUCTION = PASS (TRIAL-H1-CD1, seq 7; byte-identical to historical metrics)
H1_TRADE_LEVEL_REPRODUCTION = UNVERIFIED (TRIAL-H1-CD1 trade list produced but not captured)
H1_FULL_ARTIFACT_EQUIVALENCE = NOT_PROVEN
H1_HISTORICAL_QUALIFICATION = PASS (TRIAL-H1-QUAL-2, seq 19, SURVIVED)
H1_PAPER_READINESS_DECISION = ADVANCE_TO_PAPER_ADMISSION_REVIEW
H1_FROZEN                 = YES — no further H1 research in Cycle 1
H1_PAPER_ADMITTED         = NO
H1_PAPER_WORKER_STARTED   = NO
H1_PROSPECTIVE_EDGE_PROVEN = NO
```

Development-window centre result (TRIAL-H1-CD1, 2021-01-01 → 2024-12-31):
net +20.02%, 76 trades, win rate 25.0%, profit factor 2.17, max drawdown 5.18%,
average capital exposure 5.54%. Passive references in the same record:
BTC market change +225.58%; max-exposure-matched passive +44.42%;
realised-exposure-matched passive +12.31% (an approximation that ignores *when*
exposure occurred) → recorded excess +7.72 pp.

Qualification diagnostics (TRIAL-H1-QUAL-2, GitHub run 36563150060), as
recorded: temporal slices 2021 +8.25%, 2022 −5.30%, 2023 +9.80%, 2024 +7.12%
(`TEMPORAL_STABILITY = PASS`); 8/8 parameter neighbours positive, 16.52%–21.91%
(`PARAMETER_SENSITIVITY = STABLE`); adverse fee 0.2%/side +18.51% with engine
fee propagation proven from the run log (`COST_STRESS = PASS`);
`FRICTION_STRESS = NOT_SUPPORTED` (disclosed, non-material per preregistration).

Meaning of the decision, verbatim from the ledger: *"H1 survived the bounded
historical paper-readiness screens strongly enough to justify a separate Owner
decision on isolated forward-paper admission. Not prospective edge proof, not
paper admission, not production/live/real-money readiness."*

---

## C — MEAN-REVERSION FINAL STATUS

```text
CANDIDATE                 = MR_ZSCORE (family MEAN_REVERSION, lineage MEAN_REVERSION_ZSCORE)
CODE_IDENTITY             = research/mean_reversion/MeanReversionZScore.py
                            sha256 7bf98861338f4e4a79cd96113f8e73185247398c71af801d8756a9f2c65885fc
TRIAL                     = TRIAL-MR-ZSCORE-WF-1 (PREREGISTERED seq 14 → REJECTED seq 15)
GITHUB_RUN                = 36557441715
MEAN_REVERSION_DECISION   = REJECTED (terminal; not pending, not to be rerun or repaired)
MEAN_REVERSION_PAPER_ADMISSION_REVIEW_ELIGIBLE = NO
```

Preregistered falsification condition met exactly as frozen: the TRAIN-selected
configuration's EVAL return was negative in 2 of 2 anchored walk-forward folds
(Fold 1, EVAL 2023: −1.90%; Fold 2, EVAL 2024: −0.28%). All 4 grid
configurations (lookback 24/72 h × z-threshold 1.5/2.5) also lost on TRAIN in
both folds (−6.0% to −14.3%), with a smooth, directionally consistent gradient —
not a one-point artefact. Sample SUFFICIENT (EVAL 95 and 56 trades vs. a
preregistered minimum of 10). Lookahead / recursive / data-truth / walk-forward
all PASS. Cost-stress was **not meaningfully tested** (the adverse fee reached
only the reporting script, not the engine) — disclosed in the record, and
non-material because the base-cost falsification was already met and extra cost
can only worsen a negative result.

---

## D — CYCLE-1 TRIAL ACCOUNTING

All figures from `research/records/trial_ledger.jsonl`. Every one of the 10
trial IDs has exactly one `PREREGISTERED` record followed by exactly one
terminal record; there are no dangling preregistrations and no terminal record
without a prior preregistration.

**Lineages (3; 2 strategy lineages + 1 pipeline-control lineage):**

| Family / lineage | Trials | Terminal states |
|---|---|---|
| `BTSL_EMA_REGIME/L1` (H1) | TRIAL-H1-CD1, TRIAL-H1-QUAL-1, TRIAL-H1-QUAL-2 | COMPLETED, ABORTED, SURVIVED |
| `MEAN_REVERSION_ZSCORE` | TRIAL-MR-ZSCORE-WF-1 | REJECTED |
| `PIPELINE_NULL_CALIBRATION/L1` (control, not a strategy) | TRIAL-NULL-{MATCHFREQ,BLOCKSHUF}-{1,2,3} | ABORTED ×2, COMPLETED ×4 |

**By terminal state (10 trial attempts):** COMPLETED 5 · ABORTED 3 ·
REJECTED 1 · SURVIVED 1 · FAILED 0.

- ABORTED (3), all technical defects caught before any valid measurement
  existed, each superseded by a new trial ID with the original preserved:
  TRIAL-NULL-MATCHFREQ-1 / TRIAL-NULL-BLOCKSHUF-1 (recursive-analysis refused
  `startup_candle_count = 0`); TRIAL-H1-QUAL-1 (params-JSON space-nesting bug —
  9 runs produced byte-identical output not matching the centre).
- COMPLETED but `measurement_validity = FAIL` as a calibration (2):
  TRIAL-NULL-MATCHFREQ-2 / TRIAL-NULL-BLOCKSHUF-2 (1 trade vs. 76 designed —
  stuck-open position); superseded by attempt 3, which PASSED (76/76 scheduled
  exits). Ledger state is COMPLETED, so they are not counted as FAILED, but they
  are failed calibration attempts and are reported here as such.

**Scientific configurations (13 strategy parameter points + 2 null designs):**
H1 — 1 frozen centre + 8 sensitivity neighbours = 9 (neighbours are diagnostic
only; the centre was never reselected). Mean-Reversion — 2×2 grid = 4 (selection
on TRAIN only, per fold). Null controls — 2 schedule designs (not strategy
configurations).

**Engine backtest invocations: 41** — H1-CD1 1 · null attempts 6 · MR 12
(8 TRAIN + 2 EVAL + 2 stress) · H1-QUAL-1 9 (aborted) · H1-QUAL-2 13
(8 neighbours + 4 slices + 1 cost stress). Lookahead/recursive analyses are
not counted as backtests.

---

## E — SELECTION DEBT

- **H1 upstream debt — substantial and only partly quantified**
  (`candidate_registry.json → multiple_testing_accounting`): EmaCross was the
  winner of a 42-strategy upstream benchmark (33 lost money outright);
  `TOTAL_SELECTION_PROVENANCE = PARTIALLY_DOCUMENTED`. Hard rule stands: no
  DSR/PBO certification may be claimed from the local trial count.
- **H1 local debt in Cycle 1:** zero reselection — identity frozen, 8
  neighbours diagnostic-only. But the same Development window (2021–2024) has
  now been examined for H1 repeatedly (historical run, CD1, the qualification
  campaign), so it carries no independent confirmatory weight for H1.
- **Mean-Reversion:** 4 configurations examined, 1 selected per fold on TRAIN;
  lineage REJECTED. Any future mean-reversion lineage inherits this family-level
  history and must not treat itself as a first look.
- **Cycle level:** 2 strategy families tried, 1 survived the historical
  screens. H1's survival must be read against that count plus the upstream debt
  above, not in isolation.

---

## F — DATA / HOLDOUT TRUTH

- Dataset V2 frozen (`frozen_utc 2026-09-07T03:10:00Z`); `DATASET_LOCK_GATE =
  PASS` in every Cycle-1 lane; the raw byte-hash differs only by the known,
  expected serialization difference (canonical content matches the lock).
- **Every Cycle-1 trial used only the Development window** (2021-01-01 →
  2024-12-31; ledger timeranges `20210101-20250101` / `20210101-20241231` and MR
  folds inside it), plus the December-2020 unscored warm-up overlay.
- **Validation** (2025-01-01 → 2026-08-31) is `SPENT` — opened once by
  BASELINE-1 on 2026-09-07. Cycle 1 did not touch it; it is not a holdout.
- **Locked OOS:** `designated = false` — no period of Dataset V2 qualifies as
  pristine (Dataset V1 work already inspected 2025-09 → 2026-09).
- `PRISTINE_HISTORICAL_HOLDOUT_PROVEN = NO`. The first strict holdout for any
  candidate is prospective forward paper over data that did not exist at its
  freeze time.
- Universe limits: BTC/USDT only, 1h, spot, long-only; fees modelled as a flat
  0.1%/side (0.2% stress); no slippage/friction model (`NOT_SUPPORTED`).

---

## G — EVIDENCE STATUS

- **Selection ledger:** committed in git, 20 records, hash chain verified
  (`TrialLedger.verify() == []`), tip `ef5f319f…98520be4`.
- **Evidence store (host-local):** `~/Documents/TLOS-Evidence/trading-research/`
  — 283 files, ~28 MB, indexed this unit by
  `CYCLE1_CLOSURE_SHA256SUMS.txt`
  (sha256 `7bc201d3e05ed84ee24f2cd20fefa0d63e58a225c39bbd1132f8691fdbff0bf9`).
- **Preserved this unit:** the two aborted null attempt-1 runs had no durable
  copy; their GitHub artifacts (runs 36533311358, 36533315256; expiry
  2026-10-29) were downloaded unchanged into
  `NULL-matched-frequency-ABORTED-ATTEMPT-1/` and
  `NULL-block-shuffled-ABORTED-ATTEMPT-1/`; each contains the
  `startup candle count of 0` refusal that the ledger records.
- **Directory-naming note (recorded, not renamed):** `NULL-matched-frequency-1/`
  and `NULL-block-shuffled-1/` hold the evidence of **TRIAL-NULL-*-2** (their
  metrics show trade_count = 1), not attempt 1. Evidence is not renamed after
  the fact; this mapping is the correction.
- **Known gaps:** TRIAL-H1-CD1's trade list was not captured (trade-level
  reproduction UNVERIFIED); MR cost-stress not meaningfully tested; H1 friction
  stress not supported.
- **Durability tier:** single host-local copy plus git for the ledger. No
  independent-host copy is proven; GitHub artifacts carry 30-day retention.

---

## H — PAPER-ADMISSION ELIGIBILITY

| Candidate | Terminal decision | `PAPER_ADMISSION_REVIEW_ELIGIBLE` | Admitted |
|---|---|---|---|
| H1_EMACROSS | ADVANCE_TO_PAPER_ADMISSION_REVIEW | **YES** | NO |
| MR_ZSCORE | REJECTED | **NO** | NO |
| Null controls | pipeline calibration (not candidates) | N/A | N/A |

Eligibility is **not** admission. A paper-admission review requires its own
explicit Owner authorization (`OFFLINE_RESEARCH_AUTHORITY_1.md`: no automatic
candidate promotion or paper admission). No paper worker was launched.

---

## I — P2 FIREWALL

```text
FP_CONTROL_3                      = CANONICAL ACTIVE P2 CONTROL
FP_CONTROL_3_CONTAINERS           = 6 running, all StartedAt 2026-09-28T15:28:15Z, RestartCount 0
RUNTIME_WORKTREE                  = pinned 3191285a28823907f62c6eb915327599cd6ed90b, porcelain status empty
FP_CONTROL_3_TOUCHED              = NO
P2_RUNTIME_MUTATED                = NO
P2_DB_OR_EVIDENCE_LANE_WRITTEN    = NO
THIS_BRANCH_TOUCHES               = research/RESEARCH_CYCLE1_CLOSURE_1.md, tests/test_p2_scope_audit.py, MANIFEST.txt
P3_STARTED                        = NO
REAL_MONEY_AUTHORIZED             = NO
```

---

## J — REMAINING LIMITATIONS

1. **No prospective evidence.** Every Cycle-1 number is historical and
   in-sample to a heavily inspected Development window.
2. **H1's excess over passive is thin and approximation-dependent.** In a
   strongly bullish window (+225.6% BTC), H1 returned +20.02% at ~5.5% average
   exposure. It beats the *realised*-exposure-matched passive (+12.31%) only
   under an approximation that ignores exposure timing, and it trails the
   *max*-exposure-matched passive (+44.42%). Reduced exposure is not alpha
   without exposure-adjusted analysis (CLAUDE.md).
3. **Upstream selection debt** for H1 is substantial and only partly
   quantified; no DSR/PBO certification is possible.
4. **Single pair, single timeframe, long-only, spot**; no slippage/friction
   model; 76 trades over four years is a modest sample.
5. **Trade-level reproduction** of the H1 centre remains UNVERIFIED.
6. **No pristine historical holdout** exists or can be constructed from
   Dataset V2.
7. **Evidence durability** is single-host; no independent-host copy.

---

## K — OWNER DECISION REQUIRED

**YES.** Cycle 1 is closed. No further research unit starts automatically. The
Owner decides what, if anything, follows — in particular whether to authorize a
separate, isolated **H1 paper-admission review** (review only; not admission,
not a paper worker, not P3, not real money). Not opened by this unit: Funding,
Cross-Sectional, another Mean-Reversion lineage, Paper Admission, P3.

---

## L — ONE NEXT ACTION

Owner merges this PR, then decides whether to authorize an H1
paper-admission **review** unit.

---

## RESEARCH_CYCLE1_COMPLETE law — checklist

| # | Condition | Status |
|---|---|---|
| 1 | Mean-Reversion has a terminal decision | YES — REJECTED (seq 15) |
| 2 | Trial ledger complete and chain-valid | YES — 10/10 trials terminal; verify() = [] |
| 3 | Evidence artifacts durable | YES at the canonical host-local tier; indexed; aborted-attempt gap closed this unit (limitation J7) |
| 4 | H1 remains frozen | YES — no H1 trial after seq 19 |
| 5 | No second new family opened | YES |
| 6 | P2 firewall intact | YES (§I) |
| 7 | Paper-admission eligibility recorded | YES (§H) |
| 8 | No paper worker launched | YES |
| 9 | P3 unstarted | YES |
| 10 | Real money unauthorized | YES |

## Cycle-1 final status block

```text
RESEARCH_CYCLE1_CLOSURE_1                          = PASS
RESEARCH_CYCLE1_COMPLETE                           = YES
H1_HISTORICAL_QUALIFICATION                        = PASS
H1_PAPER_ADMISSION_REVIEW_ELIGIBLE                 = YES
H1_PAPER_ADMITTED                                  = NO
MEAN_REVERSION_DECISION                            = REJECTED
MEAN_REVERSION_PAPER_ADMISSION_REVIEW_ELIGIBLE     = NO
TOTAL_CYCLE1_LINEAGES                              = 3 (2 strategy: H1, MR; 1 null-calibration control)
TOTAL_SCIENTIFIC_CONFIGURATIONS                    = 13 strategy parameter points (H1 9, MR 4) + 2 null-control designs
TOTAL_EXECUTION_ATTEMPTS                           = 10 trial attempts (41 engine backtest invocations)
TOTAL_ABORTED_ATTEMPTS                             = 3
TOTAL_FAILED_ATTEMPTS                              = 0 ledger-FAILED (+2 COMPLETED with measurement_validity=FAIL: null attempt 2)
SELECTION_LEDGER_CHAIN                             = PASS
PRISTINE_HISTORICAL_HOLDOUT_PROVEN                 = NO
PROSPECTIVE_EDGE_PROVEN                            = NO
PAPER_WORKERS_STARTED                              = 0
FP_CONTROL_3_TOUCHED                               = NO
P2_RUNTIME_MUTATED                                 = NO
FUNDING_STARTED                                    = NO
CROSS_SECTIONAL_STARTED                            = NO
P3_STARTED                                         = NO
REAL_MONEY_AUTHORIZED                              = NO
OWNER_DECISION_REQUIRED                            = YES
ONE_NEXT_ACTION                                    = Owner merges this PR, then decides whether to authorize an H1 paper-admission review unit
```

**STOP.** No unit follows automatically.
