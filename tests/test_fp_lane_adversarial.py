"""Adversarial proofs for the lane-identity repair.

Each test constructs the exact attack an independent review either reproduced or
named, and requires the code to reject it *for the stated reason*. A test that
passes because something unrelated failed first proves nothing, so where an
attack could be stopped early by a different guard, the fixture is built to get
past that guard and reach the invariant under test.

No positional registry indexing anywhere: rows are found by role, because
position is exactly the assumption this repair is removing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import check_fp_overlay
from fp import admission, capture, lane

REGISTRY_PATH = Path("research/fp/records/forward_paper_cohort_registry.json")
SCHEMA_PATH = Path("research/schema/forward_paper_cohort_registry.schema.json")
CLOSED = "FP-CONTROL-1"
SUCCESSOR = "FP-CONTROL-2"
HOST_USER_DATA = lane.HOST_USER_DATA


@pytest.fixture(scope="module")
def registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def row(registry: dict, role: str) -> dict:
    """Role lookup, never an index."""
    return next(item for item in registry["instances"] if item["role"] == role)


def rendered_overlay() -> dict:
    """The real rendered stack for the successor, as the launcher renders it."""
    env = dict(os.environ)
    resolved = subprocess.run(
        [sys.executable, "scripts/fp_instance.py", SUCCESSOR],
        capture_output=True, text=True, timeout=60, check=True,
    ).stdout
    for line in resolved.strip().splitlines():
        key, value = line.split("=", 1)
        env[key] = value.strip("'")
    out = subprocess.run(
        ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.fp.yml", "config"],
        capture_output=True, text=True, timeout=180, env=env,
    )
    if out.returncode != 0:
        pytest.skip("docker compose is unavailable in this environment")
    return yaml.safe_load(out.stdout)


def writable_sources(rendered: dict) -> list[tuple[str, dict]]:
    pairs = []
    for name in ("freqtrade", "fp-capture"):
        service = rendered["services"][name]
        for volume in service.get("volumes") or []:
            if isinstance(volume, dict) and not volume.get("read_only"):
                pairs.append((name, volume))
    return pairs


# -- 1. the reproduced critical attack -------------------------------------


def test_a_closed_host_source_on_the_successor_target_is_rejected(registry):
    """The exact bypass the review demonstrated: right target, wrong host lane."""
    rendered = rendered_overlay()
    closed_host = str(HOST_USER_DATA / "fp-control-1")
    for _, volume in writable_sources(rendered):
        volume["source"] = closed_host
    problems = check_fp_overlay.check(rendered, SUCCESSOR)
    assert problems, "a closed host lane mounted at the successor's target must be rejected"
    assert any("fp-control-1" in p and "host" in p for p in problems), problems


# -- 2. symlink escape ------------------------------------------------------


def test_a_symlinked_host_source_that_escapes_the_lane_is_rejected(tmp_path):
    """realpath, not the literal string: a symlink is the oldest escape there is."""
    rendered = rendered_overlay()
    escape = tmp_path / "looks-like-the-lane"
    escape.symlink_to(HOST_USER_DATA / "fp-control-1", target_is_directory=True)
    for _, volume in writable_sources(rendered):
        volume["source"] = str(escape)
    problems = check_fp_overlay.check(rendered, SUCCESSOR)
    assert problems, "a symlink pointing out of the lane must be resolved and rejected"
    assert any("host" in p for p in problems), problems


# -- 3. nested / parent cross-instance collision ---------------------------


def test_a_parent_of_the_lane_as_writable_source_is_rejected():
    rendered = rendered_overlay()
    for _, volume in writable_sources(rendered):
        volume["source"] = str(HOST_USER_DATA)       # the parent of every lane
    problems = check_fp_overlay.check(rendered, SUCCESSOR)
    assert problems, "mounting the parent of all lanes writable must be rejected"


def test_nested_and_parent_paths_collide_in_both_directions(registry):
    closed = row(registry, CLOSED)["runtime_identity"]["evidence_dir"]
    with pytest.raises(capture.InstanceSelectionError):
        capture.assert_paths_are_exclusive(SUCCESSOR, Path(closed) / "nested", registry)
    with pytest.raises(capture.InstanceSelectionError):
        capture.assert_paths_are_exclusive(SUCCESSOR, Path(closed).parent, registry)


def test_the_host_twin_of_another_lane_collides(registry):
    """A host-side run collides through the host path, which the container path alone never sees."""
    closed_host = lane.container_to_host(row(registry, CLOSED)["runtime_identity"]["evidence_dir"])
    with pytest.raises(capture.InstanceSelectionError) as excinfo:
        capture.assert_paths_are_exclusive(SUCCESSOR, closed_host, registry)
    assert "collides" in str(excinfo.value)


# -- 4. path-prefix neighbour, reached with a valid role -------------------


def test_a_prefix_neighbour_lane_is_rejected_for_a_valid_role():
    """`fp-control-2-evil` shares a prefix with the real lane and is not it.

    The earlier version of this proof passed for the wrong reason — it supplied
    an unknown role, so selection stopped before the path was ever considered.
    Here the role is the genuine one, so the path check is what must fail.
    """
    rendered = rendered_overlay()
    for _, volume in writable_sources(rendered):
        volume["source"] = str(HOST_USER_DATA / "fp-control-2-evil")
        volume["target"] = "/freqtrade/user_data/fp-control-2-evil"
    problems = check_fp_overlay.check(rendered, SUCCESSOR)
    assert problems, "a prefix-neighbour lane must be rejected"
    assert any("fp-control-2-evil" in p for p in problems), problems


def test_prefix_neighbours_are_not_containment(registry):
    successor_host = lane.resolve_lane(SUCCESSOR, registry).host_instance_dir
    assert not lane.resolve_lane(SUCCESSOR, registry).owns_host_path(
        Path(str(successor_host) + "-evil")
    )


# -- 5, 6. bot name --------------------------------------------------------


def test_a_missing_bot_name_is_rejected():
    rendered = rendered_overlay()
    rendered["services"]["freqtrade"]["environment"].pop("FREQTRADE__BOT_NAME", None)
    problems = check_fp_overlay.check(rendered, SUCCESSOR)
    assert any("BOT_NAME" in p for p in problems), problems


def test_a_wrong_bot_name_is_rejected():
    rendered = rendered_overlay()
    rendered["services"]["freqtrade"]["environment"]["FREQTRADE__BOT_NAME"] = "fp-control-1"
    problems = check_fp_overlay.check(rendered, SUCCESSOR)
    assert any("bot" in p for p in problems), problems


# -- 7, 8. exact argument spoofs ------------------------------------------


def test_a_role_argument_spoof_is_rejected():
    """Substring matching accepted `--role=FP-CONTROL-2-evil`; parsing must not."""
    rendered = rendered_overlay()
    command = rendered["services"]["fp-capture"]["command"]
    rendered["services"]["fp-capture"]["command"] = [
        f"--role={SUCCESSOR}-evil" if str(c).startswith("--role=") else c for c in command
    ]
    problems = check_fp_overlay.check(rendered, SUCCESSOR)
    assert any("role" in p for p in problems), problems


def test_an_evidence_dir_argument_spoof_is_rejected():
    rendered = rendered_overlay()
    command = rendered["services"]["fp-capture"]["command"]
    rendered["services"]["fp-capture"]["command"] = [
        "--evidence-dir=/freqtrade/user_data/fp-control-2/evidence-evil"
        if str(c).startswith("--evidence-dir=") else c
        for c in command
    ]
    problems = check_fp_overlay.check(rendered, SUCCESSOR)
    assert any("evidence" in p for p in problems), problems


def test_argument_parsing_returns_exact_values():
    parsed = check_fp_overlay.parse_args(["python", "x.py", "--role=FP-CONTROL-2", "--evidence-dir", "/a/b"])
    assert parsed["--role"] == "FP-CONTROL-2"
    assert parsed["--evidence-dir"] == "/a/b"


# -- 9, 10, 11, 12. selection versus execution -----------------------------


def test_an_unknown_role_fails_closed(registry):
    with pytest.raises(lane.LaneError) as excinfo:
        lane.resolve_lane("FP-CONTROL-404", registry)
    assert "unknown instance role" in str(excinfo.value)


def test_a_duplicate_role_fails_closed(registry):
    doubled = json.loads(json.dumps(registry))
    doubled["instances"].append(json.loads(json.dumps(row(doubled, SUCCESSOR))))
    with pytest.raises(lane.LaneError) as excinfo:
        lane.resolve_lane(SUCCESSOR, doubled)
    assert "ambiguous" in str(excinfo.value)


@pytest.mark.parametrize("status", [None, "", "RUNNIG", "started", 7])
def test_a_malformed_or_missing_status_fails_closed(registry, status):
    broken = json.loads(json.dumps(registry))
    target = row(broken, SUCCESSOR)
    if status is None:
        target.pop("status")
    else:
        target["status"] = status
    with pytest.raises(lane.LaneError) as excinfo:
        lane.resolve_lane(SUCCESSOR, broken)
    assert "status" in str(excinfo.value)


def test_a_paused_row_may_not_start_or_capture_but_may_be_stopped(registry):
    paused = json.loads(json.dumps(registry))
    target = row(paused, SUCCESSOR)
    target["status"] = "PAUSED"
    target["t0_utc"] = "2026-09-14T00:00:00Z"
    target["cohort_id"] = "FP-CONTROL-2-20260914T000000Z"
    target["runtime_identity"]["source_commit"] = "0" * 40

    with pytest.raises(lane.LaneError) as excinfo:
        lane.resolve_lane(SUCCESSOR, paused, allowed_statuses=lane.EXECUTABLE_STATUSES)
    assert "PAUSED" in str(excinfo.value)
    with pytest.raises(capture.InstanceSelectionError):
        capture.select_instance(SUCCESSOR, paused)

    # ... and stopping it must still work, or PAUSED becomes a trap.
    assert lane.resolve_lane(SUCCESSOR, paused, allowed_statuses=lane.STOPPABLE_STATUSES).status == "PAUSED"


def test_a_closed_row_never_executes(registry):
    with pytest.raises(lane.LaneError):
        lane.resolve_lane(CLOSED, registry, allowed_statuses=lane.EXECUTABLE_STATUSES)
    with pytest.raises(lane.LaneError):
        lane.resolve_lane(CLOSED, registry, allowed_statuses=lane.STOPPABLE_STATUSES)


# -- 13, 14, 15. started-state schema --------------------------------------


def validator():
    import jsonschema

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return jsonschema.validators.validator_for(schema)(schema)


@pytest.mark.parametrize("field", ["t0_utc", "cohort_id", "source_commit"])
def test_an_empty_started_identity_field_is_rejected(registry, field):
    """An empty string is a JSON string: type alone never caught this."""
    doc = json.loads(json.dumps(registry))
    target = row(doc, SUCCESSOR)
    target["status"] = "RUNNING"
    doc["fp_run_active"] = True
    target["t0_utc"] = "2026-09-14T00:00:00Z"
    target["cohort_id"] = "FP-CONTROL-2-20260914T000000Z"
    target["runtime_identity"]["source_commit"] = "0" * 40
    if field == "source_commit":
        target["runtime_identity"][field] = ""
    else:
        target[field] = ""
    assert list(validator().iter_errors(doc)), f"an empty {field} must not validate"


def test_a_well_formed_started_row_still_validates(registry):
    doc = json.loads(json.dumps(registry))
    target = row(doc, SUCCESSOR)
    target["status"] = "RUNNING"
    doc["fp_run_active"] = True
    target["t0_utc"] = "2026-09-14T00:00:00Z"
    target["cohort_id"] = "FP-CONTROL-2-20260914T000000Z"
    target["runtime_identity"]["source_commit"] = "a" * 40
    assert list(validator().iter_errors(doc)) == [], "the repair must not forbid a legitimate started row"


# -- 16, 17, 18, 19. candidate cardinality ---------------------------------


def candidate_row(registry: dict, role: str) -> dict:
    template = json.loads(json.dumps(row(registry, SUCCESSOR)))
    template["role"] = role
    template["runtime_identity"]["candidate_family"] = f"family-of-{role}"
    return template


def test_zero_eligible_candidates_identifies_none(registry, tmp_path, monkeypatch):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    monkeypatch.setattr(admission, "COHORT_REGISTRY", path)
    assert admission.candidate_cardinality()[0] == "NONE"
    assert admission.identified_candidate() is None
    assert admission.evaluate()["paper_admission"] == "BLOCKED"


def test_exactly_one_eligible_candidate_is_used(registry, tmp_path, monkeypatch):
    doc = json.loads(json.dumps(registry))
    doc["instances"].append(candidate_row(registry, "FP-CANDIDATE-B"))
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(admission, "COHORT_REGISTRY", path)
    shape, rows = admission.candidate_cardinality()
    assert shape == "UNIQUE"
    assert [r["role"] for r in rows] == ["FP-CANDIDATE-B"]
    # and the emitted record names B, not a hard-coded A
    assert admission.evaluate()["candidate"]["role"] == "FP-CANDIDATE-B"


def test_multiple_eligible_candidates_fail_closed(registry, tmp_path, monkeypatch):
    doc = json.loads(json.dumps(registry))
    doc["instances"].append(candidate_row(registry, "FP-CANDIDATE-A"))
    doc["instances"].append(candidate_row(registry, "FP-CANDIDATE-B"))
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(admission, "COHORT_REGISTRY", path)
    assert admission.candidate_cardinality()[0] == "AMBIGUOUS"
    assert admission.identified_candidate() is None
    record = admission.evaluate()
    assert record["paper_admission"] == "BLOCKED"
    assert any("eligible candidates" in c["evidence"] for c in record["conditions"])


def test_a_closed_candidate_is_never_eligible(registry, tmp_path, monkeypatch):
    doc = json.loads(json.dumps(registry))
    closed_candidate = candidate_row(registry, "FP-CANDIDATE-A")
    closed_candidate["status"] = "CLOSED"
    closed_candidate["t0_utc"] = "2026-09-01T00:00:00Z"
    closed_candidate["cohort_id"] = "FP-CANDIDATE-A-20260901T000000Z"
    closed_candidate["runtime_identity"]["source_commit"] = "b" * 40
    doc["instances"].append(closed_candidate)
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(admission, "COHORT_REGISTRY", path)
    assert admission.candidate_cardinality()[0] == "NONE"
    assert admission.identified_candidate() is None


def test_candidate_order_does_not_change_the_result(registry, tmp_path, monkeypatch):
    """Reversing the rows changed the identified candidate before this repair."""
    doc = json.loads(json.dumps(registry))
    doc["instances"].append(candidate_row(registry, "FP-CANDIDATE-B"))
    forward = tmp_path / "forward.json"
    forward.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(admission, "COHORT_REGISTRY", forward)
    first = admission.identified_candidate()

    reversed_doc = json.loads(json.dumps(doc))
    reversed_doc["instances"].reverse()
    backward = tmp_path / "backward.json"
    backward.write_text(json.dumps(reversed_doc), encoding="utf-8")
    monkeypatch.setattr(admission, "COHORT_REGISTRY", backward)
    assert admission.identified_candidate() == first


# -- 20. the activation pack carries no runnable mutation ------------------


def test_the_activation_pack_has_no_runnable_registry_write(tmp_path):
    """Not "is it fenced as text" — is there anything left that could run?"""
    pack = Path("docs/fp-boot-1/FP_CONTROL_1_ACTIVATION_PACK.md").read_text(encoding="utf-8")
    a14 = pack[pack.index("### A14"):pack.index("### A15")]
    for runnable in ("python3 - <<", "reg.write_text", "json.dumps(r", "subprocess.check_output",
                     'inst["t0_utc"]', 'inst["cohort_id"]', '["fp_run_active"] = True', "git commit -m"):
        assert runnable not in a14, f"A14 still carries runnable material: {runnable!r}"
    # Nothing anywhere in the pack writes the registry file.
    assert "reg.write_text" not in pack
    assert "forward_paper_cohort_registry.json" not in a14


# -- 21. the legitimate lane still resolves, in both namespaces ------------


def test_the_successor_lane_resolves_in_both_namespaces(registry):
    resolved = lane.resolve_lane(SUCCESSOR, registry, allowed_statuses=lane.EXECUTABLE_STATUSES)
    assert resolved.instance_dir == "fp-control-2"
    assert resolved.bot_name == "fp-control-2"
    assert str(resolved.container_evidence_dir) == "/freqtrade/user_data/fp-control-2/evidence"
    assert resolved.host_evidence_dir == HOST_USER_DATA / "fp-control-2" / "evidence"
    assert resolved.matches_evidence_dir(resolved.container_evidence_dir)
    assert resolved.matches_evidence_dir(resolved.host_evidence_dir)
    # and the host path a real qualification would use is accepted by the runtime gate
    capture.assert_evidence_dir_is_declared(SUCCESSOR, resolved.host_evidence_dir, registry)
    capture.assert_evidence_dir_is_declared(SUCCESSOR, Path(str(resolved.container_evidence_dir)), registry)


def test_every_component_resolves_the_lane_through_one_module():
    """Launcher, capture, preflight and the overlay guard share the resolver."""
    for path, needle in (
        ("research/fp/capture.py", "fp_lane.resolve_lane"),
        ("research/fp/preflight.py", "assert_evidence_dir_is_declared"),
        ("scripts/check_fp_overlay.py", "fp_lane.resolve_lane"),
        ("scripts/fp_instance.py", "resolve_lane"),
    ):
        assert needle in Path(path).read_text(encoding="utf-8"), f"{path} does not use the shared resolver"
