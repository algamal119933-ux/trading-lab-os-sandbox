# Claude Account Handoff — 2026-09-29

**Authority:** Owner directive `CLAUDE-ACCOUNT-HANDOFF-1` (2026-09-29). **This
is not a research unit.** It creates one canonical continuity document so a
fresh Claude Code account can resume immediately from canonical project state
without re-auditing closed stages.

**Do NOT re-audit:** `TRADING-RESEARCH-RECONCILIATION-0`,
`RESEARCH-FOUNDATION-CLOSURE-1`, Null Attempt 3, H1 controlled reproduction,
`H1-PAPER-READINESS-QUALIFICATION-1`, PR #33, PR #34, PR #35, PR #36, PR #37.
Those units are closed evidence.

## Correction to the Owner's original §3 framing (recorded honestly, not
## reopened)

The Owner's authorization for this handoff stated: *"The Owner previously
requested Mean-Reversion Cycle-1 discovery, but H1-PAPER-READINESS-QUALIFICATION-1
was executed instead."* That framing does not match canonical history, and the
current account stopped and reported this before writing this document, per
the authorization's own §0 NO-LOOP LAW ("if existing canonical records disagree
materially with the handoff facts below: STOP and report the exact
contradiction"). The Owner reviewed the contradiction and directed the
correction recorded below.

**What canonical history actually shows:** both units were separately
authorized and both were separately executed to a terminal decision, in this
order, within the same session:

1. `MEAN-REVERSION-CYCLE1-DISCOVERY-1` — executed, reached **`REJECTED`**.
   Trial `TRIAL-MR-ZSCORE-WF-1`: `PREREGISTERED` (ledger seq 14) →
   `REJECTED` (ledger seq 15). Merged as **PR #36**, merge commit
   `fb2c8fb6738bd40296bf705a82373fd8e86d2514`.
2. `H1-PAPER-READINESS-QUALIFICATION-1` — authorized and executed afterward,
   reached **`ADVANCE_TO_PAPER_ADMISSION_REVIEW`**. Trials `TRIAL-H1-QUAL-1`
   (`ABORTED` — a params-JSON space-nesting bug caught before any valid
   result existed) and `TRIAL-H1-QUAL-2` (`SURVIVED`). Merged as **PR #37**,
   merge commit `0862ea3c7dd26265ccab6c45c264fda2d23d1198`.

So Mean-Reversion Cycle-1 is **not pending** — it already ran and was
rejected. Per the Owner's own §23 continuation law ("immediately after
Mean-Reversion reaches SURVIVOR/REJECTED/INCONCLUSIVE, do NOT return for
another review — automatically create RESEARCH-CYCLE1-CLOSURE-1"), the correct
next unit, once the history is stated accurately, is **`RESEARCH-CYCLE1-CLOSURE-1`**,
not a fresh Mean-Reversion execution. This is what §5 below records.

## Section 3 record (kept, unmodified in substance — not investigated further)

```text
LAST_OWNER_UNIT_MISMATCH        = RECORDED (see correction above)
H1_RESULT                       = RETAINED_AS_OBSERVED_CANONICAL_EVIDENCE
H1_FROZEN                       = YES
NO_FURTHER_H1_RESEARCH_IN_CYCLE1 = YES
```

## Current authoritative state

```text
P2                                  = ACTIVE
FP_CONTROL_3                        = CANONICAL ACTIVE P2 CONTROL
FP_CONTROL_3_TOUCHED_BY_RESEARCH    = NO
P2_RUNTIME_MUTATED_BY_RESEARCH      = NO
P3_STARTED                          = NO
REAL_MONEY_AUTHORIZED               = NO

RESEARCH_FOUNDATION_CLOSED          = YES
OFFLINE_RESEARCH_AUTHORITY          = ACTIVE
RESEARCH_EXECUTION_DEFAULT          = SEPARATE RUNNER / CI
RESEARCH_TRIAL_ACCOUNTING           = OPERATIONAL
TRADE_LEVEL_ARTIFACT_CAPTURE        = PRESENT
NULL_CALIBRATION                    = PASS
PIPELINE_VALIDITY_ISSUE             = NO

H1_AGGREGATE_REPRODUCTION           = PASS
H1_RECORDED_METRICS_MATCH           = EXACT
H1_TRADE_LEVEL_REPRODUCTION         = UNVERIFIED
H1_FULL_ARTIFACT_EQUIVALENCE        = NOT_PROVEN
H1_PAPER_READINESS_QUALIFICATION    = PASS
H1_PAPER_READINESS_DECISION         = ADVANCE_TO_PAPER_ADMISSION_REVIEW
H1_PAPER_ADMITTED                   = NO
H1_PAPER_WORKER_STARTED             = NO
H1_PROSPECTIVE_EDGE_PROVEN          = NO

PRISTINE_HISTORICAL_HOLDOUT_PROVEN  = NO
FUNDING_AUTHORIZED                  = NO
CROSS_SECTIONAL_AUTHORIZED          = NO

MEAN_REVERSION_STARTED              = YES
MEAN_REVERSION_DECISION             = REJECTED
MEAN_REVERSION_PAPER_ADMISSION_REVIEW_ELIGIBLE = NO

NEXT_AUTHORIZED_RESEARCH_UNIT       = RESEARCH-CYCLE1-CLOSURE-1
```

## Exact file pointers (do not scan the repo — start here)

```text
Offline research authority     research/OFFLINE_RESEARCH_AUTHORITY_1.md
Research Selection Ledger      research/records/trial_ledger.jsonl
Ledger enforcement module      research/trial_ledger.py
Candidate registry             research/external/candidate_registry.json
Dataset V2 lock                research/datasets/dataset_v2.lock.json
Research workflows             .github/workflows/extbench.yml
                                .github/workflows/null_control.yml
                                .github/workflows/mean_reversion.yml
                                .github/workflows/h1_qualification.yml
Mean-Reversion Cycle-1 code     research/mean_reversion/
                                  PREREGISTRATION.md (frozen hypothesis/laws)
                                  MeanReversionZScore.py
                                  run_walkforward.py
                                (terminal record: PR #36, ledger seq 14-15,
                                 REJECTED — cite, do not re-run)
H1 qualification record         research/h1_qualification/
                                  PREREGISTRATION.md (frozen H1 identity/laws)
                                  run_qualification.py
                                (terminal record: PR #37, ledger records for
                                 TRIAL-H1-QUAL-1/2 — cite, do not re-run;
                                 H1 remains frozen at
                                 ADVANCE_TO_PAPER_ADMISSION_REVIEW)
Research Foundation closure     PR #35 description (merge commit
                                 30064e86a4ec05d27d5e5187596452499503b39e);
                                 research/OFFLINE_RESEARCH_AUTHORITY_1.md
Governing repo instructions     CLAUDE.md
Evidence storage                ~/Documents/TLOS-Evidence/trading-research/
Scope-audit history / rollover  tests/test_p2_scope_audit.py
                                 (MERGED_STAGE_SCOPES — one entry per merged
                                  PR, keyed to its own two-parent merge SHA)
```

## Continuation law

```text
NEXT UNIT:              RESEARCH-CYCLE1-CLOSURE-1

No further Owner review is required to begin RESEARCH-CYCLE1-CLOSURE-1,
because it is a closure/reporting unit, not a new research trial: Mean-
Reversion Cycle-1 already reached a terminal decision (REJECTED) and H1
already reached its terminal qualification decision
(ADVANCE_TO_PAPER_ADMISSION_REVIEW). No new performance trials are allowed
during closure. No second research family may start automatically.
```

## RESEARCH-CYCLE1-CLOSURE-1 — operative instructions for the next account

These are the Owner's own closure-unit instructions from
`CLAUDE-ACCOUNT-HANDOFF-1` §§23-29, carried forward verbatim because Mean-
Reversion Cycle-1 has already reached its terminal state and this is now the
operative next step (not the original Mean-Reversion execution instructions
in that authorization's §§6-22, which are moot: that lineage already ran and
closed as `TRIAL-MR-ZSCORE-WF-1` / `REJECTED`, PR #36).

### Automatic follow-on

Immediately after Mean-Reversion reached a terminal decision (it has:
`REJECTED`), do NOT return for another planning review. Create
`RESEARCH-CYCLE1-CLOSURE-1`. This is a closure/reporting unit, not another
research unit. No new performance trials are allowed during closure.

### Cycle-1 closure must summarize

- H1 final historical state
- Mean-Reversion final state
- all Cycle-1 lineages
- all selection/trial counts
- all aborted/failed attempts
- known selection debt
- data limitations
- holdout truth
- prospective-evidence status
- P2 firewall status
- paper-admission eligibility
- remaining scientific limitations
- No new strategy family.

### Paper-admission eligibility

At Cycle-1 closure:
- H1 may be listed as `PAPER_ADMISSION_REVIEW_ELIGIBLE` because its
  qualification already reached `ADVANCE_TO_PAPER_ADMISSION_REVIEW`.
- For Mean-Reversion: since the decision is `REJECTED`,
  `PAPER_ADMISSION_REVIEW_ELIGIBLE = NO`.
- Eligibility is NOT admission. Do not launch any paper worker.

### RESEARCH_CYCLE1_COMPLETE law

Set `RESEARCH_CYCLE1_COMPLETE = YES` only when:
1. Mean-Reversion has a terminal decision. (It does: `REJECTED`.)
2. Trial ledger is complete and chain-valid.
3. Evidence artifacts are durable.
4. H1 remains frozen.
5. No second new family was opened.
6. P2 firewall remains intact.
7. Paper-admission eligibility is recorded.
8. No paper worker was launched.
9. P3 remains unstarted.
10. Real money remains unauthorized.

### Cycle-1 final report — required sections

```text
A — CANONICAL STATE
B — H1 FINAL STATUS
C — MEAN-REVERSION FINAL STATUS
D — CYCLE-1 TRIAL ACCOUNTING
E — SELECTION DEBT
F — DATA / HOLDOUT TRUTH
G — EVIDENCE STATUS
H — PAPER-ADMISSION ELIGIBILITY
I — P2 FIREWALL
J — REMAINING LIMITATIONS
K — OWNER DECISION REQUIRED
L — ONE NEXT ACTION
```

### Cycle-1 final status block (fill and return)

```text
RESEARCH_CYCLE1_CLOSURE_1                          = PASS / PARTIAL / BLOCKED
RESEARCH_CYCLE1_COMPLETE                           = YES / NO
H1_HISTORICAL_QUALIFICATION                        = PASS
H1_PAPER_ADMISSION_REVIEW_ELIGIBLE                 = YES
H1_PAPER_ADMITTED                                  = NO
MEAN_REVERSION_DECISION                            = REJECTED
MEAN_REVERSION_PAPER_ADMISSION_REVIEW_ELIGIBLE     = NO
TOTAL_CYCLE1_LINEAGES                              = ...
TOTAL_SCIENTIFIC_CONFIGURATIONS                    = ...
TOTAL_EXECUTION_ATTEMPTS                            = ...
TOTAL_ABORTED_ATTEMPTS                              = ...
TOTAL_FAILED_ATTEMPTS                                = ...
SELECTION_LEDGER_CHAIN                              = PASS / FAIL
PRISTINE_HISTORICAL_HOLDOUT_PROVEN                  = NO
PROSPECTIVE_EDGE_PROVEN                             = NO
PAPER_WORKERS_STARTED                               = 0
FP_CONTROL_3_TOUCHED                                = NO
P2_RUNTIME_MUTATED                                  = NO
FUNDING_STARTED                                     = NO
CROSS_SECTIONAL_STARTED                             = NO
P3_STARTED                                          = NO
REAL_MONEY_AUTHORIZED                               = NO
OWNER_DECISION_REQUIRED                             = ...
ONE_NEXT_ACTION                                     = ...
```

### Terminal stop

After `RESEARCH-CYCLE1-CLOSURE-1`: **STOP.** Do not automatically open
Funding, open Cross-Sectional, open another Mean-Reversion lineage, start
Paper Admission, launch a paper worker, start P3, or start real money. The
next Owner decision must be based on the completed Cycle-1 evidence.

## Hard constraints that remain in force (unchanged, repeated for continuity)

- Absolute P2 / FP-CONTROL-3 firewall: never mutate its strategy, config,
  DB, evidence, or containers.
- No real money, no P3.
- Research execution defaults to off-host / separate CI runner.
- Preregister every trial before its outcome is known; the ledger
  (`research/trial_ledger.py`) enforces this technically.
- Never report only winning configurations — every attempt (aborted, failed,
  rejected, survived) stays in the ledger.
- Reuse-before-build / minimum-delta rule. Forbidden new tools/frameworks in
  this cycle: trialgate, arch, DVC, Hummingbot, NautilusTrader, VectorBT,
  Qlib, FinRL, ML/RL, LLM trading decisions, Control Room implementation.
- No silent widening of scope after seeing results.
- A technical bug fix reuses the same trial identity only while zero valid
  results exist yet; anything past that gets a fresh attempt ID with the
  prior one preserved, never overwritten.

## Account-handoff readiness (this account's own preflight, read-only)

```text
CANONICAL_MAIN_SHA (before this doc's merge)  = 0862ea3c7dd26265ccab6c45c264fda2d23d1198
RUNTIME_PINNED_SHA                            = 3191285a28823907f62c6eb915327599cd6ed90b
WORKTREE_CLEAN                                = YES
UNTRACKED_FILES                               = NONE (other than this new document)
OPEN_RESEARCH_WORKFLOWS                       = 0
BACKGROUND_TASKS                              = 0
FP_CONTROL_3_TOUCHED                          = NO
P2_RUNTIME_MUTATED                            = NO
HANDOFF_DOCUMENT                              = research/CLAUDE_ACCOUNT_HANDOFF_2026-09-29.md
NEXT_AUTHORIZED_UNIT                          = RESEARCH-CYCLE1-CLOSURE-1
AUTOMATIC_FOLLOW_ON                           = none (RESEARCH-CYCLE1-CLOSURE-1 is itself the closure unit)
```
