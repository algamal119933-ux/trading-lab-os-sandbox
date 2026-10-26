"""What each P2 stage's diff changed, and what no P2 branch may ever change.

A stage contract is only as good as the diff it actually produced, so the audit
is made executable: every changed path is listed against the requirement it
satisfies, and the map is compared against git in both directions, so a file
that arrives without a reason fails the suite and deleting an entry is not a way
past it.

The file is in three layers, and the split is the repair of a defect this audit
had against itself.

``MERGED_STAGE_SCOPES`` pins each closed stage to **its own merge range**. The
first version of this file audited "whatever this branch changes against main",
which is the right question on a branch and an unanswerable one afterwards: the
moment S2 merged, the branch's diff against main became empty, all forty map
entries read as stale, and CI on main failed on the very audit that had just
passed on the PR. A range that names two commits does not decay.

``BRANCH_SCOPE`` audits the stage currently in flight the same way, against the
merge base. When there is no branch — merged main, where HEAD *is* the merge
base — the both-directions comparison has no domain, and the tests prove that
condition rather than skipping on it.

The negatives are the third layer, and they are split by what they are about.
Those that describe a closed stage are asserted over that stage's pinned range.
Those that must hold for every P2 branch until the Owner freezes a T0 are
asserted live, against the merge base and the working tree.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from fp import capability as fp_capability  # noqa: F401  (import proves it loads)

PARKED_BRANCH = "19d7d7e76831a44c0c3ee643e2cebe7979f456f0"

# PR #17, merged. Two parents: e80be32e (main before) + 480d8039 (the branch).
S2_MERGE = "2b96dbde0af745dc68db0c191b73f116e0a7b173"

# Every path S2 touched → the S2 requirement it satisfies.
# Contract section 13 lists the requirements; the right-hand side names one.
S2_SCOPE: dict[str, str] = {
    # -- the mechanisms -----------------------------------------------------
    "research/fp/semantic_identity.py": "semantic-equivalence tooling",
    "scripts/prove_semantic_equivalence.py": "semantic-equivalence tooling",
    "research/fp/registry_law.py": "RUNNING/T0 correspondence",
    "research/fp/archive.py": "archive_fp_lane tooling / Tier-1 archival",
    "scripts/archive_fp_lane.py": "archive_fp_lane tooling / Tier-1 archival",
    "scripts/publish_evidence_digest.py": "Tier-2 digest publication",
    "research/fp/records/evidence_digest_publication.json": "Tier-2 digest publication",
    "research/schema/evidence_digest_publication.schema.json": "Tier-2 digest publication",
    "scripts/seal_pre_t0_qualification.py": "pre-T0 qualification sealing",
    "research/schema/p2_qualification_binding.schema.json": "pre-T0 qualification sealing",
    "scripts/freeze_t0.py": "freeze_t0 implementation",
    "scripts/validate_activation.py": "activation validation",
    "scripts/fp_watch.py": "continuity/stall watch tooling",
    "scripts/check_freeze_candidate.py": "CI freeze-candidate guards",
    "scripts/second_device_discovery.py": "durability policy — second-device availability",
    "scripts/replicate_to_second_device.py": "durability policy — append-only second-device copy",
    "research/fp/capability.py": "property model — one source for the twelve",
    # -- corrections to existing modules ------------------------------------
    "research/fp/reconcile.py": "registry/source-commit equivalence reconciliation",
    "research/fp/preflight.py": "the preflight correction (check 5 names its refusals)",
    "research/fp/capture.py": "activation validation — the activation_gap incident",
    # -- governance and integrity -------------------------------------------
    "docs/p2/P2_CONTRACT.md": "property model — the corrected 9 + 3 = 12",
    "docs/p2/S2_PRE_T0_IMPLEMENTATION.md": "S2 stage record",
    ".github/workflows/ci.yml": "CI freeze-candidate guards",
    ".gitignore": "Tier-1 archival — disposable test lanes, narrowed to a test namespace",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
    # -- tests ---------------------------------------------------------------
    "tests/test_p2_semantic_identity.py": "negative/adversarial controls",
    "tests/test_p2_registry_law.py": "legitimate RUNNING/T0 correspondence tests",
    "tests/test_p2_archival.py": "negative/adversarial controls",
    "tests/test_p2_freeze_t0.py": "negative/adversarial controls",
    "tests/test_p2_activation.py": "negative/adversarial controls",
    "tests/test_p2_watch_and_seal.py": "negative/adversarial controls",
    "tests/test_p2_freeze_candidate.py": "CI freeze-candidate guards",
    "tests/test_p2_contract_invariants.py": "negative/adversarial controls",
    "tests/test_p2_capability_model.py": "property model invariants",
    "tests/test_p2_gitignore_boundary.py": "gitignore boundary audit",
    "tests/test_p2_reconciliation_version.py": "reconciliation version audit",
    "tests/test_p2_scope_audit.py": "PR scope audit",
    "tests/test_p2_durability_policy.py": "Owner amendment 1 — durability policy",
    "tests/test_p2_window_law.py": "Owner amendment 2 — P2 window law",
    "CLAUDE.md": "durability policy — the Tier-3 return trigger is superseded",
}

# PR #18, merged. Two parents: 2b96dbde (main before) + a887fa93 (the branch).
S3_MERGE = "d6b1eeb3fd5995e69b3e31ab6d21807af5b9ec5b"

# Every path S3 / S3b touched → the requirement it satisfies. These entries were
# BRANCH_SCOPE while the stage was in flight; they move here on the merge, where
# they stop depending on which branch is checked out.
S3_SCOPE: dict[str, str] = {
    "tests/test_p2_scope_audit.py": "S3 — the scope audit is pinned to ranges so it cannot decay",
    "research/fp/records/evidence_digest_publication.json": "S3 — Tier 2, the sealed lanes' digests",
    "scripts/seal_pre_t0_qualification.py": "S3 — the seal must attach the live runtime, not only refuse",
    "tests/test_p2_watch_and_seal.py": "S3 — the seal is proven able to succeed, not only to refuse",
    "tests/test_p2_archival.py": "S3 — Tier 2 tests must survive Tier 2 being used",
    "research/fp/records/p2_qualification_binding.json": "S3b — the class-O binding of Mq and the certificate",
    "tests/test_p2_qualification_binding.py": "S3b — the binding's claims are recomputed, not trusted",
    "docs/p2/S3_LIVE_PRE_T0_QUALIFICATION.md": "S3 / S3b stage record",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}

# PR #19, merged. Two parents: d6b1eeb3 (main before) + 4e058f08 (the branch).
S4_MERGE = "19301eb4c943f084b1d91bdf53312174c7b3cd7e"

# Every path S4 touched → the requirement it satisfies.
S4_SCOPE: dict[str, str] = {
    "docs/p2/OWNER_T0_AUTHORIZATION.md": "S4 — the Owner's merged T0 authorization record",
    "tests/test_p2_scope_audit.py": "S4 — S3 pinned to its merge range; the absence of an "
                                    "authorization stops being asserted as law",
    "tests/test_p2_freeze_t0.py": "S4 — the authority controls construct the absence they need",
    "tests/test_p2_qualification_binding.py": "S4 — the binding's claim is separated from the "
                                              "authorization's existence",
    ".github/workflows/ci.yml": "S4 — the authority gate proves the boundary in both states",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}

# PR #26, merged. Two parents: 66ec5da2 (main before) + b7f8f992 (the branch).
RECOVERY_MERGE = "909bf5fa551e9cb4351de6eb40cc42f9cbe28cbd"

# Every path the recovery transaction touched → the requirement it satisfies.
# These entries were BRANCH_SCOPE while it was in flight.
RECOVERY_SCOPE: dict[str, str] = {
    "research/fp/preflight.py": "recovery — the restart drill moves to the lifecycle point "
                                "where it can be true; nothing deleted",
    "scripts/validate_activation.py": "recovery — the validator can attach the runtime it validates",
    "research/schema/forward_paper_cohort_registry.schema.json":
        "recovery — one successor control role, FP-CONTROL-3",
    "research/fp/records/forward_paper_cohort_registry.json":
        "recovery — FP-CONTROL-2 closed class B; FP-CONTROL-3 created NOT_STARTED",
    "research/fp/records/evidence_digest_publication.json":
        "recovery — Tier 2 digest of the sealed FP-CONTROL-2 cohort lane",
    "docs/p2/FP_CONTROL_2_COHORT_CLOSURE.md": "recovery — the cohort closure record",
    "docs/p2/OWNER_REPLACEMENT_AUTHORIZATION.md": "recovery — the bounded replacement grant",
    "docs/p2/P2_RECOVERY.md": "recovery — what this transaction is and why it is one",
    ".gitignore": "recovery — the successor lane, listed literally",
    ".github/workflows/ci.yml": "recovery — the overlay render names the runnable control",
    "tests/conftest.py": "recovery — the default runnable control is the successor",
    "tests/test_p2_activation.py": "recovery — positive and negative initial-activation controls",
    "tests/test_fp_capture.py": "recovery — repointed to the runnable control",
    "tests/test_fp_lane_adversarial.py": "recovery — repointed to the runnable control",
    "tests/test_fp_lane_io_adversarial.py": "recovery — repointed to the runnable control",
    "tests/test_fp_overlay.py": "recovery — repointed to the runnable control",
    "tests/test_fp_successor_instance.py": "recovery — repointed, and the row selected by role",
    "tests/test_p2_window_law.py": "recovery — repointed to the runnable control",
    "tests/test_p2_gitignore_boundary.py": "recovery — fp-control-3 declared; fp-control-4 undeclared",
    ".github/gates/check_t0_authority.py": "recovery — entering RUNNING is a freeze; "
                                           "leaving it for CLOSED is a closure",
    "tests/test_p2_freeze_t0.py": "recovery — a closed row is a lawful third state",
    "tests/test_p2_scope_audit.py": "recovery — this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}

# PR #27, merged. Two parents: 909bf5fa (main before) + 58e27f2f (the branch).
S8_MERGE = "e6fa7eebe37592d982ca5c09066e84cd32465e71"

# Every path S8 touched → the requirement it satisfies. These entries were
# BRANCH_SCOPE while the stage was in flight.
S8_SCOPE: dict[str, str] = {
    "research/schema/p2_qualification_binding.schema.json":
        "S8 — the binding may name the successor control",
    "research/fp/records/p2_qualification_binding.json":
        "S8 — the class-O binding of the fresh Mq and certificate",
    "tests/test_p2_qualification_binding.py":
        "S8 — the binding's claims are recomputed against the run that produced them",
    "research/fp/records/evidence_digest_publication.json":
        "S8 — Tier 2 digest of the sealed FP-CONTROL-3 qualification lane",
    "research/schema/evidence_digest_publication.schema.json":
        "S8 — the publication may name the successor control",
    "tests/test_p2_t0_authority_gate.py":
        "S8 — the gate's controls are driven at the role actually under authority",
    "tests/test_p2_freeze_t0.py":
        "S8 — the live authorization assertion checks agreement, not a fixture's cohort name",
    "docs/p2/OWNER_T0_AUTHORIZATION.md":
        "S8 — the Owner's T0 authorization for the successor control",
    ".github/gates/check_t0_authority.py":
        "S8 — the gate judges the role under authority, not a hardcoded cohort",
    "docs/p2/S8_SUCCESSOR_QUALIFICATION.md": "S8 stage record",
    "tests/test_p2_scope_audit.py": "S8 — the recovery pinned to its merge range; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #28, merged. Two parents: e6fa7eeb (main before) + 575997dd (the branch).
S9A_MERGE = "83c49414cc9eaba9a4e25809672d65d032669616"

# Every path S9a touched → the requirement it satisfies. These entries were
# BRANCH_SCOPE while the stage was in flight.
S9A_SCOPE: dict[str, str] = {
    "tests/conftest.py":
        "S9a — the live role is resolved from the registry, not named",
    "tests/test_p2_registry_law.py": "S9a — repointed to the resolved live role",
    "tests/test_p2_watch_and_seal.py":
        "S9a — resolved live role, and the lane redirect derives its own segment",
    "tests/test_p2_freeze_t0.py": "S9a — repointed to the resolved live role",
    "tests/test_fp_admission.py": "S9a — the pre-T0 fixture is asked for by default",
    "tests/test_p2_scope_audit.py": "S9a — S8 pinned to its merge range; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}

# PR #29, merged. Two parents: 83c49414 (main before) + cc9688e4 (the branch).
# The T0 freeze transaction for FP-CONTROL-3. Its scope is not this file's
# ordinary branch map but contract section 6's exact pair, which is why it
# equals FREEZE_CANDIDATE_SCOPE below: a freeze that had changed anything else
# would have been refused by scripts/check_freeze_candidate.py before reaching
# main, and pinning it here says so permanently rather than by exemption.
S9B_MERGE = "3191285a28823907f62c6eb915327599cd6ed90b"

S9B_SCOPE: dict[str, str] = {
    "research/fp/records/forward_paper_cohort_registry.json":
        "S9b — the T0 freeze transaction, audited by scripts/check_freeze_candidate.py",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}

# PR #30, merged. Two parents: 3191285a (main before, M2) + 96feb8ed (the branch).
S9C_MERGE = "52e0d2bf7f05496a6adf10de318ed8061bd3fcd1"

S9C_SCOPE: dict[str, str] = {
    "docs/p2/S9C_ACTIVATION.md":
        "S9c — the contract section 6 activation record for FP-CONTROL-3 (M3)",
    "tests/test_p2_scope_audit.py":
        "S9c — S9a and S9b pinned to their merge ranges; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}

# PR #31, merged. Two parents: 52e0d2bf (main before, S9C_MERGE) + ddefa015 (the branch).
RUNTIME_RECON_0927_MERGE = "00d719ff6c6bf917b8f497793f300c733524d1e0"

# Every path the 2026-09-27 runtime reconciliation touched → the requirement it
# satisfies. These entries were BRANCH_SCOPE while it was in flight.
RUNTIME_RECON_0927_SCOPE: dict[str, str] = {
    "docs/p2/FP_CONTROL_3_RUNTIME_RECONCILIATION_2026-09-27.md":
        "runtime reconciliation — the two TRADING-STATE-RECONCILIATION-0 findings, "
        "plus the §1.2.2 timer-arming timestamp correction",
    "tests/test_p2_scope_audit.py":
        "runtime reconciliation — S9C pinned to its merge range; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}

# PR #32, merged. Two parents: 00d719ff (main before, RUNTIME_RECON_0927_MERGE) +
# 60f4d4e3 (the branch).
STAGE0_CLOSURE_MERGE = "15ce01becce9e771af75e0af9433aba5b0a90c81"

# Every path the Stage-0 closure (H1 evidence preservation + Restart #2
# reconciliation + the RUNTIME_RECON_0927 scope rollover) touched → the
# requirement it satisfies. These entries were BRANCH_SCOPE while it was in
# flight.
STAGE0_CLOSURE_SCOPE: dict[str, str] = {
    "docs/p2/FP_CONTROL_3_RUNTIME_RECONCILIATION_2026-09-29.md":
        "Stage-0 closure — the 2026-09-28T15:28Z restart (restart_counter 1->2) and "
        "the incident records since the 2026-09-27 reconciliation",
    "research/external/h1_evidence_preservation.json":
        "Stage-0 closure — H1 evidence preservation manifest, durable storage record "
        "and reproducibility classification",
    "tests/test_p2_scope_audit.py":
        "Stage-0 closure — the 2026-09-27 runtime reconciliation (PR #31) pinned to "
        "its merge range; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #33, merged. Two parents: 15ce01be (main before, STAGE0_CLOSURE_MERGE) +
# da1640e1 (the branch).
RESEARCH_FOUNDATION_UNIT_A_MERGE = "72105b2eaacd63d06c5cf27196c9d11e5a027ddb"

# Every path Unit A touched → the requirement it satisfies. These entries
# were BRANCH_SCOPE while it was in flight.
RESEARCH_FOUNDATION_UNIT_A_SCOPE: dict[str, str] = {
    "research/schema/trial_record.schema.json":
        "Research Foundation Unit A — the shape of one research-selection "
        "accounting record",
    "research/trial_ledger.py":
        "Research Foundation Unit A — enforced research-selection accounting: "
        "preregistration must precede any terminal outcome, per trial_id",
    "tests/test_trial_ledger.py":
        "Research Foundation Unit A — the seven attempt-accounting properties "
        "the ledger must hold",
    "tests/test_p2_scope_audit.py":
        "Research Foundation Unit A — the Stage-0 closure (PR #32) pinned to "
        "its merge range; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #34, merged. Two parents: 72105b2e (main before, RESEARCH_FOUNDATION_UNIT_A_MERGE) +
# 300c2314 (the branch).
RESEARCH_FOUNDATION_UNIT_B_MERGE = "4433120d46949786cc235c0cc8cfd7c3650c99f1"

# Every path Unit B touched → the requirement it satisfies. These entries
# were BRANCH_SCOPE while it was in flight.
RESEARCH_FOUNDATION_UNIT_B_SCOPE: dict[str, str] = {
    "research/null_controls/generate_schedules.py":
        "Research Foundation Unit B — deterministic, re-derivable generation of "
        "the two null-control entry schedules",
    "research/null_controls/NullControlMatchedFrequency.py":
        "Research Foundation Unit B — null control: matched-frequency random entries",
    "research/null_controls/NullControlBlockShuffled.py":
        "Research Foundation Unit B — null control: block-shuffled entries",
    "research/null_controls/null_matched_frequency_schedule.json":
        "Research Foundation Unit B — the frozen matched-frequency schedule",
    "research/null_controls/null_block_shuffled_schedule.json":
        "Research Foundation Unit B — the frozen block-shuffled schedule",
    ".github/workflows/null_control.yml":
        "Research Foundation Unit B — runs a null-control strategy through the "
        "same acquisition/lock-check/backtest/metrics steps extbench.yml uses",
    "research/records/trial_ledger.jsonl":
        "Research Foundation Unit B — the preregistered H1 controlled-derivation "
        "and null-control trials, and their outcomes",
    "tests/test_p2_scope_audit.py":
        "Research Foundation Unit B — Unit A (PR #33) pinned to its merge range; "
        "this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #35, merged. Two parents: 4433120d (main before, RESEARCH_FOUNDATION_UNIT_B_MERGE) +
# d1cf8942 (the branch).
RESEARCH_FOUNDATION_CLOSURE_1_MERGE = "30064e86a4ec05d27d5e5187596452499503b39e"

# Every path RESEARCH-FOUNDATION-CLOSURE-1 touched -> the requirement it
# satisfies. These entries were BRANCH_SCOPE while it was in flight.
RESEARCH_FOUNDATION_CLOSURE_1_SCOPE: dict[str, str] = {
    "research/OFFLINE_RESEARCH_AUTHORITY_1.md":
        "Gate 1 - the prospective sibling offline-research authority",
    ".github/workflows/null_control.yml":
        "Gate 2/2A - collect the full trade-level backtest result; drop the "
        "bootstrap push trigger",
    ".github/workflows/extbench.yml":
        "Gate 2 - collect the full trade-level backtest result, prospectively",
    "research/null_controls/generate_schedules.py":
        "Gate 3 - precompute each entry's matching exit candle",
    "research/null_controls/null_matched_frequency_schedule.json":
        "Gate 3 - regenerated with exits_utc",
    "research/null_controls/null_block_shuffled_schedule.json":
        "Gate 3 - regenerated with exits_utc",
    "research/null_controls/NullControlMatchedFrequency.py":
        "Gate 3 - exit mechanism corrected",
    "research/null_controls/NullControlBlockShuffled.py":
        "Gate 3 - exit mechanism corrected",
    "research/null_controls/__init__.py":
        "Gate 3 - makes research/null_controls importable for its own test",
    "tests/test_null_control_schedules.py":
        "Gate 3 - proves the corrected exit mechanism's schedule-level semantics",
    "research/records/trial_ledger.jsonl":
        "Gate 3 - the preregistered Attempt-3 null trials and their outcomes",
    "tests/test_p2_scope_audit.py":
        "Unit B (PR #34) pinned to its merge range; this branch's scope",
    "MANIFEST.txt": "repository integrity - regenerated after staging",
}


# PR #36, merged. Two parents: 30064e86 (main before, RESEARCH_FOUNDATION_CLOSURE_1_MERGE) +
# 44d14db0 (the branch).
MEAN_REVERSION_CYCLE1_MERGE = "fb2c8fb6738bd40296bf705a82373fd8e86d2514"

# Every path Mean-Reversion Cycle 1 touched -> the requirement it satisfies.
# These entries were BRANCH_SCOPE while it was in flight.
MEAN_REVERSION_CYCLE1_SCOPE: dict[str, str] = {
    "research/mean_reversion/PREREGISTRATION.md":
        "the frozen hypothesis, mechanism, parameter grid, walk-forward "
        "design, falsification and survivor conditions",
    "research/mean_reversion/MeanReversionZScore.py":
        "the rolling z-score mean-reversion strategy",
    "research/mean_reversion/run_walkforward.py":
        "the 2-fold x 4-config walk-forward campaign driver",
    ".github/workflows/mean_reversion.yml":
        "runs the walk-forward campaign; workflow_dispatch only",
    "research/records/trial_ledger.jsonl":
        "TRIAL-MR-ZSCORE-WF-1 and its REJECTED outcome",
    "tests/test_p2_scope_audit.py":
        "RESEARCH-FOUNDATION-CLOSURE-1 (PR #35) pinned to its merge range; "
        "this branch's scope",
    "MANIFEST.txt": "repository integrity - regenerated after staging",
}


# PR #37, merged. Two parents: 30064e86 (main before, RESEARCH_FOUNDATION_CLOSURE_1_MERGE) +
# TRIAL-MR-ZSCORE-WF-1's merge was PR #36; PR #37's first parent is that merge:
# fb2c8fb6 (main before, MEAN_REVERSION_CYCLE1_MERGE) + the h1-qualification branch.
H1_QUALIFICATION_MERGE = "0862ea3c7dd26265ccab6c45c264fda2d23d1198"

# Every path H1-Paper-Readiness-Qualification-1 touched -> the requirement it
# satisfies. These entries were BRANCH_SCOPE while it was in flight.
H1_QUALIFICATION_SCOPE: dict[str, str] = {
    "research/h1_qualification/PREREGISTRATION.md":
        "H1-PAPER-READINESS-QUALIFICATION-1 — frozen H1 identity, temporal-"
        "stability/parameter-sensitivity/cost-stress designs and every "
        "PASS/FAIL/INSUFFICIENT law",
    "research/h1_qualification/run_qualification.py":
        "the diagnostic campaign driver — 8 parameter neighbors, 4 temporal "
        "slices, 1 cost-stress run, reusing pin_upstream.py's fetch mechanism",
    "research/h1_qualification/__init__.py":
        "makes research/h1_qualification importable for its own tests",
    ".github/workflows/h1_qualification.yml":
        "runs the qualification campaign; workflow_dispatch only",
    "tests/test_h1_qualification_fee_propagation.py":
        "proves the cost-stress fee-propagation fix and the params-JSON "
        "space-nesting fix, both before any diagnostic trial executed",
    "research/records/trial_ledger.jsonl":
        "TRIAL-H1-QUAL-1 (ABORTED — a params-JSON nesting bug) and "
        "TRIAL-H1-QUAL-2 (SURVIVED — ADVANCE_TO_PAPER_ADMISSION_REVIEW), "
        "every diagnostic attempt preserved",
    "tests/test_p2_scope_audit.py":
        "Mean-Reversion Cycle 1 (PR #36) pinned to its merge range; this "
        "branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #38, merged. Two parents: 0862ea3c (main before, H1_QUALIFICATION_MERGE) +
# the account-handoff-1 branch.
ACCOUNT_HANDOFF_1_MERGE = "effa2e7645833743e43006b999ce08749dd708f2"

# Every path CLAUDE-ACCOUNT-HANDOFF-1 touched -> the requirement it satisfies.
# These entries were BRANCH_SCOPE while it was in flight.
ACCOUNT_HANDOFF_1_SCOPE: dict[str, str] = {
    "research/CLAUDE_ACCOUNT_HANDOFF_2026-09-29.md":
        "CLAUDE-ACCOUNT-HANDOFF-1 — the canonical continuity document for a "
        "Claude-account change: current state, exact file pointers, the "
        "corrected continuation law (RESEARCH-CYCLE1-CLOSURE-1, not a fresh "
        "Mean-Reversion run, since Cycle 1 already reached REJECTED), and "
        "the operative closure-unit instructions carried forward for the "
        "next account",
    "tests/test_p2_scope_audit.py":
        "H1-Paper-Readiness-Qualification-1 (PR #37) pinned to its merge "
        "range; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #39, merged. Two parents: effa2e76 (main before, ACCOUNT_HANDOFF_1_MERGE) +
# the research-cycle1-closure-1 branch.
RESEARCH_CYCLE1_CLOSURE_1_MERGE = "2a7fc4ebeab1d7dca034c5e1687ae25be9a05895"

# Every path RESEARCH-CYCLE1-CLOSURE-1 touched -> the requirement it satisfies.
# These entries were BRANCH_SCOPE while it was in flight.
RESEARCH_CYCLE1_CLOSURE_1_SCOPE: dict[str, str] = {
    "research/RESEARCH_CYCLE1_CLOSURE_1.md":
        "RESEARCH-CYCLE1-CLOSURE-1 — closure/reporting only: H1 and "
        "Mean-Reversion terminal states, Cycle-1 trial accounting, selection "
        "debt, data/holdout truth, evidence status, paper-admission "
        "eligibility, P2 firewall and remaining limitations; no new trial",
    "tests/test_p2_scope_audit.py":
        "CLAUDE-ACCOUNT-HANDOFF-1 (PR #38) pinned to its merge range; this "
        "branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #40, merged. Two parents: 2a7fc4eb (main before, RESEARCH_CYCLE1_CLOSURE_1_MERGE) +
# 8df86051 (the h1-paper-admission-and-launch-package-1 branch).
H1_PAPER_ADMISSION_1_MERGE = "3e5ef38b5eb8b72ee9b3541c50c02a87634db8f2"

# Every path H1-PAPER-ADMISSION-AND-LAUNCH-PACKAGE-1 touched -> the requirement it
# satisfies. These entries were BRANCH_SCOPE while it was in flight.
H1_PAPER_ADMISSION_1_SCOPE: dict[str, str] = {
    "research/paper/h1/H1_PAPER_ADMISSION_AND_LAUNCH_PACKAGE_1.md":
        "H1-PAPER-ADMISSION-AND-LAUNCH-PACKAGE-1 — the unit report: PR #39 "
        "closure, frozen identity, admission decision (ADMIT_TO_ISOLATED_PAPER), "
        "durability, licensing, isolation, placement and launch readiness",
    "research/paper/h1/package/PREREGISTRATION.md":
        "H1-PAPER-COHORT-1 prospective question, benchmark contract, terminal, "
        "freeze, incident/recovery and placement law, frozen before any T0",
    "research/paper/h1/package/cohort.json":
        "H1-PAPER-COHORT-1 frozen cohort identity; T0 null",
    "research/paper/h1/package/config.h1-paper.json":
        "the paper-only Freqtrade config: config.paper.json.example narrowed to "
        "BTC/USDT with its own bot name",
    "research/paper/h1/package/docker-compose.h1-paper.yml":
        "the standalone, resource-capped, P2-isolated runtime definition; not started",
    "research/paper/h1/package/incident.schema.json":
        "incident payload schema for the cohort's hash-chained incident ledger",
    "research/paper/h1/package/h1_paper.py":
        "static verify, launch-time preflight (starts nothing) and incident append",
    "research/paper/h1/package/PACKAGE_MANIFEST.sha256":
        "binds every package byte; its sha256 is the digest a launch "
        "authorization must name",
    "tests/test_h1_paper_package.py":
        "static package law: identity, paper safety, P2 isolation, no vendoring, "
        "no T0, incident-ledger law",
    "tests/test_p2_scope_audit.py":
        "RESEARCH-CYCLE1-CLOSURE-1 (PR #39) pinned to its merge range; this "
        "branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #41, merged. Two parents: 3e5ef38b (main before, H1_PAPER_ADMISSION_1_MERGE) +
# 0e9d39c6 (the p2-master-plan-installation branch).
MASTER_PLAN_1_MERGE = "d7e3fb26cca6a42dc2dc554bf18ec6c9a9cd2ba2"

# Every path TRADING-LAB-OS-MASTER-PLAN-1 installation touched -> the requirement
# it satisfies. These entries were BRANCH_SCOPE while it was in flight.
MASTER_PLAN_1_SCOPE: dict[str, str] = {
    "docs/governance/TRADING_LAB_OS_MASTER_EXECUTION_AND_MONITORING_PLAN.md":
        "TRADING-LAB-OS-MASTER-PLAN-1 v1.2 — the Owner-provided master planning "
        "SSOT (v1.1 installed byte-for-byte, then the Owner's three v1.2 "
        "reconciliation corrections); non-authorizing by itself",
    "CLAUDE.md":
        "a pointer to the master planning SSOT and its field-specific, "
        "non-authorizing standing",
    "tests/test_p2_scope_audit.py":
        "H1-PAPER-ADMISSION-AND-LAUNCH-PACKAGE-1 (PR #40) pinned to its merge "
        "range; the master plan's single path admitted to the allowed set; "
        "this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #42, merged. Two parents: d7e3fb26 (main before, MASTER_PLAN_1_MERGE) +
# d7a95419 (the research-cycle2-opening branch).
CYCLE2_OPENING_1_MERGE = "4bbb1df6e866d657b9e486ca683c30fef4133035"

# Every path OFFLINE-RESEARCH-CYCLE-2-OPENING-1 touched -> the requirement it
# satisfies. These entries were BRANCH_SCOPE while it was in flight.
CYCLE2_OPENING_1_SCOPE: dict[str, str] = {
    "research/OFFLINE_RESEARCH_CYCLE_2_OPENING_1.md":
        "OFFLINE-RESEARCH-CYCLE-2-OPENING-1 — the Owner-approved Cycle-2 "
        "opening record (governance-only, non-executing)",
    "docs/governance/TRADING_LAB_OS_MASTER_EXECUTION_AND_MONITORING_PLAN.md":
        "Lane-B research-authority sentence corrected; §22.1 change record "
        "MP1-CR-001",
    "tests/test_p2_scope_audit.py":
        "TRADING-LAB-OS-MASTER-PLAN-1 installation (PR #41) pinned to its merge "
        "range; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #43, merged. Two parents: 4bbb1df6 (main before, CYCLE2_OPENING_1_MERGE) +
# eed4c880 (the research-cycle2-unit-7-1 branch).
CYCLE2_UNIT_7_1_MERGE = "6ba84c3c49470f7c5e97a9920b3e592c7bbcfb14"

# Every path CYCLE-2 UNIT 7.1 touched -> the requirement it satisfies. These
# entries were BRANCH_SCOPE while it was in flight.
CYCLE2_UNIT_7_1_SCOPE: dict[str, str] = {
    "research/cycle2/__init__.py":
        "CYCLE-2 UNIT 7.1 — package marker for the OPENING-1 §6 minimum tooling",
    "research/cycle2/TRIALGATE_AUDIT_1.md":
        "CYCLE-2 UNIT 7.1 A1–A6 — trialgate==0.5.0 audit record and verdict",
    "research/cycle2/multiple_testing.py":
        "CYCLE-2 UNIT 7.1 B / OPENING-1 §6.3 — thin wrapper over "
        "trialgate.validation with the NOT_EVALUABLE law",
    "research/cycle2/driver.py":
        "CYCLE-2 UNIT 7.1 C / OPENING-1 §6.1 + §6.2 — strategy-agnostic "
        "WF/robustness driver, engine-propagated fee proxy, hard-cap guard",
    "research/cycle2/prereg.schema.json":
        "CYCLE-2 UNIT 7.1 C — schema of the driver's preregistration input "
        "(explicit enumeration only)",
    "research/cycle2/regime_session.py":
        "CYCLE-2 UNIT 7.1 D / OPENING-1 §6.4 — diagnostic-only regime/session "
        "script, trailing labels",
    "tests/test_cycle2_multiple_testing.py":
        "CYCLE-2 UNIT 7.1 A2–A4, A6, B — trialgate audit and wrapper tests",
    "tests/test_cycle2_driver.py":
        "CYCLE-2 UNIT 7.1 C — driver tests with subprocess mocked (nothing executes)",
    "tests/test_cycle2_regime_session.py":
        "CYCLE-2 UNIT 7.1 D — no-lookahead and diagnostic-only tests",
    "research/requirements.txt":
        "CYCLE-2 UNIT 7.1 A5 — audit verdict ADOPT: trialgate==0.5.0 pinned with "
        "both audited hashes",
    "tests/test_p2_scope_audit.py":
        "OFFLINE-RESEARCH-CYCLE-2-OPENING-1 (PR #42) pinned to its merge range; "
        "this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #44, merged. Two parents: 6ba84c3c (main before, CYCLE2_UNIT_7_1_MERGE) +
# c43c139b (the research-cycle2-unit-7-1a branch).
CYCLE2_UNIT_7_1A_MERGE = "9bae31961437356f963ac723f299446db2b5e267"

# Every path CYCLE-2 UNIT 7.1a touched -> the requirement it satisfies. These
# entries were BRANCH_SCOPE while it was in flight.
CYCLE2_UNIT_7_1A_SCOPE: dict[str, str] = {
    "research/requirements-cycle2.txt":
        "CYCLE-2 UNIT 7.1a — audit §A5 disclosures 1+2: the hash-pinned trialgate "
        "line moved to its own file, installed with --require-hashes --no-deps",
    "research/requirements.txt":
        "CYCLE-2 UNIT 7.1a — audit §A5 disclosure 2: restored to mlflow only "
        "(byte-identical to 4bbb1df), out of hash-checking mode",
    ".github/workflows/ci.yml":
        "CYCLE-2 UNIT 7.1a — audit §A5 disclosure 1 (Owner-approved): the static "
        "job installs the hash-checked pin and sets TLOS_REQUIRE_TRIALGATE=1",
    "tests/test_cycle2_multiple_testing.py":
        "CYCLE-2 UNIT 7.1a — pin test reads requirements-cycle2.txt; trialgate "
        "tests fail closed under TLOS_REQUIRE_TRIALGATE=1; ci.yml install asserted",
    "research/cycle2/TRIALGATE_AUDIT_1.md":
        "CYCLE-2 UNIT 7.1a — append-only addendum: disclosures 1 and 2 closed",
    "tests/test_p2_scope_audit.py":
        "CYCLE-2 UNIT 7.1 (PR #43) pinned to its merge range; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}

# PR #45, merged. Two parents: 9bae3196 (main before, CYCLE2_UNIT_7_1A_MERGE) +
# c60168e9 (the research-cycle2-unit-7-2a branch).
CYCLE2_UNIT_7_2A_MERGE = "31c26b6be55ad009bc0c81fec607f3ff20a34273"

# Every path CYCLE-2 UNIT 7.2 PART A touched -> the requirement it satisfies.
# These entries were BRANCH_SCOPE while it was in flight.
CYCLE2_UNIT_7_2A_SCOPE: dict[str, str] = {
    "research/cycle2/FUNNEL_LAW_1.md":
        "CYCLE-2 UNIT 7.2 PART A — the frozen Cycle-2 funnel law (Owner card: "
        "RECOMMENDED), applicable to every Cycle-2 trial",
    "research/cycle2/config_n.py":
        "CYCLE-2 UNIT 7.2 PART A — N LAW: family_configuration_N from the pinned "
        "Cycle-1 closure table + ledger-bound Cycle-2 grids (never trial IDs)",
    "research/cycle2/funnel.py":
        "CYCLE-2 UNIT 7.2 PART A — pure, deterministic funnel-law evaluator; "
        "derived non-authoritative output; never writes the ledger",
    "research/cycle2/prereg.schema.json":
        "CYCLE-2 UNIT 7.2 PART A — funnel_law binding; optional fixture_files, "
        "pair_universe, requires_prior_terminal; params {} only for NULL_CALIBRATION",
    "research/cycle2/driver.py":
        "CYCLE-2 UNIT 7.2 PART A — null fixtures (sha256-checked copy, no params "
        "file, pair universe) and the null sequencing refusals",
    "research/cycle2/prereg/TRIAL-C2-NULL-MATCHFREQ-1.json":
        "CYCLE-2 UNIT 7.2 PART A — preregistration of null #1 (calibration ID 1/6)",
    "research/cycle2/prereg/TRIAL-C2-NULL-BLOCKSHUF-1.json":
        "CYCLE-2 UNIT 7.2 PART A — preregistration of null #2 (calibration ID 2/6), "
        "requires null #1 REJECTED",
    ".github/workflows/cycle2_research.yml":
        "CYCLE-2 UNIT 7.2 PART A — manual-dispatch-only, contents:read workflow "
        "that runs one preregistered Cycle-2 trial off-host",
    "research/records/trial_ledger.jsonl":
        "CYCLE-2 UNIT 7.2 PART A — exactly 2 appended PREREGISTERED records "
        "(TRIAL-C2-NULL-MATCHFREQ-1, TRIAL-C2-NULL-BLOCKSHUF-1)",
    "tests/test_cycle2_funnel.py":
        "CYCLE-2 UNIT 7.2 PART A — every funnel-law branch, determinism, read-only ledger",
    "tests/test_cycle2_config_n.py":
        "CYCLE-2 UNIT 7.2 PART A — N LAW tests (identity, not trial IDs; fail-closed)",
    "tests/test_cycle2_driver.py":
        "CYCLE-2 UNIT 7.2 PART A — null fixture path and null sequencing tests",
    "tests/test_cycle2_workflow.py":
        "CYCLE-2 UNIT 7.2 PART A — static checks of the dispatch-only workflow",
    "tests/test_cycle2_multiple_testing.py":
        "CYCLE-2 UNIT 7.2 PART A — the canonical ledger's observed null-family "
        "trial-ID count follows the 2 appends (6 → 8); no threshold or reference changed",
    "tests/test_p2_scope_audit.py":
        "CYCLE-2 UNIT 7.1a (PR #44) pinned to its merge range; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #46, merged. Two parents: 31c26b6b (main before, CYCLE2_UNIT_7_2A_MERGE) +
# 533c138d (the research-cycle2-unit-7-2b1 branch).
CYCLE2_UNIT_7_2B1_MERGE = "8654156db8bcbc8c38c1606b31d0121ac1035c1e"

# Every path CYCLE-2 UNIT 7.2 PART B1 touched -> the requirement it satisfies.
# These entries were BRANCH_SCOPE while it was in flight.
CYCLE2_UNIT_7_2B1_SCOPE: dict[str, str] = {
    "research/records/trial_ledger.jsonl":
        "CYCLE-2 UNIT 7.2 PART B1 — exactly 1 appended terminal record "
        "(TRIAL-C2-NULL-MATCHFREQ-1, REJECTED, run 37032878568)",
    "research/cycle2/records/TRIAL-C2-NULL-MATCHFREQ-1_RESULT.md":
        "CYCLE-2 UNIT 7.2 PART B1 — durable result record of run 37032878568 "
        "(the GitHub artifact expires after 30 days)",
    "research/cycle2/records/TRIAL-C2-NULL-MATCHFREQ-1_funnel_result.json":
        "CYCLE-2 UNIT 7.2 PART B1 — byte copy of the run's derived funnel_result.json",
    "tests/test_cycle2_driver.py":
        "CYCLE-2 UNIT 7.2 PART B1 — tests updated for the recorded MATCHFREQ terminal state",
    "tests/test_p2_scope_audit.py":
        "CYCLE-2 UNIT 7.2 PART A (PR #45) pinned to its merge range; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #47, merged. Two parents: 8654156d (main before, CYCLE2_UNIT_7_2B1_MERGE) +
# 171046bd (the research-cycle2-unit-7-2b2 branch).
CYCLE2_UNIT_7_2B2_MERGE = "45c1e5837159d5bfe04ed1a46031def80a7b3fcc"

# Every path CYCLE-2 UNIT 7.2 PART B2 touched -> the requirement it satisfies.
# These entries were BRANCH_SCOPE while it was in flight.
CYCLE2_UNIT_7_2B2_SCOPE: dict[str, str] = {
    "research/records/trial_ledger.jsonl":
        "CYCLE-2 UNIT 7.2 PART B2 — exactly 1 appended terminal record "
        "(TRIAL-C2-NULL-BLOCKSHUF-1, REJECTED, run 37038822799)",
    "research/cycle2/records/TRIAL-C2-NULL-BLOCKSHUF-1_RESULT.md":
        "CYCLE-2 UNIT 7.2 PART B2 — durable result record of run 37038822799 "
        "(the GitHub artifact expires after 30 days)",
    "research/cycle2/records/TRIAL-C2-NULL-BLOCKSHUF-1_funnel_result.json":
        "CYCLE-2 UNIT 7.2 PART B2 — byte copy of the run's derived funnel_result.json",
    "research/cycle2/records/UNIT_7_2_NULL_RECALIBRATION_RESULT.md":
        "CYCLE-2 UNIT 7.2 PART B2 — the 7.2 null-recalibration result (OPENING-1 §7.2, Master Plan §12)",
    "tests/test_p2_scope_audit.py":
        "CYCLE-2 UNIT 7.2 PART B1 (PR #46) pinned to its merge range; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #48, merged. Two parents: 45c1e583 (main before, CYCLE2_UNIT_7_2B2_MERGE) +
# 22d7c562 (the research-cycle2-unit-7-3a branch).
CYCLE2_UNIT_7_3A_MERGE = "efe6e77187992fb06f9ddadd470b20d04e583eca"

# Every path CYCLE-2 UNIT 7.3 PART A touched -> the requirement it satisfies.
# These entries were BRANCH_SCOPE while it was in flight.
CYCLE2_UNIT_7_3A_SCOPE: dict[str, str] = {
    "research/trend_breakout/DonchianBreakoutV1.py":
        "CYCLE-2 UNIT 7.3 — the Trend/Breakout lineage strategy (OPENING-1 §2.1; no moving average)",
    "research/trend_breakout/PREREGISTRATION.md":
        "CYCLE-2 UNIT 7.3 — the lineage's human preregistration (signal, independence from H1, grid, outcomes)",
    "research/cycle2/prereg/TRIAL-C2-TREND-DONCHIAN-1.json":
        "CYCLE-2 UNIT 7.3 — the machine-readable preregistration the driver and funnel read",
    "research/cycle2/prereg.schema.json":
        "CYCLE-2 UNIT 7.3 — optional parameter_robustness block (FUNNEL_LAW_1 L4 'per the trial's preregistration')",
    "research/cycle2/driver.py":
        "CYCLE-2 UNIT 7.3 — refuse an unreachable or null-lineage parameter_robustness block",
    "research/cycle2/funnel.py":
        "CYCLE-2 UNIT 7.3 — L4 evaluated from the preregistered criterion; null verdicts unchanged",
    ".github/workflows/cycle2_research.yml":
        "CYCLE-2 UNIT 7.3 — the Trend prereg in the dispatch allowlist; the L4 robustness-window passive line",
    "research/records/trial_ledger.jsonl":
        "CYCLE-2 UNIT 7.3 — exactly 1 appended PREREGISTERED record (TRIAL-C2-TREND-DONCHIAN-1)",
    "tests/test_cycle2_funnel.py": "CYCLE-2 UNIT 7.3 — L4 evaluator tests",
    "tests/test_cycle2_workflow.py": "CYCLE-2 UNIT 7.3 — allowlist and robustness benchmark step checks",
    "tests/test_cycle2_trend_prereg.py": "CYCLE-2 UNIT 7.3 — the Trend preregistration, read only",
    "tests/test_cycle2_multiple_testing.py":
        "CYCLE-2 UNIT 7.3 — the canonical ledger's observed trend-family trial-ID count follows the "
        "1 append (3 → 4); no threshold or reference changed",
    "tests/test_p2_scope_audit.py":
        "CYCLE-2 UNIT 7.2 PART B2 (PR #47) pinned to its merge range; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #49, merged. Two parents: efe6e771 (main before, CYCLE2_UNIT_7_3A_MERGE) +
# e302d1d7 (the research-cycle2-unit-7-3r branch).
CYCLE2_UNIT_7_3R_MERGE = "21cf0a6cc260ecf8644f4f6bcc0ca22f7a82c62d"

# Every path CYCLE-2 UNIT 7.3 RECORD touched -> the requirement it satisfies.
# These entries were BRANCH_SCOPE while it was in flight.
CYCLE2_UNIT_7_3R_SCOPE: dict[str, str] = {
    "research/records/trial_ledger.jsonl":
        "CYCLE-2 UNIT 7.3 RECORD — exactly 1 appended terminal record "
        "(TRIAL-C2-TREND-DONCHIAN-1, REJECTED, run 37155789386)",
    "research/cycle2/records/TRIAL-C2-TREND-DONCHIAN-1_RESULT.md":
        "CYCLE-2 UNIT 7.3 RECORD — durable result record of run 37155789386 "
        "(the GitHub artifact expires after 30 days)",
    "research/cycle2/records/TRIAL-C2-TREND-DONCHIAN-1_funnel_result.json":
        "CYCLE-2 UNIT 7.3 RECORD — byte copy of the run's derived funnel_result.json",
    "tests/test_p2_scope_audit.py":
        "CYCLE-2 UNIT 7.3 PART A (PR #48) pinned to its merge range; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #50, merged. Two parents: 21cf0a6c (main before, CYCLE2_UNIT_7_3R_MERGE) +
# 85804168 (the research-cycle2-closure-1 branch).
RESEARCH_CYCLE2_CLOSURE_1_MERGE = "4c14d259b42060240158b2abee8105a55d2e4dd2"

# Every path CYCLE-2 UNIT 7.5 (RESEARCH-CYCLE2-CLOSURE-1) touched -> the requirement
# it satisfies. These entries were BRANCH_SCOPE while it was in flight.
RESEARCH_CYCLE2_CLOSURE_1_SCOPE: dict[str, str] = {
    "research/RESEARCH_CYCLE2_CLOSURE_1.md":
        "CYCLE-2 UNIT 7.5 — closure/reporting only (OPENING-1 §7.5/§9); no trial",
    "tests/test_p2_scope_audit.py":
        "CYCLE-2 UNIT 7.3 RECORD (PR #49) pinned to its merge range; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #51, merged. Two parents: 4c14d259 (main before, RESEARCH_CYCLE2_CLOSURE_1) +
# eff705e7 (the claude/auth-1-continuous-execution branch).
AUTH_1_MERGE = "3eba2b858b652cf8f18c50da9f64929e452ba5d6"

# Every path AUTH-1 (CEA-1) touched -> the requirement it satisfies. These entries
# were BRANCH_SCOPE while it was in flight.
AUTH_1_SCOPE: dict[str, str] = {
    "docs/governance/CONTINUOUS_EXECUTION_AUTHORITY_1.md":
        "AUTH-1 (CEA-1) D1 — the continuous-execution law",
    ".github/gates/protected_paths.txt": "AUTH-1 (CEA-1) D2 — PROTECTED_VERIFICATION_PATHS",
    ".github/gates/AUTONOMY_STATE.json": "AUTH-1 (CEA-1) D3 — kill state, layer 1",
    ".github/gates/ACTIVATION.json": "AUTH-1 (CEA-1) D3 — auto-merge activation flags, all false",
    ".github/gates/cea_policy.py": "AUTH-1 (CEA-1) D4-D7 — shared policy reading at a git revision",
    ".github/gates/merge_law.py": "AUTH-1 (CEA-1) D4 — the base-policy merge law",
    ".github/workflows/merge-law.yml": "AUTH-1 (CEA-1) D4 — merge-law check on pull_request_target, base policy",
    ".github/gates/resolve_next_unit.py": "AUTH-1 (CEA-1) D5 — the deterministic next-unit resolver (dry run)",
    "charters/charter.schema.json": "AUTH-1 (CEA-1) D6 — program charter schema",
    "charters/ticket.schema.json": "AUTH-1 (CEA-1) D6/D8 — evidence ticket schema (no customer-data fields)",
    ".github/gates/check_charters.py": "AUTH-1 (CEA-1) D6 — charter and ticket validator",
    "charters/research_program.schema.json": "AUTH-1 (CEA-1) D7 — AUTH-2 structure, no program instance",
    ".github/gates/check_research_program.py": "AUTH-1 (CEA-1) D7 — research program validator and self-test",
    "charters/COMMERCIAL-VERIFICATION-LANE-1.json": "AUTH-1 (CEA-1) D8 — first Program Charter (machine-readable)",
    "charters/COMMERCIAL-VERIFICATION-LANE-1.md": "AUTH-1 (CEA-1) D8 — first Program Charter (record)",
    "CLAUDE.md": "AUTH-1 (CEA-1) D9 — 'Never auto-merge' qualified by CEA-1 §5; pointer to CEA-1",
    "docs/governance/TRADING_LAB_OS_MASTER_EXECUTION_AND_MONITORING_PLAN.md":
        "AUTH-1 (CEA-1) D10 — §22.1 change record MP1-CR-002 (§21)",
    "tests/test_merge_law.py": "AUTH-1 (CEA-1) D11 — merge-law refusals",
    "tests/test_resolve_next_unit.py": "AUTH-1 (CEA-1) D11 — resolver determinism, lease, serialization, kill",
    "tests/test_charters.py": "AUTH-1 (CEA-1) D11 — charter and ticket law",
    "tests/test_research_program_schema.py": "AUTH-1 (CEA-1) D11 — AUTH-2 structure refusals; no program exists",
    "tests/test_protected_paths.py": "AUTH-1 (CEA-1) D11 — the protected list is real and self-protecting",
    "tests/test_p2_scope_audit.py":
        "AUTH-1 (CEA-1) D12 — PR #50 pinned; charters/ and verification/ admitted; the CEA-1 law file admitted "
        "by exact path; auto/<charter>/<unit> branches audited against their charter's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #54, merged. Two parents: 3eba2b85 (main before, AUTH_1) + 5f447a82 (the
# claude/cea-1-test-fix branch).
CEA_1_TEST_FIX_MERGE = "7360096c93a0fb77fbf115da1943f8dec0af6fb0"

# Every path the CEA-1 test fix touched -> the requirement it satisfies. These
# entries were BRANCH_SCOPE while it was in flight.
CEA_1_TEST_FIX_SCOPE: dict[str, str] = {
    "tests/test_merge_law.py":
        "CEA-1 test fix — the merge-law probe tolerates an existing verification/ (CI red on every CV unit)",
    "tests/test_p2_scope_audit.py": "AUTH-1 (PR #51) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #56, merged. Two parents: d1fe2b4f (main before) + 8c66a04f (the
# claude/cea-1-merge-law-fetch branch).
CEA_1_MERGE_LAW_FETCH_MERGE = "390bf4bf66ae92f49ff8a9490b59e142ed592724"

# Every path the CEA-1 merge-law fetch fix touched -> the requirement it satisfies.
# These entries were BRANCH_SCOPE while it was in flight.
CEA_1_MERGE_LAW_FETCH_SCOPE: dict[str, str] = {
    ".github/workflows/merge-law.yml":
        "CEA-1 merge-law fix — authenticate the PR-head fetch (private repo; the job never reached its verdict)",
    "tests/test_p2_scope_audit.py": "CEA-1 test fix (PR #54) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #58, merged. Two parents: 390bf4bf (main before) + a59880bc (the
# claude/cea-1-merge-law-ledger-import branch).
CEA_1_MERGE_LAW_LEDGER_IMPORT_MERGE = "0106ffbbf2599d28c7b3355bf5702873eaf02a66"

# Every path the CEA-1 merge-law ledger-import fix touched -> the requirement it satisfies.
# These entries were BRANCH_SCOPE while it was in flight.
CEA_1_MERGE_LAW_LEDGER_IMPORT_SCOPE: dict[str, str] = {
    ".github/gates/merge_law.py":
        "CEA-1 merge-law fix — import the BASE fp package with the BASE ledger code (the job crashed on any append)",
    "tests/test_merge_law.py": "CEA-1 merge-law fix — an appended record verifies in a fresh process",
    "tests/test_p2_scope_audit.py": "PR #56 pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #57, merged. Two parents: 0106ffbb (main before, CEA_1_MERGE_LAW_LEDGER_IMPORT) +
# 50fdb496 (the claude/auth-2-discovery-qualification-1 branch).
AUTH_2_MERGE = "70e047ecc3a13e051cfdcc2d284e70c95e3fc55a"

# AUTH-2-DISCOVERY-QUALIFICATION-1: the Owner-approved frozen package materialised as one
# merge set (research/auth2/FUNNEL_LAW_2.md). Research lane only: nothing under P2, FP or
# the commercial lane, no strategy or risk semantics, no Dataset V1/V2 change. These
# entries were BRANCH_SCOPE while it was in flight.
_AUTH2 = "AUTH-2 (frozen package)"
_AUTH2_NODES = ["D0", "CAL-A1", "CAL-A2", "CAL-A3", "PC-A1", "PC-A2", "PC-A3", "N-A1", "N-A2", "N-A3",
                "A1", "A2", "A3", "HOLM", "SC-A1", "SC-A2", "SC-A3"]
AUTH_2_SCOPE: dict[str, str] = {
    # -- records the package lists (§FINAL_AUTH2_SPEC "Records the package needs") ------
    "research/auth2/FUNNEL_LAW_2.md": f"{_AUTH2} record 1 — the gate sections verbatim",
    "charters/research_program.schema.json": f"{_AUTH2} record 2 — schema v2, minimal extension [OD-7]",
    ".github/gates/check_research_program.py": f"{_AUTH2} record 2 — the v2 structural checks",
    "research/auth2/prereg.schema.json": f"{_AUTH2} record 3 — auth2-prereg-1.0.0",
    "research/datasets/dataset_v3.lock.json": f"{_AUTH2} record 4 — the Dataset V3 lock",
    **{f"research/datasets/dataset_v3/{t}.json": f"{_AUTH2} record 4 — membership tables and coverage report"
       for t in ("a3_window", "candidates", "coverage", "engine_data", "membership_u12", "membership_u6",
                 "membership_u8")},
    **{f"research/auth2/{f}": f"{_AUTH2} record 5 — fixtures, benchmarks, nulls, generators"
       for f in ("__init__.py", "signals.py", "families.py", "synthetic.py", "engine/AUTH2ScheduleFollower.py")},
    "research/auth2/replay.py": f"{_AUTH2} record 6 — the replay evaluator [OD-6]",
    "charters/programs/AUTH-2-DISCOVERY-QUALIFICATION-1.json": f"{_AUTH2} record 7 — the program charter",
    **{f"research/auth2/prereg/{n}.json": f"{_AUTH2} record 7 — node preregistration" for n in _AUTH2_NODES},
    "research/RESEARCH_CYCLE2_CLOSURE_1_ERRATA_1.md": f"{_AUTH2} record 8 — Cycle-2 errata (append-only)",
    # -- the implementation of the frozen DAG --------------------------------------------
    **{f"research/auth2/{f}": f"{_AUTH2} — Dataset V3 acquisition and point-in-time universe law"
       for f in ("archive.py", "universe.py", "dataset_v3.py", "market_io.py")},
    **{f"research/auth2/{f}": f"{_AUTH2} — the judged engine (freqtrade 2026.7, disclosed launcher patches)"
       for f in ("engine/run_backtest.py", "engine/markets.py", "engine_io.py", "engine_selftest.py")},
    "research/auth2/stats.py": f"{_AUTH2} — statistics (C3, C7, C9, BOOTSTRAP_RULE)",
    "research/auth2/gates.py": f"{_AUTH2} — COMMON_GATES and family gates",
    "research/auth2/calibration.py": f"{_AUTH2} — CALIBRATION_DAG size/power and the planted edge",
    "research/auth2/calibration_edges.json": f"{_AUTH2} — the calibrated planted-edge record",
    "research/auth2/run_node.py": f"{_AUTH2} — one node per job; refusals; --next",
    "research/auth2/closure.py": f"{_AUTH2} — closure record and terminal ledger mapping",
    "research/auth2/make_preregs.py": f"{_AUTH2} — preregistrations, charter and ledger preregistration",
    "research/auth2/dispatch_guard.py": f"{_AUTH2} — COMPUTE_CAP_PROOF and MONTHLY_BILLING_PACING_RULE",
    "research/auth2/requirements-auth2.txt": f"{_AUTH2} — arch hash pin (evidence task 5)",
    "research/auth2/IMPLEMENTATION_NOTES.md": f"{_AUTH2} — operationalisations and disclosures",
    ".github/workflows/auth2.yml": f"{_AUTH2} — one manually dispatched job per node",
    "research/records/trial_ledger.jsonl": f"{_AUTH2} — 14 PREREGISTERED records (append-only)",
    # -- CI, gates and their tests ---------------------------------------------------------
    ".github/workflows/ci.yml": f"{_AUTH2} — install the arch pin; engine self-test in the pinned image",
    ".github/gates/protected_paths.txt": f"{_AUTH2} — research/auth2/** and Dataset V3 tables protected",
    ".github/gates/resolve_next_unit.py": f"{_AUTH2} — research lane names the program's runner",
    "tests/test_protected_paths.py": f"{_AUTH2} — AUTH-2 judges are protected",
    "tests/test_research_program_schema.py": f"{_AUTH2} — exactly the AUTH-2 program exists; v2 edges",
    "tests/test_resolve_next_unit.py": f"{_AUTH2} — the research lane now has a program",
    "tests/test_p2_scope_audit.py": f"{_AUTH2} — PRs #56 and #58 pinned to their merges; this branch's scope",
    **{f"tests/test_auth2_{t}.py": f"{_AUTH2} — verification before the PR"
       for t in ("replay", "stats", "gates", "calibration", "dispatch_guard", "dag", "records", "engine")},
    "tests/fixtures/auth2_engine_marks.json": f"{_AUTH2} — recorded engine marks for the replay parity fixture",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #59, merged. Two parents: 70e047ec (main before, AUTH_2) + dd75a5d0 (the
# claude/auth-2-guard-in-actions branch).
AUTH_2_OPERATOR_GATE_MERGE = "76bb14d569fb1b53b59c2190de3bd34de0325b61"

# AUTH-2 operator gate (Owner decision card: "Check in Actions"). The executor's session
# cannot read account billing or download run artifacts, so the pre-dispatch guard runs in
# Actions and every record the executor needs is published as a job annotation. Nothing
# under research/auth2/ changes: its code is pinned by sha256 in every preregistration.
# These entries were BRANCH_SCOPE while it was in flight.
_OPGATE = "AUTH-2 operator gate (guard in Actions)"
AUTH_2_OPERATOR_GATE_SCOPE: dict[str, str] = {
    ".github/gates/auth2_operator.py":
        f"{_OPGATE} — dispatch_guard.decide unchanged plus guard/closure jobs; check-dispatch; readouts",
    ".github/workflows/auth2-guard.yml": f"{_OPGATE} — the pre-dispatch guard job, record published",
    ".github/workflows/auth2-closure.yml": f"{_OPGATE} — the closure record computed where the artifacts are",
    ".github/workflows/auth2.yml": f"{_OPGATE} — in-job guard through the operator; result summary published",
    "research/auth2/IMPLEMENTATION_NOTES.md": f"{_OPGATE} — the dispatch procedure as operated",
    "tests/test_auth2_operator.py": f"{_OPGATE} — refusals, freshness, byte-exact channel, workflows",
    "tests/test_p2_scope_audit.py": "AUTH-2 (PR #57) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #60, merged. Two parents: 76bb14d5 (main before, AUTH_2_OPERATOR_GATE) + 2d338257 (the
# claude/auth-2-billing-evidence branch).
AUTH_2_BILLING_EVIDENCE_MERGE = "2a48f249171afd2ce86381927c426a3f68dae205"

# AUTH-2 billing evidence (Owner P0 "D0 Billing Guard Corrective Execution"). The billing
# endpoint dispatch_guard reads was closed down by GitHub (HTTP 410); the guard reads the
# supported usage report with the billing token only and records what it proves. Neither
# pacing-rule control (remaining included minutes, the USD 0 budget) is exposed for a
# personal account, so both stay unproven: NO_DISPATCH. research/auth2/*.py untouched.
# These entries were BRANCH_SCOPE while it was in flight.
_BILLING = "AUTH-2 billing evidence"
AUTH_2_BILLING_EVIDENCE_SCOPE: dict[str, str] = {
    ".github/gates/auth2_operator.py":
        f"{_BILLING} — supported usage endpoint, token-only, classified failures; RE_RUN; all-attempt minutes",
    "research/auth2/IMPLEMENTATION_NOTES.md": f"{_BILLING} — the closed endpoint and the evidence gap, recorded",
    "tests/test_auth2_operator.py": f"{_BILLING} — 410/403/401/missing token/fields/malformed/account/period/caps/replay",
    "tests/test_p2_scope_audit.py": "AUTH-2 operator gate (PR #59) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #61, merged. Two parents: 2a48f249 (main before, AUTH_2_BILLING_EVIDENCE) + 6cc4559d (the
# claude/auth-2-owner-billing-evidence-bridge branch).
AUTH_2_OWNER_BILLING_EVIDENCE_BRIDGE_MERGE = "e2cb36ed0840cc0f44f2572626db7b795340bfac"

# AUTH-2 Owner billing evidence bridge (Owner decision AUTH2-OWNER-BILLING-EVIDENCE-BRIDGE-1).
# GitHub's API exposes neither pacing-rule control for a personal account, so the Owner
# attests both in the pre-dispatch guard run, authenticated by the run's actor as the Actions
# API reports it, beside the billing token's verified usage report. Every node and closure
# dispatch names that guard run and its evidence digest, and the in-job guard verifies the
# binding. A_m stays the first node run's in-job record. research/auth2/*.py untouched.
# These entries were BRANCH_SCOPE while it was in flight.
_BRIDGE = "AUTH-2 Owner billing evidence bridge"
AUTH_2_OWNER_BILLING_EVIDENCE_BRIDGE_SCOPE: dict[str, str] = {
    ".github/gates/auth2_operator.py":
        f"{_BRIDGE} — Owner evidence and digest; node/closure binding verified in the job; first-month A_m",
    ".github/workflows/auth2-guard.yml": f"{_BRIDGE} — the Owner's typed billing inputs, read from the event",
    ".github/workflows/auth2.yml": f"{_BRIDGE} — the dispatch names its guard run and evidence digest",
    ".github/workflows/auth2-closure.yml": f"{_BRIDGE} — the closure is bound the same way",
    "research/auth2/IMPLEMENTATION_NOTES.md": f"{_BRIDGE} — the evidence source and the binding, recorded",
    "tests/test_auth2_operator.py": f"{_BRIDGE} — actor, inputs, usage, digest, binding, A_m, caps, replay",
    "tests/test_p2_scope_audit.py": "AUTH-2 billing evidence (PR #60) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #62, merged. Two parents: e2cb36ed (main before, AUTH_2_OWNER_BILLING_EVIDENCE_BRIDGE) + 2b9d327a
# (the claude/auth-2-usage-report-repository-name branch).
AUTH_2_USAGE_REPORT_REPOSITORY_NAME_MERGE = "410418e3ac436683b75d5c338ce640fb5e7dab37"

# AUTH-2 usage report repository name (guard run 38220977904, NO_DISPATCH: WRONG_ACCOUNT).
# GitHub's per-user usage report names the account's own repositories without an owner
# ("trading-lab-os-sandbox"), not in the docs example's "user/example" form, so the account
# check refused every live report. A bare name is accepted; a name qualified with any other
# owner, or a non-string, is still refused. No threshold, cap, input, binding or freshness
# rule changes. research/auth2/*.py untouched.
# These entries were BRANCH_SCOPE while it was in flight.
_REPO_NAME = "AUTH-2 usage report repository name"
AUTH_2_USAGE_REPORT_REPOSITORY_NAME_SCOPE: dict[str, str] = {
    ".github/gates/auth2_operator.py": f"{_REPO_NAME} — the account check accepts the live report's bare names",
    "research/auth2/IMPLEMENTATION_NOTES.md": f"{_REPO_NAME} — the live report form and guard run 38220977904",
    "tests/test_auth2_operator.py": f"{_REPO_NAME} — live-form fixture; other owners still refused; replay",
    "tests/test_p2_scope_audit.py":
        "AUTH-2 Owner billing evidence bridge (PR #61) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #63, merged. Two parents: 410418e3 (main before, AUTH_2_USAGE_REPORT_REPOSITORY_NAME) + 7e21a418
# (the claude/auth-2-node-checkout-history branch).
AUTH_2_NODE_CHECKOUT_HISTORY_MERGE = "8013e216075fcdfdf1068ef1b43b52aea5747d78"

# AUTH-2 node checkout history (D0 run 38273417548 refused: every node's ledger record "older
# than the program"). The node job checked out one commit, so the program check dated the
# program by the dispatched commit instead of the commit that first added it. The node job
# now fetches full history, as CI does. No gate, record, threshold or cap changes;
# research/auth2/*.py untouched.
# These entries were BRANCH_SCOPE while it was in flight.
_HISTORY = "AUTH-2 node checkout history"
AUTH_2_NODE_CHECKOUT_HISTORY_SCOPE: dict[str, str] = {
    ".github/workflows/auth2.yml": f"{_HISTORY} — the node job fetches the history its program check reads",
    "research/auth2/IMPLEMENTATION_NOTES.md": f"{_HISTORY} — D0 run 38273417548 and its cause, recorded",
    "tests/test_auth2_operator.py": f"{_HISTORY} — full-history checkout pinned; depth-1 refusal reproduced",
    "tests/test_p2_scope_audit.py":
        "AUTH-2 usage report repository name (PR #62) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}

# PR #64, merged. Two parents: 8013e216 (main before, AUTH_2_NODE_CHECKOUT_HISTORY) + 48aeb4fd
# (the claude/auth-2-governance-closure-1 branch).
AUTH2_GOVERNANCE_CLOSURE_1_MERGE = "f5c6bc332288c5968926ce536db0f1d4cb710f64"

# AUTH2-GOVERNANCE-CLOSURE-1 (Owner decision "AUTH-2 CLOSURE AND SUCCESSOR READINESS",
# 2026-10-12, Gate 1: OD-C1 to OD-C7). AUTH-2 closes by a governance record outside the trial
# ledger: OPERATIONAL_EXHAUSTION, scientific outcome NONE. The record folder holds the approved
# bundle byte for byte. The charter's status becomes CLOSED and no other byte of it changes.
# No ledger append, no dispatch, no operator change; research/auth2/*.py untouched.
# These entries were BRANCH_SCOPE while it was in flight.
_CLOSURE = "AUTH2-GOVERNANCE-CLOSURE-1"
_CLOSURE_DIR = "docs/governance/records/AUTH2-GOVERNANCE-CLOSURE-1/"
AUTH2_GOVERNANCE_CLOSURE_1_SCOPE: dict[str, str] = {
    **{f"{_CLOSURE_DIR}{f}": f"{_CLOSURE} — the Owner-approved bundle, byte for byte [OD-C1, OD-C2]"
       for f in ("evidence.json", "governance_closure.proposed.json", "trial_ledger_option.check.json",
                 "SHA256SUMS", "closure_proposal.py")},
    f"{_CLOSURE_DIR}README.md": f"{_CLOSURE} — the closure record; preservation steps [OD-C1, OD-C5, OD-C6]",
    "charters/programs/AUTH-2-DISCOVERY-QUALIFICATION-1.json": f"{_CLOSURE} — status CLOSED, nothing else [OD-C3]",
    "tests/test_auth2_records.py": f"{_CLOSURE} — the charter is the code's, with only its status closed",
    "tests/test_auth2_governance_closure.py":
        f"{_CLOSURE} — the approved bundle, append-only; charter, ledger and rebuild checked",
    "tests/test_p2_scope_audit.py":
        "AUTH-2 node checkout history (PR #63) pinned to its merge; this branch's scope; the record admitted",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #65, merged. Two parents: f5c6bc33 (main before, AUTH2_GOVERNANCE_CLOSURE_1) + a93bbda9
# (the claude/auth-2-od-c4-operator-refusal branch).
AUTH_2_OD_C4_OPERATOR_REFUSAL_MERGE = "a80733f60c10a858f7f311a39b94043744d3630b"

# AUTH-2 OD-C4 operator refusal (Owner decision "AUTH-2 CLOSURE AND SUCCESSOR READINESS",
# 2026-10-12, Gate 1, OD-C4; carried out on the Owner's instruction of 2026-10-13). Every AUTH-2
# dispatch is refused unless the program charter says ACTIVE: at the Owner's pre-dispatch guard,
# the executor's check-dispatch and the in-job guard of every node and closure run. It only adds
# a refusal. No workflow, record, ledger, threshold or cap changes; research/auth2/ untouched.
# These entries were BRANCH_SCOPE while it was in flight.
_OD_C4 = "AUTH-2 OD-C4 operator refusal"
AUTH_2_OD_C4_OPERATOR_REFUSAL_SCOPE: dict[str, str] = {
    ".github/gates/auth2_operator.py":
        f"{_OD_C4} — CHARTER_NOT_ACTIVE at the guard, in-job and at check-dispatch [OD-C4]",
    "tests/test_auth2_operator.py":
        f"{_OD_C4} — every gate, every status, unreadable charters; only a refusal is added",
    "tests/test_p2_scope_audit.py": "AUTH2-GOVERNANCE-CLOSURE-1 (PR #64) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #66, merged. Two parents: a80733f6 (main before, AUTH_2_OD_C4_OPERATOR_REFUSAL) + 4271e201
# (the claude/auth-2-successor-readiness-tooling branch).
AUTH_2Q2_READINESS_TOOLING_MERGE = "ecfec8295c89d45fe683d3fc31c5d766341de077"

# AUTH-2-DISCOVERY-QUALIFICATION-2, Gate 2 successor readiness tooling (Owner decision "AUTH-2
# CLOSURE AND SUCCESSOR READINESS", 2026-10-12, Gate 2: OD-S1 to OD-S8; carried out on the Owner's
# instruction of 2026-10-13). The infrastructure the readiness runs RT-0 to RT-11 need, built and
# tested offline: nothing is dispatched. No hypothesis, strategy, risk setting, threshold, window,
# DAG, dataset science, preregistration or trial id changes; research/auth2/ and the trial ledger
# untouched; the successor law is not written. Only the snapshot release job may write.
# These entries were BRANCH_SCOPE while it was in flight.
_Q2 = "AUTH-2-DISCOVERY-QUALIFICATION-2 readiness tooling"
AUTH_2Q2_READINESS_TOOLING_SCOPE: dict[str, str] = {
    "research/auth2q2/__init__.py": f"{_Q2} — the successor's readiness package, its id [OD-S1]",
    "research/auth2q2/snapshot.py":
        f"{_Q2} — deterministic content-addressed snapshot and manifest; strict, verified restore [OD-S2]",
    "research/auth2q2/listing.py": f"{_Q2} — the archive listing replayed offline; any other request refused",
    "research/auth2q2/offline.py": f"{_Q2} — the science phase without network: namespace probe, socket guard",
    "research/auth2q2/prepare.py":
        f"{_Q2} — checksum-verified parallel preparation bound to the Dataset V3 lock (RT-1, RT-2)",
    "research/auth2q2/release.py":
        f"{_Q2} — the immutable-release publication path and its RT-3 probes [OD-S2, OD-S3]",
    "research/auth2q2/attempts.py":
        f"{_Q2} — ADMISSION/INFRA/SCIENCE/RESULT, bounded INFRA retries, TECHNICAL_EXHAUSTION [OD-S5, OD-S6]",
    "research/auth2q2/compute.py":
        f"{_Q2} — the guarded 4,000-minute compute proof, timeout + 1, closure reserve [OD-S7]",
    "research/auth2q2/plan.py": f"{_Q2} — RT-1 to RT-11 as jobs and timeouts; the 300-minute ledger [OD-S4]",
    "research/auth2q2/harness.py":
        f"{_Q2} — the readiness jobs' steps: restore, verify, offline science, classifiers, verdicts",
    "research/auth2q2/record.py": f"{_Q2} — the INFRA_READINESS record, rebuilt and verified offline [OD-S8]",
    ".github/gates/auth2q2_readiness.py":
        f"{_Q2} — the readiness gate: Owner billing evidence, serial, 300-minute cap, R_m; RT-8, RT-9 [OD-S4]",
    ".github/gates/protected_paths.txt": f"{_Q2} — the successor's tooling and its tests are protected paths",
    ".github/workflows/auth2q2-prepare.yml":
        f"{_Q2} — RT-1 to RT-3, Owner-dispatched; the only contents: write job [OD-S3, OD-S4]",
    ".github/workflows/auth2q2-readiness.yml": f"{_Q2} — RT-4 to RT-11, Owner-dispatched, read-only [OD-S3, OD-S4]",
    "tests/fixtures/auth2q2_jobs_api.json": f"{_Q2} — the jobs API shapes of AUTH-2's two D0 runs",
    "tests/test_auth2q2_snapshot.py": f"{_Q2} — RT-0: manifest determinism, canonical tar, hostile restores",
    "tests/test_auth2q2_prepare.py": f"{_Q2} — RT-0: preparation, listing replay, offline guard",
    "tests/test_auth2q2_release.py": f"{_Q2} — RT-0: publish, immutability, download, RT-3 probes",
    "tests/test_auth2q2_attempts.py": f"{_Q2} — RT-0: attempt classes, TECHNICAL_EXHAUSTION, compute proof",
    "tests/test_auth2q2_readiness.py": f"{_Q2} — RT-0: the gate's refusals, ledger, reserve, RT-8, RT-9",
    "tests/test_auth2q2_harness.py": f"{_Q2} — RT-0: restore and cache fallback, offline science, classifiers",
    "tests/test_auth2q2_record.py": f"{_Q2} — RT-0: the readiness record, every shortfall a FAIL",
    "tests/test_auth2q2_workflows.py": f"{_Q2} — RT-0: the two workflows hold to the plan and OD-S3",
    "tests/test_p2_scope_audit.py": "AUTH-2 OD-C4 operator refusal (PR #65) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #67, merged. Two parents: ecfec829 (main before, AUTH_2Q2_READINESS_TOOLING) + 757edee9
# (the claude/p2-h1-g11-records branch).
H1_G11_RECORDS_MERGE = "1078c2f69120acb6f10f05e8b18dccc39349342b"

# H1 G11 records (Owner decisions G5 "host check", 2026-10-17T14:39Z, and G6 "both",
# 2026-10-17T17:59Z; Owner directive "PREPARE NEXT H1 PHASE NOW", 2026-10-17T18:09Z, item 2), with
# the vanished-upstream pin gate (Owner directive, 2026-10-17T21:39:21Z: fix only this, without
# weakening hash, identity, provenance or security). Records and the gate only: the frozen H1
# package, every P2 file, the registry, the trial ledger and every runtime file are untouched;
# upstream_pins.json is byte-identical and no GPL-3.0 source is committed.
# These entries were BRANCH_SCOPE while it was in flight.
_G11 = "H1 G11 records (G5 RECOVERED, G6 amendments)"
H1_G11_RECORDS_SCOPE: dict[str, str] = {
    "research/paper/h1/amendments/G5_HOST_CHECK.md":
        f"{_G11} — the Owner-host byte check: all five pinned sha256 found [G5]",
    "research/paper/h1/amendments/H1_AMENDMENTS_G6.md":
        f"{_G11} — H1-P2-CONDITION-AMENDMENT-1 and H1-MATERIALISATION-AMENDMENT-1 [G6]",
    "research/external/upstream_vanished.json":
        "vanished-upstream pin gate — btc_strategy_lab listed VANISHED; upstream_pins.json byte-identical",
    "research/external/pin_upstream.py":
        "vanished-upstream pin gate — a pinned 404 is recorded, not failed; reappearing bytes must still match",
    "tests/test_upstream_vanished.py":
        "vanished-upstream pin gate — every way past the gate the pins would not allow is refused",
    "tests/test_p2_scope_audit.py":
        "AUTH-2-DISCOVERY-QUALIFICATION-2 readiness tooling (PR #66) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #68, merged. Two parents: 1078c2f6 (main before, H1_G11_RECORDS) + 50ed3181
# (the claude/p2-h1-prelaunch-prep branch).
H1_PRELAUNCH_PREP_MERGE = "4fec17693347adaf74d7112e6cb304691161f6b8"

# H1 pre-launch preparation (Owner directive "PREPARE NEXT H1 PHASE NOW", 2026-10-17T18:09Z,
# items 3 to 8). Tools and a binder only. Nothing starts H1, sets a T0, writes the frozen package,
# or touches P2.
# These entries were BRANCH_SCOPE while it was in flight.
_PREP = "H1 pre-launch preparation"
H1_PRELAUNCH_PREP_SCOPE: dict[str, str] = {
    "research/paper/h1/launch/h1_materialise.py":
        f"{_PREP} — G.2-b credential-free, hash-verified materialisation [item 3]",
    "research/paper/h1/launch/h1_p2_entry_gate.py":
        f"{_PREP} — H1_P2_ENTRY_GATE: ELIGIBLE / WAITING / BLOCKED from the git ref [item 5]",
    "research/paper/h1/launch/h1_host_placement.py":
        f"{_PREP} — no running P2 cohort on the H1 host; no automatic exception [item 6]",
    "research/paper/h1/launch/h1_launch_card.py":
        f"{_PREP} — the H1_LAUNCH_AUTHORIZATION card, default DENY [item 8]",
    "research/paper/h1/launch/H1_LAUNCH_BINDER.md":
        f"{_PREP} — the launch binder; templates only, no T0 [item 4]",
    "tests/test_h1_launch_prep.py":
        f"{_PREP} — every refusal of the four tools, on synthetic inputs",
    "tests/test_p2_scope_audit.py": "H1 G11 records (PR #67) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #69, merged. Two parents: 4fec1769 (main before, H1_PRELAUNCH_PREP) + 29ec7b98
# (the claude/p2-h1-window-30d branch).
H1_WINDOW_AMENDMENT_MERGE = "f6628477d9e7241e60e0aea2896133d8cb32ab4e"

# H1-WINDOW-AMENDMENT-1 (Owner, 2026-10-17T19:30Z: did not agree to 180 days; 20:29Z: run the plan;
# 20:44Z: 10 days). A record beside the package, effective only on the Owner's merge; the card denies
# until then. The frozen package and P2 are untouched.
# These entries were BRANCH_SCOPE while it was in flight.
_WIN = "H1 window amendment"
H1_WINDOW_AMENDMENT_SCOPE: dict[str, str] = {
    "research/paper/h1/amendments/H1_WINDOW_AMENDMENT_10D.md":
        f"{_WIN} — 10-day operational window (Owner, 2026-10-17T20:44Z), B2 reported only, EDGE_EVIDENCE not evaluated",
    "research/paper/h1/launch/h1_launch_card.py":
        f"{_WIN} — the H1_WINDOW_AMENDMENT row: adopted only at its sha256, through a merge",
    "research/paper/h1/launch/H1_LAUNCH_BINDER.md": f"{_WIN} — the closure schedule names the 10-day END_UTC",
    "tests/test_h1_launch_prep.py": f"{_WIN} — the record is pinned; adoption tested in a scratch repository",
    "tests/test_p2_scope_audit.py": "H1 pre-launch preparation (PR #68) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #70, merged. Two parents: f6628477 (main before, H1_WINDOW_AMENDMENT) + 95571275
# (the claude/p2-closure branch).
P2_CLOSURE_MERGE = "0ce72358c3cf10ac97428ff7b721c45b02353d49"

# P2 CLOSURE (Owner GO 1R 2026-10-24T21:37Z, GO 2 21:42Z, GO 3 21:46Z, closure preparation 21:54Z).
# FP-CONTROL-3 closes under trigger A, the contract section 7 NORMAL END. Records only: no
# runtime, strategy, risk or dataset file changes, and the frozen identity of every row is kept.
# These entries were BRANCH_SCOPE while it was in flight.
_CLOSE = "P2 closure"
P2_CLOSURE_SCOPE: dict[str, str] = {
    "docs/p2/P2_CLOSURE.md": f"{_CLOSE} — the stage closure record and its machine block (contract section 12)",
    "research/fp/records/forward_paper_cohort_registry.json":
        f"{_CLOSE} — FP-CONTROL-3 CLOSED with its outcome; fp_run_active false; frozen identity unchanged",
    "research/fp/records/evidence_digest_publication.json":
        f"{_CLOSE} — Tier 2 digest of the sealed FP-CONTROL-3 cohort lane l2-cohort-20260924T120000Z",
    "tests/conftest.py":
        f"{_CLOSE} — live role after closure; executable_registry: isolated temporary fixtures for tests "
        "that must drive an open row",
    "tests/test_fp_capture.py": f"{_CLOSE} — the capture loop runs against the isolated executable registry",
    "tests/test_fp_lane_adversarial.py":
        f"{_CLOSE} — lane proofs run against the isolated executable registry and a disposable copy",
    "tests/test_fp_lane_io_adversarial.py":
        f"{_CLOSE} — lane I/O and launcher proofs run against the isolated executable registry",
    "tests/test_fp_overlay.py": f"{_CLOSE} — the overlay guard runs against the isolated executable registry",
    "tests/test_fp_successor_instance.py":
        f"{_CLOSE} — the CLOSED lawful state; new negatives: a committed CLOSED cohort cannot be "
        "selected, resolved or rendered",
    ".github/workflows/ci.yml":
        f"{_CLOSE} — the overlay render asserts the CLOSED cohort is refused, then renders it in a "
        "disposable executable copy",
    "tests/test_h1_launch_prep.py":
        f"{_CLOSE} — the card's P2 rows mirror the entry gate at the ref, before and after the closure merge",
    "tests/test_p2_scope_audit.py": "H1 window amendment (PR #69) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #71, merged. Two parents: 0ce72358 (main before, P2_CLOSURE) + b9cbf91d
# (the claude/p3-pln-00-reconciliation branch). These entries were BRANCH_SCOPE while it was in flight.
P3_PLN_00_MERGE = "f597041a1f813c27a03e90b1659aea60a7065044"

# P3-PLN-00 — Final P2 → P3 Reconciliation (master plan §17.1). Planning only: no P3 execution,
# no runtime, strategy, risk, dataset, registry or evidence change.
_PLN00 = "P3-PLN-00 reconciliation"
P3_PLN_00_SCOPE: dict[str, str] = {
    "docs/p2/P3_PLN_00_P2_TO_P3_RECONCILIATION.md":
        f"{_PLN00} — P2 outcome reviewed, findings placed in existing P3 workstreams, entry truth inputs",
    "CLAUDE.md": f"{_PLN00} — the stage pointer: P2 closed, P3 planning only (P3_STARTED = NO)",
    "tests/test_p2_scope_audit.py": "P2 closure (PR #70) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #72, merged. Two parents: f597041a (main before, P3_PLN_00) + 2ef29735
# (the claude/p3-pln-01-contract branch). These entries were BRANCH_SCOPE while it was in flight.
P3_PLN_01_MERGE = "fcd06b2124445c12808aa259f070d9e9a39999aa"

# P3-PLN-01 — Contract & Acceptance (master plan §17). A draft stage contract for Owner review and
# freeze. Planning only: P3_STARTED stays NO, and execution needs a separate Owner authorization record.
_PLN01 = "P3-PLN-01 contract"
P3_PLN_01_SCOPE: dict[str, str] = {
    "docs/p3/P3_CONTRACT.md":
        f"{_PLN01} — the P3 stage contract draft: 12 workstreams, acceptance, priorities, authorization package",
    "tests/test_p2_scope_audit.py": "P3-PLN-00 (PR #71) pinned to its merge; docs/p3/ admitted; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #73, merged. Two parents: fcd06b21 (main before, P3_PLN_01) + 5cbb6f87
# (the owner/p3-execution-authorization branch). These entries were BRANCH_SCOPE while it was in flight.
P3_AUTHORIZATION_MERGE = "7b1b1fa190405dd5dee1266fdf3975a994a7c171"

# OWNER_AUTHORIZES_P3_EXECUTION (master plan §17.1, P3_CONTRACT.md §9). The Owner's own record;
# paper-only; names the frozen contract by sha256 and freeze merge.
_P3AUTH = "Owner P3 execution authorization"
P3_AUTHORIZATION_SCOPE: dict[str, str] = {
    "docs/p3/OWNER_P3_EXECUTION_AUTHORIZATION.md":
        f"{_P3AUTH} — the record P3_CONTRACT.md §9 requires, created by an Owner-merged PR",
    "tests/test_p2_scope_audit.py": "P3-PLN-01 (PR #72) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #74, merged. Two parents: 7b1b1fa1 (main before, P3_AUTHORIZATION) + 0112a81e
# (the claude/p3-pln-02-state-inventory branch). These entries were BRANCH_SCOPE while it was in flight.
P3_PLN_02_MERGE = "652f06f71a2ff5876c4d6dab84345696e6339fab"

# P3-PLN-02 — State & Recovery Inventory (P3_CONTRACT.md §3), executed under the Owner P3 authorization.
# A read-only classifier and recovery verifier over existing tooling; no runtime, strategy, risk,
# dataset, registry or evidence change.
_PLN02 = "P3-PLN-02 state inventory"
P3_PLN_02_SCOPE: dict[str, str] = {
    "research/p3/__init__.py": f"{_PLN02} — package marker",
    "research/p3/state_inventory.py": f"{_PLN02} — classify every stateful file and verify its recovery source",
    "research/p3/records/state_classes.json": f"{_PLN02} — the declared state classes (runtime, worktree, operator)",
    "scripts/p3/state_inventory.py":
        f"{_PLN02} — CLI over the library, reusing verify_archive; in scripts/p3/ so it stays outside the "
        "FP runtime tree (scripts/*.py) that the frozen P2 semantic identity covers",
    "tests/test_p3_state_inventory.py": f"{_PLN02} — every refusal produced on synthetic repositories",
    "docs/p3/PLN_02_STATE_INVENTORY.md": f"{_PLN02} — the execution record and verdict on this host",
    "CLAUDE.md": f"{_PLN02} — the stage pointer: P3 executing under its frozen contract and Owner authorization",
    "tests/test_p2_scope_audit.py": "Owner P3 authorization (PR #73) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #75, merged. Two parents: 652f06f7 (main before, P3_PLN_02) + 330a0812
# (the claude/p3-pln-03-backup-restore branch). These entries were BRANCH_SCOPE while it was in flight.
P3_PLN_03_MERGE = "71b9f3025718e2c36d47687afef077042ad7a2c8"

# P3-PLN-03 — Backup & Restore (P3_CONTRACT.md §3), executed under the Owner P3 authorization.
# Append-only backup sets and a restore drill over existing tools; the host timer is prepared, not
# installed. No runtime, strategy, risk, dataset, registry or evidence change.
_PLN03 = "P3-PLN-03 backup"
P3_PLN_03_SCOPE: dict[str, str] = {
    "research/p3/backup.py": f"{_PLN03} — append-only sets, verify, restore drill (wraps tar/zstd, git bundle)",
    "research/p3/state_inventory.py": f"{_PLN03} — symlinks verified by target text, the same rule as backup.py",
    "scripts/p3/backup.py": f"{_PLN03} — CLI create/verify/drill; config load via the pinned engine, no trading",
    "scripts/p3/scheduled_backup.sh": f"{_PLN03} — the scheduled wrapper; append-only, never deletes",
    "scripts/p3/units/tlos-p3-backup.service": f"{_PLN03} — systemd user service (installed by the Owner)",
    "scripts/p3/units/tlos-p3-backup.timer": f"{_PLN03} — daily systemd user timer (installed by the Owner)",
    "tests/test_p3_backup.py": f"{_PLN03} — every refusal produced on synthetic roots",
    "tests/test_p3_state_inventory.py": f"{_PLN03} — a symlink is verified by its target text",
    "docs/p3/PLN_03_BACKUP_RESTORE.md": f"{_PLN03} — the execution record: a real set and a passing drill",
    "tests/test_p2_scope_audit.py": "P3-PLN-02 (PR #74) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #76, merged. Two parents: 71b9f302 (main before, P3_PLN_03) + 5bc6c698
# (the claude/p3-pln-06-07-08-ops branch). These entries were BRANCH_SCOPE while it was in flight.
P3_OPS_MERGE = "2161277792c6c72deac9db01989f7a91c66e7ec7"

# P3-PLN-06/07/08 — operational tooling that does not depend on PLN-04 (P3_CONTRACT.md §3, §5): a health
# check, a per-execution audit (F-2) and a kill switch with an attributable operator ledger (O-1).
# All of it outside the FP runtime tree; no runtime, strategy, risk, dataset, registry or evidence change.
_OPS = "P3-PLN-06/07/08 operations"
P3_OPS_SCOPE: dict[str, str] = {
    "research/p3/health.py": f"{_OPS} — PLN-06 health: capacity, RPO, timers, normal-end detection (F-3)",
    "scripts/p3/health_check.py": f"{_OPS} — PLN-06 health CLI, §19 severities, read-only",
    "research/p3/execution_audit.py": f"{_OPS} — PLN-07 every fill backed by an admitted decision (F-2)",
    "scripts/p3/execution_audit.py": f"{_OPS} — PLN-07 audit CLI, read-only",
    "research/p3/kill_switch.py": f"{_OPS} — PLN-08 stop every paper runtime, hash-chained operator ledger (O-1)",
    "scripts/p3/kill_switch.py": f"{_OPS} — PLN-08 kill switch CLI; docker stop only, reason required",
    "tests/test_p3_operations.py": f"{_OPS} — every refusal produced with injected docker/systemctl",
    "docs/p3/PLN_06_07_08_OPERATIONS.md": f"{_OPS} — the execution record: real drill, real audit, real health run",
    "tests/test_p2_scope_audit.py": "P3-PLN-03 (PR #75) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #77, merged. Two parents: 21612777 (main before, P3_OPS) + f25c3f85
# (the claude/p3-pln-04-recovery branch). These entries were BRANCH_SCOPE while it was in flight.
P3_PLN_04_MERGE = "9d984f4db4024a54e0d208aacb18a0ea8b13c991"

# P3-PLN-04 — restart / reboot / host recovery (P3_CONTRACT.md §3): the terminal-state restart guard (F-5),
# resume authorization and the reboot snapshot/verify; the PLN-07 failure/recovery matrix; the PLN-06
# Prometheus textfile; PLN-02/03 acceptance updates. Outside the FP runtime tree; no runtime, strategy,
# risk, dataset, registry or evidence change.
_PLN04 = "P3-PLN-04 recovery"
P3_PLN_04_SCOPE: dict[str, str] = {
    "research/p3/recovery.py": f"{_PLN04} — may_restart guard, authorize_resume, reboot snapshot and verify",
    "scripts/p3/recovery.py": f"{_PLN04} — CLI may-restart (exit 0/3), authorize-resume, snapshot, verify-boot",
    "research/p3/health.py": f"{_PLN04} — PLN-06 Prometheus text exposition, written atomically",
    "scripts/p3/health_check.py": f"{_PLN04} — PLN-06 --prom-textfile",
    "tests/test_p3_recovery.py": f"{_PLN04} — every negative control produced, synthetic only",
    "docs/p3/PLN_04_RECOVERY.md": f"{_PLN04} — the execution record and the PLN-07 failure/recovery matrix",
    "docs/p3/PLN_02_STATE_INVENTORY.md": f"{_PLN04} — PLN-02 acceptance update: all 14 roots PASS",
    "docs/p3/PLN_03_BACKUP_RESTORE.md": f"{_PLN04} — PLN-03 acceptance update: second set and drill PASS",
    "tests/test_p2_scope_audit.py": "P3-PLN-06/07/08 (PR #76) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #78, merged. Two parents: 9d984f4d (main before, P3_PLN_04) + c45f0042
# (the claude/p3-pln-03-06-schedule branch). These entries were BRANCH_SCOPE while it was in flight.
P3_SCHED_MERGE = "253dbf29e3c5e6e69068d642248fd0fac185c254"

# P3-PLN-06 alert delivery (scheduled health with journal + desktop notification and the Prometheus
# textfile) and P3-PLN-05 offsite push with destination verification. Units prepared, not installed.
# Outside the FP runtime tree; no runtime, strategy, risk, dataset, registry or evidence change.
_SCHED = "P3-PLN-05/06 durability and alerts"
P3_SCHED_SCOPE: dict[str, str] = {
    "scripts/p3/scheduled_health.sh": f"{_SCHED} — hourly health: textfile, journal, notify-send on WARNING/CRITICAL",
    "scripts/p3/units/tlos-p3-health.service": f"{_SCHED} — systemd user service; SuccessExitStatus=1 2",
    "scripts/p3/units/tlos-p3-health.timer": f"{_SCHED} — hourly systemd user timer (installed by the Owner)",
    "scripts/p3/units/tlos-p3-backup.service": f"{_SCHED} — Documentation path points at the tools checkout",
    "research/p3/offsite.py": f"{_SCHED} — push a verified set, verify on the destination, append-only",
    "scripts/p3/offsite.py": f"{_SCHED} — offsite CLI",
    "tests/test_p3_offsite_and_units.py": f"{_SCHED} — offsite refusals and unit invariants, synthetic only",
    "docs/p3/PLN_05_EVIDENCE_DURABILITY.md": f"{_SCHED} — PLN-05 record: tiers today, Tier 3 pending a host",
    "docs/p3/PLN_06_07_08_OPERATIONS.md": f"{_SCHED} — PLN-06 alert delivery update",
    "tests/test_p2_scope_audit.py": "P3-PLN-04 (PR #77) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #79, merged. Two parents: 253dbf29 (main before, P3_SCHED) + 819ee7e4
# (the claude/p3-acceptance-03-06 branch). These entries were BRANCH_SCOPE while it was in flight.
P3_ACC_MERGE = "8f673eb448b3490710a90c0caedabbd30d561e24"

# P3 acceptance record for PLN-03 (first scheduled set under systemd: verify + restore drill PASS) and
# PLN-06 (hourly health under systemd), plus classifying the hourly-rewritten health textfile as derived
# so the operator inventory is not perpetually STALE. No runtime, strategy, risk, dataset or evidence change.
_ACC = "P3-PLN-03/06 scheduled acceptance"
P3_ACC_SCOPE: dict[str, str] = {
    "research/p3/records/state_classes.json": f"{_ACC} — operator profile: p3-evidence/*.prom is derived (rewritten hourly)",
    "docs/p3/PLN_03_BACKUP_RESTORE.md": f"{_ACC} — scheduled set 20261025T211956Z verify + drill PASS",
    "docs/p3/PLN_06_07_08_OPERATIONS.md": f"{_ACC} — health timer installed and running; remaining PLN-06 condition",
    "tests/test_p3_state_inventory.py": f"{_ACC} — the health textfile is classified derived in the operator profile",
    "tests/test_p2_scope_audit.py": "P3-PLN-05/06 (PR #78) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}

# PR #80, merged. Two parents: 8f673eb4 (main before, P3_ACC) + 7919e776
# (the claude/p3-pln-09-authority branch). These entries were BRANCH_SCOPE while it was in flight.
P3_PLN_09_AUTHORITY_MERGE = "d21bebe57844ec57104df953b41f03eb2784fdf1"

# P3-PLN-09 product-shape authority: the Owner-identified frozen sources, byte for byte, with digests,
# and the identification + reconciliation record. Documents only; no runtime, strategy, risk, dataset,
# registry or evidence change.
_P09A = "P3-PLN-09 product-shape authority"
P3_PLN_09_AUTHORITY_SCOPE: dict[str, str] = {
    "docs/p3/PLN_09_PRODUCT_SHAPE_AUTHORITY.md": f"{_P09A} — identification, hash verification, contract reconciliation",
    "docs/p3/product_shape/Trading_Lab_OS_Prototype_v0.2.5_FINAL.html": f"{_P09A} — frozen prototype, sha256 e17d50dc…",
    "docs/p3/product_shape/Trading_Lab_OS_LEVEL_A_FREEZE_RECORD_v1.0.md": f"{_P09A} — Level-A freeze record v1.0",
    "docs/p3/product_shape/TLOS_Control_Room_Approved_Design.md": f"{_P09A} — approved visual direction 2026-09-24",
    "docs/p3/product_shape/Trading_Lab_OS_CLAUDE_NEW_SESSION_PACK_v1.0.md": f"{_P09A} — carries Shape Lock v1.2 as Appendix A",
    "docs/p3/product_shape/SOURCES.sha256": f"{_P09A} — the digests of the four sources",
    "tests/test_p3_product_shape_authority.py": f"{_P09A} — digests, prototype identity, 12 screens, offline CSP",
    "tests/test_p2_scope_audit.py": "P3-PLN-03/06 acceptance (PR #79) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}

# PR #81, merged. Two parents: d21bebe5 (main before, P3_PLN_09_AUTHORITY) + 6a12899c
# (the claude/p3-pln-09-command-center branch). These entries were BRANCH_SCOPE while it was in flight.
P3_PLN_09_CR_MERGE = "82a975d3ea91c33bfade4b3ce5729c206db1d4ef"

# P3-PLN-09 Control Room, slices 1–2: the frozen prototype used verbatim plus a read-only evidence
# adapter; 8 of 12 screens bound to live evidence; hourly regeneration in the health run.
_P09CR = "P3-PLN-09 Control Room"
P3_PLN_09_CR_SCOPE: dict[str, str] = {
    "research/p3/control_room.py": f"{_P09CR} — collect / project / build; digest-checked prototype, read-only",
    "research/p3/control_room_live.js": f"{_P09CR} — live adapter: same markup, data-bearing components only",
    "research/p3/records/p3_workstreams.json": f"{_P09CR} — governed PLN-00..11 status read by the view",
    "research/p3/records/state_classes.json": f"{_P09CR} — operator profile: p3-evidence/control_room/* is derived",
    "scripts/p3/control_room.py": f"{_P09CR} — build CLI",
    "scripts/p3/scheduled_health.sh": f"{_P09CR} — hourly view regeneration; health verdict unchanged",
    "research/p3/health.py": f"{_P09CR} — standard_findings shared by the health CLI and the view",
    "scripts/p3/health_check.py": f"{_P09CR} — uses health.standard_findings",
    "tests/test_p3_control_room.py": f"{_P09CR} — degraded mappings and refusals, synthetic only",
    "docs/p3/PLN_09_CONTROL_ROOM.md": f"{_P09CR} — execution record, slices 1–2, binding plan and estimate",
    "tests/test_p2_scope_audit.py": "P3-PLN-09 authority (PR #80) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


# PR #87, merged. Two parents: 82a975d3 (main before, P3_PLN_09_CR) + 507e0f77
# (the claude/p3-pln-09-slice-3 branch). These entries were BRANCH_SCOPE while it was in flight.
P3_PLN_09_S3_MERGE = "bf208ba647c76e2350b99a4bb744e9b9ad570d40"

# P3-PLN-09 Control Room, slice 3: Decisions, Trades & Positions, Market Workspace and Settings bound from
# the sealed cohort named by the newest PLN-07 audit record (read-only); all 12 screens bound.
_P09S3 = "P3-PLN-09 Control Room"
P3_PLN_09_S3_SCOPE: dict[str, str] = {
    "research/p3/control_room.py": f"{_P09S3} — slice 3: sealed cohort reader and the four remaining screens",
    "research/p3/control_room_live.js": f"{_P09S3} — slice 3: Decisions, Trades & Positions, Market Workspace, Settings",
    "research/p3/records/p3_workstreams.json": f"{_P09S3} — PLN-09 evidence: 12 of 12 screens bound",
    "tests/test_p3_control_room.py": f"{_P09S3} — slice-3 sealed screens and missing-evidence negatives, synthetic only",
    "docs/p3/PLN_09_CONTROL_ROOM.md": f"{_P09S3} — execution record, slice 3",
    "tests/test_p2_scope_audit.py": "P3-PLN-09 Control Room slices 1–2 (PR #81) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}

# PR #85, merged. Two parents: bf208ba6 (main before, P3_PLN_09_S3) + dc385f10
# (the claude/p3-pln-06-alerting branch). These entries were BRANCH_SCOPE while it was in flight.
P3_PLN_06_ALERT_MERGE = "19d77e905100bca4063fcae309d28aa43fb9e9e5"

# P3-PLN-06 §19 alert leg: node-exporter scrape target, alert rules with promtool rule tests, an
# Alertmanager template with no secrets, a separate loopback-only ops-plane compose project, and the §19
# CRITICAL health checks (fail-closed). Prepared, not installed or started.
_P06AL = "P3-PLN-06 §19 alert leg"
P3_PLN_06_ALERT_SCOPE: dict[str, str] = {
    "scripts/p3/ops/docker-compose.p3-ops.yml": f"{_P06AL} — separate ops-plane compose: Prometheus + Alertmanager, 127.0.0.1 only",
    "scripts/p3/ops/prometheus.yml": f"{_P06AL} — scrape the host node-exporter, load the rules, send to Alertmanager",
    "scripts/p3/ops/rules/tlos_p3_alerts.yml": f"{_P06AL} — §19 CRITICAL/WARNING, staleness, exporter-down, watchdog",
    "scripts/p3/ops/rules/tlos_p3_alerts.test.yml": f"{_P06AL} — promtool rule unit tests: every condition raises its alert",
    "scripts/p3/ops/alertmanager.yml.template": f"{_P06AL} — receivers via *_file secrets, routed to null until the Owner chooses",
    "docs/p3/PLN_06_ALERTING.md": f"{_P06AL} — design, §19 coverage matrix, verification, Owner runbook, acceptance mapping",
    "docs/p3/PLN_06_07_08_OPERATIONS.md": f"{_P06AL} — pointer update; PLN-06 stays PARTIAL",
    "tests/test_p3_alerting.py": f"{_P06AL} — rules read only emitted metrics; loopback, pinned, secret-free",
    "research/p3/health.py": f"{_P06AL} — §19 CRITICAL checks: paper guard, real-money state, evidence chains, paper runtime vs registry",
    "scripts/p3/health_check.py": f"{_P06AL} — runs the §19 checks by default (--no-s19 for diagnosis)",
    "research/p3/control_room.py": f"{_P06AL} — the Control Room health view includes the §19 checks",
    "research/p3/records/p3_workstreams.json": f"{_P06AL} — PLN-06 evidence text: §19 coverage, still PARTIAL",
    "tests/test_p3_health_s19.py": f"{_P06AL} — positive/negative per §19 condition; no secret value in any finding",
    "tests/test_p2_scope_audit.py": "P3-PLN-09 Control Room slice 3 (PR #87) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


MERGED_STAGE_SCOPES: dict[str, tuple[str, dict[str, str]]] = {
    "S2": (S2_MERGE, S2_SCOPE),
    "S3": (S3_MERGE, S3_SCOPE),
    "S4": (S4_MERGE, S4_SCOPE),
    "RECOVERY": (RECOVERY_MERGE, RECOVERY_SCOPE),
    "S8": (S8_MERGE, S8_SCOPE),
    "S9A": (S9A_MERGE, S9A_SCOPE),
    "S9B": (S9B_MERGE, S9B_SCOPE),
    "S9C": (S9C_MERGE, S9C_SCOPE),
    "RUNTIME_RECON_0927": (RUNTIME_RECON_0927_MERGE, RUNTIME_RECON_0927_SCOPE),
    "STAGE0_CLOSURE": (STAGE0_CLOSURE_MERGE, STAGE0_CLOSURE_SCOPE),
    "RESEARCH_FOUNDATION_UNIT_A": (RESEARCH_FOUNDATION_UNIT_A_MERGE, RESEARCH_FOUNDATION_UNIT_A_SCOPE),
    "RESEARCH_FOUNDATION_UNIT_B": (RESEARCH_FOUNDATION_UNIT_B_MERGE, RESEARCH_FOUNDATION_UNIT_B_SCOPE),
    "RESEARCH_FOUNDATION_CLOSURE_1": (RESEARCH_FOUNDATION_CLOSURE_1_MERGE,
                                      RESEARCH_FOUNDATION_CLOSURE_1_SCOPE),
    "MEAN_REVERSION_CYCLE1": (MEAN_REVERSION_CYCLE1_MERGE, MEAN_REVERSION_CYCLE1_SCOPE),
    "H1_QUALIFICATION": (H1_QUALIFICATION_MERGE, H1_QUALIFICATION_SCOPE),
    "ACCOUNT_HANDOFF_1": (ACCOUNT_HANDOFF_1_MERGE, ACCOUNT_HANDOFF_1_SCOPE),
    "RESEARCH_CYCLE1_CLOSURE_1": (RESEARCH_CYCLE1_CLOSURE_1_MERGE,
                                  RESEARCH_CYCLE1_CLOSURE_1_SCOPE),
    "H1_PAPER_ADMISSION_1": (H1_PAPER_ADMISSION_1_MERGE, H1_PAPER_ADMISSION_1_SCOPE),
    "MASTER_PLAN_1": (MASTER_PLAN_1_MERGE, MASTER_PLAN_1_SCOPE),
    "CYCLE2_OPENING_1": (CYCLE2_OPENING_1_MERGE, CYCLE2_OPENING_1_SCOPE),
    "CYCLE2_UNIT_7_1": (CYCLE2_UNIT_7_1_MERGE, CYCLE2_UNIT_7_1_SCOPE),
    "CYCLE2_UNIT_7_1A": (CYCLE2_UNIT_7_1A_MERGE, CYCLE2_UNIT_7_1A_SCOPE),
    "CYCLE2_UNIT_7_2A": (CYCLE2_UNIT_7_2A_MERGE, CYCLE2_UNIT_7_2A_SCOPE),
    "CYCLE2_UNIT_7_2B1": (CYCLE2_UNIT_7_2B1_MERGE, CYCLE2_UNIT_7_2B1_SCOPE),
    "CYCLE2_UNIT_7_2B2": (CYCLE2_UNIT_7_2B2_MERGE, CYCLE2_UNIT_7_2B2_SCOPE),
    "CYCLE2_UNIT_7_3A": (CYCLE2_UNIT_7_3A_MERGE, CYCLE2_UNIT_7_3A_SCOPE),
    "CYCLE2_UNIT_7_3R": (CYCLE2_UNIT_7_3R_MERGE, CYCLE2_UNIT_7_3R_SCOPE),
    "RESEARCH_CYCLE2_CLOSURE_1": (RESEARCH_CYCLE2_CLOSURE_1_MERGE, RESEARCH_CYCLE2_CLOSURE_1_SCOPE),
    "AUTH_1": (AUTH_1_MERGE, AUTH_1_SCOPE),
    "CEA_1_TEST_FIX": (CEA_1_TEST_FIX_MERGE, CEA_1_TEST_FIX_SCOPE),
    "CEA_1_MERGE_LAW_FETCH": (CEA_1_MERGE_LAW_FETCH_MERGE, CEA_1_MERGE_LAW_FETCH_SCOPE),
    "CEA_1_MERGE_LAW_LEDGER_IMPORT": (CEA_1_MERGE_LAW_LEDGER_IMPORT_MERGE, CEA_1_MERGE_LAW_LEDGER_IMPORT_SCOPE),
    "AUTH_2": (AUTH_2_MERGE, AUTH_2_SCOPE),
    "AUTH_2_OPERATOR_GATE": (AUTH_2_OPERATOR_GATE_MERGE, AUTH_2_OPERATOR_GATE_SCOPE),
    "AUTH_2_BILLING_EVIDENCE": (AUTH_2_BILLING_EVIDENCE_MERGE, AUTH_2_BILLING_EVIDENCE_SCOPE),
    "AUTH_2_OWNER_BILLING_EVIDENCE_BRIDGE": (AUTH_2_OWNER_BILLING_EVIDENCE_BRIDGE_MERGE,
                                             AUTH_2_OWNER_BILLING_EVIDENCE_BRIDGE_SCOPE),
    "AUTH_2_USAGE_REPORT_REPOSITORY_NAME": (AUTH_2_USAGE_REPORT_REPOSITORY_NAME_MERGE,
                                            AUTH_2_USAGE_REPORT_REPOSITORY_NAME_SCOPE),
    "AUTH_2_NODE_CHECKOUT_HISTORY": (AUTH_2_NODE_CHECKOUT_HISTORY_MERGE, AUTH_2_NODE_CHECKOUT_HISTORY_SCOPE),
    "AUTH2_GOVERNANCE_CLOSURE_1": (AUTH2_GOVERNANCE_CLOSURE_1_MERGE, AUTH2_GOVERNANCE_CLOSURE_1_SCOPE),
    "AUTH_2_OD_C4_OPERATOR_REFUSAL": (AUTH_2_OD_C4_OPERATOR_REFUSAL_MERGE, AUTH_2_OD_C4_OPERATOR_REFUSAL_SCOPE),
    "AUTH_2Q2_READINESS_TOOLING": (AUTH_2Q2_READINESS_TOOLING_MERGE, AUTH_2Q2_READINESS_TOOLING_SCOPE),
    "H1_G11_RECORDS": (H1_G11_RECORDS_MERGE, H1_G11_RECORDS_SCOPE),
    "H1_PRELAUNCH_PREP": (H1_PRELAUNCH_PREP_MERGE, H1_PRELAUNCH_PREP_SCOPE),
    "H1_WINDOW_AMENDMENT": (H1_WINDOW_AMENDMENT_MERGE, H1_WINDOW_AMENDMENT_SCOPE),
    "P2_CLOSURE": (P2_CLOSURE_MERGE, P2_CLOSURE_SCOPE),
    "P3_PLN_00": (P3_PLN_00_MERGE, P3_PLN_00_SCOPE),
    "P3_PLN_01": (P3_PLN_01_MERGE, P3_PLN_01_SCOPE),
    "P3_AUTHORIZATION": (P3_AUTHORIZATION_MERGE, P3_AUTHORIZATION_SCOPE),
    "P3_PLN_02": (P3_PLN_02_MERGE, P3_PLN_02_SCOPE),
    "P3_PLN_03": (P3_PLN_03_MERGE, P3_PLN_03_SCOPE),
    "P3_OPS": (P3_OPS_MERGE, P3_OPS_SCOPE),
    "P3_PLN_04": (P3_PLN_04_MERGE, P3_PLN_04_SCOPE),
    "P3_SCHED": (P3_SCHED_MERGE, P3_SCHED_SCOPE),
    "P3_ACC": (P3_ACC_MERGE, P3_ACC_SCOPE),
    "P3_PLN_09_AUTHORITY": (P3_PLN_09_AUTHORITY_MERGE, P3_PLN_09_AUTHORITY_SCOPE),
    "P3_PLN_09_CR": (P3_PLN_09_CR_MERGE, P3_PLN_09_CR_SCOPE),
    "P3_PLN_09_S3": (P3_PLN_09_S3_MERGE, P3_PLN_09_S3_SCOPE),
    "P3_PLN_06_ALERT": (P3_PLN_06_ALERT_MERGE, P3_PLN_06_ALERT_SCOPE),
}

# The stage in flight. Every path this branch touches → the requirement it
# satisfies. When the stage merges, its entry moves into MERGED_STAGE_SCOPES
# against the merge commit, where it stops depending on which branch is checked
# out and starts being a permanent record.

# Owner research authority record for A1b (Lane B, outside P3) and its field test.
# No runtime, strategy, risk, dataset, registry, trial-ledger or evidence change.
_BR = "OWNER-RESEARCH-AUTHORIZATION-A1B-1"
BRANCH_SCOPE: dict[str, str] = {
    "research/OWNER_RESEARCH_AUTHORIZATION_A1B_1.md": f"{_BR} — the Owner's Lane B authority record (binds on Owner merge)",
    "tests/test_owner_research_authorization_a1b.py": f"{_BR} — every field exactly once; boundary fields NO",
    "tests/test_p2_scope_audit.py": "P3-PLN-06 §19 alert leg (PR #85) pinned to its merge; this branch's scope",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def _resolve_base_ref() -> str | None:
    """The merge base against main, however this checkout names it — or None.

    A working clone has `origin/main`; a CI `pull_request` checkout is detached
    and may have only `FETCH_HEAD`; and this repository's own parity convention
    (`conftest.clone_at_head`) deliberately removes the remote entirely, so that
    a reproduction cannot depend on the repository it came from.

    In that last case there is genuinely no baseline, and the honest answer is
    None rather than an invented one. The branch-layer audits below skip, the
    pinned and state-dependent ones still run, and `test_the_audit_was_not
    _silently_skipped` plus a CI step make sure the skip can never become the
    normal case where it matters.
    """
    for ref in ("origin/main", "refs/remotes/origin/main", "main", "FETCH_HEAD"):
        probe = subprocess.run(["git", "merge-base", "HEAD", ref], capture_output=True, text=True)
        if probe.returncode == 0 and probe.stdout.strip():
            return probe.stdout.strip()
    subprocess.run(["git", "fetch", "--quiet", "origin", "main"], capture_output=True, text=True)
    probe = subprocess.run(["git", "merge-base", "HEAD", "FETCH_HEAD"],
                           capture_output=True, text=True)
    if probe.returncode == 0 and probe.stdout.strip():
        return probe.stdout.strip()
    return None


BASE_REF = _resolve_base_ref()

# Applied to the audits that compare this branch against main. Never applied to
# the pinned audits, which name both of their commits and therefore resolve in
# any checkout that has the history at all; and never to the audits that read
# the current state — "no T0 exists" is answerable in any checkout, and letting
# it skip alongside the others would quietly drop the checks that matter most.
needs_baseline = pytest.mark.skipif(
    BASE_REF is None,
    reason=(
        "no main reference in this checkout, so there is no baseline to diff against. "
        "The pinned and state-dependent audits in this file still run."
    ),
)


def merge_base() -> str:
    assert BASE_REF is not None
    return BASE_REF


def head() -> str:
    return _git("rev-parse", "HEAD").strip()


def changed_paths() -> list[str]:
    """Every path this branch changes: committed, staged, or still untracked.

    All three, because the audit has to give the same answer before the commit
    as after it. A map checked only against committed history would let a file
    be added in the same breath as the commit that was supposed to justify it.
    """
    paths = {p for p in _git("diff", "--name-only", merge_base()).split("\n") if p.strip()}
    for line in _git("status", "--porcelain").split("\n"):
        if not line.strip():
            continue
        entry = line[3:].strip().strip('"')
        # A rename reads `old -> new`. Both ends are changes and both need a
        # reason: the destination because it is new, and the source because its
        # disappearance is itself a change someone has to account for.
        if " -> " in entry:
            # A rename in the working tree reads `old -> new`. Only the
            # destination is counted: against main, a file created and renamed
            # within this branch has one net path, and requiring a scope entry
            # for an intermediate name that never reached main would make the
            # map wrong the moment it was committed.
            entry = entry.split(" -> ", 1)[1].strip().strip('"')
            paths.add(entry)
        else:
            paths.add(entry)
    return sorted(paths)


def stage_changed_paths(merge_commit: str) -> list[str]:
    """Exactly what a merged stage brought onto main.

    A merge commit's diff against its FIRST parent is the branch's net
    contribution: what main gained by taking it, with everything main already
    had excluded. Naming both ends is what makes this audit permanent — unlike
    a diff against "main", which empties out the moment the branch is merged.
    """
    return sorted(
        p for p in _git("diff", "--name-only", f"{merge_commit}^1", merge_commit).split("\n")
        if p.strip()
    )


def blob_at(rev: str, path: str) -> str | None:
    result = subprocess.run(["git", "rev-parse", f"{rev}:{path}"],
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def registry_at(rev: str) -> dict:
    return json.loads(_git("show", f"{rev}:research/fp/records/forward_paper_cohort_registry.json"))


MERGED_STAGES = sorted(MERGED_STAGE_SCOPES)
# ".github/gates/" is where a CI gate lives when it must stay OUTSIDE
# RUNTIME_TREE — contract section 5 puts scripts/*.py inside it, and a gate
# added there between Mq and the freeze would break the equivalence proof.
# "charters/" and "verification/" arrive with CEA-1 (AUTH-1): the program charters
# and the first charter's product directory. Both are outside RUNTIME_TREE.
# The AUTH-2 governance closure record is admitted by its own folder, not by docs/governance/
# (Owner decision OD-C1, 2026-10-12): the record, its evidence, its generator and any
# append-only errata.
# docs/p3/ holds the P3 stage records (contract, authorization, closure), as docs/p2/ does for P2.
ALLOWED_PREFIXES = ("research/", "scripts/", "tests/", "docs/p2/", "docs/p3/",
                    ".github/workflows/", ".github/gates/", "charters/", "verification/",
                    "docs/governance/records/AUTH2-GOVERNANCE-CLOSURE-1/")
# The master planning SSOT is admitted by its exact path, not by a docs/governance/
# prefix: one non-authorizing planning document is the whole of what that
# directory is for, and a prefix would let anything else arrive beside it.
# The continuous-execution law is admitted the same way, by its exact path.
ALLOWED_FILES = (".gitignore", "MANIFEST.txt", "CLAUDE.md",
                 "docs/governance/TRADING_LAB_OS_MASTER_EXECUTION_AND_MONITORING_PLAN.md",
                 "docs/governance/CONTINUOUS_EXECUTION_AUTHORITY_1.md")


# -- the pinned layer: each closed stage against its own merge range --------


@pytest.mark.parametrize("stage", MERGED_STAGES)
def test_a_merged_stage_range_resolves_and_is_a_normal_merge(stage):
    """The range has to exist before anything can be audited over it.

    Also the shape: a two-parent merge the Owner performed, and an ancestor of
    whatever is checked out. A squashed or rebased stage would have one parent
    and the range would silently become "this commit alone".
    """
    merge_commit, _ = MERGED_STAGE_SCOPES[stage]
    parents = _git("rev-list", "--parents", "-n", "1", merge_commit).split()
    assert len(parents) == 3, f"{stage} at {merge_commit[:8]} is not a two-parent merge: {parents}"
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", merge_commit, "HEAD"],
                              capture_output=True, text=True)
    assert ancestor.returncode == 0, f"{stage} at {merge_commit[:8]} is not an ancestor of HEAD"


@pytest.mark.parametrize("stage", MERGED_STAGES)
def test_every_file_a_merged_stage_changed_has_a_reason(stage):
    merge_commit, scope = MERGED_STAGE_SCOPES[stage]
    unexplained = [path for path in stage_changed_paths(merge_commit) if path not in scope]
    assert unexplained == [], (
        f"{stage} changed these files without naming a requirement: {unexplained}"
    )


@pytest.mark.parametrize("stage", MERGED_STAGES)
def test_a_merged_stage_scope_map_has_no_stale_entries(stage):
    """A map that outlives its diff stops being an audit."""
    merge_commit, scope = MERGED_STAGE_SCOPES[stage]
    changed = set(stage_changed_paths(merge_commit))
    stale = sorted(path for path in scope if path not in changed)
    assert stale == [], f"the {stage} scope map lists files {stage} did not change: {stale}"


@pytest.mark.parametrize("stage", MERGED_STAGES)
def test_no_merged_stage_changed_a_file_outside_the_directories_p2_may_touch(stage):
    merge_commit, _ = MERGED_STAGE_SCOPES[stage]
    for path in stage_changed_paths(merge_commit):
        assert path in ALLOWED_FILES or path.startswith(ALLOWED_PREFIXES), f"{stage}: {path}"


# -- the pinned negatives: what S2 did not do, over S2's own range ----------


def test_s2_changed_no_strategy_semantics():
    before, after = f"{S2_MERGE}^1", S2_MERGE
    for path in (
        "freqtrade/user_data/strategies/BaselineEmaRegimeV1.py",
        "freqtrade/user_data/strategies/PlumbingSmokeStrategy.py",
    ):
        assert blob_at(before, path) == blob_at(after, path), path
    assert not any(p.startswith("freqtrade/user_data/strategies/")
                   for p in stage_changed_paths(S2_MERGE))


def test_s2_changed_no_risk_semantics():
    """The fields that decide exposure, sizing and stops, compared value by value."""
    base_registry, head_registry = registry_at(f"{S2_MERGE}^1"), registry_at(S2_MERGE)
    for role in ("FP-CONTROL-1", "FP-CONTROL-2"):
        before = next(r for r in base_registry["instances"]
                      if r["role"] == role)["runtime_identity"]
        after = next(r for r in head_registry["instances"]
                     if r["role"] == role)["runtime_identity"]
        for field in ("sizing", "max_open_trades", "order_policy", "fee_model", "pairs",
                      "timeframe", "detail_timeframe", "wallet", "paper_fill_model_version",
                      "strategy_sha256", "config_sha256", "candidate_family"):
            assert before.get(field) == after.get(field), f"{role}.{field}"
    # And the config the engine actually reads is untouched.
    assert blob_at(f"{S2_MERGE}^1", "freqtrade/user_data/config.paper.json.example") == blob_at(
        S2_MERGE, "freqtrade/user_data/config.paper.json.example"
    )


def test_s2_changed_no_dataset_content_or_authority():
    for path in _git("ls-tree", "-r", "--name-only", S2_MERGE, "research/datasets/").split():
        assert blob_at(f"{S2_MERGE}^1", path) == blob_at(S2_MERGE, path), path
    assert not any(p.startswith("research/datasets/") for p in stage_changed_paths(S2_MERGE))


def test_s2_widened_no_candidate_or_admission():
    for path in (
        "research/fp/records/paper_candidate_admission.json",
        "research/schema/paper_candidate_admission.schema.json",
        "research/fp/admission.py",
    ):
        assert blob_at(f"{S2_MERGE}^1", path) == blob_at(S2_MERGE, path), path


def test_s2_left_the_whole_registry_untouched():
    """S2 built the tool that will one day write the registry and did not write it."""
    registry_path = "research/fp/records/forward_paper_cohort_registry.json"
    assert blob_at(f"{S2_MERGE}^1", registry_path) == blob_at(S2_MERGE, registry_path)
    assert registry_path not in stage_changed_paths(S2_MERGE)


def test_s2_created_no_t0_and_no_qualification_binding():
    row = next(r for r in registry_at(S2_MERGE)["instances"] if r["role"] == "FP-CONTROL-2")
    assert row["t0_utc"] is None
    assert row["cohort_id"] is None
    assert row["status"] == "NOT_STARTED"
    assert row["runtime_identity"]["source_commit"] is None
    assert row["change_log"] == []
    # Both are S3-and-later artifacts. Asserting their absence *here*, at S2's
    # own commit, is a statement that stays true; asserting it against whatever
    # is checked out would make S3b's lawful binding look like a violation.
    for path in ("docs/p2/OWNER_T0_AUTHORIZATION.md",
                 "research/fp/records/p2_qualification_binding.json"):
        assert blob_at(S2_MERGE, path) is None, path


# -- the branch layer: the stage in flight, against the merge base ----------


# The freeze candidate's own two files, which contract section 6 fixes exactly.
FREEZE_CANDIDATE_SCOPE = {
    "research/fp/records/forward_paper_cohort_registry.json":
        "the T0 freeze transaction — audited by scripts/check_freeze_candidate.py",
    "MANIFEST.txt": "repository integrity — regenerated after staging",
}


def branch_scope() -> dict[str, str]:
    """What this branch is allowed to change.

    A freeze candidate is not an ordinary branch: it may change exactly the two
    files section 6 names, and nothing else — which is a narrower rule than this
    map, not a wider one.
    """
    if branch_is_a_freeze_candidate():
        return FREEZE_CANDIDATE_SCOPE
    charter_scope = charter_branch_scope()
    return BRANCH_SCOPE if charter_scope is None else charter_scope


def current_branch() -> str:
    """The PR head branch in CI (detached checkout), else the checked-out branch."""
    import os

    return os.environ.get("GITHUB_HEAD_REF") or _git("rev-parse", "--abbrev-ref", "HEAD").strip()


def charter_branch_scope() -> dict[str, str] | None:
    """CEA-1 §16: an auto/<charter>/<unit> branch is audited against its charter.

    A charter PR must never edit this protected file, so its scope cannot come
    from BRANCH_SCOPE. It comes from the charter's scope.paths read at the MERGE
    BASE, never from the branch: a charter widened on the branch itself would
    otherwise justify its own diff. Each changed path matching the charter (or
    MANIFEST.txt) gets a reason; a path matching nothing gets none and fails
    test_every_changed_file_on_this_branch_is_in_scope. Every live negative
    below still applies. None when this is not a charter branch.
    """
    import cea_policy

    match = cea_policy.CHARTER_BRANCH.match(current_branch())
    if match is None or BASE_REF is None:
        return None
    charter = cea_policy.charters_at(Path("."), merge_base()).get(match["charter"])
    if charter is None:
        return {}
    globs = charter["scope"]["paths"]
    scope: dict[str, str] = {}
    for path in changed_paths():
        if path in cea_policy.ALWAYS_ALLOWED:
            scope[path] = "repository integrity — regenerated after staging"
        elif any(cea_policy.glob_match(g, path) for g in globs):
            scope[path] = f"{charter['id']} {match['unit']} — inside the charter scope"
    return scope


@needs_baseline
def test_every_changed_file_on_this_branch_is_in_scope():
    unexplained = [path for path in changed_paths() if path not in branch_scope()]
    assert unexplained == [], (
        f"these files changed without naming a requirement: {unexplained}. Either name the "
        "requirement they satisfy or remove the change"
    )


@needs_baseline
def test_the_branch_scope_map_has_no_stale_entries():
    """Both directions — while there is a branch to audit.

    On merged main the branch diff is empty by construction, and comparing a map
    against an empty diff would report every entry in it as stale. That is not a
    finding about the map; it is the audit outliving its subject, and it is
    exactly how this file failed on main the moment S2 landed. Where there is no
    branch the condition is *proven* rather than skipped, and the both-directions
    comparison lives on in the pinned layer, which cannot empty out.
    """
    changed = set(changed_paths())
    if not changed:
        assert head() == merge_base(), (
            "no change was detected against the baseline, yet HEAD is not the merge base. "
            "The diff is not empty because this is merged main; something is wrong with it"
        )
        return
    stale = sorted(path for path in branch_scope() if path not in changed)
    assert stale == [], f"the branch scope map lists files this branch does not change: {stale}"


@needs_baseline
def test_no_changed_file_on_this_branch_lies_outside_the_directories_p2_may_touch():
    for path in changed_paths():
        assert path in ALLOWED_FILES or path.startswith(ALLOWED_PREFIXES), path


# -- the live negatives: true for every P2 branch up to the freeze ----------


@needs_baseline
def test_no_strategy_semantic_change():
    base = merge_base()
    for path in (
        "freqtrade/user_data/strategies/BaselineEmaRegimeV1.py",
        "freqtrade/user_data/strategies/PlumbingSmokeStrategy.py",
    ):
        assert blob_at(base, path) == blob_at("HEAD", path), path
    assert not any(p.startswith("freqtrade/user_data/strategies/") for p in changed_paths())


@needs_baseline
def test_no_risk_semantic_change():
    """The fields that decide exposure, sizing and stops, compared value by value."""
    base_registry, head_registry = registry_at(merge_base()), registry_at("HEAD")
    for role in ("FP-CONTROL-1", "FP-CONTROL-2"):
        before = next(r for r in base_registry["instances"]
                      if r["role"] == role)["runtime_identity"]
        after = next(r for r in head_registry["instances"]
                     if r["role"] == role)["runtime_identity"]
        for field in ("sizing", "max_open_trades", "order_policy", "fee_model", "pairs",
                      "timeframe", "detail_timeframe", "wallet", "paper_fill_model_version",
                      "strategy_sha256", "config_sha256", "candidate_family"):
            assert before.get(field) == after.get(field), f"{role}.{field}"
    # And the config the engine actually reads is untouched.
    assert blob_at(merge_base(), "freqtrade/user_data/config.paper.json.example") == blob_at(
        "HEAD", "freqtrade/user_data/config.paper.json.example"
    )


# AUTH-2 added Dataset V3 (record 4 of the Owner-approved package, PR #57). Additive only:
# a V3 path may be created where main does not have it yet, and every dataset file main
# already has (V3 included, now that it is merged) stays byte-identical.
DATASET_ADDITIONS = ("research/datasets/dataset_v3.lock.json", "research/datasets/dataset_v3/")


@needs_baseline
def test_no_dataset_content_or_authority_change():
    base = merge_base()
    for path in _git("ls-tree", "-r", "--name-only", "HEAD", "research/datasets/").split():
        if blob_at(base, path) is None:
            assert path.startswith(DATASET_ADDITIONS), f"{path}: only Dataset V3 may be added"
            continue
        assert blob_at(base, path) == blob_at("HEAD", path), path
    assert not any(p.startswith("research/datasets/") and
                   (not p.startswith(DATASET_ADDITIONS) or blob_at(base, p) is not None)
                   for p in changed_paths())


@needs_baseline
def test_no_candidate_or_admission_widening():
    base = merge_base()
    for path in (
        "research/fp/records/paper_candidate_admission.json",
        "research/schema/paper_candidate_admission.schema.json",
        "research/fp/admission.py",
    ):
        assert blob_at(base, path) == blob_at("HEAD", path), path
    record = json.loads(Path("research/fp/records/paper_candidate_admission.json")
                        .read_text(encoding="utf-8"))
    assert record["paper_admission"] == "BLOCKED"
    assert record["entry_state"] == "C"


def branch_is_a_freeze_candidate() -> bool:
    """Is this branch the T0 freeze transaction itself?

    The audits below forbid touching the registry, and say in their own comments
    that the one branch permitted to write it is the freeze candidate, "which is
    audited by scripts/check_freeze_candidate.py rather than here". That
    exemption was described and never implemented, so the first real freeze
    candidate failed the audit that had deliberately excluded it.

    The answer comes from the freeze gate itself rather than from a second
    detector written here: two checkers that disagree about what a freeze looks
    like would be worse than one.
    """
    if BASE_REF is None:
        return False
    try:
        import check_freeze_candidate

        verdict = check_freeze_candidate.check(merge_base(), "HEAD")
    except Exception:
        return False
    return verdict.get("classification") == check_freeze_candidate.FREEZE_CANDIDATE


@needs_baseline
def test_the_fp_control_1_row_is_byte_identical():
    base = merge_base()
    before = next(r for r in registry_at(base)["instances"] if r["role"] == "FP-CONTROL-1")
    after = next(r for r in registry_at("HEAD")["instances"] if r["role"] == "FP-CONTROL-1")
    assert before == after
    # In fact the whole registry file is untouched up to the freeze: the only
    # branch permitted to write it is the freeze candidate, which is audited by
    # scripts/check_freeze_candidate.py rather than here.
    registry_path = "research/fp/records/forward_paper_cohort_registry.json"
    if branch_is_a_freeze_candidate():
        # The freeze writes the registry by design. Its transaction — two files,
        # seven values, the closed row untouched — is audited by
        # scripts/check_freeze_candidate.py, which has just classified this
        # branch. The FP-CONTROL-1 assertion above still holds and has already
        # run: a freeze that moved the closed row would fail it here.
        return
    if registry_path not in changed_paths():
        assert blob_at(base, registry_path) == blob_at("HEAD", registry_path)
        return
    # The registry did change. The freeze is not the only lawful writer: a
    # cohort CLOSURE is another, and FP-CONTROL-1's own closure was exactly such
    # a commit. What no branch may do is move an existing row's FROZEN IDENTITY,
    # so that is what is checked instead of forbidding the file outright.
    before_reg, after_reg = registry_at(base), registry_at("HEAD")
    for row in before_reg["instances"]:
        role = row["role"]
        after_row = next((r for r in after_reg["instances"] if r["role"] == role), None)
        assert after_row is not None, f"{role} disappeared from the registry"
        for field in ("t0_utc", "cohort_id"):
            assert row.get(field) == after_row.get(field), (
                f"{role}.{field} moved: {row.get(field)!r} -> {after_row.get(field)!r}")
        assert (row.get("runtime_identity") or {}).get("source_commit") == \
            (after_row.get("runtime_identity") or {}).get("source_commit"), \
            f"{role} source_commit moved"


# -- the state layer: answerable in any checkout ----------------------------


def test_no_real_money_capability():
    registry = registry_at("HEAD")
    assert registry["real_money_authorized"] is False
    example = json.loads(Path("freqtrade/user_data/config.paper.json.example")
                         .read_text(encoding="utf-8"))
    assert example["dry_run"] is True
    assert example.get("trading_mode", "spot") == "spot"
    import paper_guard

    assert paper_guard.main([]) == 0


# A T0 is written by t0_utc and cohort_id appearing and by a row ENTERING
# RUNNING. Leaving RUNNING for CLOSED is a lawful cohort closure, checked
# separately below, so status is not in this tuple.
FROZEN_FIELDS = ("t0_utc", "cohort_id")


def _fp_control_2(rev: str) -> dict:
    return next(r for r in registry_at(rev)["instances"] if r["role"] == "FP-CONTROL-2")


@needs_baseline
def test_this_branch_created_no_t0():
    """This branch did not write a T0 — which is not "no T0 exists".

    This assertion has been narrowed twice, each time because it described a day
    rather than stating a law. First it also claimed no Owner authorization
    existed, and the Owner granting one ended that. Then it claimed the registry
    carries no T0, and the Owner merging the freeze has ended that too —
    permanently, for every commit that will ever follow.

    What is durable is that the freeze is the only branch that may move these
    fields, and that its transaction is audited by
    scripts/check_freeze_candidate.py rather than here.
    """
    if branch_is_a_freeze_candidate():
        return
    base, head = _fp_control_2(merge_base()), _fp_control_2("HEAD")
    moved = {f: (base.get(f), head.get(f)) for f in FROZEN_FIELDS if base.get(f) != head.get(f)}
    assert moved == {}, f"this branch moves {sorted(moved)} without being a freeze candidate"
    assert not (head.get("status") == "RUNNING" and base.get("status") != "RUNNING"), (
        "this branch puts a row into RUNNING without being a freeze candidate")
    assert base["runtime_identity"].get("source_commit") == \
        head["runtime_identity"].get("source_commit"), "this branch moves the declared source_commit"


def test_an_owner_authorization_if_it_exists_is_lawful_and_freezes_nothing():
    """The mirror of the binding audit, for the object that does carry authority.

    Absent is lawful — it is the default, and the default is refusal. Present is
    lawful too, and then exactly one thing must be true of it: it is what
    ``freeze_t0`` will read, it names this role and the qualification run the
    merged S3b binding pins, it forbids real money, and it carries an expiry.
    What it must NOT have done is freeze anything by existing.
    """
    path = Path("docs/p2/OWNER_T0_AUTHORIZATION.md")
    if not path.exists():
        return
    import freeze_t0

    granted: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = freeze_t0.AUTHORIZATION_LINE.match(line)
        if match and match.group(1) in freeze_t0.AUTHORIZATION_KEYS:
            granted.setdefault(match.group(1), []).append(match.group(2))
    # Every field, each exactly once: a file that says two things about one
    # field is an ambiguity, and the tool refuses it rather than choosing.
    for key in freeze_t0.AUTHORIZATION_KEYS:
        assert granted.get(key, []) != [], f"the authorization does not declare {key}"
        assert len(granted[key]) == 1, f"the authorization declares {key} more than once"

    binding = json.loads(Path("research/fp/records/p2_qualification_binding.json")
                         .read_text(encoding="utf-8"))
    # The two records must name the SAME role, and it must be a role the
    # registry still has open. Naming a literal cohort here would have to be
    # edited at every successor, and an assertion that has to be edited to keep
    # passing is not holding anything: what matters is that the Owner's grant
    # and the binding agree, and that they agree about a row that can still be
    # frozen rather than one whose T0 is already history.
    assert granted["ROLE"][0] == binding["role"]
    registry = json.loads(Path("research/fp/records/forward_paper_cohort_registry.json")
                          .read_text(encoding="utf-8"))
    open_roles = {row["role"] for row in registry["instances"] if row.get("status") != "CLOSED"}
    if open_roles:
        assert binding["role"] in open_roles, (
            f"the authorization and binding name {binding['role']}, which is not an open row"
        )
    else:
        # Every row is CLOSED: the stage has closed and no successor is registered.
        # The grant has then been spent on exactly one freeze, so it must name the
        # cohort frozen most recently, and that row must carry a frozen T0 and its
        # closure. A grant naming any other row, or a never-frozen one, still fails.
        import conftest

        spent = next(r for r in registry["instances"] if r["role"] == binding["role"])
        assert binding["role"] == conftest.live_role(), (
            f"the authorization and binding name {binding['role']}, which is not the cohort "
            "frozen most recently")
        assert spent["t0_utc"] and spent["cohort_id"] and spent["closed_utc"], spent["role"]
    assert granted["QUALIFICATION_COMMIT"][0] == binding["qualification_commit"]
    assert granted["QUALIFICATION_CERTIFICATE_SHA256"][0] == binding["certificate_sha256"]
    assert granted["REAL_MONEY_AUTHORIZED"][0].strip().upper() == "NO"
    freeze_t0._parse_utc(granted["EXPIRES_UTC"][0], "EXPIRES_UTC")

    # It authorizes a freeze; it does not perform one. Once the freeze is merged
    # the registry carries that T0 for good, so what stays checkable is that the
    # row is internally consistent in whichever lawful state it is in — and that
    # a cohort id, where one exists, derives from its own T0.
    from fp import registry_law as _law

    registry = registry_at("HEAD")
    row = next(r for r in registry["instances"] if r["role"] == "FP-CONTROL-2")
    if row["status"] == "NOT_STARTED":
        assert row["t0_utc"] is None and row["cohort_id"] is None
        assert row["change_log"] == []
    elif row["status"] == "CLOSED":
        # A closed cohort keeps its frozen identity and carries an outcome.
        assert row["t0_utc"] and row["cohort_id"]
        assert row["cohort_id"] == _law.cohort_id_for(row["role"], row["t0_utc"])
        assert row.get("outcome"), "a closed cohort must record what it established"
    else:
        assert row["status"] == "RUNNING"
        assert row["cohort_id"] == _law.cohort_id_for("FP-CONTROL-2", row["t0_utc"])
        assert row["runtime_identity"]["source_commit"]
        assert registry["fp_run_active"] is True
    assert registry["real_money_authorized"] is False


@needs_baseline
def test_this_branch_created_no_cohort():
    """The same narrowing, for the cohort id, the change log and the run flag.

    ``paper_alpha_cohort`` is different in kind and stays absolute: FP-CONTROL-2
    is a CONTROL, and no lawful P2 act promotes it into the paper-alpha cohort.
    """
    if branch_is_a_freeze_candidate():
        return
    base, head = _fp_control_2(merge_base()), _fp_control_2("HEAD")
    assert base.get("cohort_id") == head.get("cohort_id"), "this branch moves the cohort id"
    if head.get("status") != "CLOSED":
        # A closure legitimately appends its own class-O entry and clears the
        # run flag; what it may never do is invent a cohort.
        assert base.get("change_log") == head.get("change_log"), "this branch writes the change log"
        assert registry_at(merge_base())["fp_run_active"] == registry_at("HEAD")["fp_run_active"]
    assert registry_at("HEAD")["paper_alpha_cohort"] == "NONE"
    assert registry_at("HEAD")["real_money_authorized"] is False


def test_a_qualification_binding_if_it_exists_binds_and_does_not_authorize():
    """S3b's binding is lawful; a binding that had grown authority would not be.

    The record pins what the S3 run observed. It is class O by construction —
    an observation of a runtime, never an instruction to one — and it carries no
    T0, no cohort id and no authorization. Authority is a merged Owner file, and
    the binding must never start standing in for it.
    """
    path = Path("research/fp/records/p2_qualification_binding.json")
    if not path.exists():
        return
    record = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(Path("research/schema/p2_qualification_binding.schema.json")
                        .read_text(encoding="utf-8"))
    import jsonschema

    jsonschema.validate(record, schema)
    assert record["real_money_authorized"] is False
    assert record["role"] == "FP-CONTROL-3"
    assert record.get("t0_relation_of_every_record", "T0_NOT_FROZEN") == "T0_NOT_FROZEN"
    assert record.get("prospective_evidence", "NONE") == "NONE"
    for forbidden in ("t0_utc", "cohort_id", "authorization", "authorized", "expires_utc"):
        assert forbidden not in record, (
            f"the qualification binding carries {forbidden!r}; it binds observations and never "
            "authorizes a T0"
        )


def test_no_storage_resource_was_provisioned():
    """Discovery only. The second device is found, never formatted or mounted."""
    import second_device_discovery

    report = second_device_discovery.discover()
    assert report["provisioned"] is False
    assert report["actions_taken"].startswith("NONE")
    assert report["host_loss_redundancy"] == "NOT_PROVEN"
    assert report["blocks_t0"] is False


def test_the_parked_branch_is_untouched():
    """19d7d7e must not have been merged into this branch's history."""
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", PARKED_BRANCH, "HEAD"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0, "the parked strategy-source branch was merged"


def test_no_evidence_lane_content_is_tracked():
    """P2 produces tooling and records, never evidence."""
    tracked = _git("ls-files").split()
    for path in tracked:
        assert "/fp-control-1/" not in path
        assert "/fp-control-2/" not in path
        assert "/fp-testlane-" not in path
        assert not path.endswith(".jsonl") or "records" in path


def test_the_audit_was_not_silently_skipped():
    """Where a baseline exists, the branch-layer audits must actually have run.

    A skip is the correct answer in a remote-less reproduction clone and the
    wrong answer anywhere a reviewer is reading the result, so the difference is
    made visible rather than left to whoever scrolls past the `s` characters.
    The pinned layer is not covered by this: it names both of its commits and so
    it never skips at all, which is the whole reason it exists.
    """
    assert MERGED_STAGES, "no closed stage is pinned, so the permanent audit covers nothing"
    if BASE_REF is None:
        pytest.skip("no baseline in this checkout; the CI step asserts one exists there")
    assert len(BASE_REF) == 40
    assert changed_paths() or head() == merge_base(), (
        "a baseline resolved, no change was detected against it, and HEAD is not the merge base"
    )
