# AUTH-2 implementation notes

Program: `AUTH-2-DISCOVERY-QUALIFICATION-1`. Law: [`FUNNEL_LAW_2.md`](FUNNEL_LAW_2.md). This file records every
place where the code had to choose a concrete definition the package does not spell out, every engine behaviour
that differs from a stock Freqtrade 2026.7 backtest, and everything seen before preregistration. It changes no
law, threshold, family, window, dataset, engine or cap. Each value below is also fixed in the node
preregistrations (`prereg/*.json`) and pinned by sha256 in the program charter before any node runs.

PAPER / RESEARCH ONLY. Backtesting only; `dry_run` true; spot; long or cash; no exchange key, private endpoint,
order, leverage, margin, future or short. Hyperopt 0. No LLM or agent call exists in the experiment code.

## Files

| File | Role |
|---|---|
| `archive.py`, `universe.py`, `dataset_v3.py` | Dataset V3 acquisition, point-in-time universe law, lock build and byte-identical verification (D0). Their sha256 are recorded in the lock; they are not edited after the lock. |
| `market_io.py` | Loads the lock's engine data, membership and funding into the generators and the replay evaluator. |
| `signals.py` | Every schedule generator (primaries, perturbations, matched benchmarks, nulls) and the causality checks. |
| `families.py` | Named bundles of schedules per family; perturbation table; N; null seeds. |
| `replay.py` | The replay evaluator (§REPLAY_EVALUATOR_CONTRACT) and the parity check. |
| `engine/run_backtest.py`, `engine/markets.py`, `engine/AUTH2ScheduleFollower.py`, `engine_io.py` | The judged engine: Freqtrade 2026.7 driven by a frozen schedule. |
| `stats.py`, `gates.py` | Statistics and the gate table (C1–C12, family gates, Holm). |
| `synthetic.py`, `calibration.py` | Synthetic worlds, the planted-edge calibration and CAL-Ax-STAT. |
| `run_node.py` | Runs one DAG node; `--next` lists the nodes the DAG allows next. |
| `dispatch_guard.py` | Billing, serial, re-run, attempt, minutes, invocation and reserve checks before every job. |
| `closure.py` | Closure record and the terminal ledger records. |
| `make_preregs.py` | Writes (or `--check`s) the 17 preregistrations, the program charter, and appends the 14 PREREGISTERED ledger records. |
| `calibration_edges.json` | The calibrated planted-edge strength per family (see §Calibration). |
| `requirements-auth2.txt` | Hash-pinned `arch` 8.0.0 and its closure (cp312 and cp313 wheels). |

## Engine

* **Image.** `freqtradeorg/freqtrade:2026.7` for every engine run in AUTH-2 [OD-5]. Locally the same code runs
  under `freqtrade==2026.7`; the workflow uses the image.
* **One strategy class.** `AUTH2ScheduleFollower` trades a frozen target-weight schedule. It makes no decision; the
  schedule is generated before the run by `signals.py` and pinned by sha256 in the run config. Fills, fees,
  wallet and position accounting are Freqtrade's own.
* **Schedule semantics.** At an execution time T each row holds every pair's target weight as a fraction of
  equity E(T) = free stake + Σ amount × open(T), computed once per row before any order at T. A pair absent
  from a row is exited at T's open. A delisting terminal bar forces an exit at that bar's open. Signals sit on the
  candle before T because Freqtrade fills at the next candle's open.
* **No stop-loss and no ROI exit** (`stoploss = -1.0`, `minimal_roi = {}`). The package's strategies have neither.
  This matters on real data: the archive contains flash-crash wicks (20 symbols have a 1h low below 0.2 × open;
  LINKUSDT prints 0.0001 on 2020-03-12; no zero lows exist). An earlier follower with a −99% stop exited on such
  a wick, which the strategies never intend; it was removed before preregistration.
* **Disclosed launcher patches** (`engine/run_backtest.py`):
  1. **Frozen market table.** Freqtrade loads markets through ccxt before backtesting; Binance's API refuses
     GitHub runners (HTTP 451) and delisted symbols are absent from today's list. The launcher installs a frozen,
     neutral USDT spot market per engine pair (no minimum amount or notional).
  2. **Price precision from the frozen markets (none).** Freqtrade otherwise infers a price tick from the candle
     data and rounds every exit price to the tick of the month the trade opened in, which can push an exit capped
     at the candle low just outside [low, high] (unfilled) and rounds away or doubles the A2 +0.05%/side
     surcharge on cheap coins. With no price precision every order fills at open ± the schedule's slippage,
     capped to the candle's range, which is the cost law.
  3. **Defensive trade deep copy skipped.** Before each strategy callback that receives a trade, Freqtrade deep
     copies it with its whole order history; a daily-rebalancing follower accumulates thousands of orders per
     trade and the copy becomes quadratic (over 90% of run time; one A3 year 73 s → 9 s). The follower only reads
     the trade. Proven result-identical: with and without the copy the exported trades are equal and the wallet
     feather files are byte-identical (only the backtest start/end timestamps differ). `--keep-trade-copy` runs the
     stock path for that test.
* **Amount precision.** Per pair, `amount_tick(min_price) = 10^(floor(log10(1e7 / min_price)) − 14)`, so every
  amount has at most 15 significant digits. Freqtrade 2026.7 closes a trade's books only when the remaining
  amount, summed exactly over its orders, truncates to zero; a 1e-12 float residual after partial exits made it
  book only the last exit's profit (found as an A2 parity failure on 2019-11-25 and fixed before
  preregistration). The implied truncation is below 1e-14 of an order's value.
* **Paper safety.** Every run config passes the backtest-applicable checks of `scripts/paper_guard.py`
  (`engine_io.guard_config`): `dry_run` true, spot, no key, the only command is `backtesting`.

## Replay evaluator and parity

* The replay evaluator mirrors Freqtrade 2026.7's backtest accounting as read from its source (fills at the bar
  open with min/max capping, average-cost basis, fee realisation at sale, sizing equity fixed once per row,
  processing order: open positions in opening order, then new entries in whitelist order, buys capped by free
  cash, the equity mark at each day boundary taken at the bar open before any order).
* **END_AT_CLOSE.** The secondary window ends 2026-08-31 inclusive, so its last daily mark is 2026-09-01 00:00,
  where Dataset V3 has no bar (its last 4h bar opens 2026-08-31 20:00 and closes at that mark). In that case only,
  the engine and the replay both value the final mark at the last bar's close: the replay with its own holdings,
  the engine with the balances Freqtrade captured at the last bar times that bar's close, read from the engine's
  own data files. Nothing executes in the last bar (every row is a 00:00 or 04:00 execution and delisting exits
  fall before the dataset end); the engine reader refuses a schedule that would. The window is unchanged. Every
  input that worked before is unaffected (such a window used to raise). The engine self-test proves the
  convention in the pinned image (final-day return difference to the replay ≤ 1e-6; measured 7.7e-12 for A2 and
  3.9e-12 for A3).
* Parity is checked for every engine run of PC-Ax, N-Ax, Ax and SC-Ax: daily-return correlation ≥ 0.999 and
  total-return difference ≤ 0.25 pp. A failure is a C1 integrity failure (INVALID_RUN) and every replay-derived
  statistic for that family is NOT_EVALUABLE.
* Pre-freeze parity measurements (timing runs only; see §Disclosed pre-registration exposure): A3 total-return
  difference 8.8e-11, A1 6.3e-11, A2 (null fixture, 55 pairs) 3.8e-6.

## Data and universe

* Dataset V3 is the Binance public archive (`data.binance.vision`, checksum-verified), spot 1h klines
  2018-01 → 2026-08 for every USDT spot symbol, live and delisted, plus BTCUSDT/ETHUSDT USDT-M funding (read
  only). Market data is never committed; the lock pins every file's sha256. D0 rebuilds the lock on a runner and
  requires every committed lock file to be byte-identical.
* Operationalisations of the universe law are listed in `universe.py`'s header: listing segments split at
  ≥ 168 hours without a kline (a reused ticker such as LUNAUSDT is two listings); eligibility needs a kline in the
  24 hours before the selection time; the ranking statistic is the quote volume of klines opening in the 90 days
  before it, ties by symbol; "price data on a day" is the 23:00 UTC kline; the coverage window is 2019-01-01 →
  2026-08-31 with each window also reported.
* Trustworthy terminal price: the 24 klines before the last one all exist with volume > 0; otherwise the
  member-days count as missing (DATA_LIMITED law). Primary delisting exit at 0.80 × last close; 1.00× and 0.60×
  are diagnostics (`gates.delisting_diagnostics`, reported, never a rescue).
* The lock records `data_limited` false for A1, A2 and A3 and `a3_start_utc` = 2021-02-01 (4 complete folds).
* The 4h engine bars are derived from 1h deterministically and reconciled (C1 DATA_TRUTH).

## Signals

Frozen conventions (`signals.py`): the daily close C(D) is the close of the 4h bar opening at D − 4h; an L-day
return is C(D)/C(D − L) − 1; realised vol is the sample sd (ddof 1) of daily simple returns × √365; funding m7(D)
is the mean of rates with calc time in [D − 7 days, D); z(D) uses the 365 daily m7 values ending at D; a weight
that cannot be computed is 0 (cash). LOOKAHEAD and RECURSIVE checks run on every generator a node judges.

## Statistics

* Sharpe ratios are annualised with √365 on calendar-day returns (24/7).
* C3 / C7 / A3-1: the Ledoit–Wolf (2008) studentized stationary bootstrap of SR(a) − SR(b), paired, 10,000
  resamples, fixed seeds (C3 20261010, C7 20261011, SPA 20261012). The covariance of the four moments is the
  batch-means estimator with batch length b (the §BOOTSTRAP_RULE block length), in the sample and inside every
  resample, so each resample is studentized like the sample.
* p-values are (1 + #{t* at least as extreme as t}) / (1 + B), never zero.
* Block length follows §BOOTSTRAP_RULE exactly with `arch.bootstrap.optimal_block_length`; a non-finite estimate
  is NOT_EVALUABLE, never a fallback.
* SPA: `arch.bootstrap.SPA`, consistent p-value, performance levelled to 20% annualised volatility inside the test
  only.
* DSR: the audited Cycle-2 wrapper (`research/cycle2/multiple_testing.py`, trialgate), N = 21 / 6 / 4.
* PBO (C11): CSCV with 16 blocks through the same wrapper. The wrapper requires a threshold argument; 0.5 is
  passed and its PASS/FAIL is discarded. Only the value is reported; PBO is never a gate.
* `arch` 8.0.0 is hash-pinned (`requirements-auth2.txt`); a fixed test vector in the test suite checks
  `optimal_block_length` and `SPA`.

## Verdicts

Gate precedence in one family (`gates._verdict`): any evaluable gate that FAILS ⇒ REJECTED; otherwise any gate
NOT_EVALUABLE or short coverage (C8) ⇒ INCONCLUSIVE; otherwise PRE_HOLM_PASS. So a family that fails a gate is
REJECTED even if its coverage is short: a failure is evidence, short coverage only withholds a pass. C1 is
checked before the gates; any C1 failure is INVALID_RUN.

## Calibration

* **True δ.** "Computed by the frozen generator on a 200-year simulation of the same design": one 200-year path
  of a 70%-volatility price leaves floating-point range, so the 200 years are pooled from consecutive independent
  worlds of the frozen generator (seeds 500000, 500001, …), each priced over the family's scored window, until
  the scored days reach 200 × 365. True δ is SR(primary) − SR(matched benchmark) on the pooled series at base
  cost (A3: overlay versus base).
* **Edge strength.** Bisection (14 steps) on the planted-edge strength until true δ is within 0.005 of the Owner's
  δ (0.40 / 0.40 / 0.30). The results are in `calibration_edges.json` (edge, true δ, trace) and in each CAL/PC
  preregistration.
* **CAL-Ax-STAT.** No-edge worlds use seeds 1–200, planted-edge worlds 10001–10200, PC-Ax seed 777; all disjoint
  from the true-δ seeds. A count stops early only once its outcome is decided (more than 10 accepted no-edge
  worlds, or more than 40 rejected planted-edge worlds); the record says so. A world is accepted only if the full
  stack passes and its C3 p-value passes Holm's first step at m = 3 (0.05 / 3), the other two families entering
  with p = 1. In a world, evaluation stops at the first gate that prevents acceptance; acceptance is the
  conjunction, so the order changes no outcome.
* In calibration worlds every series, including those an engine run judges in PC/N/Ax, comes from the replay
  evaluator; PC-Ax then proves the engine path on one planted world.

## Synthetic worlds

`synthetic.py`: GARCH(1,1) Student-t (4 dof) daily returns, one common factor (ρ = 0.6), 70% annualised
unconditional volatility, 4h bars built from the daily path; nothing is fitted to AUTH-2 results or to market
data. Planted edges: A1 drift ∝ sign of the trailing 60-day return; A2 weekly drift by cross-sectional rank of the
trailing 28-day return; A3 funding AR(1) per asset and, while z > 2, a 30-day window of elevated one-day crash
probability.

A3 correction before preregistration: in the first version the elevated crash probability also lowered every
asset's expected drift, so planted worlds were simply worse markets (primary total return about −85% on check
seeds 900001/900002, used by no node) and C2 rejected even a perfect overlay. Each asset now receives the constant
log drift that returns its expected crash loss to the no-edge level, so a planted world differs from a no-edge
world in crash timing, not in expected drift. The A3 edge strength was calibrated after this change. No-edge
worlds are unchanged.

Same worlds on every CPU: bar prices are exp of the log path through the C library's scalar exp. numpy's
vectorised exp takes a different code path on CPUs with and without AVX-512, and the last bit differed, so the
first PR CI run (on a runner without AVX-512) regenerated a different A3 world from the one recorded here.
Everything else in a world is IEEE arithmetic and square roots. With the change, worlds, schedules, replay results
and true δ are bit-identical with numpy's AVX-512 paths enabled and disabled (`NPY_DISABLE_CPU_FEATURES`). The edge
calibration was re-run in full on the revised generator: the same edges, with true δ moving only in the last digits
(`calibration_edges.json` `code_revisions`). Real-data schedules never depended on this (verified with AVX-512 on
and off on identical bars), so the N-Ax to Ax engine-run reuse is unaffected.

## Nulls and engine-run reuse

* C4 null distributions use seeds 1–1000. The N-Ax fixture is null seed 0; its "perturbations" are null seeds
  1001–1005 (A3: 1001–1003).
* C1 LOOKAHEAD and RECURSIVE in N-Ax run on the family's own generators (primary, perturbations, matched
  benchmark) on the node's real data, the procedure the null traverses. The null fixtures are not put through
  them: the law defines each null over the whole window (A1 shifts by an offset in [90 days, T − 90 days]; A3
  places the primary's episode count and durations at random times), so truncating the window changes a null by
  construction although its placement reads no price. Checking them would make every N-A1 and N-A3 an
  INVALID_RUN. A pre-registration end-to-end smoke test on synthetic data found this; the node record says which
  generators were checked.
* The matched-benchmark engine runs (base, ×2, latency, A2 U8, secondary) execute once, in N-Ax, and are reused in
  Ax and SC-Ax only if the re-generated schedule's sha256 equals the N run's (identical configuration). Otherwise
  the node refuses.

## Compute and dispatch

* One node (PC-A2 and N-A2: one half) per GitHub Actions job, dispatched by hand through
  `.github/workflows/auth2.yml`, `workflow_dispatch` only. Job timeouts equal the package table (Σ 1,980 minutes);
  planned engine invocations 107. Results pass between nodes as artifacts with 90-day retention: a DAG paused
  longer than that cannot read its predecessors and stops (fail-closed).
* `dispatch_guard.py` runs before every dispatch and again as the job's first step. It fails closed when the
  account's remaining included minutes or the USD 0 Actions budget cannot be read. It needs a repository secret
  `AUTH2_BILLING_TOKEN` (a token that may read the account's billing); without it every job stops at the guard.
  A run the in-job guard stops still counts as an attempt and its billed minutes count toward 4,000 (conservative).
* Operated dispatch (Owner decision card "Check in Actions", after PR #57 merged). The executor's session
  reaches GitHub only through repository endpoints, so it can neither read the account's billing nor download
  run artifacts. The pre-dispatch guard therefore runs as its own job, `.github/workflows/auth2-guard.yml`
  (10-minute timeout, the `AUTH2_BILLING_TOKEN` secret), and publishes its decision record as a job
  annotation. A node (or the closure) is dispatched only after `.github/gates/auth2_operator.py
  check-dispatch` verifies that record: a successful guard run of that node part on the current main,
  deciding DISPATCH, at most 15 minutes old, with no AUTH-2 run created after it. Every guard (pre-dispatch
  and in-job) is `dispatch_guard.decide`, unchanged, over the node runs, plus two additions for the guard
  and closure jobs: none may be active, and their billed minutes count toward the 4,000-minute ledger. The
  additions only refuse; no refusal of `dispatch_guard.py` is removed. Node jobs publish a summary of their
  result records (sha256, terminal state, `data_limited`, `holm_pass`), which `auth2_operator.py next`
  feeds to `run_node.eligible`. The closure record is computed by `.github/workflows/auth2-closure.yml`
  (where the artifacts are readable), published the same way, and read back byte-exact (`readout`); the
  terminal ledger records are appended from it by `closure.append_ledger`. Nothing under `research/auth2/`
  changed, so every preregistration's code pins still hold.
* Billing evidence (after PR #59; the first guard runs answered HTTP 403, then HTTP 410). `dispatch_guard.read_billing`
  reads `GET /users/{owner}/settings/billing/actions`, one of the product-specific billing endpoints GitHub closed
  down (changelog 2025-09-26); it answers 410 "This endpoint has been moved" (the earlier 403 was the workflow's own
  token answering while the secret was unset). The guard now reads billing through `.github/gates/auth2_operator.py`
  instead: the replacement for a personal account, `GET /users/{owner}/settings/billing/usage` (enhanced billing
  platform; fine-grained token with the "Plan" user permission, read), called with the billing token only, never
  the workflow token. A well-formed report of this account and month is recorded as evidence of the token, the
  account and the period. It cannot prove either control the pacing rule needs, and no GitHub endpoint can for a
  personal account: no field holds the included-minutes quota or the remaining included minutes, and
  `discountAmount` merges included usage with the free usage of public repositories and self-hosted runners
  (GitHub docs, "Billing reports reference"), so no difference of reported figures is the remaining allowance;
  and the budgets API exists for organizations only, so the USD 0 budget and its stop-usage setting cannot be
  read. Both controls therefore stay unproven and every decision is NO_DISPATCH (fail-closed) until the Owner
  settles how they are evidenced. The same change makes a re-run attempt of a node or closure job refuse in the job
  (RE_RUN; a technical retry is a new dispatch) and counts the billed minutes of every attempt toward 4,000.
* Owner billing evidence (Owner decision AUTH2-OWNER-BILLING-EVIDENCE-BRIDGE-1, after PR #60). Only the evidence
  source of the two controls GitHub does not expose changes; the rule, A_m, R_m and the caps do not. The Owner states
  both in the pre-dispatch guard run itself: `auth2-guard.yml` takes the remaining included Linux minutes the billing
  page shows (digits only: no sign, separator, space or leading zero) and two choices, `actions_budget_usd_zero` and
  `stop_usage_enabled`, that default to NOT_CONFIRMED. The guard reads them from the event GitHub delivered to the job,
  never from an environment value, repository variable, committed file or secret, and accepts them only when the
  Actions API reports the Owner (`algamal119933-ux`, account id 325778659) as the run's actor and triggering actor,
  at the run's first attempt, on main, with the event's sender the same account. The usage report is still read with
  the billing token beside it, as independent evidence of the token, account, month and schema; it never supplies a
  figure, and without it nothing dispatches. The guard records one evidence object (`AUTH2_OWNER_BILLING_EVIDENCE_1`:
  repository, guard run and attempt, main SHA, node part, actor and triggering actor with their ids, billing month,
  remaining minutes, both confirmations, the run's creation time, the usage endpoint and period, and the sha256 of all
  of it). Only valid evidence beside a verified usage report makes billing readable, with the attested minutes and a
  confirmed budget. Every node or closure dispatch names that guard run and evidence digest (`check-dispatch` prints
  both). Its in-job guard reads the guard record from the guard run's artifact and verifies, as of its own run's
  creation, what `check-dispatch` verified before the dispatch: same repository, node part and main SHA; a
  successful first-attempt guard run by the Owner deciding DISPATCH; valid evidence with that digest; a verified usage
  report; a record at most 15 minutes old; no AUTH-2 run created after the guard run. It then takes the billing state
  from that record, never from its own inputs, and verifies the usage report again itself. A_m stays where
  `dispatch_guard` keeps it. A guard run fixes nothing. The in-job record of the month's first node run states A_m (the
  attested remaining minutes at that dispatch) and R_m = max(500, ceil(0.20 × A_m)), and every later guard that month
  takes both from it; later attestations give only the current remaining minutes. That record must be the run's own,
  for the month, the same across its attempts, and resting on the Owner evidence it was dispatched on; otherwise every
  guard that month refuses. So a month's first node run whose binding fails states no A_m and blocks the month: only
  the inputs `check-dispatch` printed are dispatched. Limitation: the executor's GitHub access is the Owner's account,
  so the actor check proves the account, not who typed the figures. The executor therefore never dispatches
  `auth2-guard.yml`; only the Owner does.
* Usage report repository names (guard run 38220977904, after PR #61). GitHub's live usage report names the account's
  own repositories without an owner (`"repositoryName": "trading-lab-os-sandbox"`), not in the "user/example" form of
  its docs example, and the account check required the owner prefix. It therefore refused every live report
  (WRONG_ACCOUNT, at HTTP 200), and the Owner's D0 attestation (1,495 minutes, both confirmations) decided
  NO_DISPATCH. The report is per account: the endpoint names the account, and GitHub answers it only for a token that
  may read that account's billing. A bare name is therefore this account's repository and is accepted, as is the
  owner-qualified form for this account. A name qualified with any other owner, or a name that is not a string, is
  still refused. No threshold, cap, input, binding, freshness or evidence rule changed.
* Node checkout history (D0 run 38273417548, after PR #62). The node job checked out one commit (the
  `actions/checkout` default, depth 1). `run_node`'s program check (`check_research_program.py`, commit order) dates
  the program by the commit that first added it, and in that checkout the only commit, the dispatched main
  (410418e, 2026-10-12T08:29:03Z), looked like that commit. Every node's PREREGISTERED record (2026-10-11T05:16:40Z
  on) was therefore "older than the program", and the node refused before any data work. In full history the program
  was first added at 2026-10-11T00:38:48Z (ef6336d), before every record, and the check passes, as it does in CI,
  which fetches full history. The node job now fetches full history too. The run counts as D0's first run, so one
  D0 run remains (dispatch_guard MAX_ATTEMPTS 2). No gate, record, threshold or cap changed.
* `run_node.py` exits 4 on INVALID_RUN so the job fails and the one technical retry is available; every law
  terminal is a successful run. A second INVALID_RUN stops the program (`closure.py --stop-program`).

## Ledger

* 14 trial IDs: `TRIAL-AUTH2-D0`, `-CAL-A1..3`, `-PC-A1..3`, `-N-A1..3`, `-A1..3` (scientific; SC-Ax is part of
  it), `-HOLM`. Each PREREGISTERED record binds the sha256 of every preregistration that runs under it
  (`dataset_identity.preregs`); `run_node.py` refuses a node whose preregistration differs.
* The program charter is committed before the PREREGISTERED records (the program validator requires it).
* Terminal records are appended at closure only, mapped as §DAG_OPERATIONS states.

## Disclosed pre-registration exposure

On 2026-10-10 about 21:20 UTC an implementation smoke test ran the A3 and A1 PRIMARY configurations through the
engine on real Dataset V3 data over their scored windows, before preregistration, to measure run time and replay
parity. It printed each run's engine total return: A3 +104.0%, A1 +260.5% (under the since-removed −99%
stop-loss follower). No benchmark, ΔSR, p-value or gate was computed; A2's primary run was stopped before it
reported. Nothing that these numbers could inform was changed afterwards: primary configurations, perturbations,
thresholds, windows and δ are the Owner-frozen package values. Later timing runs used a null fixture with seed
424242, which no node uses, and printed only timing and parity.

## Not in AUTH-2

No H1 launch, no AUTH-3 or AUTH-4 content, no change to P2 / FP-CONTROL-3, no real-money authorisation, no engine
upgrade, no new framework, control plane, dashboard, database or orchestration platform.
