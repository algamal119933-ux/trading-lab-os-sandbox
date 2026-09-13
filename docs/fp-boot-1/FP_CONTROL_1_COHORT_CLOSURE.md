# FP-CONTROL-1 — cohort closure record

**Cohort:** `FP-CONTROL-1-20260908T121513Z`
**T0 (frozen, preserved as history):** `2026-09-08T12:15:13Z`
**Closed:** `2026-09-13T20:58:24Z`
**Closure reason:** `EVIDENCE_LANE_LOST_IN_HOST_MIGRATION`
**Owner decision:** PATH 2 — terminate, do not continue, do not reconstruct.

```text
PAPER_TRADING_OPERATIONAL_CAPABILITY = NOT_PROVEN
FULL_TRADE_LIFECYCLE                 = NOT_OBSERVED
PROSPECTIVE_PAPER_EDGE               = NOT_EVALUATED_BY_FP_CONTROL_1
MEASURABLE_POST_T0_EVIDENCE          = NONE
REAL_MONEY_AUTHORIZED                = NO
```

This cohort establishes nothing. It is recorded so that the window it occupied
cannot later be read as evidence, and so that the T0 it consumed is visibly
spent rather than silently available for reuse.

## What happened

FP-CONTROL-1 was activated on the prior host on 2026-09-08 after a passing
pre-T0 gate (commit `6d5d27c`, merged as `d001dfb`): preflight 16/16 PASS with
`--require-pass` exit 0, entry state C, admission BLOCKED with no candidate
admitted, reconciliation PASS over 1998 real captured candles, dataset lock gate
PASS, canonical cache unmutated, clock skew within tolerance, clean worktree.

The project then moved to a native Ubuntu host. The move was made with a **git
bundle** (`git clone` from `trading-lab-os.bundle`), which carries committed
history and nothing else. Everything the FP protocol deliberately keeps out of
Git stayed behind:

| Lost | Why it was not in Git |
| --- | --- |
| `freqtrade/user_data/fp-control-1/evidence/` — input, decision, trade and incident ledgers | `.gitignore` §29-34: the live evidence lane is append-only and would keep the worktree permanently dirty, tripping stop condition S2 |
| `freqtrade/user_data/fp-control-1/tradesv3.sqlite`, `logs/` | same |
| `artifacts/fp_preflight.json`, `artifacts/fp_admission.json` | `.gitignore` §55-65: host-run evidence, published deliberately at closure |
| `dataset-cache/binance/*.feather`, `freqtrade/user_data/data/` | market data is never committed (CLOUD-0 C0.7) |
| Docker volumes for freqtrade, capture, exporter, Prometheus, Grafana, MLflow | runtime state |

The Owner has confirmed the prior host will not be used again. The evidence lane
is therefore unrecoverable, not merely absent.

## Why the cohort could not be continued

Continuing would have required classifying the migration as a class **R** change
— runtime repair, semantics preserved — and section 15 requires R to carry
**before/after replay parity**. Parity is computed against the ledgers that this
closure exists because we no longer have. There is no lawful way to prove that
the instance which would start on Ubuntu is a continuation of the instance that
ran on the prior host, and an unprovable continuation asserted anyway is exactly
the defect the change model exists to catch.

Nor could the gap be characterised. Between T0 and this closure the cohort was
registered `RUNNING` for 5 days 8 hours while no capture process existed for an
unknown part of that span. The incident ledger that would record an outage is
itself lost, so an unrecorded gap is indistinguishable from an undetected one.

## Why the closure is classified S

The change log entry carries class `S`, and that needs stating plainly because
the class description does not fit on its face: **no trading semantics were
changed.** The strategy, configuration, sizing, pair universe and timeframe are
untouched and remain byte-identical to their frozen hashes.

`S` is used because `S` is the class whose *consequence* this is — the evidence
stream ends here and may never be spliced to another, and a future run is a new
cohort with a new T0. `R` was not available for the reason above, and `O`
(observability only) would have been false: an observability change leaves a
cohort collecting evidence, and this one stops.

The vocabulary was not extended to invent a fourth class. The reasoning is
recorded here instead of being resolved silently.

## What is preserved, and what is forbidden

`t0_utc`, `cohort_id` and `runtime_identity.source_commit` are left exactly as
they were frozen. They are history:

```text
NEVER reuse  NEVER rewrite  NEVER move  NEVER back-date
```

A future forward-paper run is a **new cohort**, requiring:

1. a full host-side pre-T0 pass on the new host (activation pack A1-A13),
2. `preflight.py --require-pass` exit 0 on this host's runtime,
3. a new Owner authorisation, and
4. a new `T0` and a new `cohort_id` derived from it.

Nothing from the closed window may be carried into that cohort — no ledger, no
warm-up state, no partial result, no elapsed-time credit.

## Machine-readable record

`research/fp/records/forward_paper_cohort_registry.json`: instance status
`CLOSED`, `closed_utc`, `closure_reason` and `outcome` as above,
`fp_run_active` false, `paper_alpha_cohort` `NONE`, `entry_state` `C`,
`real_money_authorized` false.

The registry schema gained an optional `outcome` object for this purpose: a
closed cohort must be able to state, in machine-readable form, what it did and
did not establish. Invariants for a closed row are asserted in
`tests/test_fp_admission.py`.

## Unchanged by this closure

```text
ENTRY_STATE           = C            (no paper-admissible survivor exists)
PAPER_ALPHA_COHORT    = NONE
PAPER_ADMISSION       = BLOCKED
BASELINE-1            = closed; Development PASS/NEUTRAL, Validation spent
Dataset V2            = frozen by research/datasets/dataset_v2.lock.json;
                        NOT re-acquired and NOT re-frozen by this work
REAL_MONEY_AUTHORIZED = NO
```
