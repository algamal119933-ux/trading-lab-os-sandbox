#!/usr/bin/env bash
# Deterministic market-data acquisition (CLOUD-0 / C0.7).
#
# Market data is intentionally NOT committed. This script is the single documented
# way to reproduce it. It refuses to touch a dataset that is already frozen by a
# lock file unless the operator explicitly re-freezes, so an experiment can never
# silently move its own dataset underneath itself.
#
# Usage:
#   scripts/download_data.sh <START-END>            # e.g. 20250701-20260907
#   ALLOW_REFREEZE=1 scripts/download_data.sh <START-END>
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

TIMERANGE="${1:-}"
if [[ -z "$TIMERANGE" ]]; then
  echo "usage: scripts/download_data.sh <TIMERANGE e.g. 20250701-20260907>" >&2
  exit 2
fi

if [[ -z "${TIMEFRAMES+x}" ]]; then
  TIMEFRAMES=("5m" "1h")
fi
DATA_DIR="freqtrade/user_data/data/${EXCHANGE}"
LOCK="${LOCK:-research/datasets/dataset_v1.lock.json}"
ALLOW_REFREEZE="${ALLOW_REFREEZE:-0}"

require_paper_config

if [[ -f "$LOCK" && -d "$DATA_DIR" && "$ALLOW_REFREEZE" != "1" ]]; then
  echo "DATASET_FROZEN: $LOCK exists and $DATA_DIR already holds data." >&2
  echo "Re-downloading would change frozen fingerprints mid-protocol." >&2
  echo "If a re-freeze is genuinely intended, re-run with ALLOW_REFREEZE=1 and record why." >&2
  exit 2
fi

echo "Exchange:   ${EXCHANGE} (spot)"
echo "Pairs:      ${PAIRS[*]}"
echo "Timeframes: ${TIMEFRAMES[*]}"
echo "Timerange:  ${TIMERANGE}"

docker compose run --rm freqtrade download-data \
  --config "$CONTAINER_CONFIG" \
  --exchange "$EXCHANGE" \
  --pairs "${PAIRS[@]}" \
  --timeframes "${TIMEFRAMES[@]}" \
  --timerange "$TIMERANGE" \
  --data-format-ohlcv feather

echo
echo "Download complete. Now audit and fingerprint before any experiment:"
echo "  python3 scripts/audit_data.py --data-dir $DATA_DIR \\"
echo "    $(printf -- '--pair %s ' "${PAIRS[@]}")\\"
echo "    $(printf -- '--timeframe %s ' "${TIMEFRAMES[@]}")\\"
echo "    --out freqtrade/user_data/baseline_v1_data_audit.json --lock $LOCK"
