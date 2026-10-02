# FUNNEL-LAW-1 — the frozen Cycle-2 funnel law (CYCLE-2 UNIT 7.2 PART A)

**Authority:** research/OFFLINE_RESEARCH_CYCLE_2_OPENING_1.md §3 (caps), §4 (funnel), §6.1–6.3, §7.2;
Master Plan §12 NULL / NEGATIVE CONTROL LAW; research/cycle2/TRIALGATE_AUDIT_1.md (ADOPT_VALIDATION_ONLY);
research/mean_reversion/PREREGISTRATION.md "Falsification conditions (frozen)" and "Survivor conditions"
(the Cycle-1 frozen law, reused unchanged). Owner, 2026-10-01: "Prepare 7.2"; funnel law = RECOMMENDED.
**Classification:** governance record. It executes nothing.
**Status:** FROZEN. Every Cycle-2 preregistration binds this file by path and sha256
(`funnel_law` in research/cycle2/prereg.schema.json). Changing any word or value below requires a new
Owner record and a new law file; this one is never edited.

## Applicability

The law applies to every Cycle-2 trial, calibration and scientific alike: the two null-recalibration
trials of §7.2 and every later Trend or Mean-Reversion trial. It applies per preregistration and per
lineage. It is evaluated only by research/cycle2/funnel.py, which is pure and deterministic, reads the
trial ledger read-only, and never writes it. The family configuration count N is derived only by
research/cycle2/config_n.py.

## The law (verbatim)

```text
Applies to every Cycle-2 trial (calibration and scientific). Per preregistration, per lineage.
L1 WALK_FORWARD (Cycle-1 frozen law, unchanged):
   selected config's EVAL return < 0 in ALL folds              → REJECTED
   any EVAL fold trade_count < 10 → that fold INSUFFICIENT; all folds INSUFFICIENT → INCONCLUSIVE
   otherwise WALK_FORWARD = PASS only if aggregate EVAL return (sum over folds) > 0, else FAIL → REJECTED
L2 COST_STRESS: any stress fee level flips the sign of aggregate EVAL return → COST_STRESS = FAIL
   (weighed under the survivor law: a FAIL here blocks SURVIVED)
L3 MULTIPLE_TESTING (trialgate validation via research/cycle2/multiple_testing.py only):
   DSR ≥ 0.95 with N = family_configuration_N (below); PBO ≤ 0.05 with pbo_block_count from the prereg.
   NOT_EVALUABLE (e.g. PBO with a single configuration) is never PASS and blocks SURVIVED.
   Upstream selection debt that cannot be observed (candidate_registry.json multiple_testing_accounting)
   is DISCLOSED verbatim beside every DSR/PBO figure, never silently folded into or dropped from N.
N LAW (OPENING-1 §3: "cumulative family N"):
   family_configuration_N = number of DISTINCT tested configuration identities in the family, across
   cycles, including the configurations of the trial being evaluated.
   Identity = sha256 of canonical JSON {strategy file sha256, sorted fixture/schedule sha256s, canonical
   params}. Re-running an identical configuration is NOT a new configuration (candidate_registry:
   "re-evaluating one frozen configuration is not an additional trial"). Robustness neighbours and
   regime-gated variants ARE configurations (OPENING-1 §3).
   Trial-ID count is NOT N. research/trial_ledger.py stays canonical for trial IDs/accounting only.
   Sources, in order: (a) Cycle-1 per-family configuration counts from RESEARCH_CYCLE1_CLOSURE_1.md
   (frozen table in code, pinned by that file's sha256; mismatch → refuse); (b) Cycle-2 grids of every
   preregistration bound in the ledger for that family. Any configuration whose identity cannot be
   resolved → N = NOT_EVALUABLE → DSR NOT_EVALUABLE (never a guessed or smaller N).
   For PIPELINE_NULL_CALIBRATION: Cycle 1 tested 2 null designs; Cycle 2 reuses the same 2 byte-identical
   fixtures, so the expected N is 2 (proved by test, not assumed).
PBO DISCLOSURE: with one configuration per null, PBO is NOT_EVALUABLE. The null controls do NOT
   validate PBO, and no record may claim they do. PBO's first real exercise is a multi-config trial.
NULL SEQUENCING LAW:
   Order: TRIAL-C2-NULL-MATCHFREQ-1 first, then TRIAL-C2-NULL-BLOCKSHUF-1.
   Null #2 executes only if the ledger holds null #1's terminal record with state REJECTED.
   Ledger mapping: funnel REJECTED → REJECTED; SURVIVED → SURVIVED; INCONCLUSIVE → COMPLETED with
   outcome.funnel_result = INCONCLUSIVE (the ledger has no INCONCLUSIVE state).
   Null #1 SURVIVED or INCONCLUSIVE → Cycle 2 STOP immediately; null #2 is never dispatched.
   No dangling preregistration: at closure, any preregistered-but-not-run trial gets terminal ABORTED
   with outcome {reason: NOT_RUN_CYCLE2_STOP, engine_invocations: 0}.
L4 PARAMETER_ROBUSTNESS: NOT_APPLICABLE only for lineage_kind NULL_CALIBRATION (no parameters);
   otherwise required, per the trial's preregistration.
SURVIVED ⇔ every applicable gate PASS (DATA_TRUTH, LOOKAHEAD, RECURSIVE where applicable, LEDGER_CHAIN,
   WALK_FORWARD, PARAMETER_ROBUSTNESS, COST_STRESS, MULTIPLE_TESTING) and SAMPLE_EVIDENCE = SUFFICIENT.
   Any gate FAIL → REJECTED. Anything else unresolved → INCONCLUSIVE. Never rounded up.
NULL CALIBRATION VERDICT (lineage_kind NULL_CALIBRATION only):
   null REJECTED → CALIBRATION = PASS
   null SURVIVED → CALIBRATION = FAIL → Cycle 2 STOP
   null INCONCLUSIVE → CALIBRATION = NOT_PROVEN → Cycle 2 STOP (fail-closed; UNPROVEN blocks as FAIL)
Thresholds above are the only ones; no defaults anywhere; changing any requires a new Owner record.
```

## Where each part is enforced

| part | enforced by |
|---|---|
| L1–L4, SURVIVED, calibration verdict, ledger mapping | research/cycle2/funnel.py (derived, non-authoritative output; never writes the ledger) |
| N LAW | research/cycle2/config_n.py (closure-record sha256 pin; ledger read-only) |
| NULL SEQUENCING LAW (execution side) | research/cycle2/driver.py refuses a real run before any engine call |
| thresholds | each preregistration's `multiple_testing` block; no code default exists |
| terminal and ABORTED records | the operator's own ledger appends (research/trial_ledger.py), never this tooling |

## Relationship to TRIALGATE-AUDIT-1

TRIALGATE_AUDIT_1.md stated that `effective_trials` must be "at least `ledger_family_trial_count`" (a count of
trial IDs). The N LAW above is the Owner's later, specific rule for Cycle 2: N counts distinct configuration
identities, and the trial-ID count is not N. The audit record is not edited; this law governs where they
differ.
