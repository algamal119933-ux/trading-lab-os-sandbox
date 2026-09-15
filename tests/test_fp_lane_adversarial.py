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


# =========================================================================
# P1 stage contract §8 — behavioural proofs at the real entrypoints.
#
# Two escapes survived two independent reviews by slipping through the gap
# between a unit-level truth and the production path that actually runs. These
# proofs therefore exercise the rendered graph and the real scripts, and their
# expected values are anchored independently of the implementation constants
# they check — a test that imports the constant it is verifying cannot catch a
# sabotaged constant.
# =========================================================================

# Anchored by hand, not by importing lane.HOST_USER_DATA.
REPO_ROOT_LITERAL = Path(__file__).resolve().parent.parent
HOST_USER_DATA_LITERAL = REPO_ROOT_LITERAL / "freqtrade" / "user_data"
CLOSED_LANE_LITERAL = HOST_USER_DATA_LITERAL / "fp-control-1"
SUCCESSOR_LANE_LITERAL = HOST_USER_DATA_LITERAL / "fp-control-2"


def all_service_names(rendered: dict) -> list[str]:
    return sorted(rendered.get("services", {}))


def test_the_rendered_graph_has_more_services_than_the_two_named_ones():
    """If this ever shrinks to two, the whole-graph proof below means less."""
    names = all_service_names(rendered_overlay())
    assert len(names) > 2, names
    assert {"freqtrade", "fp-capture"}.issubset(set(names))


def test_a_writable_closed_lane_is_rejected_on_every_rendered_service():
    """The bypass the second review found: an auxiliary service, unchecked."""
    base = rendered_overlay()
    for name in all_service_names(base):
        rendered = json.loads(json.dumps(base))
        rendered["services"][name]["volumes"] = [
            {"type": "bind", "source": str(CLOSED_LANE_LITERAL),
             "target": "/freqtrade/user_data/fp-control-1", "read_only": False}
        ]
        problems = check_fp_overlay.check(rendered, SUCCESSOR)
        assert problems, f"{name} may not mount the closed lane writable"
        assert any("fp-control-1" in p for p in problems), (name, problems)


def test_a_service_added_later_cannot_bypass_mount_isolation():
    """Enforcement must follow the graph, not a hard-coded list of names."""
    rendered = rendered_overlay()
    rendered["services"]["some-future-sidecar"] = {
        "image": "busybox",
        "volumes": [{"type": "bind", "source": str(CLOSED_LANE_LITERAL),
                     "target": "/freqtrade/user_data/fp-control-1", "read_only": False}],
    }
    problems = check_fp_overlay.check(rendered, SUCCESSOR)
    assert any("some-future-sidecar" in p for p in problems), problems


def test_shared_read_only_mounts_remain_acceptable():
    """The repair must not make the legitimate render fail."""
    assert check_fp_overlay.check(rendered_overlay(), SUCCESSOR) == []


@pytest.mark.parametrize(
    "argument,spoof",
    [
        ("--strategy", "BaselineEmaRegimeV1Evil"),
        ("--db-url", "sqlite:////freqtrade/user_data/fp-control-2/tradesv3.sqlite-evil"),
        ("--logfile", "/freqtrade/user_data/fp-control-2/logs/freqtrade.log-evil"),
        ("--config", "/freqtrade/user_data/config.json-evil"),
    ],
)
def test_engine_argument_spoofs_are_rejected(argument, spoof):
    """Suffix lookalikes are different runtimes, and must be read as different."""
    rendered = rendered_overlay()
    command = [str(c) for c in rendered["services"]["freqtrade"]["command"]]
    out, index = [], 0
    while index < len(command):
        token = command[index]
        out.append(token)
        if token == argument and index + 1 < len(command):
            out.append(spoof)
            index += 2
            continue
        index += 1
    rendered["services"]["freqtrade"]["command"] = out
    problems = check_fp_overlay.check(rendered, SUCCESSOR)
    assert problems, f"a spoofed {argument} must be rejected"


def test_the_paused_stop_path_works_at_the_real_entrypoint(tmp_path):
    """scripts/stop_fp_control.sh itself, not the resolver underneath it.

    The escape this catches hid exactly in that gap: the resolver was correct and
    the script still refused. The script is run with a patched registry and a
    stubbed `docker` on PATH, so the test proves the script reaches the stop
    command without starting or stopping anything real.
    """
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    paused = row(registry, SUCCESSOR)
    paused.update(status="PAUSED", t0_utc="2026-09-14T00:00:00Z",
                  cohort_id="FP-CONTROL-2-20260914T000000Z")
    paused["runtime_identity"]["source_commit"] = "0" * 40
    patched = tmp_path / "registry.json"
    patched.write_text(json.dumps(registry), encoding="utf-8")

    # A docker that records its arguments and does nothing.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "docker-args.txt"
    (bin_dir / "docker").write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$*" >> {marker}\nexit 0\n', encoding="utf-8"
    )
    (bin_dir / "docker").chmod(0o755)

    # A sitecustomize that points the lane module at the patched registry.
    site = tmp_path / "site"
    site.mkdir()
    (site / "sitecustomize.py").write_text(
        "import pathlib, sys\n"
        f"sys.path.insert(0, {str(Path('research').resolve())!r})\n"
        "from fp import lane\n"
        f"lane.COHORT_REGISTRY = pathlib.Path({str(patched)!r})\n",
        encoding="utf-8",
    )

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["PYTHONPATH"] = f"{site}:{env.get('PYTHONPATH', '')}"
    result = subprocess.run(["bash", "scripts/stop_fp_control.sh", SUCCESSOR],
                            capture_output=True, text=True, timeout=120, env=env)
    assert result.returncode == 0, f"the stop script must handle a PAUSED row: {result.stderr}"
    assert marker.exists(), "the stop script never reached the compose command"
    assert "down" in marker.read_text(), marker.read_text()
    assert "Stopped FP-CONTROL-2" in result.stdout


def test_paused_refuses_capture_at_the_capture_entrypoint(tmp_path, monkeypatch):
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    paused = row(registry, SUCCESSOR)
    paused.update(status="PAUSED", t0_utc="2026-09-14T00:00:00Z",
                  cohort_id="FP-CONTROL-2-20260914T000000Z")
    paused["runtime_identity"]["source_commit"] = "0" * 40
    patched = tmp_path / "registry.json"
    patched.write_text(json.dumps(registry), encoding="utf-8")
    monkeypatch.setattr(lane, "COHORT_REGISTRY", patched)
    monkeypatch.setattr(capture, "COHORT_REGISTRY", patched)
    with pytest.raises(capture.InstanceSelectionError) as excinfo:
        capture.CaptureLoop(tmp_path / "lane", ["BTC/USDT"], role=SUCCESSOR)
    assert "PAUSED" in str(excinfo.value)


def test_evidence_records_carry_the_writing_role(tmp_path, monkeypatch):
    """Attribution must be written, not assumed by the consumer."""
    monkeypatch.setattr(capture, "COHORT_REGISTRY", REGISTRY_PATH.resolve())
    monkeypatch.setattr(lane, "COHORT_REGISTRY", REGISTRY_PATH.resolve())

    class StubMarket:
        TIMEFRAME_MS = {"1h": 3_600_000}

    loop = capture.CaptureLoop(tmp_path / "lane", ["BTC/USDT"], role=SUCCESSOR, market_module=StubMarket)
    loop.record_incident("probe", "role attribution")
    record = loop.ledgers["incident"].records()[-1]
    assert record.payload["identity"]["role"] == SUCCESSOR
    assert record.payload["identity"]["cohort_id"] is None


def test_preflight_refuses_evidence_written_by_another_role(tmp_path, monkeypatch):
    """Through preflight.run(), not a private helper, and for every ledger.

    The previous version called `_check_hashes_match_registry` directly, so it
    would have passed even if the real gate stopped invoking that check. This
    drives the public entry point and asserts the check's own verdict inside the
    produced report.
    """
    from fp import ledger as fp_ledger, preflight

    monkeypatch.setattr(capture, "COHORT_REGISTRY", REGISTRY_PATH.resolve())
    monkeypatch.setattr(lane, "COHORT_REGISTRY", REGISTRY_PATH.resolve())
    monkeypatch.setattr(capture, "assert_evidence_dir_is_declared", lambda *a, **k: None)

    def report_for(ledger_name: str, identity: dict) -> dict:
        evidence = tmp_path / ledger_name
        ledgers = fp_ledger.open_ledgers(evidence)
        ledgers[ledger_name].append({"candle_ts": 1_700_000_000_000, "identity": identity})
        return preflight.run(
            runtime=preflight.RuntimeContext(evidence_dir=evidence, role=SUCCESSOR)
        )

    def hash_check(report: dict) -> dict:
        return next(c for c in report["checks"] if "hashes match registry" in c["check"])

    foreign = {
        "runtime_id": "FP-CONTROL-1:fp-control-1", "run_id": "f" * 32, "role": CLOSED,
        "cohort_id": "FP-CONTROL-1-20260908T121513Z", "source_commit": "0" * 40,
        "strategy_sha256": "0" * 64,
    }
    # A foreign record in ANY ledger must be caught, not only in decisions.
    for ledger_name in ("decision", "input", "trade", "incident"):
        check = hash_check(report_for(ledger_name, foreign))
        assert check["result"] == "FAIL", (ledger_name, check)
        assert CLOSED in check["evidence"] or "role" in check["evidence"], (ledger_name, check)

    unstamped = hash_check(report_for("decision", {"run_id": "a" * 32}))
    assert unstamped["result"] == "FAIL", unstamped
    assert "no role" in unstamped["evidence"]


def test_preflight_compares_the_stamped_config_hash(tmp_path, monkeypatch):
    """A record written against some other config must not pass unnoticed."""
    from fp import ledger as fp_ledger, preflight

    monkeypatch.setattr(capture, "COHORT_REGISTRY", REGISTRY_PATH.resolve())
    monkeypatch.setattr(lane, "COHORT_REGISTRY", REGISTRY_PATH.resolve())
    monkeypatch.setattr(capture, "assert_evidence_dir_is_declared", lambda *a, **k: None)

    evidence = tmp_path / "evidence"
    ledgers = fp_ledger.open_ledgers(evidence)
    ledgers["decision"].append({
        "candle_ts": 1_700_000_000_000,
        "identity": {
            "runtime_id": "FP-CONTROL-2:fp-control-2", "run_id": "a" * 32, "role": SUCCESSOR,
            "cohort_id": None, "source_commit": "0" * 40,
            "strategy_sha256": capture.sha256_file(capture.STRATEGY_PATH),
            "config_sha256": "d" * 64,          # not the config on disk
        },
    })
    report = preflight.run(runtime=preflight.RuntimeContext(evidence_dir=evidence, role=SUCCESSOR))
    check = next(c for c in report["checks"] if "hashes match registry" in c["check"])
    assert check["result"] == "FAIL", check
    assert "config hash" in check["evidence"], check


def test_reconciliation_requires_role_on_every_record(tmp_path):
    """Attribution that is never compared proves nothing."""
    from fp import ledger as fp_ledger, reconcile

    evidence = tmp_path / "evidence"
    ledgers = fp_ledger.open_ledgers(evidence)
    ledgers["input"].append({
        "market_event_id": "BTC/USDT|1h|1",
        "identity": {"run_id": "a" * 32, "runtime_id": "x", "source_commit": "0" * 40},
    })
    report = reconcile.reconcile(evidence, expected_role=SUCCESSOR)
    attribution = [f for f in report["findings"] if f["check"] == "record_attribution"]
    assert attribution and attribution[0]["result"] == "FAIL", report["findings"]


@pytest.mark.parametrize("ledger_name", ["input", "decision", "trade", "incident"])
def test_reconciliation_rejects_a_foreign_role_in_any_ledger(tmp_path, ledger_name):
    """A foreign input or incident is as damaging as a foreign decision."""
    from fp import ledger as fp_ledger, reconcile

    evidence = tmp_path / ledger_name
    ledgers = fp_ledger.open_ledgers(evidence)
    ledgers[ledger_name].append({
        "market_event_id": "BTC/USDT|1h|1",
        "identity": {"run_id": "f" * 32, "runtime_id": "FP-CONTROL-1:fp-control-1",
                     "source_commit": "0" * 40, "role": CLOSED},
    })
    report = reconcile.reconcile(evidence, expected_role=SUCCESSOR)
    binding = [f for f in report["findings"] if f["check"] == "record_role_binding"]
    assert binding and binding[0]["result"] == "FAIL", (ledger_name, report["findings"])


def test_host_container_mapping_against_independently_written_paths():
    """Expectations written by hand: sabotaging the constant must fail this."""
    resolved = lane.resolve_lane(SUCCESSOR)
    assert resolved.host_instance_dir == SUCCESSOR_LANE_LITERAL
    assert resolved.host_evidence_dir == SUCCESSOR_LANE_LITERAL / "evidence"
    assert resolved.host_db_path == SUCCESSOR_LANE_LITERAL / "tradesv3.sqlite"
    assert resolved.host_log_path == SUCCESSOR_LANE_LITERAL / "logs" / "freqtrade.log"
    assert str(resolved.container_evidence_dir) == "/freqtrade/user_data/fp-control-2/evidence"
    assert lane.container_to_host("/freqtrade/user_data/fp-control-1/evidence") == \
        CLOSED_LANE_LITERAL / "evidence"


def test_a_status_less_candidate_row_is_not_eligible(registry, tmp_path, monkeypatch):
    """Fail closed on an unreadable status, not only on CLOSED."""
    doc = json.loads(json.dumps(registry))
    stranger = json.loads(json.dumps(row(doc, SUCCESSOR)))
    stranger["role"] = "FP-CANDIDATE-A"
    stranger["runtime_identity"]["candidate_family"] = "x"
    stranger.pop("status")
    doc["instances"].append(stranger)
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(admission, "COHORT_REGISTRY", path)
    assert admission.eligible_candidates() == []
    assert admission.identified_candidate() is None


def test_an_ancestor_bind_at_an_unrelated_target_is_rejected():
    """The repository root mounted at /workspace reaches every lane at once.

    Containment was checked in one direction only — "is the source inside
    user_data" — so a source that *contains* user_data was invisible.
    """
    rendered = rendered_overlay()
    rendered["services"]["some-future-sidecar"] = {
        "image": "busybox",
        "volumes": [{"type": "bind", "source": str(REPO_ROOT_LITERAL),
                     "target": "/workspace", "read_only": False}],
    }
    problems = check_fp_overlay.check(rendered, SUCCESSOR)
    assert problems, "a writable ancestor bind must be rejected"
    assert any("some-future-sidecar" in p for p in problems), problems


def test_a_local_driver_named_volume_backed_by_user_data_is_rejected():
    """A named volume with device= is a bind wearing a volume's clothes."""
    rendered = rendered_overlay()
    rendered.setdefault("volumes", {})["sneaky"] = {
        "driver": "local",
        "driver_opts": {"type": "none", "o": "bind", "device": str(CLOSED_LANE_LITERAL)},
    }
    rendered["services"]["some-future-sidecar"] = {
        "image": "busybox",
        "volumes": [{"type": "volume", "source": "sneaky",
                     "target": "/freqtrade/user_data/fp-control-1", "read_only": False}],
    }
    problems = check_fp_overlay.check(rendered, SUCCESSOR)
    assert problems, "a local-driver volume backed by the closed lane must be rejected"


def test_a_plain_named_volume_is_still_accepted():
    """Grafana's own storage must not be flagged, or the check becomes noise."""
    rendered = rendered_overlay()
    rendered.setdefault("volumes", {})["ordinary"] = {}
    rendered["services"]["some-future-sidecar"] = {
        "image": "busybox",
        "volumes": [{"type": "volume", "source": "ordinary", "target": "/data", "read_only": False}],
    }
    assert check_fp_overlay.check(rendered, SUCCESSOR) == []


def test_an_escaped_lane_root_is_refused_by_every_consumer(tmp_path, monkeypatch):
    """A lane root that resolves outside user_data owns nothing.

    Comparing the given path against the declared path made an escaping symlink
    agree with itself: both sides followed the same link and matched, so the
    rendered overlay passed and the launcher created directories outside
    user_data. Canonicality is now asked of the root itself.
    """
    escape = tmp_path / "elsewhere"
    escape.mkdir()
    link = lane.HOST_USER_DATA / "fp-control-2"
    assert not link.exists(), "the real lane must not exist during this test"
    link.symlink_to(escape, target_is_directory=True)
    try:
        escaped = lane.resolve_lane(SUCCESSOR)
        assert not escaped.root_is_canonical()
        assert not escaped.owns_host_path(escaped.host_instance_dir)
        with pytest.raises(lane.LaneError):
            escaped.assert_root_is_canonical()
        # the compose guard refuses the rendered graph outright
        problems = check_fp_overlay.check(rendered_overlay(), SUCCESSOR)
        assert problems and any("canonical" in p for p in problems), problems
        # and the launcher refuses before creating anything
        result = subprocess.run(["bash", "scripts/start_fp_control.sh", SUCCESSOR],
                                capture_output=True, text=True, timeout=180)
        assert result.returncode != 0, result.stdout
        assert "FP_LANE_FAIL" in result.stderr or "FP_OVERLAY_FAIL" in result.stderr, result.stderr
        assert not (escape / "logs").exists(), "the launcher created directories despite refusing"
        assert not (escape / "evidence").exists()
    finally:
        link.unlink()


def test_the_launcher_detects_runtime_config_drift(tmp_path):
    """Behavioural: a drifted config.json must stop the launcher.

    The previous proof read the script's source text, which would have passed a
    launcher that hashed the right file and then ignored the answer.
    """
    runtime_config = Path("freqtrade/user_data/config.json")
    original = runtime_config.read_bytes()
    drifted = json.loads(original)
    drifted["stake_amount"] = drifted["stake_amount"] + 1      # sizing drift
    try:
        runtime_config.write_text(json.dumps(drifted, indent=2) + "\n", encoding="utf-8")
        result = subprocess.run(["bash", "scripts/start_fp_control.sh", SUCCESSOR],
                                capture_output=True, text=True, timeout=180)
        assert result.returncode != 0, "a drifted runtime config must stop the launcher"
        assert "config_sha256" in result.stderr or "FP_IDENTITY_FAIL" in result.stderr, result.stderr
    finally:
        runtime_config.write_bytes(original)
    assert runtime_config.read_bytes() == original
