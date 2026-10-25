# P3-PLN-00 — Final P2 → P3 Reconciliation

**Status: PLANNING RECORD. It is not P3 execution.** Master plan §17.1: "Neither `PLN-00` nor `PLN-01` planning is P3 execution."
It becomes the reconciled P3 entry truth only when the Owner merges it. Then `P3_ENTRY_TRUTH = RECONCILED`.
It starts nothing, freezes nothing, authorizes nothing, and changes no P2 record.

```text
BASE              main 0ce72358c3cf10ac97428ff7b721c45b02353d49 (PR #70, the P2 closure, Owner-merged)
P2_CLOSED         YES · P2_TERMINAL_STATUS = CLOSED / PASS (docs/p2/P2_CLOSURE.md)
P3_STARTED        NO   (requires PLN-01 contract freeze + OWNER_AUTHORIZES_P3_EXECUTION)
H1_LAUNCHED       NO   (separate cohort; requires its own H1_LAUNCH_AUTHORIZATION)
REAL_MONEY_AUTHORIZED = NO
```

## 1. Where this sits (master plan §1, §17.1, §27)
```text
… P2 closure transaction → OWNER MERGE → merged-main verification → P2_CLOSED = YES   ✔ done
  → P2 terminal outcome reviewed                                                       ✔ §2 below
  → P3-PLN-00 Final P2 → P3 Reconciliation   [planning]                                ◀ this record
  → P3_ENTRY_TRUTH = RECONCILED                                                        (on Owner merge)
  → P3-PLN-01 contract review / freeze        [planning]                               next
  → OWNER_AUTHORIZES_P3_EXECUTION → P3_STARTED = YES → P3 production implementation
```
The critical path is P1 → P2 → **P3 (Paper Beta)** → POST-BETA. H1-PAPER-COHORT-1 is not a critical-path stage: it is a prepared, held paper cohort (research/paper/h1/), and its launch is a separate Owner decision. NEW_STAGES = NONE.

## 2. P2 terminal outcome, reviewed (from the merged closure record)
| Field | Value |
|---|---|
| Trigger | A, NORMAL END (contract §7). The credited lifecycle is BTC/USDT trade 1 (admitted entry 2026-10-21T02:00Z candle → fill 03:00:02; admitted exit 2026-10-22T22:00Z candle → close 23:00:01) |
| Capability | 12/12 (9 pre-T0 at Mq 909bf5fa + 3 from the credited lifecycle). paper_trading_operational_capability = PROVEN · full_trade_lifecycle = OBSERVED |
| Edge | prospective_paper_edge = NOT_EVALUATED. n = 1 credited lifecycle, and both closed trades lost money. **Operational capability, not profitability** |
| ETH trade 2 | CONTEXTUAL, not credited (F-1) |
| Evidence | Archive l2-cohort-20260924T120000Z, pack 6ab601940e3e6201: Tier 1 (same host), Tier 2 (digest on main), second device (WDC). HOST_LOSS_REDUNDANCY = NOT_PROVEN |
| Registry | FP-CONTROL-1/2/3 all CLOSED · fp_run_active = false |
| Runtime | stopped. The P2 window-monitor timer is disabled. The pinned checkout 3191285a is clean |

## 3. Carry-forward: every P2 finding enters an existing P3 workstream (no WORKSTREAM_13)
| P2 item | Enters | Requirement for P3 planning |
|---|---|---|
| **F-1** ETH runtime/lane divergence: the lane derives EMA from gapped captured history | PLN-07, PLN-06 | The lane's signal history must be gap-free or reconciled against the runtime's candles before crediting. The record names this a Class B fix |
| **F-2** reconcile.py `execution_backed_by_decision` is pair-level (an unresolved verification-tool weakness) | PLN-07 | Per-execution verification: bar timing plus admission result, as a reconcile finding, with negative tests |
| **F-3** the cohort ran about 37 h past its normal end (the A15 check was scheduled at the cap) | PLN-06, PLN-08 | Detect the normal end on lifecycle completion and stop under governance. Post-window records stay context |
| **F-4** the ETH close is off a candle boundary (inference: fill latency, unverified) | PLN-07 | Verify the fill-timing model against order-book fills and the unfilled timeout |
| **F-5** the host timer undid the Owner-authorized GO 1 (no hard-cap guard) | PLN-04, PLN-06, PLN-08 | Recovery automation must honour terminal states (cap, normal end, Owner stop). It must not restart a stopped cohort |
| **O-1** a governed stop leaves no attributable record | PLN-05, PLN-08 | Every governed stop or start writes an attributable, verifiable record |

## 4. State and recovery inventory for P3 (inputs to PLN-02 to PLN-05; measured 2026-10-25)
| Item | Truth |
|---|---|
| Host | hamza-workstation. nvme0n1 (Lexar 256 GB, OS and root ext4). sda (WDC WD10EZEX 1 TB HDD, NTFS sda2 mounted at /mnt/tlos-wdc, ntfs3 noexec) |
| Root capacity | about 9.0 GiB free (97% used). Below any 20 GiB storage condition |
| Power | 6 unclean host-down intervals between 2026-09-28 and 10-23 (power-loss-consistent; P2 gap audit). **No UPS recorded** |
| Durability | Tier 1 + Tier 2 + same-host second device. Tier 3 (an independent host) does not exist; it is PLN-05 scope |
| Cold backup | /mnt/tlos-wdc/tlos-migration-20261025: a verified Trading Lab OS copy (tar.zst + git bundles + manifests) on the same host |
| Proposed storage | an active migration of Trading Lab OS onto a WDC ext4 partition is planned, not executed. It is **blocked**: the other WDC data has no independently verified copy, so partitioning needs external backup protection and a separate Owner authorization. The plan and runbook are operator documents outside the repository (/home/hamza/tlos-paper/WDC_*_20261025.md) |

These are inputs only. Backup and restore proof, reboot recovery and evidence durability are designed in PLN-02 to PLN-05 and executed only after P3 authorization.

## 5. H1-PAPER-COHORT-1 status (not P3; reported for completeness)
- The card on 0ce72358 (recomputed 2026-10-25T15:51Z from machine state) passes **11/12**. The only NOT PASS row is MATERIALISATION_PREFLIGHT: "less than 20 GB free on the lane's filesystem" (the lane is on the root fs, 9.0 GiB). Package ef9a3d0c…bc43c verifies.
- Open: H1_LAUNCH_BINDER §6's daily "host free space (≥ 20 GB)" does not name its filesystem. It is held unresolved pending an authorized clarification. The Owner has proposed an additional operational condition: at least 20 GiB on the lane fs **and** on the root fs.
- H1 launch requires the separate Owner H1_LAUNCH_AUTHORIZATION naming the package digest.

## 6. Reconciliation verdict (proposed)
```text
P2_OUTCOME_REVIEWED          = YES (CLOSED / PASS, trigger A, 12/12; edge NOT_EVALUATED)
P2_FINDINGS_PLACED           = F-1..F-5, O-1 → existing P3 workstreams (§3); none creates a stage
P3_STATE_INVENTORY_INPUTS    = recorded (§4)
CONTRADICTIONS_FOUND         = 1 — CLAUDE.md still named P2 as the current authorized stage; corrected in this
                               change to the post-closure truth (P2 closed; P3 planning only)
P3_ENTRY_TRUTH               = RECONCILED on Owner merge of this record
NEXT                         = P3-PLN-01 Contract & Acceptance (review / freeze), planning only
P3_STARTED = NO · H1_LAUNCHED = NO · REAL_MONEY_AUTHORIZED = NO
```
