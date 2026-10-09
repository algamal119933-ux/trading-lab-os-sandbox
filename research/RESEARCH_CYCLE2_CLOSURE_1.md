# RESEARCH-CYCLE2-CLOSURE-1 — Cycle-2 Closure Record

**Authority:** `research/OFFLINE_RESEARCH_CYCLE_2_OPENING_1.md` §7.5 ("Cycle-2 closure
record, then STOP") and §9 (format), Owner record merged as PR #42
(`4bbb1df6e866d657b9e486ca683c30fef4133035`), under
`research/OFFLINE_RESEARCH_AUTHORITY_1.md` (unchanged). The trigger is
`research/trend_breakout/PREREGISTRATION.md` "Outcomes", the REJECTED row, verbatim:

```text
REJECTED      any gate FAIL. Terminal; the lineage is not modified, re-tuned or rerun. With
              MR not approved (OPENING-1 §2.2), Cycle 2 proceeds to its closure record (7.5).
```

**This is a closure/reporting unit, not a research unit.** No backtest, no
trial, no preregistration, no workflow dispatch and no ledger append was made.
Nothing here reruns, repairs, re-tunes, re-interprets or re-judges any Cycle-2
trial; every figure below is cited from an already-merged record or recomputed
read-only from the chain-verified ledger. The only non-document action taken was
evidence *preservation* (§G): the three Cycle-2 GitHub run artifacts were copied
unchanged into the evidence store before their retention expiry.

Closure performed 2026-10-09 against canonical `main` =
`21cf0a6cc260ecf8644f4f6bcc0ca22f7a82c62d` (PR #49 merge).

---

## A — CANONICAL STATE

```text
CANONICAL_MAIN_SHA                  = 21cf0a6cc260ecf8644f4f6bcc0ca22f7a82c62d (PR #49 merge)
CONTROL_WORKTREE                    = clean at start
RUNTIME_PINNED_SHA                  = 3191285a28823907f62c6eb915327599cd6ed90b (observed; porcelain empty)
RESEARCH_WORKFLOWS_RUNNING          = 0 (cycle2_research.yml: exactly 3 runs, all completed/success; no run in progress)
OPEN_PULL_REQUESTS_AT_START         = 0
TRIAL_LEDGER                        = research/records/trial_ledger.jsonl
TRIAL_LEDGER_RECORDS                = 26 (seq 0..25)
TRIAL_LEDGER_TIP_DIGEST             = b258ec2b05d422b849484acd490371befa07fe828ddaa58fa3d7acbe0aeaa071
TRIAL_LEDGER_VERIFY                 = [] (TrialLedger.verify(): no errors)
DATASET                             = dataset_v2 (research/datasets/dataset_v2.lock.json), frozen 2026-09-07T03:10:00Z
FUNNEL_LAW                          = research/cycle2/FUNNEL_LAW_1.md
                                      sha256 5ad00f5ad79a192aac9454e5eb8a90f3ce787fc332e3467fdd9ecf969800468a
```

Cycle-2 merged units, in order (merge commits verified with `git log --first-parent`
and `gh pr view`; no difference found):

| PR | Unit | Merge commit | Terminal / effect |
|----|------|--------------|-------------------|
| #42 | OFFLINE-RESEARCH-CYCLE-2-OPENING-1 (governance-only) | `4bbb1df6e866d657b9e486ca683c30fef4133035` | Cycle 2 opened |
| #43 | UNIT 7.1 — trialgate audit + minimum tooling | `6ba84c3c49470f7c5e97a9920b3e592c7bbcfb14` | tooling; 0 trial IDs |
| #44 | UNIT 7.1a — CI trialgate enablement | `9bae31961437356f963ac723f299446db2b5e267` | tooling; 0 trial IDs |
| #45 | UNIT 7.2 PART A — null-recalibration preparation | `31c26b6be55ad009bc0c81fec607f3ff20a34273` | seq 20, 21 PREREGISTERED |
| #46 | UNIT 7.2 B1 — TRIAL-C2-NULL-MATCHFREQ-1 record | `8654156db8bcbc8c38c1606b31d0121ac1035c1e` | seq 22 `REJECTED` |
| #47 | UNIT 7.2 B2 — TRIAL-C2-NULL-BLOCKSHUF-1 record + 7.2 result | `45c1e5837159d5bfe04ed1a46031def80a7b3fcc` | seq 23 `REJECTED`; 7.2 PASS |
| #48 | UNIT 7.3 PART A — Trend/Breakout preregistration | `efe6e77187992fb06f9ddadd470b20d04e583eca` | seq 24 PREREGISTERED |
| #49 | UNIT 7.3 RECORD — TRIAL-C2-TREND-DONCHIAN-1 record | `21cf0a6cc260ecf8644f4f6bcc0ca22f7a82c62d` | seq 25 `REJECTED` |

---

## B — TREND FINAL STATUS

```text
CANDIDATE                 = TREND_DONCHIAN_BREAKOUT (family BTSL_EMA_REGIME, lineage BTSL_EMA_REGIME/L2)
CODE_IDENTITY             = research/trend_breakout/DonchianBreakoutV1.py
                            sha256 375dd3dbf65f472fd640bae970abf492fdc7808d757bb2ea1c114bf8ac0bf1cc
PREREGISTRATION           = research/cycle2/prereg/TRIAL-C2-TREND-DONCHIAN-1.json
                            sha256 98f5b6c9d9b39c0779adf23bd497760fdfaa316a332fd10b0046b0ed98a07d80
TRIAL                     = TRIAL-C2-TREND-DONCHIAN-1 (PREREGISTERED seq 24 → REJECTED seq 25)
GITHUB_RUN                = 37155789386
TREND_DONCHIAN_DECISION   = REJECTED (terminal; the lineage is not modified, re-tuned or rerun)
REJECTED_BY               = COST_STRESS, MULTIPLE_TESTING, PARAMETER_ROBUSTNESS, WALK_FORWARD
INTEGRITY_GATES           = DATA_TRUTH, LOOKAHEAD, RECURSIVE, LEDGER_CHAIN = PASS
SAMPLE_EVIDENCE           = SUFFICIENT (EVAL 19 and 22 trades)
TREND_PAPER_ADMISSION_REVIEW_ELIGIBLE = NO
```

All figures cited from `research/cycle2/records/TRIAL-C2-TREND-DONCHIAN-1_RESULT.md`:

- **Walk-forward (L1/L2, base fee 0.1%/side).** TRAIN-selected E336_X168 in both
  folds. Excess over the exposure-matched passive: fold 1 (2023) −16.61 pp
  (+7.99% vs +24.60%), fold 2 (2024) −7.93 pp (+8.57% vs +16.50%); Σ −24.54 →
  `WALK_FORWARD = FAIL`.
- **Cost stress (L3).** Σ excess −25.20 at 0.2%/side → `COST_STRESS = FAIL`.
- **Parameter robustness (L4).** 0 of 6 grid configurations positive against the
  exposure-matched passive (+57.59%) over the 2021–2024 robustness window
  (minimum 4) → `PARAMETER_ROBUSTNESS = FAIL`.
- **Multiple testing.** DSR 0.9552 PASS (threshold 0.95, N = 15); PBO 0.6143 FAIL
  (threshold 0.05) → `MULTIPLE_TESTING = FAIL`. The DSR figure is not a
  certification (it cannot observe the H1 upstream debt; §E).
- **Engine fee propagation** PROVEN 22/22. Regime/session diagnostic **NOT PRODUCED**
  (no preregistered spec; diagnostic only, never gating), as recorded in the RESULT.

Terminal; the lineage is not modified, re-tuned or rerun.

---

## C — MEAN-REVERSION

```text
MEAN_REVERSION_LINEAGE_OPENED = NO
MR_BUDGET                     = 0 (OPENING-1 §2.2: "Budget is 0 until the Owner explicitly approves a named mechanism")
UNIT_7_4                      = DID NOT RUN (OPENING-1 §7.4 condition not met)
MR_BUDGET_RESERVED            = NO ("No budget is reserved merely to keep the MR slot available")
```

Evidence, from authority on `main` and not from memory:

- (a) No ledger record after seq 15 has `family_id = MEAN_REVERSION` or a lineage
  under it; the Cycle-2 records seq 20..25 are `PIPELINE_NULL_CALIBRATION/L2`
  (seq 20–23) and `BTSL_EMA_REGIME/L2` (seq 24–25) only.
- (b) `research/cycle2/prereg/` holds exactly three preregistrations, none MR:
  TRIAL-C2-NULL-MATCHFREQ-1, TRIAL-C2-NULL-BLOCKSHUF-1, TRIAL-C2-TREND-DONCHIAN-1.
- (c) A grep of the merged tree (`research/`, `docs/`) finds no Owner approval of an
  OPENING-1 §2.2 MR mechanism. The only Cycle-2 MR references are the conditional
  rule itself (OPENING-1 §2.2, §3, §7.4), the schema field that would carry such an
  approval (`research/cycle2/prereg.schema.json`), and the REJECTED row quoted above.
- (d) The Trend lineage reached its terminal at seq 25 (2026-10-03T22:54:02Z) with
  MR unapproved. By OPENING-1 §2.2, "Cycle 2 may close without opening MR".

The MR family history from Cycle 1 is unchanged: MR_ZSCORE / `MEAN_REVERSION_ZSCORE`
`REJECTED` at seq 15 (`research/RESEARCH_CYCLE1_CLOSURE_1.md` §C). Any future MR
lineage inherits that history and is never a first look.

## C2 — NULL RECALIBRATION

```text
NULL_RECALIBRATION (7.2)     = PASS
TRIAL-C2-NULL-MATCHFREQ-1    = REJECTED (seq 22, run 37032878568), rejected_by COST_STRESS, WALK_FORWARD
TRIAL-C2-NULL-BLOCKSHUF-1    = REJECTED (seq 23, run 37038822799), rejected_by COST_STRESS, WALK_FORWARD
INTEGRITY_GATES              = PASS on both (DATA_TRUTH, LOOKAHEAD, RECURSIVE, LEDGER_CHAIN)
ENGINE_FEE_PROPAGATION       = PROVEN 6/6 on each
CYCLE2_STOP                  = false on both
```

Cited from `research/cycle2/records/UNIT_7_2_NULL_RECALIBRATION_RESULT.md`: both
no-edge controls were REJECTED by the frozen funnel law in the 2023/2024 EVAL windows
with every integrity gate PASS, so each calibration verdict is PASS. Σ excess:
MATCHFREQ-1 −46.56 (stress −47.08) · BLOCKSHUF-1 −48.41 (stress −48.95).

PBO and DSR were **NOT_EVALUABLE** for both single-configuration nulls. The nulls do
**not** validate PBO or DSR; they calibrate L1–L3 only.

**Pre-freeze law revision disclosed (PR #45, UNIT 7.2 PART A).** Before any Cycle-2
run existed, the funnel law was revised once: L1/L2 were made benchmark-relative
(excess over the exposure-matched passive instead of absolute EVAL return), and the
integrity rule was added (a null with any integrity gate ≠ PASS is INVALID_RUN →
NOT_PROVEN → STOP). No threshold value changed. The superseded, never-merged ledger
records seq 20/21 are preserved in that branch's history at `2662dc9`; they were
never on `main` and never bound by any run. Disclosed in `FUNNEL_LAW_1.md`
"Pre-freeze revision".

---

## D — CYCLE-2 TRIAL ACCOUNTING

All figures from `research/records/trial_ledger.jsonl` (read-only), reconciled
against the three `*_funnel_result.json` budget blocks. Every Cycle-2 trial ID has
exactly one `PREREGISTERED` record followed by exactly one terminal record; there are
no dangling preregistrations and no terminal record without a prior preregistration.
Unit 7.1 / 7.1a consumed 0 trial IDs (no ledger record between seq 19, the last
Cycle-1 record, and seq 20).

**Ledger records:** 26 in total; Cycle 2 = 6 (seq 20..25); Cycle-2 trial IDs = 3.

| seq | Trial ID | State | Lineage | Recorded (UTC) |
|---|---|---|---|---|
| 20 | TRIAL-C2-NULL-MATCHFREQ-1 | PREREGISTERED | PIPELINE_NULL_CALIBRATION/L2 | 2026-10-02T12:59:32.625Z |
| 21 | TRIAL-C2-NULL-BLOCKSHUF-1 | PREREGISTERED | PIPELINE_NULL_CALIBRATION/L2 | 2026-10-02T12:59:32.637Z |
| 22 | TRIAL-C2-NULL-MATCHFREQ-1 | REJECTED | PIPELINE_NULL_CALIBRATION/L2 | 2026-10-02T16:31:24.931Z |
| 23 | TRIAL-C2-NULL-BLOCKSHUF-1 | REJECTED | PIPELINE_NULL_CALIBRATION/L2 | 2026-10-03T16:57:09.530Z |
| 24 | TRIAL-C2-TREND-DONCHIAN-1 | PREREGISTERED | BTSL_EMA_REGIME/L2 | 2026-10-03T19:23:51.722Z |
| 25 | TRIAL-C2-TREND-DONCHIAN-1 | REJECTED | BTSL_EMA_REGIME/L2 | 2026-10-03T22:54:02.435Z |

**Lineages (2; 1 strategy lineage + 1 pipeline-control lineage):**

| Family / lineage | Trials | Terminal states |
|---|---|---|
| `BTSL_EMA_REGIME/L2` (Trend / Donchian) | TRIAL-C2-TREND-DONCHIAN-1 | REJECTED |
| `PIPELINE_NULL_CALIBRATION/L2` (control, not a strategy) | TRIAL-C2-NULL-MATCHFREQ-1, TRIAL-C2-NULL-BLOCKSHUF-1 | REJECTED ×2 |

**By terminal state (3 trial IDs):** REJECTED 3 · SURVIVED 0 · COMPLETED 0 ·
ABORTED 0 · FAILED 0.

**Gates per run:** integrity gates (DATA_TRUTH, LOOKAHEAD, RECURSIVE, LEDGER_CHAIN)
PASS on all 3 runs; `cycle2_stop = false` on all 3.

**Budget (OPENING-1 §3 hard caps):**

| Budget | Used | Cap | Remaining | Detail |
|---|---|---|---|---|
| scientific trial IDs | 1 | 12 | 11 | TRIAL-C2-TREND-DONCHIAN-1 |
| calibration/tooling trial IDs | 2 | 6 | 4 | TRIAL-C2-NULL-MATCHFREQ-1, TRIAL-C2-NULL-BLOCKSHUF-1 |
| scientific configurations | 6 | 24 | 18 | Trend 6/12 · MR 0/8 · regime/session-gated 0/4 |
| engine backtest invocations | 34 | 120 | 86 | 6 + 6 + 22; engine_fee_propagation PROVEN 34/34 |
| Hyperopt / open sweeps | 0 | 0 | — | none |

**No cap was exhausted.** Unexhausted: scientific trial IDs (11 left), calibration
trial IDs (4), scientific configurations (18; Trend 6, MR 8, regime/session-gated 4),
engine invocations (86). Cycle 2 closes by the OPENING-1 §2.2/§7 order of work
(Trend terminal at seq 25; MR unapproved; §7.4 did not run), **not** by cap
exhaustion. The unused budget is not carried forward; it lapses with this closure.

---

## E — SELECTION DEBT

- **Trend-family cumulative N = 15** (`BTSL_EMA_REGIME`, N LAW in
  `research/cycle2/config_n.py`): Cycle-1 H1's 9 configurations (1 frozen centre +
  8 sensitivity neighbours) + Donchian's 6. The trial-ID count is not N.
- **H1 upstream debt** (42-strategy benchmark winner, 21-point public sweep,
  undocumented midpoint choice; `research/external/candidate_registry.json →
  multiple_testing_accounting`) is disclosed, **not** folded into N, and still not
  certifiable. No DSR/PBO certification may be claimed from N = 15.
- **Development window 2021–2024** has now been examined by Cycle 1 (H1, MR, nulls)
  and Cycle 2 (nulls, Donchian). It carries no independent confirmatory weight for
  any future candidate.
- **EVAL years 2023/2024** are publicly known rising years for BTC and ETH; this was
  disclosed in the Trend preregistration before results
  (`research/trend_breakout/PREREGISTRATION.md`).
- **Inheritance:** any future trend or MR lineage inherits these counts (trend N = 15
  plus the H1 upstream debt; MR family: MR_ZSCORE REJECTED, 4 configurations) and is
  never a first look.

---

## F — DATA / HOLDOUT TRUTH

- Dataset V2 lock unchanged (`frozen_utc 2026-09-07T03:10:00Z`); `DATA_TRUTH = PASS`
  (DATASET_LOCK_GATE and WARMUP_OVERLAY_JOIN) in all three Cycle-2 runs.
- **Every Cycle-2 trial used only the Development window.** All three preregistrations'
  folds lie in 20210101–20241231 (TRAIN 20210101–20221231 / 20210101–20231231; EVAL
  20230101–20231231 / 20240101–20241231; Trend robustness window 20210101–20241231).
  The run artifacts' 34 engine timeranges are exactly these windows (8 + 8 + 6 + 6 + 6);
  no 2025+ timerange appears. The only earlier data is the December-2020 unscored
  warm-up overlay.
- **Validation** (2025-01-01 → 2026-08-31) was **not touched by Cycle 2**. It remains
  `SHARED_NON_PRISTINE` and `SPENT` (opened once by BASELINE-1, 2026-09-07). No Cycle-2
  candidate reached FREEZE, so no Validation run was due.
- **Locked OOS:** `designated = false`. `PRISTINE_HISTORICAL_HOLDOUT_PROVEN = NO`.
- **Option B (OPENING-1 §5) unchanged:** the first strict holdout for any future
  survivor is prospective, isolated forward paper over data that did not exist at
  candidate freeze.
- Universe limits: BTC/USDT only in every Cycle-2 run, 1h, Binance spot, long-only;
  fees a flat 0.1%/side (0.2% stress) as a symmetric fee proxy; slippage, latency
  and partial fills `NOT_SUPPORTED`.

---

## G — EVIDENCE STATUS

- **Selection ledger:** committed in git, 26 records, hash chain verified
  (`TrialLedger.verify() == []`), tip `b258ec2b…a071`.
- **Durable records in git:** `research/cycle2/records/` — 3 `*_RESULT.md`, 3
  `*_funnel_result.json` and `UNIT_7_2_NULL_RECALIBRATION_RESULT.md`.
- **Preserved this unit:** the three GitHub artifacts were downloaded unchanged, once,
  into `~/Documents/TLOS-Evidence/trading-research/CYCLE2/`:

| Directory | Run | Files | Artifact expiry (UTC) |
|---|---|---|---|
| `37032878568-cycle2-NullControlMatchedFrequency/` | 37032878568 | 50 | 2026-11-01T16:20:01Z |
| `37038822799-cycle2-NullControlBlockShuffled/` | 37038822799 | 50 | 2026-11-01T17:12:29Z |
| `37155789386-cycle2-DonchianBreakoutV1/` | 37155789386 | 132 | 2026-11-02T21:48:48Z |

- Each preserved `funnel_result.json` is byte-identical (sha256) to its git copy:
  MATCHFREQ `860cc994…5e29`, BLOCKSHUF `cb2f6028…2ed7`, TREND `a15fbfdc…1ce5` (3/3 match).
- **Index:** `~/Documents/TLOS-Evidence/trading-research/CYCLE2_CLOSURE_SHA256SUMS.txt`
  — 232 files (~21 MB), sorted paths, sha256
  `40ee0d4430a8917887f4ad1b8e126bb3b24f2cbc9056e831c8d18a6c2b5241c0`;
  `sha256sum -c` passes. No existing evidence was deleted or renamed.
- **Known gaps:** the Trend regime/session diagnostic was not produced (§B); its input
  EVAL trade lists are preserved.
- **Durability tier:** git + a single host-local copy. No independent-host copy is
  proven; the GitHub artifacts expire on the dates above.

---

## H — PAPER-ADMISSION ELIGIBILITY

| Candidate | Terminal decision | `PAPER_ADMISSION_REVIEW_ELIGIBLE` | Admitted |
|---|---|---|---|
| TREND_DONCHIAN_BREAKOUT | REJECTED | **NO** | NO |
| Null controls (Cycle 2) | pipeline calibration (not candidates) | N/A | N/A |

**Cycle 2 produced no survivor** and therefore no `PAPER_ADMISSION_REVIEW_ELIGIBLE`
candidate.

**H1 status is unchanged by Cycle 2.** Cited from
`research/paper/h1/H1_PAPER_ADMISSION_AND_LAUNCH_PACKAGE_1.md`:
`SCIENTIFIC_PAPER_ADMISSION = ADMIT`, `PAPER_LAUNCH_READY = NO`,
`RECOMMENDED_PAPER_LOCATION = WAIT_FOR_P2_CLOSURE`. No H1 trial, package change or
paper action occurred in Cycle 2. No paper worker was started.

---

## I — P2 FIREWALL

```text
FP_CONTROL_3                      = CANONICAL ACTIVE P2 CONTROL
FP_CONTROL_3_CONTAINERS           = 6 running (freqtrade, mlflow, exporter, capture, prometheus, grafana),
                                    StartedAt 2026-10-08T11:01:28Z–11:01:29Z, RestartCount 0;
                                    observed only, identical before and after this unit
RUNTIME_WORKTREE                  = pinned 3191285a28823907f62c6eb915327599cd6ed90b, porcelain status empty,
                                    before and after
FP_CONTROL_3_TOUCHED              = NO
P2_RUNTIME_MUTATED                = NO
P2_DB_OR_EVIDENCE_LANE_WRITTEN    = NO
THIS_BRANCH_TOUCHES               = research/RESEARCH_CYCLE2_CLOSURE_1.md, tests/test_p2_scope_audit.py, MANIFEST.txt
P3_STARTED                        = NO
REAL_MONEY_AUTHORIZED             = NO
```

The container start time differs from the Cycle-1 record (2026-09-28T15:28:15Z). The
containers were started on 2026-10-08, before this unit. This unit did not start,
stop or restart anything and only records what it observed.

---

## J — REMAINING LIMITATIONS

1. **No prospective evidence.** Every Cycle-2 number is historical and in a heavily
   inspected Development window.
2. **One scientific lineage only.** Cycle 2 tested one Trend lineage (6
   configurations); MR was never opened. The REJECTED verdict covers that lineage, not
   trend-following in general.
3. **The L4 robustness window overlaps the EVAL years.** L4 is a parameter-plateau
   check, not out-of-sample evidence.
4. **Benchmark whole-window exposure bias** (disclosed in `FUNNEL_LAW_1.md`): the
   max-exposure-matched passive is held for the whole window, so a strategy with lower
   time-in-market is disadvantaged in rising windows, and both EVAL years rose.
   Disclosed, not corrected.
5. **Friction:** slippage, latency and partial fills `NOT_SUPPORTED`; fees are a
   symmetric proxy.
6. **Single pair BTC/USDT, 1h, long-only, spot.**
7. **Evidence durability** is single-host; no independent-host copy.
8. **No pristine historical holdout** exists or can be constructed from Dataset V2.

---

## K — OWNER DECISION REQUIRED

**YES.** Cycle 2 is **CLOSED**. No research unit starts automatically. Any further
research needs a **new** Owner research authority: a new program with its own
frozen content, budget and order of work. The unused Cycle-2 budget is not
carried forward. Not opened by this unit: Mean-Reversion, Funding, Cross-Sectional,
ML/RL, a Validation run, paper admission, P3.

---

## L — ONE NEXT ACTION

Owner merges this PR (manual merge). Cycle 2 then STOPs.

---

## RESEARCH_CYCLE2_COMPLETE law — checklist

| # | Condition | Status |
|---|---|---|
| 1 | Trend lineage has a terminal decision | YES — REJECTED (seq 25) |
| 2 | MR not opened, by authority | YES — §2.2 unapproved at Trend terminal; no MR record, prereg or approval (§C) |
| 3 | Trial ledger complete and chain-valid | YES — 3/3 Cycle-2 trial IDs terminal; verify() = []; tip `b258ec2b…a071` |
| 4 | Evidence preserved and indexed | YES — 232 files, `CYCLE2_CLOSURE_SHA256SUMS.txt`; 3/3 funnel results byte-identical (§G) |
| 5 | H1 untouched | YES — no H1 trial or package change in Cycle 2 |
| 6 | No new family opened | YES — only BTSL_EMA_REGIME/L2 and PIPELINE_NULL_CALIBRATION/L2 |
| 7 | P2 firewall intact | YES (§I) |
| 8 | Paper-admission eligibility recorded | YES — none eligible (§H) |
| 9 | No paper worker launched | YES |
| 10 | P3 unstarted | YES |
| 11 | Real money unauthorized | YES |

## Cycle-2 final status block

```text
RESEARCH_CYCLE2_CLOSURE_1                    = PASS
RESEARCH_CYCLE2_COMPLETE                     = YES
CYCLE2_SURVIVORS                             = 0
TREND_DONCHIAN_DECISION                      = REJECTED
MEAN_REVERSION_LINEAGE_OPENED                = NO
NULL_RECALIBRATION                           = PASS
CYCLE2_TRIAL_IDS                             = 3 (SCI 1/12 · CAL 2/6)
CYCLE2_CONFIGURATIONS                        = 6/24
CYCLE2_ENGINE_INVOCATIONS                    = 34/120
CYCLE2_CAP_EXHAUSTED                         = NO
TREND_FAMILY_CUMULATIVE_N                    = 15
SELECTION_LEDGER_CHAIN                       = PASS (26 records, tip b258ec2b…a071)
VALIDATION_WINDOW_TOUCHED_IN_CYCLE2          = NO
PRISTINE_HISTORICAL_HOLDOUT_PROVEN           = NO
PROSPECTIVE_EDGE_PROVEN                      = NO
PAPER_ADMISSION_REVIEW_ELIGIBLE_CANDIDATES   = 0
PAPER_WORKERS_STARTED                        = 0
H1_STATUS_CHANGED                            = NO
EVIDENCE_PRESERVED                           = YES (232 files, SHA256SUMS 40ee0d4430a8917887f4ad1b8e126bb3b24f2cbc9056e831c8d18a6c2b5241c0)
FP_CONTROL_3_TOUCHED                         = NO
P2_RUNTIME_MUTATED                           = NO
P3_STARTED                                   = NO
REAL_MONEY_AUTHORIZED                        = NO
OWNER_DECISION_REQUIRED                      = YES
ONE_NEXT_ACTION                              = Owner merges this PR manually; Cycle 2 then STOPs
```

**STOP.**
