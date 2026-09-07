"""Paper admission and the cohort registry (FP-BOOT-1 sections 3, 5, 6, 7, 15).

Section 5 ends with "Otherwise: PAPER_ADMISSION = BLOCKED". These tests exist so
that "otherwise" cannot erode: the evaluator must fail closed, and it must stay
failed closed while the entry conditions are genuinely absent.
"""

from __future__ import annotations

import json

import pytest

from fp import admission

REGISTRY = "research/fp/records/forward_paper_cohort_registry.json"
ADMISSION_RECORD = "research/fp/records/paper_candidate_admission.json"


@pytest.fixture(scope="module")
def record() -> dict:
    return admission.evaluate()


@pytest.fixture(scope="module")
def committed(request) -> dict:
    return json.loads((request.config.rootpath / ADMISSION_RECORD).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def registry(request) -> dict:
    return json.loads((request.config.rootpath / REGISTRY).read_text(encoding="utf-8"))


# -- the evaluator --------------------------------------------------------


def test_all_eighteen_conditions_are_evaluated(record):
    assert [c["id"] for c in record["conditions"]] == list(range(1, 19))
    assert [c["requirement"] for c in record["conditions"]] == list(admission.REQUIREMENTS)


def test_every_condition_carries_evidence(record):
    for condition in record["conditions"]:
        assert condition["evidence"].strip(), f"condition {condition['id']} has no evidence"


def test_admission_is_blocked_in_the_current_repository_state(record):
    assert record["paper_admission"] == "BLOCKED"
    assert record["paper_alpha_cohort"] == "NONE"


def test_entry_state_requires_both_merges(record):
    """Section 3 + 7: the entry state is recomputed from authoritative merged main.

    Both merges are the precondition — BASELINE-1 closure (3.1) and the benchmark
    lineage (3.2). The sprint must also actually be over: closed, or ended by an
    Owner amendment that says so in Repo Truth.
    """
    lineage_ok = record["authoritative_lineage"]["is_ancestor_of_main"]
    over = record["benchmark_closure"]["state"] in {"CLOSED", "OWNER_TERMINATED_INCONCLUSIVE"}
    if lineage_ok and over:
        assert record["entry_state"] in {"A", "B", "C"}
    else:
        assert record["entry_state"] == "NOT_AUTHORITATIVE"
    assert record["entry_state_reason"].strip()


def test_a_terminated_sprint_is_not_a_closed_one(monkeypatch):
    """An Owner amendment ends a sprint without closing it.

    A terminated sprint has executed rows, so counting rows alone would report it
    CLOSED and grant it an authority it does not have.
    """
    import json as _json

    closure = _json.dumps({"status": "OWNER_TERMINATED_INCONCLUSIVE"})
    scorecard = "candidate_id,lane\n# comment\nH1_EMACROSS,H1_DEV\n"

    def fake_show(ref, path):
        if path.endswith("sprint_closure.json"):
            return closure
        if path.endswith(".csv"):
            return scorecard
        return "{}"

    monkeypatch.setattr(admission, "_git_show", fake_show)
    state, detail = admission.benchmark_closure_state()
    assert state == "OWNER_TERMINATED_INCONCLUSIVE"
    assert "NOT_DETERMINED" in detail

    # Without the amendment the same scorecard reads as closure.
    monkeypatch.setattr(
        admission, "_git_show",
        lambda ref, path: None if path.endswith("sprint_closure.json") else (scorecard if path.endswith(".csv") else "{}"),
    )
    assert admission.benchmark_closure_state()[0] == "CLOSED"


def test_entry_state_c_says_which_kind_of_c_it_is(record):
    """'No survivor available' and 'no survivor survived' are different facts."""
    if record["benchmark_closure"]["state"] == "OWNER_TERMINATED_INCONCLUSIVE":
        assert record["entry_state"] == "C"
        reason = record["entry_state_reason"]
        assert "terminated by Owner amendment" in reason
        assert "never as 'none survived'" in reason


def test_a_merged_but_unexecuted_sprint_is_not_closure(monkeypatch, tmp_path):
    """The three benchmark states must stay distinguishable.

    A pre-registered scorecard carrying only its header and comment is the state
    the sprint freezes *before* running; reading it as closure would let an
    unexecuted sprint satisfy section 3.2.
    """
    header = "candidate_id,lane,measurement_validity\n# columns pre-registered before any result exists\n"

    def fake_show(ref, path):
        if path.endswith("qualification_scorecard.csv"):
            return header
        if path.endswith("candidate_registry.json"):
            return "{}"
        return None

    monkeypatch.setattr(admission, "_git_show", fake_show)
    state, detail = admission.benchmark_closure_state()
    assert state == "MERGED_NOT_EXECUTED"
    assert "not executed" in detail

    monkeypatch.setattr(
        admission, "_git_show", lambda ref, path: header + "cand_a,native,PASS\n"
        if path.endswith(".csv") else "{}"
    )
    assert admission.benchmark_closure_state()[0] == "CLOSED"


def test_absent_sprint_artifacts_are_not_merged(monkeypatch):
    monkeypatch.setattr(admission, "_git_show", lambda ref, path: None)
    state, detail = admission.benchmark_closure_state()
    assert state == "NOT_MERGED"
    assert "3.2" in detail


def test_the_lineage_proof_is_computed_not_asserted(record):
    """Condition 18 must agree with the recorded ancestry proof."""
    lineage = record["authoritative_lineage"]
    assert lineage["baseline_closure_commit"] == admission.BASELINE_CLOSURE_COMMIT
    integrity = record["conditions"][17]
    assert integrity["result"] == ("PASS" if lineage["is_ancestor_of_main"] else "FAIL")


def test_the_benchmark_closure_state_is_recorded(record):
    assert record["benchmark_closure"]["state"] in {
        "NOT_MERGED", "MERGED_NOT_EXECUTED", "OWNER_TERMINATED_INCONCLUSIVE", "CLOSED",
    }
    assert record["benchmark_closure"]["detail"].strip()


def _force_all_pass(monkeypatch):
    """Make every mechanical check report PASS, so one condition can be isolated."""
    monkeypatch.setattr(admission, "_spot_only", lambda: ("PASS", "stub"))
    for name in ("_no_leverage", "_no_futures", "_no_margin", "_no_shorts"):
        monkeypatch.setattr(admission, name, lambda: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_frozen_configuration", lambda: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_project_integrity", lambda: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_contracts_frozen", lambda: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_paper_execution_rights", lambda: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_replay_available", lambda: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_semantic_change_rules", lambda: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_outage_predeclared", lambda contract: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_from_gate_records", lambda key, desc: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_timestamp_knowability", lambda: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_candidate_identity_frozen", lambda: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_timestamp_knowability", lambda: ("PASS", "stub"))
    monkeypatch.setattr(
        admission,
        "_feature_availability",
        lambda: ({"status": "CONTRACTED", "features": []}, "PASS", "stub"),
    )


def test_admission_is_granted_when_all_eighteen_pass(monkeypatch):
    """The gate is not simply wired shut: forced all-PASS must yield ADMITTED.

    Without this, every other assertion in this file would be satisfied by an
    evaluator that returns BLOCKED unconditionally.
    """
    _force_all_pass(monkeypatch)
    record = admission.evaluate()
    assert [c["result"] for c in record["conditions"]] == ["PASS"] * 18
    assert record["paper_admission"] == "ADMITTED"
    assert record["real_money_authorized"] is False


@pytest.mark.parametrize("blocked_result", ["UNPROVEN", "FAIL"])
@pytest.mark.parametrize(
    "target", ["_candidate_identity_frozen", "_replay_available", "_contracts_frozen", "_project_integrity"]
)
def test_a_single_non_passing_condition_blocks_admission(monkeypatch, target, blocked_result):
    """UNPROVEN must block exactly as FAIL does, whichever condition it is."""
    _force_all_pass(monkeypatch)
    monkeypatch.setattr(admission, target, lambda: (blocked_result, "stub"))
    record = admission.evaluate()
    assert record["paper_admission"] == "BLOCKED"
    assert sum(1 for c in record["conditions"] if c["result"] != "PASS") == 1


def test_the_data_contract_condition_tracks_the_dataset_lock(request, record):
    """Condition 9 must follow the lock file, not a hard-coded verdict.

    Written so it stays honest after Dataset V2 is acquired: while the lock says
    the data is not frozen the condition must FAIL and say why, and once it is
    frozen with fingerprints the condition must PASS.
    """
    lock = json.loads(
        (request.config.rootpath / "research/datasets/dataset_v2.lock.json").read_text(encoding="utf-8")
    )
    condition = record["conditions"][11]
    frozen = lock.get("status") == "frozen" and bool(admission.dataset_v2_fingerprints(lock))
    if frozen:
        assert condition["result"] == "PASS"
    else:
        assert condition["result"] == "FAIL"
        assert str(lock.get("status")) in condition["evidence"]


def test_safety_conditions_pass_on_their_own_evidence(record):
    """Conditions 7-11 and 13 are mechanically checkable and must not be UNPROVEN."""
    for index in (6, 7, 8, 9, 10, 12):
        assert record["conditions"][index]["result"] == "PASS", record["conditions"][index]


def test_the_four_derivative_prohibitions_have_distinct_evidence(record):
    """Section 9 splits leverage, futures, margin and shorts into four conditions.

    One enforcer answers all four, so the evidence must still say which
    prohibition each row is about; otherwise a gap in one hides inside the
    others.
    """
    evidence = [record["conditions"][i]["evidence"] for i in (7, 8, 9, 10)]
    assert len(set(evidence)) == 4
    assert "leverage" in evidence[0]
    assert "spot" in evidence[1]
    assert "margin_mode" in evidence[2]
    assert "can_short" in evidence[3]


def test_example_records_cannot_satisfy_a_condition(monkeypatch, tmp_path):
    """A schema template must never be mistaken for a passing gate result."""
    (tmp_path / "EXAMPLE_experiment_record.json").write_text(
        json.dumps({"gate": "PASS", "run_name": "template",
                    "strategy": {"name": "Cand"}, "analyses": {"lookahead": "pass"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(admission, "RECORDS_DIR", tmp_path)
    monkeypatch.setattr(admission, "identified_candidate", lambda: "Cand")
    assert admission._gate_records() == []
    assert admission._from_gate_records("lookahead", "lookahead analysis")[0] == "UNPROVEN"

    (tmp_path / "real_record.json").write_text(
        json.dumps({"gate": "PASS", "run_name": "real",
                    "strategy": {"name": "Cand"}, "analyses": {"lookahead": "pass"}}),
        encoding="utf-8",
    )
    assert admission._from_gate_records("lookahead", "lookahead analysis")[0] == "PASS"


def test_a_controls_evidence_never_satisfies_a_candidates_condition(monkeypatch, tmp_path):
    """The bug this scoping fixes, pinned.

    After the BASELINE-1 lineage merged, research/records/ carried passing
    records for the *control*. Unscoped, they made the candidate's lookahead and
    timestamp-knowability conditions report PASS while no candidate existed.
    """
    (tmp_path / "baseline1_development.json").write_text(
        json.dumps({"gate": "PASS", "run_name": "baseline-1-development",
                    "strategy": {"name": "BaselineEmaRegimeV1"},
                    "analyses": {"lookahead": "pass", "recursive": "pass"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(admission, "RECORDS_DIR", tmp_path)

    monkeypatch.setattr(admission, "identified_candidate", lambda: None)
    result, evidence = admission._from_gate_records("lookahead", "lookahead analysis")
    assert result == "UNPROVEN"
    assert "control" in evidence

    monkeypatch.setattr(admission, "identified_candidate", lambda: "SomeCandidate")
    result, evidence = admission._from_gate_records("lookahead", "lookahead analysis")
    assert result == "UNPROVEN"
    assert "SomeCandidate" in evidence

    monkeypatch.setattr(admission, "identified_candidate", lambda: "BaselineEmaRegimeV1")
    assert admission._from_gate_records("lookahead", "lookahead analysis")[0] == "PASS"


def test_no_candidate_is_identified_yet():
    """Entry state C: there is no survivor to admit."""
    assert admission.identified_candidate() is None


@pytest.mark.parametrize("flag", ["--force", "--override", "--allow-blocked", "--assume-pass"])
def test_no_override_flag_is_accepted(flag):
    """Section 9 names these four and says do not provide them.

    Tested through the CLI rather than by grepping the source, so that merely
    documenting the prohibition does not fail the test while an actual
    implementation of it would pass.
    """
    with pytest.raises(SystemExit) as excinfo:
        admission.main(["evaluate", flag])
    assert excinfo.value.code != 0


def test_no_environment_variable_can_flip_the_verdict(monkeypatch):
    """Section 9 also forbids a *silent environment override*."""
    for name in (
        "FP_FORCE",
        "FP_ADMISSION",
        "PAPER_ADMISSION",
        "FP_ALLOW_BLOCKED",
        "FP_ASSUME_PASS",
        "FP_OVERRIDE",
    ):
        monkeypatch.setenv(name, "ADMITTED")
    assert admission.evaluate()["paper_admission"] == "BLOCKED"


def test_record_is_schema_valid(record):
    assert admission.validate(record) == []


def test_real_money_is_never_authorized(record, committed):
    assert record["real_money_authorized"] is False
    assert committed["real_money_authorized"] is False


# -- the committed record -------------------------------------------------


def test_committed_record_matches_the_current_evaluation(committed, record):
    """The record in git must not drift from what the evaluator now says."""
    assert committed["paper_admission"] == record["paper_admission"]
    assert committed["entry_state"] == record["entry_state"]
    assert [c["result"] for c in committed["conditions"]] == [c["result"] for c in record["conditions"]]


def test_committed_record_is_schema_valid(committed):
    assert admission.validate(committed) == []


# -- feature availability (section 6) -------------------------------------


def test_every_feature_declares_a_full_availability_contract(record):
    contract = record["feature_availability"]
    assert contract["features"], "at least the OHLCV candle must be contracted"
    for feature in contract["features"]:
        for field in (
            "source_identity",
            "retrieval_path",
            "source_latency",
            "max_admissible_staleness",
            "outage_policy",
            "fallback_policy",
            "provenance",
        ):
            assert feature[field].strip(), f"{feature['feature']} has no {field}"


def test_outage_policy_is_one_of_the_predeclared_four(record):
    allowed = {"NO_NEW_ENTRY", "SAFE_HOLD", "INSTANCE_PAUSE", "FORCED_EXIT"}
    for feature in record["feature_availability"]["features"]:
        assert feature["outage_policy"] in allowed


def test_no_feature_is_forward_filled(record):
    for feature in record["feature_availability"]["features"]:
        assert "no forward-fill" in feature["fallback_policy"]


# -- the cohort registry (sections 3, 4, 7) -------------------------------


def test_registry_records_state_c_with_no_cohort(registry):
    assert registry["entry_state"] == "C"
    assert registry["paper_alpha_cohort"] == "NONE"
    assert registry["fp_run_active"] is False
    assert registry["real_money_authorized"] is False


def test_no_instance_has_a_t0(registry):
    """No T0 may exist while preflight is blocked."""
    for instance in registry["instances"]:
        assert instance["t0_utc"] is None
        assert instance["status"] == "NOT_STARTED"


def test_cohort_size_respects_the_section_4_maximum(registry):
    instances = registry["instances"]
    assert len(instances) <= 3
    roles = [i["role"] for i in instances]
    assert len(roles) == len(set(roles))
    assert sum(1 for r in roles if r == "FP-CONTROL-1") <= 1


def test_registry_is_schema_valid(request, registry):
    import jsonschema

    schema = json.loads(
        (request.config.rootpath / "research/schema/forward_paper_cohort_registry.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert list(jsonschema.validators.validator_for(schema)(schema).iter_errors(registry)) == []


def test_change_model_is_predeclared(request):
    """Section 15 agreed after the fact is worth nothing, so it must be in git."""
    doc = (request.config.rootpath / "docs/fp-boot-1/FP_BOOT_1_ENTRY_STATE.md").read_text(encoding="utf-8")
    for token in ("OBSERVABILITY", "RUNTIME REPAIR", "SEMANTIC CHANGE", "OLD_COHORT = CLOSED"):
        assert token in doc


def test_replay_condition_tracks_the_ema_parity_status(monkeypatch):
    """Condition 12 must follow the parity evidence, not a hard-coded verdict.

    While the EMA equivalence with TA-Lib is only asserted, "deterministic or
    explainable replay exists" is UNPROVEN; once CI has executed it, it passes.
    """
    from fp import replay

    monkeypatch.setattr(replay, "EMA_PARITY_STATUS", "ASSERTED_PENDING_TALIB_EXECUTION")
    assert admission._replay_available()[0] == "UNPROVEN"

    monkeypatch.setattr(replay, "EMA_PARITY_STATUS", "VERIFIED_IN_CI")
    assert admission._replay_available()[0] == "PASS"


def test_the_committed_parity_status_is_one_of_the_two_known_values():
    from fp import replay

    assert replay.EMA_PARITY_STATUS in {"ASSERTED_PENDING_TALIB_EXECUTION", "VERIFIED_IN_CI"}
