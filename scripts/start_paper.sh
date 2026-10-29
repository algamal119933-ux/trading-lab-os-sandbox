#!/usr/bin/env bash
# Start the local PAPER-only stack. Refuses to start without a paper-safe config.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

if [[ ! -f .env ]]; then
  echo "Missing .env. Run: install -m 600 .env.example .env and change the placeholder passwords." >&2
  exit 2
fi

if grep -q "CHANGE_ME" .env; then
  echo "Refusing to start: .env still contains CHANGE_ME placeholders." >&2
  echo "Set a real local password for every CHANGE_ME_* value first." >&2
  exit 2
fi

require_paper_config
docker compose up -d

echo "Started PAPER stack (dry_run=true). Check: docker compose ps"
