# CLAUDE.md — Trading Lab OS

## Identity

Repository: `trading-lab-os-sandbox`

This repository is checked out on a **native Ubuntu host with Docker Engine**,
reconstituted by `P1 — HOST RECONSTITUTION`. It is the workspace a live paper
runtime is started from, and the terminal on this host is the operator surface.

The earlier Windows / WSL / Docker Desktop host is gone. Its evidence lane did
not survive the migration — see
[`docs/fp-boot-1/FP_CONTROL_1_COHORT_CLOSURE.md`](docs/fp-boot-1/FP_CONTROL_1_COHORT_CLOSURE.md)
— so nothing on it is reachable and nothing recorded there may be treated as
current.

### Critical environment rule

Do **not** assume you can access:
- `C:\trading_lab_os_v1`, the Windows filesystem, or any WSL instance
- the prior host's `.env`, SQLite databases, or Grafana/Prometheus/MLflow state
- the FP-CONTROL-1 evidence lane, in any form

Repository evidence is authoritative. Previously recorded runtime evidence from
any host is historical evidence only, and evidence from *this* host is current
only for the commit it was produced at.

Do not claim a runtime test passed unless it was actually run in the current
environment or in CI, at a commit you can name.

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

`P2 — PROSPECTIVE PAPER PROOF`

**The stage contract is [`docs/p2/P2_CONTRACT.md`](docs/p2/P2_CONTRACT.md).** It
is the P2 single source of truth: purpose, lane model, source-commit model, the
T0 transaction, crediting law, durability tiers, authority and closure law all
live there and are deliberately not restated here.

Do **not** jump directly to FreqAI, RD-Agent, Hyperopt, Hummingbot, Condor,
NautilusTrader, Qlib, or live trading.

Do **not** run or optimize a complex `TrendMomentumBaselineV1` merely because
such a file exists.

## Closed stages — their records, not their directives

The execution directives for the stages below were spent when those stages
closed. Their outcomes live in their closure records, which remain authoritative
for what was established; the directives themselves are not reproduced here,
because a spent instruction sitting under "current stage" is how a closed stage
gets re-run.

```text
CLOUD-0     repository readiness and reproducible research harness
            docs/cloud-0/CLOUD-0_CLOSURE.md  (+ C0.1, C0.2, C0.4, C0.7 records)
BASELINE-1  simple deterministic active benchmark — both protocol windows run
            docs/research/BASELINE_1_PROTOCOL.md
            docs/research/BASELINE_1_DEVELOPMENT_RESULT.md
            docs/research/BASELINE_1_VALIDATION_RESULT.md
            BASELINE_PROTOCOL = PASS · BASELINE_PERFORMANCE = NEUTRAL ·
            DURABLE_ALPHA = NOT_PROVEN · Validation is SPENT, never pristine OOS
FP-BOOT-1   forward-paper scaffold, admission, preflight, ledgers, capture loop
            docs/fp-boot-1/
P1          host reconstitution — docs/p1/P1_CLOSURE.md — CLOSED / PASS
```

## Execution model

```text
Terminal = operator surface     Claude Code = sole writer/executor
CliDeck = NONE                  Codex = NONE
branch → PR → CI → OWNER MERGE → re-ground → resume the SAME stage
fail-closed: UNPROVEN blocks exactly as FAIL does, and no override flag exists
```

## Standing prerequisite order and boundaries

[`docs/NEXT_EXECUTION_PREREQUISITES_2026-09-14.md`](docs/NEXT_EXECUTION_PREREQUISITES_2026-09-14.md)
records the ordered prerequisites to Paper Beta and the authority boundaries. It
grants no execution authority and is not superseded by the P2 contract; P2 is
items 3 through 5 of that order.

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

Branch names are stage-scoped, e.g. `claude/p2-governance`,
`claude/p2-pre-t0-implementation`.

Make small coherent commits.

Never push to `main`. Never auto-merge. Never squash or rebase a PR: merges are
normal two-parent merges the Owner performs.

Do not rewrite published history.

Do not delete evidence to make a gate pass.

While a forward-paper cohort is running, the runtime's checkout stays pinned at
its frozen commit. Cut branches and make commits from a separate worktree — a
`git checkout` in the runtime's own directory changes what the launcher would
stamp and dirties the tree the running capture loop reads.

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

Read [`docs/p2/P2_CONTRACT.md`](docs/p2/P2_CONTRACT.md), then re-ground on merged
`main` and resume P2 at the first stage of §13 that is not yet merged.

Proceed autonomously within that contract.

Do not ask the owner to run ordinary repository checks you can perform yourself.

Return only at an `OWNER_MERGE_REQUIRED` gate, a Tier-3 durability blocker, a
genuine strategy/risk/Dataset authority conflict, or `T0_PRECONDITIONS = PASS`.
Ordinary implementation, test and runtime issues are not returns.
