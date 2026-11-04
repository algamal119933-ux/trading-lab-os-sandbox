# P3-PLN-02 — State & Recovery Inventory (execution record)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-02 (frozen at fcd06b21, sha256 2c057cb5…487f4d).
It is executed under [`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md), merged at 7b1b1fa1 with post-merge CI green.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCHED = NO

## Deliverable (implemented)
| Item | Path | Reuse classification (§10) |
|---|---|---|
| Inventory library | `research/p3/state_inventory.py` | BUILD_SMALL_MISSING_LAYER. It classifies and verifies only, and delegates all verification to existing tools |
| Declared state classes (runtime / worktree / operator profiles) | `research/p3/records/state_classes.json` | record |
| CLI | `scripts/p3/state_inventory.py` (outside the P2-era FP runtime tree `scripts/*.py`) | wraps `scripts/publish_evidence_digest.py verify_archive` (REUSE_EXISTING) |
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

## Acceptance update (2026-10-25T18:51Z)
Re-run against backup set `20261025T185052Z` (`scripts/p3/backup.py` through `scripts/p3/scheduled_backup.sh`): **all 14 roots PASS**. That is runtime, tlos-control plus 9 worktrees, the operator workspace, tlos-ar-render, the evidence docs and memory, with 0 unclassified, 0 unreadable and every class verified. The Docker volumes are in the set.

**Correction (2026-11-03):** "the Docker volumes" were the named volumes `trading_lab_os_final_*`. The live runtime
containers bind-mount `/srv/project-data/trading-data/runtime/data/{grafana,prometheus,mlflow}`, which no root above
lists. Those volume exports are not evidence of runtime-data completeness; the root results above stand. Live data is
covered from the set whose record shows `LIVE_DATA_COVERAGE = PASS` ([`PLN_03_BACKUP_RESTORE.md`](PLN_03_BACKUP_RESTORE.md)).
**PLN-02 ACCEPTANCE = PASS** as of that set. It is re-checked after each scheduled backup.

## Runtime service data under `/srv/project-data` (preparation, 2026-11-04; host acceptance NOT claimed)
**Why this is a new scope, not a repeated test.** The 2026-10-25 acceptance stands for the 14 roots it inventoried.
After the 2026-10-29 store migration, the runtime's Grafana, Prometheus and MLflow data lives in bind-mounted
directories under `/srv/project-data/trading-data/runtime/data/`, which no inventoried root contains. The contract
asks for 100% of TLOS state, so these roots must be inventoried once. This adds state; it does not re-test what was
accepted.

**How their recovery source is verified.** Profile `runtime_data`, class `service_data`, recovery kind
`BACKUP_SET_DATA`.
- The data is owned by the containers and changes while the runtime runs, so a per-file hash against a manifest
  could never be current.
- The recovery source is the newest backup set that covers **this** root. Every link is required:
  - the set verifies;
  - its record lists the root as a data source with `LIVE_DATA_COVERAGE = PASS`, which `backup.py` proved by
    re-reading the source as root;
  - a persisted drill of **that** set restored `data:<name>`.
- Coverage is still walked (names and `lstat` only). An unreadable directory is a coverage FAIL, as for every
  other root.

**Host run, after PLN-03 host steps H5 and H7, under the Owner's authorization for those steps.** It is read-only:
```bash
for s in grafana prometheus mlflow; do
  python3 scripts/p3/state_inventory.py --root /srv/project-data/trading-data/runtime/data/$s --profile runtime_data \
    --backup-set <the H5 set> --drill-json <the H7 drill of that set> --json ~/tlos-paper/p3-evidence/inventory_$s.json
done
```
**Open dependency.** If a service directory cannot be traversed by the backup user (Prometheus and MLflow
ownership is not yet known here), coverage fails truthfully. The fix is an Owner decision about directory
permissions, not a tool exception. Tests: `tests/test_p3_state_inventory_runtime_data.py`.

## Runtime service data: host acceptance (2026-11-04)
The three roots under `/srv/project-data/trading-data/runtime/data/` were inventoried against the re-accepted
PLN-03 set `20261104T143958Z`. The drill link was the H7 re-acceptance drill
`h7_reaccept_20261104T162813Z.d/drill.json` (`backup_set = 20261104T143958Z`, `data:*` PASS). Claude verified the
evidence below by reading the files (read-only), not from a summary.

| Root | Walk | Files | Unreadable dirs | Coverage | Recovery (BACKUP_SET_DATA) | Inventory |
|---|---|---|---|---|---|---|
| prometheus | unprivileged (`hamza`) | 37 (35 in the set; live data grows) | 0 | PASS | PASS | **PASS** |
| mlflow | unprivileged (`hamza`) | 1 | 0 | PASS | PASS | **PASS** |
| grafana | unprivileged (`hamza`) | 1,259 | **4** (`csv`, `pdf`, `png`, `unified-search`) | FAIL | PASS | NOT_PASS (exit 1) |
| grafana | privileged, read-only (Owner) | 1,259 | 0 | PASS | PASS | **PASS** (exit 0) |

**How the recovery link was proven:** each Recovery PASS is the tool's own check of every link:
- the set verifies;
- its record lists the root as a data source with `LIVE_DATA_COVERAGE = PASS` (`before_runtime_stop`);
- the drill of that same stamp restored `data:<name>`.

**Why the Grafana coverage holds:**
- The privileged walk saw exactly the 1,259 files the unprivileged walk saw. The four directories it could not
  enter hold no files.
- The same count was read independently at backup time. `backup.py` read the source as root, compared it with the
  archive (`live == archived`), and recorded `files: 1259`.
- So the privileged walk found nothing the backup does not cover.

**Evidence** (`/home/hamza/tlos-paper/p3-evidence/`; both manifests verify and cover every file):

| Directory | sha256 of its `SHA256SUMS` | Written (UTC) |
|---|---|---|
| `pln02_runtime_data_20261104T174252Z.d` (3 roots, unprivileged) | `31b8d3c898e75d03c27cf1a8c57d649eef76797da20551bc7389bb5eee1f25bc` | 2026-11-04T17:42:52Z |
| `pln02_grafana_privileged_20261104T174741Z.d` (Grafana, privileged) | `8487c47690b112eba4f7e63dac7f6aeb5502f4a03920102f1c9c3fca562f10c6` | 2026-11-04T17:47:51Z |

**Tool identity:** `research/p3/state_inventory.py`, its class profile and `backup.py` are byte-identical in every
tools checkout the host has had since H2 (`b8667293`, `8e7597d2`, `20c9779d`). They were last changed in #110.

**Owner-reported, not evidenced in the files:**
- the privileged walk's exact invocation and identity;
- that no permission was changed to obtain it.

A read-only `stat` of the Grafana root and the four directories would evidence the second point. It is not a gate.

**Lesson (Grafana permissions):**
- **Observed:** an unprivileged walk cannot enter four Grafana directories, so coverage fails truthfully.
- **Cause (Owner-reported):** they belong to the container user (UID 472) and are not traversable by `hamza`.
- **Method that worked:** a privileged read-only walk run by the Owner, with the same `--backup-set` and
  `--drill-json`. No filesystem change, and no tool exception.
- **For the next run:** the scheduled re-check of this root needs the same Owner-run privileged walk. The ownership
  of these directories is decided in the separate Grafana permission review, never by loosening modes so that an
  inventory can pass.

**State found since the 2026-10-25 inventory that no PLN-02 run has walked** (found by Claude while checking the
"100%" claim against current main; not a host observation):
- `~/projects/trading/tlos-runtime/`. It holds the installed backup wrapper (`backup.sh`) and the runtime's compose
  override. It sits inside the backup root `trading`, so set `20261104T143958Z` archives it in
  `roots/trading.tar.zst` and lists its files in `roots/trading.files.sha256`. That is a recovery source, but no
  inventory has proven it file by file. The existing tool can do so with no code change (read-only, `operator`
  profile; `load_manifest` reads that manifest format):
  ```bash
  S=/srv/project-data/tlos-backups/sets/20261104T143958Z   # or the newest scheduled set
  python3 scripts/p3/state_inventory.py --root ~/projects/trading/tlos-runtime --profile operator \
    --cold-manifest "$S/roots/trading.files.sha256" --cold-prefix tlos-runtime/ \
    --json ~/tlos-paper/p3-evidence/pln02_tlos_runtime_<stamp>.json
  ```
  A file changed after the set was written reports STALE. Then the next scheduled set is used, not a tool exception.
- The `tlos-runtime.service` user unit. The P3 timers are governed in `scripts/p3/units/`; this unit is not, and its
  file location is not inside any backup root that the repository records. Its recovery source is **UNVERIFIED**. A
  read-only `systemctl --user cat tlos-runtime.service` shows the path. Then it is either inside a backup root or a
  gap.

```text
PLN_02_RUNTIME_DATA_INVENTORY = PASS (grafana, prometheus, mlflow; set 20261104T143958Z)
PLN_02_ACCEPTANCE             = NOT YET. PASS for the 14 recorded roots and the 3 runtime-data roots. Two later
                                items are not yet proven: the tlos-runtime directory (in the set, not inventoried)
                                and the tlos-runtime.service unit (recovery source UNVERIFIED). "100% of TLOS state"
                                is not claimed until both are.
PLN_02_FORMAL_CLOSURE         = NO. It needs both items above, then an Owner merge of the record that shows them.
```
This record takes effect when the Owner merges it.

## Remaining items closed: tlos-runtime and the TLOS systemd user state (2026-11-04)
**Host evidence:** `pln02_remaining_20261104T182628Z.d`. Claude re-hashed every file against its `SHA256SUMS`
(sha256 of the manifest `513888d3…d58c`), all OK.

**1. `~/projects/trading/tlos-runtime`.**
- Inventory (`operator` profile): 10 files, 0 unclassified, 0 unreadable; recovery 10 PASS, 0 STALE, 0 MISSING
  → `PLN_02_STATE_INVENTORY = PASS`.
- The report does not name the manifest it used. Claude therefore checked the link independently against set
  `20261104T143958Z` on the SSD mirror (read-only):
  - `sha256(SHA256SUMS)` = `7f721940…148b`, the record's digest;
  - `roots/trading.files.sha256` = its `SHA256SUMS` entry (`086c4052…5a00`);
  - the entries for `units/tlos-runtime.service`, `boot-autostart.sh`, `tlos-runtime.sh` and `README.md` equal the
    bytes of the live files;
  - the H7 re-acceptance drill of this set restored `root:trading` PASS.

**2. TLOS systemd user state** (`~/.config/systemd/user`). This directory is in no backup root. Claude compared every
TLOS file in it, byte for byte, with a recovery source (read-only listing and copies; nothing on the host was written):

| Live file | Class | Recovery source | Isolated test (scratch only) |
|---|---|---|---|
| `tlos-runtime.service` (`a81bab23…`) | PERSISTENT | `tlos-runtime/units/tlos-runtime.service`, in set `20261104T143958Z` (manifest entry = live bytes) | **PASS**: byte-identical |
| `tlos-runtime.service.d/20-boot-autostart.conf` (`d625f777…`) | REPRODUCIBLE | generated by `tlos-runtime/boot-autostart.sh` (`dropin_text`, in the same set) | **PASS**: the function was evaluated alone with `HERE` = the install path, and its output is byte-identical. No `systemctl` call |
| `tlos-p3-backup.service` | REPRODUCIBLE | git `f174678:scripts/p3/units/tlos-p3-backup.service` (the host runs that version, not main's) | **PASS**: byte-identical |
| `tlos-p3-backup.timer`, `tlos-p3-health.{service,timer}` | REPRODUCIBLE | `scripts/p3/units/` on main | **PASS**: byte-identical |
| `tlos-p3-backup.service.d/10-hdd-destination.conf` (`4cd00835…`), `20-umask-0077.conf` (`d2bb7c9f…`) | PERSISTENT | **none before this record.** Governed copies are now in `scripts/p3/ops/systemd/tlos-p3-backup.service.d/` | **PASS**: governed copy = live bytes |
| `default.target.wants/tlos-runtime.service`, `timers.target.wants/tlos-p3-{backup,health}.timer` | REPRODUCIBLE | `systemctl --user enable` from each unit's `[Install]` | not byte-compared (symlinks) |
| `tlos-p2-window-fp-control-3.{service,timer}` (disabled) | DISPOSABLE | P2 is closed; cold backup `tlos-host-extras` (2026-10-25) | n/a |

The merged units (unit plus drop-ins) also pass `systemd-analyze verify` offline, on renamed copies in a temp
directory:
- no parse error;
- the only finding is that the `ExecStart` script does not exist on the test machine.

**What this does not claim:**
- A saved `systemctl cat` output was not used as a recovery source. Every PASS above compares real file bytes.
- `20-boot-autostart.conf` embeds `boot-autostart.sh`'s own directory, so the reconstruction is exact only when
  `tlos-runtime` is restored to `~/projects/trading/tlos-runtime`. That is where the set's `trading` root restores.

**Inventory scope (reconciled, so PLN-02 does not grow indefinitely):** PLN-02 covers the TLOS-owned state:
- the recorded file roots;
- the 3 runtime-data roots;
- `tlos-runtime`;
- the TLOS systemd user units above.

Host provisioning outside the user's TLOS files is not PLN-02 file state:
- fstab, linger, docker and containerd enablement;
- the sshd and Tailscale settings;
- the unattended-upgrades configuration;
- UPS and NUT.

It is rebuilt by the procedures that own it (PLN-04, PLN-06, decision H). `boot-autostart.sh diagnose` checks the
pieces the runtime needs.

**Grafana root (read-only stat, same evidence directory; nothing was changed):**
- The root `/srv/project-data/trading-data/runtime/data/grafana` is mode `drwxrwxrwx` (777), owner `472:0`, on `/dev/sdb1` (ext4, `rw,relatime`).
- `csv`, `pdf` and `png` are `700`, and `unified-search` is `750`, all owned by `472:0`. That explains the 4 unreadable directories.
- **Implication:** with no sticky bit, any local account or process can create, rename or delete entries in the
  root, including replacing `grafana.db`. The single-user host limits the exposure, but it is an integrity weakness
  of live monitoring state.
- The mode is an Owner decision in the Grafana permission review. It is not changed to make an inventory pass.

```text
PLN_02_TLOS_RUNTIME_INVENTORY  = PASS (10 files; set 20261104T143958Z, link verified by Claude)
PLN_02_SYSTEMD_USER_PROVENANCE = PASS (every TLOS unit and drop-in byte-identical to a recovery source)
PLN_02_ACCEPTANCE              = PASS: 100% of the PLN-02 scope above has a verified recovery source
PLN_02_FORMAL_CLOSURE          = on the Owner's merge of this record, with CI green
GRAFANA_ROOT_MODE_777          = OBSERVED, not changed: Owner decision
```
