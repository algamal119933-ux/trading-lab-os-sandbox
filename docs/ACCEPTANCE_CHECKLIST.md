# v1 Acceptance Checklist

- [ ] `.env` secrets changed from placeholders.
- [ ] `config.json` created from paper example.
- [ ] `python3 scripts/paper_guard.py` -> PASS.
- [ ] `docker compose config` -> PASS.
- [ ] `docker compose up -d` starts all services.
- [ ] `docker compose ps` shows expected services.
- [ ] Freqtrade local `/api/v1/ping` returns ready.
- [ ] Exporter metric `freqtrade_api_up` becomes 1.
- [ ] Prometheus target is UP.
- [ ] Grafana dashboard loads data.
- [ ] MLflow UI opens and test run is logged.
- [ ] Historical data download succeeds.
- [ ] Backtest is reproducible.
- [ ] lookahead-analysis reviewed.
- [ ] recursive-analysis reviewed.
- [ ] No private exchange API keys exist anywhere in repository files.
- [ ] No live/futures/leverage configuration enabled.
