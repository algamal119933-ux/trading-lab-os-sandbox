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
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

import conftest

from fp import capture

REGISTRY_PATH = "research/fp/records/forward_paper_cohort_registry.json"
SCHEMA_PATH = "research/schema/forward_paper_cohort_registry.schema.json"
HISTORICAL = "FP-CONTROL-1"
SUCCESSOR = "FP-CONTROL-3"


@pytest.fixture(scope="module")
def registry(request) -> dict:
    """The committed registry, with the SUCCESSOR row stated as pre-T0.

    This file is about what the successor inherited from the cohort that closed
    — which is nothing — and every test here was written while the successor had
    not started. The helper winds back only the freeze's own seven values, and
    only for the successor: FP-CONTROL-1 is returned exactly as committed, so
    the historical assertions below still read the real closed row.
    """
    return conftest.pre_t0_registry(SUCCESSOR)


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


def _pre_t0_registry_file(tmp_path) -> Path:
    """A real registry file whose successor row is stated pre-T0."""
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(conftest.pre_t0_registry(SUCCESSOR), indent=2) + "\n",
                    encoding="utf-8")
    return path


def test_a_capture_identity_for_the_successor_carries_no_cohort(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "COHORT_REGISTRY", _pre_t0_registry_file(tmp_path))
    identity = capture.build_identity(tmp_path, role=SUCCESSOR)
    assert identity.cohort_id is None
    assert identity.bot_name == "fp-control-3"
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


def test_there_is_no_first_row_fallback(registry, tmp_path, monkeypatch, executable_registry_file):
    """Behavioural, not textual: an unknown role must raise, never return row 0."""
    monkeypatch.setattr(capture, "COHORT_REGISTRY", executable_registry_file)
    with pytest.raises(capture.InstanceSelectionError):
        capture.build_identity(tmp_path, role="FP-CONTROL-404")
    # And the successor's identity is the successor's, not whichever row is first.
    identity = capture.build_identity(tmp_path, role=SUCCESSOR)
    assert identity.role == SUCCESSOR
    assert identity.bot_name == "fp-control-3"
    assert identity.db_path == "/freqtrade/user_data/fp-control-3/tradesv3.sqlite"


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
    monkeypatch.setattr(capture, "COHORT_REGISTRY", _pre_t0_registry_file(tmp_path))
    loop = capture.CaptureLoop(tmp_path, ["BTC/USDT"], role=SUCCESSOR)
    assert loop.t0_ms is None
    assert loop.t0_relation(1_789_000_000_000) == "T0_NOT_FROZEN"


def test_the_committed_successor_is_pre_t0_or_a_lawfully_frozen_cohort():
    """The one claim here whose subject really is the committed file.

    It used to assert the successor is NOT_STARTED, which was true right up to
    the moment the Owner lawfully froze a T0 onto it — the state the whole of P2
    exists to reach. A test that fails when the project succeeds is testing the
    calendar. What is durable is that the committed row is in one of the two
    lawful states, that the flag agrees with it, and that a control is never
    promoted to a candidate by being started.
    """
    registry = conftest.committed_registry()
    successor = next(i for i in registry["instances"] if i["role"] == SUCCESSOR)
    frozen = successor["status"] == "RUNNING"
    closed = successor["status"] == "CLOSED"

    if frozen or closed:
        assert successor["t0_utc"] and successor["cohort_id"]
        assert successor["cohort_id"].startswith(SUCCESSOR + "-")
        assert successor["runtime_identity"]["source_commit"]
    else:
        assert successor["status"] == "NOT_STARTED"
        assert successor["t0_utc"] is None and successor["cohort_id"] is None
        assert successor["runtime_identity"]["source_commit"] is None
    if closed:
        # The third lawful state: the frozen cohort, closed. Its frozen identity
        # stays, it carries its closure and its outcome, and nothing runs.
        assert successor["closed_utc"] and successor["closure_reason"]
        assert successor["outcome"]["paper_trading_operational_capability"] in ("PROVEN", "NOT_PROVEN")
        assert successor["outcome"]["prospective_paper_edge"] == "NOT_EVALUATED"
    else:
        assert successor["closed_utc"] is None and successor["closure_reason"] is None
        assert "outcome" not in successor
    assert registry["fp_run_active"] is frozen

    # Neither state promotes a control, and neither admits a candidate.
    assert registry["paper_alpha_cohort"] == "NONE"
    assert registry["entry_state"] == "C"
    assert registry["real_money_authorized"] is False


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


# -- bypasses an earlier review found, and must stay closed ---------------


def test_a_caller_cannot_forge_a_cohort_id(tmp_path, monkeypatch):
    """build_identity used to accept cohort_id=, bot_name=, db_path=, log_path=.

    A caller could stamp a cohort the registry never froze — INVENTED-BEFORE-T0
    in a ledger is indistinguishable from a real one afterwards. The parameters
    are gone, not guarded.
    """
    monkeypatch.setattr(capture, "COHORT_REGISTRY", Path(REGISTRY_PATH).resolve())
    with pytest.raises(TypeError):
        capture.build_identity(tmp_path, role=SUCCESSOR, cohort_id="INVENTED-BEFORE-T0")
    for forbidden in ("bot_name", "db_path", "log_path"):
        with pytest.raises(TypeError):
            capture.build_identity(tmp_path, role=SUCCESSOR, **{forbidden: "/tmp/forged"})


def test_a_capture_loop_cannot_be_handed_a_forged_identity(tmp_path, monkeypatch):
    """CaptureLoop(identity=...) bypassed selection completely."""
    monkeypatch.setattr(capture, "COHORT_REGISTRY", Path(REGISTRY_PATH).resolve())
    with pytest.raises(TypeError):
        capture.CaptureLoop(tmp_path, ["BTC/USDT"], identity=object())


def test_a_capture_loop_has_no_default_role(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "COHORT_REGISTRY", Path(REGISTRY_PATH).resolve())
    with pytest.raises(capture.InstanceSelectionError):
        capture.CaptureLoop(tmp_path, ["BTC/USDT"])


def test_an_undeclared_evidence_lane_is_refused(tmp_path, registry):
    """Collision-freedom alone permits a third lane belonging to no instance."""
    with pytest.raises(capture.InstanceSelectionError) as excinfo:
        capture.assert_evidence_dir_is_declared(SUCCESSOR, tmp_path, registry)
    assert "declared" in str(excinfo.value)
    declared = next(i for i in registry["instances"] if i["role"] == SUCCESSOR)["runtime_identity"]["evidence_dir"]
    capture.assert_evidence_dir_is_declared(SUCCESSOR, Path(declared), registry)  # must not raise


def test_prefix_neighbours_are_not_treated_as_the_same_lane(registry):
    """`/x/fp-control-3-evil` shares a prefix with `/x/fp-control-3` and is a
    different lane; `/x/lane/nested` looks different and is the same lane."""
    assert capture._collides(Path("/x/lane"), Path("/x/lane/nested"))
    assert capture._collides(Path("/x/lane/nested"), Path("/x/lane"))
    assert not capture._collides(Path("/x/fp-control-3"), Path("/x/fp-control-3-evil"))


def test_a_malformed_t0_is_not_read_as_unfrozen(tmp_path, monkeypatch):
    """"Unreadable boundary" and "no boundary" must not collapse together."""
    broken = json.loads(Path(REGISTRY_PATH).read_text(encoding="utf-8"))
    successor = next(i for i in broken["instances"] if i["role"] == SUCCESSOR)
    successor["t0_utc"] = "not-a-timestamp"
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(broken), encoding="utf-8")
    monkeypatch.setattr(capture, "COHORT_REGISTRY", path)
    with pytest.raises(capture.InstanceSelectionError):
        capture._registry_t0_ms(SUCCESSOR)


def test_the_overlay_refuses_to_render_without_a_selection():
    """Unset variables used to render an unnamed lane with user_data writable."""
    overlay = Path("docker-compose.fp.yml").read_text(encoding="utf-8")
    for variable in ("FP_ROLE", "FP_INSTANCE_DIR", "FP_BOT_NAME"):
        assert f"${{{variable}:?" in overlay, f"{variable} must be required, not defaulted"


def test_the_overlay_guard_rejects_a_prefix_neighbour_lane():
    """Substring checking passed `fp-control-3-evil`; component checking must not."""
    import check_fp_overlay

    rendered = {
        "services": {
            "freqtrade": {
                "command": [
                    "trade",
                    "--logfile", "/freqtrade/user_data/fp-control-3-evil/logs/freqtrade.log",
                    "--db-url", "sqlite:////freqtrade/user_data/fp-control-3-evil/tradesv3.sqlite",
                    "--config", "/freqtrade/user_data/config.json",
                    "--strategy", "BaselineEmaRegimeV1",
                ],
            },
            "fp-capture": {
                "volumes": [
                    {"source": "./freqtrade/user_data/fp-control-3-evil",
                     "target": "/freqtrade/user_data/fp-control-3-evil", "read_only": False},
                ],
            },
        }
    }
    assert check_fp_overlay.check(rendered, "fp-control-3"), "a prefix-neighbour lane must be rejected"


def test_ci_selects_an_instance_before_rendering_the_overlay():
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "scripts/fp_instance.py FP-CONTROL-3" in workflow
    assert "An unselected FP overlay render must fail closed" in workflow
    # Once the cohort is CLOSED, CI must first prove the resolver refuses it.
    assert 'grep -q "is CLOSED" /tmp/fp-selection.err' in workflow


def test_preflight_refuses_an_unbound_runtime():
    """--evidence-dir without --role compared a runtime against every hashed row."""
    from fp import preflight

    assert preflight.main(["--evidence-dir", "/tmp"]) == 2
    assert preflight.main(["--role", HISTORICAL]) == 2       # CLOSED
    assert preflight.main(["--role", "FP-CONTROL-404"]) == 2  # unknown


def test_preflight_refuses_a_runtime_whose_lane_is_not_declared(tmp_path):
    """Behavioural: run() must reject an evidence directory the registry does not declare."""
    from fp import preflight

    (tmp_path / "paper_input_ledger.jsonl").write_text("", encoding="utf-8")
    with pytest.raises((ValueError, capture.InstanceSelectionError)):
        preflight.run(runtime=preflight.RuntimeContext(evidence_dir=tmp_path, role=SUCCESSOR))
    with pytest.raises((ValueError, capture.InstanceSelectionError)):
        preflight.run(runtime=preflight.RuntimeContext(evidence_dir=tmp_path))


def test_an_unknown_role_is_never_read_as_a_candidate(registry, tmp_path, monkeypatch):
    """Behavioural: a hashed row with an unrecognised role must not become a candidate."""
    from fp import admission

    doctored = json.loads(json.dumps(registry))
    stranger = json.loads(json.dumps(doctored["instances"][1]))
    stranger["role"] = "UNKNOWN-A"
    stranger["runtime_identity"]["candidate_family"] = "wrong-first"
    doctored["instances"].append(stranger)
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(doctored), encoding="utf-8")
    monkeypatch.setattr(admission, "COHORT_REGISTRY", path)
    assert admission.identified_candidate() is None
    assert admission.evaluate()["paper_admission"] == "BLOCKED"


def test_a_control_role_is_not_a_valid_candidate_in_the_admission_schema(request):
    """A mutated record naming a control as the candidate must fail validation."""
    import jsonschema

    schema = json.loads(
        (request.config.rootpath / "research/schema/paper_candidate_admission.schema.json").read_text(
            encoding="utf-8"
        )
    )
    record = json.loads(
        (request.config.rootpath / "research/fp/records/paper_candidate_admission.json").read_text(
            encoding="utf-8"
        )
    )
    validator = jsonschema.validators.validator_for(schema)(schema)
    assert list(validator.iter_errors(record)) == []
    for control in (HISTORICAL, SUCCESSOR):
        mutated = json.loads(json.dumps(record))
        mutated["candidate"]["role"] = control
        assert list(validator.iter_errors(mutated)), f"{control} must not validate as a candidate"


def test_the_activation_pack_carries_no_runnable_registry_write():
    """A14 wrote t0_utc and cohort_id straight into the FP-CONTROL-1 row.

    A banner is a warning; what matters is that the snippet is no longer a bash
    block anyone can lift out and run.
    """
    pack = Path("docs/fp-boot-1/FP_CONTROL_1_ACTIVATION_PACK.md").read_text(encoding="utf-8")
    assert "SUPERSEDED" in pack[:2000]
    a14 = pack[pack.index("### A14"):pack.index("### A15")]
    # A fence language is not an execution control: the program itself is gone.
    for runnable in ("python3 - <<", "reg.write_text", "json.dumps(r",
                     'inst["t0_utc"]', 'inst["cohort_id"]', '["fp_run_active"] = True',
                     "git commit -m", "```bash"):
        assert runnable not in a14, f"A14 still carries runnable registry-write material: {runnable!r}"
    assert "removed" in a14.lower()


def test_the_registry_schema_enforces_role_uniqueness_and_started_state(request, registry):
    import jsonschema

    schema = json.loads(
        (request.config.rootpath / SCHEMA_PATH).read_text(encoding="utf-8")
    )
    validator = jsonschema.validators.validator_for(schema)(schema)

    duplicated = json.loads(json.dumps(registry))
    duplicated["instances"].append(json.loads(json.dumps(duplicated["instances"][1])))
    assert list(validator.iter_errors(duplicated)), "a duplicated role must not validate"

    started_with_nulls = json.loads(json.dumps(registry))
    successor = next(i for i in started_with_nulls["instances"] if i["role"] == SUCCESSOR)
    successor["status"] = "RUNNING"
    started_with_nulls["fp_run_active"] = True
    assert list(validator.iter_errors(started_with_nulls)), (
        "a started row with null t0/cohort/source must not validate"
    )


def test_the_overlay_guard_requires_the_declared_paths_and_role(executable_registry_file):
    import check_fp_overlay

    # Selected by ROLE, never by index: the registry gained a third row when
    # FP-CONTROL-2 closed, and instances[1] silently became the closed cohort.
    registry_identity = next(
        r for r in json.loads(Path(REGISTRY_PATH).read_text(encoding="utf-8"))["instances"]
        if r["role"] == SUCCESSOR
    )[
        "runtime_identity"
    ]
    good = {
        "services": {
            "freqtrade": {
                "command": [
                    "trade", "--logfile", registry_identity["log_path"],
                    "--db-url", f"sqlite:///{registry_identity['db_path']}",
                    "--config", "/freqtrade/user_data/config.json",
                    "--strategy", "BaselineEmaRegimeV1",
                ],
                "environment": {"FREQTRADE__BOT_NAME": registry_identity["bot_name"]},
                "volumes": [
                    {"source": "./freqtrade/user_data", "target": "/freqtrade/user_data", "read_only": True},
                    {"source": "./freqtrade/user_data/fp-control-3",
                     "target": "/freqtrade/user_data/fp-control-3", "read_only": False},
                ],
            },
            "fp-capture": {
                "command": ["python", "/app/research/fp/capture.py", "--role=FP-CONTROL-3",
                            f"--evidence-dir={registry_identity['evidence_dir']}"],
                "volumes": [
                    {"source": "./freqtrade/user_data/fp-control-3",
                     "target": "/freqtrade/user_data/fp-control-3", "read_only": False},
                ],
            },
        }
    }
    assert check_fp_overlay.check(good, SUCCESSOR) == []

    # the closed role is refused outright
    assert check_fp_overlay.check(good, HISTORICAL)

    # a writable whole-user_data mount is refused
    wide = json.loads(json.dumps(good))
    wide["services"]["freqtrade"]["volumes"][0]["read_only"] = False
    assert check_fp_overlay.check(wide, SUCCESSOR)

    # a capture service that does not name the role is refused
    unnamed = json.loads(json.dumps(good))
    unnamed["services"]["fp-capture"]["command"] = ["python", "/app/research/fp/capture.py"]
    assert check_fp_overlay.check(unnamed, SUCCESSOR)

    # a bot name that is not the declared one is refused
    wrong_bot = json.loads(json.dumps(good))
    wrong_bot["services"]["freqtrade"]["environment"]["FREQTRADE__BOT_NAME"] = "fp-control-1"
    assert check_fp_overlay.check(wrong_bot, SUCCESSOR)


def test_the_resolver_quotes_every_value_it_emits(tmp_path):
    """The launchers eval this output; an unquoted registry string would be code."""
    import subprocess

    # Run in a disposable copy whose registry holds the role executable
    # (conftest ``executable_registry``): the resolver rightly refuses the
    # committed, closed row, which is proved separately below.
    repo = conftest.executable_repo_copy(tmp_path / "repo", SUCCESSOR)
    result = subprocess.run(
        [sys.executable, "scripts/fp_instance.py", SUCCESSOR],
        capture_output=True, text=True, timeout=60, cwd=repo,
    )
    assert result.returncode == 0
    emitted = dict(line.split("=", 1) for line in result.stdout.strip().splitlines())
    assert set(emitted) == {
        "FP_ROLE", "FP_INSTANCE_DIR", "FP_BOT_NAME", "FP_DB_PATH", "FP_LOG_PATH", "FP_EVIDENCE_DIR",
        "FP_HOST_INSTANCE_DIR", "FP_HOST_EVIDENCE_DIR", "FP_T0",
    }
    for key, value in emitted.items():
        assert value == shlex.quote(shlex.split(value)[0] if value else ""), f"{key} is not shell-quoted"


def test_reconciliation_requires_every_identity_field_it_claims():
    from fp import reconcile

    # Behavioural, and role is now part of the same contract — see
    # tests/test_fp_lane_adversarial.py::test_reconciliation_requires_role_on_every_record
    source = Path("research/fp/reconcile.py").read_text(encoding="utf-8")
    assert '"run_id", "runtime_id", "source_commit", "role"' in source
    assert hasattr(reconcile, "reconcile")


# -- a CLOSED cohort cannot be restarted, proved against the committed file ----


def _committed_closed_roles() -> list[str]:
    return [r["role"] for r in conftest.committed_registry()["instances"] if r.get("status") == "CLOSED"]


@pytest.mark.parametrize("role", _committed_closed_roles())
def test_a_committed_closed_cohort_is_refused_by_selection(role):
    """Every CLOSED row in the committed registry is refused — no fixture involved."""
    with pytest.raises(capture.InstanceSelectionError) as excinfo:
        capture.select_instance(role, conftest.committed_registry())
    assert "CLOSED" in str(excinfo.value)


@pytest.mark.parametrize("role", _committed_closed_roles())
def test_a_committed_closed_cohort_cannot_be_resolved_for_a_launch(role):
    """The resolver the launcher evals refuses a CLOSED row, so nothing can start it."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "scripts/fp_instance.py", role],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0, result.stdout
    assert "CLOSED" in result.stderr, result.stderr
    assert "FP_ROLE=" not in result.stdout


@pytest.mark.parametrize("role", _committed_closed_roles())
def test_a_committed_closed_cohort_is_refused_by_the_overlay_guard(role):
    import check_fp_overlay

    problems = check_fp_overlay.check({"services": {}}, role)
    assert problems and "CLOSED" in problems[0], problems

