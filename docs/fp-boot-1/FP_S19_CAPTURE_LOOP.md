# S19 — the as-seen capture loop

> **Note, 2026-09-14.** This document describes the capture loop as built for a
> single FP-CONTROL-1 runtime. That cohort is now closed, the loop requires an
> explicit `--role`, and the instance it may run as is the pre-T0 successor —
> see [`FP_PRE_T0_SUCCESSOR_CONTROL.md`](FP_PRE_T0_SUCCESSOR_CONTROL.md).
> The mechanism described below is unchanged.

**Closes:** activation-pack stop condition `S19` and the known gap in section 0.1
**Scope:** one control instance at a time, selected by role. Control-only. Paper /
dry-run only. Written when FP-CONTROL-1 was the only instance; the runnable
instance today is the pre-T0 successor FP-CONTROL-2.
**Does not change:** BASELINE-1 strategy logic, indicators, entry rules, exit rules,
thresholds, pair universe, timeframe semantics, or any historical evidence.

---

## 1. What was missing

The activation pack states the gap plainly:

> The scaffold provides the admission gate, the preflight gate, the append-only
> ledgers, event-time replay and the paper Freqtrade stack. It does **not** yet
> provide the process that binds a running Freqtrade dry-run to
> `paper_input_ledger` and `paper_decision_ledger` — the as-seen capture loop.

`scripts/start_paper.sh` started a stack that traded on paper and wrote nothing to
the evidence lane. Nine preflight checks were therefore `UNPROVEN` — 5, 6, 8, 10,
11, 12, 13, 14, 16 — and `S19` held: *"the capture loop of §0.1 does not exist, so
the evidence lane cannot be written."*

## 2. What was built

Three modules and their tests. Nothing else in the runtime changed.

| File | Responsibility |
| --- | --- |
| `research/fp/market.py` | Real public market input. Live Binance spot REST klines, two independent timestamps per candle, unclosed candles refused. |
| `research/fp/capture.py` | The loop. Runtime identity, single-writer lock, state recovery, input/decision/trade/incident capture, risk-admission recording. |
| `research/fp/reconcile.py` | Cross-ledger reconciliation and the event-time parity gate on real captured data. |
| `scripts/check_fp_overlay.py` | Asserts the compose overlay cannot drift into an unsafe runtime. |
| `docker-compose.fp.yml` | The FP control runtime: BASELINE-1 on the selected instance's isolated paths, plus the capture service. |
| `scripts/start_fp_control.sh` / `stop_fp_control.sh` | Fail-closed launcher and a stop that retains evidence. |

### The evidence chain

```text
real public candle      -> paper_input_ledger      market.py, source + receive timestamps
frozen-logic decision   -> paper_decision_ledger   replay.py, linked by market_event_id
risk / admission        -> carried on the decision record
paper order / fill      -> paper_trade_ledger      Freqtrade read-only API
position transition     -> paper_trade_ledger
exit / realised PnL     -> paper_trade_ledger
anything unexpected     -> paper_incident_ledger
```

### Evidence identity carried on every record

`run_id` (one process lifetime), `runtime_id` (the persistent instance),
`cohort_id` (null until the Owner freezes T0), `restart_counter`, `source_commit`,
`strategy_sha256`, `config_sha256`, `capture_engine_version`. Market events carry
`market_event_id` = `pair|timeframe|open_ts`, which is what links a decision back
to the input it was taken on, and what makes a re-fetched candle recognisable as a
duplicate rather than a new event.

## 3. Design decisions worth stating

**The loop observes; it never participates.** BASELINE-1 is frozen, so the capture
loop does not import the strategy, hook it, or influence it. Decisions are derived
by `research/fp/replay.py`, whose periods are read out of the frozen strategy file
by AST. Freqtrade's actual trades are read back through a client that exposes only
`ping`, `status`, `trades` and `show_config` — there is no method on it that could
place, cancel or force a trade. Divergence between the derived decision and the
observed execution is recorded as evidence, never repaired.

**State is recovered from the ledgers, not from a cursor file.** A sidecar cursor
can disagree with the evidence; the evidence cannot disagree with itself. On every
start the loop replays its own ledgers to learn which market events it captured and
which bars it decided, and refuses to write either again. Idempotence across
restarts falls out of that rather than being bolted on.

**Warm-up is classified, not hidden.** A backfilled bar is `bar_class: WARMUP` and
its admission result is `WARMUP_NOT_EXECUTABLE`. BASELINE-1 declares
`startup_candle_count = 600`, so several hundred bars must be captured before a
decision means anything, and those bars contribute indicator state and no outcome
claim. This is the pack's A9 boundary made mechanical:

```text
PRE_T0  = indicator/state initialisation only; contributes no PnL and no outcome claim
T0      = prospective evidence boundary, frozen once
POST_T0 = the only measurable forward-paper evidence
```

Before the Owner freezes T0, `t0_relation` reads `T0_NOT_FROZEN` — not an
optimistic `POST_T0` that would later look like prospective evidence it never was.
The capture loop reads T0 from the registry and can never write one.

**Rejections are recorded.** A malformed or out-of-order market event becomes an
`input_rejected` incident. Silently dropping it would be indistinguishable, in the
evidence, from a market event that never arrived.

**The single-writer lock is `flock`, not a PID file.** A PID file left by a killed
process blocks every later start until someone deletes it by hand, and "delete the
lock and retry" is a habit that eventually deletes a live one. The kernel drops a
`flock` when its holder dies, so a crash self-heals while a genuine second instance
is still refused.

## 4. What the preflight gate now proves

With no runtime attached — the CI case — behaviour is unchanged, deliberately: the
gate must not become easier to pass by being run somewhere with less evidence
available. With `--role`, `--evidence-dir` and the runtime URLs, these are answered from the
running instance instead (`--role` is required whenever evidence is attached, so
the runtime is compared against the instance it actually is):

| # | Check | How it is now proven |
| --- | --- | --- |
| 5 | runtime hashes match registry | registry, working tree and the hashes the running loop stamped onto its own evidence are compared three ways |
| 6 | real market-data ingestion | hosts probed *and* candles shown to have been ingested through them |
| 8 | input ledger on real incoming data | exchange-sourced records, both timestamps present, altering a real captured candle is detected |
| 10 | DB is isolated | the registry now binds distinct `bot_name`/`db_path`/`log_path`/`evidence_dir` |
| 11 | monitoring is alive | exporter, Prometheus and the bot are probed separately (section 18 keeps those states apart) |
| 12 | event-time replay on real data | full reconciliation plus a negative control that flips one recorded action |
| 13 | no duplicate-instance risk | a second writer is actually attempted against the live evidence directory and must be refused |
| 14 | clock/timestamp tolerance | skew measured against the exchange and evaluated against S16, never waived |
| 16 | restart drill | the real evidence must show ≥2 runs, strictly increasing restart counters, intact chains, and no re-decided bar |

## 5. Tests

`tests/test_fp_capture.py` and `tests/test_fp_overlay.py`, plus additions to
`tests/test_fp_preflight.py`. Every one is offline and deterministic: a test that
reached the exchange would fail for reasons unrelated to the code under test, and
CI must prove these properties without a market route.

The thirteen required proofs, and where each lives:

| Required proof | Test |
| --- | --- |
| input-ledger write | `test_input_ledger_write_captures_real_shape` |
| decision-ledger write | `test_decision_ledger_write_records_frozen_logic` |
| input→decision linkage | `test_every_decision_links_to_a_captured_input` |
| duplicate-input handling | `test_refetching_the_same_candles_appends_nothing`, `test_duplicate_input_survives_a_fresh_process` |
| duplicate-decision rejection | `test_a_bar_is_never_decided_twice`, `test_duplicate_decision_rejected_across_a_restart` |
| no duplicate paper execution | `test_repeated_polling_records_each_execution_once`, `test_close_adds_one_event_and_never_reopens` |
| restart / reopen | `test_restart_resumes_the_chain_and_increments_the_counter` |
| state persistence | `test_evidence_survives_reopening_by_fresh_readers`, `test_recovered_state_matches_what_was_written` |
| existing-position recovery | `test_an_open_position_is_recovered_after_restart` |
| malformed-event rejection | `test_malformed_events_are_rejected` (9 cases) |
| missing-timestamp rejection | `test_missing_timestamp_is_rejected`, `test_unusable_timestamp_values_are_rejected` |
| out-of-order event handling | `test_out_of_order_candle_is_rejected`, `test_out_of_order_candle_becomes_an_incident_not_a_silent_drop` |
| ledger reconciliation | `test_reconciliation_passes_on_a_clean_capture` plus three negative controls |

Each negative control matters more than its positive twin: a reconciliation that
only ever passes proves nothing, so tampering with a decision, orphaning a
decision from its input, and duplicating an execution must each be caught.

## 6. Boundaries preserved

```text
FP-CONTROL-1                = BASELINE-1 as operational control, State C, control-only
                              NOT a candidate, NOT a survivor, NOT candidate-quality evidence
warmup_overlay              = NOT APPLICABLE (BASELINE-1 declares startup_candle_count 600;
                              Dataset V2 supplies 744 pre-Development candles)
canonical dataset cache     = WRITE ONCE / IMMUTABLE — untouched by this build
single cohort only          — no medium/high risk cohorts, no dual instances, no dual wallets,
                              no parallel orchestration, no agents, no strategy expansion
PAPER_TRADING_OPERATIONAL_CAPABILITY  is what this can prove
PROSPECTIVE_PAPER_EDGE                is NOT evaluated by FP-CONTROL-1
REAL_MONEY_AUTHORIZED       = NO
```
