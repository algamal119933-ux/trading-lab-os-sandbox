#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
TIMERANGE="${1:-20250101-}"
python3 scripts/paper_guard.py

docker compose run --rm freqtrade lookahead-analysis \
  --config /freqtrade/user_data/config.json \
  --strategy PlumbingSmokeStrategy \
  --timeframe 15m \
  --timerange "$TIMERANGE"
