#!/usr/bin/env python3
"""AUTH-2 operator gate: the pre-dispatch guard run in Actions, and the readouts the executor needs.

    python .github/gates/auth2_operator.py guard --node <ID> [--part N] --repo-slug owner/name
                                               [--self-run-id ID] [--in-job] [--out F] [--annotate]
    python .github/gates/auth2_operator.py check-dispatch --guard-run ID --node <ID> [--part N]
                                               --repo-slug owner/name --main-sha SHA
    python .github/gates/auth2_operator.py annotate --title T --file F
    python .github/gates/auth2_operator.py annotate-results --dir out
    python .github/gates/auth2_operator.py next --repo-slug owner/name --main-sha SHA RUN_ID...
    python .github/gates/auth2_operator.py readout --run ID --title AUTH2_CLOSURE --repo-slug owner/name
                                               --main-sha SHA --out F

Why it exists. The executor's session reaches GitHub only through repository endpoints: it cannot read the
account's Actions billing (FUNNEL_LAW_2.md §MONTHLY_BILLING_PACING_RULE) and cannot download run artifacts.
So the pre-dispatch guard runs as its own small Actions job (.github/workflows/auth2-guard.yml) with the
AUTH2_BILLING_TOKEN secret, and publishes its decision record as a job annotation, which the session can read.
The executor dispatches a node only after ``check-dispatch`` verifies that record: a successful guard run of
this node part, on the current main, at most FRESH_MINUTES old, deciding DISPATCH, with no AUTH-2 run created
after it. Node jobs publish a summary of their result records the same way (``annotate-results``), which is
what ``next`` reads to apply the frozen DAG (run_node.eligible), and the closure job publishes the closure
record (``readout``).

Nothing here changes research/auth2/: its code is pinned by sha256 in every preregistration. The decision is
research/auth2/dispatch_guard.decide, unchanged, over the node runs; this gate only adds checks for the AUTH-2
jobs that are not node runs (guard and closure jobs): they must not be active (SERIAL) and their billed
minutes count toward the 4,000-minute ledger. It never removes a refusal, so it can only be stricter.

Billing is read here, not by dispatch_guard.read_billing: the endpoint that function calls was closed down by
GitHub and answers HTTP 410 (see ``read_billing`` below). A run attempt after the first never runs a node or
the closure again, and the minutes of every attempt count.

PAPER / RESEARCH ONLY. Read-only against GitHub: it dispatches nothing and writes nothing there.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "research") not in sys.path:
    sys.path.insert(0, str(REPO / "research"))

from auth2 import dispatch_guard as DG  # noqa: E402

GUARD_WORKFLOW = "auth2-guard.yml"
CLOSURE_WORKFLOW = "auth2-closure.yml"
GUARD_TIMEOUT = 10
CLOSURE_TIMEOUT = 20
CLOSURE = "CLOSURE"
FRESH_MINUTES = 15
GUARD_TITLE = re.compile(r"^AUTH2-GUARD (?P<node>[A-Z0-9-]+) part (?P<part>\d+)$")
CLOSURE_TITLE = "AUTH2-CLOSURE"
AUX = {GUARD_WORKFLOW: GUARD_TIMEOUT, CLOSURE_WORKFLOW: CLOSURE_TIMEOUT}
CHUNK = 16000
RECORD, RESULT, CLOSURE_RECORD = "AUTH2_GUARD_RECORD", "AUTH2_RESULT", "AUTH2_CLOSURE"

# Billing evidence (FUNNEL_LAW_2.md §MONTHLY_BILLING_PACING_RULE). dispatch_guard.read_billing reads
# GET /users/{owner}/settings/billing/actions, one of the product-specific billing endpoints GitHub closed down
# (changelog 2025-09-26); it answers HTTP 410 "This endpoint has been moved". Its replacement for a personal
# account is the enhanced billing platform's usage report (fine-grained token: "Plan" user permission, read):
# per-day usage items with gross, discount and net amounts. That report does not carry either control the
# pacing rule needs, and no other endpoint does for a personal account:
#   remaining included minutes  no field holds the plan's included quota or what is left of it, and
#                               discountAmount merges included usage with the free usage of public repositories
#                               and self-hosted runners (GitHub docs, "Billing reports reference"), so no
#                               difference of reported figures is the remaining allowance;
#   USD 0 budget, stop usage    the budgets API exists for organizations only.
# So the reader verifies what can be verified, that the billing token reads this account's report for this
# month and the report is well formed, records it, and reports both controls as unproven: NO_DISPATCH.
BILLING_USAGE = "/users/{owner}/settings/billing/usage?year={year}&month={month}"
HTTP_CLASS = {401: "TOKEN_INVALID", 403: "PERMISSION_DENIED", 404: "NOT_FOUND", 410: "ENDPOINT_RETIRED"}
NUMBER = (int, float)
USAGE_FIELDS = {"date": str, "product": str, "sku": str, "unitType": str, "quantity": NUMBER,
                "grossAmount": NUMBER, "discountAmount": NUMBER, "netAmount": NUMBER}
INCLUDED_NOT_EXPOSED = ("NOT_EXPOSED: GitHub's billing API gives no included-minutes quota and no remaining included "
                        "minutes; discountAmount merges included usage with public-repository and self-hosted "
                        "discounts")
BUDGET_NOT_EXPOSED = ("NOT_EXPOSED: GitHub's budgets API is organization-only, so a personal account's Actions "
                      "budget and its stop-usage setting cannot be read")


# -- the decision ---------------------------------------------------------------------------------

def _verdict(rec: dict, park: bool) -> dict:
    reasons = rec["reasons"]
    if not reasons:
        rec["decision"] = DG.DISPATCH
    elif park and all(r.startswith("RESERVE") for r in reasons):
        rec["decision"] = DG.PARK
    else:
        rec["decision"] = DG.NO_DISPATCH
    return rec


def decide(state: dict, aux: list[dict], node: str, part: int, attempt: int = 1, earlier_minutes: int = 0) -> dict:
    """dispatch_guard.decide over the node runs, plus the checks for guard and closure jobs.

    ``aux`` = [{"id", "workflow", "status", "conclusion", "created_at", "minutes"}] for every guard and
    closure run except the caller's own (minutes of all its attempts). CLOSURE has the HOLM plan (0
    invocations, 15 minutes) widened to CLOSURE_TIMEOUT; its re-run and attempt rules apply to the closure
    runs. ``attempt`` is the calling node or closure job's own run attempt (1 before dispatch);
    ``earlier_minutes`` the billed minutes of node-run attempts dispatch_guard does not see."""
    if node == CLOSURE:
        rec = DG.decide(state, "HOLM", 1)
        rec["reasons"] = [r for r in rec["reasons"] if not r.startswith(("NEVER_RERUN", "ATTEMPTS"))]
        rec.update({"node": CLOSURE, "part": 1, "timeout_minutes": CLOSURE_TIMEOUT})
        mine = [r for r in aux if r["workflow"] == CLOSURE_WORKFLOW]
        if any(r["conclusion"] == "success" for r in mine):
            rec["reasons"].append("NEVER_RERUN: CLOSURE already succeeded")
        elif len(mine) >= DG.MAX_ATTEMPTS:
            rec["reasons"].append(f"ATTEMPTS: CLOSURE already ran {len(mine)} time(s); the retry is spent")
        if rec.get("remaining_included_minutes") is not None and \
                rec["remaining_included_minutes"] - 2 * CLOSURE_TIMEOUT < rec["r_m"]:
            rec["reasons"].append(f"RESERVE: remaining {rec['remaining_included_minutes']} - 2 x "
                                  f"{CLOSURE_TIMEOUT} < R_m {rec['r_m']}; PARK until next month")
    else:
        rec = DG.decide(state, node, part)
    t = rec["timeout_minutes"]
    if attempt > 1:
        rec["reasons"].append(f"RE_RUN: this is attempt {attempt} of its run; a node or the closure runs once per "
                              "dispatch, and a technical retry is a new dispatch")
    busy = [r["id"] for r in aux if r["status"] in DG.ACTIVE]
    if busy:
        rec["reasons"].append(f"SERIAL: AUTH-2 guard/closure run(s) {busy} still active")
    aux_minutes = sum(int(r["minutes"]) for r in aux) + int(earlier_minutes)
    rec["aux_minutes_ledger"] = aux_minutes
    rec["earlier_attempt_minutes"] = int(earlier_minutes)
    if "minutes_ledger" in rec:
        total = rec["minutes_ledger"] + aux_minutes
        rec["total_minutes_ledger"] = total
        cap = (f"CAP: minutes ledger {total} (incl. {aux_minutes} guard/closure/earlier attempts) + 2 x {t} > "
               f"{DG.CAP_MINUTES}")
        if total + 2 * t > DG.CAP_MINUTES and not any(r.startswith("CAP: minutes") for r in rec["reasons"]):
            rec["reasons"].append(cap)
    bill = state.get("billing") or {}
    if not bill.get("budget_usd_zero") and not any("budget of USD 0" in r for r in rec["reasons"]):
        rec["reasons"].append("FAIL_CLOSED: an Actions budget of USD 0 that stops usage is not verified"
                              + (f" ({bill['budget_reason']})" if bill.get("budget_reason") else ""))
    rec["billing"] = {k: bill.get(k) for k in ("readable", "remaining_included_minutes", "budget_usd_zero",
                                                "usage_evidence")}
    park = any(r.startswith("RESERVE") for r in rec["reasons"])
    rec["reasons"] = list(dict.fromkeys(rec["reasons"]))
    return _verdict(rec, park)


# -- billing (read-only; the billing token only) ----------------------------------------------------

def billing_get(path: str, token: str) -> tuple[int | None, object]:
    """GET ``path`` with the billing token. The workflow's own token is never used for billing: it is removed
    from the environment, so a missing secret can never turn into a misleading permission error."""
    env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN")}
    env["GH_TOKEN"] = token
    proc = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json",
                           "-H", "X-GitHub-Api-Version: 2022-11-28", path], capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        m = re.search(r"\(HTTP (\d{3})\)", err)
        return (int(m[1]) if m else None), err[:300]
    try:
        return 200, json.loads(proc.stdout)
    except ValueError:
        return 200, None


def usage_evidence(owner: str, year: int, month: int, status: int | None, body) -> dict:
    """Classify one usage-report response; ``verified`` only for a well-formed report of this account and month.

    A verified report proves the token, the account and the period. It is evidence, never a billing control."""
    ev: dict = {"verified": False, "status": status, "period": f"{year:04d}-{month:02d}"}
    if status != 200:
        ev.update({"class": HTTP_CLASS.get(status, "API_ERROR"), "detail": str(body)[:300]})
        return ev
    items = body.get("usageItems") if isinstance(body, dict) else None
    if not isinstance(items, list):
        ev.update({"class": "MALFORMED", "detail": "the response has no usageItems list"})
        return ev
    actions: dict[str, dict] = {}
    for it in items:
        bad = sorted(k for k, kind in USAGE_FIELDS.items() if not isinstance(it, dict)
                     or not isinstance(it.get(k), kind) or isinstance(it.get(k), bool))
        if bad:
            ev.update({"class": "MISSING_FIELDS", "detail": f"a usage item lacks or mistypes {bad}"})
            return ev
        if not it["date"].startswith(ev["period"]):
            ev.update({"class": "WRONG_PERIOD", "detail": f"usage dated {it['date'][:32]} in the {ev['period']} report"})
            return ev
        repo = it.get("repositoryName") or ""
        if not isinstance(repo, str) or (repo and not repo.lower().startswith(owner.lower() + "/")):
            ev.update({"class": "WRONG_ACCOUNT", "detail": f"usage of {str(repo)[:100]} in the report for {owner}"})
            return ev
        if it["product"].lower() == "actions":
            tot = actions.setdefault(it["sku"], {"unitType": it["unitType"], "quantity": 0.0, "grossAmount": 0.0,
                                                 "discountAmount": 0.0, "netAmount": 0.0})
            for k in ("quantity", "grossAmount", "discountAmount", "netAmount"):
                tot[k] = round(tot[k] + float(it[k]), 6)
    ev.update({"verified": True, "class": "USAGE_VERIFIED", "actions": actions})
    return ev


def read_billing(owner: str, token_env: str, now: datetime, get=billing_get) -> dict:
    """The billing state dispatch_guard.decide reads. Neither control the pacing rule needs is exposed by
    GitHub's API for a personal account (see BILLING_USAGE above), so ``readable`` and ``budget_usd_zero`` are
    never true here and every decision is NO_DISPATCH; ``usage_evidence`` records what the token proved."""
    token = (os.environ.get(token_env) or "").strip()
    if not token:
        ev = {"verified": False, "status": None, "class": "TOKEN_MISSING", "period": f"{now.year:04d}-{now.month:02d}",
              "detail": f"{token_env} is not set; the workflow token is never used for billing"}
    else:
        path = BILLING_USAGE.format(owner=owner, year=now.year, month=now.month)
        status, body = get(path, token)
        ev = usage_evidence(owner, now.year, now.month, status, body)
        ev["endpoint"] = path.split("?")[0]
        if "detail" in ev:
            ev["detail"] = ev["detail"].replace(token, "***")
    reason = INCLUDED_NOT_EXPOSED if ev["verified"] else f"{ev['class']}: {ev['detail']}; {INCLUDED_NOT_EXPOSED}"
    return {"readable": False, "remaining_included_minutes": None, "budget_usd_zero": False, "reason": reason,
            "budget_reason": BUDGET_NOT_EXPOSED, "usage_evidence": ev}


# -- collection (read-only, repository endpoints only) ---------------------------------------------

def read_aux_runs(slug: str, self_run_id: int | None) -> list[dict]:
    out = []
    for wf, timeout in AUX.items():
        page = 1
        while True:
            got = DG._api(f"/repos/{slug}/actions/workflows/{wf}/runs?per_page=100&page={page}")
            batch = got.get("workflow_runs", [])
            for r in batch:
                if r["id"] == self_run_id:
                    continue
                jobs = DG._api(f"/repos/{slug}/actions/runs/{r['id']}/jobs?per_page=100&filter=all").get("jobs", [])
                if r["status"] == "completed" and not jobs:
                    raise RuntimeError(f"run {r['id']} cannot be reconciled with the Actions API")
                minutes = sum(DG.billed_minutes(j, timeout) for j in jobs) if jobs else timeout
                out.append({"id": r["id"], "workflow": wf, "status": r["status"],
                            "conclusion": r.get("conclusion"), "created_at": r["created_at"], "minutes": minutes})
            if len(batch) < 100:
                break
            page += 1
    return out


def earlier_attempt_minutes(slug: str) -> int:
    """Billed minutes of the earlier attempts of re-run node runs. dispatch_guard.read_runs reads each run's
    latest attempt only, so without this a re-run ("Re-run jobs" in GitHub) would drop them from the ledger."""
    total, page = 0, 1
    while True:
        got = DG._api(f"/repos/{slug}/actions/workflows/{DG.WORKFLOW_FILE}/runs?per_page=100&page={page}")
        batch = got.get("workflow_runs", [])
        for r in batch:
            latest = int(r.get("run_attempt") or 1)
            if latest <= 1:
                continue
            m = DG.RUN_NAME.match(r.get("display_title") or "")
            if not m:
                raise RuntimeError(f"run {r['id']} has an unparseable title")
            t = DG.node_plan(m["node"], int(m["part"]))["timeout_minutes"]
            jobs = DG._api(f"/repos/{slug}/actions/runs/{r['id']}/jobs?per_page=100&filter=all").get("jobs", [])
            total += sum(DG.billed_minutes(j, t) for j in jobs if int(j.get("run_attempt") or latest) < latest)
        if len(batch) < 100:
            break
        page += 1
    return total


def collect(slug: str, owner: str, token_env: str, self_run_id: int | None) -> dict:
    """dispatch_guard.collect with this module's billing reader (the one there calls a closed endpoint)."""
    now = datetime.now(timezone.utc)
    state = {"now": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "self_run_id": self_run_id,
             "billing": read_billing(owner, token_env, now), "runs": []}
    try:
        state["runs"] = DG.read_runs(slug)
        DG.attach_first_guard(slug, state["runs"], now.strftime("%Y-%m"))
    except Exception as exc:  # noqa: BLE001 - every failure is the same fail-closed answer
        state["runs_error"] = str(exc)[:300]
    return state


def guard(a) -> int:
    self_id = a.self_run_id or (int(os.environ["GITHUB_RUN_ID"]) if os.environ.get("GITHUB_RUN_ID") else None)
    attempt = int(os.environ.get("GITHUB_RUN_ATTEMPT") or 1) if a.in_job else 1
    state = collect(a.repo_slug, a.billing_owner or a.repo_slug.split("/")[0], a.billing_token_env,
                    self_id if a.in_job else None)
    try:
        aux = read_aux_runs(a.repo_slug, self_id)
        earlier = earlier_attempt_minutes(a.repo_slug)
    except Exception as exc:  # noqa: BLE001 - every failure is the same fail-closed answer
        state.setdefault("runs_error", f"guard/closure runs: {exc}"[:300])
        aux, earlier = [], 0
    if state.get("runs_error"):
        rec = {"node": a.node, "part": a.part, "decision": DG.NO_DISPATCH,
               "reasons": [f"FAIL_CLOSED: AUTH-2 run history not readable ({state['runs_error']})"],
               "billing": {k: state["billing"].get(k) for k in ("readable", "remaining_included_minutes",
                                                                 "budget_usd_zero", "usage_evidence")}}
    else:
        rec = decide(state, aux, a.node, a.part, attempt, earlier)
    rec["run_attempt"] = int(os.environ.get("GITHUB_RUN_ATTEMPT") or 1)
    rec["mode"] = "in-job" if a.in_job else "pre-dispatch"
    rec["checked_utc"] = state.get("now")
    rec["run_id"] = self_id
    rec["sha"] = os.environ.get("GITHUB_SHA")
    body = json.dumps(rec, indent=1, sort_keys=True) + "\n"
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(body)
    print(body, end="")
    if a.annotate:
        print(annotation_lines(RECORD, body.encode()))
    print(f"AUTH2_DISPATCH_GUARD = {rec['decision']}")
    return 0 if rec["decision"] == DG.DISPATCH else 3


# -- annotations: the one channel from a job to the executor's session --------------------------------

def annotation_lines(title: str, data: bytes) -> str:
    """``::notice`` workflow commands carrying ``data`` as base64 chunks: '<sha256>:<i>/<n>:<chunk>'."""
    sha = hashlib.sha256(data).hexdigest()
    b64 = base64.b64encode(data).decode()
    chunks = [b64[i:i + CHUNK] for i in range(0, len(b64), CHUNK)] or [""]
    n = len(chunks)
    if n > 10:
        raise SystemExit(f"{title}: {len(data)} bytes need {n} annotations; a step may emit at most 10")
    return "\n".join(f"::notice title={title}::{sha}:{i}/{n}:{c}" for i, c in enumerate(chunks, 1))


def decode_annotations(annotations: list[dict], title: str) -> list[bytes]:
    """Every payload titled ``title`` in a job's annotations, each verified against its sha256."""
    groups: dict[str, dict[int, tuple[int, str]]] = {}
    for a in annotations:
        if a.get("title") != title:
            continue
        m = re.fullmatch(r"([0-9a-f]{64}):(\d+)/(\d+):([A-Za-z0-9+/=]*)", (a.get("message") or "").strip())
        if not m:
            raise ValueError(f"{title}: malformed annotation")
        parts = groups.setdefault(m[1], {})
        if int(m[2]) in parts:
            raise ValueError(f"{title}: chunk {m[2]} of {m[1][:12]} published twice")
        parts[int(m[2])] = (int(m[3]), m[4])
    out = []
    for sha, parts in sorted(groups.items()):
        n = {v[0] for v in parts.values()}
        if len(n) != 1 or sorted(parts) != list(range(1, n.pop() + 1)):
            raise ValueError(f"{title}: incomplete chunks for {sha[:12]}")
        data = base64.b64decode("".join(parts[i][1] for i in sorted(parts)))
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError(f"{title}: sha256 mismatch for {sha[:12]}")
        out.append(data)
    return out


def result_summary(path: Path) -> dict:
    """What the frozen DAG (run_node.eligible) and the executor need from one result record."""
    data = path.read_bytes()
    rec = json.loads(data)
    s = {"key": path.name[: -len(".result.json")], "sha256": hashlib.sha256(data).hexdigest(),
         "bytes": len(data), "terminal_state": rec.get("terminal_state"),
         "program_sha256": rec.get("program_sha256")}
    for k in ("data_limited", "holm_pass"):
        if k in rec:
            s[k] = rec[k]
    return s


def annotate_results(directory: Path) -> str:
    files = sorted(directory.glob("*.result.json"))
    body = json.dumps([result_summary(f) for f in files], sort_keys=True).encode()
    return annotation_lines(RESULT, body)


# -- executor side: verify a job's published record -------------------------------------------------

def run_annotations(slug: str, run_id: int) -> tuple[dict, list[dict]]:
    run = DG._api(f"/repos/{slug}/actions/runs/{run_id}")
    jobs = DG._api(f"/repos/{slug}/actions/runs/{run_id}/jobs?per_page=100").get("jobs", [])
    notes: list[dict] = []
    for j in jobs:
        notes += DG._api(f"/repos/{slug}/check-runs/{j['id']}/annotations?per_page=100")
    return run, notes


def check_provenance(run: dict, workflow: str, main_sha: str, title: str | None = None) -> list[str]:
    bad = []
    if run.get("path") != f".github/workflows/{workflow}":
        bad.append(f"run {run.get('id')} is not a run of {workflow}")
    if run.get("event") != "workflow_dispatch" or run.get("head_branch") != "main":
        bad.append(f"run {run.get('id')} is not a workflow_dispatch run on main")
    if run.get("head_sha") != main_sha:
        bad.append(f"run {run.get('id')} ran at {str(run.get('head_sha'))[:12]}, not main {main_sha[:12]}")
    if title is not None and run.get("display_title") != title:
        bad.append(f"run {run.get('id')} is titled {run.get('display_title')!r}, not {title!r}")
    return bad


def check_dispatch(run: dict, notes: list[dict], later_runs: list[dict], node: str, part: int, main_sha: str,
                   now: datetime) -> dict:
    """DISPATCH only if the guard run of (node, part) on this main succeeded, is fresh, decided DISPATCH,
    and no AUTH-2 run was created after it (``later_runs``: every AUTH-2 run, any workflow)."""
    reasons = check_provenance(run, GUARD_WORKFLOW, main_sha, f"AUTH2-GUARD {node} part {part}")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        reasons.append(f"guard run {run.get('id')} did not succeed ({run.get('status')}/{run.get('conclusion')})")
    rec: dict = {}
    try:
        payloads = decode_annotations(notes, RECORD)
        if len(payloads) != 1:
            raise ValueError(f"{len(payloads)} guard records")
        rec = json.loads(payloads[0])
    except ValueError as exc:
        reasons.append(f"guard record unreadable: {exc}")
    if rec:
        if (rec.get("node"), rec.get("part"), rec.get("mode")) != (node, part, "pre-dispatch"):
            reasons.append(f"guard record is for {rec.get('node')} part {rec.get('part')} ({rec.get('mode')})")
        if rec.get("decision") != DG.DISPATCH:
            reasons.append(f"guard decided {rec.get('decision')}: {rec.get('reasons')}")
        if rec.get("run_id") != run.get("id") or rec.get("sha") != main_sha:
            reasons.append("guard record does not name this run and main")
        try:
            age = (now - datetime.fromisoformat(rec["checked_utc"].replace("Z", "+00:00"))).total_seconds() / 60
        except (KeyError, TypeError, ValueError):
            age = None
        if age is None or not 0 <= age <= FRESH_MINUTES:
            reasons.append(f"guard record is not fresh (age {age} min > {FRESH_MINUTES})")
    created = run.get("created_at") or ""
    newer = [r["id"] for r in later_runs if r["id"] != run.get("id") and r["created_at"] >= created]
    if newer:
        reasons.append(f"AUTH-2 run(s) {newer} were created after the guard run")
    active = [r["id"] for r in later_runs if r["id"] != run.get("id") and r["status"] in DG.ACTIVE]
    if active:
        reasons.append(f"SERIAL: AUTH-2 run(s) {active} still active")
    return {"node": node, "part": part, "guard_run": run.get("id"), "main_sha": main_sha,
            "decision": DG.NO_DISPATCH if reasons else DG.DISPATCH, "reasons": reasons, "record": rec}


def all_runs(slug: str) -> list[dict]:
    out = []
    for wf in (DG.WORKFLOW_FILE, GUARD_WORKFLOW, CLOSURE_WORKFLOW):
        page = 1
        while True:
            batch = DG._api(f"/repos/{slug}/actions/workflows/{wf}/runs?per_page=100&page={page}") \
                .get("workflow_runs", [])
            out += [{"id": r["id"], "workflow": wf, "status": r["status"], "created_at": r["created_at"]}
                    for r in batch]
            if len(batch) < 100:
                break
            page += 1
    return out


def published(slug: str, run_id: int, workflow: str, title: str, main_sha: str) -> list[bytes]:
    run, notes = run_annotations(slug, run_id)
    bad = check_provenance(run, workflow, main_sha)
    if bad:
        raise SystemExit("AUTH2_READOUT_REFUSED: " + "; ".join(bad))
    return decode_annotations(notes, title)


def next_nodes(summaries: dict[str, dict]) -> dict:
    """run_node.eligible over the result summaries (the fields it reads, nothing else)."""
    from auth2 import run_node as RN

    return RN.eligible(summaries)


# -- CLI -----------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("guard")
    g.add_argument("--node", required=True)
    g.add_argument("--part", type=int, default=1)
    g.add_argument("--repo-slug", required=True)
    g.add_argument("--billing-owner")
    g.add_argument("--billing-token-env", default="AUTH2_BILLING_TOKEN")
    g.add_argument("--self-run-id", type=int)
    g.add_argument("--in-job", action="store_true", help="the caller is the node's (or closure's) own run")
    g.add_argument("--out")
    g.add_argument("--annotate", action="store_true", help="publish the record as a job annotation")
    c = sub.add_parser("check-dispatch")
    c.add_argument("--guard-run", type=int, required=True)
    c.add_argument("--node", required=True)
    c.add_argument("--part", type=int, default=1)
    c.add_argument("--repo-slug", required=True)
    c.add_argument("--main-sha", required=True)
    n = sub.add_parser("annotate")
    n.add_argument("--title", required=True, choices=[CLOSURE_RECORD])
    n.add_argument("--file", required=True)
    r = sub.add_parser("annotate-results")
    r.add_argument("--dir", required=True)
    x = sub.add_parser("next")
    x.add_argument("--repo-slug", required=True)
    x.add_argument("--main-sha", required=True)
    x.add_argument("runs", nargs="+", type=int, help="the node runs that count, one per node part")
    o = sub.add_parser("readout")
    o.add_argument("--run", type=int, required=True)
    o.add_argument("--title", required=True, choices=[CLOSURE_RECORD])
    o.add_argument("--repo-slug", required=True)
    o.add_argument("--main-sha", required=True)
    o.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "guard":
        if a.node != CLOSURE:
            DG.node_plan(a.node, a.part)  # unknown node or part: KeyError, never a dispatch
        return guard(a)
    if a.cmd == "annotate":
        print(annotation_lines(a.title, Path(a.file).read_bytes()))
        return 0
    if a.cmd == "annotate-results":
        print(annotate_results(Path(a.dir)))
        return 0
    if a.cmd == "check-dispatch":
        run, notes = run_annotations(a.repo_slug, a.guard_run)
        rec = check_dispatch(run, notes, all_runs(a.repo_slug), a.node, a.part, a.main_sha,
                             datetime.now(timezone.utc))
        print(json.dumps(rec, indent=1, sort_keys=True))
        print(f"AUTH2_DISPATCH_CHECK = {rec['decision']}")
        return 0 if rec["decision"] == DG.DISPATCH else 3
    if a.cmd == "next":
        summaries: dict[str, dict] = {}
        for rid in a.runs:
            for payload in published(a.repo_slug, rid, DG.WORKFLOW_FILE, RESULT, a.main_sha):
                for s in json.loads(payload):
                    if s["key"] in summaries:
                        raise SystemExit(f"AUTH2_READOUT_REFUSED: two result records for {s['key']}")
                    summaries[s["key"]] = {**s, "run_id": rid}
        print(json.dumps({"results": summaries, "eligible": next_nodes(summaries)}, indent=1, sort_keys=True))
        return 0
    if a.cmd == "readout":
        payloads = published(a.repo_slug, a.run, CLOSURE_WORKFLOW, a.title, a.main_sha)
        if len(payloads) != 1:
            raise SystemExit(f"AUTH2_READOUT_REFUSED: {len(payloads)} {a.title} payloads")
        Path(a.out).write_bytes(payloads[0])
        print(f"{a.out}: {len(payloads[0])} bytes, sha256 {hashlib.sha256(payloads[0]).hexdigest()}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
