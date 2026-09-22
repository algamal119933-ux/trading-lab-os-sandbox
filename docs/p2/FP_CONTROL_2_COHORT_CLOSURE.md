# FP-CONTROL-2 — COHORT CLOSURE

**Stage:** `P2 — PROSPECTIVE PAPER PROOF`.
**Authority:** [`P2_CONTRACT.md`](P2_CONTRACT.md) §11, class **B** — *a repair
needing a tracked runtime change: cohort invalid, runtime stop, CLOSED*.

```text
T0              2026-09-20T12:00:00Z            retained, never moved
cohort_id       FP-CONTROL-2-20260920T120000Z   retained
source_commit   3924986a (M1 declared) · 0e920db6 (M2 stamped)   retained
closed_utc      2026-09-21T17:05:00Z
closure_reason  ACTIVATION_CERTIFICATION_NOT_ACHIEVABLE_UNDER_FROZEN_ACTIVATION_CONTRACT

ACTIVATION      NOT CERTIFIED — validate_activation never returned exit 0
P2              NOT CLOSED by this record. This closes the COHORT, not the stage.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO
PROSPECTIVE_PAPER_EDGE = NOT_EVALUATED
```

This record keeps two things apart that are easy to blur, and the whole point of
it is that they stay apart:

```text
A  the cohort's EVIDENCE and IDENTITY        valid, attributable, intact
B  ACTIVATION CERTIFICATION                  not proven, and not provable
```

---

## 1. Why the cohort is closed

The activation contract cannot be satisfied. Not by this cohort, not by any
cohort, and not by any action available to an operator.

```text
validate_activation check 1   PASS only if the lane holds EXACTLY ONE run_started
                              with restart_counter 0
preflight check 16            UNPROVEN while the lane holds FEWER THAN TWO starts
contract §7 check 8           requires preflight --require-pass, i.e. 16/16
contract §1                   UNPROVEN blocks exactly as FAIL does
```

Both read the `evidence_dir` this row declares — `validate_activation` resolves
it from the registry lane and hands that same directory to preflight. So one
lane must hold both exactly one start and at least two. It is unsatisfiable, and
it was demonstrated in both directions on this cohort's own lane:

```text
with 1 run    preflight blocked [6, 11, 14, 16]    check 16 UNPROVEN
with 2 runs   preflight blocked [6, 11, 14]        check 16 PASS, check 1 FAIL
```

### Why it could not be repaired in place

Check 1 lives in `scripts/validate_activation.py` and check 16 in
`research/fp/preflight.py`. Both match `RUNTIME_TREE`. The freeze wrote
`runtime_identity.source_commit = M1`, immutable for the cohort's life, and
`reconcile`'s `registry_source_commit_equivalence` asks whether the declared
commit and the stamped one are the same system. Any commit editing either file
is semantically different from M1, so evidence stamped against it fails that
finding. This is not a prediction: CI rejected exactly such a commit —

```text
SEMANTIC_EQUIVALENCE(3924986a, 8e4df827) = DIFFERENT
  1 semantic difference(s): scripts/validate_activation.py
→ test_reconciliation_passes_on_a_clean_capture
  FAILED: ['registry_source_commit_equivalence']
```

Moving or deleting either file changes the tree too. **For the life of a cohort,
a defect in the tools inside `RUNTIME_TREE` is unfixable.** That is the defect
this closure is about.

## 2. What the evidence does say

The lane was never in question. Sealed as `l2-cohort-20260920T120000Z`, pack
digest `c0356770a21e6910`, replicated and re-verified on the second device.

```text
records          2056 input · 2056 decision · 5 incident · 0 trade · 2 runs
chains           all four verify from genesis
reconciliation   PASS, all fourteen findings, --require-pass exit 0
identity         one role · one cohort id · one source commit 0e920db6
paper authority  PAPER_GUARD_PASS; no record claims a live execution
credited         60 POST_T0 + LIVE decisions
PRE_T0 + LIVE    none
first credited   the bar closing exactly at 2026-09-20T12:00:00Z
activation gap   none; the runtime started 186 s after T0, inside the 3600 s bound
```

Eight of the ten activation checks passed. The two that did not are checks 1 and
8 — the contradiction above, and the fact that the pinned validator cannot attach
a running runtime at all.

## 3. What this closure is NOT

```text
NOT evidence corruption      the chains verify and reconciliation is PASS
NOT trading performance      the strategy signalled hold on every live bar, so the
                             trade ledger is empty. That is a recorded observation
                             of the frozen system, and §11 class F is explicit that
                             a result never invalidates a cohort. It is not the
                             reason for this closure and must never be read as one.
NOT a strategy/risk/Dataset change   none occurred; hashes match the frozen identity
NOT an activation PASS               activation was never certified
NOT a P2 PASS                        P2 remains open
NOT a replacement authorization      §11: "Replacement-T0 budget is not granted by
                                     this contract." None is claimed or implied here.
```

## 4. An error of mine, kept in the record

To satisfy preflight check 16 I performed a governed restart on the cohort lane.
Check 16 is a *pre-T0* drill by its own name and was already satisfied on L1 in
S3; driving it on L2 was wrong. The restart was lawful continuity —
`restart_continuity` reports both runs resumed the existing chain — and the
evidence survived it intact. It did not cause this closure: the contradiction
existed before it and would have blocked check 8 regardless, because M2's
validator cannot attach a runtime. But it is why check 1 reads FAIL rather than
PASS, and the record should say so.

## 5. Disposition and what follows

```text
runtime            stopped through scripts/stop_fp_control.sh
containers         zero, any state
capture processes  zero
lane               archived whole, then empty
archive            artifacts/l2-cohort-20260920T120000Z — Tier 1 sealed,
                   Tier 2 digests published, replicated to the second device
frozen identity    T0, cohort_id and source_commit retained unchanged
FP-CONTROL-1       byte-identical, untouched
```

No record in this lane may be credited to any future cohort. The crediting law
refuses it on `cohort_id` alone, and the archive lives outside the only host tree
any container mounts.

**What this record does not decide.** Whether a replacement cohort may exist is
not settled here and is not implied by this closure. §11 grants no replacement
budget, so a replacement requires a new Owner authorization naming this defect
and this closure. The activation tooling repair comes first, at its root, and
only then does the replacement question arise.

```text
PAPER / RESEARCH ONLY
REAL_MONEY_AUTHORIZED = NO
PROSPECTIVE_PAPER_EDGE = NOT_EVALUATED
P3 NOT STARTED · NOT AUTHORIZED
```
