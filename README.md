# Trading Lab OS — cloud sandbox

A sanitised, cloud-developable copy of Trading Lab OS. **Paper / research only.**

`dry_run=true`, Binance **spot**, long-only, no leverage, no margin or futures,
no shorts, no exchange credentials anywhere in the repository, no withdrawal
path. `CLAUDE.md` is the governing directive; it wins over anything here.

## What is in the repository, and what is not

| In Git | Not in Git (regenerated locally) |
| --- | --- |
| stack definition, configs, strategy, exporter, dashboards | `.env`, `freqtrade/user_data/config.json` |
| scripts, tests, CI, schemas, docs | market data, trade DB, logs, MLflow store, backtest results |

Market data is reproduced from `research/datasets/dataset_v1.lock.json` — see
[`docs/cloud-0/C0.7_DATA_REPRODUCTION_PLAN.md`](docs/cloud-0/C0.7_DATA_REPRODUCTION_PLAN.md).

## Checks that run anywhere (no Docker, no secrets, no data)

```bash
pip install -r requirements-dev.txt

python3 scripts/paper_guard.py        # fail-closed paper-safety invariant
python3 scripts/verify_repo.py        # secrets, artifacts, JSON/YAML, manifest
python3 scripts/effective_config.py   # redacted effective config + hash
python -m pytest                      # the full suite
```

`python3 scripts/verify_repo.py --fix` regenerates `MANIFEST.txt`; CI fails if it
is stale.

## Running the paper stack (needs Docker)

```bash
cp .env.example .env                  # then change every CHANGE_ME_* value
cp freqtrade/user_data/config.paper.json.example freqtrade/user_data/config.json
scripts/start_paper.sh                # guard runs first; refuses an unsafe config
scripts/stop.sh
```

Windows: `.\START_WINDOWS.ps1` / `.\STOP_WINDOWS.ps1`.

Every service binds to `127.0.0.1` only: Freqtrade `:8080`, MLflow `:5000`,
Prometheus `:9090`, Grafana `:3000`, exporter `:9108`.

## Research commands

Each requires an explicit timerange — an open-ended window is not reproducible —
and runs the paper guard before touching Freqtrade.

```bash
scripts/download_data.sh 20250701-20260907   # refuses to move a frozen dataset
scripts/backtest.sh      20250901-20260501
scripts/lookahead.sh     20250901-20260501
scripts/recursive.sh     20250901-20260501
```

Override with `STRATEGY=...`, `PAIRS=(...)`, `TIMEFRAMES=(...)`.

## Recording evidence

```bash
python3 research/record_experiment.py template > research/records/my_run.json
# fill in command, metrics, gate, reason
python3 research/record_experiment.py stamp    research/records/my_run.json
python3 research/record_experiment.py validate research/records/my_run.json
python3 research/record_experiment.py summarize research/records/my_run.json
```

Records validate against `research/schema/experiment_record.schema.json`. A
record labelled `oos` refuses to summarise without `--unlock-oos`.

## Current stage

`BASELINE-1` — closed. A deterministic EMA50/EMA200 spot long-only reference,
evaluated on Dataset V2 (real, checksum-verified Binance spot data) under a
protocol fixed before any result existed.

| Stage | State |
| --- | --- |
| `CLOUD-0` — repository readiness and reproducible harness | closed — [`docs/cloud-0/CLOUD-0_CLOSURE.md`](docs/cloud-0/CLOUD-0_CLOSURE.md) |
| `DATASET-V2` — frozen research dataset | frozen — [`docs/research/DATASET_V2_SPEC.md`](docs/research/DATASET_V2_SPEC.md), [`research/datasets/dataset_v2.lock.json`](research/datasets/dataset_v2.lock.json) |
| `BASELINE-1` Development | protocol **PASS**, performance **NEUTRAL** — [`docs/research/BASELINE_1_DEVELOPMENT_RESULT.md`](docs/research/BASELINE_1_DEVELOPMENT_RESULT.md) |
| `BASELINE-1` Validation | run once, unchanged; **NEUTRAL** — [`docs/research/BASELINE_1_VALIDATION_RESULT.md`](docs/research/BASELINE_1_VALIDATION_RESULT.md) |

The reference neither beat nor badly lagged a passive position of the same
average exposure: −1.38 pp on Development, +1.97 pp on Validation. That is the
number any future candidate has to improve on, under the same frozen protocol.

No prospective out-of-sample evidence exists yet. The first strict holdout must
be forward paper over data that did not exist when the strategy was frozen.
This repository remains **paper / research only**.

Arabic quick start: [`README_AR.md`](README_AR.md), [`RUN_WINDOWS_AR.md`](RUN_WINDOWS_AR.md).
