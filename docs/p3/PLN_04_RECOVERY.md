# P3-PLN-04 — Restart / Reboot / Host Recovery, and the PLN-07 failure/recovery matrix (execution record)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 (frozen at fcd06b21), executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1).
**PLN-04 acceptance (contract):**
- after a reboot, the stack's state is correct;
- a cohort in a terminal or Owner-stopped state is **never** auto-restarted (negative test);
- a host-recovery drill from backup passes.

PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCHED = NO

## Implemented (outside the FP runtime tree)
| Item | Path |
|---|---|
| Terminal-state restart guard (F-5), resume authorization, reboot snapshot/verify | `research/p3/recovery.py` |
| CLI: `may-restart` (exit 0 / 3), `authorize-resume`, `snapshot`, `verify-boot` | `scripts/p3/recovery.py` |
| Prometheus textfile for the PLN-06 health check (atomic write) | `research/p3/health.py` `write_textfile`, `scripts/p3/health_check.py --prom-textfile` |
| Tests: 18, synthetic. Every negative control is produced | `tests/test_p3_recovery.py` |

Guard rule: a restart is allowed only when:
- the registry row is RUNNING;
- no kill-switch STOPPED record for the role's containers stands in the hash-chained operator ledger, unless a later attributable `RESUME_AUTHORIZED` record for that role exists.

A tampered ledger refuses rather than guesses. **Any recovery automation must gate on `scripts/p3/recovery.py may-restart`.** The retired P2 window monitor stays disabled.

## Executed on hamza-workstation (2026-10-25T18:5xZ)
- `may-restart --role FP-CONTROL-3` gives **NO** (exit 3): "FP-CONTROL-3 is CLOSED; only a RUNNING cohort may be restarted".
- **Host-recovery drill:** the PLN-03 restore drill on the newest set `20261025T185052Z` passes every check:
  - root identity;
  - 8 sealed archives ARCHIVE_VERIFIED;
  - the runtime config and strategies load in the pinned engine;
  - git fsck and HEAD.
- **Pre-reboot snapshot:** `/home/hamza/tlos-paper/p3-evidence/pre_reboot_snapshot.json`, boot_id bb6de453. It records:
  - `/` and `/mnt/tlos-wdc` mounted;
  - tlos-p3-backup.timer not-found (not yet installed);
  - tlos-p2-window-fp-control-3.timer disabled/inactive;
  - 5 unrelated containers, and no paper runtime.
- The capture bug found here (a disabled unit recorded as absent, because `systemctl is-enabled` exits non-zero) is fixed and tested.
- **Reboot test: PENDING the Owner's reboot window.** After the reboot, run `scripts/p3/recovery.py verify-boot --before /home/hamza/tlos-paper/p3-evidence/pre_reboot_snapshot.json`. Its checks:
  - the boot id changed;
  - the mounts came back;
  - the timers are in the same state;
  - the unrelated running containers came back;
  - no stopped paper runtime came back;
  - no new paper runtime appeared.

## PLN-07 failure/recovery matrix (each row has a passing test or a real drill)
| Failure mode | Expected handling | Evidence |
|---|---|---|
| Fill without an admitted decision (F-2) | audit FAIL | `test_p3_operations` (5 negatives), plus the real audit on sealed P2 (ETH unbacked) |
| Fill outside its decided bar / off-boundary close (F-4) | audit FAIL | `test_an_unbacked_fill_fails[...outside...]`, plus the real ETH close at 11:10 (unbacked) |
| Restart of a CLOSED / NOT_STARTED / unknown cohort (F-5) | guard refuses | `test_a_terminal_or_unstarted_or_unknown_cohort_never_restarts`, plus real FP-CONTROL-3: NO |
| Restart after an Owner stop (F-5) | guard refuses until an attributable resume | `test_an_owner_stop_stands_until_an_attributable_resume` |
| Unattributed stop (O-1) | refused without a reason; every stop is chained | `test_a_stop_without_a_reason_is_refused…`, plus the real drill ledger |
| Tampered operator ledger | kill switch and guard refuse | `test_a_tampered_ledger…` (×2) |
| Runtime runs past its normal end (F-3) | health WARNING "governed stop due" | `test_a_completed_lifecycle_on_a_running_cohort_flags_the_normal_end` |
| Disk below 20 GiB, WDC unmounted, stale or corrupt backup | health CRITICAL / WARNING | `test_free_space_and_mount_findings`, `test_backup_recency_against_the_rpo` |
| Corrupt backup artifact or rewritten SHA256SUMS | verify and drill FAIL | `test_a_tampered_artifact…`, `test_a_rewritten_sums_file…` |
| Sealed archive drift | drill FAIL | `test_a_sealed_archive_that_no_longer_verifies…`, plus real ARCHIVE_VERIFIED ×8 |
| Host loss (restore elsewhere) | restore drill from a set | real drills `20261025T171416Z`, `20261025T185052Z`: PASS |
| Reboot | reboot check | snapshot taken. **Verify pending the Owner's reboot window** |
| Lane / launcher symlink and identity attacks | existing P2 adversarial suites | `test_fp_lane_adversarial`, `test_fp_lane_io_adversarial` (unchanged, passing) |

## Acceptance status
```text
PLN-04  terminal-state guard         PASS (negative tests + real refusal of FP-CONTROL-3)
        host-recovery drill          PASS (restore drill, newest set)
        reboot correctness           PENDING — Owner reboot window (snapshot ready)
PLN-07  failure/recovery matrix      PASS for every row except the reboot row (pending, as above)
PLN-06  alert delivery               Prometheus textfile implemented; wiring it into a scrape (node-exporter
                                     textfile collector or equivalent) and a scheduled health run are host
                                     installs — Owner action, together with the backup timer
```
