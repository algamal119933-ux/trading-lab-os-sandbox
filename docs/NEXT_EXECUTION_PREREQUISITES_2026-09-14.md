# Verified State, Prerequisite Order, and Authority Boundaries — 2026-09-14

**Authoritative main:** `b27fe69c0688e6244ffc7b50e3d668b18392d42a`

```text
THIS DOCUMENT GRANTS NO EXECUTION AUTHORITY.
```

It records only:

* verified current state;
* prerequisite / order relationships;
* existing authority boundaries.

**Listing an item in the prerequisite order does not authorize its execution.**
Every prerequisite below remains subject to the authorization and gates defined
by its governing repository artifacts and Owner-controlled boundaries.

This document creates no stage taxonomy, renames no stage, reorders no roadmap,
and moves no gate.

---

## Verified current state

| Fact | Evidence |
| --- | --- |
| The prior FP-CONTROL-1 cohort is **CLOSED** | PR #10, merged as `b27fe69` with two parents; second parent `3d95909` verbatim. Registry instance status `CLOSED`, `closure_reason` `EVIDENCE_LANE_LOST_IN_HOST_MIGRATION`, `fp_run_active` false. [`FP_CONTROL_1_COHORT_CLOSURE.md`](fp-boot-1/FP_CONTROL_1_COHORT_CLOSURE.md) |
| The old T0 and cohort identity are **preserved, not reused** | `t0_utc` `2026-09-08T12:15:13Z`, `cohort_id` `FP-CONTROL-1-20260908T121513Z`, `source_commit` `4b0d7f63…` — unchanged on merged main |
| `REAL_MONEY_AUTHORIZED` | **NO** |
| `claude/strategy-source-research-prep` (`19d7d7e`) | **PARKED** — not an ancestor of `origin/main` |
| Dataset V2 | **absent / unrestored** on this host; the frozen lock is unchanged and remains the only authority |
| Runtime and T0 | **none active** — no container, no evidence directory, no new T0 |

The closed cohort claims nothing: `PAPER_TRADING_OPERATIONAL_CAPABILITY`
`NOT_PROVEN`, `PROSPECTIVE_PAPER_EDGE` `NOT_EVALUATED`, `FULL_TRADE_LIFECYCLE`
`NOT_ESTABLISHED_BY_AVAILABLE_EVIDENCE`, `MEASURABLE_POST_T0_EVIDENCE`
`UNAVAILABLE_IN_CURRENT_EVIDENCE_LANE`.

---

## Prerequisite order to Paper Beta

Ordered. Each item is a prerequisite of the next; none may be skipped, reordered
or run in parallel with an item it depends on. The order is a dependency
relationship, not a schedule and not a permission.

1. **Dataset V2 restoration**, against the existing frozen authority. The
   existing lock is the authority and is not rewritten, superseded or re-frozen.
2. **Native Ubuntu runtime qualification** — the required A-series gates, on this
   host, including those that need a running paper instance.
3. **Owner-authorized NEW T0 and cohort.** New `T0`, new `cohort_id` derived from
   it. Nothing from the closed cohort is carried forward.
4. **Forward paper cohort.**
5. **Evidence-based A15 closure** — closed on evidence its own run produced,
   never on recollection or on evidence that cannot be read.
6. **Operational hardening — backup and recovery.** The failure this project has
   already paid for: an evidence lane that existed only on one host.
7. **Paper Beta acceptance.**

### Dataset V2

Dataset V2 restoration remains **BLOCKED pending separate explicit Owner
authorization**. This document does not authorize download, restoration,
reacquisition, re-freeze, modification, or any other Dataset V2 action.

---

## Non-blocking engineering workstream

Claude Writer ↔ Codex Fresh Independent Verifier automation / conductor.

* It is **not** trading authority and never becomes one.
* It **must not reorder or block** any item of the prerequisite order above.
* One writer, a fresh independent verifier, fail closed, with a kill switch.
* CliDeck remains an **optional operator UI only**.

Nothing in this workstream is implemented by this document.

---

## Authority boundaries

```text
new T0                              OWNER ONLY
live trading / real money           OWNER ONLY
strategy or risk semantic expansion OWNER GATE
dataset authority                   CANNOT BE REWRITTEN
19d7d7e (strategy-source research)  PARKED until explicit research-opening authorization
```

`PAPER / RESEARCH ONLY`
`REAL_MONEY_AUTHORIZED = NO`
