# H1-PAPER-ADMISSION-AND-LAUNCH-PACKAGE-1

**Authority:** Owner directive `H1-PAPER-ADMISSION-AND-LAUNCH-PACKAGE-1`
(2026-09-29). Scope: Cycle-1 finalization, the H1 paper-admission decision,
and a **non-running** paper launch package.

It carried **no** authority for P2 mutation, new historical research, starting a
worker, T0, P3 or real money. None was exercised: no backtest was run, nothing
was appended to the trial ledger, no worker was started and no T0 was set.

Package: `research/paper/h1/package/` (`H1-PAPER-COHORT-PACKAGE-1` v1.0.0,
`PACKAGE_MANIFEST.sha256` digest
**`ef9a3d0c5b5b9abe122faaa1bd4ef67feb0c3ec4437bed56cd6ef33d910bc43c`**).

---

## A — PR #39 / CYCLE-1 CANONICAL CLOSURE

These were checked before the merge:
- The PR #39 head was still `34f3b1e5`, unchanged.
- CI was 6/6 pass.
- The PR was `MERGEABLE` / `CLEAN`.
- `main` was still `effa2e76`.

It was merged as a normal two-parent merge under this directive's explicit
authorization (`--match-head-commit` pinned): merge commit
`2a7fc4ebeab1d7dca034c5e1687ae25be9a05895`, with parents `effa2e76` and
`34f3b1e5`. After the merge, local `main` was fast-forwarded and was clean.

```text
RESEARCH_CYCLE1_MERGED   = YES
RESEARCH_CYCLE1_COMPLETE = YES
CANONICAL_MAIN_CLEAN     = YES
```

Cycle 1 was not reopened.

## B — H1 FROZEN IDENTITY

This was recovered from canonical records (`upstream_pins.json`,
`research/h1_qualification/PREREGISTRATION.md`, trial ledger seq 7/19). It was
then re-verified by a read-only, hash-checked fetch of the pinned upstream
bytes.

| Field | Value | Verified |
|---|---|---|
| Candidate | `H1_EMACROSS` (family `BTSL_EMA_REGIME`, lineage `BTSL_EMA_REGIME/L1`) | ledger |
| Strategy repository / commit | `wiktorj137/btc-strategy-lab` @ `b68a5518b4a3eba2fde1733160d7d7de356023b5` | pins |
| Strategy path | `user_data/strategies/EmaCross.py` (class `EmaCross`) | fetch |
| Strategy sha256 | `387cf39f58d266bb63d06865a0784bc2e08676edf54f4610c7d7709bb2a95f24` | fetch = pin |
| Params | `EmaCross.json`: `ema_period = 600`, `exit_threshold = 2.0` | fetch |
| Params sha256 | `9209a90e5092216af166fd10b9e7415690ab16af0fb3010c7e94e162c027e3ee` | fetch = pin |
| Fixed in code | 1h, long-only, stoploss −0.15, trailing stop, `startup_candle_count` 1300 | fetch |
| Pair / timeframe | BTC/USDT, 1h, Binance spot | ledger |
| Engine | Freqtrade 2026.7, `freqtradeorg/freqtrade:2026.7` → digest `sha256:da3428fd…a643` | `docker inspect` |
| Historical data | Dataset V2 (`research/datasets/dataset_v2.lock.json`), Development 2021-01-01 → 2024-12-31, `DATASET_LOCK_GATE = PASS` | ledger |

No identity field was changed. Deployment needs **no** strategy change: an
offline Freqtrade load of the pinned bytes reports `EmaCross … Status OK`, with
1 buy parameter and 1 sell parameter picked up from `EmaCross.json`.
Historically the engine was pinned by tag only; the paper package pins the
digest the tag currently resolves to, which is the same image FP-CONTROL-3
runs.

`H1_FROZEN_IDENTITY = PASS`

## C — HISTORICAL EVIDENCE AND LIMITATIONS

These figures are unchanged from Cycle-1 closure and are not reinterpreted.

| Measure | Value |
|---|---|
| Net return, 2021–2024 | +20.02% (76 trades, win rate 25%, max drawdown 5.18%, ~5.5% average capital exposure) |
| BTC full passive | +225.58% |
| Passive matched to realised exposure (approximation) | +12.31%, giving a recorded excess of +7.72 pp |
| Passive scaled to peak exposure (context) | +44.42% |
| Yearly slices | +8.25 / −5.30 / +9.80 / +7.12% |
| 8 parameter neighbours | all positive |
| Adverse-fee run | +18.51% |

Limitations that remain in force:
- no prospective evidence;
- trade-level reproduction is UNVERIFIED;
- full artifact equivalence is NOT_PROVEN;
- BTC/USDT only, one timeframe, long-only, no slippage model;
- no pristine holdout.

H1 is **not** historically dominant. It trails full passive by a wide margin
and trails the peak-exposure-scaled passive. Its only margin over passive
depends on an exposure approximation that ignores timing.

```text
H1_PROSPECTIVE_EDGE_PROVEN        = NO
H1_HISTORICAL_EDGE_INTERPRETATION = MODEST / UNCERTAIN BUT TESTABLE PROSPECTIVELY
                                    (excess over passive rests only on an approximate
                                    exposure-matched comparison; no timing-adjusted
                                    historical evidence exists)
```

## D — SELECTION DEBT

The known selection debt, all preserved:
- **Upstream 42-strategy benchmark.** EmaCross was that benchmark's winner (33
  of the 42 lost money).
- **Upstream 21-point parameter sweep.** It sits in the same selection history
  (`candidate_registry.json → multiple_testing_accounting`,
  `TOTAL_SELECTION_PROVENANCE = PARTIALLY_DOCUMENTED`).
- **Repeated examination of the Development window.** The historical run, CD1
  and the 13-run qualification campaign all used it.
- **Cycle-level family count.** Two families were tried and one survived.

None of these is claimed: DSR certification, PBO certification, an
independent 20-trial proof, or prospective edge.

Paper evidence will be **new** evidence. It does not erase any of this debt.

`H1_SELECTION_DEBT = MATERIAL`

## E — SCIENTIFIC PAPER-ADMISSION DECISION

**Question:** does the frozen H1 evidence justify collecting prospective
forward-paper evidence?

**Decision: `ADMIT_TO_ISOLATED_PAPER`.**

The basis is these five points together. Positive historical PnL alone was not
the reason:
1. **It survived preregistered screens.** H1 passed its frozen temporal,
   parameter and cost screens mechanically, with no reselection
   (`TRIAL-H1-QUAL-2`, `SURVIVED`).
2. **It makes testable, falsifiable predictions.** A deterministic, very simple
   mechanism makes candle-level predictions that a replay can check exactly
   (B1 fidelity). Its drawdown envelope and cost treatment can also be checked.
   A paper run can therefore *fail* it on grounds other than luck.
3. **Paper is the only unbiased test left.** There is no pristine historical
   holdout (`locked_oos.designated = false`, Validation is SPENT), so
   prospective data that did not exist at freeze time is the only remaining
   unbiased evidence source for this candidate.
4. **It adds information backtests cannot.** Paper exercises the live
   data path, dry-run order-book fills and multi-month operational continuity.
5. **The cost is bounded and the risk is nil.** The run is paper only, with no
   credential, and it is isolated from P2.

**The weakness, stated plainly.** At a cadence of about 19 trades a year, a
180-day window cannot settle edge (`PAPER_EXPECTED_INFORMATION_RATE: EDGE =
LOW`). What the cohort can establish is **behavior** and **operational
capability**. This is admitted as scientifically useful, not as a route to
proving edge. The Owner decides whether that information is worth the
opportunity cost.

ADMIT means only that H1 justifies a frozen prospective paper experiment. It
does **not** mean edge proven, production-ready, P3, controlled live or real
money.

`SCIENTIFIC_PAPER_ADMISSION = ADMIT`

## F — EVIDENCE DURABILITY

```text
PRIMARY_EVIDENCE_COPY        = VERIFIED  ~/Documents/TLOS-Evidence/trading-research/, 283 files
PRIMARY_CHECKSUM_MANIFEST    = PASS      CYCLE1_CLOSURE_SHA256SUMS.txt (sha256 7bc201d3…0bf9),
                                          sha256sum -c: every file OK, 2026-09-29
SECOND_DURABLE_EVIDENCE_COPY = MISSING
EVIDENCE_DURABILITY_GATE     = PARTIAL
```

The search looked only for an **existing, approved** second destination:
- `scripts/second_device_discovery.py` (the project's own tool) reports
  `status = UNAVAILABLE` and `SAME_HOST_SECOND_DEVICE = NO`. The host has one
  disk: Lexar NM620 256 GB, `/` on `nvme0n1p2`.
- No backup tool is configured: no rclone, restic or borg.
- The P3 draft `P3_EVIDENCE_DURABILITY_SPEC.md` marks the off-host destination
  **"NOT ESTABLISHED. Scope, destination and cost are D-1."** It is a
  provisional draft, not authority.
- `P2_CONTRACT.md` §8 places independent-host storage in P3 scope.

No platform was invented and nothing was provisioned. The scientific result is
unaffected. This is an **operational launch blocker**, and the Owner must
decide `SECOND_DURABLE_EVIDENCE_LOCATION`.

## G — LICENSING / CODE MATERIALIZATION

Upstream is GPL-3.0 (LICENSE sha256 `3972dc97…6986`, pinned).
`upstream_pins.json` policy: *"No upstream source is committed to this
repository … vendoring_authorised: false."*

The existing compliant path is `research/external/pin_upstream.py --verify
--materialize <dir>`. It fetches the pinned blobs from `raw.githubusercontent.com`,
refuses any byte that does not match its sha256, refuses to run with
credential-shaped environment variables, and writes into a throwaway workspace
outside git. The package's launch procedure copies exactly `EmaCross.py`,
`EmaCross.json` **and `LICENSE`** into the runtime strategy directory, so the
licence notice travels with the deployed copy. Preflight enforces exactly those
three files and their hashes.

Nothing is committed, relicensed or modified. Use is private, with no
redistribution. A test asserts that no `EmaCross.py` or `EmaCross.json` is
tracked in git. The path was exercised end to end in the scratchpad:
`UPSTREAM_PIN_GATE = PASS`, `ISOLATION_GATE = PASS`, and the three hashes
matched.

```text
H1_CODE_MATERIALIZATION = HASH_PINNED_EXTERNAL_SOURCE
LICENSING_GATE          = PASS
```

## H — PAPER COHORT PACKAGE

`research/paper/h1/package/`, bound by `PACKAGE_MANIFEST.sha256`:

| File | Role |
|---|---|
| `cohort.json` | frozen cohort identity: `H1-PAPER-COHORT-1`; strategy, params, config and engine digests; sizing; paper mode; T0 semantics (`null`); container paths; resource limits; forbidden identity reuse |
| `config.h1-paper.json` | Freqtrade config (sha256 `8c780507…1db`). It equals `config.paper.json.example` except for the BTC/USDT-only whitelist and the bot name. `dry_run = true`, empty key/secret, `force_entry_enable = false`, paper_guard PASS. |
| `docker-compose.h1-paper.yml` | standalone project `tlos-h1-paper-cohort-1`; digest-pinned image; own container, network and port; resource caps; read-only config and strategy mounts; one writable lane |
| `PREREGISTRATION.md` | prospective question, benchmark contract, terminal law, freeze law, incident and recovery law, placement, T0 and launch binding |
| `incident.schema.json` | incident payload schema (11 types; restart counter; host bindings; terminal state) |
| `h1_paper.py` | `verify` (static), `preflight` (launch-time host bindings; starts nothing), `incident` (append to the hash-chained ledger via `research/fp/ledger.py`) |

The package reuses existing machinery: `paper_guard`, `pin_upstream`, the
`fp/ledger` hash chain, `summarize_backtest`'s exposure formula, and
Freqtrade's own dry-run DB and logs. There is no new engine, database, control
plane or capture service. The P2 capture loop is keyed to P2 registry roles;
adding H1 to that registry would be a P2 mutation, so it was not reused.

**The one honest gap.** There is no as-seen market-input ledger. The
benchmarks and the B1 replay are computed after the terminal event from Binance
public candles, not from candles captured live.

```text
PAPER_COHORT_ID               = H1-PAPER-COHORT-1
PAPER_PACKAGE_VERSION         = H1-PAPER-COHORT-PACKAGE-1 v1.0.0
PAPER_PACKAGE_MANIFEST_SHA256 = ef9a3d0c5b5b9abe122faaa1bd4ef67feb0c3ec4437bed56cd6ef33d910bc43c
PAPER_COHORT_DESIGN           = PASS
```

## I — P2 ISOLATION

Separate identities: compose project `tlos-h1-paper-cohort-1`, container
`tlos-h1-paper-cohort-1-freqtrade`, network `tlos-h1-paper-cohort-1-net`, bot
`h1-paper-cohort-1`, and API port `127.0.0.1:8181`. FP-CONTROL-3 publishes
8080, 3000, 9090, 9108 and 5000.

The DB, logs, evidence and incident ledger live only in the H1 lane. `verify`
refuses any mount source containing `fp-control`, `trading_lab_os_final` or
`freqtrade/user_data`. `preflight` refuses a lane or strategy directory that is
inside any git worktree or on any P2 path, and refuses a non-empty lane.

H1 appears nowhere in P2's records:
- not in the cohort registry;
- not in `paper_candidate_admission.json`, which stays `BLOCKED` and
  byte-identical, as the scope audit enforces.

The FP-CONTROL-3 identities are listed in `forbidden_identity_reuse`. Tests
prove that a P2 mount, a P2 port, an exchange override, a second pair, a
dropped memory cap and a T0 are each refused.

`P2_ISOLATION_DESIGN = PASS`

## J — HOST / RESOURCE / NETWORK PLACEMENT

- **Separate host.** No separate persistent host exists or is authorized.
  GitHub Actions runners are ephemeral and are not a paper host.
- **Same host now.** The host has 16 CPUs, 30 GiB RAM and 142 GB free.
  FP-CONTROL-3 currently uses about 1.4% CPU and about 3.2 GiB. It runs with no
  resource limits and has been running since 2026-09-28T15:28Z with 0 restarts.
- **Caps.** H1 is capped at 1 CPU and 1 GiB, with `cpu_shares` 256 against P2's
  1024 and `oom_score_adj` 500 so H1 is killed first under memory pressure.
  Docker logs are capped, the lane has a 2 GB budget, and preflight requires at
  least 20 GB free.
- **Network.** CPU and memory contention is negligible. The real residual risks
  are shared ones:
  - Binance request weight is counted **per egress IP**, which both runtimes
    would share;
  - a **shared DNS resolver** (the host has prior DNS incidents);
  - a **shared Docker daemon and disk**;
  - ambiguous attribution of simultaneous incidents between the two cohorts.

  H1's load is one pair on 1h: small, but not zero.
- **Waiting is cheap.** FP-CONTROL-3's hard cap is **2026-10-24T12:01:14Z**, at
  most about 25 days away, against a 180-day H1 window.

```text
RECOMMENDED_PAPER_LOCATION = WAIT_FOR_P2_CLOSURE
(technically supported alternative: ISOLATED_SAME_HOST_AFTER_OWNER_APPROVAL)
```

## K — PROSPECTIVE QUESTION

The question is in `PREREGISTRATION.md` §2: does the frozen identity, running
forward on post-freeze data, behave as its specification and historical profile
say, and can the project operate it continuously and verifiably, all without
intervention?

It covers signal fidelity, completed lifecycles, realised frequency and
exposure against the historical profile, drawdown envelope, costs, benchmark
context and operational continuity. **EDGE_EVIDENCE** (descriptive only) is kept
separate from **PROSPECTIVE_BEHAVIOR** and **OPERATIONAL_CAPABILITY**.

## L — BENCHMARK CONTRACT

The contract is `PREREGISTRATION.md` §4, frozen before T0:
- `CASH` (exact);
- `BTC_PASSIVE_FULL` (exact, 0.1% per side);
- `BTC_PASSIVE_REALISED_EXPOSURE_MATCHED` (labelled **APPROXIMATE**; same
  formula as `summarize_backtest.py`);
- `BTC_PASSIVE_TIMING_MATCHED` (exact for timing).

Realised exposure is reported both as time in position and as average capital
exposure. The fee is the dry-run fill fee of 0.1% per side. Slippage and
latency are not modelled, and the difference between order-book fills and
candle-open fills is reported rather than corrected. No benchmark may change
after T0.

`PAPER_BENCHMARK_CONTRACT = PASS`

## M — TERMINAL / INCIDENT LAW

**Terminal law** (`PREREGISTRATION.md` §5):
- **Window.** `MAX_CALENDAR_DURATION` = 180 days from `ACTIVATION_UTC`,
  fixed-horizon, with no automatic extension and no early stop on performance.
  The only early stops are a safety breach, an Owner stop, or P2 protection.
- **No forced exits.** An open position at the end is recorded as open.
- **Why 180 days.** It was chosen from cadence alone, not to make H1 pass:
  - 180 days: an expected 6.4, 9.4 or 11.3 lifecycles at the lowest, mean and
    highest historical rate; P(fewer than 4) is 0.12 at the lowest rate and
    0.02 at the mean;
  - 90 days: P(fewer than 4) is 0.60 at the lowest rate and 0.31 at the mean.
- **Behavior criteria.**
  - B1: candle-level signal fidelity against a replay;
  - B2: at least 4 completed lifecycles;
  - B3: maximum drawdown below 15%;
  - B4: every fill at 0.1% fee;
  - B5: at least 80% of candles processed.
- **Behavior outcome.** If B1, B3 or B4 fails, the outcome is `NOT_SUPPORTED`.
  If only B2 or B5 fails, it is `INCONCLUSIVE_INSUFFICIENT_EVIDENCE`. If all
  pass, it is `SUPPORTED`.
- **Operational outcome.** `OPERATIONAL_CAPABILITY` is
  PROVEN, NOT_PROVEN or INCONCLUSIVE, under its own separate criteria.

`PAPER_TERMINAL_LAW = PASS`

**Incident and recovery law** (§7, `incident.schema.json`, `h1_paper.py
incident`):
- The ledger is hash-chained under `CANONICAL_LEDGER_V1`.
- `COHORT_START` is first, and its time **is** PAPER_T0.
- `restart_counter` is derived by the tool and never reset.
- Nothing may follow `COHORT_TERMINAL`.
- There is a defined handling for each of: restart, missed candle, market-data
  failure, DNS/network failure, API unreachable, resource pressure,
  reconciliation, and safety breach.
- Missed signals are never executed after the fact.
- A recovered process continues the same cohort, and only from the identical
  package digest.

`PAPER_INCIDENT_CONTRACT = PASS`

## N — STATIC PACKAGE VALIDATION

All of these are non-trading and no worker was started:

| Check | Result |
|---|---|
| `h1_paper.py verify`: manifest, identity against pins, paper_guard, template equality, compose isolation, resource caps, P2 registry separation, incident schema | PASS |
| `paper_guard.py --config config.h1-paper.json` | PAPER_GUARD_PASS |
| `docker compose -f docker-compose.h1-paper.yml config --quiet` (render only) | PASS |
| `pin_upstream.py --verify --materialize` (credential-free environment, scratchpad) | `UPSTREAM_PIN_GATE = PASS`, `ISOLATION_GATE = PASS`, 3 hashes match |
| `h1_paper.py preflight` against the recommended lane path (read-only; nothing created) | PASS |
| Offline Freqtrade `list-strategies` (`--network none`, digest-pinned image) | `EmaCross … OK`, 1 buy / 1 sell param |
| Offline Freqtrade `show-config` | `dry_run: true`, BTC/USDT only, stake 10, wallet 100, fee 0.001, spot |
| `tests/test_h1_paper_package.py` | 17 passed |
| full local suite | 1137 passed, 8 skipped |

`STATIC_PACKAGE_VALIDATION = PASS`

## O — LAUNCH READINESS

```text
SCIENTIFIC_PAPER_ADMISSION = ADMIT
PAPER_PACKAGE_STATUS       = READY    (frozen, verified, digest ef9a3d0c…c43c)
PAPER_LAUNCH_READY         = NO
```

There are two named operational blockers. Neither is scientific.
1. `SECOND_DURABLE_EVIDENCE_COPY = MISSING` (§F).
2. Placement: FP-CONTROL-3 is active until at most 2026-10-24T12:01:14Z. The
   recommendation is `WAIT_FOR_P2_CLOSURE` (§J).

## P — OWNER DECISIONS REQUIRED

1. **`SECOND_DURABLE_EVIDENCE_LOCATION`**: name an approved second destination
   for evidence (and for the future H1 lane).
2. **Placement**: accept `WAIT_FOR_P2_CLOSURE` (recommended), or explicitly
   approve `ISOLATED_SAME_HOST` while P2 runs.
3. Then `AUTHORIZE_PAPER_LAUNCH` or `DO_NOT_LAUNCH`, naming package digest
   `ef9a3d0c5b5b9abe122faaa1bd4ef67feb0c3ec4437bed56cd6ef33d910bc43c`. Any byte
   change voids that authorization.

## Q — ONE NEXT ACTION

Resolve only the named operational blockers: the Owner names an approved second
durable evidence location and confirms placement. H1 research is not reopened.

---

## Final status block

```text
RESEARCH_CYCLE1_MERGED                  = YES
RESEARCH_CYCLE1_COMPLETE                = YES
H1_PAPER_ADMISSION_AND_LAUNCH_PACKAGE_1 = PARTIAL

H1_FROZEN_IDENTITY                      = PASS
H1_HISTORICAL_QUALIFICATION             = PASS
H1_SELECTION_DEBT                       = MATERIAL
H1_PROSPECTIVE_EDGE_PROVEN              = NO
H1_HISTORICAL_EDGE_INTERPRETATION       = MODEST / UNCERTAIN BUT TESTABLE PROSPECTIVELY

SCIENTIFIC_PAPER_ADMISSION              = ADMIT

PRIMARY_EVIDENCE_COPY                   = VERIFIED
PRIMARY_CHECKSUM_MANIFEST               = PASS
SECOND_DURABLE_EVIDENCE_COPY            = MISSING
EVIDENCE_DURABILITY_GATE                = PARTIAL

H1_CODE_MATERIALIZATION                 = HASH_PINNED_EXTERNAL_SOURCE
LICENSING_GATE                          = PASS

PAPER_COHORT_ID                         = H1-PAPER-COHORT-1
PAPER_PACKAGE_VERSION                   = H1-PAPER-COHORT-PACKAGE-1 v1.0.0
PAPER_PACKAGE_MANIFEST_SHA256           = ef9a3d0c5b5b9abe122faaa1bd4ef67feb0c3ec4437bed56cd6ef33d910bc43c
PAPER_COHORT_DESIGN                     = PASS
PAPER_TERMINAL_LAW                      = PASS
PAPER_BENCHMARK_CONTRACT                = PASS
PAPER_INCIDENT_CONTRACT                 = PASS

RECOMMENDED_PAPER_LOCATION              = WAIT_FOR_P2_CLOSURE
P2_ISOLATION_DESIGN                     = PASS
STATIC_PACKAGE_VALIDATION               = PASS

PAPER_PACKAGE_STATUS                    = READY
PAPER_LAUNCH_READY                      = NO

PAPER_WORKER_STARTED                    = NO
PAPER_T0_SET                            = NO
FP_CONTROL_3_TOUCHED                    = NO
P2_RUNTIME_MUTATED                      = NO
P3_STARTED                              = NO
REAL_MONEY_AUTHORIZED                   = NO

OWNER_DECISION_REQUIRED                 = SECOND_DURABLE_EVIDENCE_LOCATION + PLACEMENT (then AUTHORIZE_PAPER_LAUNCH / DO_NOT_LAUNCH)
ONE_NEXT_ACTION                         = resolve only the named operational blockers (second durable evidence location; placement), without reopening H1 research
```

**STOP.** The H1 paper worker is not launched.
