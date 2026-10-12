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
        assert mine["reasons"][:len(base["reasons"])] == base["reasons"]  # it only adds refusals
        added = mine["reasons"][len(base["reasons"]):]
        assert added == ([] if s["billing"].get("budget_usd_zero") else
                         ["FAIL_CLOSED: an Actions budget of USD 0 that stops usage is not verified"])


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


# -- billing evidence: the endpoint dispatch_guard reads is closed; nothing unproven dispatches ----------------

OWNER = "algamal119933-ux"
OCT = datetime(2026, 10, 12, 0, 5, tzinfo=timezone.utc)
TOKEN = "TESTONLY-billing-token-0123456789"  # not a token format: the hygiene gate scans for real ones


def usage_item(**kw) -> dict:
    it = {"date": "2026-10-11", "product": "Actions", "sku": "Actions Linux", "quantity": 12.0, "unitType": "Minutes",
          "pricePerUnit": 0.008, "grossAmount": 0.096, "discountAmount": 0.096, "netAmount": 0.0,
          "repositoryName": f"{OWNER}/trading-lab-os-sandbox"}
    it.update(kw)
    return it


def read_with(monkeypatch, response, token=TOKEN):
    calls = []
    if token is None:
        monkeypatch.delenv("AUTH2_BILLING_TOKEN", raising=False)
    else:
        monkeypatch.setenv("AUTH2_BILLING_TOKEN", token)

    def get(path, tok):
        calls.append((path, tok))
        return response

    return OP.read_billing(OWNER, "AUTH2_BILLING_TOKEN", OCT, get=get), calls


def decided(bill: dict, **kw) -> dict:
    return OP.decide(state(billing=bill), [], "D0", 1, **kw)


def test_a_410_from_the_closed_endpoint_never_dispatches(monkeypatch):
    bill, calls = read_with(monkeypatch, (410, "gh: This endpoint has been moved. (HTTP 410)"))
    assert calls == [(f"/users/{OWNER}/settings/billing/usage?year=2026&month=10", TOKEN)]
    assert bill["usage_evidence"]["class"] == "ENDPOINT_RETIRED"
    d = decided(bill)
    assert d["decision"] == DG.NO_DISPATCH and any("ENDPOINT_RETIRED" in r for r in d["reasons"])


def test_the_closed_endpoint_is_no_longer_called(monkeypatch):
    def closed(*_a, **_k):
        raise AssertionError("dispatch_guard.read_billing calls /settings/billing/actions, closed by GitHub (410)")

    monkeypatch.setattr(DG, "read_billing", closed)
    monkeypatch.setattr(DG, "_api", lambda path, token_env=None: {"workflow_runs": []})
    monkeypatch.setattr(OP, "billing_get", lambda path, tok: (410, "gh: This endpoint has been moved. (HTTP 410)"))
    monkeypatch.setenv("AUTH2_BILLING_TOKEN", TOKEN)
    st = OP.collect("o/r", OWNER, "AUTH2_BILLING_TOKEN", None)
    assert st["runs"] == [] and "runs_error" not in st and st["billing"]["readable"] is False


def test_a_403_is_a_permission_failure_not_an_api_migration(monkeypatch):
    bill, _ = read_with(monkeypatch, (403, "gh: Resource not accessible by personal access token (HTTP 403)"))
    assert bill["usage_evidence"]["class"] == "PERMISSION_DENIED"
    assert decided(bill)["decision"] == DG.NO_DISPATCH


@pytest.mark.parametrize("token", [None, "", "   "])
def test_a_missing_token_never_falls_back_to_the_workflow_token(monkeypatch, token):
    bill, calls = read_with(monkeypatch, (200, {"usageItems": [usage_item()]}), token=token)
    assert calls == []  # no request at all, so the workflow's GITHUB_TOKEN can never answer for billing
    assert bill["usage_evidence"]["class"] == "TOKEN_MISSING"
    d = decided(bill)
    assert d["decision"] == DG.NO_DISPATCH and any("TOKEN_MISSING" in r for r in d["reasons"])


def test_an_invalid_token_is_classified(monkeypatch):
    bill, _ = read_with(monkeypatch, (401, "gh: Bad credentials (HTTP 401)"))
    assert bill["usage_evidence"]["class"] == "TOKEN_INVALID"
    assert decided(bill)["decision"] == DG.NO_DISPATCH


def test_billing_requests_carry_only_the_billing_token(monkeypatch):
    seen = {}

    def run(cmd, capture_output, text, env):
        seen.update(cmd=cmd, env=env)
        return OP.subprocess.CompletedProcess(cmd, 1, "", "gh: This endpoint has been moved. (HTTP 410)")

    monkeypatch.setenv("GITHUB_TOKEN", "workflow-token")
    monkeypatch.setenv("GH_TOKEN", "workflow-token")
    monkeypatch.setattr(OP.subprocess, "run", run)
    assert OP.billing_get("/users/x/settings/billing/usage", TOKEN) == \
        (410, "gh: This endpoint has been moved. (HTTP 410)")
    assert seen["env"]["GH_TOKEN"] == TOKEN and "GITHUB_TOKEN" not in seen["env"]
    assert TOKEN not in " ".join(seen["cmd"])


@pytest.mark.parametrize("item", [
    {k: v for k, v in usage_item().items() if k != "quantity"},
    usage_item(quantity="12"),
    usage_item(netAmount=True),
    usage_item(date=None),
    "not an object",
])
def test_missing_or_mistyped_billing_fields_never_dispatch(monkeypatch, item):
    bill, _ = read_with(monkeypatch, (200, {"usageItems": [usage_item(), item]}))
    assert bill["usage_evidence"]["class"] == "MISSING_FIELDS" and not bill["usage_evidence"]["verified"]
    assert decided(bill)["decision"] == DG.NO_DISPATCH


@pytest.mark.parametrize("body", [None, [], {"items": []}, {"usageItems": {"0": usage_item()}}, "html"])
def test_a_malformed_response_never_dispatches(monkeypatch, body):
    bill, _ = read_with(monkeypatch, (200, body))
    assert bill["usage_evidence"]["class"] == "MALFORMED"
    assert decided(bill)["decision"] == DG.NO_DISPATCH


@pytest.mark.parametrize("item,why", [
    (usage_item(repositoryName="someone-else/repo"), "WRONG_ACCOUNT"),
    (usage_item(repositoryName=7), "WRONG_ACCOUNT"),
    (usage_item(date="2026-09-30"), "WRONG_PERIOD"),
    (usage_item(date="2025-10-11"), "WRONG_PERIOD"),
])
def test_another_account_or_billing_period_never_dispatches(monkeypatch, item, why):
    bill, _ = read_with(monkeypatch, (200, {"usageItems": [usage_item(), item]}))
    assert bill["usage_evidence"]["class"] == why
    assert decided(bill)["decision"] == DG.NO_DISPATCH


@pytest.mark.parametrize("status", [None, 404, 500, 503])
def test_any_other_api_failure_never_dispatches(monkeypatch, status):
    bill, _ = read_with(monkeypatch, (status, "gh: Internal Error"))
    assert bill["usage_evidence"]["class"] in ("API_ERROR", "NOT_FOUND")
    assert decided(bill)["decision"] == DG.NO_DISPATCH


def test_valid_usage_evidence_is_recorded_but_cannot_prove_remaining_included_minutes(monkeypatch):
    items = [usage_item(), usage_item(date="2026-10-01", quantity=3.0, grossAmount=0.024, discountAmount=0.024),
             usage_item(product="Copilot", sku="Copilot Premium Request", unitType="requests", repositoryName=None)]
    bill, _ = read_with(monkeypatch, (200, {"usageItems": items}))
    ev = bill["usage_evidence"]
    assert ev["verified"] and ev["class"] == "USAGE_VERIFIED" and ev["period"] == "2026-10"
    assert ev["endpoint"] == f"/users/{OWNER}/settings/billing/usage"
    assert ev["actions"] == {"Actions Linux": {"unitType": "Minutes", "quantity": 15.0, "grossAmount": 0.12,
                                               "discountAmount": 0.12, "netAmount": 0.0}}
    assert bill["readable"] is False and bill["remaining_included_minutes"] is None
    d = decided(bill)
    assert d["decision"] == DG.NO_DISPATCH
    assert any(r.startswith("FAIL_CLOSED: remaining included Actions minutes not readable (NOT_EXPOSED")
               for r in d["reasons"])
    assert d["billing"]["usage_evidence"]["verified"] is True


def test_the_usd_0_budget_is_never_assumed(monkeypatch):
    for response in [(200, {"usageItems": [usage_item()]}), (410, "gh: moved (HTTP 410)")]:
        bill, _ = read_with(monkeypatch, response)
        assert bill["budget_usd_zero"] is False
        assert any(r.startswith("FAIL_CLOSED: an Actions budget of USD 0 that stops usage is not verified "
                                "(NOT_EXPOSED: GitHub's budgets API is organization-only")
                   for r in decided(bill)["reasons"])


def test_only_proven_billing_controls_open_the_gate():
    proven = {"readable": True, "remaining_included_minutes": 2000, "budget_usd_zero": True}
    assert decided(proven)["decision"] == DG.DISPATCH
    for missing in ({**proven, "budget_usd_zero": False}, {**proven, "readable": False},
                    {"readable": True, "remaining_included_minutes": 2000}, {}):
        assert decided(missing)["decision"] == DG.NO_DISPATCH


def test_no_token_ever_reaches_the_record(monkeypatch):
    bill, _ = read_with(monkeypatch, (403, f"gh: token {TOKEN} lacks Plan (HTTP 403)"))
    rec = decided(bill)
    assert TOKEN not in json.dumps(rec) and TOKEN not in json.dumps(bill)
    assert "***" in bill["usage_evidence"]["detail"]


# -- caps and replay -------------------------------------------------------------------------------------

PROVEN = {"readable": True, "remaining_included_minutes": 100000, "budget_usd_zero": True}


def test_a_re_run_attempt_of_a_node_or_closure_job_never_runs_again():
    assert decided(PROVEN, attempt=1)["decision"] == DG.DISPATCH
    d = decided(PROVEN, attempt=2)
    assert d["decision"] == DG.NO_DISPATCH and any(r.startswith("RE_RUN") for r in d["reasons"])


def test_earlier_attempts_count_toward_the_4000_minute_cap():
    ok = OP.decide(state(billing=PROVEN), [aux(1, minutes=100)], "PC-A2", 1, earlier_minutes=3000)
    assert ok["decision"] == DG.DISPATCH and ok["total_minutes_ledger"] == 3100  # + 2 x 180 = 3460
    d = OP.decide(state(billing=PROVEN), [aux(1, minutes=100)], "PC-A2", 1, earlier_minutes=3600)
    assert d["decision"] == DG.NO_DISPATCH and any(r.startswith("CAP: minutes") for r in d["reasons"])


def fake_api(runs_by_workflow: dict, jobs_by_run: dict, seen: list):
    def api(path, token_env=None):
        seen.append(path)
        for wf, runs in runs_by_workflow.items():
            if f"/workflows/{wf}/runs" in path:
                return {"workflow_runs": runs}
        rid = int(path.split("/runs/")[1].split("/")[0])
        return {"jobs": jobs_by_run[rid]}
    return api


def job(attempt, start, end):
    return {"status": "completed", "run_attempt": attempt, "started_at": f"2026-10-12T{start}:00Z",
            "completed_at": f"2026-10-12T{end}:00Z"}


def test_guard_and_closure_minutes_count_every_attempt(monkeypatch):
    seen = []
    runs = {OP.GUARD_WORKFLOW: [{"id": 5, "status": "completed", "conclusion": "failure", "run_attempt": 2,
                                 "created_at": "2026-10-11T23:36:08Z"}], OP.CLOSURE_WORKFLOW: []}
    monkeypatch.setattr(DG, "_api", fake_api(runs, {5: [job(1, "00:00", "00:01"), job(2, "00:02", "00:03")]}, seen))
    [r] = OP.read_aux_runs("o/r", None)
    assert r["minutes"] == 2 and any("/runs/5/jobs" in p and "filter=all" in p for p in seen)


def test_earlier_attempts_of_a_re_run_node_run_are_counted(monkeypatch):
    seen = []
    runs = {DG.WORKFLOW_FILE: [{"id": 9, "run_attempt": 2, "display_title": "AUTH2 PC-A1 part 1"},
                               {"id": 8, "run_attempt": 1, "display_title": "AUTH2 D0 part 1"}]}
    jobs = {9: [job(1, "00:00", "01:00"), job(2, "02:00", "02:01")]}
    monkeypatch.setattr(DG, "_api", fake_api(runs, jobs, seen))
    assert OP.earlier_attempt_minutes("o/r") == 60  # the latest attempt is dispatch_guard's; run 8 has none
    assert not any("/runs/8/" in p for p in seen)
    runs[DG.WORKFLOW_FILE][0]["display_title"] = "something else"
    with pytest.raises(RuntimeError):
        OP.earlier_attempt_minutes("o/r")
