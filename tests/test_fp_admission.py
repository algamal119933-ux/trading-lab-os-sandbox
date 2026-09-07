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


def test_all_fourteen_conditions_are_evaluated(record):
    assert [c["id"] for c in record["conditions"]] == list(range(1, 15))
    assert [c["requirement"] for c in record["conditions"]] == list(admission.REQUIREMENTS)


def test_every_condition_carries_evidence(record):
    for condition in record["conditions"]:
        assert condition["evidence"].strip(), f"condition {condition['id']} has no evidence"


def test_admission_is_blocked_in_the_current_repository_state(record):
    assert record["paper_admission"] == "BLOCKED"
    assert record["entry_state"] == "C"
    assert record["paper_alpha_cohort"] == "NONE"


def _force_all_pass(monkeypatch):
    """Make every mechanical check report PASS, so one condition can be isolated."""
    monkeypatch.setattr(admission, "_spot_only", lambda: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_no_derivatives", lambda: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_contracts_frozen", lambda: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_paper_execution_rights", lambda: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_replay_available", lambda: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_semantic_change_rules", lambda: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_outage_predeclared", lambda contract: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_from_gate_records", lambda key, desc: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_candidate_identity_frozen", lambda: ("PASS", "stub"))
    monkeypatch.setattr(admission, "_timestamp_knowability", lambda: ("PASS", "stub"))
    monkeypatch.setattr(
        admission,
        "_feature_availability",
        lambda: ({"status": "CONTRACTED", "features": []}, "PASS", "stub"),
    )


def test_admission_is_granted_when_all_fourteen_pass(monkeypatch):
    """The gate is not simply wired shut: forced all-PASS must yield ADMITTED.

    Without this, every other assertion in this file would be satisfied by an
    evaluator that returns BLOCKED unconditionally.
    """
    _force_all_pass(monkeypatch)
    record = admission.evaluate()
    assert [c["result"] for c in record["conditions"]] == ["PASS"] * 14
    assert record["paper_admission"] == "ADMITTED"
    assert record["real_money_authorized"] is False


@pytest.mark.parametrize("blocked_result", ["UNPROVEN", "FAIL"])
@pytest.mark.parametrize("target", ["_candidate_identity_frozen", "_replay_available", "_contracts_frozen"])
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
    condition = record["conditions"][8]
    frozen = lock.get("status") == "frozen" and bool(lock.get("files"))
    if frozen:
        assert condition["result"] == "PASS"
    else:
        assert condition["result"] == "FAIL"
        assert str(lock.get("status")) in condition["evidence"]


def test_safety_conditions_pass_on_their_own_evidence(record):
    """Conditions 7, 8 and 10 are mechanically checkable and must not be UNPROVEN."""
    for index in (6, 7, 9):
        assert record["conditions"][index]["result"] == "PASS", record["conditions"][index]


def test_example_records_cannot_satisfy_a_condition(monkeypatch, tmp_path):
    """A schema template must never be mistaken for a passing gate result."""
    (tmp_path / "EXAMPLE_experiment_record.json").write_text(
        json.dumps({"gate": "PASS", "run_name": "template", "analyses": {"lookahead": "pass"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(admission, "RECORDS_DIR", tmp_path)
    assert admission._gate_records() == []
    assert admission._from_gate_records("lookahead", "lookahead analysis")[0] == "UNPROVEN"

    (tmp_path / "real_record.json").write_text(
        json.dumps({"gate": "PASS", "run_name": "real", "analyses": {"lookahead": "pass"}}),
        encoding="utf-8",
    )
    assert admission._from_gate_records("lookahead", "lookahead analysis")[0] == "PASS"


def test_no_committed_record_claims_a_passing_gate_yet():
    assert admission._gate_records() == []


def test_no_override_flag_exists():
    """Section 5 has no escape hatch, and neither may the implementation."""
    source = (admission.REPO_ROOT / "research" / "fp" / "admission.py").read_text(encoding="utf-8")
    for flag in ("--force", "--override", "--allow-blocked", "--assume-pass"):
        assert flag not in source


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
