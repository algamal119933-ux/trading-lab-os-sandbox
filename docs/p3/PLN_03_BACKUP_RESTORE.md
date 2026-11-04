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

- **Host integration support (PR-A, 2026-11-04).** The host stops its runtime with `docker compose down`, which removes the
  containers, so coverage can only be observed while the runtime still runs.
  - **Bound pre-stop coverage.** `coverage --json F` writes a report, 0600 and never overwritten, with
    `report_version`, `generated_utc`, `compose_project`, the exact `data` and the resolved `roots`.
    `create --coverage-report F` refuses the set, writing nothing, unless the report says PASS, names exactly this
    create's data and roots, and was observed 0–1800 s ago. The record carries the report with
    `observed: before_runtime_stop` and `report_sha256`. `--compose-project` (observed at create) and
    `--coverage-report` are mutually exclusive. Without either, the record's coverage is `null` (UNPROVEN), and
    such a set counts toward no gate.
  - **One run at a time.** `create` holds an exclusive flock on `<target>/.backup.lock` and `mirror` one on
    `<mirror>/.mirror.lock`. A second run is refused and writes nothing. The kernel releases a lock when its holder
    dies, SIGKILL included. The wrapper's runtime stop/start needs its own lock in the wrapper.
  - **Second-device mirror (`mirror`).** It publishes a verified full copy as `sets/<stamp>` and points `current` at
    it.
    - Invariant: the last verified full generation is never destroyed while a replacement is published.
    - The copy is staged under a dot-name and renamed only after verify, file-list, record and permission checks,
      so a non-dot name always means verified.
    - `current` is switched atomically; older generations beyond `--keep` are retired by rename, then deleted.
    - No space is ever made by deleting.
    - Legacy partial copies (`latest`, `previous`, `.incoming`) are never touched. Their removal is a separate
      Owner decision.
    - Interruption at every step, including mid-copy, is tested.
  - **Drill provenance.** A drill record now states which copy it restored: `source.set_dir`, `source.realpath`
    and `source.tier`. The tier is `SECOND_DEVICE_MIRROR` only for a generation under the `sets/` of a published
    mirror (its lock file present), and `UNCLASSIFIED` otherwise, including an offsite-opened copy. Drills recorded
    earlier have no source, and the Control Room shows them as `SOURCE_UNKNOWN`.
  - **`runtime-check`.** Each compose service individually: exactly one container, running, not restarting,
    healthy if it has a healthcheck, and started after the restoration began. It polls up to `--wait`, then
    FAILs; it never hangs. An incomplete recovery exits 1.
  - **Limits.** No EXIT trap survives power loss or SIGKILL. After power loss, `tlos-runtime.service` starts at boot.
    After a SIGKILL during a backup, the runtime stays down until the next start. The governed wrapper therefore
    records a marker before stopping the runtime. Its next run recovers and proves the runtime **before** it backs
    up anything (see the wrapper below).
    Tests: `tests/test_p3_backup_host_integration.py`.

- **Governed host wrapper.** `scripts/p3/ops/tlos_runtime_backup.sh` is the host's effective `backup.sh`. Commit
  `ca0e917` is the verbatim original (sha256 `561c44d2…b531`, rebuilt from the H1 report and hash-checked); the
  next commit is the patch:
  - one run at a time (`flock`, exit 75);
  - recovery first: a marker left by a run killed after stopping the runtime (SIGKILL, timeout escalation) makes
    the next run restart the runtime and prove it (running, answering its probes) before anything else. Then it
    observes fresh coverage and backs up as usual. If the recovery fails, no backup is attempted (exit 6) and the
    marker stays. The marker is in `$XDG_RUNTIME_DIR`, so a reboot clears it; from then on the boot path owns the
    runtime (`docs/p3/PLN_03_HOST_INSTALL_H2_H7.md` §R);
  - the store identity (UUID) is checked first, before the recovery: no runtime is started on an unproven store
    (exit 3, marker kept). The runtime's own unit and guard are host-local and not governed by this repository;
  - a runtime that is not running and that no backup run stopped (no marker) is down for an unknown cause (an Owner
    stop, a failed boot start and a missing mount look the same) and is never started by the backup. Its set is **archive-only**: verified and mirrored, coverage UNPROVEN, exit 7;
  - two separate results: `ARCHIVE_INTEGRITY` (verify and mirror) and `LIVE_DATA_COVERAGE`, read back from the
    set's own record. Only both together give `BACKUP = PASS` and exit 0;
  - coverage observed before `compose down`, bound into **this** run's set (`--stamp`). Only that set is verified
    and mirrored; the original took "the newest set" by `sort | tail -1`;
  - a restore that is proven, never masked: each of grafana, prometheus and mlflow running, started by this
    restoration, and answering its own readiness probe (`runtime-check --probe`; no container defines a Docker
    healthcheck). Otherwise exit 6;
  - the live bind-mounted data instead of the old named volumes;
  - a verified full-set SSD copy via `backup.py mirror`. The legacy partial copies are left untouched.
  - Lifecycle tests: `tests/test_p3_backup_wrapper.py`, which runs the real wrapper and `backup.py` against stubbed
    `systemctl`/`docker`/`findmnt` and local probe servers, with failure injection, SIGTERM, SIGKILL and
    concurrency.
  - Installation and rollback: [`PLN_03_HOST_INSTALL_H2_H7.md`](PLN_03_HOST_INSTALL_H2_H7.md).

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

## Re-acceptance after the live-data change (2026-11-04)
**Why it was needed.** On 2026-11-03 a limitation was found: the accepted sets exported named volumes that the live
runtime does not use. Its data had moved to bind mounts under `/srv/project-data/trading-data/runtime/data`. The
contract asks for the drill to be repeated after a change. The repository side was merged as #106 (live-data backup),
#108 (Control Room backup truth), #111 (governed host wrapper and H2–H7 runbook, replacing #107) and #112 (G8
correction). The host steps H2–H7 then ran, each under its own Owner authorization
(`PLN_03_HOST_INSTALL_H2_H7.md`).

**History of this re-acceptance.**
1. **H2–H6:** tools checkout `6d2f2075` → `b8667293`; wrapper installed (`561c44d2…` → `4308f50c…`, rollback copy
   kept); one backup run through the existing unit wrote set **`20261104T143958Z`** (`Result=success`,
   `ExecMainStatus=0`, `BACKUP = PASS`).
2. **First H7 (2026-11-04T14:49Z): G7 PASS, G8 FAIL** on `prometheus WAL_RECOVERY`. Kept unchanged:
   `h7_restore_20261104T144942Z.d/`.
3. **Root cause (2026-11-04):** both reasons were defects in the check, not in the data.
   - The seven `repair|corrupt` matches were `source=repair.go:54 msg="Found healthy block"`. Production Prometheus,
     restarted at 16:40 on the same bytes, logged the same seven lines with `wal_corruptions_total = 0` and
     `mmap_chunk_corruptions_total = 0` (`h7_readonly_20261104T153247Z.d/`).
   - The `-1` was an HTTP 422 from Prometheus. `count_over_time` drops the metric name, so two metrics of one target
     collide.
   - The original run's own log is not recoverable (`json-file` driver, container removed).
4. **#112 (merge `8e7597d2`):**
   - detection reads only the `msg=`/`err=` fields, and also requires the two TSDB corruption counters (0) and no ERROR
     line;
   - the query uses `last_over_time`;
   - raw logs and HTTP responses are kept.
   - The acceptance requirement is unchanged.
5. **H7 re-acceptance (2026-11-04T16:28Z):** tools checkout `b8667293` → `8e7597d2`. The drill used a fresh scratch
   from the same SSD set. The first scratch was not touched. **G7 PASS, G8 PASS.**

**Set identity.**
- `20261104T143958Z`, created `2026-11-04T14:40:11Z`, 757,825,066 bytes.
- `sha256(SHA256SUMS)` = `7f7219400604205c9d4444527c08c0f30a29f1ffc8b768462547e32e0ccf148b` = the record's
  `sha256sums_digest`.
- HDD (`/srv/project-data/tlos-backups/`) and SSD (`~/tlos-backups-ssd-mirror/sets/`) copies: identical record,
  identical `SHA256SUMS`, same 19 files with the same sizes and times. `current` → `sets/20261104T143958Z`.
- Data sources: grafana 1,259 files (531,100,044 B, `grafana.db` included), prometheus 35 (5,259,634 B), mlflow 1
  (872,448 B). Roots: trading, tlos-paper, tlos-ar-render, tlos-evidence-docs, claude-memory. Bundle:
  trading_lab_os_final.

**Gates (verified by Claude on 2026-11-04 from the files themselves, read-only, not from the terminal output):**

| Gate | Result | Evidence |
|---|---|---|
| G1 live-data coverage | PASS | record `live_data_coverage`: `PASS`, `before_runtime_stop`; its `report_sha256` = sha256 of `backup_coverage_20261104T143958Z.json`; 3 sources with file counts; `grafana.db` in `data/grafana.files.sha256`; H3 negative control FAIL as designed |
| G2 backup integrity | PASS | the run's own verify (`ARCHIVE_INTEGRITY = PASS`, journal); re-acceptance `VERIFY = PASS []` on the SSD set; record digest matches |
| G3 permissions | PASS (by construction) | `create` refuses to publish any entry open to group or other (`GROUP_OR_OTHER_ACCESSIBLE_ENTRIES`), and the set was published. **Gap:** no saved post-hoc `find -perm` listing (no H6 directory was written) |
| G4 SSD mirror | PASS | `backup_mirror_20261104T143958Z.json`: `SSD_MIRROR = PASS`, `current = sets/20261104T143958Z`, legacy `latest`/`previous` untouched (legacy SOURCE_SET hashes identical before/after); identical file list on HDD and SSD |
| G5 runtime recovery | PASS | `RUNTIME_RECOVERY = PASS` after the backup (16:40:17) and before/after the re-acceptance; runtime unit active, `NRestarts=0` |
| G6 schedule | PASS | unit hash unchanged before/after H4 (`2563b52c…`); timer listed; next run 2026-11-05 03:30Z |
| G7 isolated restore | PASS | `PLN_03_RESTORE_DRILL = PASS` (13 checks incl. `data:grafana/prometheus/mlflow`, `git:*`, `config_load:*`); `source.tier = SECOND_DEVICE_MIRROR` |
| G8 application consistency | PASS | `RESTORE_APP_CHECKS = PASS`: Grafana SQLite integrity ok; MLflow 1 experiment read; Prometheus ready in 2 s, `WAL replay completed`, 0 repair/corruption events, 0 ERROR lines, both counters 0, query HTTP 200 → 5 series at the stamp |

**Also verified:**
- The set's `data/prometheus.tar` equals its `SHA256SUMS` entry and the re-acceptance "before" hash now. The set is
  unchanged.
- The installed wrapper (`4308f50c…`) equals the governed file at both `b8667293` and `8e7597d2`.
- No throwaway container was left.
- The raw Prometheus log and the HTTP bodies are kept in `app.prometheus.log` and `app.http/`.

**Evidence** (`/home/hamza/tlos-paper/p3-evidence/`; every directory's `SHA256SUMS` verified, sha256 of each manifest):

| Directory or file | sha256 |
|---|---|
| `backup_install_20261104T140532Z.d/SHA256SUMS` (H2) | `4a0321efb9984e5529c02d47e89ecef241792f132af9a2ac93a613357fafff63` |
| `h3_verify_20261104T140937Z.d/SHA256SUMS` | `9ac1e667910f5634fc9afe5f98d09101a181ce43cfdf94606fdc62b63a12591a` |
| `h4_install_20261104T141246Z.d/SHA256SUMS` | `1c29d36ba2f59f92f3f5242db7afe29959cf440a211bde276b665bfbde559ebb` |
| `h5_real_20261104T143958Z.d/SHA256SUMS` | `78ee0135b797abf29ffc6d6853dfba3c39c4b05964401f045f717612fb9a55cf` |
| `h7_restore_20261104T144942Z.d/SHA256SUMS` (first H7, G8 FAIL) | `9238d31c25d8961d84d6d14d1ba725665229b1e79b2e7c14283f254023dae4af` |
| `h7_readonly_20261104T153247Z.d/SHA256SUMS` (root cause) | `d865f68136fb1c3413697b4591870c0538e0042994b43b6bfff8910c3e994958` |
| `h7_reaccept_20261104T162813Z.d/SHA256SUMS` (re-acceptance) | `516595e56c0f236e2da34b987320a8e6c80246ffb962c15a94d9d89aa63cb54e` |
| `backup_coverage_20261104T143958Z.json` | `fa26d9503cf21013f9784cf8f2c908d04769f8cac3ff6c15948985817260bf45` |
| `backup_mirror_20261104T143958Z.json` | `39406562cbab1a5cdb6d83c57203fd10f4acb70f325e9a780dfa6314a1b623cb` |

`h5_safe_20261104T143653Z.d/` holds a first H5 attempt that refused before starting anything (timer parse). It is kept.

**What is and is not established:**

| Claim | State |
|---|---|
| Backup integrity | PROVEN for set `20261104T143958Z` (G2, G3) |
| Live-data coverage | PROVEN for that set: observed before the stop, bound into the set (G1) |
| Isolated restoration | PROVEN from the second-device copy into a scratch (G7) |
| Application consistency | PROVEN on the restored copy: Grafana database file, MLflow read, Prometheus TSDB open and WAL replay (G8) |
| Operational readiness | PARTIAL. The run used the existing unit under `systemctl start`; the first timer-driven run with the governed wrapper is due 2026-11-05 03:30Z and is not yet observed. Interrupted-run recovery and the exit-7 path are CI-tested only |
| Offsite disaster recovery | NOT PROVEN. Both copies are on one machine, one PSU. PLN-05 Tier 3 (VPS, sealed upload) is not provisioned; `HOST_LOSS_REDUNDANCY = NOT_PROVEN` |

**Remaining limitations:**
- **Prometheus:** the recent window held 5 series only. The scrape target is the Freqtrade exporter, and it is down
  because the paper runtime is stopped. G8 proves the WAL was captured and replayed up to the last scrape
  (head max time 4.2 s before the stamp). It does **not** prove every historical sample was recovered.
- **Prometheus throwaway:** it ran with the image's default configuration and retention. It deleted one obsolete block
  in the scratch copy, so older history is hash-verified only.
- **Grafana:** checked at the database file. A started Grafana is not part of G8.
- **Restore fidelity:** ownership and modes are not restored as in production (the drill restores as `hamza`), and
  empty directories are not proven.
- **Scope:** one set, one drill. Later sets carry their own integrity and coverage, but no drill until another runs.
  The Control Room shows these separately.
- **Evidence custody:** the evidence lives on the same host. It is included in later sets' `tlos-paper` root, not
  offsite.
- **Evidence gaps (not gate failures):**
  - G3 has no saved post-hoc permission listing.
  - The re-acceptance kept "before" fingerprints of the set and the first scratch; the "after" comparison was printed,
    not saved. The set itself was re-hashed afterwards and is unchanged.

```text
PLN_03_REACCEPTANCE   = PASS (set 20261104T143958Z; G7 PASS, G8 PASS after the #112 correction)
LOCAL_BACKUP_HARDENED = PASS (G1–G8 on that set; local only: not offsite, not a trading authorization)
HOST_LOSS_REDUNDANCY  = NOT_PROVEN (PLN-05)
PAPER_LAUNCH_AUTHORIZED = NO · REAL_MONEY_AUTHORIZED = NO
```
This record takes effect when the Owner merges it.
