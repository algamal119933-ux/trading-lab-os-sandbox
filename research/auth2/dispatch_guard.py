#!/usr/bin/env python3
"""AUTH-2 dispatch guard (FUNNEL_LAW_2.md §COMPUTE_CAP_PROOF, §MONTHLY_BILLING_PACING_RULE).

    python -m auth2.dispatch_guard --node <ID> [--part N] --repo-slug owner/name
                                   [--in-job] [--out guard.json]

Decides whether one AUTH-2 node job may run. It is called twice for every job:
by the executor before ``workflow_dispatch`` (nothing is dispatched unless it
says DISPATCH) and again as the first step inside the job (``--in-job``), where
anything but DISPATCH ends the job before any engine or data work.

DISPATCH only if ALL hold at that moment (any unreadable input => NO_DISPATCH):

    billing           the account's remaining included Linux minutes are readable
                      and an Actions budget of USD 0 that stops usage is confirmed
    serial            no other AUTH-2 run is queued, waiting or in progress
    never re-run      no earlier run of this node part succeeded; at most
                      MAX_ATTEMPTS runs of it ever (one technical retry)
    minutes ledger    sum of billed minutes of every AUTH-2 job (each rounded up;
                      a job still running counts its full timeout)
                      + 2 x this job's timeout <= 4,000
    invocations       sum of the planned engine invocations of every AUTH-2 node
                      run ever dispatched (conservative: a failed run counts in
                      full) + 2 x this part's planned invocations <= 240
    monthly reserve   remaining_included_now - 2 x timeout >= R_m, where
                      R_m = max(500, ceil(0.20 x A_m)) and A_m is the remaining
                      allowance read at the month's first AUTH-2 dispatch (kept
                      in that run's guard record); otherwise PARK (EXTERNAL)
                      until the next billing month

The decision is a pure function of the collected state (``decide``); the
collection reads GitHub with ``gh api`` and never writes anything there.

PAPER / RESEARCH ONLY. It dispatches nothing itself and holds no secret beyond
the read token it is given.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

CAP_MINUTES = 4000
CAP_INVOCATIONS = 240
RESERVE_FLOOR = 500
RESERVE_SHARE = 0.20
MAX_ATTEMPTS = 2
WORKFLOW_FILE = "auth2.yml"
RUN_NAME = re.compile(r"^AUTH2 (?P<node>[A-Z0-9-]+) part (?P<part>\d+)$")
ACTIVE = ("queued", "in_progress", "waiting", "requested", "pending")

DISPATCH, NO_DISPATCH, PARK = "DISPATCH", "NO_DISPATCH", "PARK"


def node_plan(node: str, part: int) -> dict:
    """Timeout and planned engine invocations of one node part (the compute plan)."""
    from auth2 import run_node as RN

    if node not in RN.NODES:
        raise KeyError(f"unknown node {node}")
    spec = RN.NODES[node]
    if not 1 <= part <= spec["parts"]:
        raise KeyError(f"{node} has {spec['parts']} part(s)")
    inv = 0
    if spec["invocations"]:
        plan = RN.run_plan(node, spec["family"])
        inv = sum(1 for i, _r in enumerate(plan) if spec["parts"] == 1 or i % spec["parts"] == part - 1)
    return {"timeout_minutes": spec["timeout_minutes"], "invocations": inv}


def reserve(a_m: int) -> int:
    return max(RESERVE_FLOOR, math.ceil(RESERVE_SHARE * a_m))


def billed_minutes(job: dict, timeout: int) -> int:
    """GitHub bills a job by the minute, rounded up; a job not finished counts its whole timeout."""
    if job.get("status") != "completed" or not job.get("started_at") or not job.get("completed_at"):
        return timeout
    a = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))
    b = datetime.fromisoformat(job["completed_at"].replace("Z", "+00:00"))
    return max(0, math.ceil((b - a).total_seconds() / 60))


def decide(state: dict, node: str, part: int) -> dict:
    """The dispatch decision for (node, part) given the collected state.

    state = {"now": ISO, "self_run_id": int | None,
             "billing": {"readable": bool, "remaining_included_minutes": int, "budget_usd_zero": bool,
                         "reason": str},
             "runs": [{"id", "node", "part", "status", "conclusion", "created_at",
                       "jobs": [{"status", "started_at", "completed_at"}], "guard": {...} | None}]}
    """
    plan = node_plan(node, part)
    t, inv = plan["timeout_minutes"], plan["invocations"]
    reasons: list[str] = []
    out = {"node": node, "part": part, "timeout_minutes": t, "planned_invocations": inv,
           "caps": {"minutes": CAP_MINUTES, "invocations": CAP_INVOCATIONS}}
    me = state.get("self_run_id")
    runs = [r for r in state["runs"] if r["id"] != me]

    bill = state.get("billing") or {}
    if not bill.get("readable"):
        reasons.append("FAIL_CLOSED: remaining included Actions minutes not readable"
                       + (f" ({bill.get('reason')})" if bill.get("reason") else ""))
    elif not bill.get("budget_usd_zero"):
        reasons.append("FAIL_CLOSED: an Actions budget of USD 0 that stops usage is not confirmed")

    busy = [r["id"] for r in runs if r["status"] in ACTIVE]
    if busy:
        reasons.append(f"SERIAL: AUTH-2 run(s) {busy} still active")

    mine = [r for r in runs if r["node"] == node and r["part"] == part]
    if any(r["conclusion"] == "success" for r in mine):
        reasons.append(f"NEVER_RERUN: {node} part {part} already succeeded")
    elif len(mine) >= MAX_ATTEMPTS:
        reasons.append(f"ATTEMPTS: {node} part {part} already ran {len(mine)} time(s); the retry is spent")

    minutes = 0
    invocations = 0
    unreconciled = []
    for r in runs:
        try:
            p = node_plan(r["node"], r["part"])
        except KeyError:
            unreconciled.append(r["id"])
            continue
        if r["status"] == "completed" and not r["jobs"]:
            unreconciled.append(r["id"])
        minutes += sum(billed_minutes(j, p["timeout_minutes"]) for j in r["jobs"]) if r["jobs"] else p["timeout_minutes"]
        invocations += p["invocations"]
    if unreconciled:
        reasons.append(f"FAIL_CLOSED: runs {unreconciled} cannot be reconciled with the Actions API")
    out["minutes_ledger"] = minutes
    out["invocation_ledger"] = invocations
    if minutes + 2 * t > CAP_MINUTES:
        reasons.append(f"CAP: minutes ledger {minutes} + 2 x {t} > {CAP_MINUTES}")
    if invocations + 2 * inv > CAP_INVOCATIONS:
        reasons.append(f"CAP: invocation ledger {invocations} + 2 x {inv} > {CAP_INVOCATIONS}")

    park = False
    if bill.get("readable"):
        now = datetime.fromisoformat(state["now"].replace("Z", "+00:00"))
        month = now.strftime("%Y-%m")
        firsts = sorted((r for r in runs if r["created_at"][:7] == month), key=lambda r: r["created_at"])
        remaining = int(bill["remaining_included_minutes"])
        if firsts:
            g = firsts[0].get("guard")
            if not g or g.get("month") != month or "a_m" not in g:
                reasons.append(f"FAIL_CLOSED: the month's first AUTH-2 run {firsts[0]['id']} has no readable "
                               "guard record, so R_m is unknown")
                a_m = None
            else:
                a_m = int(g["a_m"])
        else:
            a_m = remaining  # this is the month's first AUTH-2 dispatch
        if a_m is not None:
            r_m = reserve(a_m)
            out.update({"month": month, "a_m": a_m, "r_m": r_m, "remaining_included_minutes": remaining})
            if remaining - 2 * t < r_m:
                park = True
                reasons.append(f"RESERVE: remaining {remaining} - 2 x {t} < R_m {r_m}; PARK until next month")

    if not reasons:
        out["decision"] = DISPATCH
    elif park and all(x.startswith("RESERVE") for x in reasons):
        out["decision"] = PARK
    else:
        out["decision"] = NO_DISPATCH
    out["reasons"] = reasons
    return out


# -- collection (read-only GitHub API) ----------------------------------------------------


def _api(path: str, token_env: str | None = None) -> dict | list:
    env = dict(os.environ)
    if token_env and os.environ.get(token_env):
        env["GH_TOKEN"] = os.environ[token_env]
    proc = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path],
                          capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip()[:300])
    return json.loads(proc.stdout)


def _api_bytes(path: str) -> bytes:
    proc = subprocess.run(["gh", "api", path], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace")[:300])
    return proc.stdout


def read_billing(owner: str, token_env: str) -> dict:
    """Remaining included Linux minutes and the USD 0 budget; unreadable => readable False."""
    try:
        usage = _api(f"/users/{owner}/settings/billing/actions", token_env)
        included = int(usage["included_minutes"])
        used = int(math.ceil(float(usage["total_minutes_used"])))
    except Exception as exc:  # noqa: BLE001 - every failure is the same fail-closed answer
        return {"readable": False, "reason": f"usage: {exc}"[:300]}
    out = {"readable": True, "remaining_included_minutes": included - used, "included_minutes": included,
           "used_minutes": used, "budget_usd_zero": False}
    try:
        budgets = _api(f"/users/{owner}/settings/billing/budgets", token_env)
        items = budgets.get("budgets", budgets) if isinstance(budgets, dict) else budgets
        for b in items:
            scope = json.dumps(b).lower()
            if "actions" in scope and float(b.get("budget_amount", -1)) == 0 and b.get("prevent_further_usage"):
                out["budget_usd_zero"] = True
    except Exception as exc:  # noqa: BLE001
        out["budget_reason"] = f"budgets: {exc}"[:300]
    return out


def read_runs(slug: str) -> list[dict]:
    runs = []
    page = 1
    while True:
        got = _api(f"/repos/{slug}/actions/workflows/{WORKFLOW_FILE}/runs?per_page=100&page={page}")
        batch = got.get("workflow_runs", [])
        for r in batch:
            m = RUN_NAME.match(r.get("display_title") or r.get("name") or "")
            if not m:
                raise RuntimeError(f"run {r['id']} has an unparseable title {r.get('display_title')!r}")
            jobs = _api(f"/repos/{slug}/actions/runs/{r['id']}/jobs?per_page=100").get("jobs", [])
            runs.append({"id": r["id"], "node": m["node"], "part": int(m["part"]), "status": r["status"],
                         "conclusion": r.get("conclusion"), "created_at": r["created_at"],
                         "jobs": [{k: j.get(k) for k in ("status", "started_at", "completed_at")} for j in jobs],
                         "guard": None})
        if len(batch) < 100:
            break
        page += 1
    return runs


def attach_first_guard(slug: str, runs: list[dict], month: str) -> None:
    """Read the guard record of the month's first AUTH-2 run (R_m is fixed by it)."""
    firsts = sorted((r for r in runs if r["created_at"][:7] == month), key=lambda r: r["created_at"])
    if not firsts:
        return
    first = firsts[0]
    arts = _api(f"/repos/{slug}/actions/runs/{first['id']}/artifacts").get("artifacts", [])
    for a in arts:
        if a["name"].startswith("auth2-") and not a.get("expired"):
            body = _api_bytes(f"/repos/{slug}/actions/artifacts/{a['id']}/zip")
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                names = [n for n in z.namelist() if n.endswith("guard.json")]
                if names:
                    first["guard"] = json.loads(z.read(names[0]))
            return


def collect(slug: str, owner: str, token_env: str, self_run_id: int | None) -> dict:
    now = datetime.now(timezone.utc)
    state = {"now": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "self_run_id": self_run_id,
             "billing": read_billing(owner, token_env), "runs": []}
    try:
        state["runs"] = read_runs(slug)
        attach_first_guard(slug, state["runs"], now.strftime("%Y-%m"))
    except Exception as exc:  # noqa: BLE001
        state["runs_error"] = str(exc)[:300]
    return state


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--node", required=True)
    ap.add_argument("--part", type=int, default=1)
    ap.add_argument("--repo-slug", required=True)
    ap.add_argument("--billing-owner", help="account whose Actions minutes are read (default: the repo owner)")
    ap.add_argument("--billing-token-env", default="AUTH2_BILLING_TOKEN",
                    help="environment variable holding a token that may read the account's billing")
    ap.add_argument("--in-job", action="store_true", help="running inside the node's own workflow run")
    ap.add_argument("--state", help="decide on a saved state JSON instead of reading GitHub (tests)")
    ap.add_argument("--out", help="write the decision record here")
    a = ap.parse_args(argv)
    if a.state:
        state = json.loads(Path(a.state).read_text())
    else:
        me = int(os.environ["GITHUB_RUN_ID"]) if a.in_job else None
        state = collect(a.repo_slug, a.billing_owner or a.repo_slug.split("/")[0], a.billing_token_env, me)
    if state.get("runs_error"):
        rec = {"node": a.node, "part": a.part, "decision": NO_DISPATCH,
               "reasons": [f"FAIL_CLOSED: AUTH-2 run history not readable ({state['runs_error']})"]}
    else:
        rec = decide(state, a.node, a.part)
    rec["mode"] = "in-job" if a.in_job else "pre-dispatch"
    rec["checked_utc"] = state.get("now")
    if a.out:
        Path(a.out).write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    print(json.dumps(rec, indent=1, sort_keys=True))
    print(f"AUTH2_DISPATCH_GUARD = {rec['decision']}")
    return 0 if rec["decision"] == DISPATCH else 3


if __name__ == "__main__":
    sys.exit(main())
