# P3-PLN-10 — Paper Beta Acceptance Program (DRAFT, not executed)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-10, §5, §7 and §8 (frozen at fcd06b21), executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1).
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCH_AUTHORIZED = NO · PAPER_LAUNCH_AUTHORIZED = NO

**Contract acceptance:** every PLN-02 to PLN-09 acceptance holds in **one continuous Paper Beta run**, and the P&L
measurement reconciles to fills and fees. No real money.

**Status: DRAFT. PLN-10 = NOT STARTED and NOT ACCEPTED.** This document and `research/p3/acceptance.py` prepare the
program. Nothing here starts a runtime, sets a T0 or claims a result. The validators were developed against
synthetic evidence only. Reconciled with main `f584cd43` (PRs #88, #89, #92 and #94 merged).

**Reuse, not re-specification.** Each workstream's procedure and pass rule already live in its own merged record
(runbook, checklist or execution record). This program does not restate them. For every criterion the matrix names:
- the **procedure** that the in-run scenario re-executes, unchanged; and
- the **standalone record** that holds the workstream's own acceptance.

A standalone acceptance is a **prerequisite** (§1). It never replaces the in-run record, because the contract requires
every acceptance to hold in the same continuous run. Nothing is waived.

## 1. Prerequisites. All must hold before T0
1. **PLN-02 to PLN-09 are each accepted by their own merged record** (contract §5: PLN-10 "needs PLN-02..PLN-09").
   State on main `f584cd43`, from `research/p3/records/p3_workstreams.json`:

   | WS | State | What is still open |
   |---|---|---|
   | PLN-02 | ACCEPTED | — |
   | PLN-03 | ACCEPTED | — |
   | PLN-04 | PARTIAL | Reboot correctness **PASS** ([`PLN_04_RECOVERY.md`](PLN_04_RECOVERY.md) reboot record, RUN 3 10/10 with a clean gap attestation, accepted by the merge of PR #94). Open: the power-loss posture (UPS or an accepted posture), an Owner decision |
   | PLN-05 | PARTIAL | HOST_LOSS_REDUNDANCY = NOT_PROVEN. Needs the independent host and the [`PLN_05_TIER3_PROCEDURE.md`](PLN_05_TIER3_PROCEDURE.md) run |
   | PLN-06 | PARTIAL | The delivery runbook is merged ([`PLN_06_ALERTING.md`](PLN_06_ALERTING.md) §3, PR #92). The Owner steps 1–8 are pending. The unexpected-writer row is NOT_COVERED |
   | PLN-07 | PARTIAL | Failure/recovery matrix PASS for every row, including the reboot row (#94). Open: the §13 data-truth evidence |
   | PLN-08 | ACCEPTED | — |
   | PLN-09 | IN_PROGRESS | 12 of 12 screens and the mobile tabs are bound. The Owner walkthrough ([`PLN_09_OWNER_ACCEPTANCE_CHECKLIST.md`](PLN_09_OWNER_ACCEPTANCE_CHECKLIST.md) §6) is PENDING |
2. **A complete run configuration** (§8). All five Owner decisions are set in `docs/p3/PLN_10_RUN_CONFIG.json`, by the
   Owner's own PR, and `launch_readiness` returns `CONFIG_COMPLETE_FOR_OWNER_LAUNCH`. Today the file does not exist,
   so the program is `LAUNCH_BLOCKED` on D1–D5.
3. **The host is frozen** at the configuration's `frozen_commit` for the whole window:
   - `tlos-p3` is at that commit;
   - the host-freeze rules of [`PLN_04_RECOVERY.md`](PLN_04_RECOVERY.md) ("Host-freeze lift conditions") apply;
   - the Owner's unattended-upgrades decision (the same record, decision packet item H) is in force for the window.
4. Storage headroom for the window is checked by the health check's `free_space:*` findings at INFO (contract §6).

## 2. Acceptance matrix
The authoritative copy is `ACCEPTANCE_MATRIX` in `research/p3/acceptance.py`. Its canonical sha256 (`matrix_digest()`)
is pinned by the run configuration (D4), so a criterion cannot change silently.

The **criterion id is the evidence ID**. The evidence records (§4) and the PLN-11 execution pack's evidence index
use the same ids.

| Evidence id | Scenario | Procedure (re-executed in the window) | Standalone record (prerequisite) | Validator |
|---|---|---|---|---|
| `PLN-02.inventory_complete` | S-INV | `PLN_02_STATE_INVENTORY.md` §Verdict (COVERAGE) | `PLN_02_STATE_INVENTORY.md` §Acceptance update (PASS, 14 roots) | `status_pass` |
| `PLN-02.recovery_sources` | S-INV | `PLN_02_STATE_INVENTORY.md` §Verdict (RECOVERY) | `PLN_02_STATE_INVENTORY.md` §Acceptance update (PASS, 14 roots) | `status_pass` |
| `PLN-03.restore_drill` | S-RESTORE | `PLN_03_BACKUP_RESTORE.md` §Scheduled acceptance (verify + drill) | same record, PASS (set 20261025T211956Z) | `status_pass` |
| `PLN-03.repeated_after_change` | S-RESTORE-2 | `PLN_03_BACKUP_RESTORE.md` §Scheduled acceptance | same record, §Acceptance update (second set) | `status_pass` |
| `PLN-04.reboot_correct` | S-REBOOT | `PLN_04_REBOOT_ACCEPTANCE_RUNBOOK.md` §1–§4, record per §7 | `PLN_04_RECOVERY.md` §Reboot record (RUN 3 PASS, #94) | `status_pass` |
| `PLN-04.terminal_never_restarted` | S-RESTART | `PLN_04_RECOVERY.md` §Acceptance status (terminal-state guard) | same, PASS | `restart_continuity` |
| `PLN-04.host_recovery_drill` | S-RESTORE | `PLN_03_BACKUP_RESTORE.md` §Scheduled acceptance (one drill, cited twice) | `PLN_04_RECOVERY.md` §Acceptance status, PASS | `status_pass` |
| `PLN-05.host_loss_redundancy` | S-TIER3 | `PLN_05_TIER3_PROCEDURE.md` §5–§6, record per §8 | NONE (NOT_PROVEN) | `status_pass` |
| `PLN-05.attributable_stop_start` | S-KILL + every start | `PLN_06_07_08_OPERATIONS.md` §PLN-08 (operator ledger) | `PLN_05_EVIDENCE_DURABILITY.md` §Acceptance status, PASS | `status_pass` |
| `PLN-06.s19_alerts` | S-ALERT | `PLN_06_ALERTING.md` §3 steps 6–8 (PASS/FAIL table) and §4 | NONE (PLN-06 PARTIAL, delivery PENDING) | `status_pass` |
| `PLN-06.capacity_enforced` | S-ALERT | `PLN_06_ALERTING.md` §4 (capacity row) | same, rule leg PASS in test | `status_pass` |
| `PLN-06.normal_end_detected` | S-END | `PLN_06_ALERTING.md` §4 (normal-end row) | same, detection met | `status_pass` |
| `PLN-07.matrix_rows` | S-CI | `PLN_04_RECOVERY.md` §PLN-07 failure/recovery matrix | same, PASS for every row (#94) | `status_pass` |
| `PLN-07.f2_finding` | S-AUDIT | `PLN_06_07_08_OPERATIONS.md` §PLN-07 (per-execution audit) | same, F-2 finding on the sealed P2 archive | `status_pass` |
| `PLN-07.data_truth` | S-AUDIT | `P3_CONTRACT.md` §4 (data truth, master plan §13) | NONE (open on main) | `status_pass` |
| `PLN-08.kill_bounded` | S-KILL | `PLN_06_07_08_OPERATIONS.md` §PLN-08 (kill switch) | same, PASS (drill 0.162 s) | `kill_switch_bounded` |
| `PLN-08.no_live_route` | S-CI + S-ALERT | `PLN_06_07_08_OPERATIONS.md` §PLN-08 (guard) | same, PASS | `status_pass` |
| `PLN-09.projection` | S-UI | `PLN_09_OWNER_ACCEPTANCE_CHECKLIST.md` §2–§4, sign-off block §6 | NONE (PENDING) | `status_pass` |
| `PLN-10.pnl_reconciles` | S-PNL | this program §3 S-PNL | NONE (measured only in the run) | `reconcile_pnl` |

Each row also names its **owner** and its **stop condition** (§2a).

`status_pass`: the procedure's own tool or checklist already decides PASS or FAIL. The PLN-10 record carries that
status and the sha256 of the tool's output. A test checks that every cited document exists on the branch.

### 2a. Who performs each step, and when it stops
`owner` is who performs the step inside the window (Claude always writes the evidence record; acceptance is always
the Owner's merged record). `stop_condition` says when the step stops the run (§9) or records FAIL / UNPROVEN (§10).
Both are fields of `ACCEPTANCE_MATRIX`; `matrix_completeness` refuses a row without them.

| Evidence id | Owner | Source procedure | Stop condition |
|---|---|---|---|
| `PLN-02.inventory_complete` | Claude | docs/p3/PLN_02_STATE_INVENTORY.md §Verdict (COVERAGE) | the inventory cannot run, or finds an unlisted TLOS state root: FAIL for this run (§10); unattributable state stops the run (§9) |
| `PLN-02.recovery_sources` | Claude | docs/p3/PLN_02_STATE_INVENTORY.md §Verdict (RECOVERY) | an item has no verified recovery source in a set written inside the window: FAIL for this run (§10) |
| `PLN-03.restore_drill` | Claude | docs/p3/PLN_03_BACKUP_RESTORE.md §Scheduled acceptance (verify + drill) | the drill reports FAIL, or a restore would touch live state: FAIL (§10); a restore over live state is never run (§9 destructive storage operation) |
| `PLN-03.repeated_after_change` | Claude | docs/p3/PLN_03_BACKUP_RESTORE.md §Scheduled acceptance (verify + drill) | a change merged in the window without a second PASS drill on a newer set: criterion unmet (§10) |
| `PLN-04.reboot_correct` | Owner + Claude | docs/p3/PLN_04_REBOOT_ACCEPTANCE_RUNBOOK.md §1-§4 (record per §7) | verify-boot reports any FAIL or the gap attestation is not clean: FAIL (§10); a host change outside the frozen state stops the run (§9) |
| `PLN-04.terminal_never_restarted` | Owner + Claude | docs/p3/PLN_04_RECOVERY.md §Acceptance status (terminal-state guard) | a stopped runtime comes back without an attributable resume: stop the run with the kill switch (§9) and record FAIL (§10) |
| `PLN-04.host_recovery_drill` | Claude | docs/p3/PLN_03_BACKUP_RESTORE.md §Scheduled acceptance (verify + drill) | the shared S-RESTORE drill is not PASS: FAIL (§10) |
| `PLN-05.host_loss_redundancy` | Owner + Claude | docs/p3/PLN_05_TIER3_PROCEDURE.md §5-§6 (record per §8) | no independent host, or the remote restore is not PASS: UNPROVEN or FAIL, never PASS (§10) |
| `PLN-05.attributable_stop_start` | Owner + Claude | docs/p3/PLN_06_07_08_OPERATIONS.md §PLN-08 (operator ledger, --verify-ledger) | a stop or start without an attributable ledger record, or a broken chain: stop the run (§9 evidence unattributable) |
| `PLN-06.s19_alerts` | Owner + Claude | docs/p3/PLN_06_ALERTING.md §3 (steps 6-8, PASS/FAIL table) and §4 | a §19 condition without a delivered alert: FAIL (§10); any §19 CRITICAL raised for real stops the run (§9) |
| `PLN-06.capacity_enforced` | Claude | docs/p3/PLN_06_ALERTING.md §4 (capacity row) | a free_space finding below INFO at run start: no T0; during the window: stop the run before storage runs out (§9) |
| `PLN-06.normal_end_detected` | Claude | docs/p3/PLN_06_ALERTING.md §4 (normal-end row) | the lifecycle ends without a normal_end finding: FAIL (§10) |
| `PLN-07.matrix_rows` | Claude | docs/p3/PLN_04_RECOVERY.md §PLN-07 failure/recovery matrix | any test of the failure/recovery matrix fails at frozen_commit: FAIL (§10) |
| `PLN-07.f2_finding` | Claude | docs/p3/PLN_06_07_08_OPERATIONS.md §PLN-07 (per-execution audit) | an execution not backed by an admitted decision is unexplained: FAIL (§10); a live route stops the run (§9) |
| `PLN-07.data_truth` | Claude | docs/p3/P3_CONTRACT.md §4 (Data truth, master plan §13) | a missing or duplicate candle is filled or hidden: FAIL (§10); a dataset authority conflict stops the run (§9) |
| `PLN-08.kill_bounded` | Owner + Claude | docs/p3/PLN_06_07_08_OPERATIONS.md §PLN-08 (kill switch) | the stop exceeds the D3 bound, is not attributable, or leaves a runtime running: FAIL (§10) and a §9 stop by any bounded means |
| `PLN-08.no_live_route` | Claude | docs/p3/PLN_06_07_08_OPERATIONS.md §PLN-08 (guard) | paper_guard or real_money goes CRITICAL, or dry_run is not true: stop the run at once (§9) |
| `PLN-09.projection` | Owner | docs/p3/PLN_09_OWNER_ACCEPTANCE_CHECKLIST.md §2-§4 (sign-off block §6) | a walkthrough step reads FAIL: record it under FINDINGS; it is never waived (§10) |
| `PLN-10.pnl_reconciles` | Claude | docs/p3/PLN_10_PAPER_BETA_ACCEPTANCE_PROGRAM.md §3 S-PNL | any closed trade does not reconcile within the D4 tolerance: FAIL (§10); never re-measured to fit |

## 3. Scenarios
All of these run inside the same window, against the same paper runtime, with the code frozen at `frozen_commit`.

| Id | Scenario | Notes |
|---|---|---|
| S-INV | state inventory at the start and the end | PLN-02 tooling |
| S-RESTORE / S-RESTORE-2 | restore drill from a set taken during the run; repeated after any change | PLN-03 tooling, empty scratch |
| S-KILL | the kill switch engaged on the running paper runtime | bound = D3 |
| S-RESTART | after S-KILL, a reboot or restart; the stopped runtime must stay stopped until an attributable resume | PLN-04 guard `may-restart` |
| S-REBOOT | planned clean reboot per [`PLN_04_REBOOT_ACCEPTANCE_RUNBOOK.md`](PLN_04_REBOOT_ACCEPTANCE_RUNBOOK.md) | baseline taken at run start; may be the same reboot as S-RESTART |
| S-TIER3 | push and remote-restore drill per [`PLN_05_TIER3_PROCEDURE.md`](PLN_05_TIER3_PROCEDURE.md) | needs the Owner's independent host |
| S-ALERT | [`PLN_06_ALERTING.md`](PLN_06_ALERTING.md) §3 steps 6–8, plus health findings throughout | needs the PLN-06 Owner install |
| S-END | the runtime reaches its lifecycle end; `normal_end` is raised | — |
| S-AUDIT | execution audit (F-2/F-4) and data-truth report over the run's ledgers | §13: never fill gaps |
| S-CI | full suite and CI at `frozen_commit` | — |
| S-UI | the Owner re-walks the PLN-09 checklist inside the window and fills its §6 block with the `run_id` | — |
| S-PNL | net-of-fees P&L reconciliation for every closed trade | **measurement only** |

### S-PNL: net-of-fees reconciliation (measurement only)
For each closed trade, `reconcile_pnl` recomputes realised net quote from the trade's fills and fees, then compares
it with the reported value. The tolerance is **not a default**: it is `acceptance_criteria.pnl_tolerance_quote` from
the run configuration (D4), passed explicitly. A call without it is refused.

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

Also a FAIL, never a silently signed number: a side other than `buy` / `sell`, a quantity or price that is not a
finite positive number, a negative or non-finite fee, or a non-finite reported net.

This proves the measurement is truthful. **It says nothing about profitability** (contract §2, Priority 1).

## 4. Evidence requirements
Every result is one `P3_PLN10_EVIDENCE_V1` JSON record (`EVIDENCE_SCHEMA` in `research/p3/acceptance.py`):
- `run_id`: the run configuration's `run_id`;
- `criterion_id`: the evidence id, one of the matrix ids;
- `scenario`;
- `utc`: ISO-8601 Z, inside the trial window;
- `status`: `PASS`, `FAIL` or `UNPROVEN`;
- `artifacts`: at least one `{path, sha256}`. Each is the output that the row's **procedure** already defines (its
  JSON, its evidence directory listing or its filled template). This program adds no new artifact format;
- `detail`: optional;
- `real_money_authorized`: must be `false`.

Additional properties are rejected. The records are stored under `p3-evidence/pln10/<run_id>/`, which the scheduled
backups pick up. A record is never edited: a correction is a new record, and a FAIL stays (§5).

Evidence labels in the acceptance record follow the lane rules: CLAUDE-VERIFIED, OWNER-REPORTED, OWNER-ATTACHED,
NOT_RUN or UNPROVEN. An OWNER-REPORTED value counts only once the Owner attaches the output it reports.

## 5. Verdict rule (fail-closed)
`run_verdict(records, config=…)` takes the run configuration as a **required** argument. It returns
`CANDIDATE_FOR_OWNER_ACCEPTANCE` only when the configuration is complete (§8) **and** every matrix criterion has a
valid `PASS` record from that configuration's `run_id`. Otherwise it returns `NOT_ACCEPTED`, listing each unmet
criterion and its state (`MISSING`, `UNPROVEN` or `FAIL`) and each configuration blocker.

- Evidence from another run never counts.
- A record whose `utc` lies outside the configuration's trial window (`start_utc` to `start_utc + duration_hours`,
  D2) never counts and is listed as a problem: the contract asks for one continuous run.
- Within a run, FAIL ranks above PASS, which ranks above UNPROVEN. A failure is never overwritten by a later pass.
- One malformed record blocks the verdict.
- The verdict is an input to the Owner. **PLN-10 is accepted only by the Owner's merged acceptance record.**

## 6. Safety boundaries (hold for the whole program)
- PAPER only: `dry_run` stays literally `true`, and `real_money_authorized` literally `false`, in the configuration
  and in every record. No private exchange key, no withdrawal, no leverage, margin, futures or shorts (`CLAUDE.md`).
- `paper_guard` and the §19 health checks stay on. They are never weakened or silenced to finish a run.
- No strategy, risk or dataset change. The runtime's governed limits stay as its own authority defines them.
- FP-CONTROL-3 is never restarted. An H1 runtime runs only under its own `H1_LAUNCH_AUTHORIZATION`; this program
  grants neither H1 nor any other launch.
- The runtime must be inside the kill switch's scope (`kill_switch.PAPER_RUNTIME_PATTERNS`), so S-KILL can stop it.
- Every host change outside the frozen state needs its own explicit Owner authorization
  ([`PLN_04_RECOVERY.md`](PLN_04_RECOVERY.md), "Host-freeze lift conditions").
- The Control Room is a read-only projection and never evidence authority (§23).
- No new engine, database, control plane or monitoring platform (§10).

## 7. Operator procedure
**Phase 0 — repository (now).** This DRAFT and its validators. Nothing on the host.

**Phase A — before T0 (Owner).**
1. Confirm each §1 prerequisite by its own merged record.
2. Merge `docs/p3/PLN_10_RUN_CONFIG.json` with D1–D5 set (§8). CI must show `validate_run_config` = [] for it.
3. Freeze the host at `frozen_commit` (§1.3). Take the PLN-04 runbook §1 baseline. Run `paper_guard` and the health
   check: both must be clean.

**Phase B — T0 (Owner).** The runtime is launched by the Owner under the authority record that D5 cites, following
that runtime's own launch procedure. This program never launches anything.

**Phase C — inside the window.** Each step writes one evidence record (§4).
1. S-INV (start), S-ALERT (PLN-06 §3 steps 6–8), S-RESTORE.
2. S-KILL, then S-RESTART together with S-REBOOT: the stopped runtime stays stopped after the reboot, and resumes only
   by an attributable `scripts/p3/recovery.py authorize-resume`. Record `restart_continuity` before/after.
3. S-TIER3, S-UI, and S-RESTORE-2 if any change was merged during the window.
4. S-END at the lifecycle end, then S-INV (end), S-AUDIT, S-PNL and S-CI.

**Phase D — after the window.** Compute `run_verdict`. Claude prepares the acceptance record PR with the verdict and
the evidence index. The Owner's merge is the only acceptance. PLN-11 then builds its pack at `frozen_commit`.

## 8. Owner decisions: the run configuration
Each decision is a field of `P3_PLN10_RUN_CONFIG_V1` (`OWNER_DECISIONS` and `validate_run_config` in
`research/p3/acceptance.py`). Every field starts unset in `RUN_CONFIG_TEMPLATE`, and **no default exists anywhere**.
A missing key, `null`, a placeholder (`TBD`, `default`, `<…>`, …), a string where a number is required, `0`, a
negative or a non-finite number all keep the run `LAUNCH_BLOCKED`.

| Decision | Owner decides | Field that blocks until set | Blocks until |
|---|---|---|---|
| D1 | approved paper runtime | `paper_runtime` | `runtime_id` matches the kill switch's scope and is not FP-CONTROL-3; `authority_record` and its 40-hex `authority_merge` are cited; top-level `dry_run` is `true` |
| D2 | trial duration | `trial_window` | `start_utc` is ISO-8601 Z, `duration_hours` is a positive number, and the window ends no later than the P3 authorization's `EXPIRES_UTC` (2027-01-31T23:59:59Z) |
| D3 | emergency-stop bound | `emergency_stop_bound_s` | a positive, finite number of seconds. PLN-08's drill measured 0.162 s; the kill switch's per-container stop timeout is 30 s. The bound is the Owner's choice |
| D4 | acceptance criteria | `acceptance_criteria` | `matrix_sha256` equals `matrix_digest()`; `criterion_ids` lists **every** matrix id (a subset would be a waiver); `pnl_tolerance_quote` is an explicit decimal string ≥ 0 |
| D5 | explicit launch authority | `launch_authority` | `granted_by = Owner`; `paper_launch_authorized` is literally `true`; `record_path` and its 40-hex `merge_commit` cite an Owner-merged record. The P3 execution authorization is refused, and an H1 runtime needs an `H1_LAUNCH_AUTHORIZATION` record |

Template (all decisions open; validates to `LAUNCH_BLOCKED` on D1–D5):
```json
{"record_type": "P3_PLN10_RUN_CONFIG_V1", "run_id": null, "frozen_commit": null,
 "dry_run": true, "real_money_authorized": false,
 "paper_runtime": {"runtime_id": null, "authority_record": null, "authority_merge": null},
 "trial_window": {"start_utc": null, "duration_hours": null},
 "emergency_stop_bound_s": null,
 "acceptance_criteria": {"matrix_sha256": null, "criterion_ids": null, "pnl_tolerance_quote": null},
 "launch_authority": {"granted_by": null, "record_path": null, "merge_commit": null, "paper_launch_authorized": false}}
```
Even a complete configuration only yields `CONFIG_COMPLETE_FOR_OWNER_LAUNCH`. It launches nothing.

The options and consequences of each decision are in [`PLN_10_OWNER_DECISION_PACKET.md`](PLN_10_OWNER_DECISION_PACKET.md). No value is chosen there.

## 9. Stop conditions (contract §7)
Stop the run (S-KILL) and return to the Owner if any of these happens:
- a safety gate fails: `dry_run` is not true, a credential or live route appears, or `paper_guard`, `real_money` or
  `unauthorized_execution` goes CRITICAL;
- evidence is found corrupt or unattributable: `evidence_chain:*` goes CRITICAL, or a stop or start has no
  attributable record;
- a strategy, risk or dataset authority conflict appears;
- a destructive storage operation is needed;
- the host changes outside its frozen state (for example a package change outside the Owner's posture for item H);
- anything would touch real money.

## 10. Failure handling
- **FAIL** (a criterion's procedure says FAIL): record it. It stays FAIL for this `run_id`. The fix goes through a PR
  under the same contract, and acceptance needs a **new** continuous run with a new `run_id` and a new configuration.
  No evidence carries over between runs (§5). Never waived (§8 of the contract).
- **UNPROVEN** (for example S-KILL with nothing running): re-exercise inside the same window if possible. Otherwise
  the criterion stays unmet.
- **ABORTED** (host unavailable, or an Owner abort): not an acceptance FAIL, but never PASS. A new run is required.
- A §9 stop condition always ends the run as ABORTED or FAIL. The first stop is the kill switch, not a repair.

## 11. Controlled rollback
- **Runtime:** stop only with `scripts/p3/kill_switch.py --reason …` (bounded, recorded). The restart guard keeps it
  stopped; resume only by `recovery.py authorize-resume`, with a record. Never `docker rm` or `down -v`.
- **Host code:** `tlos-p3` returns to `frozen_commit`, or to the Owner's previous main SHA, by Owner action. A code
  fix is a new PR and a new run. Published history is never rewritten.
- **PLN-06 ops plane:** use the rollback column of [`PLN_06_ALERTING.md`](PLN_06_ALERTING.md) §3
  (`docker compose … down`, never `down -v`).
- **Evidence and data:** nothing is deleted. A restore goes only into an empty scratch (PLN-03), never over live
  state. A wrong record is superseded by a new record; it is never edited.
- **Authority:** an Owner PR that sets `launch_authority.paper_launch_authorized` to `false`, or removes the
  configuration, blocks any further launch at once.

## 12. Not claimed
PLN-10 is not started and not accepted. No run configuration, cohort or T0 exists. No launch is authorized, and no
profitability claim is made.
