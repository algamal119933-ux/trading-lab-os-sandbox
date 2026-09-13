# The pre-T0 successor control instance

**Repairs:** the structural block at activation-pack step A11 on the native
Ubuntu host.
**Does not create:** a T0, a cohort, a cohort id, or any prospective evidence.

## The block

FP-CONTROL-1 is `CLOSED`. Its registry row still carried the only runnable
runtime identity in the repository, and the capture loop resolved cohort id and
T0 from whatever row matched the role — so starting a runtime for host
qualification would have stamped `FP-CONTROL-1-20260908T121513Z` and a `POST_T0`
relation, against a spent T0, onto brand-new records. That is the splice the
closure record forbids, and no later check could unpick it.

## The repair, in full

One additional registry row, and selection that refuses everything else.

```text
FP-CONTROL-2   status NOT_STARTED
               t0_utc null          cohort_id null      source_commit null
               bot_name     fp-control-2
               db_path      /freqtrade/user_data/fp-control-2/tradesv3.sqlite
               log_path     /freqtrade/user_data/fp-control-2/logs/freqtrade.log
               evidence_dir /freqtrade/user_data/fp-control-2/evidence
```

It is **not a cohort**. It is the state FP-CONTROL-1 itself occupied before
2026-09-08: a registered instance with no T0, whose captured bars read
`T0_NOT_FROZEN` and are qualification evidence, never prospective evidence.

`research/fp/capture.py` gains `select_instance()`, which fails closed on an
unknown role, a duplicated role and a `CLOSED` row, and
`assert_paths_are_exclusive()`, which refuses a runtime about to write into
another instance's declared paths. There is no default row and no first-row
fallback: `--role` is required on the capture CLI, `scripts/fp_instance.py`
resolves it in one place, and `scripts/start_fp_control.sh FP-CONTROL-2` /
`scripts/stop_fp_control.sh FP-CONTROL-2` take it explicitly. The compose
overlay is rendered from that selection and checked against it before the stack
starts.

`research/fp/admission.py` now excludes **every** control role from candidate
identification rather than one role literal. Without that, registering a second
control would have made a control look like an identified candidate and let its
records answer candidate-scoped conditions 1-6 — the exact hazard that function
was written to prevent. Conditions 1 and 2 carry the same fix.

## What cannot happen

| | |
| --- | --- |
| capture against the closed instance | refused — `CAPTURE_REFUSED`, exit 5, no ledger opened |
| the successor inheriting T0 or cohort id | both null, and the loop has no registry write path |
| qualification creating a T0 or a cohort id | impossible: T0 is read, never written |
| writing into the closed instance's paths | refused by path exclusivity, including nested paths |
| unknown or ambiguous role | hard failure before any file is touched |
| a control being read as a candidate | excluded by role prefix; admission stays `BLOCKED` |

`tests/test_fp_successor_instance.py` carries a negative control for each row
above, plus assertions that the closed instance's recorded truth, the Dataset V2
lock and the parked research branch are all unchanged.

## Unchanged

```text
FP-CONTROL-1     CLOSED, t0_utc 2026-09-08T12:15:13Z, cohort FP-CONTROL-1-20260908T121513Z,
                 outcome and change_log untouched, paths never reused
fp_run_active    false          entry_state C          paper_alpha_cohort NONE
PAPER_ADMISSION  BLOCKED        Dataset V2 lock  frozen and untouched
NEW T0           OWNER ONLY     REAL_MONEY_AUTHORIZED  NO
```
