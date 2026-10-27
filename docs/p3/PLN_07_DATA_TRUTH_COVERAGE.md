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
  repository controls             12 of 14 items have at least one tested control (3 only partly: point-in-time
                                  universe, symbol changes, and redownload/cache on the engine feed)
  not applicable to frozen spot   2 (funding timestamps, mark price)
  named gaps                      G-1 … G-5 (§3)
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
| **Point-in-time universe** | L/F: a static two-pair universe, `StaticPairList` with `pair_whitelist` [BTC/USDT, ETH/USDT] in `config.paper.json.example`, fixed ex ante; no runtime selection. `paper_guard.py` forces a non-empty spot-only list. R: `universe.py` point-in-time selection law | `test_paper_guard` (empty, derivative and leveraged lists refused); `test_auth2_gates::test_delisting_convention_and_data_limited_law` (R constants only) | CLAUDE-VERIFIED for the guard. **G-4:** no test pins the paper config to exactly the frozen two pairs and `StaticPairList` |
| **Inactive pairs** | L: a pair that returns no rows or an error raises `MarketError` (never an empty success), and the loop records `market_fetch_failed` | `test_p3_data_truth::test_no_usable_host_raises_instead_of_returning_no_candles`, `…::test_a_missed_bar_is_an_incident_and_is_never_backfilled` | CLAUDE-VERIFIED (new in this PR) |
| **Delisted pairs** | L: as for inactive pairs (Binance answers `-1121 Invalid symbol`, which is refused). R: listing segments and the delisting haircut in `universe.py` | `test_p3_data_truth::test_no_usable_host_raises…[answers1]`; `test_auth2_gates::test_delisting_convention…`, `::test_terminal_price_trust_rule` | CLAUDE-VERIFIED |
| **Survivorship bias** | Not a property of a fixed two-pair paper runtime: no universe is selected from survivors at run time. R: `universe.py` delisting convention | `test_auth2_gates` (R) | CLAUDE-VERIFIED for R; not applicable to the P3 runtime beyond G-4 |
| **Missing candles** | D: `audit_data.py` gap detection and clusters. L: a fetch failure becomes an incident, and the missed bar is never synthesised; the capture loop never backfills | `test_data_audit::test_gap_is_detected`, `::test_gap_clusters_group_contiguous_holes`, `::test_a_gap_is_a_continuity_finding_not_a_structural_one`; `test_p3_data_truth::test_a_missed_bar_is_an_incident_and_is_never_backfilled` | CLAUDE-VERIFIED. **G-1:** no automated missing-bar audit of a captured input ledger. P2's gap audit (P2_CLOSURE §4) was done by hand |
| **Duplicate candles** | D: duplicate timestamps fail the audit. L: one identity per (pair, timeframe, open time); a re-fetched or repeated candle is written once; `reconcile.py` `input_uniqueness` | `test_data_audit::test_duplicate_timestamp_is_detected`; `test_fp_capture::test_refetching_the_same_candles_appends_nothing`, `::test_duplicate_input_survives_a_fresh_process`; `test_p3_data_truth::test_a_candle_served_twice_in_one_response_is_written_once`, `::test_the_market_event_identity_is_pair_timeframe_and_open_time_only` | CLAUDE-VERIFIED |
| **Timezone consistency** | Integer UTC milliseconds throughout. D: off-grid timestamps fail; ms normalisation. L: UTC rendering, a clock-skew stop at one candle period, and `receive_ts ≥ source_ts`. Host: `health.clock_sync` (NTP) | `test_data_audit::test_off_grid_timestamp_is_detected`; `test_fetch_binance_public_data::test_timestamps_are_normalised_to_milliseconds`; `test_fp_capture::test_receive_before_source_is_rejected`; `test_p3_data_truth::test_timestamps_render_as_utc`, `::test_clock_skew_tolerance_is_one_candle_period_and_symmetric`; `test_p3_health_s19::test_clock_sync_is_info_only_when_ntp_says_yes` | CLAUDE-VERIFIED for the code; the host's NTP state is host-only NOT_RUN in P3 |
| **Partial datasets** | D: coverage assertions; a partial live candle in a dataset is rejected. L: the still-forming candle is dropped, and a candle closing exactly at receipt counts as forming; one malformed row fails the whole response | `test_data_audit::test_coverage_assertions_flag_a_short_dataset`, `::test_a_partial_live_candle_is_rejected`; `test_p3_data_truth::test_the_forming_candle_is_dropped…`, `::test_a_candle_that_closes_exactly_at_receipt_is_still_forming`, `::test_one_malformed_row_fails_the_whole_response…` | CLAUDE-VERIFIED |
| **Silent redownload** | D: dataset locks (raw and canonical digests); `--lock` fails on content drift; downloads verify Binance's published checksums | `test_data_audit::test_dataset_lock_reports_content_drift_as_a_failure`, `::test_lock_gate_still_fails_when_the_content_drifts`, `::test_committed_dataset_lock_matches_the_recorded_audit`; `test_fetch_binance_public_data::test_a_bad_checksum_aborts_rather_than_using_the_data` | CLAUDE-VERIFIED for D. **G-3:** F re-downloads at will inside Freqtrade; no lock applies to it |
| **Mixed data versions** | D: a versioned canonical digest; V1 lock untouched by V2; a serialisation change is a note, not a pass on content. L: every input record carries `source_id` and `source_host` | `test_data_audit::test_canonical_digest_is_order_independent_and_versioned`, `::test_dataset_v1_lock_is_untouched_by_dataset_v2`, `::test_serialization_difference_is_a_note_not_a_failure`; `test_p3_data_truth::test_the_fallback_host_serves_and_is_named_in_every_candle` | CLAUDE-VERIFIED |
| **Symbol changes** | L: a renamed symbol answers `Invalid symbol` and is refused (as for delisted pairs). R: `universe.py` splits a reused ticker into listing segments | `test_p3_data_truth::test_no_usable_host_raises…[answers1]` | Partly CLAUDE-VERIFIED. **G-5:** `universe.segments` (ticker reuse) has no unit test; it is research-only |
| **Funding timestamp alignment** | R: `fetch_binance_funding.py` integrity (off-grid, duplicate, missing settlement, API equivalence) | `test_fetch_binance_funding` (23 tests) | **N/A** to frozen spot; R CLAUDE-VERIFIED |
| **Mark-price alignment** | none | none | **N/A** to frozen spot (no mark price in spot); NOT_COVERED if a derivative market were ever authorized |
| **Cache contamination** | L reads live REST with no cache. D: lock re-check. R: `auth2q2` snapshot-cache law. Backups exclude derived caches | `test_auth2q2_harness::test_a_broken_cache_is_discarded…`, `::test_a_cache_holding_another_snapshot_is_not_this_one`; `test_p3_backup` (derived excluded) | CLAUDE-VERIFIED for R and L. **G-3** applies to F's own data cache |
| *§4 "no silent dataset replacement"* | D: dataset locks, as for silent redownload | as for silent redownload | CLAUDE-VERIFIED |
| *§4 "recorded, never filled"* | L: an incident on a missed fetch; the loop has no fill path; `input_rejected` on out-of-order input | `test_p3_data_truth::test_a_missed_bar_is_an_incident…`; `test_fp_capture::test_out_of_order_candle_becomes_an_incident_not_a_silent_drop` | CLAUDE-VERIFIED |
| *Structural truth of a received candle* (supports all rows) | L: OHLC consistency, non-negative volume, a complete row, parseable values; refused, never repaired. D: the same in `audit_data.py`, plus NaN | `test_p3_data_truth::test_a_malformed_kline_is_refused_not_repaired` (5 cases); `test_data_audit::test_invalid_ohlc_is_detected`, `::test_nan_and_nonpositive_prices_are_detected`, `::test_negative_volume_is_detected`, `::test_reconciliation_catches_a_corrupted_hourly_bar` (5m→1h) | CLAUDE-VERIFIED |

## 3. Named gaps (not closed by this record)
| Gap | What is missing | Where it belongs |
|---|---|---|
| **G-1** | An automated missing-bar audit over a captured input ledger. It should list the missing bars per pair against the expected 1h grid and classify them against `market_fetch_failed`, restart and host-down records. P2 did this by hand. `audit_data.gap_clusters` is reusable for it (REUSE_EXISTING), but the wiring is new code | PLN-07 (with the PLN-06 F-1 "lane signal history gap control") |
| **G-2** | Captured-input vs. runtime-feed equality per bar: an L-vs-F candle comparison for the same bar. Today, agreement is inferred through `event_time_replay` and the F-2/F-4 audit | PLN-07 |
| **G-3** | Freqtrade's own data path (F) has no lock and no cache control from this repository. It is inside the pinned engine image | Accepted as engine behaviour, or covered by G-2 |
| **G-4** | A test that pins the shipped paper config to `StaticPairList` with exactly BTC/USDT and ETH/USDT, the frozen universe | PLN-07; a small test, but it asserts frozen configuration, so it is left to an explicit decision rather than added here |
| **G-5** | Unit tests for `universe.segments` (ticker reuse). Research-only | Research lane, not P3 |

## 4. Host-side data-truth checks (NOT_RUN in P3)
| Check | Why it is host-only | Status |
|---|---|---|
| `audit_data.py --lock` on the frozen dataset files | The files are not in Git (CLAUDE.md "Historical dataset evidence") | Historical `DATA_INTEGRITY_GATE = PASS` from an earlier host. **NOT_RUN in P3** |
| A missing-bar audit of a real P3 paper cohort's input ledger | No P3 paper cohort has run (`PAPER_LAUNCH_AUTHORIZED = NO`); needs G-1 | NOT_RUN |
| NTP state (`health.clock_sync`) | Host state | Runs hourly in the host health timer. Not read for this record |
| L-vs-F agreement on real bars | Needs a running paper runtime | NOT_RUN |

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
  open                           G-1 captured-ledger gap audit · G-2 L-vs-F bar equality · G-3 engine feed
                                 lock/cache · G-4 frozen-universe config pin · (G-5 research-only)
  host-only                      dataset lock audit, real-cohort gap audit, NTP, L-vs-F on real bars: NOT_RUN
```
PLN-07 acceptance is **not** claimed. The acceptance is "the data-truth checks pass". That needs G-1 and G-2, or
an Owner decision that records them as accepted residuals, and the host-side checks in §4 run on real data.
