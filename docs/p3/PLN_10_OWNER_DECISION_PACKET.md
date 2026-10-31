# P3-PLN-10 — Owner decision packet D1–D5 (preparation only; nothing chosen)

**Authority:** [`PLN_10_PAPER_BETA_ACCEPTANCE_PROGRAM.md`](PLN_10_PAPER_BETA_ACCEPTANCE_PROGRAM.md) §8 and
`OWNER_DECISIONS` / `validate_run_config` in `research/p3/acceptance.py`.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCH_AUTHORIZED = NO · PAPER_LAUNCH_AUTHORIZED = NO

**Status: DECISIONS_OPEN = D1, D2, D3, D4, D5. No value is chosen here.** This packet lists options, their
consequences and what the validator requires. The Owner records the choices in `docs/p3/PLN_10_RUN_CONFIG.json`, in the
Owner's own PR. That file does not exist, and until it validates the program is `LAUNCH_BLOCKED`. Choosing values does
not launch anything: the launch is the Owner's act under the record that D5 cites.

The Owner also sets two identity fields that are not numbered decisions: `run_id` (a new id per run; evidence never
carries over between runs) and `frozen_commit` (the 40-hex commit the host is frozen at for the whole window).

## D1 — approved paper runtime (`paper_runtime`)
| Option | Consequence |
|---|---|
| A. H1-PAPER-COHORT-1 (`tlos-h1-paper-cohort-*`) | Needs its own `H1_LAUNCH_AUTHORIZATION` record (today `H1_LAUNCH_AUTHORIZED = NO`) and the H1 package. The acceptance run then also starts the H1 research cohort, so a PLN-10 FAIL or abort and an H1 outcome share one window |
| B. A new governed paper cohort under `tradinglab-fp-control-*` (never FP-CONTROL-3) | Needs its own Owner authority record and registry row, with an existing governed strategy and risk (no change). Keeps Beta acceptance separate from research |
| C. Defer | PLN-10 stays `LAUNCH_BLOCKED`; P3 cannot close (contract §8) |

Validator requires: `runtime_id` is a string inside the kill switch's scope (`tradinglab-fp-control-*`,
`tlos-h1-paper-cohort-*`) and not FP-CONTROL-3; `authority_record` is set; `authority_merge` is a 40-hex commit;
top-level `dry_run` is literally `true` and `real_money_authorized` literally `false`.

## D2 — trial duration (`trial_window`)
| Option | Consequence |
|---|---|
| Short window (days) | Fits the scheduled scenarios (S-INV, S-RESTORE, S-KILL/S-RESTART, S-REBOOT, S-ALERT, S-TIER3, S-UI). Risk: `PLN-06.normal_end_detected` and `PLN-10.pnl_reconciles` need at least one **completed** trade lifecycle; without one they stay MISSING and the run is NOT_ACCEPTED |
| Window sized to reach a lifecycle | Historical reference only: FP-CONTROL-3 needed T0 2026-09-24T12:00Z → close 2026-10-24T21:38Z (about 30 days) for its first natural lifecycle. Longer windows keep the host frozen longer (PLN-04 host-freeze rules, decision H) |
| Window that outlives the P3 authorization | Refused by the validator |

Validator requires: `start_utc` ISO-8601 Z; `duration_hours` a positive finite number (not a string, not a bool); the
window ends no later than `EXPIRES_UTC` of `OWNER_P3_EXECUTION_AUTHORIZATION.md` (2027-01-31T23:59:59Z). Evidence
records outside the window never count (`run_verdict`).

## D3 — emergency-stop bound (`emergency_stop_bound_s`)
| Option | Consequence |
|---|---|
| Near the measured drill (PLN-08 drill: 0.162 s) | Proves a fast stop, but a container that uses its stop grace period under load turns S-KILL into a FAIL and forces a new run |
| Equal to the kill switch's own per-container stop timeout (`DEFAULT_TIMEOUT_S` = 30 s) | Matches what the mechanism guarantees; a stop within the grace period passes |
| Above 30 s | Accepts a slower stop than the mechanism is configured for; weaker evidence |

Validator requires: a positive, finite number of seconds (not a string, not a bool). `kill_switch_bounded` also FAILs a
record whose `elapsed_s` is missing, negative or not finite.

## D4 — acceptance criteria (`acceptance_criteria`)
| Item | Options and consequence |
|---|---|
| `matrix_sha256` | Only one valid value: `matrix_digest()` computed **at `frozen_commit`**. The digest changes whenever the matrix changes (round 3 added `owner` and `stop_condition` to every row), so it is computed at the chosen commit, never copied from an older one |
| `criterion_ids` | Only one valid value: every matrix id (19 today). A subset is a waiver and is refused (contract §8) |
| `pnl_tolerance_quote` | `"0"`: exact Decimal comparison; any rounding in the reported value becomes a FAIL. A quote-precision tolerance (for example `"0.00000001"`): absorbs representation only. A larger tolerance: at the historical 10 USDT stake and a 0.1 % fee, one fee leg is about 0.01 USDT, so a tolerance at or above that size could let a missing fee pass. Measurement only; it says nothing about profitability |

Validator requires: `matrix_sha256` 64-hex and equal to `matrix_digest()`; `criterion_ids` a list equal in content to
the matrix ids; `pnl_tolerance_quote` a decimal **string**, finite and ≥ 0 (no float, no placeholder).

## D5 — explicit launch authority (`launch_authority`)
| Option | Consequence |
|---|---|
| A. A dedicated Owner record authorizing this PLN-10 paper run | Scoped to the acceptance run only; the P3 execution authorization stays non-launching |
| B. For an H1 runtime (D1 A): its `H1_LAUNCH_AUTHORIZATION` record | Required by the validator for H1; it also authorizes the H1 research cohort |
| C. Withhold | `paper_launch_authorized` stays `false`; `LAUNCH_BLOCKED` |

Validator requires: `granted_by` is exactly `Owner`; `paper_launch_authorized` is literally `true`; `record_path` is a
`.md` record that is not `OWNER_P3_EXECUTION_AUTHORIZATION.md` (and contains `H1_LAUNCH_AUTHORIZATION` for an H1
runtime); `merge_commit` is the 40-hex Owner merge commit.

## How the validator treats an unset or defaulted decision
A missing key, `null`, a placeholder (`TBD`, `default`, `<…>`, …), a template value, a string where a number is
required, `0`, a negative or a non-finite number keeps the decision open. Each decision left at its template value
blocks exactly that decision (`launch_readiness(...)["open_owner_decisions"]`), and `run_verdict` is `NOT_ACCEPTED`
whenever any decision is open. Tests: `tests/test_p3_acceptance.py`.

## Not claimed
No decision is made, no run configuration exists, nothing is launched, and no profitability claim is made.
