#!/usr/bin/env bash
# Deterministic backtest. Timerange is required: an implicit window is not evidence.
# Usage: scripts/backtest.sh <TIMERANGE> [extra freqtrade args...]
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

TIMERANGE="${1:-}"
if [[ -z "$TIMERANGE" ]]; then
  echo "usage: scripts/backtest.sh <TIMERANGE e.g. 20250901-20260501> [extra args]" >&2
  exit 2
fi
shift

require_paper_config

docker compose run --rm freqtrade backtesting \
  --config "$CONTAINER_CONFIG" \
  --strategy "$STRATEGY" \
  --timerange "$TIMERANGE" \
  --enable-protections \
  --export trades \
  "$@"
