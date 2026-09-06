#!/usr/bin/env bash
# Recursive-indicator analysis. Usage: scripts/recursive.sh <TIMERANGE> [extra args...]
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

TIMERANGE="${1:-}"
if [[ -z "$TIMERANGE" ]]; then
  echo "usage: scripts/recursive.sh <TIMERANGE e.g. 20250901-20260501> [extra args]" >&2
  exit 2
fi
shift

require_paper_config

docker compose run --rm freqtrade recursive-analysis \
  --config "$CONTAINER_CONFIG" \
  --strategy "$STRATEGY" \
  --timerange "$TIMERANGE" \
  -p "${PAIRS[0]}" \
  "$@"
