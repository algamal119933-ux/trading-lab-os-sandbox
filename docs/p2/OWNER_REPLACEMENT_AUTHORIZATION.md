# OWNER BOUNDED REPLACEMENT AUTHORIZATION — ONE COHORT

**Granted by:** the Owner. Materialized here because it is a standing authority
that outlives the conversation that granted it, and because the T0 instrument
`freeze_t0` reads cannot carry it: that file names a qualification commit and
certificate which do not exist until the successor has been qualified.

```text
REPLACEMENT_DEFECT      ACTIVATION-CONTRACT-UNSATISFIABLE
REPLACEMENT_BUDGET      1
BUDGET_CONSUMED_BY      the first successor cohort frozen under this record
SUCCESSOR_ROLE          FP-CONTROL-3
PRIOR_COHORT            FP-CONTROL-2-20260920T120000Z
PRIOR_CLOSURE           ACTIVATION_CONTRACT_UNSATISFIABLE
REAL_MONEY_AUTHORIZED   NO
```

---

## The defect this replaces

`validate_activation`'s initial-run requirement versus preflight's
restart-continuity requirement, both applied to the same activation lane and
state, and not simultaneously satisfiable:

```text
validate_activation check 1   PASS only if the lane holds EXACTLY ONE run_started
preflight check 16            UNPROVEN while that same lane holds FEWER THAN TWO
contract §7 check 8           requires preflight --require-pass
contract §1                   UNPROVEN blocks exactly as FAIL does
```

Repairing either requires editing a file inside `RUNTIME_TREE`, and a frozen
cohort cannot consume such a change without failing
`registry_source_commit_equivalence`. §11 grants no replacement budget, so this
record is what grants one — for this defect, once.

## What it is not

```text
NOT performance-based            never for zero trades, poor P&L, an unfavourable
                                 window, or strategy shopping
NOT automatically renewable      budget 1, and a second use requires a new record
NOT a new stage, strategy,       FP-CONTROL-3 runs the SAME frozen BASELINE-1
    candidate or role factory    control, with the same strategy and config hashes
NOT authority for P3 or live money
```

Section 11 class F is unchanged and remains the load-bearing rule: a valid
unfavourable cohort is a RESULT, and re-running it to obtain a better one is the
behaviour every gate here exists to prevent. This record may never be cited for
that.

## What it requires before it may be used

```text
truthful disposition of FP-CONTROL-2      merged
repaired activation tooling               merged, with a passing activation fixture
fresh qualification at a new Mq           certificate and binding pinned
fresh source identity                     new M1 / M2
fresh lane                                freqtrade/user_data/fp-control-3
new future T0 and new cohort_id           chosen under the current timing law
zero inherited credit                     no FP-CONTROL-1 or FP-CONTROL-2 record
                                          may be credited to it
paper-only runtime                        REAL_MONEY_AUTHORIZED = NO
PROSPECTIVE_PAPER_EDGE                    NOT_EVALUATED
```

The T0 freeze itself still requires the separate merged
`docs/p2/OWNER_T0_AUTHORIZATION.md` naming `FP-CONTROL-3` and the fresh
qualification commit and certificate. `freeze_t0` reads that file from git and
refuses without it; this record does not replace it and cannot.

```text
PAPER / RESEARCH ONLY
REAL_MONEY_AUTHORIZED = NO
```
