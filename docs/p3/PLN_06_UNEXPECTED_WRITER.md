# P3-PLN-06: §19 "unexpected writer" (auditd-first evaluation and design)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-06 (frozen at fcd06b21), executed under [`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md). The master plan's §19 lists "unexpected writer" as CRITICAL. Delivery of the resulting alert is [`PLN_06_ALERTING.md`](PLN_06_ALERTING.md) (merged in PR #85 and PR #92); it is referenced here, not repeated.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCH_AUTHORIZED = NO

```text
STATUS_ON_HOST   = NOT_COVERED
                   No watch is installed. The Owner installs auditd and the rules (§7), and the acceptance tests (§8) must pass on the host.
REPOSITORY_SIDE  = PREPARED: research/p3/writer_watch.py (rules generator, rules check, read-only classifier, self-test)
                   and 47 synthetic tests (round-3 adversarial review: §4, §5, §10). Acceptance AT-0..AT-7 (§8): NOT_RUN.
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

| Class (audit key) | Paths | Derived from | Lawful writers (comm = exe program · uid/euid · auid · exe under a system bin dir) |
|---|---|---|---|
| `tlos_sealed` | `~/projects/trading/trading_lab_os_final/artifacts`; `/mnt/tlos-wdc/trading-lab-os-evidence` | `health.RUNTIME_ROOT`/artifacts; `control_room.BACKUP_TARGET.parent` + `replicate_to_second_device.REPLICA_ROOT_NAME` | **none.** A sealed archive is never written. A future governed archive operation is announced beforehand and its events are reviewed against that announcement |
| `tlos_ledger` | `~/tlos-paper/operator-ledger` | `health.OPERATOR_LEDGER` (= `control_room.LEDGER`) | `python*` · 1000 · auid 1000 (`scripts/p3/kill_switch.py`; `recovery.py authorize-resume`) |
| `tlos_p3_evidence` | `~/tlos-paper/p3-evidence` | `control_room.EVIDENCE_DIR` (the health textfile directory in `scheduled_health.sh`) | `python*` · 1000 · auid 1000 (hourly health job, Control Room build, reboot snapshot and verify); `mkdir` · 1000 · auid 1000 (`scheduled_health.sh` `mkdir -p` of the Control Room dir) |
| `tlos_backups` | `/mnt/tlos-wdc/tlos-backups` | `control_room.BACKUP_TARGET` | each of `python*`, `tar`, `zstd`, `git`, `sha256sum` · 1000 · auid 1000 (`scheduled_backup.sh` → `backup.py`); `tar` · 0 · auid unset `4294967295` (the `python:3.12-slim` volume-export helper container, started by dockerd outside any login session) |
| `tlos_registry` | `~/projects/trading/trading_lab_os_final/research/fp/records` | `health.RUNTIME_ROOT` | `git` · 1000 · auid 1000 (only a checkout of a merged commit changes it) |
| `tlos_h1_lane` | `~/tlos-paper/h1-paper-cohort-1` | `health.H1_LANE` | **none** while `H1_LAUNCH_AUTHORIZED = NO`. The H1 grant PR adds the launcher and container writers |
| `tlos_canary` | `~/tlos-paper/writer-canary`; `/mnt/tlos-wdc/tlos-writer-canary` | one per watched filesystem (new, by design) | **none, by design.** They hold no evidence and exist so the alert path can be proven on each filesystem without touching real evidence |

Nine watches in total. The generated rules list the classes with no lawful writer first (`tlos_sealed`, `tlos_h1_lane`, `tlos_canary`): the kernel records only the key of the **first** rule an event matches, so an event that reaches one of them carries its key. Sealed archives the hourly rehash finds in **other** checkouts (`~/projects/trading/*/artifacts`) are not watched by this rule set; AT-1 lists them and fails if any exists, so the inventory is extended by a reviewed PR rather than assumed.

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
`parse_audit_log` assembles one event per `msg=audit(<time>:<serial>)` from its SYSCALL, CWD, PATH (one per item number, so a duplicated record is not a second name) and PROCTITLE records, in any order. The **classes** an event touches are:
- the class of each `tlos_` key (a multi-key field, `\x01`-separated and hex-encoded by auditd, is decoded and split), and
- the class of every PATH name that lies under a protected path. Names are resolved against the CWD record and `..` is folded.

An event with no `tlos_` key counts only if one of its PATH records CREATEs or DELETEs a name under a protected path. That happens when another rule matched first and took the key. A read audited by some other rule is not a write and is ignored.

Each event that touches a class is classified as one of (the first matching line wins):
1. **UNEXPECTED.** It touches a class with no lawful writer (`tlos_sealed`, `tlos_h1_lane`, `tlos_canary`). This holds even when the event cannot be attributed.
2. **UNATTRIBUTED.** A `tlos_` key not in the inventory; no SYSCALL record; a missing `comm`, `uid`, `euid` or `auid`; or a link/move whose new name cannot be resolved (no CWD record).
3. **UNEXPECTED.** A link or move under a `tlos_` key whose new name (PATH `CREATE`, next to a `DELETE` or `NORMAL` item) lies outside every protected tree. Writes through that name would carry no key, so the move itself is the finding.
4. **UNEXPECTED.** For some class it touches, no declared writer matches all of these:
   - `comm` matches the writer's program glob;
   - the `exe` file name matches the same program;
   - `exe` sits under a root-owned system bin directory (`/usr/bin/`, `/bin/`, `/usr/local/bin/`, `/usr/sbin/`, `/sbin/`);
   - `uid` **and** `euid` are in the writer's uid list;
   - the login uid `auid` is in the writer's auid list.
5. **AUTHORIZED.** Otherwise: a declared writer matches for **every** class touched.

A failed attempt (`success=no`) is classified the same way, because the attempt is the finding.

Hardening against evasion (each has a regression test, §10):
- **Rename or link across trees** (`p3-evidence/x → h1-paper-cohort-1/x`) is judged by both classes, not by whichever rule the kernel matched first. The same holds for a relative name, a `..` traversal, and a hex-encoded name.
- **A hard link or move out of a watched tree** by a declared writer identity is UNEXPECTED (row 3).
- **A system binary renamed to an allowed comm** (`prctl(PR_SET_NAME, "python3")` from `/usr/bin/perl`) fails the exe-program test. So does a binary in a user-writable place.
- **A setuid escalation** (`uid=1000 euid=0`) fails the euid test.
- **Another login identity acting as the owner** (`auid=0` or `1001` with uid 1000, i.e. `su`/`sudo -u`) fails the auid test. So does a process with no login session at all (`auid` unset, for example a container running as uid 1000).
- **auditd hex-encoding.** `comm`, `exe`, `name`, `cwd` and `key` values are always decoded, including names with control bytes.
- **ENRICHED logs.** Only the raw part before the `0x1d` separator is read, so `UID="hamza"` never overwrites `uid=1000`.

Residual limits, stated rather than hidden:
- Attribution is to a process identity, not to intent. Any `/usr/bin/python3` run as uid 1000 from the owner's login is a declared writer of the ledger and of `p3-evidence`. The ledger's hash chain (checked hourly) remains the control for *what* was appended.
- PATH names are lexical. A name that reaches a protected tree through a symlink is seen only through the key, which comes from the kernel's inode match. That is why the no-writer classes are listed first in the rules.
- A name relative to a directory fd (`openat(dirfd, …)`) is resolved against CWD. That can only **add** a class (a false UNEXPECTED, surfaced by AT-2/AT-4); it never removes the key's class.
- A hard link that already existed before the rules were loaded is invisible to a directory watch. AT-1 lists multi-linked files under the protected trees.
- auid 1000 for the user services assumes `pam_loginuid` in `/etc/pam.d/systemd-user`. auid unset for the helper container assumes dockerd/containerd start it. AT-2 and AT-4 verify both on the host. A mismatch is UNEXPECTED, which leads to a reviewed inventory PR, never a relaxed rule.

## 5. Mapping to a health finding (fail-closed)
`writer_watch.finding` (or `evaluate`, text in) returns one finding `unexpected_writer`. The first matching row wins:

| # | Situation | Finding |
|---|---|---|
| 1 | Any UNEXPECTED event | **CRITICAL**, naming key, comm, exe, uid, auid and path. This wins over every other row |
| 2 | No audit data (log, `auditctl -s` or `auditctl -l` missing or unreadable) | WARNING "UNPROVEN" |
| 3 | Any of the nine `(path, key)` watches not loaded (checked per path, not only per key) | WARNING "UNPROVEN", naming `key:path` |
| 4 | auditd not enabled (`enabled 0`); not connected to the kernel (`pid 0` or absent: records go to the kernel log, not `audit.log`); the `lost` counter unavailable; or **no lost baseline recorded** (CLI `--lost-baseline` missing, empty or not an integer, e.g. `BASE=$(cat missing-file)`) | WARNING "UNPROVEN" |
| 5 | `lost` above the recorded baseline | WARNING "UNPROVEN" (events may be missing) |
| 6 | `lost` below the baseline (the counter reset, e.g. a reboot) | WARNING "UNPROVEN": re-record the baseline |
| 7 | `backlog` ≥ `backlog_limit` | WARNING "UNPROVEN" (events may be dropped) |
| 8 | Coverage gap inside the window: a `DAEMON_END`, `DAEMON_ABORT`, `DAEMON_ERR`, `DAEMON_START` (a `kill -9` leaves no `DAEMON_END`, only the restart's start record) or `DAEMON_RESUME` (logging resumed after a suspend) record; a `CONFIG_CHANGE` removing a `tlos_` watch; or `audit_enabled=0`. `DAEMON_ROTATE` is not a gap | WARNING "UNPROVEN", naming the record and the `auid`. A watch removed and re-added inside the window does not show in `auditctl -l`, so this is the only place it is seen |
| 9 | Any UNATTRIBUTED event | WARNING "UNPROVEN" |
| 10 | Heartbeat: no event at all on `tlos_p3_evidence` in the window. The hourly health job writes there on every run, so silence means the watch is blind (wrong log, detached watch) | WARNING "UNPROVEN" |
| 11 | Everything above proven | INFO |

An unknown result is never INFO. The CLI exits 0 / 1 / 2 for INFO / WARNING / CRITICAL and reports an unreadable input or a missing baseline as UNPROVEN, never as a crash.

The classifier itself has no window: the window is whatever `ausearch -ts` returns. A window edge that cuts off events (clock skew, a late `-ts`) can only remove evidence, and that fails closed through the heartbeat (row 10). auditd log rotation that **deletes** a file inside the window is not visible in the records. The window must stay shorter than `num_logs × max_log_file` (AT-5 records both).

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

Every row writes only under `$EV` (or `$W` for the baseline), and is executed in order; one FAIL stops the sequence and is recorded, never waived.

| ID | Command (Owner) | Evidence written | PASS when | FAIL when | Status |
|---|---|---|---|---|---|
| AT-0 classifier self-test (read-only, before AT-1; needs no auditd) | `python3 research/p3/writer_watch.py self-test > $EV/at0_selftest.txt; echo exit=$? >> $EV/at0_selftest.txt` | `at0_selftest.txt` | last lines `SELFTEST = PASS (15/15 expectations)` and `exit=0` (the shipped synthetic fixture `tests/fixtures/p3_writer_watch_selftest.audit` classifies as expected at this checkout) | any `FAIL` line, `SELFTEST = FAIL`/`UNPROVEN`, or `exit=1`: the checkout is not the reviewed one; stop | NOT_RUN |
| AT-1 rules loaded | `sudo auditctl -l > $EV/at1_rules.txt; python3 research/p3/writer_watch.py check-rules --rules $EV/at1_rules.txt > $EV/at1.txt; echo exit=$? >> $EV/at1.txt; ls -d ~/projects/trading/*/artifacts/*/archive_manifest.json >> $EV/at1.txt; find ~/tlos-paper/operator-ledger ~/tlos-paper/p3-evidence ~/projects/trading/trading_lab_os_final/artifacts /mnt/tlos-wdc/tlos-backups -type f -links +1 > $EV/at1_hardlinks.txt` | `at1_rules.txt`, `at1.txt`, `at1_hardlinks.txt` | `RULES = LOADED (9/9 watches)`, `exit=0`, every listed `archive_manifest.json` is under `~/projects/trading/trading_lab_os_final/artifacts/`, and `at1_hardlinks.txt` is empty | `RULES = INCOMPLETE` or `UNPROVEN`; a sealed archive under another checkout (extend the inventory by PR); or any multi-linked file (a second name outside the watch may exist: send to Claude) | NOT_RUN |
| AT-2 authorized write | `T0=$(date +%s)`; wait until after the next `tlos-p3-health.service` run (`systemctl --user list-timers tlos-p3-health.timer`); `snap at2 $T0` | `at2_status.txt`, `at2_rules.txt`, `at2_audit.raw`, `at2_classify.txt` | `at2_classify.txt` ends `INFO unexpected_writer …` then `exit=0`; it has `COUNT tlos_p3_evidence AUTHORIZED n` with n ≥ 1; it has no `UNEXPECTED` or `UNATTRIBUTED` line | any other severity. An UNEXPECTED health-job write (an `exe` outside the system bin dirs, or `auid=4294967295` because the user manager has no login uid) is sent to Claude for a reviewed inventory PR; the host inventory is never edited | NOT_RUN |
| AT-3 canary, both filesystems | `T0=$(date +%s); sleep 1; touch ~/tlos-paper/writer-canary/probe-$T0 /mnt/tlos-wdc/tlos-writer-canary/probe-$T0; sleep 2; snap at3 $T0` | `at3_*` (as AT-2) | `exit=2`; `CRITICAL unexpected_writer`; two `UNEXPECTED tlos_canary` lines, one per probe path, each with `comm='touch' exe='/usr/bin/touch' uid=1000 euid=1000 auid=1000`. Once the check is wired and PLN-06 delivery passes, the same probe must page within 2 minutes (recorded then, not now) | fewer than two canary lines (a filesystem is not watched), or any exit other than 2 | NOT_RUN |
| AT-4 backup night | `T0=$(date +%s)` in the evening; after the backup: `systemctl --user show tlos-p3-backup.service -p Result -p ExecMainExitTimestamp > $EV/at4_unit.txt; snap at4 $T0` | `at4_unit.txt`, `at4_*` (as AT-2) | `Result=success`; `exit=0`; `COUNT tlos_backups AUTHORIZED n` with n ≥ 1; no `UNEXPECTED`, `UNATTRIBUTED` or `coverage gap` line | any UNEXPECTED or UNATTRIBUTED backup event (for the volume-export helper, check its `auid` first: the inventory expects `4294967295`), or a coverage gap | NOT_RUN |
| AT-5 loss detection | after AT-2..AT-4: `{ sudo auditctl -s; grep -E '^(num_logs\|max_log_file\|max_log_file_action) ' /etc/audit/auditd.conf; } > $EV/at5_status.txt; grep -E '^(lost\|pid\|backlog\|backlog_limit) ' $EV/at5_status.txt; grep -lE 'lost [0-9]+ event\|backlog saturated\|coverage gap\|below the baseline\|not connected\|no lost baseline' $W/*/at[234]_classify.txt \|\| echo NO_LOSS_FINDINGS` | `at5_status.txt` (plus the terminal output, copied into `$EV/at5.txt`) | `lost` equals `$BASE`; `pid` ≠ 0; `backlog` < `backlog_limit`; `max_log_file_action = ROTATE` with `num_logs × max_log_file` above one day of audit volume; `NO_LOSS_FINDINGS`. A forced-overflow test is out of scope on production | `lost` above `$BASE`, `pid 0`, or any loss finding | NOT_RUN |
| AT-6 overhead | `journalctl --user -u tlos-p3-backup.service -o short-iso-precise --since "-14 days" \| grep -E 'Starting\|Finished\|Consumed' > $EV/at6_journal.txt`; tabulate the Starting→Finished duration of at least 3 runs before the install and the first run after it, in `$EV/at6_overhead.txt` | `at6_journal.txt`, `at6_overhead.txt` | the table is recorded and the increase is ≤ +20 % | above +20 %: **ESCALATE** to the Owner (decision recorded); never hidden, never a silent PASS | NOT_RUN |
| AT-7 reboot persistence | after the next Owner-authorized reboot: `cp $W/lost_baseline.txt $W/lost_baseline.prev; sudo auditctl -s \| awk '$1=="lost"{print $2}' > $W/lost_baseline.txt; BASE=$(cat $W/lost_baseline.txt)`; then repeat AT-1 and AT-3 (ids `at7_rules`, `at7_canary`) | `$W/lost_baseline.{prev,txt}`, `at7_rules*`, `at7_canary*` | AT-1 PASS and AT-3 PASS with no manual step. The WDC canary event proves the watch attached to the mounted ntfs3 filesystem and not to the bare mount point | either fails. A WDC-only failure means the rules loaded before the mount; the remedy (unit ordering) is an Owner decision, not improvised | NOT_RUN |

Only after AT-0 to AT-7 pass is the check wired into the hourly health run, in a separate PR, and the §19 row moved from NOT_COVERED to COVERED. That PR needs one more Owner decision: the health job runs as uid 1000 and cannot read `/var/log/audit` or run `auditctl -s`/`-l`. A small root-run collector must save those three snapshots for it, and a stale snapshot must read as UNPROVEN. Until then the honest status on the host is **NOT_COVERED**. The Owner may instead accept the gap explicitly in a recorded decision. That is never inferred from silence.

## 9. Verification of this change (cloud, synthetic only)
`tests/test_p3_writer_watch.py` (47 tests, synthetic raw audit lines; no host path is read) covers:
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
- **CLI:** `rules`, `check-rules`, `classify` and `self-test`, with exit codes 0, 1 or 2, run standalone as the runbook invokes them.

Delivery-side tests added with this change (PLN-06-owned files, no new framework):
- `scripts/p3/ops/rules/tlos_p3_alerts.test.yml`: `unexpected_writer` = 2 raises `TLOSHealthCritical` and = 1 raises `TLOSHealthWarning` (`promtool test rules`).
- `tests/test_p3_alerting.py`: with `amtool config routes test`, the template routes everything to `null` until the Owner chooses. After the runbook's edit (Telegram or ntfy), `TLOSWatchdog` goes only to `deadman`, and every critical or warning alert (including `unexpected_writer` and the step-6 `TLOSDeliveryTest`) goes to the chosen channel.

## 10. Round-3 adversarial review (2026-10-28, local staging, synthetic only)
Each defect below had a failing synthetic test before the fix and passes after it. Nothing ran on a host.

| # | Defect at c30be15 | Effect | Fix | Regression test |
|---|---|---|---|---|
| W1 | `exe` was checked only against the system bin prefixes | `comm=python3` from `/usr/bin/perl` was AUTHORIZED | the exe file name must match the same program glob | `test_an_authorized_comm_from_a_different_system_binary_is_unexpected` |
| W2 | a missing `euid` skipped the euid test | an event without `euid` was AUTHORIZED | a missing comm/uid/euid/auid is UNATTRIBUTED | `test_an_event_missing_euid_or_auid_is_never_authorized` |
| W3 | `auid` was not matched | uid 1000 under a root or other login (or no login) was AUTHORIZED | writers declare auids | `test_a_login_identity_other_than_the_owner_is_unexpected` |
| W4 | only the key decided the class; the kernel keeps the first matching rule's key | `rename(p3-evidence/x → h1 lane/x)` by python was AUTHORIZED | the classes of the PATH names (CWD-resolved, `..` folded) are judged too | `test_a_rename_into_a_stricter_class_is_judged_by_every_class_it_touches` |
| W5 | a link/move out of a watched tree was judged by its source class | a hard link of the ledger to `/tmp` was AUTHORIZED; later writes there carry no key | a CREATE outside the protected trees in a link/move is UNEXPECTED | `test_a_hard_link_or_move_out_of_a_watched_tree_is_unexpected` |
| W6 | a no-writer class event lacking comm/uid was UNATTRIBUTED | a sealed/H1/canary write could be WARNING instead of CRITICAL | no-writer classes are UNEXPECTED first | `test_a_write_to_a_no_writer_class_is_critical_even_when_unattributable` |
| W7 | a hex value with a control byte was left encoded | a multi-key (`\x01`) field was ignored entirely | always decode; split keys on `\x01` | `test_a_hex_encoded_multi_key_is_decoded_and_split` |
| W8 | events without a `tlos_` key were dropped | a change taken by another rule's key was invisible | CREATE/DELETE under a protected path is classified | `test_a_change_under_a_protected_path_carrying_another_key_is_still_classified` |
| W9 | a duplicated PATH record was a second name | duplicate input doubled names (and would skew the link/move test) | one name per item number | `test_duplicated_and_out_of_order_records_assemble_into_one_event` |
| W10 | `pid 0` (auditd not connected) was not checked | could be INFO while nothing reached `audit.log` | UNPROVEN | `test_an_auditd_not_connected_to_the_kernel_is_unproven` |
| W11 | `DAEMON_START`/`DAEMON_RESUME` were not gaps | a `kill -9` + restart inside the window was INFO | added to the gap types | `test_a_daemon_start_or_resume_inside_the_window_is_a_coverage_gap` |
| W12 | the lost baseline defaulted to 0; an empty `--lost-baseline` crashed argparse | a run with no recorded baseline could be INFO | missing/unparsable baseline is UNPROVEN | `test_a_missing_or_unparsable_lost_baseline_is_unproven` |
| W13 | rule order put the H1 lane and canary last | a write reaching them via a symlinked name inside `p3-evidence` carried `tlos_p3_evidence` | no-writer classes are rendered first | `test_the_rules_put_the_classes_without_a_lawful_writer_first` |

Changed expectations in existing tests, as the new contract requires: the volume-export helper is lawful only with `auid` unset, and the CLI test passes `--lost-baseline 0`.
