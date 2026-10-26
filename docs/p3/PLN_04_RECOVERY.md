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
| Reboot | reboot check | planned reboot 2026-10-27: verify-boot PASS 10/10 (owner-reported); **PASS_CANDIDATE**, pending gap attestation and Owner acceptance (see the reboot record below) |
| Lane / launcher symlink and identity attacks | existing P2 adversarial suites | `test_fp_lane_adversarial`, `test_fp_lane_io_adversarial` (unchanged, passing) |

## Acceptance status
```text
PLN-04  terminal-state guard         PASS (negative tests + real refusal of FP-CONTROL-3)
        host-recovery drill          PASS (restore drill, newest set)
        reboot correctness           PASS_CANDIDATE — planned reboot 2026-10-27 verify-boot PASS 10/10
                                     (owner-reported); gap attestation + Owner acceptance pending (record below)
PLN-07  failure/recovery matrix      PASS for every row; reboot row PASS_CANDIDATE (as above)
PLN-06  alert delivery               Prometheus textfile implemented; wiring it into a scrape (node-exporter
                                     textfile collector or equivalent) and a scheduled health run are host
                                     installs — Owner action, together with the backup timer
```

## Reboot record (template: [`PLN_04_REBOOT_ACCEPTANCE_RUNBOOK.md`](PLN_04_REBOOT_ACCEPTANCE_RUNBOOK.md) §7)

Provenance labels:
- `CLAUDE-VERIFIED` means Claude saw the output.
- `OWNER-REPORTED` (HANDOFF_ONLY) means the Owner reported the values. Claude has not read the host file. An Owner-reported value becomes verified only when the Owner attaches the gap-attestation output (below), which prints the RUN 3 JSON and its sha256.

```text
REBOOT RUN 1  2026-10-26 ~10:54 Cairo (boot bb6de453 → 29eaec64)  class UNCLEAN_SHUTDOWN + BASELINE_DRIFT
              verify-boot vs pre_reboot_snapshot.json: FAIL 9/10                       [CLAUDE-VERIFIED output]
              single FAIL: unit:tlos-p3-backup.timer not-found → enabled/active (installed after that baseline, PR #78)
              previous boot's journal ended mid-activity (no system-manager shutdown lines): power loss
              evidence: ~/tlos-paper/p3-evidence/post_reboot_verify_20261026.json
              verdict: not a reboot defect; not PASS; new baseline taken
                       (pre_reboot_snapshot_20261026.json, 2026-10-26T15:57:28Z, sha256 42f0d28f…3956f)
REBOOT RUN 2  2026-10-26 21:02 Cairo (boot 29eaec64 unchanged)  class PROCEDURAL_NON_RUN    [CLAUDE-VERIFIED output]
              `systemctl reboot` inhibited by the logged-in GNOME session; no reboot occurred
              verify-boot FAIL 9/10, single FAIL: rebooted (29eaec64 → 29eaec64)
              evidence: ~/tlos-paper/p3-evidence/post_reboot_verify_20261026T2102*.json
              verdict: not a reboot result
REBOOT RUN 3  2026-10-27 ~02:27 Cairo (boot 29eaec64 → dc3ccd57-7a8e-40c7-a206-52c16a1f9da2)  [OWNER-REPORTED]
              preflight: ~/tlos-paper/p3-evidence/reboot_preflight_20261026T2100*.txt (GO; 2026-10-26 21:00 Cairo)
              verify-boot vs pre_reboot_snapshot_20261026.json (sha256 42f0d28fea3246385d571e52a973a3cc935bf6ef333b7d2da61d640ae1a3956f)
              verify-boot: ~/tlos-paper/p3-evidence/post_reboot_verify_20261026T233717Z.json
                           sha256 d5214021b9136b01d43f14af50f63abde85562656dc9a5711c42abb56383c499   checks 10/10 PASS
              clean shutdown: shutdown.target, final.target and reboot.target reached (system manager)
              health: INFO, health_exit 0 · root 161 GiB free · WDC mounted · tlos-p3-backup.timer enabled/active
                      · tlos-p2-window-fp-control-3.timer disabled/inactive · no paper runtime · tlos-p3 still 253dbf2
              class: PASS on every runbook §4 criterion, with one procedural deviation (below)
              verdict: PLN_04_REBOOT_CORRECTNESS = PASS_CANDIDATE
                       (pending: gap attestation clean + Owner acceptance of this record by merge)
PLN-07        reboot row = PASS_CANDIDATE (closes with PLN-04 reboot correctness)
```

### Procedural review: preflight age (recorded, not waived)
| Fact | Detail |
|---|---|
| What happened | The preflight was taken 2026-10-26 at 21:00 Cairo. The reboot happened about 02:27 the next day, roughly 5.5 h later. RUN 2 (a non-run verify) happened in between, at 21:02. |
| What the runbook requires | The §0 ordering rule sets **no clock limit**. It forbids four baseline-altering changes between the preflight and the verify: (1) updating `tlos-p3`; (2) installing node-exporter or auditd; (3) enabling, disabling or editing any user unit; (4) starting or stopping containers. |
| What RUN 3 already evidences | (1) `tlos-p3` still at `253dbf2`. (3) Unit states identical to the baseline. (4) The same containers running, and no paper runtime. |
| What it does not evidence | Package installs, (2), are not covered by verify-boot. Edits to unit *files* that leave the enabled/active state unchanged are not covered either. |
| Classification | `PROCEDURAL_DEVIATION_PREFLIGHT_AGE`. This is not one of the §4 failure classes and not a reboot defect. It is a gap in the pre-reboot evidence. |
| Acceptance condition | A read-only **gap attestation** over the window from 2026-10-26 21:00 to the reboot, showing no prohibited change. **If it is clean, no repeat reboot is required.** If it shows any prohibited change, RUN 3 is reclassified `BASELINE_DRIFT` / unknown, and a new baseline plus a repeat reboot are **mandatory**. |
| Runbook change | §2 now says the preflight runs immediately before the reboot. If the reboot is delayed, either re-run the preflight or produce this attestation. |

### Gap attestation (read-only; the Owner runs it on hamza-workstation)
```bash
out=~/tlos-paper/p3-evidence/reboot_gap_attestation_$(date +%Y%m%dT%H%M%S).txt
[ -e "$out" ] && echo "STOP: $out exists" || {
{
echo "== boot";            cat /proc/sys/kernel/random/boot_id; journalctl --list-boots --no-pager | tail -3
echo "== packages installed/upgraded/removed since 2026-10-26 21:00 (dpkg)"
awk '$1" "$2 >= "2026-10-26 21:00:00" && ($3=="install"||$3=="upgrade"||$3=="remove"||$3=="purge")' /var/log/dpkg.log 2>&1
echo "== apt history since 2026-10-26";  grep -A4 "^Start-Date: 2026-10-2[67]" /var/log/apt/history.log 2>&1 | head -60
echo "== node-exporter / auditd present?"; dpkg -l prometheus-node-exporter auditd 2>&1 | tail -3
echo "== tlos-p3";          git -C ~/projects/trading/tlos-p3 rev-parse HEAD; git -C ~/projects/trading/tlos-p3 status --short | head; echo "(empty = clean)"
                            git -C ~/projects/trading/tlos-p3 reflog -5 --date=iso
echo "== user unit files changed since 2026-10-26 21:00"; find ~/.config/systemd/user -newermt "2026-10-26 21:00" -ls 2>&1; echo "(empty = none)"
echo "== systemctl invocations in the window (system journal)"
journalctl --since "2026-10-26 21:00" --until "2026-10-27 02:30" _COMM=systemctl --no-pager 2>&1 | tail -20
echo "== hourly health runs in the window (rc must be 0)"
journalctl --user --since "2026-10-26 21:00" --until "2026-10-27 02:30" -u tlos-p3-health.service --no-pager 2>&1 | grep -E "Finished|Failed|rc=" | head -12
journalctl --since "2026-10-26 21:00" --until "2026-10-27 02:30" -t tlos-p3-health --no-pager 2>&1 | grep -o "rc=[0-9]*.*" | head -12
echo "== reboot evidence files (sha256)"
sha256sum ~/tlos-paper/p3-evidence/pre_reboot_snapshot*.json ~/tlos-paper/p3-evidence/reboot_preflight_*.txt ~/tlos-paper/p3-evidence/post_reboot_verify_*.json 2>&1
echo "== RUN 3 verify-boot JSON"; cat ~/tlos-paper/p3-evidence/post_reboot_verify_20261026T233717Z.json
echo "== RUN 3 shutdown lines (previous boot, system manager)"
journalctl -b -1 --no-pager _PID=1 | grep -E "Reached target (reboot|shutdown|final)\.target|Shutting down" | tail -5
} > "$out" 2>&1; cat "$out"; }
```
**Clean means all of the following:**
- No `install`/`upgrade`/`remove` line in the window.
- node-exporter and auditd are not installed.
- `tlos-p3` is at `253dbf2`, clean, with no reflog entry in the window.
- No user unit file changed in the window.
- No `systemctl enable/disable/start/stop` of a TLOS unit in the window. Routine timer activations are fine.
- Every health run in the window finished, and every logged `rc=0`.
- RUN 3 JSON sha256 = `d5214021…c499`, with 10/10 PASS.
- Every older evidence file is still present.

Package updates by the system's unattended-upgrades are recorded as they are. They count as a prohibited change only if they touch node-exporter, auditd, Docker or systemd. The Owner decides with the output in view.

### Host-freeze lift conditions
1. The gap attestation is clean, as defined above.
2. The Owner accepts this record by merging it. That acceptance closes PLN-04 reboot correctness and the PLN-07 reboot row.
3. The freeze then lifts **only** for the controlled `tlos-p3` update (the Owner's host acceptance packet, step 7) to an **Owner-chosen** main SHA. Recommended: the SHA after #92 and #90 are merged, so the host runs the final health code once.
4. **Every later host-changing step needs its own explicit Owner authorization.** That covers node-exporter, Alertmanager, auditd, the Tier-3 key, and anything else.
5. **Next baseline:** the recovery `UNITS` do not yet include `tlos-p3-health.timer`. Adding it is a separate change, and it requires a new baseline afterwards.
