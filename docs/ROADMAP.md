# Roadmap — Gate-driven

## Gate 0 — Boot & Observability
PASS only when:
- Docker services healthy.
- Freqtrade API responds locally.
- Grafana receives exporter metrics.
- MLflow accepts an experiment.
- Paper Guard rejects an intentionally unsafe test config.

## Gate 1 — Baseline Data/Backtest Correctness
PASS only when:
- Historical data downloaded and checksummed.
- Baseline backtest reproducible from a clean checkout.
- lookahead-analysis PASS.
- recursive-analysis acceptable.
- costs/fees documented.

## Gate 2 — Walk-forward / Out-of-sample
Add a research splitter and frozen train/test windows.
Reject any strategy whose edge disappears out-of-sample.

## Gate 3 — FreqAI Lab
Switch image to `2026.7_freqai`.
Add one model at a time.
Every model run must log dataset window, features, model class, hyperparameters, and code commit to MLflow.
AI/model remains proposal-only.

## Gate 4 — Independent Event-driven Validation
Candidate: NautilusTrader.
Purpose: second engine to challenge fills/timing assumptions, not to replace Freqtrade immediately.

## Gate 5 — Research Agents
Candidates: Qlib + RD-Agent.
Permissions: read data, generate hypotheses, write candidate code, launch sandbox experiments.
Forbidden: exchange private keys, changing risk policy, direct live orders.

## Gate 6 — Optional Market-making / DEX Branch
Candidates: Hummingbot + Condor.
Only open this gate if the actual strategy class requires market-making/arbitrage/DEX execution.

## Gate 7 — Tiny Live (NOT AUTHORIZED BY THIS PACKAGE)
Requires a new explicit owner decision and a new live config. v1 artifacts must not be silently edited into live mode.
Minimum evidence before considering it:
- stable paper results over a meaningful period,
- OOS/walk-forward consistency,
- risk limits and kill switches,
- secrets handling,
- incident/recovery procedure,
- exchange-specific min order/fee/slippage verification.
