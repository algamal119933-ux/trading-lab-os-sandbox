# P3-PLN-04/07 — Decision H: unattended upgrades under the host freeze (DECIDED: option C; applied on the host 2026-11-03)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-04 and PLN-07 (frozen at fcd06b21), executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1). The finding comes from
[`PLN_04_RECOVERY.md`](PLN_04_RECOVERY.md), "Finding: unattended-upgrades mutates the host automatically (Owner
decision)". That record names it decision packet item H, with options (a), (b) and (c), which correspond to A, B
and C below.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO

```text
DECISION_H            = DECIDED — option (C), security-only in a fixed window; Owner decision U1, 2026-11-03
HOST SETTINGS CHANGED = APPLIED by the Owner 2026-11-03T14:27:13Z (U1) — §5 is the application record;
                        §4 below is the text as prepared and stays unchanged
FIRST WINDOW          = 2026-11-04T04:20:00Z — its package delta is still to be verified (§5.4)
```

## 1. Facts
All from [`PLN_04_RECOVERY.md`](PLN_04_RECOVERY.md), as read from the gap attestation the Owner attached
(OWNER-ATTACHED). Claude has not read the host's apt configuration.

- `unattended-upgrade` is active on `hamza-workstation`. On 2026-10-27, from 06:58:37 to 07:00:40 Cairo, it
  upgraded packages with no per-step authorization.
- It upgraded the NVIDIA 595 driver stack (595.91 → 595.99) and its kernel modules, and removed
  `nvidia-firmware-595-595.91.07`. These take effect at the next boot.
- It also upgraded `openssh-server`, `sudo`, `git`, `curl`, `ca-certificates`, `libnss3`, `tzdata`, poppler and
  freerdp.
- It touched none of node-exporter, auditd, Docker or systemd. It happened after RUN 3's window, so the reboot
  verdict stands.
- **The governance gap:** the freeze rule "do not modify the host without explicit Owner authorization" is not
  enforced against the OS's own updater. And `verify-boot` does not record package changes. The gap attestation
  had to reconstruct them from `dpkg.log`.
- **Unknown:**
  - the exact apt policy on the host: `Allowed-Origins`, whether third-party origins are allowed, and
    `Automatic-Reboot`;
  - whether `needrestart` is installed, and in which mode;
  - the `apt-daily-upgrade.timer` schedule.

  §4.0 reads them.

## 2. The options
| | (A) Accept automatic security updates | (B) Suspend during freezes | (C) Controlled maintenance window + emergency-security exception |
|---|---|---|---|
| What | Leave unattended-upgrades on, as today. Record it as baseline host behaviour. Every verify-boot records the package delta, and the delta is not drift | Keep today's behaviour, but turn installation off for each declared freeze (a reboot test, an acceptance run, a launch). Turn it back on afterwards | Security origins only. Install at a fixed, recorded time (no random delay), never right after a boot. No automatic reboot. Suspend during declared freezes. An out-of-window install only for an urgent security fix, with a record |
| Security | Best patch latency | Latency grows with the length of each freeze (PLN-10 may last days) | Latency at most one window interval. Urgent fixes go out immediately through the exception |
| Freeze compliance | **None.** The updater can change the host inside any freeze or acceptance window | Good, inside declared freezes | Good, inside declared freezes |
| Evidence | Possible, but the timing is random (`RandomizedDelaySec`), so changes can land anywhere, including right after a reboot (`Persistent=true`) | As for A, outside freezes | Changes happen only in known windows. Each one is attributable and recorded |
| Burden | None | Two actions per freeze | One-time setup, plus the freeze actions, plus a record per exception |
| Risk | Unattributed drift during acceptance runs. A driver or kernel change that is activated by an unrelated reboot | Forgetting to re-enable, which leaves security patches off | Small misconfiguration risk, which the verification in §4.3 checks |

## 3. Recommendation (Claude's, labeled; the Owner decides)
**RECOMMENDATION: (C)**, configured as follows:
- **Origins:** security origins only (`${distro_id}:${distro_codename}-security`, plus the ESM security origins,
  which match nothing without Ubuntu Pro).
- **Window:** a **daily** window at a fixed UTC time, with no random delay and `Persistent=false`, so a missed
  window never fires at boot. Daily keeps patch latency at no more than about a day. A weekly window is a lawful
  alternative if the Owner prefers less churn. The window must avoid the 03:30 UTC backup and the top-of-hour
  health run; **04:20 UTC** is the placeholder.
- **Reboots:** `Automatic-Reboot "false"`. If `/var/run/reboot-required` appears, the Owner schedules a reboot
  with a fresh baseline and `verify-boot`.
- **needrestart:** if installed, set to list-only (`$nrconf{restart} = 'l'`), so services (Docker among them) are
  not restarted silently.
- **Freeze suspension:** a single drop-in file that turns installation off. It survives reboots and is removed at
  freeze end. Both acts are recorded.
- **Emergency exception:** an urgent security fix is installed out of window, with a record.
- **Package delta as evidence:**
  - a package list and its sha256 are saved with every pre-reboot baseline;
  - every verify-boot is followed by the delta (§4.6);
  - recording the package-set digest inside `recovery.py snapshot` and verify-boot, as "recorded, not drift", is a
    proposed later code change, not part of this packet.

Why not A: it leaves the freeze rule unenforceable during the PLN-10 acceptance run, where attribution matters
most. Why not B alone: it keeps random timing outside freezes, including `Persistent` installs right after a boot,
and it depends on remembering to re-enable.

## 4. Procedures for later Owner execution (all NOT_RUN; each step needs explicit authorization)
### 4.0 Inspect first (read-only)
```bash
out=~/tlos-paper/p3-evidence/apt_policy_$(date +%Y%m%dT%H%M%S).txt
[ -e "$out" ] && echo "STOP: $out exists" || {
{
echo "== 20auto-upgrades";   cat /etc/apt/apt.conf.d/20auto-upgrades 2>&1
echo "== effective policy";  apt-config dump | grep -E '^(APT::Periodic|Unattended-Upgrade::(Allowed-Origins|Origins-Pattern|Automatic-Reboot|Package-Blacklist|Remove))'
echo "== timers";            systemctl list-timers 'apt-daily*' --all --no-pager; systemctl cat apt-daily-upgrade.timer --no-pager
echo "== packages";          dpkg -l unattended-upgrades needrestart 2>&1 | tail -2
echo "== needrestart mode";  grep -rhE '^\s*\$nrconf\{restart\}' /etc/needrestart/ 2>/dev/null || echo "(default)"
echo "== dry run";           sudo unattended-upgrade --dry-run -d 2>&1 | grep -E 'Allowed origins|Packages that will be upgraded' | head
echo "== last runs";         tail -30 /var/log/unattended-upgrades/unattended-upgrades.log 2>&1
} > "$out" 2>&1; cat "$out"; }
```
Attach the output. If the dry run lists an origin other than the security origins (for example a third-party
repository), that is recorded before anything changes.

### 4.1 Implement (C)
Override files are added. The distribution's own `20auto-upgrades` and `50unattended-upgrades` are not edited, so
rollback is deletion.
```bash
# 1. Policy: security origins only, no automatic reboot. "#clear" replaces the lists rather than appending to them.
sudo tee /etc/apt/apt.conf.d/52tlos-unattended-policy >/dev/null <<'EOF'
// TLOS decision H (C): governed unattended upgrades. Remove this file to roll back.
#clear Unattended-Upgrade::Allowed-Origins;
#clear Unattended-Upgrade::Origins-Pattern;
Unattended-Upgrade::Allowed-Origins {
        "${distro_id}:${distro_codename}-security";
        "${distro_id}ESMApps:${distro_codename}-apps-security";
        "${distro_id}ESM:${distro_codename}-infra-security";
};
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::SyslogEnable "true";
EOF

# 2. The window: fixed time, no random delay, never at boot.
sudo mkdir -p /etc/systemd/system/apt-daily-upgrade.timer.d
sudo tee /etc/systemd/system/apt-daily-upgrade.timer.d/50-tlos-window.conf >/dev/null <<'EOF'
[Timer]
OnCalendar=
OnCalendar=*-*-* 04:20:00 UTC
RandomizedDelaySec=0
Persistent=false
EOF
sudo systemctl daemon-reload && sudo systemctl restart apt-daily-upgrade.timer

# 3. needrestart (only if installed): list, never restart services by itself.
dpkg -s needrestart >/dev/null 2>&1 && printf '%s\n' '# TLOS decision H' "\$nrconf{restart} = 'l';" \
  | sudo tee /etc/needrestart/conf.d/50-tlos.conf >/dev/null
```
### 4.2 Freeze suspension and the emergency exception
```bash
# Freeze start: installation off (survives reboots). The timer still fires, but installs nothing.
echo 'APT::Periodic::Unattended-Upgrade "0";' | sudo tee /etc/apt/apt.conf.d/99tlos-freeze >/dev/null
apt-config dump | grep 'APT::Periodic::Unattended-Upgrade'          # expect "0"
# Freeze end:
sudo rm /etc/apt/apt.conf.d/99tlos-freeze; apt-config dump | grep 'APT::Periodic::Unattended-Upgrade'   # expect "1"

# Emergency security exception (out of window): within the same policy, then record it.
sudo unattended-upgrade -v 2>&1 | tee ~/tlos-paper/p3-evidence/emergency_upgrade_$(date +%Y%m%dT%H%M%S).txt
```
Each freeze start and end, and each exception, gets a line in the next P3 record:
- the UTC time;
- the reason: the freeze name, or the USN/CVE for an exception;
- the packages changed, from `dpkg.log`;
- whether a reboot is required.

### 4.3 Verify (C) after implementing
```bash
apt-config dump | grep -E 'Unattended-Upgrade::(Allowed-Origins|Automatic-Reboot)'
systemctl show apt-daily-upgrade.timer -p TimersCalendar -p RandomizedDelayUSec -p Persistent --no-pager
systemctl list-timers apt-daily-upgrade.timer --no-pager            # NEXT = the window
sudo unattended-upgrade --dry-run -d 2>&1 | grep 'Allowed origins'  # security origins only
[ -f /etc/needrestart/conf.d/50-tlos.conf ] && cat /etc/needrestart/conf.d/50-tlos.conf
```
**PASS requires all of the following:**
- the allowed origins are exactly the security entries;
- `Automatic-Reboot "false"`;
- the timer calendar is the window, with `RandomizedDelayUSec=0` and `Persistent=no`;
- after the next window, `unattended-upgrades.log` shows a run at the window time and none at any other time.

### 4.4 Rollback
```bash
sudo rm -f /etc/apt/apt.conf.d/52tlos-unattended-policy /etc/apt/apt.conf.d/99tlos-freeze /etc/needrestart/conf.d/50-tlos.conf
sudo rm -f /etc/systemd/system/apt-daily-upgrade.timer.d/50-tlos-window.conf
sudo systemctl daemon-reload && sudo systemctl restart apt-daily-upgrade.timer
apt-config dump | grep -E 'Unattended-Upgrade::Allowed-Origins' ; systemctl list-timers apt-daily-upgrade.timer --no-pager
```
This restores exactly the distribution's behaviour as found in §4.0.

### 4.5 Option (A) or (B) instead
- **(A):** no change. Run §4.0 once and attach it as the recorded baseline behaviour. Use §4.6 for every
  verify-boot.
- **(B):** only §4.2's freeze suspension, plus §4.6.

### 4.6 How verify-boot and health would record the package delta (all options)
Today, `recovery.py` snapshot and verify-boot do not record packages, and health has no package finding. Until a
later code change adds a package-set digest to the snapshot, the record is kept beside each baseline:
```bash
# with every pre-reboot baseline:
p=~/tlos-paper/p3-evidence/packages_$(date -u +%Y%m%dT%H%M%SZ).txt
dpkg-query -W -f='${binary:Package} ${Version}\n' | sort > "$p"; sha256sum "$p"
# after every boot / verify-boot:
q=~/tlos-paper/p3-evidence/packages_$(date -u +%Y%m%dT%H%M%SZ).txt
dpkg-query -W -f='${binary:Package} ${Version}\n' | sort > "$q"; sha256sum "$q"
diff "$p" "$q" && echo "PACKAGE_DELTA = NONE" || echo "PACKAGE_DELTA = PRESENT (listed above; classified per decision H)"
awk -v since="<baseline UTC as YYYY-MM-DD HH:MM:SS, converted to local>" '$1" "$2 >= since && ($3=="install"||$3=="upgrade"||$3=="remove"||$3=="purge")' /var/log/dpkg.log
```
How the delta is classified:
- under (C), a delta is lawful only if every change falls inside a recorded window or exception;
- under (B), a delta inside a declared freeze is drift;
- under (A), a delta is recorded and is not drift.

Proposed later changes, not made here:
- `recovery.py`: a `package_set_sha256` field and a verify-boot "recorded, not drift" check. This is Lane B code;
- `health.py`: a `reboot_required` and last-unattended-run finding. This is Lane A, PLN-06.

## 5. Owner decision and host application record (2026-11-03)
Host evidence lives in `~/tlos-paper/p3-evidence/` on hamza-workstation. It is not committed, and is cited by
sha256 below.

### 5.1 The decision
The Owner approved option (C), referred to as U1. It covers:
- security origins only;
- a fixed window at **04:20 UTC**, which is always 50 minutes after the 03:30 UTC backup, in both seasons;
- `Automatic-Reboot` and `Automatic-Reboot-WithUsers` set to `"false"`;
- the experiment freeze switch;
- no run while the backup is running;
- a package baseline before the first run, and a package delta after every run;
- the original configuration and its hashes kept.

Two settings are deliberately not changed:
- **Metered connections:** not overridden. The Owner first confirms the tariff.
- **Snap refresh schedule:** unchanged, until a specific conflict is shown.

### 5.2 What was installed
Four new files were installed, and no vendor file was edited:

| File | sha256 |
|---|---|
| `/etc/apt/apt.conf.d/52tlos-unattended-upgrades` | `90dc0367…b1d060` |
| `/etc/systemd/system/apt-daily-upgrade.timer.d/50-tlos-window.conf` | `4a5d7b60…4360e3` |
| `/etc/systemd/system/apt-daily-upgrade.service.d/50-tlos-freeze-delta.conf` | `855dff09…3277f9` |
| `/usr/local/sbin/tlos-apt-delta` (v2) | `9c1e30a0…e9f1fa` |

The vendor files `10periodic`, `20auto-upgrades`, `50unattended-upgrades` and the `apt-daily-upgrade` timer and
service units match their recorded pre-U1 hashes.

Differences from the §4.1 text as prepared:
- **No `Origins-Pattern` clear:** the vendor file sets no `Origins-Pattern`. The effective configuration was
  verified to contain exactly the three `-security` origins.
- **The window:** it is the fixed `04:20 UTC` timer, with `RandomizedDelaySec=0` and `Persistent=false`.
- **The freeze:** it is enforced by an `ExecCondition` hook (`/etc/tlos/apt-freeze`, or the backup unit
  running). A skipped run is SKIPPED, not FAILED.
- **The delta:** a per-run `/var/log/tlos-apt/delta-<UTC>.txt` (+ `.sha256`, directory `root:adm 0750`).
- **`needrestart`:** not installed, so no service is restarted by a run.

The two hook fixes made before application are:
- **v1 → v2, freeze delta:** systemd runs `ExecStopPost` after an `ExecCondition` skip, but not `ExecStartPre`. In
  v1, a frozen day therefore wrote a diff against a stale or missing `pre.list`. v2 pairs pre and post through
  `run.pending`, so a skipped run records "skipped", never a diff. This was reproduced and then tested through
  user systemd.
- **Backup guard:** the guard tests the `tlos-p3-backup.service` cgroup. A backup started by hand is not
  detected, so set the freeze for it.

The preflight of the apply script was hardened before the Owner ran it:
- **Backup check:** it uses the set's own `VERIFY = PASS` journal line and the record-digest match, rather than
  the unit `Result`. After a reboot, `Result` reads `success` for a unit that has not run.
- **`sudo` and `fuser`:** a `sudo -v` / `fuser` failure stops the run.

### 5.3 Application and independent verification
- **Applied by:** the Owner, in a local terminal, at `2026-11-03T14:27:13Z` on boot `f9c2931f`.
- **Apply script and result:** `u1_apply.sh` sha256 `0db1841a…919485`. PREFLIGHT PASS and 14/14 checks PASS. It
  installed no packages, started no update, did not reboot, and did not touch SSH, UFW, Tailscale or Docker.
- **Independent check by Claude** (`u1_verification_20261103T143054Z.md`, sha256 `6ab874f0…7f5b`):
  - the installed hashes match;
  - the effective origins are exactly the three `-security` origins;
  - automatic reboot is off;
  - the timer is `*-*-* 04:20:00 UTC`, next run `2026-11-04T04:20:00Z`;
  - the freeze file is absent;
  - the package set is unchanged;
  - the only system event was one `daemon-reload`;
  - `RUNTIME_VERIFY` 23/23 and health INFO;
  - Docker 7/7 required containers running;
  - backup 8/8 sets digest-OK.
- **`U1 = PASS`.**

### 5.4 Still open
- **U1-D1:** verify the first window's `/var/log/tlos-apt/delta-*.txt`:
  - the result line;
  - the pre/post hashes;
  - the package lines, or "skipped";
  - the `reboot-required` line.

  Then re-run health and `RUNTIME_VERIFY`.
- **Outside this policy, by design:** the desktop Software Updater, or any manual `apt`, installs everything.
  On 2026-11-03, before U1, it installed 104 package actions, Docker and systemd included, and was followed by a
  reboot. See [`PLN_04_RECOVERY.md`](PLN_04_RECOVERY.md) §"Out-of-band update and unplanned reboot (2026-11-03)".
  Classification under (C): that delta predates the decision and is recorded as an out-of-band host event, not
  as a lawful window run.
- **The §4.6 code changes** (`package_set_sha256` in `recovery.py`, a `reboot_required` health finding) remain
  proposals.
