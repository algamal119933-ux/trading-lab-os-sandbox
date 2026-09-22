"""RUNNING/T0 correspondence: the invariants a per-row JSON schema cannot state.

The schema already does a great deal, and these tests do not restate it. What a
schema cannot do is relate a row to the registry header or to another row:
``fp_run_active`` is one flag summarising many rows, ``cohort_id`` is *derived*
from role and T0 by a stated rule the schema can only type-check, and "at most
one cohort is live" is a statement about the array rather than about any element
of it.

Each test below names a registry that the schema would accept and the law must
not, and the last group proves the law accepts the legitimate shapes — a rule
that rejected the real registry would be a rule nobody could satisfy.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import conftest

from fp import registry_law as law

REGISTRY_PATH = Path("research/fp/records/forward_paper_cohort_registry.json")
CLOSED = "FP-CONTROL-1"
# The cohort this repository is freezing, resolved from the registry rather
# than named: a literal here winds back a row nobody froze while another row
# is RUNNING, which is an unlawful registry, not a pre-T0 one.
SUCCESSOR = conftest.live_role()


@pytest.fixture
def registry() -> dict:
    return conftest.pre_t0_registry(SUCCESSOR)


def row(registry: dict, role: str) -> dict:
    return next(item for item in registry["instances"] if item["role"] == role)


def _freeze(registry: dict, role: str, t0: str = "2026-09-20T14:00:00Z") -> dict:
    """A lawfully frozen row, as scripts/freeze_t0.py would write it."""
    registry = copy.deepcopy(registry)
    target = row(registry, role)
    target["status"] = "RUNNING"
    target["t0_utc"] = t0
    target["cohort_id"] = law.cohort_id_for(role, t0)
    target["runtime_identity"]["source_commit"] = "e" * 40
    target["change_log"] = [{"utc": t0, "class": "O", "description": "T0 frozen."}]
    registry["fp_run_active"] = True
    return registry


# -- the committed registry, and a lawful freeze of it ---------------------


def test_the_committed_registry_is_lawful(registry):
    assert law.check_registry(registry) == []


def test_a_lawful_freeze_is_lawful(registry):
    assert law.check_registry(_freeze(registry, SUCCESSOR)) == []


def test_the_derivation_reproduces_the_real_frozen_cohort_id(registry):
    """FP-CONTROL-1's id was frozen on the prior host and is the precedent."""
    closed = row(registry, CLOSED)
    assert law.cohort_id_for(CLOSED, closed["t0_utc"]) == closed["cohort_id"]
    assert closed["cohort_id"] == "FP-CONTROL-1-20260908T121513Z"


# -- what the schema would accept and the law must not ---------------------


def test_a_running_row_with_the_flag_off_is_refused(registry):
    unlawful = _freeze(registry, SUCCESSOR)
    unlawful["fp_run_active"] = False
    problems = law.check_registry(unlawful)
    assert any("fp_run_active is false" in p for p in problems), problems


def test_the_flag_on_with_no_running_row_is_refused(registry):
    unlawful = copy.deepcopy(registry)
    unlawful["fp_run_active"] = True
    problems = law.check_registry(unlawful)
    assert any("no row is RUNNING" in p for p in problems), problems


def test_a_cohort_id_naming_a_different_instant_is_refused(registry):
    """The schema requires a non-empty string; it cannot require the right one."""
    unlawful = _freeze(registry, SUCCESSOR)
    row(unlawful, SUCCESSOR)["cohort_id"] = "FP-CONTROL-2-20260101T000000Z"
    problems = law.check_registry(unlawful)
    assert any("derives" in p for p in problems), problems


def test_two_running_rows_are_refused(registry):
    unlawful = _freeze(registry, SUCCESSOR)
    closed = row(unlawful, CLOSED)
    closed["status"] = "RUNNING"
    closed.pop("outcome", None)
    problems = law.check_registry(unlawful)
    assert any("rows are RUNNING" in p for p in problems), problems


def test_a_not_started_row_holding_a_t0_is_refused(registry):
    unlawful = copy.deepcopy(registry)
    row(unlawful, SUCCESSOR)["t0_utc"] = "2026-09-20T14:00:00Z"
    problems = law.check_registry(unlawful)
    assert any("NOT_STARTED but carries t0_utc" in p for p in problems), problems


def test_a_running_row_with_a_short_commit_is_refused(registry):
    unlawful = _freeze(registry, SUCCESSOR)
    row(unlawful, SUCCESSOR)["runtime_identity"]["source_commit"] = "abc1234"
    problems = law.check_registry(unlawful)
    assert any("not a 40-hex commit id" in p for p in problems), problems


def test_a_running_row_with_a_malformed_t0_does_not_cascade(registry):
    """One bad input produces one finding, not a second computed from the first."""
    unlawful = _freeze(registry, SUCCESSOR)
    row(unlawful, SUCCESSOR)["t0_utc"] = "yesterday"
    problems = [p for p in law.check_registry(unlawful) if SUCCESSOR in p]
    assert len(problems) == 1, problems
    assert "not a frozen instant" in problems[0]


def test_two_rows_declaring_one_lane_are_refused(registry):
    unlawful = copy.deepcopy(registry)
    closed_paths = row(unlawful, CLOSED)["runtime_identity"]
    successor_paths = row(unlawful, SUCCESSOR)["runtime_identity"]
    successor_paths["evidence_dir"] = closed_paths["evidence_dir"]
    problems = law.check_registry(unlawful)
    assert any("declared by more than one row" in p for p in problems), problems


def test_real_money_authorized_must_be_false(registry):
    unlawful = copy.deepcopy(registry)
    unlawful["real_money_authorized"] = True
    problems = law.check_registry(unlawful)
    assert any("PAPER / RESEARCH ONLY" in p for p in problems), problems


def test_a_duplicated_role_is_refused(registry):
    unlawful = copy.deepcopy(registry)
    unlawful["instances"].append(copy.deepcopy(row(unlawful, SUCCESSOR)))
    problems = law.check_registry(unlawful)
    assert any("declared more than once" in p for p in problems), problems


def test_an_unknown_status_is_refused(registry):
    unlawful = copy.deepcopy(registry)
    row(unlawful, SUCCESSOR)["status"] = "STARTING"
    problems = law.check_registry(unlawful)
    assert any("not a status the registry admits" in p for p in problems), problems


# -- the law and the schema must not contradict each other -----------------


def test_a_registry_the_law_accepts_also_validates_against_the_schema(registry):
    """A lawful freeze must be a schema-valid registry, or the two disagree."""
    import jsonschema

    schema = json.loads(
        Path("research/schema/forward_paper_cohort_registry.schema.json").read_text(encoding="utf-8")
    )
    frozen = _freeze(registry, SUCCESSOR)
    errors = list(jsonschema.validators.validator_for(schema)(schema).iter_errors(frozen))
    assert not errors, [e.message for e in errors]
