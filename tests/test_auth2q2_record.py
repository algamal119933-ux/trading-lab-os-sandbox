"""The readiness record (research/auth2q2/record.py): INFRA_READINESS for RT-0 to RT-11 at one named commit.

Offline: the evidence is built here the way the Actions API reports it (runs, jobs, steps, and the records the gate
and verdict jobs publish as annotations), and every way a readiness run can fall short of its plan is shown to
turn PASS into FAIL with the reason named. PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
for extra in (REPO / "research", REPO / ".github" / "gates"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import auth2q2_readiness as RG  # noqa: E402
from auth2q2 import harness as H  # noqa: E402
from auth2q2 import plan as PL  # noqa: E402
from auth2q2 import record as R  # noqa: E402
from auth2q2 import snapshot as SN  # noqa: E402

OP = RG.OP
COMMIT = "c" * 40
SLUG = f"{OP.OWNER_LOGIN}/trading-lab-os-sandbox"
OWNER = {"login": OP.OWNER_LOGIN, "id": OP.OWNER_ID}
ADDRESS = "sha256:" + "a" * 64
CI_ID = 9000
RUN_IDS = {t: 1000 + i for i, t in enumerate(PL.RUN_TESTS)}


@pytest.fixture(autouse=True)
def _outside_actions(monkeypatch):
    """The CLIs stamp GitHub Actions' run identity into their records; in CI those variables belong to the CI
    run, not to the fixtures, so every test here starts without them and sets what it needs."""
    for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "GITHUB_EVENT_PATH"):
        monkeypatch.delenv(k, raising=False)


def notes(title: str, obj) -> list[dict]:
    body = json.dumps(obj, sort_keys=True).encode()
    return [{"title": title, "message": line.split("::", 2)[2]}
            for line in OP.annotation_lines(title, body).splitlines()]


def gate_rec(test: str, run_id: int, /, **kw) -> dict:
    rec = {"schema": RG.GATE_SCHEMA, "program": SN.PROGRAM_ID, "decision": "DISPATCH", "test": test,
           "repository": SLUG, "workflow": PL.workflow_of(test), "run_id": run_id, "run_attempt": 1, "sha": COMMIT,
           "main_sha": COMMIT, "reasons": [], "checked_utc": "2026-10-20T10:00:00Z",
           "ledger": {"minutes": 40, "total_if_admitted": 40 + PL.planned_max(test) + PL.NEXT_GATE_RESERVE},
           "reserve": {"remaining": 1500, "a_m": 1600, "r_m": 500},
           "release": {"address": ADDRESS} if test in PL.NEEDS_SNAPSHOT else None}
    rec.update(kw)
    return rec


def verdict_rec(test: str, job: str, run_id: int, /, **kw) -> dict:
    rec = {"schema": H.RESULT_SCHEMA, "program": SN.PROGRAM_ID, "test": test, "job": job, "result": "PASS",
           "checks": {"everything_held": True}, "problems": [], "measurements": {}, "run_id": str(run_id),
           "run_attempt": "1", "sha": COMMIT, "created_utc": "2026-10-20T10:05:00Z"}
    if test == "RT-1":
        rec["measurements"] = {"address": ADDRESS, "tar_sha256": "b" * 64, "release": {"tag": "t", "release_id": 5}}
    rec.update(kw)
    return rec


MINUTES = {"Cold preparation": 12, "Snapshot release (contents: write)": 3, "RT-4 cold restore and D0 data path": 9,
           "RT-11 engine data path": 14, "RT-10 probe": 3}


def job(jid: int, name: str, *, conclusion="success", minutes=1, ran=True, annotations=None) -> dict:
    if not ran:
        return {"id": jid, "name": name, "run_attempt": 1, "status": "completed", "conclusion": "skipped",
                "started_at": "2026-10-20T10:00:00Z", "completed_at": "2026-10-20T10:00:00Z", "runner_id": None,
                "runner_name": None, "steps": []}
    return {"id": jid, "name": name, "run_attempt": 1, "status": "completed", "conclusion": conclusion,
            "started_at": "2026-10-20T10:00:00Z", "completed_at": f"2026-10-20T10:{minutes - 1:02d}:30Z",
            "runner_id": 7, "runner_name": "GitHub Actions 7",
            "steps": [{"name": "Set up job", "number": 1, "status": "completed", "conclusion": "success",
                       "started_at": "2026-10-20T10:00:01Z", "completed_at": "2026-10-20T10:00:02Z"}],
            "annotations": annotations or []}


def run(test: str, run_id: int, n: int) -> dict:
    wf, planned, verdicts = PL.TESTS[test]
    jobs = []
    for k, name in enumerate(PL.JOBS[wf]):
        jid = run_id * 100 + k
        if name == PL.GATE_JOB:
            jobs.append(job(jid, name, annotations=notes(RG.GATE_TITLE, gate_rec(test, run_id))))
        elif name in planned:
            jobs.append(job(jid, name, conclusion=PL.designed_end(name), minutes=MINUTES.get(name, 1),
                            annotations=notes(RG.RT_TITLE, verdict_rec(test, name, run_id)) if name in verdicts
                            else []))
        else:
            jobs.append(job(jid, name, ran=False))
    designed = all(PL.designed_end(j) == "success" for j in planned)
    return {"id": run_id, "name": "x", "path": f".github/workflows/{wf}", "event": "workflow_dispatch",
            "head_branch": "main", "head_sha": COMMIT, "display_title": PL.TITLE.format(test=test), "run_attempt": 1,
            "status": "completed", "conclusion": "success" if designed else "failure",
            "created_at": f"2026-10-20T{10 + n:02d}:00:00Z", "run_started_at": f"2026-10-20T{10 + n:02d}:00:05Z",
            "actor": OWNER, "triggering_actor": OWNER, "repository": {"full_name": SLUG}, "jobs": jobs}


def ci_run(**kw) -> dict:
    rec = {"id": CI_ID, "name": "CI", "path": ".github/workflows/ci.yml", "event": "push", "head_branch": "main",
           "head_sha": COMMIT, "display_title": "Merge pull request", "run_attempt": 1, "status": "completed",
           "conclusion": "success", "created_at": "2026-10-20T09:00:00Z", "run_started_at": "2026-10-20T09:00:01Z",
           "actor": OWNER, "triggering_actor": OWNER, "repository": {"full_name": SLUG},
           "jobs": [job(CI_ID * 10, R.CI_JOB, minutes=6), job(CI_ID * 10 + 1, "Compose render and exporter image")]}
    rec.update(kw)
    return rec


def evidence() -> dict:
    return {"schema": R.EVIDENCE_SCHEMA, "program": SN.PROGRAM_ID, "repository": SLUG, "commit": COMMIT,
            "named": {"RT-0": CI_ID, **RUN_IDS}, "collected_utc": "2026-10-21T00:00:00Z",
            "runs": [run(t, RUN_IDS[t], i) for i, t in enumerate(PL.DISPATCH_ORDER)], "ci_run": ci_run()}


def raw(ev) -> bytes:
    return R.dumps(ev)


def decided(ev) -> dict:
    return json.loads(R.build(raw(ev))[R.RECORD])


def the_run(ev: dict, test: str) -> dict:
    return next(r for r in ev["runs"] if r["id"] == RUN_IDS[test])


def the_job(ev: dict, test: str, name: str) -> dict:
    return next(j for j in the_run(ev, test)["jobs"] if j["name"] == name)


# -- PASS ------------------------------------------------------------------------------------------------

def test_every_test_passing_at_one_commit_is_infra_readiness_pass():
    rec = decided(evidence())
    assert rec["INFRA_READINESS"] == "PASS", rec["problems"]
    assert rec["schema"] == R.RECORD_SCHEMA and rec["program"] == SN.PROGRAM_ID and rec["commit"] == COMMIT
    assert set(rec["tests"]) == set(PL.ALL_TESTS)
    assert all(t["result"] == "PASS" for t in rec["tests"].values())
    assert rec["snapshot"]["address"] == ADDRESS and rec["snapshot"]["tag"] == "auth2q2-snapshot-sha256-" + "a" * 64
    assert rec["real_money_authorized"] is False and rec["dry_run"] is True
    # the ledger is every job of every readiness run, at the plan's timeouts; skipped jobs bill nothing
    want = sum(t["billed_minutes"] for k, t in rec["tests"].items() if k != "RT-0")
    assert rec["ledger"]["minutes"] == want <= PL.READINESS_CAP and rec["ledger"]["cap"] == 300
    probe = next(j for j in rec["tests"]["RT-10"]["jobs"] if j["name"] == "RT-10 probe")
    assert probe == {"name": "RT-10 probe", "attempt": 1, "conclusion": "cancelled",
                     "designed_end": "cancelled", "timeout_minutes": 2, "seconds": 150.0, "billed_minutes": 3}
    # OD-S8: the slowest measured run of each workload job, and twice it; the probes are not workloads
    assert rec["measured"]["Cold preparation"] == {"seconds": 690.0, "test": "RT-1", "run_id": RUN_IDS["RT-1"],
                                                   "timeout_minutes": 90, "twice_minutes": 23}
    assert rec["measured"]["RT-11 engine data path"]["twice_minutes"] == 27
    assert not set(rec["measured"]) & set(PL.DESIGNED_END)


def test_the_bundle_is_deterministic_and_verifies_byte_for_byte(tmp_path):
    files = R.build(raw(evidence()))
    assert files == R.build(raw(evidence()))
    assert set(files) == {R.EVIDENCE, R.RECORD, R.SUMS}
    sums = files[R.SUMS].decode().splitlines()
    assert [line.split("  ")[1] for line in sums] == sorted([R.EVIDENCE, R.RECORD])
    for name, body in files.items():
        (tmp_path / name).write_bytes(body)
    assert R.verify(tmp_path) == []
    assert R.main(["verify", "--dir", str(tmp_path)]) == 0
    rec = json.loads(files[R.RECORD])
    assert rec["evidence_sha256"] == __import__("hashlib").sha256(files[R.EVIDENCE]).hexdigest()


@pytest.mark.parametrize("edit, problem", [
    (lambda d: (d / R.RECORD).write_bytes((d / R.RECORD).read_bytes().replace(b'"PASS"', b'"PAS5"', 1)),
     f"{R.RECORD}: differs"),
    (lambda d: (d / R.SUMS).write_text("0" * 64 + "  evidence.json\n"), f"{R.SUMS}: differs"),
    (lambda d: (d / R.EVIDENCE).write_bytes((d / R.EVIDENCE).read_bytes().replace(b'"cancelled"', b'"success"', 1)),
     f"{R.RECORD}: differs"),
    (lambda d: (d / "notes.txt").write_text("x"), "notes.txt: not part of the bundle"),
    (lambda d: (d / R.RECORD).unlink(), f"{R.RECORD}: "),
    (lambda d: (d / R.EVIDENCE).unlink(), f"{R.EVIDENCE}: "),
])
def test_any_change_to_the_bundle_fails_its_verification(tmp_path, edit, problem):
    for name, body in R.build(raw(evidence())).items():
        (tmp_path / name).write_bytes(body)
    edit(tmp_path)
    got = R.verify(tmp_path)
    assert any(p.startswith(problem) for p in got), got
    assert R.main(["verify", "--dir", str(tmp_path)]) == 3


def test_a_failing_record_verifies_as_a_bundle_but_the_cli_says_it_is_not_pass(tmp_path, capsys):
    ev = evidence()
    the_run(ev, "RT-7")["run_attempt"] = 2
    for name, body in R.build(raw(ev)).items():
        (tmp_path / name).write_bytes(body)
    assert R.verify(tmp_path) == []
    assert R.main(["verify", "--dir", str(tmp_path)]) == 3
    assert "INFRA_READINESS = FAIL" in capsys.readouterr().out


# -- FAIL, one reason at a time -------------------------------------------------------------------------

def _gate(test, /, **kw):
    def edit(ev):
        the_job(ev, test, PL.GATE_JOB)["annotations"] = notes(RG.GATE_TITLE, gate_rec(test, RUN_IDS[test], **kw))
    return edit


def _verdict(test, job_name, /, **kw):
    def edit(ev):
        the_job(ev, test, job_name)["annotations"] = notes(RG.RT_TITLE, verdict_rec(test, job_name, RUN_IDS[test],
                                                                                     **kw))
    return edit


def _set_run(test, **kw):
    return lambda ev: the_run(ev, test).update(kw)


def _set_job(test, name, **kw):
    return lambda ev: the_job(ev, test, name).update(kw)


def _past_run(minutes: int, name: str = PL.GATE_JOB):
    def edit(ev):
        past = run("RT-4", 500, 0)
        past.update(head_sha="d" * 40, created_at="2026-10-19T08:00:00Z", conclusion="failure")
        past["jobs"] = [job(50000, name, conclusion="failure", minutes=1)]
        past["jobs"][0]["completed_at"] = "2026-10-20T10:00:00Z"
        past["jobs"][0]["started_at"] = f"2026-10-20T{10 - minutes // 60 - (1 if minutes % 60 else 0):02d}:" \
                                        f"{(60 - minutes % 60) % 60:02d}:01Z"  # a second short: bills ``minutes``
        ev["runs"].append(past)
    return edit


def _tamper_note(test, name):
    def edit(ev):
        j = the_job(ev, test, name)
        m = j["annotations"][0]["message"]
        j["annotations"][0]["message"] = m[:-4] + ("AAAA" if m[-4:] != "AAAA" else "BBBB")
    return edit


def _drop_named(test):
    return lambda ev: ev["named"].pop(test)


def _two_gate_records(ev):
    j = the_job(ev, "RT-4", PL.GATE_JOB)
    j["annotations"] += notes(RG.GATE_TITLE, gate_rec("RT-4", RUN_IDS["RT-4"], checked_utc="2026-10-20T10:00:01Z"))


def _extra_job_ran(ev):
    j = the_job(ev, "RT-4", "RT-5 restore without a cache entry")
    j.update(job(j["id"], j["name"]))


def _duplicate_job(ev):
    r = the_run(ev, "RT-9")
    r["jobs"].append(copy.deepcopy(the_job(ev, "RT-9", "RT-9 billing guard")))


def _unknown_job(ev):
    the_run(ev, "RT-9")["jobs"].append(job(1, "a job the plan does not name"))


@pytest.mark.parametrize("edit, problem", [
    (_drop_named("RT-7"), "NAMES: the evidence names"),
    (lambda ev: ev["named"].update({"RT-8": RUN_IDS["RT-9"]}), "NAMES: every test names one run id"),
    (lambda ev: ev["named"].update({"RT-8": 77}), "NAMES: RT-8 names run 77"),
    (lambda ev: ev["named"].update({"RT-8": True}), "NAMES: every test names one run id"),
    (lambda ev: ev.update(commit="not a sha"), "EVIDENCE: 'not a sha'"),
    (lambda ev: ev.update(schema="OTHER"), "EVIDENCE: schema OTHER"),
    (_set_run("RT-4", head_sha="d" * 40), "PROVENANCE: RT-4: run"),
    (_set_run("RT-4", run_attempt=2), "PROVENANCE: RT-4 run"),
    (_set_run("RT-4", triggering_actor={"login": "someone", "id": 1}), "PROVENANCE: RT-4 run"),
    (_set_run("RT-4", actor={"login": "someone", "id": 1}), "PROVENANCE: RT-4 run"),
    (_set_run("RT-4", display_title="AUTH2Q2-READINESS RT-5"), "PROVENANCE: RT-4: run"),
    (_set_run("RT-4", event="push"), "PROVENANCE: RT-4: run"),
    (_set_run("RT-4", head_branch="claude/x"), "PROVENANCE: RT-4: run"),
    (_set_run("RT-4", path=".github/workflows/auth2q2-prepare.yml"), "PROVENANCE: RT-4: run"),
    (_set_run("RT-4", status="in_progress"), "PROVENANCE: RT-4 run"),
    (_set_run("RT-4", repository={"full_name": "other/repo"}), "PROVENANCE: RT-4 run"),
    (_gate("RT-4", decision="PARK"), "GATE: RT-4 run"),
    (_gate("RT-4", decision="NO_DISPATCH", reasons=["SERIAL: x"]), "GATE: RT-4 run"),
    (_gate("RT-4", reasons=["SERIAL: x"]), "GATE: RT-4 run"),
    (_gate("RT-4", test="RT-5"), "GATE: RT-4 run"),
    (_gate("RT-4", run_id=1), "GATE: RT-4 run"),
    (_gate("RT-4", sha="d" * 40), "GATE: RT-4 run"),
    (_gate("RT-4", main_sha="d" * 40), "GATE: RT-4 run"),
    (_gate("RT-4", ledger={"minutes": 230, "total_if_admitted": 301}), "GATE: RT-4 run"),
    (_gate("RT-4", ledger={"minutes": 0}), "GATE: RT-4 run"),
    (_two_gate_records, "GATE: RT-4 run"),
    (_set_job("RT-4", PL.GATE_JOB, annotations=[]), "GATE: RT-4 run"),
    (_tamper_note("RT-4", PL.GATE_JOB), "GATE: RT-4 run"),
    (_verdict("RT-4", "RT-4 cold restore and D0 data path", result="FAIL", checks={"lock_byte_identical": False}),
     "VERDICT: RT-4 job"),
    (_verdict("RT-4", "RT-4 cold restore and D0 data path", checks={"lock_byte_identical": False}),
     "VERDICT: RT-4 job"),
    (_verdict("RT-4", "RT-4 cold restore and D0 data path", checks={}), "VERDICT: RT-4 job"),
    (_verdict("RT-4", "RT-4 cold restore and D0 data path", checks={"a": 1}), "VERDICT: RT-4 job"),
    (_verdict("RT-4", "RT-4 cold restore and D0 data path", problems=["x"]), "VERDICT: RT-4 job"),
    (_verdict("RT-4", "RT-4 cold restore and D0 data path", run_id="1"), "VERDICT: RT-4 job"),
    (_verdict("RT-4", "RT-4 cold restore and D0 data path", run_attempt="2"), "VERDICT: RT-4 job"),
    (_verdict("RT-4", "RT-4 cold restore and D0 data path", sha="d" * 40), "VERDICT: RT-4 job"),
    (_verdict("RT-4", "RT-4 cold restore and D0 data path", test="RT-11"), "VERDICT: RT-4 job"),
    (_verdict("RT-4", "RT-4 cold restore and D0 data path", job="RT-11 engine data path"), "VERDICT: RT-4 job"),
    (_verdict("RT-4", "RT-4 cold restore and D0 data path", schema="X"), "VERDICT: RT-4 job"),
    (_set_job("RT-4", "RT-4 cold restore and D0 data path", annotations=[]), "VERDICT: RT-4 job"),
    (_tamper_note("RT-3", "Read-only probe"), "VERDICT: RT-3 job 'Read-only probe'"),
    (_set_job("RT-7", "RT-7 probe infra", conclusion="success"), "JOBS: RT-7 job 'RT-7 probe infra'"),
    (_set_job("RT-10", "RT-10 probe", conclusion="failure"), "JOBS: RT-10 job 'RT-10 probe'"),
    (_set_job("RT-4", "RT-4 cold restore and D0 data path", conclusion="failure"), "JOBS: RT-4 job"),
    (_set_job("RT-4", "RT-4 cold restore and D0 data path", run_attempt=2), "JOBS: RT-4 job"),
    (_set_job("RT-6", "RT-6 classify", status="in_progress", conclusion=None), "JOBS: RT-6 job 'RT-6 classify'"),
    (_extra_job_ran, "JOBS: RT-4 run"),
    (_duplicate_job, "JOBS: RT-9 run"),
    (_unknown_job, "JOBS: RT-9 run"),
    (_unknown_job, "LEDGER: run"),
    (lambda ev: ev["ci_run"].update(conclusion="failure"), "RT-0: CI run"),
    (lambda ev: ev["ci_run"].update(event="pull_request"), "RT-0: CI run"),
    (lambda ev: ev["ci_run"].update(head_sha="d" * 40), "RT-0: CI run"),
    (lambda ev: ev["ci_run"].update(head_branch="claude/x"), "RT-0: CI run"),
    (lambda ev: ev["ci_run"].update(path=".github/workflows/merge-law.yml"), "RT-0: run"),
    (lambda ev: ev["ci_run"]["jobs"][0].update(conclusion="failure"), "RT-0: CI run"),
    (lambda ev: ev["ci_run"].update(id=1), "RT-0: the CI run"),
    (lambda ev: ev.pop("ci_run"), "RT-0: the CI run"),
    (_gate("RT-11", release={"address": "sha256:" + "e" * 64}), "SNAPSHOT: RT-11 read the snapshot"),
    (_verdict("RT-1", "Snapshot release (contents: write)", measurements={}), "SNAPSHOT: RT-1 names no"),
    (_past_run(PL.READINESS_CAP), "LEDGER: "),
    (_past_run(3, name="not a planned job"), "LEDGER: run 500"),
])
def test_any_shortfall_fails_infra_readiness_and_names_its_reason(edit, problem):
    ev = evidence()
    edit(ev)
    rec = decided(ev)
    assert rec["INFRA_READINESS"] == "FAIL"
    assert any(p.startswith(problem) for p in rec["problems"]), rec["problems"]


def test_the_cap_edge_passes_and_one_minute_more_fails():
    ev = evidence()
    used = decided(ev)["ledger"]["minutes"]
    edge = copy.deepcopy(ev)
    _past_run(PL.READINESS_CAP - used)(edge)
    rec = decided(edge)
    assert rec["ledger"]["minutes"] == PL.READINESS_CAP and rec["INFRA_READINESS"] == "PASS", rec["problems"]
    over = copy.deepcopy(ev)
    _past_run(PL.READINESS_CAP - used + 1)(over)
    assert decided(over)["INFRA_READINESS"] == "FAIL"


def test_unreadable_evidence_is_a_fail_not_a_crash():
    for body in (b"not json", b"[]", b"null", b"{}"):
        rec = json.loads(R.build(body)[R.RECORD])
        assert rec["INFRA_READINESS"] == "FAIL" and rec["problems"]


def test_a_failing_test_keeps_its_run_and_measurements_in_the_record():
    ev = evidence()
    _verdict("RT-11", "RT-11 engine data path", result="FAIL", checks={"data_truth_pass": False})(ev)
    rec = decided(ev)
    t = rec["tests"]["RT-11"]
    assert t["result"] == "FAIL" and t["run_id"] == RUN_IDS["RT-11"]
    assert t["verdicts"]["RT-11 engine data path"]["checks"] == {"data_truth_pass": False}
    assert all(rec["tests"][k]["result"] == "PASS" for k in PL.ALL_TESTS if k != "RT-11")


# -- collect and check-live, against an in-memory Actions API --------------------------------------------

class FakeAPI:
    def __init__(self, ev: dict):
        self.slug = SLUG
        self.ev = copy.deepcopy(ev)
        self.calls: list[str] = []

    def api(self, method, path, body=None):
        assert method == "GET", "the record only reads"
        self.calls.append(path)
        base = path.split("?")[0]
        page = int(path.split("&page=")[1]) if "&page=" in path else 1
        for wf in PL.WORKFLOWS:
            if base == f"/repos/{SLUG}/actions/workflows/{wf}/runs":
                runs = [{k: v for k, v in r.items() if k != "jobs"} for r in self.ev["runs"]
                        if r["path"].endswith(wf)]
                return 200, {"workflow_runs": runs if page == 1 else []}
        for r in self.ev["runs"] + [self.ev["ci_run"]]:
            if base == f"/repos/{SLUG}/actions/runs/{r['id']}/jobs":
                jobs = [{k: v for k, v in j.items() if k != "annotations"} for j in r["jobs"]]
                return 200, {"jobs": jobs if page == 1 else []}
            if base == f"/repos/{SLUG}/actions/runs/{r['id']}":
                return 200, {k: v for k, v in r.items() if k != "jobs"}
            for j in r["jobs"]:
                if base == f"/repos/{SLUG}/check-runs/{j['id']}/annotations":
                    extra = [{"title": None, "message": "Process completed with exit code 3."}]
                    return 200, (j.get("annotations", []) + extra) if page == 1 else []
        return 404, "not found (HTTP 404)"


def expected_evidence() -> dict:
    """What collect reads back: only the jobs that ran carry their annotations."""
    ev = evidence()
    for r in ev["runs"]:
        for j in r["jobs"]:
            if j["conclusion"] == "skipped" and not j["steps"]:
                j.pop("annotations", None)
    for j in ev["ci_run"]["jobs"]:
        j.pop("annotations", None)
    ev["runs"].sort(key=lambda r: (r["created_at"], r["id"]))
    return ev


def test_collect_reads_only_and_captures_what_build_needs():
    fake = FakeAPI(evidence())
    got = R.collect(fake, COMMIT, {"RT-0": CI_ID, **RUN_IDS}, R._ts("2026-10-21T00:00:00Z"))
    assert got == expected_evidence()
    assert decided(got)["INFRA_READINESS"] == "PASS"


def test_check_live_finds_any_difference_from_the_api():
    ev = expected_evidence()
    assert R.live_problems(ev, copy.deepcopy(ev)) == []
    changed = copy.deepcopy(ev)
    changed["runs"][0]["jobs"][0]["completed_at"] = "2026-10-20T10:30:00Z"
    assert R.live_problems(ev, changed) == [f"run {changed['runs'][0]['id']}: the evidence differs from the API"]
    left_out = copy.deepcopy(ev)
    left_out["runs"].append({**run("RT-4", 600, 0), "created_at": "2026-10-20T23:00:00Z"})
    assert R.live_problems(ev, left_out) == [f"run 600: created 2026-10-20T23:00:00Z, before the evidence was "
                                             "collected, and left out"]
    later = copy.deepcopy(ev)
    later["runs"].append({**run("RT-4", 601, 0), "created_at": "2026-10-22T00:00:00Z"})
    assert R.live_problems(ev, later) == []
    ci = copy.deepcopy(ev)
    ci["ci_run"]["conclusion"] = "failure"
    assert R.live_problems(ev, ci) == ["the RT-0 CI run differs from the API"]


def test_check_live_refuses_a_moved_collection_time_or_a_ledger_over_the_cap():
    ev = expected_evidence()
    early = {**copy.deepcopy(ev), "collected_utc": "2026-10-19T00:00:00Z"}  # before its own newest run
    assert R.live_problems(early, {**copy.deepcopy(ev), "collected_utc": "2026-10-22T00:00:00Z"})[0].startswith(
        "collected_utc '2026-10-19T00:00:00Z' is not between")
    future = {**copy.deepcopy(ev), "collected_utc": "2026-10-23T00:00:00Z"}  # after the live reading
    assert R.live_problems(future, {**copy.deepcopy(ev), "collected_utc": "2026-10-22T00:00:00Z"})
    later = copy.deepcopy(ev)
    later["collected_utc"] = "2026-10-22T00:00:00Z"
    big = {**run("RT-4", 602, 0), "created_at": "2026-10-21T12:00:00Z"}
    big["jobs"] = [job(60200, PL.GATE_JOB, conclusion="failure", minutes=1)]
    big["jobs"][0]["started_at"], big["jobs"][0]["completed_at"] = "2026-10-21T10:00:00Z", "2026-10-21T14:59:00Z"
    later["runs"].append(big)  # a run after the evidence: not a difference, but its minutes still count
    got = R.live_problems(ev, later)
    assert len(got) == 1 and got[0].startswith("the live readiness ledger is ") and "(cap 300)" in got[0]


def test_the_cli_collects_builds_verifies_and_checks_live(tmp_path, monkeypatch, capsys):
    fake = FakeAPI(evidence())
    monkeypatch.setattr(R.RL, "GH", lambda slug: fake)
    clock = iter(["2026-10-21T00:00:00Z", "2026-10-22T00:00:00Z", "2026-10-22T01:00:00Z"])

    class Clock(R.datetime):
        @classmethod
        def now(cls, tz=None):
            return R._ts(next(clock))
    monkeypatch.setattr(R, "datetime", Clock)
    args = ["collect", "--repo-slug", SLUG, "--commit", COMMIT, "--out", str(tmp_path / "e.json")]
    for t, i in {"RT-0": CI_ID, **RUN_IDS}.items():
        args += ["--run", f"{t}={i}"]
    assert R.main(args) == 0
    assert R.main(["build", "--evidence", str(tmp_path / "e.json"), "--out-dir", str(tmp_path / "b")]) == 0
    assert "INFRA_READINESS = PASS" in capsys.readouterr().out
    assert R.main(["verify", "--dir", str(tmp_path / "b")]) == 0
    assert R.main(["check-live", "--repo-slug", SLUG, "--dir", str(tmp_path / "b")]) == 0
    fake.ev["runs"][0]["jobs"][0]["completed_at"] = "2026-10-20T10:30:00Z"
    assert R.main(["check-live", "--repo-slug", SLUG, "--dir", str(tmp_path / "b")]) == 3
    assert all(c.startswith(f"/repos/{SLUG}/") for c in fake.calls)


@pytest.mark.parametrize("runs", [
    ["RT-1=1"],
    [f"{t}=1" for t in PL.ALL_TESTS] + ["RT-1=2"],
    [f"{t}=x" for t in PL.ALL_TESTS],
    [f"{t}=1" for t in PL.ALL_TESTS if t != "RT-0"] + ["RT-12=1"],
])
def test_collect_needs_every_test_named_once(runs):
    with pytest.raises(SystemExit):
        R._named(runs)
    assert R._named([f"{t}={i}" for i, t in enumerate(PL.ALL_TESTS, 1)])["RT-11"] == 12
