# P3-PLN-04 / PLN-07 — Reboot acceptance runbook (prepared, not executed)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-04 and PLN-07 (frozen at fcd06b21), executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1). The execution record is
[`PLN_04_RECOVERY.md`](PLN_04_RECOVERY.md).
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCH_AUTHORIZED = NO

The reboot is the **Owner's act**, and Claude never reboots the host. This runbook is read-only except for the evidence
files it creates. Each of those gets a new dated name and is never overwritten.

**PLN-04 reboot correctness is PENDING. This document claims nothing.**

## 0. Fixed inputs. Do not change them before the run

| Input | Value |
|---|---|
| Baseline snapshot | `~/tlos-paper/p3-evidence/pre_reboot_snapshot_20261026.json` |
| Baseline sha256 | `42f0d28fea3246385d571e52a973a3cc935bf6ef333b7d2da61d640ae1a3956f` |
| Baseline content | Taken 2026-10-26T15:57:28Z on boot `29eaec64`. Records `/` and `/mnt/tlos-wdc` mounted; `tlos-p3-backup.timer` enabled/active; `tlos-p2-window-fp-control-3.timer` disabled/inactive; 5 non-TLOS containers; no paper runtime |
| Code that runs the check | `~/projects/trading/tlos-p3`, detached at `253dbf2` (PR #78), clean |

**Ordering rule.** The reboot verify runs with `tlos-p3` still at `253dbf2`.

The following changes all alter what the baseline compares against, so none of them may happen between the preflight and the verify:
- updating `tlos-p3` to a newer main (#79, #80, #81, #85 and #87 have merged since `253dbf2`);
- installing node-exporter or auditd;
- enabling, disabling or editing any user unit;
- starting or stopping containers.

Do all of them only **after** the verify has been recorded.

The baseline does not list `tlos-p3-health.timer` in the recovery `UNITS`. Adding it is a later, separate change: a new
baseline must be taken after that change, never edited into this one.

## 1. Pre-reboot validation (read-only)
```bash
d=~/projects/trading/tlos-p3; PY=~/projects/trading/trading_lab_os_final/.venv/bin/python
out=~/tlos-paper/p3-evidence/reboot_preflight_$(date +%Y%m%dT%H%M%S).txt
{
echo "== time / boot"; date -Is; cat /proc/sys/kernel/random/boot_id
echo "== mounts"; findmnt / ; findmnt /mnt/tlos-wdc
echo "== disk"; df -h / /mnt/tlos-wdc
echo "== timers"; systemctl --user list-timers --all 'tlos-*' --no-pager
echo "P2 timer: $(systemctl --user is-enabled tlos-p2-window-fp-control-3.timer 2>&1) / $(systemctl --user is-active tlos-p2-window-fp-control-3.timer 2>&1)"
echo "== latest backup set"; last=$(ls -1d /mnt/tlos-wdc/tlos-backups/2* | tail -1); echo "$last"
echo "== verify latest set (read-only)"; (cd "$d" && "$PY" scripts/p3/backup.py verify --set "$last"); echo "verify_exit=$?"
echo "== last backup runs"; journalctl --user -u tlos-p3-backup.service --no-pager -n 2
echo "== health (prints only; does not rewrite the textfile)"; (cd "$d" && "$PY" scripts/p3/health_check.py); echo "health_exit=$?"
echo "== restore drill records"; ls -1dt /home/hamza/tlos-restore-drill-* 2>/dev/null | head -3
echo "== docker"; docker ps -a --format '{{.Names}}  {{.Status}}'
echo "== TLOS paper runtimes (must be none)"; docker ps --format '{{.Names}}' | grep -E 'tradinglab-fp-control|tlos-h1-paper' || echo none
echo "== baseline snapshot"; sha256sum ~/tlos-paper/p3-evidence/pre_reboot_snapshot_20261026.json
echo "== code"; git -C "$d" log -1 --format='%h %s'; git -C "$d" status --short | head -5; echo "(empty = clean)"
} > "$out" 2>&1; cat "$out"
```

**GO only if every line below holds.** Otherwise STOP, keep the file, and send it for review:
- `verify_exit=0`
- `health_exit=0`
- both mounts are listed
- `P2 timer: disabled / inactive`
- `TLOS paper runtimes` prints `none`
- the baseline sha256 equals `42f0d28f…3956f`
- `tlos-p3` is at `253dbf2` and clean

## 2. The reboot (Owner)
1. Save your work and close your apps. Wait until no other project's job is running.
2. Restart from the GNOME menu (top-right → Power → Restart), or in a terminal run `sudo systemctl reboot -i`.
   - A plain `systemctl reboot` is refused while the GNOME session holds an inhibitor. That is what happened on 2026-10-26 at 21:02.
   - Never use the power button. A hard power-off is an unclean shutdown, and §4 classifies it as such.
3. Log back in. The user timers run in the user session. Wait about one minute.
4. **Prove a reboot happened before §3:** `cat /proc/sys/kernel/random/boot_id` must **not** start with `29eaec64`. If it does, no reboot occurred, so do not run §3.

## 3. Post-reboot acceptance commands
```bash
d=~/projects/trading/tlos-p3
out=~/tlos-paper/p3-evidence/post_reboot_verify_$(date +%Y%m%dT%H%M%S).json
[ -e "$out" ] && echo "STOP: exists" || {
  echo "== boot"; cat /proc/sys/kernel/random/boot_id
  (cd "$d" && python3 scripts/p3/recovery.py verify-boot --before ~/tlos-paper/p3-evidence/pre_reboot_snapshot_20261026.json --json "$out"); echo "verify_boot_exit=$?"
  echo "== clean shutdown evidence (previous boot, system manager)"; journalctl -b -1 --no-pager _PID=1 | grep -E "Reached target (reboot|shutdown|final)\.target|Shutting down" | tail -4
  echo "== previous boot tail"; journalctl -b -1 --no-pager -n 6
  echo "== boots"; journalctl --list-boots --no-pager | tail -3
  echo "== timers"; systemctl --user list-timers --all 'tlos-*' --no-pager
  echo "== health"; (cd "$d" && ~/projects/trading/trading_lab_os_final/.venv/bin/python scripts/p3/health_check.py); echo "health_exit=$?"
  echo "== saved"; cat "$out"; sha256sum "$out"
}
```

## 4. Expected outcomes and failure classification

**Expected result (PASS):**
- `verify_boot_exit=0` and `PLN_04_REBOOT_CHECK = PASS`, with all 10 checks passing:
  - `rebooted`;
  - `mount:/`;
  - `mount:/mnt/tlos-wdc`;
  - `unit:tlos-p3-backup.timer` enabled → enabled/active;
  - `unit:tlos-p2-window-fp-control-3.timer` disabled → disabled/inactive;
  - the 4 running non-TLOS containers came back;
  - `no_new_paper_runtime`.
- The system manager logged a clean shutdown: `Reached target reboot.target` or `shutdown.target`, or `Shutting down`.
- `health_exit=0`.

Any other outcome falls into exactly one of these classes. Record the class; never waive it:

| Class | Signature | Meaning | Action |
|---|---|---|---|
| `PROCEDURAL_NON_RUN` | `rebooted FAIL`, boot_id unchanged | No reboot happened, e.g. it was inhibited | Not a reboot result. Keep the file, cite it, and repeat §2–§3 |
| `BASELINE_DRIFT` | A unit or container row FAILs because the host was changed after the baseline, e.g. a unit installed later | The check compared against an outdated baseline | Not a reboot defect, and **not** PASS. Take a new baseline when the change is intended, then repeat the reboot |
| `UNCLEAN_SHUTDOWN` | The previous boot's journal ends mid-activity, with no system-manager shutdown lines | Power loss or a hard reset, not the planned reboot | Record it as a power-posture event (UPS decision) and repeat with a clean reboot. The checks still show how the stack recovered |
| `NON_TLOS_CONTAINER` | Only a `container:moneyprinterturbo-*` or `container:niche-finder-*` row FAILs | That project's restart policy | Record it. Do not touch that project. The TLOS reboot rows decide PLN-04. The Owner decides whether the run counts, and records that decision |
| `REAL_DEFECT` | A mount is missing, a TLOS timer is in the wrong state, a stopped paper runtime came back, a new paper runtime appeared, or health is CRITICAL | The stack did not recover correctly | **STOP.** This is a contract §7 return to the Owner. Fix it under the contract and repeat |

## 5. Recovery steps (when a row fails)
These are diagnosis steps only. Each mutation listed is the Owner's, and only where the row says so.

- **Mount missing:** `findmnt /mnt/tlos-wdc` and `journalctl -b -u mnt-tlos\\x2dwdc.mount`. The fstab entry uses `nofail`, so the boot completes without it. The Owner mounts it, and the backup timer refuses to run until then (`RequiresMountsFor`).
- **Backup timer not active:** `systemctl --user status tlos-p3-backup.timer`. If linger is off, the user session must be logged in. The Owner re-enables the timer only if it was disabled.
- **P2 timer active:** **STOP.** This is an F-5 class event. Read `scripts/p3/recovery.py may-restart --role FP-CONTROL-3`, which must give NO. The Owner disables the timer, and the incident is recorded.
- **New paper runtime:** **STOP.** Run the kill switch `scripts/p3/kill_switch.py` with a reason. It is attributable in the operator ledger. Then record the incident.

## 6. Evidence to collect (kept on the host, indexed in the record)
- the `reboot_preflight_*.txt` file;
- the `post_reboot_verify_*.json` file and its sha256;
- the §3 console output, including the clean-shutdown lines and the boot ids;
- the health output after the reboot.

The next scheduled backup set picks these up under `p3-evidence/`, and PLN-02's re-check covers them.

## 7. Record template for `PLN_04_RECOVERY.md` (filled in only after a real run)
```text
REBOOT RUN 1  2026-10-26 ~10:54 (boot bb6de453 → 29eaec64)  class UNCLEAN_SHUTDOWN + BASELINE_DRIFT
              verify-boot vs pre_reboot_snapshot.json: FAIL 9/10
              single FAIL: unit:tlos-p3-backup.timer not-found → enabled/active (installed after that baseline, PR #78)
              evidence: ~/tlos-paper/p3-evidence/post_reboot_verify_20261026.json
              verdict: not a reboot defect; not PASS; new baseline taken (pre_reboot_snapshot_20261026.json)
REBOOT RUN 2  2026-10-26 21:02 (boot 29eaec64 unchanged)  class PROCEDURAL_NON_RUN
              `systemctl reboot` inhibited by the logged-in GNOME session; no reboot occurred
              verify-boot FAIL 9/10, single FAIL: rebooted (29eaec64 → 29eaec64)
              evidence: ~/tlos-paper/p3-evidence/post_reboot_verify_20261026T2102*.json
              verdict: not a reboot result
REBOOT RUN 3  <date> (boot 29eaec64 → <new>)  class <PASS | …>
              preflight: <file>  verify-boot: <file> sha256 <…>  checks <n>/10
              clean shutdown: <system-manager lines>   health_exit: <n>
              verdict: PLN_04_REBOOT_CORRECTNESS = <PASS | FAIL (class)>
```

**PLN-07** closes its reboot row only when PLN-04 reboot correctness is PASS. All its other rows are already PASS (see
[`PLN_04_RECOVERY.md`](PLN_04_RECOVERY.md)).
