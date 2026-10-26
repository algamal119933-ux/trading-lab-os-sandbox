# P3-PLN-05 — Tier-3 independent-host backup and restore procedure (prepared, not executed)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-05 (frozen at fcd06b21), executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1).
The execution record is [`PLN_05_EVIDENCE_DURABILITY.md`](PLN_05_EVIDENCE_DURABILITY.md).
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO

**Acceptance (contract):** `HOST_LOSS_REDUNDANCY = PROVEN` by **restoring from the independent host**.

Status today: `HOST_LOSS_REDUNDANCY = NOT_PROVEN`. No independent host exists. This document grants no access,
assumes no access, and claims no transfer or restore.

## 1. Reuse decision
`scripts/p3/offsite.py`, merged in PR #78, is reused as it is (reuse class WRAP_EXISTING: rsync plus sha256sum).

What it already does:
- It refuses to push a set that does not verify locally (`backup.verify_backup`).
- It is append-only. An existing remote set is re-verified, never overwritten, and a divergent copy is FAIL.
- It verifies **on the destination**, running `sha256sum -c SHA256SUMS` on the remote host over ssh.
- A remote PASS reports `host_loss_redundancy = CANDIDATE`. That is never PROVEN.

The gaps below are covered by this procedure, not by new code:

| Gap | Handling |
|---|---|
| A restore from the remote is not automated | §6: pull the set back with rsync into an empty scratch directory on a machine that is **not** the primary, then run the existing `scripts/p3/backup.py drill` against it |
| No scheduled offsite push | §5 retention/schedule. A user timer is a later Owner-approved install. The first acceptance run is manual |
| No offsite-recency alert | §7 maps it to a proposed health finding. That is Lane B / PLN-06 code, not part of this PR |
| Remote verification needs a shell command, so a pure `rrsync` forced command would block it | §4: a narrow forced-command wrapper that allows only the operations `offsite.py` issues |

## 2. Destination prerequisites (the "independent" test)
Owner decisions on candidate destinations, including that the Toshiba USB disk does not satisfy Tier-3, are recorded in [`PLN_05_DESTINATION_DECISIONS.md`](PLN_05_DESTINATION_DECISIONS.md).

The destination counts only if a total loss of `hamza-workstation` cannot also take the copy. That loss includes disk,
power, fire, theft, a ransomware account compromise, and the WDC disk, which is in the same machine.

| Requirement | Accepted | Not accepted |
|---|---|---|
| Separate hardware | another computer, NAS, VPS or cloud VM | another disk or partition in the workstation; the WDC disk; a VM on the workstation |
| Separate power | a different power circuit or site, or a UPS-backed device elsewhere | the same power strip as the workstation |
| Separate failure domain | a different room, building or provider | — |
| Separate credentials | a dedicated account on the destination that the workstation can only append to (§4) | the Owner's main account, or root |
| Reachable | ssh from the workstation (LAN, Tailscale or internet) | — |
| Linux shell with `rsync` and `sha256sum` | required by `offsite.py` | object-only storage (S3/B2) is out of scope for this tool; a different tool would be a new reuse decision |

## 3. Capacity
- **Measured size:** a P3 backup set is about **1 GB**. It holds 5 roots, 2 git bundles and 3 Docker volumes, with the Grafana volume about 0.53 GB ([`PLN_05_EVIDENCE_DURABILITY.md`](PLN_05_EVIDENCE_DURABILITY.md); the 2026-10-25 migration report).
- **Retention:** keep the 14 most recent daily sets plus 6 monthly sets. That is 20 sets, about 20 GB.
- **Minimum free capacity at the destination: 30 GB.** That is 20 GB of retention plus 50% headroom for set growth and one in-flight transfer.
- **Recommended:** 50 GB or more.
- **Check before each push:** the append-only gate (§4) refuses `df`, so the free-space check runs on the destination itself, as its owner (`df -h <dest-path>` in a session on the destination host), or via its own monitoring. Push nothing if free space is below 2× the newest set's size.

## 4. Authenticated transport (append-only account)
These are steps on the **destination**, done by the Owner. Claude has no access there.
1. Create a dedicated user, e.g. `tlos-offsite`, with home `/srv/tlos-offsite`. No sudo. The destination path is owned by that user.
2. On the workstation, create a dedicated key that is not reused anywhere else:
   `ssh-keygen -t ed25519 -f ~/.ssh/tlos_offsite_ed25519 -C tlos-offsite -N ''`
3. On the destination, add it to `~tlos-offsite/.ssh/authorized_keys` with restrictions:
   ```text
   restrict,from="<workstation address or tailnet IP>",command="/usr/local/bin/tlos-offsite-gate" ssh-ed25519 AAAA… tlos-offsite
   ```
4. `/usr/local/bin/tlos-offsite-gate` (on the destination, root-owned, mode 755) allows only the commands `offsite.py` and
   the restore pull send, and nothing else:
   ```sh
   #!/bin/sh
   # Allow only: rsync server (push/pull), test -d, mkdir -p, cd <set> && sha256sum -c --quiet SHA256SUMS. No delete.
   case "$SSH_ORIGINAL_COMMAND" in
     "rsync --server"*)          case "$SSH_ORIGINAL_COMMAND" in *--delete*|*--remove-source-files*) exit 1;; esac
                                 exec $SSH_ORIGINAL_COMMAND ;;
     "test -d /srv/tlos-offsite/"*|"mkdir -p /srv/tlos-offsite"*) exec $SSH_ORIGINAL_COMMAND ;;
     "cd /srv/tlos-offsite/"*" && sha256sum -c --quiet SHA256SUMS") exec sh -c "$SSH_ORIGINAL_COMMAND" ;;
     *) echo "refused: $SSH_ORIGINAL_COMMAND" >&2; exit 1 ;;
   esac
   ```
   Paths outside `/srv/tlos-offsite/` and any `..` must be rejected. The Owner reviews the wrapper before installing it.
5. On the workstation, add an `~/.ssh/config` entry `Host tlos-offsite`. It sets `HostName`, `User tlos-offsite`, `IdentityFile ~/.ssh/tlos_offsite_ed25519`, `IdentitiesOnly yes`, and `StrictHostKeyChecking yes`, with the host key pinned on first contact by the Owner.

Destination-side retention pruning is the Owner's manual act, done in a separate shell. The gate forbids deletes, so a compromised workstation cannot erase the offsite history.

## 5. Push and integrity (repeatable)
```bash
d=~/projects/trading/tlos-p3      # after the planned reboot verify and the tlos-p3 update
last=$(ls -1d /mnt/tlos-wdc/tlos-backups/2* | tail -1)
out=~/tlos-paper/p3-evidence/offsite_push_$(date +%Y%m%dT%H%M%S).json
[ -e "$out" ] && echo STOP || { (cd "$d" && python3 scripts/p3/offsite.py --set "$last" --dest tlos-offsite:/srv/tlos-offsite) > "$out"; echo "offsite_exit=$?"; cat "$out"; }
```

Expected output:
- `"action": "PUSHED"`, or `"VERIFIED_EXISTING"` when the set was already there;
- `"destination_verify": "PASS"`;
- `"host_loss_redundancy": "CANDIDATE"`.

Any `FAIL` is recorded as it is. A divergent existing copy is a §7 integrity incident, not something to overwrite.

## 6. Restore verification from the remote. This is the act that can make it PROVEN
The drill runs on a machine **other than the workstation** wherever possible. That can be the destination itself if it has Python and the repository, or a third machine.

If only the workstation is available, the pull runs **from the remote** into an empty scratch directory on the workstation. That proves the bytes on the independent host restore. Record which machine ran the drill.

```bash
scratch=~/tlos-restore-drill-offsite-$(date +%Y%m%dT%H%M%S); mkdir "$scratch"
set_name=<stamp>        # the set pushed in §5
rsync -a tlos-offsite:/srv/tlos-offsite/$set_name/ "$scratch/set/"
(cd ~/projects/trading/tlos-p3 && python3 scripts/p3/backup.py verify --set "$scratch/set") ; echo "verify_exit=$?"
(cd ~/projects/trading/tlos-p3 && python3 scripts/p3/backup.py drill --set "$scratch/set" --scratch "$scratch/restore" \
   --config-load trading/trading_lab_os_final --json "$scratch/drill.json"); echo "drill_exit=$?"
```

**PROVEN only if both hold:**
- `verify_exit=0`;
- `drill_exit=0`, with every drill check PASS: manifest sha256 equal, git fsck clean, ARCHIVE_VERIFIED, and config load in dry-run.

## 7. Failure alerts (mapping only; implementation belongs to PLN-06)
| Condition | Proposed finding → severity | Owner of the code |
|---|---|---|
| No offsite-verified set newer than 26 h, once the Tier-3 schedule is live | `offsite_recency` WARNING (CRITICAL after 72 h) | Lane B (`research/p3/health.py`), separate PR |
| `destination_verify = FAIL` or a divergent copy | `offsite_integrity` CRITICAL | Lane B |
| Destination free space < 2× the newest set | `offsite_capacity` WARNING | Lane B |

Until these exist, the push output files in `p3-evidence/` are the record, and the Owner reviews them.

## 8. Evidence to record in `PLN_05_EVIDENCE_DURABILITY.md` (only after real runs)
```text
TIER3_DESTINATION     <type: NAS / VPS / remote PC> at <site/provider>; independence: hardware / power / failure domain
TRANSPORT             ssh key tlos_offsite_ed25519 (fingerprint <…>), restricted gate (sha256 <…>)
PUSH                  set <stamp>, offsite_push_<…>.json, destination_verify PASS
RESTORE_DRILL         from tlos-offsite:/srv/tlos-offsite/<stamp> on <machine>, drill.json sha256 <…>, all checks PASS
HOST_LOSS_REDUNDANCY  PROVEN (<date>)    ← only with both PUSH and RESTORE_DRILL evidence
```

## 9. Minimum Owner inputs needed
1. **Destination:** its type (NAS / VPS / remote PC / cloud VM) and where it lives. It must be a different machine, power and failure domain.
2. **Hostname or address** reachable over ssh from the workstation, plus the account name the Owner will create (suggested: `tlos-offsite`).
3. **Destination path** (suggested: `/srv/tlos-offsite`) and its **free capacity**, which must be 30 GB or more.
4. **Owner approval** to create the key and install the gate on the destination. Both are Owner actions.
