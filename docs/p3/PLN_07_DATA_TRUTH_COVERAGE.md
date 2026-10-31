# P3-PLN-07 — Data-truth coverage (master plan §13; contract §4)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-07 (frozen at fcd06b21), executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1).
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO

**What the contract requires.**
- PLN-07 remaining deliverable: "Data-truth checks (§13)".
- PLN-07 acceptance: "**The data-truth checks pass**".
- §4 cross-cutting law: "no silent dataset replacement. Missing and duplicate candles are recorded, never filled."
- §2 priority 3 limits the scope to "the markets the frozen configuration uses (Binance spot BTC/USDT and
  ETH/USDT, 1h)". Adding markets is not P3 scope.

**What §13 lists** (master plan §13, the "data-truth contract"): point-in-time universe, inactive pairs, delisted
pairs, survivorship bias, missing candles, duplicate candles, timezone consistency, partial datasets, silent
redownload, mixed data versions, symbol changes, funding timestamp alignment, mark-price alignment, cache
contamination. "Data truth must be explicit and reproducible. Silent dataset replacement is prohibited."

```text
PLN-07 DATA-TRUTH CHECKS (§13)   = PARTIAL
  repository controls             12 of 14 items have at least one tested control (2 only partly: symbol changes,
                                  and redownload/cache on the engine feed)
  not applicable to frozen spot   2 (funding timestamps, mark price)
  named gaps                      G-1, G-2, G-4 have a repository control and synthetic tests (§3, §7);
                                  G-3 needs an Owner/design decision (§8); G-5 research-only
  host-side checks                NOT_RUN in P3 (§4)
PLN-07 overall                   PARTIAL — the failure/recovery matrix is PASS (PLN_04_RECOVERY.md);
                                 the data-truth leg is not complete
```

## 1. The data paths in P3 scope
| Path | Code | Role |
|---|---|---|
| **L — live public klines** | `research/fp/market.py` (REST `/api/v3/klines`, two public hosts), consumed by `research/fp/capture.py` | The as-seen input of a forward-paper capture loop. The path a governed paper cohort records as evidence |
| **F — Freqtrade's own dry-run feed** | inside the pinned Freqtrade image | What the paper runtime trades on. It is not repository code. Its agreement with L is what `reconcile.py` `event_time_replay` and F-2/F-4 check after the fact |
| **D — frozen research datasets** | `scripts/audit_data.py`, `scripts/fetch_binance_public_data.py`, `research/datasets/*.lock.json` | Backtest and research data. The files are not in Git; the locks are |
| *R — research-only extensions* | `research/auth2/universe.py`, `scripts/fetch_binance_funding.py`, `research/auth2q2/harness.py` | Multi-symbol and funding research, under separate research authority. Listed because they own §13 items, not because P3 runs them |

## 2. Coverage matrix
Evidence classes:
- **CLAUDE-VERIFIED** means Claude ran the named tests and saw them pass, at the commit stated in §5.
- **host-only NOT_RUN** means only a check on `hamza-workstation` against real data can show it, and it has not been run in P3.
- **NOT_COVERED** means no repository control exists.
- **N/A** means the item does not arise for the frozen spot configuration.

| §13 item | Control (path) | Test(s) | Evidence class |
|---|---|---|---|
| **Point-in-time universe** | L/F: a static two-pair universe, `StaticPairList` with `pair_whitelist` [BTC/USDT, ETH/USDT] in `config.paper.json.example`, fixed ex ante; no runtime selection. `paper_guard.py` forces a non-empty spot-only list. R: `universe.py` point-in-time selection law | `test_paper_guard` (empty, derivative and leveraged lists refused); `test_auth2_gates::test_delisting_convention_and_data_limited_law` (R constants only) | CLAUDE-VERIFIED for the guard. **G-4 (§7):** `test_p3_data_truth_audits::test_the_shipped_paper_config_trades_only_the_frozen_spot_universe`, `::test_the_frozen_strategy_is_long_only_on_the_frozen_timeframe`, `::test_the_registry_froze_this_config_this_strategy_and_this_universe`, `::test_the_overlay_runs_the_frozen_strategy_and_captures_exactly_the_frozen_universe` — CLAUDE-VERIFIED (local) |
| **Inactive pairs** | L: a pair that returns no rows or an error raises `MarketError` (never an empty success), and the loop records `market_fetch_failed` | `test_p3_data_truth::test_no_usable_host_raises_instead_of_returning_no_candles`, `…::test_a_missed_bar_is_an_incident_and_is_never_backfilled` | CLAUDE-VERIFIED (new in this PR) |
| **Delisted pairs** | L: as for inactive pairs (Binance answers `-1121 Invalid symbol`, which is refused). R: listing segments and the delisting haircut in `universe.py` | `test_p3_data_truth::test_no_usable_host_raises…[answers1]`; `test_auth2_gates::test_delisting_convention…`, `::test_terminal_price_trust_rule` | CLAUDE-VERIFIED |
| **Survivorship bias** | Not a property of a fixed two-pair paper runtime: no universe is selected from survivors at run time. R: `universe.py` delisting convention | `test_auth2_gates` (R) | CLAUDE-VERIFIED for R; not applicable to the P3 runtime beyond G-4 |
| **Missing candles** | D: `audit_data.py` gap detection and clusters. L: a fetch failure becomes an incident, and the missed bar is never synthesised; the capture loop never backfills | `test_data_audit::test_gap_is_detected`, `::test_gap_clusters_group_contiguous_holes`, `::test_a_gap_is_a_continuity_finding_not_a_structural_one`; `test_p3_data_truth::test_a_missed_bar_is_an_incident_and_is_never_backfilled` | CLAUDE-VERIFIED. **G-1 (§7):** `research/p3/data_truth.audit_input_ledger` (CLI `scripts/p3/data_truth.py ledger-bars`) — 18 synthetic tests in `test_p3_data_truth_audits`, plus 2 CLI tests shared with G-2 — CLAUDE-VERIFIED (local). On a real cohort ledger: host-only NOT_RUN |
| **Duplicate candles** | D: duplicate timestamps fail the audit. L: one identity per (pair, timeframe, open time); a re-fetched or repeated candle is written once; `reconcile.py` `input_uniqueness` | `test_data_audit::test_duplicate_timestamp_is_detected`; `test_fp_capture::test_refetching_the_same_candles_appends_nothing`, `::test_duplicate_input_survives_a_fresh_process`; `test_p3_data_truth::test_a_candle_served_twice_in_one_response_is_written_once`, `::test_the_market_event_identity_is_pair_timeframe_and_open_time_only` | CLAUDE-VERIFIED |
| **Timezone consistency** | Integer UTC milliseconds throughout. D: off-grid timestamps fail; ms normalisation. L: UTC rendering, a clock-skew stop at one candle period, and `receive_ts ≥ source_ts`. Host: `health.clock_sync` (NTP) | `test_data_audit::test_off_grid_timestamp_is_detected`; `test_fetch_binance_public_data::test_timestamps_are_normalised_to_milliseconds`; `test_fp_capture::test_receive_before_source_is_rejected`; `test_p3_data_truth::test_timestamps_render_as_utc`, `::test_clock_skew_tolerance_is_one_candle_period_and_symmetric`; `test_p3_health_s19::test_clock_sync_is_info_only_when_ntp_says_yes` | CLAUDE-VERIFIED for the code; the host's NTP state is host-only NOT_RUN in P3 |
| **Partial datasets** | D: coverage assertions; a partial live candle in a dataset is rejected. L: the still-forming candle is dropped, and a candle closing exactly at receipt counts as forming; one malformed row fails the whole response | `test_data_audit::test_coverage_assertions_flag_a_short_dataset`, `::test_a_partial_live_candle_is_rejected`; `test_p3_data_truth::test_the_forming_candle_is_dropped…`, `::test_a_candle_that_closes_exactly_at_receipt_is_still_forming`, `::test_one_malformed_row_fails_the_whole_response…` | CLAUDE-VERIFIED |
| **Silent redownload** | D: dataset locks (raw and canonical digests); `--lock` fails on content drift; downloads verify Binance's published checksums | `test_data_audit::test_dataset_lock_reports_content_drift_as_a_failure`, `::test_lock_gate_still_fails_when_the_content_drifts`, `::test_committed_dataset_lock_matches_the_recorded_audit`; `test_fetch_binance_public_data::test_a_bad_checksum_aborts_rather_than_using_the_data` | CLAUDE-VERIFIED for D. **G-3 (§8):** F's feed has no repository lock; Owner/design decision |
| **Mixed data versions** | D: a versioned canonical digest; V1 lock untouched by V2; a serialisation change is a note, not a pass on content. L: every input record carries `source_id` and `source_host` | `test_data_audit::test_canonical_digest_is_order_independent_and_versioned`, `::test_dataset_v1_lock_is_untouched_by_dataset_v2`, `::test_serialization_difference_is_a_note_not_a_failure`; `test_p3_data_truth::test_the_fallback_host_serves_and_is_named_in_every_candle` | CLAUDE-VERIFIED |
| **Symbol changes** | L: a renamed symbol answers `Invalid symbol` and is refused (as for delisted pairs). R: `universe.py` splits a reused ticker into listing segments | `test_p3_data_truth::test_no_usable_host_raises…[answers1]` | Partly CLAUDE-VERIFIED. **G-5:** `universe.segments` (ticker reuse) has no unit test; it is research-only |
| **Funding timestamp alignment** | R: `fetch_binance_funding.py` integrity (off-grid, duplicate, missing settlement, API equivalence) | `test_fetch_binance_funding` (23 tests) | **N/A** to frozen spot; R CLAUDE-VERIFIED |
| **Mark-price alignment** | none | none | **N/A** to frozen spot (no mark price in spot); NOT_COVERED if a derivative market were ever authorized |
| **Cache contamination** | L reads live REST with no cache. D: lock re-check. R: `auth2q2` snapshot-cache law. Backups exclude derived caches | `test_auth2q2_harness::test_a_broken_cache_is_discarded…`, `::test_a_cache_holding_another_snapshot_is_not_this_one`; `test_p3_backup` (derived excluded) | CLAUDE-VERIFIED for R and L. **G-3 (§8)** applies to F's own data cache |
| *L-vs-F bar equality* (supports silent redownload, cache contamination, mixed versions) | **G-2 (§7):** `research/p3/data_truth.compare_feeds` (CLI `scripts/p3/data_truth.py feed-compare`), exact per-bar OHLCV equality over two recorded sequences | `test_p3_data_truth_audits` (12 G-2 tests) | CLAUDE-VERIFIED (local) for the comparator. Real L-vs-F: host-only NOT_RUN, and the engine-side recording is the §8 decision |
| *§4 "no silent dataset replacement"* | D: dataset locks, as for silent redownload | as for silent redownload | CLAUDE-VERIFIED |
| *§4 "recorded, never filled"* | L: an incident on a missed fetch; the loop has no fill path; `input_rejected` on out-of-order input | `test_p3_data_truth::test_a_missed_bar_is_an_incident…`; `test_fp_capture::test_out_of_order_candle_becomes_an_incident_not_a_silent_drop` | CLAUDE-VERIFIED |
| *Structural truth of a received candle* (supports all rows) | L: OHLC consistency, non-negative volume, a complete row, parseable values; refused, never repaired. D: the same in `audit_data.py`, plus NaN | `test_p3_data_truth::test_a_malformed_kline_is_refused_not_repaired` (5 cases); `test_data_audit::test_invalid_ohlc_is_detected`, `::test_nan_and_nonpositive_prices_are_detected`, `::test_negative_volume_is_detected`, `::test_reconciliation_catches_a_corrupted_hourly_bar` (5m→1h) | CLAUDE-VERIFIED |

## 3. Named gaps
Status after the round-3 staging change (§7): G-1, G-2 and G-4 have repository controls with synthetic tests.
None of them is evidence about a real cohort; that stays host-only (§4).

| Gap | What is missing | Where it belongs |
|---|---|---|
| **G-1** | An automated missing-bar audit over a captured input ledger. It should list the missing bars per pair against the expected 1h grid and classify them against `market_fetch_failed`, restart and host-down records. P2 did this by hand. `audit_data.gap_clusters` is reusable for it (REUSE_EXISTING), but the wiring is new code | PLN-07 (with the PLN-06 F-1 "lane signal history gap control"). **Control added (§7)**; real-ledger run host-only |
| **G-2** | Captured-input vs. runtime-feed equality per bar: an L-vs-F candle comparison for the same bar. Today, agreement is inferred through `event_time_replay` and the F-2/F-4 audit | PLN-07. **Comparator added (§7)**; the engine-side recording is the §8 decision |
| **G-3** | Freqtrade's own data path (F) has no lock and no cache control from this repository. It is inside the pinned engine image | Accepted as engine behaviour, or covered by G-2. **Owner/design decision (§8)** |
| **G-4** | A test that pins the shipped paper config to `StaticPairList` with exactly BTC/USDT and ETH/USDT, the frozen universe | PLN-07. **Pin added (§7)**: it asserts the frozen configuration and changes nothing |
| **G-5** | Unit tests for `universe.segments` (ticker reuse). Research-only | Research lane, not P3 |

## 4. Host-side data-truth checks (NOT_RUN in P3)
| Check | Why it is host-only | Status |
|---|---|---|
| `audit_data.py --lock` on the frozen dataset files | The files are not in Git (CLAUDE.md "Historical dataset evidence") | Historical `DATA_INTEGRITY_GATE = PASS` from an earlier host. **NOT_RUN in P3** |
| A missing-bar audit of a real P3 paper cohort's input ledger | No P3 paper cohort has run (`PAPER_LAUNCH_AUTHORIZED = NO`). The tool now exists: `scripts/p3/data_truth.py ledger-bars --evidence-dir <lane>/evidence --pair BTC/USDT --pair ETH/USDT --timeframe 1h --start <window start> --end <window end>` | NOT_RUN |
| NTP state (`health.clock_sync`) | Host state | Runs hourly in the host health timer. Not read for this record |
| L-vs-F agreement on real bars | Needs a running paper runtime and a recording of F's bars (§8 decision); then `scripts/p3/data_truth.py feed-compare` | NOT_RUN |

## 5. What this PR adds
- `tests/test_p3_data_truth.py`, 16 tests, synthetic and offline. They exercise the existing validators of the live
  path, `research/fp/market.py`, which the capture tests had always replaced with a stub. They cover:
  - malformed klines are refused, not repaired;
  - the forming candle is dropped;
  - the fallback host is identified in every candle;
  - no usable host is an error, never an empty success;
  - market-event identity;
  - UTC rendering and the clock-skew bound;
  - on the capture loop, a missed bar is an incident and is never backfilled, and a repeated candle is written once.

  No production code changed. No market data was manufactured beyond the rows each test builds. No validator was
  weakened.
- Test runs, CLAUDE-VERIFIED in the cloud environment:
  - the existing suites in §2 were run at the branch base `b1eef7d` (code identical to main `f584cd43` for every file named),
    all passing: `test_data_audit` 37, `test_fetch_binance_public_data` 17, `test_fetch_binance_funding` 23,
    `test_fp_capture` 45, `test_fp_preflight` 29, `test_p3_health_s19` 42, `test_paper_guard` 55, `test_auth2_gates` 10,
    `test_auth2q2_harness` 54, `test_p3_backup` 13;
  - the new file was run at this PR's head.

  The PR body records the counts and the head SHA.

## 6. Status
```text
PLN-07 data-truth checks (§13)   PARTIAL
  covered and passing            point-in-time universe (guard only), inactive, delisted, missing, duplicate,
                                 timezone (code), partial, silent redownload (datasets), mixed versions,
                                 cache (live path and research), and the §4 "recorded, never filled" rule
  N/A to frozen spot             funding timestamps, mark price
  repository control, synthetic  G-1 captured-ledger gap audit · G-2 L-vs-F bar comparator · G-4 frozen-universe
                                 config pin (§7; CLAUDE-VERIFIED locally, not GitHub CI)
  open                           G-3 engine feed lock/cache (Owner/design decision, §8) · (G-5 research-only)
  host-only                      dataset lock audit, real-cohort gap audit, NTP, L-vs-F on real bars: NOT_RUN
```
PLN-07 acceptance is **not** claimed. The acceptance is "the data-truth checks pass". That needs the §4 host-side
checks run on real data with these tools, and the §8 decisions; a repository control on synthetic fixtures is not
a data-truth check that passed.

## 7. Round-3 additions: G-1, G-2, G-4 (staging branch `staging/r3-pln-07-data-truth`)
Reuse classification: **BUILD_SMALL_MISSING_LAYER** over REUSE_EXISTING parts. `research/p3/data_truth.py` reads
through `fp.ledger` (chain verification included), takes the market-event identity and timeframe table from
`fp.market`, the live candles from `fp.replay.candles_from_input_ledger`, and gap clustering / UTC parsing from
`audit_data`. `research/fp` (the frozen runtime tree) is not changed; `scripts/p3/` is outside `RUNTIME_TREE`.
Both audits are read-only, always emit their full findings law, and treat UNPROVEN as blocking.

| Gap | Control | Findings (all always emitted) | Fail-closed behaviour |
|---|---|---|---|
| **G-1** | `audit_input_ledger(evidence_dir, pairs, timeframe, start_ms, end_ms)` | `ledger_readable`, `ledger_chain_integrity`, `record_shape`, `timeframe_conformance`, `universe_conformance`, `bar_alignment`, `bar_ordering`, `bar_uniqueness`, `missing_bars` | unreadable / absent / empty ledger → UNPROVEN; broken chain → FAIL; a frozen pair with no bar → UNPROVEN; a missing bar with no incident inside its capture opportunity → FAIL |
| **G-2** | `compare_feeds(live_rows, engine_rows, pair, timeframe, start_ms, end_ms)` | `rows_readable`, `bar_alignment`, `bar_uniqueness`, `bar_coverage`, `value_equality` | exact equality (the contract states no tolerance); a bar on one side only, in either direction, → FAIL; conflicting copies → FAIL; unreadable row → UNPROVEN; nothing to compare → UNPROVEN |
| **G-4** | four assertions in `test_p3_data_truth_audits` | config: `dry_run` true, `trading_mode` spot, no margin mode, `binance`, empty key/secret, `pairlists == [StaticPairList]`, `pair_whitelist == [BTC/USDT, ETH/USDT]`, no leverage/short/futures key, no `:` pair · strategy `BaselineEmaRegimeV1`: `timeframe = "1h"`, `can_short = False` · every FP-CONTROL registry row: same pairs, timeframe, `config_sha256` = sha256 of the shipped example (`d1d078c6…`), `strategy_sha256` (`8c0bc6c5…`) · overlay: engine `--strategy BaselineEmaRegimeV1` with no timeframe override; capture `--pair` exactly the two frozen pairs, `--timeframe=1h` | asserts only; no configuration was changed. The repository and the registry agree; no disagreement was found |

G-1 missing-bar classes, the ones the P2 closure audit applied by hand (P2_CLOSURE §4), in precedence order:
`EXPLAINED_INPUT_REJECTED` (an `input_rejected` incident names the bar's market event), `EXPLAINED_FETCH_FAILURE`
(a `market_fetch_failed` for that pair, or with no pair, inside the bar's opportunity),
`EXPLAINED_DOWNTIME_THEN_RESTART` (a `run_started` inside it), else `UNEXPLAINED`. A bar's opportunity runs from its
close to the receipt of the next bar captured for that pair, because the loop never writes an older bar after a
newer one. An incident with no readable time explains nothing. Contract §4 makes a recorded miss compliant and an
unrecorded one a finding, so `UNEXPLAINED` is FAIL. In P2 the 74 unexplained bar-hours were host-down intervals
consistent with power loss, which no in-lane record can explain; whether such bars are an accepted residual is the
§8 decision, not a tolerance in the tool.

Each control is shown failing on its own defect (duplicate, out-of-order, off-grid, foreign pair, foreign
timeframe, tampered chain, unexplained gap, an incident outside the opportunity, a 1e-9 volume difference, a bar on
one side only). Two mutations were run by hand and caught: removing the opportunity bound
(`test_an_incident_outside_the_bars_opportunity_explains_nothing` fails) and introducing a 1e-6 tolerance
(`test_a_value_difference_is_a_finding_however_small` fails). The H1 package config
(`research/paper/h1/package/config.h1-paper.json`, BTC/USDT only) is under separate H1 authority and is not the P3
paper config; it is not asserted here.

## 8. Decisions this record cannot make (Owner)
- **G-3, engine feed lock/cache.** The contract (§13 "silent redownload", "cache contamination"; PLN-07 "the
  data-truth checks pass") names no engine-feed lock. Repository facts: the FP overlay mounts `user_data`
  read-only for the engine except its own lane (`check_fp_overlay`), so F cannot persist a data cache into the
  repository's data directory; in dry-run trade mode Freqtrade keeps its candles in process memory [engine
  behaviour, inference; Freqtrade is not installed in this environment]. There is therefore no on-disk F cache to
  hash against a lock manifest. Options: (a) accept F's feed as engine behaviour and rely on G-2 against a
  recording of F's bars; (b) record F's bars per cycle through the read-only Freqtrade API into a separate
  host-side file (new recorder: design decision, and it must not write into the evidence lane); (c) record
  nothing and keep L-vs-F agreement inferred through `event_time_replay` and F-2/F-4, as today.
- **G-1 unexplained host-down gaps.** Whether bars missed during an unclean host-down interval (no in-lane record
  possible) are an accepted residual for PLN-10, or must be explained by an out-of-lane host record
  (`health`/journal), is an Owner decision. The tool reports them as FAIL until then.
- **G-2 tolerance.** None is stated; the comparator is exact. Any tolerance (for example on volume of the last bar
  read near its close) needs an explicit Owner decision recorded in the contract chain, not a tool default.
- **Host-side runs.** The §4 checks need the Owner's host and a paper cohort (`PAPER_LAUNCH_AUTHORIZED = NO`).
