# OFFLINE-RESEARCH-AUTHORITY-1

**Status:** ACTIVE, prospective only. **Authority:** Owner directive
`RESEARCH-FOUNDATION-CLOSURE-1` (2026-09-29), Gate 1. **Relationship to
P2:** sibling, not an amendment. [`docs/p2/P2_CONTRACT.md`](../docs/p2/P2_CONTRACT.md)
is not modified by this document and is not modified in any commit this
document is part of. FP-CONTROL-3 remains the sole canonical P2 control.

---

## 1. What this document is not

This document does **not** retroactively authorize anything. The Research
Foundation's Unit B (H1 controlled derivation, null-control strategy/workflow
work, and the CI trials that produced them — PRs #33 and #34) executed under
a direct Owner directive (`TRADING LAB OS — COMPRESSED RESEARCH FOUNDATION`,
2026-09-29) that is separate from, and later than, the earlier
`TRADING-RESEARCH-STAGE0-CLOSURE-1` authorization. Relative to that earlier,
narrower authorization, Unit B's execution was out of its scope. It was not
out of scope relative to the Owner directive that actually authorized it.
Neither this document nor anything else here should be read as claiming
otherwise, and this document grants no authority for anything already done —
only for what follows it.

## 2. Scope

This authority opens **Cycle 1 of offline, historical, preregistered
research**, conducted entirely outside the P2 runtime, under the
research-selection accounting enforced by `research/trial_ledger.py`
(Research Foundation Unit A).

### 2.1 Authorized

- Preregistered historical research (development-window backtests against
  already-acquired, hash-locked data).
- Deterministic research trials, preregistered before their outcome is
  known, per `research/trial_ledger.py`'s enforcement.
- Null calibration of the research/validation pipeline.
- H1 robustness work, later, only if a specific, named need is identified —
  not authorized as open-ended activity by this document alone.
- One future Mean-Reversion lineage, **after** Research Foundation closure
  is recorded — not opened by this document.
- Execution on GitHub Actions or another separate runner.
- Use of public/historical market data already within this project's
  existing acquisition and lock conventions (`research/datasets/`).
- Research evidence preservation, following the durable-storage convention
  established in `TRADING-RESEARCH-STAGE0-CLOSURE-1`
  (`~/Documents/TLOS-Evidence/trading-research/`).
- Research trial accounting via the canonical ledger.
- Minimal validation tooling specifically required by Cycle 1 — not a
  general validation framework.

### 2.2 Not authorized

- Any FP-CONTROL-3 mutation — strategy, config, database, cohort, runtime,
  evidence, or the P2 authority contract.
- Any write to a P2 database or P2 evidence lane.
- Any new paper worker.
- Live trading, real money, or exchange trading credentials of any kind.
- P3 implementation.
- Automatic candidate promotion or automatic paper admission — a survivor
  decision and a paper-admission decision each require their own explicit
  Owner authorization, never an automatic consequence of a research result.
- Opening a protected/locked holdout outside that holdout's own,
  not-yet-defined gate. (No such holdout currently exists — see
  `RESEARCH-FOUNDATION-CLOSURE-1` Gate 0B / the closure report's Section E.
  This clause pre-authorizes nothing about a future one either; it only
  states that none may be opened outside a gate this document does not
  itself define.)
- Funding-conditioned research.
- Cross-sectional research.
- Any new trading engine, backtesting engine, or execution platform.
- ML/RL.
- LLM-driven trading decisions.

## 3. Execution environment default

Research execution defaults to a **separate runner** (GitHub Actions, or
another environment that does not share the P2 host's containers, network
path, filesystem, or credentials). Batch research execution on the P2 host
is not authorized by default. A specific, narrow exception would require its
own explicit Owner authorization naming the exception.

## 4. Relationship to existing mechanisms

This authority does not create a new framework. It opens the use of what
Research Foundation Units A and B already built and proved:

- `research/trial_ledger.py` + `research/schema/trial_record.schema.json` —
  preregistration-before-outcome enforcement (Unit A).
- The `extbench.yml` / `null_control.yml` pattern — off-host CI execution
  reusing the existing acquisition, data-lock, lookahead, recursive and
  metrics-normalisation steps (Unit B, Gate 2 correction applied).
- `~/Documents/TLOS-Evidence/trading-research/` — durable, off-git evidence
  storage (Stage 0 closure).

No new database, control plane, engine, or research platform is opened by
this document. Building one remains out of scope here, whether or not
Cycle 1's own trials eventually call for it — that would be its own,
separate decision.

## 5. Boundary enforcement

Every trial run under this authority must:

- be preregistered in the canonical trial ledger before its outcome is
  known, per Unit A's enforcement;
- execute off the P2 host by default (§3);
- write to no P2-owned path, database, or evidence lane;
- carry no exchange trading credential of any kind;
- never automatically promote a result to survivor status or paper
  admission.

A trial or a workflow that cannot satisfy these is not authorized by this
document, regardless of what it is trying to test.
