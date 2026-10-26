# P3-PLN-10 — Paper Beta Acceptance Program (DRAFT, not executed)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-10, §5, §7 and §8 (frozen at fcd06b21), executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1).
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCH_AUTHORIZED = NO

**Contract acceptance:** every PLN-02 to PLN-09 acceptance holds in **one continuous Paper Beta run**, and the P&L
measurement reconciles to fills and fees. No real money.

**Status: DRAFT. PLN-10 = NOT STARTED and NOT ACCEPTED.** This document and `research/p3/acceptance.py` prepare the
program. Nothing here starts a cohort, sets a T0 or claims a result. The validators were developed against
synthetic evidence only.

## 1. Prerequisites. All must hold before the run starts
1. **PLN-02 to PLN-09 are each accepted** with their own evidence (contract §5: PLN-10 "needs PLN-02..PLN-09").
   - Today PLN-04 is PENDING (reboot), PLN-05 is NOT_PROVEN (Tier 3), PLN-06 is PARTIAL, and PLN-07 is PENDING (its reboot row).
   - PLN-09's Owner acceptance is PENDING.
2. **A paper runtime under its own authority.** The run needs a running paper cohort, and no cohort runs today.
   - **Which runtime is used is an OPEN Owner decision.** It could be H1 under its separate `H1_LAUNCH_AUTHORIZATION`, or another paper cohort under its own authority.
   - Do not restart FP-CONTROL-3 (`CLAUDE.md`).
   - This program never launches a runtime.
3. Host frozen at a recorded commit for the run. The PLN-11 execution pack inventory is taken at that commit.
4. The Owner fixes the run window, its duration and the kill-switch time bound, in writing, before T0.

## 2. Acceptance matrix
Each criterion in contract §3 is mapped to a scenario, the evidence it must produce, and the validator that judges
that evidence. The authoritative copy is `ACCEPTANCE_MATRIX` in `research/p3/acceptance.py`; this table is rendered
from it.

| Criterion id | WS | Criterion (contract §3) | Scenario | Evidence | Validator |
|---|---|---|---|---|---|
| `PLN-02.inventory_complete` | PLN-02 | the inventory lists 100% of tracked and untracked TLOS state | S-INV: state inventory at run start and run end | scripts/p3/state_inventory.py JSON: COVERAGE PASS, 0 unclassified, 0 unreadable | `status_pass` |
| `PLN-02.recovery_sources` | PLN-02 | each item has a verified recovery source | S-INV: recheck against the newest scheduled backup set | state inventory RECOVERY PASS on every declared root | `status_pass` |
| `PLN-03.restore_drill` | PLN-03 | restore drill passes: manifest sha256 equal, git fsck clean, ARCHIVE_VERIFIED, restored runtime starts in dry-run | S-RESTORE: drill from a set taken during the run, into an empty scratch | scripts/p3/backup.py drill --json: every check PASS | `status_pass` |
| `PLN-03.repeated_after_change` | PLN-03 | the drill is repeated after a change | S-RESTORE-2: second drill after any code/config change merged during the run | second drill JSON, newer set than the first | `status_pass` |
| `PLN-04.reboot_correct` | PLN-04 | after a reboot, the stack's state is correct | S-REBOOT: planned clean reboot during the run (runbook PLN_04_REBOOT_ACCEPTANCE_RUNBOOK.md) | verify-boot JSON PASS + clean-shutdown journal lines + health exit 0 | `status_pass` |
| `PLN-04.terminal_never_restarted` | PLN-04 | a terminal or Owner-stopped cohort is never auto-restarted (negative test) | S-RESTART: kill-switch stop, then reboot; the stopped runtime must stay stopped | restart_continuity record: stopped runtime stayed stopped; may-restart = NO | `restart_continuity` |
| `PLN-04.host_recovery_drill` | PLN-04 | a host-recovery drill from backup passes | S-RESTORE (shared with PLN-03) | drill JSON PASS | `status_pass` |
| `PLN-05.host_loss_redundancy` | PLN-05 | HOST_LOSS_REDUNDANCY = PROVEN by restoring from the independent host | S-TIER3: push + restore drill from the independent host (PLN_05_TIER3_PROCEDURE.md) | offsite push JSON destination_verify PASS + remote-restore drill JSON PASS | `status_pass` |
| `PLN-05.attributable_stop_start` | PLN-05 | every governed stop/start has an attributable record | S-KILL and every start during the run | operator ledger: chain verifies; one record per stop/start with operator and reason | `status_pass` |
| `PLN-06.s19_alerts` | PLN-06 | each §19 CRITICAL condition raises an alert in a test | S-ALERT: promtool rule tests + one delivered test alert on the chosen channel | promtool test rules SUCCESS + delivered-alert record (time, channel, alert name) | `status_pass` |
| `PLN-06.capacity_enforced` | PLN-06 | capacity thresholds are enforced | S-ALERT: health findings free_space:root / free_space:h1_lane at run start and end | health JSON with the thresholds applied | `status_pass` |
| `PLN-06.normal_end_detected` | PLN-06 | normal end is detected on lifecycle completion | S-END: the run's cohort completes its lifecycle | health finding normal_end WARNING 'governed stop due' raised at completion | `status_pass` |
| `PLN-07.matrix_rows` | PLN-07 | every failure/recovery matrix row has a passing test | S-CI: full suite at the run's frozen commit | CI run id + pytest exit 0 | `status_pass` |
| `PLN-07.f2_finding` | PLN-07 | F-2 has a reconcile finding with negative controls | S-AUDIT: execution audit over the run's fills | execution_audit JSON | `status_pass` |
| `PLN-07.data_truth` | PLN-07 | the data-truth checks pass | S-AUDIT: missing/duplicate candles recorded, never filled (§13) | data-truth report over the run's input ledger | `status_pass` |
| `PLN-08.kill_bounded` | PLN-08 | the kill switch stops everything within a bounded time and leaves an attributable record | S-KILL: engage the kill switch on the run's paper runtime | P3_KILL_SWITCH_V1 ledger record | `kill_switch_bounded` |
| `PLN-08.no_live_route` | PLN-08 | no control can set dry_run=false or reach a live route (guard test) | S-CI + S-ALERT: paper guard and real_money health findings throughout the run | paper_guard PASS + real_money INFO in every health run | `status_pass` |
| `PLN-09.projection` | PLN-09 | a Control Room projection over canonical evidence, Arabic/English, realising the frozen shape; the UI is never evidence authority | S-UI: Owner acceptance checklist on the host | signed Owner acceptance checklist (PLN-09) | `status_pass` |
| `PLN-10.pnl_reconciles` | PLN-10 | P&L measurement reconciles to fills and fees (measurement only) | S-PNL: every closed trade of the run | fills + fees + reported P&L records | `reconcile_pnl` |
`status_pass`: the scenario's own tool already decides PASS or FAIL. The PLN-10 record carries that status and the
sha256 of the tool's output.

## 3. Scenarios
All of these run inside the same run window, against the same paper runtime, with the code frozen at the run commit.

| Id | Scenario | Notes |
|---|---|---|
| S-INV | state inventory at the start and the end | PLN-02 tooling |
| S-RESTORE / S-RESTORE-2 | restore drill from a set taken during the run; repeated after any change | PLN-03 tooling, empty scratch |
| S-RESTART | kill-switch stop, then a restart or reboot; the stopped runtime must stay stopped until an attributable resume | PLN-04 guard `may-restart` |
| S-REBOOT | planned clean reboot per [`PLN_04_REBOOT_ACCEPTANCE_RUNBOOK.md`](PLN_04_REBOOT_ACCEPTANCE_RUNBOOK.md) | the baseline is taken at the run start |
| S-TIER3 | push and remote-restore drill per [`PLN_05_TIER3_PROCEDURE.md`](PLN_05_TIER3_PROCEDURE.md) | needs the Owner's independent host |
| S-ALERT | promtool tests, plus one delivered test alert, plus health findings throughout | needs node-exporter and a channel (PLN-06) |
| S-END | the cohort reaches its lifecycle end; `normal_end` is raised | — |
| S-KILL | the kill switch engaged on the running paper runtime | bound fixed by the Owner before T0 |
| S-AUDIT | execution audit (F-2/F-4) and data-truth report over the run's ledgers | §13: never fill gaps |
| S-CI | full suite and CI at the run commit | — |
| S-UI | the Owner walks the PLN-09 acceptance checklist on the host | — |
| S-PNL | net-of-fees P&L reconciliation for every closed trade | **measurement only** |

### S-PNL: net-of-fees reconciliation (measurement only)
For each closed trade, `reconcile_pnl` recomputes realised net quote from the trade's fills and fees, then compares
it with the reported value (default tolerance 1e-8 quote).

```text
gross    = Σ sell qty × price − Σ buy qty × price
net      = gross − quote fees − third-asset fees × the conversion price recorded at that fill   (e.g. BNB)
dust     = Σ buy qty − Σ sell qty − base-asset fees      (measured and reported, never hidden)
```

How each fee asset is handled:
- **Base-asset fees** are not deducted twice. They reduce the base held, and that loss is already inside the gross.
- **BNB fees** need a recorded conversion price. A BNB fee without one is a **FAIL**, never an estimate.

Each of these is a FAIL:
- a duplicate fill id (double execution);
- a reported trade with no fills;
- fills with no reported P&L;
- selling more than was bought.

This proves the measurement is truthful. **It says nothing about profitability** (contract §2, Priority 1).

## 4. Evidence schema
Every result is one `P3_PLN10_EVIDENCE_V1` JSON record (`EVIDENCE_SCHEMA` in `research/p3/acceptance.py`), with these fields:
- `run_id`
- `criterion_id`: one of the matrix ids
- `scenario`
- `utc`: ISO-8601 Z
- `status`: `PASS`, `FAIL` or `UNPROVEN`
- `artifacts`: at least one `{path, sha256}`
- `detail`: optional
- `real_money_authorized`: must be `false`

Additional properties are rejected. The records are stored under `p3-evidence/pln10/<run_id>/`, which the scheduled
backups pick up.

## 5. Verdict rule (fail-closed)
`run_verdict(records, run_id)` returns `CANDIDATE_FOR_OWNER_ACCEPTANCE` only when **every** matrix criterion has a valid
`PASS` record from **this** `run_id`. Otherwise it returns `NOT_ACCEPTED`, listing each unmet criterion and its state:
`MISSING`, `UNPROVEN` or `FAIL`.

- Evidence from another run never counts.
- Within a run, FAIL ranks above PASS, which ranks above UNPROVEN. A failure is never overwritten by a later pass. It is fixed under the contract and a new continuous run is required (§8: never waived).
- One malformed record blocks the verdict.
- The verdict is an input to the Owner. **PLN-10 is accepted only by the Owner's merged acceptance record.**

## 6. Stop and failure conditions during the run (contract §7)
Stop the run and return to the Owner if any of these happens:
- a safety gate fails: `paper_guard`, `real_money` or `unauthorized_execution` goes CRITICAL;
- evidence is found corrupt or unattributable: `evidence_chain:*` goes CRITICAL, or an unattributed stop or start occurs;
- a strategy, risk or dataset authority conflict appears;
- a destructive storage operation is needed;
- anything would touch real money.

These conditions stop the run, but are not, by themselves, an acceptance FAIL:
- the host being unavailable;
- the Owner aborting the run.

The run is recorded as `ABORTED`, never as PASS.

## 7. Open Owner decisions
1. Which paper runtime runs the acceptance (§1.2), and its authority.
2. Run window and duration.
3. Kill-switch time bound for `S-KILL`. PLN-08's drill measured 0.162 s; the bound is the Owner's choice.
4. Whether PLN-09 acceptance (the S-UI checklist) is done inside the run window or before it.

## 8. Not claimed
PLN-10 is not started and not accepted. No cohort or T0 exists, and no profitability claim is made.
