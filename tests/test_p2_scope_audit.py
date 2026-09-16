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

MERGED_STAGE_SCOPES: dict[str, tuple[str, dict[str, str]]] = {
    "S2": (S2_MERGE, S2_SCOPE),
}

# The stage in flight. Every path this branch touches → the requirement it
# satisfies. When the stage merges, its entry moves into MERGED_STAGE_SCOPES
# against the merge commit, where it stops depending on which branch is checked
# out and starts being a permanent record.
BRANCH_SCOPE: dict[str, str] = {
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
ALLOWED_PREFIXES = ("research/", "scripts/", "tests/", "docs/p2/", ".github/workflows/")
ALLOWED_FILES = (".gitignore", "MANIFEST.txt", "CLAUDE.md")


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


@needs_baseline
def test_every_changed_file_on_this_branch_is_in_scope():
    unexplained = [path for path in changed_paths() if path not in BRANCH_SCOPE]
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
    stale = sorted(path for path in BRANCH_SCOPE if path not in changed)
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
    # In fact the whole registry file is untouched up to the freeze: the only
    # branch permitted to write it is the freeze candidate, which is audited by
    # scripts/check_freeze_candidate.py rather than here.
    registry_path = "research/fp/records/forward_paper_cohort_registry.json"
    assert blob_at(base, registry_path) == blob_at("HEAD", registry_path)
    assert registry_path not in changed_paths()


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


def test_no_t0_was_created():
    row = next(r for r in registry_at("HEAD")["instances"] if r["role"] == "FP-CONTROL-2")
    assert row["t0_utc"] is None
    assert row["status"] == "NOT_STARTED"
    assert row["runtime_identity"]["source_commit"] is None
    assert not Path("docs/p2/OWNER_T0_AUTHORIZATION.md").exists()


def test_no_cohort_was_created():
    registry = registry_at("HEAD")
    row = next(r for r in registry["instances"] if r["role"] == "FP-CONTROL-2")
    assert row["cohort_id"] is None
    assert row["change_log"] == []
    assert registry["fp_run_active"] is False
    assert registry["paper_alpha_cohort"] == "NONE"


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
    assert record["role"] == "FP-CONTROL-2"
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
