#!/usr/bin/env bash
# P3-PLN-03 scheduled backup: one append-only, verified backup set of every Trading Lab OS root.
#
# Run by tlos-p3-backup.timer (scripts/p3/units/). Writes only a new <stamp> directory under the
# target. It never deletes or overwrites a set; retention is a separate Owner decision. It needs no
# network and starts no runtime. Exit status: that of `backup.py create` (0 = created and verified).
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="${TLOS_PYTHON:-/home/hamza/projects/trading/trading_lab_os_final/.venv/bin/python}"
TARGET="${TLOS_BACKUP_TARGET:-/mnt/tlos-wdc/tlos-backups}"
H=/home/hamza
mountpoint -q /mnt/tlos-wdc || { echo "BACKUP_REFUSED: /mnt/tlos-wdc is not mounted" >&2; exit 3; }
exec "$PY" "$REPO/scripts/p3/backup.py" create --target "$TARGET" \
  --root trading="$H/projects/trading" \
  --root tlos-paper="$H/tlos-paper" \
  --root tlos-ar-render="$H/tlos-ar-render" \
  --root tlos-evidence-docs="$H/Documents/TLOS-Evidence" \
  --root claude-memory="$H/.claude/projects/-home-hamza-projects-trading/memory" \
  --repo trading_lab_os_final="$H/projects/trading/trading_lab_os_final" \
  --volume trading_lab_os_final_grafana_data \
  --volume trading_lab_os_final_mlflow_data \
  --volume trading_lab_os_final_prometheus_data
