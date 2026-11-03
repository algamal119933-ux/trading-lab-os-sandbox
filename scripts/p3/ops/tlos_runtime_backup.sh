#!/usr/bin/env bash
# Trading Lab OS daily backup, 3TB-HDD destination (host-level replacement for the ExecStart of
# tlos-p3-backup.service while its repo script still hard-codes the retired /mnt/tlos-wdc target).
#
# 1. Checks that /srv/project-data is the expected HDD (UUID).
# 2. Briefly stops the monitoring runtime so its SQLite and TSDB files are exported quiescent, then
#    restarts it if it was running (always, also on failure).
# 3. Runs the governed P3-PLN-03 tool (scripts/p3/backup.py create) with the same roots and repo bundle
#    as scripts/p3/scheduled_backup.sh, plus the live runtime volumes, into /srv/project-data/tlos-backups.
#    The set is append-only and verified by `create`; this script verifies it again.
# 4. Mirrors the newest set's runtime-volume exports to the SSD (two generations), checksum-verified,
#    because a copy of HDD-resident data on the same HDD is a local recovery copy, not protection
#    against an HDD failure.
#
# Protection this gives: SSD data -> HDD (cross-device); HDD runtime data -> SSD mirror (cross-device).
# It is NOT offsite: one machine, one PSU. Offsite is P3-PLN-05 (Owner destination decision, PR #95).
# PAPER / RESEARCH ONLY. Exit: 0 = backup created, verified and mirrored.
set -euo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1
H=/home/hamza
P3="$H/projects/trading/tlos-p3"
PY="${TLOS_PYTHON:-$H/projects/trading/trading_lab_os_final/.venv/bin/python}"
MOUNT=/srv/project-data
UUID=6d45029b-05c4-47ca-92a3-76d33d40f507
TARGET="$MOUNT/tlos-backups"
MIRROR="$H/tlos-backups-ssd-mirror"

[ "$(findmnt -no UUID "$MOUNT" 2>/dev/null || true)" = "$UUID" ] \
  || { echo "BACKUP_REFUSED: $MOUNT is not the expected HDD ($UUID)" >&2; exit 3; }
[ -d "$TARGET" ] || { echo "BACKUP_REFUSED: $TARGET missing" >&2; exit 3; }

WAS_ACTIVE=0
systemctl --user is-active --quiet tlos-runtime.service && WAS_ACTIVE=1
restore_runtime() { [ "$WAS_ACTIVE" = 1 ] && systemctl --user start tlos-runtime.service || true; }
trap restore_runtime EXIT
[ "$WAS_ACTIVE" = 1 ] && systemctl --user stop tlos-runtime.service

"$PY" "$P3/scripts/p3/backup.py" create --target "$TARGET" \
  --root trading="$H/projects/trading" \
  --root tlos-paper="$H/tlos-paper" \
  --root tlos-ar-render="$H/tlos-ar-render" \
  --root tlos-evidence-docs="$H/Documents/TLOS-Evidence" \
  --root claude-memory="$H/.claude/projects/-home-hamza-projects-trading/memory" \
  --repo trading_lab_os_final="$H/projects/trading/trading_lab_os_final" \
  --volume tlos_runtime_grafana_data \
  --volume tlos_runtime_mlflow_data \
  --volume tlos_runtime_prometheus_data

restore_runtime
trap - EXIT

SET="$(find "$TARGET" -mindepth 1 -maxdepth 1 -type d -name '2*' | sort | tail -1)"
"$PY" "$P3/scripts/p3/backup.py" verify --set "$SET"

# Cross-device mirror of the HDD-resident runtime data: latest + previous generation on the SSD.
mkdir -p "$MIRROR"
NEW="$MIRROR/.incoming"
rm -rf "$NEW"
mkdir -p "$NEW/volumes"
cp "$SET/BACKUP_RECORD.json" "$SET/SHA256SUMS" "$NEW/"
cp "$SET"/volumes/*.tar "$NEW/volumes/"
(cd "$NEW" && grep ' volumes/' SHA256SUMS | sha256sum --quiet -c -) \
  || { echo "MIRROR_FAIL: checksum mismatch in $NEW" >&2; exit 1; }
basename "$SET" > "$NEW/SOURCE_SET"
rm -rf "$MIRROR/previous"
[ -d "$MIRROR/latest" ] && mv "$MIRROR/latest" "$MIRROR/previous"
mv "$NEW" "$MIRROR/latest"
echo "MIRROR = PASS ($MIRROR/latest <- $(basename "$SET"))"
