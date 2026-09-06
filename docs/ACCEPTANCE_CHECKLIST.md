# v1 Acceptance Checklist

## A. Cloud-verifiable (no Docker, no secrets, no market data)

These run in any checkout and in CI. Automated unless noted.

- [x] No secret material or local-only artifact is tracked — `scripts/verify_repo.py`.
- [x] Every tracked JSON and YAML parses — `scripts/verify_repo.py`.
- [x] `MANIFEST.txt` matches the tracked tree — `scripts/verify_repo.py`.
- [x] Paper guard passes on the committed example config — `scripts/paper_guard.py`.
- [x] Paper guard **rejects** an unsafe config (live, futures, leverage, shorts,
      credentials, withdrawal, unbounded stake/wallet) — `tests/test_paper_guard.py`.
- [x] Config carries no strategy-owned ROI/stoploss/timeframe — `tests/test_config_isolation.py`.
- [x] Effective config renders and hashes without secrets — `scripts/effective_config.py`.
- [x] Every published port is bound to `127.0.0.1` — `tests/test_compose.py`.
- [x] Exporter is read-only and reports `freqtrade_api_up 0` on failure — `tests/test_exporter.py`.
- [x] Dataset auditor detects gaps, duplicates, bad OHLC, NaN and fingerprint drift — `tests/test_data_audit.py`.
- [x] Experiment records validate against the schema — `research/record_experiment.py validate`.
- [x] Python, shell and PowerShell sources parse — CI `static` job.

## B. CI-verifiable (containers, no private credentials)

- [ ] `docker compose config` renders with dummy local values — CI `compose` job.
- [ ] Exporter image builds and serves `/metrics` — CI `compose` job.
- [ ] Freqtrade image loads the paper config and the strategy — CI `freqtrade-load` job.

## C. Requires a Docker host with market data (owner's machine)

Not provable in the cloud sandbox. Record results as experiment records.

- [ ] `.env` secrets changed from placeholders.
- [ ] `config.json` created from the paper example.
- [ ] `docker compose up -d` starts all services; `docker compose ps` is healthy.
- [ ] Freqtrade `/api/v1/ping` returns ready.
- [ ] Exporter metric `freqtrade_api_up` becomes 1.
- [ ] Prometheus target is UP.
- [ ] Grafana dashboard loads data.
- [ ] MLflow UI opens and a test run is logged.
- [ ] `scripts/download_data.sh 20250701-20260907` succeeds.
- [ ] `scripts/audit_data.py --lock research/datasets/dataset_v1.lock.json` → `DATA_INTEGRITY_GATE = PASS`.
- [ ] Backtest is reproducible from a clean checkout at a pinned commit.
- [ ] lookahead-analysis reviewed.
- [ ] recursive-analysis reviewed.
- [ ] Results recorded as a schema-valid experiment record with a gate decision.
