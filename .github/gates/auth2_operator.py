#!/usr/bin/env python3
"""AUTH-2 operator gate: the pre-dispatch guard run in Actions, and the readouts the executor needs.

    python .github/gates/auth2_operator.py guard --node <ID> [--part N] --repo-slug owner/name
                                               [--self-run-id ID] [--out F] [--annotate]
                                               [--in-job --guard-run ID --evidence-digest sha256:HEX]
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

Owner billing evidence (Owner decision AUTH2-OWNER-BILLING-EVIDENCE-BRIDGE-1). GitHub's API exposes neither
pacing-rule control for a personal account, so the Owner states both in the pre-dispatch guard's own
workflow_dispatch: the remaining included Linux minutes the billing page shows, and that the Actions budget is
USD 0 and stops usage. The guard takes them only from a run whose actor and triggering actor, as the Actions API
reports them, are the Owner (OWNER_LOGIN, OWNER_ID), and only beside a usage report the billing token verified
for this account and month; it records them as one Owner-evidence object with a sha256 digest. Every node or
closure dispatch names that guard run and digest. Its in-job guard verifies the binding (``check_dispatch``,
measured at the run's creation, which is the dispatch) and takes the billing state from that record, never from
its own inputs. A_m stays where dispatch_guard keeps it: the in-job guard record of the month's first node run.

PAPER / RESEARCH ONLY. Read-only against GitHub: it dispatches nothing and writes nothing there.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import zipfile
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
# month and the report is well formed, and records it. It never proves either control: only the Owner's
# attestation does (``billing_state``), and only beside a verified report. Without both: NO_DISPATCH.
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

# Owner billing evidence (see the module docstring). The Owner is the repository and account owner; the id
# pins the account, so a renamed or re-registered login cannot attest.
OWNER_LOGIN, OWNER_ID = "algamal119933-ux", 325778659
USAGE_ENDPOINT = BILLING_USAGE.split("?")[0]
EVIDENCE_SCHEMA = "AUTH2_OWNER_BILLING_EVIDENCE_1"
EVIDENCE_FIELDS = {"schema": str, "repository": str, "guard_run_id": int, "guard_run_attempt": int,
                   "main_sha": str, "node": str, "part": int, "actor": str, "actor_id": int,
                   "triggering_actor": str, "triggering_actor_id": int, "billing_month": str,
                   "remaining_included_linux_minutes": int, "budget_usd_zero_confirmed": bool,
                   "stop_usage_confirmed": bool, "attested_utc": str, "usage_api_verified": bool,
                   "usage_endpoint": str, "usage_period": str, "evidence_digest": str}
MINUTES_INPUT = "remaining_included_linux_minutes"
CONFIRMED, NOT_CONFIRMED = "CONFIRMED", "NOT_CONFIRMED"
CONFIRMATIONS = {"actions_budget_usd_zero": "budget_usd_zero_confirmed", "stop_usage_enabled": "stop_usage_confirmed"}
WHOLE_MINUTES = re.compile(r"0|[1-9][0-9]{0,8}")  # digits only: no sign, separator, space or leading zero
RUN_ID = re.compile(r"[1-9][0-9]{0,19}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


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
    rec["reasons"] += state.get("first_record_problems") or []  # why the month's A_m record is not usable
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
                                                "usage_evidence", "owner_evidence", "owner_evidence_problems")}
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
        # The report is per user and names the account's own repositories without an owner (live, guard run
        # 38220977904: "trading-lab-os-sandbox"; GitHub's docs example shows "user/example"). A bare name is
        # therefore this account's; a name qualified with another owner is refused.
        if not isinstance(repo, str) or ("/" in repo and not repo.lower().startswith(owner.lower() + "/")):
            ev.update({"class": "WRONG_ACCOUNT", "detail": f"usage of {str(repo)[:100]} in the report for {owner}"})
            return ev
        if it["product"].lower() == "actions":
            tot = actions.setdefault(it["sku"], {"unitType": it["unitType"], "quantity": 0.0, "grossAmount": 0.0,
                                                 "discountAmount": 0.0, "netAmount": 0.0})
            for k in ("quantity", "grossAmount", "discountAmount", "netAmount"):
                tot[k] = round(tot[k] + float(it[k]), 6)
    ev.update({"verified": True, "class": "USAGE_VERIFIED", "actions": actions})
    return ev


def read_usage(owner: str, token_env: str, now: datetime, get=None) -> dict:
    """This month's usage report read with the billing token, classified (``usage_evidence``); the token is
    redacted from anything recorded. No token: no request at all."""
    token = (os.environ.get(token_env) or "").strip()
    path = BILLING_USAGE.format(owner=owner, year=now.year, month=now.month)
    if not token:
        ev = {"verified": False, "status": None, "class": "TOKEN_MISSING", "period": f"{now.year:04d}-{now.month:02d}",
              "detail": f"{token_env} is not set; the workflow token is never used for billing"}
    else:
        status, body = (get or billing_get)(path, token)
        ev = usage_evidence(owner, now.year, now.month, status, body)
        if "detail" in ev:
            ev["detail"] = ev["detail"].replace(token, "***")
    ev["endpoint"] = path.split("?")[0]
    return ev


def billing_state(usage: dict, owner: dict | None) -> dict:
    """The billing state dispatch_guard.decide reads. GitHub's API exposes neither pacing-rule control for a
    personal account (see BILLING_USAGE above), so ``readable``, the remaining minutes and ``budget_usd_zero``
    come only from valid Owner evidence (``owner`` = {"evidence", "problems"}) together with a usage report the
    billing token verified. Anything less is unreadable, and the decision is NO_DISPATCH."""
    if owner is None:
        owner = {"evidence": None, "problems": ["OWNER_EVIDENCE_MISSING: no authenticated Owner attestation; the "
                                                "Owner gives it in the pre-dispatch guard run"]}
    ev, problems = owner.get("evidence"), list(owner.get("problems") or [])
    if ev is None and not problems:
        problems = ["OWNER_EVIDENCE_MISSING: no Owner evidence object"]
    out = {"usage_evidence": usage, "owner_evidence": ev, "owner_evidence_problems": problems}
    if usage.get("verified") is True and ev is not None and not problems:
        return {**out, "readable": True, "remaining_included_minutes": ev[MINUTES_INPUT], "budget_usd_zero": True}
    used = INCLUDED_NOT_EXPOSED if usage.get("verified") is True else \
        f"{usage.get('class')}: {usage.get('detail')}; {INCLUDED_NOT_EXPOSED}"
    stated = "; ".join(problems) or "the Owner evidence is valid, but the usage report did not verify"
    return {**out, "readable": False, "remaining_included_minutes": None, "budget_usd_zero": False,
            "reason": f"{used}; {stated}", "budget_reason": f"{BUDGET_NOT_EXPOSED}; {stated}"}


def read_billing(owner: str, token_env: str, now: datetime, get=None, owner_evidence: dict | None = None) -> dict:
    """``billing_state`` over this month's usage report."""
    return billing_state(read_usage(owner, token_env, now, get), owner_evidence)


# -- Owner billing evidence (Owner decision AUTH2-OWNER-BILLING-EVIDENCE-BRIDGE-1) --------------------

def evidence_digest(ev: dict) -> str:
    """sha256 of the canonical JSON of every field but the digest itself."""
    body = {k: v for k, v in ev.items() if k != "evidence_digest"}
    return "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def who(user) -> tuple:
    return (user.get("login"), user.get("id")) if isinstance(user, dict) else (None, None)


def parse_owner_inputs(inputs) -> tuple[dict | None, list[str]]:
    """The Owner's three guard inputs, strictly: a whole number of minutes (digits only, no sign, separator,
    space or leading zero) and CONFIRMED or NOT_CONFIRMED for each confirmation. Nothing is coerced."""
    if not isinstance(inputs, dict):
        return None, ["OWNER_EVIDENCE_MISSING: the guard run carries no workflow_dispatch inputs"]
    missing = [k for k in (MINUTES_INPUT, *CONFIRMATIONS) if inputs.get(k) in (None, "")]
    if missing:
        return None, [f"OWNER_EVIDENCE_MISSING: no {', '.join(missing)}"]
    problems, values = [], {}
    raw = inputs[MINUTES_INPUT]
    if not isinstance(raw, str) or not WHOLE_MINUTES.fullmatch(raw):
        problems.append(f"OWNER_EVIDENCE_REMAINING_INVALID: {str(raw)[:40]!r} is not a whole number of minutes "
                        "(digits only: no sign, separator, space or leading zero)")
    for key, field in CONFIRMATIONS.items():
        if inputs[key] not in (CONFIRMED, NOT_CONFIRMED):
            problems.append(f"OWNER_EVIDENCE_MALFORMED: {key} is {str(inputs[key])[:40]!r}, not {CONFIRMED} "
                            f"or {NOT_CONFIRMED}")
        values[field] = inputs[key] == CONFIRMED
    if problems:
        return None, problems
    values[MINUTES_INPUT] = int(raw)
    return values, []


def owner_evidence_problems(ev, *, slug: str, guard_run_id, main_sha: str, node: str, part: int,
                            month: str) -> list[str]:
    """Why ``ev`` is not valid Owner evidence for this guard run, repository, main, node part and billing month
    ([] when it is). The digest covers every other field, so any change to the object is refused."""
    if not isinstance(ev, dict):
        return ["OWNER_EVIDENCE_MISSING: no Owner evidence object"]
    if set(ev) != set(EVIDENCE_FIELDS):
        return [f"OWNER_EVIDENCE_MALFORMED: fields {sorted(set(ev) ^ set(EVIDENCE_FIELDS))} differ from the schema"]
    bad = sorted(k for k, kind in EVIDENCE_FIELDS.items()
                 if not isinstance(ev[k], kind) or (kind is int and isinstance(ev[k], bool)))
    if bad:
        return [f"OWNER_EVIDENCE_MALFORMED: {bad} mistyped"]
    p = []
    if ev["schema"] != EVIDENCE_SCHEMA:
        p.append(f"OWNER_EVIDENCE_MALFORMED: schema {ev['schema'][:40]!r}, not {EVIDENCE_SCHEMA}")
    if not DIGEST.fullmatch(ev["evidence_digest"]) or ev["evidence_digest"] != evidence_digest(ev):
        p.append("OWNER_EVIDENCE_DIGEST_MISMATCH: the evidence does not hash to its digest")
    if (ev["actor"], ev["actor_id"]) != (OWNER_LOGIN, OWNER_ID) or \
            (ev["triggering_actor"], ev["triggering_actor_id"]) != (OWNER_LOGIN, OWNER_ID):
        p.append(f"OWNER_EVIDENCE_ACTOR_MISMATCH: dispatched by {ev['triggering_actor'][:40]} "
                 f"({ev['triggering_actor_id']}) as {ev['actor'][:40]} ({ev['actor_id']}); only the Owner "
                 f"{OWNER_LOGIN} ({OWNER_ID}) attests billing")
    if ev["repository"] != slug:
        p.append(f"OWNER_EVIDENCE_WRONG_REPOSITORY: {ev['repository'][:100]}, not {slug}")
    if ev["guard_run_id"] != guard_run_id:
        p.append(f"OWNER_EVIDENCE_WRONG_RUN: the evidence is guard run {ev['guard_run_id']}'s, not {guard_run_id}'s")
    if ev["guard_run_attempt"] != 1:
        p.append(f"OWNER_EVIDENCE_REPLAYED: attempt {ev['guard_run_attempt']} of a guard run re-uses the inputs "
                 "given at its first attempt")
    if ev["main_sha"] != main_sha:
        p.append(f"OWNER_EVIDENCE_WRONG_SHA: given at {ev['main_sha'][:12]}, not {str(main_sha)[:12]}")
    if (ev["node"], ev["part"]) != (node, part):
        p.append(f"OWNER_EVIDENCE_WRONG_NODE: given for {ev['node'][:20]} part {ev['part']}, not {node} part {part}")
    if not (ev["billing_month"] == ev["usage_period"] == ev["attested_utc"][:7] == month):
        p.append(f"OWNER_EVIDENCE_WRONG_MONTH: attested {ev['attested_utc'][:7]} for {ev['billing_month'][:7]} "
                 f"(usage report {ev['usage_period'][:7]}), billing month now {month}")
    if ev[MINUTES_INPUT] < 0:
        p.append(f"OWNER_EVIDENCE_REMAINING_INVALID: {ev[MINUTES_INPUT]} is negative")
    if ev["budget_usd_zero_confirmed"] is not True:
        p.append("OWNER_EVIDENCE_BUDGET_NOT_CONFIRMED: the Owner did not confirm an Actions budget of USD 0")
    if ev["stop_usage_confirmed"] is not True:
        p.append("OWNER_EVIDENCE_STOP_USAGE_NOT_CONFIRMED: the Owner did not confirm that the budget stops usage")
    if ev["usage_api_verified"] is not True or ev["usage_endpoint"] != USAGE_ENDPOINT.format(owner=OWNER_LOGIN):
        p.append("OWNER_EVIDENCE_USAGE_NOT_VERIFIED: the Owner's own usage report was not verified with the "
                 "billing token beside the attestation")
    try:
        datetime.strptime(ev["attested_utc"], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        p.append(f"OWNER_EVIDENCE_MALFORMED: attested_utc {ev['attested_utc'][:40]!r}")
    return p


def presented_evidence(run: dict, event: dict, *, slug: str, node: str, part: int, now: datetime,
                       usage: dict) -> dict:
    """The Owner evidence a pre-dispatch guard run carries: its own workflow_dispatch inputs (``event``, the
    payload GitHub delivered), attributed to the actor and triggering actor the Actions API reports for the run
    (``run``), never to an environment value, repository variable, committed file or secret."""
    month = now.strftime("%Y-%m")
    problems = [f"OWNER_EVIDENCE_PROVENANCE: {x}" for x in
                check_provenance(run, GUARD_WORKFLOW, run.get("head_sha") or "", f"AUTH2-GUARD {node} part {part}")]
    if (run.get("repository") or {}).get("full_name") != slug:
        problems.append(f"OWNER_EVIDENCE_WRONG_REPOSITORY: run {run.get('id')} is not a run of {slug}")
    event = event if isinstance(event, dict) else {}
    given = event.get("inputs")
    if isinstance(given, dict) and (given.get("node"), given.get("part")) != (node, str(part)):
        problems.append("OWNER_EVIDENCE_WRONG_NODE: the dispatch inputs name another node part")
    if who(event.get("sender")) != who(run.get("triggering_actor")):
        problems.append("OWNER_EVIDENCE_ACTOR_MISMATCH: the event sender is not the run's triggering actor")
    values, bad = parse_owner_inputs(given)
    problems += bad
    ev = None
    if values is not None:
        (actor, actor_id), (trig, trig_id) = who(run.get("actor")), who(run.get("triggering_actor"))
        ev = {"schema": EVIDENCE_SCHEMA, "repository": slug, "guard_run_id": run.get("id"),
              "guard_run_attempt": run.get("run_attempt"), "main_sha": run.get("head_sha"), "node": node,
              "part": part, "actor": actor, "actor_id": actor_id, "triggering_actor": trig,
              "triggering_actor_id": trig_id, "billing_month": month, **values,
              "attested_utc": run.get("created_at"), "usage_api_verified": usage.get("verified") is True,
              "usage_endpoint": usage.get("endpoint"), "usage_period": usage.get("period")}
        ev["evidence_digest"] = evidence_digest(ev)
        problems += owner_evidence_problems(ev, slug=slug, guard_run_id=run.get("id"), main_sha=run.get("head_sha"),
                                            node=node, part=part, month=month)
    return {"evidence": ev, "problems": list(dict.fromkeys(problems))}


def month_first_record(records: list, run: dict, month: str, slug: str) -> tuple[dict | None, list[str]]:
    """The record A_m is read from (dispatch_guard keeps it there): the in-job guard record of the month's first
    node run. It must be that run's own, for this month, with A_m >= 0 and R_m = max(500, ceil(0.20 x A_m)); no
    other record of the run may state another A_m; and A_m must be the remaining minutes of the valid Owner
    evidence that run was dispatched on, so it is the Owner-attested value at the month's first node dispatch."""
    tag = f"the month's first AUTH-2 node run {run['id']}"
    stated = [r for r in records if isinstance(r, dict) and r.get("mode") == "in-job" and r.get("run_id") == run["id"]
              and "a_m" in r]
    if not stated:
        return None, [f"FAIL_CLOSED: {tag} has no in-job guard record stating A_m, so R_m is unknown"]
    if len({json.dumps([r.get("month"), r.get("a_m"), r.get("r_m")]) for r in stated}) > 1:
        return None, [f"FAIL_CLOSED: {tag} has conflicting A_m records "
                      f"{sorted({str(r.get('a_m')) for r in stated})}"]
    rec = stated[0]
    a_m = rec.get("a_m")
    if rec.get("month") != month or not isinstance(a_m, int) or isinstance(a_m, bool) or a_m < 0 \
            or rec.get("r_m") != DG.reserve(a_m) or (rec.get("node"), rec.get("part")) != (run["node"], run["part"]):
        return None, [f"FAIL_CLOSED: {tag} has an invalid A_m record (month {rec.get('month')}, A_m {a_m}, "
                      f"R_m {rec.get('r_m')}, {rec.get('node')} part {rec.get('part')})"]
    bill = rec.get("billing") if isinstance(rec.get("billing"), dict) else {}
    bound = rec.get("binding") if isinstance(rec.get("binding"), dict) else {}
    ev = bill.get("owner_evidence")
    bad = owner_evidence_problems(ev, slug=slug, guard_run_id=bound.get("guard_run"), main_sha=rec.get("sha"),
                                  node=run["node"], part=run["part"], month=month)
    if bad or ev["evidence_digest"] != bound.get("evidence_digest") or ev[MINUTES_INPUT] != a_m \
            or rec.get("remaining_included_minutes") != a_m:
        return None, [f"FAIL_CLOSED: {tag}'s A_m does not rest on the Owner evidence it was dispatched on"
                      + (f" ({'; '.join(bad)[:300]})" if bad else "")]
    return rec, []


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


def guard_records(slug: str, run_id: int, match) -> list[bytes]:
    """Every guard.json in the run's artifacts whose name ``match`` accepts (read inside Actions; the executor's
    session cannot download artifacts and reads the annotation instead)."""
    out = []
    for a in DG._api(f"/repos/{slug}/actions/runs/{run_id}/artifacts?per_page=100").get("artifacts", []):
        if match(a["name"]) and not a.get("expired"):
            with zipfile.ZipFile(io.BytesIO(DG._api_bytes(f"/repos/{slug}/actions/artifacts/{a['id']}/zip"))) as z:
                out += [z.read(n) for n in z.namelist() if n.endswith("guard.json")]
    return out


def attach_first_record(slug: str, runs: list[dict], month: str, self_run_id: int | None) -> list[str]:
    """dispatch_guard.attach_first_guard, strict: every guard record of the month's first node run is read (all
    attempts), and ``month_first_record`` decides; the runs and the order are dispatch_guard.decide's."""
    firsts = sorted((r for r in runs if r["created_at"][:7] == month and r["id"] != self_run_id),
                    key=lambda r: r["created_at"])
    if not firsts:
        return []
    first = firsts[0]
    try:
        records = [json.loads(b) for b in guard_records(slug, first["id"], lambda n: n.startswith("auth2-"))]
    except (ValueError, zipfile.BadZipFile) as exc:
        return [f"FAIL_CLOSED: the guard record of the month's first AUTH-2 node run {first['id']} is unreadable "
                f"({str(exc)[:120]})"]
    first["guard"], problems = month_first_record(records, first, month, slug)
    return problems


def collect(slug: str, owner: str, token_env: str, self_run_id: int | None, owner_evidence: dict | None = None,
            now: datetime | None = None, usage: dict | None = None) -> dict:
    """dispatch_guard.collect with this module's billing state (the reader there calls a closed endpoint) and
    the strict reader of the month's A_m record."""
    now = now or datetime.now(timezone.utc)
    usage = usage if usage is not None else read_usage(owner, token_env, now)
    state = {"now": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "self_run_id": self_run_id,
             "billing": billing_state(usage, owner_evidence), "runs": []}
    try:
        state["runs"] = DG.read_runs(slug)
        state["first_record_problems"] = attach_first_record(slug, state["runs"], now.strftime("%Y-%m"),
                                                             self_run_id)
    except Exception as exc:  # noqa: BLE001 - every failure is the same fail-closed answer
        state["runs_error"] = str(exc)[:300]
    return state


def presented(slug: str, node: str, part: int, self_run_id: int | None, now: datetime, usage: dict) -> dict:
    """Pre-dispatch: the Owner evidence of this guard run (``presented_evidence`` over the Actions API's run and
    the event payload GitHub delivered to the job)."""
    path = os.environ.get("GITHUB_EVENT_PATH")
    if not self_run_id or not path:
        return {"evidence": None, "problems": ["OWNER_EVIDENCE_MISSING: not a guard workflow run; the Owner gives "
                                               "the evidence when dispatching one"]}
    try:
        run = DG._api(f"/repos/{slug}/actions/runs/{self_run_id}")
        event = json.loads(Path(path).read_text())
    except Exception as exc:  # noqa: BLE001
        return {"evidence": None, "problems": [f"OWNER_EVIDENCE_MISSING: the guard run is unreadable "
                                               f"({str(exc)[:200]})"]}
    got = presented_evidence(run, event, slug=slug, node=node, part=part, now=now, usage=usage)
    if os.environ.get("GITHUB_SHA") not in (None, run.get("head_sha")):
        got["problems"].append("OWNER_EVIDENCE_WRONG_SHA: the job's checkout is not the run's commit")
    return got


def bound_evidence(slug: str, node: str, part: int, self_run_id: int | None, guard_run: str | None,
                   digest: str | None, now: datetime) -> dict:
    """In-job: the Owner evidence of the pre-dispatch guard run this node or closure run was dispatched on.
    ``check_dispatch`` verifies the binding as of this run's creation (its dispatch); the evidence is taken from
    that guard record, never from this run's inputs, which only name it."""
    if not (guard_run and RUN_ID.fullmatch(guard_run) and digest and DIGEST.fullmatch(digest) and self_run_id):
        return {"evidence": None, "problems": ["OWNER_EVIDENCE_BINDING_MISSING: the dispatch must name the guard "
                                               "run and its evidence digest (sha256:...)"]}
    workflow, title = (CLOSURE_WORKFLOW, CLOSURE_TITLE) if node == CLOSURE else \
        (DG.WORKFLOW_FILE, f"AUTH2 {node} part {part}")
    try:
        me = DG._api(f"/repos/{slug}/actions/runs/{self_run_id}")
        run = DG._api(f"/repos/{slug}/actions/runs/{int(guard_run)}")
        later = all_runs(slug)
        at = datetime.fromisoformat(me["created_at"].replace("Z", "+00:00"))
    except Exception as exc:  # noqa: BLE001
        return {"evidence": None, "problems": [f"OWNER_EVIDENCE_BINDING_UNREADABLE: {str(exc)[:200]}"]}
    try:
        records: list[bytes] | Exception = guard_records(slug, int(guard_run),
                                                         lambda n: n == f"auth2guard-{node}-p{part}")
    except Exception as exc:  # noqa: BLE001
        records = ValueError(str(exc)[:200])
    sha = me.get("head_sha") or ""
    problems = [f"OWNER_EVIDENCE_BINDING: {x}" for x in check_provenance(me, workflow, sha, title)]
    if os.environ.get("GITHUB_SHA") not in (None, sha):
        problems.append("OWNER_EVIDENCE_BINDING: the job's checkout is not the run's commit")
    got = check_dispatch(run, records, later, node, part, sha, at, slug=slug, self_run_id=self_run_id,
                         digest=digest, month=now.strftime("%Y-%m"))
    problems += [f"OWNER_EVIDENCE_BINDING: {x}" for x in got["reasons"]]
    return {"evidence": None if problems else got["owner_evidence"], "problems": problems,
            "binding": {"guard_run": int(guard_run), "evidence_digest": digest}}


def guard(a) -> int:
    self_id = a.self_run_id or (int(os.environ["GITHUB_RUN_ID"]) if os.environ.get("GITHUB_RUN_ID") else None)
    attempt = int(os.environ.get("GITHUB_RUN_ATTEMPT") or 1) if a.in_job else 1
    owner = a.billing_owner or a.repo_slug.split("/")[0]
    now = datetime.now(timezone.utc)
    usage = read_usage(owner, a.billing_token_env, now)
    if a.in_job:
        evidence = bound_evidence(a.repo_slug, a.node, a.part, self_id, a.guard_run, a.evidence_digest, now)
    else:
        evidence = presented(a.repo_slug, a.node, a.part, self_id, now, usage)
    state = collect(a.repo_slug, owner, a.billing_token_env, self_id if a.in_job else None, evidence, now, usage)
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
                                                                 "budget_usd_zero", "usage_evidence",
                                                                 "owner_evidence", "owner_evidence_problems")}}
    else:
        rec = decide(state, aux, a.node, a.part, attempt, earlier)
    if a.in_job:
        rec["binding"] = evidence.get("binding") or {"guard_run": a.guard_run, "evidence_digest": a.evidence_digest}
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


def annotated_records(notes: list[dict]) -> list[bytes] | ValueError:
    """The guard records a job published as annotations, or why they cannot be read."""
    try:
        return decode_annotations(notes, RECORD)
    except ValueError as exc:
        return exc


def check_dispatch(run: dict, records: list[bytes] | Exception, later_runs: list[dict], node: str, part: int,
                   main_sha: str, now: datetime, *, slug: str, self_run_id: int | None = None,
                   digest: str | None = None, month: str | None = None) -> dict:
    """DISPATCH only if the guard run of (node, part) on this main and repository succeeded at its first attempt,
    was dispatched by the Owner, is fresh, decided DISPATCH on valid Owner evidence beside a verified usage report,
    and no AUTH-2 run was created after it (``later_runs``: every AUTH-2 run, any workflow).

    ``records`` are the guard records the run published (or the error reading them). The executor calls this
    before dispatching (``now`` = now). A node or closure run calls it in the job on the guard run it names, with
    its own id as ``self_run_id``, its creation time (the dispatch) as ``now``, the digest it was dispatched with
    and the billing month it runs in."""
    month = month or now.strftime("%Y-%m")
    reasons = check_provenance(run, GUARD_WORKFLOW, main_sha, f"AUTH2-GUARD {node} part {part}")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        reasons.append(f"guard run {run.get('id')} did not succeed ({run.get('status')}/{run.get('conclusion')})")
    if run.get("run_attempt") != 1:
        reasons.append(f"OWNER_EVIDENCE_REPLAYED: guard run {run.get('id')} is at attempt {run.get('run_attempt')}; "
                       "a re-run replays the inputs of its first attempt")
    if (run.get("repository") or {}).get("full_name") != slug:
        reasons.append(f"guard run {run.get('id')} is not a run of {slug}")
    if who(run.get("actor")) != (OWNER_LOGIN, OWNER_ID) or who(run.get("triggering_actor")) != (OWNER_LOGIN, OWNER_ID):
        reasons.append(f"OWNER_EVIDENCE_ACTOR_MISMATCH: guard run {run.get('id')} was dispatched by "
                       f"{who(run.get('triggering_actor'))} as {who(run.get('actor'))}, not by the Owner "
                       f"{(OWNER_LOGIN, OWNER_ID)}")
    rec: dict = {}
    try:
        if isinstance(records, Exception):
            raise ValueError(str(records))
        if len(records) != 1:
            raise ValueError(f"{len(records)} guard records")
        rec = json.loads(records[0])
        if not isinstance(rec, dict):
            raise ValueError("not a record")
    except ValueError as exc:
        reasons.append(f"guard record unreadable: {exc}")
        rec = {}
    ev = None
    if rec:
        if (rec.get("node"), rec.get("part"), rec.get("mode")) != (node, part, "pre-dispatch"):
            reasons.append(f"guard record is for {rec.get('node')} part {rec.get('part')} ({rec.get('mode')})")
        if rec.get("decision") != DG.DISPATCH:
            reasons.append(f"guard decided {rec.get('decision')}: {rec.get('reasons')}")
        if rec.get("run_id") != run.get("id") or rec.get("sha") != main_sha or rec.get("run_attempt") != 1:
            reasons.append("guard record does not name this run, its first attempt and main")
        try:
            age = (now - datetime.fromisoformat(rec["checked_utc"].replace("Z", "+00:00"))).total_seconds() / 60
        except (KeyError, TypeError, ValueError, AttributeError):
            age = None
        if age is None or not 0 <= age <= FRESH_MINUTES:
            reasons.append(f"guard record is not fresh (age {age} min > {FRESH_MINUTES})")
        bill = rec.get("billing") if isinstance(rec.get("billing"), dict) else {}
        ev = bill.get("owner_evidence")
        bad = owner_evidence_problems(ev, slug=slug, guard_run_id=run.get("id"), main_sha=main_sha, node=node,
                                      part=part, month=month)
        reasons += bad
        if not bad:
            if ev["attested_utc"] != run.get("created_at"):
                reasons.append("OWNER_EVIDENCE_BINDING: the attestation time is not the guard run's dispatch")
            if (bill.get("readable"), bill.get("remaining_included_minutes"), bill.get("budget_usd_zero")) != \
                    (True, ev[MINUTES_INPUT], True):
                reasons.append("guard record's billing state does not rest on its Owner evidence")
            if digest is not None and ev["evidence_digest"] != digest:
                reasons.append(f"OWNER_EVIDENCE_DIGEST_MISMATCH: dispatched with {digest[:19]}..., the guard "
                               f"record holds {ev['evidence_digest'][:19]}...")
        usage = bill.get("usage_evidence") if isinstance(bill.get("usage_evidence"), dict) else {}
        if (usage.get("verified"), usage.get("class"), usage.get("period"), usage.get("endpoint")) != \
                (True, "USAGE_VERIFIED", month, USAGE_ENDPOINT.format(owner=OWNER_LOGIN)):
            reasons.append(f"the guard record's usage report is not verified for {month} "
                           f"({usage.get('class')}, {usage.get('period')})")
    created = run.get("created_at") or ""
    others = [r for r in later_runs if r["id"] not in (run.get("id"), self_run_id)]
    newer = [r["id"] for r in others if r["created_at"] >= created]
    if newer:
        reasons.append(f"AUTH-2 run(s) {newer} were created after the guard run")
    active = [r["id"] for r in others if r["status"] in DG.ACTIVE]
    if active:
        reasons.append(f"SERIAL: AUTH-2 run(s) {active} still active")
    reasons = list(dict.fromkeys(reasons))
    ok = not reasons
    return {"node": node, "part": part, "guard_run": run.get("id"), "main_sha": main_sha,
            "decision": DG.DISPATCH if ok else DG.NO_DISPATCH, "reasons": reasons, "record": rec,
            "owner_evidence": ev if ok else None,
            "dispatch_inputs": {"node": node, "part": str(part), "guard_run": str(run.get("id")),
                                "evidence_digest": ev["evidence_digest"]} if ok else None}


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
    g.add_argument("--guard-run", help="in-job: the pre-dispatch guard run this dispatch names")
    g.add_argument("--evidence-digest", help="in-job: the Owner evidence digest this dispatch names")
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
        rec = check_dispatch(run, annotated_records(notes), all_runs(a.repo_slug), a.node, a.part, a.main_sha,
                             datetime.now(timezone.utc), slug=a.repo_slug)
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
