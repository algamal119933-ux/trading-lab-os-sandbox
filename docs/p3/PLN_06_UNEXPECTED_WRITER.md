# P3-PLN-06: §19 "unexpected writer" (auditd-first evaluation and design)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-06 (frozen at fcd06b21), executed under [`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md). The master plan's §19 lists "unexpected writer" as CRITICAL. Delivery of the resulting alert is [`PLN_06_ALERTING.md`](PLN_06_ALERTING.md) (merged in PR #85 and PR #92); it is referenced here, not repeated.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCH_AUTHORIZED = NO

```text
STATUS_ON_HOST   = NOT_COVERED
                   No watch is installed. The Owner installs auditd and the rules (§7), and the acceptance tests (§8) must pass on the host.
REPOSITORY_SIDE  = PREPARED: research/p3/writer_watch.py (rules generator, rules check, read-only classifier) and 31
                   synthetic tests. Acceptance AT-1..AT-7 (§8): NOT_RUN.
WIRED_INTO_HOURLY_HEALTH = NO. That waits until auditd is installed and AT-1..AT-7 pass, so an absent daemon cannot
                           permanently hold the health verdict at WARNING before the Owner has decided.
PLN-06           = PARTIAL. This document does not close it. Delivery and the dead-man are in PLN_06_ALERTING.md §3.
```

## 1. Why the existing checks do not cover this
- The hourly `evidence_chain:sealed_archives` check rehashes sealed archives against their manifests. It sees **that** a sealed byte changed, after the fact. It does not see **who** changed it, or a write that leaves the hash unchanged (attribute or ownership changes).
- `evidence_chain:operator_ledger` sees a broken chain. It does not see a correctly chained record appended by an unauthorized process.
- Nothing watches `p3-evidence/`, the backup sets, the runtime's governed records or the (absent) H1 lane for writes.

## 2. Protected paths (derived from existing repository constants, not a new list)
The paths are computed in `writer_watch.py` from the constants the hourly health job and the Control Room already use, so a path that moves there moves here too. `tests/test_p3_writer_watch.py` pins each derivation.

| Class (audit key) | Paths | Derived from | Lawful writers (comm · uid/euid · exe under a system bin dir) |
|---|---|---|---|
| `tlos_sealed` | `~/projects/trading/trading_lab_os_final/artifacts`; `/mnt/tlos-wdc/trading-lab-os-evidence` | `health.RUNTIME_ROOT`/artifacts; `control_room.BACKUP_TARGET.parent` + `replicate_to_second_device.REPLICA_ROOT_NAME` | **none.** A sealed archive is never written. A future governed archive operation is announced beforehand and its events are reviewed against that announcement |
| `tlos_ledger` | `~/tlos-paper/operator-ledger` | `health.OPERATOR_LEDGER` (= `control_room.LEDGER`) | `python*` · 1000 (`scripts/p3/kill_switch.py`; `recovery.py authorize-resume`) |
| `tlos_p3_evidence` | `~/tlos-paper/p3-evidence` | `control_room.EVIDENCE_DIR` (the health textfile directory in `scheduled_health.sh`) | `python*` · 1000 (hourly health job, Control Room build, reboot snapshot and verify); `mkdir` · 1000 (`scheduled_health.sh` `mkdir -p` of the Control Room dir) |
| `tlos_backups` | `/mnt/tlos-wdc/tlos-backups` | `control_room.BACKUP_TARGET` | `python*`, `tar`, `zstd`, `git`, `sha256sum` · 1000 (`scheduled_backup.sh` → `backup.py`); `tar` · 0 (the `python:3.12-slim` volume-export helper container) |
| `tlos_registry` | `~/projects/trading/trading_lab_os_final/research/fp/records` | `health.RUNTIME_ROOT` | `git` · 1000 (only a checkout of a merged commit changes it) |
| `tlos_h1_lane` | `~/tlos-paper/h1-paper-cohort-1` | `health.H1_LANE` | **none** while `H1_LAUNCH_AUTHORIZED = NO`. The H1 grant PR adds the launcher and container writers |
| `tlos_canary` | `~/tlos-paper/writer-canary`; `/mnt/tlos-wdc/tlos-writer-canary` | one per watched filesystem (new, by design) | **none, by design.** They hold no evidence and exist so the alert path can be proven on each filesystem without touching real evidence |

Nine watches in total. Sealed archives the hourly rehash finds in **other** checkouts (`~/projects/trading/*/artifacts`) are not watched by this rule set; AT-1 lists them and fails if any exists, so the inventory is extended by a reviewed PR rather than assumed.

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
An event is considered only if it has a SYSCALL record and its audit key starts with `tlos_`. Each such event carries `key`, `comm`, `exe`, `uid`, `euid`, `auid`, `pid`, `success` and up to four PATH names, and is classified as one of:
- **AUTHORIZED.** The key's class declares a writer whose `comm` glob matches, whose uid list contains **both** `uid` and `euid`, and whose `exe` starts with a root-owned system bin directory (`/usr/bin/`, `/bin/`, `/usr/local/bin/`, `/usr/sbin/`, `/sbin/`).
- **UNEXPECTED.** The class is known and the event is attributable, but no declared writer matches. Any write to `tlos_sealed`, `tlos_h1_lane` or `tlos_canary` is always UNEXPECTED. A failed attempt (`success=no`) is classified the same way: the attempt is the finding.
- **UNATTRIBUTED.** The key is not in the inventory, or the event lacks `comm` or `uid`.

Hardening against evasion:
- auditd hex-encodes `comm`, `exe` and `name` values that contain spaces or unusual bytes. These are decoded before matching.
- A process that renames itself to `python3` (`prctl(PR_SET_NAME)`) from a binary in a user-writable place fails the `exe` test.
- A setuid escalation (`uid=1000 euid=0`) fails the `euid` test.
- In an ENRICHED log, only the raw part before the `0x1d` separator is read, so `UID="hamza"` never overwrites `uid=1000`.

Residual limit, stated rather than hidden: attribution is to a process identity, not to intent. Any `/usr/bin/python3` run as uid 1000 is a declared writer of the ledger and of `p3-evidence`. The ledger's hash chain (checked hourly) remains the control for *what* was appended.

## 5. Mapping to a health finding (fail-closed)
`writer_watch.finding` (or `evaluate`, text in) returns one finding `unexpected_writer`. The first matching row wins:

| # | Situation | Finding |
|---|---|---|
| 1 | Any UNEXPECTED event | **CRITICAL**, naming key, comm, exe, uid, auid and path. This wins over every other row |
| 2 | No audit data (log, `auditctl -s` or `auditctl -l` missing or unreadable) | WARNING "UNPROVEN" |
| 3 | Any of the nine `(path, key)` watches not loaded (checked per path, not only per key) | WARNING "UNPROVEN", naming `key:path` |
| 4 | auditd not enabled (`enabled 0`), or the `lost` counter unavailable | WARNING "UNPROVEN" |
| 5 | `lost` above the recorded baseline | WARNING "UNPROVEN" (events may be missing) |
| 6 | `lost` below the baseline (the counter reset, e.g. a reboot) | WARNING "UNPROVEN": re-record the baseline |
| 7 | `backlog` ≥ `backlog_limit` | WARNING "UNPROVEN" (events may be dropped) |
| 8 | Coverage gap inside the window: a `DAEMON_END`, `DAEMON_ABORT` or `DAEMON_ERR` record; a `CONFIG_CHANGE` removing a `tlos_` watch; or `audit_enabled=0` | WARNING "UNPROVEN", naming the record and the `auid`. A watch removed and re-added inside the window does not show in `auditctl -l`, so this is the only place it is seen |
| 9 | Any UNATTRIBUTED event | WARNING "UNPROVEN" |
| 10 | Heartbeat: no event at all on `tlos_p3_evidence` in the window. The hourly health job writes there on every run, so silence means the watch is blind (wrong log, detached watch) | WARNING "UNPROVEN" |
| 11 | Everything above proven | INFO |

An unknown result is never INFO. The CLI exits 0 / 1 / 2 for INFO / WARNING / CRITICAL and reports an unreadable input as UNPROVEN, never as a crash.

## 6. False positives, tampering and overhead
- **Expected false positives:**
  - A manual `git checkout` in the runtime is a real write. It is attributed to `git` and is lawful.
  - An operator editing a ledger by hand is UNEXPECTED. That is a true positive.
  - Backup helpers outside the declared `comm` set would raise UNEXPECTED. They are added to the inventory only through a reviewed PR, never by silencing.
  - An Owner step that changes ACLs under `p3-evidence` (`setfacl`, [`PLN_06_ALERTING.md`](PLN_06_ALERTING.md) §3 step 3) is an attribute change by root and is UNEXPECTED. Install auditd **after** that step, or record the event as an announced Owner action.
  - If the runtime venv's interpreter resolves outside the system bin directories (for example a uv-managed Python under `~/.local`), every health run classifies UNEXPECTED. AT-2 exposes this. The fix is a reviewed inventory PR, not a relaxed rule.
- **Tampering with the watch itself:**
  - Removing rules shows as missing watches (row 3). Removing and re-adding inside a window shows as a coverage gap (row 8).
  - Stopping auditd shows as `enabled 0` / unavailable data (rows 2 and 4) and as `DAEMON_END` (row 8).
  - Immutable mode (`-e 2`, rules locked until reboot) is stronger, but makes rule changes and the rollback need a reboot. That is an Owner decision, and it is never generated (a test enforces this).
- **Overhead:**
  - Watches add cost only to syscalls on watched inodes.
  - The heaviest writer is the daily backup, about 8 s. AT-6 measures its duration with and without the rules.
  - The backlog limit is `-b 8192`, and `--backlog_wait_time 60000`.
  - On overflow, `-f 1` (printk) logs the overflow instead of panicking.

## 7. Owner installation (HOST; only under its own Owner authorization)
Preconditions: the host freeze is lifted for this step by the Owner ([`PLN_04_RECOVERY.md`](PLN_04_RECOVERY.md) "Host-freeze lift conditions" item 4); `~/projects/trading/tlos-p3` is at a main that contains this document; [`PLN_06_ALERTING.md`](PLN_06_ALERTING.md) §3 step 3 (the `setfacl` step) is done or will be recorded as announced.
```bash
# OWNER ACTION. Read every line first.
cd ~/projects/trading/tlos-p3 && export PYTHONDONTWRITEBYTECODE=1
W=~/tlos-paper/pln06-writer-acceptance; mkdir -p "$W"          # acceptance evidence; not a watched path
sudo apt install auditd 2>&1 | tee "$W/install.txt"
mkdir -p ~/tlos-paper/writer-canary /mnt/tlos-wdc/tlos-writer-canary   # before the rules load
python3 research/p3/writer_watch.py rules > /tmp/tlos-evidence.rules
sudo install -m 0640 /tmp/tlos-evidence.rules /etc/audit/rules.d/tlos-evidence.rules
sudo augenrules --load
sudo auditctl -l > "$W/install_rules.txt"
python3 research/p3/writer_watch.py check-rules --rules "$W/install_rules.txt"   # expect: RULES = LOADED (9/9 watches)
sudo auditctl -s | tee "$W/install_status.txt" | awk '$1=="lost"{print $2}' > "$W/lost_baseline.txt"
```

**Rollback:**
```bash
sudo rm /etc/audit/rules.d/tlos-evidence.rules && sudo augenrules --load
```
Uninstalling auditd is a separate Owner decision. With `-e 2` in force, the rollback takes effect only after a reboot.

## 8. Acceptance tests (host; NOT_RUN)
Each test session uses a new evidence directory and the same snapshot helper. Nothing in it is overwritten:
```bash
cd ~/projects/trading/tlos-p3 && export PYTHONDONTWRITEBYTECODE=1
W=~/tlos-paper/pln06-writer-acceptance
EV=$W/$(date -u +%Y%m%dT%H%M%SZ); [ -e "$EV" ] && echo STOP || mkdir -p "$EV"
BASE=$(cat "$W/lost_baseline.txt")
snap() {  # $1 = test id, $2 = window start (epoch seconds)
  sudo auditctl -s > "$EV/$1_status.txt"; sudo auditctl -l > "$EV/$1_rules.txt"
  sudo LC_ALL=C ausearch --raw -ts $(LC_ALL=C date -d "@$2" '+%x %T') > "$EV/$1_audit.raw" || true  # no match = empty
  python3 research/p3/writer_watch.py classify --log "$EV/$1_audit.raw" --status "$EV/$1_status.txt" \
    --rules "$EV/$1_rules.txt" --lost-baseline "$BASE" > "$EV/$1_classify.txt"; echo "exit=$?" >> "$EV/$1_classify.txt"
}
```

| ID | Command (Owner) | PASS when | FAIL when | Status |
|---|---|---|---|---|
| AT-1 rules loaded | `sudo auditctl -l > $EV/at1_rules.txt; python3 research/p3/writer_watch.py check-rules --rules $EV/at1_rules.txt > $EV/at1.txt; echo exit=$? >> $EV/at1.txt; ls -d ~/projects/trading/*/artifacts/*/archive_manifest.json >> $EV/at1.txt` | `RULES = LOADED (9/9 watches)`, `exit=0`, and every listed `archive_manifest.json` is under `~/projects/trading/trading_lab_os_final/artifacts/` | `RULES = INCOMPLETE` or `UNPROVEN`, or a sealed archive under another checkout (extend the inventory by PR) | NOT_RUN |
| AT-2 authorized write | `T0=$(date +%s)`; wait until after the next `tlos-p3-health.service` run (`systemctl --user list-timers tlos-p3-health.timer`); `snap at2 $T0` | `at2_classify.txt` ends `INFO unexpected_writer …` with `exit=0`; it has `COUNT tlos_p3_evidence AUTHORIZED n` with n ≥ 1; it has no `UNEXPECTED` or `UNATTRIBUTED` line | any other severity. An UNEXPECTED health-job write (e.g. an `exe` outside the system bin dirs) is sent to Claude for a reviewed inventory PR; the host inventory is never edited | NOT_RUN |
| AT-3 canary, both filesystems | `T0=$(date +%s); sleep 1; touch ~/tlos-paper/writer-canary/probe-$T0 /mnt/tlos-wdc/tlos-writer-canary/probe-$T0; sleep 2; snap at3 $T0` | `exit=2`; `CRITICAL unexpected_writer`; two `UNEXPECTED tlos_canary` lines, one per probe path, each with `comm='touch' exe='/usr/bin/touch' uid=1000 auid=1000`. Once the check is wired and PLN-06 delivery passes, the same probe must page within 2 minutes (recorded then, not now) | fewer than two canary lines (a filesystem is not watched), or any exit other than 2 | NOT_RUN |
| AT-4 backup night | `T0=$(date +%s)` in the evening; after the backup: `systemctl --user show tlos-p3-backup.service -p Result -p ExecMainExitTimestamp > $EV/at4_unit.txt; snap at4 $T0` | `Result=success`; `exit=0`; `COUNT tlos_backups AUTHORIZED n` with n ≥ 1; no `UNEXPECTED`, `UNATTRIBUTED` or `coverage gap` line | any UNEXPECTED or UNATTRIBUTED backup event, or a coverage gap | NOT_RUN |
| AT-5 loss detection | after AT-2..AT-4: `sudo auditctl -s > $EV/at5_status.txt; grep -E '^(lost\|backlog\|backlog_limit) ' $EV/at5_status.txt; grep -lE 'lost [0-9]+ event\|backlog saturated\|coverage gap\|below the baseline' $W/*/at[234]_classify.txt \|\| echo NO_LOSS_FINDINGS` | `lost` equals `$BASE`; `backlog` < `backlog_limit`; `NO_LOSS_FINDINGS`. A forced-overflow test is out of scope on production | `lost` above `$BASE`, or any loss finding | NOT_RUN |
| AT-6 overhead | `journalctl --user -u tlos-p3-backup.service -o short-iso-precise --since "-14 days" \| grep -E 'Starting\|Finished\|Consumed' > $EV/at6_journal.txt`; tabulate the Starting→Finished duration of at least 3 runs before the install and the first run after it, in `$EV/at6_overhead.txt` | the table is recorded and the increase is ≤ +20 % | above +20 %: **ESCALATE** to the Owner (decision recorded); never hidden, never a silent PASS | NOT_RUN |
| AT-7 reboot persistence | after the next Owner-authorized reboot: `cp $W/lost_baseline.txt $W/lost_baseline.prev; sudo auditctl -s \| awk '$1=="lost"{print $2}' > $W/lost_baseline.txt; BASE=$(cat $W/lost_baseline.txt)`; then repeat AT-1 and AT-3 (ids `at7_rules`, `at7_canary`) | AT-1 PASS and AT-3 PASS with no manual step. The WDC canary event proves the watch attached to the mounted ntfs3 filesystem and not to the bare mount point | either fails. A WDC-only failure means the rules loaded before the mount; the remedy (unit ordering) is an Owner decision, not improvised | NOT_RUN |

Only after AT-1 to AT-7 pass is the check wired into the hourly health run, in a separate PR, and the §19 row moved from NOT_COVERED to COVERED. That PR needs one more Owner decision: the health job runs as uid 1000 and cannot read `/var/log/audit` or run `auditctl -s`/`-l`. A small root-run collector must save those three snapshots for it, and a stale snapshot must read as UNPROVEN. Until then the honest status on the host is **NOT_COVERED**. The Owner may instead accept the gap explicitly in a recorded decision. That is never inferred from silence.

## 9. Verification of this change (cloud, synthetic only)
`tests/test_p3_writer_watch.py` (31 tests, synthetic raw audit lines; no host path is read) covers:
- **Inventory:** every path is derived from `health` / `control_room` / `replicate_to_second_device` constants; the rules cover all nine watches; `-e 2` is never generated; one canary per watched filesystem, overlapping no evidence path.
- **Listings:** `loaded_watches` reads both the `-w` and the `-F dir= … key=` forms.
- **Attribution:**
  - a declared writer is AUTHORIZED, with key/comm/exe/uid/euid/auid carried;
  - sealed, H1-lane and canary writes are CRITICAL;
  - a foreign comm or uid, a renamed process from a user-writable exe, or an escalated euid is UNEXPECTED;
  - root `tar` is lawful only on the backup sets, and `mkdir` only on `p3-evidence`;
  - hex `comm` is decoded, and ENRICHED fields never overwrite the ids;
  - a failed attempt is still classified.
- **Fail-closed:**
  - no data, an unreadable input, a missing watch (per path), a disabled daemon, lost events, a counter reset, a saturated backlog, a coverage gap (`DAEMON_*`, removed watch, auditing off), an UNATTRIBUTED event and a silent heartbeat are all UNPROVEN;
  - UNEXPECTED wins over all of them.
- **CLI:** `rules`, `check-rules` and `classify`, with exit codes 0, 1 or 2, run standalone as the runbook invokes them.

Delivery-side tests added with this change (PLN-06-owned files, no new framework):
- `scripts/p3/ops/rules/tlos_p3_alerts.test.yml`: `unexpected_writer` = 2 raises `TLOSHealthCritical` and = 1 raises `TLOSHealthWarning` (`promtool test rules`).
- `tests/test_p3_alerting.py`: with `amtool config routes test`, the template routes everything to `null` until the Owner chooses. After the runbook's edit (Telegram or ntfy), `TLOSWatchdog` goes only to `deadman`, and every critical or warning alert (including `unexpected_writer` and the step-6 `TLOSDeliveryTest`) goes to the chosen channel.
