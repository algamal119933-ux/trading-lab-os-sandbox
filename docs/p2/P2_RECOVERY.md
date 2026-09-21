# P2 RECOVERY — ONE TRANSACTION

**Stage:** `P2 — PROSPECTIVE PAPER PROOF`. **Authority:**
[`P2_CONTRACT.md`](P2_CONTRACT.md) §11 class **B**, plus the Owner's bounded
replacement grant recorded in
[`OWNER_REPLACEMENT_AUTHORIZATION.md`](OWNER_REPLACEMENT_AUTHORIZATION.md).

```text
FP-CONTROL-2   CLOSED   ACTIVATION_CONTRACT_UNSATISFIABLE — immutable history
FP-CONTROL-3   NOT_STARTED — one successor control, fresh everything
REPLACEMENT_BUDGET  1, granted for this named defect only
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO
PROSPECTIVE_PAPER_EDGE = NOT_EVALUATED · P3 NOT STARTED
```

---

## 1. The defect, and why one transaction

The activation contract was unsatisfiable. `validate_activation` check 1 passed
only when the lane held **exactly one** `run_started`; preflight check 16 —
required at 16/16 by §7 — reported `UNPROVEN` until the **same lane** held at
least two, and `UNPROVEN` blocks as `FAIL` does. No cohort could pass both.

Repair needs a `RUNTIME_TREE` file, and a frozen cohort cannot consume one: its
declared `source_commit` would no longer be "the same system", and
`registry_source_commit_equivalence` fails. CI proved that rather than
predicting it. So the cohort had to close before the tooling could be repaired,
and closing it alone would have stranded P2 with **no unclosed control role** —
the schema enum held only `FP-CONTROL-1` and `FP-CONTROL-2`. Closure, successor
and repair are therefore mutually dependent and land together.

## 2. The root repair — a lifecycle, not a deleted check

`RuntimeContext` gains `lifecycle`:

```text
PRE_T0_QUALIFICATION   default; unchanged. Before any T0 is frozen the candidate
                       must survive a real stop/start, so check 16 still demands
                       a second run — this is how S3 qualified.
INITIAL_ACTIVATION     a fresh cohort's FIRST validation. Such a lane holds one
                       run by construction, so the check asserts the opposite and
                       equally strict fact: EXACTLY one run, counter 0, all four
                       chains verifying, no bar decided twice, nothing re-recorded.
```

Nothing is deleted and nothing is disabled. Each requirement now sits where it
can be true, and restart continuity is still proven three times over:

```text
before the freeze   preflight check 16 on the qualification lane (unchanged)
during the cohort   reconcile's restart_continuity finding, every reconciliation
before closure      the A15 restart drill
```

`validate_activation` also gains an `Attachment` so it can interrogate the live
runtime — without it, four of preflight's checks answered `UNPROVEN` and check 8
could never pass for any cohort. The lane and role are **not** fields on
`Attachment` and never can be: they stay the validator's own.

## 3. The successor

Exactly one: `FP-CONTROL-3`, the smallest identifier the schema's closed role
enum can express. It runs the **same frozen BASELINE-1 control** — identical
`strategy_sha256`, `config_sha256`, pairs, timeframe, sizing, wallet and
`max_open_trades`. Nothing about the experiment changes.

```text
status NOT_STARTED · t0_utc null · cohort_id null · source_commit null
no outcome · empty change_log · fresh lane, db, logs and bot identity
    /freqtrade/user_data/fp-control-3/…   bot_name fp-control-3
```

`FP-CONTROL-1` is byte-identical. `FP-CONTROL-2` retains its T0, cohort id,
source identity, evidence, incidents, digests and archive unchanged.

## 4. What FP-CONTROL-2's evidence does and does not say

Kept deliberately apart, because they are different claims:

```text
evidence and identity   VALID — four chains verify from genesis over 2056
                        records, reconciliation PASS on all fourteen findings,
                        one role, one cohort, one source commit 0e920db6,
                        paper-only authority held, 60 credited POST_T0 + LIVE
                        decisions, sealed as l2-cohort-20260920T120000Z
                        (pack c0356770a21e6910) and replicated to the second device
activation              NOT CERTIFIED, and not certifiable
defect                  tooling and contract implementation
no evidence corruption  none found, none claimed
no performance cause    the trade ledger is empty because the frozen strategy
                        signalled hold on every live bar. §11 class F: a result
                        never invalidates a cohort. That is an OBSERVED RESULT,
                        not the defect, and may never be cited as one.
no Strategy/Risk/Dataset drift · no paper-only breach
```

## 5. Why some things are not in this transaction

The freeze law fixes a freeze candidate at registry + MANIFEST only, and
`freeze_t0` reads `docs/p2/OWNER_T0_AUTHORIZATION.md` from git naming the
successor role and a **fresh** qualification commit and certificate — values
that cannot exist until the successor has been qualified against this repaired
tooling. Those therefore follow as their own minimal transactions. This is an
executable gate forcing the split, not a preference.

```text
PAPER / RESEARCH ONLY
REAL_MONEY_AUTHORIZED = NO
PROSPECTIVE_PAPER_EDGE = NOT_EVALUATED
```
