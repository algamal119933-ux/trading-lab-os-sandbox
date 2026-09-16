# P1 — closure record

**Stage:** `P1 — HOST RECONSTITUTION`
**Qualification source commit:** `4543d4c330ed7a11c442e9b2ef78a23ac12cea40`
**Environment:** native Ubuntu host, Docker Engine, public market route only.

The qualification commit is the identity that matters here: it is the single
commit every authoritative runtime record resolves to. This record reaches main
by merge afterwards, so it cannot name the commit that carries it — the lineage
below does that instead.

P1 restored this host to a state where a **pre-T0 qualification runtime** can be
started, proven and stopped without touching the closed cohort's history. It
establishes that the machinery works. It establishes nothing about the strategy:
no edge, no profitability, no forward-paper result, no live readiness.

## Lineage

| | |
| --- | --- |
| PR #12 | merged as `9f8102d46ad6b95afaf2a009cd625c60532c5c43`, two parents `dc0792aa` + `17f36eb9` |
| PR #13 | merged as `4543d4c330ed7a11c442e9b2ef78a23ac12cea40`, two parents `9f8102d4` + `ef91d4c2` |
| accepted heads | `17f36eb9` and `ef91d4c2` are both ancestors of main |
| CI on merged main | run `35063688242` on `4543d4c3` — green |
| parked research | `19d7d7e` is **not** an ancestor of main |

## Gate results

| Gate | Result | Evidence |
| --- | --- | --- |
| Merged-main re-ground | **PASS** | `main == origin/main`, worktree clean, both merges normal two-parent commits |
| Pre-runtime acceptance | **PASS** | `679 passed, 8 skipped`; `REPO_CHECK_PASS (143 tracked files)`; `PAPER_GUARD_PASS` on the example and the runtime config; both registry schemas valid; `git diff --check` clean |
| Dataset V2 | **PASS** | `DATASET_LOCK_GATE = PASS (content matches the frozen lock)`; lock file identical to pre-P1 main; not reacquired, not rewritten |
| Lane selection | **PASS** | closed role refused (`FP_SELECTION_FAIL`), unknown role refused, unselected compose render refused, `FP_OVERLAY_PASS` on the selected render |
| A11 runtime qualification | **PASS** | below |
| A12 restart / persistence / no-duplicate | **PASS** | below |
| A13 runtime-attached preflight | **PASS** | 16/16 checks, `--require-pass` exit 0 |
| Reconciliation | **PASS** | 13/13 findings, exit 0 |
| Observability | **PASS** | exporter up, Prometheus scrape healthy, `freqtrade_api_up = 1` |
| Safe end-state | **PASS** | 0 containers, no orphan writer, evidence retained |

## A11 — the engine actually ran

Started through `scripts/start_fp_control.sh FP-CONTROL-2`, which refuses before
touching anything if selection, identity, lane containment, the rendered mount
graph or the tracked tree disagree with the registry.

```text
services              6/6 running; engine state "running", /api/v1/ping -> pong
dry_run               true          trading_mode spot        stake 10 USDT
bot_name              fp-control-2  strategy BaselineEmaRegimeV1   timeframe 1h
max_open_trades       2             stake_currency USDT
config_sha256         d1d078c63adc…  matches the frozen registry row
strategy_sha256       8c0bc6c5f705…  matches the frozen registry row
source_commit         4543d4c330ed7a11c442e9b2ef78a23ac12cea40
db / logs / evidence  /freqtrade/user_data/fp-control-2/{tradesv3.sqlite,logs,evidence}
```

Isolation, read from the live containers rather than from the compose file:

```text
writable host mounts  exactly one path, the fp-control-2 lane (engine and capture)
                      the other writable mounts are the monitoring stack's own named volumes
user_data             mounted read-only
fp-control-1          0 references in any mount or environment of any service
symlinks in the lane  0
exchange credentials  no exchange key/secret variable in the engine environment
```

Market truth, over 1998 captured candles:

```text
source        binance:spot:public-rest:klines   pairs BTC/USDT, ETH/USDT   1h
closed        every candle closed                no future data (close < now)
ordering      source timestamp <= receive timestamp on every record
attribution   role FP-CONTROL-2, cohort_id null, t0_relation T0_NOT_FROZEN
```

`T0_NOT_FROZEN` is the point: these are qualification records, not prospective
evidence, and the runtime has no path that could write a T0.

## A12 — restart, persistence, no duplicates

Stopped and restarted through the governed scripts at the same commit, with
nothing committed in between.

```text
runs            2 (run_started seq 0 and 1), restart counters [0, 1]
chains          all four verify from genesis after the restart
records         1998 inputs / 1998 decisions before and after — the restart
                re-captured nothing and re-decided nothing
database        preserved, 94208 bytes, same declared path
identity        one (source_commit, role, config, strategy) tuple across all evidence
fallback        no FP-CONTROL-1 path was opened, read or written at any point
```

## A13 and reconciliation

`research/fp/preflight.py` attached to the running instance with the market
route enabled: **16/16 PASS**, `--require-pass` exit 0,
`FP_RUNTIME_READINESS = PASS`. Checks that previously read `UNPROVEN` for want
of a runtime — real-data ingestion, monitoring liveness, duplicate-instance
exclusion, clock skew, the restart drill — now pass on observed behaviour.

`research/fp/reconcile.py --role FP-CONTROL-2 --require-pass`: **13/13 PASS**
over 3999 live records, including `record_source_commit` (one commit, matching
the repository), `event_time_replay` (the frozen logic reproduces every recorded
decision), `restart_continuity` and `paper_only_authority`.

Evidence fingerprints at closure:

```text
input     1998   tip 566e86c8bb7f83eb
decision  1998   tip 27f95df081f7db22
incident     3   tip 762de6ee71656968
trade        0   tip 0000000000000000
daily_pack_digest fa347aa5d9084777…
```

The lane itself stays on the host and out of Git, like every other evidence
lane. The digests above are what a later reader checks it against.

## What P1 changed, and why

Three defects were found by running the system rather than by reading it, and
each is worth recording because each looked like something else first:

* **Safe I/O was a call-site convention.** `write_runtime_state` followed a
  symlink planted at `capture_runtime.json`; aimed at the cohort registry, it
  truncated the registry. The evidence lane now owns its I/O through a held
  directory descriptor with pinned `(st_dev, st_ino)` identity, so containment
  and identity are properties of the lane rather than habits of its callers.
* **The stamped source commit was never checked.** Every record names the commit
  it was written from; nothing compared that to anything. Reconciliation now
  does, reading git directly rather than through the environment variable the
  runtime itself supplies.
* **The engine could not start under its own isolation.** Freqtrade creates
  missing `user_data` sub-directories at startup and that mount is read-only by
  design, so it crash-looped while the capture side ran on happily — "the stack
  came up" and "the engine is running" were not the same statement. The
  directories are provisioned before start; the mount was not loosened.

## Authority state at closure

```text
NEW_T0_CREATED          NO     t0_utc remains null
NEW_COHORT_CREATED      NO     cohort_id remains null
FP-CONTROL-2            NOT_STARTED, source_commit null, fp_run_active false
FP-CONTROL-1            CLOSED, registry row byte-identical to pre-P1 main,
                        historical T0 2026-09-08T12:15:13Z and cohort
                        FP-CONTROL-1-20260908T121513Z untouched, lane not reused
P2_STARTED              NO
REAL_MONEY_AUTHORIZED   NO     dry_run true throughout, no live execution route
19d7d7e                 parked, not an ancestor of main
CODEX_REQUIREMENT       NOT REQUIRED — OWNER AMENDMENT
```

The Codex verifier was removed from the P1 closure path by Owner amendment, and
no substitute AI verifier replaced it. P1's final verification basis is the
deterministic repository gates, clean-checkout reproducibility, CI, the retained
single-provenance runtime evidence and its replay, and the governance invariants
above — each of which is reproducible by a later reader without asking any model
what it thought.

`preflight` reports `T0_PERMITTED = YES`. P1 deliberately does not take it:
freezing a T0 and opening a cohort is an Owner decision with no script in this
repository, and qualification evidence is not a cohort.

## What this record does not claim

No prospective edge. No profitability. No forward-paper result. No Paper Beta
acceptance. No controlled-live readiness. P1 says one thing: this host can run,
restart, prove and stop a pre-T0 qualification instance whose evidence is
attributable to exactly one commit, one role and one lane.
