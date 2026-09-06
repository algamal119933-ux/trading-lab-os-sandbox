#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "Missing .env. Run: cp .env.example .env and change the passwords." >&2
  exit 2
fi
if [[ ! -f freqtrade/user_data/config.json ]]; then
  echo "Missing config.json. Run: cp freqtrade/user_data/config.paper.json.example freqtrade/user_data/config.json" >&2
  exit 2
fi
python3 scripts/paper_guard.py
docker compose up -d

echo "Started PAPER stack. Check: docker compose ps"
