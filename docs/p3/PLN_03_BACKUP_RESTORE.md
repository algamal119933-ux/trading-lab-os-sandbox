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
