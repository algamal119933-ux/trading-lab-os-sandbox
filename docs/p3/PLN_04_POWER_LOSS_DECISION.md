# P3-PLN-04 — Power-loss posture: decision packet G (prepared for the Owner; nothing purchased or configured)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-04 (frozen at fcd06b21; it lists "Power-loss posture
(6 unclean losses; UPS)"), §6 known blocker "Repeated unclean power loss, no UPS recorded → a UPS, or an accepted
power-loss posture, as an Owner decision". Executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1), which states "The PLN-04
power posture (UPS) is an Owner decision". The acceptance record is
[`PLN_04_RECOVERY.md`](PLN_04_RECOVERY.md), where the power-loss posture is `OPEN` (decision packet G).
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO

```text
PLN-04 POWER-LOSS POSTURE  = OPEN (this packet; the Owner decides)
PLN-04                     = not CLOSED until a posture is recorded
```

Every command here is `NOT_RUN`. Each is a host change or a host read that needs the Owner's explicit
authorization. Claude has no host access and purchased, installed and configured nothing.

## 1. Facts (repository evidence)
| Fact | Source | Label |
|---|---|---|
| 6 unclean host-down intervals, 2026-09-28 → 2026-10-23, consistent with power loss: 3.5 h, 5.4 h, 3.7 h, 3.0 h, 20.3 h, 18.5 h | [`P2_CLOSURE.md`](../p2/P2_CLOSURE.md) §4; [`P3_PLN_00_P2_TO_P3_RECONCILIATION.md`](../p2/P3_PLN_00_P2_TO_P3_RECONCILIATION.md) | CLAUDE-VERIFIED (read in the repository) |
| Effect on P2: 74 bar-hours per pair UNEXPLAINED, all inside those intervals; never filled | P2_CLOSURE §4–§5 (F-1) | CLAUDE-VERIFIED (record) |
| A 7th event: REBOOT RUN 1, 2026-10-26 ~10:54 Cairo. The previous boot's journal ended mid-activity, with no system-manager shutdown lines: power loss | [`PLN_04_RECOVERY.md`](PLN_04_RECOVERY.md) reboot record | CLAUDE-VERIFIED output |
| After RUN 1, verify-boot showed the stack recovered. Its single FAIL was a baseline drift, not a power defect | same | CLAUDE-VERIFIED output |
| No UPS is recorded | contract §6 | — |
| Whether the host powers on by itself when mains returns (BIOS "Restore on AC power loss") | not recorded | **UNKNOWN** |
| Whether the multi-hour intervals were grid outages, or short outages followed by the host staying off until someone pressed the power button | not recorded | **UNKNOWN** |

That is **at least 7 unclean losses in 29 days**. The interval lengths matter for the choice. A UPS rides through
minutes, not hours. If the outages really last hours, a UPS can turn an unclean loss into a clean shutdown, but it
cannot keep the host up.

## 2. What an unclean loss risks here
- **Recorded gaps.** Missed bars are recorded and never filled (contract §4). During a Paper Beta acceptance run
  (PLN-10), each outage costs coverage and adds an unexplained interval to explain.
- **Write-in-flight corruption.** Possible targets:
  - Freqtrade's SQLite trade database, when a paper runtime runs;
  - Prometheus TSDB (WAL replay on start);
  - the Grafana and MLflow volumes;
  - a capture-loop ledger append;
  - a backup set being written.

  Backup sets are written to a `.incoming` staging directory and renamed only when complete. The health check's
  `backup_recency` ignores hidden directories, so a torn set is never taken as the newest. A leftover
  `.<stamp>.incoming` directory is not cleaned automatically.
- **Hardware.** The WDC HDD and the NVMe, from a power cut during a write, or a surge on return.
- **Evidence ambiguity.** `verify-boot` cannot tell a clean boot from an unclean one. Only the previous boot's
  journal can (runbook §4 `UNCLEAN_SHUTDOWN`).

What already limits the damage, all CLAUDE-VERIFIED in the repository:
- `restart: unless-stopped` in the compose files;
- the terminal-state guard `recovery.py may-restart` (F-5), with negative tests;
- `nofail` for the WDC;
- daily verified backups, with restore drills passing (PLN-03);
- hourly health with `backup_recency` (RPO 26 h);
- ledgers that are hash-chained.

## 3. Options
### Option A — a UPS with NUT-triggered clean shutdown
**What:** a line-interactive UPS with a USB HID link, plus Network UPS Tools (NUT) in standalone mode. When the UPS
is on battery and reaches low battery, `upsmon` runs a clean `shutdown`. When mains returns, the host boots, if
BIOS is set to power on.

| Item | Detail |
|---|---|
| Evidence the Owner provides | UPS make and model, VA/W rating, and the measured workstation load (the GPU matters). Runtime at that load: at least 10 min recommended, so NUT has margin. The BIOS AC-recovery setting. That the WDC is on the protected outlets |
| Host changes (NOT_RUN; authorization needed) | `sudo apt install nut`. Config files under `/etc/nut/` (below). Enable `nut-server` and `nut-monitor` |
| Acceptance criteria | (1) `upsc tlosups@localhost` shows `ups.status: OL`, a battery charge and a runtime. (2) A **controlled FSD test** in a maintenance window: `sudo upsmon -c fsd` produces a clean shutdown, and the previous boot's journal shows `upsmon` and `Reached target … shutdown.target`. (3) After power-on, `recovery.py verify-boot` against a baseline taken just before the test passes 10/10, health is INFO, and the newest backup set verifies. (4) Optional: a real pulled-plug test, recorded the same way |
| What verify-boot / health record | verify-boot: `rebooted`, mounts, user units, containers, paper-runtime states, as today. The clean/unclean classification comes from `journalctl -b -1`. NUT is a system service, so it is not in verify-boot's user-unit set; tracking it would be a later baseline change |
| Residual risk | Outages longer than the runtime still stop the host, cleanly, and leave recorded gaps. UPS battery ageing (replace every 3–5 years; NUT reports `battery.charge` and `ups.status RB` on some models). A UPS failure is a new single point of failure unless bypassed. Cost |

Configuration for later Owner execution (NOT_RUN). `primary` needs NUT ≥ 2.8; older versions use `master`.
```text
/etc/nut/nut.conf        MODE=standalone
/etc/nut/ups.conf        [tlosups]
                           driver = usbhid-ups
                           port = auto
                           desc = "hamza-workstation UPS"
/etc/nut/upsd.users      [upsmon_local]
                           password = <generated on the host; never committed>
                           upsmon primary
/etc/nut/upsmon.conf     MONITOR tlosups@localhost 1 upsmon_local <same password> primary
                         SHUTDOWNCMD "/sbin/shutdown -h +0"
```
Verify: `upsc tlosups@localhost ups.status battery.charge battery.runtime`, then
`systemctl is-active nut-server nut-monitor`.

Rollback: `sudo systemctl disable --now nut-monitor nut-server`, then `sudo apt remove nut`. The config files
stay, and nothing else is changed.

### Option B — an accepted-risk posture (no UPS)
**What:** the Owner records that unclean power loss is an accepted host risk. The system relies on the existing
controls in §2, plus a fixed **post-power-loss procedure** run after every unexpected boot.

| Item | Detail |
|---|---|
| Evidence the Owner provides | A signed-off statement accepting the observed rate (≥ 7 in 29 days) and its effect on coverage. The BIOS AC-recovery setting. Whether a paper runtime will run during outages (PLN-10) |
| Host changes | None |
| Post-power-loss procedure (read-only; NOT_RUN) | See the block below |
| Acceptance criteria | (1) The posture is recorded and merged by the Owner. (2) The procedure is executed **after the next unclean boot**, and its output is attached showing: verify-boot PASS against the current baseline; health INFO or explained; the newest set verifying; no ext4 or I/O errors; and, if a paper runtime ran, the SQLite integrity check `ok`. (3) Each event is entered in a power-event register (§4) |
| What verify-boot / health record | The same as today. The `UNCLEAN_SHUTDOWN` classification comes from the procedure's journal lines |
| Residual risk | Torn writes and possible SQLite or TSDB corruption, detected after the fact rather than prevented. Hardware wear from repeated cuts. Coverage loss in PLN-10. The 7-in-29-days rate makes a long acceptance run likely to include unclean events |

The post-power-loss procedure:
```bash
out=~/tlos-paper/p3-evidence/power_event_$(date +%Y%m%dT%H%M%S).txt
[ -e "$out" ] && echo "STOP: $out exists" || {
{
echo "== boots"; journalctl --list-boots --no-pager | tail -3
echo "== previous boot: last lines and shutdown targets (none = UNCLEAN)"
journalctl -b -1 --no-pager -n 5
journalctl -b -1 --no-pager _PID=1 | grep -E "Reached target (reboot|shutdown|final|poweroff)\.target" | tail -3
echo "== verify-boot"
(cd ~/projects/trading/tlos-p3 && python3 scripts/p3/recovery.py verify-boot --before ~/tlos-paper/p3-evidence/<current baseline>.json)
echo "== health";  (cd ~/projects/trading/tlos-p3 && python3 scripts/p3/health_check.py); echo "health_exit=$?"
echo "== newest backup set"; last=$(ls -1d /mnt/tlos-wdc/tlos-backups/2* | tail -1)
(cd ~/projects/trading/tlos-p3 && python3 scripts/p3/backup.py verify --set "$last")
ls -1a /mnt/tlos-wdc/tlos-backups | grep incoming || echo "no leftover staging"
echo "== file-system / disk errors this boot (empty = none)"
journalctl -b -k --no-pager | grep -iE "EXT4-fs (error|warning)|I/O error|blk_update_request" | head
} > "$out" 2>&1; cat "$out"; }
```
If a paper runtime ran, add `sqlite3 <its tradesv3 db> "PRAGMA integrity_check;"`, which only reads.

### Option C — hybrid: B now, A before the Paper Beta acceptance run
**What:** record B immediately, with an **expiry**. Install and test A before the PLN-10 acceptance run starts.
If A is not accepted by then, PLN-10 runs under B, and its record states so.

| Item | Detail |
|---|---|
| Evidence the Owner provides | B's evidence now. A's evidence before PLN-10 |
| Acceptance criteria | B's criteria now, which is enough to record PLN-04's posture. A's criteria before PLN-10, recorded as an update to this packet |
| Residual risk | B's risk until A is accepted. Then A's |

## 4. Power-event register (any option)
Append one row per unexpected boot, in a P3 record on the next PR, only from attached output:
```text
EVENT  boot <prev> → <new>  last journal <utc>  first journal <utc>  down <h>  class UNCLEAN/CLEAN(UPS)
       verify-boot <PASS n/n | FAIL…>  health <sev>  newest set <stamp> VERIFY <…>  fs errors <none|…>  [OWNER-ATTACHED]
```

## 5. Recommendation (Claude's, labeled; the Owner decides)
**RECOMMENDATION: Option C.** Reasons:
- The observed rate (≥ 7 unclean losses in 29 days) is high enough that a multi-day PLN-10 run will very likely
  meet one. Only a UPS converts those into clean shutdowns.
- But the purchase, the sizing and the BIOS check are Owner-side and take time. B unblocks PLN-04 now without
  pretending the risk is gone.

Two Owner facts could change this:
- if the BIOS does not power on after AC returns, set it first, under every option. Otherwise each outage ends
  only when someone presses the button;
- if the multi-hour intervals were mostly long grid outages, a UPS buys clean shutdowns but not uptime, and B may
  be judged enough.

**This recommendation decides nothing.** PLN-04's power-loss posture stays OPEN until the Owner records A, B
or C.
