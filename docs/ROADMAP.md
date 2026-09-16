# Roadmap — Gate-driven

> **SUPERSEDED AS A PLAN OF RECORD — 2026-09-16.** The Gate 0–7 taxonomy below is
> the project's original sketch. It was never reconciled with the stages the
> project actually executed, and it is kept unedited as that sketch rather than
> rewritten to look as though it always agreed.
>
> **Nothing in this file authorizes a stage.** The current authorized stage is in
> [`../CLAUDE.md`](../CLAUDE.md); the P2 contract is
> [`p2/P2_CONTRACT.md`](p2/P2_CONTRACT.md); the ordered prerequisites to Paper
> Beta are in
> [`NEXT_EXECUTION_PREREQUISITES_2026-09-14.md`](NEXT_EXECUTION_PREREQUISITES_2026-09-14.md).
> Gate 3 (FreqAI) and Gate 5 (research agents) in particular read as available
> next steps and are not: AI comes only after a deterministic baseline survives
> the research protocol, and no candidate has yet been admitted.
>
> ## Mapping — what the gates became
>
> | Gate | What actually happened |
> | --- | --- |
> | Gate 0 — Boot & Observability | subsumed by `CLOUD-0` (closed) and by `P1`'s runtime qualification (closed) |
> | Gate 1 — Baseline Data/Backtest Correctness | `BASELINE-1` Development window, on frozen Dataset V2 — protocol `PASS`, performance `NEUTRAL` |
> | Gate 2 — Walk-forward / Out-of-sample | `BASELINE-1` Validation window — run once, **spent**, never a locked OOS. The first strict prospective holdout is forward paper, which is `P2`. |
> | Gate 3 — FreqAI Lab | **not open.** Requires a candidate; `entry_state = C`, `PAPER_ADMISSION = BLOCKED` |
> | Gate 4 — Independent Event-driven Validation | **not open** |
> | Gate 5 — Research Agents | **not open.** Same precondition as Gate 3 |
> | Gate 6 — Market-making / DEX | **not open** |
> | Gate 7 — Tiny Live | **not authorized.** `REAL_MONEY_AUTHORIZED = NO` |
>
> Stages that have no Gate row, because the sketch did not anticipate them:
> `FP-BOOT-1` (forward-paper scaffold, admission, preflight, ledgers, capture
> loop), `P1 — HOST RECONSTITUTION`, and `P2 — PROSPECTIVE PAPER PROOF`.

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
