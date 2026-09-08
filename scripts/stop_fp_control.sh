#!/usr/bin/env bash
# Stop the FP-CONTROL-1 paper runtime, leaving every ledger on disk.
#
# Named volumes and the evidence directory are deliberately not removed: the
# evidence outlives the runtime that produced it, and a restart must be able to
# recover its position from the ledgers.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

docker compose -f docker-compose.yml -f docker-compose.fp.yml down

echo "Stopped FP-CONTROL-1. Evidence retained in freqtrade/user_data/fp-control-1/evidence."
