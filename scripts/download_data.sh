#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
TIMERANGE="${1:-20250101-}"
python3 scripts/paper_guard.py

docker compose run --rm freqtrade download-data \
  --config /freqtrade/user_data/config.json \
  --timeframes 15m 1h 4h \
  --timerange "$TIMERANGE"
