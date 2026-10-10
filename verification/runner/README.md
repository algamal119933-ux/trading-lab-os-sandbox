# Minimum isolated runner (CV-03)

Runs one verification case: a strategy, its config and the market data, inside one container that has no
network. Freqtrade and the repository's paper guard are used as published; nothing in `research/` changes.

```bash
python3 verification/runner/run_case.py --case CASE --data-dir DATA --out-dir OUT            # plan and check
python3 verification/runner/run_case.py --case CASE --data-dir DATA --out-dir OUT --execute  # run it
```

## Where it may run

Only on a machine that is neither the P2 host nor a cloud executor, launched by a person. `CASE`, `DATA` and
`OUT` stay outside this repository. The runner refuses otherwise.

## The case directory

```text
CASE/
  case.json            case_id, strategy_class, timeframe, timerange, fee, and the sha256 of every file below
  strategy/<Name>.py   the strategy (+ its params JSON, if any, next to it)
  config.json          the customer's config, with every key and secret removed
  exchangeInfo.json    a snapshot of the exchange's public market list (GET /api/v3/exchangeInfo), taken once
```

## What isolation means here

- `--network none`. Freqtrade must load the market list before a backtest. Inside the container,
  `entrypoint.sh` serves the pinned `exchangeInfo.json` on loopback, and the effective config points the
  exchange there.
- The engine is pulled by digest (`engine.json`), never by tag.
- The root filesystem is read-only, all capabilities are dropped, no-new-privileges is set, and the user is
  unprivileged. Every input is mounted read-only; only `OUT/results` is writable.
- `scripts/paper_guard.py` must pass the effective config: dry-run, spot, no leverage, no shorts, no
  credentials.

After a run, `research/summarize_backtest.py` reads the result as it is.
