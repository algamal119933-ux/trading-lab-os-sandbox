#!/usr/bin/env bash
# Shared preamble for the Freqtrade helper scripts.
# Every trading-related command must pass the paper guard first (fail closed).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

HOST_CONFIG="${HOST_CONFIG:-freqtrade/user_data/config.json}"
CONTAINER_CONFIG="${CONTAINER_CONFIG:-/freqtrade/user_data/config.json}"
STRATEGY="${STRATEGY:-PlumbingSmokeStrategy}"
EXCHANGE="${EXCHANGE:-binance}"
# PAIRS may be pre-set as an array by the caller; otherwise use the v1 pair set.
if [[ -z "${PAIRS+x}" ]]; then
  PAIRS=("BTC/USDT" "ETH/USDT")
fi

require_paper_config() {
  if [[ ! -f "$HOST_CONFIG" ]]; then
    echo "Missing $HOST_CONFIG. Run: cp freqtrade/user_data/config.paper.json.example $HOST_CONFIG" >&2
    exit 2
  fi
  python3 scripts/paper_guard.py --config "$HOST_CONFIG"
}
