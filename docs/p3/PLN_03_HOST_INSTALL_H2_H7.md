# P3-PLN-03: host installation of the backup integration (H2–H7) and rollback

**Status:** prepared, **not executed**. Each step **H2, H3+H4, H5 and H7** runs only under its **own** Owner
authorization. H6 is read-only evidence collection after H5.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · PAPER_LAUNCH_AUTHORIZED = NO · no reboot, no SSH/UFW change,
no unit or timer change, no private GPG key on the host.

## 0. Basis
- **Code:** PR #107, merged by the Owner at `<M>` with a normal merge commit. `<M>` below is that SHA.
- **Host evidence (H1):** `backup_h1_inputs_20261103T233303Z.txt`, sha256 `362f0c87…7bc77f`.
  - **Wrapper:** `~/projects/trading/tlos-runtime/backup.sh`, 0700, 3391 bytes, sha256 `561c44d2…b531`. It is
    byte-identical to commit `ca0e917` of `scripts/p3/ops/tlos_runtime_backup.sh`, which was rebuilt from the
    numbered H1 text and hash-checked.
  - **Unit:** `Type=oneshot`, `TimeoutStartUSec=1h`, `TimeoutStopUSec=1min 30s`, `KillMode=control-group`,
    `UMask=0077`, no `OnFailure`.
  - **Checkout:** `tlos-p3` at `6d2f2075`, detached HEAD.
  - **Data:** Grafana ≥ 531 MB (incomplete: 4 directories unreadable to `hamza`), Prometheus 5.2 MB (TSDB + WAL),
    MLflow 0.87 MB (`mlflow.db` SQLite; artifact root `/mlflow/artifacts`).
  - **Free space:** `/` 151 GB, `/srv/project-data` 1.89 TB.
  - **Containers:** no Docker healthcheck on any of the three. `flock` present. `XDG_RUNTIME_DIR=/run/user/1000`.
- **Expected sizes:**
  - a new full set ≈ the 2026-11-03 set (757 MB, whose 0.54 GB volume exports are replaced by the live data) plus
    whatever the four unreadable Grafana directories hold;
  - SSD: two full generations ≈ 1.6 GB + the untouched legacy copies (1.08 GB), against 151 GB free and a 20 GiB
    margin.

## 1. Rules for every step
- **Timing:** one host operation at a time; never within 45 min of the 04:20Z unattended-upgrades window; never
  during another drill. Check the timer first: `systemctl --user list-timers tlos-p3-backup.timer`. H4 and H5 must
  not overlap the timer's next firing.
- **Evidence:** everything goes to
  `E=~/tlos-paper/p3-evidence/backup_install_$(date -u +%Y%m%dT%H%M%SZ).d`, created with `mkdir -m 700 "$E"`.
- **Stop rule:** anything unexpected means stop, keep the state, and send the evidence. No improvised fixes.

Shell variables used below:
```bash
P3=~/projects/trading/tlos-p3; PY=~/projects/trading/trading_lab_os_final/.venv/bin/python
D=/srv/project-data/trading-data/runtime/data; H=/home/hamza; W=~/projects/trading/tlos-runtime/backup.sh
ROOTS=(--root trading=$H/projects/trading --root tlos-paper=$H/tlos-paper --root tlos-ar-render=$H/tlos-ar-render
       --root tlos-evidence-docs=$H/Documents/TLOS-Evidence --root claude-memory=$H/.claude/projects/-home-hamza-projects-trading/memory)
DATA=(--data grafana=$D/grafana --data prometheus=$D/prometheus --data mlflow=$D/mlflow)
SVCS=(--service grafana --service prometheus --service mlflow)
```

## H2: tools checkout update (authorization 1)
```bash
cd "$P3" && git status --porcelain | tee "$E/h2_status.txt"   # must be empty
git rev-parse HEAD | tee "$E/h2_before.txt"                   # expect 6d2f20756c417e2707ae2344055ff0cd3f130c77
git fetch origin main && git merge-base --is-ancestor HEAD <M> && echo FF_OK | tee -a "$E/h2_before.txt"
git -c advice.detachedHead=false checkout --detach <M>
git rev-parse HEAD | tee "$E/h2_after.txt"                    # = <M>
systemctl --user list-timers tlos-p3-backup.timer tlos-p3-health.timer --no-pager | tee "$E/h2_timers.txt"
```
- **PASS:** a clean tree, a fast-forward, and HEAD = `<M>`.
- **Effect:**
  - The **old** wrapper keeps running on schedule. It calls the new `backup.py` with its old `--volume` arguments,
    which still works: the volume archives are now private (#105), and the set is owner-only.
  - The hourly health job and the Control Room now run the #108 code, so the PLN-09 walkthrough can follow.
  - Read the next hourly health run before going on.
- **Rollback:** `git -C "$P3" checkout --detach 6d2f20756c417e2707ae2344055ff0cd3f130c77`.

## H3 + H4: read-only pre-checks, then install the wrapper (authorization 2)
**H3**, read-only, with the runtime running:
```bash
$PY $P3/scripts/p3/backup.py coverage --compose-project tlos_runtime "${DATA[@]}" "${ROOTS[@]}" --json "$E/h3_coverage.json"
#   expect exit 0, LIVE_DATA_COVERAGE = PASS, no UNCOVERED_RW, no STALE_DATA_SOURCE
$PY $P3/scripts/p3/backup.py coverage --compose-project tlos_runtime --data grafana=tlos_runtime_grafana_data "${ROOTS[@]}"
#   negative N2: expect exit 1 (STALE_DATA_SOURCE + UNCOVERED_RW)
$PY $P3/scripts/p3/backup.py runtime-check --compose-project tlos_runtime "${SVCS[@]}" --probe | tee "$E/h3_runtime.txt"
#   expect RUNTIME_RECOVERY = PASS with "application PASS" for all three. This proves the probes and the published
#   loopback ports before the wrapper relies on them.
docker run --rm --network none python:3.12-slim sh -c 'python3 -V; tar --version|head -1; find --version|head -1; xargs --version|head -1; sha256sum --version|head -1' | tee "$E/h3_helper.txt"
#   a throwaway container with no mount and no network: GNU tar/findutils/coreutils, Python 3.12
```
**Stop if** coverage is not PASS, a probe is not PASS (for example a port not published), or the helper lacks GNU
tools. Without these, a scheduled run would refuse (exit 4) or report a failed restore (exit 6).

**H4**, which changes only the wrapper file:
```bash
sha256sum "$W" | tee "$E/h4_before.txt"                        # must be 561c44d2c0602a7a0471b60a024bc3d7a25ef5d98457391f1ea6c5c17413b531
cp -p "$W" "$W.pre-p3-$(date -u +%Y%m%dT%H%M%SZ)"
systemctl --user cat tlos-p3-backup.service | sha256sum | tee "$E/h4_unit.txt"
install -m 0700 "$P3/scripts/p3/ops/tlos_runtime_backup.sh" "$W"
sha256sum "$W" "$P3/scripts/p3/ops/tlos_runtime_backup.sh" | tee "$E/h4_after.txt"   # both equal
bash -n "$W" && stat -c '%a %U:%G' "$W"                        # 700 hamza:hamza
```
- **Rollback:** `install -m 0700 "$W.pre-p3-<stamp>" "$W"`, then `sha256sum "$W"` must equal `561c44d2…`.

## H5: one backup run through the existing unit (authorization 3)
Note the legacy mirror state first, so it can be shown untouched afterwards:
```bash
sha256sum ~/tlos-backups-ssd-mirror/{latest,previous}/SOURCE_SET | tee "$E/h5_legacy_before.txt"
systemctl --user start tlos-p3-backup.service                  # oneshot: returns when the run ends (≤ 1 h)
systemctl --user show tlos-p3-backup.service -p Result -p ExecMainStatus | tee "$E/h5_result.txt"
journalctl --user -u tlos-p3-backup.service --since "-2h" --no-pager > "$E/h5_journal.txt"
```
- **PASS:** `Result=success`, `ExecMainStatus=0`, and the journal shows `BACKUP = PASS (<set>, mirrored …)`.
- The runtime is stopped only between the coverage observation and the proven restore (minutes).
- **On a non-zero exit, do not retry.** Keep the state and send the evidence. The code says where it stopped:
  - 3: refused before anything;
  - 4: coverage refused, runtime untouched;
  - 5: mirror failed, set valid, runtime back;
  - 6: runtime not restored;
  - 75: another run holds the lock.
- **Runtime rollback if needed:**
  ```bash
  systemctl --user start tlos-runtime.service
  $PY $P3/scripts/p3/backup.py runtime-check --compose-project tlos_runtime "${SVCS[@]}" --wait 180 --probe
  ```

## H6: gates (read-only)
```bash
S=/srv/project-data/tlos-backups/<stamp from the journal>
$PY $P3/scripts/p3/backup.py verify --set "$S"                                         # G2: VERIFY = PASS
$PY -c "import json,sys;r=json.load(open(sys.argv[1]));c=r['live_data_coverage'] or {};print(c.get('LIVE_DATA_COVERAGE'),c.get('observed'),c.get('report_sha256'));print({k:v['files'] for k,v in r['data_sources'].items()})" "$S/BACKUP_RECORD.json"
sha256sum ~/tlos-paper/p3-evidence/backup_coverage_<stamp>.json                       # G1: equals report_sha256
grep -c ' grafana.db$' "$S/data/grafana.files.sha256"                                  # G1: 1
find "$S" -perm /077 | wc -l; stat -c '%a %U %n' "$S"/data/*.tar                       # G3: 0 · 600 hamza
readlink ~/tlos-backups-ssd-mirror/current                                            # G4: sets/<stamp>
$PY $P3/scripts/p3/backup.py verify --set ~/tlos-backups-ssd-mirror/current            # G4: PASS
diff <(cd "$S" && find . -type f -printf '%P\n'|sort) <(cd ~/tlos-backups-ssd-mirror/current/ && find . -type f -printf '%P\n'|sort)   # G4: empty
sha256sum ~/tlos-backups-ssd-mirror/{latest,previous}/SOURCE_SET | diff - "$E/h5_legacy_before.txt"   # legacy untouched
$PY $P3/scripts/p3/backup.py runtime-check --compose-project tlos_runtime "${SVCS[@]}" --probe     # G5: PASS ×3
systemctl --user list-timers tlos-p3-backup.timer --no-pager; systemctl --user cat tlos-p3-backup.service | sha256sum   # G6: unchanged
```

## H7: isolated restore from the SSD copy + application consistency (authorization 4)
Only throwaway containers run, with `--network none`, on the **restored copy**. Production data and containers are
never touched.
```bash
mkdir -p -m 700 /srv/project-data/tlos-restore-drills; X=/srv/project-data/tlos-restore-drills/<stamp>   # X must not exist
umask 077; $PY $P3/scripts/p3/backup.py drill --set ~/tlos-backups-ssd-mirror/current --scratch "$X" \
  --config-load trading/trading_lab_os_final --json "$E/h7_drill.json"
#   G7: PLN_03_RESTORE_DRILL = PASS incl. data:grafana/prometheus/mlflow, git:*, config_load:*; source.tier = SECOND_DEVICE_MIRROR
python3 -c "import sqlite3,sys;[print(p,sqlite3.connect('file:'+p+'?mode=ro',uri=True).execute('pragma integrity_check').fetchone()[0]) for p in sys.argv[1:]]" \
  "$X/data/grafana/grafana.db" "$X/data/mlflow/mlflow.db"                          # G8: ok, ok
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$X/data/mlflow:/mlflow" ghcr.io/mlflow/mlflow:v3.15.1 \
  python -c "import mlflow;c=mlflow.MlflowClient('sqlite:////mlflow/mlflow.db');e=c.search_experiments();print(len(e),[x.artifact_location for x in e][:3])"   # G8: experiments listed
docker run -d --name tlos-drill-prom --network none --user "$(id -u):$(id -g)" -v "$X/data/prometheus:/prometheus" \
  prom/prometheus:v3.14.0 --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/prometheus
sleep 30; docker exec tlos-drill-prom wget -qO- http://127.0.0.1:9090/-/ready; docker logs tlos-drill-prom 2>&1 | grep -Ei 'replay|corrupt|error' | tee "$E/h7_prom.txt"
docker rm -f tlos-drill-prom                                                        # G8: "Ready", WAL replay completed, no corruption
```
- **Consistency limits:** file-hash equality is not application consistency. G8 is where it is checked, on the
  restored copy only.
- **Not proven here:** ownership and modes (the drill restores as `hamza`), and empty directories.
- **Rollback:** nothing to roll back. The scratch `$X` holds restored secrets (0700). It is kept until the Owner
  decides.

## After H7
- Claude prepares the PLN-03 re-acceptance record from `$E`, and the first PLN-02 runtime-data inventory
  (`state_inventory.py --profile runtime_data`, PR #110).
- **Open dependency:** the 4 Grafana directories unreadable to `hamza` will fail the inventory's coverage walk.
  That is an Owner decision about permissions, made together with the Grafana `777` review, not a tool exception.
- `LOCAL_BACKUP_HARDENED = PASS` only when G1–G8 all pass on the H5 set. Synthetic CI tests are not host acceptance.
