# P3-PLN-06 / PLN-07 / PLN-08 — operational tooling (execution record)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 (frozen at fcd06b21), executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1).
The contract runs these three in parallel after PLN-04. The parts delivered here **do not depend on PLN-04**, so they are implemented now, and their PLN-04-dependent acceptance is left open, not claimed.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCHED = NO

All tooling lives in `research/p3/` and `scripts/p3/`, **outside the FP runtime tree** (`research/fp/*.py`, `scripts/*.py`, `scripts/*.sh`), which the frozen P2 semantic identity covers. No runtime, strategy, risk, dataset, registry or evidence file changes. Tests are in `tests/test_p3_operations.py`: 17 tests, synthetic only, with docker and systemctl injected.

## PLN-07 — per-execution audit (P2 finding F-2)
`research/p3/execution_audit.py` and `scripts/p3/execution_audit.py`: an independent verifier, reuse classification BUILD_SMALL_MISSING_LAYER. reconcile.py is untouched, because it is in the frozen FP runtime tree.

Rule: each paper fill must be backed by an **ADMITTED, POST_T0, LIVE** decision with the same pair and action, whose candle closed at or before the fill and within one timeframe of it.

**Run on the sealed P2 archive** l2-cohort-20260924T120000Z, read-only:
```text
trade 1 BTC/USDT position_opened 2026-10-21 03:00:02  BACKED   (candle close 03:00Z, ADMITTED)
trade 2 ETH/USDT position_opened 2026-10-21 20:00:01  UNBACKED (nearest: 22:00Z, BLOCKED)
trade 2 ETH/USDT position_closed 2026-10-22 11:10:07  UNBACKED (nearest: 08:00Z ADMITTED, outside the bar)
trade 1 BTC/USDT position_closed 2026-10-22 23:00:01  BACKED   (candle close 23:00Z, ADMITTED)
EXECUTION_BACKED_BY_ADMITTED_DECISION = FAIL (2 unbacked)
```
The machine check reproduces exactly the closure record's manual classification: BTC credited, and ETH contextual (F-1, F-2, F-4). **F-2 now has its per-execution finding with negative controls.**

## PLN-08 — kill switch with an attributable record (O-1)
`research/p3/kill_switch.py` and `scripts/p3/kill_switch.py`, reuse classification WRAP_EXISTING (`docker stop`):
- scope: only `tradinglab-fp-control-*` and `tlos-h1-paper-cohort-*`;
- only `ps` and `stop` are issued, never `rm` or `down -v`, so lanes are untouched;
- a reason is required;
- every invocation appends a hash-chained record to the operator ledger (`/home/hamza/tlos-paper/operator-ledger/operator_ledger.jsonl`, which is inside the backed-up tlos-paper root);
- a tampered ledger is refused before anything is stopped.

**Real drill (2026-10-25T18:37Z):**
- A decoy `tradinglab-fp-control-killdrill` was started (python:3.12-slim `sleep`, `--network none --rm --init`).
- The dry run was recorded.
- The kill switch was engaged: `STOPPED`, 1 target, **0.162 s**, still_running [], decoy gone.
- The unrelated containers (moneyprinterturbo, niche-finder) were unchanged.
- The operator ledger holds 2 chained records, and `--verify-ledger` gives PASS.

Guard: no control here can set dry_run=false or reach a live route. The kill switch only stops, and the existing `paper_guard` continues to gate configs.

## PLN-06 — operational health check (F-3, F-5, capacity, RPO)
`research/p3/health.py` and `scripts/p3/health_check.py`, using the master-plan §19 severities. Read-only. Exit codes 0/1/2.

It checks:
- root and H1-lane free space against the proposed Owner condition of at least 20 GiB;
- the WDC mount;
- the age of the newest backup set against the RPO (26 h), and that it verifies;
- the backup timer enabled and active;
- the retired P2 restart timer disabled (F-5);
- a RUNNING cohort that already completed a lifecycle, which means NORMAL END reached and a governed stop due (F-3).

**Real run (2026-10-25T18:3xZ):**
```text
INFO     free_space:root            153.2 GiB free (min 20)
INFO     free_space:h1_lane         153.2 GiB free (min 20)
INFO     mount:/mnt/tlos-wdc        mounted
INFO     backup_recency             newest set 20261025T171416Z, 1.4 h old (RPO 26 h)
WARNING  timer:tlos-p3-backup.timer not installed (expected enabled+active)
INFO     timer:tlos-p2-window-…     disabled/inactive (as required)
INFO     normal_end                 no RUNNING cohort
HEALTH = WARNING
```
The only warning is the uninstalled backup timer. That is an Owner action from PLN-03.

## Acceptance status (honest)
| WS | Implemented | Verified | Acceptance |
|---|---|---|---|
| PLN-06 | health check, normal-end detection, capacity and RPO alerts | 17 tests + real run | **PARTIAL**. The §19 alert *delivery* (to Prometheus/Grafana) is not done yet. The exporter is in the FP runtime tree; a safe path is a node-exporter textfile or a P3 exporter, to be decided |
| PLN-07 | per-execution audit (F-2) | tests + real run on sealed P2 evidence | **PARTIAL**. The failure/recovery matrix and F-4 fill-timing verification remain, and depend on PLN-04 |
| PLN-08 | kill switch + operator ledger (O-1) | tests + real drill on Docker | **PASS** for the kill switch (bounded stop, attributable record, scope limited). The operator runbook is folded into this record |

## Update 2026-10-25T19:5xZ — PLN-06 alert delivery
- `scripts/p3/scheduled_health.sh` and `scripts/p3/units/tlos-p3-health.{service,timer}` run hourly from the clean tools checkout `~/projects/trading/tlos-p3`.
- Each run writes the Prometheus textfile (for a node-exporter textfile collector when one is installed), journals `tlos-p3-health rc=… HEALTH = …`, and on WARNING or CRITICAL raises a desktop notification (`notify-send`, urgency critical for CRITICAL).
- `SuccessExitStatus=1 2`, so an alert never masquerades as a unit failure.
- **Proven by one manual run (19:48Z):** journal line `rc=1 HEALTH = WARNING`, textfile updated (`tlos_p3_health_overall 1`), notification raised.
- The units are **prepared, not installed**. Host installation was refused by this session's permission system, so it is an Owner action. Wiring the textfile into Prometheus additionally needs `prometheus-node-exporter` (a package install, Owner).

## Update 2026-10-25T21:2xZ — health timer installed (Owner)
- `tlos-p3-health.timer` is enabled and hourly. The Owner's manual start succeeded: Result=success, journal `tlos-p3-health rc=0 HEALTH = INFO`.
- The textfile `/home/hamza/tlos-paper/p3-evidence/tlos_p3_health.prom` is rewritten with every check at 0 and `tlos_p3_health_overall 0`.
- Delivery on WARNING (journal plus `notify-send`) was proven at 22:48 and 22:55 local time, before the backup timer existed. An INFO run correctly sends no notification.
- The retired P2 timer `tlos-p2-window-fp-control-3.timer` is disabled, and the check reads 0 (F-5).

PLN-06 acceptance status:
- **Met:** normal-end detection (F-3), capacity and RPO alerts, scheduled hourly execution, journal record, and desktop notification.
- **Remaining:** the §19 Prometheus/Grafana leg. It needs `prometheus-node-exporter` with the textfile collector pointed at `p3-evidence/` (a package install, an Owner action), then a scrape target and an alert rule. Without that, **PLN-06 = PARTIAL**, not PASS.
