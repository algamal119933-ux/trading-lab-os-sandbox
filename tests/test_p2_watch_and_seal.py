"""The continuity watch, the qualification seal, and the reconciliation finding.

Three mechanisms that only earn their place by refusing things.

``fp_watch`` exists for the failures that present identically from outside: a
wedged loop whose process is alive and whose container is up, a stack that
stopped and nobody restarted, and a chain that broke between two reconciliation
runs. All three look like a lane that is simply not growing, and all three are
only visible by comparing the lane against the clock. It must also never write:
a watchdog that repairs what it finds destroys the evidence that it happened.

``seal_pre_t0_qualification`` produces the value the Owner's authorization will
name, so a certificate sealed over a lane that is not a pre-T0 lane would let a
freeze be authorized against the wrong evidence.

``registry_source_commit_equivalence`` is the reconciliation finding that closes
P2's declared-versus-stamped gap. Its whole point is that a declaration compared
to nothing is not a check.
"""

from __future__ import annotations

import copy
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import conftest

import fp_watch
import seal_pre_t0_qualification as sealer
from fp import lane as fp_lane
from fp import ledger as fp_ledger
from fp import reconcile as fp_reconcile
from fp import registry_law as fp_law
from fp import semantic_identity as fp_semantic

REGISTRY_PATH = Path("research/fp/records/forward_paper_cohort_registry.json")
ROLE = "FP-CONTROL-2"
TEST_LANE = "fp-testlane-s2watch"
HOUR_MS = 3_600_000
COMMIT = "a" * 40


def _iso(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def lane_env(tmp_path, monkeypatch):
    # A pre-T0 row, asked for by name. These tests drive the seal and the
    # watch, both of which require a row that has started nothing; inheriting
    # that state from whatever is committed is what broke them the first time
    # a lawful T0 was frozen.
    registry = copy.deepcopy(conftest.pre_t0_registry(ROLE))
    row = next(item for item in registry["instances"] if item["role"] == ROLE)
    for field in ("db_path", "log_path", "evidence_dir"):
        row["runtime_identity"][field] = (
            row["runtime_identity"][field].replace("/fp-control-2/", f"/{TEST_LANE}/")
        )
    registry_file = tmp_path / "registry.json"
    registry_file.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(fp_lane, "COHORT_REGISTRY", registry_file)
    monkeypatch.setattr(fp_law, "COHORT_REGISTRY", registry_file)

    root = fp_lane.HOST_USER_DATA / TEST_LANE
    if root.exists():
        shutil.rmtree(root)
    evidence = root / "evidence"
    evidence.mkdir(parents=True)
    try:
        yield registry, root, evidence
    finally:
        if root.exists():
            shutil.rmtree(root)


def stamp(cohort_id=None, commit=COMMIT) -> dict:
    return {
        "runtime_id": f"{ROLE}:fp-control-2",
        "run_id": "run-0",
        "role": ROLE,
        "cohort_id": cohort_id,
        "restart_counter": 0,
        "source_commit": commit,
        "strategy_sha256": "c" * 64,
        "config_sha256": "d" * 64,
        "capture_engine_version": "FP_CAPTURE_LOOP_V1",
    }


def write_lane(evidence: Path, *, age_hours: float = 0.0, relation="T0_NOT_FROZEN",
               cohort_id=None, commit=COMMIT, snapshot=True):
    now = datetime.now(timezone.utc)
    last_close = now - timedelta(hours=age_hours)
    candle_ts = int(last_close.timestamp() * 1000) - HOUR_MS
    ledgers = fp_ledger.open_ledgers(evidence, create=True)
    identity = stamp(cohort_id, commit)
    ledgers["incident"].append({
        "category": "run_started", "detail": "start", "observed_utc": _iso(now),
        "full_identity": {**identity, "restart_counter": 0}, "identity": identity,
    })
    ledgers["input"].append({
        "pair": "BTC/USDT", "timeframe": "1h", "candle_ts": candle_ts,
        "market_event_id": f"BTC/USDT|1h|{candle_ts}", "identity": identity,
    })
    ledgers["decision"].append({
        "pair": "BTC/USDT", "timeframe": "1h", "candle_ts": candle_ts,
        "market_event_id": f"BTC/USDT|1h|{candle_ts}", "intended_action": "hold",
        "signal_state": "flat", "t0_relation": relation, "bar_class": "LIVE",
        "identity": identity,
    })
    if snapshot:
        (evidence / "capture_runtime.json").write_text(
            json.dumps({"written_utc": _iso(last_close)}) + "\n", encoding="utf-8"
        )
    return ledgers


def observation(report: dict, name: str) -> dict:
    return next(o for o in report["observations"] if o["observation"] == name)


def as_running(registry: dict, t0: str = "2026-09-01T00:00:00Z") -> dict:
    registry = copy.deepcopy(registry)
    row = next(item for item in registry["instances"] if item["role"] == ROLE)
    row["status"] = "RUNNING"
    row["t0_utc"] = t0
    row["cohort_id"] = fp_law.cohort_id_for(ROLE, t0)
    row["runtime_identity"]["source_commit"] = "b" * 40
    row["change_log"] = [{"utc": t0, "class": "O", "description": "T0 frozen."}]
    registry["fp_run_active"] = True
    return registry


# -- the watch -------------------------------------------------------------


def test_a_running_lane_that_stopped_advancing_is_stalled(lane_env):
    """Alive, container up, nothing moving — the failure nothing else notices."""
    registry, _, evidence = lane_env
    write_lane(evidence, age_hours=6)
    report = fp_watch.watch(ROLE, registry=as_running(registry))
    assert report["watch"] == fp_watch.STALLED
    assert observation(report, "cycle heartbeat")["result"] == fp_watch.STALLED
    assert observation(report, "decision progress")["result"] == fp_watch.STALLED


def test_a_running_lane_that_is_advancing_is_healthy(lane_env):
    registry, _, evidence = lane_env
    write_lane(evidence, age_hours=0.2)
    report = fp_watch.watch(ROLE, registry=as_running(registry))
    assert observation(report, "cycle heartbeat")["result"] == fp_watch.OK
    assert observation(report, "decision progress")["result"] == fp_watch.OK


def test_a_stopped_lane_that_is_not_running_is_not_a_fault(lane_env):
    """A retained qualification lane stopped because it finished.

    Reporting that as a fault every day is how a real stall stops being noticed.
    """
    registry, _, evidence = lane_env
    write_lane(evidence, age_hours=48)
    report = fp_watch.watch(ROLE, registry=registry)
    assert report["watch"] == fp_watch.OK
    assert "no advance is expected" in observation(report, "cycle heartbeat")["detail"]


def test_a_running_row_with_no_writer_is_reported(lane_env):
    """It went down and nobody restarted it: no crash to notice, no alert to fire."""
    registry, _, evidence = lane_env
    write_lane(evidence, age_hours=0.1)
    report = fp_watch.watch(ROLE, registry=as_running(registry))
    assert observation(report, "writer present")["result"] == fp_watch.STALLED
    assert "stopped and nothing" in observation(report, "writer present")["detail"]


def test_silent_chain_corruption_between_reconciliations_is_broken(lane_env):
    registry, _, evidence = lane_env
    write_lane(evidence, age_hours=0.1)
    path = evidence / "paper_decision_ledger.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["payload"]["intended_action"] = "enter_long"
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    report = fp_watch.watch(ROLE, registry=as_running(registry))
    assert report["watch"] == fp_watch.BROKEN
    assert observation(report, "chain integrity")["result"] == fp_watch.BROKEN


def test_the_watch_never_writes_into_the_lane(lane_env):
    """Repairing a lane destroys the evidence of the fault."""
    registry, root, evidence = lane_env
    write_lane(evidence, age_hours=6)
    before = {p: p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}
    fp_watch.watch(ROLE, registry=as_running(registry))
    after = {p: p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}
    assert before == after
    report = fp_watch.watch(ROLE, registry=as_running(registry))
    assert report["action_taken"].startswith("NONE")


def test_an_unlawful_registry_is_reported_as_broken(lane_env):
    registry, _, evidence = lane_env
    write_lane(evidence, age_hours=0.1)
    unlawful = copy.deepcopy(registry)
    unlawful["fp_run_active"] = True
    report = fp_watch.watch(ROLE, registry=unlawful)
    assert observation(report, "registry law")["result"] == fp_watch.BROKEN


# -- the reconciliation finding --------------------------------------------


@dataclass
class FakeRecord:
    seq: int
    payload: dict


def finding(live, decisions, role, stamped):
    return fp_reconcile._registry_source_commit_equivalence(live, decisions, role, stamped)


def _records(relation="T0_NOT_FROZEN", commit=COMMIT, cohort=None):
    identity = stamp(cohort, commit)
    live = [FakeRecord(1, {"identity": identity})]
    decisions = [FakeRecord(1, {"identity": identity, "t0_relation": relation})]
    return live, decisions


def test_a_not_started_row_has_no_declaration_to_contradict(lane_env):
    """L1 qualification: nothing is declared, and the records agree there is no T0."""
    live, decisions = _records()
    result = finding(live, decisions, ROLE, {COMMIT})
    assert result.result == fp_reconcile.PASS
    assert "NOT_STARTED" in result.detail


def test_a_not_started_row_whose_records_claim_a_boundary_fails(lane_env):
    """A t0_relation the registry cannot account for came from somewhere else."""
    live, decisions = _records(relation="POST_T0")
    result = finding(live, decisions, ROLE, {COMMIT})
    assert result.result == fp_reconcile.FAIL
    assert "did not come from the registry" in result.detail


def test_a_started_row_with_no_declared_commit_fails(lane_env, monkeypatch):
    registry = as_running(lane_env[0])
    next(r for r in registry["instances"] if r["role"] == ROLE)["runtime_identity"]["source_commit"] = None
    monkeypatch.setattr(fp_lane, "read_identity_text", lambda path: json.dumps(registry))
    live, decisions = _records(relation="POST_T0")
    result = finding(live, decisions, ROLE, {COMMIT})
    assert result.result == fp_reconcile.FAIL
    assert "must" in result.detail


def test_a_declared_commit_equivalent_to_the_stamped_one_passes(lane_env, monkeypatch):
    registry = as_running(lane_env[0])
    monkeypatch.setattr(fp_lane, "read_identity_text", lambda path: json.dumps(registry))
    monkeypatch.setattr(fp_reconcile.fp_semantic, "compare",
                        lambda a, b, role, **kw: {"result": fp_semantic.EQUIVALENT,
                                                  "detail": "identical", "differences": []})
    live, decisions = _records(relation="POST_T0")
    result = finding(live, decisions, ROLE, {COMMIT})
    assert result.result == fp_reconcile.PASS


def test_a_declared_commit_that_runs_a_different_system_fails(lane_env, monkeypatch):
    registry = as_running(lane_env[0])
    monkeypatch.setattr(fp_lane, "read_identity_text", lambda path: json.dumps(registry))
    monkeypatch.setattr(fp_reconcile.fp_semantic, "compare",
                        lambda a, b, role, **kw: {"result": fp_semantic.DIFFERENT,
                                                  "detail": "strategy moved",
                                                  "differences": [{}]})
    live, decisions = _records(relation="POST_T0")
    result = finding(live, decisions, ROLE, {COMMIT})
    assert result.result == fp_reconcile.FAIL
    assert "do not run the same system" in result.detail


def test_an_uncomparable_pair_is_unproven_not_a_pass(lane_env, monkeypatch):
    registry = as_running(lane_env[0])
    monkeypatch.setattr(fp_lane, "read_identity_text", lambda path: json.dumps(registry))
    monkeypatch.setattr(fp_reconcile.fp_semantic, "compare",
                        lambda a, b, role, **kw: {"result": fp_semantic.UNPROVEN,
                                                  "detail": "git unavailable",
                                                  "differences": []})
    live, decisions = _records(relation="POST_T0")
    result = finding(live, decisions, ROLE, {COMMIT})
    assert result.result == fp_reconcile.UNPROVEN


def test_two_stamped_commits_cannot_be_compared(lane_env):
    live, decisions = _records()
    result = finding(live, decisions, ROLE, {COMMIT, "f" * 40})
    assert result.result == fp_reconcile.UNPROVEN


def test_a_role_the_registry_does_not_declare_fails(lane_env):
    live, decisions = _records()
    result = finding(live, decisions, "FP-CANDIDATE-A", {COMMIT})
    assert result.result == fp_reconcile.FAIL


def test_the_finding_appears_in_a_real_reconciliation(lane_env):
    _, _, evidence = lane_env
    write_lane(evidence)
    report = fp_reconcile.reconcile(evidence, expected_role=ROLE, expected_source_commit=COMMIT)
    names = [f["check"] for f in report["findings"]]
    assert "registry_source_commit_equivalence" in names


# -- the qualification seal ------------------------------------------------


def _seal(evidence, monkeypatch, *, commit=COMMIT, **kwargs):
    monkeypatch.setattr(sealer, "_require_clean_tree", lambda: commit)
    return sealer.seal(
        ROLE, evidence,
        image_digest=kwargs.pop("image_digest", "sha256:" + "e" * 64),
        python_version=kwargs.pop("python_version", "3.14.6"),
        **kwargs,
    )


def test_sealing_refuses_a_malformed_image_digest(lane_env, monkeypatch):
    _, _, evidence = lane_env
    with pytest.raises(sealer.SealError, match="not a sha256 digest"):
        _seal(evidence, monkeypatch, image_digest="latest")


def test_sealing_refuses_without_an_observed_python_version(lane_env, monkeypatch):
    _, _, evidence = lane_env
    with pytest.raises(sealer.SealError, match="python-version"):
        _seal(evidence, monkeypatch, python_version="")


def test_sealing_refuses_a_started_row(lane_env, monkeypatch):
    """A started row's evidence is prospective evidence, never qualification."""
    registry, _, evidence = lane_env
    running = as_running(registry)
    monkeypatch.setattr(sealer.fp_law, "load_registry", lambda path=None: running)
    with pytest.raises(sealer.SealError, match="not NOT_STARTED"):
        _seal(evidence, monkeypatch)


def test_sealing_refuses_a_lane_the_role_does_not_declare(lane_env, monkeypatch, tmp_path):
    _, _, _ = lane_env
    with pytest.raises(sealer.SealError, match="not the evidence directory"):
        _seal(tmp_path / "elsewhere", monkeypatch)


def test_sealing_refuses_a_dirty_tree(lane_env, monkeypatch):
    """Mq must describe what ran; a dirty tree makes the commit a false statement."""
    _, _, evidence = lane_env

    def dirty(args):
        if args[:1] == ["status"]:
            return " M research/fp/capture.py"
        return COMMIT

    monkeypatch.setattr(sealer, "_git", dirty)
    with pytest.raises(sealer.SealError, match="differ from HEAD"):
        sealer.seal(ROLE, evidence, image_digest="sha256:" + "e" * 64, python_version="3.14.6")


def test_a_certificate_is_never_written_inside_a_lane(lane_env):
    _, root, evidence = lane_env
    with pytest.raises(sealer.SealError, match="is not written into it"):
        sealer.write_certificate({"certificate_version": "x"}, evidence / "certificate.json")


def test_a_certificate_hashes_to_the_value_the_owner_will_name(tmp_path):
    certificate = {"certificate_version": sealer.CERTIFICATE_VERSION, "role": ROLE}
    path, digest = sealer.write_certificate(certificate, tmp_path / "certificate.json")
    import hashlib
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(digest) == 64


# -- the seal must be able to succeed, not only to refuse -------------------
#
# Every seal test above proves a refusal, and that is exactly the gap that hid
# the freeze_t0 ordering defect S2 recorded: a tool driven only into its
# refusals is never shown to reach its output at all. It hid one here too.
# `seal` built its own preflight RuntimeContext with no observability endpoints
# and no market route, so 'real market-data ingestion works', 'monitoring is
# alive' and 'clock/timestamp handling is within tolerance' answered UNPROVEN —
# which blocks exactly as FAIL does — and no certificate could ever be produced.
# Observed on a live L1 lane at 9ba714fd whose own gates were green: preflight
# 16/16 PASS and reconciliation 14/14 PASS by hand, and
#
#   QUALIFICATION_SEAL_REFUSED: preflight is BLOCKED; not PASS:
#   ['real market-data ingestion works', 'monitoring is alive',
#    'clock/timestamp handling is within tolerance']
#
# The refusal named three checks and not the one thing the operator had to do.


ATTACHED = dict(
    freqtrade_url="http://127.0.0.1:8080",
    exporter_url="http://127.0.0.1:9108/metrics",
    prometheus_url="http://127.0.0.1:9090",
    api_user="qualification-api-user-never-recorded",
    api_password="qualification-api-password-never-recorded",
    check_market_route=True,
)


def _attached(**overrides) -> sealer.fp_preflight.RuntimeContext:
    return sealer.fp_preflight.RuntimeContext(**{**ATTACHED, **overrides})


def _pass_reconcile(monkeypatch):
    """The synthetic lane cannot satisfy event_time_replay, which runs first.

    The wiring refusals below are about the runtime context, so reconciliation
    is stubbed past rather than satisfied; its own refusals are proven by
    tests/test_p2_reconciliation_version.py and by the live S3 run.
    """
    monkeypatch.setattr(sealer.fp_reconcile, "reconcile", lambda *a, **k: {
        "reconciliation": fp_reconcile.PASS,
        "counts": {"input": 1, "decision": 1, "trade": 0, "incident": 1},
        "ledger_tips": {"input": "a" * 64},
        "daily_pack_digest": "b" * 64,
        "failing_checks": [],
    })


def _green_gates(monkeypatch, evidence):
    """Stub the two gate reports so seal's own assembly is what is under test.

    Reproducing a sixteen-check runtime-attached preflight in-process would mean
    reimplementing the runtime, and the real one is exercised against the live
    lane during S3. What is asserted here is the part that was broken: that seal
    wires the context it was given, demands PASS from both gates, and assembles
    a certificate at all.
    """
    report = {
        "preflight": fp_reconcile.PASS,
        "checks": [{"check": f"check {i}", "result": fp_reconcile.PASS} for i in range(16)],
    }
    seen: dict = {}

    def fake_preflight(evidence_dir=None, runtime=None):
        seen["runtime"] = runtime
        return report

    monkeypatch.setattr(sealer.fp_preflight, "run", fake_preflight)
    _pass_reconcile(monkeypatch)
    monkeypatch.setattr(sealer.fp_semantic, "semantic_identity",
                        lambda commit, role: type("I", (), {"digest": "c" * 64,
                                                            "runtime_tree": {"x": "y"}})())
    return seen


def test_sealing_refuses_a_runtime_with_no_market_route(lane_env, monkeypatch):
    _, _, evidence = lane_env
    write_lane(evidence)
    _pass_reconcile(monkeypatch)
    with pytest.raises(sealer.SealError, match="check-market-route is required"):
        _seal(evidence, monkeypatch, runtime=_attached(check_market_route=False))


def test_sealing_refuses_a_runtime_with_no_monitoring_endpoint(lane_env, monkeypatch):
    _, _, evidence = lane_env
    write_lane(evidence)
    _pass_reconcile(monkeypatch)
    with pytest.raises(sealer.SealError, match="exporter-url or --freqtrade-url is required"):
        _seal(evidence, monkeypatch,
              runtime=_attached(exporter_url=None, freqtrade_url=None))


def test_sealing_refuses_an_endpointless_runtime_by_default(lane_env, monkeypatch):
    """The old behaviour, now a refusal that names the wiring."""
    _, _, evidence = lane_env
    write_lane(evidence)
    _pass_reconcile(monkeypatch)
    with pytest.raises(sealer.SealError, match="check-market-route is required"):
        _seal(evidence, monkeypatch, runtime=None)


def test_the_seal_owns_the_lane_the_gates_run_over(lane_env, monkeypatch, tmp_path):
    """A caller supplies endpoints; it never redirects the gates at another lane."""
    _, _, evidence = lane_env
    write_lane(evidence)
    seen = _green_gates(monkeypatch, evidence)
    elsewhere = tmp_path / "someone-elses-lane"
    elsewhere.mkdir()
    _seal(evidence, monkeypatch,
          runtime=_attached(evidence_dir=elsewhere, role="FP-CONTROL-1"))
    assert Path(seen["runtime"].evidence_dir) == Path(evidence)
    assert seen["runtime"].role == ROLE
    # and the endpoints the caller did supply survived
    assert seen["runtime"].exporter_url == ATTACHED["exporter_url"]
    assert seen["runtime"].check_market_route is True


def test_a_fully_attached_seal_produces_a_certificate(lane_env, monkeypatch):
    _, _, evidence = lane_env
    write_lane(evidence)
    _green_gates(monkeypatch, evidence)
    certificate = _seal(evidence, monkeypatch, runtime=_attached())

    assert certificate["certificate_version"] == sealer.CERTIFICATE_VERSION
    assert certificate["role"] == ROLE
    assert certificate["qualification_commit"] == COMMIT
    assert certificate["qualification_result"]["preflight"] == "PASS"
    assert certificate["qualification_result"]["preflight_checks_passed"] == 16
    assert certificate["qualification_result"]["preflight_checks_total"] == 16
    assert certificate["qualification_result"]["reconciliation"] == "PASS"
    assert certificate["t0_relation_of_every_record"] == "T0_NOT_FROZEN"
    assert certificate["prospective_evidence"] == "NONE"
    assert certificate["real_money_authorized"] is False

    # The nine pre-T0 properties, and never a lifecycle one.
    from fp import capability as fp_capability

    evidenced = certificate["qualification_result"]["properties_evidenced"]
    assert sorted(evidenced) == sorted(fp_capability.PRE_T0_QUALIFIABLE)
    assert not set(evidenced) & set(fp_capability.POST_T0_LIFECYCLE)

    # What the sixteen checks were answered against, so "PASS 16/16" can be
    # told apart from "PASS 16/16 with three checks excused".
    attached = certificate["qualification_result"]["runtime_attached"]
    assert attached["market_route_probed"] is True
    assert attached["exporter_url"] == ATTACHED["exporter_url"]
    assert attached["prometheus_url"] == ATTACHED["prometheus_url"]
    assert attached["freqtrade_url"] == ATTACHED["freqtrade_url"]


def test_a_certificate_records_no_credential(lane_env, monkeypatch):
    """The certificate is published as a digest and read by later reviewers."""
    _, _, evidence = lane_env
    write_lane(evidence)
    _green_gates(monkeypatch, evidence)
    certificate = _seal(evidence, monkeypatch, runtime=_attached())
    text = json.dumps(certificate)
    assert ATTACHED["api_password"] not in text
    assert ATTACHED["api_user"] not in text

    # Keys, not substrings: a bare substring search for "user" matches
    # "user_data" in every lane path in the record, which is how a credential
    # check ends up failing on a path and proving nothing about credentials.
    def keys(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from keys(value)
        elif isinstance(node, list):
            for item in node:
                yield from keys(item)

    for key in keys(certificate):
        assert not any(word in key.lower()
                       for word in ("password", "secret", "token", "credential", "api_user"))
