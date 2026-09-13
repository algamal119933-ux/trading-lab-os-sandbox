"""The pre-T0 successor control instance, and the selection that guards it.

FP-CONTROL-1 closed with its evidence lane lost. Qualifying a runtime on the new
host needs a runnable instance, and the dangerous shortcut is to reuse the closed
one: its paths exist, its identity is bound, and nothing in the old code stopped
a capture loop from stamping a terminated cohort's id onto fresh evidence. These
tests hold the line the closure record drew — a closed cohort accepts nothing
further, and a successor inherits nothing.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from fp import capture

REGISTRY_PATH = "research/fp/records/forward_paper_cohort_registry.json"
SCHEMA_PATH = "research/schema/forward_paper_cohort_registry.schema.json"
HISTORICAL = "FP-CONTROL-1"
SUCCESSOR = "FP-CONTROL-2"


@pytest.fixture(scope="module")
def registry(request) -> dict:
    return json.loads((request.config.rootpath / REGISTRY_PATH).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def historical(registry) -> dict:
    return next(i for i in registry["instances"] if i["role"] == HISTORICAL)


@pytest.fixture(scope="module")
def successor(registry) -> dict:
    return next(i for i in registry["instances"] if i["role"] == SUCCESSOR)


# -- 1. a closed instance accepts no further capture ----------------------


def test_a_closed_instance_is_refused_by_selection(registry):
    with pytest.raises(capture.InstanceSelectionError) as excinfo:
        capture.select_instance(HISTORICAL, registry)
    assert "CLOSED" in str(excinfo.value)


def test_a_closed_instance_cannot_build_a_runtime_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "COHORT_REGISTRY", Path(REGISTRY_PATH).resolve())
    with pytest.raises(capture.InstanceSelectionError):
        capture.build_identity(tmp_path, role=HISTORICAL)


def test_the_capture_cli_refuses_a_closed_role(tmp_path):
    """End to end: the process exits non-zero before opening any ledger."""
    result = subprocess.run(
        [sys.executable, "research/fp/capture.py", "--role", HISTORICAL,
         "--evidence-dir", str(tmp_path), "--cycles", "1"],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode != 0
    assert "CAPTURE_REFUSED" in result.stderr
    assert not list(tmp_path.iterdir()), "a refused run must leave no evidence behind"


# -- 2, 3. the successor inherits nothing ---------------------------------


def test_the_successor_inherits_no_t0(successor, historical):
    assert successor["t0_utc"] is None
    assert historical["t0_utc"] == "2026-09-08T12:15:13Z"
    assert successor["t0_utc"] != historical["t0_utc"]


def test_the_successor_inherits_no_cohort_id(successor, historical):
    assert successor["cohort_id"] is None
    assert historical["cohort_id"] == "FP-CONTROL-1-20260908T121513Z"


def test_the_successor_inherits_no_outcome_or_evidence(successor):
    assert "outcome" not in successor
    assert successor["change_log"] == []
    assert successor["closed_utc"] is None
    assert successor["closure_reason"] is None
    assert successor["runtime_identity"]["source_commit"] is None


def test_a_capture_identity_for_the_successor_carries_no_cohort(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "COHORT_REGISTRY", Path(REGISTRY_PATH).resolve())
    identity = capture.build_identity(tmp_path, role=SUCCESSOR)
    assert identity.cohort_id is None
    assert identity.bot_name == "fp-control-2"
    assert capture._registry_t0_ms(SUCCESSOR) is None


# -- 4, 5. unknown and ambiguous selection fail closed --------------------


def test_an_unknown_role_fails_closed(registry):
    with pytest.raises(capture.InstanceSelectionError) as excinfo:
        capture.select_instance("FP-CONTROL-404", registry)
    assert "unknown instance role" in str(excinfo.value)


def test_an_ambiguous_role_fails_closed(registry):
    duplicated = json.loads(json.dumps(registry))
    duplicated["instances"].append(json.loads(json.dumps(duplicated["instances"][-1])))
    with pytest.raises(capture.InstanceSelectionError) as excinfo:
        capture.select_instance(SUCCESSOR, duplicated)
    assert "ambiguous" in str(excinfo.value)


def test_there_is_no_first_row_fallback(registry):
    """The old behaviour returned an empty identity for an unknown role."""
    source = Path("research/fp/capture.py").read_text(encoding="utf-8")
    assert "select_instance(role, registry)" in source
    assert 'if item.get("role") == role),\n        {},\n    )' not in source


# -- 6. path collisions fail ----------------------------------------------


def test_paths_are_distinct_between_the_instances(historical, successor):
    for field in ("db_path", "log_path", "evidence_dir", "bot_name"):
        assert historical["runtime_identity"][field] != successor["runtime_identity"][field], field


def test_writing_into_the_closed_instances_paths_is_refused(registry):
    closed_evidence = registry["instances"][0]["runtime_identity"]["evidence_dir"]
    with pytest.raises(capture.InstanceSelectionError) as excinfo:
        capture.assert_paths_are_exclusive(SUCCESSOR, Path(closed_evidence), registry)
    assert "collides" in str(excinfo.value)


def test_a_nested_path_under_the_closed_instance_is_also_refused(registry):
    closed_evidence = registry["instances"][0]["runtime_identity"]["evidence_dir"]
    with pytest.raises(capture.InstanceSelectionError):
        capture.assert_paths_are_exclusive(SUCCESSOR, Path(closed_evidence) / "nested", registry)


def test_the_successors_own_path_is_permitted(registry):
    own = registry["instances"][-1]["runtime_identity"]["evidence_dir"]
    capture.assert_paths_are_exclusive(SUCCESSOR, Path(own), registry)  # must not raise


# -- 7, 8. qualification can create neither a T0 nor a cohort id ----------


def test_the_capture_loop_has_no_registry_write_path():
    source = Path("research/fp/capture.py").read_text(encoding="utf-8")
    assert "COHORT_REGISTRY" in source
    for write in ("COHORT_REGISTRY.write_text", "open(COHORT_REGISTRY, \"w\")", "json.dump(registry"):
        assert write not in source, f"capture.py can write the registry via {write}"


def test_a_pre_t0_instance_reports_t0_not_frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "COHORT_REGISTRY", Path(REGISTRY_PATH).resolve())
    loop = capture.CaptureLoop(tmp_path, ["BTC/USDT"], role=SUCCESSOR)
    assert loop.t0_ms is None
    assert loop.t0_relation(1_789_000_000_000) == "T0_NOT_FROZEN"


def test_the_successor_stays_pre_t0_in_the_committed_registry(successor, registry):
    assert successor["status"] == "NOT_STARTED"
    assert registry["fp_run_active"] is False
    assert registry["paper_alpha_cohort"] == "NONE"
    assert registry["entry_state"] == "C"


# -- 9, 10, 11. nothing else moved ----------------------------------------


def test_the_historical_closed_truth_is_unchanged(historical):
    assert historical["status"] == "CLOSED"
    assert historical["closed_utc"] == "2026-09-13T20:58:24Z"
    assert historical["closure_reason"] == "EVIDENCE_LANE_LOST_IN_HOST_MIGRATION"
    assert historical["runtime_identity"]["source_commit"] == "4b0d7f6326ead0a19f8870f94528a9aa75114e10"
    outcome = historical["outcome"]
    assert outcome["paper_trading_operational_capability"] == "NOT_PROVEN"
    assert outcome["full_trade_lifecycle"] == "NOT_ESTABLISHED_BY_AVAILABLE_EVIDENCE"
    assert outcome["prospective_paper_edge"] == "NOT_EVALUATED"
    assert outcome["measurable_post_t0_evidence"] == "UNAVAILABLE_IN_CURRENT_EVIDENCE_LANE"
    assert [e["class"] for e in historical["change_log"]] == ["O", "O"]


def test_the_dataset_authority_is_unchanged(request):
    lock = json.loads((request.config.rootpath / "research/datasets/dataset_v2.lock.json").read_text(encoding="utf-8"))
    assert lock["status"] == "frozen"
    assert lock["canonical_hashes"]["BTC/USDT 1h"] == (
        "9e564a7d5738821757202263bf98f12062e43021c6a810020f4d9d9907ca9763"
    )
    assert lock["raw_file_hashes"]["BTC/USDT 1h"] == (
        "d8e2ffd5cd78c6bdf24f41e5e71d463f2343b3fb099f6546e2bc6c68b48b67e4"
    )
    assert len(lock["canonical_hashes"]) == 4 and len(lock["raw_file_hashes"]) == 4


def test_the_research_branch_stays_parked():
    """19d7d7e must not have been merged into this branch's history."""
    merged = subprocess.run(
        ["git", "merge-base", "--is-ancestor", "19d7d7e76831a44c0c3ee643e2cebe7979f456f0", "HEAD"],
        capture_output=True, text=True, timeout=60,
    )
    assert merged.returncode != 0, "the parked research branch is an ancestor of HEAD"


def test_the_registry_still_validates(request, registry):
    import jsonschema

    schema = json.loads((request.config.rootpath / SCHEMA_PATH).read_text(encoding="utf-8"))
    assert list(jsonschema.validators.validator_for(schema)(schema).iter_errors(registry)) == []


# -- a control is never a candidate, however many control rows exist ------


def test_a_successor_control_is_not_read_as_a_candidate(registry):
    """A control row must never satisfy a candidate's admission conditions.

    The evaluator excluded one role literal, so registering a second control
    made it look like an identified candidate — and conditions 3-6 would then
    have been answered from the control's own records. Entry state C says there
    is no survivor to admit; adding a qualification instance must not change that.
    """
    from fp import admission

    assert admission.identified_candidate() is None
    record = admission.evaluate()
    assert record["paper_admission"] == "BLOCKED"
    assert record["candidate"]["name"] is None
    assert record["entry_state"] == "C"
    assert registry["paper_alpha_cohort"] == "NONE"
