# S9c — ACTIVATION OF FP-CONTROL-3, CERTIFIED

**Stage:** `P2 — PROSPECTIVE PAPER PROOF`, the contract §6 activation record.
**Authority:** [`P2_CONTRACT.md`](P2_CONTRACT.md). This record does not restate
it and does not extend it.

```text
T0              2026-09-24T12:00:00Z          immutable, never moved
cohort_id       FP-CONTROL-3-20260924T120000Z
ACTIVATION_UTC  2026-09-24T12:01:14Z          hard cap 2026-10-24T12:01:14Z
M1 (declared)   83c49414cc9eaba9a4e25809672d65d032669616   registry source_commit
M2 (stamped)    3191285a28823907f62c6eb915327599cd6ed90b   on every L2 record
Mq              909bf5fa551e9cb4351de6eb40cc42f9cbe28cbd   the qualification run

ACTIVATION_CERTIFIED = YES       validate_activation 10/10, exit 0
PAPER / RESEARCH ONLY            REAL_MONEY_AUTHORIZED = NO
PROSPECTIVE_PAPER_EDGE = NOT_EVALUATED
```

This is the first activation in this project's history that its own validator
certifies. [`S6_ACTIVATION.md`](S6_ACTIVATION.md) recorded why the previous one
could not be, and that record stands unchanged: it is history, and the defects
it named are the reason this one passes.

---

## 1. What happened

A host-level `systemd --user` one-shot fired at `2026-09-24T12:01:00Z`, inside
the lawful window `[T0, T0 + one candle period)`. It re-verified every
precondition and then started the cohort through `scripts/start_fp_control.sh`
— no manual Docker, no alternate launcher.

```text
TLOS P2 ACTIVATION — FP-CONTROL-3 — 2026-09-24T12:01:00Z
  [ok] window: T0+60s, inside [T0, T0+3600s)
  [ok] pinned at M2 3191285a28823907f62c6eb915327599cd6ed90b, tree clean
  [ok] lane empty, no capture lock, no containers
  [ok] registry lawful; role/cohort/T0 agree; strategy+config match the frozen identity
  [ok] PAPER_GUARD_PASS
  [ok] DATASET_LOCK_GATE = PASS
starting the governed runtime...
Started FP-CONTROL-3 (dry_run=true, paper only).
ACTIVATION_START_ISSUED 2026-09-24T12:01:05Z
```

The same guard had been run once **before** T0, at `11:06:58Z`, and refused:
`ACTIVATION_REFUSED: before T0 (2026-09-24T12:00:00Z); activation may not
precede the boundary`, exit 2, lane still empty and no container created. A
mechanism that has only ever been seen to succeed has not been shown to refuse.

## 2. The ten checks

```text
 1 single fresh run            exactly one run_started, restart_counter 0
 2 chains verify, no erratum   four chains from genesis over 3997 records
 3 one identity throughout     role FP-CONTROL-3, cohort …20260924T120000Z,
                               the single source commit 3191285a
 4 lane was fresh              no record reads T0_NOT_FROZEN
 5 warm-up never executable    no decision is both PRE_T0 and LIVE
 6 first credited bar          the bar closing 2026-09-24T12:00:00Z — the first
                               1h boundary at or after T0
 7 reconciliation              RECONCILIATION = PASS
 8 preflight                   PREFLIGHT = PASS (16/16)
 9 activation gap recorded     no bar closed after T0 unobserved; the absence of
                               an incident is the correct evidence
10 activation within bound     started 65s after T0, within one 1h period (3600s)

ACTIVATION = PASS       exit 0
```

Reconciliation is complete as well as passing: all fourteen expected findings
are present, none missing and none unexpected.

```text
ledger_chain_integrity · record_role_binding · record_attribution ·
record_source_commit · registry_source_commit_equivalence · input_uniqueness ·
decision_uniqueness · decision_input_linkage · decision_causality ·
event_time_replay · execution_backed_by_decision · no_duplicate_execution ·
restart_continuity · paper_only_authority
```

At the moment of validation:

```text
counts        input 1998 · decision 1998 · trade 0 · incident 1 · runs 1
the incident  seq 0, run_started, restart_counter=0 — the only one
crediting     2 POST_T0 + LIVE · 1996 PRE_T0 + WARMUP · 0 POST_T0 + WARMUP
gap bars      0
trade tip     0000…0000, an empty chain, as it must be before any trade
daily pack    0aa46a30e638702a863408a3802f3459dd7abf8aaba7671353bbdc377ccb83d2
```

Zero gap bars is the fact check 10's bound exists to make visible. The runtime
started 65 s after T0 and the first decided bar is the one that closed *at* T0,
so no bar that should have been observed live was recovered by backfill instead.

## 3. Why this activation could be certified and the last one could not

`S6_ACTIVATION.md` §4 named two defects. Neither was argued away; both were
repaired in the recovery transaction, and this run is the measurement.

```text
4.1  check 1 and preflight check 16 could not both hold on one lane
     → RuntimeContext.lifecycle: INITIAL_ACTIVATION asserts EXACTLY one run,
       PRE_T0_QUALIFICATION still demands the second. Check 1 PASS and check 8
       PREFLIGHT = PASS (16/16) now hold together, on the same lane, measured.
4.2  the validator could not attach the runtime it validates
     → Attachment. Four preflight checks that answered UNPROVEN now answer.
```

The repairs were merged **before** this cohort's T0, which is the only order
§5's equivalence law permits: a defect in `RUNTIME_TREE` is unfixable for the
whole life of a cohort frozen against it.

## 4. The window law

```text
T0_UTC          2026-09-24T12:00:00Z    the crediting boundary, immutable
ACTIVATION_UTC  2026-09-24T12:01:14Z    the active-window clock — the decision
                                        timestamp of the first lawful
                                        POST_T0 + LIVE record, so re-running the
                                        validator later reports the same instant
HARD CAP        2026-10-24T12:01:14Z    ACTIVATION_UTC + 30 days, no automatic
                                        extension
state           OPEN
```

Normal end is the first naturally completed full paper trade lifecycle **and**
all twelve capability properties **and** reconciliation, evidence and safety
PASS. Reaching the cap without a natural lifecycle is lawful and closes as
`P2 INCONCLUSIVE / INSUFFICIENT`. Nothing may be done to make the window end —
no artificial trade, no threshold change, no forced entry or exit, no strategy
modification.

Capability stands at **nine of twelve**: the nine pre-T0 properties from the
Mq qualification, and the three lifecycle properties — paper order/fill,
position state, no duplicate execution — still unevidenced, because no trade has
occurred. `full_trade_lifecycle` is reported beside the twelve and is never
counted among them.

```text
paper_trading_operational_capability = NOT_PROVEN   (9/12, three await a trade)
full_trade_lifecycle                 = NOT_YET_OBSERVED
prospective_paper_edge               = NOT_EVALUATED
measurable_post_t0_evidence          = AVAILABLE
```

## 5. Exactly one activation path

The FP-CONTROL-2 mechanism was retired before the successor's was built, so the
two never coexisted.

```text
REMOVED    ~/.config/systemd/user/tlos-p2-activate.{timer,service}
           disabled, unlinked from timers.target.wants, deleted, daemon reloaded
RETIRED    ~/.local/share/tlos-p2/activate_guarded.sh  → superseded/, non-executable
           it named ROLE=FP-CONTROL-2, M2=0e920db6, T0=2026-09-20T12:00:00Z
CREATED    ~/.local/share/tlos-p2/activate_fp_control_3.sh
           tlos-p2-activate-fp-control-3.{timer,service}, OnCalendar 12:01:00 UTC,
           no Persistent, RemainAfterElapse=no — one shot, and it has now elapsed
```

Proved by enumeration before arming and again after: no other user unit, system
unit, `/etc/cron.d` entry, user crontab, or executable host script referenced
this project, and no container existed. All of this is host state; none of it is
tracked, and none of it is authority.

## 6. Two observations recorded rather than acted on

**The dataset.** `scripts/audit_data.py --gate lock` reports
`DATASET_LOCK_GATE = PASS (content matches the frozen lock)`, which is §9's
precondition, and it is what the guard required. The stricter `full` gate reports
`DATA_INTEGRITY_GATE = FAIL` on the exact 5m→1h cross-timeframe reconciliation
over the multi-year mirror. Since the lock gate is `structural_pass` **and** no
lock drift, structural soundness and lock identity both hold. The mirror files
are unchanged since 2026-09-14, so this is the identical dataset state under
which FP-CONTROL-2 ran and under which the Mq qualification passed 16/16. It is
neither new nor caused by anything here. Dataset authority is the Owner's, so it
is recorded and nothing is changed.

**The second device.** `scripts/second_device_discovery.py` now reports
`status = UNAVAILABLE`, `SAME_HOST_SECOND_DEVICE = NO`, no candidates,
`blocks_t0 = false`. §8 requires the second device *when available and healthy*
and §9 excludes it from the T0 preconditions, so the cohort proceeds on Tier 1
and Tier 2, which are unconditional. §10 is explicit that an unavailable second
device is not a return.

```text
SAME_HOST_SECOND_DEVICE = NO
HOST_LOSS_REDUNDANCY    = NOT_PROVEN
```

## 7. What this change does not do

```text
no T0 moved · no cohort created · no lane reused · no sealed evidence credited
no strategy, risk, Dataset, admission, qualification or authorization change
no runtime semantic change — nothing here touches RUNTIME_TREE, so this branch
  is EQUIVALENT to the declared M1 and the cohort's evidence stays attributable
the runtime was not stopped and the cohort was not restarted for this record
the pinned M2 checkout is untouched; this work is from the control worktree
no replacement budget is requested; the one granted is consumed by this cohort
P3 is not started and is not authorized
```

```text
PAPER / RESEARCH ONLY
REAL_MONEY_AUTHORIZED = NO
PROSPECTIVE_PAPER_EDGE = NOT_EVALUATED
```
