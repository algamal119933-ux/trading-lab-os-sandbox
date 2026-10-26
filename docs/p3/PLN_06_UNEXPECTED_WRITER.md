# P3-PLN-06: §19 "unexpected writer" (auditd-first evaluation and design)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-06 (frozen at fcd06b21), executed under [`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md). The master plan's §19 lists "unexpected writer" as CRITICAL.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCH_AUTHORIZED = NO

```text
STATUS_ON_HOST   = NOT_COVERED
                   No watch is installed. The Owner installs auditd and the rules (§7), and the acceptance tests (§8) must pass on the host.
REPOSITORY_SIDE  = PREPARED: research/p3/writer_watch.py (rules generator + read-only classifier) and 16 synthetic tests.
WIRED_INTO_HOURLY_HEALTH = NO. That waits until auditd is installed and AT-1..AT-7 pass, so an absent daemon cannot
                           permanently hold the health verdict at WARNING before the Owner has decided.
PLN-06           = PARTIAL. This document does not close it.
```

## 1. Why the existing checks do not cover this
- The hourly `evidence_chain:sealed_archives` check rehashes sealed archives against their manifests. It sees **that** a sealed byte changed, after the fact. It does not see **who** changed it, or a write that leaves the hash unchanged (attribute or ownership changes).
- `evidence_chain:operator_ledger` sees a broken chain. It does not see a correctly chained record appended by an unauthorized process.
- Nothing watches `p3-evidence/`, the backup sets, the runtime's governed records or the (absent) H1 lane for writes.

## 2. Protected paths (derived from the PLN-02 state inventory)
| Class (audit key) | Paths | Lawful writers |
|---|---|---|
| `tlos_sealed` | `~/projects/trading/trading_lab_os_final/artifacts`; `/mnt/tlos-wdc/trading-lab-os-evidence` | **none.** A sealed archive is never written. A future governed archive operation is announced beforehand and its events are reviewed against that announcement |
| `tlos_ledger` | `~/tlos-paper/operator-ledger` | `python*` as uid 1000 (`scripts/p3/kill_switch.py`; `recovery.py authorize-resume`) |
| `tlos_p3_evidence` | `~/tlos-paper/p3-evidence` | `python*` as uid 1000 (hourly health job, Control Room build, reboot snapshot and verify) |
| `tlos_backups` | `/mnt/tlos-wdc/tlos-backups` | `python*`, `tar`, `zstd`, `git`, `sha256sum` as uid 1000 (`scheduled_backup.sh` → `backup.py`); `tar` as uid 0 (the volume-export helper container) |
| `tlos_registry` | `~/projects/trading/trading_lab_os_final/research/fp/records` | `git` as uid 1000 (only a checkout of a merged commit changes it) |
| `tlos_h1_lane` | `~/tlos-paper/h1-paper-cohort-1` | **none** while `H1_LAUNCH_AUTHORIZED = NO`. The H1 grant PR adds the launcher and container writers |
| `tlos_canary` | `~/tlos-paper/writer-canary` | **none, by design.** It holds no evidence and exists so the alert path can be proven without touching real evidence |

The inventory lives in code (`writer_watch.DEFAULT_INVENTORY`), so the rules file and the classifier cannot drift apart.

## 3. Mechanism: auditd first, inotify compared
| Criterion | auditd (`-w path -p wa -k key`) | inotify (`inotifywait`) |
|---|---|---|
| Attribution (who wrote) | **Yes.** Each event carries `comm`, `exe`, `uid`, `auid` and `pid` | **No.** inotify reports the path and the event, never the process |
| Recursion | A directory watch covers the whole subtree, including files created later | Needs one watch per directory and a re-arm race when directories are created |
| Event loss | A kernel `lost` counter and backlog, readable with `auditctl -s` | Queue overflow (`IN_Q_OVERFLOW`) is reported, but what was lost cannot be attributed |
| Restart / reboot | The rules in `/etc/audit/rules.d/` load at boot before user services | The watcher must be a running service; nothing is watched until it starts |
| Writes by containers | Seen by the host kernel, with uid as mapped on the host | Seen, but unattributed |
| Overhead | A path watch only adds work on syscalls touching watched inodes. The watched paths change hourly, daily, or on governed actions only | Low, but proportional to the number of watched directories |
| Install | `sudo apt install auditd` (Owner) | `sudo apt install inotify-tools` (Owner) |

**Decision: auditd.** Attribution is the whole point of "unexpected writer", and only auditd provides it. inotify is kept only as a fallback note. It is not implemented.

## 4. Attribution rules (`writer_watch.classify`)
An event is considered only if its audit key starts with `tlos_`. Each such event is classified as one of:
- **AUTHORIZED.** The key's class declares a writer whose `comm` glob, `uid` and (optional) `exe` prefix all match.
- **UNEXPECTED.** The class is known and the event is attributable, but no declared writer matches. Any write to `tlos_sealed`, `tlos_h1_lane` or `tlos_canary` is always UNEXPECTED.
- **UNATTRIBUTED.** The key is not in the inventory, or the event lacks `comm` or `uid`.

auditd hex-encodes `comm`, `exe` and `name` values that contain spaces or unusual bytes. These are decoded before matching, so a renamed process cannot hide behind hex encoding.

## 5. Mapping to a health finding (fail-closed)
| Situation | Finding `unexpected_writer` |
|---|---|
| Any UNEXPECTED event | **CRITICAL** (this wins over every other row) |
| No audit data (auditd absent, log unreadable, status or rules not queried) | WARNING "UNPROVEN" |
| A `tlos_*` rule is not loaded (`auditctl -l`) | WARNING "UNPROVEN", naming the missing keys |
| auditd is not enabled, or the `lost` counter is unavailable | WARNING "UNPROVEN" |
| `lost` is above the recorded baseline | WARNING "UNPROVEN" (events may be missing) |
| Any UNATTRIBUTED event | WARNING "UNPROVEN" |
| Rules loaded for every class, no loss, every event AUTHORIZED | INFO |

An unknown result is never INFO.

## 6. False positives, tampering and overhead
- **Expected false positives:**
  - A manual `git checkout` in the runtime is a real write. It is attributed to `git` and is lawful.
  - An operator editing a ledger by hand is UNEXPECTED. That is a true positive.
  - Backup helpers outside the declared `comm` set would raise UNEXPECTED. They are added to the inventory only through a reviewed PR, never by silencing.
- **Tampering with the watch itself:**
  - Removing rules shows as missing keys (WARNING).
  - Stopping auditd shows as `enabled 0` / unavailable data (WARNING).
  - Rule changes are themselves audited when auditd runs with `-e 1`.
  - Immutable mode (`-e 2`, rules locked until reboot) is stronger, but makes rule changes need a reboot. That is an Owner decision, and it is never generated silently (a test enforces this).
- **Overhead:**
  - Watches add cost only to syscalls on watched inodes.
  - The heaviest writer is the daily backup, about 8 s. AT-6 measures its duration with and without the rules.
  - The backlog limit is `-b 8192`, and `--backlog_wait_time 60000`.
  - On overflow, `-f 1` (printk) logs the overflow instead of panicking.

## 7. Owner installation (HOST, after the planned reboot acceptance; not now)
```bash
# OWNER ACTION, only after the host freeze is lifted. Read every line first.
sudo apt install auditd
mkdir -p ~/tlos-paper/writer-canary
cd ~/projects/trading/tlos-p3 && python3 research/p3/writer_watch.py rules > /tmp/tlos-evidence.rules
sudo install -m 0640 /tmp/tlos-evidence.rules /etc/audit/rules.d/tlos-evidence.rules
sudo augenrules --load
sudo auditctl -l | grep -c tlos_          # expect 8 (one per watched path)
sudo auditctl -s                          # record the 'lost' value as the baseline
```

**Rollback:**
```bash
sudo rm /etc/audit/rules.d/tlos-evidence.rules && sudo augenrules --load
```
Uninstalling auditd is a separate Owner decision.

## 8. Acceptance tests (host; each writes its output to a new dated file)
| ID | Test | PASS when |
|---|---|---|
| AT-1 | Rules loaded: `auditctl -l` | every key in §2 present; `writer_watch.finding` is not "rules not loaded" |
| AT-2 | Authorized write: wait for one hourly health run | its `p3_evidence` events classify AUTHORIZED |
| AT-3 | Canary: `touch ~/tlos-paper/writer-canary/probe-$(date -u +%s)` | the event is UNEXPECTED, the finding is CRITICAL, and (once PLN-06 delivery is wired) the alert arrives |
| AT-4 | Backup night: after `tlos-p3-backup` runs | every `tlos_backups` event AUTHORIZED; none UNATTRIBUTED |
| AT-5 | Loss detection: compare `lost` with the baseline after AT-2..AT-4 | `lost` unchanged; a forced overflow test is out of scope on production |
| AT-6 | Overhead: backup duration with and without rules (journal timestamps) | the increase is recorded; above +20 % is escalated to the Owner, not hidden |
| AT-7 | Reboot persistence: after the next planned reboot | AT-1 still passes with no manual step |

Only after AT-1 to AT-7 pass is the check wired into the hourly health run, in a separate PR, and the §19 row moved from NOT_COVERED to COVERED. Until then the honest status on the host is **NOT_COVERED**. The Owner may instead accept the gap explicitly in a recorded decision. That is never inferred from silence.

## 9. Verification of this change (cloud, synthetic only)
`tests/test_p3_writer_watch.py` (16 tests) covers:
- the rules cover every protected path;
- a declared writer is AUTHORIZED;
- a sealed-archive write is CRITICAL;
- a foreign comm or uid on the ledger is UNEXPECTED;
- root `tar` is lawful only on the backup sets;
- the H1 lane has no lawful writer;
- hex `comm` is decoded;
- an event without comm or uid is UNATTRIBUTED (WARNING);
- unknown keys and foreign keys are handled;
- no data, missing rules, lost events or a disabled daemon are UNPROVEN;
- UNEXPECTED wins over UNPROVEN;
- the canary has no writer and overlaps no evidence path;
- the CLI exits 0, 1 or 2 by severity.
