# FP-CONTROL-3 — runtime reconciliation, 2026-09-29

**Stage:** `P2 — PROSPECTIVE PAPER PROOF`. **Authority:** [`P2_CONTRACT.md`](P2_CONTRACT.md)
and [`S9C_ACTIVATION.md`](S9C_ACTIVATION.md), which this record does not restate,
extend or supersede. **Trigger:** Owner authorization `TRADING LAB OS — STAGE A —
CLOSE & PRESERVE` (2026-09-29), workstream A2, itself grounded in the read-only
`TRADING-RESEARCH-RECONCILIATION-0` pass that first surfaced the event this
record narrates. **Scope:** the 2026-09-28T15:28:15Z runtime event and every
incident record on or after 2026-09-27T23:46:08Z not covered by
[`FP_CONTROL_3_RUNTIME_RECONCILIATION_2026-09-27.md`](FP_CONTROL_3_RUNTIME_RECONCILIATION_2026-09-27.md)
("the 09-27 record"), which this record supplements and does not supersede.

```text
COHORT      FP-CONTROL-3-20260924T120000Z          T0 = 2026-09-24T12:00:00Z
STATUS      RUNNING, unchanged by this record       window OPEN, cap 2026-10-24T12:01:14Z
NO CHANGE   strategy, risk, Dataset, admission, T0, cohort, credentials, or RUNTIME_TREE
NO ACTION   nothing here restarted, stopped, sealed, or otherwise touched the live runtime
PAPER / RESEARCH ONLY               REAL_MONEY_AUTHORIZED = NO
P3 is not started and is not authorized by this record
```

This record was produced entirely by reading the merged repository, the live
container/journal/systemd state, and the cohort's own evidence ledgers, all
read-only. No script that writes to `RUNTIME_TREE`, the evidence lane, or the
pinned runtime checkout was run in producing it. The digest-chain verification
below was recomputed independently, outside `research/fp/reconcile.py`, over
the ledger's full current contents (`seq 0`–`13`), not merely the boundary this
record narrates.

---

## 1. Finding — the 2026-09-28T15:28:15Z runtime restart (`restart_counter` 1→2)

### 1.1 What is directly observed

```text
run 2   observed_utc 2026-09-28T15:28:16.378Z   restart_counter=2   host 6601c797a5ce
        incident seq=10, "capture loop start, restart_counter=2"
        recovered: prior_runs=2, captured_events=2188, decided_bars=2188,
                   decision_records=2188, input_records=2188, trade_records=0,
                   open_positions=[]
```

`docker inspect` on every FP-CONTROL-3 container shows `Created=2026-09-24T14:28:45Z`
unchanged from the 09-27 record, but `StartedAt=2026-09-28T15:28:15.821Z` — a
process restart of the **same container objects**, not a recreation.
`RestartCount=0` on every container, as before. This is the opposite pattern
from the 2026-09-24T14:28:46Z event the 09-27 record narrates (a fresh
container object, `host 6601c797a5ce` replacing `host 2f222e7de29b`): here the
host id is unchanged (`6601c797a5ce`, same as `run 1`), only the process inside
it restarted.

### 1.2 Cause — established, and established by a different mechanism than the 09-27 event

Unlike the 2026-09-24 event, this restart's mechanism is directly established
by primary evidence, not merely narrowed to one plausible explanation:

1. **A real host reboot, confirmed by `journalctl --list-boots`** (not inferred
   from `uptime` alone): the prior boot's last journal entry is
   `2026-09-28 14:55:37 EEST`; the current boot's first entry is
   `2026-09-28 18:27:47 EEST` (`= 2026-09-28T15:27:47Z`). This is systemd's own
   boot-sequence record, distinct boot IDs either side of the gap — the host
   was down and came back up at that instant, not merely idle.
2. **`docker.service` restarted as part of that boot**, per
   `systemctl show docker --property=ActiveEnterTimestamp`:
   `2026-09-28 18:28:16 EEST` (`= 2026-09-28T15:28:16Z`) — 29 seconds after the
   boot's first journal entry, consistent with ordinary service-startup
   sequencing, and `docker.service` is enabled at
   `/etc/systemd/system/multi-user.target.wants/docker.service` (starts on
   every boot by design, not by any P2-specific configuration).
3. **Every FP-CONTROL-3 service carries `restart: unless-stopped`** in
   `docker-compose.yml`/`docker-compose.fp.yml` — confirmed both in the
   compose file text and directly on the live containers via
   `docker inspect --format '{{.HostConfig.RestartPolicy.Name}}'`
   (`unless-stopped` on every one checked). This is a standard Docker
   behavior: when the daemon restarts, containers under this policy are
   brought back up automatically, without daemon-level tracking as a
   restart-policy retry and without container recreation — which is exactly
   the `RestartCount=0` / `Created` unchanged / `StartedAt` moved pattern
   observed here.
4. **The one documented alternative actor explicitly did not act.** The window
   monitor's own log, `artifacts/fp-control-3-window/window.log`, has an entry
   timestamped `2026-09-28T15:28:07Z` — a `Persistent=true` catch-up firing
   for the timer it missed while the host was down — reading
   `WATCH=2 STALLED | all checks OK` and, in its own words,
   `NOT OK and the stack is up — left for judgement, nothing was restarted`.
   The monitor found the stack already up (Docker's restart policy having
   already acted in the ~9 seconds before this log line) and took no action
   itself. `scripts/start_fp_control.sh`, the sole governed launcher, was
   not invoked — the container objects were never recreated (§1.1), and that
   script's own effect is always a fresh container per the 09-27 record's own
   established policy ("no manual Docker, no alternate launcher" describes
   the launcher's own path, not Docker's independent restart-policy path,
   which this repository's compose files opt into separately).

```text
RESTART_CAUSE = HOST REBOOT, ACTING THROUGH DOCKER'S OWN restart:unless-stopped
                POLICY ON docker.service's return — CONFIRMED, not inferred from
                timing proximity alone
```

**What remains open:** *why the host itself rebooted* — a scheduled event, a
crash, a power interruption, or a manual action — is not established by any
evidence inspected in this pass. `journalctl --list-boots` proves a boot
boundary occurred; it does not, by itself, name a cause for the boundary, and
no shutdown/kernel-panic/power-event journal entry was found in the brief
window checked around it. This is a narrower, lower-stakes open question than
the 09-24 event's: the 09-24 question was *what/who caused a governed action to
run*; this one is *why did the host reboot*, given that everything downstream
of the reboot (container restart, evidence recovery) is now fully accounted
for by ordinary, documented mechanisms.

### 1.3 Restart continuity

```text
RESTART_CONTINUITY = PASS
```

`run 2`'s own incident record states what it recovered before continuing:
`prior_runs=2`, `captured_events=2188`, `decided_bars=2188`,
`decision_records=2188`, `trade_records=0`, `open_positions=[]` — the process
read the persisted database and evidence lane, found exactly the prior run's
state, and resumed from it. `input` and `decision` ledger counts remained
equal at every point checked after the boundary (2208 = 2208 at the time of
this record), and no duplicate `seq` or `market_event_id` was found in either
ledger.

### 1.3a Database continuity — full evidentiary basis

```text
DATABASE_CONTINUITY = PASS
```

`trade_records=0` alone is not, by itself, proof of continuity — a count of
zero is equally consistent with a database that was silently replaced,
truncated, or never actually read. `DATABASE_CONTINUITY = PASS` here rests
instead on the combination of:

* **Identity/path** — `run 2`'s `full_identity.db_path` is
  `/freqtrade/user_data/fp-control-3/tradesv3.sqlite`, the same path recorded
  for `run 0` and `run 1`; no alternate or new database path appears anywhere
  in the ledger across the restart.
* **Persistent state recovered, not reinitialized** — the `recovered` block
  (`captured_events=2188`, `decided_bars=2188`, `decision_records=2188`,
  `input_records=2188`, `prior_runs=2`) is exactly the state the prior run
  (`run 1`) had reached at `seq 9` (§2, incident count through that point),
  not a reset to zero on any of these counters — a fresh/replaced database
  would show `prior_runs=0` and empty counters, as `run 0` itself did at
  cohort start.
* **Cohort identity unchanged** — `cohort_id=FP-CONTROL-3-20260924T120000Z` is
  identical in every record either side of the boundary.
* **Expected persistent record matches the live table** — the live
  `tradesv3.sqlite` `trades` table, queried read-only this session, returns
  `COUNT(*)=0`, which is the value the recovered state *predicts*
  (`trade_records=0`), not merely a coincidental independent zero.
* **Incident-ledger and digest-chain continuity spanning the boundary** —
  §1.4 below: every record's digest and `prev_digest` link verified intact
  across `seq 9` → `seq 10`, independently recomputed over the full ledger.
* **Input/decision ledger continuity** — counts remain equal
  (`2208 = 2208`) and no duplicate `seq` or `market_event_id` exists in
  either ledger spanning the boundary (§1.3 above).

Each of these individually is circumstantial; together — same path, resumed
(not reset) counters, unchanged cohort identity, a live-table value matching
the recovered prediction, and an intact hash chain across the boundary — they
jointly support `PASS`. If any one of them had instead shown a reset,
mismatch, or break, this record would downgrade to `PARTIAL` or `FAIL` rather
than retain `PASS` on count alone.

### 1.4 Digest-chain continuity

```text
DIGEST_CONTINUITY = PASS
```

Recomputed independently over the incident ledger's full current contents
(`seq 0` through `13`, 14 records — not just the boundary this record
narrates), following the same algorithm the 09-27 record used
(`research/fp/ledger.py`'s `record_digest`: `sha256` over
`CANONICAL_LEDGER_V1 \n seq \n kind \n recorded_utc \n prev_digest \n
canonical_payload`), by a script written for this record and run outside
`research/fp/reconcile.py`. Every one of the 14 records' own recorded `digest`
matched the value recomputed from its `payload`, and every record's
`prev_digest` matched the immediately preceding record's `digest` exactly
(`seq 0`'s absence of a `prev_digest` is the one correct exception). The chain
crosses both the `run 1`→`run 2` boundary (`seq 9`→`seq 10`) and the two
`activation_gap` records immediately after it (`seq 11`, `seq 12`) without a
break.

### 1.5 What this proves and does not prove for A15

As the 09-27 record established for the first event, `A15`
(`docs/fp-boot-1/FP_CONTROL_1_ACTIVATION_PACK.md` §A15) is a deliberate,
operator-run drill: stop, restart, `pytest tests/test_fp_ledger.py`, and —
at cohort closure only — write the closure artifacts.

**What this event proves for A15:** real-world evidence, independent of the
09-24 event, that the same continuity property — no duplicate decision, chain
still verifies — held under a second, mechanistically different kind of
restart (a daemon-level restart-policy resume, not a container recreation).
Two independent restart mechanisms have now each demonstrated this property
without a drill.

**What it does not prove:** it was not run as an A15 drill — no closure
artifacts exist for it, `tests/test_fp_ledger.py` was not run against this
event by any process this record can find, and FP-CONTROL-3 remains open, so
A15's closure sense does not yet apply.

```text
A15_FORMAL_DRILL = NO (neither restart event was a certified drill)
A15_FINAL_STATE  = NOT CLOSED (cohort still running)
```

---

## 2. Post-09-27 incidents not covered by the 09-27 record

The 09-27 record closed against `paper_incident_ledger.jsonl` as it stood at
the time (`seq 0`–`6`). Five further incidents have since been recorded,
`seq 7` through `seq 9` (before this event) and `seq 11`–`13` (immediately
after it):

```text
seq 7    2026-09-27T23:46:08.xxxZ   BTC/USDT   market_fetch_failed — DNS
seq 8    2026-09-27T23:46:32.612Z   ETH/USDT   market_fetch_failed — DNS
seq 9    2026-09-28T01:07:37.441Z   BTC/USDT   market_fetch_failed — DNS
seq 11   2026-09-28T15:28:17.671Z   BTC/USDT   activation_gap — WARMUP, POST_T0,
                                                staleness_ms=5297637 (~88.3 min)
seq 12   2026-09-28T15:28:18.902Z   ETH/USDT   activation_gap — WARMUP, POST_T0,
                                                staleness_ms=5298861 (~88.3 min)
seq 13   2026-09-28T15:28:18.936Z   —          freqtrade_api_unreachable
                                                (Connection refused, transient)
```

```text
MARKET_FETCH_INCIDENTS (seq 7-9) = 3, identical failure class to the 09-27
  record's four: neither `data-api.binance.vision` nor `api.binance.com`
  resolvable from inside the capture container at that instant. No new
  failure category.
ACTIVATION_GAP INCIDENTS (seq 11-12) = 2, both directly caused by the §1
  restart: the 1h bars that closed while the host was down were recovered
  ~88 minutes late on restart. Both are correctly classified `POST_T0` and
  `WARMUP`, and are contextual evidence only — never credited toward the
  window. This is independently confirmed by the window monitor's own
  `CREDIT` computation: `gap_bars 0` at the last check before the restart
  (`2026-09-28T15:28:07Z`) and `gap_bars 2` at every check since
  (`16:10:20Z` onward) — the count matches these two records exactly, with
  no additional, unaccounted-for gap.
API_UNREACHABLE (seq 13) = 1, transient (the Freqtrade container was still
  starting up in the same restart window as §1); self-resolved by the
  capture loop's next cycle.
```

```text
MARKET_FETCH_EVIDENCE_IMPACT = NONE_DEMONSTRATED (seq 7-9, same basis as the
  09-27 record: §1.4's full-chain verification already rules out any stale,
  missing, duplicated or tampered record around these timestamps)
ACTIVATION_GAP_EVIDENCE_IMPACT = NONE BEYOND THE GAP ITSELF, WHICH IS BY
  DESIGN NEVER CREDITED — no decision bar, input record or chain link is
  missing as a *result* of these incidents; the two skipped bars are the
  incident, correctly recorded and correctly excluded, not a symptom of a
  larger problem
```

---

## 3. Remaining unresolved evidence gap

```text
RESTART_CAUSE (container level)   HOST REBOOT via docker restart:unless-stopped
                                   policy — CONFIRMED (§1.2)
REBOOT_CAUSE (host level)         NOT ESTABLISHED — journalctl proves a boot
                                   boundary at 2026-09-28T15:27:47Z; no
                                   evidence inspected in this pass names why
GOVERNANCE RECORD CURRENCY        this record supplies the narration the
                                   09-27 record could not (it predates this
                                   event); it supersedes nothing in either
                                   the 09-27 record or S9C_ACTIVATION.md
```

Nothing else in the incident ledger's current contents (`seq 0`–`13`) remains
open after this record and the 09-27 record together.

---

## 4. Summary

```text
FP_CONTROL_3_VALIDITY  = VALID — evidence intact; both restart events (09-24
                          container recreation, 09-28 daemon-restart-policy
                          resume) independently confirmed continuous; the
                          sole remaining gap is the host reboot's own root
                          cause, which does not bear on evidence validity
P2_STATE                = ACTIVE / FP-CONTROL-3 RUNNING — unchanged
P3_AUTHORIZED           = NO
REAL_MONEY_AUTHORIZED   = NO
RESTART_COUNT (cohort)  = 2 (restart_counter now reads 2 in every current
                          ledger record)
```

This record does not close FP-CONTROL-3, does not certify a new activation,
and does not open any new stage. It narrates one runtime event and five
incident records against the live evidence, truthfully, including the one
question — why the host rebooted at `2026-09-28T15:27:47Z` — that this
evidence cannot answer.
