"""AUTH-2-DISCOVERY-QUALIFICATION-2 readiness gate (.github/gates/auth2q2_readiness.py), RT-8 and RT-9, and the
readiness plan (research/auth2q2/plan.py), against fixtures and an in-memory Actions API.

Every readiness run starts with this gate, so each refusal below is a way a run could start that it must not:
not the Owner, not this month's verified billing, a re-run, a moved main, another run active, a ledger the API
cannot reconcile, the 300-minute cap or the R_m reserve, or a test whose snapshot precondition does not hold.
The billing token is used for the usage report only and never reaches the workflow-token calls.

PAPER / RESEARCH ONLY. Nothing here dispatches or calls GitHub.
"""

from __future__ import annotations

import copy
import io
import json
import math
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import auth2_operator as OP
import auth2q2_readiness as R
from auth2 import dispatch_guard as DG
from auth2q2 import plan as PL
from auth2q2 import release as RL

SLUG = "algamal119933-ux/trading-lab-os-sandbox"
SHA = "a" * 40
OLD = "b" * 40          # an earlier readiness commit
NOW = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
OWNER = {"login": OP.OWNER_LOGIN, "id": OP.OWNER_ID}
DIGEST = "sha256:" + "d" * 64
TAG = RL.tag_for(DIGEST, SHA)
OLD_TAG = RL.tag_for(DIGEST, OLD)


@pytest.fixture(autouse=True)
def _outside_actions(monkeypatch):
    """The CLIs stamp GitHub Actions' run identity into their records; in CI those variables belong to the CI
    run, not to the fixtures, so every test here starts without them and sets what it needs."""
    for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "GITHUB_EVENT_PATH"):
        monkeypatch.delenv(k, raising=False)


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def usage(period: str = "2026-10", storage: float = 10.0, net: float = 0.0, linux: float = 100.0) -> dict:
    return {"verified": True, "class": "USAGE_VERIFIED", "status": 200, "period": period,
            "endpoint": OP.USAGE_ENDPOINT.format(owner=OP.OWNER_LOGIN),
            "actions": {"Actions Linux": {"quantity": linux, "netAmount": net, "unitType": "Minutes",
                                          "grossAmount": 0.6, "discountAmount": 0.6},
                        R.STORAGE_SKU: {"quantity": storage, "netAmount": 0.0, "unitType": "GigabyteHours",
                                        "grossAmount": 0.0, "discountAmount": 0.0}}}


def run_obj(test: str = "RT-4", rid: int = 9001, *, created: datetime = NOW, attempt: int = 1, sha: str = SHA,
            actor=OWNER, trig=OWNER, status: str = "in_progress") -> dict:
    return {"id": rid, "run_attempt": attempt, "head_sha": sha, "head_branch": "main", "event": "workflow_dispatch",
            "path": f".github/workflows/{PL.workflow_of(test)}", "display_title": PL.TITLE.format(test=test),
            "repository": {"full_name": SLUG}, "created_at": iso(created), "status": status, "conclusion": None,
            "actor": dict(actor), "triggering_actor": dict(trig)}


def event(test: str = "RT-4", remaining: str = "1200", budget: str = "CONFIRMED", stop: str = "CONFIRMED",
          sender=OWNER) -> dict:
    return {"inputs": {"test": test, OP.MINUTES_INPUT: remaining, "actions_budget_usd_zero": budget,
                       "stop_usage_enabled": stop}, "sender": dict(sender)}


def job(name: str, minutes: float = 2.0, *, attempt: int = 1, start: datetime = NOW - timedelta(days=1),
        conclusion: str = "success", status: str = "completed") -> dict:
    return {"name": name, "run_attempt": attempt, "status": status, "conclusion": conclusion,
            "started_at": iso(start),  # a second short of ``minutes``: whole minutes bill exactly that
            "completed_at": iso(start + timedelta(minutes=minutes, seconds=-1)) if status == "completed" else None, "steps": [{"name": "Set up job"}], "runner_id": 7, "runner_name": "GitHub Actions 7"}


def past_run(rid: int, test: str, jobs: list[dict], *, created: datetime = NOW - timedelta(days=1),
             conclusion: str = "success", attempt: int = 1) -> dict:
    r = run_obj(test, rid, created=created, attempt=attempt, status="completed")
    r.update(conclusion=conclusion, jobs=jobs)
    return r


def release(**kw) -> dict:
    rel = {"id": 5, "tag_name": TAG, "draft": False, "prerelease": False, "immutable": True,
           "author": {"login": RL.BOT}, "target_commitish": SHA,
           "assets": [{"id": 10 + i, "name": n, "size": 100 + i, "state": "uploaded",
                       "digest": DIGEST if n == RL.MANIFEST else "sha256:" + str(i) * 64}
                      for i, n in enumerate(RL.ASSETS)]}
    rel.update(kw)
    return rel


def facts(test: str = "RT-4", **kw) -> dict:
    f = {"test": test, "slug": SLUG, "now": NOW, "errors": [],
         "env": {"GITHUB_SHA": SHA, "GITHUB_RUN_ID": "9001", "GITHUB_RUN_ATTEMPT": "1"},
         "run": run_obj(test), "event": event(test), "usage": usage(), "main_sha": SHA, "runs": [],
         "auth2_active": [], "records": [], "releases": [release()], "tag_commits": {TAG: SHA}}
    f.update(kw)
    for r in f["records"] if isinstance(f["records"], list) else []:  # each record's run, in the history
        if r.get("run_id") not in {x.get("id") for x in f["runs"]}:
            at = datetime.strptime(r["checked_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            f["runs"] = [*f["runs"], past_run(r["run_id"], r["test"], [job(PL.GATE_JOB, 1, start=at)], created=at)]
    return f


def decide(f: dict) -> dict:
    return R.decide(copy.deepcopy(f))


def admitted(test: str, rid: int, *, at: datetime, remaining: int = 1200, a_m: int | None = None) -> dict:
    """The gate record an admitted run of ``test`` wrote at ``at``."""
    f = facts(test, run=run_obj(test, rid, created=at), event=event(test, str(remaining)), now=at,
              env={"GITHUB_SHA": SHA, "GITHUB_RUN_ID": str(rid), "GITHUB_RUN_ATTEMPT": "1"},
              releases=[] if test == "RT-1" else [release()])
    rec = decide(f)
    assert rec["decision"] == DG.DISPATCH, rec["reasons"]
    if a_m is not None:
        rec["reserve"]["a_m"], rec["reserve"]["r_m"] = a_m, DG.reserve(a_m)
    return rec


# -- the plan ---------------------------------------------------------------------------------------

def test_the_plan_names_every_test_once_with_its_timeouts_and_a_verdict_job():
    assert PL.RUN_TESTS == tuple(f"RT-{i}" for i in range(1, 12)) and PL.ALL_TESTS[0] == "RT-0"
    assert sorted(PL.DISPATCH_ORDER) == sorted(PL.RUN_TESTS)
    assert PL.DISPATCH_ORDER.index("RT-8") == len(PL.DISPATCH_ORDER) - 1  # after RT-7 (review section 4)
    assert PL.DISPATCH_ORDER[0] == "RT-1"
    for t, (wf, jobs, verdict) in PL.TESTS.items():
        assert set(verdict) <= set(jobs) and PL.GATE_JOB not in jobs
        assert all(j in PL.JOBS[wf] for j in jobs)
    # review section 4's bounds
    j = PL.JOBS
    assert j[PL.PREPARE_WORKFLOW]["Cold preparation"] == 90
    assert j[PL.READINESS_WORKFLOW]["RT-4 cold restore and D0 data path"] == 60
    assert j[PL.READINESS_WORKFLOW]["RT-11 engine data path"] == 60
    assert j[PL.READINESS_WORKFLOW]["RT-10 probe"] == 2
    assert all(t <= 10 for n, t in j[PL.READINESS_WORKFLOW].items() if n.startswith(("RT-7", "RT-8", "RT-9")))


def test_the_planned_maxima_are_every_job_at_timeout_plus_one():
    want = {"RT-1": 11 + 91 + 16, "RT-2": 11 + 91, "RT-3": 11 + 16 + 11, "RT-4": 11 + 61, "RT-5": 11 + 21 + 21,
            "RT-6": 11 + 16 + 16 + 11, "RT-7": 11 + 11 + 11 + 11, "RT-8": 11 + 11, "RT-9": 11 + 11,
            "RT-10": 11 + 3 + 11, "RT-11": 11 + 61}
    assert {t: PL.planned_max(t) for t in PL.RUN_TESTS} == want
    assert PL.totals() == {"planned_max": sum(want.values()), "expected": sum(PL.EXPECTED.values()), "cap": 300}
    assert sum(PL.EXPECTED.values()) <= 160 < PL.READINESS_CAP
    # every single run fits an empty ledger with room for one more gate
    assert all(PL.planned_max(t) + PL.NEXT_GATE_RESERVE <= PL.READINESS_CAP for t in PL.RUN_TESTS)


# -- the decision -----------------------------------------------------------------------------------

def test_a_clean_owner_dispatch_is_admitted_and_records_its_evidence():
    rec = decide(facts())
    assert rec["decision"] == DG.DISPATCH and rec["reasons"] == []
    ev = rec["billing"]["owner_evidence"]
    assert ev["schema"] == R.EVIDENCE_SCHEMA and ev["test"] == "RT-4" and ev["run_id"] == 9001
    assert ev["evidence_digest"] == OP.evidence_digest(ev)
    assert rec["billing"]["remaining_included_minutes"] == 1200 and rec["billing"]["budget_usd_zero"] is True
    assert rec["reserve"] == {"a_m": 1200, "r_m": 500, "first_run_id": 9001, "remaining": 1200,
                              "planned_max": PL.planned_max("RT-4")}
    assert rec["ledger"]["total_if_admitted"] == PL.planned_max("RT-4") + PL.NEXT_GATE_RESERVE
    assert rec["release"]["tag"] == TAG


@pytest.mark.parametrize("change, reason", [
    (lambda f: f.update(main_sha="b" * 40), "PROVENANCE"),
    (lambda f: f.update(main_sha=None), "PROVENANCE"),
    (lambda f: f["env"].update(GITHUB_SHA="c" * 40), "PROVENANCE"),
    (lambda f: f["env"].update(GITHUB_RUN_ID="1"), "PROVENANCE"),
    (lambda f: f["run"].update(path=".github/workflows/auth2q2-prepare.yml"), "OWNER_EVIDENCE_PROVENANCE"),
    (lambda f: f["run"].update(event="push"), "OWNER_EVIDENCE_PROVENANCE"),
    (lambda f: f["run"].update(head_branch="feature"), "OWNER_EVIDENCE_PROVENANCE"),
    (lambda f: f["run"].update(display_title="AUTH2Q2-READINESS RT-5"), "OWNER_EVIDENCE_PROVENANCE"),
    (lambda f: f["run"].update(repository={"full_name": "x/y"}), "OWNER_EVIDENCE_WRONG_REPOSITORY"),
    (lambda f: (f["run"].update(run_attempt=2), f["env"].update(GITHUB_RUN_ATTEMPT="2")), "RE_RUN"),
    (lambda f: f["env"].update(GITHUB_RUN_ATTEMPT="2"), "RE_RUN"),
    (lambda f: f["run"].update(triggering_actor={"login": "x", "id": 1}), "OWNER_EVIDENCE_ACTOR_MISMATCH"),
    (lambda f: f["run"].update(actor={"login": OP.OWNER_LOGIN, "id": 2}), "OWNER_EVIDENCE_ACTOR_MISMATCH"),
    (lambda f: f["event"].update(sender={"login": "x", "id": 1}), "OWNER_EVIDENCE_ACTOR_MISMATCH"),
    (lambda f: f["event"]["inputs"].update(test="RT-5"), "OWNER_EVIDENCE_WRONG_TEST"),
    (lambda f: f.update(event={}), "OWNER_EVIDENCE_MISSING"),
    (lambda f: f["event"]["inputs"].update({OP.MINUTES_INPUT: "1,200"}), "OWNER_EVIDENCE_REMAINING_INVALID"),
    (lambda f: f["event"]["inputs"].update({OP.MINUTES_INPUT: "-5"}), "OWNER_EVIDENCE_REMAINING_INVALID"),
    (lambda f: f["event"]["inputs"].update({OP.MINUTES_INPUT: "01200"}), "OWNER_EVIDENCE_REMAINING_INVALID"),
    (lambda f: f["event"]["inputs"].update({OP.MINUTES_INPUT: ""}), "OWNER_EVIDENCE_MISSING"),
    (lambda f: f["event"]["inputs"].update(actions_budget_usd_zero="NOT_CONFIRMED"), "BUDGET_NOT_CONFIRMED"),
    (lambda f: f["event"]["inputs"].update(stop_usage_enabled="NOT_CONFIRMED"), "STOP_USAGE_NOT_CONFIRMED"),
    (lambda f: f["event"]["inputs"].update(stop_usage_enabled="yes"), "OWNER_EVIDENCE_MALFORMED"),
    (lambda f: f.update(usage={"verified": False, "class": "TOKEN_MISSING", "period": "2026-10",
                               "endpoint": OP.USAGE_ENDPOINT.format(owner=OP.OWNER_LOGIN)}),
     "OWNER_EVIDENCE_USAGE_NOT_VERIFIED"),
    (lambda f: f.update(usage={"verified": False, "class": "TOKEN_MISSING", "period": "2026-10",
                               "endpoint": OP.USAGE_ENDPOINT.format(owner=OP.OWNER_LOGIN)}),
     "FAIL_CLOSED: the billing state is not readable"),
    (lambda f: f.update(usage={"verified": False, "class": "NOT_READ"}), "OWNER_EVIDENCE_MALFORMED"),
    (lambda f: f.update(usage=usage(period="2026-09")), "OWNER_EVIDENCE_WRONG_MONTH"),
    (lambda f: f["run"].update(created_at="2026-09-30T23:59:59Z"), "OWNER_EVIDENCE_WRONG_MONTH"),
    (lambda f: f.update(auth2_active=[38286502721]), "SERIAL"),
    (lambda f: f.update(runs=[{**run_obj("RT-5", 9000), "jobs": []}]), "SERIAL"),
    (lambda f: f.update(errors=["FAIL_CLOSED: the run history is unreadable (HTTP 502)"]), "FAIL_CLOSED"),
    (lambda f: f.update(records="HTTP 500"), "FAIL_CLOSED: earlier gate records"),
    (lambda f: f.update(releases="HTTP 500"), "FAIL_CLOSED: the snapshot releases"),
    (lambda f: f.update(releases=[]), "SNAPSHOT"),
    (lambda f: f.update(releases=[release(immutable=False)]), "SNAPSHOT"),
    (lambda f: f.update(releases=[release(assets=release()["assets"][:2])]), "SNAPSHOT"),
    (lambda f: f.update(releases=[release(author={"login": OP.OWNER_LOGIN})]), "SNAPSHOT"),
    # this readiness execution's snapshot only: never another commit's, never an ambiguous or unanchored one
    (lambda f: f.update(releases=[release(tag_name=OLD_TAG, target_commitish=OLD)]),
     "SNAPSHOT: RT-4 reads the readiness commit's snapshot: 0 published"),
    (lambda f: f.update(releases=[release(), release(id=6, tag_name=RL.tag_for("sha256:" + "e" * 64, SHA))]),
     "2 published snapshot releases for the readiness commit"),
    (lambda f: f.update(releases=[release(target_commitish=OLD)]), "targets"),
    (lambda f: f.update(tag_commits={TAG: OLD}), "points at"),
    (lambda f: f.update(tag_commits={}), "points at"),
    (lambda f: f.update(releases=[release(tag_name=RL.TAG_PREFIX + "d" * 64)]), "0 published"),
    (lambda f: f.update(now=NOW + timedelta(minutes=16)), "STALE_EVIDENCE"),
    (lambda f: f.update(runs=[{**past_run(9000, "RT-5", [job(PL.GATE_JOB, 1)]),
                                "updated_at": iso(NOW + timedelta(seconds=30))}], now=NOW + timedelta(minutes=1)),
     "STALE_EVIDENCE"),
    (lambda f: f.update(records=[admitted("RT-1", 8000, at=NOW - timedelta(days=3))],
                        runs=[past_run(8000, "RT-1", [])]), "a readiness run is missing from the history"),
])
def test_every_refusal_is_a_way_a_run_must_not_start(change, reason):
    f = facts()
    change(f)
    rec = decide(f)
    assert rec["decision"] == DG.NO_DISPATCH
    assert any(r.startswith(reason) or reason in r for r in rec["reasons"]), rec["reasons"]


def test_billing_the_operator_cannot_read_refuses_even_beside_valid_evidence(monkeypatch):
    monkeypatch.setattr(R.OP, "billing_state", lambda usage, owner: {
        "readable": False, "remaining_included_minutes": None, "budget_usd_zero": False, "reason": "unreadable",
        "usage_evidence": usage, "owner_evidence": owner["evidence"], "owner_evidence_problems": []})
    rec = decide(facts())
    assert rec["decision"] == DG.NO_DISPATCH
    assert rec["reasons"] == ["FAIL_CLOSED: the billing state is not readable (unreadable)"]


@pytest.mark.parametrize("change, problem", [
    (dict(test="RT-5"), "OWNER_EVIDENCE_WRONG_TEST"),
    (dict(stop_usage_confirmed=False), "OWNER_EVIDENCE_STOP_USAGE_NOT_CONFIRMED"),
    (dict(budget_usd_zero_confirmed=False), "OWNER_EVIDENCE_BUDGET_NOT_CONFIRMED"),
    (dict(run_attempt=2), "OWNER_EVIDENCE_REPLAYED"),
    (dict(usage_api_verified=False), "OWNER_EVIDENCE_USAGE_NOT_VERIFIED"),
])
def test_owner_evidence_is_checked_field_by_field_not_only_by_its_digest(change, problem):
    ev = decide(facts())["billing"]["owner_evidence"]
    kw = dict(slug=SLUG, run_id=9001, main_sha=SHA, test="RT-4", month="2026-10")
    assert R.evidence_problems(ev, **kw) == []
    resealed = {**ev, **change}
    resealed["evidence_digest"] = OP.evidence_digest(resealed)
    assert [p.split(":")[0] for p in R.evidence_problems(resealed, **kw)] == [problem]
    stale = {**ev, "attested_utc": iso(NOW - timedelta(minutes=1))}  # same month, digest not recomputed
    assert [p.split(":")[0] for p in R.evidence_problems(stale, **kw)] == ["OWNER_EVIDENCE_DIGEST_MISMATCH"]


def test_an_unreadable_run_is_refused_and_nothing_about_it_is_trusted():
    rec = decide(facts(run={}, event={}))
    assert rec["decision"] == DG.NO_DISPATCH and rec["billing"]["owner_evidence"] is None


def test_rt1_runs_again_at_the_same_commit_and_at_a_new_one_but_never_beside_an_ambiguous_snapshot():
    rt1 = dict(run=run_obj("RT-1"), event=event("RT-1"))
    assert decide(facts("RT-1", releases=[], **rt1))["decision"] == DG.DISPATCH
    # again at the same commit: RT-1 verifies the release it finds and changes nothing (release.py)
    assert decide(facts("RT-1", **rt1))["decision"] == DG.DISPATCH
    # at a new commit, beside an earlier commit's release: RT-1 prepares and publishes this commit's own
    old = release(tag_name=OLD_TAG, target_commitish=OLD)
    rec = decide(facts("RT-1", releases=[old], **rt1))
    assert rec["decision"] == DG.DISPATCH and rec["release"] is None
    two = [release(), release(id=6, tag_name=RL.tag_for("sha256:" + "e" * 64, SHA))]
    rec = decide(facts("RT-1", releases=two, **rt1))
    assert rec["decision"] == DG.NO_DISPATCH and rec["reasons"][0].startswith("SNAPSHOT_AMBIGUOUS")
    assert decide(facts("RT-1", releases=[old, two[1]], **rt1))["decision"] == DG.DISPATCH
    for t in ("RT-9", "RT-10"):
        assert decide(facts(t, run=run_obj(t), event=event(t), releases=[]))["decision"] == DG.DISPATCH
    for t in sorted(PL.NEEDS_SNAPSHOT):
        assert decide(facts(t, run=run_obj(t), event=event(t), releases=[]))["decision"] == DG.NO_DISPATCH, t


# -- the ledger and the cap -------------------------------------------------------------------------

def test_the_ledger_counts_every_job_of_every_attempt_at_its_billed_minutes():
    runs = [past_run(1, "RT-1", [job(PL.GATE_JOB, 1.2), job("Cold preparation", 31.0),
                                 job("Snapshot release (contents: write)", 2.5)]),
            past_run(2, "RT-6", [job(PL.GATE_JOB, 0.5), job("RT-6 corrupted restored file", 1.1, conclusion="failure"),
                                 job("RT-6 asset with the wrong digest", 0.9, conclusion="failure"),
                                 job("RT-6 classify", 0.4)]),
            past_run(3, "RT-7", [job(PL.GATE_JOB, 0.5), job(PL.GATE_JOB, 0.5, attempt=2, conclusion="failure")],
                     attempt=2, conclusion="failure"),
            past_run(4, "RT-4", [job(PL.GATE_JOB, 0.6, conclusion="failure"),
                                 {**job("RT-4 cold restore and D0 data path"), "conclusion": "skipped", "steps": [],
                                  "runner_id": None, "runner_name": None}], conclusion="failure"),
            past_run(5, "RT-5", [], conclusion="cancelled")]
    led = R.ledger(runs, None)
    assert [r["minutes"] for r in led["runs"]] == [2 + 31 + 3, 1 + 2 + 1 + 1, 1 + 1, 1 + 0, 0]
    assert led["minutes"] == 36 + 5 + 2 + 1 and led["problems"] == []
    rec = decide(facts(runs=runs))
    assert rec["decision"] == DG.DISPATCH and rec["ledger"]["minutes"] == 44
    assert rec["ledger"]["total_if_admitted"] == 44 + PL.planned_max("RT-4") + 11


def test_unfinished_unknown_or_unreconcilable_jobs_never_count_low():
    running = past_run(1, "RT-4", [job(PL.GATE_JOB, 1), job("RT-4 cold restore and D0 data path", status="in_progress")])
    running["status"] = "in_progress"
    m, _rows, p = R.run_minutes(running, running["jobs"])
    assert m == 1 + 61 and p == []
    queued = {**run_obj("RT-5", 2), "status": "queued"}
    assert R.run_minutes(queued, []) == (PL.GATE_TIMEOUT + 1, [], [])
    m, _rows, p = R.run_minutes(past_run(3, "RT-4", [job("Some other job")]), [job("Some other job")])
    assert p and "not in the readiness plan" in p[0]
    m, _rows, p = R.run_minutes(past_run(4, "RT-4", [], conclusion="failure"), [])
    assert p and "cannot be reconciled" in p[0]
    other = {**past_run(5, "RT-4", []), "path": ".github/workflows/ci.yml"}
    assert R.run_minutes(other, [])[2]
    # a job of the wrong workflow's plan is unknown there
    m, _rows, p = R.run_minutes(past_run(6, "RT-1", [job("RT-4 cold restore and D0 data path")]),
                                [job("RT-4 cold restore and D0 data path")])
    assert p
    rec = decide(facts(runs=[past_run(3, "RT-4", [job("Some other job")])]))
    assert rec["decision"] == DG.NO_DISPATCH and "not in the readiness plan" in rec["reasons"][0]


def _minutes_runs(total: int) -> list[dict]:
    out, i = [], 0
    while total > 0:
        m = min(total, 10)
        i += 1
        out.append(past_run(100 + i, "RT-9", [job(PL.GATE_JOB, m)]))
        total -= m
    return out


def test_the_cap_counts_this_run_and_one_more_gate_and_refuses_one_minute_over():
    planned = PL.planned_max("RT-11")
    edge = PL.READINESS_CAP - planned - PL.NEXT_GATE_RESERVE
    t = "RT-11"
    ok = decide(facts(t, run=run_obj(t), event=event(t), runs=_minutes_runs(edge)))
    assert ok["decision"] == DG.DISPATCH and ok["ledger"]["total_if_admitted"] == 300
    over = decide(facts(t, run=run_obj(t), event=event(t), runs=_minutes_runs(edge + 1)))
    assert over["decision"] == DG.NO_DISPATCH and over["reasons"][0].startswith("CAP: readiness ledger")


def test_the_cap_is_not_a_park_even_beside_a_reserve_breach():
    f = facts(runs=_minutes_runs(300), event=event(remaining="510"))
    rec = decide(f)
    assert rec["decision"] == DG.NO_DISPATCH and any(r.startswith("RESERVE") for r in rec["reasons"])


# -- the monthly reserve --------------------------------------------------------------------------------

def test_the_reserve_parks_and_a_m_comes_from_the_months_first_admitted_run():
    planned = PL.planned_max("RT-4")
    edge = decide(facts(event=event(remaining=str(planned + 500))))
    assert edge["decision"] == DG.DISPATCH and edge["reserve"]["r_m"] == 500
    park = decide(facts(event=event(remaining=str(planned + 499))))
    assert park["decision"] == DG.PARK and park["reasons"][0].startswith("RESERVE")
    # A_m = 5,000 at the month's first admitted run: R_m 1,000, whatever is stated now
    first = admitted("RT-1", 8000, at=NOW - timedelta(days=3), remaining=5000)
    rec = decide(facts(records=[first], event=event(remaining=str(planned + 999))))
    assert rec["reserve"] == {"a_m": 5000, "r_m": 1000, "first_run_id": 8000, "remaining": planned + 999,
                              "planned_max": planned}
    assert rec["decision"] == DG.PARK
    assert decide(facts(records=[first], event=event(remaining=str(planned + 1000))))["decision"] == DG.DISPATCH


def reseal(ev: dict, **change) -> None:
    """Edit Owner evidence and recompute its digest, as a forger would."""
    ev.update(change)
    ev["evidence_digest"] = OP.evidence_digest(ev)


@pytest.mark.parametrize("edit", [
    lambda r: r["reserve"].update(r_m=499),
    lambda r: r["reserve"].update(a_m=4000),
    lambda r: r["reserve"].update(a_m=-1),
    lambda r: r["reserve"].update(first_run_id=1),
    lambda r: r.update(month="2026-09"),
    lambda r: r.update(decision=DG.PARK),
    lambda r: r.update(schema="OTHER"),
    lambda r: r["billing"]["owner_evidence"].update(remaining_included_linux_minutes=4000),
    lambda r: r["billing"].update(owner_evidence=None),
    lambda r: r["billing"]["owner_evidence"].update(attested_utc=iso(NOW - timedelta(days=3, minutes=1))),
    lambda r: reseal(r["billing"]["owner_evidence"], test="RT-2"),
    lambda r: reseal(r["billing"]["owner_evidence"], stop_usage_confirmed=False),
])
def test_a_first_record_that_does_not_rest_on_its_own_evidence_fails_closed(edit):
    first = admitted("RT-1", 8000, at=NOW - timedelta(days=3), remaining=5000)
    edit(first)
    rec = decide(facts(records=[first]))
    assert rec["decision"] == DG.NO_DISPATCH
    assert any(r.startswith("FAIL_CLOSED: the month's first admitted") for r in rec["reasons"])


# -- RT-8's baseline ------------------------------------------------------------------------------------

def test_rt8_needs_a_billing_reading_of_this_month_six_hours_old():
    t = "RT-8"
    young = admitted("RT-1", 8000, at=NOW - timedelta(hours=5, minutes=59))
    rec = decide(facts(t, run=run_obj(t), event=event(t), records=[young]))
    assert rec["decision"] == DG.NO_DISPATCH and rec["reasons"][0].startswith("RT8_BASELINE")
    old = admitted("RT-1", 7999, at=NOW - timedelta(hours=6))
    rec = decide(facts(t, run=run_obj(t), event=event(t), records=[old, young]))
    assert rec["decision"] == DG.DISPATCH and rec["rt8_baseline_run_id"] == 7999


# -- RT-8 -----------------------------------------------------------------------------------------------

def _rt8(**kw):
    base = admitted("RT-1", 8000, at=NOW - timedelta(hours=30))
    own = decide(facts("RT-8", run=run_obj("RT-8"), event=event("RT-8"), records=[base]))
    own["billing"]["usage_evidence"] = usage(storage=10.0 + 30 * 0.06, linux=245.0)
    args = {"own": own, "base": base, "rel": release(),
            "artifacts": [{"name": "auth2q2-gate", "size_in_bytes": 2000, "expires_at": "2027-01-18T00:00:00Z",
                           "expired": False},
                          {"name": "auth2-D0-p1", "size_in_bytes": 1127, "expires_at": "2027-01-10T00:00:00Z",
                           "expired": False}],
            "cache_usage": {"active_caches_size_in_bytes": 2 * 10 ** 9, "active_caches_count": 2}}
    args.update(kw)
    return R.rt8(**args)


def test_rt8_passes_on_two_clean_readings_an_immutable_release_and_small_storage():
    rec = _rt8()
    assert rec["result"] == "PASS", rec["problems"]
    assert rec["measurements"]["storage_rate_gb"] == pytest.approx(0.06)
    assert rec["measurements"]["hours_between_readings"] == 30.0
    assert rec["measurements"]["snapshot_release"] == {"address": DIGEST, "commit": SHA, "tag": TAG, "release_id": 5}


@pytest.mark.parametrize("change, check", [
    (lambda a: a["own"]["billing"].update(usage_evidence=usage(storage=10.0 + 30 * 1.0)),
     "no_storage_charge_from_the_release"),
    (lambda a: a["own"]["billing"].update(usage_evidence=usage(net=0.01)), "no_actions_charge"),
    (lambda a: a["own"]["billing"].update(usage_evidence=usage(period="2026-11")), "same_billing_month"),
    (lambda a: a["own"]["billing"]["usage_evidence"].update(verified=False), "both_readings_verified"),
    (lambda a: a.update(base={**a["base"], "checked_utc": iso(NOW - timedelta(hours=2))}),
     "readings_far_enough_apart"),
    (lambda a: a.update(base={}), "both_readings_verified"),
    (lambda a: a.update(rel=release(immutable=False)), "release_immutable"),
    (lambda a: a.update(rel=None), "release_immutable"),
    (lambda a: a.update(rel=release(tag_name=OLD_TAG, target_commitish=OLD)), "release_bound_to_this_commit"),
    (lambda a: a.update(rel=release(id=None)), "release_bound_to_this_commit"),
    (lambda a: a.update(rel={**release(), "expires_at": "2027-01-01T00:00:00Z"}), "release_has_no_expiry"),
    (lambda a: a["artifacts"].append({"name": "big", "size_in_bytes": 60 * 10 ** 6, "expired": False}),
     "artifact_storage_far_below_500_mb"),
    (lambda a: a["artifacts"].append({"name": "auth2q2-rt-RT-4", "size_in_bytes": 10, "expires_at": None}),
     "every_readiness_artifact_expires"),
    (lambda a: a.update(cache_usage={"active_caches_size_in_bytes": 11 * 1024 ** 3}), "cache_within_10_gb"),
    (lambda a: a.update(cache_usage={}), "cache_within_10_gb"),
    (lambda a: a["own"]["billing"].update(usage_evidence=usage(storage=10.0)), "second_reading_moved"),
    (lambda a: a["own"]["billing"]["usage_evidence"]["actions"].pop("Actions Linux"), "second_reading_moved"),
])
def test_rt8_fails_on_any_charge_storage_or_retention_finding(change, check):
    base = admitted("RT-1", 8000, at=NOW - timedelta(hours=30))
    own = decide(facts("RT-8", run=run_obj("RT-8"), event=event("RT-8"), records=[base]))
    own["billing"]["usage_evidence"] = usage(storage=10.0 + 30 * 0.06, linux=245.0)
    args = {"own": own, "base": base, "rel": release(),
            "artifacts": [{"name": "auth2q2-gate", "size_in_bytes": 2000, "expires_at": "2027-01-18T00:00:00Z",
                           "expired": False}],
            "cache_usage": {"active_caches_size_in_bytes": 2 * 10 ** 9}}
    change(args)
    rec = R.rt8(**args)
    assert rec["result"] == "FAIL" and rec["checks"][check] is False


# -- an in-memory Actions API, for collect(), the CLI and RT-9 ------------------------------------------

def zipped(obj: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("gate.json", json.dumps(obj))
    return buf.getvalue()


class FakeActions:
    def __init__(self, runs: list[dict], self_run: dict, *, releases=None, records=None, main=SHA, fail=()):
        self.slug = SLUG
        self.runs = {r["id"]: r for r in runs}
        self.self_run = self_run
        self.releases = releases if releases is not None else [release()]
        self.tags = {r["tag_name"]: RL.commit_of(r["tag_name"]) for r in self.releases}
        self.records = records or {}  # run id -> gate record
        self.main = main
        self.fail = set(fail)
        self.calls: list[str] = []

    def _page(self, items: list, path: str) -> list:
        page = int(path.split("page=")[-1]) if "page=" in path else 1
        return items[(page - 1) * 100: page * 100]

    def api(self, method, path, body=None):
        assert method == "GET", (method, path)
        self.calls.append(path)
        p = path.removeprefix(f"/repos/{SLUG}")
        if any(f in p for f in self.fail):
            return 502, "gh: Bad Gateway (HTTP 502)"
        if p == f"/actions/runs/{self.self_run['id']}":
            return 200, {k: v for k, v in self.self_run.items() if k != "jobs"}
        if p == "/git/ref/heads/main":
            return 200, {"object": {"sha": self.main}}
        if p.startswith("/actions/workflows/"):
            wf = p.split("/")[3]
            if wf not in (*PL.WORKFLOWS, *R.AUTH2_WORKFLOWS):
                return 404, "gh: Not Found (HTTP 404)"
            mine = [{k: v for k, v in r.items() if k != "jobs"} for r in self.runs.values()
                    if r["path"] == f".github/workflows/{wf}"]
            return 200, {"workflow_runs": self._page(mine, path), "total_count": len(mine)}
        if "/jobs" in p and p.startswith("/actions/runs/"):
            rid = int(p.split("/")[3])
            jobs = self.runs[rid].get("jobs") or []
            if "/attempts/" in p:
                n = int(p.split("/")[5])
                jobs = [j for j in jobs if j.get("run_attempt", 1) == n]
            return 200, {"jobs": self._page(jobs, path), "total_count": len(jobs)}
        if p.startswith("/actions/runs/") and p.split("?")[0].endswith("/artifacts"):
            rid = int(p.split("/")[3])
            arts = [{"id": rid, "name": R.GATE_ARTIFACT, "expired": False}] if rid in self.records else []
            return 200, {"artifacts": arts}
        if p.startswith("/releases?"):
            return 200, self._page(self.releases, path)
        if p.startswith("/git/ref/tags/"):
            tag = p.removeprefix("/git/ref/tags/")
            return (200, {"object": {"sha": self.tags[tag], "type": "commit"}}) if tag in self.tags else \
                (404, "gh: Not Found (HTTP 404)")
        raise AssertionError(f"unexpected GET {path}")

    def api_bytes(self, path):
        rid = int(path.split("/")[-2])
        return 200, zipped(self.records[rid])


def world(test: str = "RT-4", *, runs=(), **kw) -> tuple[FakeActions, dict]:
    me = run_obj(test)
    me["jobs"] = [job(PL.GATE_JOB, status="in_progress")]
    fa = FakeActions([*runs, me], me, **kw)
    return fa, me


@pytest.fixture()
def env(monkeypatch, tmp_path):
    def set_event(test="RT-4", **kw):
        p = tmp_path / "event.json"
        p.write_text(json.dumps(event(test, **kw)))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(p))
    monkeypatch.setenv("GITHUB_SHA", SHA)
    monkeypatch.setenv("GITHUB_RUN_ID", "9001")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    set_event()
    return set_event


def reader(seen: list):
    def read(owner, token_env, now):
        seen.append((owner, token_env, now))
        return usage()
    return read


def test_collect_reads_the_run_the_event_the_ledger_the_records_and_the_releases(env):
    first = admitted("RT-1", 8000, at=NOW - timedelta(days=3), remaining=5000)
    r1 = past_run(8000, "RT-1", [job(PL.GATE_JOB, 1), job("Cold preparation", 30),
                                 job("Snapshot release (contents: write)", 2)], created=NOW - timedelta(days=3))
    fa, _me = world(runs=[r1], records={8000: first})
    env(remaining="1050")
    seen = []
    f = R.collect(fa, "RT-4", NOW, reader(seen))
    assert seen == [(OP.OWNER_LOGIN, "AUTH2_BILLING_TOKEN", NOW)]
    assert f["errors"] == [] and f["main_sha"] == SHA and f["auth2_active"] == []
    assert [r["id"] for r in f["runs"]] == [8000, 9001] and f["records"] == [first]
    rec = R.decide(f)
    assert rec["decision"] == DG.PARK  # remaining 1,050 - 72 < R_m 1,000 from A_m 5,000
    assert rec["reserve"]["a_m"] == 5000 and rec["ledger"]["minutes"] == 1 + 30 + 2


def test_collect_fails_closed_when_the_api_does(env):
    fa, _ = world(fail=("/jobs",))
    rec = R.decide(R.collect(fa, "RT-4", NOW, reader([])))
    assert rec["decision"] == DG.NO_DISPATCH and "run history is unreadable" in rec["reasons"][0]
    fa, _ = world(fail=("/releases",))
    rec = R.decide(R.collect(fa, "RT-4", NOW, reader([])))
    assert rec["decision"] == DG.NO_DISPATCH and any("snapshot releases are unreadable" in r for r in rec["reasons"])
    r1 = past_run(8000, "RT-1", [job(PL.GATE_JOB, 1)], created=NOW - timedelta(days=3))
    fa, _ = world(runs=[r1], records={})  # admitted, but its gate record is gone
    rec = R.decide(R.collect(fa, "RT-4", NOW, reader([])))
    assert rec["decision"] == DG.NO_DISPATCH and any("earlier gate records" in r for r in rec["reasons"])


@pytest.mark.parametrize("change", [
    {"head_branch": "feature"}, {"event": "push"}, {"triggering_actor": {"login": "x", "id": 1}},
    {"actor": {"login": "x", "id": 1}}, {"display_title": "something else"}, {"repository": {"full_name": "x/y"}},
    {"path": ".github/workflows/other.yml"},
])
def test_a_run_the_api_does_not_show_as_the_owners_on_main_is_never_an_admitted_record(env, change):
    forged = admitted("RT-1", 8000, at=NOW - timedelta(days=3), remaining=99999)  # claims the Owner in its artifact
    r1 = past_run(8000, "RT-1", [job(PL.GATE_JOB, 1)], created=NOW - timedelta(days=3))
    r1.update(change)
    fa, _ = world(runs=[r1], records={8000: forged})
    assert R.admitted_records(fa, [r1], "2026-10", 9001) == []
    clean = past_run(8000, "RT-1", [job(PL.GATE_JOB, 1)], created=NOW - timedelta(days=3))
    assert R.admitted_records(fa, [clean], "2026-10", 9001) == [forged]
    other = {**forged, "test": "RT-2"}
    fa, _ = world(runs=[clean], records={8000: other})
    with pytest.raises(RuntimeError, match="not that run's"):
        R.admitted_records(fa, [clean], "2026-10", 9001)


def test_only_a_first_attempt_gate_admits_a_run_into_the_months_records(env):
    gates = [job(PL.GATE_JOB, 1, conclusion="failure"), job(PL.GATE_JOB, 1, attempt=2)]
    r1 = past_run(8000, "RT-1", gates, created=NOW - timedelta(days=3), conclusion="failure", attempt=2)
    fa, _ = world(runs=[r1], records={})  # a re-run's gate is not an admission; there is no record to read
    assert R.admitted_records(fa, [r1], "2026-10", 9001) == []
    r1["jobs"][0]["conclusion"] = "success"
    with pytest.raises(RuntimeError, match="holds 0 gate record"):
        R.admitted_records(fa, [r1], "2026-10", 9001)


def test_the_gate_cli_writes_annotates_and_exits_by_decision(env, monkeypatch, tmp_path, capsys):
    fa, _ = world()
    monkeypatch.setattr(R.RL, "GH", lambda slug: fa)
    monkeypatch.setattr(R.OP, "read_usage", lambda owner, token_env, now: usage(period=now.strftime("%Y-%m")))
    out = tmp_path / "gate.json"
    now = datetime.now(timezone.utc)
    fa.self_run["created_at"] = iso(now)
    rc = R.main(["gate", "--test", "RT-4", "--repo-slug", SLUG, "--out", str(out), "--annotate"])
    text = capsys.readouterr().out
    rec = json.loads(out.read_text())
    assert rc == 0 and rec["decision"] == DG.DISPATCH and "AUTH2Q2_READINESS_GATE = DISPATCH" in text
    notes = [{"title": R.GATE_TITLE, "message": line.split("::", 2)[2]} for line in text.splitlines()
             if line.startswith("::notice title=AUTH2Q2_GATE::")]
    assert [json.loads(b) for b in OP.decode_annotations(notes, R.GATE_TITLE)] == [rec]
    env(remaining="12OO")
    rc = R.main(["gate", "--test", "RT-4", "--repo-slug", SLUG, "--out", str(out)])
    assert rc == 3 and json.loads(out.read_text())["decision"] == DG.NO_DISPATCH


def test_the_billing_token_reaches_only_the_usage_report(monkeypatch):
    monkeypatch.setenv("AUTH2_BILLING_TOKEN", "github_pat_billing")
    assert "AUTH2_BILLING_TOKEN" not in RL.GH(SLUG)._env()
    calls = []
    monkeypatch.setattr(OP.subprocess, "run", lambda args, **kw: calls.append((args, kw["env"])) or
                        type("P", (), {"returncode": 0, "stdout": json.dumps({"usageItems": []}), "stderr": ""})())
    monkeypatch.setenv("GH_TOKEN", "workflow-token")
    monkeypatch.setenv("GITHUB_TOKEN", "workflow-token")
    got = OP.read_usage(OP.OWNER_LOGIN, "AUTH2_BILLING_TOKEN", NOW)
    assert got["verified"] is True
    (args, e), = calls
    assert e["GH_TOKEN"] == "github_pat_billing" and "GITHUB_TOKEN" not in e
    monkeypatch.delenv("AUTH2_BILLING_TOKEN")
    assert OP.read_usage(OP.OWNER_LOGIN, "AUTH2_BILLING_TOKEN", NOW)["class"] == "TOKEN_MISSING"
    assert len(calls) == 1  # no token: no request, and never the workflow token


# -- RT-9 ---------------------------------------------------------------------------------------------

def rt9_world(edit=None):
    r1 = past_run(8000, "RT-1", [job(PL.GATE_JOB, 1.5), job("Cold preparation", 29.2),
                                 job("Snapshot release (contents: write)", 2.1)], created=NOW - timedelta(days=2))
    r2 = past_run(8001, "RT-7", [job(PL.GATE_JOB, 0.5), job(PL.GATE_JOB, 0.7, attempt=2, conclusion="failure")],
                  created=NOW - timedelta(days=1), attempt=2, conclusion="failure")
    me = run_obj("RT-9")
    me["jobs"] = [job(PL.GATE_JOB, status="in_progress")]
    first = admitted("RT-1", 8000, at=NOW - timedelta(days=2))
    f = facts("RT-9", run=run_obj("RT-9"), event=event("RT-9"), runs=[r1, r2, me], records=[first], releases=[])
    own = decide(f)
    assert own["decision"] == DG.DISPATCH, own["reasons"]
    if edit:
        edit(r1, r2)
    return FakeActions([r1, r2, me], me), own


def test_rt9_reconciles_the_gate_ledger_with_the_api_and_every_breach_is_refused():
    fa, own = rt9_world()
    rec = R.rt9(fa, own)
    assert rec["result"] == "PASS", rec["problems"]
    assert rec["measurements"]["api_ledger"] == {8000: 2 + 30 + 3, 8001: 1 + 1}
    assert all(v["got"] == v["want"] for v in rec["measurements"]["fixtures"].values())
    assert any("/attempts/2/jobs" in c for c in fa.calls)  # read per attempt, not as the gate read it
    assert rec["checks"]["program_cap_breach_closes_cap_reached"] is True


def test_rt9_fails_when_the_api_disagrees_by_a_minute_or_a_run():
    fa, own = rt9_world(lambda r1, r2: r1["jobs"][1].update(completed_at="2026-10-18T12:31:00Z"))
    rec = R.rt9(fa, own)
    assert rec["result"] == "FAIL" and rec["checks"]["each_run_matches_to_the_minute"] is False
    fa, own = rt9_world()
    own["ledger"]["runs"] = own["ledger"]["runs"][:1]
    assert R.rt9(fa, own)["checks"]["same_runs_as_the_api"] is False


def test_rt9_fails_if_a_breach_were_admitted(monkeypatch):
    fa, own = rt9_world()
    real = R.decide
    monkeypatch.setattr(R, "decide", lambda f: {**real(f), "decision": DG.DISPATCH})
    rec = R.rt9(fa, own)
    assert rec["result"] == "FAIL" and rec["checks"]["fixture_cap_breach_refused"] is False


def test_the_r_m_rule_is_auth2s():
    for a_m in (0, 1, 2500, 2501, 10_000):
        assert DG.reserve(a_m) == max(500, math.ceil(0.2 * a_m))


def test_the_gate_outputs_name_the_admitted_snapshot_and_nothing_else(tmp_path, capsys):
    hexd = "a" * 64
    tag = RL.tag_for("sha256:" + hexd, SHA)
    rec = {"decision": DG.DISPATCH, "sha": SHA,
           "release": {"address": "sha256:" + hexd, "tag": tag, "commit": SHA}}
    assert R.outputs(rec) == f"address=sha256:{hexd}\ntag={tag}\nhex={hexd}\n"
    assert tag.endswith(f"-at-{SHA}")
    empty = "address=\ntag=\nhex=\n"
    for bad in ({**rec, "decision": DG.PARK}, {**rec, "decision": DG.NO_DISPATCH}, {**rec, "release": None},
                {**rec, "release": {**rec["release"], "address": "sha256:" + "A" * 64}},
                {**rec, "release": {**rec["release"], "address": f"sha256:{hexd}\nhex=injected"}},
                {**rec, "sha": OLD},                                                # another run's commit
                {**rec, "release": {**rec["release"], "commit": OLD}},              # another commit's release
                {**rec, "release": {**rec["release"], "tag": RL.tag_for("sha256:" + hexd, OLD)}},
                {**rec, "sha": None}, {"decision": DG.DISPATCH}, [], None):
        assert R.outputs(bad) == empty, bad
    p = tmp_path / "gate.json"
    p.write_text(json.dumps(rec))
    assert R.main(["outputs", "--gate", str(p)]) == 0
    assert capsys.readouterr().out == R.outputs(rec)
