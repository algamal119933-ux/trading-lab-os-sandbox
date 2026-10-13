#!/usr/bin/env python3
"""AUTH-2-DISCOVERY-QUALIFICATION-2 readiness gate: the check at the start of every readiness run, the 300-minute
readiness ledger, and readiness tests RT-8 and RT-9 (Owner decisions OD-S3, OD-S4 and OD-S7; review section 4).

    python .github/gates/auth2q2_readiness.py gate --test RT-n --repo-slug O/R --out F [--annotate]
    python .github/gates/auth2q2_readiness.py ledger --repo-slug O/R                     (readout, no billing)
    python .github/gates/auth2q2_readiness.py rt8 --repo-slug O/R --gate F --out F       (RT-8)
    python .github/gates/auth2q2_readiness.py rt9 --repo-slug O/R --gate F --out F       (RT-9)
    python .github/gates/auth2q2_readiness.py annotate --title AUTH2Q2_GATE|AUTH2Q2_RT --file F
    python .github/gates/auth2q2_readiness.py outputs --gate F                           (the gate job's outputs)

Every readiness run is dispatched by the Owner, one at a time, and starts with this gate, which runs AUTH-2's
billing check (auth2_operator.py, imported and unchanged) for the run's test. It decides DISPATCH, PARK or
NO_DISPATCH, and the test's jobs run only after DISPATCH. Each check only adds a refusal; anything it cannot read
is a refusal (fail closed):

  PROVENANCE   a workflow_dispatch run of the test's workflow, on main, at main's current commit, titled for its
               test, at its first attempt (a re-run is refused: its inputs are the first attempt's)
  OWNER        the Owner's billing evidence from this run's own dispatch inputs, attributed to the actor and
               triggering actor the Actions API reports, beside this month's usage report read with
               AUTH2_BILLING_TOKEN (never the workflow token): the remaining included Linux minutes the billing page
               shows, an Actions budget of USD 0 and stop usage. GitHub's API exposes none of the three for a
               personal account, so nothing is derived: no evidence, NO_DISPATCH
  SERIAL       no other readiness or AUTH-2 run is active
  CAP          readiness ledger + this run's planned maximum + one more gate run <= 300 (OD-S4). The ledger is
               the billed minutes of every job of every attempt of every readiness run (jobs API; a job not
               finished counts timeout + 1); a job the plan does not name, or a finished run with no jobs that
               GitHub did not cancel or skip, cannot be reconciled and is refused
  RESERVE      remaining included minutes - this run's planned maximum >= R_m = max(500, ceil(0.20 x A_m)),
               A_m the remaining minutes the Owner stated at the month's first admitted readiness run; else PARK
  TEST         RT-1 only while the run's commit has at most one published snapshot release (RT-1 again at the
               same commit verifies that release and changes nothing; at a new commit it publishes that commit's
               own); every test that reads the snapshot only while the run's commit has exactly one published,
               immutable, complete snapshot release, the bot's, its tag naming and pointing at that commit
               (release.py: one release per snapshot address and readiness commit; other commits' releases are
               history and never read); RT-8 only with a billing reading of this month at least
               STORAGE_INTERVAL_HOURS old

The decision record is published as an artifact and as an annotation. The ledger is separate from the successor
program's 4,000 minutes (OD-S7). Nothing here dispatches, writes GitHub, reads market data or runs a strategy.
PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

_GATES = Path(__file__).resolve().parent
REPO = _GATES.parents[1]
for extra in (_GATES, REPO / "research"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import auth2_operator as OP  # noqa: E402
from auth2 import dispatch_guard as DG  # noqa: E402
from auth2q2 import attempts as AT  # noqa: E402
from auth2q2 import compute as C  # noqa: E402
from auth2q2 import plan as PL  # noqa: E402
from auth2q2 import release as RL  # noqa: E402

GATE_SCHEMA = "AUTH2Q2_READINESS_GATE_1"
EVIDENCE_SCHEMA = "AUTH2Q2_READINESS_BILLING_EVIDENCE_1"
EVIDENCE_FIELDS = {"schema": str, "repository": str, "run_id": int, "run_attempt": int, "main_sha": str,
                   "test": str, "actor": str, "actor_id": int, "triggering_actor": str, "triggering_actor_id": int,
                   "billing_month": str, "remaining_included_linux_minutes": int, "budget_usd_zero_confirmed": bool,
                   "stop_usage_confirmed": bool, "attested_utc": str, "usage_api_verified": bool,
                   "usage_endpoint": str, "usage_period": str, "evidence_digest": str}
GATE_TITLE, RT_TITLE = "AUTH2Q2_GATE", "AUTH2Q2_RT"
GATE_ARTIFACT = "auth2q2-gate"
AUTH2_WORKFLOWS = (DG.WORKFLOW_FILE, OP.GUARD_WORKFLOW, OP.CLOSURE_WORKFLOW)
NEVER_STARTED = ("cancelled", "skipped", "startup_failure")
STORAGE_SKU = "Actions storage"
LINUX_SKU = "Actions Linux"
STORAGE_RATE_GB = 0.5          # RT-8: the release (~1 GB) would show as >= 1 GB of Actions storage
ARTIFACT_LIMIT_BYTES = 50 * 10 ** 6   # "far below 500 MB"
CACHE_LIMIT_BYTES = 10 * 1024 ** 3


def _ts(raw) -> datetime | None:
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


# -- Owner billing evidence for a readiness run --------------------------------------------------------

def evidence_problems(ev, *, slug: str, run_id, main_sha: str, test: str, month: str) -> list[str]:
    """Why ``ev`` is not valid Owner evidence for this readiness run ([] when it is); auth2_operator's rules
    with the test in place of the node part. The digest covers every other field."""
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
    if not OP.DIGEST.fullmatch(ev["evidence_digest"]) or ev["evidence_digest"] != OP.evidence_digest(ev):
        p.append("OWNER_EVIDENCE_DIGEST_MISMATCH: the evidence does not hash to its digest")
    if (ev["actor"], ev["actor_id"]) != (OP.OWNER_LOGIN, OP.OWNER_ID) or \
            (ev["triggering_actor"], ev["triggering_actor_id"]) != (OP.OWNER_LOGIN, OP.OWNER_ID):
        p.append(f"OWNER_EVIDENCE_ACTOR_MISMATCH: dispatched by {ev['triggering_actor'][:40]} "
                 f"({ev['triggering_actor_id']}) as {ev['actor'][:40]} ({ev['actor_id']}); only the Owner "
                 f"{OP.OWNER_LOGIN} ({OP.OWNER_ID}) attests billing")
    if ev["repository"] != slug:
        p.append(f"OWNER_EVIDENCE_WRONG_REPOSITORY: {ev['repository'][:100]}, not {slug}")
    if ev["run_id"] != run_id:
        p.append(f"OWNER_EVIDENCE_WRONG_RUN: the evidence is run {ev['run_id']}'s, not {run_id}'s")
    if ev["run_attempt"] != 1:
        p.append(f"OWNER_EVIDENCE_REPLAYED: attempt {ev['run_attempt']} re-uses the inputs of the first attempt")
    if ev["main_sha"] != main_sha:
        p.append(f"OWNER_EVIDENCE_WRONG_SHA: given at {ev['main_sha'][:12]}, not {str(main_sha)[:12]}")
    if ev["test"] != test:
        p.append(f"OWNER_EVIDENCE_WRONG_TEST: given for {ev['test'][:10]}, not {test}")
    if not (ev["billing_month"] == ev["usage_period"] == ev["attested_utc"][:7] == month):
        p.append(f"OWNER_EVIDENCE_WRONG_MONTH: attested {ev['attested_utc'][:7]} for {ev['billing_month'][:7]} "
                 f"(usage report {ev['usage_period'][:7]}), billing month now {month}")
    if ev[OP.MINUTES_INPUT] < 0:
        p.append(f"OWNER_EVIDENCE_REMAINING_INVALID: {ev[OP.MINUTES_INPUT]} is negative")
    if ev["budget_usd_zero_confirmed"] is not True:
        p.append("OWNER_EVIDENCE_BUDGET_NOT_CONFIRMED: the Owner did not confirm an Actions budget of USD 0")
    if ev["stop_usage_confirmed"] is not True:
        p.append("OWNER_EVIDENCE_STOP_USAGE_NOT_CONFIRMED: the Owner did not confirm that the budget stops usage")
    if ev["usage_api_verified"] is not True or ev["usage_endpoint"] != OP.USAGE_ENDPOINT.format(owner=OP.OWNER_LOGIN):
        p.append("OWNER_EVIDENCE_USAGE_NOT_VERIFIED: the Owner's own usage report was not verified with the "
                 "billing token beside the attestation")
    try:
        datetime.strptime(ev["attested_utc"], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        p.append(f"OWNER_EVIDENCE_MALFORMED: attested_utc {ev['attested_utc'][:40]!r}")
    return p


def presented_evidence(run: dict, event, *, slug: str, test: str, month: str, usage: dict) -> dict:
    """The Owner evidence this readiness run carries: its own workflow_dispatch inputs (``event``, the payload
    GitHub delivered), attributed to the actor and triggering actor the Actions API reports (``run``), never to
    an environment value, repository variable, committed file or secret."""
    wf = PL.workflow_of(test)
    problems = [f"OWNER_EVIDENCE_PROVENANCE: {x}" for x in
                OP.check_provenance(run, wf, run.get("head_sha") or "", PL.TITLE.format(test=test))]
    if (run.get("repository") or {}).get("full_name") != slug:
        problems.append(f"OWNER_EVIDENCE_WRONG_REPOSITORY: run {run.get('id')} is not a run of {slug}")
    event = event if isinstance(event, dict) else {}
    given = event.get("inputs")
    if not isinstance(given, dict) or given.get("test") != test:
        problems.append("OWNER_EVIDENCE_WRONG_TEST: the dispatch inputs name another test")
    if OP.who(event.get("sender")) != OP.who(run.get("triggering_actor")):
        problems.append("OWNER_EVIDENCE_ACTOR_MISMATCH: the event sender is not the run's triggering actor")
    values, bad = OP.parse_owner_inputs(given)
    problems += bad
    ev = None
    if values is not None:
        (actor, actor_id), (trig, trig_id) = OP.who(run.get("actor")), OP.who(run.get("triggering_actor"))
        ev = {"schema": EVIDENCE_SCHEMA, "repository": slug, "run_id": run.get("id"),
              "run_attempt": run.get("run_attempt"), "main_sha": run.get("head_sha"), "test": test, "actor": actor,
              "actor_id": actor_id, "triggering_actor": trig, "triggering_actor_id": trig_id, "billing_month": month,
              **values, "attested_utc": run.get("created_at"), "usage_api_verified": usage.get("verified") is True,
              "usage_endpoint": usage.get("endpoint"), "usage_period": usage.get("period")}
        ev["evidence_digest"] = OP.evidence_digest(ev)
        problems += evidence_problems(ev, slug=slug, run_id=run.get("id"), main_sha=run.get("head_sha"), test=test,
                                      month=month)
    return {"evidence": ev, "problems": list(dict.fromkeys(problems))}


# -- the readiness ledger --------------------------------------------------------------------------------

def run_minutes(run: dict, jobs: list[dict]) -> tuple[int, list[dict], list[str]]:
    """(billed minutes, per-job rows, problems) of one readiness run, every attempt of every job."""
    wf = (run.get("path") or "").removeprefix(".github/workflows/")
    if wf not in PL.WORKFLOWS:
        return 0, [], [f"run {run.get('id')} is not a readiness run ({run.get('path')})"]
    if not jobs:
        if run.get("status") == "completed" and run.get("conclusion") in NEVER_STARTED:
            return 0, [], []
        if run.get("status") != "completed":
            return PL.GATE_TIMEOUT + 1, [], []  # a queued run's gate, at most
        return 0, [], [f"run {run.get('id')} finished {run.get('conclusion')} with no jobs; it cannot be reconciled"]
    rows, problems, total = [], [], 0
    for j in jobs:
        t = PL.timeout_of(wf, j.get("name"))
        if t is None:
            problems.append(f"run {run.get('id')}: job {str(j.get('name'))[:80]!r} is not in the readiness plan")
            continue
        m = AT.billed_minutes(j, t)
        total += m
        rows.append({"name": j.get("name"), "attempt": j.get("run_attempt"), "minutes": m,
                     "status": j.get("status"), "conclusion": j.get("conclusion")})
    return total, rows, problems


def ledger(runs: list[dict], self_run_id: int | None) -> dict:
    """The readiness ledger over ``runs`` (each with its "jobs", every attempt), the caller's own run left out."""
    rows, problems, total = [], [], 0
    for r in sorted(runs, key=lambda r: (r.get("created_at") or "", r.get("id") or 0)):
        if r.get("id") == self_run_id:
            continue
        m, jobs, p = run_minutes(r, r.get("jobs") or [])
        total += m
        problems += p
        rows.append({"id": r.get("id"), "workflow": (r.get("path") or "").removeprefix(".github/workflows/"),
                     "title": r.get("display_title"), "created_at": r.get("created_at"), "status": r.get("status"),
                     "conclusion": r.get("conclusion"), "run_attempt": r.get("run_attempt"), "minutes": m,
                     "jobs": jobs})
    return {"minutes": total, "runs": rows, "problems": problems}


# -- the decision ------------------------------------------------------------------------------------------

def first_record(records: list[dict], month: str, slug: str) -> tuple[dict | None, list[str]]:
    """A_m's record: the gate record of the month's first admitted readiness run (``records``: the admitted
    gate records of this month, oldest first). It must be that run's own, for this month, with A_m the remaining
    minutes of its valid Owner evidence and R_m = max(500, ceil(0.20 x A_m))."""
    if not records:
        return None, []
    rec = records[0]
    ev = (rec.get("billing") or {}).get("owner_evidence")
    res = rec.get("reserve") or {}
    a_m = res.get("a_m")
    bad = evidence_problems(ev, slug=slug, run_id=rec.get("run_id"), main_sha=rec.get("sha"), test=rec.get("test"),
                            month=month)
    if rec.get("schema") != GATE_SCHEMA or rec.get("decision") != DG.DISPATCH or rec.get("month") != month \
            or not isinstance(a_m, int) or isinstance(a_m, bool) or a_m < 0 or res.get("r_m") != DG.reserve(a_m) \
            or bad or ev[OP.MINUTES_INPUT] != a_m or res.get("first_run_id") != rec.get("run_id"):
        return None, [f"FAIL_CLOSED: the month's first admitted readiness run {rec.get('run_id')} has no valid A_m "
                      f"record (A_m {a_m}, R_m {res.get('r_m')}{'; ' + '; '.join(bad)[:300] if bad else ''})"]
    return rec, []


def baseline(records: list[dict], now: datetime) -> dict | None:
    """RT-8's first billing reading: the month's earliest admitted gate record at least STORAGE_INTERVAL_HOURS
    old."""
    for rec in records:
        at = _ts(rec.get("checked_utc"))
        if at is not None and (now - at).total_seconds() >= PL.STORAGE_INTERVAL_HOURS * 3600:
            return rec
    return None


def _verdict(rec: dict) -> dict:
    reasons = rec["reasons"] = list(dict.fromkeys(rec["reasons"]))
    if not reasons:
        rec["decision"] = DG.DISPATCH
    elif all(r.startswith("RESERVE") for r in reasons):
        rec["decision"] = DG.PARK
    else:
        rec["decision"] = DG.NO_DISPATCH
    return rec


def decide(f: dict) -> dict:
    """The gate's decision over the facts ``collect`` read (or a fixture of them). Pure: no I/O."""
    test, slug, now = f["test"], f["slug"], f["now"]
    month = now.strftime("%Y-%m")
    run = f.get("run") if isinstance(f.get("run"), dict) else {}
    env = f.get("env") or {}
    planned = PL.planned_max(test)
    rec: dict = {"schema": GATE_SCHEMA, "program": RL.SN.PROGRAM_ID, "test": test, "repository": slug,
                 "workflow": PL.workflow_of(test),
                 "run_id": run.get("id"), "run_attempt": run.get("run_attempt"), "sha": run.get("head_sha"),
                 "main_sha": f.get("main_sha"), "checked_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "month": month,
                 "reasons": list(f.get("errors") or [])}
    reasons = rec["reasons"]
    # provenance and attempt
    if not f.get("main_sha") or run.get("head_sha") != f.get("main_sha"):
        reasons.append(f"PROVENANCE: run {run.get('id')} is at {str(run.get('head_sha'))[:12]}, main is at "
                       f"{str(f.get('main_sha'))[:12]}; every readiness run is at main's current commit")
    if env.get("GITHUB_SHA") != run.get("head_sha") or str(env.get("GITHUB_RUN_ID")) != str(run.get("id")):
        reasons.append("PROVENANCE: the job's checkout or run id is not the run's")
    if run.get("run_attempt") != 1 or str(env.get("GITHUB_RUN_ATTEMPT")) != "1":
        reasons.append(f"RE_RUN: this is attempt {env.get('GITHUB_RUN_ATTEMPT')} ({run.get('run_attempt')}) of "
                       "its run; a readiness run is dispatched anew by the Owner, never re-run")
    # Owner billing evidence
    usage = f.get("usage") or {"verified": False, "class": "NOT_READ"}
    owner = presented_evidence(run, f.get("event"), slug=slug, test=test, month=month, usage=usage)
    reasons += owner["problems"]
    bill = OP.billing_state(usage, owner)
    rec["billing"] = {k: bill.get(k) for k in ("readable", "remaining_included_minutes", "budget_usd_zero",
                                                "usage_evidence", "owner_evidence", "owner_evidence_problems")}
    if bill.get("readable") is not True:
        reasons.append(f"FAIL_CLOSED: the billing state is not readable ({str(bill.get('reason'))[:300]})")
    # the Owner's reading is of now: given at dispatch, read within FRESH_MINUTES, nothing billed since
    attested = _ts(run.get("created_at"))
    age = (now - attested).total_seconds() / 60 if attested else None
    if age is None or not 0 <= age <= OP.FRESH_MINUTES:
        reasons.append(f"STALE_EVIDENCE: the Owner's billing reading is {None if age is None else round(age)} "
                       f"minute(s) old at the gate (at most {OP.FRESH_MINUTES}); dispatch again when no run is "
                       "queued")
    ended = sorted(r["id"] for r in f.get("runs") or [] if r.get("id") != run.get("id") and attested
                   and (_ts(r.get("updated_at") or r.get("created_at")) or attested) > attested)
    if ended:
        reasons.append(f"STALE_EVIDENCE: readiness run(s) {ended} billed after the Owner's reading")
    # serial
    busy = sorted(r["id"] for r in f.get("runs") or [] if r.get("id") != run.get("id")
                  and r.get("status") in DG.ACTIVE) + sorted(f.get("auth2_active") or [])
    if busy:
        reasons.append(f"SERIAL: readiness or AUTH-2 run(s) {busy} still active")
    # ledger and cap
    led = ledger(f.get("runs") or [], run.get("id"))
    reasons += [f"FAIL_CLOSED: {p}" for p in led["problems"]]
    total = led["minutes"] + planned + PL.NEXT_GATE_RESERVE
    rec["ledger"] = {**led, "cap": PL.READINESS_CAP, "planned_max": planned,
                     "next_gate_reserve": PL.NEXT_GATE_RESERVE, "total_if_admitted": total}
    shrunk = [r.get("run_id") for r in (f.get("records") if isinstance(f.get("records"), list) else [])
              if not isinstance((r.get("ledger") or {}).get("minutes"), int)
              or led["minutes"] < r["ledger"]["minutes"] + 1]
    if shrunk:
        reasons.append(f"FAIL_CLOSED: the ledger ({led['minutes']}) is below what admitted run(s) {shrunk} counted "
                       "before them plus their own gate; a readiness run is missing from the history")
    if total > PL.READINESS_CAP:
        reasons.append(f"CAP: readiness ledger {led['minutes']} + {test}'s planned maximum {planned} + "
                       f"{PL.NEXT_GATE_RESERVE} for one more gate run = {total} > {PL.READINESS_CAP}; stop and "
                       "return to the Owner")
    # the monthly reserve
    records = f.get("records")
    first, problems = (None, [f"FAIL_CLOSED: earlier gate records unreadable ({records})"]) \
        if isinstance(records, str) else first_record(records or [], month, slug)
    reasons += problems
    remaining = bill.get("remaining_included_minutes") if bill.get("readable") else None
    if first is not None:
        a_m, first_id = first["reserve"]["a_m"], first["run_id"]
    else:
        a_m, first_id = (remaining, run.get("id")) if not problems else (None, None)
    r_m = DG.reserve(a_m) if isinstance(a_m, int) else None
    rec["reserve"] = {"a_m": a_m, "r_m": r_m, "first_run_id": first_id, "remaining": remaining,
                      "planned_max": planned}
    if isinstance(remaining, int) and isinstance(r_m, int) and remaining - planned < r_m:
        reasons.append(f"RESERVE: remaining {remaining} - {test}'s planned maximum {planned} < R_m {r_m}; PARK "
                       "until next month")
    # the test's own preconditions
    rels = f.get("releases")
    if isinstance(rels, str):
        reasons.append(f"FAIL_CLOSED: the snapshot releases are unreadable ({rels[:200]})")
        rels = None
    commit = run.get("head_sha")
    # this readiness execution's snapshot: the releases bound to the run's own commit, never another commit's
    snap = RL.at_commit(rels or [], commit) if RL.is_commit(commit) else []
    rec["release"] = None
    if rels is not None and test == "RT-1" and len(snap) > 1:
        reasons.append(f"SNAPSHOT_AMBIGUOUS: the readiness commit has {len(snap)} published snapshot releases "
                       f"{sorted(str(r.get('tag_name')) for r in snap)}; it may have one")
    if rels is not None and test in PL.NEEDS_SNAPSHOT:
        problems = [] if len(snap) == 1 else [f"{len(snap)} published snapshot releases for the readiness commit "
                                              f"{str(commit)[:12]}; exactly one is required"]
        if len(snap) == 1:
            problems += RL.release_problems(snap[0], commit=commit)
            if (snap[0].get("author") or {}).get("login") != RL.BOT:
                problems.append(f"the release's author is {(snap[0].get('author') or {}).get('login')!r}, not "
                                f"{RL.BOT}")
            tagged = (f.get("tag_commits") or {}).get(snap[0].get("tag_name"))
            if tagged != commit:
                problems.append(f"the tag {snap[0].get('tag_name')} points at {str(tagged)[:12]}, not the readiness "
                                f"commit {str(commit)[:12]}")
        if problems:
            reasons.append(f"SNAPSHOT: {test} reads the readiness commit's snapshot: {'; '.join(problems)[:400]}")
        else:
            rec["release"] = {**RL.summary(snap[0]), "tag_commit": commit}
    if test == "RT-8":
        base = baseline(records if isinstance(records, list) else [], now)
        rec["rt8_baseline_run_id"] = base.get("run_id") if base else None
        if base is None:
            reasons.append(f"RT8_BASELINE: RT-8 compares two billing readings of this month at least "
                           f"{PL.STORAGE_INTERVAL_HOURS} hours apart, and no admitted readiness run of {month} "
                           "is that old")
    return _verdict(rec)


# -- collection (read-only; the workflow token, and the billing token for the usage report only) ----------

def _paged(gh, path: str, key: str | None) -> list:
    out, page = [], 1
    while True:
        status, body = gh.api("GET", f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        if status != 200:
            raise RuntimeError(f"GET {path.split('?')[0]} failed (HTTP {status}): {str(body)[:200]}")
        batch = body.get(key) if key and isinstance(body, dict) else body
        if not isinstance(batch, list):
            raise RuntimeError(f"GET {path.split('?')[0]}: no {key or 'list'} in the response")
        out += batch
        if len(batch) < 100:
            return out
        page += 1


def workflow_runs(gh, workflow: str) -> list[dict]:
    return _paged(gh, f"/repos/{gh.slug}/actions/workflows/{workflow}/runs", "workflow_runs")


def readiness_runs(gh, with_jobs: bool = True) -> list[dict]:
    """Every run of both readiness workflows, each with every job of every attempt (filter=all)."""
    runs = []
    for wf in PL.WORKFLOWS:
        try:
            got = workflow_runs(gh, wf)
        except RuntimeError as exc:
            if "HTTP 404" in str(exc):
                continue  # the workflow file does not exist (yet): no runs
            raise
        for r in got:
            if with_jobs:
                r["jobs"] = _paged(gh, f"/repos/{gh.slug}/actions/runs/{r['id']}/jobs?filter=all", "jobs")
            runs.append(r)
    return runs


def gate_records(gh, run_id: int) -> list[dict]:
    """The gate record(s) a readiness run uploaded (its GATE_ARTIFACT artifact)."""
    out = []
    for a in _paged(gh, f"/repos/{gh.slug}/actions/runs/{run_id}/artifacts", "artifacts"):
        if a.get("name") != GATE_ARTIFACT:
            continue
        if a.get("expired"):
            raise RuntimeError(f"run {run_id}'s gate record has expired")
        status, data = gh.api_bytes(f"/repos/{gh.slug}/actions/artifacts/{a['id']}/zip")
        if status != 200:
            raise RuntimeError(f"run {run_id}'s gate record cannot be downloaded (HTTP {status})")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            out += [json.loads(z.read(n)) for n in z.namelist() if n.endswith("gate.json")]
    return out


def owner_dispatched(run: dict, slug: str) -> str | None:
    """The test of a readiness run the Owner dispatched on main of ``slug``, as the Actions API reports it (never
    as an artifact says), or None."""
    test = next((t for t in PL.RUN_TESTS if run.get("display_title") == PL.TITLE.format(test=t)), None)
    owner = (OP.OWNER_LOGIN, OP.OWNER_ID)
    if test is None or OP.check_provenance(run, PL.workflow_of(test), run.get("head_sha") or "",
                                           PL.TITLE.format(test=test)) \
            or OP.who(run.get("actor")) != owner or OP.who(run.get("triggering_actor")) != owner \
            or (run.get("repository") or {}).get("full_name") != slug:
        return None
    return test


def admitted_records(gh, runs: list[dict], month: str, self_run_id: int | None) -> list[dict]:
    """The gate records of this month's admitted readiness runs, oldest first: runs the Owner dispatched on main
    (by the API's account of the run) whose first-attempt gate job succeeded. A run of a branch, of another
    account or under another title is not admitted, whatever its artifact says; its minutes still count in the
    ledger."""
    out = []
    for r in sorted(runs, key=lambda r: (r.get("created_at") or "", r["id"])):
        if r["id"] == self_run_id or (r.get("created_at") or "")[:7] != month:
            continue
        test = owner_dispatched(r, gh.slug)
        if test is None:
            continue
        gates = [j for j in r.get("jobs") or [] if j.get("name") == PL.GATE_JOB and j.get("run_attempt") in (1, None)]
        if not any(j.get("conclusion") == "success" for j in gates):
            continue
        recs = [x for x in gate_records(gh, r["id"]) if x.get("run_id") == r["id"]]
        if len(recs) != 1:
            raise RuntimeError(f"admitted run {r['id']} holds {len(recs)} gate record(s), not one")
        if (recs[0].get("sha"), recs[0].get("test"), recs[0].get("run_attempt")) != (r.get("head_sha"), test, 1):
            raise RuntimeError(f"admitted run {r['id']}'s gate record is not that run's (sha, test or attempt)")
        out.append(recs[0])
    return out


def collect(gh, test: str, now: datetime, usage_reader=None) -> dict:
    f: dict = {"test": test, "slug": gh.slug, "now": now, "errors": [],
               "env": {k: os.environ.get(k) for k in ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")}}
    run_id = os.environ.get("GITHUB_RUN_ID")
    try:
        status, f["run"] = gh.api("GET", f"/repos/{gh.slug}/actions/runs/{int(run_id)}")
        if status != 200:
            raise RuntimeError(f"HTTP {status}")
        f["event"] = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
        f["errors"].append(f"FAIL_CLOSED: this run is unreadable ({str(exc)[:200]})")
        f["run"], f["event"] = {}, {}
    owner = gh.slug.split("/")[0]
    f["usage"] = (usage_reader or OP.read_usage)(owner, "AUTH2_BILLING_TOKEN", now)
    try:
        status, ref = gh.api("GET", f"/repos/{gh.slug}/git/ref/heads/main")
        f["main_sha"] = (ref.get("object") or {}).get("sha") if status == 200 and isinstance(ref, dict) else None
    except RuntimeError:
        f["main_sha"] = None
    try:
        f["runs"] = readiness_runs(gh)
        f["auth2_active"] = [r["id"] for wf in AUTH2_WORKFLOWS for r in workflow_runs(gh, wf)
                             if r.get("status") in DG.ACTIVE]
    except RuntimeError as exc:
        f["errors"].append(f"FAIL_CLOSED: the run history is unreadable ({str(exc)[:200]})")
        f["runs"] = []
    try:
        f["records"] = admitted_records(gh, f["runs"], now.strftime("%Y-%m"), (f.get("run") or {}).get("id"))
    except (RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        f["records"] = str(exc)[:200]
    try:
        f["releases"] = RL.snapshot_releases(gh)
        commit = (f.get("run") or {}).get("head_sha")
        f["tag_commits"] = {r["tag_name"]: RL.tag_commit(gh, r["tag_name"])
                            for r in (RL.at_commit(f["releases"], commit) if RL.is_commit(commit) else [])}
    except RL.ReleaseError as exc:
        f["releases"] = str(exc)[:200]
    return f


def gate(a) -> int:
    gh = RL.GH(a.repo_slug)
    now = datetime.now(timezone.utc)
    rec = decide(collect(gh, a.test, now))
    body = json.dumps(rec, indent=1, sort_keys=True) + "\n"
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(body)
    print(body, end="")
    if a.annotate:
        print(OP.annotation_lines(GATE_TITLE, body.encode()))
    print(f"AUTH2Q2_READINESS_GATE = {rec['decision']}")
    return 0 if rec["decision"] == DG.DISPATCH else 3


def outputs(rec: dict) -> str:
    """The gate job's outputs for the test's jobs: the address, tag and hex of the snapshot the gate admitted the
    run to read, all empty unless the decision is DISPATCH with a release bound to the run's own commit."""
    release = rec.get("release") if isinstance(rec, dict) and rec.get("decision") == DG.DISPATCH else None
    m = RL.DIGEST.fullmatch(str((release or {}).get("address") or ""))
    commit = rec.get("sha") if isinstance(rec, dict) else None
    try:
        tag = RL.tag_for(m[0], commit) if m else ""
    except RL.ReleaseError:
        tag = ""
    if not tag or (release or {}).get("tag") != tag or (release or {}).get("commit") != commit:
        return "address=\ntag=\nhex=\n"
    return f"address={m[0]}\ntag={tag}\nhex={m[1]}\n"


# -- RT-8: storage, retention and billing ------------------------------------------------------------

def _storage(usage: dict) -> float:
    return float(((usage.get("actions") or {}).get(STORAGE_SKU) or {}).get("quantity") or 0.0)


def _linux(u: dict) -> float | None:
    """This month's Linux minutes in a usage report: the second RT-8 reading must have moved past the first, or
    the report had not caught up and its storage figure proves nothing."""
    q = ((u.get("actions") or {}).get(LINUX_SKU) or {}).get("quantity")
    return float(q) if isinstance(q, (int, float)) and not isinstance(q, bool) else None


def rt8(own: dict, base: dict, rel: dict | None, artifacts: list[dict], cache_usage: dict) -> dict:
    """The two billing readings (RT-8's baseline and this run's own gate), the release and the run artifacts."""
    u0 = ((base or {}).get("billing") or {}).get("usage_evidence") or {}
    u1 = ((own or {}).get("billing") or {}).get("usage_evidence") or {}
    t0, t1 = _ts((base or {}).get("checked_utc")), _ts((own or {}).get("checked_utc"))
    hours = (t1 - t0).total_seconds() / 3600 if t0 and t1 else None
    rate = (_storage(u1) - _storage(u0)) / hours if hours else None
    net = {f"{when}:{sku}": v.get("netAmount") for when, u in (("before", u0), ("after", u1))
           for sku, v in (u.get("actions") or {}).items()}
    live = [x for x in artifacts if not x.get("expired")]
    live_bytes = sum(int(x.get("size_in_bytes") or 0) for x in live)
    mine = [x for x in live if str(x.get("name", "")).startswith("auth2q2-")]
    checks = {"both_readings_verified": u0.get("verified") is True and u1.get("verified") is True,
              "same_billing_month": u0.get("period") == u1.get("period") is not None,
              "readings_far_enough_apart": hours is not None and hours >= PL.STORAGE_INTERVAL_HOURS,
              "second_reading_moved": _linux(u1) is not None and _linux(u0) is not None and _linux(u1) > _linux(u0),
              "no_actions_charge": bool(net) and all(v == 0 for v in net.values()),
              "no_storage_charge_from_the_release": rate is not None and rate < STORAGE_RATE_GB,
              "release_immutable": bool(rel) and rel.get("immutable") is True,
              "release_bound_to_this_commit": bool(rel) and _bound(rel, (own or {}).get("sha")),
              "release_has_no_expiry": bool(rel) and not any(k in rel for k in ("expires_at", "expired")),
              "artifact_storage_far_below_500_mb": live_bytes < ARTIFACT_LIMIT_BYTES,
              "every_readiness_artifact_expires": all(x.get("expires_at") for x in mine),
              "cache_within_10_gb": isinstance(cache_usage.get("active_caches_size_in_bytes"), int)
              and cache_usage["active_caches_size_in_bytes"] < CACHE_LIMIT_BYTES}
    meas = {"baseline_run_id": (base or {}).get("run_id"), "hours_between_readings": round(hours, 2) if hours else None,
            "snapshot_release": _binding(rel),
            "actions_storage_gb_hours": {"before": _storage(u0), "after": _storage(u1)},
            "actions_linux_minutes": {"before": _linux(u0), "after": _linux(u1)},
            "storage_rate_gb": round(rate, 4) if rate is not None else None, "net_amounts": net,
            "release": {n: {"size": a.get("size"), "digest": a.get("digest")} for n, a in RL.asset_map(rel or {}).items()},
            "artifacts_live_bytes": live_bytes, "artifacts_live": len(live),
            "readiness_artifacts": sorted((x.get("name"), x.get("size_in_bytes"), x.get("expires_at")) for x in mine),
            "cache_usage": cache_usage}
    return _result("RT-8", "RT-8 storage, retention and billing", checks, meas)


# -- RT-9: the billing guard, against the API and against fixtures ------------------------------------

def recompute(gh, own: dict) -> tuple[dict, list[str]]:
    """Each run's billed minutes from the per-attempt jobs endpoint, a different read from the gate's."""
    out, problems = {}, []
    stamp = own.get("checked_utc") or ""
    for wf in PL.WORKFLOWS:
        try:
            runs = workflow_runs(gh, wf)
        except RuntimeError as exc:
            if "HTTP 404" in str(exc):
                continue
            raise
        for r in runs:
            if r["id"] == own.get("run_id") or (r.get("created_at") or "") > stamp:
                continue
            jobs = []
            for n in range(1, int(r.get("run_attempt") or 1) + 1):
                jobs += _paged(gh, f"/repos/{gh.slug}/actions/runs/{r['id']}/attempts/{n}/jobs", "jobs")
            m, _rows, p = run_minutes(r, jobs)
            out[r["id"]] = m
            problems += p
    return out, problems


def _fixture(own: dict, **change) -> dict:
    """A gate fact set that admits RT-9 (a clean control), with ``change`` applied."""
    now = _ts(own["checked_utc"]) or datetime.now(timezone.utc)
    sha = "f" * 40
    run = {"id": 1, "run_attempt": 1, "head_sha": sha, "path": f".github/workflows/{PL.READINESS_WORKFLOW}",
           "event": "workflow_dispatch", "head_branch": "main", "display_title": PL.TITLE.format(test="RT-9"),
           "repository": {"full_name": own.get("repository") or "o/r"}, "created_at": own["checked_utc"],
           "actor": {"login": OP.OWNER_LOGIN, "id": OP.OWNER_ID},
           "triggering_actor": {"login": OP.OWNER_LOGIN, "id": OP.OWNER_ID}}
    usage = {"verified": True, "class": "USAGE_VERIFIED", "period": now.strftime("%Y-%m"),
             "endpoint": OP.USAGE_ENDPOINT.format(owner=OP.OWNER_LOGIN), "actions": {}}
    event = {"inputs": {"test": "RT-9", OP.MINUTES_INPUT: "1000", "actions_budget_usd_zero": OP.CONFIRMED,
                        "stop_usage_enabled": OP.CONFIRMED}, "sender": run["actor"]}
    f = {"test": "RT-9", "slug": run["repository"]["full_name"], "now": now, "errors": [],
         "env": {"GITHUB_SHA": sha, "GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "1"}, "run": run, "event": event,
         "usage": usage, "main_sha": sha, "runs": [], "auth2_active": [], "records": [], "releases": []}
    for k, v in change.items():
        if callable(v):
            v(f)
        else:
            f[k] = v
    return f


def _past_runs(minutes: int) -> list[dict]:
    """Finished readiness runs billing ``minutes`` in all (one gate job each, at most 10 per job)."""
    out, left, i = [], minutes, 0
    while left > 0:
        m = min(left, PL.GATE_TIMEOUT)
        i += 1
        out.append({"id": 100 + i, "path": f".github/workflows/{PL.READINESS_WORKFLOW}", "status": "completed",
                    "conclusion": "failure", "created_at": "2000-01-01T00:00:00Z", "run_attempt": 1,
                    "jobs": [{"name": PL.GATE_JOB, "status": "completed", "conclusion": "failure", "run_attempt": 1,
                              "started_at": "2000-01-01T00:00:00Z",
                              "completed_at": f"2000-01-01T00:{m - 1:02d}:30Z", "steps": [{"name": "x"}]}]})
        left -= m
    return out


def breach_fixtures(own: dict) -> dict[str, tuple[dict, str]]:
    """name -> (fact set, the decision the gate must reach). One clean control, then one breach each."""
    planned = PL.planned_max("RT-9")
    r_m = DG.reserve(1000)

    def remaining(n: int):
        return lambda f: f["event"]["inputs"].__setitem__(OP.MINUTES_INPUT, str(n))

    def other_actor(f):
        f["run"]["triggering_actor"] = {"login": "someone-else", "id": 1}
        f["event"]["sender"] = f["run"]["triggering_actor"]

    over = PL.READINESS_CAP - planned - PL.NEXT_GATE_RESERVE + 1
    return {
        "control_admitted": (_fixture(own), DG.DISPATCH),
        "reserve_breach_parks": (_fixture(own, x=remaining(planned + r_m - 1)), DG.PARK),
        "reserve_edge_admitted": (_fixture(own, x=remaining(planned + r_m)), DG.DISPATCH),
        "cap_breach_refused": (_fixture(own, runs=_past_runs(over)), DG.NO_DISPATCH),
        "cap_edge_admitted": (_fixture(own, runs=_past_runs(over - 1)), DG.DISPATCH),
        "budget_not_confirmed_refused": (_fixture(
            own, x=lambda f: f["event"]["inputs"].__setitem__("actions_budget_usd_zero", OP.NOT_CONFIRMED)),
            DG.NO_DISPATCH),
        "usage_not_verified_refused": (_fixture(own, x=lambda f: f["usage"].update(verified=False,
                                                                                    **{"class": "TOKEN_MISSING"})),
                                       DG.NO_DISPATCH),
        "not_the_owner_refused": (_fixture(own, x=other_actor), DG.NO_DISPATCH),
        "re_run_refused": (_fixture(own, x=lambda f: (f["run"].update(run_attempt=2),
                                                       f["env"].update(GITHUB_RUN_ATTEMPT="2"))), DG.NO_DISPATCH),
        "unknown_job_refused": (_fixture(own, runs=[{**_past_runs(1)[0], "jobs": [
            {**_past_runs(1)[0]["jobs"][0], "name": "not in the plan"}]}]), DG.NO_DISPATCH),
        "concurrent_run_refused": (_fixture(own, auth2_active=[7]), DG.NO_DISPATCH),
    }


def program_fixtures() -> dict[str, bool]:
    """The successor's guarded compute proof (compute.py) at the 4,000 cap: a dispatch that could pass it closes
    the program CAP_REACHED instead, and whatever was admitted still leaves the closure and its guard their
    reserve. The node timeout is a fixture (AUTH-2's D0, 150): the successor's are set from the readiness
    measurements (OD-S8)."""
    g = C.GUARD_TIMEOUT
    part = {"node": "D0", "part": 1, "timeout": 150, "first_science_attempt": True}
    n = C.need(part["timeout"], True, g)
    at_cap = C.decide(C.CAP - n["total"] + 1, part)
    edge = C.decide(C.CAP - n["total"], part)
    refused = C.decide(0, part, refusals=["SERIAL: a fixture refusal"])
    done = C.decide(C.CAP - C.RESERVE, None)
    worst_after_edge = (C.CAP - n["total"]) + n["this_guard"] + n["node"] + n["retry"]
    return {"reserve_is_closure_and_its_guard": C.RESERVE == (C.CLOSURE_TIMEOUT + 1) + (g + 1),
            "first_attempt_reserves_its_retry": n["retry"] == (g + 1) + (part["timeout"] + 1),
            "cap_breach_closes_cap_reached": at_cap["decision"] == C.CLOSE and at_cap["reason"] == AT.CAP_REACHED,
            "cap_edge_dispatches": edge["decision"] == C.DISPATCH,
            "other_refusals_never_dispatch": refused["decision"] == C.NO_DISPATCH,
            "nothing_left_closes": done["decision"] == C.CLOSE and done["reason"] is None,
            "closure_reserve_survives_the_worst_case": worst_after_edge + C.RESERVE <= C.CAP}


def rt9(gh, own: dict) -> dict:
    checks: dict[str, bool] = {}
    meas: dict = {}
    led = own.get("ledger") or {}
    gate_runs = {r["id"]: r["minutes"] for r in led.get("runs") or []}
    try:
        api, problems = recompute(gh, own)
    except RuntimeError as exc:
        api, problems = {}, [str(exc)[:300]]
    checks["gate_admitted_this_run"] = own.get("decision") == DG.DISPATCH and own.get("test") == "RT-9"
    checks["ledger_reconciles"] = not problems and not led.get("problems")
    checks["same_runs_as_the_api"] = set(api) == set(gate_runs)
    checks["each_run_matches_to_the_minute"] = all(api.get(i) == m for i, m in gate_runs.items())
    checks["ledger_total_matches"] = sum(api.values()) == led.get("minutes")
    res = own.get("reserve") or {}
    checks["r_m_is_max_500_or_20_percent_of_a_m"] = isinstance(res.get("a_m"), int) and \
        res.get("r_m") == max(DG.RESERVE_FLOOR, math.ceil(DG.RESERVE_SHARE * res["a_m"]))
    checks["cap_check_counted_this_run_and_one_more_gate"] = led.get("total_if_admitted") == \
        led.get("minutes", -1) + PL.planned_max("RT-9") + PL.NEXT_GATE_RESERVE <= PL.READINESS_CAP
    outcomes = {}
    for name, (facts, want) in breach_fixtures(own).items():
        got = decide(facts)
        outcomes[name] = {"want": want, "got": got["decision"], "reasons": got["reasons"][:3]}
        checks[f"fixture_{name}"] = got["decision"] == want
    for name, ok in program_fixtures().items():
        checks[f"program_{name}"] = ok
    meas.update({"gate_ledger": gate_runs, "api_ledger": api, "problems": problems, "fixtures": outcomes,
                 "a_m": res.get("a_m"), "r_m": res.get("r_m"), "remaining": res.get("remaining"),
                 "ledger_minutes": led.get("minutes"), "cap": PL.READINESS_CAP})
    return _result("RT-9", "RT-9 billing guard", checks, meas)


def _result(test: str, job: str, checks: dict, meas: dict) -> dict:
    from auth2q2 import harness as H

    return H.result(test, job, checks, meas)


def _binding(rel) -> dict | None:
    from auth2q2 import harness as H

    return H.snapshot_binding(RL.summary(rel)) if isinstance(rel, dict) and rel else None


def _bound(rel: dict, commit) -> bool:
    from auth2q2 import harness as H

    return H.bound_to(RL.summary(rel), commit)


# -- CLI ---------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gate")
    g.add_argument("--test", required=True, choices=PL.RUN_TESTS)
    g.add_argument("--repo-slug", required=True)
    g.add_argument("--out", required=True)
    g.add_argument("--annotate", action="store_true")
    led = sub.add_parser("ledger")
    led.add_argument("--repo-slug", required=True)
    for name in ("rt8", "rt9"):
        p = sub.add_parser(name)
        p.add_argument("--repo-slug", required=True)
        p.add_argument("--gate", required=True, help="this run's gate record")
        p.add_argument("--out", required=True)
    n = sub.add_parser("annotate")
    n.add_argument("--title", required=True, choices=(GATE_TITLE, RT_TITLE))
    n.add_argument("--file", required=True)
    o = sub.add_parser("outputs")
    o.add_argument("--gate", required=True, help="this run's gate record")
    a = ap.parse_args(argv)
    if a.cmd == "outputs":
        print(outputs(json.loads(Path(a.gate).read_text())), end="")
        return 0
    if a.cmd == "gate":
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", a.repo_slug):
            raise SystemExit(f"{a.repo_slug!r} is not owner/name")
        return gate(a)
    if a.cmd == "annotate":
        print(OP.annotation_lines(a.title, Path(a.file).read_bytes()))
        return 0
    gh = RL.GH(a.repo_slug)
    if a.cmd == "ledger":
        rec = ledger(readiness_runs(gh), None)
        print(json.dumps({**rec, "cap": PL.READINESS_CAP, "plan": PL.table(), "totals": PL.totals()}, indent=1,
                         sort_keys=True))
        return 0 if not rec["problems"] else 3
    own = json.loads(Path(a.gate).read_text())
    if a.cmd == "rt8":
        try:
            base_id = own.get("rt8_baseline_run_id")
            base = [r for r in gate_records(gh, int(base_id)) if r.get("run_id") == base_id] if base_id else []
            rel = RL.the_snapshot(gh, own.get("sha"), (own.get("release") or {}).get("address"))
            arts = _paged(gh, f"/repos/{gh.slug}/actions/artifacts", "artifacts")
            status, usage = gh.api("GET", f"/repos/{gh.slug}/actions/cache/usage")
            rec = rt8(own, base[0] if len(base) == 1 else {}, rel, arts, usage if status == 200 else {})
        except (RuntimeError, RL.ReleaseError, ValueError, zipfile.BadZipFile) as exc:
            rec = _result("RT-8", "RT-8 storage, retention and billing", {}, {"error": str(exc)[:400]})
    else:
        rec = rt9(gh, own)
    body = json.dumps(rec, indent=1, sort_keys=True) + "\n"
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(body)
    print(body, end="")
    print(f"{rec['test']} = {rec['result']}")
    return 0 if rec["result"] == "PASS" else 3


if __name__ == "__main__":
    sys.exit(main())
