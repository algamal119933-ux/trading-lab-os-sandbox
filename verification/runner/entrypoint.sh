#!/usr/bin/env bash
# Runs inside the isolated container (--network none). Freqtrade must load the
# exchange's market list before it backtests; with no network it reads the case's
# pinned exchangeInfo snapshot from a static file server on the container's own
# loopback. The engine itself is unmodified.
set -euo pipefail
CASE_DIR="${CASE_DIR:-/case}"
STUB_DIR="${STUB_DIR:-/tmp/markets-stub}"
STUB_PORT="${STUB_PORT:-18080}"
mkdir -p "$STUB_DIR/api/v3"
cp "$CASE_DIR/exchangeInfo.json" "$STUB_DIR/api/v3/exchangeInfo"
python -m http.server "$STUB_PORT" --bind 127.0.0.1 --directory "$STUB_DIR" >/dev/null 2>&1 &
i=0
until python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$STUB_PORT/api/v3/exchangeInfo')" 2>/dev/null; do
    i=$((i + 1))
    [ "$i" -lt 50 ] || { echo "RUNNER = MARKETS_STUB_DID_NOT_START" >&2; exit 3; }
    sleep 0.1
done
exec freqtrade backtesting "$@"
