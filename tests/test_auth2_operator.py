"""AUTH-2 operator gate (.github/gates/auth2_operator.py): the pre-dispatch guard in Actions only ever
adds refusals to research/auth2/dispatch_guard.decide, a dispatch needs a fresh, successful guard run's
DISPATCH record on the current main, and the published records survive the annotation channel byte-exact.

PAPER / RESEARCH ONLY. Nothing here calls GitHub: every function under test is pure.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("numpy")
yaml = pytest.importorskip("yaml")

from auth2 import dispatch_guard as DG  # noqa: E402
from auth2 import run_node as RN  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
WF = REPO / ".github" / "workflows"
_spec = importlib.util.spec_from_file_location("auth2_operator", REPO / ".github" / "gates" / "auth2_operator.py")
OP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(OP)

MAIN = "a" * 40
NOW = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)


def state(**kw) -> dict:
    s = {"now": "2026-11-03T10:00:00Z", "self_run_id": None,
         "billing": {"readable": True, "remaining_included_minutes": 2000, "budget_usd_zero": True},
         "runs": []}
    s.update(kw)
    return s


def aux(i, workflow=OP.GUARD_WORKFLOW, status="completed", conclusion="success", minutes=2,
        created="2026-11-03T09:00:00Z"):
    return {"id": i, "workflow": workflow, "status": status, "conclusion": conclusion, "created_at": created,
            "minutes": minutes}


# -- the decision only adds refusals ---------------------------------------------------------------

@pytest.mark.parametrize("node,part", [("D0", 1), ("PC-A2", 2), ("HOLM", 1), ("SC-A3", 1)])
def test_with_no_guard_or_closure_runs_the_decision_is_dispatch_guards(node, part):
    for s in (state(), state(billing={"readable": False}),
              state(billing={"readable": True, "remaining_included_minutes": 700, "budget_usd_zero": True})):
        base = DG.decide(json.loads(json.dumps(s)), node, part)
        mine = OP.decide(s, [], node, part)
        assert mine["decision"] == base["decision"]
        assert mine["reasons"] == base["reasons"]


def test_unreadable_billing_never_dispatches():
    d = OP.decide(state(billing={"readable": False, "reason": "HTTP 403"}), [aux(1)], "D0", 1)
    assert d["decision"] == DG.NO_DISPATCH and any(r.startswith("FAIL_CLOSED") for r in d["reasons"])
    assert d["billing"]["readable"] is False


def test_an_active_guard_or_closure_run_blocks_dispatch():
    d = OP.decide(state(), [aux(5, status="in_progress", conclusion=None)], "D0", 1)
    assert d["decision"] == DG.NO_DISPATCH and any(r.startswith("SERIAL") for r in d["reasons"])


def test_guard_and_closure_minutes_count_toward_the_4000_cap():
    big = {"readable": True, "remaining_included_minutes": 100000, "budget_usd_zero": True}
    ok = OP.decide(state(billing=big), [aux(1, minutes=3000)], "PC-A2", 1)  # 3000 + 2 x 180 = 3360
    assert ok["decision"] == DG.DISPATCH and ok["total_minutes_ledger"] == 3000
    d = OP.decide(state(billing=big), [aux(1, minutes=3700)], "PC-A2", 1)  # 3700 + 360 > 4000
    assert d["decision"] == DG.NO_DISPATCH and any(r.startswith("CAP: minutes") for r in d["reasons"])


def test_closure_is_guarded_with_its_own_rerun_and_attempt_rules():
    holm_done = [{"id": 1, "node": "HOLM", "part": 1, "status": "completed", "conclusion": "success",
                  "created_at": "2026-11-01T00:00:00Z",
                  "jobs": [{"status": "completed", "started_at": "2026-11-01T00:00:00Z",
                            "completed_at": "2026-11-01T00:02:00Z"}],
                  "guard": {"month": "2026-11", "a_m": 2000}}]
    d = OP.decide(state(runs=holm_done), [], OP.CLOSURE, 1)
    assert d["decision"] == DG.DISPATCH and d["node"] == OP.CLOSURE  # HOLM succeeded: not a re-run of CLOSURE
    assert d["timeout_minutes"] == OP.CLOSURE_TIMEOUT
    done = OP.decide(state(runs=holm_done), [aux(2, OP.CLOSURE_WORKFLOW)], OP.CLOSURE, 1)
    assert any(r.startswith("NEVER_RERUN: CLOSURE") for r in done["reasons"])
    spent = OP.decide(state(runs=holm_done), [aux(2, OP.CLOSURE_WORKFLOW, conclusion="failure"),
                                              aux(3, OP.CLOSURE_WORKFLOW, conclusion="failure")], OP.CLOSURE, 1)
    assert any(r.startswith("ATTEMPTS") for r in spent["reasons"])
    low = OP.decide(state(billing={"readable": True, "remaining_included_minutes": 535, "budget_usd_zero": True}),
                    [], OP.CLOSURE, 1)  # 535 - 2 x 20 < 500, although 535 - 2 x 15 >= 500
    assert low["decision"] == DG.PARK


# -- the annotation channel ------------------------------------------------------------------------

def notes_from(lines: str) -> list[dict]:
    out = []
    for line in lines.splitlines():
        m = re.fullmatch(r"::notice title=([A-Z0-9_]+)::(.*)", line)
        assert m, line
        out.append({"title": m[1], "message": m[2], "annotation_level": "notice"})
    return out


@pytest.mark.parametrize("size", [0, 10, OP.CHUNK, 3 * OP.CHUNK + 7])
def test_published_bytes_round_trip_exactly(size):
    data = bytes(range(256)) * (size // 256) + bytes(size % 256)
    notes = notes_from(OP.annotation_lines(OP.CLOSURE_RECORD, data))
    assert OP.decode_annotations(notes, OP.CLOSURE_RECORD) == [data]
    assert OP.decode_annotations(notes, OP.RECORD) == []


def test_a_tampered_or_incomplete_publication_is_refused():
    data = b"x" * (2 * OP.CHUNK)
    notes = notes_from(OP.annotation_lines(OP.CLOSURE_RECORD, data))
    with pytest.raises(ValueError, match="incomplete"):
        OP.decode_annotations(notes[:-1], OP.CLOSURE_RECORD)
    sha, i, rest = notes[0]["message"].split(":", 2)
    forged = base64.b64encode(b"y" * 12000).decode()
    bad = [{**notes[0], "message": f"{sha}:{i}:{forged}"}] + notes[1:]
    with pytest.raises(ValueError, match="sha256"):
        OP.decode_annotations(bad, OP.CLOSURE_RECORD)
    with pytest.raises(SystemExit):
        OP.annotation_lines(OP.CLOSURE_RECORD, b"z" * (11 * OP.CHUNK))


def test_result_summaries_carry_what_the_frozen_dag_reads(tmp_path):
    (tmp_path / "D0.result.json").write_text(json.dumps(
        {"terminal_state": "PASS", "data_limited": {"A1": False, "A2": False, "A3": True}, "program_sha256": "p"}))
    lines = OP.annotate_results(tmp_path)
    [payload] = OP.decode_annotations(notes_from(lines), OP.RESULT)
    [s] = json.loads(payload)
    assert s["key"] == "D0" and s["terminal_state"] == "PASS"
    assert s["sha256"] == hashlib.sha256((tmp_path / "D0.result.json").read_bytes()).hexdigest()
    nxt = OP.next_nodes({"D0": s})
    assert nxt == RN.eligible({"D0": json.loads((tmp_path / "D0.result.json").read_text())})
    assert ("CAL-A1", 1) in nxt["next"] and not any(n.endswith("A3") for n, _ in nxt["next"])


# -- check-dispatch -------------------------------------------------------------------------------

def guard_run(i=100, node="D0", part=1, sha=MAIN, conclusion="success", created="2026-11-03T09:55:00Z", **kw):
    r = {"id": i, "path": f".github/workflows/{OP.GUARD_WORKFLOW}", "event": "workflow_dispatch",
         "head_branch": "main", "head_sha": sha, "status": "completed", "conclusion": conclusion,
         "display_title": f"AUTH2-GUARD {node} part {part}", "created_at": created}
    r.update(kw)
    return r


def record(node="D0", part=1, decision=DG.DISPATCH, checked="2026-11-03T09:55:30Z", run_id=100, sha=MAIN):
    body = {"node": node, "part": part, "decision": decision, "mode": "pre-dispatch", "checked_utc": checked,
            "run_id": run_id, "sha": sha, "reasons": [] if decision == DG.DISPATCH else ["X"]}
    return notes_from(OP.annotation_lines(OP.RECORD, (json.dumps(body) + "\n").encode()))


def test_a_fresh_successful_dispatch_record_on_main_dispatches():
    d = OP.check_dispatch(guard_run(), record(), [{"id": 100, "status": "completed",
                                                   "created_at": "2026-11-03T09:55:00Z"}],
                          "D0", 1, MAIN, NOW)
    assert d["decision"] == DG.DISPATCH, d["reasons"]


@pytest.mark.parametrize("run,notes,later,why", [
    (guard_run(conclusion="failure"), record(), [], "did not succeed"),
    (guard_run(), record(decision=DG.NO_DISPATCH), [], "guard decided NO_DISPATCH"),
    (guard_run(sha="b" * 40), record(sha="b" * 40), [], "not main"),
    (guard_run(path=".github/workflows/ci.yml"), record(), [], "not a run of"),
    (guard_run(event="push"), record(), [], "not a workflow_dispatch run on main"),
    (guard_run(node="CAL-A1"), record(node="CAL-A1"), [], "titled"),
    (guard_run(), record(checked="2026-11-03T09:30:00Z"), [], "not fresh"),
    (guard_run(), record(run_id=99), [], "does not name this run"),
    (guard_run(), [], [], "unreadable"),
    (guard_run(), record() + record(), [], "unreadable"),
    (guard_run(), record(), [{"id": 101, "status": "completed", "created_at": "2026-11-03T09:56:00Z"}],
     "created after"),
    (guard_run(), record(), [{"id": 7, "status": "queued", "created_at": "2026-11-02T00:00:00Z"}], "SERIAL"),
])
def test_anything_short_of_that_never_dispatches(run, notes, later, why):
    d = OP.check_dispatch(run, notes, later, "D0", 1, MAIN, NOW)
    assert d["decision"] == DG.NO_DISPATCH
    assert any(why in r for r in d["reasons"]), d["reasons"]


def test_a_record_from_the_future_is_not_fresh():
    d = OP.check_dispatch(guard_run(), record(checked=(NOW + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")),
                          [], "D0", 1, MAIN, NOW)
    assert any("not fresh" in r for r in d["reasons"])


# -- the workflows ---------------------------------------------------------------------------------

def load(name: str) -> dict:
    return yaml.safe_load((WF / name).read_text())


@pytest.mark.parametrize("name,run_name", [
    ("auth2-guard.yml", "AUTH2-GUARD ${{ inputs.node }} part ${{ inputs.part }}"),
    ("auth2-closure.yml", "AUTH2-CLOSURE"),
])
def test_the_operator_workflows_are_manual_serial_read_only(name, run_name):
    wf = load(name)
    text = (WF / name).read_text()
    on = wf.get("on", wf.get(True))
    assert list(on) == ["workflow_dispatch"]
    assert wf["permissions"] == {"contents": "read", "actions": "read"}
    assert wf["concurrency"] == {"group": "auth2-program", "cancel-in-progress": False}
    assert wf["run-name"] == run_name
    [job] = wf["jobs"].values()
    assert job["timeout-minutes"] == (OP.GUARD_TIMEOUT if name == "auth2-guard.yml" else OP.CLOSURE_TIMEOUT)
    assert set(re.findall(r"secrets\.([A-Z0-9_]+)", text)) == {"AUTH2_BILLING_TOKEN"}
    for forbidden in ("git push", "git commit", "contents: write", "dry_run\": false", "docker",
                      "--append-ledger", "run_node"):
        assert forbidden not in text
    names = [s.get("name", s.get("uses", "")) for s in job["steps"]]
    guard = next(i for i, n in enumerate(names) if "dispatch guard" in n)
    assert all("uses" in s or "Install" in s.get("name", "") for s in job["steps"][:guard])


def test_the_guard_workflow_offers_every_node_and_closure():
    on = load("auth2-guard.yml").get("on")
    on = on if on is not None else load("auth2-guard.yml")[True]
    assert sorted(on["workflow_dispatch"]["inputs"]["node"]["options"]) == sorted([*RN.NODES, OP.CLOSURE])
    assert OP.GUARD_TITLE.match("AUTH2-GUARD PC-A2 part 2")


def test_node_jobs_guard_through_the_operator_and_publish_their_results():
    steps = load("auth2.yml")["jobs"]["node"]["steps"]
    guard = next(s for s in steps if "dispatch guard" in s.get("name", ""))
    assert "auth2_operator.py guard" in guard["run"] and "--in-job" in guard["run"]
    pub = next(s for s in steps if s.get("name", "").startswith("Publish the result summary"))
    assert pub["if"] == "always()" and "annotate-results" in pub["run"]
    names = [s.get("name", s.get("uses", "")) for s in steps]
    assert names.index(pub["name"]) < names.index("actions/upload-artifact@v4")


def test_guard_and_closure_artifacts_are_never_read_as_node_results():
    for name in ("auth2-guard.yml", "auth2-closure.yml"):
        upload = next(s for s in load(name)["jobs"][next(iter(load(name)["jobs"]))]["steps"]
                      if s.get("uses", "").startswith("actions/upload-artifact"))
        assert not upload["with"]["name"].startswith("auth2-")


def test_research_auth2_code_is_untouched_by_the_operator():
    """The gate lives outside research/auth2/, whose *.py files are pinned in every preregistration."""
    pins = json.loads((REPO / "research/auth2/prereg/D0.json").read_text())["code_sha256"]
    assert pins == RN.code_sha256()
    assert not any("operator" in k for k in pins)
