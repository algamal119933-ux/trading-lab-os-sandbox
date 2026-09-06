# CLAUDE.md — Trading Lab OS Cloud Sandbox

## Identity

Repository: `trading-lab-os-sandbox`

This repository is a **sanitized cloud-development copy** of Trading Lab OS.
It is intentionally separated from the owner's local Windows/WSL/Docker project.

### Critical environment rule

Do **not** assume you can access:
- `C:\trading_lab_os_v1`
- the owner's Windows filesystem
- the owner's WSL instance
- the owner's Docker Desktop runtime
- local `.env`
- local exchange data files
- local SQLite databases
- local Grafana/Prometheus/MLflow state

Repository evidence is authoritative for this cloud workspace.
Previously recorded local-runtime evidence may be used as historical evidence only.

Do not claim a local runtime test passed unless the test was actually run in the current environment or in CI.

---

## Owner intent

Act as the primary engineering agent for this repository.

Work autonomously:
- inspect the repository;
- edit code/config/docs;
- create tests and CI;
- run every test available in the current cloud environment;
- diagnose and repair ordinary failures yourself;
- commit coherent changes;
- keep evidence reproducible.

Do not stop after every minor command.
Return only at a meaningful gate, a real blocker, or completion of the currently authorized scope.

---

## Hard safety boundary

This project is **PAPER / RESEARCH ONLY**.

You are NOT authorized to:
- set `dry_run=false`;
- add or request private exchange API keys;
- place real exchange orders;
- enable withdrawals;
- enable leverage, margin, futures, or shorts;
- store secrets in Git;
- weaken the paper-safety guard;
- bypass a failed safety or integrity gate;
- expose locked OOS results early merely to improve a strategy.

If any requested action would cross this boundary:

`OWNER_AUTHORIZATION_REQUIRED`

---

## Known historical evidence from the local runtime

The following was previously observed on the owner's local machine. Treat it as historical evidence, not as proof of the current cloud runtime:

- Freqtrade 2026.7
- Binance spot
- `dry_run=true`
- simulated wallet: 100 USDT
- stake: 10 USDT
- max open trades: 2
- pairs: BTC/USDT, ETH/USDT
- Freqtrade API previously reachable
- exporter / Prometheus / Grafana / MLflow previously ran locally

The original `PlumbingSmokeStrategy` was an infrastructure smoke strategy, not a research candidate.

Historical smoke backtest:
- 1230 trades
- total profit: about -27.31%
- max drawdown: about 27.73%
- Sharpe: about -6.06

Do not optimize or rehabilitate the smoke strategy.

---

## Historical dataset evidence

A local deep audit previously returned:

`DATA_INTEGRITY_GATE = PASS`

Historical frozen hashes:

- BTC/USDT 1h  
  `b29689f5d0c0e86c95b5ec15e63e6bcfbcb8ad4596408dcc0f9040b3bbdfb4f9`

- BTC/USDT 5m  
  `2ab332f23d2376677b61d5a02492b5a4b67f2d37ac68f89a925697252cc7b908`

- ETH/USDT 1h  
  `a5de3ae5e9c3c73439eb8aec8ff496f9e9d5ebc7cec83842b2b2827880201ccf`

- ETH/USDT 5m  
  `4fa5ca782864ee84aff0e02786be3ca663de159288a7fb4baf12398fcdcca5c4`

Historical audit checks passed:
- no duplicate timestamps
- no gaps
- no NaN
- valid OHLC
- BTC/ETH range alignment
- exact 5m -> 1h OHLCV reconciliation

The actual market-data files are intentionally **not committed** to this cloud repository.

---

## Historical passive Development benchmark

For the previous Development window:

- BTC net buy-and-hold: `-29.60%`
- ETH net buy-and-hold: `-48.75%`
- fully invested 50/50: `-39.17%`
- exposure-matched passive: `-7.83%`

Important interpretation:

This Development sample was strongly bearish.
A long-only strategy may appear strong merely by sitting in cash.
Do not call reduced exposure "alpha" without exposure-adjusted analysis.

---

# CURRENT AUTHORIZED STAGE

`CLOUD-0 — REPOSITORY READINESS & REPRODUCIBLE RESEARCH HARNESS`

Do **not** jump directly to FreqAI, RD-Agent, Hyperopt, Hummingbot, Condor, or live trading.

Do **not** run or optimize a complex `TrendMomentumBaselineV1` merely because such a file exists.

The first goal is to make this repository safe, reproducible, CI-verifiable, and ready for controlled deterministic baseline research.

---

## CLOUD-0 execution gates

### C0.1 — Repository truth

Inspect the entire repository.

Identify:
- tracked source/config/docs;
- local-only artifacts that should not be tracked;
- stale or conflicting directives;
- configuration precedence risks;
- tests/scripts that currently exist;
- missing dependency pins;
- assumptions that only work on the owner's local machine.

Produce a concise repository state record.

---

### C0.2 — Secret and artifact hygiene

Verify the repository contains no:
- `.env`
- real API keys
- JWT secrets
- GitHub tokens
- private keys
- SQLite trade DBs
- logs containing credentials
- market-data directories
- backtest-result archives that are not deliberate fixtures
- MLflow runtime state

Strengthen `.gitignore` if necessary.

Do not remove useful reproducibility reports merely because they are generated artifacts; classify them explicitly.

---

### C0.3 — Paper-safety invariant

The repository must make unsafe live activation difficult.

Verify / test that baseline configuration and scripts enforce:
- `dry_run=true`
- spot only
- no leverage
- no futures/margin
- no shorts
- blank exchange key/secret in examples
- no withdrawal path
- bounded max open trades
- bounded simulated wallet/stake

The paper guard must fail closed.

Add automated tests for these invariants.

---

### C0.4 — Configuration isolation

Do not rely on a runtime-generated `config.json` being committed.

Use a safe example / research config pattern.

Document Freqtrade precedence:
CLI > environment > config > strategy.

Create a reproducible way for CI/research to show the effective config without requiring secrets.

No test should silently mix config-level ROI/stoploss/timeframe with strategy-level values.

---

### C0.5 — CI

Create a GitHub Actions workflow appropriate for this repository.

At minimum, CI should verify what is feasible without private data:
- Python syntax / compile checks
- JSON validity
- YAML validity
- PowerShell or shell-script sanity where practical
- paper-guard tests
- exporter unit/smoke tests
- Docker Compose configuration rendering using safe dummy local-only environment values
- exporter image build
- deterministic repository checks

Use pinned major/minor action versions and avoid unnecessary third-party actions.

If a Freqtrade container can be used safely in CI without private credentials:
- verify the strategy/config can be loaded;
- do not run live trading.

Do not make CI depend on locked OOS results.

---

### C0.6 — Research evidence schema

Create a machine-readable experiment record schema containing at least:
- timestamp
- command
- code commit
- config hash
- dataset hashes
- strategy hash
- Freqtrade version
- pairs
- timeframe
- detail timeframe
- timerange
- fee assumption
- wallet
- stake
- max open trades
- result metrics
- gate decision
- reason

Prefer JSON plus concise Markdown summary.

---

### C0.7 — Data-reproduction plan

Because market data is intentionally excluded from Git:

Create a documented, deterministic data acquisition and audit workflow.

Requirements:
- exact exchange / market type
- exact pairs
- exact timeframes
- explicit start/end
- deep audit after download
- SHA256 fingerprints
- no accidental update of a frozen dataset during an experiment

Do not expose or use a locked OOS simply to optimize a candidate.

Before choosing Dataset V2 dates, explain the regime-coverage rationale without looking at active-strategy outcomes.

---

# NEXT RESEARCH STAGE AFTER CLOUD-0

Only after CLOUD-0 closes:

`BASELINE-1 — SIMPLE DETERMINISTIC ACTIVE BENCHMARK`

Preferred initial concept:
- 1h
- spot
- long-only
- EMA50 / EMA200 regime logic
- no Hyperopt
- no AI
- no RSI/ATR/volume filter initially
- no complex ROI schedule
- transparent exit logic
- conservative emergency stoploss only

This is an interpretable reference, not a profit-maximization attempt.

Before adding complexity:
- normal Development backtest
- lookahead analysis
- recursive analysis
- detailed-timeframe simulation where appropriate
- exposure-adjusted evaluation

Measure:
- return
- max drawdown
- Sharpe / Sortino / Calmar
- profit factor
- win rate
- trade count
- consecutive losses
- fees
- turnover
- time/capital exposure
- return per unit of exposure
- per-pair contribution
- exposure-matched passive comparison

Add later features by **ablation only**, one at a time.

---

## Locked OOS rule

Locked OOS must not be opened until:
- dataset/protocol is frozen;
- deterministic baseline logic is frozen;
- Development gates pass;
- Validation gates pass.

If OOS is inspected and then used to alter the system:

`OOS = BURNED`

A new future holdout / forward paper period is then required.

If the OOS sample is too small:

`OOS = INCONCLUSIVE`

Do not tune to it.

---

## AI authority

AI comes only after a deterministic baseline survives the research protocol.

Later candidates may include:
- FreqAI
- Qlib
- RD-Agent

They must beat the deterministic reference under the same frozen protocol.

AI may research/propose.
AI does not receive unrestricted real-money execution authority.

---

## Git behavior

Work on a dedicated branch, not directly on `main`.

Preferred branch:

`claude/cloud-0-repo-readiness`

Make small coherent commits.

Do not rewrite published history.

Do not delete evidence to make a gate pass.

---

## Return format

At each meaningful return, provide:

```text
CURRENT_HEAD =
BRANCH =
WORKTREE =
CURRENT_STAGE =
LAST_GATE =
RESULT =
EVIDENCE =
FILES_CHANGED =
TESTS =
RISKS =
NEXT_ACTION =
OWNER_DECISION_REQUIRED = YES/NO
```

---

## Immediate first action

Start with `C0.1 — Repository truth`.

Then proceed autonomously through CLOUD-0.

Do not ask the owner to run ordinary repository checks that you can perform in the cloud environment yourself.

Stop only for a true blocker, a safety boundary, or completion of CLOUD-0.
