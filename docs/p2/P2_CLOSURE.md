# P2 — STAGE CLOSURE

**Stage:** `P2 — PROSPECTIVE PAPER PROOF`.
**Authority:** [`P2_CONTRACT.md`](P2_CONTRACT.md) §7 (the window law, NORMAL END) and §12
(the closure law). This record does not restate the contract and does not extend it.
**Owner authorizations:** GO 1 (the governed shutdown, executed 2026-10-24T18:52:04Z) ·
GO 1R 21:37:14Z · GO 2 21:42:04Z · GO 3 21:46:34Z · closure preparation 21:54:01Z ·
closure corrections 22:14:40Z. P2 is closed only when this record reaches `main` through the
Owner's normal two-parent merge.

```text
P2_TERMINAL_STATUS = CLOSED / PASS
COHORT_ID = FP-CONTROL-3-20260924T120000Z
EVIDENCE_VALID = YES
EVIDENCE_CHAINS = INTACT
RECONCILIATION = PASS
UNRESOLVED_INTEGRITY_DEFECTS = NONE
UNRESOLVED_TECHNICAL_DEFECTS = NONE
SAFETY_FAILURES = NONE
REAL_MONEY_AUTHORIZED = NO
```

```text
TRIGGER                          A — NORMAL END (contract §7)
CAPABILITY_PROPERTIES            12/12 PASS   (9 pre-T0 at Mq + 3 from the credited L2 lifecycle)
paper_trading_operational_capability = PROVEN
full_trade_lifecycle                 = OBSERVED
prospective_paper_edge               = NOT_EVALUATED
measurable_post_t0_evidence          = AVAILABLE

T0              2026-09-24T12:00:00Z          immutable, never moved
ACTIVATION_UTC  2026-09-24T12:01:14Z
HARD_CAP        2026-10-24T12:01:14Z          not the trigger: the lifecycle completed first
NORMAL END      2026-10-22T23:00:01Z          BTC/USDT trade 1 closed
GO 1            2026-10-24T18:52:04Z          Owner-authorized governed shutdown of the stack
AUTO RESTART    2026-10-24T19:10:18Z          host monitor timer, restart_counter 9 (F-5)
SHUTDOWN        2026-10-24T21:37:57Z          GO 1R: timer disabled, then scripts/stop_fp_control.sh, rc 0
SEALED          2026-10-24T21:42:51Z          l2-cohort-20260924T120000Z (GO 2)
M1 (declared)   83c49414cc9eaba9a4e25809672d65d032669616
M2 (stamped)    3191285a28823907f62c6eb915327599cd6ed90b   on every record
Mq              909bf5fa551e9cb4351de6eb40cc42f9cbe28cbd
PAPER / RESEARCH ONLY
```

**P&L determines neither PASS nor FAIL** (§12). Both closed trades lost money, and that changes
nothing here.

---

## 1. The credited lifecycle

The first naturally completed full paper trade lifecycle credited to this cohort is
**BTC/USDT trade 1**. Every step is a `POST_T0 + LIVE` record that the admission gate admitted.

```text
entry decision   decision seq 3044 · candle 2026-10-21T02:00Z · decided 03:04:58Z
                 intended_action enter_long · POST_T0 · LIVE · admission ADMITTED
paper fill       trade seq 0 · position_opened · 2026-10-21 03:00:02 · open_rate 82804.23
                 amount 0.00012 · stake 9.9365076 USDT · enter_tag ema_regime_up
                 paper_fill_model_version FREQTRADE_2026.7_DRYRUN_ORDERBOOK_V1
exit decision    decision seq 3132 · candle 2026-10-22T22:00Z · decided 23:03:45Z
                 intended_action exit_long · POST_T0 · LIVE · admission ADMITTED
paper close      trade seq 3 · position_closed · 2026-10-22 23:00:01 · close_rate 81355.63
                 exit_reason ema_regime_down · realised PnL -0.19353118 USDT
identity         cohort FP-CONTROL-3-20260924T120000Z · source_commit 3191285a
                 restart_counter 7 for both events
```

Nothing was forced. There was no `/forceenter` and no `/forceexit`, and no threshold, pair,
strategy or config changed. The entry and the exit are the frozen logic's own signals, and
event-time replay reproduces both.

### ETH/USDT trade 2 is CONTEXTUAL, not credited

```text
paper fill       2026-10-21 20:00:01 · open_rate 2495.06
paper close      2026-10-22 11:10:07 · close_rate 2404.41 · exit_reason ema_regime_down
lane decisions   entry  decision seq 3083 · candle 2026-10-21T21:00Z · decided 22:01:29Z
                        enter_long · POST_T0 · LIVE · admission BLOCKED (open_position_count 2)
                 exit   decision seq 3103 · candle 2026-10-22T07:00Z · decided 08:02:51Z · ADMITTED
```

The ETH paper fill happened about an hour **before** the lane's own entry decision for that pair.
That decision was BLOCKED because two positions were already open, one of them this ETH position.
The close at 11:10:07 also does not line up with the admitted exit decision at 08:02Z. Freqtrade
acted on its own view of the candles, and the lane's captured series placed the cross later (§4,
F-1). The ETH lifecycle is real and recorded, and it is reported here. But an execution that no
admitted lane decision backs cannot be credited, so it is not.

## 2. The twelve properties

| # | Property | Bucket | Evidence | Result |
|---|---|---|---|---|
| 1 | real market input | pre-T0 | S3 certificate at Mq `909bf5fa`, `p2_qualification_binding.json` (certificate `b339c995…`) | PASS |
| 2 | event-time/timestamp knowability | pre-T0 | same | PASS |
| 3 | paper-only authority | pre-T0 | same | PASS |
| 4 | decision logging | pre-T0 | same | PASS |
| 5 | risk/admission | pre-T0 | same | PASS |
| 6 | persistence | pre-T0 | same | PASS |
| 7 | restart recovery | pre-T0 | same | PASS |
| 8 | ledger reconciliation | pre-T0 | same | PASS |
| 9 | data integrity | pre-T0 | same | PASS |
| 10 | paper order/fill | L2 lifecycle | BTC trade 1: admitted entry, then a paper fill under the frozen fill model | PASS |
| 11 | position state | L2 lifecycle | BTC trade 1: position opened, held and closed with realised PnL | PASS |
| 12 | no duplicate execution | L2 lifecycle | reconcile `no_duplicate_execution`: 4 paper execution events, each recorded once | PASS |

`full_trade_lifecycle` is reported beside the twelve and is never counted among them (§3).
**Disclosure:** no restart happened while the BTC position was open; restart_counter was 7 at
both entry and exit. Restart recovery is the pre-T0 property certified at Mq. This cohort's
own ten starts (counters 0–9) all resumed the existing chains (`restart_continuity` PASS).

## 3. Evidence, reconciliation and the seal

```text
ledgers          input 3194 · decision 3194 · trade 4 · incident 3335 · runs 10
tips             input    4f73fea548e1babe9989f92683728421ee5d4f25e38ec2e0e7fb5a7e708d8e40
                 decision 35148ec664df114338fb424b40aaf7fcbdb3da3445e08869cda3c965c77344e2
                 trade    050099ed7239d0521c4077aecbacf50a174fd15a133f84d37c173878adfc2a17
                 incident a3411a93d0e51c6f49ec6c31706a896567dc0aa05f06bb577093887d14751c35
pack digest      6ab601940e3e62018eedfb63d4f879d6c9a7fa863af8d6f33bea97c2add32e1c
reconcile        PASS · 14/14 findings · failing_checks [] · findings_complete true
                 event_time_replay BTC/USDT 1597/1597 · ETH/USDT 1597/1597 · 0 mismatches
                 registry_source_commit_equivalence: 83c49414 ≡ 3191285a (semantic identity 04578497dc51…)
chains           all four verify from genesis (reconcile and an independent recompute)
decisions        POST_T0 + LIVE 1170 · POST_T0 + WARMUP 28 · PRE_T0 + WARMUP 1996
```

| Durability | Where | Verification |
|---|---|---|
| Tier 1 (same host) | `artifacts/l2-cohort-20260924T120000Z`, 18 files, 125,901,115 B, manifest sha256 `6594e9cd…40d3` | COPY → VERIFY → SEAL → REMOVE; `--verify-only` PASS; live lane `LANE_EMPTY = YES` |
| Tier 2 (digest) | `research/fp/records/evidence_digest_publication.json`, entry `l2-cohort-20260924T120000Z` | 18 file digests, re-read from disk before publication |
| Second device | `/mnt/tlos-wdc/trading-lab-os-evidence/l2-cohort-20260924T120000Z` (WDC WD10EZEX, sda) | 19/19 sha256 match; `replicate --verify-only` PASS |

`SAME_HOST_SECOND_DEVICE = YES` · `HOST_LOSS_REDUNDANCY = NOT_PROVEN`. Neither copy survives the
loss of this host. Tier 3 is P3 scope.

## 4. Interruptions and coverage

```text
pair coverage     BTC/USDT 598/729 bars · ETH/USDT 598/729 bars · 131 missing per pair in 11 gaps
missing bar-hours EXPLAINED_FETCH_FAILURES 166 (DNS / timeout; host up, link down)
(both pairs)      UNEXPLAINED 74 (host down, unclean end, power-loss-consistent; no record possible)
                  EXPLAINED_DOWNTIME_THEN_RESTART 22
activation_gap    28 incidents · their bars are POST_T0 + WARMUP: counted, never credited
host down         2026-09-28T11:55Z..15:27Z 3.5h · 10-08T05:40Z..11:01Z 5.4h · 10-10T11:50Z..15:31Z 3.7h
(unclean)         10-13T06:34Z..09:34Z 3.0h · 10-13T13:34Z..10-14T09:51Z 20.3h · 10-23T03:20Z..21:49Z 18.5h
longest outage    2026-10-04T13:00Z..10-07T17:00Z 77h of fetch failures (DNS), host up
restarts          10 run_started, restart_counter 0..9, one cohort, one commit
```

Missed bars are never executed afterwards. A gap is recorded, never filled. Signal completeness
against the contiguous public series reads `SIGNAL_SETS_EQUAL = NO` for both pairs. That compares
the captured candles with candles the lane never received, so it measures coverage, not replay
fidelity. Replay over the captured inputs matches 1597/1597 on each pair.

## 5. Findings

F-1 to F-5 below are the canonical findings of the A15 closure review. The Owner's closure
decision (2026-10-24T22:14:40Z) adopted them, set the GO 1 attribution and classified F-2. The
text is reproduced verbatim, re-wrapped only, from the copy posted to the Owner in the closure
thread at 22:14:50Z. The supporting record under each one is this record's own detail. It cites
evidence and does not change the finding.

```text
F-1 ETH runtime/lane divergence: runtime entry on the 19:00 signal and exit on the 10:00 signal
    (both match the contiguous public series); lane entry decision 21:00 BLOCKED, exit decision
    07:00. Cause: the lane derives EMA from its gapped captured history (gap audit section 4,
    verified). Trade 2 is contextual, not credited. The fix would be Class B and goes to P3
    PLN-07/PLN-06.
F-2 reconcile.py execution_backed_by_decision (lines 479-490) is pair-level: it ignores bar
    timing and the admission result, and it passed the ETH entry on a later BLOCKED decision.
    This is an unresolved verification-tool weakness carried to P3. It is not a runtime fault
    and does not invalidate the cohort.
F-3 The cohort ran about 37 h past its normal end (2026-10-22T23:00:01Z), because the A15 check
    was scheduled at the cap, not at the lifecycle. Post-window and post-cap records are context,
    not credited. The 10-23 host-down interval (03:20Z to 21:49Z) falls in this span.
F-4 The ETH close at 11:10:07Z is not on a candle boundary. A likely cause is exit-order fill
    latency under order-book pricing with a 10-minute unfilled timeout [inference, unverified].
F-5 The Owner-authorized GO 1 stop at 18:52:17Z was undone at 19:10:20Z by
    tlos-p2-window-fp-control-3.timer, through its Class-A recovery path, which has no hard-cap
    guard. This is a runbook gap, resolved by GO 1R (timer disabled 21:37Z, stopped 21:37:57Z).
    The run-9 records are post-window context, not credited.
```

**F-1, supporting record.** This is §1 and the gaps in §4. Against the contiguous public series
the signal candles are: ETH public EXIT 10-07T04, ENTER 10-21T19, EXIT 10-22T10; ETH captured
EXIT 10-07T19, ENTER 10-21T21, EXIT 10-22T07. BTC agrees on the two lifecycle candles (ENTER
10-21T02, EXIT 10-22T22); its earlier EXIT differs (public 10-07T16, captured 10-08T14). Each pair
has 598 of 729 bars, with 131 missing in 11 gaps. Of the missing bar-hours, 166 are explained
fetch failures, 22 are explained downtime then restart, and 74 are unexplained. All 74 fall
inside unclean host-down intervals consistent with power loss. Replay over what was captured is
exact, 1597/1597 on each pair. That is self-consistency, so it does not cover this divergence.

**F-2, supporting record.** Reconcile's `execution_backed_by_decision` checks only that each entry
falls on a pair the frozen logic signalled for, so it passes on ETH. The per-execution check that
separates credited from contextual (bar timing plus admission result) was made by hand for this
record.

**F-3, supporting record.** Nothing stops a cohort at `HARD_CAP`. The original run kept deciding
until GO 1. Records after the cap are `input 20 · decision 20` (10 hourly bars × 2 pairs,
12:04:26Z to 21:01:42Z) and `incident 2`. They are kept in the sealed archive and not credited.
No trade event occurred after the normal end. The window law forbids extending a window, and
none was claimed.

**F-4, supporting record.** The ETH close is recorded at 2026-10-22 11:10:07, while the lane's
admitted exit decision is for candle 07:00 (§1). The cause in F-4 is an inference and is not
verified here.

**F-5, supporting record.** The stop began at 18:52:04Z, when the daemon sent SIGTERM to the
stack. 18:52:17Z is the time printed after the stop command returned. At 19:10Z the host-side
user timer saw "registry RUNNING, 0 containers" and ran `scripts/start_fp_control.sh
FP-CONTROL-3` (restart_counter 9, incidents seq 3333–3334). The monitor logged `HARD_CAP_REACHED
… NEEDS JUDGEMENT` every hour from 16:10Z, but its restart path has no hard-cap guard, and GO 1
did not disable it. Under GO 1R the timer was disabled and stopped before the second governed
shutdown. The monitor's unit files and script live outside the repository and are kept
unchanged.

### Additional observation, not a canonical finding

**O-1 — a governed stop leaves no attributable record.** The GO 1 attribution comes from the
Owner's authorization and the Owner's own terminal output. Nothing in the evidence lane records
the stop itself: a stop writes nothing into it, and the next record is the 19:10Z `run_started`.
Docker keeps no durable event history. The host journal shows the daemon stopping the containers
(SIGTERM, then a forced kill after 10 s) and removing the stack's network, with no command or
actor. This is carried to P3 operational hardening with F-2: governed stops and starts must leave
a verifiable, attributable record. It does not invalidate the cohort.

### How the machine block reads these findings

`UNRESOLVED_INTEGRITY_DEFECTS = NONE`. Every chain verifies from genesis, every record is
attributable, reconciliation passes on all fourteen findings, and paper-only authority held.

`UNRESOLVED_TECHNICAL_DEFECTS = NONE` is stated under the contract's own definition and no wider
one. P2_CONTRACT §11 says "A cohort is invalidated ONLY by a technical defect in its evidence or
identity", and its classes B to E name those defects: a tracked runtime repair, corrupted or
missing evidence, a strategy or risk change, a Dataset authority change. The registry schema
defines no other meaning. None of F-1 to F-5 or O-1 is such a defect in this cohort's evidence or
identity, and none needed a runtime repair to close it. F-2 stays visible as an **unresolved
verification-tool weakness** carried to P3. F-1 is a Class B fix for P3 (PLN-07/PLN-06), and F-3,
F-5 and O-1 are runbook and tooling gaps carried as inputs to a later stage. If the Owner reads
"technical defect" more widely than §11, this field must not read NONE, and this record must be
revised before it is merged.

## 6. What this closure proves, and does not

```text
PROVES    a real signal from real closed candles reached a paper order under the frozen
          fill model; a position existed and closed with realised PnL; the ledgers agree;
          event-time replay reproduces the decisions; no execution was duplicated;
          paper-only authority held for the cohort's whole life.
DOES NOT  anything about edge, profitability or expectancy (n = 1 credited lifecycle);
PROVE     live fill quality; regimes other than the one observed; controlled-live
          readiness; host-loss survival of the evidence.
```

The registry row FP-CONTROL-3 is `CLOSED` (closed_utc 2026-10-24T21:37:57Z), and
`fp_run_active = false`. The T0, cohort id and source identity are unchanged. They are history,
and no record of this cohort may be credited to any successor. P3 does not start automatically.
H1 entry becomes eligible from this merged record, but H1 still needs its own launch
authorization.

```text
PAPER / RESEARCH ONLY
REAL_MONEY_AUTHORIZED = NO
```
