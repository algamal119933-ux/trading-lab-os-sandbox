#!/usr/bin/env bash
# P3-PLN-03 scheduled backup: one append-only, verified backup set of every Trading Lab OS root.
#
# Run by tlos-p3-backup.timer (scripts/p3/units/). Writes only a new <stamp> directory under the
# target. It never deletes or overwrites a set; retention is a separate Owner decision. It needs no
# network and starts no runtime. Exit status: that of `backup.py create` (0 = created and verified).
set -euo pipefail
umask 077  # sets hold configuration (including the runtime .env): owner-only (P3 security audit SEC-03)
export PYTHONDONTWRITEBYTECODE=1
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="${TLOS_PYTHON:-/home/hamza/projects/trading/trading_lab_os_final/.venv/bin/python}"
H=/home/hamza
# The backup store is configured once (research/p3/storage.py: env or ~/.config/tlos-p3/storage.json; mount,
# target and filesystem UUID are all required; there is no implicit default). One call both checks the live
# store and exports it, so the location written to is the location checked. The preflight refuses (exit 3) a
# missing or unusable configuration, an unmounted or symlinked mountpoint, the system disk, a different or
# unreadable UUID, and a target that resolves off the store. Only "not mounted" is waited for (a catch-up run
# at boot can start before the disk mounts), at most TLOS_STORE_WAIT_S seconds (default 300).
WAIT="${TLOS_STORE_WAIT_S:-300}"
DEADLINE=$(( $(date +%s) + WAIT ))
while :; do
  ERR="$(mktemp)"
  if STORE="$("$PY" "$REPO/research/p3/storage.py" --preflight --shell 2>"$ERR")"; then rm -f "$ERR"; break; fi
  cat "$ERR" >&2
  if grep -q "is not mounted" "$ERR" && [ "$(date +%s)" -lt "$DEADLINE" ]; then rm -f "$ERR"; sleep 10; continue; fi
  rm -f "$ERR"
  echo "BACKUP_REFUSED: backup store preflight failed (see the lines above)" >&2; exit 3
done
eval "$STORE"
TARGET="$TLOS_STORAGE_TARGET"
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
