# Component mining

Sprint v1.3 §20 and §21. **Do not import whole bots.** Mine testable hypotheses, then make
each prove incremental value against a frozen parent, one component at a time.

Nothing here is accepted. A hypothesis becomes a registered ablation in
`research/external/ablation_registry.json` only when a parent has passed its gates and the
component is expressible as a single change.

## Acceptance rule (§21)

```
FROZEN PARENT   vs   FROZEN PARENT + ONE COMPONENT
```

Held constant: data, pair/universe, fee model, position sizing, execution assumptions,
exposure policy. Accepted only if the improvement is **repeatable** and does not hide a
material risk explosion. Rejected components stay recorded as rejected. No kitchen-sink
strategy.

## btc-strategy-lab (GPL-3.0, executable)

| Hypothesis | Status | Note |
| --- | --- | --- |
| Long-horizon EMA regime timing as a cash/exposure switch | parent candidate, not a component | This *is* H1 |
| Incremental funding filter | **registered** as `ABL_FUNDING_FILTER` | Primary axis is drawdown, not return — that is the claim upstream actually makes |
| PBO as a selection gate | mined | Upstream reports 0.21 for its own strategy and 1.00 for the one it discarded |
| Deflated Sharpe | mined | Pairs with PBO for multiple-testing accounting |
| Parameter-sweep smoothness as an overfitting signal | mined | "A real effect produces a gradient. Overfitting produces a lottery." Cheap and directly testable |
| Walk-forward design | mined | Upstream's own 8-of-13 disclosure is the model for honest reporting |

Upstream's most useful contribution may be methodological rather than the strategy: it
reports against itself that dropping one window (H2 2020) leaves the remainder compounding
to +335% against BTC's +734%. That subtraction is now gate `V8_CONCENTRATION`.

## crypto-trading-bot-postmortem (GPL-3.0, executable)

| Hypothesis | Status |
| --- | --- |
| Exit diagnostics split by exit reason | mined — 100% win rate on ROI exits with 0% on signal exits was the tell |
| Activity versus expectancy | mined — trade count is not evidence of edge |
| Objective-function failure | mined — Hyperopt made results *worse*, a hard case for any optimiser we add |
| Fee-floor economics | mined — already reflected in gate `V6` |

## Passivbot (Unlicense, method/evidence only)

Planner parity between live and backtest; hard exposure limits; recovery metrics; fill
accounting; Pareto/multi-objective evaluation.

**Never imported:** perpetual/leverage execution, Martingale-like averaging, native
tail-risk assumptions. Its raw ROI is never compared with a spot-long system's.

## NostalgiaForInfinity (GPL-3.0, Wave 2)

Universe and listing controls; informative-timeframe discipline; execution and accounting
edge cases. Its difficult DCA and backtest-vs-live cases are wanted as regression tests
more than its returns.

## TrendRider (public forward paper)

Public forward ledger; parameter-change provenance; backtest-to-paper drift; release
discipline. Directly shapes the §24 forward-paper design. Its results are **paper**, never
cited as real-money evidence.

## Kronos Gauntlet (no license — method only)

Pre-registration before scoring; locked kill gates; deterministic replay; hermetic
verification; failure ledger; **errata discipline**.

Already adopted: this repository pre-registers gates before results, and
`docs/external/failure_ledger.md` carries an errata section for the lab's own corrected
errors. Kronos publishes errata against its own headline claims, including one where a data
build failed its own locked gate. That is the standard being copied — as method, with no
code vendored.

## Hummingbot (P2, method reference)

Controller/executor separation; execution architecture; market-making and inventory
concepts for later lanes. Not a current core dependency and no ROI comparison this sprint.
