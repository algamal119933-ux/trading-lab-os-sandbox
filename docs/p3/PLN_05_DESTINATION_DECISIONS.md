# P3-PLN-05 — Tier-3 destination decisions (recorded 2026-10-27)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-05 (frozen at fcd06b21), executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1). The procedure is
[`PLN_05_TIER3_PROCEDURE.md`](PLN_05_TIER3_PROCEDURE.md).
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO

```text
PLN-05 TIER-3 ACCEPTANCE = OPEN
HOST_LOSS_REDUNDANCY     = NOT_PROVEN
```

Nothing in this record ran on any machine. It grants no access and claims no transfer or restore.

## 1. Owner decision: the Toshiba USB disk (2026-10-27)
| Field | Decision |
|---|---|
| Device | Toshiba MQ04UBD200, a 2 TB USB disk with about 1.4 TB free. Owner-reported. |
| Role | **Personal, portable storage.** It is connected only when the Owner needs it, and may be disconnected at any time. |
| Existing data | Preserve all of it. **Never** format, repartition, erase or modify the disk. |
| Scheduled backups | **None.** No automatic or scheduled TLOS backup may target it. It is not an operational dependency of any timer, health check or acceptance step. |
| Allowed use | Optional, **Owner-initiated** copies only, for example a manual copy of a verified backup set. |
| Tier-3 | It **does not satisfy Tier-3**. It is portable, and it is attached to and powered from the primary host when in use. A total loss of the workstation can take it too. |

## 2. Candidate destination: the Owner's second computer
**Identity:** the Claude desktop link reports a Windows x64 computer named `desktop-hvh1jbn`. That this is the second computer the Owner means is **not yet Owner-confirmed**. Drives, free space, WSL, ssh and Tailscale are all UNKNOWN. **No change may be made to that computer** without explicit Owner authorization.

Assessed against [`PLN_05_TIER3_PROCEDURE.md`](PLN_05_TIER3_PROCEDURE.md) §2:

| Requirement | Assessment |
|---|---|
| Separate hardware | Met. It is a different physical computer. |
| Separate power | UNKNOWN. It qualifies if it is on a different circuit or a UPS. Otherwise the record must state a **residual site/power risk**: host loss is covered, site loss is not. |
| Separate failure domain | Partly met. A different machine, but a site-level loss (fire, theft) is shared if both are in the same home. |
| Separate credentials | A dedicated append-only account (§4), inside WSL. Not the Owner's Windows account. |
| Reachable over ssh | The workstation already runs Tailscale, so Tailscale on the PC is the simplest path. A LAN address is the alternative. |
| Linux shell with `rsync` and `sha256sum` | Not met on native Windows. **Recommended path: WSL2 (Ubuntu) with `openssh-server` and `rsync`.** With that, `scripts/p3/offsite.py` and the restore drill are reused unchanged (WRAP_EXISTING; no new tool). |
| Capacity | 30 GB free minimum, 50 GB or more recommended, on the drive that holds the WSL distribution or the chosen directory. UNKNOWN. |
| Availability | A push succeeds only while the PC is on and reachable. An offsite-recency health finding (procedure §7) must alert when it is not. That is a later PLN-06 change. |

**Restore proof:** `HOST_LOSS_REDUNDANCY = PROVEN` only after a set pulled **from that PC** passes the `backup.py drill` checks on a machine that is not the primary, for example inside WSL on the PC. If Docker is unavailable there, the config-load leg is recorded as NOT RUN, not PASS.

## 3. Minimum Owner inputs (nothing else is needed)
1. Confirm the second computer is `desktop-hvh1jbn`, or name the machine.
2. Is WSL2 installed? If not, do you approve installing WSL2 (Ubuntu) with `openssh-server` and `rsync` on it? That is a host change on that PC.
3. Is it on Tailscale, or what is its LAN address? Is it usually on every day?
4. Which drive and directory to use, and its free space (at least 30 GB)?
5. Is it on a separate power circuit or a UPS? If not, do you accept the residual site/power risk?
6. Do you approve installing the dedicated key and the forced-command gate (procedure §4) on it?

Until these are answered and the planned reboot acceptance is recorded, PLN-05 Tier-3 stays **OPEN**.
