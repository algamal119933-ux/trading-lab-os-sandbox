# PROFITABILITY-VERIFICATION-LAW-1 — how a profitability claim is earned

**Status: DRAFT FOR OWNER FREEZE, with the Owner's decisions OD-1, OD-2 and OD-3 applied (§15).** It binds
nothing until the Owner merges the PR that adds it. **The methodology freezes on that merge, before any new
evaluation result exists.** After the merge it is FROZEN: changing any word or value needs a new Owner record
and a new law file; this file is never edited.

**Authority:**
- the Owner directive "PRIORITY 2 — PROFITABILITY PROOF LAW" (2026-10-26). It asks to *"prepare and
  freeze a prospective profitability verification protocol … before collecting new evaluation results;
  separate historical exploratory evidence from genuinely prospective evidence; do not claim profitability"*;
- the Master Plan §14 (FUTURE VALIDATION FUNNEL) and §16 (FUTURE PAPER-WORKER CONTRACT).

**Classification:** governance record. **It authorizes nothing and executes nothing.** It does not open
research, a trial, a backtest, a paper worker, H1 or real money. Every evaluation it governs needs its own
separate Owner authority. `REAL_MONEY_AUTHORIZED = NO` · `H1_LAUNCH_AUTHORIZED = NO`.

**This law claims no profitability.** It states what evidence would be needed, and which words may be
used, before anyone may say a strategy has an edge.

**Relationship to merged law.** This law is a sibling of the merged program laws, not an amendment:
- [`research/cycle2/FUNNEL_LAW_1.md`](cycle2/FUNNEL_LAW_1.md) (Cycle 2);
- [`research/auth2/FUNNEL_LAW_2.md`](auth2/FUNNEL_LAW_2.md) (AUTH-2).

Those laws keep governing their programs unchanged. This law adds two things:
- a **prospective** layer, which none of them define (the AUTH-3 paper rule was explicitly not authorized
  in FUNNEL-LAW-2);
- **minimum requirements** that any future program's historical funnel law must meet.

Where the two merged laws differ on PBO, §4.1 resolves it explicitly (Owner decision OD-1).

---

## 1. Purpose and non-claims

- **Purpose:** fix, before any new evaluation data exists, the statistics, thresholds, sample requirements,
  multiple-testing corrections and stop conditions under which TLOS may use each of these words:
  - "not refuted";
  - "proven";
  - "refuted";
  - "killed".
- **No result today meets this law.** P2 recorded `PROSPECTIVE_PAPER_EDGE = NOT_EVALUATED` (n = 1).
  Every TLOS profit candidate to date was rejected or failed a gate. Nothing in the repository is a
  profitability claim.
- **A verdict under this law is about statistical evidence for an edge, not about money.** A Level-B
  verdict (§9) still does not authorize real money. Real money stays behind the separate Owner live
  authorization (Master Plan §1, §27).

## 2. Evidence classes (never relabelled)

| Class | What it is | May support |
|---|---|---|
| `HISTORICAL_EXPLORATORY` | Any backtest, screen, hyperparameter search or development-window result, including every run whose data was seen while the design was being chosen | Generating hypotheses only. Never a profitability claim |
| `HISTORICAL_LOCKED_HOLDOUT` | A pre-declared, hash-locked historical window opened **once**, after the design was frozen (Master Plan §14; CLAUDE.md "Locked OOS rule") | Passing or rejecting a candidate for prospective testing. Never "proven" |
| `PROSPECTIVE_PAPER` | Paper returns of a frozen candidate. The window starts at a preregistered T0 recorded (Git-merged) **before** the first included bar exists | Level A and Level B verdicts (§9) |
| `PROSPECTIVE_LIVE` | Real-money fills under a separate Owner live authority (POST-BETA) | Measuring friction, and Level A/B, under that authority only |

Rules:
- Historical evidence can **never** be relabelled prospective.
- A prospective window can never include data that existed before its T0 record was merged.
- A holdout opened twice, or used to change anything, is `BURNED` (CLAUDE.md) and becomes
  `HISTORICAL_EXPLORATORY`.
- Reporting mixes no classes. Every figure carries its class.

## 3. Preregistration (before T0; immutable after)

Each candidate entering a prospective test preregisters all of these. Every field is required, and a
missing field is `LAW_INVALID`.
1. Candidate identity: config identity sha256 (as in the FUNNEL-LAW-1 N LAW) and the frozen package
   digest.
2. **Test unit**: `DAILY` (calendar-day net returns, 365/yr) or `TRADE` (closed-trade net returns). `TRADE`
   is required when the expected trade count is below 52 a year.
3. **Declared Sharpe**:
   - the candidate's deflated historical Sharpe, with its N_eff;
   - the **alternative s**, chosen once in [0.50, 0.75] × the deflated historical Sharpe, expressed per
     unit;
   - the expected unit count per year.
4. Test design (§6): `SPRT` (default) or `FIXED_HORIZON`, with α, β, burn-in, the **truncation horizon**
   (max units, and a calendar cap no later than the authority's expiry), and the calibrated upper bound
   (§6.4).
5. Kill rules (§7) with their numeric bounds.
6. The concurrent candidate set, for Holm (§8): m is fixed at preregistration.
7. Costs: the fee and slippage model, the exchange minimum-order handling, and the benchmark lines
   reported alongside (no-trade, and BTC buy-and-hold on the same window).

## 4. Historical gates (minimum requirements for any program's funnel law)

A program's own frozen funnel law decides its historical verdicts. To feed a prospective test under this
law, that funnel law must at least require:
- **Bias gates:**
  - Freqtrade `lookahead-analysis` and `recursive-analysis` PASS on the frozen candidate (Master Plan
    §14 LOOKAHEAD / RECURSIVE);
  - DATA_TRUTH PASS (Master Plan §13).
- **DSR ≥ 0.95** on the net Sharpe of the chosen configuration. N is counted as the merged N LAW counts
  it: `family_configuration_N`, distinct configuration identities, cumulative across cycles (FUNNEL-LAW-1).
  - A program may use a correlation-clustered N_eff only if its clustering rule is preregistered and
    Owner-approved.
  - The default is no reduction, which is the conservative choice.
  - An unresolved N is `NOT_EVALUABLE`, never a guessed N.
- **PBO by CSCV with 16 blocks**, computed whenever at least two configurations exist, and always
  reported. Its gate role is fixed by §4.1 (OD-1).
- **Upstream selection debt** that cannot be observed is disclosed verbatim beside every DSR and PBO
  figure (FUNNEL-LAW-1 L3).

### 4.1 PBO resolution (Owner decision OD-1)

| Program | PBO rule | Governing law |
|---|---|---|
| Research Cycle 2 (`research/cycle2/`) | **Hard gate PBO ≤ 0.05**; NOT_EVALUABLE blocks SURVIVED | FUNNEL-LAW-1, unchanged |
| AUTH-2 (`research/auth2/`) | **Diagnostic only, never a gate** (always reported) | FUNNEL-LAW-2, unchanged |
| **Every NEW research program** opened after this law's merge (including A1b) | **Hard gate PBO ≤ 0.05** by CSCV with 16 blocks. NOT_EVALUABLE (fewer than two configurations) is never PASS and blocks a prospective test | This law |

- The two merged laws are **preserved unchanged**; they keep governing only their own programs. Changing
  either needs a separate Owner-authorized amendment.
- A new program may not choose a looser rule. There is no 0.10 ceiling any more: the earlier planning value
  of ≤ 0.10 is withdrawn.
- A program's preregistration names which row governs it. A missing or mismatched row is `LAW_INVALID`.

These statistics are computed only through the audited wrapper `research/cycle2/multiple_testing.py`
(trialgate==0.5.0, `research/cycle2/TRIALGATE_AUDIT_1.md`), which `research/verification_law` forwards to.

## 5. Reporting statistics (reported, never gates by themselves)

- **PSR** against 0 and against the deflated historical Sharpe.
- **MinTRL**: the units still needed for PSR ≥ 0.95 at the observed moments.
- **Harvey–Liu haircut Sharpe** (BHY adjustment, the declared number of tests).
- Exposure-adjusted comparison against the no-trade and buy-and-hold lines.

Reduced exposure is not alpha (CLAUDE.md "Historical passive Development benchmark").

## 6. The prospective test

### 6.1 SPRT (default)
- **Statistic:** a Wald SPRT on standardized unit returns `x_t = r_t / sd(r_1..r_{t-1})`. The standard
  deviation comes from previous units only, with no look-ahead. The first `burn_in` units (≥ 20) only
  seed the standard deviation.
- **Hypotheses:** H0: per-unit Sharpe = 0 against H1: per-unit Sharpe = s (§3.3).
- **LLR increment:** `s · x_t − s²/2`.
- **Error rates:** **α = 0.05, β = 0.20.**
- **Wald bounds:** upper `A = ln((1−β)/α) = 2.773`, lower `B = ln(β/(1−α)) = −1.558`.
- **Decisions:**
  - LLR ≥ A* (the calibrated upper bound, §6.4) → `ACCEPT_H1`;
  - LLR ≤ B → `ACCEPT_H0`, which is the refutation, and the kill boundary of §7;
  - neither, at the truncation horizon → `TRUNCATED`.

### 6.2 Fixed horizon (alternative)
- **Test:** PSR(observed, benchmark 0) ≥ 0.95 at the preregistered horizon, and nowhere else. The test
  may not peek: interim looks are reported only and never decide.
- **Horizon:** at least `years_for_power(s_annual, α=0.05, power=0.80)`.

### 6.3 Truncation
`TRUNCATED` → `INCONCLUSIVE_UNDERPOWERED` (§9). It is never rounded up to either side. The candidate may be
preregistered again only as a **new** trial (§11).

### 6.4 Calibration (mandatory before freeze; Owner decision OD-3)
Wald's bounds assume i.i.d. Gaussian units. Crypto returns are fat-tailed, volatility-clustered and serially
dependent, and the repository's own seeded simulations show the naive bound over-accepts at zero edge: about
0.073 under Student-t(3) and about 0.067 under GARCH(1,1)-t(3) (`tests/test_verification_law.py`).

The defaults (α = 0.05, β = 0.20, s in [0.50, 0.75] × the deflated historical Sharpe, burn-in ≥ 20) apply
**only through a valid preregistered calibration**. Before T0 the preregistration must record:

1. **Return models**, every one of which must pass:
   - Gaussian i.i.d. (`iid_model()`), as the baseline;
   - Student-t(3) i.i.d. (`iid_model(student_t_sampler(3))`), for fat tails;
   - GARCH(1,1)-t(3) with a = 0.12, b = 0.85 (`garch_t_model()`), for volatility clustering; a candidate may
     declare stronger clustering, never weaker;
   - a **stationary block bootstrap** of the candidate's own historical unit returns
     (`stationary_bootstrap_model(series, mean_block ≥ 20)`), for temporal dependence and the empirical
     tail. The series is demeaned and scaled, so it is a zero-edge null; historical evidence is used as a
     shape input only and never enters a verdict.
2. **The calibrated bound** `A* = max` over the models of `calibrate_upper_bound(...)["upper"]`, each with
   ≥ 2,000 paths and a fixed, recorded seed. The search starts AT Wald's A, so calibration can only make the
   test stricter. `NOT_CALIBRATABLE` under any model means the design cannot be frozen.
3. **An out-of-sample check** on a fresh seed: simulated `ACCEPT_H1` at zero edge ≤ α + 0.015 under every
   model (`simulate_model_error_rates`).
4. **Power** at A* under H1 (true per-unit Sharpe = s): simulated `ACCEPT_H1` ≥ 1 − β − 0.03 under every
   model. If power falls short, the preregistration must lengthen the truncation horizon or accept an
   underpowered design in writing; it may never lower A*.
5. **Multiple testing:** with m concurrent candidates the calibration uses α/m (§8).
6. **Temporal dependence of the unit itself:** overlapping holdings or autocorrelated units are first
   aggregated to an approximately independent unit (non-overlapping holding periods, or weekly sums), and the
   aggregation is declared. The bootstrap check above must use the aggregated unit.
7. **Selection bias:** s is set from the DSR-deflated Sharpe (N_eff from the ledger), never from the raw
   backtest Sharpe, and the forward stage counts in N (§11).

Reference result in the suite (s = 0.2 per unit, 400 units, 3,000 paths, seed 101):

| Model | False acceptance at Wald's A | A* | False acceptance at A* | Fresh seed (202, 2,000 paths) | Power at A* (seed 303) |
|---|---|---|---|---|---|
| Student-t(3) i.i.d. | 0.073 | 3.27 | 0.050 | 0.043 | 0.81 |
| GARCH(1,1)-t(3) | 0.067 | 3.37 | 0.049 | 0.036 | 0.92 |

These are illustrative; every candidate calibrates at its own s, horizon and models.

## 7. Kill rules (any one → `KILLED`, recorded, never reversed)

1. **Statistical:** the SPRT reaches the lower bound B (`ACCEPT_H0`). The verdict is `REFUTED`, and the
   candidate is stopped.
2. **Drawdown / time under water:** the preregistration declares, from s and its declared unit standard
   deviation, the 95% bounds of Bailey & López de Prado (2015):
   - `MaxDD_95 = (z·σ)²/(4μ)`;
   - `MaxTuW_95 = (z·σ/μ)²`, which is the triple penance rule: recovery takes about 3× the time taken to
     fall.

   A realised drawdown or time under water beyond its bound → `KILLED`. The helpers are
   `max_drawdown_bound` and `max_time_under_water`.
3. **Operational:**
   - a safety gate fails (dry_run is not true, or a credential or live route appears);
   - evidence is corrupt or unattributable;
   - the strategy, config or dataset is changed in any way.

   Any of these → `KILLED` (P3 contract §7 stop conditions apply as well).

## 8. Multiple candidates

- **"Proven" claims:** Holm step-down, family-wise α = 0.05, over the m candidates fixed at
  preregistration. A candidate not tested enters with p = 1, as in FUNNEL-LAW-2's Holm practice.
- **SPRT candidates:** an SPRT candidate counts as rejecting H0 at level α/k only if its calibrated bound
  A* was set for α/k at its Holm step. In practice each candidate is preregistered with A* calibrated for
  α/m, which is the conservative Bonferroni-level bound.
- **Screening only** (choosing what to watch, never a claim): BHY at FDR q = 0.10.
- **Ledger accounting:** every candidate that ever entered a prospective test counts in that family's N for
  every later DSR (§11).

## 9. Verdicts and the Owner's two proof levels

| Verdict | Condition |
|---|---|
| `PROVEN_AT_LEVEL_B` | Every one of these holds: the §4 historical gates passed; `ACCEPT_H1` at A* (or the fixed-horizon PSR ≥ 0.95); Holm passes across the preregistered set; no kill rule fired; and net returns beat the no-trade line, with the Sharpe and drawdown comparison against BTC buy-and-hold reported |
| `NOT_REFUTED_LEVEL_A` | The test is still running or `TRUNCATED` after at least the preregistered minimum duration; no kill rule fired; the LLR is above B. For any live use, **execution friction has also been measured** under a separate live authority (POST-BETA). In paper, Level A means "not refuted" only |
| `INCONCLUSIVE_UNDERPOWERED` | `TRUNCATED` without Level A's minimum, or not evaluable for lack of units |
| `REFUTED` | `ACCEPT_H0` |
| `KILLED` | §7 rule 2 or 3 fired |

**Owner decision OD-2 (binding):**
- **Level A means NOT REFUTED**: the forward test has not reached the kill boundary B, no kill rule fired, and
  (for any live consideration) execution friction has been measured. **Level A is not proof of profitability
  and never grants live authorization.** At most, the Owner *may consider* a small live incubation, which
  still needs its own separate Owner authority.
- **Level B requires prospective statistical evidence under this frozen law**: `ACCEPT_H1` at the calibrated
  A* (or the fixed-horizon PSR ≥ 0.95), Holm across the preregistered set, the §4 historical gates passed,
  and no kill rule fired. Level B is the only level at which TLOS may write "statistically supported edge".
- **No real-money, live or scaling authority follows automatically from either level.** Every such step is a
  separate Owner decision (Master Plan §1, §27).

## 10. Forbidden (any one makes the evaluation `LAW_INVALID`)

- Restarting the clock or the LLR after a drawdown, an outage or a "bad regime".
- Reopening a holdout, or tuning on prospective data.
- Changing s, α, β, A*, the unit, the horizon or the candidate set after T0.
- Dropping failed, killed or truncated trials from N.
- Re-running a configuration to obtain a new verdict.
- Mixing evidence classes (§2).
- Excluding units after the fact.
- Calling reduced exposure alpha.

## 11. Ledger accounting

Every preregistration, prospective start, incubation and terminal verdict is a trial record in the
canonical ledger (`research/trial_ledger.py`, append-only).

Forward and incubation stages are **selection steps**. They count in N exactly like historical
configurations. Evans (2010) shows that incubation that keeps only the survivors manufactures
out-of-sample alpha that disappears afterwards.

## 12. Assumptions and caveats

- **SPRT is not established for this use.** Applying it to monitor a live Sharpe ratio extends general
  sequential-testing theory; it is not a peer-reviewed procedure for this purpose. §6.4 calibration by
  simulation is therefore mandatory, not optional.
- **The return models are approximations.** Fat tails, volatility clustering and autocorrelation violate
  the Gaussian working model. The plug-in standard deviation also adds small-sample error, which the
  burn-in limits.
- **Trial sharpes and N_eff are uncertain.** The DSR's SR0 depends on the cross-trial Sharpe variance and
  on N. A flattering N voids the gate.
- **Expect decay.** Planning should assume prospective Sharpe at 50–75% of the deflated backtest Sharpe:
  - Quantopian's 888 algorithms showed backtest Sharpe R² < 0.025 out of sample;
  - McLean & Pontiff found post-publication decay of about 58%.

## 13. Worked power table (computed by `research/verification_law`; i.i.d.; pinned by tests)

| Annual Sharpe | MinTRL years, normal | MinTRL years, skew −0.5 kurt 10 | Years for 80% power (α 5%) | Power after 1 year | Trades for 80% power at 19/yr |
|---|---|---|---|---|---|
| 0.5 | 10.83 | 10.98 | 24.73 | 0.13 | 470 |
| 1.0 | 2.71 | 2.80 | 6.18 | 0.26 | 117 |
| 1.5 | 1.21 | 1.27 | 2.75 | 0.44 | 52 |
| 2.0 | 0.68 | 0.73 | 1.55 | 0.64 | 29 |

Power after 3 months at Sharpe 1 is 0.13. Under this law nothing can be proven inside the P3 window that
ends 2027-01-31.

## 14. Implementation

`research/verification_law/` (standard library only):
- `psr`, `expected_max_sharpe`, `min_trl`, `min_trl_years`;
- `years_for_power`, `power_after_years`, `trades_for_power`;
- `max_drawdown_bound`, `max_time_under_water`;
- `bhy`;
- the SPRT functions (`SprtState`, `sprt_update`, `sprt_run`, `sprt_decision`, `sprt_bounds`,
  `simulate_error_rates`, `normal_sampler`, `student_t_sampler`);
- the §6.4 calibration (`iid_model`, `garch_t_model`, `stationary_bootstrap_model`,
  `calibrate_upper_bound`, `simulate_model_error_rates`).

`dsr` and `pbo` forward to the audited Cycle-2 wrapper, and `holm` forwards to `research/auth2/stats.py`.
Nothing is reimplemented.

Tests in `tests/test_verification_law.py` cover:
- the DSR paper example (SR0 0.1132, DSR 0.9004);
- equality with trialgate's DSR;
- PBO high on noise and low with a planted edge;
- the §13 table;
- SPRT error rates under Gaussian and Student-t(3) returns;
- the §6.4 calibration: the naive Wald bound over-accepts under t(3) and GARCH-t, the calibrated bound
  restores ≤ α out of sample with power ≥ 1 − β − 0.03, a block bootstrap of a clustered series calibrates
  without weakening, `NOT_CALIBRATABLE` is reported honestly, and the fast path reproduces the SPRT decision
  unit for unit.

## 15. Owner decisions applied (2026-10-27)

- **OD-1. PBO role.** Resolved in §4.1: PBO ≤ 0.05 is the hard gate for every new research program;
  FUNNEL-LAW-1 (gate ≤ 0.05) and FUNNEL-LAW-2 (diagnostic only) are preserved unchanged for their own
  programs. No inconsistency remains open.
- **OD-2. Proof levels.** Applied in §9: Level A = NOT REFUTED, not proof, never live authorization; Level B =
  prospective statistical evidence under this frozen law; no automatic real-money or scaling authority.
- **OD-3. Defaults.** Applied in §3 and §6: α = 0.05, β = 0.20, s in [0.50, 0.75] × the deflated historical
  Sharpe, burn-in ≥ 20, valid only through the §6.4 calibration (fat tails, volatility clustering, temporal
  dependence, multiple testing, power, selection bias). Thresholds are never weakened to obtain a result.

## 16. Sources

- Bailey & López de Prado (2012), "The Sharpe Ratio Efficient Frontier" (PSR, MinTRL):
  https://www.risk.net/journal-risk/2223785/sharpe-ratio-efficient-frontier
- Bailey & López de Prado (2014), "The Deflated Sharpe Ratio": https://papers.ssrn.com/abstract=2460551
- Bailey, Borwein, López de Prado & Zhu, "The Probability of Backtest Overfitting" (CSCV):
  https://carmamaths.org/jon/backtest2.pdf and "Pseudo-Mathematics and Financial Charlatanism" (MinBTL):
  https://carmamaths.org/jon/backtest.pdf
- Bailey & López de Prado (2015), "Stop-outs under serial correlation and the triple penance rule":
  https://ideas.repec.org/a/rsk/journ4/2435335.html
- Harvey & Liu (2015), "Backtesting": https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF
- Wald SPRT: https://encyclopediaofmath.org/wiki/Sequential_probability_ratio_test
- Johari, Pekelis & Walsh, "Always Valid Inference" (mSPRT): https://arxiv.org/abs/1512.04922
- Lo (2002), "The Statistics of Sharpe Ratios": https://rpc.cfainstitute.org/research/financial-analysts-journal/2002/the-statistics-of-sharpe-ratios
- Wiecki et al. (Quantopian, 888 algorithms): https://quantpedia.com/quantopians-academic-paper-about-in-vs-out-of-sample-performance-of-trading-alg/
- McLean & Pontiff (2016): https://rpc.cfainstitute.org/research/cfa-digest/2016/06/does-academic-research-destroy-stock-return-predictability-digest-summary
- Evans (2010), "Mutual Fund Incubation": https://ideas.repec.org/a/bla/jfinan/v65y2010i4p1581-1611.html

PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCH_AUTHORIZED = NO
