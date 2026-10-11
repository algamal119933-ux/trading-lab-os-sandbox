"""AUTH-2 dispatch guard and node workflow (FUNNEL_LAW_2.md §COMPUTE_CAP_PROOF,
§MONTHLY_BILLING_PACING_RULE): every refusal fires, nothing unreadable dispatches, and the
workflow's timeouts are the compute plan's.

PAPER / RESEARCH ONLY. Nothing here calls GitHub: the decision is a pure function of a state.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("numpy")
yaml = pytest.importorskip("yaml")

from auth2 import dispatch_guard as DG  # noqa: E402
from auth2 import run_node as RN  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "auth2.yml"


def state(**kw) -> dict:
    s = {"now": "2026-11-03T10:00:00Z", "self_run_id": None,
         "billing": {"readable": True, "remaining_included_minutes": 2000, "budget_usd_zero": True},
         "runs": []}
    s.update(kw)
    return s


def run(i, node, part=1, status="completed", conclusion="success", created="2026-11-01T00:00:00Z",
        minutes=10, guard=None):
    jobs = [{"status": "completed", "started_at": "2026-11-01T00:00:00Z",
             "completed_at": f"2026-11-01T00:{minutes:02d}:00Z"}] if status == "completed" else \
        [{"status": status, "started_at": None, "completed_at": None}]
    return {"id": i, "node": node, "part": part, "status": status, "conclusion": conclusion,
            "created_at": created, "jobs": jobs,
            "guard": guard if guard is not None else {"month": created[:7], "a_m": 2000}}


def test_the_compute_plan_totals_are_the_package_proof():
    total_t = sum(n["timeout_minutes"] * n["parts"] for n in RN.NODES.values())
    total_inv = sum(DG.node_plan(k, p)["invocations"] for k, n in RN.NODES.items()
                    for p in range(1, n["parts"] + 1))
    assert total_t == 1980 and 2 * total_t <= DG.CAP_MINUTES
    assert total_inv == 107 and 2 * total_inv <= DG.CAP_INVOCATIONS
    assert (DG.CAP_MINUTES, DG.CAP_INVOCATIONS, DG.RESERVE_FLOOR, DG.RESERVE_SHARE, DG.MAX_ATTEMPTS) == \
        (4000, 240, 500, 0.20, 2)


def test_a_clean_state_dispatches():
    assert DG.decide(state(), "D0", 1)["decision"] == DG.DISPATCH


@pytest.mark.parametrize("billing,reason", [
    ({"readable": False, "reason": "HTTP 403"}, "FAIL_CLOSED"),
    ({}, "FAIL_CLOSED"),
    ({"readable": True, "remaining_included_minutes": 2000, "budget_usd_zero": False}, "FAIL_CLOSED"),
])
def test_unreadable_billing_or_unconfirmed_budget_never_dispatches(billing, reason):
    d = DG.decide(state(billing=billing), "D0", 1)
    assert d["decision"] == DG.NO_DISPATCH
    assert any(r.startswith(reason) for r in d["reasons"])


def test_one_job_at_a_time():
    d = DG.decide(state(runs=[run(1, "D0", status="in_progress", conclusion=None)]), "CAL-A1", 1)
    assert d["decision"] == DG.NO_DISPATCH and any(r.startswith("SERIAL") for r in d["reasons"])


def test_a_succeeded_node_never_reruns_and_the_retry_is_spent_after_two():
    d = DG.decide(state(runs=[run(1, "D0")]), "D0", 1)
    assert any(r.startswith("NEVER_RERUN") for r in d["reasons"])
    once = DG.decide(state(runs=[run(1, "D0", conclusion="failure")]), "D0", 1)
    assert once["decision"] == DG.DISPATCH  # the one technical retry
    twice = DG.decide(state(runs=[run(1, "D0", conclusion="failure"), run(2, "D0", conclusion="failure",
                                                                          created="2026-11-01T01:00:00Z")]),
                      "D0", 1)
    assert any(r.startswith("ATTEMPTS") for r in twice["reasons"])


def test_the_in_job_guard_ignores_its_own_run():
    s = state(runs=[run(9, "D0", status="in_progress", conclusion=None)], self_run_id=9)
    assert DG.decide(s, "D0", 1)["decision"] == DG.DISPATCH


def test_minutes_cap_reserves_a_retry():
    runs = [run(i, "D0", minutes=0, created=f"2026-11-01T00:{i:02d}:00Z") for i in range(1, 2)]
    for r in runs:
        r["jobs"] = [{"status": "completed", "started_at": "2026-11-01T00:00:00Z",
                      "completed_at": "2026-11-03T14:41:00Z"}]  # 2 x 1,440 + 881 = 3,761 billed minutes
    d = DG.decide(state(billing={"readable": True, "remaining_included_minutes": 100000,
                                 "budget_usd_zero": True}, runs=runs), "PC-A2", 1)
    assert d["minutes_ledger"] == 3761
    assert any(r.startswith("CAP: minutes") for r in d["reasons"])  # 3761 + 2 x 180 > 4000
    assert DG.decide(state(billing={"readable": True, "remaining_included_minutes": 100000,
                                    "budget_usd_zero": True}, runs=runs), "HOLM", 1)["decision"] == DG.DISPATCH


def test_invocation_cap():
    runs = [run(i, "PC-A1", created=f"2026-11-01T{i:02d}:00:00Z", conclusion="failure") for i in range(17)]
    s = state(billing={"readable": True, "remaining_included_minutes": 100000, "budget_usd_zero": True}, runs=runs)
    ok = DG.decide(s, "SC-A1", 1)  # 17 x 13 + 2 x 1 = 223 <= 240
    assert ok["invocation_ledger"] == 221 and ok["decision"] == DG.DISPATCH
    d = DG.decide(s, "PC-A3", 1)  # 221 + 2 x 11 = 243 > 240
    assert d["decision"] == DG.NO_DISPATCH and any(r.startswith("CAP: invocation") for r in d["reasons"])


def test_the_monthly_reserve_parks_until_next_month():
    s = state(billing={"readable": True, "remaining_included_minutes": 700, "budget_usd_zero": True})
    d = DG.decide(s, "A2", 1)  # 700 - 2 x 240 < max(500, 140)
    assert d["decision"] == DG.PARK and d["r_m"] == 500 and d["a_m"] == 700
    assert DG.reserve(2000) == 500 and DG.reserve(5000) == 1000


def test_r_m_is_fixed_by_the_months_first_run_and_unknown_r_m_fails_closed():
    first = run(1, "D0", created="2026-11-01T00:00:00Z", guard={"month": "2026-11", "a_m": 10000})
    s = state(billing={"readable": True, "remaining_included_minutes": 2400, "budget_usd_zero": True},
              runs=[first])
    d = DG.decide(s, "CAL-A1", 1)
    assert d["r_m"] == 2000 and d["decision"] == DG.DISPATCH  # 2400 - 120 >= 2000
    first["guard"] = None
    d = DG.decide(s, "CAL-A1", 1)
    assert d["decision"] == DG.NO_DISPATCH and any("R_m is unknown" in r for r in d["reasons"])


def test_an_unreconcilable_run_fails_closed():
    bad = run(1, "D0")
    bad["jobs"] = []
    d = DG.decide(state(runs=[bad]), "CAL-A1", 1)
    assert any("cannot be reconciled" in r for r in d["reasons"])


def test_billed_minutes_round_up_and_unfinished_jobs_count_their_timeout():
    job = {"status": "completed", "started_at": "2026-11-01T00:00:00Z", "completed_at": "2026-11-01T00:10:01Z"}
    assert DG.billed_minutes(job, 60) == 11
    assert DG.billed_minutes({"status": "in_progress"}, 60) == 60


def test_cli_exits_3_unless_dispatch(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(state(billing={"readable": False})))
    out = tmp_path / "g.json"
    assert DG.main(["--node", "D0", "--repo-slug", "o/r", "--state", str(p), "--out", str(out)]) == 3
    assert json.loads(out.read_text())["decision"] == DG.NO_DISPATCH
    p.write_text(json.dumps(state()))
    assert DG.main(["--node", "D0", "--repo-slug", "o/r", "--state", str(p)]) == 0


def test_unknown_node_or_part_is_refused():
    with pytest.raises(KeyError):
        DG.node_plan("A4", 1)
    with pytest.raises(KeyError):
        DG.node_plan("A1", 2)


# -- the workflow ------------------------------------------------------------------------

def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def test_workflow_is_manual_dispatch_only():
    wf = workflow()
    on = wf.get("on", wf.get(True))
    assert list(on) == ["workflow_dispatch"]
    assert wf["permissions"] == {"contents": "read", "actions": "read"}
    assert wf["concurrency"] == {"group": "auth2-program", "cancel-in-progress": False}


def test_workflow_node_choices_and_timeouts_equal_the_compute_plan():
    wf = workflow()
    on = wf.get("on", wf.get(True))
    assert sorted(on["workflow_dispatch"]["inputs"]["node"]["options"]) == sorted(RN.NODES)
    expr = wf["jobs"]["node"]["timeout-minutes"]
    table = json.loads(re.search(r"fromJSON\('(\{.*\})'\)", expr).group(1))
    assert table == {n: spec["timeout_minutes"] for n, spec in RN.NODES.items()}
    assert wf["run-name"] == "AUTH2 ${{ inputs.node }} part ${{ inputs.part }}"
    assert DG.RUN_NAME.match("AUTH2 PC-A2 part 2")


def test_workflow_guards_first_and_never_writes():
    text = WORKFLOW.read_text()
    steps = workflow()["jobs"]["node"]["steps"]
    names = [s.get("name", s.get("uses", "")) for s in steps]
    guard = next(i for i, n in enumerate(names) if "dispatch guard" in n)
    run_i = next(i for i, n in enumerate(names) if n.startswith("Run the node"))
    assert guard < run_i
    assert "--in-job" in steps[guard]["run"]
    for forbidden in ("git push", "git commit", "contents: write", "dry_run\": false", "--dry-run-wallet"):
        assert forbidden not in text
    secrets = set(re.findall(r"secrets\.([A-Z0-9_]+)", text))
    assert secrets == {"AUTH2_BILLING_TOKEN"}
    assert "freqtradeorg/freqtrade:2026.7" in text
