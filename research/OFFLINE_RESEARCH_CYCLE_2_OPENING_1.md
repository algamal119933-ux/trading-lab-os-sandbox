# OFFLINE-RESEARCH-CYCLE-2-OPENING-1

**Status:** ACTIVE on Owner merge, prospective only.
**Authority:** Owner directive OFFLINE-RESEARCH-CYCLE-2-OPENING-1 (2026-10-01).
**Classification:** GOVERNANCE-ONLY / NON-EXECUTING. This record executes nothing; see §10.
**Parent:** research/OFFLINE_RESEARCH_AUTHORITY_1.md. Unchanged. Every §2.2, §3 and §5 limit applies here
verbatim, and nothing in this record widens them.
**Relationship to P2:** sibling. docs/p2/P2_CONTRACT.md is not modified by this record or by any commit it is
part of. FP-CONTROL-3 remains the sole canonical P2 control.

## 1. What this record opens
Research Cycle 2: offline, historical, preregistered research, executed off the P2 host (CI), under
research/trial_ledger.py accounting. It grants nothing retroactively and nothing beyond §§2–7.

## 2. Scope
2.1 Trend / Breakout: ONE new lineage in family F1, independent of BTSL_EMA_REGIME/L1 (H1). Its
    preregistration must state the signal construction and why it is not an EMA-cross/EMA-regime re-expression.
    It inherits the trend family's Cycle-1 count and the H1 upstream selection debt (Closure §E).
2.2 Mean-Reversion: ONE new lineage, CONDITIONAL. Budget is 0 until the Owner explicitly approves a named
    mechanism and its independence from the rejected MEAN_REVERSION_ZSCORE lineage (Closure §C). It inherits
    that family history and is never a first look.
    If the MR mechanism is not approved before the Trend lineage reaches its terminal decision, Cycle 2 may
    close without opening MR. No budget is reserved merely to keep the MR slot available. Any MR allocation
    stays inside the §3 total caps.
2.3 Regime/session-aware variants: allowed only as preregistered configurations inside 2.1 or 2.2. Labels use
    trailing data only (no lookahead). Every gated variant counts as a configuration.
2.4 Universe and data: Dataset V2 as locked (BTC/USDT, ETH/USDT; 1h primary, 5m detail; Binance spot;
    long-only). Selection uses Development 2021-01-01 → 2024-12-31 only. Validation 2025-01-01 → 2026-08-31 is
    SHARED_NON_PRISTINE: at most one unchanged run per frozen candidate, never used for selection or tuning.
2.5 Excluded unless separately approved: Funding-conditioned · Cross-sectional · ML/RL · LLM-driven
    decisions · Hyperopt or any open-ended sweep · any H1 work or H1 package change · the FP-CONTROL-3
    strategy as a candidate seed · any pair, timeframe, venue or Dataset change · shorts, leverage, margin,
    futures.

## 3. Trial budget — HARD CAPS, not targets
  scientific configurations (count toward N)    ≤ 24   (Trend ≤ 12 · MR ≤ 8 if approved · regime/session-gated ≤ 4;
                                                         sub-limits sit inside the 24, never added to it)
  scientific trial IDs, aborts included          ≤ 12
  calibration/tooling trial IDs                  ≤ 6
  engine backtest invocations                    ≤ 120
  Hyperopt / open sweeps                         0
Every grid is an explicit enumeration frozen in the preregistration. Robustness neighbours count as
configurations. Any DSR/PBO figure uses the cumulative family N and states the upstream debt it cannot
observe (candidate_registry.json multiple_testing_accounting). Exhausting any cap ends the cycle in a closure
record, then STOP. There is no extension without a new Owner record.

## 4. Funnel (per lineage, in order)
preregister → provenance/lookahead/recursive → Development walk-forward → parameter robustness →
cost + friction stress → multiple-testing control → regime/session diagnostics → FREEZE →
one unchanged Validation run (non-pristine, reported, never selected on) → terminal decision.
Terminal states are the ledger's own. The best outcome is SURVIVED, recorded as
PAPER_ADMISSION_REVIEW_ELIGIBLE. A REJECTED result is a valid scientific outcome.

## 5. Holdout policy — Option B (Owner approved)
No pristine historical holdout exists (Closure §F; Dataset V2 locked_oos designated = false). The first strict
holdout for any Cycle-2 survivor is prospective, isolated forward paper over data that did not exist at
candidate freeze. Historical Validation remains SHARED_NON_PRISTINE and may not be described as a strict
holdout. No historical window is labelled a holdout. Nothing in this record opens one.

## 6. Tooling delta (minimum; reuse first)
6.1 One strategy-agnostic driver generalizing research/mean_reversion/run_walkforward.py and
    research/h1_qualification/run_qualification.py, reading folds, grid, lanes and fee levels from the
    preregistration. Same docker/freqtrade invocation and the same summarize_backtest.py. Trade lists are
    exported on every run.
6.2 Cost + friction: engine-propagated per-side fee levels, frozen in the preregistration, with a test
    proving the engine received them. Friction is labelled a symmetric fee proxy. Slippage, latency and
    partial-fill stay NOT_SUPPORTED and are disclosed.
6.3 Multiple-testing: trialgate==0.5.0 (MIT; sdist sha256 30c4ac41…b8db1d), validation functions only
    (deflated_sharpe_ratio, probability_of_backtest_overfitting), adopted only if audit unit 7.1 passes.
    Thresholds come from the preregistration, not package defaults.
    NOT_EVALUABLE law: if the audit proves a statistic cannot be meaningfully evaluated with the available
    sample or configuration structure, it is recorded NOT_EVALUABLE. Thresholds are never weakened, missing
    observations are never invented, and NOT_EVALUABLE is never reported or treated as PASS.
    trialgate's registry and holdout components are FORBIDDEN. research/trial_ledger.py remains the canonical
    and only trial-count authority. arch: DEFER.
6.4 Regime/session diagnostics: one small script over exported trade lists. Diagnostic only. It never
    selects or gates.
Not authorized: any new engine, database, platform, framework, orchestrator, or general validation
framework.

## 7. Order of work
7.1 Audit unit (calibration budget): pin and audit trialgate (reference values, determinism, configurable
    thresholds); build 6.1, 6.2 and 6.4.
7.2 Null recalibration (calibration budget): the existing null fixtures run through 6.1 + 6.3 must be
    REJECTED. If noise passes: STOP (Master Plan §12).
7.3 Trend lineage trials.
7.4 MR lineage trials, only if the Owner has approved §2.2 before the Trend terminal decision.
7.5 Cycle-2 closure record, then STOP.

## 8. Boundaries (restated from the parent; unchanged)
No FP-CONTROL-3, P2 database, P2 evidence lane or P2 host use · off-host execution only · no exchange trading
credential · no new paper worker · no automatic survivor promotion or paper admission · no H1 mutation or
launch · no P3 implementation · no real money · no new stage.

## 9. Terminal
A Cycle-2 closure record in the RESEARCH_CYCLE1_CLOSURE_1 format (trial accounting, selection debt,
data/holdout truth, evidence status, paper-admission eligibility, P2 firewall), then STOP. Each survivor's
paper admission is a separate Owner decision. Placement follows the H1 precedent (WAIT_FOR_P2_CLOSURE unless
the Owner approves otherwise).

## 10. Classification of the opening PR
GOVERNANCE-ONLY / NON-EXECUTING. Allowed scope: this record; the minimum scope-audit test update required to
recognize it; MANIFEST.txt regeneration; the Master Plan Lane-B research-authority correction with its §22 change
record. Forbidden: research implementation, strategy code, new driver or tooling,
dependency installation, workflow execution changes, trial-ledger append, candidate preregistration, H1
changes, P2 changes, runtime changes.

## 11. Control Room compatibility (architectural constraint, not a deliverable)
Cycle 2 creates no monitoring product, dashboard, database or control plane. The live Grafana / Prometheus /
exporter stack is untouched. The canonical research records and research/trial_ledger.py remain the source of
truth. Any machine-readable output that Cycle-2 tooling later produces must be deterministic, rebuildable
where appropriate, non-authoritative if derived, and ingestible by the future State Resolution layer of the
single unified Control Room (P3-PLN-02 / PLN-06 / PLN-09). It must be able to represent at least: research
authority state, cycle ID, family, lineage, candidate ID, config ID, trial ID, ledger verification state,
trial counts and budget consumption, current funnel step, candidate state, SOURCE CLAIM / OUR RESULT /
VERIFIED RESULT, terminal state, paper-admission eligibility, paper worker admission state, evidence location
and digest, selection debt, holdout status, isolation status, last activity / freshness, blocking condition,
Owner action required, and Claude action required. Budget consumption, funnel step, isolation status,
freshness and Owner/Claude action have no machine-readable source today. They are future implementation
requirements and are not implemented by the opening PR.
