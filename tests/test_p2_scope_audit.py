"""Every file PR #17 changes, and why — plus the ten things it does not do.

A stage contract is only as good as the diff it actually produced. This file is
the audit made executable: every changed path must be listed below against the
S2 requirement it satisfies, so a file that arrives without a reason fails the
suite rather than passing review by being unremarkable. Deleting an entry is not
a way past it either — the map is compared against git in both directions.

The second half proves the negatives. Each one is a thing the P2 contract
forbids S2 from doing, and each is checked against the merge base rather than
asserted in prose, because "no strategy semantics changed" is a claim about two
git objects and nothing else.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from fp import capability as fp_capability  # noqa: F401  (import proves it loads)

PARKED_BRANCH = "19d7d7e76831a44c0c3ee643e2cebe7979f456f0"

# Every path this branch touches → the S2 requirement it satisfies.
# Contract section 13 lists the requirements; the right-hand side names one.
SCOPE: dict[str, str] = {
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
    "scripts/tier3_discovery.py": "durability policy — superseded, renamed to second_device_discovery",
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
    "tests/test_p2_capability_model.py": "property model invariants",
    "CLAUDE.md": "durability policy — the Tier-3 return trigger is superseded",
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
    None rather than an invented one. The diff-dependent audits below skip, the
    state-dependent ones still run, and `test_the_baseline_dependent_audit_is_not
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

# Applied to the audits that compare two commits. Never applied to the audits
# that read the current state — "no T0 exists" is answerable in any checkout,
# and letting it skip alongside the others would quietly drop the checks that
# matter most.
needs_baseline = pytest.mark.skipif(
    BASE_REF is None,
    reason=(
        "no main reference in this checkout, so there is no baseline to diff against. "
        "The state-dependent audits in this file still run."
    ),
)


def merge_base() -> str:
    assert BASE_REF is not None
    return BASE_REF


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
            source, destination = (part.strip().strip('"') for part in entry.split(" -> ", 1))
            paths.update({source, destination})
        else:
            paths.add(entry)
    return sorted(paths)


def blob_at(rev: str, path: str) -> str | None:
    result = subprocess.run(["git", "rev-parse", f"{rev}:{path}"],
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def registry_at(rev: str) -> dict:
    return json.loads(_git("show", f"{rev}:research/fp/records/forward_paper_cohort_registry.json"))


# -- every changed file has a reason, and every reason has a file ----------


@needs_baseline
def test_every_changed_file_is_in_scope():
    unexplained = [path for path in changed_paths() if path not in SCOPE]
    assert unexplained == [], (
        f"these files changed without an S2 requirement: {unexplained}. Either name the "
        "requirement they satisfy or remove the change"
    )


@needs_baseline
def test_the_scope_map_has_no_stale_entries():
    """A map that outlives its diff stops being an audit."""
    changed = set(changed_paths())
    stale = sorted(path for path in SCOPE if path not in changed)
    assert stale == [], f"the scope map lists files this branch does not change: {stale}"


@needs_baseline
def test_no_changed_file_lies_outside_the_directories_s2_may_touch():
    allowed_prefixes = ("research/", "scripts/", "tests/", "docs/p2/", ".github/workflows/")
    allowed_files = (".gitignore", "MANIFEST.txt", "CLAUDE.md")
    for path in changed_paths():
        assert path in allowed_files or path.startswith(allowed_prefixes), path


# -- the ten negatives -----------------------------------------------------


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


@needs_baseline
def test_no_dataset_content_or_authority_change():
    base = merge_base()
    for path in _git("ls-tree", "-r", "--name-only", "HEAD", "research/datasets/").split():
        assert blob_at(base, path) == blob_at("HEAD", path), path
    assert not any(p.startswith("research/datasets/") for p in changed_paths())


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


@needs_baseline
def test_the_fp_control_1_row_is_byte_identical():
    base = merge_base()
    before = next(r for r in registry_at(base)["instances"] if r["role"] == "FP-CONTROL-1")
    after = next(r for r in registry_at("HEAD")["instances"] if r["role"] == "FP-CONTROL-1")
    assert before == after
    # In fact the whole registry file is untouched by this branch: S2 builds the
    # tool that will one day write it and does not write it.
    registry_path = "research/fp/records/forward_paper_cohort_registry.json"
    assert blob_at(base, registry_path) == blob_at("HEAD", registry_path)
    assert registry_path not in changed_paths()


def test_no_real_money_capability():
    registry = registry_at("HEAD")
    assert registry["real_money_authorized"] is False
    example = json.loads(Path("freqtrade/user_data/config.paper.json.example")
                         .read_text(encoding="utf-8"))
    assert example["dry_run"] is True
    assert example.get("trading_mode", "spot") == "spot"
    import paper_guard

    assert paper_guard.main([]) == 0


def test_no_t0_was_created():
    row = next(r for r in registry_at("HEAD")["instances"] if r["role"] == "FP-CONTROL-2")
    assert row["t0_utc"] is None
    assert row["status"] == "NOT_STARTED"
    assert row["runtime_identity"]["source_commit"] is None
    assert not Path("docs/p2/OWNER_T0_AUTHORIZATION.md").exists()
    assert not Path("research/fp/records/p2_qualification_binding.json").exists()


def test_no_cohort_was_created():
    registry = registry_at("HEAD")
    row = next(r for r in registry["instances"] if r["role"] == "FP-CONTROL-2")
    assert row["cohort_id"] is None
    assert row["change_log"] == []
    assert registry["fp_run_active"] is False
    assert registry["paper_alpha_cohort"] == "NONE"


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
    """S2 produced tooling, never evidence."""
    tracked = _git("ls-files").split()
    for path in tracked:
        assert "/fp-control-1/" not in path
        assert "/fp-control-2/" not in path
        assert "/fp-testlane-" not in path
        assert not path.endswith(".jsonl") or "records" in path


def test_the_baseline_dependent_audit_is_not_silently_skipped():
    """Where a baseline exists, the diff audits must actually have run.

    A skip is the correct answer in a remote-less reproduction clone and the
    wrong answer anywhere a reviewer is reading the result, so the difference is
    made visible rather than left to whoever scrolls past the `s` characters.
    """
    if BASE_REF is None:
        pytest.skip("no baseline in this checkout; the CI step asserts one exists there")
    assert len(BASE_REF) == 40
    assert changed_paths(), "a baseline resolved but no change was detected against it"
