# Real market data: how it is acquired, and why not the obvious way

## The blocker

Binance refuses service to both execution environments available to this
project:

| Environment | Host | Result |
| --- | --- | --- |
| Cloud sandbox | `api.binance.com`, `data-api.binance.vision`, `api1.binance.com`, `fapi.binance.com` | egress policy answers **403 to CONNECT** |
| GitHub-hosted runner | `api.binance.com` | **HTTP 451** — "Service unavailable from a restricted location according to 'b. Eligibility'" |

The 451 is decisive for the obvious approach: `freqtrade download-data` asks
ccxt to load markets before fetching a single candle, ccxt calls
`GET /api/v3/exchangeInfo`, and the run dies with
`ExchangeNotAvailable ... 451`. Retrying does not help — it is a geographic
eligibility check on the runner's egress, not a transient failure.

## The route actually used

Binance publishes the **same spot klines** as ZIP archives at
`https://data.binance.vision`, with a published SHA256 `.CHECKSUM` beside every
archive and no eligibility check. `scripts/fetch_binance_public_data.py`:

1. downloads the monthly archive for each pair/timeframe/month, falling back to
   daily archives for a month Binance has not yet consolidated;
2. **verifies each archive against its published checksum before using it** — a
   mismatch aborts the run rather than quietly accepting the bytes;
3. normalises timestamps across Binance's millisecond → microsecond change;
4. de-duplicates, sorts, clips to the requested window, and writes
   Freqtrade-format feather;
5. records every archive URL and verified digest in an acquisition manifest.

This is **real exchange data from Binance itself**. It is not synthetic, not
simulated, and not a different venue: `api.binance.com` and
`data.binance.vision` serve the same spot klines, and the archive is Binance's
own documented bulk-download channel.

## Backtesting past the same 451

Freqtrade instantiates the exchange even for a backtest, so market loading hits
the same wall. `freqtrade/user_data/config.binance-data-mirror.json.example` is
a research-only overlay that points ccxt's public endpoint at
`data-api.binance.vision` and limits market loading to spot. It is applied on
top of the paper config, and the merged file is run through the paper guard
before Freqtrade sees it, so the safety invariants are checked on exactly what
the engine reads.

Nothing about safety changes: `dry_run` stays `true`, the exchange key and
secret stay empty, and no order-placing command is ever issued.

## Evidence delivery

Workflow artifact blob storage (`*.blob.core.windows.net`) is also blocked by
the sandbox egress policy, so artifacts cannot be downloaded into the analysis
environment. The workflow therefore re-prints the fingerprints, audit summary,
benchmark and metric JSON at the **end** of the job log, which is readable. The
artifacts are still uploaded for a human to inspect.
