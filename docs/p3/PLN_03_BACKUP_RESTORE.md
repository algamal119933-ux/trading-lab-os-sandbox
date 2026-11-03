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
| Tests | `tests/test_p3_backup_volume_export.py` (volume archive owner/mode, failure paths, real Docker when available); `tests/test_p3_backup.py`: 13 tests, synthetic only. Each refusal is produced: tampered artifact, rewritten SHA256SUMS, overwrite attempt, non-empty scratch, failing sealed archive, failed config load, missing named runtime | — |

Design rules:
- A set is written once to `<target>/<stamp>/`, through a staging rename, and never overwritten.
- Derived files (.venv, bytecode, caches) are excluded.
- Each root carries a per-file sha256 manifest. Symlinks are recorded by their target text, the same rule PLN-02 uses.
- `SHA256SUMS` covers every artifact, and `BACKUP_RECORD.json` pins the digest of `SHA256SUMS`.
- The drill restores only into an empty scratch directory.
- Docker volumes are archived by a root helper container (`python:3.12-slim`), so root-owned 0600 files in a volume are included.
  That is why `docker run --user` is not used. The container has only the volume mounted read-only, `--network none`, and **no host
  write mount**: it streams the archive to stdout. `backup.py` creates the file itself with `O_EXCL`, mode 0600 and the backup
  user's uid:gid, whatever the umask. It then refuses (no set is published) any archive that is not a regular, non-empty
  file, 0600, owned by that user. This fixes the 2026-11-03 host finding: set `20261103T183447Z` verified PASS, but its three
  volume archives were `root:root 0644`, written by the container through a bind mount. Regression tests:
  `tests/test_p3_backup_volume_export.py`. Historical sets are not changed.
- **Live data sources and coverage** (2026-11-03 host finding: the runtime's Grafana, Prometheus and MLflow containers
  bind-mount `/srv/project-data/trading-data/runtime/data/{grafana,prometheus,mlflow}`, while the backup exported named
  volumes that no container uses).
  - `create --data NAME=SOURCE` archives a live source into `data/<name>.tar` (0600, the same root read-only helper).
    SOURCE is an absolute host directory, mounted with `--mount type=bind,readonly`, which refuses a missing directory, or a
    volume name.
  - The source is then read again by the helper. Its per-file sha256 must equal the archive's, which is written to
    `data/<name>.files.sha256`. A file the export could not read, or a writer still running, fails the set, so the runtime
    must be stopped for the backup. This also proves that protected files (Grafana's `grafana.db`) were read.
  - `create --compose-project P` refuses the set unless every **writable** mount of P's containers (running or stopped)
    is a declared data source or under a declared root, **and** no declared data source is unused by every container
    (`LIVE_DATA_COVERAGE`). Read-only configuration mounts are reported but do not decide the verdict. Host plumbing
    (`/proc`, `/sys`, `/dev`, `/run`, `/var/run`, the Docker socket) and tmpfs are not state. `coverage` runs the
    check alone, read-only.
  - The drill restores every data source and compares it file by file (`data:<name>`). Sets without data sources
    (all historical ones) drill as before. Regression tests: `tests/test_p3_backup_live_data.py`.
  - A writable bind counts as covered by a root only when the root actually archives it. A path through a derived
    (excluded) directory such as `.venv` covers nothing.
- **Every new set is owner-only.** `create_backup` runs under umask 077, whatever the caller's, so every directory
  is 0700 and every archive, bundle and manifest is 0600. If any entry is still open to group or other
  (`GROUP_OR_OTHER_ACCESSIBLE_ENTRIES > 0`), the set is not published. Earlier sets are never changed.
- `compare-export` (portable copy) expects 2 artifacts per root and per data source, 1 per repository and 1 per
  volume (`expected_artifact_count`). A record without `data_sources` counts as before.

### What the drill proves, and what it does not
| Property | Proven by | Status |
|---|---|---|
| File **content** and symlink targets equal to the source at backup time | archive manifest = the live source re-read by root (at `create`); restored tree = manifest (drill) | **Proven** |
| Every file was readable (protected Grafana files included) | the same equality: an unread file is missing from the archive | **Proven** |
| No writer changed the data during the backup | the re-read after the export | **Proven only between the two reads.** Runtime quiescence comes from the wrapper's stop |
| Ownership (uid/gid) and permissions | recorded in the tar headers, which the root helper writes numerically. The drill restores with `--no-same-owner --no-same-permissions` and does not compare them | **Not proven.** A restore as root with `--same-owner -p` keeps them, but nothing checks it |
| Empty directories | in the tar, restored by the drill; the manifest lists files only | **Not proven** |
| Hard-link relationships | tar stores them and GNU tar restores them; the manifest compares content per path | **Not proven** (content of each link is) |
| Application consistency (SQLite `grafana.db` / `mlflow.db` integrity, Prometheus TSDB) | nothing in the drill | **Not proven.** Needs `sqlite3 … 'PRAGMA integrity_check'` / `promtool tsdb analyze` on the restored copy, or starting the services on it |
- `--config-load <runtime>` runs the pinned engine `freqtrade@sha256:da3428…` with `--network none`, the restored user_data mounted read-only, and only `list-strategies` and `show-config`, as CI's freqtrade-load job does. **No trading command is issued.**

## Execution on hamza-workstation (2026-10-25)
**Backup set `20261025T171416Z`**, at `/mnt/tlos-wdc/tlos-backups/20261025T171416Z` (a new directory; no existing WDC data was touched):
- 700 MB, created in 17 s.
- Roots: trading (projects/trading: the runtime checkout, 9 worktrees, tlos-control, v1), tlos-paper, tlos-ar-render, tlos-evidence-docs, claude-memory (memory/ only).
- Bundles: trading_lab_os_final and h1-tools.
- Volumes: trading_lab_os_final_{grafana,mlflow,prometheus}_data, exported read-only. **This closes the PLN-02 volume gap.**
  - **Correction (2026-11-03):** this set's integrity and drill results stand as recorded. But these named volumes
    were **not shown to be the runtime's live data**, and on 2026-11-03 the live containers bind-mounted
    `/srv/project-data/trading-data/runtime/data/{grafana,prometheus,mlflow}` instead. No set before the live-data
    change proves runtime-data completeness. A set does so only when its record carries
    `live_data_coverage.LIVE_DATA_COVERAGE = PASS` and its drill passes `data:*`.
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
1. The environment variables `TLOS_BACKUP_MOUNT`, `TLOS_BACKUP_TARGET` and `TLOS_BACKUP_MOUNT_UUID`, all three set together.
2. A host-local regular file, `~/.config/tlos-p3/storage.json` or the file named by `$TLOS_STORAGE_CONFIG`, holding all three keys.

**The filesystem UUID is required.** Without it, any filesystem mounted at the path would be accepted as the store, for example a tmpfs or another disk (independent review, 2026-10-30).

**There is no implicit default.** `/mnt/tlos-wdc` remains documented history only. Falling back to it silently would let a stale or re-mounted legacy disk receive backups.

**Fail-closed.** Each of these is refused, never replaced by another location:
- nothing is configured;
- the configuration cannot be read;
- a path is relative or not normalised (`..`, `.`, `//`);
- a path contains a quote, `$`, `` ` ``, `\` or a control character;
- the mount is `/`;
- the target is outside the mount;
- the file has unknown keys;
- the UUID is missing or malformed;
- the config is not a regular file (a FIFO would block a reader).

**Live preflight** (`storage.py --preflight --shell`). The backup wrapper runs it before every set. That one call both checks the store and exports it, so the location written to is the location checked. The wrapper waits up to `TLOS_STORE_WAIT_S` (default 300 s) only for "not mounted", because a catch-up run at boot can start before the disk is mounted. The preflight refuses:
- a mountpoint that is not mounted, or is a symlink;
- a store on the same filesystem as `/` (a bind mount of a system-disk directory is not a separate store);
- a filesystem UUID that is missing, different from the configured one, or cannot be read;
- a target, or its deepest existing parent, that resolves outside the mount or onto another device (a symlink or a nested mount);
- an existing target that is not a plain directory.

This matters because `backup.py create` creates the target's parents and would follow such a link.

**Where each failure shows:**

| Consumer | Behaviour |
|---|---|
| Health | `backup_storage` CRITICAL when the configuration is unusable (and `backup_recency` CRITICAL with it); `mount:<store>` CRITICAL when not mounted; `mount_uuid:<store>` CRITICAL on mismatch, and CRITICAL `UNPROVEN` when unreadable or not configured (an unproven identity blocks exactly as a wrong one does); `backup_target_on_store` CRITICAL when the target resolves off the store or the store is the system disk; `backup_store_permissions` WARNING when group/other can reach the sets; `backup_recency` is measured only on a proven store |
| Backup wrapper | Refuses with exit 3 |
| Reboot snapshot | Errors with exit 2 |

**Permissions (security audit SEC-03).** Sets contain configuration, including the runtime `.env`, so the wrapper runs with `umask 077` and the unit with `UMask=0077`. Docker writes the volume tars as root inside the owner-only set directory, so nobody else can traverse to them. Whether to exclude `.env` from sets or encrypt them before offsite is an Owner decision. Host step: `chmod 700 <target>` on an existing store.

Tests: `tests/test_p3_storage.py`. **Residuals.**
- The preflight and `backup.py create` are separate processes, so there is a time-of-check window between them. The store has a single writer, so this is accepted.
- A manual `scripts/p3/backup.py create --target <dir>` does not run the preflight. It is an operator tool, also used for drills into scratch targets. The governed path is the wrapper.

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
