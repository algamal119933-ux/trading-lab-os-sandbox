#!/usr/bin/env python3
"""The readiness record: INFRA_READINESS for RT-0 to RT-11 at one named commit (Owner decision OD-S8; review
section 4, "INFRA_READINESS = PASS → readiness record").

    python -m auth2q2.record collect    --repo-slug O/R --commit SHA --run RT-0=ID ... --run RT-11=ID --out E
    python -m auth2q2.record build      --evidence E --out-dir DIR
    python -m auth2q2.record verify     --dir DIR
    python -m auth2q2.record check-live --repo-slug O/R --dir DIR

``collect`` reads the Actions API, read-only: every run of both readiness workflows with every job of every
attempt (the readiness ledger), the annotations each named run's jobs published (the gate's AUTH2Q2_GATE record
and the verdicts' AUTH2Q2_RT records), and the CI run named as RT-0. It writes that, and only that, as the
evidence. ``build`` is pure: from the evidence bytes alone it decides INFRA_READINESS and writes the evidence,
the record and SHA256SUMS. ``verify`` rebuilds a bundle from its own evidence and compares it byte for byte;
``check-live`` reads the API again and compares it with the evidence, so the evidence is the API's.

INFRA_READINESS = PASS only if every one of these holds, and the record says which did not:

  NAMES      RT-0 to RT-11 each name one run, every run a different one
  RT-0       a ci.yml push run on main at the named commit, completed success, its test job success
  PROVENANCE each RT-n run: its plan workflow, workflow_dispatch on main, titled for its test, attempt 1,
             completed, dispatched by the Owner, at the named commit
  JOBS       the run's gate and test jobs each ran once, at attempt 1, and ended as designed (the probes fail or
             run out of time on purpose); every other job of the workflow never ran
  GATE       the gate published one record: DISPATCH for this test, run and commit, the ledger within the cap
  VERDICT    every verdict job published one record for this test, job, run and commit, and every one of its
             checks holds (PASS is re-derived, not read)
  SNAPSHOT   every test that reads the snapshot read the one RT-1 published
  LEDGER     every job of every attempt of every readiness run, at the plan's timeouts, reconciles and is at
             most 300 minutes (OD-S4); the ledger is the gate's own function, so the numbers are the gate's

The record also lists each run's jobs with their durations and billed minutes, and the slowest measured run of
every job that works as a workload: OD-S8 sets the successor's final timeouts at no less than twice those. It
sets no timeout, writes no law and freezes nothing; the successor law comes later, by Owner merge.

PAPER / RESEARCH ONLY. Nothing here dispatches, re-runs or writes GitHub.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_GATES = _HERE.parents[1] / ".github" / "gates"
for _extra in (_HERE.parent, _GATES):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import auth2q2_readiness as RG  # noqa: E402  (the gate's ledger and records, so the record's numbers are its)
from auth2q2 import attempts as AT  # noqa: E402
from auth2q2 import harness as H  # noqa: E402
from auth2q2 import plan as PL  # noqa: E402
from auth2q2 import release as RL  # noqa: E402
from auth2q2 import snapshot as SN  # noqa: E402

OP, DG = RG.OP, RG.DG
EVIDENCE_SCHEMA = "AUTH2Q2_READINESS_EVIDENCE_1"
RECORD_SCHEMA = "AUTH2Q2_INFRA_READINESS_1"
EVIDENCE, RECORD, SUMS = "evidence.json", "INFRA_READINESS.json", "SHA256SUMS"
CI_WORKFLOW, CI_JOB = "ci.yml", "Static checks and tests"
PASS, FAIL = "PASS", "FAIL"
SHA = re.compile(r"[0-9a-f]{40}")
RUN_FIELDS = ("id", "name", "path", "event", "head_branch", "head_sha", "display_title", "run_attempt", "status",
              "conclusion", "created_at", "run_started_at")
JOB_FIELDS = ("id", "name", "run_attempt", "status", "conclusion", "started_at", "completed_at", "runner_id",
              "runner_name")
STEP_FIELDS = ("name", "number", "status", "conclusion", "started_at", "completed_at")
TITLES = (RG.GATE_TITLE, RG.RT_TITLE)


def dumps(obj) -> bytes:
    return (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _ts(raw) -> datetime | None:
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


# -- collect (the API, read-only) -----------------------------------------------------------------------

def _who(user) -> dict | None:
    return {"login": user.get("login"), "id": user.get("id")} if isinstance(user, dict) else None


def _run(r: dict) -> dict:
    out = {k: r.get(k) for k in RUN_FIELDS}
    out.update(actor=_who(r.get("actor")), triggering_actor=_who(r.get("triggering_actor")),
               repository={"full_name": (r.get("repository") or {}).get("full_name")})
    return out


def _job(j: dict) -> dict:
    out = {k: j.get(k) for k in JOB_FIELDS}
    steps = j.get("steps")
    out["steps"] = [{k: s.get(k) for k in STEP_FIELDS} for s in steps if isinstance(s, dict)] \
        if isinstance(steps, list) else steps
    return out


def _notes(gh, job_id: int) -> list[dict]:
    """The records a job published: its annotations titled AUTH2Q2_GATE or AUTH2Q2_RT."""
    return [{"title": a.get("title"), "message": a.get("message")}
            for a in RG._paged(gh, f"/repos/{gh.slug}/check-runs/{job_id}/annotations", None)
            if isinstance(a, dict) and a.get("title") in TITLES]


def collect(gh, commit: str, named: dict[str, int], now: datetime) -> dict:
    ids = set(named.values())
    runs = []
    for r in RG.readiness_runs(gh):
        row = _run(r)
        row["jobs"] = []
        for j in r.get("jobs") or []:
            jj = _job(j)
            if r["id"] in ids and not AT.never_ran(j):
                jj["annotations"] = _notes(gh, j["id"])
            row["jobs"].append(jj)
        runs.append(row)
    ci_id = named.get("RT-0")
    status, ci = gh.api("GET", f"/repos/{gh.slug}/actions/runs/{int(ci_id)}")
    if status != 200 or not isinstance(ci, dict):
        raise RuntimeError(f"the RT-0 CI run {ci_id} is unreadable (HTTP {status})")
    ci_row = _run(ci)
    ci_row["jobs"] = [_job(j) for j in RG._paged(gh, f"/repos/{gh.slug}/actions/runs/{int(ci_id)}/jobs?filter=all",
                                                 "jobs")]
    return {"schema": EVIDENCE_SCHEMA, "program": SN.PROGRAM_ID, "repository": gh.slug, "commit": commit,
            "named": dict(sorted(named.items())), "collected_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "runs": sorted(runs, key=lambda r: (r.get("created_at") or "", r.get("id") or 0)), "ci_run": ci_row}


# -- decide (pure) ---------------------------------------------------------------------------------------

def _single(jobs: list[dict], name: str) -> dict | None:
    mine = [j for j in jobs if isinstance(j, dict) and j.get("name") == name]
    return mine[0] if len(mine) == 1 else None


def _records(job: dict | None, title: str) -> tuple[list, str | None]:
    if job is None:
        return [], "no such job"
    try:
        return [json.loads(b) for b in OP.decode_annotations(job.get("annotations") or [], title)], None
    except ValueError as exc:
        return [], f"{type(exc).__name__}: {str(exc)[:200]}"


def _seconds(job: dict) -> float | None:
    a, b = _ts(job.get("started_at")), _ts(job.get("completed_at"))
    return (b - a).total_seconds() if a and b and b >= a and job.get("status") == "completed" else None


def _gate(test: str, run: dict, commit: str, slug: str) -> tuple[dict, list[str]]:
    recs, err = _records(_single(run.get("jobs") or [], PL.GATE_JOB), RG.GATE_TITLE)
    if len(recs) != 1:
        return {}, [f"GATE: {test} run {run.get('id')} published {len(recs)} gate record(s), not one"
                    f"{' (' + err + ')' if err else ''}"]
    g = recs[0] if isinstance(recs[0], dict) else {}
    want = {"schema": RG.GATE_SCHEMA, "program": SN.PROGRAM_ID, "decision": DG.DISPATCH, "test": test,
            "repository": slug, "workflow": PL.workflow_of(test), "run_id": run.get("id"), "run_attempt": 1,
            "sha": commit, "main_sha": commit, "reasons": []}
    p = [f"GATE: {test} run {run.get('id')}: gate record {k} is {str(g.get(k))[:120]}, not {str(v)[:60]}"
         for k, v in want.items() if g.get(k) != v]
    led = g.get("ledger") or {}
    total = led.get("total_if_admitted")
    if not isinstance(total, int) or isinstance(total, bool) or total > PL.READINESS_CAP:
        p.append(f"GATE: {test} run {run.get('id')} admitted a ledger total of {total}, not <= {PL.READINESS_CAP}")
    res = g.get("reserve") or {}
    return {"decision": g.get("decision"), "checked_utc": g.get("checked_utc"), "ledger_minutes": led.get("minutes"),
            "total_if_admitted": total, "remaining": res.get("remaining"), "a_m": res.get("a_m"),
            "r_m": res.get("r_m"), "release": (g.get("release") or {}).get("address")}, p


def _verdicts(test: str, run: dict, commit: str) -> tuple[dict, list[str]]:
    out, p = {}, []
    for name in PL.TESTS[test][2]:
        recs, err = _records(_single(run.get("jobs") or [], name), RG.RT_TITLE)
        if len(recs) != 1 or not isinstance(recs[0], dict):
            p.append(f"VERDICT: {test} job {name!r} published {len(recs)} verdict record(s), not one"
                     f"{' (' + err + ')' if err else ''}")
            out[name] = {"result": FAIL}
            continue
        r = recs[0]
        want = {"schema": H.RESULT_SCHEMA, "program": SN.PROGRAM_ID, "test": test, "job": name,
                "run_id": str(run.get("id")), "run_attempt": "1", "sha": commit}
        bad = [f"{k} is {str(r.get(k))[:80]}, not {v}" for k, v in want.items() if str(r.get(k)) != v]
        checks = r.get("checks")
        failed = sorted(k for k, v in checks.items() if v is not True) if isinstance(checks, dict) else ["<none>"]
        ok = not bad and isinstance(checks, dict) and bool(checks) and not failed and not r.get("problems") \
            and r.get("result") == PASS
        if not ok:
            p.append(f"VERDICT: {test} job {name!r}: {'; '.join(bad)[:300] or 'not PASS'}"
                     f"{'; failed checks ' + str(failed[:10]) if failed else ''}"
                     f"{'; problems ' + str(r.get('problems'))[:300] if r.get('problems') else ''}")
        out[name] = {"result": PASS if ok else FAIL, "checks": checks, "problems": r.get("problems"),
                     "measurements": r.get("measurements"), "created_utc": r.get("created_utc")}
    return out, p


def _jobs(test: str, run: dict) -> tuple[list[dict], list[str]]:
    wf, planned, _verdict = PL.TESTS[test]
    jobs = [j for j in run.get("jobs") or [] if isinstance(j, dict)]
    p, rows = [], []
    names = [j.get("name") for j in jobs]
    for name in sorted({n for n in names if names.count(n) > 1}, key=str):
        p.append(f"JOBS: {test} run {run.get('id')} lists job {str(name)[:80]!r} {names.count(name)} times")
    for name in (PL.GATE_JOB, *planned):
        j = _single(jobs, name)
        if j is None:
            p.append(f"JOBS: {test} run {run.get('id')} has no single job {name!r}")
            continue
        want = PL.designed_end(name)
        if j.get("status") != "completed" or j.get("conclusion") != want or j.get("run_attempt") != 1:
            p.append(f"JOBS: {test} job {name!r} ended {j.get('status')}/{j.get('conclusion')} at attempt "
                     f"{j.get('run_attempt')}, not completed/{want} at attempt 1 as designed")
    for j in jobs:
        name = j.get("name")
        t = PL.timeout_of(wf, name)
        if t is None:
            p.append(f"JOBS: {test} run {run.get('id')}: job {str(name)[:80]!r} is not in the plan")
            continue
        ran = not AT.never_ran(j)
        if ran and name not in (PL.GATE_JOB, *planned):
            p.append(f"JOBS: {test} run {run.get('id')}: job {name!r} ran, but {test} does not run it")
        if ran:
            s = _seconds(j)
            rows.append({"name": name, "attempt": j.get("run_attempt"), "conclusion": j.get("conclusion"),
                         "designed_end": PL.designed_end(name), "timeout_minutes": t,
                         "seconds": round(s, 1) if s is not None else None, "billed_minutes": AT.billed_minutes(j, t)})
    return sorted(rows, key=lambda r: (r["name"], r["attempt"] or 0)), p


def _provenance(test: str, run: dict, commit: str, slug: str) -> list[str]:
    wf = PL.workflow_of(test)
    p = [f"PROVENANCE: {test}: {x}" for x in OP.check_provenance(run, wf, commit or "", PL.TITLE.format(test=test))]
    if run.get("run_attempt") != 1:
        p.append(f"PROVENANCE: {test} run {run.get('id')} is at attempt {run.get('run_attempt')}; a readiness run "
                 "is never re-run")
    if run.get("status") != "completed":
        p.append(f"PROVENANCE: {test} run {run.get('id')} is {run.get('status')}, not completed")
    owner = {"login": OP.OWNER_LOGIN, "id": OP.OWNER_ID}
    if run.get("actor") != owner or run.get("triggering_actor") != owner:
        p.append(f"PROVENANCE: {test} run {run.get('id')} was dispatched by {run.get('triggering_actor')}, not the "
                 f"Owner {owner}")
    if (run.get("repository") or {}).get("full_name") != slug:
        p.append(f"PROVENANCE: {test} run {run.get('id')} is not a run of {slug}")
    return p


def _rt0(ci, ci_id, commit: str, slug: str) -> tuple[dict, list[str]]:
    if not isinstance(ci, dict) or ci_id is None or ci.get("id") != ci_id:
        return {"run_id": ci_id, "result": FAIL}, [f"RT-0: the CI run {ci_id} is not the evidence's CI run"]
    p = []
    if ci.get("path") != f".github/workflows/{CI_WORKFLOW}":
        p.append(f"RT-0: run {ci_id} is not a run of {CI_WORKFLOW} ({str(ci.get('path'))[:80]})")
    if ci.get("event") != "push" or ci.get("head_branch") != "main":
        p.append(f"RT-0: CI run {ci_id} is a {ci.get('event')} run on {ci.get('head_branch')}, not the push run on "
                 "main")
    if commit is None or ci.get("head_sha") != commit:
        p.append(f"RT-0: CI run {ci_id} ran at {str(ci.get('head_sha'))[:12]}, not the named commit "
                 f"{str(commit)[:12]}")
    if (ci.get("status"), ci.get("conclusion")) != ("completed", "success"):
        p.append(f"RT-0: CI run {ci_id} ended {ci.get('status')}/{ci.get('conclusion')}, not completed/success")
    if (ci.get("repository") or {}).get("full_name") != slug:
        p.append(f"RT-0: CI run {ci_id} is not a run of {slug}")
    static = [j for j in ci.get("jobs") or [] if isinstance(j, dict) and j.get("name") == CI_JOB
              and j.get("run_attempt") == ci.get("run_attempt")]
    if len(static) != 1 or static[0].get("conclusion") != "success":
        p.append(f"RT-0: CI run {ci_id} has no successful {CI_JOB!r} job at its attempt {ci.get('run_attempt')}")
    return {"run_id": ci_id, "workflow": CI_WORKFLOW, "event": ci.get("event"), "run_attempt": ci.get("run_attempt"),
            "conclusion": ci.get("conclusion"), "result": FAIL if p else PASS}, p


def decide(ev: dict, evidence_sha256: str | None = None) -> dict:
    """The readiness record over the evidence ``collect`` read. Pure: no I/O, no clock."""
    problems: list[str] = []
    ev = ev if isinstance(ev, dict) else {}
    if ev.get("schema") != EVIDENCE_SCHEMA or ev.get("program") != SN.PROGRAM_ID:
        problems.append(f"EVIDENCE: schema {str(ev.get('schema'))[:60]}, program {str(ev.get('program'))[:60]}")
    commit, slug = ev.get("commit"), ev.get("repository")
    if not isinstance(commit, str) or not SHA.fullmatch(commit):
        problems.append(f"EVIDENCE: {str(commit)[:60]!r} is not a full commit sha")
        commit = None
    named = ev.get("named") if isinstance(ev.get("named"), dict) else {}
    if set(named) != set(PL.ALL_TESTS):
        problems.append(f"NAMES: the evidence names {sorted(named)}, not {list(PL.ALL_TESTS)}")
    ids = [v for v in named.values()]
    if any(not isinstance(i, int) or isinstance(i, bool) for i in ids) or len(set(map(str, ids))) != len(ids):
        problems.append(f"NAMES: every test names one run id, each a different run: {named}")
    runs = {r.get("id"): r for r in ev.get("runs") or [] if isinstance(r, dict)}
    tests: dict[str, dict] = {}
    for test in PL.RUN_TESTS:
        run = runs.get(named.get(test))
        if run is None:
            problems.append(f"NAMES: {test} names run {named.get(test)}, which is not a readiness run in the evidence")
            tests[test] = {"run_id": named.get(test), "result": FAIL}
            continue
        p = _provenance(test, run, commit, slug)
        rows, q = _jobs(test, run)
        gate, r = _gate(test, run, commit, slug)
        verdicts, s = _verdicts(test, run, commit)
        mine = p + q + r + s
        problems += mine
        tests[test] = {"run_id": run.get("id"), "workflow": PL.workflow_of(test), "title": run.get("display_title"),
                       "created_at": run.get("created_at"), "conclusion": run.get("conclusion"),
                       "result": FAIL if mine else PASS, "gate": gate, "verdicts": verdicts, "jobs": rows,
                       "billed_minutes": sum(x["billed_minutes"] for x in rows),
                       "seconds": round(sum(x["seconds"] or 0 for x in rows), 1)}
    tests["RT-0"], p = _rt0(ev.get("ci_run"), named.get("RT-0"), commit, slug)
    problems += p
    # one snapshot: the one RT-1 published, read by every test that reads a snapshot
    rt1 = ((tests.get("RT-1") or {}).get("verdicts") or {}).get(PL.TESTS["RT-1"][2][0]) or {}
    address = (rt1.get("measurements") or {}).get("address")
    if not (isinstance(address, str) and SN.DIGEST.fullmatch(address)):
        problems.append(f"SNAPSHOT: RT-1 names no snapshot address ({str(address)[:80]})")
        address = None
    for test in sorted(PL.NEEDS_SNAPSHOT):
        got = ((tests.get(test) or {}).get("gate") or {}).get("release")
        if address is not None and got != address:
            problems.append(f"SNAPSHOT: {test} read the snapshot {got}, not RT-1's {address}")
    # the readiness ledger, by the gate's own function
    led = RG.ledger([r for r in runs.values()], None)
    problems += [f"LEDGER: {x}" for x in led["problems"]]
    if led["minutes"] > PL.READINESS_CAP:
        problems.append(f"LEDGER: {led['minutes']} billed readiness minutes > the cap {PL.READINESS_CAP}")
    # the slowest measured run of every job that works as a workload (OD-S8: final timeouts >= 2x)
    measured: dict[str, dict] = {}
    for test in PL.RUN_TESTS:
        for row in (tests.get(test) or {}).get("jobs") or []:
            if row["designed_end"] != "success" or row["seconds"] is None:
                continue
            cur = measured.get(row["name"])
            if cur is None or row["seconds"] > cur["seconds"]:
                measured[row["name"]] = {"seconds": row["seconds"], "test": test, "run_id": tests[test]["run_id"],
                                         "timeout_minutes": row["timeout_minutes"],
                                         "twice_minutes": math.ceil(2 * row["seconds"] / 60)}
    problems = list(dict.fromkeys(problems))
    return {"schema": RECORD_SCHEMA, "program": SN.PROGRAM_ID, "repository": slug, "commit": commit,
            "INFRA_READINESS": FAIL if problems else PASS, "problems": problems,
            "tests": {t: tests[t] for t in PL.ALL_TESTS if t in tests},
            "snapshot": {"address": address, "tag": RL.tag_for(address) if address else None,
                         "tar_sha256": (rt1.get("measurements") or {}).get("tar_sha256"),
                         "release": ((rt1.get("measurements") or {}).get("release") or {})},
            "ledger": {"minutes": led["minutes"], "cap": PL.READINESS_CAP, "runs": led["runs"]},
            "measured": dict(sorted(measured.items())), "collected_utc": ev.get("collected_utc"),
            "evidence_sha256": evidence_sha256, "real_money_authorized": False, "dry_run": True}


# -- bundle ------------------------------------------------------------------------------------------

def build(evidence_bytes: bytes) -> dict[str, bytes]:
    """The bundle's three files from the evidence bytes alone."""
    try:
        ev = json.loads(evidence_bytes)
    except ValueError:
        ev = None
    body = dumps(decide(ev, hashlib.sha256(evidence_bytes).hexdigest()))
    files = {EVIDENCE: evidence_bytes, RECORD: body}
    files[SUMS] = "".join(f"{hashlib.sha256(b).hexdigest()}  {n}\n" for n, b in sorted(files.items())).encode()
    return files


def verify(directory: Path) -> list[str]:
    """Why the bundle in ``directory`` is not exactly what its evidence builds ([] when it is)."""
    try:
        raw = (directory / EVIDENCE).read_bytes()
    except OSError as exc:
        return [f"{EVIDENCE}: {exc}"]
    want = build(raw)
    p = []
    for name in (RECORD, SUMS):
        try:
            got = (directory / name).read_bytes()
        except OSError as exc:
            p.append(f"{name}: {exc}")
            continue
        if got != want[name]:
            p.append(f"{name}: differs from what {EVIDENCE} builds")
    extra = sorted(x.name for x in directory.iterdir() if x.name not in want) if directory.is_dir() else []
    p += [f"{name}: not part of the bundle" for name in extra]
    return p


def live_problems(evidence: dict, live: dict) -> list[str]:
    """Where the evidence differs from what the API says now. Runs created after the evidence was collected are
    later runs, not differences, but they still count in the live ledger, which must stay within the cap; every
    run the evidence holds must be unchanged, and its collection time must fall between its newest run and now."""
    p = []
    cut = evidence.get("collected_utc") or ""
    old = {r.get("id"): r for r in evidence.get("runs") or []}
    new = {r.get("id"): r for r in live.get("runs") or []}
    for i, r in old.items():
        if new.get(i) != r:
            p.append(f"run {i}: the evidence differs from the API")
    for i, r in new.items():
        if i not in old and (r.get("created_at") or "") <= cut:
            p.append(f"run {i}: created {r.get('created_at')}, before the evidence was collected, and left out")
    newest = max((r.get("created_at") or "" for r in old.values()), default="")
    if not cut or cut < newest or cut > (live.get("collected_utc") or ""):
        p.append(f"collected_utc {cut!r} is not between the evidence's newest run ({newest}) and now")
    led = RG.ledger(list(new.values()), None)
    if led["problems"] or led["minutes"] > PL.READINESS_CAP:
        p.append(f"the live readiness ledger is {led['minutes']} billed minutes over every run the API lists now "
                 f"(cap {PL.READINESS_CAP}){'; ' + '; '.join(led['problems'])[:200] if led['problems'] else ''}")
    if evidence.get("ci_run") != live.get("ci_run"):
        p.append("the RT-0 CI run differs from the API")
    for k in ("schema", "program", "repository", "commit", "named"):
        if evidence.get(k) != live.get(k):
            p.append(f"{k}: the evidence says {str(evidence.get(k))[:80]}, now {str(live.get(k))[:80]}")
    return p


# -- CLI ---------------------------------------------------------------------------------------------

def _named(pairs: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for pair in pairs:
        m = re.fullmatch(r"(RT-(?:\d|1[01]))=(\d{1,20})", pair)
        if not m or m[1] not in PL.ALL_TESTS or m[1] in out:
            raise SystemExit(f"--run {pair!r}: expected RT-n=RUN_ID, each test once")
        out[m[1]] = int(m[2])
    if set(out) != set(PL.ALL_TESTS):
        raise SystemExit(f"--run must name every test {list(PL.ALL_TESTS)}; missing {sorted(set(PL.ALL_TESTS) - set(out))}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--repo-slug", required=True)
    c.add_argument("--commit", required=True)
    c.add_argument("--run", action="append", default=[], help="RT-n=RUN_ID, once per test (RT-0: the CI run)")
    c.add_argument("--out", required=True)
    b = sub.add_parser("build")
    b.add_argument("--evidence", required=True)
    b.add_argument("--out-dir", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--dir", required=True)
    k = sub.add_parser("check-live")
    k.add_argument("--repo-slug", required=True)
    k.add_argument("--dir", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "collect":
        if not SHA.fullmatch(a.commit):
            raise SystemExit(f"{a.commit[:50]!r} is not a full commit sha")
        ev = collect(RL.GH(a.repo_slug), a.commit, _named(a.run), datetime.now(timezone.utc))
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_bytes(dumps(ev))
        print(f"evidence: {len(ev['runs'])} readiness run(s) -> {a.out}")
        return 0
    if a.cmd == "build":
        files = build(Path(a.evidence).read_bytes())
        out = Path(a.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        for name, body in files.items():
            (out / name).write_bytes(body)
        rec = json.loads(files[RECORD])
        for line in rec["problems"][:60]:
            print(f"  {line}")
        print(f"INFRA_READINESS = {rec['INFRA_READINESS']} (ledger {rec['ledger']['minutes']} of "
              f"{rec['ledger']['cap']} minutes; commit {rec['commit']})")
        return 0 if rec["INFRA_READINESS"] == PASS else 3
    if a.cmd == "verify":
        p = verify(Path(a.dir))
        for line in p:
            print(f"  {line}")
        rec = json.loads((Path(a.dir) / RECORD).read_bytes()) if not p else {}
        print(f"READINESS_RECORD_VERIFY = {'FAIL' if p else 'PASS'}"
              f"{'' if p else ' (INFRA_READINESS = ' + rec['INFRA_READINESS'] + ')'}")
        return 3 if p or rec.get("INFRA_READINESS") != PASS else 0
    ev = json.loads((Path(a.dir) / EVIDENCE).read_bytes())
    live = collect(RL.GH(a.repo_slug), ev["commit"], ev["named"], datetime.now(timezone.utc))
    p = live_problems(ev, live)
    for line in p:
        print(f"  {line}")
    print(f"READINESS_EVIDENCE_LIVE = {'FAIL' if p else 'PASS'}")
    return 3 if p else 0


if __name__ == "__main__":
    sys.exit(main())
