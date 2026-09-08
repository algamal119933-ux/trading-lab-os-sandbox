# Research prep closure

**Scope executed:** source discovery → source lock → licence/provenance → strategy logic extraction
→ lineage/duplicate detection → source claim extraction → scientific comparison → future test design.

**Scope explicitly NOT executed:** candidate execution, backtesting, hyperopt, paper activation,
strategy promotion, runtime modification, new cohort.

```
CANDIDATE_EXECUTION_AUTHORIZED = NO
CURRENT_FP_CONTROL_MODIFIED    = NO
ACTIVE_STRATEGY_REPLACED       = NO
REAL_MONEY_AUTHORIZED          = NO
```

## Isolation

All work was done in `/mnt/d/TradingLabResearch`, never in the live worktree.
The live runtime was inspected read-only before and after; no container was started, stopped,
restarted or reconfigured, and no live file was written.

| | |
|---|---|
| `LIVE_WORKTREE` | `/mnt/c/trading_lab_os_cloud_sandbox` — read-only throughout |
| `RESEARCH_REPO` | `/mnt/d/TradingLabResearch/trading-lab-os-research` |
| `SOURCE_ROOT` | `/mnt/d/TradingLabResearch/sources` — mirror clones, never edited |

Source clones use `--filter=blob:none --no-checkout`, so no source repository has a working tree
that could be edited by accident, and blobs are fetched only when a specific file at a specific
commit is read.

## What was found

**Seven candidates are five families, not seven discoveries.** A1 and A2 sit inside A3's family:
`btc-strategy-lab`'s own NOTICE states that EmaCross and EmaCrossFunding are derived from
EMAPriceCrossoverWithThreshold, and A1's docstring says the logic is identical with three constants
promoted to parameters. Counting them as independent would have inflated the trial count.

**The planning hypothesis had the nearest neighbour wrong.** EmaCross does *not* duplicate
`BaselineEmaRegimeV1` — it crosses price against one EMA, where the baseline crosses EMA50 against
EMA200. The genuine near-relative is A5 `DoubleEMACrossoverWithTrend`, which is fast-EMA-crosses-slow-EMA
on 1h spot long-only, exactly like our control. A5 was promoted to P1 for that reason. No candidate
became `CONTROL_LINEAGE_REFERENCE`.

**The strongest source in the pool reports its own failure.** btc-strategy-lab states that its
Deflated Sharpe deflates for 25 sweep variants but not for the 42-way benchmark selection or the
added fourth rule, and that under a realistic spread of trial Sharpes "the shipped strategy does not
clear this gate". It also publishes a generalisation test showing the strategy fails on other
assets — ETH +84% against buy-and-hold +53%, three coins losing money outright. Half our universe
is ETH. This is the most decision-relevant fact discovered.

**A7 is not researchable under current constraints.** Its canonical file changed on the day it was
locked, it ships an updater that rewrites itself daily, it publishes no citable performance claim,
and a native test needs 40–80 pairs at 5m with four informative timeframes and DCA. It is HOLD, and
any BTC/ETH-only run must never be labelled native NFI validation.

**Two source-lock traps were caught.** A7's `user_data/strategies/` path is a git symlink (mode
`120000`, 31 bytes) — locking it would have hashed link text instead of a 2.5 MB strategy. And four
of seven candidates declare no `startup_candle_count` at all despite needing 200–800 bars of warm-up.

## Artifacts

`docs/research-prep/` — this file plus STRATEGY_SOURCE_REGISTRY, STRATEGY_LINEAGE_MAP,
STRATEGY_COMPARISON_MATRIX, STRATEGY_RESEARCH_PRIORITY, DATA_DEPENDENCY_MAP, FUTURE_BENCHMARK_PROTOCOL.

`research/research-prep/` — strategy_source_registry.json, strategy_lineage.json,
candidate_manifest.json, source_claims.json, research_priority.json, future_benchmark_contract.json,
data_dependency_map.json.

`scripts/capture_source_lock.py` — deterministic, re-runnable, no execution or credential path.

## Governing next action

Do not start A1–A7. Return to observing FP-CONTROL-1. The next governing runtime action remains:
finish the current ~48h window → A15 closure → M2 hardening, durable monitoring, evidence backup.

`MAIN_MERGE_AUTHORIZED_DURING_ACTIVE_FP_CONTROL = NO`
