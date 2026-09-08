# Data dependency map

**Policy:** no large dataset is acquired while FP-CONTROL-1 is active. This documents
what *would* be required. **Machine-readable:** `research/research-prep/data_dependency_map.json`

## Current dataset

`dataset_v2` — BTC/USDT and ETH/USDT, 1h and 5m, 2020-12-01 … 2026-08-31, Binance spot,
frozen, lock gate PASS.

## Per candidate

| ID | Data available | Additional needed | Acquisition | Storage | QA |
|---|---|---|---|---|---|
| A1 | **YES** | — | none | none | existing lock gate |
| A2 | **NO** | Binance perpetual funding-rate history | LOW | LOW (few MB) | publication-time audit |
| A3 | **YES** | — | none | none | existing |
| A4 | PARTIAL | 4h candles | LOW | LOW | 1h→4h aggregation must reconcile exactly |
| A5 | **YES** | — | none | none | existing |
| A6 | **YES** | — | none | none | existing |
| A7 | **NO** | 40–160 pairs × 5m × 5 timeframes | **HIGH** | **HIGH** | per-pair audit + survivorship |

Four of seven candidates need no new data at all — A1, A3, A5 and A6 run on what we already have,
frozen and audited. That is a strong argument for the P1/P2 ordering: the cheapest candidates to
investigate are also the highest-information ones.

## A2 — funding rate

The filter input is a **futures-venue metric used to gate a spot strategy**. No futures execution
is implied and none is authorized; it is a data feed only. Its QA requirement is specific: the value
at each decision bar must be the last *published* funding value, never an interpolated or future one.
The source already forward-fills for exactly this reason, but that claim must be verified by our own
lookahead analysis rather than accepted.

## A4 — 4h candles

Derivable from existing 1h data by aggregation. Must reconcile exactly on OHLC, the same way the
5m→1h check already does in `scripts/audit_data.py`.

## A7 — the reason it is HOLD

| Requirement | Current | Gap |
|---|---|---|
| Pairs | 2 | 40–80 recommended, 160 in the shipped static pairlist |
| Base timeframe | 1h + 5m | 5m required, must not be overridden |
| Informative timeframes | none | 15m, 1h, 4h, 1d for every pair |
| Position sizing | fixed 10 USDT | DCA / position adjustment |
| Open slots | 2 | 6–12 recommended |

Storage estimate: `dataset_v2` holds ~21 MB per pair for 5m over ~5.7 years, so 80 pairs at 5m is
roughly 1.7 GB before informative timeframes; 160 pairs across five timeframes is materially larger.
That is an estimate from our own measured file sizes, not a measurement of the NFI universe.

**Survivorship warning.** Any multi-pair universe must be built from a *point-in-time* listing set.
Using today's top-volume pairlist over a 2020–2026 backtest would silently select coins that both
survived and succeeded. That effect is larger than any strategy edge under test, and it would
contaminate the result invisibly.
