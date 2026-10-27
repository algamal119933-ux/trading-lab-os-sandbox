# P3-PLN-05 — Tier-3 independent-host backup and restore procedure (prepared, not executed)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-05 (frozen at fcd06b21), executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1).
The execution record is [`PLN_05_EVIDENCE_DURABILITY.md`](PLN_05_EVIDENCE_DURABILITY.md).
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO

**Acceptance (contract):** `HOST_LOSS_REDUNDANCY = PROVEN` by **restoring from the independent host**.

Status today: `HOST_LOSS_REDUNDANCY = NOT_PROVEN`. No independent host exists. The testable requirements are §10. This document grants no access,
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
Owner decisions on candidate destinations are recorded in [`PLN_05_DESTINATION_DECISIONS.md`](PLN_05_DESTINATION_DECISIONS.md). As of 2026-10-27: the Toshiba USB disk holds a portable, Owner-carried copy that does not satisfy Tier-3; the Owner's Windows PC is withdrawn as a destination and is used only to read and check that copy ([`PLN_05_PORTABLE_COPY_DRILL.md`](PLN_05_PORTABLE_COPY_DRILL.md)); no Tier-3 destination is chosen.

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
4. `/usr/local/bin/tlos-offsite-gate` (on the destination, root-owned, mode 755) allows only the exact commands
   `offsite.py` and the §6 pull send, and nothing else. It is an allowlist: nothing in the command reaches a shell,
   a push must carry `--ignore-existing` (so an existing file is never overwritten), no delete or
   `--remove-source-files` form exists, and the only paths are `BASE` and `BASE/<stamp>`:
   ```sh
   #!/bin/sh
   # tlos-offsite-gate: the only commands the tlos-offsite key may run. Root-owned, mode 755.
   # An exact allowlist of the commands scripts/p3/offsite.py and the §6 pull send. Nothing reaches a shell;
   # no delete; no overwrite (a push must carry --ignore-existing); no path except BASE and BASE/<stamp>.
   set -f
   BASE=/srv/tlos-offsite
   STAMP='[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z'
   cmd=$SSH_ORIGINAL_COMMAND
   refuse() { echo "refused: $cmd" >&2; exit 1; }
   is_set() { case "$1" in "$BASE"/$STAMP|"$BASE"/$STAMP/) return 0 ;; esac; return 1; }
   verify=' && sha256sum -c --quiet SHA256SUMS'
   case "$cmd" in
     "cd "*"$verify")
       p=${cmd#cd }; p=${p%"$verify"}
       is_set "$p" || refuse
       cd -- "$p" || exit 1
       exec sha256sum -c --quiet SHA256SUMS ;;
   esac
   case "$cmd" in *[!A-Za-z0-9./_\ -]*|*..*|"") refuse ;; esac
   set -- $cmd
   case "$1 $2" in
     "test -d")  [ $# -eq 3 ] && is_set "$3" || refuse; exec test -d "$3" ;;
     "mkdir -p") [ $# -eq 3 ] && [ "$3" = "$BASE" ] || refuse; exec mkdir -p "$BASE" ;;
     "rsync --server")
       if [ $# -eq 6 ] && [ "$3" = "--sender" ] && [ "$5" = "." ]; then flags=$4
       elif [ $# -eq 6 ] && [ "$4" = "--ignore-existing" ] && [ "$5" = "." ]; then flags=$3
       else refuse; fi
       case "$flags" in -[A-Za-z]*e.*) ;; *) refuse ;; esac
       case "${flags#-}" in *[!A-Za-z.]*) refuse ;; esac
       is_set "$6" || refuse
       exec $cmd ;;
   esac
   refuse
   ```
   The Owner reviews the wrapper before installing it. `tests/test_p3_offsite_gate.py` runs this exact block
   (extracted from this file) against injection, traversal, foreign-path, delete, overwrite and unknown-command
   attempts, and against the commands `offsite.py` actually issues, including the rsync server lines produced by
   the local rsync. Residuals: rsync's own short-option surface (for example a temp directory under the account's
   home) remains, and the gate cannot stop a compromise of the destination account itself. Destination-side
   snapshots or immutability are the stronger append-only control (§10, T3-R3).

   *Correction (round 3):* the gate first drafted here matched `"cd /srv/tlos-offsite/"*" && sha256sum …"` and ran
   it with `sh -c`, so `cd /srv/tlos-offsite/x; <any command>; cd /srv/tlos-offsite/y && sha256sum -c --quiet
   SHA256SUMS` executed `<any command>` as the destination account, which owns every set: a compromised workstation
   could have deleted the offsite history. It also accepted `..`, and it did not stop an rsync push that overwrites.
   It was never installed (this procedure is NOT_RUN). The test above keeps the injection as a negative control.
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
sha256sum "$scratch/set/SHA256SUMS" "$scratch/set/BACKUP_RECORD.json" \
  /mnt/tlos-wdc/tlos-backups/$set_name/SHA256SUMS /mnt/tlos-wdc/tlos-backups/$set_name/BACKUP_RECORD.json
(cd ~/projects/trading/tlos-p3 && python3 scripts/p3/backup.py drill --set "$scratch/set" --scratch "$scratch/restore" \
   --config-load trading/trading_lab_os_final --json "$scratch/drill.json"); echo "drill_exit=$?"
```

**PROVEN only if all hold:**
- `verify_exit=0`;
- the pulled `SHA256SUMS` and `BACKUP_RECORD.json` hash equal to the original set's on the WDC (the destination's
  `sha256sum -c` only proves the copy is self-consistent; this proves it is the set that was pushed). On a machine
  other than the workstation, compare with the two hashes printed for the original on the workstation;
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

## 10. Tier-3 requirements (testable; mapped to the checks above)
Every requirement has a measurable PASS. Status labels: `CLAUDE-VERIFIED (local)` means a repository test Claude
ran on synthetic input in the cloud container, not GitHub CI and not the destination; `NOT_RUN` means it needs the
destination or the Owner; `NOT_COVERED` means no control exists yet. `PLN-05 = OPEN`,
`HOST_LOSS_REDUNDANCY = NOT_PROVEN`; only T3-R7 on a real destination can change the latter.

| ID | Requirement | PASS only if (measurable) | Procedure check | Repository control / test | Status |
|---|---|---|---|---|---|
| **T3-R1 Independence** | A total loss of `hamza-workstation` (disk, WDC, power, fire, theft, account compromise) cannot take the copy | The Owner records the destination's type and site, and it is none of the §2 "not accepted" rows; T3-R7 runs on a machine other than the workstation where possible, and the record names the machine | §2, §6, §8 `TIER3_DESTINATION` | none (an attestation and a site fact) | NOT_RUN (no destination; decisions record §5 item 1) |
| **T3-R2 Credentials** | One dedicated, non-sudo account and one dedicated key, usable only through the gate and only from the workstation | `authorized_keys` carries `restrict,from=…,command=…` for that key alone (Owner pastes the line, key fingerprint recorded); `ssh tlos-offsite id` and an interactive login are refused by the gate | §4 steps 1–3, 5 | `test_p3_offsite_gate` (an unknown command is refused) | gate CLAUDE-VERIFIED (local); destination NOT_RUN |
| **T3-R3 Append-only** | The workstation key cannot delete, overwrite or write outside `BASE`, so a compromised workstation cannot erase or alter the offsite history | From the workstation, each of: `rm`, an injected `cd …; cmd; cd … && sha256sum …`, a `..` path, `rsync --delete*`, `--remove-source-files`, and a push without `--ignore-existing` is `refused`; afterwards every set still passes `sha256sum -c` and its file list is unchanged. Stronger, by Owner decision: destination-side snapshots or immutability, shown by restoring a deleted file from a snapshot | §4 step 4, §5 (a divergent copy is FAIL, never overwritten) | `test_p3_offsite_gate` (each refusal, plus the commands `offsite.py` issues are accepted); `test_p3_offsite_and_units::test_a_tampered_destination_copy_fails_and_is_not_overwritten` | gate CLAUDE-VERIFIED (local); destination NOT_RUN; snapshot/immutability: Owner/design decision |
| **T3-R4 Capacity** | Room for retention (14 daily + 6 monthly ≈ 20 GB) plus headroom | Destination free space ≥ 30 GB at acceptance (50 GB recommended), and ≥ 2× the newest set before every push, read by `df -h <dest-path>` on the destination | §3 | none; the `offsite_capacity` finding is proposed (§7) | NOT_RUN · alert NOT_COVERED |
| **T3-R5 Schedule and recency** | Redundancy stays current after acceptance | Once a schedule is approved and installed: the newest `offsite_push_*.json` with `destination_verify = PASS` is younger than 26 h | §5, §7 | none (timer is an Owner-approved install) | NOT_RUN · NOT_COVERED |
| **T3-R6 Alerting** | A stale, divergent or full destination is seen without anyone looking | `offsite_recency` (WARNING > 26 h, CRITICAL > 72 h), `offsite_integrity` (CRITICAL on `destination_verify = FAIL` or a divergent copy) and `offsite_capacity` (WARNING < 2× newest set) each raise in a test, as PLN-06 does for §19 | §7 | none yet (PLN-06 `research/p3/health.py`, separate change) | NOT_COVERED |
| **T3-R7 Restore proof** | The bytes on the independent host restore into a working runtime | `verify_exit=0`; the pulled `SHA256SUMS` and `BACKUP_RECORD.json` hash equal to the original's; `drill_exit=0` with every check PASS (each root byte-identical, ARCHIVE_VERIFIED, git fsck clean with the recorded HEAD, config load in dry-run); evidence per §8 | §6, §8 | `test_p3_backup` (drill semantics), `test_p3_offsite_and_units` (push, remote verify, unverified source never pushed) | NOT_RUN. **The only act that can set `HOST_LOSS_REDUNDANCY = PROVEN`** |
| **T3-R8 Data-at-rest exposure** | A set holds the runtime `.env`, `config.json` and service volumes; who can read them at the destination is a decision, not an accident | An Owner record states one of: an Owner-controlled destination with disk encryption (state recorded), acceptance of a provider's encryption and access, or client-side encryption (a new reuse decision, AUDIT_BEFORE_USE). And no set holds a private exchange key (paper boundary; the PLN-06 health check reports credential key names only) | decisions record §5 item 7 | `test_p3_health_s19::test_container_env_is_parsed_by_name_only`, `test_p3_alerting::test_secrets_live_outside_every_backup_root` | Owner decision · NOT_RUN |

Requirements are not ranked or chosen here; the destination class (decisions record §6) determines which of them are
cheap or costly, and that choice is the Owner's.
