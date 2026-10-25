#!/usr/bin/env bash
# P3-PLN-06 scheduled health check with alert delivery (master plan §19 severities).
#
# Run by tlos-p3-health.timer (scripts/p3/units/). It writes the Prometheus textfile (for a
# node-exporter textfile collector, when one is installed) and journals one line per run. On
# WARNING or CRITICAL it raises a desktop notification, so the operator is reached even with no
# scrape configured. Read-only towards the system: it changes nothing it checks.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="${TLOS_PYTHON:-/home/hamza/projects/trading/trading_lab_os_final/.venv/bin/python}"
PROM="${TLOS_HEALTH_TEXTFILE:-/home/hamza/tlos-paper/p3-evidence/tlos_p3_health.prom}"
RC=0
OUT="$("$PY" "$REPO/scripts/p3/health_check.py" --prom-textfile "$PROM" 2>&1)" || RC=$?
SUMMARY="$(printf '%s\n' "$OUT" | grep -E '^  (WARNING|CRITICAL)' | sed -E 's/ +/ /g' | head -5 || true)"
logger -t tlos-p3-health "rc=$RC $(printf '%s\n' "$OUT" | tail -1)"
if [ "$RC" -ne 0 ] && command -v notify-send >/dev/null 2>&1; then
  URGENCY=normal
  [ "$RC" -eq 2 ] && URGENCY=critical
  notify-send -u "$URGENCY" "Trading Lab OS health: $(printf '%s\n' "$OUT" | tail -1)" "$SUMMARY" || true
fi
exit "$RC"
