# DATASET-V2 — research specification

Frozen **before** any BASELINE-1 outcome was observed. Machine-readable twin:
`research/datasets/dataset_v2.lock.json`.

## Relationship to Dataset V1

Dataset V1 is **preserved unchanged** as immutable historical evidence:
`research/datasets/dataset_v1.lock.json`, its fingerprints, and
`freqtrade/user_data/baseline_v1_data_audit.json` are not rewritten to fit any
new download. V2 is a separate, additive dataset with its own identifier.

## Universe

| Field | Value |
| --- | --- |
| Exchange | Binance |
| Market type | **spot** |
| Pairs | `BTC/USDT`, `ETH/USDT` |
| Primary timeframe | `1h` (signals) |
| Detail timeframe | `5m` (intra-candle fill simulation) |
| Acquisition range | 2020-12-01T00:00:00Z → 2026-08-31T23:59:59Z |
| Freqtrade timerange | `20201201-20260901` (end-exclusive) |
| Storage | feather |

## Windows

| Window | Range | Freqtrade timerange | Status |
| --- | --- | --- | --- |
| Warm-up | 2020-12-01 → 2020-12-31 | — | never scored |
| Development | 2021-01-01 → 2024-12-31 | `20210101-20250101` | open |
| Validation | 2025-01-01 → 2026-08-31 | `20250101-20260901` | closed until the baseline and protocol are frozen |

The warm-up month carries ~744 hourly candles. BASELINE-1 declares
`startup_candle_count = 600` (three times its longest lookback), so the slow EMA
has converged before the first Development bar is scored.

## Why there is no Locked OOS in this dataset

**None of this data qualifies as a pristine holdout.** Dataset V1 work already
inspected 2025-09 through 2026-09 — its development, validation *and* OOS
windows all sit inside 2025-2026 — and the passive behaviour of that period is
recorded in this repository. Declaring any 2025-2026 span "untouched
out-of-sample" would be false, and a holdout you have already looked at is not a
holdout.

So the second window is labelled **Validation**, not OOS, and is used exactly
once with the frozen strategy. The first strict prospective holdout is a
**forward-paper / prospective OOS** run over data that did not exist at freeze
time. That is handled later, not here.

## Regime coverage rationale

Chosen from calendar and passive-market structure alone, before any active
result existed. Four years of Development spans materially different regimes —
the 2021 bull run and its late-2021 top, the 2022 drawdown, the 2023 recovery
and the 2024 continuation — rather than the single strongly bearish stretch that
made Dataset V1's development window so easy to misread. Twenty months of
Validation covers a distinct later period.

This is a deliberate improvement over Dataset V1, whose development window was
bearish end to end (BTC −29.6 %, ETH −48.8 %), where merely sitting in cash
looked like skill. The V1 exposure-matched figure of **−7.83 % is historical
evidence only and is not an acceptance threshold for V2**; V2's own passive
benchmarks are recomputed on V2 data under the frozen fee assumption.

## Frozen assumptions

| Field | Value |
| --- | --- |
| Fee | 0.001 per side (0.1 %), set explicitly in the config, not inherited from an exchange default |
| Slippage | none modelled |
| Wallet | 100 USDT simulated |
| Stake | 10 USDT fixed |
| Max open trades | 2 |
| `dry_run` | true throughout |

## Integrity contract

Two digests are recorded per file:

* **`raw_file_sha256`** — the bytes on disk.
* **`canonical_candle_content_sha256`** — `CANONICAL_CANDLE_V1`: sha256 over a
  version tag followed by one line per candle, candles sorted by timestamp, each
  line `ts|open|high|low|close|volume` with integer milliseconds and Python's
  shortest round-tripping float repr.

The canonical digest is the drift signal. A Feather/PyArrow version bump, a
different compression codec or changed file metadata all move the raw hash while
the market data is identical, and treating that as drift would block every
re-download. `scripts/audit_data.py --lock` therefore reports a raw-hash
mismatch with a matching canonical digest as a *note*, and only a canonical
mismatch as `CONTENT DRIFT`. Locks that predate canonical digests — Dataset V1's
— keep the stricter old behaviour, so V1 evidence does not get looser.

Required checks per pair and timeframe: exact timerange, expected cadence,
duplicate timestamps, gaps, NaN/non-finite cells, OHLC validity, monotonic
timestamps, completed-candle boundaries, and exact 5m → 1h reconciliation.

## Acquisition route

The cloud sandbox **cannot reach Binance**: the egress policy answers 403 to
CONNECT for `api.binance.com`, `data-api.binance.vision`, `api1.binance.com` and
`fapi.binance.com`. Data is therefore acquired on a GitHub-hosted runner by
`.github/workflows/dataset-v2.yml`, from Binance's public REST API, using the
pinned `freqtradeorg/freqtrade:2026.7` image. No exchange credential is used or
required, and no order-placing command is ever issued.

```bash
freqtrade download-data --exchange binance \
  --pairs BTC/USDT ETH/USDT --timeframes 5m 1h \
  --timerange 20201201-20260901 --data-format-ohlcv feather
```

If exchange availability forces a date adjustment, the smallest evidence-based
adjustment is made **before** the active baseline runs, and the reason is
recorded in the lock file.
