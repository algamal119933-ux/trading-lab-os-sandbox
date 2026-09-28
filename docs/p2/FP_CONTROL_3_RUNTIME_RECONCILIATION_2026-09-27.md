# FP-CONTROL-3 — runtime reconciliation, 2026-09-27

**Stage:** `P2 — PROSPECTIVE PAPER PROOF`. **Authority:** [`P2_CONTRACT.md`](P2_CONTRACT.md)
and [`S9C_ACTIVATION.md`](S9C_ACTIVATION.md), which this record does not restate,
extend or supersede. **Trigger:** Owner-reviewed `TRADING-STATE-RECONCILIATION-0`
(2026-09-27), which surfaced two open findings against the live runtime of the
cohort this record names. **Scope:** those two findings only.

```text
COHORT      FP-CONTROL-3-20260924T120000Z          T0 = 2026-09-24T12:00:00Z
STATUS      RUNNING, unchanged by this record       window OPEN, cap 2026-10-24T12:01:14Z
NO CHANGE   strategy, risk, Dataset, admission, T0, cohort, credentials, or RUNTIME_TREE
NO ACTION   nothing here restarted, stopped, sealed, or otherwise touched the live runtime
PAPER / RESEARCH ONLY               REAL_MONEY_AUTHORIZED = NO
P3 is not started and is not authorized by this record
```

This record was produced entirely by reading the merged repository, the live
container/journal state, and the cohort's own evidence ledgers. No script that
writes to `RUNTIME_TREE`, the evidence lane, or the pinned runtime checkout was
run in producing it. All chain verification below was independently recomputed
against `research/fp/ledger.py`'s documented algorithm from outside that module,
without invoking `research/fp/reconcile.py` or `research/fp/preflight.py`.

---

## 1. Finding 1 — the 2026-09-24T14:28:46Z runtime recreation

### 1.1 What is directly observed

```text
run 0   observed_utc 2026-09-24T12:01:05.920Z   restart_counter=0   host 2f222e7de29b
        incident seq=0, "capture loop start, restart_counter=0", recovered: prior_runs=0
run 1   observed_utc 2026-09-24T14:28:46.620Z    restart_counter=1   host 6601c797a5ce
        incident seq=1, "capture loop start, restart_counter=1"
        recovered: prior_runs=1, captured_events=2002, decided_bars=2002,
                   decision_records=2002, input_records=2002, trade_records=0
```

`docker inspect` on every current FP-CONTROL-3 container shows `Created ==
StartedAt == 2026-09-24T14:28:45Z` (freqtrade, capture, exporter, mlflow,
prometheus, grafana all within the same second), `RestartCount=0`. This is a
freshly created container object, not an in-place restart of the container that
ran from 12:01:05Z — that first container's host id (`2f222e7de29b`) does not
appear in `docker ps -a` at all; it was removed, not merely stopped. `run 0`'s
own instant, `12:01:05.920Z`, matches `S9C_ACTIVATION.md`'s
`ACTIVATION_START_ISSUED 2026-09-24T12:01:05Z` to within one second — that part
of the certified record is **CONFIRMED** against live evidence, not merely
asserted.

PR #30 (`Certify the activation of FP-CONTROL-3`) merged to `main` at
`2026-09-24T14:26:19Z` — 2 minutes 27 seconds before the new container's
`Created` timestamp. **This proximity is noted and not treated as evidence of
causation.** No commit in that PR touches `RUNTIME_TREE`, the pinned runtime
checkout, or any live container, and the merge event itself cannot start a
Docker container.

### 1.2 Cause — what the evidence does and does not establish

Three lines of evidence were checked for a specific trigger:

1. **The one documented automatic recovery path.** The hourly window monitor
   (`~/.local/share/tlos-p2/window_monitor_fp_control_3.sh`, run by
   `tlos-p2-window-fp-control-3.timer`, `OnCalendar=*:10:00 UTC`) contains
   exactly one automatic restart branch — contract §11 Class-A: if the registry
   reads `RUNNING` and zero containers exist, it restarts through
   `scripts/start_fp_control.sh` at the same pinned commit, and stamps
   `artifacts/fp-control-3-window/.last_governed_restart` when it does.
   That stamp file **does not exist**. The monitor's own log,
   `artifacts/fp-control-3-window/window.log`, has **no entries before
   `2026-09-24T14:30:23Z`** — its first-ever recorded run, two minutes *after*
   the new container's `Created` timestamp, already reporting `runs 2`. The
   monitor could not have caused an event it was not yet running to cause.
   **This path is ruled out by direct evidence, not assumed absent.**
2. **systemd journal.** `journalctl --user` (full boot 0, which covers
   2026-09-08 through today) shows `tlos-p2-activate-fp-control-3.timer`
   being armed at `2026-09-24T11:07:41Z` (per `journalctl --utc` — approximately
   43 seconds after the pre-T0 guard refusal `S9C_ACTIVATION.md` §1 records at
   `11:06:58Z`), but
   **no journal entry for the activation service's execution, for
   `scripts/start_fp_control.sh`, or for any Docker container-lifecycle event**
   in either the 12:01 or the 14:28 window, in either the user or the system
   journal. `journalctl --disk-usage` shows an active journal from this boot
   with no indication of truncation, but the absence of these specific entries
   means the journal cannot be used to name an actor.
3. **The container's own identity.** The new container's `strategy_sha256`,
   `config_sha256`, `source_commit` and `cohort_id` are byte-identical to the
   frozen registry row (`research/fp/records/forward_paper_cohort_registry.json`).
   Repository policy (`activate_fp_control_3.sh.spent`, §6; `CLAUDE.md`) states
   there is exactly one launcher, `scripts/start_fp_control.sh`, and "no manual
   Docker, no alternate launcher." The container **must** have been produced by
   that launcher — no other code path in this repository renders this compose
   configuration — but the launcher can be invoked either by the (ruled-out)
   monitor or directly by an operator with shell access to the pinned runtime
   checkout, and evidence does not distinguish which.

```text
RESTART_CAUSE = UNVERIFIED
```

The *mechanism* (the governed launcher, at the same pinned commit, producing
the same frozen identity) is established. The *triggering actor or event* at
`2026-09-24T14:28:4x Z` is not established by any evidence inspected, and is
not inferred from the PR #30 timing per the Owner's explicit instruction not to
do so.

### 1.3 Restart continuity

```text
RESTART_CONTINUITY = PASS
```

`run 1`'s own incident record states what it recovered before continuing:
`prior_runs=1`, `captured_events=2002`, `decided_bars=2002`,
`decision_records=2002`, `trade_records=0`, `open_positions=[]` — i.e., the new
process read the persisted database and evidence lane, found exactly the prior
run's state, and resumed from it rather than starting a second, competing
history. `input` and `decision` ledger counts are equal at every point checked
(2156 = 2156 at the time of this record), and no duplicate `seq` or duplicate
`market_event_id` was found in either ledger's full contents.

### 1.4 Digest-chain continuity

```text
DIGEST_CONTINUITY = PASS
```

Verified independently, outside `research/fp/reconcile.py`, by recomputing
`record_digest` (per `research/fp/ledger.py`: `sha256` over
`CANONICAL_LEDGER_V1 \n seq \n kind \n recorded_utc \n prev_digest \n
canonical_payload`) for every record in all three FP-CONTROL-3 ledgers and
checking both the recomputed digest and the `prev_digest` linkage:

```text
paper_incident_ledger.jsonl    records=7     chain_intact=True
paper_input_ledger.jsonl       records=2156  chain_intact=True
paper_decision_ledger.jsonl    records=2156  chain_intact=True
```

The chain crosses the `run 0` → `run 1` boundary (`seq 0` → `seq 1` in the
incident ledger) without a break: `seq 1`'s `prev_digest` matches `seq 0`'s
`digest` exactly. No record anywhere in any of the three ledgers is stale,
missing a link, duplicated, or otherwise inconsistent with append-only,
hash-chained history.

### 1.5 What this proves and does not prove for A15

`A15` (`docs/fp-boot-1/FP_CONTROL_1_ACTIVATION_PACK.md` §A15, "status, logs,
safe restart, closure") is a **deliberate, operator-run drill**: stop, restart,
`pytest tests/test_fp_ledger.py`, and — at cohort closure only — write
`fp_control_closure_admission.json` and `fp_control_closure_preflight.json`.

**What the 2026-09-24 event proves for A15:** it is real-world evidence, not
staged, that A15's check #15 property — "no duplicate decision, chain still
verifies" — holds under an actual container recreation of this cohort. That is
at least as strong as a drilled restart would have been, and it is now
independently confirmed (§1.3, §1.4).

**What it does not prove:** it was not run as an A15 drill — no closure
artifacts exist for it, `tests/test_fp_ledger.py` was not run against this
specific event by any process this record can find, and FP-CONTROL-3 is not
closed, so A15's closure sense does not yet apply to this cohort at all. It
also does not establish operator authorization for the event (§1.2), so it
cannot be cited as a *sanctioned* drill — only as a restart whose *outcome*
happens to satisfy the same property a drill would have tested.

---

## 2. Finding 2 — 2026-09-26 market-fetch incidents

### 2.1 Exact incident records

Four `market_fetch_failed` records exist in `paper_incident_ledger.jsonl` on
2026-09-26 — **not three**. `TRADING-STATE-RECONCILIATION-0` and this
authorization both said three; the ledger itself says four. The count is
corrected here against the primary evidence:

```text
seq 3   2026-09-26T14:17:24.355Z   BTC/USDT   DNS resolution failure (both hosts)
seq 4   2026-09-26T20:52:51.049Z   BTC/USDT   DNS resolution failure (both hosts)
seq 5   2026-09-26T20:58:18.658Z   BTC/USDT   DNS resolution failure (both hosts, errno -5)
seq 6   2026-09-26T20:58:42.697Z   ETH/USDT   DNS resolution failure (both hosts)
```

```text
MARKET_FETCH_INCIDENTS = 4
```

All four report the identical failure class: neither
`https://data-api.binance.vision` nor `https://api.binance.com` could be
resolved from inside the capture container at that instant. No incident
reports a different category (e.g. HTTP error, malformed response, rate limit).

### 2.2 Recovery state

Each incident is a single failed poll cycle; the capture loop's next cycle
(observed at ~5-minute spacing in `docker logs`) is not itself recorded as
failing, and no incident after `seq 6` repeats the condition through the time
of this record. No open/unresolved incident state exists in the ledger — the
schema records incidents as point events, and none of these four has any
associated "still failing" or "unresolved" marker.

### 2.3 Evidence impact

```text
MARKET_FETCH_EVIDENCE_IMPACT = NONE_DEMONSTRATED
```

Direct evidence, not inference:

* The window monitor's own hourly `CREDIT` line — computed straight from the
  decision ledger's `t0_relation`/`bar_class` counts, independent of the
  incident ledger — reports `gap_bars 0` at **every** check across
  2026-09-26, including the checks immediately following each incident
  (`15:10:21Z` after `seq 3`; `21:10:21Z` after `seq 4`–`seq 6`).
* The decision ledger itself carries `LIVE / POST_T0 / hold` decisions for
  **both** `BTC/USDT` and `ETH/USDT` for the `13:00`, `14:00`, `20:00` and
  `21:00` bars surrounding all four incidents (e.g. `21:03:44Z` for the 21:00
  bar, ~2 minutes later than the loop's usual cadence but still within the
  hour and inside the contract's one-candle-period staleness bound).
* §1.4's full-ledger digest-chain verification (`chain_intact=True` for all
  2156 input and 2156 decision records) already rules out any stale,
  missing, duplicated or tampered record anywhere in the ledger, including
  around these four timestamps.

No decision bar, input record or chain link is missing, duplicated or stale as
a result of these incidents. Absence of impact is demonstrated here from the
records themselves, not asserted from absence of a contrary report.

---

## 3. Remaining unresolved evidence gap

```text
RESTART_CAUSE                  UNVERIFIED — mechanism confirmed, triggering actor not established
JOURNAL COVERAGE                does not include the activation service's own execution log,
                                nor any Docker lifecycle event, in either the 12:01 or 14:28 window
GOVERNANCE RECORD CURRENCY      S9C_ACTIVATION.md predates run 1 and does not name it;
                                this record supplies that missing narration, and supersedes
                                nothing in S9C_ACTIVATION.md
```

Nothing else in `TRADING-STATE-RECONCILIATION-0`'s two named findings remains
open after §1–§2 above.

---

## 4. Summary

```text
FP_CONTROL_3_VALIDITY = VALID — evidence intact, restart and digest continuity
                                 both independently confirmed; the sole gap is
                                 documentary (cause of one runtime event), not
                                 an evidentiary defect
P2_STATE               = ACTIVE / FP-CONTROL-3 RUNNING — unchanged
P3_AUTHORIZED          = NO
REAL_MONEY_AUTHORIZED  = NO
```

This record does not close FP-CONTROL-3, does not certify a new activation,
and does not open any new stage. It narrates one runtime event and one
incident cluster against the live evidence, truthfully, including the one
question — who or what invoked the governed launcher at `14:28:45Z` — that
this evidence cannot answer.
