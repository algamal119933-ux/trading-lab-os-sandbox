# S6 — ACTIVATION OF FP-CONTROL-2, AND TWO GATE CONTRADICTIONS

**Stage:** `P2 — PROSPECTIVE PAPER PROOF`, §13 stage S6.
**Authority:** [`P2_CONTRACT.md`](P2_CONTRACT.md). This record does not restate
it and does not extend it.

```text
T0              2026-09-20T12:00:00Z          immutable, never moved
cohort_id       FP-CONTROL-2-20260920T120000Z
ACTIVATION_UTC  2026-09-20T12:03:14Z          hard cap 2026-10-20T12:03:14Z
M2              0e920db62e17ac43bab29bddc8f208e16d5db2a3   stamped on every record
M1 (declared)   3924986af8a709059a61a90aeb308999e1e3d02e   registry source_commit

ACTIVATION_CERTIFIED = NO        the cohort runs; the validator cannot yet certify it
PAPER / RESEARCH ONLY            REAL_MONEY_AUTHORIZED = NO
PROSPECTIVE_PAPER_EDGE = NOT_EVALUATED
```

---

## 1. What happened

A host-level `systemd --user` one-shot fired at `2026-09-20T12:03:00Z`, inside
the lawful window `[T0, T0 + one candle period)`. It re-verified every
precondition and then started the cohort through `scripts/start_fp_control.sh`
— no manual Docker, no alternate launcher.

```text
[ok] window: T0+180s, inside [T0, T0+3600s)
[ok] pinned at M2 0e920db6, tree clean
[ok] lane empty, no capture lock, no containers
[ok] registry lawful; role/cohort/T0 agree; strategy+config match the frozen identity
[ok] PAPER_GUARD_PASS
[ok] DATASET_LOCK_GATE = PASS
ACTIVATION_START_ISSUED 2026-09-20T12:03:06Z
```

The scheduler was deliberately moved off this session beforehand: a
session-owned starter would have died with the terminal, and the window is one
hour wide on a fixed date. It did die — the watcher process was killed hours
before T0 — and the activation happened anyway, which is the whole point.

## 2. The cohort is lawful

Every executable check on the cohort itself passes.

```text
reconciliation      14/14 PASS, --require-pass exit 0
  ledger_chain_integrity · record_role_binding · record_attribution ·
  record_source_commit · registry_source_commit_equivalence · input_uniqueness ·
  decision_uniqueness · decision_input_linkage · decision_causality ·
  event_time_replay · execution_backed_by_decision · no_duplicate_execution ·
  restart_continuity · paper_only_authority
paper guard         PAPER_GUARD_PASS
identity            one role, one cohort id, one source commit (0e920db6)
chains              verify from genesis
credited evidence   18 POST_T0 + LIVE decisions and rising
gap bars            0
```

Activation validation itself passes **8 of its 10 checks**: chains from genesis,
one identity throughout, a fresh lane, no `PRE_T0 + LIVE`, the first credited bar
closing exactly at T0, reconciliation, no activation gap, and a start 186 s after
T0 — inside the 3600 s bound.

## 3. An error of mine, recorded plainly

Preflight's check 16 is named *"candidate can be restarted safely in a controlled
**pre-T0** drill"*. Its subject is a pre-T0 qualification lane, and it was
satisfied on L1 during S3. Reading contract §7's requirement of `preflight 16/16`
at activation, I drove the missing check by performing a governed restart on the
**cohort** lane instead. That was wrong: a pre-T0 check does not belong on L2.

The restart was itself lawful — same commit, tracked tree clean, nothing
committed between, and §7's restart law makes it continuity; `restart_continuity`
reports *"2 recorded start(s), restart counters [0, 1] … each restart resumed the
existing chain"*. The cohort's evidence is intact. What it cost was activation
check 1.

## 4. Two contradictions in merged authority

### 4.1 Check 1 and preflight check 16 cannot both be satisfied

```text
activation check 1   requires EXACTLY ONE run_started, restart_counter 0
activation check 8   requires preflight 16/16, and preflight check 16 requires
                     the instance "stopped and started again so the second run
                     is visible in the evidence"                → at least TWO runs
both inspect the same L2 lane
```

Measured, not argued:

```text
with 1 run   preflight blocked [6, 11, 14, 16]   check 16 UNPROVEN
with 2 runs  preflight blocked [6, 11, 14]       check 16 PASS
             but check 1 FAILS on two runs
```

No lane can hold exactly one run and at least two runs. `validate_activation` is
unsatisfiable as written, for any cohort, with or without my drill. The drill did
not create this; it revealed it.

### 4.2 The validator is pinned with the runtime it validates

`scripts/validate_activation.py` matches `scripts/*.py`, so it is inside
`RUNTIME_TREE`. The runtime checkout is pinned at M2 for the cohort's whole life
(§13), and `fp_lane.REPO_ROOT` derives from the module's own location with
symlinks resolved — so a checkout that carries a repaired validator resolves to
its **own** empty `user_data`, and the checkout that holds the lane carries only
M2's validator.

**Any validator defect present at M2 is therefore unfixable for that cohort.**
Check 8 could never have reached PASS here even if no restart had happened,
because M2's validator cannot attach a running runtime at all.

### 4.3 A validator defect cannot be repaired while its cohort runs

4.2 said the pinned checkout would never receive a repair. The truth is harder,
and a gate established it rather than an argument.

The freeze writes `runtime_identity.source_commit = M1` and it is immutable for
the cohort's life. `reconcile`'s `registry_source_commit_equivalence` then asks
whether the declared commit and the stamped one are **the same system**. Any new
commit that alters `RUNTIME_TREE` is semantically different from M1, so evidence
stamped at it fails that finding:

```text
SEMANTIC_EQUIVALENCE(3924986a, <branch with the validator repair>) = DIFFERENT
  1 semantic difference(s): scripts/validate_activation.py
→ tests/test_fp_capture.py::test_reconciliation_passes_on_a_clean_capture
  FAILED: ['registry_source_commit_equivalence']
```

CI caught it on the first push. `scripts/validate_activation.py` matches
`scripts/*.py`, so **the repair may not be merged while FP-CONTROL-2 is
RUNNING** — not because a test is wrong, but because §5's equivalence law is
right. Moving the file out of `RUNTIME_TREE` would not help: removing it changes
the tree too.

So the repair is withdrawn from this change and held. What remains here touches
nothing inside `RUNTIME_TREE`, and this branch is `EQUIVALENT` to the declared
M1.

**The consequence, stated plainly: for the whole life of a cohort, any defect in
the tools inside `RUNTIME_TREE` — the activation validator among them — is
unfixable.** Check 8 could never have passed for this cohort under any sequence
of events available to me.

---

## 5. The repair that is held, not merged

`validate_activation` built its preflight context from an evidence directory and
a role alone. Four of preflight's sixteen checks are statements about a system
running right now; with no endpoints they answer `UNPROVEN`, which blocks exactly
as `FAIL` does. This is the same defect `seal_pre_t0_qualification` carried until
S3 repaired it there — the lesson did not generalise on its own.

An `Attachment` now threads the endpoints through, under the same flag names and
environment defaults as preflight's own CLI. **The lane and the role remain the
validator's own**: `Attachment` declares no lane and no role field, so a caller
supplies endpoints and can never redirect the checks at another cohort's
evidence, and a test asserts that absence.

Proven against the live cohort: check 8 reports `PREFLIGHT = PASS (16/16)`.

That repair is written and tested, and it is **not in this change** — §4.3 is
why. It waits for a lawful moment: after this cohort closes, or under an Owner
decision.

**Check 1 is deliberately left alone.** Changing what it asserts would decide,
on my own authority, that my cohort passes — and §17 forbids weakening a gate
and §23 forbids optimising evidence to obtain a verdict. That is the Owner's
call, stated in §6.

## 6. What the Owner is being asked to decide

Activation is not certified, and cannot be by the pinned validator. The cohort
is running and lawful. The options, none of which I may take unilaterally:

```text
a  read check 1 as "the FIRST start was fresh, counters contiguous, continuity
   verified" rather than "only one start ever" — aligns it with §7's restart law
   and with preflight check 16, which demands the second run
   NOTE: any such change is inside RUNTIME_TREE and so is barred while the
   cohort runs, exactly as the validator repair is — see 4.3
b  evaluate preflight check 16 against the pre-T0 qualification lane rather than
   L2 when validating activation — it is a pre-T0 drill by its own name
c  accept two-invocation evidence for this cohort: the validator's other checks
   from the pinned tool, plus attached preflight 16/16 run separately
d  treat the restart as invalidating the cohort — a replacement-T0 question,
   and §11 grants no replacement budget
```

Nothing here is a replacement-T0 situation on the evidence: a cohort is
invalidated only by a technical defect in its evidence or identity, and there is
none. The frozen T0 and cohort remain lawful.

## 7. How this reached CI

The suite was run after staging but **before committing**, when `git rev-parse
HEAD` still resolved to merged main — and
`test_reconciliation_passes_on_a_clean_capture` stamps its synthetic evidence
with HEAD. It therefore passed against a commit that did not yet contain the
change under test. Running the gates again after the commit, not only before it,
is the discipline that was missing.

## 8. What this change does not do

```text
no T0 moved · no cohort created · no lane reused · no sealed evidence credited
no strategy, risk, Dataset, admission or runtime semantic change
the runtime was not stopped and the cohort was not restarted for this record
the pinned M2 checkout is untouched; this work is from the control worktree
```

```text
PAPER / RESEARCH ONLY
REAL_MONEY_AUTHORIZED = NO
PROSPECTIVE_PAPER_EDGE = NOT_EVALUATED
```
