# P3-PLN-02 — State & Recovery Inventory (execution record)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-02 (frozen at fcd06b21, sha256 2c057cb5…487f4d).
It is executed under [`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md), merged at 7b1b1fa1 with post-merge CI green.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCHED = NO

## Deliverable (implemented)
| Item | Path | Reuse classification (§10) |
|---|---|---|
| Inventory library | `research/p3/state_inventory.py` | BUILD_SMALL_MISSING_LAYER. It classifies and verifies only, and delegates all verification to existing tools |
| Declared state classes (runtime / worktree / operator profiles) | `research/p3/records/state_classes.json` | record |
| CLI | `scripts/p3_state_inventory.py` | wraps `scripts/publish_evidence_digest.py verify_archive` (REUSE_EXISTING) |
| Tests | `tests/test_p3_state_inventory.py`: 15 tests, synthetic repositories only. Each refusal is produced: unclassified file, unreadable directory, dirty tree, unreachable HEAD, stale or missing cold entry, dataset mismatch, failing sealed archive | — |

Recovery kinds and the existing authority each delegates to:
- GIT_REMOTE: git (HEAD on a remote-tracking ref, tracked tree clean).
- SEALED_ARCHIVE: Tier 2 publication plus `verify_archive`.
- DATASET_LOCK: `research/datasets/dataset_v2.lock.json` raw_file_hashes.
- COLD_BACKUP: a sha256sum manifest.
- DISPOSABLE: regenerable files, for which no recovery is owed.

## Result on hamza-workstation (2026-10-25T17:0xZ, read-only)
Cold-backup manifests: `/mnt/tlos-wdc/tlos-migration-20261025/manifests/*.sha256` (taken about 10:00Z).

| Root | Profile | Files | Coverage | Recovery |
|---|---|---|---|---|
| projects/trading/trading_lab_os_final (runtime, HEAD 3191285a) | runtime | 24,657 | PASS (0 unclassified, 0 unreadable) | **PASS**. Source 188 (GIT_REMOTE). Sealed archives 71 files (SEALED_ARCHIVE, all rehash). Datasets 8 (raw hash = lock). .env and config.json (cold, match). Artifacts 620 (cold, match). Derived 23,768 (.venv, bytecode) |
| tlos-control + 9 cycle-2 worktrees | worktree | — | PASS | **PASS** (all 10) |
| Documents/TLOS-Evidence | operator | — | PASS | **PASS** |
| tlos-paper (operator workspace) | operator | 2,441 | PASS | **NOT_PASS**. 945 match, **1,299 MISSING, 5 STALE**: records, P3 worktrees and git metadata created or changed after the cold backup |
| tlos-ar-render | operator | 343 | PASS | **NOT_PASS**. 1 MISSING (`prof/lock`) |
| ~/.claude project memory | operator | 37 | PASS | **NOT_PASS**. 3 STALE (live session log, memory updated today) |

Host state outside the file roots:
| State | Recovery source | Status |
|---|---|---|
| Docker images: freqtrade:2026.7 (da3428…), grafana:13.2.0, prometheus:v3.14.0, mlflow:v3.15.1, python:3.12-slim | pinned digests (re-pull) | present, digests recorded |
| Docker volumes trading_lab_os_final_{grafana,mlflow,prometheus}_data (≈0.54 GB, P2 monitoring, non-authoritative) | **none** (the cold backup lists them as pending) | **GAP** |
| P2 window-monitor units (disabled) | cold backup tlos-host-extras | in the cold backup |

## Verdict
```text
COVERAGE                   = PASS on every declared root (0 unclassified, 0 unreadable)
RECOVERY                   = PASS for runtime, worktrees and evidence docs;
                             NOT_PASS for the operator workspace, tlos-ar-render and memory (cold backup older than the
                             state, its RPO is breached), and a GAP for the 3 Docker monitoring volumes
PLN_02_DELIVERABLE         = IMPLEMENTED + VERIFIED (tool, classes, 15 tests)
PLN_02_ACCEPTANCE          = PENDING. "Each item has a verified recovery source" needs a current backup: the scheduled
                             backup in PLN-03, plus the Docker volume export. Then re-run this inventory
```

## Hand-off to PLN-03
- Backups must run on a schedule, with an RPO shorter than the operator workspace's change rate. A one-off copy is not enough.
- The three Docker monitoring volumes must be exported. They are non-authoritative, but they are state.
- Storage: root has about 9.0 GiB free. The WDC NTFS volume is the backup target (noexec is fine for archives). Independent-host (Tier 3) copies are PLN-05.
