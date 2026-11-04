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
  during another drill. Check the timer first: `systemctl --user list-timers tlos-p3-backup.timer`. H2, H4 and H5
  must not overlap the timer's firing (03:30 UTC + up to 300 s, `Persistent=true`). `backup_host_install.sh`
  enforces this for H2 and H4 (§ "Legacy wrapper race"); for H5 it is the operator's check. Not within 10 min
  after a boot either: `Persistent=true` makes a missed 03:30 run fire right after the user manager starts.
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
Every checkout move and every wrapper replacement goes through `scripts/p3/ops/backup_host_install.sh`. It changes
no unit and no timer: its only `systemctl` calls are two read-only `show` queries.

**Legacy wrapper race.** Until H4, the installed wrapper is the original, and it takes **no lock**. The install
script's lock (exit 75 if held) therefore protects only against the governed wrapper. Against the original, three
checks apply, in this order:
1. **Unit idle:** `tlos-p3-backup.service` is `inactive` or `failed` (a oneshot is `activating` while it runs).
   Otherwise exit 3, nothing changed.
2. **Timer far enough:** the timer's next firing (`NextElapseUSecRealtime`) is more than 900 s away. The firing may
   come up to `RandomizedDelaySec` = 300 s after that time, which only widens the gap. Otherwise, or if the time
   cannot be read, exit 3, nothing changed.
3. **Re-check after the change:** if the unit became active during the change, exit 4 with `RACE`. The change is
   complete; read the run's journal before going on.

What each step risks if the original starts anyway (by hand, or a clock jump):
- **H4:** nothing. `mv` gives the wrapper path a new inode; a running original keeps reading its own open file, and
  the next start reads the whole new one (test: `test_the_atomic_rename_leaves_an_already_open_wrapper_reading…`).
- **H2:** the original calls `backup.py` from the tree being checked out. A file read mid-checkout can fail that
  run's `create` or `verify`. Sets appear only by rename from `.<stamp>.incoming`, so no partial set is published.
  The original's own restart is unproven (it masks failures with `|| true`), so after a `RACE`, also check the
  runtime with `runtime-check --probe` (the H5 rollback block).
- The hourly health job also reads the tree; a run during the checkout can fail once. The next hour is clean.
```bash
systemctl --user show -p ActiveState --value tlos-p3-backup.service | tee "$E/h2_unit_state.txt"   # inactive
git -C "$P3" rev-parse HEAD | tee "$E/h2_before.txt"          # expect 6d2f20756c417e2707ae2344055ff0cd3f130c77
git -C "$P3" fetch origin main                                # changes no working file
git -C "$P3" show <M>:scripts/p3/ops/backup_host_install.sh > "$E/install.sh"   # 6d2f2075 does not contain it yet
git -C "$P3" rev-parse <M>:scripts/p3/ops/backup_host_install.sh; git hash-object "$E/install.sh"   # equal
bash "$E/install.sh" checkout <M> | tee "$E/h2_checkout.txt"
#   refuses a dirty tree, a SHA not on origin/main, and anything that is not a fast-forward; ends detached at <M>
git -C "$P3" rev-parse HEAD | tee "$E/h2_after.txt"           # = <M>
systemctl --user list-timers tlos-p3-backup.timer tlos-p3-health.timer --no-pager | tee "$E/h2_timers.txt"
```
- **PASS:** exit 0, `CHECKOUT 6d2f2075… -> <M>`, HEAD = `<M>`, detached.
- **Effect:**
  - The **old** wrapper keeps running on schedule. It calls the new `backup.py` with its old `--volume` arguments,
    which still works: the volume archives are now private (#105), and the set is owner-only.
  - The hourly health job and the Control Room now run the #108 code, so the PLN-09 walkthrough can follow.
  - Read the next hourly health run before going on.
- **Rollback:** with the unit inactive, `git -C "$P3" checkout --detach 6d2f20756c417e2707ae2344055ff0cd3f130c77`
  (the script prints this line).

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
systemctl --user cat tlos-p3-backup.service | sha256sum | tee "$E/h4_unit.txt"
bash "$P3/scripts/p3/ops/backup_host_install.sh" install | tee "$E/h4_install.txt"
#   INSTALLED <W> sha256 <governed> (mode 700) · ROLLBACK_COPY <W>.pre-p3-<stamp> sha256 561c44d2…
sha256sum "$W" "$P3/scripts/p3/ops/tlos_runtime_backup.sh" | tee "$E/h4_after.txt"   # both equal
stat -c '%a %U:%G' "$W"; ls -A "$(dirname "$W")" | grep -c '^\.backup\.sh\.' # 700 hamza:hamza · 0 temporaries
systemctl --user cat tlos-p3-backup.service | sha256sum | diff - "$E/h4_unit.txt"   # unit unchanged
```
What `install` does, in order, and refuses (exit 3, nothing replaced) at the first step that does not hold:
1. the unit is `inactive` or `failed`, and the wrapper lock is free;
2. the current wrapper's sha256 is exactly the original `561c44d2…` (an already-installed governed copy is a no-op);
3. `cp -p` keeps a rollback copy `"$W.pre-p3-<UTC stamp>"`, whose sha256 must equal the original;
4. the governed script is copied to a temporary file **in the wrapper's own directory**, set to 0700, and must hash
   to the governed blob and pass `bash -n`;
5. one `mv -f` renames it over `$W`. Same directory, same filesystem: the rename is atomic, so the unit can only
   ever start the whole old file or the whole new one. Any refusal removes the temporary file.
- **Rollback:** with the unit inactive,
  `bash "$P3/scripts/p3/ops/backup_host_install.sh" rollback "$W.pre-p3-<stamp>"`. It accepts only a copy whose
  sha256 is the original, and replaces the wrapper the same atomic way. Then `sha256sum "$W"` = `561c44d2…`.

## H5: one backup run through the existing unit (authorization 3)
Note the legacy mirror state first, so it can be shown untouched afterwards:
```bash
sha256sum ~/tlos-backups-ssd-mirror/{latest,previous}/SOURCE_SET | tee "$E/h5_legacy_before.txt"
systemctl --user start tlos-p3-backup.service                  # oneshot: returns when the run ends (≤ 1 h)
systemctl --user show tlos-p3-backup.service -p Result -p ExecMainStatus | tee "$E/h5_result.txt"
journalctl --user -u tlos-p3-backup.service --since "-2h" --no-pager > "$E/h5_journal.txt"
```
- **Before:** the runtime is `active`, and no marker exists
  (`test ! -e "$XDG_RUNTIME_DIR/tlos-p3-backup.runtime-stopped"`). Without a running runtime the run can only be
  archive-only (exit 7), which is not H5.
- **PASS:** `Result=success`, `ExecMainStatus=0`, and the journal shows, in this order, `ARCHIVE_INTEGRITY = PASS`,
  `LIVE_DATA_COVERAGE = PASS (observed before the runtime stop, bound into <set>)` and `BACKUP = PASS (<set>, …)`.
  `BACKUP = PASS` is printed only when the set's own record carries `PASS before_runtime_stop`.
- The runtime is stopped only between the coverage observation and the proven restore (minutes).
- **On a non-zero exit, do not retry.** Keep the state and send the evidence. The code says where it stopped:
  - 3: refused before anything;
  - 4: coverage refused, runtime untouched;
  - 5: mirror failed, set valid, runtime back;
  - 6: runtime not restored, or (`RUNTIME_RECOVERY_FAILED`) an earlier run's stop could not be recovered, so no
    backup was attempted; the marker is kept;
  - 7: archive only: the set verifies and is mirrored, but `LIVE_DATA_COVERAGE` is not PASS. Not a hardened backup;
  - 75: another run holds the lock.
- **Runtime rollback if needed:**
  ```bash
  systemctl --user start tlos-runtime.service
  $PY $P3/scripts/p3/backup.py runtime-check --compose-project tlos_runtime "${SVCS[@]}" --wait 180 --probe
  ```

## R: interrupted runs, the marker and reboots (wrapper behavior; nothing to run)
The wrapper's order, after the lock:
0. **Store identity:** `/srv/project-data` must have UUID `6d45029b…`, else exit 3. Nothing is started or written,
   the recovery included, and the marker is kept. The runtime's bind mounts live under the store, and its unit
   and guard (`tlos-runtime.sh`, reported to check the mount and UUID; `GUARD_OK` logged at boot, PLN-04) are
   host-local and not pinned by this repository. So the wrapper does not rely on them.
1. **Marker present** (an earlier run stopped the runtime and was killed: SIGKILL, timeout escalation): the runtime
   is started (or, if someone started it since, only checked) and must be running and answering its probes.
   - Proven: `RECOVERED`, the marker is removed, and the run continues from a running runtime.
   - Not proven: `BACKUP_REFUSED: RUNTIME_RECOVERY_FAILED`, exit 6. No set, no coverage report, no stop; the marker
     stays, so the next run tries again.
2. Target check, then this run's stamp (taken after the recovery).
3. **Runtime running:** fresh `LIVE_DATA_COVERAGE` is observed now and must PASS (exit 4 otherwise). After a
   recovery this is a new observation, never the interrupted run's.
4. **Runtime not running and no marker:** no backup run stopped it. The cause is **unknown** to the wrapper: an
   Owner stop, a failed boot start and a missing mount look the same (`RUNTIME_DOWN_CAUSE_UNKNOWN`). It is never
   started here. The set is archive-only: exit 7, fail-closed.
5. Stop, create, proven restore (exit 6 wins over any other status), verify, mirror. Then the two results:
   `ARCHIVE_INTEGRITY`, then `LIVE_DATA_COVERAGE` read back from the set's record. Exit 0 only with both.

**Reboot and the marker.** The marker is in `$XDG_RUNTIME_DIR` (`/run/user/1000`), a tmpfs that exists as long as
the user manager. With linger `yes` that is from boot to shutdown, so a logout does not clear it; a reboot or power
loss does. That is deliberate:
- `systemctl --user stop` does not survive a reboot. After a boot, whether the runtime runs depends only on the boot
  path: the unit is enabled with the boot-ready drop-in (`boot-autostart.sh e8e68231…`). Run 4 on 2026-10-30, a
  clean reboot, showed it active at 11.2 s, 23/23, 0 restarts.
- A persistent marker would outlive the fact it records. After a reboot, it could make the backup start a runtime
  the Owner had stopped since. So a cleared marker loses nothing the boot path does not already cover.
- **Gap:** if the boot path fails to start the runtime, there is no marker. This case is **not proven**: the
  late-mount path is unit-tested only, and power-loss recovery is untested (decision G is Option C; the UPS
  implementation and its acceptance are pending). The next backup then finds
  the runtime down and unmarked, does not start it, and ends with exit 7. That shows as a failed unit and as
  `coverage UNPROVEN` in the Control Room, never as a hardened backup. Before this change, the same situation gave
  exit 0.
- A run cut off by a power loss leaves only `.<stamp>.incoming` on the HDD. It is never a published set; it is
  replaced only if the same stamp recurs, and otherwise stays until the Owner removes it.
- With `Persistent=true`, a missed 03:30 run fires about 12.6 s after boot, before the HDD is mounted on a slow boot
  (29.6 s on 2026-10-30). That run refuses with exit 3 (store UUID), and the next attempt is the following 03:30.
  This is unchanged by this PR; changing the timer needs Owner authorization.

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
bash $P3/scripts/p3/ops/restore_app_checks.sh "$X/data" <stamp> "$E/h7_app.json" | tee "$E/h7_app.txt"
#   G8: exit 0 and RESTORE_APP_CHECKS = PASS
docker ps -a --filter name=tlos-drill-prom --format '{{.Names}}' | wc -l             # 0: the throwaway is gone
```
G8 is four checks with fixed PASS conditions. Each is FAIL otherwise; no step waits a fixed time.

| Check | PASS only if |
|---|---|
| `grafana_db SQLITE_INTEGRITY` | read-only `pragma integrity_check` = `ok` and `foreign_key_check` returns nothing |
| `mlflow APPLICATION_READ` | the pinned `ghcr.io/mlflow/mlflow:v3.15.1` opens the restored `mlflow.db` with `MlflowClient`, exits 0 and lists ≥ 1 experiment |
| `prometheus APPLICATION_READY` | the pinned `prom/prometheus:v3.14.0`, started on the restored TSDB, stays running and answers `/-/ready` before the 300 s deadline (polled every 2 s) |
| `prometheus WAL_RECOVERY` | its log contains `WAL replay completed`, **no** log line mentions a repair or corruption, and `count(count_over_time({__name__=~".+"}[15m]))` evaluated **at the set stamp** is > 0 |

- **Why the stamp:** samples the throwaway server scrapes after it starts are later than the stamp, so they cannot
  satisfy the WAL check. Only data restored from the set can.
- **What G8 proves about Prometheus:**
  - the restored TSDB directory opens in the pinned v3.14.0, and the head is rebuilt from the checkpoint and WAL
    segments without a repair or a corruption report;
  - samples from the 15 minutes before the stamp are queryable. Blocks are cut at 2-hour boundaries, so this recent
    data lives only in the WAL and head. It was therefore captured in the set and replayed.
- **What it cannot prove:**
  - completeness: "> 0 series" is not "every series and sample up to the stop"; nothing is compared with the live
    server's series count or last sample time;
  - silent loss in the newest WAL segment: a torn record is detected only if Prometheus reports it, and the clean
    shutdown before the export makes one unlikely, not impossible;
  - older history: older blocks are checked only as the files `verify` hashes, not queried one by one;
  - the production configuration: the throwaway uses the image's default `prometheus.yml`, so scrape jobs, rules
    and alerts are not exercised;
  - the production path and ownership: it runs as `hamza` on the scratch copy; the live data is `nobody:nogroup`;
  - another Prometheus version; and a second run on the same scratch, which this run has already written to.
- **Cleanup:** the Prometheus container (`tlos-drill-prom-<stamp>-<pid>`) is removed on every exit: pass, fail,
  error, SIGINT and SIGTERM. The last command above confirms it.
- **Consistency limits:**
  - `verify` and the drill's hash comparison prove the restored files equal the set. They are **not** application
    consistency, and are never reported as such.
  - G8 checks the applications on the restored copy. Grafana is checked at the database file only; a started
    Grafana is **not** part of G8.
  - Prometheus writes to the scratch copy when it starts (new WAL segment, lock file). That is the scratch copy, not
    the set.
- **Not proven here:** ownership and modes (the drill restores as `hamza`), and empty directories.
- **Rollback:** nothing to roll back. The scratch `$X` holds restored secrets (0700). It is kept until the Owner
  decides.

## After H7
- Claude prepares the PLN-03 re-acceptance record from `$E`, and the first PLN-02 runtime-data inventory
  (`state_inventory.py --profile runtime_data`, PR #110).
- **Open dependency:** the 4 Grafana directories unreadable to `hamza` will fail the inventory's coverage walk.
  That is an Owner decision about permissions, made together with the Grafana `777` review, not a tool exception.
- `LOCAL_BACKUP_HARDENED = PASS` only when G1–G8 all pass on the H5 set. Synthetic CI tests are not host acceptance.
