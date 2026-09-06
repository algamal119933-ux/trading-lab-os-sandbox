# Trading Lab OS — Architecture v1

## Authority split

```text
Research / human / future AI
        |
        v
Strategy candidate
        |
        v
Validation gates
        |
        v
Paper-only Freqtrade
        |
        v
Exchange public market data
```

No component in v1 receives a private exchange key.

## Components

### 1. Freqtrade
Role: backtest + dry-run + trade-state database + local UI/API.

### 2. MLflow
Role: immutable-ish experiment trace: code commit, parameters, metrics, artifacts.

### 3. Freqtrade Exporter
Role: read-only telemetry adapter. It cannot call force-enter/force-exit endpoints.

### 4. Prometheus
Role: collect time-series operational metrics.

### 5. Grafana
Role: visualize truth from Prometheus, not manually entered marketing numbers.

### 6. Paper Guard
Role: local fail-closed preflight before scripts start trading-related commands.

## Trust boundaries

- Freqtrade REST is bound to `127.0.0.1` on host.
- Grafana/MLflow/Prometheus are bound to `127.0.0.1`.
- API credentials stay in `.env`, not committed.
- Exchange key/secret fields are empty in v1.
- No remote LLM has execution authority.
