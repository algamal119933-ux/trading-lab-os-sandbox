# P3-PLN-03 — Backup & Restore (execution record)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-03 (frozen at fcd06b21), executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1).
**Acceptance (contract):** a restore drill passes: manifest sha256 equal, git fsck clean, ARCHIVE_VERIFIED on the restored copy, and the restored runtime starts in dry-run. It is repeated after a change.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCHED = NO

## Deliverable (implemented)
| Item | Path | Reuse (§10) |
|---|---|---|
| Backup / verify / restore-drill library | `research/p3/backup.py` | WRAP_EXISTING: GNU tar + zstd, `git bundle --all`, a read-only helper container for volumes, `verify_archive` for sealed evidence |
| CLI (`create`, `verify`, `drill`) | `scripts/p3/backup.py` | — |
| Scheduled wrapper | `scripts/p3/scheduled_backup.sh` | — |
| systemd user units (daily 03:30 UTC, Persistent) | `scripts/p3/units/tlos-p3-backup.{service,timer}` | REUSE (systemd) |
| Tests | `tests/test_p3_backup.py`: 13 tests, synthetic only. Each refusal is produced: tampered artifact, rewritten SHA256SUMS, overwrite attempt, non-empty scratch, failing sealed archive, failed config load, missing named runtime | — |

Design rules:
- A set is written once to `<target>/<stamp>/`, through a staging rename, and never overwritten.
- Derived files (.venv, bytecode, caches) are excluded.
- Each root carries a per-file sha256 manifest. Symlinks are recorded by their target text, the same rule PLN-02 uses.
- `SHA256SUMS` covers every artifact, and `BACKUP_RECORD.json` pins the digest of `SHA256SUMS`.
- The drill restores only into an empty scratch directory.
- `--config-load <runtime>` runs the pinned engine `freqtrade@sha256:da3428…` with `--network none`, the restored user_data mounted read-only, and only `list-strategies` and `show-config`, as CI's freqtrade-load job does. **No trading command is issued.**

## Execution on hamza-workstation (2026-10-25)
**Backup set `20261025T171416Z`**, at `/mnt/tlos-wdc/tlos-backups/20261025T171416Z` (a new directory; no existing WDC data was touched):
- 700 MB, created in 17 s.
- Roots: trading (projects/trading: the runtime checkout, 9 worktrees, tlos-control, v1), tlos-paper, tlos-ar-render, tlos-evidence-docs, claude-memory (memory/ only).
- Bundles: trading_lab_os_final and h1-tools.
- Volumes: trading_lab_os_final_{grafana,mlflow,prometheus}_data, exported read-only. **This closes the PLN-02 volume gap.**
- `verify`: PASS.

**Restore drill** into `/home/hamza/tlos-restore-drill-20261025T171416Z-5` (empty scratch, Linux fs):
```text
backup_integrity                          PASS
root:trading                              PASS (5,226 files byte-identical)
sealed:trading/trading_lab_os_final       PASS — 7 archives ARCHIVE_VERIFIED (incl. l2-cohort-20260924T120000Z)
sealed:trading/tlos-control               PASS — l2-cohort-20260920T120000Z ARCHIVE_VERIFIED
config_load:trading/trading_lab_os_final  PASS — list-strategies + show-config, pinned engine, --network none, read-only
root:tlos-paper / tlos-ar-render / tlos-evidence-docs / claude-memory   PASS
git:trading_lab_os_final / git:h1-tools   PASS — recorded HEAD present, fsck clean
PLN_03_RESTORE_DRILL = PASS
```
The drill itself caught three faults in the tooling while it was being run, and they were fixed in code with tests before the passing run:
- the sealed and config checks did not look one level down;
- a corrupt bundle aborted the drill instead of failing it;
- a config-load rule did not match Freqtrade's real output. The legacy v1 tree is not a runtime: its config uses `OVERWRITTEN_BY_ENV` placeholders, so the check targets the named runtime explicitly.

**PLN-02 re-run against this set:**
- runtime, tlos-control and 9 worktrees, the evidence docs and memory: **PASS**.
- tlos-paper: 3 STALE files, the PLN-03 sources edited after the backup ran. The next scheduled set resolves this.
- tlos-ar-render: 1 MISSING (`prof/lock`, a dangling symlink). Symlinks are now recorded by both tools. The next set includes it.

## Verdict
```text
PLN_03_DELIVERABLE      = IMPLEMENTED + VERIFIED (tooling, 13 tests, a real backup set and a real passing drill)
PLN_03_ACCEPTANCE       = PASS for set 20261025T171416Z (restore drill PASS on every check)
SCHEDULE                = PREPARED, NOT INSTALLED (installing a persistent host timer is an Owner action, below)
RETENTION               = not implemented: sets are append-only. Pruning old sets deletes data and needs a separate
                          Owner decision. At about 0.7 GB/day the WDC (≈525 GB free) holds about 2 years
```

## Owner action: install the daily schedule (it changes host configuration)
```
git -C /home/hamza/projects/trading/trading_lab_os_final worktree add /home/hamza/projects/trading/tlos-p3 origin/main
mkdir -p ~/.config/systemd/user && cp /home/hamza/projects/trading/tlos-p3/scripts/p3/units/tlos-p3-backup.* ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now tlos-p3-backup.timer
systemctl --user list-timers tlos-p3-backup.timer          # next run 03:30 UTC
```
Rollback: `systemctl --user disable --now tlos-p3-backup.timer`. The backup sets already written stay, because nothing is deleted.

## Hand-off
- PLN-04 (restart, reboot and host recovery) uses these sets as its restore source.
- PLN-05 needs a **Tier-3 independent-host** copy. These sets are same-host (WDC), so HOST_LOSS_REDUNDANCY = NOT_PROVEN.

## Acceptance update (2026-10-25T18:51Z)
Second set `20261025T185052Z` (verify PASS, 3 volumes included). Its restore drill passes every check, with 8 archives ARCHIVE_VERIFIED and the runtime config load passing.
Still open: **the scheduled execution**. The timer is not installed (Owner action). After installation, the first unattended set, its verify and its drill complete PLN-03.

## Scheduled acceptance (2026-10-25T21:2xZ)
The Owner installed `tlos-p3-backup.timer` and `tlos-p3-health.timer` as user units: enabled, linger on, ExecStart from the clean tools checkout `~/projects/trading/tlos-p3` at main 253dbf29. The Owner then started both services once.

The first set **written by systemd** is `20261025T211956Z`:
- `tlos-p3-backup.service`: Result=success, ExecMainStatus=0.
- 699 MB. Roots: trading 5,666 files, tlos-paper 2,431, tlos-ar-render 343, tlos-evidence-docs 517, claude-memory 6. Two bundles; three volumes.
- `verify`: PASS.
- Restore drill into the empty scratch `/home/hamza/tlos-restore-drill-20261025T211956Z`: every check PASS. That covers byte identity on all five roots, 8 sealed archives ARCHIVE_VERIFIED, config load of `trading/trading_lab_os_final` (pinned engine, `--network none`, read-only), and the git bundles with HEAD present and fsck clean. **PLN_03_RESTORE_DRILL = PASS.**

PLN-02 re-run against this set: PASS on runtime, the 10 worktrees, the tools checkout, tlos-ar-render, the evidence docs and memory. tlos-paper differed by a single STALE file, `p3-evidence/tlos_p3_health.prom`, which the health timer rewrites hourly, so it will always be newer than the last backup. It is now classified **derived** in the operator profile, and the rest of `p3-evidence/` stays operator state.

```text
PLN_03_ACCEPTANCE = PASS (the scheduled execution under systemd: verify PASS, drill PASS)
```
The next run is the timer's own unattended 03:30 UTC run. The health check's `backup_recency` (RPO 26 h) alerts if any later run is missed.

## Backup store configuration (2026-10-30)
**Why.** The store path `/mnt/tlos-wdc` was hard-coded in five places: the backup wrapper, the backup unit, the health check, the Control Room and the reboot snapshot.

The Owner-reported host migration of 2026-10-29 moved the TLOS backups to an internal HDD under `/srv/project-data/tlos-backups`. Label: HANDOFF_ONLY. Claude has not seen the host. After the move, the hard-coded path broke health in two ways:
- the hourly health run reported the old store as CRITICAL;
- the run never checked the store the backups actually went to.

**What changed.** `research/p3/storage.py` is now the single source. Every consumer reads it:
- `scheduled_backup.sh`;
- `health.py` and `health_check.py`;
- `control_room.py`;
- `scripts/p3/recovery.py`.

The backup unit no longer carries `RequiresMountsFor`.

**Resolution order:**
1. The environment variables `TLOS_BACKUP_MOUNT` and `TLOS_BACKUP_TARGET`, set together, plus the optional `TLOS_BACKUP_MOUNT_UUID`.
2. A host-local file, `~/.config/tlos-p3/storage.json` or the file named by `$TLOS_STORAGE_CONFIG`.

**There is no implicit default.** `/mnt/tlos-wdc` remains documented history only. Falling back to it silently would let a stale or re-mounted legacy disk receive backups.

**Fail-closed.** Each of these is refused, never replaced by another location:
- nothing is configured;
- the configuration cannot be read;
- a path is relative or not normalised (`..`, `.`, `//`);
- a path contains a quote, `$`, `` ` ``, `\` or a control character;
- the mount is `/`;
- the target is outside the mount;
- the file has unknown keys;
- the UUID is malformed.

**Live preflight** (`storage.py --preflight`, run by the backup wrapper before every set). It refuses:
- a mountpoint that is not mounted, or is a symlink;
- a filesystem UUID different from the configured one, or one that cannot be read;
- a target, or its deepest existing parent, that resolves outside the mount or onto another device (a symlink or a nested mount);
- an existing target that is not a plain directory.

This matters because `backup.py create` creates the target's parents and would follow such a link.

**Where each failure shows:**

| Consumer | Behaviour |
|---|---|
| Health | `backup_storage` CRITICAL when the configuration is unusable (and `backup_recency` CRITICAL with it); `mount:<store>` CRITICAL when not mounted; `mount_uuid:<store>` CRITICAL on mismatch and WARNING `UNPROVEN` when unreadable; `backup_target_on_store` CRITICAL when the target resolves off the store |
| Backup wrapper | Refuses with exit 3 |
| Reboot snapshot | Errors with exit 2 |

Tests: `tests/test_p3_storage.py`. Residual: the preflight and `backup.py create` are separate steps, so the gap between them is a time-of-check window. The store is single-writer, so this is accepted.

**Host steps (Owner; each needs authorization, nothing here has been run):**
1. Write the host file. The values below are as reported for the migrated host; the mountpoint and UUID come from the host itself.
   ```bash
   install -d -m 700 ~/.config/tlos-p3
   M=/srv/project-data            # the HDD mountpoint (confirm: findmnt -T /srv/project-data/tlos-backups)
   U=$(findmnt -no UUID --mountpoint "$M")
   printf '{"backup_mount": "%s", "backup_target": "%s/tlos-backups", "mount_uuid": "%s"}\n' "$M" "$M" "$U" \
     > ~/.config/tlos-p3/storage.json
   python3 ~/projects/trading/tlos-p3/research/p3/storage.py      # prints the resolved store; exit 0
   ```
2. Do the controlled `tlos-p3` update to a main SHA that contains this change.
3. Run one health check: `scripts/p3/health_check.py`. Expect `backup_storage`, `mount:<M>`, `mount_uuid:<M>` and `backup_target_on_store` all INFO, and `backup_recency` measured on the new store. Also run `python3 research/p3/storage.py --preflight`, which must exit 0.
4. **Take a new reboot baseline** (`recovery.py snapshot`). The accepted baseline `42f0d28f…` records `/mnt/tlos-wdc`. A verify-boot against it now reports `mount:/mnt/tlos-wdc` missing, which is correct, because the store changed.
5. The Owner-reported drop-in that points `tlos-p3-backup.service` at a host-local `backup.sh` is outside the repository. Bringing that wrapper into the repository is a separate change. It needs the host files, which Claude cannot read. It must cover:
   - the runtime volume aliases;
   - the short stop around the export;
   - the SSD mirror.

   Until then the governed wrapper (`scheduled_backup.sh`) is not what the timer runs on that host.

PLN-03 stays **ACCEPTED** for its procedure and drills. This change touches only where the store is found, not how a set is made, verified or restored.
