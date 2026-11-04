#!/usr/bin/env bash
# Trading Lab OS daily backup, 3TB-HDD destination (host-level replacement for the ExecStart of
# tlos-p3-backup.service while its repo script still hard-codes the retired /mnt/tlos-wdc target).
# Governed copy: scripts/p3/ops/tlos_runtime_backup.sh. Installed at ~/projects/trading/tlos-runtime/backup.sh,
# mode 0700. It patches the host original (sha256 561c44d2…b531, 2026-11-03), and the repository diff is the change.
#
# 1. One run at a time (flock).
# 2. Recovery first. If an earlier run stopped the runtime and was killed before restoring it (SIGKILL, timeout
#    escalation), its marker is found. This run restores the runtime and proves it (running, answering its probes)
#    before anything else. If that fails, no backup is attempted (exit 6) and the marker stays for the next run.
#    The marker lives in $XDG_RUNTIME_DIR, as long as the user manager: a reboot clears it, and the boot path
#    (tlos-runtime.service enabled) owns the runtime from then on.
# 3. Checks that /srv/project-data is the expected HDD (UUID).
# 4. While the runtime runs, LIVE_DATA_COVERAGE is observed (`compose down` removes the containers) and written to
#    a report that `create` binds into this run's set. A runtime that is not running and that no backup run stopped
#    (no marker) was stopped on purpose: it is never started here. Its set can only be archive-only (exit 7).
# 5. Stops the monitoring runtime so its SQLite (Grafana, MLflow) and TSDB/WAL (Prometheus) files are exported
#    quiescent, then restores it if it was running. The restore must be proven: each of grafana, prometheus and
#    mlflow running, started by this restoration, and answering its own readiness probe. A failed restore fails
#    the run (exit 6). It is never masked.
# 6. Runs the governed P3-PLN-03 tool (scripts/p3/backup.py create) with the same roots and repo bundle as
#    before plus the live bind-mounted service data, into /srv/project-data/tlos-backups/<this run's stamp>.
#    Only that set is verified and mirrored; an older set is never taken for this run's result.
# 7. Publishes a verified full copy of that set on the SSD (backup.py mirror: the last verified generation is
#    never destroyed while publishing; the legacy partial copies latest/ and previous/ are left untouched).
#
# Protection this gives: SSD data -> HDD (cross-device); HDD runtime data -> SSD mirror (cross-device).
# It is NOT offsite: one machine, one PSU. Offsite is P3-PLN-05 (Owner destination decision, PR #95).
# 8. Reports two separate results: ARCHIVE_INTEGRITY (the set verifies and is mirrored) and LIVE_DATA_COVERAGE
#    (read back from the set's own record). BACKUP = PASS, exit 0, needs both.
# PAPER / RESEARCH ONLY. Exit: 0 = hardened backup: created, verified, mirrored, LIVE_DATA_COVERAGE = PASS bound
#   into the set, runtime restored.
#   3 refused (store, target, stamp) · 4 coverage refused before the stop · 5 mirror failed (set valid on the HDD)
#   6 runtime not restored or not recovered (whatever else failed first; that status is printed)
#   7 archive only: set verified and mirrored, LIVE_DATA_COVERAGE not PASS. Not a hardened backup
#   75 another run holds the lock · 130/143 interrupted · otherwise create/verify failed.
set -euo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1
H="${TLOS_HOME:-/home/hamza}"
P3="${TLOS_P3:-$H/projects/trading/tlos-p3}"
PY="${TLOS_PYTHON:-$H/projects/trading/trading_lab_os_final/.venv/bin/python}"
MOUNT="${TLOS_MOUNT:-/srv/project-data}"
UUID=6d45029b-05c4-47ca-92a3-76d33d40f507
TARGET="$MOUNT/tlos-backups"
MIRROR="$H/tlos-backups-ssd-mirror"
DATA="$MOUNT/trading-data/runtime/data"
EVID="$H/tlos-paper/p3-evidence"
PROJECT=tlos_runtime
SERVICES=(--service grafana --service prometheus --service mlflow)
RUNDIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
MARKER="$RUNDIR/tlos-p3-backup.runtime-stopped"
ROOT_ARGS=(--root trading="$H/projects/trading"
  --root tlos-paper="$H/tlos-paper"
  --root tlos-ar-render="$H/tlos-ar-render"
  --root tlos-evidence-docs="$H/Documents/TLOS-Evidence"
  --root claude-memory="$H/.claude/projects/-home-hamza-projects-trading/memory")
DATA_ARGS=(--data "grafana=$DATA/grafana" --data "prometheus=$DATA/prometheus" --data "mlflow=$DATA/mlflow")

exec 9>"$RUNDIR/tlos-p3-backup.lock"
flock -n 9 || { echo "BACKUP_REFUSED: another backup run holds $RUNDIR/tlos-p3-backup.lock" >&2; exit 75; }

runtime_proven() {  # [--started-after <epoch>]: grafana, prometheus and mlflow running and answering their probes
  "$PY" "$P3/scripts/p3/backup.py" runtime-check --compose-project "$PROJECT" "${SERVICES[@]}" "$@" \
    --wait "${TLOS_RUNTIME_WAIT_S:-180}" --probe
}

if [ -e "$MARKER" ]; then
  echo "RECOVERING: an earlier run stopped the runtime at $(cat "$MARKER") and did not restore it" >&2
  recovered=0
  if systemctl --user is-active --quiet tlos-runtime.service; then
    runtime_proven && recovered=1          # started since by someone else: proven, not restarted
  else
    since="$(date +%s)"
    systemctl --user start tlos-runtime.service && runtime_proven --started-after "$since" && recovered=1
  fi
  if [ "$recovered" = 1 ]; then
    rm -f "$MARKER"
    echo "RECOVERED: the runtime is running and answering; this run now starts from a running runtime" >&2
  else
    echo "BACKUP_REFUSED: RUNTIME_RECOVERY_FAILED: the runtime an earlier run stopped is not proven back;" \
      "no backup is attempted and the marker is kept" >&2
    exit 6
  fi
fi

[ "$(findmnt -no UUID "$MOUNT" 2>/dev/null || true)" = "$UUID" ] \
  || { echo "BACKUP_REFUSED: $MOUNT is not the expected HDD ($UUID)" >&2; exit 3; }
[ -d "$TARGET" ] || { echo "BACKUP_REFUSED: $TARGET missing" >&2; exit 3; }
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SET="$TARGET/$STAMP"
[ ! -e "$SET" ] || { echo "BACKUP_REFUSED: $SET already exists" >&2; exit 3; }

WAS_ACTIVE=0
COV_ARGS=()
if systemctl --user is-active --quiet tlos-runtime.service; then
  WAS_ACTIVE=1
  COV="$EVID/backup_coverage_$STAMP.json"
  "$PY" "$P3/scripts/p3/backup.py" coverage --compose-project "$PROJECT" "${DATA_ARGS[@]}" "${ROOT_ARGS[@]}" \
    --json "$COV" || { echo "BACKUP_REFUSED: LIVE_DATA_COVERAGE before the stop, see $COV" >&2; exit 4; }
  COV_ARGS=(--coverage-report "$COV")
else
  echo "RUNTIME_LEFT_STOPPED: tlos-runtime is not running and no backup run stopped it; it is not started here" >&2
  echo "LIVE_DATA_COVERAGE = UNPROVEN: no container can be observed; this set can only be archive-only" >&2
fi

restore_runtime() {
  [ "$WAS_ACTIVE" = 1 ] || return 0
  local since
  since="$(date +%s)"
  systemctl --user start tlos-runtime.service || return 1
  runtime_proven --started-after "$since" || return 1
  rm -f "$MARKER"
}
on_exit() {
  local rc=$?
  trap - EXIT
  if ! restore_runtime; then
    # A runtime left down outranks whatever ended the run: the documented status is 6. The original status is kept
    # in the message, not lost.
    echo "RUNTIME_RESTORE_FAILED (the run had ended with exit $rc before the restore was attempted)" >&2
    rc=6
  fi
  exit "$rc"
}
trap 'exit 143' TERM
trap 'exit 130' INT
trap on_exit EXIT
if systemctl --user is-active --quiet tlos-runtime.service; then
  date -u +%Y-%m-%dT%H:%M:%SZ > "$MARKER"
  systemctl --user stop tlos-runtime.service
fi

"$PY" "$P3/scripts/p3/backup.py" create --target "$TARGET" --stamp "$STAMP" \
  "${ROOT_ARGS[@]}" \
  --repo trading_lab_os_final="$H/projects/trading/trading_lab_os_final" \
  "${DATA_ARGS[@]}" "${COV_ARGS[@]}"

trap - EXIT
restore_runtime || { echo "RUNTIME_RESTORE_FAILED" >&2; exit 6; }

"$PY" "$P3/scripts/p3/backup.py" verify --set "$SET"

# Cross-device copy of the whole set on the SSD: verified before it is published, never deleting to make room.
"$PY" "$P3/scripts/p3/backup.py" mirror --set "$SET" --mirror "$MIRROR" --keep "${TLOS_MIRROR_KEEP:-2}" \
  --margin-gib "${TLOS_MIRROR_MARGIN_GIB:-20}" --json "$EVID/backup_mirror_$STAMP.json" \
  || { echo "SSD_MIRROR=FAIL: $SET is valid on the HDD; the SSD copy was not published" >&2; exit 5; }
echo "ARCHIVE_INTEGRITY = PASS ($SET verified, mirrored to $MIRROR/current)"

# Hardened only if the set's own record says so: the same field the Control Room and gate G1 read.
COVERAGE="$("$PY" -c 'import json, sys
c = json.load(open(sys.argv[1])).get("live_data_coverage") or {}
print(c.get("LIVE_DATA_COVERAGE") or "NONE", c.get("observed") or "-")' "$SET/BACKUP_RECORD.json")"
if [ "$COVERAGE" = "PASS before_runtime_stop" ]; then
  echo "LIVE_DATA_COVERAGE = PASS (observed before the runtime stop, bound into $SET)"
  echo "BACKUP = PASS ($SET, mirrored to $MIRROR/current)"
else
  echo "BACKUP = ARCHIVE_ONLY ($SET): LIVE_DATA_COVERAGE = UNPROVEN (record: $COVERAGE); not a hardened backup" >&2
  exit 7
fi
