# FP-CONTROL-1 — cohort closure record

**Cohort:** `FP-CONTROL-1-20260908T121513Z`
**T0 (frozen, preserved as history):** `2026-09-08T12:15:13Z`
**Closed:** `2026-09-13T20:58:24Z`
**Closure reason:** `EVIDENCE_LANE_LOST_IN_HOST_MIGRATION`
**Owner decision:** PATH 2 — terminate, do not continue, do not reconstruct.

```text
PAPER_TRADING_OPERATIONAL_CAPABILITY = NOT_PROVEN
PROSPECTIVE_PAPER_EDGE               = NOT_EVALUATED
FULL_TRADE_LIFECYCLE                 = NOT_ESTABLISHED_BY_AVAILABLE_EVIDENCE
MEASURABLE_POST_T0_EVIDENCE          = UNAVAILABLE_IN_CURRENT_EVIDENCE_LANE
CHANGE_MODEL_CLASSIFICATION          = NOT_APPLICABLE_TO_TRADING_SEMANTICS /
                                       OWNER_EVIDENCE_DISPOSITION
REAL_MONEY_AUTHORIZED                = NO
```

Every line above is a statement about evidence. None of them is a statement
about what happened between T0 and this closure.

## What can be said, and what cannot

The cohort's evidence lane is not present in this workspace: the four ledgers
(`paper_input_ledger`, `paper_decision_ledger`, `paper_trade_ledger`,
`paper_incident_ledger`), the trade database, the logs, and the pre-T0
preflight and admission artifacts. They were gitignored by design, and the
migration was made with a **git bundle**, which carries committed history and no
untracked runtime state.

What follows from that, exactly:

| Claim | Status |
| --- | --- |
| the surviving evidence establishes a full trade lifecycle | **no** — it does not |
| post-T0 evidence can be read and measured here | **no** — unavailable in the current evidence lane |
| paper trading operational capability is proven | **no** — remains `NOT_PROVEN` |
| prospective paper edge was evaluated | **no** — remains `NOT_EVALUATED`, and FP-CONTROL-1 was never able to evaluate it |
| no trade occurred during the window | **not claimed** — unknowable from what survives |
| the instance stopped, or when it stopped | **not claimed** — unknowable from what survives |

The distinction is the point of this record. "The ledgers are unavailable"
supports "this cannot be established". It does not support "this did not
happen". Where the evidence cannot answer, the question is left open rather
than resolved in the convenient direction.

## The Owner disposition, filed as a disposition

```text
"The prior host will not be used again; treat the cohort as unrecoverable."
= OWNER DISPOSITION
```

It is a decision about how the project proceeds. It is **not** independent
evidence of historical non-occurrence, and it is recorded in the registry's
`outcome.owner_disposition` field, separate from every evidence field, so that
it can never be read as such.

The evidence lane's absence and the Owner's decision are two different facts:
the first limits what can be shown, the second settles that no attempt to
recover it will be made.

## Change-model classification

```text
CHANGE_MODEL_CLASSIFICATION = NOT_APPLICABLE_TO_TRADING_SEMANTICS /
                              OWNER_EVIDENCE_DISPOSITION
```

Stated explicitly:

* **No strategy, config, pair, timeframe or sizing semantics changed.** The
  strategy and config still hash to their frozen values — `8c0bc6c5…` and
  `d1d078c6…`.
* **No O/R/S classification is asserted for this closure.** It is not filed as
  an `O`, `R` or `S` change-log entry, because it is not a section-15 change to
  a running cohort; it is an administrative disposition of evidence.
* **The O/R/S model is unchanged.** It continues to govern changes to a running
  cohort exactly as written in
  [`FP_BOOT_1_ENTRY_STATE.md`](FP_BOOT_1_ENTRY_STATE.md), and the cohort's two
  pre-existing `O` entries are untouched. No class was added, removed or
  reinterpreted.

## What is preserved, and what is forbidden

`t0_utc`, `cohort_id` and `runtime_identity.source_commit` are left exactly as
they were frozen. They are history:

```text
NEVER reuse  NEVER rewrite  NEVER move  NEVER back-date
```

A future forward-paper run is a **new cohort**, requiring:

1. a full host-side pre-T0 pass on the new host (activation pack A1-A13),
2. `preflight.py --require-pass` exit 0 against this host's runtime,
3. a new Owner authorisation, and
4. a new `T0` and a new `cohort_id` derived from it.

Nothing from the closed window may be carried into that cohort — no ledger, no
warm-up state, no partial result, no elapsed-time credit.

## Machine-readable record and the rules that hold it

`research/fp/records/forward_paper_cohort_registry.json`: instance status
`CLOSED`, with `closed_utc`, `closure_reason` and `outcome` as above;
`fp_run_active` false; `paper_alpha_cohort` `NONE`; `entry_state` `C`;
`real_money_authorized` false.

The registry schema carries the closure rules as conditional JSON Schema, so
they are enforced on the document itself rather than only in a test:

| Rule | Enforcement |
| --- | --- |
| `outcome` is forbidden on a `NOT_STARTED`, `RUNNING` or `PAUSED` row | instance `allOf` / `if`-`then` |
| a `CLOSED` FP-CONTROL-1 row must carry `closed_utc`, `closure_reason` and `outcome` | instance `allOf` / `if`-`then` |
| an `EVIDENCE_LANE_LOST_IN_HOST_MIGRATION` closure must read `NOT_PROVEN`, `NOT_EVALUATED` or `NOT_PROVEN`, `NOT_ESTABLISHED_BY_AVAILABLE_EVIDENCE` and `UNAVAILABLE_IN_CURRENT_EVIDENCE_LANE` — `PROVEN`, `OBSERVED`, `NOT_OBSERVED`, `AVAILABLE` and `NONE` all fail | instance `allOf` / `if`-`then` |
| the shared vocabulary stays open to every other closure reason | the constraint lives in the conditional, not in the enums |
| `fp_run_active` must agree with the instance rows in both directions | root `allOf` / `if`-`then`-`else` |
| no undeclared `outcome` field | `additionalProperties: false` |

`tests/test_fp_admission.py` carries a negative control for each rule: every one
is shown to reject its own violation, and the two rules whose failure message is
generic are additionally shown to accept the same document once the violation is
removed.

## Unchanged by this closure

```text
ENTRY_STATE           = C            (no paper-admissible survivor exists)
PAPER_ALPHA_COHORT    = NONE
PAPER_ADMISSION       = BLOCKED
BASELINE-1            = closed; Development PASS/NEUTRAL, Validation spent
REAL_MONEY_AUTHORIZED = NO
```

## Dataset V2

Dataset V2 remains a **separate blocked prerequisite**. No dataset was
downloaded, reacquired, re-frozen or modified by this closure. Its restoration
decision will be handled in a separately authorised stage after closure
acceptance.
