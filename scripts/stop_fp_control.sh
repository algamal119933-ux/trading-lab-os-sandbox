#!/usr/bin/env bash
# Stop an FP control paper runtime, leaving every ledger on disk.
#
# Usage: scripts/stop_fp_control.sh FP-CONTROL-2
#
# Named volumes and the evidence directory are deliberately not removed: the
# evidence outlives the runtime that produced it, and a restart must be able to
# recover its position from the ledgers.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

if [[ $# -ne 1 ]]; then
  echo "usage: scripts/stop_fp_control.sh FP-CONTROL-ROLE" >&2
  exit 2
fi

# The substitution's exit status must be checked before eval sees it: `eval
# "$(...)"` reports eval's success, not the selector's, and a refusal would then
# surface as an unbound variable several lines later instead of as a refusal.
# Stop-class selection: a PAUSED instance must be stoppable. Asking for
# start-class selection here made PAUSED unstoppable, so the only exit from it
# was editing the registry by hand.
if ! FP_SELECTION="$(python3 scripts/fp_instance.py "$1" --stop)"; then
  exit 3
fi
eval "$FP_SELECTION"
export FP_ROLE FP_INSTANCE_DIR FP_BOT_NAME FP_DB_PATH FP_LOG_PATH FP_EVIDENCE_DIR

docker compose -f docker-compose.yml -f docker-compose.fp.yml down

echo "Stopped $FP_ROLE. Evidence retained in freqtrade/user_data/$FP_INSTANCE_DIR/evidence."
