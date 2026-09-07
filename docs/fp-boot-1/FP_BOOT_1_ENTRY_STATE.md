# FP-BOOT-1 — entry-state determination

**Specification:** `TRADING_LAB_OS_FP_BOOT1_AND_FP_RUN_v1.1_FINAL_20260907.md`
**Determined in:** the cloud sandbox, from repository evidence only.
**Result:** `ENTRY_STATE = C` — no paper-admissible survivor exists.

## Why the stage cannot be activated for a candidate

Section 2 lists the inputs FP-BOOT-1 requires from the preceding benchmark
sprint. None of them exists in this repository, and the reason is not an
oversight: the sprint that produces them has been pre-registered but has not
been executed.

| Required input (section 2) | State in this repository |
| --- | --- |
| candidate/survivor registry | **pre-registered but unexecuted** — see "The sprint that is in flight" below |
| source/config/params hashes for a survivor | absent |
| measurement-validity verdict | absent — `research/records/` holds only `EXAMPLE_experiment_record.json` |
| candidate-quality verdict | absent |
| licensing/provenance status | absent |
| Dataset V2 / BASELINE-1 immutability proof | **`dataset_v2.lock.json` has `status = "pending_acquisition"` and zero fingerprinted files** |
| forward-paper admission recommendation | absent |
| no unresolved P0 validity defect | vacuous — there is no candidate to hold a defect |
| `REAL_MONEY_AUTHORIZED = NO` | satisfied, and unchanged by anything in this stage |

Two further facts settle it. `docs/cloud-0/CLOUD-0_CLOSURE.md` records, under
"What is explicitly NOT proven", that **no Freqtrade backtest, dry-run,
lookahead or recursive analysis has ever been executed** in this workspace. And
`BASELINE-1 — SIMPLE DETERMINISTIC ACTIVE BENCHMARK`, the stage `CLAUDE.md`
names as the successor to CLOUD-0, has not been run either: `BaselineEmaRegimeV1`
exists as source and as invariant tests, not as a result.

So the ordering the specification assumes —
`POST-BASELINE-EXTBENCH-1 → FP-BOOT-1 → FP-RUN` — is ahead of this repository by
two whole stages. Section 2 is explicit about what to do with that:

> If no candidate survives, do not invent one merely to populate FP-RUN.

## The sprint that is in flight

`POST-BASELINE-EXTBENCH-1` is not merely absent: it has been **specified and
pre-registered**, on the sibling branch `claude/new-session-140zbb`, and it has
**not been executed**. That distinction matters enough to record precisely,
because "the sprint has not run" and "no sprint work exists" are different
claims and only the first is true.

That branch carries `research/external/candidate_registry.json` with
`stage_label = "POST-BASELINE-EXTBENCH-1"`,
`frozen_before_any_candidate_result = true`, and its own activation gate:

> "1dfb69604bb87856b75c8c90957f2acc8e1fab7f must be an ancestor of main via a
> merge commit, with merged-main CI green" — status at freeze: **NOT MET**.
> "No candidate in this registry may be executed until the gate passes."

Its `research/external/qualification_scorecard.csv` is a header row and a
comment: *"columns pre-registered before any result exists; one row per
executable experiment"*. Its negative control is marked
`survivor_eligible = false`, and its Wave-2 candidate is
`survivor_eligible = "pending qualification"`.

This is **stronger** evidence for entry state C than an empty repository would
be. The sprint's own frozen registry states, from before any result existed,
that no candidate has been executed and none may be. There is therefore no
survivor to adopt, and section 3's STATE A ("survivor already running") does not
apply: no paper cohort was started early under the specification's
"start the clock early" rule, so there is no original `T0` to preserve.

Nothing in this stage touches that branch, its registry, or its pre-registered
scorecard columns.

## What state C authorises

Section 3, STATE C:

> Do not spend weeks in empty Forward Paper.
> Optional:
> - run BASELINE-1 control-only runtime hardening for a short bounded infrastructure check;
> - then start the next hypothesis/component R&D stage.
> Record: `PAPER_ALPHA_COHORT = NONE`

That is exactly the scope taken here, and no more. The evidence-lane machinery
FP-RUN will need is built and proven against synthetic data; no cohort is
started, no `T0` is created, and no candidate is admitted.

Recorded accordingly:

```text
PAPER_ALPHA_COHORT = NONE
FP_RUN_ACTIVE      = NO
FP_T0              = NONE
```

Section 3 also supplies the caveat that keeps this honest: **BASELINE-1 control
operation is not candidate-quality evidence.** Nothing built in this stage is a
claim about whether any strategy works.

## Admission verdict

`research/fp/admission.py` evaluates all fourteen section-5 conditions against
repository state and writes `research/fp/records/paper_candidate_admission.json`.

`PAPER_ADMISSION = BLOCKED`.

The evaluator fails closed in the strict sense: `ADMITTED` requires all fourteen
results to be `PASS`, and `UNPROVEN` blocks exactly as `FAIL` does. There is no
override flag, because an override flag is the failure mode the gate exists to
prevent.

## Preflight verdict

`research/fp/preflight.py` runs the twelve section-12 checks.

`PREFLIGHT = BLOCKED`, `T0_PERMITTED = NO`.

Checks 7, 8 and 11 — input ledger, decision ledger, event-time replay — are
*executed*, against a synthetic 600-candle sample, each with a negative control:
a tampered candle payload must break the ledger chain, an erratum must not
rewrite the record it corrects, and a single flipped decision must be caught by
replay. Checks 5, 10 and 12 need a running paper instance and a route to
Binance, neither of which exists here, and are reported `UNPROVEN` rather than
waved through.

---

# Change model after T0 (specification section 15)

Predeclared now, before any cohort exists, because a change model agreed after
the fact is worth nothing. Every post-`T0` change to a running instance is
classified as one of three kinds, and the class is recorded in that instance's
`change_log` in `forward_paper_cohort_registry.json`.

## O — OBSERVABILITY ONLY

Dashboards, metric labels, alert routing, log formatting. Decisions are
unchanged. The cohort continues; the change is recorded.

## R — RUNTIME REPAIR, SEMANTICS PRESERVED

Restart wrappers, database recovery tooling, network retry repair, metrics
sidecar repair. Requires before/after replay parity, a repair record, and no
change to signal or position semantics. Proven, the cohort may continue.

## S — SEMANTIC CHANGE

Strategy code, parameters, feature transformation, timeframe, pair or universe,
sizing, exit logic, order logic, or any fee/execution assumption used to make
decisions. Then:

```text
OLD_COHORT = CLOSED
```

and a new candidate version, new cohort and new `T0` begin. The evidence streams
are never spliced.

Section 28 follows from this and is restated so it cannot be mislaid: against a
running cohort, Hyperopt, EMA changes, added indicators, pair switching, exit
changes, sizing changes and retroactive filter changes are all forbidden. Any
semantic improvement is a new candidate, not an edit.

---

# Outage behaviour (specification section 17)

Predeclared, so that no future agent improvises it. BASELINE-1's only
decision-time input is the closed 1h OHLCV candle for its pair.

| Condition | Response |
| --- | --- |
| required candle missing or stale beyond one candle period | `NO_NEW_ENTRY` |
| duplicate, out-of-order or malformed candle | `NO_NEW_ENTRY`, incident recorded |
| exchange/local clock skew beyond one candle period | `INSTANCE_PAUSE` |
| repeated source failure across consecutive cycles | `INSTANCE_PAUSE` |

A required feature is **never** silently forward-filled beyond its declared
horizon. An open position is left to its frozen exit logic; `FORCED_EXIT` is not
used, because nothing in BASELINE-1's risk design justifies it.

---

`PAPER / RESEARCH ONLY`
`REAL_MONEY_AUTHORIZED = NO`
