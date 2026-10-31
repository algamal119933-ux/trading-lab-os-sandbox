# P3-PLN-05 — Tier-3 destination decisions (recorded 2026-10-27, corrected 2026-10-27)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-05 (frozen at fcd06b21), executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1). The procedure is
[`PLN_05_TIER3_PROCEDURE.md`](PLN_05_TIER3_PROCEDURE.md). The read-only check of the portable copy is
[`PLN_05_PORTABLE_COPY_DRILL.md`](PLN_05_PORTABLE_COPY_DRILL.md).
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO

```text
PLN-05 TIER-3 ACCEPTANCE   = OPEN
HOST_LOSS_REDUNDANCY       = NOT_PROVEN
PORTABLE_COPY (Toshiba)    = EXISTS (OWNER-REPORTED) · supplementary · NOT Tier-3
WINDOWS_SIDE_SHA256_CHECK  = NOT_RUN
TIER3_DESTINATION          = NONE CHOSEN (the Windows PC is WITHDRAWN as a destination, §3)
```

Claude ran nothing on any machine for this record. It has not seen the host output behind any OWNER-REPORTED
line. The record grants no access and claims no transfer, verification or restore that Claude saw.

Evidence labels: `CLAUDE-VERIFIED` (Claude ran it or read its output) · `OWNER-REPORTED` (the Owner stated it;
Claude has not seen it) · `NOT_RUN` · `UNPROVEN`.

## 1. Owner decision: the Toshiba USB disk (latest, 2026-10-27)
| Field | Decision / fact | Label |
|---|---|---|
| Device | Toshiba MQ04UBD200, a 2 TB USB disk, about 1.4 TB free when first described | OWNER-REPORTED |
| Role | **Personal, portable storage.** It is connected only when the Owner chooses, and may be disconnected or carried away at any time | Owner decision |
| Existing data | Preserve all of it. **Never** format, repartition, erase or modify the disk, its partitions or its file system | Owner decision |
| Scheduled backups | **None.** No automatic, scheduled or unattended TLOS backup may target it. It is not a dependency of any timer, health check or acceptance step | Owner decision |
| Allowed use | Owner-initiated manual copies of a verified backup set only | Owner decision |
| Copy made | The Owner manually transferred backup set **`20261026T033318Z`** to the disk | OWNER-REPORTED |
| Ubuntu-side verification of the copy | `VERIFY = PASS` (the `scripts/p3/backup.py verify` semantics: `SHA256SUMS` matches the digest pinned in `BACKUP_RECORD.json`, and every listed artifact re-hashes equal) | OWNER-REPORTED — Claude has not seen the output |
| Windows-side SHA-256 verification | **Not established.** No result exists in the repository | `NOT_RUN` (pending; procedure in [`PLN_05_PORTABLE_COPY_DRILL.md`](PLN_05_PORTABLE_COPY_DRILL.md)) |
| Contents | A full P3 set: the five roots (including the runtime checkout with its `.env` and `config.json`, per the PLN-02 inventory), the git bundle, and the Grafana, MLflow and Prometheus volumes. The disk therefore carries credential-bearing files and is handled as sensitive | from [`PLN_03_BACKUP_RESTORE.md`](PLN_03_BACKUP_RESTORE.md) and `scripts/p3/scheduled_backup.sh`; the copy's contents themselves are UNPROVEN |

The Ubuntu-side result becomes `OWNER-ATTACHED` only when the Owner pastes the command and its output: the mount
path, `backup.py verify --set <toshiba path>/20261026T033318Z` with its `VERIFY = PASS` line, and
`sha256sum SHA256SUMS BACKUP_RECORD.json` for that copy. The strongest form also prints the same two hashes for
the original set on the WDC, which proves the copy is the original set and not only self-consistent.

## 2. Owner decision: the secondary Windows computer (2026-10-27)
**Identity:** the Claude desktop link reports a Windows x64 computer named `desktop-hvh1jbn`. That this is the
computer the Owner means is **not yet Owner-confirmed**.

| Field | Decision |
|---|---|
| Role | **Read** the portable copy on the Toshiba disk, **check its integrity**, and possibly run a **controlled restore test** |
| Permanent storage | **No.** The Owner does not want a permanent TLOS backup on that computer's internal drive |
| Allowed writes | A small text report of hashes (no file contents), and, only if the Owner approves it per run, a temporary scratch restore that is deleted at the end ([`PLN_05_PORTABLE_COPY_DRILL.md`](PLN_05_PORTABLE_COPY_DRILL.md) §4) |
| Changes to the computer | None without explicit Owner authorization. Installing WSL, ssh, Tailscale, keys or a gate is not authorized |

## 3. Superseded: the Windows PC as the Tier-3 destination — **WITHDRAWN by Owner decision (2026-10-27)**
The first version of this record (commit `5ce4766`) assessed `desktop-hvh1jbn` as a candidate Tier-3 destination:
WSL2 (Ubuntu) with `openssh-server` and `rsync`, a dedicated append-only account and forced-command gate, and
`scripts/p3/offsite.py` pushing sets to it over Tailscale or the LAN. It listed six Owner inputs for that plan.

The Owner has withdrawn that plan: the PC is not to hold a permanent backup. **That evaluation and its six
inputs no longer apply.** They remain in the git history of this file and are not to be revived without a new
Owner decision.

## 4. Why the portable copy does not satisfy Tier-3
The contract's acceptance is `HOST_LOSS_REDUNDANCY = PROVEN` **by restoring from the independent host**. The
procedure ([`PLN_05_TIER3_PROCEDURE.md`](PLN_05_TIER3_PROCEDURE.md) §2) counts a destination only if a total
loss of `hamza-workstation` cannot also take the copy. Assessed against each criterion:

| Procedure §2 requirement | The Toshiba copy | Met? |
|---|---|---|
| Separate hardware (another computer, NAS, VPS or cloud VM) | A disk, not a host. While it is being written it is a device of the workstation itself, which the table lists as "not accepted" | No |
| Separate power | Bus-powered from the workstation whenever it is in use | No |
| Separate failure domain | Wherever the Owner keeps it. Nothing records or guarantees that it is away from the workstation; when stored beside it, fire, theft and flood take both | Not established |
| Separate credentials (append-only account) | Mounted read-write under the Owner's own account. A ransomware or account compromise while it is attached can encrypt or delete it | No |
| Reachable over ssh | No. It is offline by design | No |
| Linux shell with `rsync` and `sha256sum` on the destination | Not applicable; it is not a host | No |
| Schedule, recency and alerting (procedure §5, §7) | Forbidden by the Owner's decision (§1). The copy is a single point-in-time set and ages without bound, so it cannot meet the 26 h offsite-recency rule | No |
| Restore proven from that destination (procedure §6) | `NOT_RUN`. Even a passing drill from it would prove only that this one portable set restores | No |

**What the copy does provide:** an offline, Owner-held, point-in-time copy of one verified set. While it is
disconnected it is out of reach of anything that compromises the workstation. It is recorded as a supplementary
copy. It does not change `HOST_LOSS_REDUNDANCY`, and no record may cite it as Tier-3.

## 5. Unresolved Tier-3 requirements (all open)
Their testable form, with a measurable PASS and the procedure check for each, is
[`PLN_05_TIER3_PROCEDURE.md`](PLN_05_TIER3_PROCEDURE.md) §10 (T3-R1 … T3-R8).

1. **A destination** of an accepted class (§6), chosen by the Owner, on separate hardware, separate power and a
   separate failure domain from `hamza-workstation`.
2. **Capacity** of at least 30 GB (50 GB or more recommended) on it (procedure §3).
3. **Authenticated append-only transport:** a dedicated account and key, and the forced-command gate reviewed and
   installed by the Owner (procedure §4), or an equivalent append-only control for a non-ssh destination.
4. **A first push** of a verified set with `destination_verify = PASS` (procedure §5).
5. **A restore drill from that destination** on a machine other than the primary where possible, with every
   `backup.py drill` check PASS (procedure §6). This is the act that can make `HOST_LOSS_REDUNDANCY = PROVEN`.
6. **A recurring schedule and an offsite-recency/integrity/capacity alert** (procedure §5, §7). These are needed
   for continued redundancy, after acceptance, and are separate Owner-authorized installs.
7. **Data-at-rest exposure decision:** a set contains the runtime `.env`, `config.json` and service volumes. A
   destination run by a third party needs either the Owner's acceptance of that exposure or client-side
   encryption, which would be a new reuse decision.

## 6. Candidate destination classes (options for the Owner, not a choice)
| Class | What it needs | Fits the existing tool? | Residual risk / cost |
|---|---|---|---|
| **A. Remote VPS or cloud VM** (any provider, Linux) | A small VM with ≥ 30 GB disk; an account `tlos-offsite` and the gate (procedure §4); ssh reachable from the workstation (public address with key-only ssh, or Tailscale on the VM); a provider account and payment by the Owner | Yes: `offsite.py` and the procedure apply unchanged (WRAP_EXISTING). The restore drill can run on the VM itself | Recurring cost. Data sits with a provider, so item 7 applies. The provider account becomes a credential to protect |
| **B. Object storage** (S3-compatible, e.g. Backblaze B2, Cloudflare R2, AWS S3) | A bucket with object lock or versioning for append-only behaviour; a scoped write key; a separate read key for restore | **No.** The procedure §2 places object-only storage out of scope for `offsite.py` (no remote `sha256sum`). It needs a new reuse decision (for example `rclone` or `restic`, AUDIT_BEFORE_USE) and a restore drill that downloads to a non-primary machine | Lowest cost per GB. New tool, new verification semantics, and item 7 applies. Most change of the four |
| **C. A second always-on machine at another site** (a family or office computer, a small Linux box) | Owner-controlled hardware at a different address; Linux or WSL with `rsync`, `sha256sum` and ssh; Tailscale; the account and gate; usually-on availability | Yes, unchanged | No third party, but it depends on another person's site and power. Availability gaps must surface as the recency alert |
| **D. NAS at another site** | A NAS with ssh, `rsync` and `sha256sum` (most offer them), the account and gate, reachable over Tailscale or VPN | Usually yes; the forced-command gate must be checked against the NAS shell | Hardware purchase; same site dependency as C |
| *(Withdrawn)* the Windows PC `desktop-hvh1jbn` | — | — | Withdrawn by the Owner (§3). Even if revived, it shares the Owner's site with the workstation unless it is elsewhere |

Claude does not recommend a class in this record. The choice weighs cost, third-party data exposure and the
Owner's sites, which only the Owner can weigh.

## 7. Minimum Owner inputs now
1. Confirm whether `desktop-hvh1jbn` is the secondary computer (for the read-only drill only).
2. Optionally attach the Ubuntu-side verification output of the Toshiba copy (§1), to move it from OWNER-REPORTED
   to OWNER-ATTACHED.
3. Optionally run the read-only Windows check ([`PLN_05_PORTABLE_COPY_DRILL.md`](PLN_05_PORTABLE_COPY_DRILL.md)
   §3) and attach its report.
4. **For Tier-3:** choose a destination class from §6 (or another accepted class), then supply the procedure §9
   inputs for it.

Until a destination is chosen, pushed to and restored from, PLN-05 Tier-3 stays **OPEN** and
`HOST_LOSS_REDUNDANCY = NOT_PROVEN`.
