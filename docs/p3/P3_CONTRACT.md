# P3 — PAPER BETA RELEASE · stage contract (P3-PLN-01, DRAFT FOR FREEZE)

**Status: PLANNING. This document is the P3-PLN-01 "Contract & Acceptance" deliverable for review and freeze.** It binds nothing until the Owner merges it (freeze). Even after that, **P3 execution starts only with a separate Owner `OWNER_AUTHORIZES_P3_EXECUTION` record (§9)**. It derives from the master plan (docs/governance/TRADING_LAB_OS_MASTER_EXECUTION_AND_MONITORING_PLAN.md §1, §10, §13, §14, §17, §18, §23, §25, §27) and from the reconciled entry truth (docs/p2/P3_PLN_00_P2_TO_P3_RECONCILIATION.md, merged at f597041a). It does not redesign P3, adds no stage and no workstream, and changes no frozen trading semantics.

```text
BASE                 main f597041a1f813c27a03e90b1659aea60a7065044
P2_CLOSED            YES (CLOSED / PASS)        P3_ENTRY_TRUTH = RECONCILED (PR #71)
P3_CONTRACT          DRAFT → FROZEN on Owner merge
P3_STARTED           NO
H1_LAUNCHED          NO (separate authorization; not a P3 dependency)
REAL_MONEY_AUTHORIZED = NO
```

## 1. Purpose and limit (master plan §17.3)
P3 turns the P2-proven paper capability into an operable, recoverable, verifiable **Paper Beta**:
- backup and restore proof;
- restart, reboot and host recovery;
- evidence durability;
- monitoring continuity and operational hardening;
- failure and recovery verification;
- operator controls and kill switch;
- the Control Room implementation of the frozen product shape;
- Paper Beta acceptance;
- final freeze and execution pack.

**P3 is not** a strategy stage, an edge-discovery stage, a real-money stage or a redesign stage. P3_IS_ONE_STAGE = YES · P3_WORKSTREAM_COUNT = 12 · WORKSTREAM_13 = FORBIDDEN.

## 2. Owner strategic priorities, placed inside the existing workstreams (no new stage)
| Priority | Where it lives | What P3 can establish, and what it cannot |
|---|---|---|
| 1. Verified net profitability | PLN-10 (acceptance: net-of-fees P&L **measurement** and reporting are correct and reconciled), then the **POST-BETA research-qualification lane** (§14 validation funnel) | P3 proves the system measures net results truthfully: fees, fills, realised P&L, reconciliation. **P3 cannot prove profitability.** §17.3 says P3 is not an edge-discovery stage, and P2 recorded `PROSPECTIVE_PAPER_EDGE = NOT_EVALUATED` (n = 1). Profitability is verified only by separately authorized research under §14, followed by isolated forward paper |
| 2. Open-source reuse before building | Every workstream, under §10 | Each deliverable carries a reuse classification (REUSE_EXISTING / WRAP_EXISTING / AUDIT_BEFORE_USE / BUILD_SMALL_MISSING_LAYER / DEFER / DO_NOT_BUILD). The retained stack is Freqtrade, Git, Docker, Prometheus, Grafana and the existing evidence and reconciliation tooling. No new engine, database, control plane or monitoring stack without demonstrated need |
| 3. Multi-market coverage | PLN-06 and PLN-07, for **data-truth controls** (§13) over every data feed in use | P3 hardens and verifies data truth and coverage monitoring for the markets the frozen configuration uses (Binance spot BTC/USDT and ETH/USDT, 1h). **Adding markets or pairs changes frozen trading semantics.** That needs separate authority through the §14 funnel and is not P3 scope |
| 4. Independent verification | PLN-07 (verification tooling and adversarial and recovery tests), PLN-05 (Tier 3 independent-host evidence), CI | Every acceptance criterion is machine-checked or reproducible by a second party. Per-execution reconciliation (F-2). Independent-host evidence (HOST_LOSS_REDUNDANCY, currently NOT_PROVEN) |
| 5. Capital preservation | PLN-08 (operator controls and kill switch), and the hard safety boundary | `REAL_MONEY_AUTHORIZED = NO` for all of P3. A kill switch and terminal-state guards are tested. Recovery automation can never restart a stopped or terminal cohort (F-5) |

## 3. The twelve workstreams: scope, existing assets, acceptance
Acceptance criteria are the evidence the stage needs. "Existing" is what is already in the repository or on the host, verified 2026-10-25.

| WS | Scope | Existing (reuse) | Remaining deliverables | Acceptance (machine-checkable where possible) |
|---|---|---|---|---|
| **PLN-00** Final P2 → P3 Reconciliation | entry truth | docs/p2/P3_PLN_00_P2_TO_P3_RECONCILIATION.md | none | **DONE.** Merged as PR #71, P3_ENTRY_TRUTH = RECONCILED |
| **PLN-01** Contract & Acceptance | this contract | master plan §17 | Owner review and freeze (merge) | This file merged. Every WS has acceptance criteria. Priorities placed (§2) |
| **PLN-02** State & Recovery Inventory | every stateful asset and its recovery source | PLN-00 §4. The registry. Lanes. archive_fp_lane manifests. Cold-backup manifests (operator copy) | A machine-readable state inventory: path, device, owner, authority, size, recovery source, RPO | The inventory lists 100% of tracked and untracked TLOS state. Each item has a verified recovery source |
| **PLN-03** Backup & Restore | proven restore, not just copies | Tier 1 archive_fp_lane, Tier 2 publish_evidence_digest, replicate_to_second_device (all used in P2). Cold backup tar.zst + git bundles + manifests | An automated backup schedule. A **restore drill** into a scratch location from each backup tier | A restore drill passes: manifest sha256 equal, git fsck clean, ARCHIVE_VERIFIED on the restored copy, and the restored runtime starts in dry-run. Repeated after a change |
| **PLN-04** Restart / Reboot / Host Recovery | survive reboot and host loss | Restart law (restart_continuity), `restart: unless-stopped`, fstab `nofail` for the WDC | A reboot test. Host-recovery runbook execution. **Terminal-state-aware recovery** (F-5). Power-loss posture (6 unclean losses; UPS) | After a reboot, the stack's state is correct. A cohort in a terminal or Owner-stopped state is **never** auto-restarted (negative test). A host-recovery drill from backup passes |
| **PLN-05** Evidence Durability | evidence survives the loss of a disk and of the host | Tier 1 and Tier 2 plus a same-host second device (P2) | A **Tier 3 independent-host** copy. An attributable start/stop record (O-1). Storage capacity, root at about 9 GiB (see §6) | HOST_LOSS_REDUNDANCY = PROVEN by restoring from the independent host. Every governed stop/start has an attributable record |
| **PLN-06** Monitoring & Operational Hardening | continuity, alerts, capacity | fp_watch, the exporter, Prometheus, Grafana (REUSE) | Alerts per §19 severity. Capacity alerts (root and lane). **Normal-end detection** (F-3). Lane signal history gap control (F-1) | Each §19 CRITICAL condition raises an alert in a test. Capacity thresholds are enforced. Normal end is detected on lifecycle completion |
| **PLN-07** Failure & Recovery Verification | prove that the failure modes are handled | Adversarial lane and lane-I/O tests, reconcile (14 findings), the gap audit | A **per-execution reconciliation** finding (bar timing plus admission result, F-2). Fill-timing verification (F-4). A failure/recovery matrix with a test per row. Data-truth checks (§13) | Every matrix row has a passing test. F-2 has a reconcile finding with negative controls. The data-truth checks pass |
| **PLN-08** Operator Controls & Kill Switch | a safe operator surface | start/stop_fp_control.sh, fp_watch (read-only) | A **kill switch**: one governed command that stops all paper runtimes and records the stop. Terminal-state guards. Operator runbook | The kill switch stops everything within a bounded time and leaves an attributable record (test). No control can set dry_run=false or reach a live route (guard test) |
| **PLN-09** Control Room UX / UI | realise the frozen product shape (§18): one unified surface | Grafana is the live operator surface. The Control Room is not present (§18.2) | A Control Room projection over canonical evidence. Arabic/English | **BLOCKED** until the frozen product-shape reference (§18.1 "approved/frozen product shape") is identified. It is not in the repository. PLN-09 realises the shape and never reopens it. The UI is never evidence authority (§23) |
| **PLN-10** Paper Beta Acceptance Program | the acceptance run | P2 capability 12/12 (CLOSED / PASS) | An acceptance plan: duration, scenarios (restart, reboot, restore, kill), and net-of-fees P&L measurement checks (Priority 1, measurement only) | Every PLN-02 to PLN-09 acceptance holds in one continuous Paper Beta run. P&L measurement reconciles to fills and fees. No real money |
| **PLN-11** Final Freeze & Execution Pack | close P3 | — | A frozen execution pack (versions, digests, runbooks), the P3 closure record, and the POST-BETA handoff | The closure record is merged by the Owner. The pack is reproducible from Git plus digests |

## 4. Cross-cutting laws
- **Reuse-before-build** (§10): every deliverable records its reuse classification. NEW_ENGINE, NEW_DATABASE, NEW_CONTROL_PLANE and NEW_MONITORING_PLATFORM are all NO.
- **Data truth** (§13): no silent dataset replacement. Missing and duplicate candles are recorded, never filled.
- **Absolute prohibitions** (§23), including no strategy or risk mutation, no unauthorized backtests or paper bots, no UI as evidence authority, and no Control Room production work before its P3 authority.
- **Execution model:** branch, PR, CI, Owner merge. Auto-merge is INACTIVE (CEA-1).
- **Evidence:** every acceptance criterion cites a reproducible artifact (test, digest or record) in the repository or in a sealed archive.

## 5. Sequence (dependencies, not a schedule)
```text
PLN-01 freeze (Owner merge) → OWNER_AUTHORIZES_P3_EXECUTION
  → PLN-02 inventory
  → PLN-03 backup/restore  ∥ PLN-05 durability (Tier 3)    (both need PLN-02)
  → PLN-04 restart/reboot/host recovery                    (needs PLN-03)
  → PLN-06 monitoring/hardening ∥ PLN-07 verification ∥ PLN-08 operator controls
  → PLN-09 Control Room (after its product-shape authority is identified)
  → PLN-10 Paper Beta acceptance run (needs PLN-02..PLN-09)
  → PLN-11 freeze & execution pack → P3 closure (Owner merge) → POST-BETA
```

## 6. Known blockers at freeze time
| Blocker | Affects | Resolution path |
|---|---|---|
| Root fs about 9.0 GiB free (97%) | PLN-03, 05, 06, 10; H1 | Owner-approved capacity recovery or storage migration (the operator runbook, outside the repository). Partitioning is blocked pending independent backup of the WDC data |
| No independent host (Tier 3) | PLN-05 acceptance | The Owner provides an independent host or storage target |
| Frozen product-shape reference not in the repository | PLN-09 | The Owner identifies or merges the product-shape authority (§18.1) |
| Repeated unclean power loss, no UPS recorded | PLN-04 | A UPS, or an accepted power-loss posture, as an Owner decision |
| Merge law `AUTO_MERGE_INACTIVE:p2_closed` (base policy) | autonomy only | A CEA-1 governance change (Owner merge) if ever wanted. It does not block P3 |

## 7. Stop conditions (P3 execution, once authorized)
Stop and return to the Owner if any of these happens:
- a safety gate fails (dry_run is not true, or a credential or live route appears);
- evidence is found corrupt or unattributable;
- a strategy, risk or dataset authority conflict arises;
- a deliverable would need a new stage, engine or control plane, or would reopen the product shape;
- a destructive storage operation is needed;
- any action would touch real money.

## 8. Closure law (P3)
P3 is CLOSED / PASS only when all of these hold:
- every PLN-02 to PLN-11 acceptance criterion is evidenced;
- the PLN-10 Paper Beta acceptance run passes;
- the PLN-11 execution pack is frozen;
- the P3 closure record is merged by the Owner.

A failed acceptance is recorded and fixed under the same contract. It is never waived. P3 closure does **not** authorize Controlled-Live readiness or real money. Those are POST-BETA and need separate Owner authority.

## 9. P3 execution authorization package (prepared; not granted)
P3 execution requires, in order:
1. this contract frozen by Owner merge;
2. an Owner record `docs/p3/OWNER_P3_EXECUTION_AUTHORIZATION.md`, created and merged **by the Owner**.

That record must declare, each exactly once:
```text
AUTHORIZED_STAGE          = P3 — PAPER BETA RELEASE
P3_CONTRACT_PATH          = docs/p3/P3_CONTRACT.md
P3_CONTRACT_SHA256        = <sha256 of this file at its freeze merge>
P3_CONTRACT_FREEZE_MERGE  = <merge commit of the freeze PR>
SCOPE                     = PLN-02..PLN-11 as defined in §3; no new stage or workstream
REAL_MONEY_AUTHORIZED     = NO
H1_LAUNCH_AUTHORIZED      = NO   (H1 has its own authorization)
EXPIRES_UTC               = <date>
```
Until that record is merged, `P3_STARTED = NO`, and no P3 production implementation (including Control Room adapters) may be written.
